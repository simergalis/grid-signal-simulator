---
name: incremental-turbine-dispatch
description: Design decisions for the incremental turbine startup dispatch in stage_for_predicted_step and the per-tick headroom check in evaluate_tick.
---

## Rule

### stage_for_predicted_step (dispatch.py) — Phase B sequential-start contract

**D-05 sequential-start (current behaviour after Phase B):**
- At most ONE offline unit starts per call to `stage_for_predicted_step()`.
- The N_needed+1 simultaneous-start formula is removed.
- When `_eff_delta > 0`, call `_offline[0].stage_target(_eff_delta, sim_time)` for the first offline unit only.
- When `_eff_delta == 0` (demand step is zero or negative), skip the call — `stage_target(0, OFFLINE)` is a no-op on OFFLINE units anyway, and the N-1 spare is handled by the per-tick headroom check.
- BESS bridges the gap until the first unit is SYNCHRONISED and the headroom check can stage the second.

**Negative delta guard (on-bus only, unchanged):**
- Never propagate `delta_p_mw <= 0` to `_on_bus` turbines — that sends simultaneous stop commands causing the 7.5 MW → 0 oscillation.
- Guard: `if _on_bus and delta_p_mw > 0.0: stage_target(output + delta/N, ...)`.

### Per-tick headroom check (simulation_core.py — unchanged)

```
_DISPATCH_HEADROOM_FRAC = 0.20   # start next unit when synchronised fleet ≥ 80% loaded
_sync_rated_mw = sum(rated for t where t.state == SYNCHRONISED and not hot_standby)
if _sync_rated_mw > 0 and turbine_output_mw / _sync_rated_mw >= 0.80:
    first_offline.stage_target(_p_dispatch_droop_mw, sim_time)
    break  # one at a time
```

Key: `_sync_rated_mw` counts SYNCHRONISED-only (not RAMPING). A freshly-RAMPING unit from
`stage_for_predicted_step` is excluded, so the guard `_sync_rated_mw > 0` prevents a
same-tick double-start.  The headroom check only fires once the first unit is fully SYNCHRONISED.

## Why

**Why sequential (not N_needed+1):**
TC-87/TC-88 gate: simultaneous starts violate the sequential-start contract (D-05, §7.1.3).
The N-1 spare is provided through the staircase: turbine-0 synchronises → headroom check starts
turbine-1. During the startup window BESS bridges any single-unit contingency.

**Why COVERED_WITH_SHED is acceptable pre-trip (TC-84f update):**
With sequential starts, only turbine-0 is running during the startup window. N-1 contingency for
a single-unit fleet relies on BESS bridge — legitimately COVERED_WITH_SHED. The old assertion
("must be COVERED") was specific to the N_needed+1 world. TC-84f's pre-trip assertion now accepts
COVERED or COVERED_WITH_SHED (must not be CANNOT_CARRY).

**Why `stage_target(0, OFFLINE)` is a no-op:**
`stage_target` only transitions OFFLINE→RAMPING when `target_mw > 0`. With target=0 the stop
path runs, but `if self.state != OFFLINE` guard prevents any action. Net effect: OFFLINE stays
OFFLINE, `_target_mw = 0`. The old N_needed+1 code's "delta=0 → start 1 unit with target 0"
was therefore also a no-op on OFFLINE units — behaviour is preserved.

## How to apply

- `stage_for_predicted_step` is called for every STARTING/SOLAR_STEP/COMPLETION event (not every tick).
- The per-tick headroom check in `evaluate_tick` is the sole mechanism for starting units 2+ in a multi-unit fleet.
- Phases C-E of the ramp-algorithm replacement will migrate this from stage_target/RAMPING to command_start/STARTING.

## Test impact (Phase B)

- **TC-87**: PASSES — at most 1 unit non-OFFLINE after tick 0.
- **TC-88**: PASSES — at most 1 OFFLINE→non-OFFLINE transition per tick across 20 ticks.
- **test_tc84f** (test_unit_trip.py): pre-trip assertion updated from "must be COVERED" to "must not be CANNOT_CARRY" (COVERED_WITH_SHED is correct with sequential starts during startup window).
- All other 965 previously-passing tests: still passing (zero regression).
- Suite: 12 failed (pre-existing), 967 passed, 976 collected, 0 errors.
