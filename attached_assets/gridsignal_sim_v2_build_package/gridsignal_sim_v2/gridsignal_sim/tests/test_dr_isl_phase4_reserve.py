"""TC-ISL-01–03: DR D2-r/D1-b; fixtures are not scenario calibrations."""
import copy
import json

import pytest

from api.schemas import ScenarioSpec
from core._plane_guard import _EVALUATE_TICK_PERMITTED
from core.dispatch import MARGIN_MULTIPLIER
from core.models import DieselState, TurbineState
from core.sim_clock import SimClock
from runtime.build_warnings import reserve_capacity_warnings
from runtime.scenario_factory import build_run_context_from_spec


def _context(**overrides):
    # PROPOSED_HERE: synthetic 10 MW / 20 MWh BESS and 600 s restart make
    # reserve arithmetic visible; all timing stays in explicit fixture config.
    spec = {
        "name": "tc-isl-reserve", "frequency_nominal_hz": 60.0,
        "power_factor": .85, "pue_base": 1.0, "island_mode": True,
        "initial_spinning_count": 0, "bess_normal_dispatch_depth_fraction": 0.0,
        "solar_rated_mw": 0.0,
        "turbine_units": [
            {"asset_id": "gt-reserve", "rated_mw": 1.0,
             "hot_standby": False, "min_down_enabled": False,
             "initial_thermal_state": "cold", "cold_start_s": 600.0},
        ],
        "bess_units": [
            {"asset_id": "bess-reserve", "rated_mw": 10.0,
             "usable_mwh": 20.0, "initial_soc_fraction": 1.0,
             "grid_forming": True, "p_anchor_reserve_mw": 0.0},
        ],
    }
    spec.update(overrides)
    if spec.get("diesel_units"):
        diesel = spec["diesel_units"][0]
        # ScenarioSpec materializes diesel_units from the enabled power block;
        # a declared list alone is intentionally not an enabled fleet.
        spec["diesel_power_block"] = {
            "enabled": True, "target_capacity_mw": diesel["rated_mw"],
            "unit_rating_mw": diesel["rated_mw"],
            "delta_t_start_s": diesel["delta_t_start_s"],
            "residual_ramp_s": diesel["residual_ramp_s"],
        }
    for diesel in spec.get("diesel_units", []):
        # PROPOSED_HERE: complete the explicit materialized test fleet schema;
        # zero guards isolate reserve behavior, not operational diesel timing.
        defaults = {
            "start_offset_s": 0.0, "f_block": .6,
            "min_stable_load_mw": .3 * diesel["rated_mw"],
            "min_run_s": 0.0, "min_down_s": 0.0, "cooldown_s": 60.0,
        }
        for key, value in defaults.items():
            diesel.setdefault(key, value)
    canonical = ScenarioSpec.model_validate_json(json.dumps(spec)).model_dump(mode="json")
    return build_run_context_from_spec("tc-isl-reserve", canonical)


def _tick(state):
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        from core.simulation_core import evaluate_tick
        # PROPOSED_HERE: one normal simulator interval, not a timing override.
        return evaluate_tick(state, SimClock(0.0, 5.0, None, 1.0, 1))
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


def test_tc_isl_01_no_diesel_positive_floor_and_recorded_basis():
    ctx = _context()
    arb = ctx.sim_state.arbitrator
    bess = ctx.sim_state.bess_units[0]
    expected = MARGIN_MULTIPLIER * 10.0 * 600.0 / 3600.0
    assert arb.soc_floor_mwh(bess) == pytest.approx(expected)
    basis = ctx.metadata["bess_reserve_floor_basis"]["bess-reserve"]
    assert basis["winning_term"] == "d2r_bridge"
    assert basis["basis"] == "offline_restart"
    assert basis["unit_id"] == "gt-reserve"
    assert basis["eligibility_wait_s"] == 0.0
    assert basis["start_duration_s"] == 600.0
    assert ctx.metadata["bess_reserve_floor_history"]
    print({"TC-ISL-01": basis})


