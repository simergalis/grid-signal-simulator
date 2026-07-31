"""
tests/test_step10_arbitration.py — Step 10: deterministic arbitration + pre-staging.

TC-41: Mandatory curtailment ordering — never invoke tier B while A still has
       headroom; never skip to C/D while A/B cover the gap.
TC-42: C/D always require_confirmation=True; autonomy flag is independent of
       OperatingTier — there is no tier setting that makes C/D autonomous.
TC-43: low_confidence segment blocks ALL curtailment proposals regardless of gap.
TC-44: 120 s dwell must elapse before any proposal; 20% restoration margin
       governs de-escalation.
TC-46: Dead-man expiry — auto-release after MAX_HOLD_S when gap persists.
TC-49: select_candidates() is reproducible over ALL PERMUTATIONS of a candidate
       set — tested over every ordering of a five-candidate set (120 cases).
TC-55: Pre-staging is bounded by the inlet-temperature band; shift drops to 0.0
       when inlet temperature reaches the lower comfort limit.
TC-56: BMS override is unconditional — pre-staging returns 0.0 regardless of
       gap size, temperature, or max_shift_mw.
"""
from __future__ import annotations

import itertools

import pytest

from core.dispatch import (
    CandidateResponse,
    CurtailmentLadder,
    CurtailmentTier,
    LadderPosition,
    PreStagingEngine,
    select_candidates,
)
from core.models import OperatingTier, PreStagingConfig


# ---------------------------------------------------------------------------
# TC-49 — select_candidates() deterministic over ALL permutations
# ---------------------------------------------------------------------------

