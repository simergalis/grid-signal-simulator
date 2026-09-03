"""
api/routes/economic_profiles.py — Margin Contribution Tool: Economic Profile CRUD
and proforma calculation (Forecast Engine Functional Spec Addendum §30).

POST   /api/economic-profiles                          create profile
GET    /api/economic-profiles                          list profiles
GET    /api/economic-profiles/{id}                     profile detail
PUT    /api/economic-profiles/{id}                     update profile
DELETE /api/economic-profiles/{id}                     delete profile
GET    /api/economic-profiles/{id}/proforma            calculate margin contribution
GET    /api/economic-profiles/{id}/proforma/export     CSV export

Locked decisions (from T1 implementation prompt):
  1. Dispatch data durability: in-memory MVP — proforma only generatable while the
     originating server process is alive.  A 410 or 409 from /runs/{id}/timeseries
     results in a clear operator-facing message, not a crash.
  2. EconomicProfile scoping: site_id FK (no RLS).
  3. Per-tenant MWh: quick approximate sum from est_draw_mw per tick.

Grid exchange sign: grid_exchange_mw in tick_dicts is positive-on-import
  (simulation_core.py:2089 negates the internal supply-residual convention).
  COGS uses max(0, grid_exchange_mw) to count import energy only.

dt_s per tick: computed from consecutive sim_time_seconds differences, not
  assumed constant.  Satisfies AC-3.2.

MC-1 period scaling: repeat-and-scale.  Monthly=730h, Quarterly=2190h,
  Annual=8760h.  scale_factor = target_hours / run_duration_hours.
  Operator must acknowledge this in the UI (mockup note is functional, not decoration).

is-not-None discipline: every Optional cost field tested independently per
  api/routes/runs.py:194–200.  None → 0.0 contribution (not a fallback rate).
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from api.db import get_db_session
from runtime.persistence import EconomicProfile, EconomicProfileTenantRate
from runtime.run_manager import RunManager

router = APIRouter(prefix="/api/economic-profiles", tags=["economic-profiles"])

# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _run_manager(request: Request) -> RunManager:
    return request.app.state.run_manager


# ---------------------------------------------------------------------------
# Period scaling constants (MC-1)
# ---------------------------------------------------------------------------

_PERIOD_HOURS: dict[str, float] = {
    "monthly": 730.0,
    "quarterly": 2190.0,
    "annual": 8760.0,
}

# ---------------------------------------------------------------------------
# Internal calculation engine
# ---------------------------------------------------------------------------

def _coalesce(v: Optional[float]) -> float:
    """None → 0.0.  Follows is-not-None discipline: absence contributes $0,
    not a fallback default rate.  See api/routes/runs.py:194–200 and
    runtime/solar_sim.py:116–124 (0.0 is a valid physical value, not falsy)."""
    return v if v is not None else 0.0


def _compute_proforma(
    tick_dicts: list[dict],
    profile: EconomicProfile,
    tenant_rates: list[EconomicProfileTenantRate],
    period: str,
) -> dict:
    """Core §30.5 margin contribution calculation.

    Returns a dict matching ProformaResponse shape (serialisable to JSON).
    All monetary values are in USD.

    Per-tenant MWh approximation disclosure (MC-10):
    Derived by summing instantaneous per-job est_draw_mw × dt_h from
    active_jobs_detail, grouped by tenant_id.  This is NOT metered;
    it is an approximation from instantaneous draw estimates.  The report
    must disclose this (enforced in AC-4.4 / AC-4.7).

    Session-scope limitation (MC-11):
    tick_dicts must come from the current server process.  The caller
    is responsible for handling 410/409 before calling this function.
    """
    target_hours = _PERIOD_HOURS.get(period, 730.0)

    # ── Run duration from tick data (AC-3.2: use actual, not assumed constant) ──
    if not tick_dicts:
        run_duration_hours = 0.0
    else:
        run_duration_hours = tick_dicts[-1].get("sim_time_seconds", 0.0) / 3600.0

    scale_factor = (
        target_hours / run_duration_hours if run_duration_hours > 0.0 else 1.0
    )

    # ── Cost rates: None → 0.0, never a fallback default ──────────────────
    r_grid = _coalesce(profile.grid_peak_rate_per_mwh)  # MVP: peak rate for all imports
    r_turb_fuel = _coalesce(profile.turbine_fuel_per_mwh)
    r_turb_capex = _coalesce(profile.turbine_capex_per_mwh)
    r_bess_marginal = _coalesce(profile.bess_marginal_per_mwh)
    r_bess_capex = _coalesce(profile.bess_capex_per_mwh)
    r_solar_capex = _coalesce(profile.solar_capex_per_mwh)
    r_curtail = _coalesce(profile.curtailment_per_mwh)

    # ── Per-tenant MWh accumulators ────────────────────────────────────────
    known_tids = {r.tenant_id for r in tenant_rates}
    tenant_mwh: dict[str, float] = {tid: 0.0 for tid in known_tids}

    # ── Site-level cost accumulators ───────────────────────────────────────
    total_energy_cogs = 0.0   # grid import + turbine fuel + BESS marginal
    total_capex_cost = 0.0    # turbine capex + BESS capex + solar capex
    total_curtailment_cost = 0.0

    for i, tick in enumerate(tick_dicts):
        # Per-tick duration in hours (AC-3.2: variable dt, not assumed constant)
        t_now = tick.get("sim_time_seconds", 0.0)
        t_prev = tick_dicts[i - 1].get("sim_time_seconds", 0.0) if i > 0 else 0.0
        dt_h = (t_now - t_prev) / 3600.0
        if dt_h <= 0.0:
            continue  # degenerate or duplicate tick — skip

        # Per-tenant MWh (MC-10 approximation): sum active job draws by tenant
        for job in tick.get("active_jobs_detail", []):
            tid = job.get("tenant_id", "")
            if tid in tenant_mwh:
                tenant_mwh[tid] += _coalesce(job.get("est_draw_mw")) * dt_h

        # COGS energy (variable costs): grid + turbine fuel + BESS marginal
        # grid_exchange_mw: positive = import (simulation_core.py:2089 convention)
        grid_import_mw = max(0.0, tick.get("grid_exchange_mw", 0.0))
        turb_mw = max(0.0, tick.get("turbine_output_mw", 0.0))
        # BESS: discharge is a cost (output > 0); charging is an asset reload
        bess_dispatch_mw = max(0.0, tick.get("bess_output_mw", 0.0))
        renewable_mw = max(0.0, tick.get("p_renewable_mw", 0.0))
        curtailed_mw = max(0.0, tick.get("p_renewable_curtailed_mw", 0.0))

        total_energy_cogs += (
            grid_import_mw * r_grid
            + turb_mw * r_turb_fuel
            + bess_dispatch_mw * r_bess_marginal
        ) * dt_h

        # Fixed / capex costs: amortised capital against output
        total_capex_cost += (
            turb_mw * r_turb_capex
            + bess_dispatch_mw * r_bess_capex
            + renewable_mw * r_solar_capex
        ) * dt_h

        total_curtailment_cost += curtailed_mw * r_curtail * dt_h

    # ── Apply period scale factor (MC-1: repeat-and-scale) ────────────────
    for tid in tenant_mwh:
        tenant_mwh[tid] *= scale_factor
    total_energy_cogs *= scale_factor
    total_capex_cost *= scale_factor
    total_curtailment_cost *= scale_factor

    total_usage_mwh = sum(tenant_mwh.values())

    # ── Per-tenant revenue + allocated costs (§30.5 formulas) ─────────────
    tenant_rows = []
    for rate in sorted(tenant_rates, key=lambda r: r.tenant_id):
        tid = rate.tenant_id
        usage = tenant_mwh.get(tid, 0.0)

        # §30.5 allocation formulas
        within_alloc = min(usage, rate.contracted_allocation)
        over_alloc = max(0.0, usage - rate.contracted_allocation)

        # TC-MC-9: tenant with no overage_rate bills flat (no error state)
        eff_overage_rate = (
            rate.overage_rate if rate.overage_rate is not None else rate.base_rate
        )

        revenue_within = within_alloc * rate.base_rate
        revenue_over = over_alloc * eff_overage_rate
        revenue = revenue_within + revenue_over

        # Allocate pooled COGS by metered-usage weighting (MC-7 proxy)
        weight = usage / total_usage_mwh if total_usage_mwh > 0.0 else 0.0
        alloc_cogs = total_energy_cogs * weight
        alloc_fixed = total_capex_cost * weight

        margin_contribution = revenue - alloc_cogs - alloc_fixed
        margin_pct = (margin_contribution / revenue * 100.0) if revenue > 0.0 else 0.0

        tenant_rows.append(
            {
                "tenant_id": tid,
                "billing_basis": rate.billing_basis,
                "usage_mwh": round(usage, 4),
                "contracted_allocation": rate.contracted_allocation,
                "within_alloc": round(within_alloc, 4),
                "over_alloc": round(over_alloc, 4),
                "revenue": round(revenue, 2),
                "revenue_within_alloc": round(revenue_within, 2),
                "revenue_over_alloc": round(revenue_over, 2),
                "allocated_cogs": round(alloc_cogs, 2),
                "allocated_fixed_cost": round(alloc_fixed, 2),
                "margin_contribution": round(margin_contribution, 2),
                "margin_pct": round(margin_pct, 2),
                "over_alloc_flag": over_alloc > 0.0,
                "usage_weight": round(weight, 6),
            }
        )

    total_revenue = sum(r["revenue"] for r in tenant_rows)
    total_margin = (
        total_revenue
        - total_energy_cogs
        - total_capex_cost
        - total_curtailment_cost
    )
    total_margin_pct = (
        total_margin / total_revenue * 100.0 if total_revenue > 0.0 else 0.0
    )
    proposed_here = json.loads(profile.proposed_here_fields or "[]")

    return {
        "profile_id": profile.id,
        "profile_name": profile.name,
        "period": period,
        "scale_factor": round(scale_factor, 4),
        "run_duration_hours": round(run_duration_hours, 4),
        "target_hours": target_hours,
        "proposed_here_fields": proposed_here,
        "proposed_here_count": len(proposed_here),
        "tenant_rows": tenant_rows,
        "total_revenue": round(total_revenue, 2),
        "total_energy_cogs": round(total_energy_cogs, 2),
        "total_capex_cost": round(total_capex_cost, 2),
        "total_curtailment_cost": round(total_curtailment_cost, 2),
        "total_margin_contribution": round(total_margin, 2),
        "total_margin_pct": round(total_margin_pct, 2),
        # MC-10 + MC-11 metadata (must be present in every response per AC-4.4)
        "disclosure_tenant_mwh_is_approx": True,
        "disclosure_session_scoped": True,
    }


# ---------------------------------------------------------------------------
# CRUD — CREATE
# ---------------------------------------------------------------------------

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_economic_profile(
    body: dict,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Create a new Economic Profile and its tenant rate rows.

    Body shape:
      name: str
      grid_peak_rate_per_mwh?: float
      grid_offpeak_rate_per_mwh?: float
      turbine_fuel_per_mwh?: float
      turbine_capex_per_mwh?: float
      bess_marginal_per_mwh?: float
      bess_capex_per_mwh?: float
      solar_capex_per_mwh?: float
      curtailment_per_mwh?: float
      proposed_here_fields?: list[str]
      tenant_rates?: list[{tenant_id, billing_basis, base_rate,
                            contracted_allocation, overage_rate?, sla_credit?}]
    """
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    profile_id = str(uuid.uuid4())
    profile = EconomicProfile(
        id=profile_id,
        site_id=body.get("site_id"),
        name=name,
        created_at=datetime.now(timezone.utc),
        grid_peak_rate_per_mwh=body.get("grid_peak_rate_per_mwh"),
        grid_offpeak_rate_per_mwh=body.get("grid_offpeak_rate_per_mwh"),
        turbine_fuel_per_mwh=body.get("turbine_fuel_per_mwh"),
        turbine_capex_per_mwh=body.get("turbine_capex_per_mwh"),
        bess_marginal_per_mwh=body.get("bess_marginal_per_mwh"),
        bess_capex_per_mwh=body.get("bess_capex_per_mwh"),
        solar_capex_per_mwh=body.get("solar_capex_per_mwh"),
        curtailment_per_mwh=body.get("curtailment_per_mwh"),
        proposed_here_fields=json.dumps(body.get("proposed_here_fields", [])),
    )
    db.add(profile)

    for tr_body in body.get("tenant_rates", []):
        tr = EconomicProfileTenantRate(
            economic_profile_id=profile_id,
            tenant_id=tr_body["tenant_id"],
            billing_basis=tr_body.get("billing_basis", "per_mwh_consumed"),
            base_rate=float(tr_body.get("base_rate", 0.0)),
            contracted_allocation=float(tr_body.get("contracted_allocation", 0.0)),
            overage_rate=tr_body.get("overage_rate"),
            sla_credit=tr_body.get("sla_credit"),
        )
        db.add(tr)

    await db.commit()
    await db.refresh(profile)
    return {"profile_id": profile.id, "name": profile.name}


