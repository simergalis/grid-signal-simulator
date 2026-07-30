"""
api/routes/runs.py — Run lifecycle REST endpoints.

Step 6 / v2.5 §8.1.

POST   /runs               start a new run
GET    /runs               list active run IDs
GET    /runs/{run_id}      status of one run
DELETE /runs/{run_id}      cancel a run

Invariants:
  - RunManager is retrieved from app.state (set once in the lifespan).
    No endpoint creates its own RunManager instance.
  - No SimClock construction or evaluate_tick() calls here.
    All simulation logic lives in RunContext.step() (runtime/run_manager.py).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.schemas import RunListResponse, RunStatusResponse, StartRunRequest, StartRunResponse
from runtime.run_manager import RunManager
from runtime.scenario_factory import build_run_context

router = APIRouter(prefix="/runs", tags=["runs"])

# ---------------------------------------------------------------------------
# F1 scaffolding: named scenario presets.
# Maps scenario_preset values to build_run_context keyword arguments,
# mirroring the parameters used by runtime/example_usage.py.
# Step 8 replaces this dict with real scenario CRUD; nothing in core/ or
# runtime/ knows about these names — they are an API-layer convenience only.
# ---------------------------------------------------------------------------

_SCENARIO_PRESETS: dict[str, dict] = {
    "demo-20mw": dict(
        job_id="job-big",
        node_count=1900,
        turbine_rated_mw=25.0,
        bess_rated_mw=18.0,
        bess_usable_mwh=8.0,
        bess_grid_forming=True,
    ),
    "demo-alert": dict(
        job_id="job-alert",
        node_count=1900,
        turbine_rated_mw=25.0,
        # bess_rated_mw uses build_run_context default of 5.0
        bess_usable_mwh=2.5,
        bess_grid_forming=True,
    ),
    "demo-5mw": dict(
        job_id="job-small",
        node_count=476,
        dt_lead_seconds=60.0,
    ),
    "demo-baseline": dict(
        job_id="job-idle",
        node_count=1,
    ),
}


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
    manager: RunManager = Depends(_run_manager),
) -> StartRunResponse:
    """Create and immediately start a new RunContext.

    Returns the assigned run_id.  The run advances autonomously via an
    asyncio task; subscribe to /ws/{run_id} for live tick data.

    When scenario_preset is provided, all BESS / turbine parameters are
    expanded from _SCENARIO_PRESETS.  When absent, job_id and node_count
    must both be present (enforced by the StartRunRequest validator).
    """
    run_id = f"run-{uuid.uuid4().hex[:12]}"

    if body.scenario_preset is not None:
        preset_kwargs = _SCENARIO_PRESETS[body.scenario_preset].copy()
    else:
        # hardware_profile_id is passed as an explicit kwarg below; omit it here
        # to avoid "multiple values for keyword argument" when the two are merged.
        preset_kwargs = {
            "job_id": body.job_id,
            "node_count": body.node_count,
        }

    ctx = build_run_context(
        run_id,
        hardware_profile_id=body.hardware_profile_id,
        end_sim_time=body.end_sim_time,
        playback_speed=body.playback_speed,
        **preset_kwargs,
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
