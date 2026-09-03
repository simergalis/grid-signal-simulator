"""
tests/test_margin_contribution.py — Margin Contribution Tool unit tests (§30).

Test plan (from T1 implementation prompt):
  TC-MC-1  COGS formula: grid import only when grid_exchange_mw > 0
  TC-MC-2  COGS formula: turbine fuel cost proportional to turbine_output_mw
  TC-MC-3  COGS formula: BESS marginal cost on dispatch only (not charge)
  TC-MC-4  Per-tenant MWh: summed from active_jobs_detail, grouped by tenant_id
  TC-MC-5  Period scaling: scale_factor = target_hours / run_duration_hours
  TC-MC-6  Revenue: within_alloc × base_rate + over_alloc × overage_rate
  TC-MC-7  Pooled COGS allocation: by usage_weight (tenant_mwh / total_mwh)
  TC-MC-8  Aggregate margin: total_revenue − total_energy_cogs − total_capex_cost
  TC-MC-9  Tenant with no overage_rate: bills at base_rate (no error, no crash)
  TC-MC-10 Determinism: same inputs → identical float output (SHA-256 hash match)
  TC-MC-11 dt_s variable: uses sim_time_seconds delta, not assumed constant
  TC-MC-12 410 path: get_proforma raises 410 when run not in manager
  TC-MC-13 409 path: get_proforma raises 409 when run is still active

Follows test_step13_agents.py:151–180 for determinism test pattern.
"""

from __future__ import annotations

import hashlib
import json
import types
from typing import Optional
from unittest.mock import MagicMock

import pytest

from api.routes.economic_profiles import _compute_proforma, _PERIOD_HOURS

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_profile(
    grid_peak: Optional[float] = None,
    turb_fuel: Optional[float] = None,
    turb_capex: Optional[float] = None,
    bess_marginal: Optional[float] = None,
    bess_capex: Optional[float] = None,
    solar_capex: Optional[float] = None,
    curtail: Optional[float] = None,
) -> MagicMock:
    p = MagicMock()
    p.id = "test-profile-id"
    p.name = "Test Profile"
    p.grid_peak_rate_per_mwh = grid_peak
    p.grid_offpeak_rate_per_mwh = None
    p.turbine_fuel_per_mwh = turb_fuel
    p.turbine_capex_per_mwh = turb_capex
    p.bess_marginal_per_mwh = bess_marginal
    p.bess_capex_per_mwh = bess_capex
    p.solar_capex_per_mwh = solar_capex
    p.curtailment_per_mwh = curtail
    p.proposed_here_fields = "[]"
    return p


def _make_rate(
    tenant_id: str,
    base_rate: float,
    contracted_allocation: float,
    overage_rate: Optional[float] = None,
    billing_basis: str = "per_mwh_consumed",
) -> MagicMock:
    r = MagicMock()
    r.tenant_id = tenant_id
    r.billing_basis = billing_basis
    r.base_rate = base_rate
    r.contracted_allocation = contracted_allocation
    r.overage_rate = overage_rate
    r.sla_credit = None
    return r


def _make_tick(
    sim_time_seconds: float,
    grid_exchange_mw: float = 0.0,
    turbine_output_mw: float = 0.0,
    bess_output_mw: float = 0.0,
    p_renewable_mw: float = 0.0,
    p_renewable_curtailed_mw: float = 0.0,
    active_jobs_detail: Optional[list] = None,
) -> dict:
    return {
        "sim_time_seconds": sim_time_seconds,
        "grid_exchange_mw": grid_exchange_mw,
        "turbine_output_mw": turbine_output_mw,
        "bess_output_mw": bess_output_mw,
        "p_renewable_mw": p_renewable_mw,
        "p_renewable_curtailed_mw": p_renewable_curtailed_mw,
        "active_jobs_detail": active_jobs_detail or [],
    }


