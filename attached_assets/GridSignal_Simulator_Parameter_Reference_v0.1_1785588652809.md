# GridSignal Simulator — Calculation and Parameter Reference

**Version 0.1 — companion to Forecast Engine Functional Specification v2.5**

---

## 0. Purpose, audience, and status

This document consolidates two things that are currently scattered: the exact arithmetic
the simulator must implement, and the assumptions baked into every constant that arithmetic
consumes.

**Two audiences, one document.**

- *A human reviewer* should be able to read Sections 2–4 and reproduce every number by hand.
- *A coding agent* should treat `gridsignal_parameters.json` as the single source of truth for
  defaults, ranges, and UI control types, and this document as the rationale for why each is
  what it is. **Do not hard-code any value from this document into application code.** Load it
  from the JSON. If a value appears in both and they disagree, the JSON wins and this document
  is stale.

**Status.** The arithmetic in Section 2 is exact and testable today. Almost every *input* to it
is an estimate. Section 5 states which is which, per parameter, and that distinction is the most
important content here — it is what separates a specification defect from an uncalibrated
constant, and those need different responses.

**Scope.** This covers the control-plane calculation chain and its parameters. It does not cover
the learning plane (v2.5 §21), persistence (§22), or the K8s/Slurm adapter, which is specified
but unbuilt.

---

## 1. Notation and units

| Symbol | Meaning | Unit |
|---|---|---|
| `N_i(t)` | Active node count for job instance *i* | nodes |
| `kW_i` | Per-node power draw for the hardware profile of job *i* | kW |
| `PUE_base` | Non-cooling overhead multiplier (distribution, conversion, UPS) | dimensionless |
| `P_compute(t)` | Instantaneous compute draw including `PUE_base` | MW |
| `α(t)` | Incremental cooling fraction, time-varying | dimensionless |
| `α_max` | Steady-state value of `α` | dimensionless |
| `Δt_thermal` | Delay before cooling begins responding at all | s |
| `τ` | Cooling rise-time constant | s |
| `P_cooling(t)` | Cooling draw attributable to compute | MW |
| `P_total(t)` | Site draw | MW |
| `P_renewable(t)` | Non-dispatchable supply (measured/forecast, never commanded) | MW |
| `P_dispatch_required(t)` | Load the controllable fleet must serve | MW |
| `ΔP` | Step change in `P_dispatch_required` | MW |
| `Δt_lead` | Allocation event → GPUs at full TDP | s |
| `r_asset` | Turbine mechanical ramp rate | MW/s |
| `t_ramp` | Time for turbines to reach `ΔP` | s |
| `t_gap` | Window BESS alone must bridge | s |
| `P_anchor_reserve` | Headroom withheld from a grid-forming BESS for V/f regulation | MW |
| `P_bridge_avail` | Anchor-adjusted BESS bridging capability | MW |

**Unit discipline.** `kW_i` is kilowatts and everything downstream is megawatts; the `/1000` in
§2.1 is the only place that conversion happens. A discharge *duration* (seconds) is never
compared against `MW × seconds` (an energy-like quantity) — v2.5 §7.2 step 4 calls this out
explicitly because it is an easy and silent error.

---

## 2. The calculation chain

Evaluated on every validated WorkloadSignal event, plus a fixed 5-second tick to advance the
lag models between events (v2.5 §3.1).

### 2.1 Compute term — instantaneous

```
P_compute(t) = Σᵢ [ N_i(t) × kW_i ] × PUE_base / 1000
```

The sum is over **job instances**, not hardware profiles. Two concurrent jobs on identical
hardware superpose; they do not collapse into one term (§11.1). `PUE_base` covers only overhead
responding on the same timescale as compute — never active cooling, which would double-count
against §2.2.

### 2.2 Cooling term — lagged, first-order rise

```
α(t) = α_max × (1 − e^−(t − t₀ − Δt_thermal)/τ)     for t ≥ t₀ + Δt_thermal
α(t) = 0                                            otherwise

P_cooling(t) = α(t) × P_compute(t − Δt_thermal)
```

`t₀` is compute step-load onset. The rise is deliberately continuous: a step function would
alias as a second instantaneous event to the dispatch controller (§8).

### 2.3 Total and net

