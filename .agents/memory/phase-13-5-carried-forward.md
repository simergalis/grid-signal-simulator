---
name: phase-13-5-carried-forward
description: Phase 13.5 — TC-03 determinism, R4-R6 turbine constraints, R8 dispatchable_mw single source.
---

## What was built

### TC-03 — cooling determinism at 7τ, noise-disabled
- `test_tc03a`: scalar path, 7τ settle, 0.5% tolerance (updated from 5τ/2%).
- `test_tc03b`: 10 seeds, scalar path (zero noise), spread = 0% < 0.5%.
- `test_tc03c`: 7τ error < 5τ error, confirms tighter settlement.
- Location: `tests/test_13_5_criteria.py::TestTC03Determinism`

### R4 — p_min_stable_frac
- Added `p_min_stable_frac: float = 0.0` to `TurbineConfig` (default 0 = disabled).
- Spec-chosen value 0.45 must be set explicitly for scenarios exercising IP claim 4.
- Enforced in `stage_target()`: positive targets clamped to max(target, frac × rated_mw).

### R5 — t_min_run_s
- Added `t_min_run_s: float = 0.0` to `TurbineConfig` (default 0 = disabled).
- Enforced in `stage_target(target=0)`: deferred to p_min_stable floor if elapsed < t_min_run_s.
- On allowed stop: sets `state = TurbineState.OFFLINE`, `_stop_time_s`, clears `_run_start_s`.

### R6 — t_min_down_s, gt_mode, checkpoint-valley zero cycles
- Added `t_min_down_s: float = 0.0` to `TurbineConfig` (default 0 = disabled).
- Added `gt_mode: str = "frame"` to `TurbineConfig`.
- Enforced in `stage_target(target > 0, OFFLINE)`: restart dropped if elapsed_down < t_min_down_s.
- Checkpoint-valley test: 10 repeated valleys with `below_p_min_mw = 2.0 MW` → 0 OFFLINE transitions.

### R8 — PROTO-22 fix
- `run_manager.py` ramp-relaxation `ReservePosition.available_capacity_mw` now reads
  `tick_result.contingency_coverage.dispatchable_mw` instead of `ctx.turbine_rated_mw`.
- Resolves: header showed 38 MW (dispatchable) vs tile received 20 MW (turbine-only).

## Key design decisions

### Default p_min_stable_frac = 0.0 (not 0.45)
**Why**: the spec says 0.45 is the CHOSEN value for frame-class GTs. Setting it as default breaks every existing test that stages a turbine to serve a small load (D3, I4a, D8 all failed because 0.1 MW → clamped to 4.5 MW). The constraint only makes physical sense when a scenario explicitly models combustion stability limits.
**How to apply**: set `p_min_stable_frac=0.45, t_min_run_s=1800.0, t_min_down_s=900.0` in `scenario_factory.py` when building the demo-20mw scenario for IP claim 4.

### t_min_run_s/t_min_down_s defaults also 0.0
Same rationale — existing tests create turbines that start/stop freely.

### TurbineModule tracks _run_start_s / _stop_time_s as float (math.nan = unset)
Not None (which would require Optional), avoiding the dataclass Optional[float] default issue. `math.isnan()` is the sentinel check.

### On controlled stop: immediately set state = OFFLINE + zero output
`stage_target(0, sim_time)` when allowed → `_current_output_mw = 0`, `state = OFFLINE`.
This is an instantaneous stop model. A ramp-down path is not implemented; if needed, add a STOPPING state.

### dispatch.py stage_for_predicted_step passes sim_time
`turbine.stage_target(target, sim_time)` — sim_time default=0.0 so all other call sites without sim_time still work.

## TurbineSnapshot requires r_asset_mw_per_s field
`core.contingency.TurbineSnapshot` is a frozen dataclass with `r_asset_mw_per_s: float` as a required positional field. Always pass it when constructing snapshots in tests.

## BessSnapshot requires usable_mwh field
`core.contingency.BessSnapshot` requires `usable_mwh: float`. Always pass when constructing in tests.

## Pre-existing failures (unchanged)
- test_d10, test_item4: BESS re-fire after taper, 3-tuple unpack of 4-tuple — pre-dates Phase 13.
- test_f5: GPU ramp timing — pre-dates Phase 13.
