"""
advisory/agents/renewable.py — Renewable Supply advisory agent (§26.2, §7.1.1).

Cadence: floor 60 s / ceiling 15 min.
Proposal kind: pre_staging.
Authority ceiling: ADVISORY ONLY BY CONSTRUCTION.  Solar and wind are passive
collectors — no control surface exists (§7.1.1).  This agent can only advise
on pre-staging decisions to prepare for expected renewable shortfall.
"""
from __future__ import annotations

from typing import Sequence

from core.deident import EvidenceWindow
from core.models import TickResult
from runtime.advisory_gate import Proposal, make_proposal

from advisory.agents.base import BaseAdvisoryAgent

_DISPATCH_GAP_PREFIX = "dispatch_gap_"


class RenewableSupplyAgent(BaseAdvisoryAgent):
    """Renewable supply pre-staging advisory agent.

    Qualifies when:
      • dispatch_gap anomaly present (P_total has been below 80 % of peak
        for multiple ticks — possible renewable shortfall), OR
      • curtailment_count > 0 (curtailment proposals have been raised).

    Heuristic: if dispatch_gap present, propose pre_staging at medium
               confidence to prepare turbine/BESS for renewable drop.

    ADVISORY ONLY — requires reviewer confirmation for all proposals.
    """

    AGENT_NAME:    str   = "renewable"
    PROPOSAL_KIND: str   = "pre_staging"
    FLOOR_WALL_S:  float = 60.0
    CEILING_WALL_S: float = 900.0   # 15 min

    def qualify(
        self,
        ticks: Sequence[TickResult],
        evidence: EvidenceWindow,
    ) -> bool:
        if any(a.startswith(_DISPATCH_GAP_PREFIX) for a in evidence.anomalies):
            return True
        if evidence.curtailment_count > 0:
            return True
        return False

    def heuristic_fallback(
        self,
        evidence: EvidenceWindow,
        sim_time: float,
    ) -> Proposal:
        gap_anomalies = [a for a in evidence.anomalies if a.startswith(_DISPATCH_GAP_PREFIX)]
        if gap_anomalies:
            # Extract gap count from flag name (e.g. "dispatch_gap_6" → 6)
            try:
                gap_n = int(gap_anomalies[0].split("_")[-1])
            except (ValueError, IndexError):
                gap_n = 5
            # Larger gap → higher estimated impact from pre-staging.
            impact = max(0.1, min(20.0, evidence.p_total_p95_mw * (gap_n / 60.0)))
            conf   = 0.50
            reason = f"heuristic_renewable_dispatch_gap_{gap_n}"
        else:
            impact = max(0.1, min(20.0, evidence.p_total_p95_mw * 0.05))
            conf   = 0.30
            reason = "heuristic_curtailment_event_pre_stage"
        return make_proposal(
            kind="pre_staging",
            estimated_impact_mw=impact,
            confidence=conf,
            reasoning=reason,
            created_at_sim_time=sim_time,
        )
