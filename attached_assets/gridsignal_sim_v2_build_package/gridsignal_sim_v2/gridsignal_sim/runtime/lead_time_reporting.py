"""Read-only empirical reporting for persisted GPU lead-time observations.

This module deliberately has no callers in dispatch, staging, forecasting, or
any other simulator decision path.  It can summarize directly supplied
observation records for validation and can query the measurement-only
``gpu_lead_time_observation`` table for an independent report.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean, pstdev
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import WorkloadClass
from runtime.persistence import LeadTimeObservation


# PROPOSED_HERE / UNVALIDATED: placeholder sample-size gate for empirical
# calibration reporting.  This does not authorize using the statistics in any
# simulator decision path.
MIN_TRUSTED_SAMPLE_SIZE = 30

# PROPOSED_HERE / UNVALIDATED: one population standard deviation below the
# observed mean is a conservative reporting choice, not a validated forecast
# confidence bound.  Lower lead-time estimates intentionally bias toward
# earlier staging rather than risking assets being ready too late.
CONSERVATIVE_STDDEV_MULTIPLIER = 1.0


@dataclass(frozen=True)
class LeadTimeDistributionReport:
    """Empirical lead-time statistics for one profile/workload combination."""

    hardware_profile_id: str
    workload_class: str
    observation_count: int
    mean_lead_time_seconds: float | None
    stddev_lead_time_seconds: float | None
    min_lead_time_seconds: float | None
    max_lead_time_seconds: float | None
    conservative_lead_time_seconds: float | None
    module_default_ramp_seconds: float
    minimum_trusted_sample_size: int
    statistics_trustworthy: bool
    confidence_status: str
    conservative_estimate_method: str


def _workload_class_value(workload_class: str | WorkloadClass) -> str:
    if isinstance(workload_class, WorkloadClass):
        return workload_class.value
    return str(workload_class)


def current_module_ramp_seconds() -> float:
    """Return the current GPUModule dataclass default without creating a GPU.

    The reporting layer reads this value from the existing simulator definition
    instead of duplicating the default, while never changing or invoking GPU
    decision logic.
    """
    from core.asset_modules import GPUModule

    default = GPUModule.__dataclass_fields__["ramp_seconds"].default
    if default is None:
        raise RuntimeError("GPUModule.ramp_seconds must define a module default")
    return float(default)


def summarize_lead_time_observations(
    observations: Iterable[LeadTimeObservation],
    *,
    hardware_profile_id: str,
    workload_class: str | WorkloadClass,
    module_default_ramp_seconds: float | None = None,
    minimum_trusted_sample_size: int = MIN_TRUSTED_SAMPLE_SIZE,
) -> LeadTimeDistributionReport:
    """Summarize supplied measurement rows without touching simulator state."""
    if minimum_trusted_sample_size < 1:
        raise ValueError("minimum_trusted_sample_size must be positive")

    workload_value = _workload_class_value(workload_class)
    module_default = (
        current_module_ramp_seconds()
        if module_default_ramp_seconds is None
        else float(module_default_ramp_seconds)
    )
    values = tuple(float(observation.lead_time_seconds) for observation in observations)
    count = len(values)
    is_trustworthy = count >= minimum_trusted_sample_size

    if values:
        mean = fmean(values)
        stddev = pstdev(values)
        minimum = min(values)
        maximum = max(values)
        conservative = max(
            0.0,
            mean - CONSERVATIVE_STDDEV_MULTIPLIER * stddev,
        )
    else:
        mean = None
        stddev = None
        minimum = None
        maximum = None
        conservative = None

    return LeadTimeDistributionReport(
        hardware_profile_id=hardware_profile_id,
        workload_class=workload_value,
        observation_count=count,
        mean_lead_time_seconds=mean,
        stddev_lead_time_seconds=stddev,
        min_lead_time_seconds=minimum,
        max_lead_time_seconds=maximum,
        conservative_lead_time_seconds=conservative,
        module_default_ramp_seconds=module_default,
        minimum_trusted_sample_size=minimum_trusted_sample_size,
        statistics_trustworthy=is_trustworthy,
        confidence_status=(
            "high-confidence" if is_trustworthy else "insufficient-sample"
        ),
        conservative_estimate_method=(
            "mean minus "
            f"{CONSERVATIVE_STDDEV_MULTIPLIER:g} population standard deviation"
        ),
    )


async def report_lead_time_distribution(
    session: AsyncSession,
    *,
    hardware_profile_id: str,
    workload_class: str | WorkloadClass,
    module_default_ramp_seconds: float | None = None,
    minimum_trusted_sample_size: int = MIN_TRUSTED_SAMPLE_SIZE,
) -> LeadTimeDistributionReport:
    """Query and report one persisted profile/workload distribution.

    The query is read-only: it selects measurement rows and performs no insert,
    update, delete, commit, or simulator-state operation.
    """
    workload_value = _workload_class_value(workload_class)
    result = await session.execute(
        select(LeadTimeObservation)
        .where(
            LeadTimeObservation.hardware_profile_id == hardware_profile_id,
            LeadTimeObservation.workload_type == workload_value,
        )
        .order_by(LeadTimeObservation.id)
    )
    return summarize_lead_time_observations(
        result.scalars().all(),
        hardware_profile_id=hardware_profile_id,
        workload_class=workload_value,
        module_default_ramp_seconds=module_default_ramp_seconds,
        minimum_trusted_sample_size=minimum_trusted_sample_size,
    )