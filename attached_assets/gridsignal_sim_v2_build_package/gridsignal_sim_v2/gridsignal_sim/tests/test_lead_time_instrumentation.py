"""Phase 1 lead-time instrumentation tests.

These tests cover measurement only.  They do not assert or alter dispatch,
staging, or forecast decisions.
"""
from __future__ import annotations

from core.lead_time_observations import (
    HIGH_DRAW_THRESHOLD_FRACTION,
    LeadTimeObservationRecorder,
)
from core.models import WorkloadClass, WorkloadEventType, WorkloadSignal


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

    assert recorder.observe_high_draw("job-1", 20.0, 9.4, 10.0) is None
    observation = recorder.observe_high_draw("job-1", 25.0, 9.5, 10.0)
    assert observation is not None
    assert observation.start_sim_time_seconds == 10.0
    assert observation.high_draw_sim_time_seconds == 25.0
    assert observation.lead_time_seconds == 15.0
    assert observation.hardware_profile_id == "enterprise_8gpu_air"
    assert observation.workload_type == "training"
    assert observation.threshold_fraction == HIGH_DRAW_THRESHOLD_FRACTION

    assert recorder.observe_high_draw("job-1", 30.0, 10.0, 10.0) is None
    assert recorder.drain_completed() == (observation,)


def test_threshold_is_explicitly_exposed_as_unvalidated_measurement_setting():
    assert HIGH_DRAW_THRESHOLD_FRACTION == 0.95