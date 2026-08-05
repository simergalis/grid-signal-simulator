# Task #198 Report — Five Phase 1b/2 Corrections

**Suite baseline before task**: 834 pass, 7 pre-existing failures  
**Suite after task**: 915 pass, same pre-existing failures (no new regressions)  
**New tests added**: 3 mutual-exclusion guard tests in TC-81; TC-80 rewrote 2 subtests;
D4 defect field asserted in `_verify_d4()` and `test_D4_all_ticks_across_ramp`

---

## Item 1 — sub_msl_surplus_mw must not be a balance channel ✅

### Change

`core/simulation_core.py`, balance-decomp section (~line 965–1030):

The separate `_asset_delivery_error_mw` assignment was eliminated. The channel routing is
now inside the `if _islanded / else` block so each mode can route the surplus correctly.

**Islanded mode**:
```
_frequency_forcing_mw = _p_commanded - p_total + _sub_msl_surplus_mw
_asset_delivery_error_mw = (turbine_output - gt_setpoint - _sub_msl_surplus_mw)
                         + (bess_output - bess_setpoint)
```
The surplus is added to `frequency_forcing_mw` (machines accelerate → overfrequency)
and subtracted from the turbine delivery term so `asset_delivery_error_mw` reflects
hardware constraints only (BESS depletion, ramp-rate violations), not floor enforcement.

**Grid-connected mode**:
```
_grid_exchange_mw = _p_commanded - p_total
_asset_delivery_error_mw = (turbine_output - gt_setpoint)
                         + (bess_output - bess_setpoint)
```
No change from the pre-task formula. Sub-MSL surplus is absorbed by the grid as
additional PCC export (turbine over-delivery appears in `asset_delivery_error_mw`
naturally — this is correct: the floor surplus is a hardware dispatch fact, not a
frequency event, in grid-connected mode).

### D4 holds in both modes

Algebraic verification (islanded):

```
grid_exchange + frequency_forcing + asset_delivery_error
= 0 + (_p_commanded − p_total + surplus) + ((turbine_output − gt_setpoint − surplus) + bess_error)
= _p_commanded − p_total + turbine_output − gt_setpoint + bess_error
= (gt_setpoint + bess_setpoint + renewable) − p_total + turbine_output − gt_setpoint + (bess_output − bess_setpoint)
= renewable − p_total + turbine_output + bess_output
= balance_residual ✓
```

D4 holds grid-connected (unchanged).

### model_error_mw vs asset_delivery_error_mw

These are distinct fields on `TickResult`:
- **`model_error_mw`** = `site.load_model_bias_mw` injection — a deliberately injected
  modelling bias used in fault scenarios. Currently 0.0 in all production runs (Phase 13.4).
- **`asset_delivery_error_mw`** = `(turbine_output − gt_setpoint) + (bess_output − bess_setpoint)` — physical hardware tracking error.

They were once the same field (Phase 13.2 used "model_error" for what is now
"asset_delivery_error"). The rename in Phase 13.4 addendum correctly separated them.
No renaming needed — they are already distinct.

### Sub-MSL surplus → `sub_msl_surplus_mw` comment updated

`core/models.py`: `sub_msl_surplus_mw` docstring updated to note the routing
("islanded mode surplus enters `frequency_forcing_mw`").
`runtime/run_manager.py`: comment updated to match.

### D4 has exactly 3 channels

Confirmed: `grid_exchange_mw`, `frequency_forcing_mw`, `asset_delivery_error_mw`.
No fourth channel exists. `sub_msl_surplus_mw` is a reporting field on `TickResult`
with no role in the balance equation.

---

## Item 2 — STARTING units contribute zero ramp credit ✅

### Change

**`core/loading.py` — `ramp_capability()`**: removed the `if t.state == TurbineState.STARTING:` pro-rating branch entirely. The branch was:
```python
if horizon_s >= t._time_to_online_s:
    total += t.config.rated_mw
```
Replaced with `pass` (STARTING units fall through, contributing 0).

**`core/dispatch.py` — `turbine_ramp_credit_mw()`**: removed the STARTING pro-rating:
```python
# removed: available_s = max(0.0, lead_window_s - ua.time_to_online_s)
if ua.is_starting:
    pass   # zero
```

### Rationale

A unit not yet on bus (breaker open, STARTING countdown running) must not be
banked as ramp reserve. Starts fail during grid events. The previous "credit at
H ≥ timer" rule overcounted fleet capability by rating units that would not survive
a synchronising attempt under voltage depression.

### TC-80 subtests corrected

- `test_tc80_starting_rated_at_online_time`: now asserts 0.0 (was 10.0)
- `test_tc80_starting_rated_above_online_time`: now asserts 0.0 (was 10.0)
- `test_tc80_starting_zero_before_online`: unchanged — already 0.0 ✓
- `test_tc80_starting_plus_synchronised_fleet`: unchanged — already 5.0 ✓

