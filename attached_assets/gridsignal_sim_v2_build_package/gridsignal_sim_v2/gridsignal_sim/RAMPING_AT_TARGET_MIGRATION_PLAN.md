# RAMPING / AT_TARGET → SYNCHRONISED Migration Plan

**Status**: Planning only — no code changed by this document.
**Author**: Task #198 item 4.
**Goal**: Remove the legacy RAMPING and AT_TARGET turbine states and the `advance()` side-channel
that drives them, replacing every dispatch path with the Phase 2 `STARTING → SYNCHRONISED` protocol.
Until migration is complete the mutual-exclusion guard in `_check_loading_exclusion()` prevents the
B1a double-advance defect from manifesting silently.

---

## Background

Phase 1b (loading layer) and Phase 2 (unit states) introduced a clean unit lifecycle:

| State | Meaning |
|---|---|
| `OFFLINE` | Unit down, not eligible |
| `STARTING` | Cold/warm/hot-start countdown via `command_start()` + `advance()` |
| `SYNCHRONISED` | On-bus, driven by loading layer |
| `OUT_OF_SERVICE` | Maintenance — no auto-recovery |
| `TRANSITIONAL` | Reserved for future unload tail |

RAMPING and AT_TARGET predate this design. They are produced by
`DispatchArbitrator.stage_target()` → `TurbineModule.stage_target()` which calls
`advance()` on each tick to slide output toward a setpoint. The loading layer
**does not see** these units (the filter is `state == SYNCHRONISED`), so they
operate on a parallel ramp path that is not aware of the loading layer's
equal-share allocation.

---

## All Code Paths Still Emitting RAMPING / AT_TARGET

### 1. `core/dispatch.py` — `DispatchArbitrator._stage_for_predicted_step()`

**How**: calls `t.stage_target(setpoint)` for every turbine in the fleet when a
new workload step is staged.

**Where emitted**: every scenario that calls `state.apply_workload_signal()` and
then ticks via `evaluate_tick()`. That covers:
- `demo-20mw`
- `demo-pms`
- `demo-3turbine`
- `demo-solar-peak`
- Every integration test that uses `_starting_signal()` / `_run_tick()`

**Effect**: turbines transition OFFLINE → RAMPING. `advance()` increments their
output each tick at r_asset_mw_per_s × dt until setpoint is reached, then
transitions to AT_TARGET.

### 2. `core/asset_modules.py` — `TurbineModule.stage_target()`

**How**: sets `self._state = TurbineState.RAMPING` and records the target setpoint.

**Who calls it**: `DispatchArbitrator._stage_for_predicted_step()` (path 1 above) and
any legacy scenario code that calls `turbine.stage_target()` directly.

### 3. `core/asset_modules.py` — `TurbineModule.advance()`

**How**: on RAMPING state, increments output toward the target. On AT_TARGET,
holds at setpoint and decrements the hold counter. Transition OFFLINE → STARTING
also runs through `advance()` when `command_start()` was called.

**Dual role**: `advance()` serves BOTH the legacy RAMPING path AND the Phase 2
STARTING countdown. The migration must preserve the STARTING countdown path;
only the RAMPING/AT_TARGET branch should be deleted.

---

## What Converting Each Path Requires

### Conversion plan — `_stage_for_predicted_step()`

**Target model**: when a new workload step arrives, instead of calling
`stage_target()` (which sets RAMPING), the arbitrator should:
1. Determine how many synchronised units the new setpoint requires.
2. For units not yet on-bus: call `command_start()` to begin the STARTING countdown.
3. For units already SYNCHRONISED: update their target allocation via the loading
   layer (already wired — no change needed).
4. Remove `stage_target()` call entirely.

**Dependency**: the loading layer must already support adding/removing units from
the allocated set A mid-run, not just at cold-start. Currently A is rebuilt from
`state.turbines` on every tick (the filter), so adding a unit to A requires only
changing its state to SYNCHRONISED, which `advance()` already does at timer expiry.
The loading layer is already capable of handling a growing A without changes.

**Effort estimate**: medium. The arbitrator has ~200 lines of staging logic;
the `stage_target()` API is called in one place, but the setpoint arithmetic
(how much each unit should produce) needs to be delegated to the loading layer's
equal-share algorithm instead of the proportional scalar currently used.

### Conversion plan — `TurbineModule.stage_target()`

**Action**: delete method. Any call that fails to compile after deletion has
found a callsite that needs migrating (compile-time enforcement).

**Risk**: there may be test helpers that call `stage_target()` directly (e.g.
integration tests that want a turbine at a known setpoint immediately). Those
tests should instead construct a TurbineModule in SYNCHRONISED state with the
desired `output_mw` initialised directly — already supported by the constructor.

### Conversion plan — `TurbineModule.advance()` RAMPING branch

**Action**: remove the `elif self._state == TurbineState.RAMPING:` branch and
the `elif self._state == TurbineState.AT_TARGET:` branch from `advance()`.
Retain the `elif self._state == TurbineState.STARTING:` branch (Phase 2 countdown).

**Risk**: the RAMPING branch is relied on by legacy tests that expect a turbine
to reach a setpoint after N ticks. Those tests need to be converted to start with
SYNCHRONISED state (set directly) or run through the loading layer.

### Conversion plan — `TurbineState.RAMPING` and `TurbineState.AT_TARGET`

**Action**: these can be tombstoned (kept as aliases pointing to an
`_LEGACY_DEPRECATED_` enum value) for a release cycle, then removed.

**Risk**: any code that `isinstance`-checks or string-compares against these
values will receive the tombstone value. Add a deprecation warning in the
`TurbineState.__new__` for these values if Python's enum supports it.

---

## Guard Behaviour During Migration

While any scenario still emits RAMPING or AT_TARGET, the guard in
`_check_loading_exclusion()` will fire if the allocation filter is ever widened
(e.g. `t.state in (TurbineState.SYNCHRONISED, TurbineState.RAMPING)`).
This is intentional: widening the filter is the B1a defect; the guard catches it.

The guard does NOT fire when RAMPING units exist alongside SYNCHRONISED units in
the fleet — it only fires when a RAMPING unit is also in the loading set A
(i.e. the filter included it). The current filter (`state == SYNCHRONISED`) is
structurally safe.

---

## Migration Checklist (future task)

- [ ] Delete `DispatchArbitrator.stage_target()` call; replace with
      `command_start()` for units that are OFFLINE
- [ ] Delete `TurbineModule.stage_target()`
- [ ] Delete RAMPING branch from `TurbineModule.advance()`
- [ ] Delete AT_TARGET branch from `TurbineModule.advance()`
- [ ] Update all integration tests that use `stage_target()` or rely on RAMPING state
- [ ] Tombstone `TurbineState.RAMPING` and `TurbineState.AT_TARGET`
- [ ] Remove tombstones after one release cycle
- [ ] Delete `_check_loading_exclusion()` (guard is no longer needed once paths are unified)
- [ ] Update TC-77 through TC-81 and any scenario-level tests that currently assert
      RAMPING/AT_TARGET transitions
- [ ] Confirm all 9 determinism scenarios still pass with the new dispatch path

**Suggested task title**: "Migrate all dispatch paths to SYNCHRONISED state; delete advance() RAMPING/AT_TARGET legacy branch"
**Blocked by**: nothing — work is isolated to dispatch and asset_modules.
**Effort estimate**: large (1–2 days, 50+ test updates).
