"""pms_test_double.py — PMSTestDouble: simulated Power Management System.

GS-IMPL-PSP-002 §3.4 / §5.

SIMULATOR ONLY.  This class must never be instantiated, imported, or
referenced from core/.  See §5 for the full explanation.

In a production deployment, the PMS is a real vendor system operated by
a real human via the operator console.  GridSignal publishes a ShortfallEvent
and a PowerRanker.rank() output over the §28.3 northbound REST/MQTT advisory
channel, then stops — it has no visibility into what the PMS or operator
decides.  PMSTestDouble reproduces that decision loop deterministically for
simulator testing and demonstration only.

Import boundary (§1 / §5)
--------------------------
  This file lives in runtime/.  It MAY import from:
    - core/  (for data types: AdvisoryOutput, RankedSource, etc.)
    - standard library
  It MUST NOT be imported by core/.
  It MUST NOT import southbound clients (Modbus, DNP3, OPC UA, IEC 61850).
  It MUST NOT call any LLM API at runtime (scenario_author.py is offline-only).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from core.power_source_priority import AdvisoryOutput, AuthorityTier, RankedSource

logger = logging.getLogger(__name__)


# ── Data contracts (§2.7) ─────────────────────────────────────────────────────

@dataclass
class OperatorResponseProfile:
    """Simulated operator decision profile (§2.7).

    Generated offline by scenario_author.py (§3.5) before a run starts.
    Consumed by PMSTestDouble at simulator startup.  Never modified during
    a run — a run must be deterministically reproducible from its inputs (INV-7).

    Fields
    ------
    response_latency_s
        Simulated time (seconds) the operator takes to respond to an advisory,
        keyed by ranked source position (1-indexed).  Default: 30 s for all.
    approve
        Whether the simulated operator approves each recommended source,
        keyed by ranked source position (1-indexed).  Default: True for all.

    Missing keys fall back to `default_latency_s` / `default_approve`.
    """
    response_latency_s: Dict[int, float] = field(default_factory=dict)
    approve: Dict[int, bool]             = field(default_factory=dict)
    default_latency_s: float = 30.0
    default_approve: bool    = True

    def latency_for(self, rank: int) -> float:
        return self.response_latency_s.get(rank, self.default_latency_s)

    def approves(self, rank: int) -> bool:
        return self.approve.get(rank, self.default_approve)


@dataclass
class PMSLogEntry:
    """One PMS decision log entry (§2.7)."""
    t_s: float
    source_id: str
    action: str           # "approved" | "rejected" | "no_response"
    authority_tier: str   # AuthorityTier.value
    detail: str           # human-readable reason / latency


# ── PMSTestDouble ─────────────────────────────────────────────────────────────

class PMSTestDouble:
    """Deterministic simulated PMS for escalation testing (§3.4 / §4.3 / §5).

    In the simulator tick sequence (§4.3 Simulator branch):
      1. A ShortfallEvent is produced by EconomicDispatchLoop.
      2. The harness calls PowerRanker.rank() again, restricted to
         confirm/human_only sources (NOT the autonomous-only ranking from §4.2).
      3. The harness passes that AdvisoryOutput here via process().
      4. PMSTestDouble applies the OperatorResponseProfile deterministically.
      5. The resulting PMSLogEntry list is recorded for the test/demo log.

    This class does NOT:
      - Send any southbound command (§6.1 — no southbound writes anywhere).
      - Call any LLM API (§6.2 — no runtime LLM calls).
      - Read any clock (responses are profile-driven, not wall-clock-driven).
      - Import from core/ beyond what is strictly needed for type annotations.
    """

    def __init__(self, response_profile: OperatorResponseProfile) -> None:
        self._profile = response_profile

    def process(
        self,
        advisory: AdvisoryOutput,
        t_s: float,
    ) -> List[PMSLogEntry]:
        """Apply the operator response profile to *advisory* at simulated time *t_s*.

        Parameters
        ----------
        advisory
            AdvisoryOutput from PowerRanker.rank(), restricted to
            confirm/human_only sources (the escalation ranking, §4.3).
        t_s
            Simulated seconds since run start — used as the log timestamp;
            also added to response_latency_s to produce a "response time"
            for logging purposes only (no real wait is performed).

        Returns
        -------
        list[PMSLogEntry]
            One entry per source in advisory.ranked_sources, recording
            whether the simulated operator approved or rejected it.
        """
        entries: List[PMSLogEntry] = []

        for ranked_src in advisory.ranked_sources:
            rank = ranked_src.rank
            latency_s = self._profile.latency_for(rank)
            approved = self._profile.approves(rank)
            action = "approved" if approved else "rejected"
            detail = (
                f"Simulated operator response at t={t_s + latency_s:.1f}s "
                f"(latency {latency_s:.0f}s from advisory at t={t_s:.1f}s). "
                f"Source rank={rank}, authority={ranked_src.authority_tier.value}."
            )
            logger.info(
                "PMSTestDouble [t=%.1f]: %s source=%s tier=%s",
                t_s, action, ranked_src.source_id, ranked_src.authority_tier.value,
            )
            entries.append(PMSLogEntry(
                t_s=t_s,
                source_id=ranked_src.source_id,
                action=action,
                authority_tier=ranked_src.authority_tier.value,
                detail=detail,
            ))

        if not advisory.ranked_sources:
            logger.warning(
                "PMSTestDouble [t=%.1f]: advisory has no confirm/human_only sources "
                "to escalate to — shortfall cannot be resolved by this path.",
                t_s,
            )

        return entries
