"""
advisory/agents/base.py — §26.5 BaseAdvisoryAgent.

Five-phase loop:
  1. Observe   — accept recent_ticks from caller; check minimum tick count.
  2. Qualify   — significance floor; agent-specific threshold (§26.5: an agent
                 that cannot state the evidence for a recommendation shall not
                 emit it).  The ceiling (liveness floor) overrides qualify()
                 failure when the agent has been silent past CEILING_WALL_S.
  3. Transform — deidentify() → EvidenceWindow + digest provenance strings.
  4. Reason    — router.route() with agent-specific system prompt.  Falls back
                 to heuristic_fallback() if router returns None or LP-1 active.
  5. Propose   — gate.validate() (TC-30); stamp provenance; store + return.

Provenance (stamped by base class, never forgettable per-agent):
  originating_agent  — agent class name (e.g. "compute_workload")
  prompt_digest      — SHA-256[:16] of the canonical system prompt file
  evidence_digest    — SHA-256[:16] of the serialised EvidenceWindow
  generated_by       — "model" | "fallback"
  requires_confirmation — True unless curtailment tier A/B (TC-32, TC-57)

Cadence: wall-clock (time.monotonic()), not sim time.  FLOOR_WALL_S is the
minimum interval between agent calls (rate/cost control).  CEILING_WALL_S is
the liveness floor — an agent that has been silent longer than the ceiling
fires regardless of the qualify() result.  Evidence windows are simulated time;
the two clocks answer different questions.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
from pathlib import Path
from typing import Optional, Sequence

from core.deident import EvidenceWindow, deidentify
from core.models import TickResult
from runtime.advisory_gate import AdvisoryGate, Proposal, make_proposal
from runtime.advisory_router import AdvisoryRouter

_log = logging.getLogger(__name__)

# Path to prompt files relative to this module's directory.
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# Generic fallback prompt used when no agent-specific file is found.
_GENERIC_SYSTEM_PROMPT = """\
You are an advisory agent for a data-centre power management simulator.
You receive an aggregated, anonymised evidence window and must return a
single JSON proposal in this exact schema:
{
  "kind": "<one of: curtailment, pre_staging, bess_reserve_adjust, turbine_ramp_rate, load_defer, calibration>",
  "estimated_impact_mw": <float, 0.1–20.0>,
  "confidence": <float, 0.0–1.0>,
  "reasoning": "<brief explanation, no customer identifiers>",
  "suggested_tier": "<a_defer | b_power_cap | c_suspend | d_preempt | null>"
}
Return ONLY the JSON object. No markdown.
"""


class BaseAdvisoryAgent:
    """Base class for all six advisory agents.

    Subclasses MUST set:
        AGENT_NAME        — short snake_case identifier (matches prompt filename)
        PROPOSAL_KIND     — default kind emitted by this agent
        FLOOR_WALL_S      — minimum wall-clock seconds between calls
        CEILING_WALL_S    — maximum wall-clock seconds between calls (liveness)

    Subclasses SHOULD override:
        qualify()             — significance floor (return False to suppress)
        heuristic_fallback()  — deterministic threshold heuristic
        _requires_confirmation()  — whether proposals need reviewer sign-off
    """

    AGENT_NAME:       str   = "base"
    PROPOSAL_KIND:    str   = "load_defer"
    FLOOR_WALL_S:     float = 30.0
    CEILING_WALL_S:   float = 600.0
    MIN_QUALIFY_TICKS: int  = 12       # at least 60 s of evidence (12 × 5 s ticks)

    def __init__(
        self,
        *,
        router: AdvisoryRouter,
        gate:   AdvisoryGate,
    ) -> None:
        self._router = router
        self._gate   = gate
        self._last_run_wall:  float = float("-inf")
        self._prompt_text:    Optional[str] = None
        self._prompt_digest:  str = ""

    # ── Public entry point ────────────────────────────────────────────────

    def maybe_run(
        self,
        recent_ticks: Sequence[TickResult],
        *,
        wall_time: float,
        sim_time: float,
        site_id: str = "",
        job_id: str  = "",
        hardware_profile_ids: frozenset[str] = frozenset(),  # kept for compat
        hardware_profiles: Optional[dict[str, float]] = None,  # §21.4 O1
    ) -> Optional[Proposal]:
        """Five-phase loop entry point.

        Returns a Proposal that has passed TC-30 gate.validate(), or None.
        Never raises — all exceptions are caught and logged.

        Parameters
        ----------
        recent_ticks:
            The recent tick history to use as the evidence window.
        wall_time:
            Current wall-clock time (time.monotonic() or injected for testing).
        sim_time:
            Current simulated time in seconds.
        site_id, job_id, hardware_profile_ids, hardware_profiles:
            Passed to deidentify() (TC-29) and consumed; never stored.
            hardware_profiles: dict[str, float] (profile_id → rated_kw) adds
            §21.4 hardware class entries to the evidence window when provided.
        """
        # ── Phase 0: cadence gate ─────────────────────────────────────────
        elapsed = wall_time - self._last_run_wall
        past_ceiling = self.CEILING_WALL_S > 0 and elapsed >= self.CEILING_WALL_S
        if elapsed < self.FLOOR_WALL_S:
            return None   # rate-limited

        # ── Phase 1: Observe ──────────────────────────────────────────────
        if len(recent_ticks) < self.MIN_QUALIFY_TICKS:
            return None   # not enough evidence

        # ── Phase 3: Transform (before Qualify so evidence is available) ──
        try:
            evidence = deidentify(
                recent_ticks,
                site_id=site_id,
                job_id=job_id,
                hardware_profile_ids=hardware_profile_ids,
                hardware_profiles=hardware_profiles,  # §21.4 O1
            )
        except Exception as exc:
            _log.warning("%s: deidentify failed (%s).", self.AGENT_NAME, exc)
            return None

        evidence_digest = hashlib.sha256(
            json.dumps(dataclasses.asdict(evidence)).encode()
        ).hexdigest()[:16]

        # ── Phase 2: Qualify (significance floor, §26.5) ──────────────────
        if not past_ceiling and not self.qualify(recent_ticks, evidence):
            return None   # not significant enough; ceiling not yet reached

        # ── Phase 3b: load prompt + digest ───────────────────────────────
        prompt = self._load_prompt()

        # ── Phase 4: Reason ───────────────────────────────────────────────
        generated_by = "model"
        proposal: Optional[Proposal] = None

        if self._router.has_agent:
            try:
                proposal = self._router.route(
                    evidence, sim_time=sim_time, system_prompt=prompt,
                )
            except Exception as exc:
                _log.warning("%s: router.route() raised (%s).", self.AGENT_NAME, exc)
                proposal = None

        if proposal is None:
            proposal = self.heuristic_fallback(evidence, sim_time)
            generated_by = "fallback"

        # ── Stamp provenance (base class — cannot be forgotten) ───────────
        proposal.originating_agent   = self.AGENT_NAME
        proposal.prompt_digest       = self._prompt_digest
        proposal.evidence_digest     = evidence_digest
        proposal.generated_by        = generated_by
        proposal.requires_confirmation = self._requires_confirmation(proposal)

        # ── Phase 5: Propose (TC-30) ──────────────────────────────────────
        if not self._gate.validate(proposal):
            _log.info(
                "%s: proposal rejected by TC-30 gate (%s).",
                self.AGENT_NAME, proposal.rejection_reason,
            )
            return None

        self._last_run_wall = wall_time
        _log.info(
            "%s: proposal %s kind=%s impact=%.2f MW conf=%.2f generated_by=%s.",
            self.AGENT_NAME, proposal.proposal_id[:8],
            proposal.kind, proposal.estimated_impact_mw,
            proposal.confidence, generated_by,
        )
        return proposal

    # ── Overridable hooks ─────────────────────────────────────────────────

    def qualify(
        self,
        ticks: Sequence[TickResult],
        evidence: EvidenceWindow,
    ) -> bool:
        """Significance floor (§26.5).

        Return True if there is evidence worth reporting.  The base class
        always returns True (always significant); subclasses apply domain
        knowledge.  Called ONLY after the cadence floor and tick-count
        minimum have been satisfied.
        """
        return True

    def heuristic_fallback(
        self,
        evidence: EvidenceWindow,
        sim_time: float,
    ) -> Proposal:
        """Deterministic threshold heuristic.

        Used when LP-1 is active (no API keys) or the router returns None.
        Generated proposals carry generated_by="fallback" so the UI can
        render a distinct badge.

        Base class returns a minimal load_defer proposal; subclasses should
        override with domain-specific logic.
        """
        impact = max(0.1, min(20.0, evidence.p_total_p95_mw * 0.05))
        return make_proposal(
            kind=self.PROPOSAL_KIND,
            estimated_impact_mw=impact,
            confidence=0.20,
            reasoning=f"{self.AGENT_NAME}_heuristic_threshold",
            created_at_sim_time=sim_time,
        )

    def _requires_confirmation(self, proposal: Proposal) -> bool:
        """Whether this proposal requires human reviewer sign-off before action.

        Base class returns True (safe default).  ComputeWorkloadAgent overrides
        to return False for A/B curtailment tiers at AUTONOMOUS operating tier.
        CalibrationAgent always returns True (TC-57).
        """
        return True

    # ── Prompt loading ────────────────────────────────────────────────────

    def _load_prompt(self) -> str:
        if self._prompt_text is None:
            prompt_path = _PROMPTS_DIR / f"{self.AGENT_NAME}.txt"
            try:
                self._prompt_text = prompt_path.read_text(encoding="utf-8")
            except FileNotFoundError:
                self._prompt_text = _GENERIC_SYSTEM_PROMPT
            self._prompt_digest = hashlib.sha256(
                self._prompt_text.encode()
            ).hexdigest()[:16]
        return self._prompt_text

    def agent_name(self) -> str:
        return self.AGENT_NAME