class TestSelectCandidatesDeterminism:
    """TC-49: selection is reproducible from the recommendation set alone.

    A test that exercises one ordering proves nothing — two agents may publish
    the same response kind, a dict keyed by kind silently drops one, and
    selection becomes input-order-dependent.  Test ALL PERMUTATIONS.
    """

    def _five_candidate_set(self) -> list[CandidateResponse]:
        """Five candidates spanning four ladder positions with a repeated kind."""
        return [
            CandidateResponse(
                ladder_position=LadderPosition.STORAGE_DISCHARGE,
                estimated_impact_mw=8.0,
                candidate_id="bess-a",
                response_kind="storage_discharge",
            ),
            CandidateResponse(
                ladder_position=LadderPosition.TURBINE_RAMP,
                estimated_impact_mw=6.0,
                candidate_id="turbine-1",
                response_kind="turbine_ramp",
            ),
            CandidateResponse(
                ladder_position=LadderPosition.TURBINE_RAMP,
                estimated_impact_mw=4.0,
                candidate_id="turbine-2",
                response_kind="turbine_ramp",   # SAME KIND as turbine-1 — must not drop
            ),
            CandidateResponse(
                ladder_position=LadderPosition.CURTAILMENT_A_B,
                estimated_impact_mw=2.0,
                candidate_id="curtail-ab",
                response_kind="curtailment_a_b",
            ),
            CandidateResponse(
                ladder_position=LadderPosition.CURTAILMENT_C_D,
                estimated_impact_mw=5.0,
                candidate_id="curtail-cd",
                response_kind="curtailment_c_d",
                requires_confirmation=True,
            ),
        ]

    def test_tc49_all_permutations_same_selection_partial_gap(self) -> None:
        """TC-49: gap=10 MW — all 120 input orderings yield identical selection."""
        candidates = self._five_candidate_set()
        gap_mw = 10.0

        # Reference result from the canonical ordering.
        reference = [c.candidate_id for c in select_candidates(candidates, gap_mw)]
        assert reference, "reference selection must be non-empty for gap > 0"

        mismatches: list[str] = []
        for i, perm in enumerate(itertools.permutations(candidates)):
            result = [c.candidate_id for c in select_candidates(list(perm), gap_mw)]
            if result != reference:
                mismatches.append(
                    f"permutation {i}: got {result}, expected {reference}"
                )

        assert not mismatches, (
            f"TC-49 FAIL — selection is input-order-dependent ({len(mismatches)} / 120 "
            f"permutations differ):\n" + "\n".join(mismatches[:5])
        )

    def test_tc49_all_permutations_full_gap(self) -> None:
        """TC-49: gap=25 MW (needs all candidates) — all 120 orderings agree."""
        candidates = self._five_candidate_set()
        gap_mw = 25.0

        reference = [c.candidate_id for c in select_candidates(candidates, gap_mw)]
        for perm in itertools.permutations(candidates):
            result = [c.candidate_id for c in select_candidates(list(perm), gap_mw)]
            assert result == reference, (
                f"TC-49 FAIL: ordering {[c.candidate_id for c in perm]} "
                f"produced {result}, expected {reference}"
            )

    def test_tc49_same_kind_candidates_not_dropped(self) -> None:
        """TC-49: two candidates with identical response_kind are both selectable."""
        # Two turbine candidates; gap forces both to be selected.
        candidates = [
            CandidateResponse(LadderPosition.TURBINE_RAMP, 6.0, "t1", "turbine_ramp"),
            CandidateResponse(LadderPosition.TURBINE_RAMP, 4.0, "t2", "turbine_ramp"),
        ]
        selected = select_candidates(candidates, gap_mw=9.0)
        ids = {c.candidate_id for c in selected}
        assert "t1" in ids, "first same-kind candidate must be selected"
        assert "t2" in ids, "second same-kind candidate must NOT be dropped (TC-49)"

    def test_tc49_zero_gap_returns_empty(self) -> None:
        """No selection when gap is zero."""
        candidates = self._five_candidate_set()
        assert select_candidates(candidates, gap_mw=0.0) == []

    def test_tc49_total_order_within_position(self) -> None:
        """Within the same ladder_position, higher impact is selected first."""
        candidates = [
            CandidateResponse(LadderPosition.TURBINE_RAMP, 3.0, "low-impact", "turbine"),
            CandidateResponse(LadderPosition.TURBINE_RAMP, 7.0, "high-impact", "turbine"),
        ]
        # gap=7 MW: only one candidate needed; should pick the higher-impact one.
        selected = select_candidates(candidates, gap_mw=7.0)
        assert len(selected) == 1
        assert selected[0].candidate_id == "high-impact", (
            "within the same ladder position, higher estimated_impact_mw must rank first"
        )


# ---------------------------------------------------------------------------
# TC-41 — mandatory curtailment ordering
# ---------------------------------------------------------------------------

