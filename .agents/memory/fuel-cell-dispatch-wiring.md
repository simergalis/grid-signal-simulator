---
name: fuel-cell-dispatch-wiring
description: How the Fuel Cell Module Array was wired into the physics engine and the critical sync-ceiling bug that blocked it.
---

## Rule
`_sync_ceiling_mw` in `simulation_core.py` must include ALL local generation sources — turbines, BESS, **and fuel cell rated MW** — or those sources will never be dispatched.

**Why:** `_p_dispatch_droop_mw = min(demand, _sync_ceiling_mw)`. If FC rated MW is absent from the ceiling, the dispatch target is capped at turbine+BESS capacity, so `fc_remaining = max(0, dispatch_target - turb - bess) = 0` and the fuel cell never fires even when demand far exceeds BESS capacity.

**How to apply:** Any new dispatchable source added to the merit order (e.g. hydrogen storage, backup diesel) must also be added to `_sync_ceiling_mw`. The ceiling represents "total installed fleet capable of dispatch this tick."

## What was wired (in order)

1. `core/contingency.py` — `FuelCellSnapshot` dataclass; `fuel_cell_snapshots` optional field on `PlantState`; `evaluate_contingency()` adds FC available MW to `dispatchable_mw`.
2. `core/models.py` — `fuel_cell_output_mw: float = 0.0` added to `TickResult` (after all required fields to satisfy dataclass ordering).
3. `core/simulation_core.py` — `fuel_cell_rated_mw: float = 0.0` on `SimulationState`; post-arbitrator dispatch block clips FC to remaining shortfall; `_sync_ceiling_mw` includes `fuel_cell_rated_mw`; `_p_gen_mw` and `_p_commanded_mw` include FC term; `PlantState` gets `fuel_cell_snapshots`; `TickResult` gets `fuel_cell_output_mw`.
4. `runtime/scenario_factory.py` — sets `sim_state.fuel_cell_rated_mw` from spec when `fuel_cell_enabled=True`.
5. `runtime/run_manager.py` — `fuel_cell_output_mw` emitted in WS tick payload.
6. `frontend/src/types.ts` — `fuel_cell_output_mw: number` on `TickData`.
7. `frontend/src/opening/PlantNode.tsx` — fuel-cell case shows "dispatching · X.XX MW" / "standby" / "armed".

## Test updates required (template for future sources)
When a "not yet implemented" guard test (asserting a field does NOT exist) is flipped:
- The `_aggregate_identity()` helper in `test_aggregate_sources.py` must include the new term.
- The module docstring source table must be updated.
- The `TestSwitchgearThreeSource` scenarios must be reviewed — scenarios that expected grid to cover shortfalls may now see FC covering them instead.

## Merit order
BESS → Fuel Cell → Grid (import). Turbines run in parallel via the arbitrator.

## KubeGridState / admission headroom rule
Any new dispatchable source added to the merit order must ALSO be added to `KubeGridState` as a `*_headroom_mw: float = 0.0` field and included in the headroom sum at `kube_demand.py` line 358 — otherwise the admission gate is blind to that capacity. Pattern: `max(0.0, state.X_rated_mw - X_output_mw)`, mirroring BESS treatment. FC was added as `fuel_cell_headroom_mw` (IMPL-FC-HEADROOM-001).

## Known pre-existing test failures (NOT regressions)
- `test_13_3_frequency.py::TestI3DroopRestoringForce::test_I3_*`
- `test_kube_no_oscillation.py` (4 sub-tests) — confirmed passing as of IMPL-FC-HEADROOM-001 session
- `test_telemetry_corruption_wiring.py::test_tc_gt2_*`
- `test_formulas.py::test_d10_demo_20mw_bess_fires_and_tapers`
- `test_forecast_path.py::TestDispatchTruthfulness::test_B1a_*`, `test_B5_*`, `test_B5b_*`
- `test_fabric_scenarios_e2e.py` (7 sub-tests) — missing `config/fabric_fixture_default.json`
- `test_fabric_tick_payload.py` (7 sub-tests) — same missing fixture file
- `test_bootstrap.py::test_bootstrap_one_time_code_is_usable_for_login`
- `test_cooling_ambient_timezone.py::test_ca7_scenario_factory_physics_block_has_no_wall_clock_usage`
- `test_f5_sim_time_interval_end.py::test_internal_elapsed_unaffected_by_f5`
- `test_operator_unit_commands.py::test_tc_203_2/5c/5d`
- `test_tc89_tc90_tc91_sequential_start.py::test_tc89_*`, `test_tc91b_*`
