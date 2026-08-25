"""Inbound scheduler adapters.

The Slurm endpoint accepts one raw slurmrestd job snapshot, translates it into
the simulator's WorkloadSignal contract, and queues it against an active run.
It intentionally does not create a run: the operator must start the scenario
whose physical plant should respond to the customer's workload.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from api.schemas import SlurmJobPayload, WorkloadSignalResponse
from api.routes.admin_routes import _require_admin
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