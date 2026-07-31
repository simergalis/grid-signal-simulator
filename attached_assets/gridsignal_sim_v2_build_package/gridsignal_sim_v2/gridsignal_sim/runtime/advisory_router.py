"""
runtime/advisory_router.py — Step 12: §28.6 advisory model router.

LP-1 guarantee
--------------
If both MISTRAL_API_KEY and ANTHROPIC_API_KEY are absent from the environment,
AdvisoryRouter.route() returns None on every call and the application runs as a
pure deterministic simulator with no agents and NO ERRORS.  This is the primary
acceptance criterion for Step 12 and must be verified explicitly.

Build order note: this file is written AFTER core/deident.py.  No model client
call may bypass the de-identifier — every EvidenceWindow passed to route() has
already been produced by deidentify() and therefore carries no site_id, job_id,
customer identifier, or hardware SKU name (TC-29).

Backend selection
-----------------
1. MISTRAL_API_KEY present → Mistral mistral-small-latest
2. ANTHROPIC_API_KEY present (and Mistral absent) → Anthropic claude-haiku-3-5
3. Neither present → LP-1 no-op; route() returns None

Prompt format: compact JSON evidence window + system instruction.
The EvidenceWindow is serialised by the router; no raw tick data is transmitted.

Error handling
--------------
All network exceptions are caught and logged; route() returns None on any
failure.  The principal must treat None as "no advisory proposal this tick",
not as an error condition.  This ensures LP-1 holds under network failure too.
"""
from __future__ import annotations

import json
import logging
import os
import dataclasses
from typing import Optional

from core.deident import EvidenceWindow
from runtime.advisory_gate import (
    DEFAULT_PROPOSAL_LIFETIME_S, VALID_PROPOSAL_KINDS, make_proposal,
)
from runtime.advisory_gate import Proposal

_log = logging.getLogger(__name__)

# Mistral endpoint and model.
_MISTRAL_ENDPOINT = "https://api.mistral.ai/v1/chat/completions"
_MISTRAL_MODEL    = "mistral-small-latest"
# Anthropic endpoint and model.
_ANTHROPIC_ENDPOINT = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_MODEL    = "claude-haiku-3-5"
_ANTHROPIC_VERSION  = "2023-06-01"

# Max tokens requested from the model (JSON response only).
_MAX_TOKENS = 256
# Request timeout seconds (wall clock — not sim time).
_REQUEST_TIMEOUT_S = 10.0

_SYSTEM_PROMPT = """\
You are an advisory agent for a data-centre power management simulator.
You receive an aggregated, anonymised evidence window and must return a
single JSON proposal in this exact schema:

{
  "kind": "<one of: curtailment, pre_staging, bess_reserve_adjust, turbine_ramp_rate, load_defer>",
  "estimated_impact_mw": <float, 0.1–20.0>,
  "confidence": <float, 0.0–1.0>,
  "reasoning": "<brief explanation, no customer identifiers>",
  "suggested_tier": "<optional: a_defer, b_power_cap, c_suspend, d_preempt, or null>"
}

Return ONLY the JSON object. No markdown, no explanation outside the JSON.
If you cannot make a meaningful proposal, return:
{"kind": "load_defer", "estimated_impact_mw": 0.1, "confidence": 0.0, "reasoning": "insufficient_evidence", "suggested_tier": null}
"""