def test_tc_isl_01_diesel_wins_unchanged():
    ctx = _context(diesel_units=[{
        "asset_id": "diesel-reserve", "rated_mw": 1.0, "role": "primary",
        "delta_t_start_s": 1000.0, "residual_ramp_s": 440.0,
    }])
    arb = ctx.sim_state.arbitrator
    expected = MARGIN_MULTIPLIER * 10.0 * 1440.0 / 3600.0
    assert arb.soc_floor_mwh(ctx.sim_state.bess_units[0]) == pytest.approx(expected)
    assert arb.reserve_floor_basis["bess-reserve"]["winning_term"] == "diesel_floor"
    print({"TC-ISL-01 diesel floor": expected})


def test_tc_isl_01_no_restartable_unit_records_zero():
    ctx = _context(turbine_units=[])
    arb = ctx.sim_state.arbitrator
    assert arb.soc_floor_mwh(ctx.sim_state.bess_units[0]) == 0.0
    assert arb.reserve_floor_basis["bess-reserve"]["basis"] == (
        "no restartable synchronous unit"
    )
    print({"TC-ISL-01 no restartable": arb.reserve_floor_basis})


def test_tc_isl_01_min_down_and_inflight_countdown():
    ctx = _context()
    state = ctx.sim_state
    unit = state.turbines[0]
    unit.config.min_down_enabled = True
    # PROPOSED_HERE: exactly 90 seconds still unavailable in this test only.
    unit.config.t_min_down_s = 90.0
    unit._stop_time_s = 0.0
    assert unit.start_eligibility(0.0) == (False, "min_down")
    assert state.arbitrator.soc_floor_mwh(state.bess_units[0]) == pytest.approx(
        MARGIN_MULTIPLIER * 10.0 * 690.0 / 3600.0
    )
    unit.command_start(90.0)
    state.arbitrator.reserve_sim_time_s = 90.0
    unit._time_to_online_s = 120.0  # PROPOSED_HERE: observable remaining countdown.
    assert state.arbitrator.soc_floor_mwh(state.bess_units[0]) == pytest.approx(
        MARGIN_MULTIPLIER * 10.0 * 120.0 / 3600.0
    )
    basis = state.arbitrator.reserve_floor_basis["bess-reserve"]
    assert basis["start_duration_s"] == 120.0
    assert basis["eligibility_wait_s"] == 0.0
    assert basis["basis"] == "starting_remaining"
    print({"TC-ISL-01 STARTING": basis})


def test_tc_isl_01_above_capacity_warning_attribution_only():
    ctx = _context()
    state = ctx.sim_state
    state.bess_units[0].config.usable_mwh = 1.0  # PROPOSED_HERE: over-floor fixture.
    floor = state.arbitrator.soc_floor_mwh(state.bess_units[0])
    warnings = reserve_capacity_warnings(state)
    assert floor > 1.0
    assert warnings[0]["winning_term"] == "d2r_bridge"
    assert warnings[0]["floor_mwh"] == floor
    assert state.arbitrator.soc_floor_mwh(state.bess_units[0]) == floor
    print({"TC-ISL-01 warning": warnings})


def test_tc_isl_01_hot_standby_release_basis_and_unchanged_interlocks():
    ctx = _context()
    state = ctx.sim_state
    unit = state.turbines[0]
    unit.config.hot_standby = True
    assert unit.start_eligibility(0.0) == (False, "hot_standby")
    floor = state.arbitrator.soc_floor_mwh(state.bess_units[0])
    basis = state.arbitrator.reserve_floor_basis["bess-reserve"]
    assert basis["basis"] == "hot_standby_release"
    assert basis["eligibility_wait_s"] == 0.0
    assert floor == pytest.approx(MARGIN_MULTIPLIER * 10.0 * 600.0 / 3600.0)
    assert unit.config.hot_standby
    assert unit.state == TurbineState.OFFLINE
    # PROPOSED_HERE: blocked release fixture, not a change to machine guards.
    unit.config.min_down_enabled = True
    unit.config.t_min_down_s = 90.0
    unit._stop_time_s = 0.0
    assert state.arbitrator.soc_floor_mwh(state.bess_units[0]) == 0.0
    assert state.arbitrator.reserve_floor_basis["bess-reserve"]["basis"] == (
        "no restartable synchronous unit"
    )
    assert unit.config.hot_standby
    print({"TC-ISL-01 hot standby": basis, "blocked_floor": 0.0})


