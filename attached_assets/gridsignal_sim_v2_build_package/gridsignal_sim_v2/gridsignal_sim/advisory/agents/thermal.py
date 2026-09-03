"""
advisory/agents/thermal.py — Thermal advisory agent (§26.2).

Cadence: floor 5 min / ceiling 30 min.
Proposal kind: load_defer.
Authority ceiling: advisory for anything the BMS owns.  Thermal control
actions are initiated by the BMS, not the advisory plane.
"""
from __future__ import annotations

from typing import Sequence

from core.deident import EvidenceWindow
from core.models import TickResult
from runtime.advisory_gate import Proposal, make_proposal

from advisory.agents.base import BaseAdvisoryAgent

_DISPATCH_GAP_PREFIX = "dispatch_gap_"
_CONSECUTIVE_ALERT_PREFIX = "consecutive_alerts_"


class ThermalAgent(BaseAdvisoryAgent):
    """Thermal load-defer advisory agent.

    Qualifies when:
      • dispatch_gap anomaly present (load has been low relative to peak —
        thermal shedding opportunity), OR
      • consecutive_alerts anomaly present (sustained shortfall — thermal
        load may be contributing to reserve gap).

    Heuristic: proportional to the gap magnitude or alert count.

    All proposals require BMS/reviewer confirmation.
    """

    AGENT_NAME:    str   = "thermal"
    PROPOSAL_KIND: str   = "load_defer"
    FLOOR_WALL_S:  float = 300.0    # 5 min
    CEILING_WALL_S: float = 1800.0  # 30 min

    def qualify(
        self,
        ticks: Sequence[TickResult],
        evidence: EvidenceWindow,
    ) -> bool:
        if any(a.startswith(_DISPATCH_GAP_PREFIX) for a in evidence.anomalies):
            return True
        if any(a.startswith(_CONSECUTIVE_ALERT_PREFIX) for a in evidence.anomalies):
            return True
        return False

    def heuristic_fallback(
        self,
        evidence: EvidenceWindow,
        sim_time: float,
    ) -> Proposal:
        consec = [a for a in evidence.anomalies if a.startswith(_CONSECUTIVE_ALERT_PREFIX)]
        if consec:
            try:
                n = int(consec[0].split("_")[-1])
            except (ValueError, IndexError):
                n = 3
            impact = max(0.1, min(20.0, evidence.p_total_p95_mw * 0.12))
            conf   = 0.55
            reason = f"heuristic_thermal_consecutive_alerts_{n}"
        else:
            impact = max(0.1, min(20.0, evidence.p_total_p95_mw * 0.06))
            conf   = 0.35
            reason = "heuristic_thermal_dispatch_gap"
        return make_proposal(
            kind="load_defer",
            estimated_impact_mw=impact,
            confidence=conf,
            reasoning=reason,
            created_at_sim_time=sim_time,
        )
