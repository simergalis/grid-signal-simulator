"""TC-ISL-15/16 — D7 and IMPL-ISL-10 accounting regressions."""
import pytest

from runtime.scenario_factory import build_run_context_from_spec
from tests.test_forecast_path import _run_tick, _starting_signal
from tests.test_grid_import_limit_scenario import _grid_only_tick
from tests.test_addendum_g_stage3_option_c import _factory_tick


def test_tc_isl_15a_capped_grid_shortfall_is_unserved():
    tick = _grid_only_tick(10.0)
    assert tick.p_demand_mw > 10.0
    assert tick.grid_exchange_mw == pytest.approx(-10.0)
    assert tick.p_unserved_mw == pytest.approx(tick.p_demand_mw - 10.0)
    assert tick.p_served_mw == pytest.approx(10.0)
    assert tick.physical_balance.passed is True


def test_tc_isl_15b_uncapped_grid_is_unchanged():
    tick = _grid_only_tick(None)
    assert tick.p_unserved_mw == 0.0
    assert tick.p_served_mw == tick.p_demand_mw
    assert tick.p_generation_mw == pytest.approx(tick.p_demand_mw)
    assert tick.physical_balance.passed is True


def test_tc_isl_15c_islanded_shortfall_is_unchanged():
    spec = {
        "name": "tc-isl-15c", "island_mode": True,
        "frequency_nominal_hz": 60.0, "power_factor": 0.85,
        "turbine_units": [], "bess_units": [], "solar_rated_mw": 0.0,
        "fuel_cell_enabled": False, "pue_base": 1.03,
    }
    state = build_run_context_from_spec("tc-isl-15c", spec).sim_state
    state.apply_workload_signal(
        _starting_signal(nodes=2000, ramp_s=1.0, timestamp=0.0), dt_lead_seconds=0.0
    )
    tick = _run_tick(state, sim_time=5.0, dt=5.0)
    assert tick.p_demand_mw > 0.0
    assert tick.p_generation_mw == 0.0
    assert tick.p_unserved_mw == tick.p_demand_mw
    assert tick.p_served_mw == 0.0
    assert tick.physical_balance.passed is True


def test_tc_isl_16_fc_rocof_trip_reconciles_pretrip_surplus():
    # The unchanged Stage-3 fixture produces pre-trip FC output at its stable floor.
    tick = _factory_tick(grid_forming=True, min_stable_frac=.5)
    assert tick.fuel_cell_ride_through_trips[0]["reason"] == "rocof"
    assert tick.fuel_cell_output_mw == 0.0
    assert tick.p_dispatch_curtailed_mw == 0.0
    assert tick.physical_balance.terms.p_curtailment_mw == 0.0
    assert tick.physical_balance.passed is True
