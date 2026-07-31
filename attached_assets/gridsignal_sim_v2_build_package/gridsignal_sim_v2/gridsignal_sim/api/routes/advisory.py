"""
api/routes/advisory.py — W2 advisory, telemetry, procurement, and thermal endpoints.

GET  /proposals/{run_id}              all proposals from a run's AgentRegistry
POST /proposals/{proposal_id}/accept  reviewer accepts a pending proposal
POST /proposals/{proposal_id}/reject  reviewer rejects a pending proposal
GET  /procurement/{run_id}            grid capacity + price curve snapshot
GET  /network-telemetry               fabric telemetry + corroboration records
GET  /thermal                         cooling headroom snapshot (?run_id=)

Design notes
------------
• Proposals work for both ACTIVE and COMPLETED runs (registry preserved in
  RunManager._registries after _drive() finishes).
• Procurement, telemetry, and thermal are monitoring surfaces — they only
  serve active runs (409 if run is complete, 404 if unknown).
• Accept/reject search all live registries plus completed registry store so
  a reviewer can act on a proposal that arrived just as the run ended.
• No simulation state is modified by any of these endpoints — only the
  advisory gate's proposal lifecycle.
"""
from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel

from runtime.run_manager import RunManager

router = APIRouter(tags=["advisory"])


def _run_manager(request: Request) -> RunManager:
    return request.app.state.run_manager


# ---------------------------------------------------------------------------
# Proposal schemas
# ---------------------------------------------------------------------------

class ProposalOut(BaseModel):
    proposal_id: str
    kind: str
    estimated_impact_mw: float
    confidence: float
    reasoning: str
    state: str
    expires_at_sim_time: float
    created_at_sim_time: float
    suggested_tier: Optional[str]
    originating_agent: str
    prompt_digest: str
    evidence_digest: str
    generated_by: str
    requires_confirmation: bool
    rejection_reason: Optional[str]
    reviewer_id: str
    accepted_at_sim_time: Optional[float]


class ProposalsResponse(BaseModel):
    run_id: str
    proposals: list[ProposalOut]


class AcceptBody(BaseModel):
    reviewer_id: str = ""


class RejectBody(BaseModel):
    reason: str = ""


# ---------------------------------------------------------------------------
# GET /proposals/{run_id}
# ---------------------------------------------------------------------------

@router.get(
    "/proposals/{run_id}",
    response_model=ProposalsResponse,
    summary="List all advisory proposals for a run",
)
async def list_proposals(run_id: str, request: Request) -> ProposalsResponse:
    """Return all proposals from the run's AgentRegistry, ordered by creation time.

    Works for both active and completed runs (registry is preserved in
    RunManager._registries after _drive() finishes).
    Returns 404 if the run_id is unknown to this server process.
    """
    manager = _run_manager(request)
    registry = manager.get_registry(run_id)

    # Also accept active-run check so we can return 404 vs 200 with empty list.
    ctx = manager.get_context(run_id)
    completed = manager.get_completed(run_id)

    if registry is None and ctx is None and completed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id!r} not found (unknown to this server process).",
        )

    proposals = registry.all_proposals() if registry is not None else []
    return ProposalsResponse(
        run_id=run_id,
        proposals=[
            ProposalOut(
                proposal_id=p.proposal_id,
                kind=p.kind,
                estimated_impact_mw=p.estimated_impact_mw,
                confidence=p.confidence,
                reasoning=p.reasoning,
                state=p.state.value,
                expires_at_sim_time=p.expires_at_sim_time,
                created_at_sim_time=p.created_at_sim_time,
                suggested_tier=p.suggested_tier,
                originating_agent=p.originating_agent,
                prompt_digest=p.prompt_digest,
                evidence_digest=p.evidence_digest,
                generated_by=p.generated_by,
                requires_confirmation=p.requires_confirmation,
                rejection_reason=p.rejection_reason,
                reviewer_id=p.reviewer_id,
                accepted_at_sim_time=p.accepted_at_sim_time,
            )
            for p in sorted(proposals, key=lambda p: p.created_at_sim_time)
        ],
    )


# ---------------------------------------------------------------------------
# POST /proposals/{proposal_id}/accept
# ---------------------------------------------------------------------------

@router.post(
    "/proposals/{proposal_id}/accept",
    status_code=status.HTTP_200_OK,
    summary="Accept a pending proposal (TC-52: always requires reviewer_id)",
)
async def accept_proposal(
    proposal_id: str,
    body: AcceptBody,
    request: Request,
) -> dict:
    """Transition proposal to ACCEPTED.

    TC-52 / O2: records reviewer_id and accepted_at_sim_time on the Proposal.
    Dispatch is NOT affected — TC-48 holds.
    Raises 404 if the proposal is unknown, 409 if already terminal.
    """
    manager = _run_manager(request)
    gate, current_sim_time = _find_gate_for_proposal(manager, proposal_id)
    if gate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proposal {proposal_id!r} not found in any active or completed run.",
        )
    try:
        gate.accept(
            proposal_id,
            reviewer_id=body.reviewer_id,
            accepted_at_sim_time=current_sim_time,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"accepted": True, "proposal_id": proposal_id}


