"""
tests/test_verdicts.py — Step 9: assertion evaluation and verdict gate tests.

Four tests as per the approved plan:
  1. no_insufficient_reserve_alert → INCONCLUSIVE when gaps exist (H1 regression)
  2. Empty assertions → INCONCLUSIVE
  3. Full run — passing scenario (non-vacuous guard: alert never fired)
  4. Full run — TC-10 style failing scenario (non-vacuous guard: alert fired ≥ 1 tick)

Tests 3 and 4 use the same parameters as the demo-20mw and demo-alert built-in
scenarios respectively, so they exercise the same physical path as the 140-test
suite without duplicating scenario-builder fixtures.
"""

from __future__ import annotations

import asyncio

import pytest

from runtime.verdict import (
    AlertFiresAssertion,
    EvalRow,
    MinFinalBessSocAssertion,
    NoReserveAlertAssertion,
    VerdictResult,
    evaluate_verdict,
)
from runtime.run_manager import (
    InMemoryTimeseriesSink,
    RunManager,
    WebSocketHub,
)
from runtime.scenario_factory import build_run_context


# ---------------------------------------------------------------------------
# Unit tests — evaluate_verdict() directly (no I/O)
# ---------------------------------------------------------------------------

class TestEvaluateVerdictGapHandling:
    """H1 gap rule: no_insufficient_reserve_alert cannot be PASS with gaps."""

    def test_no_alert_inconclusive_with_gaps(self) -> None:
        """Synthetic gap in tick_index — H1 regression.

        Rows 1, 2, 4 (gap before tick 4).  No alert fired in retained rows.
        With a universal assertion, gaps mean a dropped tick may have fired;
        the verdict must be INCONCLUSIVE, never PASS.
        """
        rows = [
            EvalRow(tick_index=1, p_total_mw=19.0, bess_soc_fraction=0.95, insufficient_reserve_alert=False),
            EvalRow(tick_index=2, p_total_mw=19.0, bess_soc_fraction=0.94, insufficient_reserve_alert=False),
            EvalRow(tick_index=4, p_total_mw=19.0, bess_soc_fraction=0.93, insufficient_reserve_alert=False),
            # tick 3 is missing — simulated dropped row
        ]
        result = evaluate_verdict(
            assertions=[NoReserveAlertAssertion()],
            rows=rows,
            dropped_ticks=1,
        )
        assert result.assertions[0].status == "INCONCLUSIVE", (
            "no_insufficient_reserve_alert must be INCONCLUSIVE (not PASS) "
            "when gaps exist — a dropped tick may have fired the alert"
        )
        assert result.overall == "INCONCLUSIVE"

    def test_no_alert_passes_without_gaps(self) -> None:
        """Clean sequence with no gaps and no alert — should PASS."""
        rows = [
            EvalRow(tick_index=i + 1, p_total_mw=19.0, bess_soc_fraction=0.95, insufficient_reserve_alert=False)
            for i in range(5)
        ]
        result = evaluate_verdict(
            assertions=[NoReserveAlertAssertion()],
            rows=rows,
            dropped_ticks=0,
        )
        assert result.assertions[0].status == "PASS"
        assert result.overall == "PASS"

    def test_no_alert_fails_when_alert_fires(self) -> None:
        """Alert fires in retained rows — must FAIL regardless of gaps."""
        rows = [
            EvalRow(tick_index=1, p_total_mw=19.0, bess_soc_fraction=0.95, insufficient_reserve_alert=False),
            EvalRow(tick_index=2, p_total_mw=19.0, bess_soc_fraction=0.80, insufficient_reserve_alert=True),
        ]
        result = evaluate_verdict(
            assertions=[NoReserveAlertAssertion()],
            rows=rows,
            dropped_ticks=0,
        )
        assert result.assertions[0].status == "FAIL"
        assert result.overall == "FAIL"

    def test_alert_fires_passes_despite_gaps(self) -> None:
        """Existential assertion: retained row fires → PASS even with gaps."""
        rows = [
            EvalRow(tick_index=1, p_total_mw=19.0, bess_soc_fraction=0.50, insufficient_reserve_alert=True),
            EvalRow(tick_index=3, p_total_mw=19.0, bess_soc_fraction=0.40, insufficient_reserve_alert=False),
            # gap before tick 3
        ]
        result = evaluate_verdict(
            assertions=[AlertFiresAssertion()],
            rows=rows,
            dropped_ticks=1,
        )
        assert result.assertions[0].status == "PASS", (
            "alert_fires is existential — a retained tick that fired is sufficient for PASS"
        )

    def test_empty_assertions_inconclusive(self) -> None:
        """No assertions → overall INCONCLUSIVE (cannot confirm absence of failure)."""
        rows = [
            EvalRow(tick_index=i + 1, p_total_mw=19.0, bess_soc_fraction=0.95, insufficient_reserve_alert=False)
            for i in range(5)
        ]
        result = evaluate_verdict(assertions=[], rows=rows, dropped_ticks=0)
        assert result.overall == "INCONCLUSIVE"
        assert result.assertions == []

    def test_gap_count_detection(self) -> None:
        """_count_gaps correctly counts non-contiguous sequences."""
        rows = [
            EvalRow(1, 1.0, 0.95, False),
            EvalRow(3, 1.0, 0.95, False),   # gap here
            EvalRow(7, 1.0, 0.95, False),   # gap here
        ]
        result = evaluate_verdict(assertions=[], rows=rows, dropped_ticks=2)
        assert result.gap_count == 2


