# Gas Turbine Fleet modal — with §7.1.3 closeout corrections

**Follows:** Phase E closeout. §7.1.3 implemented; §7.2 amendment evidence gathered.
**Baseline:** 18 failed, 970 passed, 16 xfailed.
**Files:** `src/subsystem/panels/turbineFleet.ts` (registered `'gas-turbine-fleet'` in `panels/index.ts`), `React.createElement` style — not JSX. Plus `core/models.py` and `tests/` for Items 1–3.
**Scope:** Items 1–3 close §7.1.3. Items 4–9 are the modal. No class C defect work.

Three things from the closeout need settling first — one is a live behavioural inconsistency, one is a guard that can no longer fail, and one is a physics finding filed as a stale assertion.

---

## Item 1 — The enable-flag defaults disagree, and the unsafe side wins

`TurbineConfig` defaults `min_run_enabled` and `min_down_enabled` to **False**. `TurbineUnitSpec` and `_turbine()` default them to **True**.

So any `TurbineConfig()` built outside the scenario path — every unit test, every direct instantiation — runs with minimum run and down times **disabled**, while scenarios run with them enabled. The stated reason was backward compatibility for unit tests.

That is D-03 half-applied: the `0.0` sentinel is gone, but the disagreement moved into the defaults, and it moved in the unsafe direction. The dwell constraints silently vanish wherever a config is constructed directly. Two of the five new failures (`test_I3_droop_*`) are this class — a bare `TurbineConfig()` now behaving differently from a scenario-built one.

**Default both to `True`.** A test needing the constraint off says so explicitly, which is the point of an explicit flag. Report every test that then needs `min_run_enabled=False` or `min_down_enabled=False` added, and add it — those are fixture repairs, not assertion changes.

## Item 2 — Guard D1 can no longer fail; it needs a successor

From the closeout:

> The Guard D1 scanner finds `ast.Constant` nodes at annotation assignment level; `_sp.value("p_min_stable_frac")` is a `Call` node, not a `Constant`. Guard D1 reports 0 drifts. ✓

The guard passes because the scanner **cannot see function calls**, not because anything agrees with the catalogue. Every catalogued default is now structurally invisible to D1. A typo'd key, or a code path assuming a value the catalogue no longer holds, reports green.

Reading through `site_parameters` is the correct design — that was the whole configuration refactor. But D1's original job is finished and its new job is unfilled.

**Add Guard D3:** a static sweep asserting that every `_sp.value("key")` / `site_parameters.value("key")` call site names a key the catalogue actually contains. `site_parameters` already raises `ParameterNotCatalogued` at runtime; this catches it at build time.

Report the call-site count found, and state plainly in the guard's docstring what D1 does and no longer does, so the ✓ is not read as coverage it does not provide.

## Item 3 — Trace the I3 droop sign inversion before accepting it

`test_I3_droop_creates_restoring_force_when_f_above_nominal` and `test_I3_droop_direction_vs_no_droop` were classified CORRECT on the grounds that a default changed. The report's own diagnosis says otherwise:

> new default 0.40 → MSL=4.0 MW; I3's sub-MSL demand is floored by the loading layer, overfrequency forcing **inverts sign**

That is a physics interaction, not a stale assertion. MSL flooring changes the sign of the droop restoring force under sub-MSL demand — and a sign inversion in a frequency-restoring force is worth establishing rather than assuming.

It may well be correct: at sub-MSL demand the fleet genuinely cannot back down further, so overfrequency has nowhere to go and the droop response is bounded by the floor. If so, that is a **§7.1.3.6 finding** and belongs in the spec, not in a test-classification table.

Produce a tick-by-tick trace across the inversion. Report frequency, fleet setpoint, per-unit setpoint, MSL floor, and droop correction. State whether the new behaviour is physically right. **Do not edit either test** — report the finding; the spec amendment is made elsewhere.

Also fix `test_R4/R5/R6_*_field_default`, which assert `== 0.0` against defaults that deliberately changed. Those are genuine one-line updates and are the only assertion edits permitted in this session.

**Gate for Items 1–3: report the corrected failure count before starting Item 4.**

---

## Item 4 — Locate the six UI defects

Line numbers are unreliable — `turbineFleet.ts` was reworked across four configuration phases and again for the D-05 rename. For each defect: locate it, report where it now lives, confirm it still exists, and say so plainly if it is already closed.

**U-1. Aggregate ramp label contradicts its arithmetic.** An aggregate ramp computed as `maxRamp × units.length` over **all** units — OFFLINE, STARTING and hot-standby included — using the fleet maximum rate rather than per-unit rates, beneath a subtitle claiming *"SYNCHRONISED only — starts excluded"*. Both cannot be true.

**U-2. The aggregate row mixes two sources.** `rampEnergyMW = tick.ramp_capability_mw ?? (aggRampMWs × horizonS)` — value from the backend, rate beside it from the frontend formula, and they disagree. `tick.ramp_capability_mw` is authoritative; delete the fallback and the frontend aggregate.

**U-3. Single-unit ramp is unclamped.** The "Ramp with 1 unit" row renders `rate × horizonS` with no clamp — 33 MW from a 15 MW machine. Clamp to `rated_mw` and derive it from the same function as the aggregate row, so the two cannot diverge.

