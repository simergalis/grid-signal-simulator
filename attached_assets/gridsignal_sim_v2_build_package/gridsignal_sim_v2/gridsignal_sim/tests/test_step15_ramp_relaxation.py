"""
tests/test_step15_ramp_relaxation.py — Step 15 gate tests for §23.7.2 adaptive
ramp relaxation.

TC-75  Relaxation requires a reserve check passing against the confidence
       band's UPPER demand bound (= lower bound on reserve headroom).
       "No warning at current demand" is NOT sufficient.

TC-76  On loss of GridSignal, relaxation lapses and the site baseline policy
       resumes.  The failure direction is toward conservative pre-installation
       behaviour — never toward an unramped start.
"""
from __future__ import annotations

import pytest

from core.ramp_relaxation import (
    RampRelaxationEngine,
    ReservePosition,
    SiteRampPolicy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _engine(
    threshold: float = 2.0,
    cap_mw: float = 5.0,
    baseline_s: float = 75.0,
    adaptive_s: float = 30.0,
) -> RampRelaxationEngine:
    return RampRelaxationEngine(
        reserve_threshold_mw=threshold,
        baseline_ramp_cap_mw=cap_mw,
        baseline_ramp_duration_s=baseline_s,
        adaptive_ramp_duration_s=adaptive_s,
    )


def _pos(
    available: float,
    current: float,
    upper: float,
) -> ReservePosition:
    return ReservePosition(
        available_capacity_mw=available,
        current_demand_mw=current,
        forecast_upper_bound_mw=upper,
    )


# ---------------------------------------------------------------------------
# TC-75: upper-bound reserve check required for relaxation
# ---------------------------------------------------------------------------

class TestTC75UpperBoundCheck:

    def test_absence_of_warning_not_sufficient(self) -> None:
        """TC-75: no-warning at current demand is not enough.

        Current demand: 15 MW (headroom at current = 5 MW — no warning).
        Upper demand bound: 19 MW (headroom at upper = 1 MW < 2 MW threshold).
        → relaxation must NOT be active.
        """
        engine = _engine(threshold=2.0)
        pos = _pos(available=20.0, current=15.0, upper=19.0)

        # Confirm the "no-warning" appearance at current demand
        assert pos.headroom_at_current_demand == pytest.approx(5.0)
        # But upper-bound check fails
        assert pos.headroom_at_upper_bound == pytest.approx(1.0)

        policy = engine.evaluate(pos, gridSignal_connected=True)
        assert not policy.adaptive_active, (
            "TC-75: relaxation must be inactive when upper-bound headroom "
            f"({pos.headroom_at_upper_bound} MW) < threshold (2.0 MW)"
        )

    def test_eligible_when_upper_bound_passes(self) -> None:
        """TC-75: relaxation is active when upper-bound reserve clears threshold."""
        engine = _engine(threshold=2.0)
        pos = _pos(available=25.0, current=15.0, upper=20.0)  # headroom = 5 MW >= 2 MW
        policy = engine.evaluate(pos, gridSignal_connected=True)
        assert policy.adaptive_active

    def test_exactly_at_threshold_is_eligible(self) -> None:
        """headroom_at_upper_bound == threshold → eligible (not strictly greater-than)."""
        engine = _engine(threshold=3.0)
        pos = _pos(available=23.0, current=15.0, upper=20.0)  # headroom = 3.0 == 3.0
        assert pos.headroom_at_upper_bound == pytest.approx(3.0)
        policy = engine.evaluate(pos, gridSignal_connected=True)
        assert policy.adaptive_active

    def test_just_below_threshold_not_eligible(self) -> None:
        """headroom_at_upper_bound just below threshold → not eligible."""
        engine = _engine(threshold=3.0)
        pos = _pos(available=22.99, current=15.0, upper=20.0)  # headroom = 2.99 < 3.0
        policy = engine.evaluate(pos, gridSignal_connected=True)
        assert not policy.adaptive_active

    def test_upper_bound_below_current_demand_not_eligible(self) -> None:
        """Upper bound < current demand → negative headroom → not eligible."""
        engine = _engine(threshold=0.0)
        pos = _pos(available=20.0, current=18.0, upper=21.0)  # headroom = -1 MW
        policy = engine.evaluate(pos, gridSignal_connected=True)
        assert not policy.adaptive_active

    def test_adaptive_duration_shorter_than_baseline(self) -> None:
        """When adaptive is active, ramp_duration_s < baseline_ramp_duration_s."""
        engine = _engine(threshold=2.0, baseline_s=75.0, adaptive_s=30.0)
        pos = _pos(available=30.0, current=10.0, upper=15.0)  # headroom = 15 MW
        policy = engine.evaluate(pos, gridSignal_connected=True)
        assert policy.adaptive_active
        assert policy.ramp_duration_s == pytest.approx(30.0)
        assert 30.0 < 75.0   # adaptive is shorter than baseline

    def test_baseline_duration_when_not_eligible(self) -> None:
        """When not eligible, ramp_duration_s == baseline."""
        engine = _engine(threshold=10.0, baseline_s=75.0, adaptive_s=30.0)
        pos = _pos(available=20.0, current=15.0, upper=19.0)  # headroom = 1 MW < 10
        policy = engine.evaluate(pos, gridSignal_connected=True)
        assert not policy.adaptive_active
        assert policy.ramp_duration_s == pytest.approx(75.0)


# ---------------------------------------------------------------------------
# TC-76: GridSignal loss lapses to baseline
# ---------------------------------------------------------------------------

class TestTC76GridSignalLoss:

    def test_gridSignal_loss_forces_baseline(self) -> None:
        """TC-76: GridSignal loss → adaptive_active=False regardless of reserve."""
        engine = _engine(threshold=2.0)
        # Excellent reserve — would be eligible if connected
        pos = _pos(available=40.0, current=5.0, upper=10.0)   # headroom = 30 MW

        # Confirm eligible when connected
        assert engine.evaluate(pos, gridSignal_connected=True).adaptive_active

        # TC-76: disconnected → baseline, no matter how good the reserve
        policy = engine.evaluate(pos, gridSignal_connected=False)
        assert not policy.adaptive_active, (
            "TC-76: GridSignal loss must force adaptive_active=False even "
            "when reserve position is excellent"
        )

    def test_gridSignal_loss_preserves_ramp_cap(self) -> None:
        """TC-76: failure direction is conservative, not unramped.

        On GridSignal loss the baseline cap is preserved.  ramp_cap_mw > 0
        means the site continues under the static ramp discipline.
        """
        engine = _engine(threshold=2.0, cap_mw=5.0, baseline_s=75.0)
        pos = _pos(available=40.0, current=5.0, upper=10.0)
        policy = engine.evaluate(pos, gridSignal_connected=False)

        # Cap is preserved (not zero = not unramped)
        assert policy.ramp_cap_mw > 0.0, (
            f"TC-76: ramp_cap_mw must be > 0 after GridSignal loss; "
            f"got {policy.ramp_cap_mw}"
        )
        assert policy.ramp_cap_mw == pytest.approx(5.0)

    def test_gridSignal_loss_preserves_ramp_duration(self) -> None:
        """TC-76: GridSignal loss uses baseline ramp duration, not zero."""
        engine = _engine(threshold=2.0, cap_mw=5.0, baseline_s=75.0)
        pos = _pos(available=40.0, current=5.0, upper=10.0)
        policy = engine.evaluate(pos, gridSignal_connected=False)
        assert policy.ramp_duration_s == pytest.approx(75.0)
        assert policy.ramp_duration_s > 0.0

    def test_reconnect_resumes_adaptive_when_eligible(self) -> None:
        """After GridSignal reconnection, adaptive can resume if reserve passes."""
        engine = _engine(threshold=2.0)
        pos = _pos(available=30.0, current=10.0, upper=15.0)  # headroom = 15 MW

        # Disconnected → baseline
        assert not engine.evaluate(pos, gridSignal_connected=False).adaptive_active
        # Reconnected → adaptive
        assert engine.evaluate(pos, gridSignal_connected=True).adaptive_active

    def test_baseline_cap_must_be_positive(self) -> None:
        """RampRelaxationEngine refuses a zero cap at construction (TC-76 guard)."""
        with pytest.raises(ValueError, match="unramped start"):
            RampRelaxationEngine(
                reserve_threshold_mw=2.0,
                baseline_ramp_cap_mw=0.0,   # invalid
            )


# ---------------------------------------------------------------------------
# ReservePosition semantics (shared by TC-75 and TC-76)
# ---------------------------------------------------------------------------

class TestReservePositionSemantics:

    def test_headroom_at_current_demand(self) -> None:
        pos = _pos(available=20.0, current=15.0, upper=19.0)
        assert pos.headroom_at_current_demand == pytest.approx(5.0)

    def test_headroom_at_upper_bound(self) -> None:
        pos = _pos(available=20.0, current=15.0, upper=19.0)
        assert pos.headroom_at_upper_bound == pytest.approx(1.0)

    def test_negative_headroom_at_upper_bound(self) -> None:
        """Upper bound can exceed available capacity — negative headroom."""
        pos = _pos(available=18.0, current=14.0, upper=22.0)
        assert pos.headroom_at_upper_bound == pytest.approx(-4.0)
