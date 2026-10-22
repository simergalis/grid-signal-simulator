# DR-2026-10-20-ISLAND-COLLAPSE — Phase 4 reserve design

Date: 2026-10-22.
Base: `ae49aaab89564ccf2ef42d505e021641484d0d3a`.
Status: **Resumed with C1–C3, then STOP at the focused TC-ISL-18 check.
Candidate retained in stash `69350a319e71e97f136b875b00c4660624aee59a`.
Main application code restored to `ae49aaa`; implementation not committed.
The earlier candidate/report remain preserved; no acceptance runs or full suite
were started for this resumption.**

P = `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/`.
This document concerns D2-r / D1-b / IMPL-ISL-2. It is not the separate
DR-2026-10-22-ISL-P4 start-event logging work accepted as IMPL-ISL-17.

## 4.0 — Existing implementation at base `ae49aaa`

### One existing reserve formula and its consumers

`P/core/dispatch.py:37`: existing `MARGIN_MULTIPLIER = 2.5`.

`P/core/dispatch.py:509–532`, `soc_floor_mwh`:
```text
diesel_floor_mwh =
    MARGIN_MULTIPLIER * bess.config.rated_mw
    * diesel_worst_case_sync_s() / 3600
depth_reserve_mwh =
    usable_mwh * max(0, initial_soc_fraction - normal_depth_fraction)
    if normal_depth_fraction > 0 else 0
return max(depth_reserve_mwh, diesel_floor_mwh)
```

The diesel timing helper at `P/core/dispatch.py:479–507` uses the fleet's
greatest configured start offset plus that driver's startup and residual
ramp durations. The existing formula and multiplier must not be retuned.

Production consumers:

- `P/core/simulation_core.py:1841–1856`: one per-BESS reconciled floor
  constrains the normal dispatch energy ceiling.
- `P/core/dispatch.py:844–847`: direct arbitrator callers obtain the same
  floor when no floor vector was supplied.
- `P/runtime/build_warnings.py:23–25`: build-time warning compares that
  same floor against usable energy. No cap or rejection is performed.

### Existing emergency release

`P/core/simulation_core.py:2051–2078`:
normal energy exhaustion plus an actual residual after permitted grid
support can authorize emergency reserve discharge. Line 2074 is:
```python
_emergency_release_authorized = _emergency_gap_mw > 0.0
```
Lines 2081–2089 add the released reserve to the upstream BESS ceilings.
Lines 2100–2104 currently replace every downstream physical floor with zero
on an authorized release:
```python
_bess_soc_floors_mwh = (
    [0.0] * len(_bess_reconciled_reserve_mwh)
    if _emergency_release_authorized
    else _bess_reconciled_reserve_mwh
)
```
Consequently D1-b must constrain both the released MW upstream and the
physical floor downstream; changing only one would introduce contradictory
requested-versus-delivered dispatch.

### Eligibility, thermal timing, and live source definitions

`P/core/asset_modules.py:1057–1067` is the single start predicate. It
returns `(False, "state")` whenever the unit is not OFFLINE. It also owns
the hot-standby and minimum-down guards. Their conditions must remain
unchanged.

`P/core/asset_modules.py:1086–1108` selects first-start thermal state from
`config.initial_thermal_state`, or restart thermal state from elapsed time
since `_last_sync_stop_s` and the configured hot/warm thresholds. It then
selects `hot_start_s`, `warm_start_s`, or `cold_start_s`.
The state field is documented at lines 909–914 as updated at each
`command_start`, not as an independently cooling clock.

For a unit already STARTING, `_time_to_online_s` is the existing remaining
countdown (`P/core/asset_modules.py:913–914,1214–1220`).
`unit_availability` reports this existing countdown at lines 1131–1132.
When it expires, the unit becomes SYNCHRONISED.

Turbine on-bus semantics are already `SYNCHRONISED` / `UNLOADING`, excluding
hot standby (`P/core/asset_modules.py:991–1003`).
The existing viability predicate at
`P/core/simulation_core.py:3352–3368` checks turbine and diesel `is_on_bus`,
plus usable GF BESS energy and delivering GF block FC arrays. Its FC branch
uses `BlockFuelCellFleet`, `array.config.grid_forming`, and actual
`array.output_mw() > 1e-9`; installed capacity alone is not delivery.

### Existing advisory bridging floor is not this energy reserve

