"""
tests/test_kube_capacity_gate.py — Black-box tests for the contracted MW
capacity admission gate (Task #510).

Feature under test: when design_peak_load_mw is declared, the Kube admission
loop must block any new job whose addition would push committed compute MW above
the ceiling.  Deferred jobs are re-queued (never dropped) and retried every tick.

Five cases from the uploaded spec:

  BB-CAP-001 — Core positive block: job that would breach ceiling is deferred.
  BB-CAP-002 — Boundary: job that lands exactly at the ceiling is admitted (strict >).
  BB-CAP-003 — Retry: deferred job is automatically admitted once headroom opens.
  BB-CAP-004 — Running jobs are never evicted by the gate (admission-only gate).
  BB-CAP-005 — Backward compat: no ceiling set → gate is silent on every tick.

All tests are direct unit tests against KubeDemandAgent.tick() so they run
without a full simulator instance.  Poisson arrivals are suppressed
(mean_interarrival_s=1e6) so only manually injected pending admissions fire.
Power-cap is disabled (headroom_threshold_mw=0.0, large ample-grid headroom)
so the MW gate and the power-cap gate do not interfere.

Run with:
    pytest tests/test_kube_capacity_gate.py -v
"""
from __future__ import annotations

import unittest

from core.kube_demand import (
    KubeConfig,
    KubeDemandAgent,
    KubeGridState,
    _ActiveJob,
    _PendingAdmission,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

#: kW consumed per node in all cap-gate tests — round number for clean arithmetic.
_KW_PER_NODE: float = 10.0


def _cap_gate_agent(
    *,
    ceiling_mw: float | None,
    rated_kw_per_node: float = _KW_PER_NODE,
    rng_seed: int = 42,
) -> KubeDemandAgent:
    """
    Minimal KubeDemandAgent configured for cap-gate isolation:

    * capacity_ceiling_mw  — the ceiling under test (None to disable gate).
    * rated_kw_per_node    — power per node used for MW estimates (default 10 kW).
    * max_nodes=9000       — large enough that the node-count cap never triggers.
    * min_nodes=0          — idle cluster draws no baseline.
    * mean_interarrival_s  — extremely high (suppresses Poisson arrivals).
    * reorder_window_s=0   — no ordering delay (injected events drain immediately).
    * ntp_jitter_s=0       — no jitter (deterministic timing).
    * headroom_threshold_mw=0.0 — power-cap fires only when headroom_mw < 0
      (never in the ample-grid state below), so the MW ceiling gate is isolated.
    * power_cap_hysteresis_s=0.0 — no post-recovery hold.
    """
    cfg = KubeConfig(
        max_nodes=9000,
        min_nodes=0,
        rated_kw_per_node=rated_kw_per_node,
        capacity_ceiling_mw=ceiling_mw,
        mean_interarrival_s=1e6,
        reorder_window_s=0.0,
        ntp_jitter_s=0.0,
        headroom_threshold_mw=0.0,
        power_cap_hysteresis_s=0.0,
        rng_seed=rng_seed,
    )
    agent = KubeDemandAgent(cfg, site_id="test-cap-gate")
    # Suppress the initial-tick Poisson arrival so only injected events fire.
    agent._next_arrival_sim_time = 1e9
    return agent


def _ample_grid() -> KubeGridState:
    """
    Grid state with headroom >> 0 so the power-cap gate never activates.
    The cap-gate tests must run without power-cap interference.
    """
    return KubeGridState(
        p_dispatch_required_mw=5.0,
        bess_soc_fraction=0.9,
        turbine_headroom_mw=50.0,
        bess_headroom_mw=20.0,
    )


def _inject_active_job(agent: KubeDemandAgent, node_count: int, job_id: str) -> None:
    """Pre-load a running job directly into the agent (bypasses admission)."""
    agent._active_jobs.append(
        _ActiveJob(
            event_id=job_id,
            node_count=node_count,
            hardware_profile_id="enterprise_8gpu_air",
            admitted_at=0.0,
            ends_at=99999.0,
        )
    )


def _inject_pending(agent: KubeDemandAgent, node_count: int, job_id: str,
                    observed_at: float = 0.0, requeue_count: int = 0) -> None:
    """Push a job into the reorder buffer so it is ready on the next tick call."""
    agent._reorder_buffer.append(
        _PendingAdmission(
            event_id=job_id,
            node_count=node_count,
            hardware_profile_id="enterprise_8gpu_air",
            observed_at=observed_at,
            event_timestamp=observed_at,
            duration_s=300.0,
            first_queued_at=observed_at,
            requeue_count=requeue_count,
        )
    )


def _nodes_for_mw(mw: float, kw_per_node: float = _KW_PER_NODE) -> int:
    """
    Inverse of  MW = nodes × kw_per_node / 1000.
    Returns the integer node count whose compute draw equals mw exactly.
    """
    return round(mw * 1000 / kw_per_node)


# ---------------------------------------------------------------------------
# BB-CAP-001 — Core positive block
# ---------------------------------------------------------------------------

class TestCapGateBlock(unittest.TestCase):
    """
    BB-CAP-001: A job whose compute MW addition would exceed the ceiling is
    deferred by exactly 1, stays in the queue (not dropped), and the already-
    running committed load is unchanged.

    Design:
        ceiling             = 37.8 MW
        active committed MW = 36.0 MW   (3 600 nodes × 10 kW / 1000)
        candidate job MW    =  3.0 MW   (300 nodes × 10 kW / 1000)
        36.0 + 3.0 = 39.0 > 37.8 → BLOCK
    """

    _CEILING_MW = 37.8
    _COMMITTED_NODES = _nodes_for_mw(36.0)   # 3600
    _NEW_JOB_NODES   = _nodes_for_mw(3.0)    #  300

    def _run_one_tick(self):
        agent = _cap_gate_agent(ceiling_mw=self._CEILING_MW)
        _inject_active_job(agent, self._COMMITTED_NODES, "pre-job-1")
        _inject_pending(agent, self._NEW_JOB_NODES, "candidate-001")
        agent._started = True
        agent._last_total_nodes = self._COMMITTED_NODES
        _signals, metrics = agent.tick(
            sim_time=10.0, dt_seconds=5.0, grid_state=_ample_grid()
        )
        return agent, metrics

    def test_cap_gate_deferred_count_is_one(self):
        """cap_gate_deferred_count must be exactly 1 when one job is blocked."""
        _agent, metrics = self._run_one_tick()
        self.assertEqual(
            metrics.cap_gate_deferred_count, 1,
            msg=(
                f"Expected cap_gate_deferred_count=1 when the candidate job "
                f"({self._NEW_JOB_NODES} nodes = {self._NEW_JOB_NODES * _KW_PER_NODE / 1000:.1f} MW) "
                f"would push committed ({self._COMMITTED_NODES * _KW_PER_NODE / 1000:.1f} MW) "
                f"above ceiling ({self._CEILING_MW} MW). "
                f"Got {metrics.cap_gate_deferred_count}."
            ),
        )

    def test_job_not_admitted(self):
        """The blocked job must not appear in active_jobs."""
        _agent, metrics = self._run_one_tick()
        self.assertEqual(
            metrics.active_jobs, 1,   # only the pre-existing job
            msg=(
                f"Expected active_jobs=1 (only the pre-existing job); "
                f"got {metrics.active_jobs}.  The candidate job must be deferred, "
                f"not admitted, when its addition would breach the ceiling."
            ),
        )

    def test_committed_nodes_unchanged(self):
        """admitted_nodes must reflect only the pre-existing load, not the candidate."""
        _agent, metrics = self._run_one_tick()
        self.assertEqual(
            metrics.admitted_nodes, self._COMMITTED_NODES,
            msg=(
                f"admitted_nodes must remain at {self._COMMITTED_NODES} "
                f"(pre-existing load = {self._COMMITTED_NODES * _KW_PER_NODE / 1000:.1f} MW) "
                f"when the gate defers the candidate. Got {metrics.admitted_nodes}."
            ),
        )

    def test_job_stays_in_queue_not_dropped(self):
        """
        The blocked job must survive in the reorder buffer — never dropped.
        (deferred ≠ rejected; design convention from project docs.)
        """
        agent, _metrics = self._run_one_tick()
        self.assertGreater(
            len(agent._reorder_buffer), 0,
            msg=(
                "After a cap-gate deferral, the reorder buffer must be non-empty. "
                "The deferred job must be re-queued with a -capdefer-N suffix, "
                "not dropped."
            ),
        )
        # The re-queued entry must carry the original node count forward.
        deferred_node_counts = [pa.node_count for pa in agent._reorder_buffer]
        self.assertIn(
            self._NEW_JOB_NODES, deferred_node_counts,
            msg=(
                f"Expected the deferred job's node_count ({self._NEW_JOB_NODES}) "
                f"to appear in the reorder buffer after deferral. "
                f"Found counts: {deferred_node_counts}."
            ),
        )

    def test_power_cap_not_active(self):
        """
        The power-cap gate must remain inactive (headroom >> 0) so this test
        isolates the MW ceiling gate from the power-cap gate.
        """
        _agent, metrics = self._run_one_tick()
        self.assertFalse(
            metrics.power_cap_active,
            msg=(
                "power_cap_active must be False in the ample-grid state. "
                "If True, the power-cap gate is interfering with BB-CAP-001 — "
                "check that headroom_threshold_mw=0 and ample headroom is supplied."
            ),
        )


# ---------------------------------------------------------------------------
# BB-CAP-002 — Boundary: exactly at the ceiling is admitted, not blocked
# ---------------------------------------------------------------------------

class TestCapGateBoundary(unittest.TestCase):
    """
    BB-CAP-002: A job that lands exactly at the ceiling must be admitted.

    The gate uses strict inequality (committed + new > ceiling), so
    committed + new = ceiling is the boundary case that passes.

    SPEC DECISION: implemented as strict-greater-than (>), not >=.
    This aligns with the spec instruction: "Flag as SPEC-GAP if the
    implementation treats >= as the block condition."  The present
    implementation does not — it uses strict >.

    Design:
        ceiling             = 37.8 MW
        active committed MW = 35.0 MW   (3 500 nodes × 10 kW / 1000)
        candidate job MW    =  2.8 MW   (280 nodes × 10 kW / 1000)
        35.0 + 2.8 = 37.8 = ceiling  →  not (37.8 > 37.8)  →  ADMIT
    """

    _CEILING_MW      = 37.8
    _COMMITTED_NODES = _nodes_for_mw(35.0)   # 3500
    _NEW_JOB_NODES   = _nodes_for_mw(2.8)    #  280

    def _run_one_tick(self):
        agent = _cap_gate_agent(ceiling_mw=self._CEILING_MW)
        _inject_active_job(agent, self._COMMITTED_NODES, "pre-job-boundary")
        _inject_pending(agent, self._NEW_JOB_NODES, "boundary-job-001")
        agent._started = True
        agent._last_total_nodes = self._COMMITTED_NODES
        _signals, metrics = agent.tick(
            sim_time=10.0, dt_seconds=5.0, grid_state=_ample_grid()
        )
        return metrics

    def test_boundary_job_admitted(self):
        """
        A job that takes committed load exactly to the ceiling must be admitted.
        The gate uses strict > so equality passes.
        """
        metrics = self._run_one_tick()
        self.assertEqual(
            metrics.active_jobs, 2,   # pre-existing + new boundary job
            msg=(
                f"Expected active_jobs=2 when committed ({self._COMMITTED_NODES * _KW_PER_NODE / 1000:.1f} MW) "
                f"+ new ({self._NEW_JOB_NODES * _KW_PER_NODE / 1000:.1f} MW) = {self._CEILING_MW} MW = ceiling. "
                f"Strict > means equal-to-ceiling must pass (be admitted). "
                f"Got active_jobs={metrics.active_jobs}."
            ),
        )

    def test_cap_gate_deferred_count_is_zero(self):
        """cap_gate_deferred_count must be 0 for the boundary-admit case."""
        metrics = self._run_one_tick()
        self.assertEqual(
            metrics.cap_gate_deferred_count, 0,
            msg=(
                f"cap_gate_deferred_count must be 0 when the boundary job is admitted. "
                f"Got {metrics.cap_gate_deferred_count}."
            ),
        )

    def test_committed_nodes_includes_new_job(self):
        """After admission, admitted_nodes must include both jobs."""
        metrics = self._run_one_tick()
        expected = self._COMMITTED_NODES + self._NEW_JOB_NODES
        self.assertEqual(
            metrics.admitted_nodes, expected,
            msg=(
                f"admitted_nodes must be {expected} "
                f"({self._COMMITTED_NODES} pre-existing + {self._NEW_JOB_NODES} new) "
                f"after boundary admission. Got {metrics.admitted_nodes}."
            ),
        )


# ---------------------------------------------------------------------------
# BB-CAP-003 — Deferred job admitted once headroom opens
# ---------------------------------------------------------------------------

class TestCapGateRetryOnHeadroomRecovery(unittest.TestCase):
    """
    BB-CAP-003: A job deferred by the cap gate must be automatically admitted
    on the tick where headroom becomes sufficient.  No manual operator action.

    Sequence (dt=5 s):
        tick(10): committed=36.0 MW, candidate=3.0 MW → 39.0 > 37.8 → deferred.
                  Retry queued at observed_at=15.0.
        tick(15): committed drops to 33.0 MW (old job completes); retry is ready
                  (observed_at=15, reorder_window=0).
                  33.0 + 3.0 = 36.0 ≤ 37.8 → admitted.

    Also verifies:
    • The admitted job is not in a "poisoned" state; it draws the correct node count.
    • cap_gate_deferred_count returns to 0 after the retry succeeds.
    • The ordering behaviour when partial headroom opens is documented (FIFO by
      injection order, since re-queued entries use observed_at=sim_time+dt which
      sorts them in deferral order).
    """

    _CEILING_MW    = 37.8
    _COMMIT_HIGH   = _nodes_for_mw(36.0)   # 3600 — too high for the 3-MW job
    _COMMIT_LOW    = _nodes_for_mw(33.0)   # 3300 — headroom opens
    _NEW_JOB_NODES = _nodes_for_mw(3.0)    #  300

    def test_deferred_job_admitted_after_headroom_recovery(self):
        """
        BB-CAP-003a: The deferred job must be admitted automatically on the tick
        where headroom becomes ≥ the job's projected MW.
        """
        agent = _cap_gate_agent(ceiling_mw=self._CEILING_MW)

        # ── Tick 1 (sim_time=10): high load, job blocked ──────────────────────
        _inject_active_job(agent, self._COMMIT_HIGH, "pre-job-high")
        _inject_pending(agent, self._NEW_JOB_NODES, "retry-job-001")
        agent._started = True
        agent._last_total_nodes = self._COMMIT_HIGH

        _sig1, m1 = agent.tick(
            sim_time=10.0, dt_seconds=5.0, grid_state=_ample_grid()
        )
        self.assertEqual(
            m1.cap_gate_deferred_count, 1,
            msg=f"Tick 1: expected 1 deferral, got {m1.cap_gate_deferred_count}.",
        )
        self.assertEqual(
            m1.active_jobs, 1,
            msg=f"Tick 1: expected 1 active job (pre-existing only), got {m1.active_jobs}.",
        )

        # ── Drop active load to simulate a running job completing ─────────────
        # Remove the large job and replace with a smaller one so committed MW
        # falls to 33.0 MW.  We clear and re-inject to keep the state clean.
        agent._active_jobs.clear()
        _inject_active_job(agent, self._COMMIT_LOW, "pre-job-low")
        agent._last_total_nodes = self._COMMIT_LOW

        # ── Tick 2 (sim_time=15): headroom opens, retry drains ────────────────
        # The re-queued job has observed_at=15.0 (sim_time=10 + dt=5);
        # reorder_window=0 so it is ready at sim_time=15.
        _sig2, m2 = agent.tick(
            sim_time=15.0, dt_seconds=5.0, grid_state=_ample_grid()
        )
        self.assertEqual(
            m2.active_jobs, 2,
            msg=(
                f"Tick 2: expected active_jobs=2 (pre-low + formerly-deferred job). "
                f"Got {m2.active_jobs}.  Re-queued job must be admitted when headroom "
                f"({self._CEILING_MW} - {self._COMMIT_LOW * _KW_PER_NODE / 1000:.1f} = "
                f"{self._CEILING_MW - self._COMMIT_LOW * _KW_PER_NODE / 1000:.1f} MW) "
                f"≥ job MW ({self._NEW_JOB_NODES * _KW_PER_NODE / 1000:.1f} MW)."
            ),
        )
        self.assertEqual(
            m2.cap_gate_deferred_count, 0,
            msg=(
                f"Tick 2: cap_gate_deferred_count must be 0 after the retry succeeds. "
                f"Got {m2.cap_gate_deferred_count}."
            ),
        )

    def test_admitted_job_has_correct_node_count(self):
        """
        BB-CAP-003b: The admitted job must carry its original node count —
        no information is lost across the deferral-and-retry cycle.
        """
        agent = _cap_gate_agent(ceiling_mw=self._CEILING_MW)
        _inject_active_job(agent, self._COMMIT_HIGH, "pre-h")
        _inject_pending(agent, self._NEW_JOB_NODES, "retry-nodecount")
        agent._started = True
        agent._last_total_nodes = self._COMMIT_HIGH

        agent.tick(sim_time=10.0, dt_seconds=5.0, grid_state=_ample_grid())

        # Drop load, retry
        agent._active_jobs.clear()
        _inject_active_job(agent, self._COMMIT_LOW, "pre-l")
        agent._last_total_nodes = self._COMMIT_LOW
        _sig, m = agent.tick(sim_time=15.0, dt_seconds=5.0, grid_state=_ample_grid())

        admitted_counts = [j.node_count for j in agent._active_jobs]
        self.assertIn(
            self._NEW_JOB_NODES, admitted_counts,
            msg=(
                f"The admitted job must preserve its original node count "
                f"({self._NEW_JOB_NODES}) after deferral-and-retry. "
                f"Active job node counts: {admitted_counts}."
            ),
        )

    def test_admitted_nodes_sum_matches_expectation(self):
        """
        BB-CAP-003c: After retry admission, admitted_nodes must equal
        COMMIT_LOW + NEW_JOB_NODES (33.0 + 3.0 = 36.0 MW worth of nodes).
        """
        agent = _cap_gate_agent(ceiling_mw=self._CEILING_MW)
        _inject_active_job(agent, self._COMMIT_HIGH, "pre-H")
        _inject_pending(agent, self._NEW_JOB_NODES, "retry-sum")
        agent._started = True
        agent._last_total_nodes = self._COMMIT_HIGH

        agent.tick(sim_time=10.0, dt_seconds=5.0, grid_state=_ample_grid())

        agent._active_jobs.clear()
        _inject_active_job(agent, self._COMMIT_LOW, "pre-L")
        agent._last_total_nodes = self._COMMIT_LOW
        _, m = agent.tick(sim_time=15.0, dt_seconds=5.0, grid_state=_ample_grid())

        expected_admitted = self._COMMIT_LOW + self._NEW_JOB_NODES
        self.assertEqual(
            m.admitted_nodes, expected_admitted,
            msg=(
                f"admitted_nodes must be {expected_admitted} "
                f"({self._COMMIT_LOW} + {self._NEW_JOB_NODES}) after retry. "
                f"Got {m.admitted_nodes}."
            ),
        )


# ---------------------------------------------------------------------------
# BB-CAP-004 — Running jobs are never evicted by the gate
# ---------------------------------------------------------------------------

class TestCapGateNoEviction(unittest.TestCase):
    """
    BB-CAP-004: The cap gate is admission-only.  Already-running jobs must
    not be touched (evicted, paused, or power-reduced) when the gate activates.

    Two sub-cases:
      TC-P4a: Committed load near ceiling, many ticks with no new admissions
              → running jobs are stable across every tick.
      TC-P4b: Submit one job that would breach; only the candidate is deferred —
              the pre-existing job is untouched.

    Distinguishing from the power-cap eviction path (headroom < 0):
    The cap gate checks MW ceiling at admission time only.  It has no southbound
    command authority over running jobs.  The power-cap eviction branch
    (headroom_mw < 0) is separate and intentional; this test does not trigger it.
    """

    _CEILING_MW     = 37.8
    _NEAR_CAP_NODES = _nodes_for_mw(37.5)   # 3750  → 37.5 MW, 0.3 MW below ceiling
    _BREACH_NODES   = _nodes_for_mw(1.0)    #  100  → 1.0 MW, total 38.5 > 37.8

    def test_running_jobs_stable_across_multiple_ticks(self):
        """
        TC-P4a: Running at 37.5 MW (near ceiling) with no new arrivals.
        After 5 ticks, active_jobs must still be 1 and admitted_nodes unchanged.
        """
        agent = _cap_gate_agent(ceiling_mw=self._CEILING_MW)
        _inject_active_job(agent, self._NEAR_CAP_NODES, "near-cap-job")
        agent._started = True
        agent._last_total_nodes = self._NEAR_CAP_NODES

        for tick_idx in range(5):
            sim_t = 10.0 + tick_idx * 5.0
            _, m = agent.tick(sim_time=sim_t, dt_seconds=5.0, grid_state=_ample_grid())
            self.assertEqual(
                m.active_jobs, 1,
                msg=(
                    f"Tick {tick_idx}: active_jobs must stay at 1 "
                    f"(cap gate must not evict running jobs). Got {m.active_jobs}."
                ),
            )
            self.assertEqual(
                m.admitted_nodes, self._NEAR_CAP_NODES,
                msg=(
                    f"Tick {tick_idx}: admitted_nodes must stay at {self._NEAR_CAP_NODES}. "
                    f"Got {m.admitted_nodes}."
                ),
            )

    def test_only_candidate_deferred_running_job_untouched(self):
        """
        TC-P4b: Running job at 37.5 MW, submit 1 MW candidate → total 38.5 > 37.8.
        Only the candidate is deferred; the running job is completely unaffected.
        """
        agent = _cap_gate_agent(ceiling_mw=self._CEILING_MW)
        _inject_active_job(agent, self._NEAR_CAP_NODES, "running-job-1")
        _inject_pending(agent, self._BREACH_NODES, "breach-candidate")
        agent._started = True
        agent._last_total_nodes = self._NEAR_CAP_NODES

        _, m = agent.tick(sim_time=10.0, dt_seconds=5.0, grid_state=_ample_grid())

        # Running job survives
        self.assertEqual(
            m.active_jobs, 1,
            msg=(
                f"active_jobs must be 1 (running job). Got {m.active_jobs}. "
                f"The cap gate must not evict or reduce the running job."
            ),
        )
        self.assertEqual(
            m.admitted_nodes, self._NEAR_CAP_NODES,
            msg=(
                f"admitted_nodes must equal the running job's nodes "
                f"({self._NEAR_CAP_NODES}). Got {m.admitted_nodes}."
            ),
        )
        # Candidate is deferred, not admitted
        self.assertEqual(
            m.cap_gate_deferred_count, 1,
            msg=(
                f"cap_gate_deferred_count must be 1 (only the candidate deferred). "
                f"Got {m.cap_gate_deferred_count}."
            ),
        )

    def test_deferred_candidate_stays_in_queue(self):
        """
        TC-P4c: The deferred candidate must be re-queued, not dropped.
        (Mirrors BB-CAP-001 framing but asserts from the running-jobs context.)
        """
        agent = _cap_gate_agent(ceiling_mw=self._CEILING_MW)
        _inject_active_job(agent, self._NEAR_CAP_NODES, "running-job-2")
        _inject_pending(agent, self._BREACH_NODES, "breach-candidate-2")
        agent._started = True
        agent._last_total_nodes = self._NEAR_CAP_NODES

        agent.tick(sim_time=10.0, dt_seconds=5.0, grid_state=_ample_grid())

        self.assertGreater(
            len(agent._reorder_buffer), 0,
            msg=(
                "Reorder buffer must be non-empty after deferral. "
                "The blocked candidate must be re-queued with a -capdefer-N suffix."
            ),
        )


# ---------------------------------------------------------------------------
# BB-CAP-005 — Backward compatibility: no ceiling → gate silent
# ---------------------------------------------------------------------------

class TestCapGateBackwardCompat(unittest.TestCase):
    """
    BB-CAP-005: Scenarios without design_peak_load_mw (capacity_ceiling_mw=None)
    must show zero behavioral change from pre-Task-#510 baseline.

    Specifically:
    • cap_gate_deferred_count is always 0.
    • Jobs that would exceed any hypothetical cap are freely admitted.
    • The power balance (admitted_nodes, active_jobs) is identical to an agent
      with no cap configured.

    This is the regression guard: all existing scenarios without
    design_peak_load_mw set must remain bit-identical after the gate code landed.
    """

    # Deliberately high load that would trigger a 37.8 MW ceiling if one were set.
    _NO_CEILING_NODES = _nodes_for_mw(40.0)   # 4000 nodes → 40 MW, above any 37.8 ceiling
    _EXTRA_JOB_NODES  = _nodes_for_mw(5.0)    #  500 nodes → 5 MW

    def test_no_gate_when_ceiling_is_none(self):
        """
        With capacity_ceiling_mw=None, any job is admitted regardless of load.
        cap_gate_deferred_count must be 0.
        """
        agent = _cap_gate_agent(ceiling_mw=None)
        _inject_active_job(agent, self._NO_CEILING_NODES, "no-cap-base")
        _inject_pending(agent, self._EXTRA_JOB_NODES, "no-cap-candidate")
        agent._started = True
        agent._last_total_nodes = self._NO_CEILING_NODES

        _, m = agent.tick(sim_time=10.0, dt_seconds=5.0, grid_state=_ample_grid())

        self.assertEqual(
            m.cap_gate_deferred_count, 0,
            msg=(
                f"cap_gate_deferred_count must be 0 when capacity_ceiling_mw=None. "
                f"Got {m.cap_gate_deferred_count}.  The gate must not activate when "
                f"no ceiling is declared."
            ),
        )
        self.assertEqual(
            m.active_jobs, 2,
            msg=(
                f"Both jobs must be admitted (active_jobs=2) when no ceiling is set. "
                f"Got {m.active_jobs}."
            ),
        )

    def test_no_gate_across_multiple_ticks(self):
        """
        BB-CAP-005b: Over several ticks with high load and multiple arrivals,
        cap_gate_deferred_count must remain 0 throughout when ceiling is None.
        """
        agent = _cap_gate_agent(ceiling_mw=None)
        _inject_active_job(agent, self._NO_CEILING_NODES, "nc-base")
        agent._started = True
        agent._last_total_nodes = self._NO_CEILING_NODES

        for tick_idx in range(5):
            sim_t = 10.0 + tick_idx * 5.0
            # Inject a fresh pending job each tick to simulate continuous arrivals
            _inject_pending(
                agent,
                self._EXTRA_JOB_NODES,
                f"nc-job-{tick_idx}",
                observed_at=sim_t - 1.0,  # already past reorder window
            )
            _, m = agent.tick(sim_time=sim_t, dt_seconds=5.0, grid_state=_ample_grid())
            self.assertEqual(
                m.cap_gate_deferred_count, 0,
                msg=(
                    f"Tick {tick_idx}: cap_gate_deferred_count must stay 0 with no ceiling. "
                    f"Got {m.cap_gate_deferred_count}."
                ),
            )

    def test_admitted_nodes_matches_no_cap_baseline(self):
        """
        BB-CAP-005c: The total admitted node count with ceiling=None must be
        identical to what would be admitted without the gate code at all.

        Baseline: 1 pre-existing job (4000 nodes) + 1 candidate (500 nodes) = 4500.
        With ceiling=None: same 4500 nodes admitted.  No regression.
        """
        agent = _cap_gate_agent(ceiling_mw=None)
        _inject_active_job(agent, self._NO_CEILING_NODES, "baseline-job")
        _inject_pending(agent, self._EXTRA_JOB_NODES, "baseline-candidate")
        agent._started = True
        agent._last_total_nodes = self._NO_CEILING_NODES

        _, m = agent.tick(sim_time=10.0, dt_seconds=5.0, grid_state=_ample_grid())

        expected = self._NO_CEILING_NODES + self._EXTRA_JOB_NODES
        self.assertEqual(
            m.admitted_nodes, expected,
            msg=(
                f"admitted_nodes must be {expected} ({self._NO_CEILING_NODES} + "
                f"{self._EXTRA_JOB_NODES}) with no ceiling. Got {m.admitted_nodes}."
            ),
        )


# ---------------------------------------------------------------------------
# Suite-level checks
# ---------------------------------------------------------------------------

class TestCapGateSuiteLevelProperties(unittest.TestCase):
    """
    Suite-level checks that cut across all five BB-CAP-* cases.

    SL-1: Single source of truth — the cap decision and cap_gate_deferred_count
          must come from the same arithmetic in the admission loop; there is no
          second comparison elsewhere.

    SL-2: Determinism (AT-7) — repeated runs with the same seed and config
          produce bit-identical results.

    SL-3: cap_gate_deferred_count never goes negative.
    """

    def test_sl2_determinism_same_seed(self):
        """
        SL-2 (AT-7): Running the same tick twice with the same agent state
        must produce identical cap_gate_deferred_count values.

        Uses a fresh agent for each run (same config, same injected state)
        so no shared mutable state can cause divergence.
        """
        def _one_run(seed: int) -> int:
            agent = _cap_gate_agent(ceiling_mw=37.8, rng_seed=seed)
            _inject_active_job(agent, _nodes_for_mw(36.0), "det-job-1")
            _inject_pending(agent, _nodes_for_mw(3.0), "det-cand")
            agent._started = True
            agent._last_total_nodes = _nodes_for_mw(36.0)
            _, m = agent.tick(sim_time=10.0, dt_seconds=5.0, grid_state=_ample_grid())
            return m.cap_gate_deferred_count

        result_a = _one_run(seed=42)
        result_b = _one_run(seed=42)

        self.assertEqual(
            result_a, result_b,
            msg=(
                f"cap_gate_deferred_count must be deterministic across identical runs. "
                f"Run A={result_a}, Run B={result_b}.  Check for any RNG or wall-clock "
                f"dependency introduced by the gate or retry logic."
            ),
        )

    def test_sl3_deferred_count_never_negative(self):
        """
        SL-3: cap_gate_deferred_count must be ≥ 0 on every tick,
        even when no jobs are pending and the gate is configured.
        """
        agent = _cap_gate_agent(ceiling_mw=37.8)
        agent._started = True

        for tick_idx in range(10):
            sim_t = 10.0 + tick_idx * 5.0
            _, m = agent.tick(sim_time=sim_t, dt_seconds=5.0, grid_state=_ample_grid())
            self.assertGreaterEqual(
                m.cap_gate_deferred_count, 0,
                msg=(
                    f"Tick {tick_idx}: cap_gate_deferred_count={m.cap_gate_deferred_count} "
                    f"is negative.  This count is a non-negative per-tick accumulator."
                ),
            )

    def test_sl1_gate_uses_capacity_ceiling_mw_from_config(self):
        """
        SL-1: The gate reads capacity_ceiling_mw from KubeConfig at tick time.
        Changing the ceiling before the tick changes gate behaviour — confirming
        the decision is evaluated from config, not from a hardcoded literal.
        """
        # Low ceiling → job blocked
        agent_low = _cap_gate_agent(ceiling_mw=5.0)
        _inject_pending(agent_low, _nodes_for_mw(10.0), "sl1-low")
        agent_low._started = True
        _, m_low = agent_low.tick(sim_time=10.0, dt_seconds=5.0, grid_state=_ample_grid())

        # High ceiling → job admitted
        agent_high = _cap_gate_agent(ceiling_mw=50.0)
        _inject_pending(agent_high, _nodes_for_mw(10.0), "sl1-high")
        agent_high._started = True
        _, m_high = agent_high.tick(sim_time=10.0, dt_seconds=5.0, grid_state=_ample_grid())

        self.assertEqual(
            m_low.cap_gate_deferred_count, 1,
            msg=f"Low ceiling (5 MW): expected deferral. Got {m_low.cap_gate_deferred_count}.",
        )
        self.assertEqual(
            m_high.cap_gate_deferred_count, 0,
            msg=f"High ceiling (50 MW): expected admission. Got {m_high.cap_gate_deferred_count}.",
        )


if __name__ == "__main__":
    unittest.main()
