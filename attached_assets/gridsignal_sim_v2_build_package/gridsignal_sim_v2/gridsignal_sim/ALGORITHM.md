# GridSignal Simulator — Algorithm Reference

## Architecture overview

GridSignal is a **deterministic, synchronous simulation** of a data-centre power plant. Every 5-second tick the same function, `evaluate_tick()`, is called in a fixed step order. There are no random numbers inside a tick; all stochastic input (Kubernetes arrivals, solar irradiance) is resolved *before* the tick begins and stored as scripted events. This makes any run byte-for-byte reproducible from its scenario spec alone.

The codebase is split into three planes:

| Plane | Role |
|---|---|
| `core/` | Synchronous, side-effect-free arithmetic (the "deterministic core") |
| `runtime/` | Async run management, persistence, WebSocket broadcast, solar pre-generation |
| `api/` | FastAPI routes and Pydantic schemas |

`core/` has zero knowledge of `asyncio`. `runtime/` calls `evaluate_tick()` exactly once per tick inside an async loop; `evaluate_tick()` never calls back into `runtime/`.

---

## Step 0 — Kubernetes demand agent (optional)

**File:** `core/kube_demand.py` · `KubeDemandAgent.tick()`

When a scenario enables the Kubernetes path (`kube_config` in `ScenarioSpec`), the agent runs **before** every other module so its node-count changes take effect in the same tick's power calculation.

**Algorithm:**

1. **Poisson arrivals** — new gang-admission events are generated using an exponential inter-arrival distribution (`mean_interarrival_s`, default 60 s). Each job's size is drawn from a Gaussian (`mean_job_nodes = 200, σ = 80`) and its duration from an exponential (`mean_job_duration_s = 300 s`). Both are clipped to their physical floors.

2. **10-second reorder buffer** — events sit in a buffer for `reorder_window_s = 10 s` to simulate NTP jitter (±2 s). They are drained in `event_timestamp` order, honouring the real ordering guarantee.

3. **Capacity validation** — admissions that would push the cluster above `max_nodes = 1900` are dropped.

4. **Power-cap hold** — when grid headroom (turbine + BESS) < `headroom_threshold_mw = 2.5 MW`, new admissions are re-queued 5 seconds later rather than admitted. The job is never lost.

5. **Critical eviction** — when headroom turns negative, the largest running job is immediately evicted to recover headroom fastest.

6. **WorkloadSignal emission** — whenever total admitted node count changes a `STARTING` or `SCALE` `WorkloadSignal` is emitted with `dt_lead_seconds = 0` (Kubernetes gives no advance notice to the grid). This is the key GridSignal value proposition: the BESS must bridge every ramp with zero warning.

The agent passes the `KubeMetrics` snapshot (utilisation, active jobs, power-cap status) through `TickResult` to the live UI.

---

## Step 1 — GPU compute term

**File:** `core/asset_modules.py` · `GPUModule`

**Formula:**

```
P_compute(t) = Σ_jobs  nodes_k × kW_k × PUE_base / 1000  ×  ρ(progress_k)
```

where `kW_k` comes from the hardware profile library and `ρ(progress)` is the **Δt\_lead ramp multiplier**:

| Phase | Progress range | Output fraction |
|---|---|---|
| Container init | 0–20 % | 0 → 0.05 (linear) |
| Weight load | 20–70 % | 0.05 → 0.95 (linear) |
| Collective warmup | 70–100 % | 0.95 → 1.00 (linear) |

`ramp_seconds = 45 s` (§6.1 specifies 30–60 s; exact curve is `PROTO-1`). On each tick, `advance()` increments `progress += dt / ramp_seconds` and clamps at 1.0. This means power rises realistically from near-zero at `STARTING` to full TDP over the lead window. A `SCALE` event snaps progress to 1.0 (already-live node count change, no cold-start delay).

**Why this matters for dispatch:** The staging calculation (Step 4 pre-staging) must use the *target* TDP (`per_job_target_mw()`, ignoring ramp), not the current draw (~0 at `STARTING`), or the turbine would stage for nothing and the BESS would receive no advance notice.

---

## Step 2 — Cooling term (lagged superposition)

**File:** `core/asset_modules.py` · `CoolingModule`

**Formula per job k:**

```
α_k(t) = α_max × (1 − e^{ −(t − t₀ₖ − Δt_thermal) / τ })    for t ≥ t₀ₖ + Δt_thermal
       = 0                                                       otherwise

P_cooling(t) = Σ_k  α_k(t) × P_compute_k(t − Δt_thermal)
```