`P/runtime/run_manager.py:1121–1141` explicitly describes bridge escalation
as downstream observation, not physics. Its existing MW threshold is:
```text
max(
    site.bess_bridging_floor_fraction * rated_mw,
    site.bess_bridging_floor_anchor_multiple * anchor_mw
)
```
Lines 1146–1151 compare that threshold with contingency bridging MW.
The independent catch-up warning uses sustained discharge and observed
turbine ramp, lines 1153–1194. Neither warning defines the retained MWh
reserve in `soc_floor_mwh`. They will not be changed. R2 must measure their
actual firing times separately from the new physical binding time.

## Candidate design after clarification (now retained in the stash)

- Extend only the existing floor calculation to
  `max(depth reserve, diesel floor, D2-r term)`.
- D2-r applies only to an islanded GF BESS without actual delivering GF
  block FC support. Reuse existing source-state semantics.
- Query the existing start-eligibility predicate, never duplicate its
  guards. Derive any minimum-down wait only from its returned reason and
  the unit's configured deadline.
- Reuse the existing thermal-duration selection without changing start
  behavior or its configured durations.
- C2, PROPOSED_HERE: the bridge is the soonest of STARTING remaining
  countdown (`starting_remaining`), OFFLINE non-hot-standby eligibility
  wait plus current thermal start (`offline_restart`), and hot standby
  releasable by the unchanged contingency path, with zero wait plus current
  thermal start (`hot_standby_release`). Exclude on-bus/failed units and
  diesel. This reserves energy until the soonest synchronous machine is on bus.
- Record the winning bridge unit, eligibility wait and startup duration,
  or the specified `"no restartable synchronous unit"` basis, in run
  metadata. Keep upstream and downstream dispatch on one computed floor.
- D1-b may release the D2-r reserve only with a turbine or diesel on bus.
  Do not accidentally introduce a new restriction on legacy diesel/depth
  release for sites where the D2-r term does not apply.
- Preserve D9b's existing warning code and strict floor-above-usable
  comparison. Do not cap or reject the floor.
- C3, PROPOSED_HERE: use `d2r_bridge` as the winning-term attribution label;
  every other warning field stays unchanged. The warning is build-time only,
  not a guarantee that the time-varying reserve never exceeds capacity later.
- No scenario, cost, commitment, start guard, diesel, frequency,
  protection or advisory-escalation behavior changes.

## Preflight issue 1 — requested tracking target does not exist

Literal file check:
```text
MISSING P/mcp_server/main.py
EXISTS  P/mcp_server/__main__.py
```
The existing `__main__.py` SHA-256 is:
```text
f62076518bb1c16c668be4376b6c379087b2f4dd5dc79ddd6b3aca08bf725fe9
```
The request authorizes tracking without content changes. Creating
`main.py`, renaming the existing CLI, or silently substituting another
path would not execute that instruction literally.
Required clarification: track the existing `__main__.py`, or omit that
CLI file. Neither action has been taken.

## Preflight issue 2 — STARTING units satisfy the proposed population

The requested population is non-hot-standby units that are not on bus and
not failed. That includes STARTING units. But the frozen predicate returns
`(False, "state")` for STARTING (`asset_modules.py:1061–1062`); completion
then moves directly to SYNCHRONISED (`1214–1220`), where the same start
predicate still refuses a new start. The predicate therefore cannot yield
a finite eligibility wait for that already-in-progress start simply by
querying a later timestamp.

Two distinct policies are possible:

1. Include STARTING units using their existing remaining countdown as
   the bridge duration, without adding a second full startup duration.
2. Restrict restart candidates to OFFLINE units; exclude in-flight starts.

Neither is silently adopted. Policy 1 is recommended for bridging a start
already in progress, but it requires an explicit exception to the written
eligibility-wait-plus-start-duration expression.

## Preflight issue 3 — warning attribution currently has only two labels

`P/runtime/build_warnings.py:37` currently sets:
```python
"winning_term": "diesel_floor" if diesel_term >= floor else "depth_reserve",
```
If a new D2-r term wins above capacity, leaving this attribution untouched
would label it `depth_reserve`. The warning would still fire, but its
reported winning term would be incorrect.

Required clarification: permit attribution-only plumbing from the single
floor result, while leaving the D9b warning condition/code and no-cap,
no-reject behavior unchanged; or require the old warning payload to stay
exactly unchanged and record the accurate D2-r basis only separately.

## Gate disposition

The initial preflight STOP was resolved by the user's answers:
```text
tracking_file = existing_main
starting_bridge = remaining_countdown
warning_attribution = attribution_only
```
Therefore track `mcp_server/__main__.py`, include STARTING turbines using
remaining startup countdown, and update only D9b winning-term attribution.
No change to the frozen start predicate or D9b warning trigger is permitted.
All original acceptance and STOP/restoration requirements remain in force.
