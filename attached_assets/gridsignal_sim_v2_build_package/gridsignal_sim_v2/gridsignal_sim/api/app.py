"""
api/app.py — FastAPI application factory.

Step 6 / v2.5 §8.1 / Design Spec Section 4.
Step 16 / §10.2: single-port model — FastAPI serves both the REST/WS API
  and the pre-built React frontend as static files.  Route registration
  order is strict: API routers first, then the static-file catch-all.
  The static mount is only attached when the frontend dist/ directory
  exists, so the test suite (which never builds the frontend) is unaffected.

ONE RunManager and ONE WebSocketHub are created in the lifespan context
and attached to app.state.  Every request handler retrieves them through
dependency injection (Depends(_run_manager) / websocket.app.state.ws_hub)
rather than constructing their own instances.

This is the enforcement point for Step 12's single-orchestrator invariant:
because agents (Step 12) interact through the HTTP API, they share the same
RunManager and therefore the same concurrency budget and the same audit log.
An agent that bypassed the API and constructed its own RunManager would be
invisible to the rate limiter, the concurrency cap, and the audit trail.

Invariants:
  - No import from core/ in api/.  All core logic is accessed through
    runtime/, which is itself accessed through the RunContext/RunManager
    boundary.  Step 4's static gate (scripts/check_plane_separation.py)
    enforces this for core/ → runtime/; api/ → core/ is prevented here
    by design and is not scanned by the static gate (which only checks
    core/).
  - api/ never constructs a SimClock or calls evaluate_tick() directly.
    RunContext.step() in runtime/run_manager.py is the sole owner of
    both the plane-guard sentinel and the wall-clock stamp.

LP-1 guarantee (Step 12/16):
  MISTRAL_API_KEY and ANTHROPIC_API_KEY are NOT required for the simulator
  to start or run.  With both absent the advisory router returns None and the
  sim runs with the deterministic heuristic fallback.  Tests and the
  deployed app MUST both pass without any LLM keys set.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from runtime.run_manager import RunManager, WebSocketHub
from api.routes import runs, ws as ws_routes
from api.routes.scenarios import build_seeded_store
from api.routes import scenarios as scenarios_routes
from api.routes import advisory as advisory_routes
from api.routes import fabric as fabric_routes
from api.routes import solar as solar_routes

# §10.2: built frontend lives two levels above this file (api/ → gridsignal_sim/ → gridsignal_sim_v2/)
#   __file__ = .../gridsignal_sim_v2/gridsignal_sim/api/app.py
#   dist     = .../gridsignal_sim_v2/frontend/dist/
_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def _lifespan(application: FastAPI):
    """Create process-lifetime singletons and attach them to app.state.

    Step 8 additions:
      scenario_store — in-memory ScenarioStore pre-seeded with the seven
      built-in demo scenarios.  Step 9 replaces this with a SqliteScenarioStore
      using the same Scenario ORM entity (runtime/persistence.py) + spec_json.
    """
    hub = WebSocketHub()
    manager = RunManager(hub)
    scenario_store = build_seeded_store()
    application.state.ws_hub = hub
    application.state.run_manager = manager
    application.state.scenario_store = scenario_store
    yield
    # Cancel all in-flight run tasks so that TestClient (which waits for
    # the event loop to drain on __exit__) and graceful uvicorn shutdown
    # both complete promptly rather than hanging on end_sim_time=1e15 runs.
    # _drive() catches CancelledError, runs its finally block, then exits.
    running_tasks = list(manager._tasks.values())
    for task in running_tasks:
        task.cancel()
    if running_tasks:
        await asyncio.gather(*running_tasks, return_exceptions=True)


def create_app() -> FastAPI:
    """Application factory.

    Used by tests (each test gets a fresh instance with a fresh lifespan)
    and by the uvicorn entry point (module-level ``app`` below).

    §10.2 single-port model: API routes are registered first so they are
    matched before the static catch-all.  The StaticFiles mount is
    conditional on the dist/ directory existing so tests are not broken by
    a missing frontend build.
    """
    application = FastAPI(
        title="GridSignal Simulator API",
        version="0.1.0",
        lifespan=_lifespan,
    )

    # ── Health check (§10.2 / Step 16) ──────────────────────────────────
    # /healthz is the deployment startup-probe path.  It must be reachable
    # before the static-file mount is added, and must not require any
    # application state — it answers immediately from the route table.
    from fastapi.responses import JSONResponse

    @application.get("/healthz", include_in_schema=False)
    async def _healthz() -> JSONResponse:
        return JSONResponse({"status": "ok", "version": "0.1.0"})

    # ── API routes (must precede the static catch-all) ──────────────────
    application.include_router(scenarios_routes.router)
    application.include_router(runs.router)
    application.include_router(ws_routes.router)
    application.include_router(advisory_routes.router)  # W2
    application.include_router(fabric_routes.router)    # Phase 10
    application.include_router(solar_routes.router)     # Task-20 solar preview

    # ── §10.2 static frontend (Step 16) ─────────────────────────────────
    # Mount the pre-built React SPA at the root.  StaticFiles(html=True)
    # serves index.html for any path that doesn't match a static asset,
    # which is the standard SPA fallback pattern.
    #
    # This block is deliberately guarded so the unit/integration test suite
    # continues to work without a frontend build: the test client only
    # exercises the API routes, which are registered unconditionally above.
    if _FRONTEND_DIST.is_dir():
        application.mount(
            "/",
            StaticFiles(directory=str(_FRONTEND_DIST), html=True),
            name="frontend",
        )

    return application


# Module-level singleton for uvicorn:
#   uvicorn api.app:app --reload
app = create_app()