class AdvisoryRouter:
    """Routes advisory evidence windows to the appropriate model backend.

    LP-1: if no API keys are present, has_agent == False and route() returns
    None immediately on every call.  The application proceeds as a pure
    deterministic simulator.

    Instantiate once (e.g. at startup in AdvisoryPrincipal.__init__) so key
    presence is checked once.  Changing env vars after construction has no
    effect — this is intentional: it prevents race conditions during a run.
    """

    def __init__(self) -> None:
        self._mistral_key:   Optional[str] = os.environ.get("MISTRAL_API_KEY") or None
        self._anthropic_key: Optional[str] = os.environ.get("ANTHROPIC_API_KEY") or None

    @property
    def has_agent(self) -> bool:
        """True if at least one model backend is configured."""
        return bool(self._mistral_key or self._anthropic_key)

    @property
    def backend(self) -> Optional[str]:
        """Active backend name, or None if LP-1 no-op."""
        if self._mistral_key:
            return "mistral"
        if self._anthropic_key:
            return "anthropic"
        return None

    def route(
        self,
        evidence: EvidenceWindow,
        sim_time: float,
        *,
        lifetime_s: float = DEFAULT_PROPOSAL_LIFETIME_S,
        system_prompt: Optional[str] = None,
        agent_name: str = "",
    ) -> Optional[Proposal]:
        """Route evidence to the active model backend and return a Proposal.

        ``agent_name`` is the calling agent's AGENT_NAME (e.g. "compute").
        Subclasses may use it to customise the returned proposal; the base
        implementation ignores it — the LLM response determines the kind.

        LP-1: returns None immediately if has_agent is False.
        Returns None on any network or parse error (never raises).

        The returned Proposal has NOT yet been validated by the gate (TC-30).
        The caller (AdvisoryPrincipal) must call gate.validate(proposal) before
        presenting it to any reviewer.
        """
        if not self.has_agent:
            return None

        wire = json.dumps(dataclasses.asdict(evidence), separators=(",", ":"))
        user_message = f"Evidence window:\n{wire}"
        active_prompt = system_prompt if system_prompt is not None else _SYSTEM_PROMPT

        try:
            if self._mistral_key:
                raw = self._call_mistral(user_message, system_prompt=active_prompt)
            else:
                raw = self._call_anthropic(user_message, system_prompt=active_prompt)
        except Exception as exc:
            _log.warning("advisory_router: model call failed (%s); returning None.", exc)
            return None

        return self._parse_response(raw, sim_time=sim_time, lifetime_s=lifetime_s)

    # ── Backend calls ─────────────────────────────────────────────────────


    def _call_mistral(self, user_message: str, *, system_prompt: str = _SYSTEM_PROMPT) -> str:
        """HTTP POST to Mistral chat completions. Returns raw assistant content."""
        import urllib.request
        payload = json.dumps({
            "model": _MISTRAL_MODEL,
            "messages": [
                {"role": "system",  "content": system_prompt},
                {"role": "user",    "content": user_message},
            ],
            "max_tokens": _MAX_TOKENS,
            # temperature=0.0 reduces output variance but does NOT make a
            # hosted model deterministic or reproducible — most vendors document
            # this explicitly.  TC-48 holds because proposals are never actioned
            # (the architectural guarantee), not because model output is
            # reproducible.  Do not rely on temperature for replay fidelity.
            "temperature": 0.0,
        }).encode()
        req = urllib.request.Request(
            _MISTRAL_ENDPOINT,
            data=payload,
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {self._mistral_key}",
            },
            method="POST",
        )
        import urllib.error
        try:
            with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT_S) as resp:
                body = json.loads(resp.read())
            return body["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Mistral HTTP {e.code}: {e.read()[:200]}") from e

    def _call_anthropic(self, user_message: str, *, system_prompt: str = _SYSTEM_PROMPT) -> str:
        """HTTP POST to Anthropic messages. Returns raw content text."""
        import urllib.request
        payload = json.dumps({
            "model": _ANTHROPIC_MODEL,
            "max_tokens": _MAX_TOKENS,
            # temperature=0.0: reduces variance, does NOT guarantee determinism
            # on hosted Anthropic endpoints.  TC-48 is architectural, not model-based.
            "temperature": 0.0,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
        }).encode()
        req = urllib.request.Request(
            _ANTHROPIC_ENDPOINT,
            data=payload,
            headers={
                "Content-Type":    "application/json",
                "x-api-key":       self._anthropic_key,
                "anthropic-version": _ANTHROPIC_VERSION,
            },
            method="POST",
        )
        import urllib.error
        try:
            with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT_S) as resp:
                body = json.loads(resp.read())
            return body["content"][0]["text"]
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Anthropic HTTP {e.code}: {e.read()[:200]}") from e

    # ── Response parsing ──────────────────────────────────────────────────

    def _parse_response(
        self,
        raw: str,
        *,
        sim_time: float,
        lifetime_s: float,
    ) -> Optional[Proposal]:
        """Parse the model's JSON response into a Proposal.

        Returns None on any parse error — never raises.  The gate will perform
        its own TC-30 bounds check; this method just does structural parsing.
        """
        try:
            # Strip markdown code fences if the model wrapped the JSON.
            text = raw.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:])
                if text.endswith("```"):
                    text = text[:-3].strip()
            data: dict = json.loads(text)
        except (json.JSONDecodeError, ValueError) as exc:
            _log.warning("advisory_router: JSON parse failed (%s); raw=%r", exc, raw[:200])
            return None

        kind    = str(data.get("kind", "load_defer"))
        impact  = float(data.get("estimated_impact_mw", 0.1))
        conf    = float(data.get("confidence", 0.0))
        reason  = str(data.get("reasoning", ""))
        tier    = data.get("suggested_tier") or None

        return make_proposal(
            kind=kind,
            estimated_impact_mw=impact,
            confidence=conf,
            reasoning=reason,
            created_at_sim_time=sim_time,
            suggested_tier=str(tier) if tier else None,
            lifetime_s=lifetime_s,
        )