# ---------------------------------------------------------------------------
# POST /proposals/{proposal_id}/reject
# ---------------------------------------------------------------------------

@router.post(
    "/proposals/{proposal_id}/reject",
    status_code=status.HTTP_200_OK,
    summary="Reject a pending proposal",
)
async def reject_proposal(
    proposal_id: str,
    body: RejectBody,
    request: Request,
) -> dict:
    """Transition proposal to REJECTED (reviewer decision).

    Raises 404 if unknown, 409 if already terminal.
    """
    manager = _run_manager(request)
    gate, _ = _find_gate_for_proposal(manager, proposal_id)
    if gate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proposal {proposal_id!r} not found in any active or completed run.",
        )
    try:
        gate.reject(proposal_id, reason=body.reason or "reviewer_rejected")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"rejected": True, "proposal_id": proposal_id}


def _find_gate_for_proposal(manager: RunManager, proposal_id: str):
    """Search all live + completed registries for a proposal.

    Returns (gate, current_sim_time) if found, or (None, 0.0).
    current_sim_time is read from the active RunContext if available.
    """
    # Search active runs first.
    for run_id, ctx in list(manager._contexts.items()):
        if ctx.registry is not None:
            gate = ctx.registry.get_gate()
            if gate.get(proposal_id) is not None:
                return gate, ctx.sim_time

    # Search completed-run registries.
    for run_id, registry in list(manager._registries.items()):
        gate = registry.get_gate()
        if gate.get(proposal_id) is not None:
            return gate, 0.0

    return None, 0.0


# ---------------------------------------------------------------------------
# Procurement schemas
# ---------------------------------------------------------------------------

class CapacityRowOut(BaseModel):
    capacity_type: str
    available_mw: float
    price_per_mwh: float
    t_reserve_s: float


class PricePointOut(BaseModel):
    sim_time: float
    price_per_mwh: float


class ProcurementResponse(BaseModel):
    run_id: str
    sim_time: float
    reserve_gap_mw: float
    firm_mw: float
    reserved_mw: float
    non_firm_mw: float
    served_load_mw: float
    capacity: list[CapacityRowOut]
    price_curve: list[PricePointOut]


# ---------------------------------------------------------------------------
# GET /procurement/{run_id}
# ---------------------------------------------------------------------------

@router.get(
    "/procurement/{run_id}",
    response_model=ProcurementResponse,
    summary="Grid capacity and price curve for an active run",
    responses={
        404: {"description": "Run not found"},
        409: {"description": "Run is complete — procurement data no longer live"},
    },
)
async def get_procurement(run_id: str, request: Request) -> ProcurementResponse:
    """Return the current grid capacity snapshot and forward price curve.

    TC-47: reserve_gap_mw is NOT reduced by non_firm imports.
    Only served for active runs (monitoring surface).
    """
    manager = _run_manager(request)

    # Reject completed runs — this is a live monitoring surface.
    if manager.get_completed(run_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run {run_id!r} is complete; procurement data is no longer live.",
        )

    ctx = manager.get_context(run_id)
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id!r} not found.",
        )
    if not ctx.grid_capacity or ctx.price_curve is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id!r} has no procurement state (test-only run).",
        )

    # Current tick values from the last completed tick.
    served_load = ctx._last_cooling_mw + (ctx.sim_state.cooling._prev_agg_mw if hasattr(ctx.sim_state.cooling, '_prev_agg_mw') else 0.0)
    # Use the most recent tick from tick_history for served_load and net demand.
    if ctx.tick_history:
        last_tick = ctx.tick_history[-1]
        served_load_mw = last_tick.net_demand_mw
        sim_t = last_tick.sim_time_seconds
    else:
        served_load_mw = 0.0
        sim_t = ctx.sim_time

    # Capacity by type.
    firm = next((c for c in ctx.grid_capacity if c.capacity_type.value == "firm"), None)
    firm_mw = firm.available_mw if firm else 0.0
    reserved = next((c for c in ctx.grid_capacity if c.capacity_type.value == "reserved"), None)
    reserved_mw = reserved.available_mw if reserved else 0.0
    non_firm = next((c for c in ctx.grid_capacity if c.capacity_type.value == "non_firm"), None)
    non_firm_mw = non_firm.available_mw if non_firm else 0.0

    # Reserve gap: firm capacity vs. current served demand.
    # TC-47: non_firm import does NOT close this gap.
    reserve_gap = max(0.0, served_load_mw - firm_mw)

    # Forward price curve: 12 points over the next simulated hour.
    curve = ctx.price_curve.points(sim_t, sim_t + 3600.0, n=12)

    return ProcurementResponse(
        run_id=run_id,
        sim_time=sim_t,
        reserve_gap_mw=round(reserve_gap, 3),
        firm_mw=firm_mw,
        reserved_mw=reserved_mw,
        non_firm_mw=non_firm_mw,
        served_load_mw=round(served_load_mw, 3),
        capacity=[
            CapacityRowOut(
                capacity_type=c.capacity_type.value,
                available_mw=c.available_mw,
                price_per_mwh=c.price_per_mwh,
                t_reserve_s=c.t_reserve_s,
            )
            for c in ctx.grid_capacity
        ],
        price_curve=[
            PricePointOut(sim_time=pt.sim_time, price_per_mwh=pt.price_per_mwh)
            for pt in curve
        ],
    )


