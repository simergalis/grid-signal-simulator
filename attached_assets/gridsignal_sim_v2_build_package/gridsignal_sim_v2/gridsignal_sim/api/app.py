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
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

_log = logging.getLogger(__name__)

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from runtime.run_manager import RunManager, WebSocketHub
from api.routes import runs, ws as ws_routes
from api.routes.scenarios import build_seeded_store
from api.routes import scenarios as scenarios_routes
from api.routes import advisory as advisory_routes
from api.routes import fabric as fabric_routes
from api.routes import solar as solar_routes
from api.routes import location as location_routes
from site_config import SiteLocation, set_site_location
from api.routes import auth_routes, admin_routes
from api.routes import export as export_routes
from api.auth_utils import COOKIE_NAME, decode_access_token
from api.db import create_auth_tables

# §10.2: built frontend lives two levels above this file (api/ → gridsignal_sim/ → gridsignal_sim_v2/)
#   __file__ = .../gridsignal_sim_v2/gridsignal_sim/api/app.py
#   dist     = .../gridsignal_sim_v2/frontend/dist/
_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


async def _solar_tick_loop(sim) -> None:
    """Drive the SolarSim at 1 Hz from a background task.

    A bad tick must not kill the loop — matches the behaviour of the
    standalone renewable console's _tick_loop() in main.py.
    """
    while True:
        await asyncio.sleep(1.0)
        try:
            sim.tick()
        except Exception as exc:
            sim._log("Tick error: %s" % exc, "bad")


@asynccontextmanager
async def _lifespan(application: FastAPI):
    """Create process-lifetime singletons and attach them to app.state.

    Step 8 additions:
      scenario_store — in-memory ScenarioStore pre-seeded with the seven
      built-in demo scenarios.  Step 9 replaces this with a SqliteScenarioStore
      using the same Scenario ORM entity (runtime/persistence.py) + spec_json.

    Renewable console addition:
      solar_sim — SolarSim singleton ticked at 1 Hz so /api/solar/state
      always returns fresh data without a run being active.
    """
    # Ensure AuthUser table exists before any requests arrive.
    await create_auth_tables()

    hub = WebSocketHub()
    manager = RunManager(hub)
    scenario_store = build_seeded_store()
    application.state.ws_hub = hub
    application.state.run_manager = manager
    application.state.scenario_store = scenario_store

    # Renewable Supply Console — one SolarSim per process, ticked continuously.
    from renewable.solar import SolarSim
    solar_sim = SolarSim()
    application.state.solar_sim = solar_sim
    _solar_ticker = asyncio.create_task(_solar_tick_loop(solar_sim))
    # Task #122: give the run manager a reference so _drive() can push each
    # tick's p_renewable_mw into SolarSim and keep the bank panel in sync.
    manager.solar_sim = solar_sim

    # SD-1: restore operator's chosen location across server restarts.
    # load_site_location() handles both schema_version 1 (new) and legacy field names.
    from api.routes.location import load_site_location as _load_loc
    from site_config import get_site_location_or_default as _gslod
    _restored = _load_loc()
    if _restored is not None:
        application.state.site_location = _restored
        set_site_location(_restored)
        _loc = _restored
        _log.info(
            "Restored site_location: %r (lat=%.2f, lon=%.2f, tz=%s)",
            _loc.site_name, _loc.latitude_deg, _loc.longitude_deg, _loc.tz_name,
        )
    else:
        _default = _gslod()
        application.state.site_location = _default
        set_site_location(_default)
        _log.info("No gridsignal_site.json found — using default location: %r", _default.site_name)

    # Sync SolarSim's site_id label to the restored operator location so the
    # /api/solar/state response shows the real site name, not "wenatchee-02".
    import re as _re
    def _loc_slug(name: str) -> str:
        return _re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "datacenter-01"
    solar_sim.cfg.site_id = _loc_slug(application.state.site_location.site_name)

    # Operator-editable site display name (default = "Riverbend DC-West").
    from api.routes.location import SiteSettings
    application.state.site_settings = SiteSettings()

    yield

    # Cancel all in-flight run tasks so that TestClient (which waits for
    # the event loop to drain on __exit__) and graceful uvicorn shutdown
    # both complete promptly rather than hanging on end_sim_time=1e15 runs.
    # _drive() catches CancelledError, runs its finally block, then exits.
    _solar_ticker.cancel()
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
    @application.get("/healthz", include_in_schema=False)
    async def _healthz() -> JSONResponse:
        return JSONResponse({"status": "ok", "version": "0.1.0"})

    # ── Auth middleware ──────────────────────────────────────────────────
    # All /api/* requests are protected except the login endpoint and
    # /healthz.  WebSocket upgrades carry the cookie too so the WS hub
    # is covered.  Returning 401 (not 403) lets the frontend detect an
    # unauthenticated session and redirect to the login page.
    _UNPROTECTED = {"/healthz"}

    @application.middleware("http")
    async def _auth_middleware(request: Request, call_next):
        path = request.url.path
        # Pass through: unprotected API paths and all non-/api/ paths
        # (static assets, SPA index.html, WebSocket upgrade — WS auth is
        # handled by the WS route itself after the HTTP upgrade).
        # Admin routes have their own key/session auth (_require_admin) so
        # the cookie middleware must not block them before they are reached.
        if not path.startswith("/api/") or path in _UNPROTECTED \
                or path.startswith("/api/auth/") or path.startswith("/api/admin") \
                or path.startswith("/api/solar/") \
                or path.startswith("/api/location") \
                or path.startswith("/api/session/"):
            return await call_next(request)
        token = request.cookies.get(COOKIE_NAME)
        if not token or decode_access_token(token) is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated"},
            )
        return await call_next(request)

    # ── API routes (must precede the static catch-all) ──────────────────
    application.include_router(auth_routes.router)   # /api/auth/*
    application.include_router(admin_routes.router)  # /api/admin/*
    application.include_router(scenarios_routes.router)
    application.include_router(runs.router)
    application.include_router(ws_routes.router)
    application.include_router(advisory_routes.router)  # W2
    application.include_router(fabric_routes.router)    # Phase 10
    application.include_router(solar_routes.router)     # Task-20 solar preview
    application.include_router(location_routes.router)  # operator location picker
    application.include_router(export_routes.router)    # telemetry-log CSV download

    # ── §10.2 static frontend (Step 16) ─────────────────────────────────
    # Catch-all GET route: serve real static assets by file path, then fall
    # back to index.html so React Router handles all SPA paths (e.g. /admin).
    #
    # Why not StaticFiles(html=True)? Starlette's html mode falls back to
    # 404.html (served with HTTP 404), not index.html — direct navigation to
    # /admin returns {"detail":"Not Found"} instead of the SPA shell.
    #
    # This block is guarded so the test suite works without a frontend build.
    if _FRONTEND_DIST.is_dir():
        _index_html = _FRONTEND_DIST / "index.html"

        @application.get("/{full_path:path}", include_in_schema=False)
        async def _spa_catchall(full_path: str) -> Response:
            # Unknown /api/* paths should remain JSON 404, not the SPA shell.
            if full_path.startswith("api/"):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            candidate = _FRONTEND_DIST / full_path
            if candidate.is_file():
                return FileResponse(str(candidate))
            return FileResponse(str(_index_html))

    return application


# Module-level singleton for uvicorn:
#   uvicorn api.app:app --reload
app = create_app()