class TestCurtailmentMandatoryOrdering:
    """TC-41: never invoke a higher tier while a lower tier has remaining headroom."""

    def _past_dwell(self, ladder: CurtailmentLadder, gap_mw: float) -> list:
        """Advance the ladder past the 120 s dwell at a fixed gap."""
        # Feed enough ticks to cross 120 s.
        for t in range(0, 125, 5):
            proposals = ladder.tick(
                gap_mw=gap_mw,
                is_low_confidence=False,
                operating_tier=OperatingTier.AUTONOMOUS,
                sim_time=float(t),
            )
        return proposals  # last call's result

    def test_tc41_small_gap_only_tier_a(self) -> None:
        """TC-41: gap within A capacity → only A proposed, B/C/D absent."""
        ladder = CurtailmentLadder()
        # A_DEFER capacity is 2.0 MW; gap of 1.5 MW is within A alone.
        proposals = self._past_dwell(ladder, gap_mw=1.5)
        tiers = {p.tier for p in proposals}
        assert CurtailmentTier.A_DEFER in tiers, "A must be proposed"
        assert CurtailmentTier.B_POWER_CAP not in tiers, (
            "TC-41: B must NOT be proposed when A covers the gap"
        )
        assert CurtailmentTier.C_SUSPEND not in tiers
        assert CurtailmentTier.D_PREEMPT not in tiers

    def test_tc41_medium_gap_a_and_b(self) -> None:
        """TC-41: gap requiring A + B → both proposed, C/D absent."""
        ladder = CurtailmentLadder()
        # A=2 MW, B=5 MW; gap=6 MW needs A+B (total 7 MW), C not needed.
        proposals = self._past_dwell(ladder, gap_mw=6.0)
        tiers = {p.tier for p in proposals}
        assert CurtailmentTier.A_DEFER in tiers
        assert CurtailmentTier.B_POWER_CAP in tiers
        assert CurtailmentTier.C_SUSPEND not in tiers, (
            "TC-41: C must NOT be proposed when A+B covers the gap"
        )
        assert CurtailmentTier.D_PREEMPT not in tiers

    def test_tc41_large_gap_includes_c(self) -> None:
        """TC-41: gap exceeding A+B capacity escalates to C (with confirmation)."""
        ladder = CurtailmentLadder()
        # A=2, B=5, C=10; gap=9 MW requires A+B+C.
        proposals = self._past_dwell(ladder, gap_mw=9.0)
        tiers = {p.tier for p in proposals}
        assert CurtailmentTier.C_SUSPEND in tiers, (
            "C must be proposed when A+B cannot cover gap=9 MW"
        )

    def test_tc41_impact_bounded_by_gap(self) -> None:
        """TC-41: total estimated_impact across proposals does not exceed tier
        capacity AND is sufficient to close the gap (bounded_by_gap=True)."""
        ladder = CurtailmentLadder()
        gap_mw = 1.5
        proposals = self._past_dwell(ladder, gap_mw=gap_mw)
        total_impact = sum(p.estimated_impact_mw for p in proposals)
        assert total_impact >= gap_mw, "proposals must cover the gap"
        # A_DEFER capacity is 2.0 MW; over-shoot must not exceed the tier capacity.
        assert total_impact <= 2.0 + 1e-9, (
            "proposals must not commit more than A's capacity when gap <= A_cap"
        )


# ---------------------------------------------------------------------------
# TC-42 — C/D always require human confirmation
# ---------------------------------------------------------------------------

class TestCurtailmentConfirmation:
    """TC-42: C/D require explicit human confirmation at EVERY invocation.
    There is no operating_tier setting that makes C/D autonomous.
    """

    def _proposals_for_large_gap(self, operating_tier: OperatingTier) -> list:
        ladder = CurtailmentLadder()
        for t in range(0, 130, 5):
            proposals = ladder.tick(
                gap_mw=15.0,  # forces A + B + C
                is_low_confidence=False,
                operating_tier=operating_tier,
                sim_time=float(t),
            )
        return proposals

    def test_tc42_c_requires_confirmation_at_autonomous_tier(self) -> None:
        """TC-42: C has requires_confirmation=True even at AUTONOMOUS tier."""
        proposals = self._proposals_for_large_gap(OperatingTier.AUTONOMOUS)
        c_proposals = [p for p in proposals if p.tier == CurtailmentTier.C_SUSPEND]
        assert c_proposals, "C must be proposed for gap=15 MW"
        assert all(p.requires_confirmation for p in c_proposals), (
            "TC-42: C must ALWAYS have requires_confirmation=True regardless of "
            "operating_tier — even AUTONOMOUS cannot make C autonomous"
        )

    def test_tc42_d_requires_confirmation_at_autonomous_tier(self) -> None:
        """TC-42: D has requires_confirmation=True even at AUTONOMOUS tier."""
        ladder = CurtailmentLadder()
        for t in range(0, 130, 5):
            proposals = ladder.tick(
                gap_mw=20.0,  # forces A + B + C + D
                is_low_confidence=False,
                operating_tier=OperatingTier.AUTONOMOUS,
                sim_time=float(t),
            )
        d_proposals = [p for p in proposals if p.tier == CurtailmentTier.D_PREEMPT]
        assert d_proposals, "D must be proposed for gap=20 MW"
        assert all(p.requires_confirmation for p in d_proposals), (
            "TC-42: D must ALWAYS have requires_confirmation=True"
        )

    def test_tc42_a_does_not_require_confirmation(self) -> None:
        """TC-42 complement: A does NOT require confirmation (autonomous is valid)."""
        ladder = CurtailmentLadder()
        for t in range(0, 130, 5):
            proposals = ladder.tick(
                gap_mw=1.0,
                is_low_confidence=False,
                operating_tier=OperatingTier.AUTONOMOUS,
                sim_time=float(t),
            )
        a_proposals = [p for p in proposals if p.tier == CurtailmentTier.A_DEFER]
        assert a_proposals, "A must be proposed for gap=1.0 MW"
        assert all(not p.requires_confirmation for p in a_proposals), (
            "A must NOT require confirmation"
        )

    def test_tc42_b_does_not_require_confirmation(self) -> None:
        """TC-42 complement: B does NOT require confirmation."""
        ladder = CurtailmentLadder()
        for t in range(0, 130, 5):
            proposals = ladder.tick(
                gap_mw=3.0,  # A=2 MW, needs B for the remaining 1 MW
                is_low_confidence=False,
                operating_tier=OperatingTier.AUTONOMOUS,
                sim_time=float(t),
            )
        b_proposals = [p for p in proposals if p.tier == CurtailmentTier.B_POWER_CAP]
        assert b_proposals
        assert all(not p.requires_confirmation for p in b_proposals)