```
P_total(t)             = P_compute(t) + P_cooling(t)
P_dispatch_required(t) = P_total(t) − P_renewable(t)
```

Steady-state effective PUE = `PUE_base × (1 + α_max)`. Validate against site nameplate at
commissioning (§4.3, §12).

**`ΔP` is a change in `P_dispatch_required`, not in `P_total`.** A compute step-load and a
collapse in renewable output are the same event class to the arbitrator. The compound case is
additive and is the worst case the reserve check must size against (§7.1.1).

### 2.4 Ramp and bridging arithmetic

```
t_ramp              = ΔP / r_asset
t_gap               = t_ramp − Δt_lead                    (when positive)
turbine_output(t)   = min(ΔP, r_asset × (t − t_stage))
BESS_output(t)      = max(0, P_total(t) − turbine_output(t))
peak_shortfall      = ΔP − (r_asset × Δt_lead)
E_bridge            = ½ × peak_shortfall × t_gap / 3600    (MWh)
```

Turbine ramp starts at the **prediction** (job `starting` event), not at load arrival, which is
why `peak_shortfall < ΔP`. The shortfall **declines linearly** from `peak_shortfall` to zero — it
is not a flat draw for the duration. BESS returns to standby once `turbine_output(t) ≥ P_total(t)`
holds for a sustained 10 s window.

### 2.5 Reserve check

```
P_bridge_avail = BESS_rated × f(SOC) − P_anchor_reserve
```

`P_anchor_reserve` applies only when the BESS is grid-forming (islanded). Grid-connected, the
utility is the reference and the term is zero. Anchor role must be **read from the power
management system**, not inferred from configuration (§7.1.2).

The check evaluates against the **confidence band, not the point estimate** (TC-17):

```
alert  ⟺  peak_shortfall × (1 + band_upper)  >  P_bridge_avail
```

`P_renewable` may reduce the load but may **never** count toward ramp capability. Solar cannot
be ramped to close a gap.

### 2.6 Checkpoint-valley classifier

Precedence: **scheduler event > power-shape heuristic > network corroboration**. Thresholds are
inclusive, not strict (§6.2):

```
drop      ≥ 15% of pre-drop P_compute
duration  5 s ≤ d ≤ 30 s
recovery  ≥ 90% of pre-drop level, within 45 s
```

All three satisfied → checkpoint, hold staging. Recovery fails → job end, release. Unresolved at
45 s → hold, flag `uncertain`; network corroboration may resolve early but may never override a
higher-precedence signal or shorten the hold when it disagrees.

---

## 3. Worked example

Inputs — a single admitted gang, islanded site, one turbine online:

```
N = 150 nodes          kW = 120 kW/node       PUE_base = 1.11
α_max = 0.20           Δt_thermal = 90 s      τ = 20 s
Δt_lead = 30 s         r_asset = 0.2 MW/s     P_renewable = 3.0 MW
BESS_rated = 15.0 MW   P_anchor_reserve = 1.0 MW   SOC factor = 1.0
```

**Compute term**

```
P_compute = 150 × 120 × 1.11 / 1000 = 19.98 MW
```

**Cooling term** (`P_compute` at full for the lagged argument)

| t | t − t₀ − Δt_thermal | α(t) | P_cooling |
|---|---|---|---|
| 0–90 s | < 0 | 0 | 0.00 MW |
| 110 s | 20 s (1τ) | 0.126424 | 2.53 MW |
| 150 s | 60 s (3τ) | 0.190043 | 3.80 MW |
| 190 s | 100 s (5τ) | 0.198652 | 3.97 MW |
| ∞ | — | 0.200000 | 4.00 MW |

**Total, net, effective PUE**

```
P_total(∞)             = 19.98 + 4.00 = 23.98 MW
P_dispatch_required(∞) = 23.98 − 3.00 = 20.98 MW
effective PUE          = 1.11 × 1.20  = 1.332
```

**Ramp arithmetic** — solar is flat, so the step is the compute term: `ΔP = 19.98 MW`

```
t_ramp         = 19.98 / 0.2      = 99.90 s
t_gap          = 99.90 − 30       = 69.90 s
turbine(T+30)  = 0.2 × 30         =  6.00 MW
peak_shortfall = 19.98 − 6.00     = 13.98 MW   at T+30 s
E_bridge       = ½ × 13.98 × 69.9 / 3600 = 0.1357 MWh
```

