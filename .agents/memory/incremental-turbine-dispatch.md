---
name: Incremental Turbine Dispatch
description: Current dispatch algorithm state; TC-84f trip test; sequential-start Phase D plan.
---

## Current dispatch state (after Phase A revert)

`core/dispatch.py` stage_for_predicted_step() uses N_needed+1 formula:

```python
_n_start = min(max(1, math.ceil(_eff_delta / _offline[0].config.rated_mw) + 1), len(_offline))
_per_start_target = _eff_delta / _n_start if _n_start else 0.0
for _ht in _offline[:_n_start]:
    _ht.stage_target(_per_start_target, sim_time)
```

N_needed = ceil(delta/rated); +1 provides N-1 reserve (if first unit trips, survivor has headroom).
Without +1, single-turbine fleet has CANNOT_CARRY contingency on first startup.

## Phase B sequential-start code was REVERTED (see ramp-algo-phases-status.md)

A single-unit dispatch was applied in error (Phase D work, not Phase A).
Revert confirmed: suite gate restored to 12/965/974/0 base + 3 xfailed = 977 collected.

## TC-84f: pre-trip assertion

test_tc84f_demo_20mw_contingency_state_changes_after_trip (tests/test_unit_trip.py)
Pre-trip assertion: `COVERED_WITH_SHED not in pre_states_set`
Why: N_needed+1 starts turbine-0 and turbine-1 at t=0. With both SYNCHRONISED the N-1
survivor (turbine-1) covers a hypothetical turbine-0 trip → COVERED throughout pre-trip window.
Post-trip assertion: `CANNOT_CARRY not in post_states_set` (COVERED_WITH_SHED acceptable).

## TC-89, TC-90, TC-91 (xfailed, Phase D)

All in tests/test_tc89_tc90_tc91_sequential_start.py, marked xfail strict=False.
TC-89 and TC-90 fail because N_needed+1 starts 2 units simultaneously (tick 0).
TC-91 fails: with turbine-0 SYNCHRONISED at 6.0 MW and 2 offline units,
  stage_for_predicted_step(delta=5 MW) → _n_start = 2 → both start simultaneously.
  After Phase D: 1 unit starts from stage_for_predicted_step; PendingStartRegister
  prevents headroom check from starting the second.

## Sequential-start Phase D plan

Phase D (see ramp-algo-phases-status.md):
- evaluate_commitment() from core/commitment.py replaces the headroom block
- At most 1 unit in STARTING (PendingStartRegister)
- inter_start_settle_s = 60 s gap between starts
- command_start() only (no direct state assignment)
- TC-89, TC-90, TC-91 all must pass

**Why:** N_needed+1 is a simultaneous-start defect. Phase D replaces it with
commitment-engine-controlled sequential starts, which also gives the operator
visibility into commitment decisions via evaluate_commitment() output.
