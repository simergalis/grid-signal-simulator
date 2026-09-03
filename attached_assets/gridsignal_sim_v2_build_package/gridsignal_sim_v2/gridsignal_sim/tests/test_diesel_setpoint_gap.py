"""DR-2026-09-02-DIESEL-SETPOINT-GAP regression coverage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.schemas import ScenarioSpec
from runtime.scenario_factory import build_run_context_from_spec


_HYBRID_SCENARIO = (
    Path(__file__).parents[1]
    / "config"
    / "scenarios"
    / "scenario-hybrid-ai-100mw-addendum-i.json"
)


def _hybrid_context():
    raw_spec = json.loads(_HYBRID_SCENARIO.read_text())
    # ScenarioSpec materializes the diesel_power_block into its 20-unit fleet,
    # matching the validated API/run-start path used by the simulator.
    spec = ScenarioSpec.model_validate(raw_spec).model_dump(mode="json")
    return build_run_context_from_spec(
        "diesel-setpoint-gap-regression",
        spec,
        playback_speed=0.0,
    )


def test_hybrid_scenario_contract_and_reserve_alert_timing() -> None:
    """The authored hybrid scenario keeps its sizing and alert contract."""
    raw_spec = json.loads(_HYBRID_SCENARIO.read_text())
    spec = ScenarioSpec.model_validate(raw_spec).model_dump(mode="json")
    ctx = build_run_context_from_spec(
        "diesel-setpoint-gap-scenario-contract",
        spec,
        playback_speed=0.0,
    )
    state = ctx.sim_state

    assert raw_spec["fuel_cell_rated_mw"] == 100.0
    assert raw_spec["fuel_cell_stack_count"] == 1
    assert state.fuel_cell_rated_mw == pytest.approx(100.0)
    assert state.fuel_cell_module is not None
    assert state.fuel_cell_module.config.rated_mw == pytest.approx(100.0)

    assert len(raw_spec["bess_units"]) == 1
    assert raw_spec["bess_units"][0]["rated_mw"] == pytest.approx(15.0)
    assert raw_spec["bess_units"][0]["usable_mwh"] == pytest.approx(6.0)
    assert len(state.bess_units) == 1
    assert state.bess_units[0].config.rated_mw == pytest.approx(15.0)
    assert state.bess_units[0].config.usable_mwh == pytest.approx(6.0)

    assert raw_spec["turbine_units"] == []
    assert len(spec["diesel_units"]) == 20
    assert all(
        unit["rated_mw"] == pytest.approx(3.25)
        for unit in spec["diesel_units"]
    )
    assert [
        unit["start_offset_s"] for unit in spec["diesel_units"]
    ] == [float(offset) for offset in range(0, 40, 2)]
    assert raw_spec["diesel_power_block"]["start_stagger_interval_s"] == pytest.approx(2.0)
    assert raw_spec["diesel_power_block"]["target_capacity_mw"] == pytest.approx(65.0)
    assert len(state.diesel_units) == 20
    assert sum(unit.config.rated_mw for unit in state.diesel_units) == pytest.approx(65.0)

    training_step = next(
        event for event in raw_spec["workload_events"]
        if event["timestamp"] == 90.0
        and event["event_type"] == "starting"
    )
    training_step_end = next(
        event for event in raw_spec["workload_events"]
        if event["timestamp"] == 210.0
        and event["event_type"] == "job_end"
    )
    assert training_step["node_count"] == 3012
    assert training_step_end["node_count"] == 0
    assert training_step["node_count"] * 10.2 * raw_spec["pue_base"] / 1000.0 == pytest.approx(
        33.0,
        abs=0.01,
    )

    reconciled_floor_mwh = state.arbitrator.soc_floor_mwh(state.bess_units[0])
    assert reconciled_floor_mwh == pytest.approx(5.52)

    results = []
    while ctx.sim_time < 100.0:
        results.append(ctx.step())

    alert_times = [
        result.sim_time_seconds
        for result in results
        if result.insufficient_reserve_alert
    ]
    assert alert_times == [5.0, 95.0]
    before_training_step = next(
        result for result in results if result.sim_time_seconds == 90.0
    )
    after_training_step = next(
        result for result in results if result.sim_time_seconds == 95.0
    )
    assert after_training_step.net_demand_mw - before_training_step.net_demand_mw == pytest.approx(
        33.0,
        abs=0.01,
    )


def test_hybrid_covered_demand_does_not_release_bess_reserve() -> None:
    """At the former t=480 s failure point, diesel + fuel cell cover demand."""
    ctx = _hybrid_context()
    state = ctx.sim_state
    bess = state.bess_units[0]
    reconciled_floor_mwh = state.arbitrator.soc_floor_mwh(bess)
    rows = []

    while ctx.sim_time < 480.0:
        result = ctx.step()
        rows.append(
            (
                result,
                bess.soc_mwh,
                state._prev_diesel_output_mw,
            )
        )

    result_480, soc_480_mwh, prev_diesel_480_mw = rows[-1]
    assert result_480.sim_time_seconds == pytest.approx(480.0)
    assert result_480.fuel_cell_output_mw + result_480.diesel_output_mw > (
        result_480.net_demand_mw
    )
    assert result_480.bess_output_mw == pytest.approx(0.0, abs=1e-9)
    assert soc_480_mwh == pytest.approx(reconciled_floor_mwh)
    assert soc_480_mwh >= reconciled_floor_mwh - 1e-9
    assert prev_diesel_480_mw == pytest.approx(result_480.diesel_output_mw)

    # Once the diesel fleet and fuel cell cover the load, reserve must remain
    # intact and BESS must not return to the old 14 MW discharge ceiling.
    covered_rows = [
        (result, soc_mwh)
        for result, soc_mwh, _prev_diesel_mw in rows
        if result.sim_time_seconds >= 55.0
        and result.fuel_cell_output_mw + result.diesel_output_mw
        >= result.net_demand_mw
    ]
    assert covered_rows
    assert max(abs(result.bess_output_mw) for result, _ in covered_rows) <= 1e-9
    assert min(soc_mwh for _, soc_mwh in covered_rows) >= (
        reconciled_floor_mwh - 1e-9
    )


def test_hybrid_first_tick_has_zero_diesel_credit() -> None:
    """Cold start uses no diesel credit before the first diesel snapshot."""
    ctx = _hybrid_context()
    state = ctx.sim_state

    assert state._prev_diesel_output_mw == 0.0
    result = ctx.step()

    assert result.sim_time_seconds == pytest.approx(5.0)
    assert result.diesel_output_mw == 0.0
    assert state._prev_diesel_output_mw == 0.0
    assert result.bess_output_mw == pytest.approx(14.0)


def test_empty_diesel_fleet_keeps_previous_output_zero() -> None:
    """The disabled-fleet path retains the existing zero-diesel behavior."""
    raw_spec = json.loads(_HYBRID_SCENARIO.read_text())
    raw_spec.pop("diesel_power_block")
    spec = ScenarioSpec.model_validate(raw_spec).model_dump(mode="json")
    spec["diesel_units"] = []
    ctx = build_run_context_from_spec(
        "diesel-setpoint-gap-no-diesel",
        spec,
        playback_speed=0.0,
    )

    assert ctx.sim_state.diesel_units == []
    assert ctx.sim_state._prev_diesel_output_mw == 0.0
    result = ctx.step()

    assert result.diesel_enabled is False
    assert result.diesel_output_mw == 0.0
    assert ctx.sim_state._prev_diesel_output_mw == 0.0