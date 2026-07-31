"""
api/routes/runs.py — Run lifecycle REST endpoints.

Step 6 / v2.5 §8.1.
Step 8: removes F1 _SCENARIO_PRESETS scaffolding; adds scenario_id path that
        looks up a stored ScenarioSpec and calls build_run_context_from_spec.

POST   /runs               start a new run
GET    /runs               list active run IDs
GET    /runs/{run_id}      status of one run
DELETE /runs/{run_id}      cancel a run

Invariants:
  - RunManager is retrieved from app.state (set once in the lifespan).
    No endpoint creates its own RunManager instance.
  - ScenarioStore is retrieved from app.state (set once in the lifespan).
    No endpoint creates its own ScenarioStore instance.
  - No SimClock construction or evaluate_tick() calls here.
    All simulation logic lives in RunContext.step() (runtime/run_manager.py).
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.schemas import RunListResponse, RunStatusResponse, StartRunRequest, StartRunResponse
from runtime.run_manager import RunManager
from runtime.scenario_factory import build_run_context, build_run_context_from_spec

router = APIRouter(prefix="/runs", tags=["runs"])


def _run_manager(request: Request) -> RunManager:
    """Dependency: retrieve the shared RunManager from FastAPI app state."""
    return request.app.state.run_manager


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=StartRunResponse,
    summary="Start a new simulation run",
)
async def start_run(
    body: StartRunRequest,
    request: Request,
    manager: RunManager = Depends(_run_manager),
) -> StartRunResponse:
    """Create and immediately start a new RunContext.

    Returns the assigned run_id.  The run advances autonomously via an
    asyncio task; subscribe to /ws/{run_id} for live tick data.

    Two accepted paths (Step 8 — scenario_preset removed):

    (a) scenario_id: looks up the stored ScenarioSpec and builds the
        RunContext via build_run_context_from_spec.  All fleet/workload
        parameters come from the stored spec.

    (b) job_id + node_count: direct programmatic path — calls the flat
        build_run_context kwarg interface.  Used by tests and load scripts.
    """
    run_id = f"run-{uuid.uuid4().hex[:12]}"

    if body.scenario_id is not None:
        scenario_store = request.app.state.scenario_store
        record = scenario_store.get(body.scenario_id)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scenario {body.scenario_id!r} not found. "
                       f"Use GET /scenarios to list available scenarios.",
            )
        scenario_store.link_run(body.scenario_id, run_id)
        spec_data = json.loads(record.spec_json)
        ctx = build_run_context_from_spec(
            run_id,
            spec_data,
            playback_speed=body.playback_speed,
        )
    else:
        # Direct programmatic path — scenario_id absent, job_id+node_count present
        # (enforced by StartRunRequest.model_validator).
        ctx = build_run_context(
            run_id,
            job_id=body.job_id,
            node_count=body.node_count,
            hardware_profile_id=body.hardware_profile_id,
            end_sim_time=body.end_sim_time,
            playback_speed=body.playback_speed,
        )

    await manager.start_run(ctx)
    return StartRunResponse(run_id=run_id)


@router.get(
    "",
    response_model=RunListResponse,
    summary="List active run IDs",
)
async def list_runs(
    manager: RunManager = Depends(_run_manager),
) -> RunListResponse:
    """Return the IDs of all runs currently held by the RunManager."""
    return RunListResponse(run_ids=manager.active_run_ids())


@router.get(
    "/{run_id}",
    response_model=RunStatusResponse,
    summary="Get run status",
    responses={404: {"description": "Run not found"}},
)
async def get_run_status(
    run_id: str,
    manager: RunManager = Depends(_run_manager),
) -> RunStatusResponse:
    """Return active status for the given run_id.

    Returns 404 if the run does not exist or has already completed and
    been cleaned up by the RunManager.
    """
    ctx = manager.get_context(run_id)
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id!r} not found",
        )
    return RunStatusResponse(run_id=run_id, active=not ctx.is_complete())


@router.delete(
    "/{run_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel a run",
    responses={404: {"description": "Run not found"}},
)
async def cancel_run(
    run_id: str,
    manager: RunManager = Depends(_run_manager),
) -> None:
    """Cancel the given run and wait for its drive task to finish.

    Returns 204 on success, 404 if the run does not exist.
    """
    ctx = manager.get_context(run_id)
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id!r} not found",
        )
    await manager.cancel_run(run_id)
