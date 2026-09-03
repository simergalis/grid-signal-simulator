"""Phase 2 integration coverage for the aggregate fuel-cell module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.schemas import ScenarioSpec
from core._plane_guard import _EVALUATE_TICK_PERMITTED
from core.fuel_cell_module import FuelCellState
from core.models import WorkloadEventType, WorkloadSignal
from core.sim_clock import SimClock
from core.simulation_core import evaluate_tick
from runtime.scenario_factory import build_run_context_from_spec


def _tick(ctx, sim_time: float, dt_seconds: float = 5.0):
    clock = SimClock(
        sim_time=sim_time,
        dt_seconds=dt_seconds,
        wall_stamp_utc=sim_time,
        rate=1.0,
        tick_seq=int(sim_time / dt_seconds) + 1,
    )
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        return evaluate_tick(ctx.sim_state, clock)
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


def _context(**overrides):
    spec = {
        "name": "fuel-cell-phase-2",
        "frequency_nominal_hz": 60.0,
        "power_factor": 0.85,
        "pue_base": 1.03,
        "island_mode": False,
        "turbine_units": [],
        "bess_units": [],
        "solar_rated_mw": 0.0,
        "fuel_cell_enabled": True,
        "fuel_cell_rated_mw": 5.0,
        "fuel_cell_stack_count": 1,
        "workload_events": [],
        "end_sim_time": 300.0,
    }
    spec.update(overrides)
    return build_run_context_from_spec("fuel-cell-phase-2", spec)


def test_existing_fuel_cell_scenarios_default_to_one_running_full_target_array():
    scenario_paths = [
        "demo-fc-bess-grid-peak.json",
        "demo-grid-fc-bess-shaped-load.json",
        "scenario-turbine-01.json",
        "scenario-kube-peak-overage.json",
        "scenario-uneven-multisched-01.json",
    ]

    for filename in scenario_paths:
        raw = json.loads(
            (Path(__file__).parents[1] / "config" / "scenarios" / filename).read_text()
        )
        spec = ScenarioSpec.model_validate(raw)
        ctx = build_run_context_from_spec(
            f"fuel-cell-default-{filename}",
            spec.model_dump(),
        )
        module = ctx.sim_state.fuel_cell_module

        assert module is not None
        assert module.state is FuelCellState.RUNNING
        assert module.target_output_mw == pytest.approx(
            raw["fuel_cell_rated_mw"] * raw["fuel_cell_stack_count"]
        )
        assert ctx.sim_state.fuel_cell_rated_mw == module.config.rated_mw


def test_explicit_state_and_target_are_applied_to_the_single_aggregate_module():
    ctx = _context(
        fuel_cell_rated_mw=4.0,
        fuel_cell_stack_count=2,
        fuel_cell_initial_state="warming",
        fuel_cell_baseload_target_mw=6.0,
    )
    module = ctx.sim_state.fuel_cell_module

    assert module is not None
    assert module.state is FuelCellState.WARMING
    assert module.target_output_mw == 6.0
    assert module.config.rated_mw == 8.0
    assert module.time_remaining_s == module.config.cold_start_s


@pytest.mark.parametrize("initial_state", [FuelCellState.COLD, FuelCellState.WARMING])
def test_cold_and_warming_arrays_report_zero_output(initial_state):
    ctx = _context(fuel_cell_initial_state=initial_state.value)
    tick = _tick(ctx, 0.0)

    assert tick.fuel_cell_output_mw == 0.0


def test_fixed_target_survives_a_step_load_and_output_remains_rate_limited():
    ctx = _context(fuel_cell_baseload_target_mw=5.0)
    ctx.sim_state.apply_workload_signal(
        WorkloadSignal(
            event_id="phase2-start",
            job_id="phase2-job",
            event_type=WorkloadEventType.STARTING,
            timestamp=0.0,
            hardware_profile_id="enterprise_8gpu_air",
            node_count=10,
            workload_class="training",
            site_id=ctx.sim_state.site.site_id,
        ),
        dt_lead_seconds=0.0,
    )
    first = _tick(ctx, 0.0)

    ctx.sim_state.apply_workload_signal(
        WorkloadSignal(
            event_id="phase2-scale",
            job_id="phase2-job",
            event_type=WorkloadEventType.SCALE,
            timestamp=5.0,
            hardware_profile_id="enterprise_8gpu_air",
            node_count=100,
            workload_class="training",
            site_id=ctx.sim_state.site.site_id,
        ),
        dt_lead_seconds=0.0,
    )
    second = _tick(ctx, 5.0)

    module = ctx.sim_state.fuel_cell_module
    assert module is not None
    assert second.p_compute_demand_mw > first.p_compute_demand_mw
    assert module.target_output_mw == 5.0
    assert second.fuel_cell_output_mw - first.fuel_cell_output_mw <= (
        module.config.ramp_rate_mw_per_s * 5.0 + 1e-9
    )


def test_fuel_cell_surplus_is_sent_to_the_existing_bess_charge_path():
    ctx = _context(
        bess_units=[{
            "asset_id": "bess-0",
            "rated_mw": 5.0,
            "usable_mwh": 5.0,
            "initial_soc_fraction": 0.5,
            "grid_forming": False,
            "p_anchor_reserve_mw": 0.0,
        }],
    )
    tick = _tick(ctx, 0.0)

    assert tick.fuel_cell_output_mw > 0.0
    assert tick.bess_output_mw < 0.0