# ---------------------------------------------------------------------------
# TC-43 — low_confidence blocks ALL autonomous curtailment
# ---------------------------------------------------------------------------

class TestCurtailmentLowConfidence:
    """TC-43: when the segment is low_confidence, no curtailment proposals
    are generated regardless of gap size or operating tier.
    """

    def test_tc43_low_confidence_no_proposals_at_large_gap(self) -> None:
        """TC-43: gap=20 MW, low_confidence=True → empty proposals."""
        ladder = CurtailmentLadder()
        # Even after a long dwell, low_confidence must block everything.
        for t in range(0, 200, 5):
            proposals = ladder.tick(
                gap_mw=20.0,
                is_low_confidence=True,
                operating_tier=OperatingTier.AUTONOMOUS,
                sim_time=float(t),
            )
        assert proposals == [], (
            "TC-43: low_confidence segment must produce ZERO proposals "
            "regardless of gap size or operating_tier"
        )

    def test_tc43_low_confidence_resets_dwell(self) -> None:
        """TC-43: switching low_confidence=True mid-dwell resets the timer.
        After the confidence recovers, the dwell must restart from zero.
        """
        ladder = CurtailmentLadder()
        # Advance 60 s of dwell at normal confidence.
        for t in range(0, 65, 5):
            ladder.tick(
                gap_mw=1.0,
                is_low_confidence=False,
                operating_tier=OperatingTier.AUTONOMOUS,
                sim_time=float(t),
            )
        # Now confidence degrades — must reset dwell.
        ladder.tick(
            gap_mw=1.0, is_low_confidence=True,
            operating_tier=OperatingTier.AUTONOMOUS, sim_time=70.0,
        )
        # Confidence restores; only 10 s more — dwell must NOT have carried
        # over from before the low_confidence interruption.
        proposals = ladder.tick(
            gap_mw=1.0, is_low_confidence=False,
            operating_tier=OperatingTier.AUTONOMOUS, sim_time=80.0,
        )
        assert proposals == [], (
            "TC-43: dwell must restart after low_confidence resets it; "
            "only 10 s since restart (< 120 s threshold)"
        )

    def test_tc43_high_confidence_after_low_eventually_proposes(self) -> None:
        """TC-43: after the confidence recovers and a full dwell elapses,
        proposals are generated — the interlock is not permanent.
        """
        ladder = CurtailmentLadder()
        # Low confidence for 0..50 s.
        for t in range(0, 55, 5):
            ladder.tick(
                gap_mw=1.0, is_low_confidence=True,
                operating_tier=OperatingTier.AUTONOMOUS, sim_time=float(t),
            )
        # Confidence restores at t=55; dwell starts fresh.
        # Advance past 120 s (55 + 125 = 180 s).
        proposals = None
        for t in range(55, 185, 5):
            proposals = ladder.tick(
                gap_mw=1.0, is_low_confidence=False,
                operating_tier=OperatingTier.AUTONOMOUS, sim_time=float(t),
            )
        assert proposals is not None and len(proposals) > 0, (
            "After full dwell at restored confidence, proposals must appear"
        )


