"""Phase 1 lead-time instrumentation tests.

These tests cover measurement only.  They do not assert or alter dispatch,
staging, or forecast decisions.
"""
from __future__ import annotations

import contextlib
import json
from pathlib import Path

import pytest

from core._plane_guard import _EVALUATE_TICK_PERMITTED
from core.lead_time_observations import (
    HIGH_DRAW_THRESHOLD_FRACTION,
    LeadTimeObservationRecorder,
)
from core.models import WorkloadClass, WorkloadEventType, WorkloadSignal
from core.sim_clock import SimClock
from core.simulation_core import evaluate_tick
from runtime.scenario_factory import build_run_context_from_spec


def _starting_signal() -> WorkloadSignal:
    return WorkloadSignal(
        event_id="start-1",
        job_id="job-1",
        event_type=WorkloadEventType.STARTING,
        timestamp=10.0,
        hardware_profile_id="enterprise_8gpu_air",
        node_count=10,
        workload_class=WorkloadClass.TRAINING,
        site_id="site-1",
    )


def test_records_first_high_draw_observation_only():
    recorder = LeadTimeObservationRecorder()
    recorder.record_start("run-1", _starting_signal())

    assert recorder.observe_high_draw(
        "job-1",
        20.0,
        9.4,
        10.0,
        previous_draw_mw=9.0,
        previous_sim_time_seconds=15.0,
    ) is None
    observation = recorder.observe_high_draw(
        "job-1",
        25.0,
        9.5,
        10.0,
        previous_draw_mw=9.4,
        previous_sim_time_seconds=20.0,
    )
    assert observation is not None
    assert observation.start_sim_time_seconds == 10.0
    assert observation.high_draw_sim_time_seconds == 25.0
    assert observation.lead_time_seconds == 15.0
    assert observation.hardware_profile_id == "enterprise_8gpu_air"
    assert observation.workload_type == "training"
    assert observation.threshold_fraction == HIGH_DRAW_THRESHOLD_FRACTION

    assert recorder.observe_high_draw(
        "job-1",
        30.0,
        10.0,
        10.0,
        previous_draw_mw=9.5,
        previous_sim_time_seconds=25.0,
    ) is None
    assert recorder.drain_completed() == (observation,)


def test_interpolates_high_draw_crossing_within_tick():
    recorder = LeadTimeObservationRecorder()
    recorder.record_start("run-1", _starting_signal())

    observation = recorder.observe_high_draw(
        "job-1",
        sim_time_seconds=15.0,
        current_draw_mw=10.0,
        target_draw_mw=10.0,
        previous_draw_mw=9.0,
        previous_sim_time_seconds=10.0,
    )

    assert observation is not None
    assert observation.high_draw_sim_time_seconds == 12.5
    assert observation.lead_time_seconds == 2.5


def test_threshold_is_explicitly_exposed_as_unvalidated_measurement_setting():
    assert HIGH_DRAW_THRESHOLD_FRACTION == 0.95


_SCENARIO_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "scenarios"
    / "addendum-h-lead-time-profile-validation.json"
)


@contextlib.contextmanager
def _plane_guard_active():
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        yield
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


def _run_addendum_h_validation_scenario():
    spec = json.loads(_SCENARIO_PATH.read_text())
    ctx = build_run_context_from_spec(
        "tc-h-lead-time-profile-validation",
        spec,
        playback_speed=0.0,
    )
    for signal in ctx.events:
        ctx.sim_state.apply_workload_signal(signal, ctx.dt_lead_seconds)

    observations = []
    sim_time = 0.0
    for tick_seq in range(1000):
        with _plane_guard_active():
            evaluate_tick(
                ctx.sim_state,
                SimClock(
                    sim_time=sim_time,
                    dt_seconds=0.1,
                    wall_stamp_utc=0.0,
                    rate=1.0,
                    tick_seq=tick_seq,
                ),
            )
        observations.extend(ctx.sim_state.lead_time_observations.drain_completed())
        if len(observations) == 2:
            break
        sim_time += 0.1
    assert len(observations) == 2
    return {
        observation.hardware_profile_id: observation
        for observation in observations
    }


def test_TC_H1_20_second_profile_matches_known_95_percent_crossing():
    observations = _run_addendum_h_validation_scenario()
    observation = observations["addendum_h_test_ramp_20s"]

    # The existing PROTO-1 curve reaches 95% of target at 70% progress.
    # With a 20 s full-ramp setting, the known 95%-crossing answer is 14 s.
    assert observation.lead_time_seconds == pytest.approx(14.0, abs=1e-9)
    assert observation.threshold_fraction == HIGH_DRAW_THRESHOLD_FRACTION


def test_TC_H2_60_second_profile_matches_known_95_percent_crossing():
    observations = _run_addendum_h_validation_scenario()
    observation = observations["addendum_h_test_ramp_60s"]

    # Same unchanged PROTO-1 curve: 0.70 × 60 s = 42 s to 95% of target.
    assert observation.lead_time_seconds == pytest.approx(42.0, abs=1e-9)
    assert observation.threshold_fraction == HIGH_DRAW_THRESHOLD_FRACTION


def test_TC_H3_profile_lead_time_ranges_are_non_overlapping():
    observations = _run_addendum_h_validation_scenario()
    short_lead = observations["addendum_h_test_ramp_20s"].lead_time_seconds
    long_lead = observations["addendum_h_test_ramp_60s"].lead_time_seconds

    assert short_lead < long_lead


def test_profile_ramp_override_flows_to_dt_lead_next_s():
    spec = json.loads(_SCENARIO_PATH.read_text())
    ctx = build_run_context_from_spec(
        "tc-h-dt-lead-profile-override",
        spec,
        playback_speed=0.0,
    )
    signal = ctx.events[0]
    ctx.sim_state.apply_workload_signal(signal, ctx.dt_lead_seconds)

    gpu = ctx.sim_state.gpu_modules[0]
    gpu._ramp_progress[signal.job_id] = 0.5

    with _plane_guard_active():
        tick = evaluate_tick(
            ctx.sim_state,
            SimClock(
                sim_time=0.0,
                dt_seconds=0.1,
                wall_stamp_utc=0.0,
                rate=1.0,
                tick_seq=0,
            ),
        )

    # evaluate_tick advances the 20 s profile by 0.1 s before calculating
    # the remaining countdown: (1 - (0.5 + 0.1 / 20)) * 20 = 9.9 s.
    assert tick.dt_lead_next_s == pytest.approx(9.9, abs=1e-9)