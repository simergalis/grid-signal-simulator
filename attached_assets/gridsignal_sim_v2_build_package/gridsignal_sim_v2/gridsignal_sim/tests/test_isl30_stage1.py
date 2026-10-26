"""Focused tests for IMPL-ISL-30/31 controller stage 1."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.schemas import ScenarioSpec, WorkloadEventSpec
from core.models import WorkloadClass, WorkloadEventType, WorkloadSignal
from runtime.scenario_factory import build_run_context_from_spec
from runtime.turbine_commitment import (
    CommitmentForecast,
    ForecastDrivenTurbineController,
)


def _event(
    start_s: float,
    *,
    job_id: str = "job-a",
    nodes: int = 40,
    submit_s: float | None = None,
) -> WorkloadSignal:
    return WorkloadSignal(
        event_id=f"starting-{job_id}",
        job_id=job_id,
        event_type=WorkloadEventType.STARTING,
        timestamp=start_s,
        hardware_profile_id="enterprise_8gpu_air",
        node_count=nodes,
        workload_class=WorkloadClass.TRAINING,
        site_id="site",
        submit_time_s=submit_s,
    )


def _spec(
    *,
    mode: str = "informed",
    spinning: int = 2,
    offline: int = 0,
    events: list[WorkloadSignal] | None = None,
    lead_s: float = 600.0,
    cap_s: float = 1800.0,
    end_s: float = 3000.0,
    ramp: float = 0.5,
    min_down: bool = True,
    thermal_state: str = "cold",
) -> ScenarioSpec:
    turbine_units = []
    for index in range(spinning + offline):
        turbine_units.append({
            "asset_id": f"turbine-{index}",
            "rated_mw": 10.0,
            "r_asset_mw_per_s": ramp,
            "hot_standby": False,
            "initial_state": "spinning" if index < spinning else "offline",
            "thermal_state": thermal_state,
            "hot_start_s": 300.0,
            "warm_start_s": 360.0,
            "cold_start_s": 600.0,
            "min_run_enabled": False,
            "min_down_enabled": min_down,
            "t_min_down_s": 900.0,
        })
    return ScenarioSpec(
        name="impl-isl-30-stage1",
        frequency_nominal_hz=60.0,
        power_factor=0.85,
        island_mode=True,
        end_sim_time=end_s,
        initial_spinning_count=spinning,
        turbine_units=turbine_units,
        workload_events=[
            {
                "event_id": event.event_id,
                "job_id": event.job_id,
                "event_type": event.event_type.value,
                "timestamp": event.timestamp,
                "submit_time_s": event.submit_time_s,
                "node_count": event.node_count,
                "hardware_profile_id": event.hardware_profile_id,
                "workload_class": event.workload_class.value,
            }
            for event in (events or [])
        ],
        turbine_commitment_mode=mode,
        turbine_forecast_lead_seconds=lead_s,
        turbine_forecast_announcement_cap_seconds=cap_s,
    )


def _context(spec: ScenarioSpec, run_id: str = "isl30-test"):
    return build_run_context_from_spec(
        run_id,
        spec.model_dump(mode="json"),
        run_seed=42,
    )


def _forecast(
    ctx,
    events: list[WorkloadSignal],
    *,
    now_s: float,
    horizon_s: float = 2500.0,
):
    controller = ctx.turbine_commitment_controller
    forecast = controller.forecast(
        sim_time_s=now_s,
        events=events,
        measured_history=[],
        power_for_event=lambda _event: 30.0,
        horizon_seconds=horizon_s,
    )
    ctx.sim_state._commitment_forecast = forecast
    return forecast


def test_tc_isl_80_forecast_does_not_originate_stop() -> None:
    ctx = _context(_spec(events=[_event(500.0)]))
    controller = ctx.turbine_commitment_controller
    ctx.sim_time = 0.0
    controller.evaluate(ctx=ctx, power_for_event=lambda _event: 30.0)
    assert not any(record.action == "stop" for record in controller.log)
    assert not any(action == "stop" for _, action in controller._pending_request_keys)


def test_tc_isl_81_core_decommit_is_vetoed_for_announced_job_in_rts() -> None:
    event = _event(200.0, submit_s=0.0)
    ctx = _context(_spec(events=[event]))
    controller = ctx.turbine_commitment_controller
    forecast = _forecast(ctx, ctx.events, now_s=100.0)
    accepted = controller.adjudicate_core_proposal(
        state=ctx.sim_state,
        decision=SimpleNamespace(
            action="decommit",
            target_unit_id="turbine-0",
            reason="core unload",
            floor_violated=False,
        ),
        sim_time_s=100.0,
        synchronized_capacity_mw=20.0,
        bess_soc_fraction=0.5,
    )
    assert accepted is False
    record = controller.log[-1]
    assert "announced workload needs unit within RTS window" in (
        record.refusal_reason or ""
    )
    assert record.evidence["triggering_announced_jobs"][0]["job_id"] == event.job_id
    assert forecast.peak_over(2500.0) > 0.0


def test_tc_isl_82_core_decommit_not_vetoed_without_announced_job() -> None:
    ctx = _context(_spec(events=[]))
    controller = ctx.turbine_commitment_controller
    _forecast(ctx, [], now_s=100.0)
    accepted = controller.adjudicate_core_proposal(
        state=ctx.sim_state,
        decision=SimpleNamespace(
            action="decommit",
            target_unit_id="turbine-0",
            reason="core unload",
            floor_violated=False,
        ),
        sim_time_s=100.0,
        synchronized_capacity_mw=20.0,
        bess_soc_fraction=0.5,
    )
    assert accepted is True


def test_tc_isl_83_return_to_service_uses_each_units_config() -> None:
    spec = _spec(spinning=2, ramp=0.5)
    ctx = _context(spec)
    first, second = ctx.sim_state.turbines
    second.config.r_asset_mw_per_s = 0.25
    first_terms, first_missing = ctx.turbine_commitment_controller._return_to_service_terms(
        first, 100.0
    )
    second_terms, second_missing = ctx.turbine_commitment_controller._return_to_service_terms(
        second, 100.0
    )
    assert first_missing is second_missing is None
    assert first_terms["return_to_service_s"] != second_terms["return_to_service_s"]
    assert first_terms["ramp_rate_mw_per_s"] == 0.5
    assert second_terms["ramp_rate_mw_per_s"] == 0.25


def test_tc_isl_84_missing_rts_term_fails_closed() -> None:
    controller = ForecastDrivenTurbineController(mode="informed")
    turbine = SimpleNamespace(
        config=SimpleNamespace(
            rated_mw=10.0,
            r_asset_mw_per_s=0.5,
            p_min_stable_frac=0.35,
            min_down_enabled=False,
        ),
        output_mw=lambda: 3.5,
    )
    reason = controller._future_burst_refusal(
        state=SimpleNamespace(turbines=[turbine]),
        turbine=turbine,
        sim_time_s=0.0,
        forecast=None,
    )
    assert reason == (
        "forecast controller veto: return-to-service time unavailable "
        "(unload_tail_s)"
    )


def test_tc_isl_85_submit_announcement_uses_cap_and_legacy_lead() -> None:
    controller = ForecastDrivenTurbineController(
        mode="informed",
        forecast_lead_seconds=600.0,
        announcement_cap_seconds=1800.0,
    )
    explicit = _event(16_771.0, submit_s=16_171.0)
    late_submit = _event(16_771.0, job_id="late", submit_s=16_700.0)
    legacy = _event(16_771.0, job_id="legacy")
    assert controller._announcement_time_s(explicit) == 16_171.0
    assert controller._announcement_time_s(late_submit) == 16_700.0
    assert controller._announcement_time_s(legacy) == 16_171.0


def test_tc_isl_86_baseline_mode_does_not_consume_forecast() -> None:
    ctx = _context(_spec(mode="baseline", events=[_event(500.0)]))
    controller = ctx.turbine_commitment_controller
    assert controller.evaluate(ctx=ctx, power_for_event=lambda _event: 30.0) is None
    assert controller.forecast_history == []
    assert controller.log == []


def test_tc_isl_87_s10_16160_announcement_and_rts_veto() -> None:
    event = _event(16_771.0, job_id="s10-job-00009", submit_s=16_171.0)
    ctx = _context(_spec(events=[event], end_s=20_000.0))
    controller = ctx.turbine_commitment_controller
    assert controller._announced_start_times(
        sim_time_s=16_160.0,
        events=ctx.events,
    ).get(event.job_id) is None
    forecast = _forecast(ctx, ctx.events, now_s=16_171.0, horizon_s=2500.0)
    assert controller._announced_start_times(
        sim_time_s=16_171.0,
        events=ctx.events,
    )[event.job_id] == 16_771.0
    accepted = controller.adjudicate_core_proposal(
        state=ctx.sim_state,
        decision=SimpleNamespace(
            action="decommit",
            target_unit_id="turbine-0",
            reason="core unload",
            floor_violated=False,
        ),
        sim_time_s=16_171.0,
        synchronized_capacity_mw=20.0,
        bess_soc_fraction=0.5,
    )
    assert accepted is False
    assert forecast.peak_over(2500.0) > 0.0


@pytest.mark.parametrize(
    ("thermal", "expected_start_s"),
    [("hot", 300.0), ("warm", 360.0), ("cold", 600.0)],
)
def test_tc_isl_88_start_horizon_uses_current_thermal_tier(
    thermal: str,
    expected_start_s: float,
) -> None:
    ctx = _context(_spec(spinning=0, offline=1, thermal_state=thermal))
    turbine = ctx.sim_state.turbines[0]
    horizon = ctx.turbine_commitment_controller._start_horizon_seconds(turbine, 0.0)
    assert horizon == pytest.approx(expected_start_s + 10.0 / 0.5)


def test_tc_isl_89_cold_unit_can_be_started_for_thermal_horizon() -> None:
    event = _event(600.0, submit_s=0.0)
    ctx = _context(_spec(spinning=1, offline=1, events=[event]))
    controller = ctx.turbine_commitment_controller
    queued: list[tuple[str, str, str]] = []
    controller._queue = lambda _ctx, unit, action, reason, *_args: queued.append(
        (unit.config.asset_id, action, reason)
    )
    ctx.sim_time = 0.0
    controller.evaluate(ctx=ctx, power_for_event=lambda _event: 30.0)
    assert queued
    assert queued[0][0:2] == ("turbine-1", "start")
    assert "620s" in queued[0][2]


def test_tc_isl_91_submit_time_round_trips_to_workload_signal() -> None:
    event_spec = WorkloadEventSpec(
        event_id="e-91",
        job_id="job-91",
        event_type="starting",
        timestamp=100.0,
        submit_time_s=25.0,
        node_count=2,
        hardware_profile_id="enterprise_8gpu_air",
        workload_class="training",
    )
    event = _event(100.0, job_id="job-91", submit_s=25.0)
    spec = _spec(events=[event])
    ctx = _context(spec, run_id="tc-isl-91")
    assert ctx.events[0].submit_time_s == 25.0
    assert event_spec.model_dump(mode="json")["submit_time_s"] == 25.0
    legacy = WorkloadEventSpec(
        event_id="e-91-legacy",
        job_id="job-91-legacy",
        event_type="starting",
        timestamp=100.0,
        node_count=2,
        hardware_profile_id="enterprise_8gpu_air",
        workload_class="training",
    )
    assert "submit_time_s" not in legacy.model_dump(mode="json")
    assert ctx.turbine_commitment_controller.announcement_cap_seconds == 1800.0
    changed_cap = _spec(events=[], cap_s=1200.0).model_dump(mode="json")
    assert changed_cap["turbine_forecast_announcement_cap_seconds"] == 1200.0
