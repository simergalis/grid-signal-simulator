"""
advisory/agents/storage.py — Storage (BESS) advisory agent (§26.2).

Cadence: floor 60 s / ceiling 15 min.
Proposal kind: bess_reserve_adjust.
Authority ceiling: advisory only.  All BESS control actions are supervisory.
"""
from __future__ import annotations

from typing import Sequence

from core.deident import EvidenceWindow
from core.models import TickResult
from runtime.advisory_gate import Proposal, make_proposal

from advisory.agents.base import BaseAdvisoryAgent

_SOC_CRITICAL_ANOMALY = "bess_soc_critical"
_ALERT_QUALIFY_THRESHOLD = 1


class StorageAgent(BaseAdvisoryAgent):
    """BESS reserve and charge scheduling advisory agent.

    Qualifies when:
      • bess_soc_critical anomaly detected (SOC < 10 %), OR
      • alert_count > 0 (reserve shortfall).

    Heuristic: if bess_soc_critical, propose 2 MW reserve adjustment at 70 %
               confidence.  If alert only, propose 1 MW at 50 % confidence.

    All proposals require reviewer confirmation (BESS control is supervisory).
    """

    AGENT_NAME:    str   = "storage"
    PROPOSAL_KIND: str   = "bess_reserve_adjust"
    FLOOR_WALL_S:  float = 60.0
    CEILING_WALL_S: float = 900.0   # 15 min

    def qualify(
        self,
        ticks: Sequence[TickResult],
        evidence: EvidenceWindow,
    ) -> bool:
        if _SOC_CRITICAL_ANOMALY in evidence.anomalies:
            return True
        if evidence.alert_count >= _ALERT_QUALIFY_THRESHOLD:
            return True
        return False

    def heuristic_fallback(
        self,
        evidence: EvidenceWindow,
        sim_time: float,
    ) -> Proposal:
        if _SOC_CRITICAL_ANOMALY in evidence.anomalies:
            impact = 2.0
            conf   = 0.70
            reason = "heuristic_bess_soc_critical"
        elif evidence.alert_count > 0:
            impact = 1.0
            conf   = 0.50
            reason = f"heuristic_alert_count_{evidence.alert_count}"
        else:
            impact = 0.5
            conf   = 0.25
            reason = "heuristic_reserve_headroom"
        return make_proposal(
            kind="bess_reserve_adjust",
            estimated_impact_mw=impact,
            confidence=conf,
            reasoning=reason,
            created_at_sim_time=sim_time,
        )
