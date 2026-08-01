"""
advisory/agent_registry.py — §26.2 AgentRegistry.

Holds the fleet of six advisory agents and the Agents ON/OFF toggle.

When enabled=False, run_all() returns [] immediately — no agent fires, no
proposals are generated, no network calls are made.  This is the kill-switch
demonstration: flipping the toggle mid-run changes nothing about dispatch
(TC-48 / TC-48-complement) and leaves the console fully functional as a
monitoring surface.

When enabled=True, run_all() iterates over all six agents in a fixed order
(cadence governs each agent independently, so most calls are no-ops).

Thread-safety: not thread-safe; designed for a single-threaded async run loop.
"""
from __future__ import annotations

import logging
from typing import Optional, Sequence

from core.deident import HardwareClassMap
from core.models import TickResult
from runtime.advisory_gate import AdvisoryGate, Proposal
from runtime.advisory_router import AdvisoryRouter

from advisory.agents.base import BaseAdvisoryAgent
from advisory.agents.compute    import ComputeWorkloadAgent
from advisory.agents.storage    import StorageAgent
from advisory.agents.generation import GenerationAgent
from advisory.agents.renewable  import RenewableSupplyAgent
from advisory.agents.thermal    import ThermalAgent
from advisory.agents.calibration import CalibrationAgent

_log = logging.getLogger(__name__)


