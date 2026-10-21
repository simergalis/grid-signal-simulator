"""TC-ISL-19..22, D10 + IMPL-ISL-14/15.

PROPOSED_HERE diagnostic fixture magnitudes are synthetic, not new plant
defaults. The runtime minimum's source/rationale is documented on the module.
"""
import copy
import pytest

from core.asset_modules import DieselModule
from core.diesel_fleet import DieselFleetCoordinator
from core.models import DieselConfig, DieselState
from core.simulation_core import _cost_ranked_dispatch_allocations
from runtime.scenario_factory import build_run_context_from_spec
from tests.test_diesel_phase3 import _spec, _tick


def _live_context():
    spec = copy.deepcopy(_spec(diesel_enabled=True))
    spec["diesel_units"][0].update(
        rated_mw=20.0, f_block=1.0, min_run_s=900.0, cooldown_s=300.0,
    )
    spec["diesel_power_block"].update(
        unit_rating_mw=20.0, target_capacity_mw=20.0,
        min_run_s=900.0, cooldown_s=300.0,
    )
    spec["bess_units"][0].update(rated_mw=10.0, usable_mwh=20.0)
    ctx = build_run_context_from_spec("D10-regression", spec)
    unit = ctx.sim_state.diesel_units[0]
    unit.state = DieselState.SYNCHRONISED
    unit._current_output_mw = 20.0
    unit._run_start_s = 0.0
    ctx.sim_state.diesel_fleet_coordinator.episode_id = "D10-fixture"
    return ctx


def test_tc_isl_19_closing_gap_backs_diesel_down_before_curtailment():
    ctx = _live_context()
    ctx.sim_state.compute_floor_mw = 30.0
    high = _tick(ctx.sim_state, 1)
    ctx.sim_state.compute_floor_mw = 1.0
    low = _tick(ctx.sim_state, 2)
    assert high.diesel_output_mw > 6.0
    assert low.diesel_output_mw == pytest.approx(6.0)
    assert high.p_dispatch_curtailed_mw == pytest.approx(0.0)
    assert low.p_dispatch_curtailed_mw == pytest.approx(0.0)
    assert high.physical_balance.passed
    assert low.physical_balance.passed


def test_tc_isl_20_shared_merit_order_rising_and_falling():
    for demand in (20.0, 40.0, 60.0, 80.0, 60.0, 40.0, 20.0):
        result = _cost_ranked_dispatch_allocations(
            demand, bess_available_mw=10.0, turbine_available_mw=20.0,
            fuel_cell_available_mw=30.0, diesel_available_mw=40.0,
        )
        assert result["bess-fleet"] == min(10.0, demand)
        assert result["turbine-fleet"] == min(20.0, max(0.0, demand - 10.0))
        assert result["fuel-cell-fleet"] == min(30.0, max(0.0, demand - 30.0))
        assert result["diesel-fleet"] == max(0.0, demand - 60.0)
    # Reversing a falling-demand unload must not expose stale rated capacity.
    unit = DieselModule(DieselConfig(asset_id="resume", rated_mw=20.0, role="primary"))
    unit.state = DieselState.UNLOADING
    unit._current_output_mw = 2.0
    unit._dispatch_ceiling_mw = 20.0
    unit.resume_from_unloading()
    unit.apply_dispatch_target(20.0)
    assert unit.output_mw() == 6.0
    # Explicit targets hold omitted GTs at minimum; they are not available
    # primary headroom for the coordinator's dispatch-aware gap.
    ctx = _live_context()
    ctx.sim_state.compute_floor_mw = 20.0
    ctx.sim_state._preload_targets_mw = {"not-on-bus": 0.0}
    constrained = _tick(ctx.sim_state, 1)
    assert constrained.turbine_output_mw == 0.0
    assert constrained.diesel_output_mw > 6.0
    assert constrained.p_unserved_mw == pytest.approx(0.0)
    assert constrained.physical_balance.passed


def test_tc_isl_21_unloading_power_fuel_and_physical_balance():
    ctx = _live_context()
    state = ctx.sim_state
    state.compute_floor_mw = 1.0
    unit = state.diesel_units[0]
    unit.state = DieselState.UNLOADING
    unit._current_output_mw = 6.0
    unit._unload_start_output_mw = 6.0
    before = state.diesel_fleet_coordinator.fuel_remaining_gal
    tick = _tick(state, 1)
    assert unit.is_on_bus
    assert tick.diesel_output_mw == pytest.approx(5.9)
    assert state.diesel_fleet_coordinator.output_mw == pytest.approx(5.9)
    assert before - state.diesel_fleet_coordinator.fuel_remaining_gal == pytest.approx(
        5.9 / 20.0 * 230.0 * 5.0 / 3600.0,
    )
    assert tick.physical_balance.passed


def test_tc_isl_22_refused_stop_does_not_credit_hold_or_shorten_ramp():
    unit = DieselModule(DieselConfig(
        asset_id="timing-fixture", rated_mw=20.0, role="primary", f_block=1.0,
    ))
    unit.state = DieselState.SYNCHRONISED
    unit._current_output_mw = 20.0
    unit._run_start_s = 0.0
    coordinator = DieselFleetCoordinator([unit])
    coordinator.episode_id = "timing-fixture"
    for t in (5.0, 100.0, 895.0):
        coordinator.step(gap_mw=0.0, sim_time=t, dt_seconds=5.0)
        assert coordinator._restore_elapsed_s == 0.0
        assert unit.state == DieselState.SYNCHRONISED
    coordinator.step(gap_mw=0.0, sim_time=900.0, dt_seconds=5.0)
    assert unit.state == DieselState.UNLOADING
    for elapsed in range(5, 300, 5):
        coordinator.step(gap_mw=0.0, sim_time=900.0 + elapsed, dt_seconds=5.0)
        assert unit.state == DieselState.UNLOADING
        assert unit.output_mw() == pytest.approx(20.0 * (1.0 - elapsed / 300.0))
    coordinator.step(gap_mw=0.0, sim_time=1200.0, dt_seconds=5.0)
    assert unit.state == DieselState.OFFLINE
    assert unit.output_mw() == 0.0