@pytest.mark.parametrize("overrides", [
    {"island_mode": False},
    {"bess_units": [{
        "asset_id": "bess-reserve", "rated_mw": 10.0, "usable_mwh": 20.0,
        "initial_soc_fraction": 1.0, "grid_forming": False,
    }]},
])
def test_tc_isl_02_grid_tied_or_nonforming_not_applied(overrides):
    ctx = _context(**overrides)
    assert ctx.sim_state.arbitrator.soc_floor_mwh(ctx.sim_state.bess_units[0]) == 0.0
    print({"TC-ISL-02 inapplicable": overrides})


def test_tc_isl_02_live_grid_forming_block_fc_not_applied():
    ctx = _context(fuel_cell_enabled=True, fuel_cell_units=[{
        "asset_id": "fc-reserve", "block_rated_mw": 1.0, "block_count": 1,
        "initial_running_blocks": 1, "initial_hot_standby_blocks": 0,
        "min_stable_frac": .1, "grid_forming": True,
    }])
    state = ctx.sim_state
    # PROPOSED_HERE: explicit 0.5 MW delivered FC fixture, independent of a
    # site's demand policy (which is not what this reserve-scope test checks).
    for array in state.fuel_cell_module.arrays:
        array.set_load_following_target_mw(.5)
        array.advance(0.0, 5.0)
    assert any(array.output_mw() > 0.0 for array in state.fuel_cell_module.arrays)
    assert state.arbitrator.soc_floor_mwh(state.bess_units[0]) == 0.0
    print({"TC-ISL-02 live FC": state.arbitrator.reserve_floor_basis})


@pytest.mark.parametrize("on_bus", [None, "turbine", "diesel"])
def test_tc_isl_03_conditional_release_and_unserved(on_bus):
    extra = {}
    if on_bus == "diesel":
        extra["diesel_units"] = [{
            "asset_id": "diesel-live", "rated_mw": 1.0, "role": "primary",
            "delta_t_start_s": 1.0, "residual_ramp_s": 0.0,
        }]
    ctx = _context(**extra)
    state = ctx.sim_state
    if on_bus == "turbine":
        # Keep the original OFFLINE candidate while another GT forms the grid.
        live = copy.deepcopy(state.turbines[0])
        live.config.asset_id = "gt-live"
        live.state = TurbineState.SYNCHRONISED
        state.turbines.append(live)
    elif on_bus == "diesel":
        state.diesel_units[0].state = DieselState.SYNCHRONISED
    bess = state.bess_units[0]
    floor = state.arbitrator.soc_floor_mwh(bess)
    bess.soc_mwh = floor
    state.compute_floor_mw = 10.0  # PROPOSED_HERE: explicit gap exceeding the 1 MW source.
    result = _tick(state)
    if on_bus is None:
        assert bess.soc_mwh == pytest.approx(floor)
        assert result.bess_output_mw == 0.0
        assert result.p_unserved_mw > 0.0
    else:
        assert bess.soc_mwh < floor
        assert result.bess_output_mw > 0.0
    assert result.physical_balance.passed
    print({"TC-ISL-03": on_bus, "floor_mwh": floor,
           "end_soc_mwh": bess.soc_mwh, "bess_mw": result.bess_output_mw,
           "unserved_mw": result.p_unserved_mw,
           "balance_passed": result.physical_balance.passed})
