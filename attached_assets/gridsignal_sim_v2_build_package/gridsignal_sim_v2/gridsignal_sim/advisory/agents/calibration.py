"""
advisory/agents/calibration.py — Calibration advisory agent (§21.6, §26.2).

Cadence: floor 60 min / ceiling 24 h.
Proposal kind: calibration.
Authority ceiling: NEVER autonomous.  ALL calibration proposals require human
reviewer confirmation (TC-57).  A calibration proposal MUST NOT trigger any
immediate control action.

Calibration proposals represent parameter adjustment recommendations that pass
through the §21.6 gate.  The estimated_impact_mw field represents projected
improvement in reserve headroom or prediction accuracy, not a power curtailment.
"""
from __future__ import annotations

from typing import Sequence

from core.deident import EvidenceWindow
from core.models import TickResult
from runtime.advisory_gate import Proposal, make_proposal

from advisory.agents.base import BaseAdvisoryAgent

_SOC_CRITICAL_ANOMALY    = "bess_soc_critical"
_CONSECUTIVE_ALERT_PREFIX = "consecutive_alerts_"


class CalibrationAgent(BaseAdvisoryAgent):
    """Parameter calibration advisory agent (§21.6 gate).

    Qualifies when significant anomalies suggest calibration parameters are
    out of line with observed site behaviour:
      • bess_soc_critical: SOC repeatedly drops below 10 % → bess_reserve_fraction
        may need increasing.
      • consecutive_alerts_N: sustained reserve shortfall → anchor_reserve_mw may
        need adjusting.

    At ceiling (24 h), fires regardless of qualify() result to provide a
    liveness-floor audit record.

    TC-57: requires_confirmation is ALWAYS True.  This is not overridable.
    """

    AGENT_NAME:     str   = "calibration"
    PROPOSAL_KIND:  str   = "calibration"
    FLOOR_WALL_S:   float = 3600.0     # 60 min
    CEILING_WALL_S: float = 86400.0   # 24 h

    def qualify(
        self,
        ticks: Sequence[TickResult],
        evidence: EvidenceWindow,
    ) -> bool:
        if _SOC_CRITICAL_ANOMALY in evidence.anomalies:
            return True
        if any(a.startswith(_CONSECUTIVE_ALERT_PREFIX) for a in evidence.anomalies):
            return True
        return False

    def heuristic_fallback(
        self,
        evidence: EvidenceWindow,
        sim_time: float,
    ) -> Proposal:
        if _SOC_CRITICAL_ANOMALY in evidence.anomalies:
            impact = 1.0
            conf   = 0.65
            reason = "heuristic_calibration_bess_soc_critical_reserve_fraction"
        else:
            consec = [a for a in evidence.anomalies if a.startswith(_CONSECUTIVE_ALERT_PREFIX)]
            if consec:
                impact = 0.5
                conf   = 0.50
                reason = "heuristic_calibration_anchor_reserve_mw"
            else:
                impact = 0.1
                conf   = 0.20
                reason = "heuristic_calibration_liveness_audit"
        return make_proposal(
            kind="calibration",
            estimated_impact_mw=impact,
            confidence=conf,
            reasoning=reason,
            created_at_sim_time=sim_time,
        )

    def _requires_confirmation(self, proposal: Proposal) -> bool:
        """TC-57: calibration proposals ALWAYS require reviewer confirmation.

        This override is final — the base class default of True is preserved
        explicitly so that future subclassing cannot accidentally weaken it.
        """
        return True