Shortfall declines linearly from 13.98 MW at T+30 to 0 at T+99.9.

**Reserve check**

```
P_bridge_avail = 15.0 − 1.0 = 14.00 MW
point estimate : 13.98 required  vs 14.00 available  →  passes by 0.02 MW
band upper 8%  : 15.10 required  vs 14.00 available  →  ALERT, 1.10 MW short
```

Alert fires at T+0, reporting a 1.10 MW shortfall across a 69.9 s window, leaving ~30 s of lead
time for operator intervention.

> The 8% band figure is **illustrative only**. v2.5 §12 and §17.3 require a band and require it to
> widen for uncalibrated sites, unmapped hardware, and quarantine-touched inputs; they do not fix
> the magnitude. See PARAM-13 in Section 5.

**Three readings worth taking from this example:**

1. The binding constraint is **power, not energy**. 0.1357 MWh against a multi-MWh pack is
   nothing; the pack fails the check on instantaneous discharge capability.
2. Omitting `P_anchor_reserve` yields 15.0 MW available and the check passes even on the band.
   That is precisely the "passes shortly before a frequency excursion" failure §7.1.2 exists to
   prevent.
3. The point estimate passes by 0.02 MW and the band fails by 1.10 MW. Any implementation that
   checks the point estimate will look correct in almost every demo and be wrong when it matters.

**Checkpoint thresholds** against this baseline: drop ≥ 2.997 MW, duration 5–30 s, recovery to
≥ 17.982 MW within 45 s.

---

## 4. The plant/engine parameter split

**The single most important structural point in this document.**

At a real site, `Δt_thermal` is *physics in the plant* and *a configuration value in the engine*.
They will differ — being wrong is the guaranteed initial state at every new site, which is exactly
why §17.3 puts every new site into `uncalibrated_site`.

A simulator that uses one shared constant for both **structurally cannot exhibit the failure mode
the product is designed to survive.** Every parameter marked `split: true` in the JSON therefore
carries two values:

```
plant.Δt_thermal  = 65 s   ← what the simulated chillers actually do
engine.Δt_thermal = 90 s   ← what the forecast believes
```

Run with these unlinked and the questions become answerable: does the reserve check still hold?
Does the confidence band cover the error, or does the point estimate sail through while reality
diverges? Whether §17.3's uncalibrated widening is sized correctly is currently an assertion. This
turns it into a result.

**UI requirement.** Not two hidden tabs. Two adjacent columns with a link control defaulted ON, so
that unlinking is a visible, deliberate act.

**Non-split parameters** (`split: false`) are engine-side configuration with no physical
counterpart — confidence band widths, alert tier, tick rate.

---

## 5. Parameter register

Provenance classes, applied per parameter:

| Class | Meaning |
|---|---|
| `MEASURED` | From an operating site. **Currently: none.** |
| `VENDOR_RATING` | Manufacturer nameplate; not observed draw |
| `SPEC_DEFAULT` | Value and range both fixed in v2.5 |
| `ESTIMATE` | Value in v2.5, no range given; midpoint or judgement |
| `PROPOSED_HERE` | Not in v2.5 at all; introduced by this document and needs review |
| `CONFORMANCE` | Constant under acceptance test — **not user-adjustable** |

### 5.1 Slider controls

