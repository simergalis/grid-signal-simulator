"""Translate slurmrestd job snapshots into scheduler-agnostic workload signals."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from core.models import WorkloadClass, WorkloadEventType, WorkloadSignal


@dataclass(frozen=True)
class SlurmTranslationError(ValueError):
    """A caller-correctable mismatch between Slurm data and GridSignal's contract."""

    code: str
    message: str
    field: str
    value: object


_STATE_TO_EVENT: dict[str, WorkloadEventType] = {
    "PENDING": WorkloadEventType.QUEUED,
    "RUNNING": WorkloadEventType.RUNNING,
    "COMPLETING": WorkloadEventType.JOB_END,
    "COMPLETED": WorkloadEventType.JOB_END,
    "CANCELLED": WorkloadEventType.CANCELLED,
    "FAILED": WorkloadEventType.CANCELLED,
    "TIMEOUT": WorkloadEventType.CANCELLED,
    "NODE_FAIL": WorkloadEventType.CANCELLED,
    "PREEMPTED": WorkloadEventType.CANCELLED,
}

_GRES_GPU_RE = re.compile(
    r"(?:^|,)\s*gres/gpu:(?P<model>[A-Za-z0-9_-]+)=(?P<count>\d+)\s*(?:,|$)",
    re.IGNORECASE,
)
_TRES_PROFILE_BY_MODEL = {
    "h100": ("h100-sxm5-8way-nvl4", 8),
}


def _profile_and_gpu_count_from_tres(tres_alloc_str: str) -> tuple[str, int]:
    """Resolve the canonical profile plus allocated accelerator count."""
    match = _GRES_GPU_RE.search(tres_alloc_str)
    if match is None:
        raise SlurmTranslationError(
            "unmapped_hardware",
            "tres_alloc_str must contain a supported gres/gpu:<model>=<count> entry.",
            "tres_alloc_str",
            tres_alloc_str,
        )
    model = match.group("model").lower()
    if int(match.group("count")) <= 0:
        raise SlurmTranslationError(
            "invalid_gpu_allocation",
            "The Slurm GPU allocation count must be greater than zero.",
            "tres_alloc_str",
            tres_alloc_str,
        )
    mapping = _TRES_PROFILE_BY_MODEL.get(model)
    if mapping is None:
        raise SlurmTranslationError(
            "unmapped_hardware",
            f"No GridSignal hardware profile is mapped for Slurm GPU model {model!r}.",
            "tres_alloc_str",
            tres_alloc_str,
        )
    return mapping[0], int(match.group("count"))


def hardware_profile_from_tres(tres_alloc_str: str) -> str:
    """Resolve the canonical GridSignal profile from Slurm TRES allocation."""
    return _profile_and_gpu_count_from_tres(tres_alloc_str)[0]


def event_type_from_job_state(job_state: list[str]) -> WorkloadEventType:
    """Map the primary slurmrestd state to the WorkloadSignal event enum."""
    state = job_state[0].strip().upper() if job_state else ""
    event_type = _STATE_TO_EVENT.get(state)
    if event_type is None:
        raise SlurmTranslationError(
            "unmapped_job_state",
            f"Slurm job state {state or '<empty>'!r} is not supported.",
            "job_state",
            job_state,
        )
    return event_type


