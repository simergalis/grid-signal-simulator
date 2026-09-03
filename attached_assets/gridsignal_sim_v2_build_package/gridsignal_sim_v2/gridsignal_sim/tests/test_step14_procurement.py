"""
tests/test_step14_procurement.py — Step 14 procurement tests.

TC-47  Non-firm spot import reduces served load but does NOT close the
       reserve gap.
TC-52  ReservationProposal.requires_confirmation is always True — never
       autonomous at any tier (§24.3).
"""
from __future__ import annotations

import pytest

from core.procurement import (
    CapacityType,
    GridCapacity,
    NonFirmImportEffect,
    PricePoint,
    ReservationProposal,
    SyntheticPriceCurve,
)
from runtime.advisory_gate import AdvisoryGate, VALID_PROPOSAL_KINDS, make_proposal


# ===========================================================================
# TC-47: Non-firm import mechanics
# ===========================================================================

class TestTC47NonFirmImport:
    """TC-47: non-firm spot import reduces served load, does NOT close reserve gap."""

    def test_served_load_reduced_by_import(self) -> None:
        new_served, new_gap = NonFirmImportEffect.apply(
            served_load_mw=10.0,
            import_mw=3.0,
            reserve_gap_mw=5.0,
        )
        assert new_served == pytest.approx(7.0)

    def test_reserve_gap_unchanged(self) -> None:
        """TC-47: the reserve gap is NOT reduced by non-firm import."""
        _, new_gap = NonFirmImportEffect.apply(
            served_load_mw=10.0,
            import_mw=3.0,
            reserve_gap_mw=5.0,
        )
        assert new_gap == pytest.approx(5.0), (
            f"TC-47: reserve_gap must be unchanged after non-firm import; got {new_gap}"
        )

    def test_import_exceeding_load_clamps_to_zero(self) -> None:
        """Served load cannot go negative — clamp at 0."""
        new_served, new_gap = NonFirmImportEffect.apply(
            served_load_mw=2.0,
            import_mw=5.0,
            reserve_gap_mw=3.0,
        )
        assert new_served == pytest.approx(0.0)
        assert new_gap == pytest.approx(3.0)    # TC-47: gap still unchanged

    def test_zero_import_no_change(self) -> None:
        new_served, new_gap = NonFirmImportEffect.apply(
            served_load_mw=10.0,
            import_mw=0.0,
            reserve_gap_mw=5.0,
        )
        assert new_served == pytest.approx(10.0)
        assert new_gap == pytest.approx(5.0)

    def test_large_import_gap_still_intact(self) -> None:
        """TC-47: even a very large import cannot close the reserve gap."""
        _, new_gap = NonFirmImportEffect.apply(
            served_load_mw=100.0,
            import_mw=100.0,
            reserve_gap_mw=20.0,
        )
        assert new_gap == pytest.approx(20.0)

    def test_negative_import_raises(self) -> None:
        with pytest.raises(ValueError, match="import_mw"):
            NonFirmImportEffect.apply(
                served_load_mw=10.0,
                import_mw=-1.0,
                reserve_gap_mw=5.0,
            )

    def test_reserve_gap_closed_by_non_firm_always_zero(self) -> None:
        """The helper method always returns 0 — semantic test for TC-47."""
        closed = NonFirmImportEffect.reserve_gap_closed_by_non_firm(
            import_mw=50.0,
            reserve_gap_mw=10.0,
        )
        assert closed == 0.0

    def test_non_firm_capacity_type_does_not_close_gap(self) -> None:
        """GridCapacity with NON_FIRM type — reserve gap semantics checked."""
        cap = GridCapacity(
            capacity_type=CapacityType.NON_FIRM,
            available_mw=10.0,
            price_per_mwh=200.0,
        )
        _, remaining_gap = NonFirmImportEffect.apply(
            served_load_mw=20.0,
            import_mw=cap.available_mw,
            reserve_gap_mw=8.0,
        )
        assert remaining_gap == pytest.approx(8.0)   # TC-47

    def test_firm_and_reserved_would_close_gap_conceptually(self) -> None:
        """Contrasting: FIRM/RESERVED capacity CAN close a reserve gap (TC-47 doesn't apply)."""
        firm = GridCapacity(capacity_type=CapacityType.FIRM, available_mw=10.0)
        reserved = GridCapacity(capacity_type=CapacityType.RESERVED, available_mw=8.0,
                                t_reserve_s=300.0)
        # These types are not FIRM/NON-FIRM — they can back commitments.
        # TC-47 only restricts NON_FIRM; this test documents the distinction.
        assert firm.capacity_type == CapacityType.FIRM
        assert reserved.capacity_type == CapacityType.RESERVED


# ===========================================================================
# TC-52: ReservationProposal always requires confirmation
# ===========================================================================

