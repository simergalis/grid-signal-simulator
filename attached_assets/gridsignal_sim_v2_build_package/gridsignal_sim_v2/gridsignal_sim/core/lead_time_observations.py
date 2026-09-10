"""Instrumentation for measuring observed workload ramp lead time.

This module is intentionally one-way telemetry.  Nothing here is consulted by
dispatch, staging, forecasting, or any other control decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .models import WorkloadSignal


# PROPOSED_HERE / UNVALIDATED: initial instrumentation threshold only.
# This is a measurement trigger, not a settled definition of "full TDP".
# Validate against real power/utilization telemetry before changing any
# downstream behavior or using this value for prediction.
HIGH_DRAW_THRESHOLD_FRACTION = 0.95


@dataclass(frozen=True)
class LeadTimeObservation:
    """One completed, additive lead-time measurement."""

    run_id: str
    site_id: str
    job_id: str
    hardware_profile_id: str
    workload_type: str
    start_sim_time_seconds: float
    high_draw_sim_time_seconds: float
    lead_time_seconds: float
    threshold_fraction: float = HIGH_DRAW_THRESHOLD_FRACTION


@dataclass
class _PendingObservation:
    run_id: str
    site_id: str
    job_id: str
    hardware_profile_id: str
    workload_type: str
    start_sim_time_seconds: float


@dataclass
class LeadTimeObservationRecorder:
    """Collect start/high-draw pairs without affecting simulator decisions."""

    threshold_fraction: float = HIGH_DRAW_THRESHOLD_FRACTION
    _pending: dict[str, _PendingObservation] = field(default_factory=dict)
    _completed: list[LeadTimeObservation] = field(default_factory=list)

    def record_start(self, run_id: str, signal: WorkloadSignal) -> None:
        """Record the first STARTING timestamp for a job."""
        if signal.job_id in self._pending:
            return
        self._pending[signal.job_id] = _PendingObservation(
            run_id=run_id,
            site_id=signal.site_id,
            job_id=signal.job_id,
            hardware_profile_id=signal.hardware_profile_id,
            workload_type=signal.workload_class.value,
            start_sim_time_seconds=signal.timestamp,
        )

    def observe_high_draw(
        self,
        job_id: str,
        sim_time_seconds: float,
        current_draw_mw: float,
        target_draw_mw: float,
    ) -> Optional[LeadTimeObservation]:
        """Complete an observation on the first high-draw sample."""
        pending = self._pending.get(job_id)
        if pending is None or target_draw_mw <= 0.0:
            return None
        if current_draw_mw < target_draw_mw * self.threshold_fraction:
            return None

        observation = LeadTimeObservation(
            run_id=pending.run_id,
            site_id=pending.site_id,
            job_id=pending.job_id,
            hardware_profile_id=pending.hardware_profile_id,
            workload_type=pending.workload_type,
            start_sim_time_seconds=pending.start_sim_time_seconds,
            high_draw_sim_time_seconds=sim_time_seconds,
            lead_time_seconds=sim_time_seconds - pending.start_sim_time_seconds,
            threshold_fraction=self.threshold_fraction,
        )
        self._pending.pop(job_id, None)
        self._completed.append(observation)
        return observation

    def pending_job_ids(self) -> tuple[str, ...]:
        return tuple(self._pending)

    def drain_completed(self) -> tuple[LeadTimeObservation, ...]:
        completed = tuple(self._completed)
        self._completed.clear()
        return completed