**Parameters (from `SiteConfig`):**

| Symbol | Name | Default |
|---|---|---|
| `Δt_thermal` | Thermal lag (HVAC response time) | 90 s |
| `τ` | Cooling time constant | 20 s |
| `α_max` | Max fractional cooling overhead | 0.20 |

Each job gets its own `_LoadEnvelope` seeded from the `STARTING` event timestamp `t₀ₖ`. The engine **never** infers onset from aggregate draw shape (§8 requirement). This means:
- A second job's cooling rises from zero after its own lag — no aliasing into an already-settled α.
- When a job ends, its heat stays in the room. The envelope is retained for `Δt_thermal + 5τ = 190 s` after `end_t` so the lagged compute term drains smoothly rather than dropping discontinuously.

**Steady-state identity:** At full saturation `Σ_k α_k × P_k = α_max × P_compute`, giving effective PUE = `PUE_base × (1 + α_max)`.

**Total site load:**
```
P_total(t) = P_compute(t) + P_cooling(t)
```

---

## Step 3 — Solar offset

**File:** `core/asset_modules.py` · `SolarModule` / `IrradianceProfile`

Solar is evaluated **before** arbitration so the fleet sizes against `P_dispatch_required`, not `P_total`:

```
P_dispatch_required(t) = max(0,  P_total(t) − P_renewable(t))
```

`P_renewable` can vanish without notice (inverter trip, cloud shadow → `Δt_lead = 0`). It is structurally absent from ramp capability calculations; the arbitrator never counts solar toward what it can ramp.

**Irradiance profile:** A list of `(sim_time_s, fraction)` samples with zero-order hold ("value applies from t onward"). The profile is generated *once* at run start by `runtime/solar_sim.py` (see Appendix A) and stored in the scenario spec as `irradiance_steps`. During ticks, `SolarModule.advance()` calls `IrradianceProfile.fraction_at(sim_time)` and multiplies by rated MW.

---

## Step 3a — Phase 0: Pre-staging (shiftable thermal load)

**File:** `core/dispatch.py` · `PreStagingEngine`

When `SiteConfig.pre_staging_config` is set, the HVAC's thermal mass is used as a shiftable load. Pre-staging pre-cools the data hall during low-demand periods, reducing `P_dispatch_required` ahead of a predicted demand peak.

```
P_dispatch_required -= min(max_shift_mw, available_cooling_headroom)
```

Bounds:
- Inlet temperature must stay inside `[inlet_temp_low_c, inlet_temp_high_c]` = [18 °C, 24 °C].
- BMS override (`bms_override = True`) returns 0 unconditionally — the BMS retains physical authority regardless of GridSignal.

This is **not** a rung on the curtailment ladder; it is a gap-reduction phase that runs before the fleet dispatch (Step 4) and before the ladder (Step 4d).

---

## Step 3b — PMS tick (Power Management System)

**File:** `core/scada_layer.py` · `SimulatedPMS`

When `SiteConfig.pms_config` is set, the PMS ticks before arbitration:

1. **Fast shed** — the PMS can issue a load-shed that pre-empts GridSignal. While `pms_fast_shed_active = True`, the curtailment ladder is bypassed entirely (TC-64).
2. **Open-transition gap** — when the site transfers to island mode via an open-transition switch (the common case), there is a brief coverage discontinuity. The PMS adds `open_transition_gap_mw = 2.0 MW` to `P_dispatch_required` for `open_transition_duration_s = 5 s` so dispatchable assets must bridge the gap.

---

## Step 4 — Dispatch arbitration

**Files:** `core/dispatch.py` · `DispatchArbitrator`

Two structural asymmetries are enforced throughout:

1. **No lead time for renewables.** Solar has `Δt_lead = 0`; it never enters ramp capability calculations.
2. **Renewables are availability, not dispatchability.** `P_renewable` is removed by the caller before entering `tick()`; there is no renewable term to add or forget inside the arbitrator.

### 4.1 Turbine ramp

Each turbine ramps at `r_asset_mw_per_s = 0.2 MW/s` toward its staged target. On each tick:

```
output_mw += r_asset × dt,  clamped at target_mw
```

Turbines cover as much of `P_dispatch_required` as they can from their current output.

### 4.2 BESS shortfall coverage

The remaining gap after turbines is the **fleet shortfall**:

```
fleet_shortfall = max(0,  P_dispatch_required − turbine_output)
```

**Fleet allocation (D14 — equal-share-then-redistribute):**