**U-4. N−1 firm capacity counts units that are not there.** `n1FirmMW = installedMW − maxUnitMW` uses installed capacity, so an OFFLINE unit contributes firm capacity. Compute it from **committed** units and reconcile against the §7.1.3.3 reserve floor — the two answer the same question and must not disagree.

**U-5. Start times hardcoded.** `_THERMAL_ROWS`, `_thermalSub`, and the cold-start stat row. The hot value was moved 60 → 300 in Phase D; the rest belong to `TurbineConfig.cold_start_s` / `warm_start_s` / `hot_start_s`.

**U-6. `units_on_bus_count` documentation.** Corrected during the D-05 rename — confirm it now describes `{SYNCHRONISED, UNLOADING}` and nothing stale remains.

## Item 5 — Payload additions

`types.ts` entry before backend emission, per task #191.

| Field | Why |
|---|---|
| `setpoint_mw` (per unit) | Output alone cannot distinguish a unit tracking from a unit stuck. The single most useful addition. |
| `msl_mw` (per unit) | Already on `UnitAvailability`, not broadcast. Now non-zero everywhere after Phase E — the `NO-LOAD / MSL MW` column has real data to show for the first time. |
| `levelled_off` (per unit) | The Phase E predicate; gates breaker-open. |
| `commitment` block | `committed_rated_mw`, `reserve_floor_mw`, `reserve_satisfied`, `utilisation`, `pending_start_unit_id`, `last_decision_reason`, `blocked_by`. |

`blocked_by` now carries real content — the closeout threaded R5 refusals through it. An operator seeing no decommitment can finally be told whether the fleet is satisfied or constrained.

## Item 6 — Per-unit bar

Alongside `CURRENT MW`: fill `output_mw / rated_mw`, dashed rule at `msl_mw / rated_mw`, thin marker at `setpoint_mw`.

**The gap between marker and fill is the ramp.** That gap closing is what "levels off at a stable state" looks like, and it is invisible on every screen today. `BulletBar` may fit — but its `max` must never derive from its own value.

STARTING shows the sync countdown draining instead of output, labelled with `thermal_state`, `start_phase` and remaining `time_to_online_s`. **UNLOADING is visually distinct from SYNCHRONISED** — a unit leaving must not read as a unit merely running low, and after Phase E that distinction exists in the model for the first time.

## Item 7 — Commitment stat rows

Replacing the aggregate-ramp rows U-1 and U-2 invalidate: committed capacity against `reserve_floor_mw`; `utilisation` against the commit and decommit thresholds; and when a decision is blocked, `blocked_by` with `last_decision_reason`.

## Item 8 — STARTING in the SYNC column

`isOnBus()` resolves to a breaker boolean. A starting unit is neither open-and-idle nor closed, and under sequential commitment it is the state the operator most needs to see — it is the fifteen minutes during which nothing can be done.

## Item 9 — Tests

**TC-98** — per-unit `output_mw` sums to the on-bus fleet total in every state, including UNLOADING.
**TC-99** — single-unit and aggregate ramp figures derive from one function, agree, and clamp to rated capacity.

Extend `src/test/smoke_panels.test.tsx`.

---

## Prohibited

- Editing any test assertion except `test_R4/R5/R6_*_field_default`.
- Editing `test_I3_droop_*` — report the trace instead.
- Defaulting either enable flag to `False`.
- Recording Guard D1 as green without stating what it no longer covers.
- Rewriting `turbineFleet.ts` from scratch, or converting it to JSX.
- Drawing any bar whose maximum derives from its own value.
- Reintroducing a peak-load literal — `design_peak_load_mw` with a labelled observed fallback is already in place.
- Emitting any payload key before its `types.ts` entry.
- Adding a module-scope numeric constant to `panels/`.
- Editing the spec. Report the Item 3 finding.
- Modifying `gridsignal_logger.py`.
- Proceeding past a phase gate without reporting.

## Acceptance criteria

- [ ] Both enable flags default `True` in `TurbineConfig`; every test needing them off updated explicitly.
- [ ] Guard D3 added, `_sp.value()` call-site count reported, D1's docstring states its remaining scope.
- [ ] I3 sign inversion traced tick-by-tick; physical correctness stated; neither test edited.
- [ ] `test_R4/R5/R6_*_field_default` updated to the new defaults.
- [ ] Corrected failure count reported before Item 4.
- [ ] U-1 … U-6 each located, current location reported, fixed or reported already-closed.
- [ ] Ramp figures derive from one function; `aggRampMWs` deleted; single-unit clamped to rated.
- [ ] N−1 firm capacity from committed units, reconciled against the §7.1.3.3 reserve floor.
- [ ] Start times derived per unit from config; no literals remain.
- [ ] Four payload additions landed, `types.ts` first.
- [ ] Per-unit bar with MSL rule and setpoint marker; STARTING countdown; UNLOADING visually distinct.
- [ ] Commitment stat rows including `blocked_by`.
- [ ] TC-98, TC-99 added and passing.
- [ ] Guards D1, D2, D3, E Tier 1 green; TypeScript `--noEmit` clean.
- [ ] Suite reported against 18 / 970 / 16 xfailed, every delta attributed.