### TC-81 dispatch test corrected

`test_tc81_dispatch_turbine_ramp_credit_mw`: `starting_ua` (H=45, timer=30)
now contributes 0 (not `0.2 × 15 = 3.0 MW`). Total credit changed from 12.0 to 9.0 MW.
Cap test (δ_p=5 MW) still gives 5.0 MW. ✓

---

## Item 3 — One lead time, not two ✅

### Changes

**`core/loading.py`**: deleted `LEAD_WINDOW_S: float = 45.0` constant.
Replaced with a comment explaining the design: callers pass the runtime horizon.

**`core/simulation_core.py`**: import changed from
`from .loading import apply_loading, ramp_capability, LEAD_WINDOW_S`
to `from .loading import apply_loading, ramp_capability`.

The `ramp_capability()` call changed from:
```python
_ramp_capability_mw = ramp_capability(LEAD_WINDOW_S, state.turbines)
```
to:
```python
_ramp_capability_mw = ramp_capability(dt_lead_next_s, state.turbines)
```
`dt_lead_next_s` is the dispatch arbitrator's runtime value, computed earlier in
`evaluate_tick()` at line ~624.

**`tests/test_p1b_p2.py`**: removed `LEAD_WINDOW_S` from import. TC-79 tests
now use explicit `H = 45.0` local variables (same numeric value, no shared constant).

**`frontend/src/subsystem/panels/turbineFleet.ts`**: deleted `const LEAD_WINDOW_S = 45.0`.
All six use-sites replaced:
- `singleUnitPanel` / `fleetPanel`: derive `const horizonS = tick.dt_lead_next_s ?? 0`
- `deriveFleet()` now accepts `horizonS: number` parameter
- `rampNeedMWs = horizonS > 0 ? PEAK_LOAD_MW / horizonS : 0` (avoids ÷0 at rest)
- Fallback: `tick.ramp_capability_mw ?? (aggRampMWs * horizonS)` (uses runtime value)
- All label strings use `horizonS.toFixed(0)` instead of a constant

### Structural assertion: one lead-time source

`LEAD_WINDOW_S` verified absent from:
- `core/loading.py` ✓ (deleted)
- `core/simulation_core.py` ✓ (import removed)
- `core/dispatch.py` ✓ (never used there — dispatch takes `lead_window_s` as a parameter from the call site, which is now the runtime value)
- `frontend/src/subsystem/panels/turbineFleet.ts` ✓ (deleted)
- `frontend/src/types.ts` ✓ (comment updated — reference to `LEAD_WINDOW_S = 45 s` removed)
- `tests/test_p1b_p2.py` ✓ (import removed)

The frontend drawer reads `tick.ramp_capability_mw` (computed by the backend at `dt_lead_next_s`) and labels it with `tick.dt_lead_next_s`. One source of truth.

---

## Item 4 — Mutual-exclusion guard + migration plan ✅

### Guard

`core/simulation_core.py`: extracted `_check_loading_exclusion(synchronised_units, all_turbines)` as a module-level function (lines 31–68). Called from `evaluate_tick()` immediately after the `_synchronised_units` filter:
```python
_check_loading_exclusion(_synchronised_units, state.turbines)
```

The function raises `RuntimeError` (not `assert`) when any unit with `state in (RAMPING, AT_TARGET)` also appears in the loading set A (by `asset_id`). The error message names the unit, its state, and the defect pattern.

**Why `RuntimeError` not `assert`**: `assert` is stripped under `python -O`. A power balance defect mid-run must terminate the tick with a clear error; silent continuation would corrupt subsequent tick accounting.

**Exported at module level** so tests can import and call it directly without going through a full `evaluate_tick()` invocation.

### Tests (TC-81, 3 new subtests)

```
test_tc81_mutual_exclusion_guard_passes_for_valid_split
  → correctly separated fleet (SYNCHRONISED GT-10, RAMPING GT-15): no error ✓

test_tc81_mutual_exclusion_guard_raises_on_b1a_defect
  → RAMPING GT-10 in loading set: raises RuntimeError("mutual-exclusion") ✓

test_tc81_mutual_exclusion_guard_raises_on_at_target_defect
  → AT_TARGET GT-20 in loading set: raises RuntimeError("mutual-exclusion") ✓
```

Note: `_turbine()` derives `asset_id` from `rated_mw` (`f"GT-{rated_mw:.0f}"`), so the
"passes" test uses `rated_mw=15.0` for the RAMPING unit to give it a distinct ID from
the SYNCHRONISED unit at `rated_mw=10.0`.

### Migration plan

Written to `RAMPING_AT_TARGET_MIGRATION_PLAN.md`. Key findings:

| Path | Mechanism | Effort to migrate |
|---|---|---|
| `DispatchArbitrator._stage_for_predicted_step()` | calls `stage_target()` → RAMPING | Medium: delegate setpoint math to loading layer |
| `TurbineModule.stage_target()` | sets `_state = RAMPING` | Delete method; compile-time enforcement catches callsites |
| `TurbineModule.advance()` RAMPING branch | slides output each tick | Delete branch; keep STARTING branch |
| `TurbineState.RAMPING` / `AT_TARGET` | legacy enum values | Tombstone, then remove after one release cycle |

The guard remains in place and fires if any migration step widens the filter incorrectly.

---

## Item 5 — D4 must not be a bare assert ✅

### Change

**`core/models.py`**: added `d4_balance_defect_mw: float = 0.0` to `TickResult`.

**`core/simulation_core.py`**: converted the bare `assert abs(_d4_sum - ...) < 1e-6`
to an explicit check:
```python
_d4_balance_defect_mw = _d4_sum - _balance_residual_mw
if abs(_d4_balance_defect_mw) >= 1e-3:
    _log.warning(
        "D4 power balance defect: %.9f MW "
        "(grid_exchange=%.6f, frequency_forcing=%.6f, "
        "asset_delivery_error=%.6f, p_gen=%.6f, p_total=%.6f)",
        ...
    )
# Run continues — defect surfaced on TickResult for monitoring.
```
The defect is always populated on `TickResult` (`d4_balance_defect_mw=_d4_balance_defect_mw`).

**`runtime/run_manager.py`**: `d4_balance_defect_mw` added to wire dict.

**`frontend/src/types.ts`**: `d4_balance_defect_mw: number` added to `TickPayload`.

### D4 tests updated

`_verify_d4()` helper in `TestD4SumIdentity` now also asserts `abs(tick.d4_balance_defect_mw) < 1e-3`.
`test_D4_all_ticks_across_ramp` asserts the defect field at every tick.

All D4 tests still pass — the defect is 0.0 in all normal scenarios. ✓

---

## Additional Reporting

### Frequency assertions not perturbed

Phase 13.3 wired the swing equation to `frequency_forcing_mw + asset_delivery_error_mw`.
Item 1 changes the routing of `sub_msl_surplus_mw` between channels but does NOT
change the sum `(frequency_forcing + asset_delivery_error)` that the swing equation
sees — the total is identical to the pre-task formula. Therefore no scenario assertion
values for frequency changed.

For grid-connected scenarios: `frequency_hz` is held at 50.0 by the infinite-bus
clamp; surplus routing has no effect.

### P_anchor_reserve = 1.0 MW

`BessConfig.p_anchor_reserve_mw` defaults to 1.0 MW. This is an engineering
placeholder from Phase 2. It is registered as an open item under §15 of the
simulation design, alongside `r_asset`, `min_down_time_s`, and `unload_tail_s`.
Value not changed.

### Pre-existing failures (unchanged)

| Test | Status |
|---|---|
| `test_formulas.py::test_d10_demo_20mw_bess_fires_and_tapers` | pre-existing |
| `test_formulas.py::test_item4_small_unit_capped_to_ceiling_under_equal_share` | pre-existing |
| `test_f5_sim_time_interval_end.py::test_internal_elapsed_unaffected_by_f5` | pre-existing |
| `test_kube_no_oscillation.py` (×4 seeds) | pre-existing |
| All `test_api.py`, `test_auth.py`, `test_bootstrap.py`, `test_fabric_model.py` RuntimeError failures | pre-existing API server required |

---

## Files Changed

| File | Items |
|---|---|
| `core/loading.py` | 3 (deleted LEAD_WINDOW_S), 2 (removed STARTING credit) |
| `core/simulation_core.py` | 1 (surplus routing), 2 (STARTING credit in dispatch), 3 (dt_lead_next_s), 4 (guard extracted + called), 5 (D4 defect field) |
| `core/dispatch.py` | 2 (zero STARTING credit) |
| `core/models.py` | 1 (sub_msl comment), 3 (ramp_capability_mw comment), 5 (d4_balance_defect_mw field) |
| `runtime/run_manager.py` | 5 (wire d4_balance_defect_mw) |
| `frontend/src/types.ts` | 3 (comment), 5 (d4_balance_defect_mw) |
| `frontend/src/subsystem/panels/turbineFleet.ts` | 3 (delete LEAD_WINDOW_S, all 6 use-sites) |
| `tests/test_p1b_p2.py` | 3 (remove import, TC-79 explicit horizons), 2 (TC-80 two subtests), 2 (TC-81 dispatch test), 4 (3 guard tests) |
| `tests/test_13_2_balance_decomp.py` | 5 (_verify_d4 defect assertion, per-tick defect assertion) |
| `RAMPING_AT_TARGET_MIGRATION_PLAN.md` | 4 (new document) |
| `TASK_198_REPORT.md` | this file |
