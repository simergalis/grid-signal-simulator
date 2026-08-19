"""Fuel-cell saturation turbine-commit policy regression tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from api.schemas import ScenarioSpec
from core._plane_guard import _EVALUATE_TICK_PERMITTED
from core.asset_modules import CoolingModule, GPUModule, TurbineModule
from core.models import (
    IslandMode,
    SiteConfig,
    ThermalState,
    TurbineConfig,
    TurbineState,
)
from core.sim_clock import SimClock
from core.simulation_core import SimulationState, evaluate_tick
from runtime.scenario_factory import build_run_context_from_spec


def _turbine(asset_id: str, thermal_state: ThermalState) -> TurbineModule:
    return TurbineModule(
        TurbineConfig(
            asset_id=asset_id,
            rated_mw=25.0,
            hot_standby=True,
            initial_thermal_state=thermal_state,
            min_run_enabled=False,
            min_down_enabled=False,
        )
    )


def _state(*, demand_mw: float, with_turbines: bool = True) -> SimulationState:
    site = SiteConfig(
        site_id="fc-turbine-commit-test",
        pue_base=1.0,
        alpha_max=0.0,
        tau_seconds=20.0,
        dt_thermal_seconds=90.0,
        island_mode=IslandMode.GRID_TIE,
        fuel_cell_turbine_commit_fraction=0.8,
    )
    # Deliberately put COLD first in roster order: selection must use readiness,
    # not array order.
    turbines = (
        [
            _turbine("cold", ThermalState.COLD),
            _turbine("hot", ThermalState.HOT),
            _turbine("warm", ThermalState.WARM),
        ]
        if with_turbines
        else []
    )
    state = SimulationState(
        run_id="fc-turbine-commit-run",
        site=site,
        gpu_modules=[
            GPUModule(
                asset_id="gpu-0",
                site=site,
                hardware_library={},
            )
        ],
        turbines=turbines,
        bess_units=[],
        solar_arrays=[],
        cooling=CoolingModule(asset_id="cooling-0", site=site),
    )
    state.compute_floor_mw = demand_mw
    state.fuel_cell_rated_mw = 24.0
    return state


def _tick(state: SimulationState, sim_time: float):
    clock = SimClock(
        sim_time=sim_time,
        dt_seconds=5.0,
        wall_stamp_utc=sim_time,
        rate=0.0,
        tick_seq=int(sim_time / 5.0) + 1,
    )
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        return evaluate_tick(state, clock)
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


def _by_id(state: SimulationState, asset_id: str) -> TurbineModule:
    return next(t for t in state.turbines if t.asset_id == asset_id)


def test_exact_80_percent_crossing_starts_hot_and_promotes_reserve() -> None:
    state = _state(demand_mw=19.199)

    below = _tick(state, 0.0)
    assert below.fuel_cell_output_mw == pytest.approx(19.199)
    assert below.commitment_action == "hold"
    assert all(t.state == TurbineState.OFFLINE for t in state.turbines)

    state.compute_floor_mw = 19.2
    crossing = _tick(state, 5.0)

    assert crossing.fuel_cell_output_mw == pytest.approx(19.2)
    assert crossing.commitment_action == "commit"
    assert crossing.commitment_target_unit_id == "hot"
    assert "reached 80%" in crossing.commitment_reason
    assert "warm:warm->hot" in crossing.commitment_reason
    assert "cold:cold->warm" in crossing.commitment_reason
    assert _by_id(state, "hot").state == TurbineState.STARTING
    assert _by_id(state, "hot").config.hot_standby is False
    assert _by_id(state, "warm").thermal_state == ThermalState.HOT
    assert _by_id(state, "cold").thermal_state == ThermalState.WARM
    assert state._pending_start.pending_unit_id == "hot"


def test_sustained_high_output_does_not_start_a_second_turbine() -> None:
    state = _state(demand_mw=19.2)
    first = _tick(state, 0.0)
    assert first.commitment_target_unit_id == "hot"

    sustained = _tick(state, 5.0)

    assert sustained.commitment_action == "hold"
    assert sustained.commitment_target_unit_id is None
    assert _by_id(state, "warm").state == TurbineState.OFFLINE
    assert _by_id(state, "cold").state == TurbineState.OFFLINE
    assert state._fuel_cell_commit_threshold_above is True
    assert state._fuel_cell_commit_signal_pending is False


def test_falling_below_threshold_rearms_next_crossing() -> None:
    state = _state(demand_mw=19.2)
    first = _tick(state, 0.0)
    assert first.commitment_target_unit_id == "hot"

    # Remove the first selected unit from dispatch and clear its completed start
    # register so this test can focus on crossing rearm rather than a 300 s timer.
    first_unit = _by_id(state, "hot")
    first_unit.state = TurbineState.OUT_OF_SERVICE
    first_unit._current_output_mw = 0.0
    state._pending_start.clear_on_synchronised("hot")

    state.compute_floor_mw = 10.0
    below = _tick(state, 5.0)
    assert below.fuel_cell_output_mw == pytest.approx(10.0)
    assert state._fuel_cell_commit_threshold_above is False

    state.compute_floor_mw = 19.2
    second = _tick(state, 10.0)

    assert second.commitment_action == "commit"
    assert second.commitment_target_unit_id == "warm"
    assert _by_id(state, "warm").state == TurbineState.STARTING
    assert _by_id(state, "warm")._time_to_online_s == pytest.approx(
        _by_id(state, "warm").config.hot_start_s
    )
    assert _by_id(state, "cold").thermal_state == ThermalState.HOT


def test_crossing_waits_for_existing_pending_start_then_starts_one_unit() -> None:
    state = _state(demand_mw=19.2)
    existing = _by_id(state, "hot")
    existing.config.hot_standby = False
    existing.state = TurbineState.STARTING
    existing._time_to_online_s = 300.0
    state._pending_start.record_start("hot", 0.0)

    blocked = _tick(state, 0.0)

    assert blocked.commitment_action == "hold"
    assert blocked.commitment_blocked_by == "start pending for 'hot'"
    assert state._fuel_cell_commit_signal_pending is True
    assert _by_id(state, "warm").state == TurbineState.OFFLINE
    assert _by_id(state, "cold").state == TurbineState.OFFLINE

    existing.state = TurbineState.SYNCHRONISED
    state._pending_start.clear_on_synchronised("hot")
    accepted = _tick(state, 5.0)

    assert accepted.commitment_action == "commit"
    assert accepted.commitment_target_unit_id == "warm"
    assert _by_id(state, "warm").state == TurbineState.STARTING
    assert _by_id(state, "cold").state == TurbineState.OFFLINE
    assert state._pending_start.pending_unit_id == "warm"
    assert state._fuel_cell_commit_signal_pending is False


def test_normal_commit_does_not_preempt_fuel_cell_standby_policy() -> None:
    state = _state(demand_mw=10.0)
    state._commit_cond.threshold_s = 0.0

    tick = _tick(state, 0.0)

    assert tick.fuel_cell_output_mw == pytest.approx(10.0)
    assert tick.commitment_action == "hold"
    assert tick.commitment_target_unit_id is None
    assert all(t.state == TurbineState.OFFLINE for t in state.turbines)
    assert all(t.config.hot_standby for t in state.turbines)


def test_cascade_commit_uses_promoted_hot_before_warm_in_roster() -> None:
    state = _state(demand_mw=5.0)
    state.site.fuel_cell_turbine_commit_fraction = None
    state.site.cascade_commit_fraction = 0.0
    state.fuel_cell_rated_mw = 0.0

    lead = _by_id(state, "hot")
    lead.config.hot_standby = False
    lead.state = TurbineState.SYNCHRONISED
    lead._current_output_mw = 5.0
    _by_id(state, "cold").assign_standby_thermal_state(ThermalState.WARM)
    _by_id(state, "warm").assign_standby_thermal_state(ThermalState.HOT)

    _tick(state, 0.0)

    assert _by_id(state, "warm").state == TurbineState.STARTING
    assert _by_id(state, "warm").config.hot_standby is False
    assert _by_id(state, "warm")._time_to_online_s == pytest.approx(
        _by_id(state, "warm").config.hot_start_s
    )
    assert _by_id(state, "cold").state == TurbineState.OFFLINE
    assert _by_id(state, "cold").thermal_state == ThermalState.HOT
    assert state._pending_start.pending_unit_id == "warm"


def test_site_without_turbines_is_unchanged() -> None:
    state = _state(demand_mw=19.2, with_turbines=False)

    tick = _tick(state, 0.0)

    assert tick.fuel_cell_output_mw == pytest.approx(19.2)
    assert tick.commitment_action == "hold"
    assert tick.commitment_target_unit_id is None
    assert state._fuel_cell_commit_signal_pending is False


def test_turbine_scenario_wires_80_percent_policy() -> None:
    scenario_path = (
        Path(__file__).resolve().parents[1]
        / "config"
        / "scenarios"
        / "scenario-turbine-01.json"
    )
    spec = ScenarioSpec.model_validate_json(scenario_path.read_text())
    ctx = build_run_context_from_spec(
        "fc-turbine-scenario-wiring",
        spec.model_dump(mode="json"),
    )

    assert spec.fuel_cell_turbine_commit_fraction == pytest.approx(0.8)
    assert ctx.sim_state.site.fuel_cell_turbine_commit_fraction == pytest.approx(0.8)
    assert [
        turbine.thermal_state
        for turbine in ctx.sim_state.turbines
    ] == [ThermalState.HOT, ThermalState.WARM, ThermalState.COLD]