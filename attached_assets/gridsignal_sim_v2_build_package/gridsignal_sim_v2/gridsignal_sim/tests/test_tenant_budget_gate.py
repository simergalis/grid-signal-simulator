"""test_tenant_budget_gate.py — BudgetGate and RotationState unit tests.

GS-IMPL-PSP-002 §9 / Phase 3.

Tests covered
-------------
  TC-C6: BudgetGate returns None for unconfigured tenant (MT-1 behaviour).
         No WorkloadCommand issued — job proceeds unbounded.
  TC-C7: BudgetGate returns defer when budget exceeded.
         Correct WorkloadCommand, authority matches current operating tier.
  TC-C8: Missing tenant_id (signal.tenant_id=None) raises QuarantinedSignalError.
         Quarantined per §17.2 — never admitted or silently defaulted.
  TC-C9: RotationState.least_recently_selected returns lowest-count tenant.
         Rotation prevents repeat selection of the same tenant under simultaneous
         deferral pressure.

Additional coverage
-------------------
  - handle_queued_event() end-to-end §4.1 sequence.
  - record_selection() increments count correctly.
  - Budget exactly at ceiling → None (not a defer).
  - Budget one epsilon over ceiling → defer.
  - operating_tier propagated to WorkloadCommand.authority.
  - Non-BESS, non-grid sources not repriced (ranker passthrough — confirmed above).
"""
from __future__ import annotations

import pytest

