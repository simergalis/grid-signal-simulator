"""Task #428 — total_edl_dispatch_cost_usd on CompletedRun and RunResultResponse.

Contract:
  - ctx.edl_sources is not None → non-null total (0.0 when no ticks retained)
  - ctx.edl_sources is None     → null total (headless / direct-job-id path)

Test groups:
  428-1  Accumulation logic — headless (edl_active=False) produces None.
  428-2  Accumulation logic — spec-path (edl_active=True) sums correctly.
  428-3  Accumulation logic — spec-path with zero ticks produces 0.0, not None.
  428-4  CompletedRun field exists with None default.
  428-5  RunResultResponse exposes the field; serialises correctly.
  428-6  verdict_json round-trip: total survives persist → DB-fallback restore.
  428-7  Integration: async _drive() run via RunManager sets the field correctly
         for both an EDL-active run and a headless run.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from runtime.run_manager import CompletedRun, RunManager, WebSocketHub
from runtime.scenario_factory import build_run_context
from runtime.verdict import VerdictResult
from api.schemas import RunResultResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_completed(total: float | None = None) -> CompletedRun:
    return CompletedRun(
        run_id="test-run",
        scenario_id="s1",
        scenario_name="Test",
        completed_at=datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc),
        verdict=VerdictResult(overall="PASS", tick_count=3, dropped_ticks=0, gap_count=0),
        tick_dicts=[],
        dropped_ticks=0,
        total_edl_dispatch_cost_usd=total,
    )


def _tick_dict(cost: float | None) -> dict:
    return {"tick_index": 0, "edl_dispatch_cost_usd": cost, "d4_balance_defect_mw": 0.0}


def _accumulate(tick_dicts: list[dict], *, edl_active: bool) -> float | None:
    """Replicate run_manager._drive() accumulation: nullability from edl_active."""
    if not edl_active:
        return None
    return round(
        sum((td.get("edl_dispatch_cost_usd") or 0.0) for td in tick_dicts),
        6,
    )


def _verdict_json_roundtrip(total: float | None) -> float | None:
    """Replicate verdict_json amendment + DB-fallback restoration."""
    import json
    base = {"overall": "PASS", "tick_count": 5, "dropped_ticks": 0,
            "gap_count": 0, "assertions": []}
    base["total_edl_dispatch_cost_usd"] = total
    return json.loads(json.dumps(base)).get("total_edl_dispatch_cost_usd")


async def _run_to_completion(manager: RunManager, ctx) -> CompletedRun | None:
    await manager.start_run(ctx)
    await manager._tasks[ctx.run_id]
    return manager.get_completed(ctx.run_id)


# ---------------------------------------------------------------------------
# 428-1: Headless (edl_active=False) → None
# ---------------------------------------------------------------------------

class TestTC428_1_HeadlessRunIsNone:
    def test_ticks_with_none_costs_produce_none(self):
        result = _accumulate(
            [_tick_dict(None), _tick_dict(None), _tick_dict(None)],
            edl_active=False,
        )
        assert result is None

    def test_empty_tick_list_with_headless_produces_none(self):
        result = _accumulate([], edl_active=False)
        assert result is None

    def test_ticks_with_costs_but_headless_produces_none(self):
        """When edl_sources is None, tick costs are ignored — result is always None."""
        result = _accumulate(
            [_tick_dict(5.0), _tick_dict(3.0)],
            edl_active=False,
        )
        assert result is None


# ---------------------------------------------------------------------------
# 428-2: Spec-path (edl_active=True) → Σ per-tick costs
# ---------------------------------------------------------------------------

class TestTC428_2_SpecPathSumCorrect:
    def test_sum_of_three_ticks(self):
        result = _accumulate(
            [_tick_dict(1.5), _tick_dict(2.25), _tick_dict(0.75)],
            edl_active=True,
        )
        assert result == pytest.approx(4.5, abs=1e-6)

    def test_single_tick(self):
        result = _accumulate([_tick_dict(7.123456)], edl_active=True)
        assert result == pytest.approx(7.123456, abs=1e-9)

    def test_none_ticks_treated_as_zero(self):
        """A tick whose edl_dispatch_cost_usd is None contributes 0.0, not skipped."""
        result = _accumulate(
            [_tick_dict(2.0), _tick_dict(None), _tick_dict(3.0)],
            edl_active=True,
        )
        assert result == pytest.approx(5.0, abs=1e-6)


# ---------------------------------------------------------------------------
# 428-3: Spec-path with zero retained ticks → 0.0, not None
# ---------------------------------------------------------------------------

class TestTC428_3_ZeroTicksWithEdlActive:
    def test_empty_tick_list_with_edl_active_gives_zero(self):
        """EDL wired but no retained ticks → 0.0, preserving EDL-active signal."""
        result = _accumulate([], edl_active=True)
        assert result is not None, "EDL active run must not return None for empty ticks"
        assert result == 0.0

    def test_all_none_costs_with_edl_active_gives_zero(self):
        """All ticks have null cost (e.g. dropped before costing) → 0.0."""
        result = _accumulate(
            [_tick_dict(None), _tick_dict(None)],
            edl_active=True,
        )
        assert result is not None
        assert result == 0.0


# ---------------------------------------------------------------------------
# 428-4: CompletedRun field contract
# ---------------------------------------------------------------------------

class TestTC428_4_CompletedRunField:
    def test_field_exists_with_none_default(self):
        completed = CompletedRun(
            run_id="r", scenario_id=None, scenario_name="X",
            completed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            verdict=VerdictResult(overall="INCONCLUSIVE", tick_count=0,
                                  dropped_ticks=0, gap_count=0),
            tick_dicts=[], dropped_ticks=0,
        )
        assert hasattr(completed, "total_edl_dispatch_cost_usd")
        assert completed.total_edl_dispatch_cost_usd is None

    def test_field_accepts_float(self):
        assert _make_completed(12.345).total_edl_dispatch_cost_usd == pytest.approx(12.345)

    def test_field_accepts_zero(self):
        assert _make_completed(0.0).total_edl_dispatch_cost_usd == 0.0

    def test_field_accepts_none(self):
        assert _make_completed(None).total_edl_dispatch_cost_usd is None


# ---------------------------------------------------------------------------
# 428-5: RunResultResponse exposes the field
# ---------------------------------------------------------------------------

class TestTC428_5_RunResultResponseField:
    def _resp(self, total: float | None) -> RunResultResponse:
        return RunResultResponse(
            run_id="r", scenario_id=None, scenario_name="X",
            completed_at="2026-08-15T12:00:00+00:00",
            overall="PASS", tick_count=3, dropped_ticks=0, gap_count=0,
            assertions=[],
            total_edl_dispatch_cost_usd=total,
        )

    def test_field_present_with_float(self):
        assert self._resp(9.876).total_edl_dispatch_cost_usd == pytest.approx(9.876)

    def test_field_present_with_none(self):
        assert self._resp(None).total_edl_dispatch_cost_usd is None

    def test_field_present_with_zero(self):
        resp = self._resp(0.0)
        assert resp.total_edl_dispatch_cost_usd is not None
        assert resp.total_edl_dispatch_cost_usd == 0.0

    def test_default_is_none_when_omitted(self):
        resp = RunResultResponse(
            run_id="r", scenario_id=None, scenario_name="X",
            completed_at="2026-08-15T12:00:00+00:00",
            overall="PASS", tick_count=0, dropped_ticks=0, gap_count=0,
            assertions=[],
        )
        assert resp.total_edl_dispatch_cost_usd is None

    def test_serialised_dict_includes_key_with_float(self):
        d = self._resp(3.14).model_dump()
        assert "total_edl_dispatch_cost_usd" in d
        assert d["total_edl_dispatch_cost_usd"] == pytest.approx(3.14)

    def test_serialised_dict_null_when_none(self):
        assert self._resp(None).model_dump()["total_edl_dispatch_cost_usd"] is None

    def test_serialised_dict_zero_when_zero(self):
        assert self._resp(0.0).model_dump()["total_edl_dispatch_cost_usd"] == 0.0


# ---------------------------------------------------------------------------
# 428-6: verdict_json round-trip (DB restart durability)
# ---------------------------------------------------------------------------

class TestTC428_6_DbFallbackRoundTrip:
    def test_float_survives_roundtrip(self):
        assert abs(_verdict_json_roundtrip(42.123456) - 42.123456) < 1e-9

    def test_none_survives_roundtrip(self):
        assert _verdict_json_roundtrip(None) is None

    def test_zero_survives_roundtrip(self):
        result = _verdict_json_roundtrip(0.0)
        assert result is not None
        assert result == 0.0

    def test_missing_key_in_legacy_row_returns_none(self):
        """Pre-#428 DB rows have no key → .get() returns None (no KeyError)."""
        import json
        legacy = {"overall": "PASS", "tick_count": 3, "dropped_ticks": 0,
                  "gap_count": 0, "assertions": []}
        assert json.loads(json.dumps(legacy)).get("total_edl_dispatch_cost_usd") is None