# ---------------------------------------------------------------------------
# TC-44 — 120 s dwell and 20% restoration margin
# ---------------------------------------------------------------------------

class TestCurtailmentHysteresis:
    """TC-44: §23.3 hysteresis — 120 s dwell before proposing; 20% restoration
    margin before de-escalating.
    """

    def test_tc44_no_proposals_before_120s(self) -> None:
        """TC-44: no proposals until 120 s of continuous gap observation."""
        ladder = CurtailmentLadder()
        for t in [0, 30, 60, 90, 115]:
            proposals = ladder.tick(
                gap_mw=1.5,
                is_low_confidence=False,
                operating_tier=OperatingTier.AUTONOMOUS,
                sim_time=float(t),
            )
            assert proposals == [], (
                f"TC-44: no proposals expected before 120 s dwell; got {proposals} "
                f"at sim_time={t}"
            )

    def test_tc44_proposals_after_120s(self) -> None:
        """TC-44: proposals appear once 120 s dwell is met."""
        ladder = CurtailmentLadder()
        proposals_before = ladder.tick(
            gap_mw=1.5, is_low_confidence=False,
            operating_tier=OperatingTier.AUTONOMOUS, sim_time=0.0,
        )
        assert proposals_before == []

        proposals_after = ladder.tick(
            gap_mw=1.5, is_low_confidence=False,
            operating_tier=OperatingTier.AUTONOMOUS, sim_time=125.0,
        )
        assert len(proposals_after) > 0, (
            "TC-44: proposals must appear after 120 s dwell"
        )

    def test_tc44_restoration_margin_20pct(self) -> None:
        """TC-44: curtailment de-escalates only when gap drops ≤80% of trigger gap.

        Trigger gap = 2.0 MW.  Restoration threshold = 2.0 * 0.80 = 1.60 MW.
        At gap = 1.7 MW (> 1.60): curtailment continues.
        At gap = 1.5 MW (≤ 1.60): curtailment de-escalates (resets).
        """
        ladder = CurtailmentLadder()
        # Activate at gap=2.0 MW.
        ladder.tick(gap_mw=2.0, is_low_confidence=False,
                    operating_tier=OperatingTier.AUTONOMOUS, sim_time=0.0)
        proposals_active = ladder.tick(gap_mw=2.0, is_low_confidence=False,
                                       operating_tier=OperatingTier.AUTONOMOUS,
                                       sim_time=125.0)
        assert len(proposals_active) > 0, "must be active after dwell"

        # Gap drops to 1.7 MW (85% of 2.0 — above 80% threshold).
        proposals_still_active = ladder.tick(gap_mw=1.7, is_low_confidence=False,
                                             operating_tier=OperatingTier.AUTONOMOUS,
                                             sim_time=130.0)
        assert len(proposals_still_active) > 0, (
            "TC-44: gap at 85% of trigger (> 80% threshold) must NOT de-escalate"
        )

        # Gap drops to 1.5 MW (75% of 2.0 — below 80% threshold).
        proposals_reset = ladder.tick(gap_mw=1.5, is_low_confidence=False,
                                      operating_tier=OperatingTier.AUTONOMOUS,
                                      sim_time=135.0)
        assert proposals_reset == [], (
            "TC-44: gap at 75% of trigger (≤ 80% threshold) must de-escalate "
            "(reset dwell and return empty proposals)"
        )

    def test_tc44_gap_going_to_zero_immediately_resets(self) -> None:
        """TC-44: gap=0 always de-escalates, regardless of restoration margin."""
        ladder = CurtailmentLadder()
        ladder.tick(gap_mw=5.0, is_low_confidence=False,
                    operating_tier=OperatingTier.AUTONOMOUS, sim_time=0.0)
        ladder.tick(gap_mw=5.0, is_low_confidence=False,
                    operating_tier=OperatingTier.AUTONOMOUS, sim_time=125.0)
        # Gap disappears entirely.
        proposals = ladder.tick(gap_mw=0.0, is_low_confidence=False,
                                operating_tier=OperatingTier.AUTONOMOUS,
                                sim_time=130.0)
        assert proposals == [], "gap=0 must reset curtailment state"