# ---------------------------------------------------------------------------
# DeterministicRouter — transport mock for testing
# ---------------------------------------------------------------------------

class DeterministicRouter(AdvisoryRouter):
    """Transport-mocked router for use under pytest and fast demo scripts.

    The full five-phase agent loop executes (qualify → deidentify → route →
    gate.validate → provenance-stamp) but ``route()`` returns a fixed
    curtailment proposal instantly — no network call, no API key required.

    ``has_agent`` is True so agents do not fall back to heuristics;
    ``backend`` is ``"deterministic"`` so provenance records are identifiable
    in test assertions.

    Design note: identical in structure to ``_DeterministicRouter`` in
    tests/test_step13_agents.py.  This public copy is imported by
    ``runtime/scenario_factory.py`` so the gate-the-transport pattern applies
    to every context built by the factory (not just TC-48 scenarios).
    """

    def __init__(self) -> None:
        # Bypass super().__init__() — avoid reading real env vars in tests.
        self._mistral_key   = "test-fake-key"
        self._anthropic_key = None

    @property
    def has_agent(self) -> bool:
        return True

    @property
    def backend(self) -> str:
        return "deterministic"

    # Agent name → (proposal_kind, suggested_tier, requires_confirmation_override)
    # requires_confirmation_override=True forces confirmation regardless of tier;
    # None means let the agent's own _requires_confirmation() decide.
    _KIND_MAP: dict[str, tuple[str, Optional[str], Optional[bool]]] = {
        "compute":     ("curtailment",         "a_defer", None),   # A/B → agent decides (False)
        "storage":     ("bess_reserve_adjust",  None,     None),
        "generation":  ("turbine_ramp_rate",    None,     None),
        "renewable":   ("pre_staging",          None,     None),
        "thermal":     ("load_defer",           None,     None),
        "calibration": ("calibration",          None,     True),   # TC-57: always True
    }

    def route(
        self,
        evidence: EvidenceWindow,
        sim_time: float,
        *,
        lifetime_s: float = DEFAULT_PROPOSAL_LIFETIME_S,
        system_prompt: Optional[str] = None,
        agent_name: str = "",
    ) -> Optional[Proposal]:
        """Return a deterministic, agent-aware proposal without any network call.

        ``agent_name`` selects the correct kind from ``_KIND_MAP``.  Unknown
        agents fall back to ``curtailment`` so the router is never a test
        blocker for new agents added in future steps.
        """
        kind, tier, _req_conf = self._KIND_MAP.get(
            agent_name, ("curtailment", "a_defer", None)
        )
        return make_proposal(
            kind=kind,
            estimated_impact_mw=1.0,
            confidence=0.5,
            reasoning=f"deterministic_router_no_network_{agent_name or 'unknown'}",
            created_at_sim_time=sim_time,
            suggested_tier=tier,
            lifetime_s=lifetime_s,
        )
