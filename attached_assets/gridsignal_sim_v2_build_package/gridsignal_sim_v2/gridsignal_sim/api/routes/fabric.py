"""
api/routes/fabric.py — Phase 10 fabric model REST endpoints.

GET  /api/fabric/fixture                 → topology fixture as loaded
GET  /api/fabric/state?run_id=X          → per-link state for latest tick
GET  /api/fabric/modal?run_id=X          → six plant-plane modal fields
GET  /api/fabric/control-path?run_id=X   → decomposed latency for latest tick
GET  /api/session/transport              → session transport (InstrumentPlane)
POST /api/fabric/stressor?run_id=X       → inject a stressor at runtime (stub)

The session transport endpoint (GET /api/session/transport) returns live
wall-clock measurements.  It must work when the simulation is stopped —
TC-85 verifies this.

Invariants:
  - No import from core/ here.  The fabric engine is accessed through
    RunContext.fabric_engine (type Any in RunContext to avoid circular imports).
  - A run_id that has no active context returns 404.
  - A run_id whose fabric_engine is None returns 503 with a clear message.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api", tags=["fabric"])

# ---------------------------------------------------------------------------
# Shared InstrumentPlane singleton — session transport is process-lifetime,
# independent of any individual run.  One instance serves all clients.
# ---------------------------------------------------------------------------
_INSTRUMENT = None


def _get_instrument():
    global _INSTRUMENT
    if _INSTRUMENT is None:
        from fabric.instrument import InstrumentPlane
        _INSTRUMENT = InstrumentPlane()
    return _INSTRUMENT


def _get_run_manager(request: Request):
    return request.app.state.run_manager


def _require_fabric_engine(run_id: str, manager):
    """Return the FabricEngine for run_id or raise an appropriate HTTPException."""
    ctx = manager.get_context(run_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail=f"No active run with id={run_id!r}")
    engine = getattr(ctx, "fabric_engine", None)
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail="Fabric engine not wired for this run (direct job-id path)",
        )
    return engine


# ---------------------------------------------------------------------------
# GET /api/fabric/fixture
# ---------------------------------------------------------------------------

@router.get("/fabric/fixture")
async def get_fabric_fixture():
    """Return the topology fixture currently loaded by the FabricEngine."""
    cfg_path = Path("config/fabric_fixture_default.json")
    if not cfg_path.exists():
        raise HTTPException(status_code=503, detail="Fabric fixture not found")
    return JSONResponse(json.loads(cfg_path.read_text()))


# ---------------------------------------------------------------------------
# GET /api/fabric/state?run_id=X
# ---------------------------------------------------------------------------

@router.get("/fabric/state")
async def get_fabric_state(
    run_id: str,
    request: Request,
):
    """Return per-link state for the latest tick of an active run."""
    manager = _get_run_manager(request)
    engine = _require_fabric_engine(run_id, manager)
    result = engine.latest_result
    if result is None:
        return JSONResponse({"links": [], "tick": None, "message": "No tick yet"})
    return JSONResponse({
        "tick": result.tick,
        "sim_time_s": result.sim_time_s,
        "links": [
            {
                "link_id":       s.link_id,
                "fabric_id":     s.fabric_id,
                "u":             round(s.u, 4),
                "demand_bps":    s.demand_bps,
                "carried_bps":   s.carried_bps,
                "capacity_bps":  s.capacity_bps,
                "headroom_bps":  s.headroom_bps,
                "congested":     s.congested,
                "loss_p":        round(s.loss_p, 6),
                "retransmit_r":  round(s.retransmit_r, 6),
                "down":          s.down,
            }
            for s in result.links
        ],
    })


# ---------------------------------------------------------------------------
# GET /api/fabric/modal?run_id=X
# ---------------------------------------------------------------------------

@router.get("/fabric/modal")
async def get_fabric_modal(
    run_id: str,
    request: Request,
):
    """
    Return the six plant-plane modal fields plus control-path decomposition.
    These are exactly the fields the Network Fabric modal renders.
    """
    manager = _get_run_manager(request)
    engine = _require_fabric_engine(run_id, manager)
    mv = engine.modal_view()
    if mv is None:
        return JSONResponse({
            "status": "no_data",
            "message": "Fabric engine has not produced a tick yet",
        })
    return JSONResponse(mv)


# ---------------------------------------------------------------------------
# GET /api/fabric/control-path?run_id=X
# ---------------------------------------------------------------------------

@router.get("/fabric/control-path")
async def get_fabric_control_path(
    run_id: str,
    request: Request,
):
    """Return the decomposed control-path latency for the latest tick."""
    manager = _get_run_manager(request)
    engine = _require_fabric_engine(run_id, manager)
    result = engine.latest_result
    if result is None:
        return JSONResponse({"status": "no_data"})
    cp = result.control
    return JSONResponse({
        "tick":             result.tick,
        "sim_time_s":       result.sim_time_s,
        "l_fabric_ms":      round(cp.l_fabric_ms, 3),
        "l_gateway_ms":     round(cp.l_gateway_ms, 3),
        "l_retransmit_ms":  round(cp.l_retransmit_ms, 3),
        "l_asset_ack_ms":   round(cp.l_asset_ack_ms, 3),
        "l_total_ms":       round(cp.l_total_ms, 3),
        "budget_ms":        cp.budget_ms,
        "breached":         cp.breached,
        "dominant_term":    cp.dominant_term,
        "asset_class":      cp.asset_class,
    })


# ---------------------------------------------------------------------------
# GET /api/session/transport
# ---------------------------------------------------------------------------

@router.get("/session/transport")
async def get_session_transport():
    """
    Return live session-transport measurements from the InstrumentPlane.
    Returns live values regardless of whether a simulation is running — TC-85.
    """
    inst = _get_instrument()
    view = inst.modal_view()
    return JSONResponse(view)


# ---------------------------------------------------------------------------
# POST /api/fabric/stressor?run_id=X  (Phase 10 stub)
# ---------------------------------------------------------------------------

@router.post("/fabric/stressor")
async def inject_fabric_stressor(
    run_id: str,
    request: Request,
):
    """
    Inject a stressor at runtime.  Phase 10 stub — returns 200 with an
    advisory message.  Full implementation will wire into FabricEngine.stressors.
    """
    body = await request.json()
    return JSONResponse({
        "accepted": False,
        "advisory": (
            "Runtime stressor injection is not yet implemented. "
            "Use the scenario JSON 'stressors' field to apply stressors before a run."
        ),
        "received": body,
    }, status_code=200)
