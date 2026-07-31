"""
advisory/agents/generation.py — Generation (turbine) advisory agent (§26.2).

Cadence: floor 5 min / ceiling 30 min.
Proposal kind: turbine_ramp_rate.
Authority ceiling: ADVISORY ONLY.  A turbine start is supervisory control
under NFR-3/NFR-4 — this agent proposes ramp rate adjustments, never starts
or stops a turbine.
"""
from __future__ import annotations

from typing import Sequence

from core.deident import EvidenceWindow
from core.models import TickResult
from runtime.advisory_gate import Proposal, make_proposal

from advisory.agents.base import BaseAdvisoryAgent


class GenerationAgent(BaseAdvisoryAgent):
    """Turbine ramp-rate advisory agent.

    Qualifies always (turbine telemetry is always valuable for ramp planning).
    The ceiling (30 min) ensures at least one proposal per half-hour.

    Heuristic: if peak load is rising (p95 > p50 * 1.05), propose faster ramp
               at medium confidence.  Otherwise, propose current rate maintenance
               at low confidence.

    ADVISORY ONLY — requires reviewer confirmation for all proposals (NFR-3/4).
    """

    AGENT_NAME:    str   = "generation"
    PROPOSAL_KIND: str   = "turbine_ramp_rate"
    FLOOR_WALL_S:  float = 300.0    # 5 min
    CEILING_WALL_S: float = 1800.0  # 30 min

    def qualify(
        self,
        ticks: Sequence[TickResult],
        evidence: EvidenceWindow,
    ) -> bool:
        # Always qualify — generation telemetry is always relevant.
        return True

    def heuristic_fallback(
        self,
        evidence: EvidenceWindow,
        sim_time: float,
    ) -> Proposal:
        rising = evidence.p_total_p95_mw > evidence.p_total_p50_mw * 1.05
        if rising:
            impact = max(0.1, min(20.0, evidence.p_total_p95_mw * 0.08))
            conf   = 0.55
            reason = "heuristic_load_rise_ramp_adjustment"
        else:
            impact = max(0.1, min(20.0, evidence.p_total_p95_mw * 0.03))
            conf   = 0.25
            reason = "heuristic_stable_ramp_maintain"
        return make_proposal(
            kind="turbine_ramp_rate",
            estimated_impact_mw=impact,
            confidence=conf,
            reasoning=reason,
            created_at_sim_time=sim_time,
        )