# Two-tick run: each tick is 1800 s (0.5 h); total 1 h = 1/730 of a month.
_SIMPLE_TICKS = [
    _make_tick(
        sim_time_seconds=1800,
        grid_exchange_mw=5.0,   # positive = import (simulation_core.py:2089)
        turbine_output_mw=10.0,
        bess_output_mw=2.0,
        p_renewable_mw=3.0,
        active_jobs_detail=[
            {"tenant_id": "A", "est_draw_mw": 8.0},
            {"tenant_id": "B", "est_draw_mw": 6.0},
            {"tenant_id": "C", "est_draw_mw": 1.0},
        ],
    ),
    _make_tick(
        sim_time_seconds=3600,
        grid_exchange_mw=-1.0,  # negative = export — should NOT contribute to COGS
        turbine_output_mw=12.0,
        bess_output_mw=-3.0,   # negative = charge — should NOT contribute to BESS COGS
        p_renewable_mw=4.0,
        active_jobs_detail=[
            {"tenant_id": "A", "est_draw_mw": 7.0},
            {"tenant_id": "B", "est_draw_mw": 5.0},
            {"tenant_id": "C", "est_draw_mw": 2.0},
        ],
    ),
]

# ---------------------------------------------------------------------------
# TC-MC-1: COGS grid — import only when grid_exchange_mw > 0
# ---------------------------------------------------------------------------

def test_cogs_grid_import_only():
    """TC-MC-1: negative grid_exchange_mw (export) must contribute zero to COGS."""
    profile = _make_profile(grid_peak=100.0)
    rates = [_make_rate("A", 10.0, 1000.0)]
    ticks = [
        _make_tick(sim_time_seconds=3600, grid_exchange_mw=-5.0),  # export
    ]
    result = _compute_proforma(ticks, profile, rates, "monthly")
    assert result["total_energy_cogs"] == pytest.approx(0.0, abs=1e-6), (
        "Negative grid_exchange_mw (export) must not contribute to energy COGS"
    )


def test_cogs_grid_positive_import():
    """TC-MC-1b: positive grid_exchange_mw (import) must contribute to COGS."""
    profile = _make_profile(grid_peak=80.0)  # $80/MWh
    rates = [_make_rate("A", 10.0, 1000.0)]
    # 1-hour tick with 10 MW import → 10 MWh → $800, scaled by monthly factor
    ticks = [_make_tick(sim_time_seconds=3600, grid_exchange_mw=10.0)]
    result = _compute_proforma(ticks, profile, rates, "monthly")
    # raw COGS = 10 MW × 1 h × $80 = $800; scaled × 730h = $584,000
    expected_scaled = 800.0 * 730.0
    assert result["total_energy_cogs"] == pytest.approx(expected_scaled, rel=1e-5)


# ---------------------------------------------------------------------------
# TC-MC-2: Turbine fuel cost proportional to turbine_output_mw
# ---------------------------------------------------------------------------

def test_cogs_turbine_fuel():
    """TC-MC-2: turbine fuel cost = turbine_output_mw × rate × dt_h, scaled."""
    profile = _make_profile(turb_fuel=50.0)  # $50/MWh
    rates = [_make_rate("A", 10.0, 1000.0)]
    # 1-hour tick, 8 MW → 8 MWh → $400 raw → × 730 scaled
    ticks = [_make_tick(sim_time_seconds=3600, turbine_output_mw=8.0)]
    result = _compute_proforma(ticks, profile, rates, "monthly")
    expected_scaled = 8.0 * 1.0 * 50.0 * 730.0
    assert result["total_energy_cogs"] == pytest.approx(expected_scaled, rel=1e-5)


# ---------------------------------------------------------------------------
# TC-MC-3: BESS marginal cost on dispatch only (not charging)
# ---------------------------------------------------------------------------

def test_cogs_bess_dispatch_only():
    """TC-MC-3: negative bess_output_mw (charging) must not contribute to COGS."""
    profile = _make_profile(bess_marginal=20.0)
    rates = [_make_rate("A", 10.0, 1000.0)]
    # One dispatch tick (positive) + one charge tick (negative)
    ticks = [
        _make_tick(sim_time_seconds=3600, bess_output_mw=4.0),   # dispatch
        _make_tick(sim_time_seconds=7200, bess_output_mw=-4.0),   # charge — not a cost
    ]
    result = _compute_proforma(ticks, profile, rates, "monthly")
    # raw: 4 MW × 1 h × $20 = $80 (only tick 0 contributes); scaled × (730 / 2)
    expected_scaled = 80.0 * (730.0 / 2.0)
    assert result["total_energy_cogs"] == pytest.approx(expected_scaled, rel=1e-5)


# ---------------------------------------------------------------------------
# TC-MC-4: Per-tenant MWh summed from active_jobs_detail
# ---------------------------------------------------------------------------