# ---------------------------------------------------------------------------
# 428-7: Integration — real _drive() through RunManager
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_edl_active_run_produces_non_none_total():
    """build_run_context wires edl_sources → completed run total must be non-None."""
    hub = WebSocketHub()
    manager = RunManager(hub)
    ctx = build_run_context("edl-428-a", job_id="job-A", node_count=10,
                            end_sim_time=30.0)
    assert ctx.edl_sources is not None, "build_run_context must wire edl_sources"

    completed = await _run_to_completion(manager, ctx)
    assert completed is not None
    assert completed.total_edl_dispatch_cost_usd is not None, (
        "EDL-active run must report a non-None total_edl_dispatch_cost_usd"
    )
    assert completed.total_edl_dispatch_cost_usd >= 0.0


@pytest.mark.asyncio
async def test_headless_run_produces_none_total():
    """When edl_sources is None the completed run total must be None."""
    hub = WebSocketHub()
    manager = RunManager(hub)
    ctx = build_run_context("edl-428-b", job_id="job-B", node_count=10,
                            end_sim_time=30.0)
    # Demote to headless: remove the EDL power sources.
    ctx.edl_sources = None  # RunContext is a mutable dataclass

    completed = await _run_to_completion(manager, ctx)
    assert completed is not None
    assert completed.total_edl_dispatch_cost_usd is None, (
        "Headless run (edl_sources=None) must report null total_edl_dispatch_cost_usd"
    )


@pytest.mark.asyncio
async def test_edl_active_run_total_equals_sum_of_tick_costs():
    """total_edl_dispatch_cost_usd must equal Σ edl_dispatch_cost_usd from tick_dicts."""
    hub = WebSocketHub()
    manager = RunManager(hub)
    ctx = build_run_context("edl-428-c", job_id="job-C", node_count=10,
                            end_sim_time=30.0)

    completed = await _run_to_completion(manager, ctx)
    assert completed is not None

    tick_sum = sum(
        (td.get("edl_dispatch_cost_usd") or 0.0)
        for td in completed.tick_dicts
    )
    assert completed.total_edl_dispatch_cost_usd == pytest.approx(tick_sum, abs=1e-5)