# ---------------------------------------------------------------------------
# CRUD — LIST
# ---------------------------------------------------------------------------

@router.get("")
async def list_economic_profiles(
    db: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    """List all Economic Profiles (summary — no tenant rates)."""
    result = await db.execute(
        select(EconomicProfile).order_by(EconomicProfile.created_at.desc())
    )
    profiles = result.scalars().all()
    return [
        {
            "profile_id": p.id,
            "name": p.name,
            "created_at": p.created_at.isoformat(),
            "proposed_here_count": len(json.loads(p.proposed_here_fields or "[]")),
        }
        for p in profiles
    ]


# ---------------------------------------------------------------------------
# CRUD — GET DETAIL
# ---------------------------------------------------------------------------

@router.get("/{profile_id}")
async def get_economic_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Return full Economic Profile including tenant rate rows."""
    profile = await db.get(EconomicProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id!r} not found")

    rates_result = await db.execute(
        select(EconomicProfileTenantRate).where(
            EconomicProfileTenantRate.economic_profile_id == profile_id
        )
    )
    rates = rates_result.scalars().all()

    return {
        "profile_id": profile.id,
        "name": profile.name,
        "created_at": profile.created_at.isoformat(),
        "grid_peak_rate_per_mwh": profile.grid_peak_rate_per_mwh,
        "grid_offpeak_rate_per_mwh": profile.grid_offpeak_rate_per_mwh,
        "turbine_fuel_per_mwh": profile.turbine_fuel_per_mwh,
        "turbine_capex_per_mwh": profile.turbine_capex_per_mwh,
        "bess_marginal_per_mwh": profile.bess_marginal_per_mwh,
        "bess_capex_per_mwh": profile.bess_capex_per_mwh,
        "solar_capex_per_mwh": profile.solar_capex_per_mwh,
        "curtailment_per_mwh": profile.curtailment_per_mwh,
        "proposed_here_fields": json.loads(profile.proposed_here_fields or "[]"),
        "tenant_rates": [
            {
                "id": r.id,
                "tenant_id": r.tenant_id,
                "billing_basis": r.billing_basis,
                "base_rate": r.base_rate,
                "contracted_allocation": r.contracted_allocation,
                "overage_rate": r.overage_rate,
                "sla_credit": r.sla_credit,
            }
            for r in sorted(rates, key=lambda x: x.tenant_id)
        ],
    }


# ---------------------------------------------------------------------------
# CRUD — UPDATE
# ---------------------------------------------------------------------------

@router.put("/{profile_id}")
async def update_economic_profile(
    profile_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Replace an Economic Profile's cost fields and tenant rates."""
    profile = await db.get(EconomicProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id!r} not found")

    name = body.get("name", "").strip()
    if name:
        profile.name = name

    # is-not-None discipline: only update fields that are explicitly present in body
    _FLOAT_FIELDS = [
        "grid_peak_rate_per_mwh",
        "grid_offpeak_rate_per_mwh",
        "turbine_fuel_per_mwh",
        "turbine_capex_per_mwh",
        "bess_marginal_per_mwh",
        "bess_capex_per_mwh",
        "solar_capex_per_mwh",
        "curtailment_per_mwh",
    ]
    for field in _FLOAT_FIELDS:
        if field in body:
            setattr(profile, field, body[field])  # may be None (clearing the field)

    if "proposed_here_fields" in body:
        profile.proposed_here_fields = json.dumps(body["proposed_here_fields"])

    # Replace tenant rates if provided
    if "tenant_rates" in body:
        await db.execute(
            sa_delete(EconomicProfileTenantRate).where(
                EconomicProfileTenantRate.economic_profile_id == profile_id
            )
        )
        for tr_body in body["tenant_rates"]:
            tr = EconomicProfileTenantRate(
                economic_profile_id=profile_id,
                tenant_id=tr_body["tenant_id"],
                billing_basis=tr_body.get("billing_basis", "per_mwh_consumed"),
                base_rate=float(tr_body.get("base_rate", 0.0)),
                contracted_allocation=float(tr_body.get("contracted_allocation", 0.0)),
                overage_rate=tr_body.get("overage_rate"),
                sla_credit=tr_body.get("sla_credit"),
            )
            db.add(tr)

    await db.commit()
    return {"profile_id": profile.id, "name": profile.name}


# ---------------------------------------------------------------------------
# CRUD — DELETE
# ---------------------------------------------------------------------------

@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_economic_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> None:
    profile = await db.get(EconomicProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id!r} not found")
    await db.execute(
        sa_delete(EconomicProfileTenantRate).where(
            EconomicProfileTenantRate.economic_profile_id == profile_id
        )
    )
    await db.delete(profile)
    await db.commit()


# ---------------------------------------------------------------------------
# CALCULATE — Proforma (AC-3.1: 410/409 handled explicitly)
# ---------------------------------------------------------------------------

@router.get("/{profile_id}/proforma")
async def get_proforma(
    profile_id: str,
    run_id: str,
    period: str = "monthly",
    db: AsyncSession = Depends(get_db_session),
    manager: RunManager = Depends(_run_manager),
) -> dict:
    """Compute the Margin Contribution Proforma for a completed run.

    AC-3.1: If the run's tick data is gone (server restarted since the run
    completed), returns a structured error with operator-facing message rather
    than crashing or returning a silently empty report.

    MC-11: Data is session-scoped.  Caller should display the session-scope
    limitation notice alongside the report.
    """
    if period not in _PERIOD_HOURS:
        raise HTTPException(
            status_code=400,
            detail=f"period must be one of: {list(_PERIOD_HOURS.keys())}",
        )

    # Load profile
    profile = await db.get(EconomicProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id!r} not found")

    rates_result = await db.execute(
        select(EconomicProfileTenantRate).where(
            EconomicProfileTenantRate.economic_profile_id == profile_id
        )
    )
    tenant_rates = list(rates_result.scalars().all())

    # AC-3.1: check for still-active run (409) first
    if manager.get_context(run_id) is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Run {run_id!r} is still active — Margin Contribution can only be "
                "generated after the run completes."
            ),
        )

    # AC-3.1: check for completed run in this session
    completed = manager.get_completed(run_id)
    if completed is None:
        # Run either never existed or was from a previous server process (MC-11)
        raise HTTPException(
            status_code=410,
            detail=(
                f"Run {run_id!r} data is no longer available — the server may have "
                "restarted since this scenario was run. Re-run the scenario to "
                "generate a Margin Contribution report. (MC-11: session-scoped "
                "tick data)"
            ),
        )

    tick_dicts = completed.tick_dicts
    result = _compute_proforma(tick_dicts, profile, tenant_rates, period)
    result["run_id"] = run_id
    # Attempt to get scenario name from completed run
    try:
        result["scenario_name"] = completed.verdict.scenario_name if completed.verdict else run_id
    except AttributeError:
        result["scenario_name"] = run_id
    return result


