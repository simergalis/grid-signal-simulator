"""Regression coverage for the seeded 100 MW fuel-cell data-center scenario."""

from __future__ import annotations

import json

import pytest

from api.routes.scenarios import build_seeded_store
from core.generation_factory import peak_compute_mw
from runtime.scenario_factory import build_run_context_from_spec


SCENARIO_ID = "scenario-100mw-fuel-cell-bess-diesel"
SCHEDULER_TYPES = {"K8S", "SLURM", "RAY"}
STEP_NODE_TOTALS = {
    0.0: 190,
    180.0: 952,
    360.0: 2856,
    540.0: 6663,
    720.0: 4759,
    900.0: 1428,
    1080.0: 190,
}


def _seeded_spec() -> dict:
    store = build_seeded_store()
    record = store.get(SCENARIO_ID)
    assert record is not None, f"seeded scenario {SCENARIO_ID!r} is missing"
    return json.loads(record.spec_json)


def test_100mw_fuel_cell_scenario_is_seeded_with_exclusive_supply_mix() -> None:
    """The catalog entry preserves the requested generation and storage mix."""
    spec = _seeded_spec()

    assert spec["island_mode"] is True
    assert spec["dt_lead_seconds"] == pytest.approx(30.0)
    assert spec["solar_rated_mw"] == 0.0
    assert spec["turbine_units"] == []
    assert spec["end_sim_time"] == pytest.approx(1260.0)
    assert spec.get("kube_config") is None
    assert not spec.get("kube_clusters")

    events = spec["workload_events"]
    starts = [event for event in events if event["event_type"] == "starting"]
    ends_by_job = {
        event["job_id"]: event
        for event in events
        if event["event_type"] == "job_end"
    }
    assert len(starts) == 21
    assert len(ends_by_job) == 21

    for timestamp, expected_nodes in STEP_NODE_TOTALS.items():
        level_jobs = [event for event in starts if event["timestamp"] == timestamp]
        assert {event["scheduler_type"] for event in level_jobs} == SCHEDULER_TYPES
        assert sum(event["node_count"] for event in level_jobs) == expected_nodes
        for start in level_jobs:
            end = ends_by_job[start["job_id"]]
            assert end["timestamp"] - start["timestamp"] == pytest.approx(180.0)
            assert end["scheduler_type"] == start["scheduler_type"]

    assert spec["fuel_cell_enabled"] is True
    assert spec["fuel_cell_rated_mw"] == pytest.approx(100.0)
    assert spec["fuel_cell_stack_count"] == 1
    assert spec["fuel_cell_baseload_target_mw"] == pytest.approx(0.0)
    assert spec["fuel_cell_load_following"] is True
    assert spec["fuel_cell_ramp_rate_mw_per_s"] == pytest.approx(5.0)
    assert spec["fuel_cell_ramp_down_rate_mw_per_s"] == pytest.approx(11.0)
    assert spec["fuel_cell_min_stable_fraction"] == pytest.approx(0.0)

    assert len(spec["bess_units"]) == 1
    bess = spec["bess_units"][0]
    assert bess["rated_mw"] == pytest.approx(25.0)
    assert bess["usable_mwh"] == pytest.approx(25.0)
    assert bess["initial_soc_fraction"] == pytest.approx(1.0)
    assert bess["grid_forming"] is True

    diesel_block = spec["diesel_power_block"]
    assert diesel_block["enabled"] is True
    assert diesel_block["target_capacity_mw"] == pytest.approx(110.0)
    assert diesel_block["unit_rating_mw"] == pytest.approx(10.0)
    assert diesel_block["min_fuel_runtime_hours"] == pytest.approx(48.0)
    assert len(spec["diesel_units"]) == 11
    assert sum(unit["rated_mw"] for unit in spec["diesel_units"]) == pytest.approx(110.0)


def test_100mw_fuel_cell_scenario_builds_and_starts_with_backup_ready() -> None:
    """A real context tick starts cleanly while diesel remains available."""
    spec = _seeded_spec()
    context = build_run_context_from_spec(
        "test-100mw-fuel-cell-scenario",
        spec,
        playback_speed=0.0,
    )

    assert context.sim_state.site.island_mode.value == "islanded"
    assert context.sim_state.fuel_cell_module is not None
    assert context.sim_state.fuel_cell_rated_mw == pytest.approx(100.0)
    assert len(context.sim_state.diesel_units) == 11
    assert all(unit.state.value == "offline" for unit in context.sim_state.diesel_units)
    assert context.dt_lead_seconds == pytest.approx(30.0)
    assert len(context.events) == 24
    for timestamp, expected_nodes in STEP_NODE_TOTALS.items():
        cluster_events = [
            event for event in context.events
            if event.timestamp == timestamp
        ]
        expected_type = "starting" if timestamp == 0.0 else "scale"
        assert {event.event_type.value for event in cluster_events} == {expected_type}
        assert {event.scheduler_type for event in cluster_events} == SCHEDULER_TYPES
        assert sum(event.node_count for event in cluster_events) == expected_nodes

    final_events = [
        event for event in context.events
        if event.timestamp == 1260.0
    ]
    assert {event.event_type.value for event in final_events} == {"job_end"}
    assert {event.scheduler_type for event in final_events} == SCHEDULER_TYPES

    tick = context.step()

    assert tick.fuel_cell_state == "running"
    assert tick.fuel_cell_output_mw == pytest.approx(tick.p_demand_mw)
    assert tick.p_imbalance_mw == pytest.approx(0.0, abs=1e-9)
    assert tick.frequency_hz == pytest.approx(60.0)
    assert tick.diesel_enabled is True
    assert tick.diesel_fleet_state == "idle"
    assert tick.diesel_n_synced == 0
    assert tick.diesel_n_out_of_service == 0
    assert tick.diesel_fuel_runtime_hours_remaining == pytest.approx(48.0)
    assert tick.bess_soc_fraction == pytest.approx(1.0)

    # The scheduler jobs peak at 70 MW of IT demand, not the old 100 MW pulse.
    assert peak_compute_mw(spec) == pytest.approx(70.0, abs=0.01)


def test_100mw_fuel_cell_scenario_balances_the_scheduler_staircase() -> None:
    """Load-following fuel cells close every scheduler-driven stair edge."""
    context = build_run_context_from_spec(
        "test-100mw-fuel-cell-staircase",
        _seeded_spec(),
        playback_speed=0.0,
    )

    ticks = [context.step() for _ in range(252)]

    assert max(abs(tick.p_imbalance_mw or 0.0) for tick in ticks) < 0.001
    assert max(abs(tick.frequency_hz - 60.0) for tick in ticks) < 0.002
    assert max(tick.diesel_output_mw for tick in ticks) == pytest.approx(0.0)
    assert max(abs(tick.bess_output_mw) for tick in ticks) <= 25.0
    assert max(tick.p_compute_demand_mw for tick in ticks) == pytest.approx(
        70.0, abs=0.01
    )