# ---------------------------------------------------------------------------
# Network telemetry schemas
# ---------------------------------------------------------------------------

class SwitchRowOut(BaseModel):
    switch_id: str
    interface_id: str
    throughput_rx_mbps: float
    throughput_tx_mbps: float
    optical_power_tx_dbm: float
    optical_power_rx_dbm: float
    clock_discipline: str
    effective_discipline: str
    observed_skew_ms: float
    error_count: int
    sample_time_s: float


class CorroborationRowOut(BaseModel):
    job_id: str
    predicted_start_sim_time: float
    result: str
    authoritative_event: Optional[str]
    fabric_rise_observed: bool
    fabric_rise_sim_time: Optional[float]


class QuarantineRowOut(BaseModel):
    event_id: str
    reason: str
    sim_time: float


class NetworkTelemetryResponse(BaseModel):
    run_id: str
    capability: str
    last_updated_s: float
    switches: list[SwitchRowOut]
    corroboration: list[CorroborationRowOut]
    quarantine: list[QuarantineRowOut]


# ---------------------------------------------------------------------------
# GET /network-telemetry?run_id=
# ---------------------------------------------------------------------------

@router.get(
    "/network-telemetry",
    response_model=NetworkTelemetryResponse,
    summary="Fabric switch telemetry and corroboration for an active run",
    responses={
        404: {"description": "Run not found or has no telemetry state"},
        409: {"description": "Run is complete"},
    },
)
async def get_network_telemetry(
    run_id: str = Query(..., description="Active run ID"),
    request: Request = None,
) -> NetworkTelemetryResponse:
    """Return validated switch records, corroboration, and quarantine log.

    TC-74: this data is dispatch-path ineligible — it never influences
    forecast or dispatch, only the monitoring surface.
    """
    manager = _run_manager(request)

    if manager.get_completed(run_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run {run_id!r} is complete.",
        )

    ctx = manager.get_context(run_id)
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id!r} not found.",
        )
    if ctx.telemetry_ingestor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id!r} has no telemetry ingestor (test-only run).",
        )

    ingestor = ctx.telemetry_ingestor
    last_t = ctx.sim_time

    # Group records by switch_id + interface_id, keeping the most recent.
    latest: dict[str, object] = {}
    for rec in ingestor.all_records():
        key = f"{rec.switch_id}:{rec.interface_id}"
        if key not in latest or rec.timestamp > latest[key].timestamp:  # type: ignore[attr-defined]
            latest[key] = rec

    switches = []
    for rec in latest.values():
        # TC-70 clock-demotion rule (inlined — no core/ import allowed in api/).
        # A source that declares PTP but shows skew > 2 ms is demoted to NTP-class.
        disc_str: str = rec.clock_discipline.value  # type: ignore[attr-defined]
        skew: float = rec.observed_skew_ms  # type: ignore[attr-defined]
        eff_str: str = "ntp" if (disc_str == "ptp" and skew > 2.0) else disc_str

        err_count = sum(max(0, v) for v in rec.error_counters.values())  # type: ignore[attr-defined]
        switches.append(SwitchRowOut(
            switch_id=rec.switch_id,  # type: ignore[attr-defined]
            interface_id=rec.interface_id,  # type: ignore[attr-defined]
            throughput_rx_mbps=round(rec.throughput_rx_bps / 1e6, 2),  # type: ignore[attr-defined]
            throughput_tx_mbps=round(rec.throughput_tx_bps / 1e6, 2),  # type: ignore[attr-defined]
            optical_power_tx_dbm=rec.optical_power_tx_dbm,  # type: ignore[attr-defined]
            optical_power_rx_dbm=rec.optical_power_rx_dbm,  # type: ignore[attr-defined]
            clock_discipline=disc_str,
            effective_discipline=eff_str,
            observed_skew_ms=skew,
            error_count=err_count,
            sample_time_s=rec.timestamp,  # type: ignore[attr-defined]
        ))

    corroboration = []
    if ctx.corroborator is not None:
        for rec in ctx.corroborator.all_records():
            corroboration.append(CorroborationRowOut(
                job_id=rec.job_id,
                predicted_start_sim_time=rec.predicted_start_sim_time,
                result=rec.result.value,
                authoritative_event=rec.authoritative_event,
                fabric_rise_observed=rec.fabric_rise_observed,
                fabric_rise_sim_time=rec.fabric_rise_sim_time,
            ))

    quarantine_rows = []
    for qr in ingestor._quarantine.all_records():
        quarantine_rows.append(QuarantineRowOut(
            event_id=qr.event_id,
            reason=qr.reason,
            sim_time=qr.sim_time,
        ))

    return NetworkTelemetryResponse(
        run_id=run_id,
        capability=ingestor.capability.value,
        last_updated_s=last_t,
        switches=sorted(switches, key=lambda s: s.switch_id),
        corroboration=sorted(corroboration, key=lambda c: c.predicted_start_sim_time),
        quarantine=quarantine_rows,
    )


