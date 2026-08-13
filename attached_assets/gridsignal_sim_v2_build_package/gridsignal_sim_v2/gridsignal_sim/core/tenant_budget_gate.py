"""tenant_budget_gate.py — BudgetGate and RotationState.

GS-IMPL-PSP-002 §3.3 / §30.5–30.7 / §4.1.

Build fresh per spec — no reference implementation existed.  This module
implements the per-tenant power-budget admission check that runs on every
WorkloadSignal(event_type=queued) event, strictly before any dispatch
arbitration (§4.1 ordering rule).

Architecture constraints (hard — enforced by TC-C11)
-----------------------------------------------------
  This file lives in core/.  It MUST NOT import from runtime/ or scripts/.
  BudgetGate never instantiates PMSTestDouble, never calls an LLM, never
  reads a clock.  It is a pure function of its arguments (§6.2).

  No new WorkloadCommand action is created by this subsystem (§6.1 / Phase 3
  scope).  BudgetGate reuses `WorkloadCommandAction.DEFER` only.

MT-1 (§10) — acknowledged, not a bug
--------------------------------------
  A missing TenantPowerBudget record (budget=None) means unbounded — the
  tenant's job proceeds without a power-budget check.  This is specified
  MT-1 behaviour, not a silent default.  See §10 for the recommended
  `unbudgeted_tenant` tag to make this state visible.

MT-4 (§10) — RotationState durability
--------------------------------------
  RotationState.selection_count is Tier 0 state per §22.3 and must survive
  a restart in production.  The in-memory implementation here satisfies the
  simulator path; production use requires persistence.  A loud warning is
  logged at construction when persistence_backed=False (the current default).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from core.models import (
    OperatingTier,
    TenantPowerBudget,
    WorkloadCommand,
    WorkloadCommandAction,
    WorkloadSignal,
)

_log = logging.getLogger(__name__)


# ── Exception ─────────────────────────────────────────────────────────────────

class QuarantinedSignalError(ValueError):
    """Raised when a WorkloadSignal fails §17.2 schema validation.

    BudgetGate.evaluate() raises this when signal.tenant_id is None (missing
    tenant identity).  The job must be quarantined — never silently admitted
    with an unbounded budget (§2.4 / §17.2: "quarantined, never defaulted").

    The caller is responsible for routing the signal to the §17.2 quarantine
    channel rather than the normal admission path.
    """


# ── RotationState (§3.3.1 / §30.7) ──────────────────────────────────────────

@dataclass
class RotationState:
    """Fairness tie-breaker for simultaneous multi-tenant deferrals (§30.7).

    selection_count tracks how many times each tenant_id has been selected for
    a deferral within the rolling window.  When multiple tenants are eligible
    to be deferred in the same cycle, the caller uses least_recently_selected()
    to identify the candidate set (lowest count), then applies its own tiebreak
    using priority class and job age per §3.3.1.

    BudgetGate.evaluate() does NOT call these methods itself — it evaluates
    one job at a time.  The §4.1 handler calls record_selection() after issuing
    a command, and the caller coordinates across multiple simultaneously-queued
    jobs to apply least_recently_selected() as described in §30.7.

    MT-4 durability note
    --------------------
    In production, selection_count must persist across a restart (Tier 0 state,
    §22.3).  This implementation is in-memory only.  A warning is always logged
    at construction — this is intentional and correct.  `persistence_backed` is
    NOT exposed as a settable flag: no backing store exists yet, so setting a
    boolean to True would suppress the warning while nothing durable actually
    happens behind it.  The warning fires unconditionally until MT-4's actual
    implementation lands.  Simulator runs are ephemeral; the warning is harmless
    there and correctly reflects the system's state.
    """
    selection_count: dict[str, int] = field(default_factory=dict)
    window_days: int = 30

    def __post_init__(self) -> None:
        _log.warning(
            "RotationState is running in-memory without persistence backing. "
            "selection_count will be lost on restart (MT-4 / §22.3). "
            "For production use, wire RotationState to durable storage and "
            "remove this warning from the implementation at that time."
        )

    def least_recently_selected(self, candidate_tenant_ids: list[str]) -> list[str]:
        """Return all candidates tied at the lowest selection_count (§3.3.1 / §30.7).

        Returns a list — the caller applies tiebreaking using priority class,
        then job age, per §3.3.1.  This method deliberately does not resolve
        ties itself: it lacks priority-class and job-age information, and
        injecting a heuristic (e.g. alphabetical tenant_id order) would
        silently override the §30.7 fairness intent with a criterion that has
        no business meaning — permanently disadvantaging tenants whose ids sort
        late, for no reason related to actual workload priority.

        A single-element list is returned when one candidate has the unique
        lowest count.  The caller's tiebreak logic need only act when the list
        has more than one element.

        Parameters
        ----------
        candidate_tenant_ids
            Non-empty list of tenant_ids eligible for selection this cycle.

        Returns
        -------
        list[str]
            All candidates tied at the minimum selection_count.  Never empty
            when candidate_tenant_ids is non-empty.

        Raises
        ------
        ValueError
            If candidate_tenant_ids is empty.
        """
        if not candidate_tenant_ids:
            raise ValueError(
                "least_recently_selected requires at least one candidate tenant_id"
            )
        min_count = min(
            self.selection_count.get(tid, 0) for tid in candidate_tenant_ids
        )
        return [
            tid for tid in candidate_tenant_ids
            if self.selection_count.get(tid, 0) == min_count
        ]

    def record_selection(self, tenant_id: str) -> None:
        """Increment the selection count for tenant_id (§4.1 step 5).

        Called by the §4.1 handler immediately after a WorkloadCommand is
        issued — NOT inside BudgetGate.evaluate().  BudgetGate evaluates one
        job; the caller controls when selection is recorded.
        """
        self.selection_count[tenant_id] = self.selection_count.get(tenant_id, 0) + 1


# ── BudgetGate (§3.3 / §30.5–30.6) ──────────────────────────────────────────

class BudgetGate:
    """Per-tenant power-budget admission gate (§3.3 / §30.5–30.6).

    Stateless — each evaluate() call is independent.  All state (budget
    records, committed draw, rotation) is passed by the caller.

    Spec note on `operating_tier`
    ------------------------------
    The §3.3 signature does not list operating_tier explicitly.  However,
    WorkloadCommand.authority (§2.6) requires the current operating tier so
    the write-back path can audit what authority issued the deferral.  This
    implementation adds operating_tier as a keyword-only argument after the
    spec-defined positional parameters, defaulting to SUPERVISED (the
    conservatively-correct default, §26.2).  This extension does not change
    BudgetGate's logic — it only propagates context needed to correctly
    populate the returned command.
    """

    def evaluate(
        self,
        signal: WorkloadSignal,
        budget: Optional[TenantPowerBudget],
        tenant_committed_mw: float,
        predicted_draw_mw: float,
        rotation_state: RotationState,
        *,
        operating_tier: OperatingTier = OperatingTier.SUPERVISED,
    ) -> Optional[WorkloadCommand]:
        """Evaluate one queued job against the tenant's power budget.

        Parameters
        ----------
        signal
            The WorkloadSignal with event_type == "queued".
            signal.tenant_id must not be None — raises QuarantinedSignalError
            if missing (§17.2 quarantine).
        budget
            The tenant's TenantPowerBudget for (tenant_id, site_id), or None
            if no budget is configured.  None → return None (MT-1 behaviour).
        tenant_committed_mw
            Sum of the tenant's active + provisionally-admitted job draws at
            the time of this evaluation (step 3 of §4.1 sequence).
        predicted_draw_mw
            Predicted MW draw for this job, computed by the caller via the
            §4.1 formula (node_count × rated_kw / 1000).
        rotation_state
            Passed through from the §4.1 handler so the caller may call
            rotation_state.record_selection() after this method returns.
            BudgetGate does not call record_selection() itself (§3.3 note).
        operating_tier
            The site's current operating tier (§23.4 / §26.2), used to
            populate WorkloadCommand.authority on a deferral.

        Returns
        -------
        None
            Job proceeds — either budget is unconfigured (MT-1) or the job
            fits within the remaining budget.
        WorkloadCommand(action=DEFER, target=signal.job_id, authority=...)
            Job exceeds the remaining budget ceiling.

        Raises
        ------
        QuarantinedSignalError
            If signal.tenant_id is None.  The caller must route the signal
            to the §17.2 quarantine path — never admit it silently.
        """
        # §17.2 / §2.4: tenant_id=None is a schema violation — quarantine.
        if signal.tenant_id is None:
            raise QuarantinedSignalError(
                f"WorkloadSignal event_id={signal.event_id!r} job_id={signal.job_id!r} "
                f"has tenant_id=None. Signal must be quarantined per §17.2. "
                f"Never admit or default — the tenant is unknown."
            )

        # MT-1: no budget record → unbounded, proceed.
        if budget is None:
            return None

        # Within ceiling → proceed.
        projected_total_mw = tenant_committed_mw + predicted_draw_mw
        if projected_total_mw <= budget.budget_mw:
            return None

        # Budget would be exceeded → defer.
        return WorkloadCommand(
            action=WorkloadCommandAction.DEFER,
            target=signal.job_id,
            authority=operating_tier,
        )


# ── §4.1 queued-event handler ─────────────────────────────────────────────────

def handle_queued_event(
    signal: WorkloadSignal,
    *,
    predicted_draw_mw: float,
    budget: Optional[TenantPowerBudget],
    tenant_committed_mw: float,
    rotation_state: RotationState,
    operating_tier: OperatingTier = OperatingTier.SUPERVISED,
) -> Optional[WorkloadCommand]:
    """Execute the §4.1 sequence for one queued WorkloadSignal.

    This is a pure function — no I/O, no hardware access, no clock reads.
    It is designed to be called identically from a simulator replay and from
    a live system (§6.2 no-runtime-clock-reads rule).

    The caller is responsible for:
      - Computing predicted_draw_mw (§4.1 step 1: node_count × rated_kw / 1000
        from the hardware profile for this signal).
      - Looking up `budget` from (signal.tenant_id, signal.site_id) in the
        contract store (§4.1 step 2).
      - Looking up `tenant_committed_mw` from the active-job registry (§4.1
        step 3: sum of starting/running/provisionally-admitted draws).
      - Writing the returned WorkloadCommand to the §23.5 write-back path if
        not None (§4.1 step 5).
      - Calling rotation_state.record_selection(signal.tenant_id) if a command
        was returned (§4.1 step 5).
      - NOT proceeding to admission logic if a command was returned (§4.1 STOP).

    This function implements steps 4–5 only (the BudgetGate evaluation and
    the record_selection call).  Steps 1–3 are the caller's responsibility
    because they require access to runtime stores (hardware profiles, job
    registry, budget store) that live outside core/.

    Parameters
    ----------
    signal
        WorkloadSignal with event_type == "queued".
    predicted_draw_mw
        Caller-computed MW draw prediction for this job (§4.1 step 1).
    budget
        TenantPowerBudget for (signal.tenant_id, signal.site_id), or None.
    tenant_committed_mw
        Sum of tenant's active+provisional draw from job registry (§4.1 step 3).
    rotation_state
        Mutable rotation state; record_selection() called here if deferred.
    operating_tier
        Site's current operating tier for WorkloadCommand.authority.

    Returns
    -------
    None
        Job proceeds — no deferral issued.
    WorkloadCommand
        Deferral command; the caller must write it to the §23.5 path and STOP.

    Raises
    ------
    QuarantinedSignalError
        If signal.tenant_id is None (propagated from BudgetGate.evaluate()).
    """
    gate = BudgetGate()
    command = gate.evaluate(
        signal,
        budget,
        tenant_committed_mw,
        predicted_draw_mw,
        rotation_state,
        operating_tier=operating_tier,
    )

    if command is not None:
        # §4.1 step 5: record the selection so rotation state reflects this deferral.
        rotation_state.record_selection(signal.tenant_id)  # type: ignore[arg-type]
        # (tenant_id is guaranteed non-None here — evaluate() would have raised otherwise)

    return command
