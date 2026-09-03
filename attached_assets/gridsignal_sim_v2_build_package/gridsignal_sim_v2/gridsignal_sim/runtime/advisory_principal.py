"""
runtime/advisory_principal.py — Step 12: §28.7 advisory principal.

Orchestrates the full advisory loop: evidence aggregation → de-identification →
routing → gate validation → proposal storage.

LP-1 guarantee
--------------
When both MISTRAL_API_KEY and ANTHROPIC_API_KEY are absent, the principal is
a complete no-op.  maybe_advise() returns None, tick() is a no-op, and the
application runs as a pure deterministic simulator with no agents and NO ERRORS.

Advisory loop per tick
----------------------
1. maybe_advise() is called by the runtime with recent tick data and sim_time.
2. If not router.has_agent → return None (LP-1 short-circuit).
3. Throttle: only advise every ADVISE_EVERY_N_TICKS (default 12 = 60 s).
4. Build EvidenceWindow from recent ticks via deidentify() (TC-29 applied).
5. Router.route(evidence) → Proposal or None (network call, may fail).
6. Gate.validate(proposal) → TC-30 bounds check; reject if out-of-bounds.
7. Supersede any prior PENDING proposal for the same shortfall kind.
8. Store valid proposal; return it to caller for TickResult population.

tick(sim_time) must be called each sim tick to expire PENDING proposals
(answers "what happens if reviewing event never arrives").
"""
from __future__ import annotations

import logging
from typing import Optional, Sequence

from core.deident import EvidenceWindow, deidentify
from core.models import TickResult
from runtime.advisory_gate import AdvisoryGate, Proposal, ProposalState
from runtime.advisory_router import AdvisoryRouter

_log = logging.getLogger(__name__)

# How many sim ticks between advisory calls (CHOSEN — PROTO-14).
# At 5 s/tick, 12 ticks = 60 s between advisory calls.
ADVISE_EVERY_N_TICKS: int = 12

# How many recent ticks to aggregate into each EvidenceWindow.
EVIDENCE_WINDOW_TICKS: int = 60   # 60 ticks × 5 s = 300 s = 5 min window


class AdvisoryPrincipal:
    """Orchestrates the advisory loop.

    LP-1: if router.has_agent is False, this class is a complete no-op.
    All state (gate, recent_ticks, tick_counter) is still initialised so
    the object is safe to instantiate even without API keys.

    Usage (from runtime run loop):
        principal = AdvisoryPrincipal(gate=AdvisoryGate(), router=AdvisoryRouter())
        ...
        per tick:
            principal.tick(sim_time)                 # expire old proposals
            proposal = principal.maybe_advise(       # may return None
                recent_ticks=ctx.sink.rows[-60:],
                sim_time=sim_time,
                site_id=ctx.sim_state.site.site_id,
                job_id=ctx.run_id,
            )
    """

    def __init__(
        self,
        *,
        gate:   Optional[AdvisoryGate]   = None,
        router: Optional[AdvisoryRouter] = None,
        advise_every_n: int = ADVISE_EVERY_N_TICKS,
        evidence_window_ticks: int = EVIDENCE_WINDOW_TICKS,
    ) -> None:
        self._gate   = gate   or AdvisoryGate()
        self._router = router or AdvisoryRouter()
        self._advise_every_n       = advise_every_n
        self._evidence_window_ticks = evidence_window_ticks
        self._tick_counter: int    = 0
        self._last_proposal_kind: Optional[str] = None

    @property
    def has_agent(self) -> bool:
        """Convenience mirror of router.has_agent."""
        return self._router.has_agent

    @property
    def backend(self) -> Optional[str]:
        """Active backend name, or None if LP-1 no-op."""
        return self._router.backend

    # ── Per-tick entry points ─────────────────────────────────────────────

    def tick(self, sim_time: float) -> list[Proposal]:
        """Advance proposal lifetimes.  Must be called once per sim tick.

        Transitions any PENDING proposal whose deadline has passed to EXPIRED.
        Returns the list of newly-expired proposals (informational; the caller
        may log these as advisory latency events).

        This answers "what happens if the reviewing event never arrives":
        proposals expire deterministically driven by the sim clock.
        """
        return self._gate.tick(sim_time)

    def maybe_advise(
        self,
        recent_ticks: Sequence[TickResult],
        sim_time: float,
        *,
        site_id: str = "",
        job_id: str  = "",
        hardware_profile_ids: frozenset[str] = frozenset(),
    ) -> Optional[Proposal]:
        """Produce an advisory proposal, or return None.

        LP-1: returns None immediately if router.has_agent is False.
        Also returns None when:
          • fewer than EVIDENCE_WINDOW_TICKS ticks are available (warm-up),
          • the throttle period (advise_every_n ticks) has not elapsed,
          • the router returns None (network failure or model error),
          • the gate rejects the proposal (TC-30 out-of-bounds).

        The proposal returned has already passed gate.validate() (TC-30) and
        is stored in the gate.  The caller does not need to validate it again.
        """
        self._tick_counter += 1

        # LP-1: no-op when no API keys are configured.
        if not self._router.has_agent:
            return None

        # Throttle: only advise every N ticks.
        if self._tick_counter % self._advise_every_n != 0:
            return None

        # Warm-up: need enough ticks for a meaningful evidence window.
        if len(recent_ticks) < self._evidence_window_ticks:
            return None

        window_ticks = list(recent_ticks[-self._evidence_window_ticks:])

        # De-identify (TC-29 applied at the wire before the router sees it).
        try:
            evidence = deidentify(
                window_ticks,
                site_id=site_id,
                job_id=job_id,
                hardware_profile_ids=hardware_profile_ids,
            )
        except Exception as exc:
            _log.warning("advisory_principal: deidentify failed (%s).", exc)
            return None

        # Route to model backend.
        proposal = self._router.route(evidence, sim_time=sim_time)
        if proposal is None:
            return None

        # TC-30 gate validation.
        if not self._gate.validate(proposal):
            _log.info(
                "advisory_principal: proposal %s rejected by TC-30 gate (%s).",
                proposal.proposal_id, proposal.rejection_reason,
            )
            return None

        # Supersede any prior PENDING proposal of the same kind.
        for prior in self._gate.pending_proposals():
            if prior.proposal_id != proposal.proposal_id and prior.kind == proposal.kind:
                self._gate.supersede(prior.proposal_id)
                _log.debug(
                    "advisory_principal: superseded prior proposal %s with %s.",
                    prior.proposal_id, proposal.proposal_id,
                )

        self._last_proposal_kind = proposal.kind
        _log.info(
            "advisory_principal: proposal %s kind=%s impact=%.2f MW confidence=%.2f.",
            proposal.proposal_id, proposal.kind,
            proposal.estimated_impact_mw, proposal.confidence,
        )
        return proposal

    # ── Queries ───────────────────────────────────────────────────────────

    def pending_proposals(self) -> list[Proposal]:
        return self._gate.pending_proposals()

    def all_proposals(self) -> list[Proposal]:
        return self._gate.all_proposals()

    def get_gate(self) -> AdvisoryGate:
        return self._gate
