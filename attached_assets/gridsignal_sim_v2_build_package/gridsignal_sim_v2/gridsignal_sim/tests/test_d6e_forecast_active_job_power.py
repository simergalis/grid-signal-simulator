"""D6e Option A regression tests for active-job forecast power."""

from types import SimpleNamespace

import pytest

from runtime.turbine_commitment import ForecastDrivenTurbineController


def _event(
    event_type: str,
    timestamp: float,
    event_id: str,
    job_id: str = "job-1",
) -> SimpleNamespace:
    return SimpleNamespace(
        event_type=event_type,
        timestamp=timestamp,
        event_id=event_id,
        job_id=job_id,
    )


def test_tc_isl_74_active_announced_job_uses_callback_in_current_and_profile() -> None:
    """DR D6d/D6e: active announced load must not be cached at zero MW."""
    controller = ForecastDrivenTurbineController(mode="informed")
    callback_calls: list[str] = []

    def power_for_event(event: SimpleNamespace) -> float:
        callback_calls.append(event.event_id)
        return 12.5

    forecast = controller.forecast(
        sim_time_s=10.0,
        events=[_event("running", 5.0, "run-1")],
        measured_history=[],
        power_for_event=power_for_event,
        horizon_seconds=10.0,
        step_seconds=5.0,
    )

    assert forecast.forecast_mw == pytest.approx(12.5)
    assert forecast.profile[0] == pytest.approx((10.0, 12.5))
    assert forecast.announced_workload_mw == pytest.approx(12.5)
    assert callback_calls


def test_tc_isl_75_starting_and_scale_records_count_one_job_once() -> None:
    """STARTING/SCALE records update one job entry rather than summing."""
    controller = ForecastDrivenTurbineController(mode="informed")
    events = [
        _event("starting", 5.0, "start-1"),
        _event("scale", 7.0, "scale-1"),
    ]

    forecast = controller.forecast(
        sim_time_s=8.0,
        events=events,
        measured_history=[],
        power_for_event=lambda event: 4.0 if event.event_id == "start-1" else 9.0,
        horizon_seconds=5.0,
        step_seconds=5.0,
    )

    assert forecast.profile[0] == pytest.approx((8.0, 9.0))
    assert forecast.announced_workload_mw == pytest.approx(9.0)
    assert len(controller._job_state_at(
        timestamp=8.0,
        events=events,
        power_for_event=lambda _event: 0.0,
    )) == 1


def test_tc_isl_76_job_end_removes_power_from_later_profile_samples() -> None:
    """A JOB_END event clears the current job from subsequent forecast points."""
    controller = ForecastDrivenTurbineController(mode="informed")
    events = [
        _event("running", 0.0, "run-1"),
        _event("job_end", 10.0, "end-1"),
    ]

    forecast = controller.forecast(
        sim_time_s=5.0,
        events=events,
        measured_history=[],
        power_for_event=lambda _event: 6.0,
        horizon_seconds=10.0,
        step_seconds=5.0,
    )

    assert forecast.profile[0] == pytest.approx((5.0, 6.0))
    assert forecast.profile[-1] == pytest.approx((15.0, 0.0))
    assert forecast.announced_workload_mw == pytest.approx(6.0)


def test_tc_isl_77_measured_history_residual_is_unchanged_and_counted_once() -> None:
    """Known event power/cooling is removed from history, then added once."""
    controller = ForecastDrivenTurbineController(mode="informed")
    events = [_event("running", 0.0, "run-1")]
    history = [
        (5.0, 14.0, 0.0, 2.0),
        (10.0, 14.0, 0.0, 2.0),
    ]
    callback = lambda _event: 4.0

    residual = controller._background_samples(
        sim_time_s=15.0,
        events=events,
        measured_history=history,
        power_for_event=callback,
        cooling_fraction=0.5,
    )
    forecast = controller.forecast(
        sim_time_s=15.0,
        events=events,
        measured_history=history,
        power_for_event=callback,
        cooling_fraction=0.5,
        horizon_seconds=5.0,
        step_seconds=5.0,
    )

    assert residual == pytest.approx([8.0, 8.0])
    assert forecast.background_mean_mw == pytest.approx(8.0)
    assert forecast.forecast_mw == pytest.approx(14.0)


def test_tc_isl_78_baseline_mode_does_not_build_or_consume_forecast() -> None:
    """Conventional mode remains on the core path and never calls the callback."""
    controller = ForecastDrivenTurbineController(mode="baseline")
    calls = 0

    def power_for_event(_event: SimpleNamespace) -> float:
        nonlocal calls
        calls += 1
        return 6.0

    state = SimpleNamespace()
    context = SimpleNamespace(
        sim_state=state,
        sim_time=10.0,
        events=[_event("running", 5.0, "run-1")],
        _measured_site_demand_history=[(5.0, 6.0)],
    )

    assert controller.evaluate(ctx=context, power_for_event=power_for_event) is None
    assert calls == 0
    assert controller.forecast_history == []
    assert controller._forecast_event_key is None


def test_tc_isl_79_announced_scan_without_callback_does_not_seed_zero_state() -> None:
    """No-callback callers index events but do not seed the cache with zero MW."""
    controller = ForecastDrivenTurbineController(mode="informed")
    events = [_event("running", 5.0, "run-1")]
    callback = lambda _event: 7.0

    starts = controller._announced_start_times(
        sim_time_s=10.0,
        events=events,
    )

    assert starts == {"job-1": 5.0}
    assert controller._timeline_cache == {}
    assert controller._timeline_max_timestamp == float("-inf")
    assert controller._job_state_at(
        timestamp=10.0,
        events=events,
        power_for_event=callback,
    )["job-1"][0] == pytest.approx(7.0)