# ---------------------------------------------------------------------------
# TC-46 — dead-man expiry
# ---------------------------------------------------------------------------

class TestCurtailmentDeadMan:
    """TC-46: dead-man — curtailment auto-releases after MAX_HOLD_S of
    continuous activation when no release signal arrives.

    Hold questions (build history D1/D2/D4 pattern):
      What bounds it?        MAX_HOLD_S = 300 s (CHOSEN, PROTO-11).
      What makes it terminal? Gap closes (restoration margin met) OR dead-man fires.
      If release never comes? Dead-man fires; curtailment auto-released; anomaly logged.
    """

    def test_tc46_dead_man_releases_after_max_hold(self) -> None:
        """TC-46: after MAX_HOLD_S of continuous curtailment, proposals stop."""
        ladder = CurtailmentLadder()
        max_hold = CurtailmentLadder.MAX_HOLD_S  # 300 s

        # Activate curtailment past dwell.
        ladder.tick(gap_mw=1.5, is_low_confidence=False,
                    operating_tier=OperatingTier.AUTONOMOUS, sim_time=0.0)
        proposals_at_dwell = ladder.tick(gap_mw=1.5, is_low_confidence=False,
                                         operating_tier=OperatingTier.AUTONOMOUS,
                                         sim_time=125.0)
        assert len(proposals_at_dwell) > 0, "must activate at t=125"

        # Feed ticks just before the dead-man boundary.
        just_before = ladder.tick(gap_mw=1.5, is_low_confidence=False,
                                  operating_tier=OperatingTier.AUTONOMOUS,
                                  sim_time=125.0 + max_hold - 1.0)
        assert len(just_before) > 0, "must still be active just before dead-man"

        # Cross the dead-man boundary.
        after_expiry = ladder.tick(gap_mw=1.5, is_low_confidence=False,
                                   operating_tier=OperatingTier.AUTONOMOUS,
                                   sim_time=125.0 + max_hold + 1.0)
        assert after_expiry == [], (
            "TC-46: dead-man must release curtailment after MAX_HOLD_S "
            f"(sim_time = {125.0 + max_hold + 1.0:.1f} s)"
        )

    def test_tc46_after_dead_man_fresh_dwell_required(self) -> None:
        """TC-46: after dead-man fires, a fresh 120 s dwell is needed before
        curtailment can be re-activated (not an immediate re-trigger).
        """
        ladder = CurtailmentLadder()
        max_hold = CurtailmentLadder.MAX_HOLD_S
        dwell = CurtailmentLadder.DWELL_BEFORE_ESCALATION_S

        # Activate, run past dead-man.
        ladder.tick(gap_mw=1.5, is_low_confidence=False,
                    operating_tier=OperatingTier.AUTONOMOUS, sim_time=0.0)
        ladder.tick(gap_mw=1.5, is_low_confidence=False,
                    operating_tier=OperatingTier.AUTONOMOUS, sim_time=dwell + 1.0)
        expiry_t = dwell + 1.0 + max_hold + 1.0
        ladder.tick(gap_mw=1.5, is_low_confidence=False,
                    operating_tier=OperatingTier.AUTONOMOUS, sim_time=expiry_t)

        # Immediately after dead-man: still needs a fresh dwell.
        proposals = ladder.tick(gap_mw=1.5, is_low_confidence=False,
                                 operating_tier=OperatingTier.AUTONOMOUS,
                                 sim_time=expiry_t + 1.0)
        assert proposals == [], (
            "After dead-man expiry a fresh dwell is required; "
            "no proposals on the very next tick"
        )


