"""
api/app.py — FastAPI application factory.

Step 6 / v2.5 §8.1 / Design Spec Section 4.

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
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from runtime.run_manager import RunManager, WebSocketHub
from api.routes import runs, ws as ws_routes
from api.routes.scenarios import build_seeded_store
from api.routes import scenarios as scenarios_routes


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
    # asyncio shuts down remaining run tasks on process exit.
    # Explicit cleanup (e.g. waiting for in-flight runs) would go here
    # in a production deployment.


def create_app() -> FastAPI:
    """Application factory.

    Used by tests (each test gets a fresh instance with a fresh lifespan)
    and by the uvicorn entry point (module-level ``app`` below).
    """
    application = FastAPI(
        title="GridSignal Simulator API",
        version="0.1.0",
        lifespan=_lifespan,
    )
    application.include_router(scenarios_routes.router)
    application.include_router(runs.router)
    application.include_router(ws_routes.router)
    return application


# Module-level singleton for uvicorn:
#   uvicorn api.app:app --reload
app = create_app()