class AgentRegistry:
    """Fleet of six advisory agents with a shared gate and router.

    Parameters
    ----------
    gate:
        Shared AdvisoryGate for TC-30 validation and lifecycle management.
        If None, a new gate is created.
    router:
        Shared AdvisoryRouter for model routing.
        If None, a new router is created (keys read from environment at
        construction time; see LP-1 in advisory_router.py).
    enabled:
        Initial state of the Agents ON/OFF toggle.  Can be changed mid-run
        via the enabled property.  Changing it never affects dispatch.

    Agents (in run order):
        ComputeWorkloadAgent  — Compute & Workload
        StorageAgent          — Storage (BESS)
        GenerationAgent       — Generation (turbine)
        RenewableSupplyAgent  — Renewable Supply
        ThermalAgent          — Thermal
        CalibrationAgent      — Calibration
    """

    def __init__(
        self,
        *,
        gate:              Optional[AdvisoryGate]   = None,
        router:            Optional[AdvisoryRouter] = None,
        enabled:           bool = True,
        hardware_profiles: Optional[dict[str, float]] = None,
    ) -> None:
        self._gate   = gate   or AdvisoryGate()
        self._router = router or AdvisoryRouter()
        self._enabled = enabled
        # P1: create a single session-stable HardwareClassMap if profiles provided.
        # The map lives for the lifetime of this AgentRegistry (= one advisory session).
        self._hw_class_map: Optional[HardwareClassMap] = (
            HardwareClassMap(hardware_profiles)
            if hardware_profiles
            else None
        )

        _agent_kwargs = dict(gate=self._gate, router=self._router)
        self._agents: list[BaseAdvisoryAgent] = [
            ComputeWorkloadAgent(**_agent_kwargs),
            StorageAgent        (**_agent_kwargs),
            GenerationAgent     (**_agent_kwargs),
            RenewableSupplyAgent(**_agent_kwargs),
            ThermalAgent        (**_agent_kwargs),
            CalibrationAgent    (**_agent_kwargs),
        ]

    # ── ON/OFF toggle ─────────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        """Agents ON/OFF toggle.  Changing this never affects dispatch (TC-48)."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        if self._enabled != value:
            _log.info("AgentRegistry: agents %s.", "ENABLED" if value else "DISABLED")
        self._enabled = value

    # ── Per-tick entry point ──────────────────────────────────────────────

    @property
    def hardware_class_map(self) -> Optional[HardwareClassMap]:
        """P1: session-stable hardware class map (None if no profiles provided).

        Reviewers can call map.resolve(class_index) to look up rated_kw_per_unit
        for a class index seen in a stored proposal.
        """
        return self._hw_class_map

    def run_all(
        self,
        recent_ticks: Sequence[TickResult],
        *,
        wall_time: float,
        sim_time: float,
        site_id: str = "",
        job_id: str  = "",
        hardware_profile_ids: frozenset[str] = frozenset(),  # kept for compat
        hardware_profiles: Optional[dict[str, float]] = None,  # backward compat
    ) -> list[Proposal]:
        """Run all agents that are due and return any proposals generated.

        Returns [] immediately if enabled=False (kill-switch).

        Each agent manages its own wall-clock cadence (floor/ceiling).  Most
        calls return None from each agent; proposals are only generated when
        the agent's floor has elapsed AND it qualifies (or its ceiling fires).

        Parameters are forwarded verbatim to BaseAdvisoryAgent.maybe_run();
        see that method for the full five-phase loop and TC-29 de-identification
        contract.
        """
        if not self._enabled:
            return []

        proposals: list[Proposal] = []
        for agent in self._agents:
            try:
                p = agent.maybe_run(
                    recent_ticks,
                    wall_time=wall_time,
                    sim_time=sim_time,
                    site_id=site_id,
                    job_id=job_id,
                    hardware_profile_ids=hardware_profile_ids,
                    hardware_profiles=hardware_profiles,
                    hardware_class_map=self._hw_class_map,  # P1: session-stable map
                )
                if p is not None:
                    proposals.append(p)
            except Exception as exc:
                # Never let one agent failure cascade to others.
                _log.error(
                    "AgentRegistry: agent %s raised unexpectedly (%s).",
                    agent.AGENT_NAME, exc,
                )

        return proposals

    # ── Tick (expiry forwarding) ──────────────────────────────────────────

    def tick(self, sim_time: float) -> list[Proposal]:
        """Forward sim-clock tick to the gate for proposal expiry."""
        return self._gate.tick(sim_time)

    # ── Queries ───────────────────────────────────────────────────────────

    def pending_proposals(self) -> list[Proposal]:
        return self._gate.pending_proposals()

    def all_proposals(self) -> list[Proposal]:
        return self._gate.all_proposals()

    def agent_names(self) -> list[str]:
        return [a.AGENT_NAME for a in self._agents]

    def get_gate(self) -> AdvisoryGate:
        return self._gate

    def get_router(self) -> AdvisoryRouter:
        return self._router

    # ── Telemetry snapshot ────────────────────────────────────────────────

    def telemetry_snapshot(self) -> dict:
        """Return a JSON-safe dict of live advisory telemetry for the tick payload.

        Called once per tick (just before broadcast) from run_manager.py.
        Reflects proposals generated by ticks 0…(t−1); the current tick's
        advisory run has not happened yet when this is stamped.

        Keys
        ----
        backend            : str | None  — "mistral" | "anthropic" | "deterministic" | None
        agents_armed       : int         — 6 if LLM configured + registry enabled, else 0
        proposals_total    : int         — cumulative proposals stored in the gate this run
        proposals_pending  : int         — proposals currently awaiting human review
        last_proposal_sim_time : float   — sim_time of most recent proposal; -1.0 if none yet
        per_agent          : dict[str, float] — agent_name → last proposal sim_time (-1.0 if none)
        """
        all_p     = self._gate.all_proposals()
        pending_p = self._gate.pending_proposals()

        # Per-agent: latest proposal sim_time across all historical proposals.
        per_agent_last: dict[str, float] = {}
        for p in all_p:
            name = p.originating_agent or ""
            if name and (name not in per_agent_last or p.created_at_sim_time > per_agent_last[name]):
                per_agent_last[name] = p.created_at_sim_time

        last_sim_time = (
            max(p.created_at_sim_time for p in all_p)
            if all_p else -1.0
        )

        return {
            "backend":              self._router.backend,
            "agents_armed":         len(self._agents) if (self._router.has_agent and self._enabled) else 0,
            "proposals_total":      len(all_p),
            "proposals_pending":    len(pending_p),
            "last_proposal_sim_time": last_sim_time,
            "per_agent": {
                name: per_agent_last.get(name, -1.0)
                for name in self.agent_names()
            },
        }
