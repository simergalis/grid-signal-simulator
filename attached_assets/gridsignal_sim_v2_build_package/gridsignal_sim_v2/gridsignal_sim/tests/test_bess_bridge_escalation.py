"""Focused coverage for the two BESS bridge early-warning conditions."""

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from runtime.run_manager import _apply_bess_bridge_escalation, _tick_result_to_dict
from runtime.scenario_factory import build_run_context_from_spec
from api.routes.runs import get_run_timeseries


ROOT = Path(__file__).resolve().parents[1]


def _context(name: str):
    spec = json.loads((ROOT / "config" / "scenarios" / name).read_text())
    return build_run_context_from_spec(f"test-{name}", spec)


def _observed_tick(ctx, *, t_s, bess_mw, turbine_mw=0.0, bridge_s=1000.0, available_mw=20.0):
    base = ctx.step()
    coverage = replace(
        base.contingency_coverage,
        bess_bridging_available_mw=available_mw,
    )
    return replace(
        base,
        sim_time_seconds=t_s,
        bess_output_mw=bess_mw,
        turbine_output_mw=turbine_mw,
        bess_bridging_seconds=bridge_s,
        contingency_coverage=coverage,
    )


def test_floor_uses_fifteen_percent_and_twice_anchor():
    ctx = _context("scenario-equinix-sj-1.json")
    tick = _observed_tick(ctx, t_s=5.0, bess_mw=0.0, available_mw=4.499)

    result = _apply_bess_bridge_escalation(ctx, tick)

    assert result.bess_bridging_floor_mw == pytest.approx(4.5)
    assert result.bess_escalation_active is True
    assert result.bess_escalation_reason == "bridging_floor"


def test_exact_floor_equality_does_not_escalate():
    ctx = _context("scenario-equinix-sj-1.json")
    tick = _observed_tick(ctx, t_s=5.0, bess_mw=0.0, available_mw=4.5)

    result = _apply_bess_bridge_escalation(ctx, tick)

    assert result.bess_bridging_floor_mw == pytest.approx(4.5)
    assert result.bess_escalation_active is False


def test_turbine_catchup_fires_on_sixth_five_second_tick():
    ctx = _context("scenario-kube-peak-overage.json")
    result = None
    for tick_no in range(1, 7):
        tick = _observed_tick(
            ctx,
            t_s=5.0 * tick_no,
            bess_mw=5.0,
            turbine_mw=0.0,
            bridge_s=1000.0,
            available_mw=17.0,
        )
        result = _apply_bess_bridge_escalation(ctx, tick)
        assert result.bess_escalation_active is (tick_no == 6)

    assert result is not None
    assert result.bess_discharge_sustained_s == pytest.approx(30.0)
    assert result.bess_escalation_reason == "turbine_catchup"


def test_converging_turbine_does_not_fire_rate_trigger():
    ctx = _context("scenario-kube-peak-overage.json")
    result = None
    for tick_no in range(1, 7):
        tick = _observed_tick(
            ctx,
            t_s=5.0 * tick_no,
            bess_mw=5.0,
            turbine_mw=float(tick_no),
            bridge_s=100.0,
            available_mw=17.0,
        )
        result = _apply_bess_bridge_escalation(ctx, tick)

    assert result is not None
    assert result.turbine_observed_ramp_mw_per_s == pytest.approx(0.2)
    assert result.turbine_estimated_time_to_close_s == pytest.approx(25.0)
    assert result.bess_escalation_active is False


def test_sj1_no_turbine_guard_never_starts_rate_timer():
    ctx = _context("scenario-equinix-sj-1.json")
    for tick_no in range(1, 9):
        tick = _observed_tick(
            ctx,
            t_s=5.0 * tick_no,
            bess_mw=10.0,
            bridge_s=1000.0,
            available_mw=29.0,
        )
        result = _apply_bess_bridge_escalation(ctx, tick)
        assert result.bess_discharge_sustained_s == 0.0
        assert result.bess_escalation_active is False


def test_material_discharge_break_resets_confirmation_window():
    ctx = _context("scenario-kube-peak-overage.json")
    for tick_no in range(1, 6):
        result = _apply_bess_bridge_escalation(
            ctx,
            _observed_tick(ctx, t_s=5.0 * tick_no, bess_mw=5.0, available_mw=17.0),
        )
    assert result.bess_discharge_sustained_s == 25.0

    result = _apply_bess_bridge_escalation(
        ctx,
        _observed_tick(ctx, t_s=30.0, bess_mw=0.5, available_mw=17.0),
    )
    assert result.bess_discharge_sustained_s == 0.0
    assert result.bess_escalation_active is False


def test_payload_contains_operator_evidence():
    ctx = _context("scenario-equinix-sj-1.json")
    result = _apply_bess_bridge_escalation(
        ctx,
        _observed_tick(ctx, t_s=5.0, bess_mw=0.0, available_mw=4.0),
    )
    payload = _tick_result_to_dict(result)

    assert payload["bess_escalation_active"] is True
    assert payload["bess_escalation_reason"] == "bridging_floor"
    assert payload["bess_bridging_floor_mw"] == pytest.approx(4.5)
    assert payload["bess_bridging_available_mw"] == pytest.approx(4.0)


@pytest.mark.asyncio
async def test_completed_timeseries_endpoint_keeps_escalation_evidence():
    ctx = _context("scenario-equinix-sj-1.json")
    result = _apply_bess_bridge_escalation(
        ctx,
        _observed_tick(ctx, t_s=5.0, bess_mw=0.0, available_mw=4.0),
    )
    payload = _tick_result_to_dict(result)
    completed = SimpleNamespace(
        tick_dicts=[payload],
        verdict=SimpleNamespace(gap_count=0),
    )

    class _Manager:
        def get_context(self, run_id):
            return None

        def get_completed(self, run_id):
            return completed

    response = await get_run_timeseries("test-run", manager=_Manager())
    row = response.rows[0]
    assert row.bess_escalation_active is True
    assert row.bess_escalation_reason == "bridging_floor"
    assert row.bess_bridging_available_mw == pytest.approx(4.0)
    assert row.bess_bridging_floor_mw == pytest.approx(4.5)