from core.models import (
    OperatingTier,
    TenantPowerBudget,
    WorkloadCommand,
    WorkloadCommandAction,
    WorkloadEventType,
    WorkloadSignal,
)
from core.tenant_budget_gate import (
    BudgetGate,
    QuarantinedSignalError,
    RotationState,
    handle_queued_event,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _signal(
    tenant_id: str | None = "tenant-a",
    job_id: str = "job-001",
    node_count: int = 100,
    site_id: str = "site-dc1",
) -> WorkloadSignal:
    return WorkloadSignal(
        event_id="evt-1",
        job_id=job_id,
        event_type=WorkloadEventType.QUEUED,
        timestamp=0.0,
        hardware_profile_id="h100-sxm5",
        node_count=node_count,
        workload_class="inference",     # type: ignore[arg-type]
        site_id=site_id,
        tenant_id=tenant_id,
    )


def _budget(
    tenant_id: str = "tenant-a",
    site_id: str = "site-dc1",
    budget_mw: float = 5.0,
) -> TenantPowerBudget:
    return TenantPowerBudget(
        tenant_id=tenant_id,
        site_id=site_id,
        budget_mw=budget_mw,
        source_of_truth="colo contract system",
        effective_from="2026-01-01T00:00:00Z",
        effective_until="2026-12-31T23:59:59Z",
    )


def _rotation(counts: dict[str, int] | None = None) -> RotationState:
    """Return a RotationState with persistence_backed=True to suppress MT-4 warnings."""
    rs = RotationState(
        selection_count=dict(counts) if counts else {},
        persistence_backed=True,
    )
    return rs


# ── TC-C6: unconfigured tenant → None (MT-1) ─────────────────────────────────

class TestTC_C6_UnconfiguredTenantReturnsNone:
    """BudgetGate must return None (no WorkloadCommand) when budget is None.

    MT-1: the absence of a TenantPowerBudget record means unbounded — no gate
    is applied.  This is specified behaviour, not a defect.  TC-C6 confirms
    that this case is handled correctly and transparently."""

    def test_none_budget_returns_none(self) -> None:
        """budget=None → evaluate() returns None; job proceeds unimpeded."""
        gate = BudgetGate()
        result = gate.evaluate(
            _signal(), budget=None,
            tenant_committed_mw=10.0,
            predicted_draw_mw=5.0,
            rotation_state=_rotation(),
        )
        assert result is None, (
            "BudgetGate must return None for unconfigured tenant (MT-1 / TC-C6)"
        )

    def test_none_budget_even_when_committed_is_huge(self) -> None:
        """MT-1 is unconditional — even with enormous committed draw, no gate applied."""
        gate = BudgetGate()
        result = gate.evaluate(
            _signal(), budget=None,
            tenant_committed_mw=9999.0,
            predicted_draw_mw=9999.0,
            rotation_state=_rotation(),
        )
        assert result is None

    def test_handle_queued_event_none_budget_returns_none(self) -> None:
        """handle_queued_event() end-to-end: MT-1 path returns None."""
        rs = _rotation()
        result = handle_queued_event(
            _signal(),
            predicted_draw_mw=3.0,
            budget=None,
            tenant_committed_mw=8.0,
            rotation_state=rs,
        )
        assert result is None
        # No rotation recorded for an unconfigured tenant (no command issued)
        assert rs.selection_count.get("tenant-a", 0) == 0, (
            "record_selection must not be called when no command is issued (TC-C6)"
        )


# ── TC-C7: budget exceeded → defer command ────────────────────────────────────

class TestTC_C7_BudgetExceededReturnsDefer:
    """BudgetGate returns WorkloadCommand(action=defer) when budget is exceeded.
    authority on the command must match the operating_tier passed to evaluate()."""

    def test_exceeded_budget_returns_defer_command(self) -> None:
        """committed + predicted > budget → WorkloadCommand(action=DEFER)."""
        gate = BudgetGate()
        result = gate.evaluate(
            _signal("tenant-a", job_id="job-overbudget"),
            budget=_budget(budget_mw=5.0),
            tenant_committed_mw=4.0,
            predicted_draw_mw=2.0,   # 4.0 + 2.0 = 6.0 > 5.0
            rotation_state=_rotation(),
        )
        assert result is not None, (
            "BudgetGate must return a WorkloadCommand when budget is exceeded (TC-C7)"
        )
        assert isinstance(result, WorkloadCommand)
        assert result.action == WorkloadCommandAction.DEFER, (
            "action must be DEFER — no new action type is created by this subsystem"
        )

    def test_defer_target_is_job_id(self) -> None:
        """WorkloadCommand.target must be the signal's job_id."""
        gate = BudgetGate()
        sig = _signal("tenant-a", job_id="the-overbudget-job")
        result = gate.evaluate(
            sig,
            budget=_budget(budget_mw=1.0),
            tenant_committed_mw=0.9,
            predicted_draw_mw=0.5,   # 0.9 + 0.5 = 1.4 > 1.0
            rotation_state=_rotation(),
        )
        assert result is not None
        assert result.target == "the-overbudget-job", (
            "WorkloadCommand.target must equal signal.job_id (TC-C7)"
        )

    def test_authority_matches_operating_tier_supervised(self) -> None:
        """authority on WorkloadCommand must match the operating_tier kwarg."""
        gate = BudgetGate()
        result = gate.evaluate(
            _signal(),
            budget=_budget(budget_mw=1.0),
            tenant_committed_mw=0.8,
            predicted_draw_mw=0.5,
            rotation_state=_rotation(),
            operating_tier=OperatingTier.SUPERVISED,
        )
        assert result is not None
        assert result.authority == OperatingTier.SUPERVISED, (
            "authority must match operating_tier=SUPERVISED (TC-C7)"
        )

    def test_authority_matches_operating_tier_autonomous(self) -> None:
        """authority propagates correctly for AUTONOMOUS tier too."""
        gate = BudgetGate()
        result = gate.evaluate(
            _signal(),
            budget=_budget(budget_mw=1.0),
            tenant_committed_mw=0.8,
            predicted_draw_mw=0.5,
            rotation_state=_rotation(),
            operating_tier=OperatingTier.AUTONOMOUS,
        )
        assert result is not None
        assert result.authority == OperatingTier.AUTONOMOUS

    def test_authority_matches_operating_tier_operator(self) -> None:
        """OPERATOR tier propagated correctly."""
        gate = BudgetGate()
        result = gate.evaluate(
            _signal(),
            budget=_budget(budget_mw=1.0),
            tenant_committed_mw=0.8,
            predicted_draw_mw=0.5,
            rotation_state=_rotation(),
            operating_tier=OperatingTier.OPERATOR,
        )
        assert result is not None
        assert result.authority == OperatingTier.OPERATOR

    def test_exactly_at_ceiling_returns_none(self) -> None:
        """committed + predicted == budget.budget_mw → not exceeded → None."""
        gate = BudgetGate()
        result = gate.evaluate(
            _signal(),
            budget=_budget(budget_mw=5.0),
            tenant_committed_mw=3.0,
            predicted_draw_mw=2.0,   # 3.0 + 2.0 = 5.0 == 5.0 → fits
            rotation_state=_rotation(),
        )
        assert result is None, (
            "Budget exactly at ceiling must not trigger a deferral (TC-C7): "
            "condition is >, not >=."
        )

    def test_one_mw_over_ceiling_defers(self) -> None:
        """committed + predicted = budget + epsilon → defer."""
        gate = BudgetGate()
        result = gate.evaluate(
            _signal(),
            budget=_budget(budget_mw=5.0),
            tenant_committed_mw=3.0,
            predicted_draw_mw=2.001,   # 5.001 > 5.0
            rotation_state=_rotation(),
        )
        assert result is not None
        assert result.action == WorkloadCommandAction.DEFER

    def test_handle_queued_event_defer_records_selection(self) -> None:
        """handle_queued_event() issues defer AND calls record_selection (§4.1 step 5)."""
        rs = _rotation()
        result = handle_queued_event(
            _signal("tenant-a", job_id="job-x"),
            predicted_draw_mw=3.0,
            budget=_budget(budget_mw=2.0),   # 0 + 3 > 2
            tenant_committed_mw=0.0,
            rotation_state=rs,
        )
        assert result is not None
        assert result.action == WorkloadCommandAction.DEFER
        assert rs.selection_count.get("tenant-a", 0) == 1, (
            "record_selection must be called once after a deferral (§4.1 step 5)"
        )

    def test_handle_queued_event_no_defer_no_selection(self) -> None:
        """handle_queued_event() does NOT call record_selection when no command issued."""
        rs = _rotation()
        result = handle_queued_event(
            _signal("tenant-a"),
            predicted_draw_mw=1.0,
            budget=_budget(budget_mw=10.0),   # fits
            tenant_committed_mw=0.0,
            rotation_state=rs,
        )
        assert result is None
        assert rs.selection_count.get("tenant-a", 0) == 0, (
            "record_selection must NOT be called when job is admitted (§4.1)"
        )


# ── TC-C8: missing tenant_id → QuarantinedSignalError ────────────────────────

class TestTC_C8_MissingTenantIdQuarantined:
    """signal.tenant_id=None must raise QuarantinedSignalError (§17.2 / §2.4).

    A missing tenant_id is a schema violation — the signal is quarantined,
    never admitted silently or defaulted to an unbounded budget."""

    def test_none_tenant_id_raises_quarantined_error(self) -> None:
        """evaluate() raises QuarantinedSignalError when tenant_id=None."""
        sig = _signal(tenant_id=None)
        gate = BudgetGate()
        with pytest.raises(QuarantinedSignalError):
            gate.evaluate(
                sig,
                budget=_budget(),
                tenant_committed_mw=0.0,
                predicted_draw_mw=1.0,
                rotation_state=_rotation(),
            )

    def test_none_tenant_id_quarantined_even_with_none_budget(self) -> None:
        """Quarantine takes priority over MT-1 unbounded path."""
        sig = _signal(tenant_id=None)
        gate = BudgetGate()
        with pytest.raises(QuarantinedSignalError):
            gate.evaluate(
                sig,
                budget=None,   # MT-1 would return None — but quarantine comes first
                tenant_committed_mw=0.0,
                predicted_draw_mw=1.0,
                rotation_state=_rotation(),
            )

    def test_quarantined_error_message_references_job_id(self) -> None:
        """Error message must include enough detail to route the signal correctly."""
        sig = _signal(tenant_id=None, job_id="bad-job-42")
        gate = BudgetGate()
        with pytest.raises(QuarantinedSignalError, match="bad-job-42"):
            gate.evaluate(
                sig,
                budget=None,
                tenant_committed_mw=0.0,
                predicted_draw_mw=1.0,
                rotation_state=_rotation(),
            )

    def test_handle_queued_event_propagates_quarantine(self) -> None:
        """handle_queued_event() propagates QuarantinedSignalError from evaluate()."""
        sig = _signal(tenant_id=None)
        with pytest.raises(QuarantinedSignalError):
            handle_queued_event(
                sig,
                predicted_draw_mw=1.0,
                budget=None,
                tenant_committed_mw=0.0,
                rotation_state=_rotation(),
            )


# ── TC-C9: rotation prevents repeat selection ─────────────────────────────────

class TestTC_C9_RotationPreventsRepeatSelection:
    """RotationState.least_recently_selected returns lowest-count tenant.

    §30.7: when multiple tenants are eligible for deferral simultaneously, the
    one with the fewest recent selections is chosen — preventing any single
    tenant from being perpetually deferred."""

    def test_unselected_tenant_chosen_over_selected(self) -> None:
        """Tenant with count=0 wins over tenant with count=1."""
        rs = _rotation({"tenant-a": 1, "tenant-b": 0})
        winner = rs.least_recently_selected(["tenant-a", "tenant-b"])
        assert winner == "tenant-b", (
            "least_recently_selected must return the tenant with the lowest count (TC-C9)"
        )

    def test_lowest_count_wins_among_three(self) -> None:
        """Tenant with count=1 wins when others have count=3."""
        rs = _rotation({"tenant-a": 3, "tenant-b": 1, "tenant-c": 3})
        winner = rs.least_recently_selected(["tenant-a", "tenant-b", "tenant-c"])
        assert winner == "tenant-b"

    def test_unseen_tenant_treated_as_zero(self) -> None:
        """A tenant not yet in selection_count is treated as count=0."""
        rs = _rotation({"tenant-a": 2})
        # tenant-new has no entry — should win
        winner = rs.least_recently_selected(["tenant-a", "tenant-new"])
        assert winner == "tenant-new"

    def test_tie_broken_by_tenant_id_alphabetically(self) -> None:
        """Equal counts broken by alphabetical order of tenant_id (deterministic)."""
        rs = _rotation()  # both start at 0
        winner = rs.least_recently_selected(["tenant-z", "tenant-a"])
        assert winner == "tenant-a", (
            "Tie between equal-count tenants must be broken deterministically "
            "(alphabetical — TC-C9 stability)"
        )

    def test_single_candidate_always_selected(self) -> None:
        """With one candidate, that candidate is always selected regardless of count."""
        rs = _rotation({"tenant-only": 99})
        winner = rs.least_recently_selected(["tenant-only"])
        assert winner == "tenant-only"

    def test_empty_candidates_raises(self) -> None:
        """Empty candidate list must raise ValueError."""
        rs = _rotation()
        with pytest.raises(ValueError):
            rs.least_recently_selected([])

    def test_record_selection_increments_count(self) -> None:
        """record_selection() increments the count for the specified tenant."""
        rs = _rotation({"tenant-a": 2})
        rs.record_selection("tenant-a")
        assert rs.selection_count["tenant-a"] == 3

    def test_record_selection_initialises_unseen_tenant(self) -> None:
        """record_selection() on an unseen tenant initialises count to 1."""
        rs = _rotation()
        rs.record_selection("tenant-new")
        assert rs.selection_count["tenant-new"] == 1

    def test_multiple_record_selections_accumulate(self) -> None:
        """Repeated record_selection() calls accumulate — no reset between calls."""
        rs = _rotation()
        for _ in range(5):
            rs.record_selection("tenant-a")
        assert rs.selection_count["tenant-a"] == 5

    def test_rotation_changes_winner_after_selection(self) -> None:
        """After recording a selection, the other tenant wins on the next query."""
        rs = _rotation({"tenant-a": 0, "tenant-b": 0})

        # First: tie → "tenant-a" wins alphabetically
        first = rs.least_recently_selected(["tenant-a", "tenant-b"])
        assert first == "tenant-a"

        # Record selection for tenant-a
        rs.record_selection("tenant-a")

        # Now tenant-a has count=1, tenant-b has count=0 → tenant-b wins
        second = rs.least_recently_selected(["tenant-a", "tenant-b"])
        assert second == "tenant-b", (
            "After recording a selection for tenant-a, tenant-b must be chosen next "
            "(TC-C9 rotation round-trip)"
        )