class TestTC52ReservationProposalNeverAutonomous:
    """TC-52: ReservationProposal is NEVER autonomous at any tier (§24.3)."""

    def test_requires_confirmation_always_true(self) -> None:
        """TC-52: requires_confirmation is always True."""
        p = ReservationProposal(
            capacity_type=CapacityType.FIRM,
            requested_mw=5.0,
            estimated_cost=55.0,
            rationale="test reservation",
        )
        assert p.requires_confirmation is True, (
            "TC-52: ReservationProposal.requires_confirmation must always be True"
        )

    def test_requires_confirmation_non_firm_still_true(self) -> None:
        """TC-52: even a spot-price non-firm reservation requires confirmation."""
        p = ReservationProposal(
            capacity_type=CapacityType.NON_FIRM,
            requested_mw=1.0,
            rationale="non-firm spot",
        )
        assert p.requires_confirmation is True

    def test_requires_confirmation_reserved_with_t_reserve_still_true(self) -> None:
        p = ReservationProposal(
            capacity_type=CapacityType.RESERVED,
            requested_mw=10.0,
            t_reserve_s=300.0,
        )
        assert p.requires_confirmation is True

    def test_gate_validates_reservation_kind(self) -> None:
        """'reservation' is in VALID_PROPOSAL_KINDS (added in Step 14)."""
        assert "reservation" in VALID_PROPOSAL_KINDS, (
            "'reservation' must be in VALID_PROPOSAL_KINDS for the gate to accept "
            "ReservationProposal from a ProcurementAgent"
        )

    def test_gate_accepts_reservation_proposal(self) -> None:
        """Advisory gate accepts a proposal with kind='reservation'."""
        from runtime.advisory_gate import Proposal, ProposalState
        gate = AdvisoryGate()
        p = make_proposal(
            kind="reservation",
            estimated_impact_mw=5.0,
            confidence=0.8,
            reasoning="need to reserve firm capacity",
            created_at_sim_time=0.0,
        )
        gate.validate(p)
        assert p.state == ProposalState.PENDING

    def test_gate_accept_path_requires_explicit_call(self) -> None:
        """TC-52: reservation proposal does NOT auto-advance to ACCEPTED."""
        from runtime.advisory_gate import Proposal, ProposalState
        gate = AdvisoryGate()
        p = make_proposal(
            kind="reservation",
            estimated_impact_mw=2.0,
            confidence=0.7,
            reasoning="reserve for peak",
            created_at_sim_time=0.0,
        )
        gate.validate(p)
        # After validation, state is still PENDING — not auto-accepted.
        assert p.state == ProposalState.PENDING

    def test_gate_accept_records_reviewer(self) -> None:
        """O2: accepting a reservation proposal records the reviewer identity."""
        from runtime.advisory_gate import Proposal, ProposalState
        gate = AdvisoryGate()
        p = make_proposal(
            kind="reservation",
            estimated_impact_mw=3.0,
            confidence=0.9,
            reasoning="firm capacity for peak hour",
            created_at_sim_time=0.0,
        )
        gate.validate(p)
        gate.accept(p.proposal_id, reviewer_id="ops-lead@example.com",
                    accepted_at_sim_time=600.0)
        assert p.state == ProposalState.ACCEPTED
        assert p.reviewer_id == "ops-lead@example.com"
        assert p.accepted_at_sim_time == pytest.approx(600.0)


# ===========================================================================
# Synthetic price curve
# ===========================================================================

class TestSyntheticPriceCurve:
    """Basic sanity checks on the seeded synthetic price curve."""

    def test_price_in_reasonable_range(self) -> None:
        curve = SyntheticPriceCurve(seed=42)
        for t in range(0, 86400, 3600):
            price = curve.price_at(float(t))
            assert 10.0 <= price <= 120.0, (
                f"price_at({t}) = {price} is outside reasonable range"
            )

    def test_different_seeds_differ(self) -> None:
        c1 = SyntheticPriceCurve(seed=1)
        c2 = SyntheticPriceCurve(seed=10)
        prices1 = [c1.price_at(float(t)) for t in range(0, 3600, 300)]
        prices2 = [c2.price_at(float(t)) for t in range(0, 3600, 300)]
        assert prices1 != prices2

    def test_deterministic_for_same_seed(self) -> None:
        c1 = SyntheticPriceCurve(seed=7)
        c2 = SyntheticPriceCurve(seed=7)
        assert [c1.price_at(float(t)) for t in range(0, 3600)] == \
               [c2.price_at(float(t)) for t in range(0, 3600)]

    def test_points_count(self) -> None:
        curve = SyntheticPriceCurve(seed=42)
        pts = curve.points(0.0, 3600.0, n=12)
        assert len(pts) == 12
        assert all(isinstance(p, PricePoint) for p in pts)

    def test_average_price_between_bounds(self) -> None:
        curve = SyntheticPriceCurve(seed=42)
        avg = curve.average_price(0.0, 86400.0)
        assert 10.0 <= avg <= 120.0
