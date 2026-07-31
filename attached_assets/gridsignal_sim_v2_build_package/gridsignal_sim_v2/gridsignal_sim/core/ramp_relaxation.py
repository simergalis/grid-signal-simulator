"""
core/ramp_relaxation.py — §23.7.2 adaptive ramp relaxation.

§23.7 context (also the spec's own strongest self-criticism)
------------------------------------------------------------
A static scheduler ramp policy — bring accelerators up under a power cap and
release it over 60–90 seconds — prevents an unmanageable step-load with no
forecasting at all.  §23.7 is explicit that this should be recommended as the
honest baseline competitor.  What GridSignal adds is making the ramp *adaptive*:
when the reserve position confirms headroom, the ramp duration can be relaxed.

TC-75  Relaxation requires a reserve check passing against the confidence
       band's UPPER demand bound (= the LOWER bound on reserve headroom).
       "No warning at current demand" is NOT sufficient — the upper demand
       bound must leave enough reserve headroom above the threshold.  This
       prevents a situation where current demand shows comfort but the
       pessimistic forecast removes it.

TC-76  On loss of GridSignal (gridSignal_connected=False) the relaxation
       lapses immediately and the site baseline policy resumes.  The failure
       direction is toward conservative pre-installation behaviour — never
       toward an unramped start.  adaptive_active=False keeps the power cap
       and the ramp duration from the site's static baseline.

Plane separation: pure computation, no I/O, no SimulationState imports.
"""
from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Reserve position snapshot
# ---------------------------------------------------------------------------

@dataclass
class ReservePosition:
    """Snapshot of the reserve position for ramp-relaxation eligibility checks.

    TC-75 terminology
    -----------------
    "confidence band's LOWER bound on reserve" =
        available_capacity_mw − forecast_upper_bound_mw

    i.e. if demand reaches the UPPER (pessimistic) end of the confidence band,
    how much reserve capacity is left?  That is the lower bound on reserve
    headroom.  TC-75 requires this to pass the threshold, not merely the
    headroom at current observed demand.
    """

    available_capacity_mw:    float   # current total dispatchable capacity
    current_demand_mw:        float   # current measured demand
    forecast_upper_bound_mw:  float   # upper (pessimistic) end of demand confidence band

    @property
    def headroom_at_current_demand(self) -> float:
        """Reserve at the currently observed demand.

        Absence of a warning at this level is NOT sufficient for relaxation
        (TC-75).  Use headroom_at_upper_bound for the eligibility check.
        """
        return self.available_capacity_mw - self.current_demand_mw

    @property
    def headroom_at_upper_bound(self) -> float:
        """Reserve at the pessimistic (upper) demand forecast bound.

        This is the 'lower bound on reserve headroom'.  TC-75 requires THIS
        value to meet or exceed the reserve threshold for relaxation to be
        eligible — not the headroom at current demand alone.
        """
        return self.available_capacity_mw - self.forecast_upper_bound_mw


# ---------------------------------------------------------------------------
# Ramp policy
# ---------------------------------------------------------------------------

@dataclass
class SiteRampPolicy:
    """The active ramp policy for site accelerator starts.

    ramp_cap_mw     Power cap in effect during the start sequence.
                    Always > 0 — even when adaptive_active=False, the cap
                    remains.  TC-76: GridSignal loss preserves the baseline
                    cap; it never drops to an uncapped (unramped) start.

    ramp_duration_s Nominal duration of the ramp.  Baseline: 60–90 s per §23.7.

    adaptive_active True only when GridSignal is connected AND the TC-75
                    reserve check passes.  Signals that relaxation is in effect;
                    callers may reduce ramp_duration_s relative to the static
                    baseline when this is True.
    """

    ramp_cap_mw:      float
    ramp_duration_s:  float
    adaptive_active:  bool = False


# ---------------------------------------------------------------------------
# Ramp relaxation engine
# ---------------------------------------------------------------------------

class RampRelaxationEngine:
    """§23.7.2 adaptive ramp relaxation engine.

    Parameters
    ----------
    reserve_threshold_mw:
        Minimum headroom at the upper demand bound required for relaxation.
    baseline_ramp_cap_mw:
        Power cap for the static baseline (and for the relaxed policy — cap
        is kept even when adaptive).  TC-76: never zero.
    baseline_ramp_duration_s:
        Baseline ramp duration.  PROTO-15 chosen midpoint: 75 s (60–90 s).
    adaptive_ramp_duration_s:
        Duration when adaptive relaxation is active.  Must be < baseline.
        PROTO-15 chosen value: 30 s.  Not used if adaptive_active=False.
    """

    # PROTO-15: chosen values; no measured basis.
    _DEFAULT_BASELINE_S: float = 75.0
    _DEFAULT_ADAPTIVE_S: float = 30.0

    def __init__(
        self,
        reserve_threshold_mw:     float,
        baseline_ramp_cap_mw:     float,
        baseline_ramp_duration_s: float | None = None,
        adaptive_ramp_duration_s: float | None = None,
    ) -> None:
        if baseline_ramp_cap_mw <= 0:
            raise ValueError(
                "baseline_ramp_cap_mw must be > 0 (TC-76: unramped start is "
                "never the failure direction)"
            )
        self.reserve_threshold_mw    = reserve_threshold_mw
        self.baseline_ramp_cap_mw    = baseline_ramp_cap_mw
        self.baseline_ramp_duration_s = (
            baseline_ramp_duration_s
            if baseline_ramp_duration_s is not None
            else self._DEFAULT_BASELINE_S
        )
        self.adaptive_ramp_duration_s = (
            adaptive_ramp_duration_s
            if adaptive_ramp_duration_s is not None
            else self._DEFAULT_ADAPTIVE_S
        )

    def evaluate(
        self,
        position: ReservePosition,
        *,
        gridSignal_connected: bool,
    ) -> SiteRampPolicy:
        """Compute the current ramp policy.

        TC-75: eligibility requires headroom_at_upper_bound >= threshold.
               "No warning at current demand" is not sufficient.

        TC-76: GridSignal loss → adaptive_active=False; returns baseline policy.
               The baseline always has ramp_cap_mw > 0 (never unramped).

        Returns a SiteRampPolicy.  Callers act on adaptive_active to decide
        whether to apply the shortened adaptive ramp duration.
        """
        # TC-76: GridSignal loss always returns baseline regardless of reserve.
        if not gridSignal_connected:
            return SiteRampPolicy(
                ramp_cap_mw=self.baseline_ramp_cap_mw,
                ramp_duration_s=self.baseline_ramp_duration_s,
                adaptive_active=False,
            )

        # TC-75: check against UPPER demand bound (lower reserve bound).
        eligible = position.headroom_at_upper_bound >= self.reserve_threshold_mw

        return SiteRampPolicy(
            ramp_cap_mw=self.baseline_ramp_cap_mw,
            ramp_duration_s=(
                self.adaptive_ramp_duration_s if eligible
                else self.baseline_ramp_duration_s
            ),
            adaptive_active=eligible,
        )
