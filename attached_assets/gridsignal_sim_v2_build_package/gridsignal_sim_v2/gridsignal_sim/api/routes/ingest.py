"""Inbound scheduler adapters.

The Slurm endpoint accepts one raw slurmrestd job snapshot, translates it into
the simulator's WorkloadSignal contract, and queues it against an active run.
It intentionally does not create a run: the operator must start the scenario
whose physical plant should respond to the customer's workload.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from api.schemas import SlurmJobConfigSpec, SlurmJobPayload, WorkloadSignalResponse
from api.routes.admin_routes import _require_admin
from core.models import WorkloadClass
from core.slurm_scheduler import SlurmJobSpec, SlurmSchedulerError
from runtime.run_manager import RunManager
from runtime.slurm_ingest import (
    SlurmTranslationError,
    hardware_profile_from_tres,
    translate_slurm_job,
)


router = APIRouter(prefix="/api/ingest", tags=["ingest"])

def _unprocessable(code: str, message: str, **extra: object) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": code, "message": message, **extra},
    )


def _manager(request: Request) -> RunManager:
    return request.app.state.run_manager


def _select_run(manager: RunManager, run_id: Optional[str]) -> tuple[str, object]:
    if run_id:
        ctx = manager.get_context(run_id)
        if ctx is None or ctx.is_complete():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "run_not_active",
                    "message": f"Run {run_id!r} was not found or is no longer active.",
                    "run_id": run_id,
                },
            )
        return run_id, ctx

    active_ids = manager.active_run_ids()
    if len(active_ids) == 1:
        selected = active_ids[0]
        ctx = manager.get_context(selected)
        if ctx is not None:
            return selected, ctx
    if not active_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "no_active_run",
                "message": "Start a simulation run before ingesting Slurm workload events.",
            },
        )
    raise _unprocessable(
        "ambiguous_run",
        "Multiple runs are active; provide the run_id query parameter.",
        active_run_ids=active_ids,
    )


@router.post(
    "/slurm",
    response_model=WorkloadSignalResponse,
    summary="Ingest one slurmrestd job snapshot",
)
async def ingest_slurm(
    payload: SlurmJobPayload,
    request: Request,
    run_id: Optional[str] = Query(
        default=None,
        description="Target active run. Omit only when exactly one run is active.",
    ),
    _: None = Depends(_require_admin),
) -> WorkloadSignalResponse:
    """Translate and enqueue a raw Slurm job snapshot.

    External scheduler timestamps are wall-clock Unix seconds, while the
    simulator uses seconds since run start.  The ingestion boundary therefore
    timestamps accepted events at the target run's current simulated time.
    """
    manager = _manager(request)
    selected_run_id, ctx = _select_run(manager, run_id)
    try:
        signal = translate_slurm_job(
            job_id=payload.job_id,
            job_state=payload.job_state,
            node_count=payload.node_count,
            tres_req_str=payload.tres_req_str,
            tres_alloc_str=payload.tres_alloc_str,
            site_id=ctx.sim_state.site.site_id,
            timestamp=ctx.sim_time,
            account=payload.account,
            partition=payload.partition,
        )
    except SlurmTranslationError as exc:
        raise _unprocessable(
            exc.code, exc.message, field=exc.field, value=exc.value
        ) from exc
    result_code, detail = manager.ingest_workload_signal(selected_run_id, signal)
    if result_code not in {"accepted", "duplicate"}:
        if result_code == "site_mismatch":
            raise _unprocessable("site_mismatch", detail)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": result_code, "message": detail},
        )
    return WorkloadSignalResponse(
        event_id=signal.event_id,
        job_id=signal.job_id,
        event_type=signal.event_type.value,
        timestamp=signal.timestamp,
        hardware_profile_id=signal.hardware_profile_id,
        node_count=signal.node_count,
        workload_class=signal.workload_class.value,
        site_id=signal.site_id,
        scheduler_domain=signal.scheduler_domain,
        tenant_id=signal.tenant_id,
        scheduler_type=signal.scheduler_type,
        capacity_unit=signal.capacity_unit,
        gpus_per_unit=signal.gpus_per_unit,
    )


@router.post(
    "/slurm/submit",
    response_model=WorkloadSignalResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit one job to the internal Slurm scheduler",
)
async def submit_internal_slurm(
    payload: SlurmJobConfigSpec,
    request: Request,
    run_id: Optional[str] = Query(
        default=None,
        description="Target active run. Omit only when exactly one run is active.",
    ),
    _: None = Depends(_require_admin),
) -> WorkloadSignalResponse:
    """Submit a simulated application to an opt-in internal Slurm queue.

    The command and environment are retained as submission metadata by the
    wire schema but are never executed on the host.  The scheduler allocates
    simulated nodes/GPUs and the normal physics loop models the resulting
    workload until the requested duration elapses.
    """
    manager = _manager(request)
    selected_run_id, ctx = _select_run(manager, run_id)
    available_profiles = {
        profile_id
        for module in ctx.sim_state.gpu_modules
        for profile_id in module.hardware_library
    }
    if payload.hardware_profile_id not in available_profiles:
        raise _unprocessable(
            "unmapped_hardware",
            f"Hardware profile {payload.hardware_profile_id!r} is not available "
            "on the active run.",
            field="hardware_profile_id",
            value=payload.hardware_profile_id,
        )
    spec = SlurmJobSpec(
        job_id=payload.job_id,
        arrival_time=ctx.sim_time,
        duration=payload.duration,
        node_count=payload.node_count,
        gpus_per_node=payload.gpus_per_node,
        cpus_per_node=payload.cpus_per_node,
        memory_mb_per_node=payload.memory_mb_per_node,
        gpu_model=payload.gpu_model,
        partition=payload.partition,
        features=frozenset(payload.features),
        priority=payload.priority,
        qos=payload.qos,
        qos_weight=payload.qos_weight,
        fair_share_usage=payload.fair_share_usage,
        dependencies=tuple(payload.dependencies),
        reservation=payload.reservation,
        hardware_profile_id=payload.hardware_profile_id,
        workload_class=WorkloadClass(payload.workload_class),
        site_id=ctx.sim_state.site.site_id,
        tenant_id=payload.tenant_id,
        command=payload.command,
        environment=tuple(sorted(payload.environment.items())),
        job_name=payload.job_name,
        user=payload.user,
        account=payload.account,
        time_limit_s=payload.time_limit_s,
        deadline=payload.deadline,
        ntasks=payload.ntasks,
        cpus_per_task=payload.cpus_per_task,
        memory_mb_per_cpu=payload.memory_mb_per_cpu,
        tmp_disk_mb=payload.tmp_disk_mb,
        gres=payload.gres,
        topology=payload.topology,
        exclusive=payload.exclusive,
        oversubscribe=payload.oversubscribe,
        licenses=payload.licenses,
        burst_buffer=payload.burst_buffer,
        burst_buffer_mb=payload.burst_buffer_mb,
        tres_per_job=payload.tres_per_job,
        requeue=payload.requeue,
        preemptible=payload.preemptible,
        checkpoint_interval_s=payload.checkpoint_interval_s,
        checkpoint_signal_s=payload.checkpoint_signal_s,
        array_start=payload.array_start,
        array_end=payload.array_end,
        array_step=payload.array_step,
        array_max_concurrent=payload.array_max_concurrent,
        federation=payload.federation,
        cluster=payload.cluster,
    )
    try:
        signal = ctx.submit_internal_slurm_job(spec)
    except SlurmSchedulerError as exc:
        raise _unprocessable(
            "slurm_submission_rejected",
            str(exc),
            field="job_id",
            value=payload.job_id,
        ) from exc
    return WorkloadSignalResponse(
        event_id=signal.event_id,
        job_id=signal.job_id,
        event_type=signal.event_type.value,
        timestamp=signal.timestamp,
        hardware_profile_id=signal.hardware_profile_id,
        node_count=signal.node_count,
        workload_class=signal.workload_class.value,
        site_id=signal.site_id,
        scheduler_domain=signal.scheduler_domain,
        tenant_id=signal.tenant_id,
        scheduler_type=signal.scheduler_type,
        capacity_unit=signal.capacity_unit,
        gpus_per_unit=signal.gpus_per_unit,
    )