# ---------------------------------------------------------------------------
# TC-55 — pre-staging bounded by inlet temperature band
# ---------------------------------------------------------------------------

class TestPreStagingTemperatureBound:
    """TC-55: §8.1 pre-staging is bounded by the inlet-temperature band.
    Shift drops to 0.0 when temperature reaches the lower comfort limit.
    """

    def _engine(self, initial_temp_c: float, max_shift_mw: float = 2.0) -> PreStagingEngine:
        config = PreStagingConfig(
            max_shift_mw=max_shift_mw,
            inlet_temp_low_c=18.0,
            inlet_temp_high_c=24.0,
            cooling_gain_c_per_mw_s=0.05,
            warmup_rate_c_per_s=0.002,
            initial_temp_c=initial_temp_c,
            bms_override=False,
        )
        return PreStagingEngine(config)

    def test_tc55_at_lower_bound_shift_is_zero(self) -> None:
        """TC-55: when inlet temp is AT the lower comfort limit, no pre-cooling."""
        engine = self._engine(initial_temp_c=18.0)  # at low bound
        shift = engine.compute_shift(gap_mw=5.0, bms_override=False,
                                     sim_time=0.0, dt_seconds=5.0)
        assert shift == 0.0, (
            "TC-55: at lower temperature bound, pre-cooling headroom = 0 → shift = 0"
        )

    def test_tc55_below_lower_bound_shift_is_zero(self) -> None:
        """TC-55: temperature below lower bound → shift = 0.0 (safety clamp)."""
        engine = self._engine(initial_temp_c=17.5)  # below low bound
        shift = engine.compute_shift(gap_mw=5.0, bms_override=False,
                                     sim_time=0.0, dt_seconds=5.0)
        assert shift == 0.0, "Below lower bound must produce zero shift"

    def test_tc55_mid_band_shift_positive(self) -> None:
        """TC-55: at mid-band temperature, positive shift is returned."""
        engine = self._engine(initial_temp_c=21.0)  # midpoint of [18, 24]
        shift = engine.compute_shift(gap_mw=5.0, bms_override=False,
                                     sim_time=0.0, dt_seconds=5.0)
        assert shift > 0.0, "Mid-band temperature must permit positive shift"
        assert shift <= 2.0, "Shift must not exceed max_shift_mw"

    def test_tc55_shift_bounded_by_max_shift_mw(self) -> None:
        """TC-55: shift never exceeds max_shift_mw regardless of gap size."""
        engine = self._engine(initial_temp_c=23.9, max_shift_mw=1.0)
        shift = engine.compute_shift(gap_mw=100.0, bms_override=False,
                                     sim_time=0.0, dt_seconds=5.0)
        assert shift <= 1.0 + 1e-9, "Shift must be capped by max_shift_mw"

    def test_tc55_temperature_state_decreases_on_shift(self) -> None:
        """TC-55: applying a shift lowers the internal temperature."""
        engine = self._engine(initial_temp_c=22.0)
        temp_before = engine.current_temp_c
        engine.compute_shift(gap_mw=2.0, bms_override=False,
                             sim_time=0.0, dt_seconds=5.0)
        assert engine.current_temp_c < temp_before, (
            "Pre-cooling must reduce inlet temperature"
        )

    def test_tc55_repeated_shifts_exhaust_headroom(self) -> None:
        """TC-55: repeated pre-cooling ticks drain headroom; shift approaches 0."""
        engine = self._engine(initial_temp_c=19.0)  # only 1 °C above low bound
        shifts = []
        for tick in range(20):
            s = engine.compute_shift(gap_mw=10.0, bms_override=False,
                                     sim_time=float(tick * 5), dt_seconds=5.0)
            shifts.append(s)
        # Once temperature hits the lower bound, shift must be zero.
        assert shifts[-1] == 0.0 or shifts[-1] < shifts[0], (
            "TC-55: shifts must decrease as temperature approaches lower bound"
        )
        assert all(s >= 0.0 for s in shifts), "Shift must never be negative"


