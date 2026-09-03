"""
advisory/agents/compute.py — Compute & Workload advisory agent (§26.2).

Cadence: floor 30 s wall-clock / ceiling 10 min wall-clock.
Proposal kind: curtailment (A/B executable at AUTONOMOUS; C/D always
               requires reviewer confirmation — TC-32).
Authority ceiling: NEVER dispatches.  A/B proposals carry
  requires_confirmation=False; C/D always carry requires_confirmation=True.
"""
from __future__ import annotations

from typing import Sequence

from core.deident import EvidenceWindow
from core.models import TickResult
from runtime.advisory_gate import Proposal, make_proposal

from advisory.agents.base import BaseAdvisoryAgent

# Heuristic thresholds (CHOSEN — PROTO-5).
_ALERT_QUALIFY_THRESHOLD = 1     # at least 1 alert tick in the window
_PEAK_LOAD_RATIO_QUALIFY = 0.90  # qualify if p95 > 90 % of p50 * 2 (high variance)

# Tiers that require reviewer confirmation regardless of operating tier (TC-32).
_C_D_TIERS: frozenset[str] = frozenset({"c_suspend", "d_preempt"})


class ComputeWorkloadAgent(BaseAdvisoryAgent):
    """Compute & Workload advisory agent.

    Qualifies when:
      • alert_count > 0 (reserve shortfall observed), OR
      • p_total_p95_mw > p_total_p50_mw * 1.15 (high variance / spike risk).

    Heuristic: if alert_count > 0, propose a_defer at 10 % of peak.
               Otherwise, propose load_defer at 5 % of peak (conservative).

    TC-32 authority ceiling:
      A/B curtailment tiers → requires_confirmation=False (AUTONOMOUS executable).
      C/D curtailment tiers → requires_confirmation=True (always need reviewer).
    """

    AGENT_NAME:    str   = "compute"
    PROPOSAL_KIND: str   = "curtailment"
    FLOOR_WALL_S:  float = 30.0
    CEILING_WALL_S: float = 600.0   # 10 min

    def qualify(
        self,
        ticks: Sequence[TickResult],
        evidence: EvidenceWindow,
    ) -> bool:
        if evidence.alert_count >= _ALERT_QUALIFY_THRESHOLD:
            return True
        if evidence.p_total_p50_mw > 0 and (
            evidence.p_total_p95_mw > evidence.p_total_p50_mw * 1.15
        ):
            return True
        # Qualify if any consecutive-alert anomaly is flagged.
        return any(a.startswith("consecutive_alerts_") for a in evidence.anomalies)

    def heuristic_fallback(
        self,
        evidence: EvidenceWindow,
        sim_time: float,
    ) -> Proposal:
        if evidence.alert_count > 0:
            impact = max(0.1, min(20.0, evidence.p_total_p95_mw * 0.10))
            tier   = "a_defer"
            conf   = 0.60
            reason = f"heuristic_alert_count_{evidence.alert_count}"
        else:
            impact = max(0.1, min(20.0, evidence.p_total_p95_mw * 0.05))
            tier   = None
            conf   = 0.30
            reason = "heuristic_variance_spike"
        return make_proposal(
            kind="curtailment",
            estimated_impact_mw=impact,
            confidence=conf,
            reasoning=reason,
            created_at_sim_time=sim_time,
            suggested_tier=tier,
        )

    def _requires_confirmation(self, proposal: Proposal) -> bool:
        """TC-32: A/B → False (AUTONOMOUS executable); C/D → True always."""
        if proposal.suggested_tier in _C_D_TIERS:
            return True
        return False
