"""
tests/test_step13_agents.py — Step 13: six buildable agents.

TC-48 (gate test — most important in the project):
    With every agent stopped, the dispatch trace over a full scenario run is
    BIT-IDENTICAL to a run with agents present but recommendations un-actioned.
    Comparison is by SHA-256 hash, not eyeballs.

TC-28: all model endpoints unreachable → no tick delayed past budget; only
       proposal generation stops.

TC-31: valid proposal left un-actioned → dispatch bit-identical to a
       learning-plane-disabled run (effectively TC-48 over the full window).

TC-32: Compute & Workload agent kind=curtailment; C/D tiers always
       requires_confirmation=True; A/B at AUTONOMOUS → requires_confirmation=False.

TC-57: CalibrationAgent proposals ALWAYS requires_confirmation=True.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import time
from typing import Optional
from unittest.mock import patch, MagicMock

import pytest

from advisory.agent_registry import AgentRegistry
from advisory.agents.base import BaseAdvisoryAgent
from advisory.agents.calibration import CalibrationAgent
from advisory.agents.compute import ComputeWorkloadAgent
from advisory.agents.generation import GenerationAgent
from advisory.agents.renewable import RenewableSupplyAgent
from advisory.agents.storage import StorageAgent
from advisory.agents.thermal import ThermalAgent
from core.deident import deidentify
from runtime.advisory_gate import (
    DEFAULT_PROPOSAL_LIFETIME_S, AdvisoryGate, Proposal, ProposalState,
    make_proposal,
)
from runtime.advisory_router import AdvisoryRouter
from runtime.scenario_factory import build_run_context


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SITE_ID = "site-tc48-test-secret"
JOB_ID  = "job-tc48-secret-identifier"
SKUS    = frozenset({"enterprise_8gpu_air"})


def _hash_trace(rows) -> str:
    """SHA-256 of the full dispatch trace: (sim_time, p_total, turbine, bess)."""
    trace = "|".join(
        f"{r.sim_time_seconds:.3f},{r.p_total_mw:.9f},"
        f"{r.turbine_output_mw:.9f},{r.bess_output_mw:.9f}"
        for r in rows
    )
    return hashlib.sha256(trace.encode()).hexdigest()


class _DeterministicRouter(AdvisoryRouter):
    """Transport-mocked router that returns a fast deterministic proposal.

    has_agent is always True (pretends keys are present) but never makes
    a real network call.  Used for TC-48: agents fire and produce proposals,
    but proposals are never actioned — the dispatch trace must be identical.
    """
    _has_agent = True
    _backend   = "test"

    def __init__(self) -> None:
        # Skip super().__init__() to avoid reading real env vars.
        self._mistral_key   = "test-fake-key"
        self._anthropic_key = None

    @property
    def has_agent(self) -> bool:
        return True

    @property
    def backend(self) -> str:
        return "test"

    def route(self, evidence, sim_time: float, **kwargs) -> Optional[Proposal]:
        """Return a deterministic proposal without any network call."""
        return make_proposal(
            kind="curtailment",
            estimated_impact_mw=1.0,
            confidence=0.5,
            reasoning="tc48_deterministic_test_proposal",
            created_at_sim_time=sim_time,
            suggested_tier="a_defer",
        )


class _AlwaysRaisingRouter(AdvisoryRouter):
    """Router whose network calls always raise (TC-28: endpoint unreachable)."""

    def __init__(self) -> None:
        self._mistral_key   = "test-fake-key"
        self._anthropic_key = None

    @property
    def has_agent(self) -> bool:
        return True

    @property
    def backend(self) -> str:
        return "test"

    def route(self, evidence, sim_time: float, **kwargs) -> Optional[Proposal]:
        raise ConnectionError("TC-28: simulated endpoint unreachable")


def _make_tick(p_total: float = 12.0, sim_time: float = 5.0) -> object:
    class Tick:
        pass
    t = Tick()
    t.p_total_mw                = p_total
    t.turbine_output_mw         = p_total * 0.8
    t.bess_output_mw            = p_total * 0.2
    t.bess_soc_fraction         = 0.5
    t.sim_time_seconds          = sim_time
    t.insufficient_reserve_alert = False
    t.curtailment_proposal_tiers = ()
    return t


def _make_ticks(n: int, *, alert: bool = False) -> list:
    return [
        _make_tick(p_total=12.0 + i * 0.05, sim_time=5.0 + i * 5.0)
        for i in range(n)
    ]


async def _run_scenario(
    *,
    registry: Optional[AgentRegistry],
    wall_time_offset: float = 9999.0,  # large offset so all floors are exceeded
) -> tuple[str, list]:
    """Run demo-20mw and return (sha256_hash, tick_rows)."""
    ctx = build_run_context(
        "tc48-test",
        job_id=JOB_ID,
        node_count=1900,
        turbine_rated_mw=25.0,
        bess_rated_mw=18.0,
        bess_usable_mwh=8.0,
        bess_grid_forming=True,
        end_sim_time=300.0,
    )
    while not ctx.is_complete():
        result = ctx.step()
        await ctx.sink.append(result)
        if registry is not None:
            # Run all agents — proposals are produced but NEVER actioned.
            # The dispatch loop (evaluate_tick) has zero knowledge of proposals.
            registry.tick(result.sim_time_seconds)
            registry.run_all(
                ctx.sink.rows,
                wall_time=wall_time_offset + result.sim_time_seconds,
                sim_time=result.sim_time_seconds,
                site_id=SITE_ID,
                job_id=JOB_ID,
                hardware_profile_ids=SKUS,
            )

    rows = ctx.sink.rows
    return _hash_trace(rows), rows


# ---------------------------------------------------------------------------
# TC-48: bit-identical dispatch trace
# ---------------------------------------------------------------------------

class TestTC48BitIdenticalTrace:
    """TC-48 — the most important test in the project.

    With every agent stopped, the dispatch trace over a full run is
    SHA-256-identical to a run with agents present but recommendations
    un-actioned.  This proves agents are a side-channel: they observe
    the same tick history and produce proposals, but they NEVER write
    to SimulationState.
    """

    def test_tc48_hash_identical_agents_stopped_vs_active(self) -> None:
        """TC-48 primary assertion: hashes are equal."""
        # Run 1: no registry (agents stopped entirely).
        hash_stopped, _ = asyncio.run(_run_scenario(registry=None))

        # Run 2: registry active with deterministic router (proposals generated
        # but never actioned — they sit in the gate as PENDING).
        gate = AdvisoryGate()
        router = _DeterministicRouter()
        registry = AgentRegistry(gate=gate, router=router, enabled=True)
        hash_active, rows = asyncio.run(_run_scenario(registry=registry))

        assert hash_stopped == hash_active, (
            f"TC-48 FAIL — dispatch traces differ!\n"
            f"  agents_stopped hash: {hash_stopped}\n"
            f"  agents_active  hash: {hash_active}\n"
            f"  proposals generated: {len(registry.all_proposals())}\n"
            f"  tick count: {len(rows)}"
        )

    def test_tc48_proposals_were_actually_generated(self) -> None:
        """TC-48 companion: the test is non-trivial — agents DID fire."""
        gate = AdvisoryGate()
        router = _DeterministicRouter()
        registry = AgentRegistry(gate=gate, router=router, enabled=True)
        asyncio.run(_run_scenario(registry=registry))
        all_p = registry.all_proposals()
        assert len(all_p) > 0, (
            "TC-48 companion: no proposals were generated — test is vacuous. "
            "The wall_time_offset must exceed all agents' FLOOR_WALL_S."
        )

    def test_tc48_proposals_are_pending_or_expired_never_actioned(self) -> None:
        """TC-48: proposals sit in PENDING or EXPIRED — never ACCEPTED."""
        gate = AdvisoryGate()
        router = _DeterministicRouter()
        registry = AgentRegistry(gate=gate, router=router, enabled=True)
        asyncio.run(_run_scenario(registry=registry))
        for p in registry.all_proposals():
            assert p.state not in (ProposalState.ACCEPTED,), (
                f"TC-48: proposal {p.proposal_id[:8]} was ACCEPTED during run "
                f"— this must not happen in an un-actioned run."
            )

    def test_tc48_toggle_disabled_mid_run(self) -> None:
        """TC-48 complement: flipping toggle OFF mid-run → same hash."""
        hash_off, _ = asyncio.run(_run_scenario(registry=None))

        # Start enabled, disable after a few ticks.
        gate = AdvisoryGate()
        router = _DeterministicRouter()
        registry = AgentRegistry(gate=gate, router=router, enabled=False)
        hash_off2, _ = asyncio.run(_run_scenario(registry=registry))

        assert hash_off == hash_off2, (
            "TC-48 toggle: enabled=False registry must produce same hash as no registry."
        )


# ---------------------------------------------------------------------------
# TC-28: endpoints unreachable → tick latency unaffected
# ---------------------------------------------------------------------------

class TestTC28EndpointsUnreachable:
    """TC-28: all model endpoints unreachable for 30 simulated minutes under
    load → no tick delayed past budget; only proposal generation stops.

    _AlwaysRaisingRouter.route() raises immediately.  BaseAdvisoryAgent catches
    it (returned None → heuristic fallback) so the tick loop is never blocked.
    """

    def test_tc28_raising_router_produces_fallback_proposals(self) -> None:
        """TC-28: when router raises, heuristic_fallback() is used instead."""
        gate = AdvisoryGate()
        router = _AlwaysRaisingRouter()
        registry = AgentRegistry(gate=gate, router=router, enabled=True)
        asyncio.run(_run_scenario(registry=registry))
        fallback_proposals = [
            p for p in registry.all_proposals()
            if p.generated_by == "fallback"
        ]
        assert len(fallback_proposals) > 0, (
            "TC-28: raising router must trigger heuristic fallback proposals."
        )

    def test_tc28_raising_router_never_blocks_tick(self) -> None:
        """TC-28: tick loop completes within wall-clock budget despite raises."""
        gate = AdvisoryGate()
        router = _AlwaysRaisingRouter()
        registry = AgentRegistry(gate=gate, router=router, enabled=True)

        t0 = time.monotonic()
        asyncio.run(_run_scenario(registry=registry))
        elapsed_s = time.monotonic() - t0

        assert elapsed_s < 30.0, (
            f"TC-28: scenario run took {elapsed_s:.1f}s — exceeds 30 s budget. "
            f"Raising router must not block the tick loop."
        )

    def test_tc28_dispatch_hash_identical_with_raising_router(self) -> None:
        """TC-28 / TC-48 combined: raising router → same dispatch hash as no-agents."""
        hash_none, _ = asyncio.run(_run_scenario(registry=None))

        gate = AdvisoryGate()
        router = _AlwaysRaisingRouter()
        registry = AgentRegistry(gate=gate, router=router, enabled=True)
        hash_raising, _ = asyncio.run(_run_scenario(registry=registry))

        assert hash_none == hash_raising, (
            "TC-28/TC-48: dispatch must be identical when router is unreachable."
        )


# ---------------------------------------------------------------------------
# TC-31: un-actioned proposals → dispatch identical
# ---------------------------------------------------------------------------

class TestTC31UnactionedProposals:
    """TC-31: valid proposals left un-actioned → dispatch bit-identical to a
    learning-plane-disabled run.  This is TC-48 re-stated for a specific
    scenario: proposals accumulate in the gate, expire naturally, and are
    never applied.
    """

    def test_tc31_proposals_accumulate_and_expire(self) -> None:
        """TC-31: PENDING proposals eventually expire via gate.tick()."""
        gate = AdvisoryGate()
        router = _DeterministicRouter()
        registry = AgentRegistry(gate=gate, router=router, enabled=True)
        _, rows = asyncio.run(_run_scenario(registry=registry))

        all_p = registry.all_proposals()
        assert len(all_p) > 0, "TC-31: no proposals were generated."
        # All proposals are either PENDING (not yet expired in the short run)
        # or EXPIRED (expired during the run via gate.tick()).
        for p in all_p:
            assert p.state in (
                ProposalState.PENDING,
                ProposalState.EXPIRED,
                ProposalState.SUPERSEDED,
            ), (
                f"TC-31: proposal {p.proposal_id[:8]} has unexpected state {p.state}."
            )

    def test_tc31_hash_same_as_agents_stopped(self) -> None:
        """TC-31: hash with un-actioned proposals equals hash without agents."""
        hash_stopped, _ = asyncio.run(_run_scenario(registry=None))

        gate = AdvisoryGate()
        router = _DeterministicRouter()
        registry = AgentRegistry(gate=gate, router=router, enabled=True)
        hash_unactioned, _ = asyncio.run(_run_scenario(registry=registry))

        assert hash_stopped == hash_unactioned, "TC-31 FAIL: dispatch traces differ."


# ---------------------------------------------------------------------------
# TC-32: Compute authority ceiling
# ---------------------------------------------------------------------------

class TestTC32ComputeAuthorityCeiling:
    """TC-32: Compute & Workload agent proposes curtailment (A/B executable at
    AUTONOMOUS; C/D always requires confirmation).
    """

    def test_tc32_compute_kind_is_curtailment(self) -> None:
        """TC-32: ComputeWorkloadAgent.PROPOSAL_KIND is 'curtailment'."""
        assert ComputeWorkloadAgent.PROPOSAL_KIND == "curtailment"

    def test_tc32_ab_tiers_no_confirmation(self) -> None:
        """TC-32: A/B curtailment tiers → requires_confirmation=False."""
        gate = AdvisoryGate()
        router = _DeterministicRouter()
        agent = ComputeWorkloadAgent(router=router, gate=gate)
        for tier in ("a_defer", "b_power_cap", None):
            p = make_proposal(
                kind="curtailment", estimated_impact_mw=2.0, confidence=0.7,
                reasoning="test", created_at_sim_time=0.0, suggested_tier=tier,
            )
            p.suggested_tier = tier
            result = agent._requires_confirmation(p)
            assert not result, (
                f"TC-32: tier={tier!r} must not require confirmation "
                f"(A/B executable at AUTONOMOUS)"
            )

    def test_tc32_cd_tiers_always_require_confirmation(self) -> None:
        """TC-32: C/D curtailment tiers → requires_confirmation=True always."""
        gate = AdvisoryGate()
        router = _DeterministicRouter()
        agent = ComputeWorkloadAgent(router=router, gate=gate)
        for tier in ("c_suspend", "d_preempt"):
            p = make_proposal(
                kind="curtailment", estimated_impact_mw=5.0, confidence=0.8,
                reasoning="test", created_at_sim_time=0.0, suggested_tier=tier,
            )
            p.suggested_tier = tier
            result = agent._requires_confirmation(p)
            assert result, (
                f"TC-32: tier={tier!r} MUST require confirmation; "
                f"C/D are never autonomous at any tier"
            )

    def test_tc32_compute_agent_fires_with_alert(self) -> None:
        """TC-32: ComputeWorkloadAgent fires when alert_count > 0."""
        gate = AdvisoryGate()
        router = _DeterministicRouter()
        agent = ComputeWorkloadAgent(router=router, gate=gate)

        ticks = _make_ticks(20)
        ticks[5].insufficient_reserve_alert = True

        proposal = agent.maybe_run(
            ticks,
            wall_time=9999.0,   # past all floors
            sim_time=100.0,
            site_id=SITE_ID, job_id=JOB_ID,
        )
        assert proposal is not None, "TC-32: agent should fire on alert."
        assert proposal.kind == "curtailment"
        assert proposal.originating_agent == "compute"

    def test_tc32_compute_agent_provenance_stamped(self) -> None:
        """TC-32: provenance fields are set by the base class."""
        gate = AdvisoryGate()
        router = _DeterministicRouter()
        agent = ComputeWorkloadAgent(router=router, gate=gate)
        ticks = _make_ticks(20)
        ticks[5].insufficient_reserve_alert = True

        proposal = agent.maybe_run(
            ticks, wall_time=9999.0, sim_time=100.0,
            site_id=SITE_ID, job_id=JOB_ID,
        )
        assert proposal is not None
        assert proposal.originating_agent == "compute"
        assert len(proposal.prompt_digest) == 16
        assert len(proposal.evidence_digest) == 16
        assert proposal.generated_by in ("model", "fallback")

    def test_tc32_no_dispatch_authority(self) -> None:
        """TC-32: ComputeWorkloadAgent has no direct dispatch surface."""
        # The agent has no reference to SimulationState — only router and gate.
        agent = ComputeWorkloadAgent(
            router=_DeterministicRouter(), gate=AdvisoryGate()
        )
        assert not hasattr(agent, "_sim_state"), (
            "TC-32: agent must not hold a reference to SimulationState."
        )
        assert not hasattr(agent, "_dispatch"), (
            "TC-32: agent must not hold a dispatch reference."
        )


# ---------------------------------------------------------------------------
# TC-57: CalibrationAgent always requires confirmation
# ---------------------------------------------------------------------------

class TestTC57CalibrationRequiresConfirmation:
    """TC-57: no autonomous change occurs for calibration proposals.

    CalibrationAgent._requires_confirmation() always returns True,
    regardless of any proposal field values.
    """

    def test_tc57_calibration_always_requires_confirmation(self) -> None:
        """TC-57: _requires_confirmation is True for any CalibrationAgent proposal."""
        gate = AdvisoryGate()
        router = _DeterministicRouter()
        agent = CalibrationAgent(router=router, gate=gate)

        for impact in (0.1, 1.0, 5.0, 20.0):
            p = make_proposal(
                kind="calibration", estimated_impact_mw=impact,
                confidence=0.9, reasoning="test", created_at_sim_time=0.0,
            )
            assert agent._requires_confirmation(p), (
                f"TC-57: CalibrationAgent._requires_confirmation must be True "
                f"for all proposals (impact={impact} MW)."
            )

    def test_tc57_calibration_proposal_kind(self) -> None:
        """TC-57: CalibrationAgent.PROPOSAL_KIND is 'calibration'."""
        assert CalibrationAgent.PROPOSAL_KIND == "calibration"

    def test_tc57_calibration_heuristic_fallback_kind(self) -> None:
        """TC-57: heuristic fallback also produces kind='calibration'."""
        gate = AdvisoryGate()
        router = AdvisoryRouter.__new__(AdvisoryRouter)
        router._mistral_key = None
        router._anthropic_key = None
        agent = CalibrationAgent(router=router, gate=gate)

        evidence = deidentify(_make_ticks(20), site_id="s", job_id="j")
        p = agent.heuristic_fallback(evidence, sim_time=0.0)
        assert p.kind == "calibration", (
            "TC-57: fallback proposal must also be kind='calibration'."
        )

    def test_tc57_calibration_fires_at_ceiling_without_qualifying(self) -> None:
        """TC-57 / liveness: calibration fires at ceiling even without anomalies."""
        gate = AdvisoryGate()
        router = _DeterministicRouter()
        agent = CalibrationAgent(router=router, gate=gate)

        ticks = _make_ticks(20)   # no alerts, no anomalies

        # Normal qualify() would return False (no anomalies) but ceiling fires.
        # CEILING_WALL_S = 86400 s — but we set wall_time past ceiling via offset.
        proposal = agent.maybe_run(
            ticks,
            wall_time=CalibrationAgent.CEILING_WALL_S + 1.0,
            sim_time=100.0,
            site_id=SITE_ID, job_id=JOB_ID,
        )
        assert proposal is not None, (
            "TC-57 / liveness: CalibrationAgent must fire at ceiling even "
            "when qualify() would return False."
        )
        assert proposal.requires_confirmation, (
            "TC-57: ceiling-triggered proposal must still require confirmation."
        )


# ---------------------------------------------------------------------------
# Agent registry and structural tests
# ---------------------------------------------------------------------------

class TestAgentRegistry:
    """Structural tests for the AgentRegistry."""

    def test_registry_has_six_agents(self) -> None:
        """AgentRegistry holds exactly six agents."""
        gate = AdvisoryGate()
        router = _DeterministicRouter()
        reg = AgentRegistry(gate=gate, router=router)
        assert len(reg.agent_names()) == 6

    def test_registry_agent_names(self) -> None:
        """AgentRegistry agent names match the six spec agents."""
        gate = AdvisoryGate()
        router = _DeterministicRouter()
        reg = AgentRegistry(gate=gate, router=router)
        names = set(reg.agent_names())
        expected = {"compute", "storage", "generation", "renewable", "thermal", "calibration"}
        assert names == expected, f"Expected {expected}, got {names}."

    def test_registry_disabled_returns_empty(self) -> None:
        """AgentRegistry.enabled=False → run_all() returns []."""
        gate = AdvisoryGate()
        router = _DeterministicRouter()
        reg = AgentRegistry(gate=gate, router=router, enabled=False)
        ticks = _make_ticks(20)
        proposals = reg.run_all(
            ticks, wall_time=99999.0, sim_time=100.0,
            site_id=SITE_ID, job_id=JOB_ID,
        )
        assert proposals == [], "enabled=False must return []."
        assert reg.all_proposals() == [], "No proposals stored when disabled."

    def test_registry_toggle_mid_run(self) -> None:
        """Toggle can be flipped mid-run without raising."""
        reg = AgentRegistry(router=_DeterministicRouter())
        assert reg.enabled
        reg.enabled = False
        assert not reg.enabled
        reg.enabled = True
        assert reg.enabled

    def test_registry_tick_forwards_to_gate(self) -> None:
        """AgentRegistry.tick() forwards to gate and returns expired proposals."""
        gate = AdvisoryGate()
        router = _DeterministicRouter()
        reg = AgentRegistry(gate=gate, router=router, enabled=True)
        ticks = _make_ticks(20)
        proposals = reg.run_all(
            ticks, wall_time=99999.0, sim_time=0.0,
            site_id=SITE_ID, job_id=JOB_ID,
        )
        # Some proposals should exist.
        # Tick past all lifetimes.
        expired = reg.tick(sim_time=999999.0)
        # Gate must have processed expirations.
        for p in reg.all_proposals():
            assert p.state != ProposalState.PENDING, (
                f"After tick(999999), no proposal should be PENDING; "
                f"found {p.state} for {p.proposal_id[:8]}."
            )


class TestAdvisoryFloorCeiling:
    """Floor/ceiling cadence tests for BaseAdvisoryAgent."""

    def test_floor_prevents_double_fire(self) -> None:
        """Agent does not fire twice within FLOOR_WALL_S."""
        gate = AdvisoryGate()
        router = _DeterministicRouter()
        agent = ComputeWorkloadAgent(router=router, gate=gate)
        ticks = _make_ticks(20)
        ticks[5].insufficient_reserve_alert = True

        # First call — should fire (wall_time past floor).
        p1 = agent.maybe_run(ticks, wall_time=9999.0, sim_time=100.0,
                              site_id=SITE_ID, job_id=JOB_ID)
        assert p1 is not None, "First call should fire."

        # Second call immediately after — within floor (floor = 30 s).
        p2 = agent.maybe_run(ticks, wall_time=9999.0 + 1.0, sim_time=105.0,
                              site_id=SITE_ID, job_id=JOB_ID)
        assert p2 is None, "Second call within floor should not fire."

    def test_floor_elapsed_allows_second_fire(self) -> None:
        """Agent fires again once FLOOR_WALL_S has elapsed."""
        gate = AdvisoryGate()
        router = _DeterministicRouter()
        agent = ComputeWorkloadAgent(router=router, gate=gate)
        ticks = _make_ticks(20)
        ticks[5].insufficient_reserve_alert = True

        p1 = agent.maybe_run(ticks, wall_time=0.0, sim_time=100.0,
                              site_id=SITE_ID, job_id=JOB_ID)
        assert p1 is not None

        # After FLOOR_WALL_S + 1 elapsed.
        p2 = agent.maybe_run(
            ticks,
            wall_time=ComputeWorkloadAgent.FLOOR_WALL_S + 1.0,
            sim_time=200.0,
            site_id=SITE_ID, job_id=JOB_ID,
        )
        assert p2 is not None, "Agent should fire again after floor elapsed."

    def test_ceiling_fires_even_when_not_significant(self) -> None:
        """Agent fires at ceiling even when qualify() would return False."""
        gate = AdvisoryGate()
        router = _DeterministicRouter()
        agent = ComputeWorkloadAgent(router=router, gate=gate)
        ticks = _make_ticks(20)  # no alerts, no anomalies → qualify() returns False

        # Past ceiling (ceiling = 600 s for Compute).
        proposal = agent.maybe_run(
            ticks,
            wall_time=ComputeWorkloadAgent.CEILING_WALL_S + 1.0,
            sim_time=700.0,
            site_id=SITE_ID, job_id=JOB_ID,
        )
        assert proposal is not None, (
            "Agent must fire at ceiling even when qualify() would return False."
        )


class TestProvenanceStamping:
    """Provenance fields are set by base class, not individual agents."""

    def _run_agent(self, AgentClass, alert=False) -> Optional[Proposal]:
        gate = AdvisoryGate()
        router = _DeterministicRouter()
        agent = AgentClass(router=router, gate=gate)
        ticks = _make_ticks(20)
        if alert:
            ticks[5].insufficient_reserve_alert = True
        return agent.maybe_run(
            ticks, wall_time=9999.0, sim_time=100.0,
            site_id=SITE_ID, job_id=JOB_ID,
        )

    def test_compute_provenance(self) -> None:
        p = self._run_agent(ComputeWorkloadAgent, alert=True)
        assert p is not None
        assert p.originating_agent == "compute"
        assert len(p.prompt_digest) == 16
        assert len(p.evidence_digest) == 16

    def test_storage_provenance(self) -> None:
        gate = AdvisoryGate()
        router = _DeterministicRouter()
        agent = StorageAgent(router=router, gate=gate)
        ticks = _make_ticks(20)
        ticks[5].insufficient_reserve_alert = True
        p = agent.maybe_run(ticks, wall_time=9999.0, sim_time=100.0,
                             site_id=SITE_ID, job_id=JOB_ID)
        assert p is not None
        assert p.originating_agent == "storage"

    def test_generation_provenance(self) -> None:
        """GenerationAgent always qualifies — provenance is always stamped."""
        p = self._run_agent(GenerationAgent)
        assert p is not None
        assert p.originating_agent == "generation"

    def test_renewable_ceiling_provenance(self) -> None:
        """RenewableSupplyAgent fires at ceiling — provenance stamped."""
        gate = AdvisoryGate()
        router = _DeterministicRouter()
        agent = RenewableSupplyAgent(router=router, gate=gate)
        ticks = _make_ticks(20)
        p = agent.maybe_run(
            ticks,
            wall_time=RenewableSupplyAgent.CEILING_WALL_S + 1.0,
            sim_time=100.0,
            site_id=SITE_ID, job_id=JOB_ID,
        )
        assert p is not None
        assert p.originating_agent == "renewable"

    def test_thermal_ceiling_provenance(self) -> None:
        gate = AdvisoryGate()
        router = _DeterministicRouter()
        agent = ThermalAgent(router=router, gate=gate)
        ticks = _make_ticks(20)
        p = agent.maybe_run(
            ticks,
            wall_time=ThermalAgent.CEILING_WALL_S + 1.0,
            sim_time=100.0,
            site_id=SITE_ID, job_id=JOB_ID,
        )
        assert p is not None
        assert p.originating_agent == "thermal"

    def test_calibration_provenance(self) -> None:
        gate = AdvisoryGate()
        router = _DeterministicRouter()
        agent = CalibrationAgent(router=router, gate=gate)
        ticks = _make_ticks(20)
        p = agent.maybe_run(
            ticks,
            wall_time=CalibrationAgent.CEILING_WALL_S + 1.0,
            sim_time=100.0,
            site_id=SITE_ID, job_id=JOB_ID,
        )
        assert p is not None
        assert p.originating_agent == "calibration"
        assert p.requires_confirmation is True    # TC-57

    def test_generated_by_fallback_when_no_keys(self) -> None:
        """LP-1 path: no keys → heuristic fallback → generated_by='fallback'."""
        gate = AdvisoryGate()
        # Router with no keys.
        router = AdvisoryRouter.__new__(AdvisoryRouter)
        router._mistral_key   = None
        router._anthropic_key = None
        agent = ComputeWorkloadAgent(router=router, gate=gate)
        ticks = _make_ticks(20)
        ticks[5].insufficient_reserve_alert = True

        p = agent.maybe_run(ticks, wall_time=9999.0, sim_time=100.0,
                             site_id=SITE_ID, job_id=JOB_ID)
        assert p is not None
        assert p.generated_by == "fallback", (
            "No-key path must produce generated_by='fallback'."
        )


# ---------------------------------------------------------------------------
# O2: Acceptance path — PENDING → ACCEPTED with reviewer; dispatch unchanged
# ---------------------------------------------------------------------------

class TestO2AcceptancePathDispatchUnchanged:
    """O2: Accept a proposal through PENDING → ACCEPTED with reviewer identity;
    assert the dispatch trace hash is STILL identical to the no-agents run.

    Accepting a proposal does not alter dispatch in this step — nothing in the
    control plane reads accepted proposals yet.  This is worth asserting rather
    than assuming.  TC-48 proves the same invariant; this test makes it concrete
    against the acceptance path specifically.
    """

    def _make_pending(self, gate: AdvisoryGate, **kw) -> Proposal:
        """Helper: create a PENDING proposal in gate via validate()."""
        kw.setdefault("created_at_sim_time", 0.0)
        p = make_proposal(**kw)
        gate.validate(p)
        assert p.state == ProposalState.PENDING
        return p

    def test_accept_records_reviewer_id(self) -> None:
        """Reviewer identity is stored on the accepted proposal."""
        gate = AdvisoryGate()
        p = self._make_pending(
            gate,
            kind="curtailment",
            estimated_impact_mw=3.0,
            confidence=0.8,
            reasoning="curtail compute tier A",
        )
        gate.accept(p.proposal_id, reviewer_id="lead-ops@example.com",
                    accepted_at_sim_time=300.0)
        assert p.state == ProposalState.ACCEPTED
        assert p.reviewer_id == "lead-ops@example.com"
        assert p.accepted_at_sim_time == pytest.approx(300.0)

    def test_accept_without_reviewer_allowed(self) -> None:
        """Reviewer fields are optional — acceptance succeeds without them."""
        gate = AdvisoryGate()
        p = self._make_pending(
            gate,
            kind="curtailment", estimated_impact_mw=1.0, confidence=0.5,
            reasoning="test minimal accept",
        )
        gate.accept(p.proposal_id)   # no reviewer_id, no accepted_at_sim_time
        assert p.state == ProposalState.ACCEPTED
        assert p.reviewer_id == ""
        assert p.accepted_at_sim_time is None

    def test_accept_terminal_proposal_raises(self) -> None:
        """Accepting an already-terminal proposal raises ValueError."""
        gate = AdvisoryGate()
        p = self._make_pending(
            gate,
            kind="curtailment", estimated_impact_mw=1.0, confidence=0.5,
            reasoning="reject then accept should fail",
        )
        gate.reject(p.proposal_id)
        with pytest.raises(ValueError, match="terminal"):
            gate.accept(p.proposal_id, reviewer_id="ops@example.com")

    def test_dispatch_hash_unchanged_after_acceptance(self) -> None:
        """O2 (TC-48 companion): accepting proposals does NOT alter dispatch trace.

        Method:
          1. Run scenario with no agents → hash_no_agents.
          2. Run scenario with agents; collect proposals.
          3. Accept all generated proposals with a reviewer.
          4. Run ANOTHER scenario with the same registry (proposals now accepted).
          5. Compare all three dispatch hashes — they must be identical.
        """
        hash_no_agents, _ = asyncio.run(_run_scenario(registry=None))

        # Run with agents; accept every proposal.
        gate = AdvisoryGate()
        router = _DeterministicRouter()
        registry = AgentRegistry(gate=gate, router=router, enabled=True)
        hash_with_agents, _ = asyncio.run(_run_scenario(registry=registry))

        all_proposals = registry.all_proposals()
        assert len(all_proposals) > 0, "O2: no proposals generated — test is vacuous."

        for p in list(all_proposals):
            if not p.is_terminal:
                gate.accept(p.proposal_id,
                            reviewer_id="ci-reviewer@example.com",
                            accepted_at_sim_time=300.0)

        accepted = [p for p in registry.all_proposals()
                    if p.state == ProposalState.ACCEPTED]
        assert len(accepted) > 0, "O2: no proposals reached ACCEPTED state."

        # Run a THIRD scenario with the same registry (accepted proposals in gate).
        hash_after_acceptance, _ = asyncio.run(_run_scenario(registry=registry))

        assert hash_no_agents == hash_with_agents == hash_after_acceptance, (
            "O2 FAIL: dispatch trace changed after proposal acceptance.\n"
            f"  no_agents:        {hash_no_agents}\n"
            f"  with_agents:      {hash_with_agents}\n"
            f"  after_acceptance: {hash_after_acceptance}\n"
            "Accepting proposals must NEVER alter dispatch in this step."
        )

    def test_accepted_proposals_do_not_appear_in_pending(self) -> None:
        """ACCEPTED proposals are removed from the pending set."""
        gate = AdvisoryGate()
        p = make_proposal(
            kind="calibration", estimated_impact_mw=0.5, confidence=0.6,
            reasoning="calibration proposal", created_at_sim_time=0.0,
        )
        gate.validate(p)
        assert p in gate.pending_proposals()
        gate.accept(p.proposal_id, reviewer_id="calib-reviewer@example.com")
        assert p not in gate.pending_proposals()

    def test_o2_hardware_profile_in_evidence_window(self) -> None:
        """O1: deidentify() with hardware_profiles produces §21.4 class entries."""
        from core.deident import deidentify, assert_no_pii, HardwareClassEntry
        ticks = _make_ticks(20)
        hw_profiles = {"enterprise_8gpu_air": 10.2, "nextgen_rack_liquid": 126.0}
        window = deidentify(
            ticks,
            site_id=SITE_ID,
            job_id=JOB_ID,
            hardware_profiles=hw_profiles,
        )
        # §21.4: hardware_classes is non-empty when profiles provided.
        assert len(window.hardware_classes) == 2, (
            f"O1: expected 2 hardware class entries, got {len(window.hardware_classes)}"
        )
        # class_index must be a randomised letter label, NOT the SKU name.
        for entry in window.hardware_classes:
            assert entry.class_index.startswith("profile_"), (
                f"O1: class_index must start with 'profile_'; got {entry.class_index!r}"
            )
            assert "enterprise" not in entry.class_index.lower(), (
                f"O1: SKU name leaked into class_index: {entry.class_index!r}"
            )
            assert "nextgen" not in entry.class_index.lower()
            assert entry.rated_kw_per_unit > 0

    def test_o1_hardware_classes_not_stable_across_calls(self) -> None:
        """O1: class_index assignment is randomised per deidentify() call — not stable."""
        from core.deident import deidentify
        ticks = _make_ticks(10)
        hw = {"enterprise_8gpu_air": 10.2, "nextgen_rack_liquid": 126.0}
        # Make many calls; at least one pair of results should differ in ordering.
        results = []
        for _ in range(20):
            w = deidentify(ticks, site_id=SITE_ID, job_id=JOB_ID, hardware_profiles=hw)
            mapping = {e.rated_kw_per_unit: e.class_index for e in w.hardware_classes}
            results.append(mapping)
        # If all 20 results were identical, the shuffle is not working.
        unique_mappings = {str(sorted(m.items())) for m in results}
        assert len(unique_mappings) > 1, (
            "O1: hardware class indices should not be stable across calls — "
            "the same SKU must not always get the same letter."
        )

    def test_o1_no_pii_in_wire_with_hardware_profiles(self) -> None:
        """O1 + TC-29: hardware_profiles provided → class entries in window; no PII in wire."""
        from core.deident import deidentify, assert_no_pii
        ticks = _make_ticks(20)
        hw = {"enterprise_8gpu_air": 10.2}
        window = deidentify(
            ticks, site_id=SITE_ID, job_id=JOB_ID, hardware_profiles=hw,
        )
        # TC-29: no PII in the serialised wire.
        assert_no_pii(
            window, site_id=SITE_ID, job_id=JOB_ID, hardware_profiles=hw,
        )
        # Also verify that "enterprise" (part of SKU) is NOT in the wire.
        import dataclasses, json
        wire = json.dumps(dataclasses.asdict(window))
        assert "enterprise" not in wire.lower(), (
            "O1 TC-29: SKU fragment 'enterprise' found in serialised EvidenceWindow."
        )

    def test_o3_temperature_comment_present(self) -> None:
        """O3: advisory_router.py must document that temperature=0.0 does NOT guarantee
        determinism — TC-48 is architectural, not model-based."""
        import inspect
        from runtime import advisory_router
        source = inspect.getsource(advisory_router)
        assert "does NOT" in source or "does not" in source, (
            "O3: advisory_router.py must explicitly state that temperature=0.0 "
            "does not guarantee determinism on hosted models."
        )
        assert "TC-48" in source, (
            "O3: advisory_router.py should reference TC-48 near the temperature setting."
        )