# ---------------------------------------------------------------------------
# Integration tests — full simulation run with InMemoryTimeseriesSink
# ---------------------------------------------------------------------------

class TestFullRunVerdicts:
    """End-to-end: run a scenario with InMemoryTimeseriesSink and check verdict.

    Each test uses a non-vacuous guard to confirm the assertion result
    genuinely reflects what the simulation produced, not a vacuous
    pass/fail on an empty or uniform time series.
    """

    def test_passing_scenario_no_alert(self) -> None:
        """demo-20mw equivalent: large turbine covers all load.

        no_insufficient_reserve_alert assertion must PASS.
        Non-vacuous guard: confirms that no tick actually fired the alert —
        the PASS is not trivial because the simulation ran 60 ticks.
        """
        hub = WebSocketHub()
        manager = RunManager(hub)
        sink = InMemoryTimeseriesSink()

        ctx = build_run_context(
            "run-verdict-pass",
            job_id="job-big-turbine",
            node_count=1900,
            turbine_rated_mw=25.0,
            bess_rated_mw=18.0,       # 18 MW / 8 MWh ≈ 2.2C — same as demo-20mw
            bess_usable_mwh=8.0,      # bridging_available = 18 - 1 (anchor) = 17 MW
            bess_grid_forming=True,   # peak_shortfall ≈ 13.97 MW < 17 MW → no alert
            end_sim_time=300.0,
        )
        ctx.assertions = [NoReserveAlertAssertion()]
        ctx.scenario_name = "demo-20mw-verdict-test"
        ctx.sink = sink

        async def go() -> None:
            await manager.start_run(ctx)
            task = manager._tasks.get("run-verdict-pass")
            if task:
                await task

        asyncio.run(go())

        completed = manager.get_completed("run-verdict-pass")
        assert completed is not None, "run must appear in _completed after finishing"

        # Non-vacuous guard: the alert must truly never have fired.
        assert all(not r.insufficient_reserve_alert for r in sink.rows), (
            "Non-vacuous PASS guard: no tick should have fired the alert "
            "in the demo-20mw configuration (18 MW BESS, 17 MW bridging headroom)"
        )
        assert len(sink.rows) == 60, "300 s / 5 s interval = 60 ticks"

        assert completed.verdict.overall == "PASS", (
            f"demo-20mw with large turbine + 18 MW BESS must PASS no_alert; "
            f"got {completed.verdict.overall!r}. "
            f"assertion detail: {completed.verdict.assertions[0].detail}"
        )
        assert completed.verdict.assertions[0].status == "PASS"

    def test_failing_scenario_tc10_style(self) -> None:
        """TC-10 style: underpowered BESS, large load.

        no_insufficient_reserve_alert assertion must FAIL.
        Non-vacuous guard: confirms that the alert genuinely fired on ≥ 1 tick —
        the FAIL is not spurious.

        Uses demo-alert parameters (5 MW BESS / 2.5 MWh / grid_forming) which
        fire an insufficient_reserve_alert when BESS SoC falls below the anchor
        reserve threshold during the turbine ramp phase.
        """
        hub = WebSocketHub()
        manager = RunManager(hub)
        sink = InMemoryTimeseriesSink()

        ctx = build_run_context(
            "run-verdict-fail",
            job_id="job-small-bess",
            node_count=1900,
            turbine_rated_mw=25.0,
            bess_usable_mwh=2.5,
            bess_rated_mw=5.0,
            bess_grid_forming=True,
            end_sim_time=300.0,
        )
        ctx.assertions = [NoReserveAlertAssertion()]
        ctx.scenario_name = "demo-alert-verdict-test"
        ctx.sink = sink

        async def go() -> None:
            await manager.start_run(ctx)
            task = manager._tasks.get("run-verdict-fail")
            if task:
                await task

        asyncio.run(go())

        completed = manager.get_completed("run-verdict-fail")
        assert completed is not None

        # Non-vacuous guard: confirm the alert actually fired.
        alert_ticks = [r for r in sink.rows if r.insufficient_reserve_alert]
        assert len(alert_ticks) > 0, (
            "Non-vacuous FAIL guard: at least one tick must have fired the alert "
            "in the demo-alert configuration"
        )

        assert completed.verdict.overall == "FAIL", (
            f"demo-alert with underpowered BESS must FAIL no_alert; "
            f"got {completed.verdict.overall!r}. "
            f"assertion detail: {completed.verdict.assertions[0].detail}"
        )
        assert completed.verdict.assertions[0].status == "FAIL"