| ID | Parameter | Default | Range | Source | Provenance | Split |
|---|---|---|---|---|---|---|
| PARAM-01 | `Δt_lead` | 45 s | 30–60 s | §9 | `SPEC_DEFAULT` | yes |
| PARAM-02 | `Δt_thermal` | 90 s | 60–120 s | §9 | `SPEC_DEFAULT` (midpoint) | yes |
| PARAM-03 | `α_max` | 0.20 | 0.10–0.30 | §8 | `SPEC_DEFAULT` | yes |
| PARAM-04 | `τ` | 20 s | 10–40 s | §8 value; **range proposed** | `PROPOSED_HERE` (range) | yes |
| PARAM-05 | `r_asset` | 0.2 MW/s | 0.1–0.5 MW/s | §7.1 value; **range proposed** | `PROPOSED_HERE` (range) | yes |
| PARAM-06 | `PUE_base` | 1.11 | 1.05–1.30 | §4.1; **range proposed** | `PROPOSED_HERE` (range) | yes |
| PARAM-07 | `BESS_rated` | 15.0 MW | 1–50 MW | site config | `VENDOR_RATING` | no |
| PARAM-08 | `SOC` | 100% | 0–100% | §7.2 | `SPEC_DEFAULT` | yes |
| PARAM-09 | `P_anchor_reserve` | 8% of rated | 0–20% of rated | §7.1.2 — "conservative fraction, **never zero**" | `PROPOSED_HERE` (number) | no |
| PARAM-10 | `P_renewable` | 3.0 MW | 0–20 MW | §7.1.1 | scenario-driven | plant only |
| PARAM-11 | `kW` per node | — | — | §5 library | `VENDOR_RATING` | **see 5.3** |
| PARAM-13 | Band width, calibrated | ±4% | 0–15% | §12 requires band, not magnitude | `PROPOSED_HERE` | no |
| PARAM-14 | Uncalibrated widening | ×2.0 | 1.0–4.0 | §17.3 | `PROPOSED_HERE` | no |
| PARAM-15 | Unmapped-hardware widening | ×1.5 | 1.0–4.0 | §5.1 | `PROPOSED_HERE` | no |

Six of fifteen slider defaults are `PROPOSED_HERE`. That is worth seeing plainly rather than
discovering later.

### 5.2 Pull-down controls

| ID | Control | Options | Note |
|---|---|---|---|
| PARAM-20 | `hardware_profile_id` | library keys + `generic_fallback` | Drives PARAM-11 |
| PARAM-21 | `workload_class` | training / inference / other | Selects load-signature model |
| PARAM-22 | Turbine count | 1 / 2 / 3 / 4 | **Integer, never a slider.** Ramp scales with unit count, not MW: 3 × 15 MW gives 3× the step response of 1 × 25 MW |
| PARAM-23 | Grid mode | grid-connected / islanded | Gates whether PARAM-09 applies at all |
| PARAM-24 | Operating tier | Advisory / Supervised / Autonomous | Changes alert behavior per NFR-4 |
| PARAM-25 | Clock discipline | NTP / PTP / declared-PTP-actually-NTP | Third option exercises TC-70 |
| PARAM-26 | Fabric signal tier | legacy / current / emerging | Degrades roles, never ingestion (TC-71) |
| PARAM-27 | Scenario preset | named scenarios | Loads a full parameter set |

### 5.3 Deliberately excluded from the modal

| Excluded | Reason |
|---|---|
| `kW` per node as a free field | Derived from PARAM-20. Editing it independently decouples the library from the forecast and silently disables the §5.1 unmapped-hardware path. **The profile dropdown is the kW control.** |
| Checkpoint thresholds (15% / 5–30 s / 90% / 45 s) | `CONFORMANCE`. A slider lets a demo invalidate TC-06…TC-09 with nobody noticing. Display read-only — an engineer asking "where does 15% come from" wants to see it, not move it |
| 5 s tick, 10 s reorder buffer, 10 s taper window | `CONFORMANCE` (§3.1, §11.3, §7.2) |
| NFR budgets (2 s decision→command, <100 ms BESS) | `CONFORMANCE`. Adjusting a requirement to pass a test inverts the test |
| Do-not-touch register (alert latch, `bridging_basis`, interval-end timestamps, decimation) | Established during the build; regression surface |
| `kW` as a time-varying function | Modelling GPU utilization — the reactive signal the product is positioned against. The legitimate dynamic is the `Δt_lead` ramp shape (0 → full TDP), which is separate |

---

## 6. Dynamic behavior: what may vary, and when

Three distinct capabilities. Only two are worth building.

**6.1 Sweep across runs — build first.** Hold each constant fixed within a run, vary between runs,
record which acceptance cases flip. Produces a sensitivity ranking that answers "which measurement
should we buy first from a design partner," which is currently unanswerable.

**6.2 Plant/engine divergence — highest value.** Section 4. This is the one that tests whether the
confidence machinery does real work.