# ---------------------------------------------------------------------------
# EXPORT — CSV (AC-4.7: per-tenant table + aggregate row; AC-4.4: disclaimers)
# ---------------------------------------------------------------------------

@router.get("/{profile_id}/proforma/export")
async def export_proforma_csv(
    profile_id: str,
    run_id: str,
    period: str = "monthly",
    db: AsyncSession = Depends(get_db_session),
    manager: RunManager = Depends(_run_manager),
) -> StreamingResponse:
    """Export the Margin Contribution Proforma as CSV.

    Follows the Blob/download pattern from RunControlBar.tsx:27–74.
    CSV includes per-tenant rows + aggregate row + disclaimer rows (AC-4.4/AC-4.7).
    """
    # Reuse the proforma calculation (calls the same validation logic)
    proforma_resp = await get_proforma(
        profile_id=profile_id,
        run_id=run_id,
        period=period,
        db=db,
        manager=manager,
    )

    buf = io.StringIO()
    writer = csv.writer(buf)

    # Header metadata
    writer.writerow(["# GridSignal Margin Contribution Proforma"])
    writer.writerow(["# Run ID", proforma_resp.get("run_id", run_id)])
    writer.writerow(["# Scenario", proforma_resp.get("scenario_name", "")])
    writer.writerow(["# Economic Profile", proforma_resp.get("profile_name", "")])
    writer.writerow(["# Period", proforma_resp.get("period", period).capitalize()])
    writer.writerow(
        [
            "# Scale factor",
            f"{proforma_resp.get('scale_factor', 1.0):.4f}x "
            f"(run={proforma_resp.get('run_duration_hours',0):.2f}h → "
            f"target={proforma_resp.get('target_hours',730):.0f}h)",
        ]
    )
    writer.writerow([])

    # Per-tenant table
    writer.writerow(
        [
            "Tenant",
            "Billing Basis",
            "Usage MWh (approx)",
            "Contracted Allocation",
            "Within Alloc MWh",
            "Over Alloc MWh",
            "Revenue ($)",
            "Revenue Within Alloc ($)",
            "Revenue Overage ($)",
            "Allocated COGS ($)",
            "Allocated Fixed Cost ($)",
            "Margin Contribution ($)",
            "Margin %",
        ]
    )
    for row in proforma_resp.get("tenant_rows", []):
        writer.writerow(
            [
                row["tenant_id"],
                row["billing_basis"],
                f"{row['usage_mwh']:.4f}",
                f"{row['contracted_allocation']:.4f}",
                f"{row['within_alloc']:.4f}",
                f"{row['over_alloc']:.4f}",
                f"{row['revenue']:.2f}",
                f"{row['revenue_within_alloc']:.2f}",
                f"{row['revenue_over_alloc']:.2f}",
                f"{row['allocated_cogs']:.2f}",
                f"{row['allocated_fixed_cost']:.2f}",
                f"{row['margin_contribution']:.2f}",
                f"{row['margin_pct']:.2f}%",
            ]
        )

    # Aggregate row (AC-4.7)
    writer.writerow(
        [
            "AGGREGATE",
            "",
            "",
            "",
            "",
            "",
            f"{proforma_resp.get('total_revenue', 0):.2f}",
            "",
            "",
            f"{proforma_resp.get('total_energy_cogs', 0):.2f}",
            f"{proforma_resp.get('total_capex_cost', 0):.2f}",
            f"{proforma_resp.get('total_margin_contribution', 0):.2f}",
            f"{proforma_resp.get('total_margin_pct', 0):.2f}%",
        ]
    )

    writer.writerow([])

    # Disclaimers (AC-4.4: operational-margin scope + MC-10 approximation)
    writer.writerow(
        [
            "# DISCLAIMER: This is an operational energy margin — revenue less "
            "energy COGS, amortised energy-asset capital, and curtailment cost. "
            "It excludes labor, insurance, property tax, non-energy G&A, interest, "
            "and depreciation outside the energy-asset line."
        ]
    )
    writer.writerow(
        [
            "# MC-10: Per-tenant MWh figures are approximations derived from "
            "instantaneous per-job estimated draw (est_draw_mw), not metered "
            "readings. They should not be used for billing without independent validation."
        ]
    )
    writer.writerow(
        [
            "# MC-11: This report was generated from in-session tick data. "
            "A server restart between the scenario run and this export would "
            "have returned an error instead."
        ]
    )

    buf.seek(0)
    filename = f"margin-contribution-{run_id}-{period}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