def test_per_tenant_mwh():
    """TC-MC-4: per-tenant MWh must sum est_draw_mw × dt_h per tick, by tenant_id."""
    profile = _make_profile()
    rates = [
        _make_rate("A", 100.0, 10000.0),
        _make_rate("B", 90.0, 10000.0),
    ]
    # Two 1-hour ticks
    ticks = [
        _make_tick(
            sim_time_seconds=3600,
            active_jobs_detail=[
                {"tenant_id": "A", "est_draw_mw": 10.0},
                {"tenant_id": "B", "est_draw_mw": 5.0},
            ],
        ),
        _make_tick(
            sim_time_seconds=7200,
            active_jobs_detail=[
                {"tenant_id": "A", "est_draw_mw": 6.0},
                {"tenant_id": "B", "est_draw_mw": 8.0},
            ],
        ),
    ]
    result = _compute_proforma(ticks, profile, rates, "monthly")
    # raw: A = (10+6) × 1h = 16 MWh; B = (5+8) × 1h = 13 MWh
    # scaled × (730 / 2) = × 365
    a_row = next(r for r in result["tenant_rows"] if r["tenant_id"] == "A")
    b_row = next(r for r in result["tenant_rows"] if r["tenant_id"] == "B")
    assert a_row["usage_mwh"] == pytest.approx(16.0 * 365.0, rel=1e-5)
    assert b_row["usage_mwh"] == pytest.approx(13.0 * 365.0, rel=1e-5)


# ---------------------------------------------------------------------------
# TC-MC-5: Period scaling = target_hours / run_duration_hours
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("period,target", list(_PERIOD_HOURS.items()))
def test_period_scaling(period: str, target: float):
    """TC-MC-5: scale_factor = target_hours / run_duration_hours for all periods."""
    profile = _make_profile(grid_peak=10.0)
    rates = [_make_rate("A", 5.0, 999.0)]
    # 2-hour run
    ticks = [
        _make_tick(sim_time_seconds=3600, grid_exchange_mw=1.0),
        _make_tick(sim_time_seconds=7200, grid_exchange_mw=1.0),
    ]
    result = _compute_proforma(ticks, profile, rates, period)
    assert result["scale_factor"] == pytest.approx(target / 2.0, rel=1e-5)
    assert result["run_duration_hours"] == pytest.approx(2.0, rel=1e-5)
    assert result["target_hours"] == pytest.approx(target, rel=1e-5)


# ---------------------------------------------------------------------------
# TC-MC-6: Revenue = within_alloc × base_rate + over_alloc × overage_rate
# ---------------------------------------------------------------------------

def test_revenue_within_and_overage():
    """TC-MC-6: revenue split correctly between within-alloc and overage tiers."""
    # usage: 10 MWh raw × 730 scale = 7300 MWh
    # contracted_allocation: 5000 MWh
    # within_alloc = 5000; over_alloc = 2300
    profile = _make_profile()
    rates = [
        _make_rate("A", base_rate=80.0, contracted_allocation=5000.0, overage_rate=120.0),
    ]
    ticks = [
        _make_tick(
            sim_time_seconds=3600,
            active_jobs_detail=[{"tenant_id": "A", "est_draw_mw": 10.0}],
        ),
    ]
    result = _compute_proforma(ticks, profile, rates, "monthly")  # × 730
    row = result["tenant_rows"][0]
    assert row["within_alloc"] == pytest.approx(5000.0, rel=1e-4)
    assert row["over_alloc"] == pytest.approx(7300.0 - 5000.0, rel=1e-4)
    assert row["revenue_within_alloc"] == pytest.approx(5000.0 * 80.0, rel=1e-4)
    assert row["revenue_over_alloc"] == pytest.approx(2300.0 * 120.0, rel=1e-4)
    assert row["over_alloc_flag"] is True


def test_revenue_no_overage():
    """TC-MC-6b: usage within contracted_allocation → zero overage revenue."""
    profile = _make_profile()
    rates = [_make_rate("A", base_rate=80.0, contracted_allocation=99_999.0)]
    ticks = [
        _make_tick(
            sim_time_seconds=3600,
            active_jobs_detail=[{"tenant_id": "A", "est_draw_mw": 5.0}],
        ),
    ]
    result = _compute_proforma(ticks, profile, rates, "monthly")
    row = result["tenant_rows"][0]
    assert row["over_alloc"] == pytest.approx(0.0, abs=1e-6)
    assert row["revenue_over_alloc"] == pytest.approx(0.0, abs=1e-6)
    assert row["over_alloc_flag"] is False