Each active BESS unit receives an equal share of the remaining demand. Units that hit their `bridging_available_mw` ceiling are frozen there and the residual is redistributed equally among remaining units. Rounds continue until the demand is fully met or every unit is at its ceiling.

```python
# Pseudocode
remaining = fleet_shortfall
while remaining > ε:
    active = [i for i where weights[i] - allocations[i] > ε]
    share = remaining / len(active)
    for i in active:
        if share >= headroom[i]:
            allocations[i] = weights[i]     # cap
        else:
            allocations[i] += share
    remaining = fleet_shortfall - sum(allocations)
    if no unit hit its ceiling: break
```

Equal-share was chosen over proportional-by-ceiling because it drives small units to 100% of their ceiling first (the physically correct order) before falling to larger units.

**BESS discharge:**

```python
discharge_mw = min(allocated_mw, power_ceiling_mw, soc_mwh / (dt / 3600))
soc_mwh -= discharge_mw × (dt / 3600)
```

**Taper:** When turbines have covered `P_dispatch_required` continuously for 10 s (`_sustained_catchup_seconds ≥ 10`), the BESS tapers to standby (output = 0) to preserve state of charge.

### 4.3 Anchor reserve (island mode)

For a `grid_forming = True` BESS unit in `ISLANDED` mode, a power reserve is withheld to maintain frequency regulation headroom in both directions:

```
bridging_available_mw = rated_mw − p_anchor_reserve_mw
```

`p_anchor_reserve_mw = 1.0 MW` (CHOSEN, `PROTO-9`). This deduction propagates into every downstream calculation (allocation, `max_sustainable_seconds`, reserve check). In `GRID_TIE` mode or for grid-following units (`grid_forming = False`) the deduction is zero.

---

## Step 4 (pre-event) — Advance staging

**File:** `core/simulation_core.py` · `apply_workload_signal()` → `DispatchArbitrator.stage_for_predicted_step()`

At a job's `STARTING` event (before the tick), the arbitrator is staged for the predicted demand step:

```
delta_p_mw = max(0, P_target_after − P_renewable) − max(0, P_target_before − P_renewable)
```

`P_target` uses full-TDP values (ignoring ramp progress) because that is the load the turbine must be ready for when `Δt_lead` expires.

**Ramp time vs. lead time:**

```
required_ramp_s = delta_p_mw / total_r_asset
gap_s = required_ramp_s − dt_lead_seconds
```

If `gap_s ≤ 0` (sufficient lead time), no alert — the turbine can ramp in time. Otherwise:

```
already_ramped_mw = total_r_asset × dt_lead_seconds
peak_shortfall_mw = max(0, delta_p_mw − already_ramped_mw)
```

**Reserve check (INV-2, confidence band):**

The fleet power ceiling is checked against the *band-widened* shortfall:

```
band_upper = reserve_band_upper(is_unmapped_hw)
_check_shortfall = peak_shortfall_mw × (1 + band_upper)

if _check_shortfall > fleet_power_ceiling:
    → InsufficientReserveAlert (power-limited)
```

If power-limited, alert immediately. Otherwise, allocate `peak_shortfall_mw` across the fleet (equal-share D14) and check energy endurance:

```
fleet_endurance_s = min_over_units(
    max_sustainable_seconds(alloc_i, island_mode)
)

if fleet_endurance_s < gap_s:
    → InsufficientReserveAlert (energy-exhausted)
```

`min()` (not `sum()`) is correct because the first unit to empty sets the fleet limit. `sum()` overestimates endurance by up to N× (D13 fix).

**Band widening formula:**

```
base = band_pct_calibrated / 100
mult = band_mult_uncalibrated   if site.uncalibrated    else 1.0
mult ×= band_mult_unmapped_hw   if unmapped hardware    else 1.0
band_upper = base × mult
```

Default values: `band_pct_calibrated = 4%`, `band_mult_uncalibrated = 2.0×`, `band_mult_unmapped_hw = 1.5×`. At calibrated 4% × 2.0 uncalibrated = ±8% upper band, which is the worked-example regression value.

---

## Step 4d — Curtailment ladder

**File:** `core/dispatch.py` · `CurtailmentLadder`

After the fleet has done its best, if a remaining gap persists, the four-tier §23.2 curtailment ladder is observed:

| Tier | Action | Capacity | Human confirmation? |
|---|---|---|---|
| A | Defer new job submissions | 2 MW | No (AUTONOMOUS/SUPERVISED) |
| B | Cap running-job power | 5 MW | No |
| C | Checkpoint + suspend | 10 MW | **Always** |
| D | Preempt (terminate) | 20 MW | **Always** |

**Interlocks:**

