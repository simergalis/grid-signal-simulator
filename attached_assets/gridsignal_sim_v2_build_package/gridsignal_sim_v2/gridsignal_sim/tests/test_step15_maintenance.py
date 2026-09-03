"""
tests/test_step15_maintenance.py — Step 15 gate tests for §27 prescriptive maintenance.

TC-58  Reserve arithmetic uses the re-rated ramp figure.
TC-59  Maintenance window validation covers the FULL duration, not just the start instant.
TC-60  Rating raises require an observation window + explicit confirmation.
       Rating reductions require neither.
"""
from __future__ import annotations

import pytest

from core.maintenance import (
    AssetAvailability,
    AssetHealthRecord,
    MaintenanceScheduler,
    MaintenanceWindow,
    RatingChangeKind,
    RatingProposal,
    reserve_contribution_mw_per_s,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _turbine(
    asset_id: str = "turbine-0",
    nameplate: float = 0.20,
    effective: float | None = None,
    availability: AssetAvailability = AssetAvailability.OPERATIONAL,
    favorable_ticks: int = 0,
) -> AssetHealthRecord:
    return AssetHealthRecord(
        asset_id=asset_id,
        availability=availability,
        nameplate_ramp_mw_per_s=nameplate,
        effective_ramp_mw_per_s=effective if effective is not None else nameplate,
        favorable_observation_ticks=favorable_ticks,
    )


def _window(
    start: float = 0.0,
    end: float = 60.0,
    window_id: str = "maint-001",
    asset_id: str = "turbine-0",
) -> MaintenanceWindow:
    return MaintenanceWindow(
        asset_id=asset_id,
        window_id=window_id,
        start_sim_time=start,
        end_sim_time=end,
    )


# ---------------------------------------------------------------------------
# TC-58: reserve arithmetic uses re-rated ramp figure
# ---------------------------------------------------------------------------

class TestTC58ReserveUsesReratedRamp:

    def test_no_rerate_uses_nameplate(self) -> None:
        """Before re-rating, reserve_contribution == nameplate."""
        record = _turbine(nameplate=0.20)
        assert reserve_contribution_mw_per_s(record) == pytest.approx(0.20)

    def test_after_lower_uses_rerated_not_nameplate(self) -> None:
        """TC-58: after a downward re-rating, contribution uses 0.16, not 0.20."""
        record = _turbine(nameplate=0.20, effective=0.20)
        scheduler = MaintenanceScheduler()
        proposal = scheduler.propose_rating_change(record, proposed_ramp_mw_per_s=0.16)
        scheduler.apply_confirmed_rating(record, proposal)

        contribution = reserve_contribution_mw_per_s(record)
        assert contribution == pytest.approx(0.16), (
            f"TC-58: expected re-rated 0.16 MW/s, got {contribution}"
        )
        # Explicitly verify it is NEITHER the nameplate NOR zero (excluded)
        assert contribution != pytest.approx(0.20), "TC-58: must not use nameplate"
        assert contribution != pytest.approx(0.0),  "TC-58: must not exclude asset"

    def test_degraded_asset_still_contributes_rerated(self) -> None:
        """DEGRADED asset is dispatch-eligible and contributes at effective rate."""
        record = _turbine(
            nameplate=0.20,
            effective=0.12,
            availability=AssetAvailability.DEGRADED,
        )
        assert reserve_contribution_mw_per_s(record) == pytest.approx(0.12)

    def test_maintenance_asset_excluded_from_reserve(self) -> None:
        """TC-58 exclusion: MAINTENANCE asset contributes 0."""
        record = _turbine(nameplate=0.20, availability=AssetAvailability.MAINTENANCE)
        assert reserve_contribution_mw_per_s(record) == pytest.approx(0.0)

    def test_failed_asset_excluded_from_reserve(self) -> None:
        """TC-58 exclusion: FAILED asset contributes 0."""
        record = _turbine(nameplate=0.20, availability=AssetAvailability.FAILED)
        assert reserve_contribution_mw_per_s(record) == pytest.approx(0.0)

    def test_multiple_rerate_steps_each_step_reflected(self) -> None:
        """Sequential re-ratings: each step changes the contribution."""
        record = _turbine(nameplate=0.20, effective=0.20)
        scheduler = MaintenanceScheduler()

        scheduler.apply_confirmed_rating(
            record, scheduler.propose_rating_change(record, 0.18)
        )
        assert reserve_contribution_mw_per_s(record) == pytest.approx(0.18)

        scheduler.apply_confirmed_rating(
            record, scheduler.propose_rating_change(record, 0.15)
        )
        assert reserve_contribution_mw_per_s(record) == pytest.approx(0.15)

    def test_rerate_to_nameplate_restores_operational(self) -> None:
        """Re-rating back to nameplate restores OPERATIONAL availability."""
        record = _turbine(nameplate=0.20, effective=0.16,
                          availability=AssetAvailability.DEGRADED)
        scheduler = MaintenanceScheduler()
        # Raise back to nameplate (requires confirmation — but apply_confirmed
        # applies whatever proposal is passed)
        record.favorable_observation_ticks = 30   # enough evidence
        proposal = scheduler.propose_rating_change(record, 0.20)
        assert proposal.kind == RatingChangeKind.RAISE
        scheduler.apply_confirmed_rating(record, proposal)
        assert record.effective_ramp_mw_per_s == pytest.approx(0.20)
        assert record.availability == AssetAvailability.OPERATIONAL


# ---------------------------------------------------------------------------
# TC-59: full-duration maintenance window validation
# ---------------------------------------------------------------------------

class TestTC59FullDurationValidation:

    def test_rejects_window_ending_in_step_load(self) -> None:
        """TC-59: window beginning in trough but ending in step-load is REJECTED."""
        scheduler = MaintenanceScheduler()
        record = _turbine()
        window = _window(start=0.0, end=60.0)

        # Trough at start (ample headroom), step-load at end (insufficient).
        forecast = [
            (0.0,  5.0,  15.0),   # headroom = 10 MW — fine
            (20.0, 6.0,  14.0),   # headroom = 8 MW  — fine
            (30.0, 18.0,  2.0),   # headroom = -16 MW — FAIL
            (50.0, 19.0,  1.0),   # headroom = -18 MW — FAIL
        ]
        valid = scheduler.validate_window(
            record, window,
            forecast_ticks=forecast,
            reserve_threshold_mw=5.0,
        )
        assert not valid, "TC-59: full-duration check must reject step-load at end"
        assert window.rejection_reason != "", "TC-59: rejection_reason must be populated"
        assert not window.forecast_validated

    def test_accepts_window_in_trough_only(self) -> None:
        """TC-59: window entirely within a demand trough is ACCEPTED."""
        scheduler = MaintenanceScheduler()
        record = _turbine()
        window = _window(start=0.0, end=60.0)

        forecast = [
            (0.0,  4.0,  16.0),   # headroom = 12 MW — fine
            (20.0, 5.0,  15.0),   # headroom = 10 MW — fine
            (40.0, 6.0,  14.0),   # headroom = 8 MW  — fine
            (60.0, 5.0,  15.0),   # headroom = 10 MW — fine
        ]
        valid = scheduler.validate_window(
            record, window,
            forecast_ticks=forecast,
            reserve_threshold_mw=5.0,
        )
        assert valid
        assert window.forecast_validated
        assert window.rejection_reason == ""

    def test_start_only_check_would_give_false_positive(self) -> None:
        """TC-59: demonstrate that start-only check gives a false positive.

        The window passes at t=start (deep trough) but fails at t=end
        (step-load).  Full-duration check catches it; start-only would not.
        """
        scheduler = MaintenanceScheduler()
        record = _turbine()
        window = _window(start=0.0, end=60.0)

        forecast = [
            (0.0,  3.0,  17.0),   # START: headroom = 14 MW — false positive if start-only
            (60.0, 20.0,  0.0),   # END:   headroom = -20 MW — FAIL
        ]
        valid = scheduler.validate_window(
            record, window,
            forecast_ticks=forecast,
            reserve_threshold_mw=5.0,
        )
        # Full-duration check catches the end-of-window failure.
        assert not valid

        # Prove the start-only check would have passed.
        start_t, start_demand, start_capacity = forecast[0]
        start_headroom = start_capacity - start_demand
        assert start_headroom >= 5.0, (
            f"Start-only headroom={start_headroom} should pass threshold=5.0 "
            f"(confirms TC-59 value: start-only is a false positive)"
        )

    def test_ticks_outside_window_are_ignored(self) -> None:
        """Forecast ticks before start or after end do not affect validation."""
        scheduler = MaintenanceScheduler()
        record = _turbine()
        window = _window(start=30.0, end=60.0)

        forecast = [
            # Outside window — bad headroom but should be ignored
            (10.0, 25.0, -5.0),
            (25.0, 20.0, -2.0),
            # Inside window — fine
            (30.0,  4.0, 16.0),
            (45.0,  5.0, 15.0),
            (60.0,  6.0, 14.0),
            # Outside window again
            (70.0, 22.0, -8.0),
        ]
        valid = scheduler.validate_window(
            record, window,
            forecast_ticks=forecast,
            reserve_threshold_mw=5.0,
        )
        assert valid, "Ticks outside window should be ignored"

    def test_empty_forecast_accepts_vacuously(self) -> None:
        """Window with no forecast ticks is accepted (no evidence of failure)."""
        scheduler = MaintenanceScheduler()
        record = _turbine()
        window = _window()
        valid = scheduler.validate_window(
            record, window,
            forecast_ticks=[],
            reserve_threshold_mw=5.0,
        )
        assert valid

    def test_exactly_at_threshold_is_accepted(self) -> None:
        """headroom == threshold is accepted (not strictly less-than)."""
        scheduler = MaintenanceScheduler()
        record = _turbine()
        window = _window()
        forecast = [(10.0, 10.0, 15.0)]  # headroom = 5.0 == threshold
        valid = scheduler.validate_window(
            record, window,
            forecast_ticks=forecast,
            reserve_threshold_mw=5.0,
        )
        assert valid


# ---------------------------------------------------------------------------
# TC-60: rating change proposals and direction-dependent confirmation
# ---------------------------------------------------------------------------

class TestTC60RatingProposals:

    def test_reduction_no_confirmation_required(self) -> None:
        """TC-60: rating reductions do not require confirmation."""
        scheduler = MaintenanceScheduler()
        record = _turbine(nameplate=0.20, effective=0.20)
        proposal = scheduler.propose_rating_change(record, proposed_ramp_mw_per_s=0.16)
        assert proposal.kind == RatingChangeKind.LOWER
        assert not proposal.requires_confirmation

    def test_raise_always_requires_confirmation(self) -> None:
        """TC-60: rating raises always require explicit confirmation."""
        scheduler = MaintenanceScheduler()
        record = _turbine(nameplate=0.20, effective=0.16)
        proposal = scheduler.propose_rating_change(record, proposed_ramp_mw_per_s=0.20)
        assert proposal.kind == RatingChangeKind.RAISE
        assert proposal.requires_confirmation   # TC-60: unconditional

    def test_raise_records_observation_ticks(self) -> None:
        """TC-60: the proposal captures observation_ticks_at_proposal."""
        scheduler = MaintenanceScheduler()
        record = _turbine(nameplate=0.20, effective=0.16, favorable_ticks=7)
        proposal = scheduler.propose_rating_change(record, proposed_ramp_mw_per_s=0.20)
        assert proposal.observation_ticks_at_proposal == 7

    def test_raise_with_insufficient_ticks_is_documented(self) -> None:
        """TC-60: a raise with insufficient ticks carries the evidence count for audit.

        The proposal is still generated (caller decides whether to present it);
        the observation_ticks_at_proposal < RAISE_CONFIRMATION_TICKS signals
        the evidence gap.
        """
        scheduler = MaintenanceScheduler()
        threshold = AssetHealthRecord.RAISE_CONFIRMATION_TICKS
        record = _turbine(nameplate=0.20, effective=0.16,
                          favorable_ticks=threshold - 1)
        proposal = scheduler.propose_rating_change(record, proposed_ramp_mw_per_s=0.20)
        assert proposal.kind == RatingChangeKind.RAISE
        assert proposal.observation_ticks_at_proposal < threshold

    def test_raise_with_sufficient_ticks(self) -> None:
        """TC-60: a raise with sufficient observation ticks."""
        scheduler = MaintenanceScheduler()
        threshold = AssetHealthRecord.RAISE_CONFIRMATION_TICKS
        record = _turbine(nameplate=0.20, effective=0.16,
                          favorable_ticks=threshold)
        proposal = scheduler.propose_rating_change(record, proposed_ramp_mw_per_s=0.20)
        assert proposal.observation_ticks_at_proposal >= threshold
        assert proposal.requires_confirmation   # still true; confirmation not auto-granted

    def test_proposal_asset_id_mismatch_raises(self) -> None:
        """apply_confirmed_rating with wrong asset_id raises ValueError."""
        scheduler = MaintenanceScheduler()
        record = _turbine(asset_id="turbine-0", nameplate=0.20, effective=0.20)
        proposal = RatingProposal(
            asset_id="turbine-99",
            kind=RatingChangeKind.LOWER,
            proposed_ramp_mw_per_s=0.16,
        )
        with pytest.raises(ValueError, match="turbine-99"):
            scheduler.apply_confirmed_rating(record, proposal)

    def test_availability_set_degraded_after_lower(self) -> None:
        """After a downward re-rating, availability becomes DEGRADED."""
        scheduler = MaintenanceScheduler()
        record = _turbine(nameplate=0.20, effective=0.20,
                          availability=AssetAvailability.OPERATIONAL)
        proposal = scheduler.propose_rating_change(record, proposed_ramp_mw_per_s=0.16)
        scheduler.apply_confirmed_rating(record, proposal)
        assert record.availability == AssetAvailability.DEGRADED

    def test_equal_rating_is_raise_direction(self) -> None:
        """A proposed value equal to effective is not a raise — classified as LOWER."""
        scheduler = MaintenanceScheduler()
        record = _turbine(nameplate=0.20, effective=0.16)
        proposal = scheduler.propose_rating_change(record, proposed_ramp_mw_per_s=0.16)
        # Same value: not > effective, so classified as LOWER (conservative).
        assert proposal.kind == RatingChangeKind.LOWER