# ---------------------------------------------------------------------------
# TC-MC-7: Pooled COGS allocated by usage_weight
# ---------------------------------------------------------------------------

def test_cogs_pooled_by_weight():
    """TC-MC-7: each tenant's allocated_cogs = total_cogs × (tenant_mwh / total_mwh)."""
    profile = _make_profile(grid_peak=100.0)  # only grid cost
    rates = [
        _make_rate("A", 50.0, 99_999.0),
        _make_rate("B", 50.0, 99_999.0),
    ]
    # Tenant A draws 3×, Tenant B draws 1× → weights 0.75 and 0.25
    ticks = [
        _make_tick(
            sim_time_seconds=3600,
            grid_exchange_mw=10.0,
            active_jobs_detail=[
                {"tenant_id": "A", "est_draw_mw": 6.0},
                {"tenant_id": "B", "est_draw_mw": 2.0},
            ],
        ),
    ]
    result = _compute_proforma(ticks, profile, rates, "monthly")
    a_row = next(r for r in result["tenant_rows"] if r["tenant_id"] == "A")
    b_row = next(r for r in result["tenant_rows"] if r["tenant_id"] == "B")
    assert a_row["usage_weight"] == pytest.approx(0.75, rel=1e-4)
    assert b_row["usage_weight"] == pytest.approx(0.25, rel=1e-4)
    total_cogs = result["total_energy_cogs"]
    assert a_row["allocated_cogs"] == pytest.approx(total_cogs * 0.75, rel=1e-4)
    assert b_row["allocated_cogs"] == pytest.approx(total_cogs * 0.25, rel=1e-4)


# ---------------------------------------------------------------------------
# TC-MC-8: Aggregate margin = total_revenue − energy_cogs − capex_cost
# ---------------------------------------------------------------------------

def test_aggregate_margin():
    """TC-MC-8: total_margin_contribution = revenue − energy_cogs − capex_cost − curtail."""
    profile = _make_profile(grid_peak=50.0, turb_capex=10.0)
    rates = [_make_rate("A", 200.0, 99_999.0)]
    ticks = [
        _make_tick(
            sim_time_seconds=3600,
            grid_exchange_mw=5.0,
            turbine_output_mw=3.0,
            active_jobs_detail=[{"tenant_id": "A", "est_draw_mw": 8.0}],
        ),
    ]
    result = _compute_proforma(ticks, profile, rates, "monthly")
    expected_margin = (
        result["total_revenue"]
        - result["total_energy_cogs"]
        - result["total_capex_cost"]
        - result["total_curtailment_cost"]
    )
    assert result["total_margin_contribution"] == pytest.approx(expected_margin, rel=1e-5)


# ---------------------------------------------------------------------------
# TC-MC-9: No overage_rate → flat billing, no error state
# ---------------------------------------------------------------------------

def test_no_overage_rate_flat_billing():
    """TC-MC-9: tenant with overage_rate=None bills all usage at base_rate (AC-2.5)."""
    profile = _make_profile()
    # 1000 MWh contracted; usage will be 7300 MWh (10 MW × 1 h × 730 scale)
    rates = [
        _make_rate("A", base_rate=70.0, contracted_allocation=1000.0, overage_rate=None),
    ]
    ticks = [
        _make_tick(
            sim_time_seconds=3600,
            active_jobs_detail=[{"tenant_id": "A", "est_draw_mw": 10.0}],
        ),
    ]
    # Should NOT raise; overage bills at base_rate
    result = _compute_proforma(ticks, profile, rates, "monthly")
    row = result["tenant_rows"][0]
    assert row["over_alloc"] == pytest.approx(7300.0 - 1000.0, rel=1e-4)
    # Revenue for overage at base_rate (not a higher overage rate)
    assert row["revenue_over_alloc"] == pytest.approx(
        (7300.0 - 1000.0) * 70.0, rel=1e-4
    ), "Overage revenue must use base_rate when overage_rate is None"


# ---------------------------------------------------------------------------
# TC-MC-10: Determinism — SHA-256 of proforma output identical for same inputs
# ---------------------------------------------------------------------------

