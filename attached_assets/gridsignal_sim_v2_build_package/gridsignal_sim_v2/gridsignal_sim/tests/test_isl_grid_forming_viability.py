"""TC-ISL-00: DR-2026-10-20-ISLAND-COLLAPSE D1 / Addendum G2 §G2.6.2."""

import pytest

from core._plane_guard import _EVALUATE_TICK_PERMITTED
from core.asset_modules import DieselModule
from core.models import (
    DieselConfig, DieselState, TurbineState, WorkloadClass, WorkloadEventType,
    WorkloadSignal,
)
from core.sim_clock import SimClock
from core.simulation_core import evaluate_tick
from runtime.scenario_factory import build_run_context_from_spec


def _state(turbine_state=None, *, hot_standby=False, diesel_state=None):
    # PROPOSED_HERE: small, unloaded fixtures isolate breaker viability, not
    # adequacy; use Stage-3's 60 Hz / .85 PF, 1 MW depleted GF-BESS and .01 s tick.
    spec = {
        "name": "tc-isl-00",
        "frequency_nominal_hz": 60.0,
        "power_factor": .85,
        "island_mode": True,
        "initial_spinning_count": 0,
        "turbine_units": [],
        "solar_rated_mw": 0.0,
        "fuel_cell_enabled": False,
        "bess_units": [{
            "asset_id": "empty-former", "rated_mw": 1.0, "usable_mwh": 1.0,
            "initial_soc_fraction": 0.0, "p_anchor_reserve_mw": 0.0,
            "grid_forming": True,
        }],
    }
    if turbine_state is not None:
        spec["turbine_units"] = [{
            "asset_id": "gt-former", "rated_mw": 1.0, "hot_standby": hot_standby,
        }]
    state = build_run_context_from_spec("tc-isl-00", spec).sim_state
    if turbine_state is not None:
        state.turbines[0].state = turbine_state
    if diesel_state is not None:
        # PROPOSED_HERE: 1 MW diesel matches the test GT; only on-bus state matters.
        diesel = DieselModule(DieselConfig(
            asset_id="diesel-former", rated_mw=1.0, role="primary",
        ))
        if diesel_state == DieselState.STARTING:
            diesel.command_start(0.0, success_override=True)
        else:
            diesel.state = diesel_state
        state.diesel_units.append(diesel)
    return state


def _tick(state):
    # PROPOSED_HERE: Stage-3's .01 s interval keeps this a single-step viability test.
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        return evaluate_tick(state, SimClock(0.0, .01, 0.0, 1.0, 1))
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


@pytest.mark.parametrize("turbine_state,hot_standby,expected_collapse", [
    (TurbineState.SYNCHRONISED, False, False),
    (None, False, True),
    (TurbineState.OFFLINE, False, True),
    (TurbineState.STARTING, False, True),
    (TurbineState.SYNCHRONISED, True, True),
])
def test_tc_isl_00_turbine_breaker_viability(
    turbine_state, hot_standby, expected_collapse
):
    state = _state(turbine_state, hot_standby=hot_standby)
    assert all(unit.soc_mwh == 0.0 for unit in state.bess_units)
    result = _tick(state)
    assert result.island_collapsed is expected_collapse
    assert result.collapse_reason == (
        "island_collapse_no_grid_forming_source" if expected_collapse else None
    )
    print({
        "state": turbine_state, "hot_standby": hot_standby,
        "island_collapsed": result.island_collapsed,
        "collapse_reason": result.collapse_reason,
    })


def test_tc_isl_00_tripped_gt_does_not_form_grid():
    state = _state(TurbineState.SYNCHRONISED)
    state.apply_workload_signal(WorkloadSignal(
        event_id="trip-gt", job_id="gt-former",
        event_type=WorkloadEventType.UNIT_TRIP, timestamp=0.0,
        hardware_profile_id="", node_count=0, workload_class=WorkloadClass.OTHER,
        site_id=state.site.site_id,
    ), dt_lead_seconds=0.0)
    assert state.turbines[0].is_on_bus is False
    result = _tick(state)
    assert result.island_collapsed is True
    assert result.collapse_reason == "island_collapse_no_grid_forming_source"
    print({"tripped_gt_state": state.turbines[0].state, "collapse_reason": result.collapse_reason})


@pytest.mark.parametrize("diesel_state,expected_collapse", [
    (DieselState.SYNCHRONISED, False),
    (DieselState.OFFLINE, True),
    (DieselState.STARTING, True),
])
def test_tc_isl_00_diesel_breaker_viability(diesel_state, expected_collapse):
    state = _state(diesel_state=diesel_state)
    result = _tick(state)
    assert result.island_collapsed is expected_collapse
    assert result.collapse_reason == (
        "island_collapse_no_grid_forming_source" if expected_collapse else None
    )
    print({"diesel_state": diesel_state, "collapse_reason": result.collapse_reason})