def translate_slurm_job(
    *,
    job_id: int,
    job_state: list[str],
    node_count: int,
    tres_req_str: Optional[str],
    tres_alloc_str: Optional[str],
    site_id: str,
    timestamp: float,
    account: Optional[str] = None,
    partition: Optional[str] = None,
) -> WorkloadSignal:
    """Build a live WorkloadSignal from one raw slurmrestd job object.

    Slurm publishes the requested TRES while a job is PENDING and its allocated
    TRES once it is RUNNING.  The state-aware choice keeps queue telemetry
    usable without pretending an allocation already exists.
    """
    event_type = event_type_from_job_state(job_state)
    if event_type == WorkloadEventType.QUEUED:
        tres_source = tres_req_str
        missing_code = "missing_resource_request"
        missing_message = (
            "PENDING Slurm jobs require tres_req_str so GridSignal can identify "
            "their requested GPU profile."
        )
    elif event_type == WorkloadEventType.RUNNING:
        tres_source = tres_alloc_str
        missing_code = "missing_resource_allocation"
        missing_message = (
            "RUNNING Slurm jobs require tres_alloc_str so GridSignal can model "
            "the actual allocated GPU profile."
        )
    else:
        # Terminal snapshots may no longer retain allocation metadata.  Either
        # TRES form is adequate because JOB_END/CANCELLED removes load rather
        # than creating a new physical allocation.
        tres_source = None
        missing_code = "missing_resource_metadata"
        missing_message = (
            "Terminal Slurm job snapshots require tres_alloc_str or tres_req_str "
            "to preserve their hardware-profile identity."
        )
    if event_type in {WorkloadEventType.QUEUED, WorkloadEventType.RUNNING} and not tres_source:
        raise SlurmTranslationError(
            missing_code, missing_message,
            "tres_req_str" if event_type == WorkloadEventType.QUEUED else "tres_alloc_str",
            tres_source,
        )
    if event_type in {WorkloadEventType.QUEUED, WorkloadEventType.RUNNING}:
        hardware_profile_id, gpu_count = _profile_and_gpu_count_from_tres(tres_source)
    else:
        # A deallocated terminal snapshot can contain a truthy but generic
        # `tres_alloc_str` (for example "cpu=0,node=0").  Prefer allocation
        # data when it remains valid, then fall back to the still-authoritative
        # resource request so JOB_END is never blocked by deallocation cleanup.
        last_parse_error: Optional[SlurmTranslationError] = None
        hardware_profile_id = ""
        gpu_count = 0
        for candidate in (tres_alloc_str, tres_req_str):
            if not candidate:
                continue
            try:
                hardware_profile_id, gpu_count = _profile_and_gpu_count_from_tres(candidate)
                break
            except SlurmTranslationError as exc:
                last_parse_error = exc
        if not hardware_profile_id:
            if last_parse_error is not None:
                raise last_parse_error
            raise SlurmTranslationError(
                missing_code,
                missing_message,
                "tres_alloc_str",
                None,
            )
    gpus_per_node = _TRES_PROFILE_BY_MODEL["h100"][1]
    signal_node_count = node_count
    if event_type in {WorkloadEventType.QUEUED, WorkloadEventType.RUNNING}:
        if gpu_count % gpus_per_node != 0:
            raise SlurmTranslationError(
                "incompatible_allocation",
                "The H100 profile represents 8 GPUs per node; the "
                "gres/gpu:h100 allocation must be divisible by 8.",
                "tres_req_str" if event_type == WorkloadEventType.QUEUED else "tres_alloc_str",
                gpu_count,
            )
        expected_node_count = gpu_count // gpus_per_node
        # Before placement Slurm commonly reports zero allocated nodes.  Queue
        # events carry requested topology, so derive their chassis count from
        # requested H100 TRES rather than rejecting the valid snapshot.
        if event_type == WorkloadEventType.QUEUED and node_count == 0:
            signal_node_count = expected_node_count
        elif node_count != expected_node_count:
            raise SlurmTranslationError(
                "incompatible_allocation",
                "The H100 profile represents 8 GPUs per node; node_count must "
                "match the gres/gpu:h100 allocation exactly.",
                "node_count",
                node_count,
            )
    return WorkloadSignal(
        # A poller can submit the same snapshot many times.  State-specific
        # IDs make those retries idempotent while allowing the same Slurm job
        # to move through PENDING → RUNNING → COMPLETING.
        event_id=f"slurm-{job_id}-{event_type.value}",
        job_id=f"slurm-{job_id}",
        event_type=event_type,
        timestamp=timestamp,
        hardware_profile_id=hardware_profile_id,
        node_count=signal_node_count,
        workload_class=WorkloadClass.TRAINING,
        site_id=site_id,
        scheduler_domain=partition or "slurm",
        tenant_id=account or None,
        scheduler_type="slurm",
        capacity_unit="chassis",
        gpus_per_unit=gpus_per_node,
    )