- **TC-41 mandatory ordering** — never invoke B while A still has headroom. Tiers are proposed cumulatively from A upward.
- **TC-43 low-confidence** — any `DataQualityTag` (unmapped hardware or uncalibrated site) blocks all autonomous curtailment. A human must confirm any action.
- **TC-44 120-second dwell** — the gap must persist continuously for 120 s before any proposal is generated. A 20% recovery margin de-escalates the ladder.
- **TC-46 dead-man** — proposals expire after 300 s of continuous curtailment. If no release signal arrives, curtailment auto-releases and logs a control anomaly.
- **TC-64 PMS interlock** — if the PMS fast shed is active, the ladder is bypassed entirely this tick.

### §26.4 Unified candidate selection

All dispatched resources plus curtailment proposals are merged into one pool and sorted by a strict total order:

```
key = (ladder_position ASC, estimated_impact_mw DESC, candidate_id ASC)
```

Positions: STORAGE\_DISCHARGE=0, TURBINE\_RAMP=1, CURTAILMENT\_A\_B=4, CURTAILMENT\_C\_D=5. The greedy prefix of this sorted pool that closes the gap is selected. This is deterministic regardless of input ordering (TC-49).

---

## Step 5 — Checkpoint classification

**File:** `core/dispatch.py` · `CheckpointClassifier`

For each active training job, the per-job draw `per_job_compute_mw(job_id)` is tracked in a state machine:

```
NORMAL → IN_VALLEY → CHECKPOINT or JOB_END or UNCERTAIN
```

**Two-tier classification:**

1. **Explicit scheduler events** (primary): a `CHECKPOINT_START` signal immediately enters `IN_VALLEY` with `explicit_hold = True`. The hold prevents the 45-second heuristic timeout from releasing the state while the checkpoint write is still in progress. `CHECKPOINT_END` sets `CHECKPOINT`. A safety release fires after 900 s of uncleared hold (scheduler crash defence, `PROTO-3`).

2. **Shape heuristic** (fallback): a 15% drop below the 5-minute trailing median triggers `IN_VALLEY`. Recovery to ≥90% of baseline within 45 s → `CHECKPOINT`; 45 s elapsed without recovery → `UNCERTAIN` (30-second grace period before `JOB_END`).

`JOB_END` is terminal — once set it never transitions back, preventing oscillation that would confuse turbine ramp-down decisions (B-3 fix).

---

## Step 6 — Confidence banding

**File:** `core/dispatch.py` · `ConfidenceEngine`

Per-segment (not per-run) confidence tags are evaluated each tick:

- `UNMAPPED_HARDWARE` — any currently active job uses a profile not in the library.
- `UNCALIBRATED_SITE` — `SiteConfig.uncalibrated = True`.

These two tags govern both the curtailment-ladder interlock (Step 4d, TC-43) and the `ConfidenceBand` emitted on `TickResult`:

```python
confidence = ConfidenceBand(
    point_estimate_mw = p_total_mw,
    plus_minus_fraction = f(tags),
)
```

A sticky run-global flag was previously used; the per-tick check was introduced (Step 2) because an unmapped job that ended two hours ago must not tag the current segment (§5.1, §12).

---

## SCADA command recording (Step 11)

**File:** `core/scada_layer.py` · `SimulatedScadaLayer`

Every turbine setpoint, BESS dispatch, and autonomous curtailment command is logged to a deterministic audit record. Only three command types are permitted at the SCADA egress boundary: `TURBINE_SETPOINT`, `BESS_DISPATCH`, and `LOAD_CURTAILMENT`. Protection commands (islanding, droop) must never be issued by GridSignal.

If GridSignal's curtailment order disagrees with the PMS shed priority order, a commissioning defect is logged (TC-65). The PMS order is authoritative; GridSignal does not override it.

---

## TickResult

Each tick produces one frozen `TickResult` value object:

| Field | Description |
|---|---|
| `sim_time_seconds` | Interval **end** timestamp (= `sim_time + dt`) |
| `p_compute_mw` | GPU compute draw |
| `p_cooling_mw` | Lagged HVAC load |
| `p_total_mw` | Compute + cooling |
| `net_demand_mw` | `P_dispatch_required` (post-solar, post-pre-staging) |
| `p_renewable_mw` | Solar output (preserved; `net_demand` clamp is lossy) |
| `turbine_output_mw` | Turbine fleet contribution |
| `bess_output_mw` | BESS fleet contribution |
| `bess_soc_fraction` | State of charge (lead unit) |
| `bess_bridging_seconds` | Fleet endurance at binding demand (min over equal-share allocation; `math.inf` when no load) |
| `bridging_basis` | `"predicted_peak"` or `"current_demand"` or `"no_load"` |
| `dt_lead_next_s` | Seconds until next in-flight job reaches full TDP (min over ramping jobs) |
| `insufficient_reserve_alert` | True on the tick the staged alert fires |
| `confidence` | `ConfidenceBand(point_estimate_mw, plus_minus_fraction, tags)` |
| `curtailment_proposal_tiers` | Tuple of tier names proposed this tick |
| `checkpoint_states` | Dict of job\_id → state string |
| `kube_metrics` | Kubernetes agent snapshot (None on scripted path) |
| `solar_weather` / `solar_conditions` | Weather label + sentence from Mistral (or "physics\_estimate") |
| `pms_fast_shed_active`, `pms_order_conflict`, `scada_commands_issued` | PMS / SCADA fields |

---

## Verdict system

**File:** `runtime/verdict.py` · `evaluate_verdict()`

After a run completes, assertions from the `ScenarioSpec` are evaluated against the retained timeseries rows. Four assertion types exist:

| Type | Quantifier | Gap treatment |
|---|---|---|
| `no_insufficient_reserve_alert` | Universal (all ticks must pass) | → INCONCLUSIVE if gaps exist and no violation found |
| `max_p_total_mw` | Universal | → INCONCLUSIVE if gaps exist and no violation found |
| `alert_fires` | Existential (at least one tick) | → INCONCLUSIVE if gaps exist but no retained tick fired |
| `min_final_bess_soc` | Final-point | PASS/FAIL when final tick present; INCONCLUSIVE if missing |

Overall verdict: FAIL if any FAIL; INCONCLUSIVE if any INCONCLUSIVE (and no FAIL); PASS if all PASS.

---

## Appendix A — Solar irradiance pre-generation

**File:** `runtime/solar_sim.py` · `generate_solar_forecast()`

Solar irradiance is generated **once at run start** (not per-tick) and stored as `(sim_time_s, fraction)` samples in `spec_data["irradiance_steps"]`. Three-level fallback chain:

1. **Mistral** (`mistral-small-latest`) — given current San Diego local time and simulation duration, returns JSON with `weather` label, `conditions` sentence, and 15–25 samples. Temperature 0.5 gives varied weather across runs while remaining deterministic within a run (samples are stored once, never regenerated). The model uses knowledge of San Diego marine-layer patterns, cloud events, and solar geometry.

2. **Physics** — pure sun-position model: solar elevation angle from hour angle, declination, and latitude 32.72°N. Output ∝ sin(elevation). Covers nights (0.0) and clear-sky days with no LLM dependency.

3. **Flat at rated output** — degenerate safe default if both above fail.

The samples are converted to an `IrradianceProfile` (zero-order hold lookup) and consumed by `SolarModule.advance()` each tick.

---

## Clock convention

`sim_time` is the interval **start**. `TickResult.sim_time_seconds` carries the interval **end** (`sim_time + dt`), so stored rows are aligned with the physical state they represent and FR-1.5 MAPE attribution is unbiased. All internal elapsed-time checks inside `evaluate_tick()` use `clock.sim_time` (start). The two-clock design (sim + wall UTC) allows forecast-error attribution to compare simulated latency against real latency.

---

## Fixed evaluation order (summary)

```
Step 0   KubeDemandAgent.tick()                    (if kube_config present)
Step 1   GPUModule.advance()  →  P_compute
Step 2   CoolingModule.advance()  →  P_cooling
         P_total = P_compute + P_cooling
Step 3   SolarModule.advance()  →  P_renewable
         P_dispatch_required = max(0, P_total − P_renewable)
Step 3a  PreStagingEngine.compute_shift()          (if pre_staging_config present)
         P_dispatch_required -= shift_mw
Step 3b  SimulatedPMS.tick()                       (if pms_config present)
         P_dispatch_required += transition_gap_mw
Step 4   TurbineModule.advance() × N
         DispatchArbitrator.tick()  →  turbine_output, bess_output
Step 4d  CurtailmentLadder.generate_candidates()  (unless PMS fast shed active)
         select_candidates() unified pool  →  curtailment_proposals
Step 5   CheckpointClassifier.record_and_classify() × active training jobs
Step 6   ConfidenceEngine.band_for()  →  ConfidenceBand
         → TickResult
```

Pre-event (at WorkloadSignal, not a tick step):
```
apply_workload_signal()  →  stage_for_predicted_step()  →  InsufficientReserveAlert?
```