# ---------------------------------------------------------------------------
# TC-56 — BMS unconditional override
# ---------------------------------------------------------------------------

class TestPreStagingBMSOverride:
    """TC-56: BMS override is unconditional — no pre-staging occurs regardless
    of gap size, inlet temperature, or max_shift_mw.
    """

    def _engine(self, bms_override_in_config: bool = False) -> PreStagingEngine:
        config = PreStagingConfig(
            max_shift_mw=5.0,
            inlet_temp_low_c=18.0,
            inlet_temp_high_c=24.0,
            cooling_gain_c_per_mw_s=0.05,
            warmup_rate_c_per_s=0.002,
            initial_temp_c=22.0,   # well within band, pre-cooling possible
            bms_override=bms_override_in_config,
        )
        return PreStagingEngine(config)

    def test_tc56_runtime_override_blocks_shift(self) -> None:
        """TC-56: bms_override=True at call time → 0.0 regardless of gap."""
        engine = self._engine(bms_override_in_config=False)
        shift = engine.compute_shift(gap_mw=10.0, bms_override=True,
                                     sim_time=0.0, dt_seconds=5.0)
        assert shift == 0.0, (
            "TC-56: BMS override=True at runtime must return 0.0 unconditionally"
        )

    def test_tc56_config_override_blocks_shift(self) -> None:
        """TC-56: bms_override=True in config → 0.0 regardless of call argument."""
        engine = self._engine(bms_override_in_config=True)
        shift = engine.compute_shift(gap_mw=10.0, bms_override=False,
                                     sim_time=0.0, dt_seconds=5.0)
        assert shift == 0.0, (
            "TC-56: BMS override=True in PreStagingConfig must block shift "
            "even when the runtime call passes bms_override=False"
        )

    def test_tc56_override_applies_at_any_temperature(self) -> None:
        """TC-56: override blocks shift even at high temperature (lots of headroom)."""
        config = PreStagingConfig(
            max_shift_mw=10.0,
            inlet_temp_low_c=18.0,
            inlet_temp_high_c=24.0,
            cooling_gain_c_per_mw_s=0.1,
            warmup_rate_c_per_s=0.001,
            initial_temp_c=23.9,   # maximum headroom
            bms_override=False,
        )
        engine = PreStagingEngine(config)
        shift = engine.compute_shift(gap_mw=50.0, bms_override=True,
                                     sim_time=0.0, dt_seconds=5.0)
        assert shift == 0.0, "Override at max headroom must still return 0.0"

    def test_tc56_override_true_then_false_resumes(self) -> None:
        """TC-56: after override clears, pre-staging resumes (BMS sends point-in-time
        override, not a permanent latch).
        """
        engine = self._engine(bms_override_in_config=False)
        # Tick with override ON.
        shift_override = engine.compute_shift(gap_mw=5.0, bms_override=True,
                                              sim_time=0.0, dt_seconds=5.0)
        assert shift_override == 0.0
        # Tick with override OFF — shift should resume (temperature is still in band).
        shift_normal = engine.compute_shift(gap_mw=5.0, bms_override=False,
                                            sim_time=5.0, dt_seconds=5.0)
        assert shift_normal > 0.0, (
            "TC-56: once BMS override clears, pre-staging must resume"
        )
