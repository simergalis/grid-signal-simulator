"""
runtime/advisory_gate.py — Step 12: §28.5 advisory proposal gate.

TC-30 guarantee
---------------
Out-of-bounds proposals are auto-rejected at generation — they never reach
a reviewer.  AdvisoryGate.validate() is the single choke point; callers MUST
call it before presenting a proposal to any reviewer or persistence layer.

Proposal lifecycle (hold questions answered here)
--------------------------------------------------
Q: What bounds a proposal's lifetime?
A: expires_at_sim_time = created_at_sim_time + lifetime_s, where lifetime_s
   is clamped to [MIN_PROPOSAL_LIFETIME_S, MAX_PROPOSAL_LIFETIME_S].  No
   proposal can be PENDING indefinitely.  The gate enforces this at creation
   (TC-30 includes the lifetime check) and at each tick() call.

Q: What makes a state terminal?
A: Any state in TERMINAL_STATES (ACCEPTED, REJECTED, EXPIRED, SUPERSEDED).
   Once terminal, no further state transition is permitted.  tick() and
   accept/reject/supersede() all no-op or raise on terminal proposals.

Q: What happens if the reviewing event never arrives?
A: gate.tick(sim_time) scans all PENDING proposals.  Any proposal whose
   expires_at_sim_time <= sim_time is transitioned to EXPIRED automatically.
   No external timeout, no threading, no side effects — purely driven by the
   sim clock forwarded from evaluate_tick via the principal.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Bounds (all CHOSEN — PROTO-13; calibrate against design-partner requirements)
# ---------------------------------------------------------------------------

MAX_PROPOSAL_MW          = 20.0    # CHOSEN (PROTO-13) — cap on estimated_impact_mw
MIN_PROPOSAL_MW          = 0.1    # CHOSEN (PROTO-13) — floor to suppress noise
MIN_CONFIDENCE           = 0.0
MAX_CONFIDENCE           = 1.0
MIN_PROPOSAL_LIFETIME_S  = 30.0   # CHOSEN — at least one tick window
MAX_PROPOSAL_LIFETIME_S  = 3600.0 # CHOSEN — 1 simulated hour maximum
DEFAULT_PROPOSAL_LIFETIME_S = 300.0  # CHOSEN — 5 simulated minutes

# Valid proposal kinds (TC-30 also rejects unknown kinds).
# "calibration" is added in Step 13 for the CalibrationAgent (§21.6 gate).
# TC-57: calibration proposals ALWAYS require reviewer confirmation.
VALID_PROPOSAL_KINDS: frozenset[str] = frozenset({
    "curtailment",
    "pre_staging",
    "bess_reserve_adjust",
    "turbine_ramp_rate",
    "load_defer",
    "calibration",    # Step 13 — CalibrationAgent (§21.6); TC-57
    "reservation",    # Step 14 — ProcurementAgent (§24.3); TC-52
                      # ReservationProposal: NEVER autonomous at any tier
})


# ---------------------------------------------------------------------------
# Proposal state machine
# ---------------------------------------------------------------------------

class ProposalState(str, Enum):
    PENDING    = "pending"      # awaiting reviewer action or expiry
    ACCEPTED   = "accepted"     # terminal — reviewer accepted
    REJECTED   = "rejected"     # terminal — TC-30 or reviewer rejected
    EXPIRED    = "expired"      # terminal — reviewing event never arrived
    SUPERSEDED = "superseded"   # terminal — newer proposal replaced this one


TERMINAL_STATES: frozenset[ProposalState] = frozenset({
    ProposalState.ACCEPTED,
    ProposalState.REJECTED,
    ProposalState.EXPIRED,
    ProposalState.SUPERSEDED,
})


@dataclass
class Proposal:
    """One advisory proposal from an agent.

    Created by AdvisoryRouter.build_proposal(); validated by AdvisoryGate.validate()
    before any reviewer or persistence layer sees it.

    Fields
    ------
    proposal_id         : stable UUID; generated at construction.
    kind                : one of VALID_PROPOSAL_KINDS (TC-30 rejects others).
    suggested_tier      : optional curtailment tier hint (e.g. "a_defer").
    estimated_impact_mw : expected load reduction or reserve headroom (MW).
                          TC-30: must be in [MIN_PROPOSAL_MW, MAX_PROPOSAL_MW].
    confidence          : model's stated confidence in [0.0, 1.0].
                          TC-30: out-of-range rejected.
    reasoning           : free-text explanation, stripped of PII before storage.
    created_at_sim_time : sim_time at which the proposal was generated.
    expires_at_sim_time : sim_time at which PENDING → EXPIRED if not reviewed.
                          TC-30: lifetime clamped to
                          [MIN_PROPOSAL_LIFETIME_S, MAX_PROPOSAL_LIFETIME_S].
    state               : current lifecycle state (see ProposalState).
    rejection_reason    : set by gate.validate() or gate.reject() when state=REJECTED.
    """
    kind:               str
    estimated_impact_mw: float
    confidence:         float
    reasoning:          str
    created_at_sim_time: float
    expires_at_sim_time: float
    suggested_tier:     Optional[str] = None
    proposal_id:        str  = field(default_factory=lambda: str(uuid.uuid4()))
    state:              ProposalState = ProposalState.PENDING
    rejection_reason:   Optional[str] = None

    # ── Provenance (stamped by BaseAdvisoryAgent, Step 13) ────────────────
    # These fields are set by advisory/agents/base.py BEFORE gate.validate()
    # is called.  They identify which agent generated the proposal, which
    # system prompt was used, what evidence was seen, and whether the output
    # came from a model or the heuristic fallback.
    #
    # originating_agent  — AGENT_NAME of the agent class (e.g. "compute")
    # prompt_digest      — SHA-256[:16] of the canonical system prompt file
    # evidence_digest    — SHA-256[:16] of the serialised EvidenceWindow
    # generated_by       — "model" | "fallback"
    # requires_confirmation — True unless curtailment A/B at AUTONOMOUS tier
    originating_agent:    str  = ""
    prompt_digest:        str  = ""
    evidence_digest:      str  = ""
    generated_by:         str  = "model"    # "model" | "fallback"
    requires_confirmation: bool = True       # TC-32, TC-57
    # O2: reviewer identity recorded when accepted (Step 13 correction).
    reviewer_id:          str  = ""
    accepted_at_sim_time: Optional[float] = None

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES


# ---------------------------------------------------------------------------
# AdvisoryGate
# ---------------------------------------------------------------------------

class AdvisoryGate:
    """TC-30 bounds checking and proposal lifecycle management.

    validate() is the single entry point for new proposals.  Out-of-bounds
    proposals are immediately transitioned to REJECTED and returned as False —
    they never reach a reviewer.

    tick(sim_time) expires PENDING proposals whose deadline has passed.  It
    must be called once per sim tick (from AdvisoryPrincipal.tick()).

    Thread-safety: not thread-safe; designed for single-threaded sim loop.
    """

    def __init__(self, max_proposal_mw: float = MAX_PROPOSAL_MW) -> None:
        self._max_proposal_mw = max_proposal_mw
        # All proposals seen this session, keyed by proposal_id.
        self._proposals: dict[str, Proposal] = {}

    # ── TC-30 validation ──────────────────────────────────────────────────

    def validate(self, proposal: Proposal) -> bool:
        """TC-30: validate proposal bounds.

        Returns True if the proposal is within all bounds (PENDING state preserved).
        Returns False if any bound is violated (state → REJECTED immediately).

        Out-of-bounds proposals are rejected HERE — before the caller can present
        them to any reviewer.  This is the TC-30 guarantee: rejection at generation,
        not at review.

        Bounds checked:
            kind                in VALID_PROPOSAL_KINDS
            estimated_impact_mw in [MIN_PROPOSAL_MW, MAX_PROPOSAL_MW]
            confidence          in [MIN_CONFIDENCE, MAX_CONFIDENCE]
            lifetime            = expires_at_sim_time - created_at_sim_time
                                  in [MIN_PROPOSAL_LIFETIME_S, MAX_PROPOSAL_LIFETIME_S]
        """
        self._proposals[proposal.proposal_id] = proposal

        violations: list[str] = []

        if proposal.kind not in VALID_PROPOSAL_KINDS:
            violations.append(
                f"unknown kind {proposal.kind!r}; "
                f"must be one of {sorted(VALID_PROPOSAL_KINDS)}"
            )
        if not (MIN_PROPOSAL_MW <= proposal.estimated_impact_mw <= self._max_proposal_mw):
            violations.append(
                f"estimated_impact_mw={proposal.estimated_impact_mw:.3f} MW "
                f"outside [{MIN_PROPOSAL_MW}, {self._max_proposal_mw}] MW"
            )
        if not (MIN_CONFIDENCE <= proposal.confidence <= MAX_CONFIDENCE):
            violations.append(
                f"confidence={proposal.confidence} outside [{MIN_CONFIDENCE}, {MAX_CONFIDENCE}]"
            )
        lifetime_s = proposal.expires_at_sim_time - proposal.created_at_sim_time
        if not (MIN_PROPOSAL_LIFETIME_S <= lifetime_s <= MAX_PROPOSAL_LIFETIME_S):
            violations.append(
                f"lifetime={lifetime_s:.0f}s outside "
                f"[{MIN_PROPOSAL_LIFETIME_S:.0f}, {MAX_PROPOSAL_LIFETIME_S:.0f}] s"
            )

        if violations:
            proposal.state = ProposalState.REJECTED
            proposal.rejection_reason = "TC-30: " + "; ".join(violations)
            return False

        return True

    # ── Lifecycle transitions ─────────────────────────────────────────────

    def tick(self, sim_time: float) -> list[Proposal]:
        """Advance proposal lifetimes.  Called once per sim tick.

        Transitions any PENDING proposal with expires_at_sim_time <= sim_time
        to EXPIRED.  Returns the list of newly-expired proposals this tick.

        This is the answer to "what happens if the reviewing event never arrives":
        tick() expires them deterministically, driven by the sim clock forwarded
        from AdvisoryPrincipal.tick().  No threading, no wall-clock timers.
        """
        newly_expired: list[Proposal] = []
        for p in self._proposals.values():
            if p.state == ProposalState.PENDING and sim_time >= p.expires_at_sim_time:
                p.state = ProposalState.EXPIRED
                newly_expired.append(p)
        return newly_expired

    def accept(
        self,
        proposal_id: str,
        *,
        reviewer_id: str = "",
        accepted_at_sim_time: Optional[float] = None,
    ) -> None:
        """Transition proposal to ACCEPTED.  Raises if terminal or not found.

        reviewer_id and accepted_at_sim_time are recorded for the O2 audit
        trail.  Accepting a proposal does NOT alter dispatch in this step —
        nothing in the control plane reads accepted proposals yet.  TC-48
        confirms this: dispatch hash is identical before and after acceptance.
        """
        p = self._get_or_raise(proposal_id)
        if p.is_terminal:
            raise ValueError(
                f"Proposal {proposal_id!r} is already terminal ({p.state.value}); "
                f"cannot accept."
            )
        p.state = ProposalState.ACCEPTED
        p.reviewer_id = reviewer_id
        p.accepted_at_sim_time = accepted_at_sim_time

    def reject(self, proposal_id: str, reason: str = "") -> None:
        """Transition proposal to REJECTED (reviewer decision).  Raises if terminal."""
        p = self._get_or_raise(proposal_id)
        if p.is_terminal:
            raise ValueError(
                f"Proposal {proposal_id!r} is already terminal ({p.state.value}); "
                f"cannot reject."
            )
        p.state = ProposalState.REJECTED
        p.rejection_reason = reason or "reviewer_rejected"

    def supersede(self, old_proposal_id: str) -> None:
        """Transition proposal to SUPERSEDED.  Called when a newer proposal replaces it."""
        p = self._get_or_raise(old_proposal_id)
        if p.is_terminal:
            return   # already terminal — supersede is idempotent
        p.state = ProposalState.SUPERSEDED

    # ── Queries ───────────────────────────────────────────────────────────

    def pending_proposals(self) -> list[Proposal]:
        return [p for p in self._proposals.values() if p.state == ProposalState.PENDING]

    def all_proposals(self) -> list[Proposal]:
        return list(self._proposals.values())

    def get(self, proposal_id: str) -> Optional[Proposal]:
        return self._proposals.get(proposal_id)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _get_or_raise(self, proposal_id: str) -> Proposal:
        p = self._proposals.get(proposal_id)
        if p is None:
            raise KeyError(f"Proposal {proposal_id!r} not found in gate.")
        return p


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------

def make_proposal(
    kind: str,
    estimated_impact_mw: float,
    confidence: float,
    reasoning: str,
    created_at_sim_time: float,
    *,
    suggested_tier: Optional[str] = None,
    lifetime_s: float = DEFAULT_PROPOSAL_LIFETIME_S,
) -> Proposal:
    """Construct a Proposal with lifetime clamped to gate bounds.

    Clamps lifetime_s to [MIN_PROPOSAL_LIFETIME_S, MAX_PROPOSAL_LIFETIME_S]
    before computing expires_at_sim_time.  This is NOT the TC-30 validation
    (that happens in gate.validate()); clamping here prevents the caller from
    accidentally constructing proposals that would immediately fail TC-30.
    """
    clamped_lifetime = max(
        MIN_PROPOSAL_LIFETIME_S, min(MAX_PROPOSAL_LIFETIME_S, lifetime_s)
    )
    return Proposal(
        kind=kind,
        estimated_impact_mw=estimated_impact_mw,
        confidence=confidence,
        reasoning=reasoning,
        created_at_sim_time=created_at_sim_time,
        expires_at_sim_time=created_at_sim_time + clamped_lifetime,
        suggested_tier=suggested_tier,
    )
