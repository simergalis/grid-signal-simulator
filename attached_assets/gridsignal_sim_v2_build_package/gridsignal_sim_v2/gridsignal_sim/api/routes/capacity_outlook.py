"""Historical Capacity Outlook analytical routes."""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException, Request

from api.db import (
    list_trace_import_reports, load_capacity_outlook_report, load_trace_import_report,
    persist_capacity_outlook_report,
)
from runtime.capacity_outlook import build_capacity_outlook
from runtime.advisory_gate import make_proposal

router = APIRouter(prefix="/api/capacity-outlook", tags=["capacity-outlook"])


@router.get("/imports")
async def list_imports() -> list[dict[str, Any]]:
    return await list_trace_import_reports()


@router.post("/project")
async def project(request: Request) -> dict[str, Any]:
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "Projection settings must be a JSON object")
    imported = await load_trace_import_report(str(body.get("import_id", "")))
    if imported is None:
        raise HTTPException(404, "Imported trace not found")
    try:
        report = build_capacity_outlook(
            imported,
            percentile=body.get("percentile", 90),
            horizon_days=body.get("horizon_days", 7),
            firm_capacity_mw=body.get("firm_capacity_mw"),
            start_date=body.get("start_date"),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await persist_capacity_outlook_report(report)
    return report


@router.get("/report/{outlook_id}")
async def get_report(outlook_id: str) -> dict[str, Any]:
    report = await load_capacity_outlook_report(outlook_id)
    if report is None:
        raise HTTPException(404, "Capacity outlook report not found")
    return report


@router.post("/report/{outlook_id}/submit-proposal")
async def submit_proposal(outlook_id: str, request: Request) -> dict[str, Any]:
    report = await load_capacity_outlook_report(outlook_id)
    if report is None:
        raise HTTPException(404, "Capacity outlook report not found")
    shortfalls = report.get("shortfall_days") or []
    if not shortfalls:
        raise HTTPException(400, "Capacity outlook has no shortfall to propose")
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    requested_run_id = str(body.get("run_id", "")) if isinstance(body, dict) else ""
    manager = request.app.state.run_manager
    run_id = requested_run_id or f"capacity-outlook-{outlook_id}"
    registry = manager.get_registry(run_id)
    if registry is None and not requested_run_id:
        registry = manager.create_advisory_registry(run_id)
    if registry is None:
        raise HTTPException(409, "Requested simulation run is not available")
    impact = max(float(day["projected_mw"]) - float(report["firm_capacity_mw"]) for day in shortfalls)
    context = manager.get_context(run_id)
    created_at = context.sim_time if context is not None else 0.0
    proposal = make_proposal(
        "reservation", max(0.1, min(20.0, impact)), 1.0,
        f"Historical Capacity Outlook: {report['percentile']:.1f}th percentile projection for "
        f"{report['site_id'] or 'unknown site'} exceeds firm capacity on "
        f"{len(shortfalls)} projected day(s). Outlook {outlook_id}.",
        created_at,
    )
    proposal.originating_agent = "generation"
    proposal.generated_by = "fallback"
    proposal.requires_confirmation = True
    gate = registry.get_gate()
    if not gate.validate(proposal):
        raise HTTPException(400, proposal.rejection_reason or "Proposal rejected")
    return {"proposal_id": proposal.proposal_id, "state": proposal.state.value, "requires_confirmation": True}