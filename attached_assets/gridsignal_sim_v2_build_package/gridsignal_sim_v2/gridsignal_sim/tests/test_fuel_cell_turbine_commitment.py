"""Fuel-cell saturation turbine-commit policy regression tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from api.schemas import ScenarioSpec
from core._plane_guard import _EVALUATE_TICK_PERMITTED
from core.asset_modules import CoolingModule, GPUModule, TurbineModule
from core.fuel_cell_module import FuelCellConfig, FuelCellModule, FuelCellState
from core.models import (
    IslandMode,
    SiteConfig,
    ThermalState,
    TurbineConfig,
    TurbineState,
)
from core.sim_clock import SimClock
from core.simulation_core import (
    SimulationState,
    _gpu_load_fraction_at,
    evaluate_tick,
)
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
    state.fuel_cell_module = FuelCellModule(
        FuelCellConfig(
            asset_id="fuel-cell-fleet",
            rated_mw=24.0,
            baseload_target_mw=24.0,
        ),
        state=FuelCellState.RUNNING,
    )
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


def test_fc_ramp_past_80_percent_does_not_start_hot_standby_turbines() -> None:
    state = _state(demand_mw=0.0)

    ticks = [_tick(state, index * 5.0) for index in range(130)]

    assert max(tick.fuel_cell_output_mw for tick in ticks) >= 19.2
    assert ticks[-1].fuel_cell_output_mw == pytest.approx(24.0)
    assert all(tick.commitment_action == "hold" for tick in ticks)
    assert all(
        turbine.state == TurbineState.OFFLINE
        and turbine.config.hot_standby
        for turbine in state.turbines
    )


def test_falling_site_demand_does_not_change_fixed_fc_output() -> None:
    state = _state(demand_mw=18.0)

    first = _tick(state, 0.0)
    state.compute_floor_mw = 0.0
    second = _tick(state, 5.0)

    assert first.fuel_cell_output_mw == pytest.approx(12.1)
    assert second.fuel_cell_output_mw == pytest.approx(12.2)
    assert second.fuel_cell_output_mw > first.fuel_cell_output_mw
    assert first.commitment_action == "hold"
    assert second.commitment_action == "hold"
    assert all(turbine.state == TurbineState.OFFLINE for turbine in state.turbines)


def test_demand_commit_credits_measured_fuel_cell_output() -> None:
    state = _state(demand_mw=35.0)

    # Make two units genuinely on bus and leave one ordinary offline candidate.
    # The current FC output makes the N-1 floor safe; the same demand without
    # FC credit would violate it and commit the offline unit after 30 seconds.
    for asset_id in ("hot", "warm"):
        turbine = _by_id(state, asset_id)
        turbine.config.hot_standby = False
        turbine.state = TurbineState.SYNCHRONISED
        turbine._current_output_mw = 12.5
    _by_id(state, "cold").config.hot_standby = False

    ticks = [_tick(state, index * 5.0) for index in range(6)]
    latest = ticks[-1]
    net_demand_mw = max(0.0, 35.0 - latest.fuel_cell_output_mw)

    assert latest.fuel_cell_output_mw == pytest.approx(12.6)
    assert 50.0 >= net_demand_mw + 25.0
    assert 50.0 < 35.0 + 25.0
    assert all(tick.commitment_action == "hold" for tick in ticks)
    assert _by_id(state, "cold").state == TurbineState.OFFLINE

    # Ordinary demand commitment remains active: raising the residual demand
    # beyond the credited reserve floor starts the eligible non-hot candidate.
    state.compute_floor_mw = 55.0
    elevated_ticks = [_tick(state, 30.0 + index * 5.0) for index in range(6)]

    assert any(
        tick.commitment_action == "commit"
        and tick.commitment_target_unit_id == "cold"
        for tick in elevated_ticks
    )
    assert _by_id(state, "cold").state == TurbineState.STARTING


def test_elevated_demand_with_only_hot_standby_turbines_does_not_start() -> None:
    state = _state(demand_mw=35.0)

    ticks = [_tick(state, index * 5.0) for index in range(8)]

    assert state._commit_cond.sustained_s >= 30.0
    assert all(tick.commitment_action == "hold" for tick in ticks)
    assert all(
        turbine.state == TurbineState.OFFLINE
        and turbine.config.hot_standby
        for turbine in state.turbines
    )


def test_low_demand_does_not_commit_turbines() -> None:
    state = _state(demand_mw=10.0)
    state._commit_cond.threshold_s = 0.0

    tick = _tick(state, 0.0)

    assert tick.fuel_cell_output_mw == pytest.approx(12.1)
    assert tick.commitment_action == "hold"
    assert tick.commitment_target_unit_id is None
    assert all(t.state == TurbineState.OFFLINE for t in state.turbines)
    assert all(t.config.hot_standby for t in state.turbines)


def test_cascade_commit_uses_promoted_hot_before_warm_in_roster() -> None:
    state = _state(demand_mw=5.0)
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

    assert tick.fuel_cell_output_mw == pytest.approx(12.1)
    assert tick.commitment_action == "hold"
    assert tick.commitment_target_unit_id is None


def test_turbine_scenario_retains_deprecated_commit_fraction_for_compatibility() -> None:
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
    assert ctx.sim_state.gpu_load_profile[:3] == [
        (0.0, 1.2),
        (600.0, 1.0),
        (720.0, 0.5),
    ]


def test_turbine_scenario_has_120_percent_gpu_peak_for_ten_minutes() -> None:
    scenario_path = (
        Path(__file__).resolve().parents[1]
        / "config"
        / "scenarios"
        / "scenario-turbine-01.json"
    )
    spec = ScenarioSpec.model_validate_json(scenario_path.read_text())

    assert spec.gpu_load_profile[:3] == [
        (0.0, 1.2),
        (600.0, 1.0),
        (720.0, 0.5),
    ]
    assert _gpu_load_fraction_at(spec.gpu_load_profile, 599.999) == pytest.approx(1.2)
    assert _gpu_load_fraction_at(spec.gpu_load_profile, 600.0) == pytest.approx(1.0)