**6.3 Time-varying within a run — `r_asset` only.** Ramp rate is genuinely not constant: cold vs.
warm, ambient derate, and a discontinuous step when a unit trips or a second comes online. Model
`r_asset(t)`. Leave the other four static within a run; `α_max` drifts with wet-bulb on a seasonal
clock, not a 100-second one.

**The governing constraint:**

> A scenario may vary a parameter. The engine may not assume one varies.

Injecting drift as a stressor is a test. Giving the forecast model a time-varying `Δt_thermal`
with no measured basis replaces a known-provisional constant with a provisional function — more
free parameters, less falsifiable. §8.2 already declines to do this for liquid cooling, and for
the same reason.

Mechanically, `param_drift` is the same shape as the existing `turbine_fault` and
`clock_skew_inject` stressors.

---

## 7. Invariants

Properties an implementation must preserve. Each is testable; several are already covered in
Addendum A.

| ID | Invariant | Ref |
|---|---|---|
| INV-1 | `PUE_base` and `α(t)` are mutually exclusive overhead buckets. No cooling term appears in both | §4, TC-01 |
| INV-2 | Reserve check evaluates the band, never the point estimate | TC-17 |
| INV-3 | Reserve check uses the **anchor-adjusted** figure whenever the BESS is grid-forming | §7.1.2 |
| INV-4 | `P_renewable` reduces load; it never contributes to ramp capability | §7.1.1 |
| INV-5 | BESS shortfall declines linearly; it is never modelled as a flat draw | §7.3 |
| INV-6 | A duration is never compared against an energy-like quantity | §7.2 step 4 |
| INV-7 | A parameter change mid-run is a scenario event, not a silent mutation — a run must be reproducible from its inputs | §21.1 |
| INV-8 | No model inference in the control path. Loss of every model vendor suspends Proposals only | LP-1, TC-28 |
| INV-9 | Superposition is per job instance, not per hardware profile | §11.1 |
| INV-10 | `NetworkTelemetry` is dispatch-path ineligible by contract | TC-74 |

---

## 8. Provenance summary — the design-partner ask

Every parameter in Section 5 carries a provenance class, surfaced in the UI as a status dot. As of
v0.1:

- `MEASURED`: **zero parameters**
- `SPEC_DEFAULT` / `ESTIMATE`: the physical time constants
- `VENDOR_RATING`: `kW` per node, `BESS_rated` — nameplate, not observed draw
- `PROPOSED_HERE`: six slider defaults or ranges, plus all three confidence-band figures

A settings panel that does not display this implies more calibration than exists. Displaying it
makes the design-partner conversation concrete: the ask is to convert specific amber dots to
green, in priority order set by the Section 6.1 sensitivity sweep.

**The four measurements that would move the most, in rough order:**

1. `kW` per node under real training load, by profile — observed draw against nameplate
2. `Δt_thermal` and `τ` from measured chiller response, per cooling topology
3. `r_asset` per turbine make/model, cold and warm
4. `Δt_lead` distribution across job types — the sharpest exposure, because it is a *software*
   artifact and shrinks as image caching and weight loading improve (§9, §15)

---

## 9. Open items

| ID | Item |
|---|---|
| OI-1 | `P_anchor_reserve` is a property of the island's dynamic stability study, not the battery nameplate. The 8% default is a placeholder pending a commissioning value |
| OI-2 | Confidence band magnitudes (PARAM-13/14/15) are unspecified in v2.5. Needs a decision, not a default |
| OI-3 | No subscription-semantics table for `WorkloadSignal` parallel to §25.4's for `NetworkTelemetry` — watch vs. poll-with-interval vs. push is undeclared per source |
| OI-4 | Node-label → `hardware_profile_id` convention is unspecified. This is the field the real adapter must derive and the simulator supplies literally, so the §5.1 fallback is currently unreachable except by injection |
| OI-5 | Genset-anchor droop dynamics are outside the §7 ramp model (PX-2) |
| OI-6 | `f(SOC)` — how state of charge derates bridging capability — is asserted but never given a form |

---

*Companion file: `gridsignal_parameters.json` — machine-readable, authoritative for defaults,
ranges, and UI control types. Generate the settings modal from it rather than hand-coding controls.*