# ---------------------------------------------------------------------------
# Thermal schemas
# ---------------------------------------------------------------------------

class CoolingZoneOut(BaseModel):
    zone_id: str
    zone_name: str
    load_mw: float
    capacity_mw: float
    utilisation: float


class ThermalResponse(BaseModel):
    run_id: str
    absorbable_mw: float
    time_to_limit_s: float
    current_load_mw: float
    rated_capacity_mw: float
    inlet_temp_c: float
    inlet_comfort_lo_c: float
    inlet_comfort_hi_c: float
    approach_rate_mw_s: float
    zones: list[CoolingZoneOut]
    tick_s: float


# ---------------------------------------------------------------------------
# GET /thermal?run_id=
# ---------------------------------------------------------------------------

@router.get(
    "/thermal",
    response_model=ThermalResponse,
    summary="Thermal headroom snapshot for an active run",
    responses={
        404: {"description": "Run not found"},
        409: {"description": "Run is complete"},
    },
)
async def get_thermal(
    run_id: str = Query(..., description="Active run ID"),
    request: Request = None,
) -> ThermalResponse:
    """Return thermal headroom derived from CoolingModule state.

    §19.6 read-only monitoring surface — no controls here affect dispatch.
    TC-55 interlock lives in the dispatch layer (core/dispatch.py).
    """
    manager = _run_manager(request)

    if manager.get_completed(run_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run {run_id!r} is complete.",
        )

    ctx = manager.get_context(run_id)
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id!r} not found.",
        )

    current_mw = ctx.sim_state.cooling.output_mw()
    rated_mw = ctx._rated_cooling_mw if ctx._rated_cooling_mw > 0 else max(current_mw * 1.25, 1.0)
    absorbable = max(0.0, rated_mw - current_mw)
    approach = ctx._approach_rate_mw_s

    # Time to limit: how long until headroom = 0 at current approach rate.
    # Cap at 24 h for JSON safety; ∞ when not rising.
    if approach > 1e-6:
        time_to_limit = min(absorbable / approach, 86_400.0)
    else:
        time_to_limit = 86_400.0   # effectively infinite

    _INLET_LO = 18.0   # PreStagingConfig.inlet_temp_low_c (PROTO-10)
    _INLET_HI = 24.0   # PreStagingConfig.inlet_temp_high_c (PROTO-10)

    # Synthesise a single-zone breakdown (real zone telemetry needs hardware).
    utilisation = min(1.0, current_mw / rated_mw) if rated_mw > 0 else 0.0
    zones = [
        CoolingZoneOut(
            zone_id="z0",
            zone_name="Aggregate (all aisles)",
            load_mw=round(current_mw, 3),
            capacity_mw=round(rated_mw, 3),
            utilisation=round(utilisation, 4),
        )
    ]

    return ThermalResponse(
        run_id=run_id,
        absorbable_mw=round(absorbable, 3),
        time_to_limit_s=round(time_to_limit, 1),
        current_load_mw=round(current_mw, 3),
        rated_capacity_mw=round(rated_mw, 3),
        inlet_temp_c=round(ctx._inlet_temp_c, 2),
        inlet_comfort_lo_c=_INLET_LO,
        inlet_comfort_hi_c=_INLET_HI,
        approach_rate_mw_s=round(approach, 6),
        zones=zones,
        tick_s=ctx.sim_time,
    )