def test_determinism():
    """TC-MC-10: identical tick_dicts, profile, rates, period → identical SHA-256 hash.

    Follows test_step13_agents.py:151–180 pattern: serialise result to canonical
    JSON, hash it, call twice, assert equal.
    """
    profile = _make_profile(grid_peak=60.0, turb_fuel=40.0, turb_capex=12.0, bess_marginal=8.0)
    rates = [
        _make_rate("A", 90.0, 5000.0, overage_rate=130.0),
        _make_rate("B", 85.0, 3500.0),
        _make_rate("C", 95.0, 2000.0, overage_rate=150.0),
    ]

    def _hash_result() -> str:
        result = _compute_proforma(_SIMPLE_TICKS, profile, rates, "quarterly")
        canonical = json.dumps(result, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(canonical.encode()).hexdigest()

    h1 = _hash_result()
    h2 = _hash_result()
    assert h1 == h2, "Proforma output is not deterministic — float ordering or rounding is unstable"


# ---------------------------------------------------------------------------
# TC-MC-11: dt_s variable — per-tick duration from sim_time_seconds delta
# ---------------------------------------------------------------------------

def test_variable_dt_s():
    """TC-MC-11: COGS must use actual per-tick duration, not assumed constant dt."""
    profile = _make_profile(grid_peak=100.0)  # $100/MWh
    rates = [_make_rate("A", 10.0, 99_999.0)]
    # Tick 0: 0 → 1800 s (0.5 h) with 10 MW import → 5 MWh → $500
    # Tick 1: 1800 → 5400 s (1.0 h) with 10 MW import → 10 MWh → $1000
    # Total raw = $1500; run_duration = 5400 s = 1.5 h
    ticks = [
        _make_tick(sim_time_seconds=1800, grid_exchange_mw=10.0),
        _make_tick(sim_time_seconds=5400, grid_exchange_mw=10.0),
    ]
    result = _compute_proforma(ticks, profile, rates, "monthly")
    raw_cogs = 5.0 * 100.0 + 10.0 * 100.0  # $1500
    scale = 730.0 / 1.5
    assert result["total_energy_cogs"] == pytest.approx(raw_cogs * scale, rel=1e-5)


# ---------------------------------------------------------------------------
# TC-MC-12 / TC-MC-13: HTTP 410 / 409 paths (async route-level tests)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_proforma_410_when_run_not_found() -> None:
    """TC-MC-12: get_proforma must raise 410 when run not in RunManager."""
    from fastapi import HTTPException
    from api.routes.economic_profiles import get_proforma
    from sqlalchemy.ext.asyncio import AsyncSession

    # Minimal mock DB session that returns a profile from db.get()
    profile = _make_profile()
    rate = _make_rate("A", 50.0, 1000.0)

    mock_session = MagicMock(spec=AsyncSession)
    mock_session.get = MagicMock(return_value=_async(profile))

    mock_execute_result = MagicMock()
    mock_execute_result.scalars.return_value.all.return_value = [rate]
    mock_session.execute = MagicMock(return_value=_async(mock_execute_result))

    # RunManager that reports no active and no completed run
    mock_manager = MagicMock()
    mock_manager.get_context = MagicMock(return_value=None)
    mock_manager.get_completed = MagicMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await get_proforma(
            profile_id="test-profile-id",
            run_id="ghost-run-id",
            period="monthly",
            db=mock_session,  # type: ignore[arg-type]
            manager=mock_manager,
        )
    assert exc_info.value.status_code == 410


@pytest.mark.anyio
async def test_proforma_409_when_run_still_active() -> None:
    """TC-MC-13: get_proforma must raise 409 when run is still active."""
    from fastapi import HTTPException
    from api.routes.economic_profiles import get_proforma
    from sqlalchemy.ext.asyncio import AsyncSession

    profile = _make_profile()
    rate = _make_rate("A", 50.0, 1000.0)

    mock_session = MagicMock(spec=AsyncSession)
    mock_session.get = MagicMock(return_value=_async(profile))

    mock_execute_result = MagicMock()
    mock_execute_result.scalars.return_value.all.return_value = [rate]
    mock_session.execute = MagicMock(return_value=_async(mock_execute_result))

    # RunManager that reports an active (non-None) context
    mock_manager = MagicMock()
    mock_manager.get_context = MagicMock(return_value=object())  # truthy = still active

    with pytest.raises(HTTPException) as exc_info:
        await get_proforma(
            profile_id="test-profile-id",
            run_id="active-run-id",
            period="monthly",
            db=mock_session,  # type: ignore[arg-type]
            manager=mock_manager,
        )
    assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# Async helper (co-routine wrapper for MagicMock.return_value)
# ---------------------------------------------------------------------------

async def _async(value):
    return value
