"""
tests/test_kube_powercap.py — Validate power-cap behaviour in KubeDemandAgent.

The KubeDemandAgent has a headroom_threshold_mw gate:
  * When grid headroom < threshold, new admissions are held (power_cap_active=True)
    and re-queued so no jobs are silently dropped.
  * When headroom < 0 (critical), the largest running job is evicted immediately.

These tests confirm that:
  1. Eviction fires when headroom goes negative — active_jobs drops and a SCALE
     signal is emitted (the "job-end" signal visible on TickResult.kube_metrics).
  2. The power-cap hold correctly re-queues admissions (requeued_this_tick > 0)
     rather than silently admitting or dropping them.
  3. insufficient_reserve_alert still fires end-to-end for load that reaches the
     arbitrator before the cap engages.  The cap must not mask physical risk.

TC-P1: Direct unit — eviction when headroom_mw < 0
TC-P2: Direct unit — power-cap hold: admissions are re-queued, not silently dropped
TC-P3: E2E — alert fires even when the power-cap is active on the same run
"""
from __future__ import annotations

import asyncio
import unittest

from core.kube_demand import (
    KubeConfig,
    KubeDemandAgent,
    KubeGridState,
    _ActiveJob,          # private but accessible in tests; intentional
)
from core.models import WorkloadEventType
from runtime.run_manager import RunManager, WebSocketHub
from runtime.scenario_factory import build_run_context


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _tight_kube_cfg(*, rng_seed: int = 7) -> KubeConfig:
    """
    KubeConfig calibrated so the first admitted job creates a large load spike.

    mean_job_nodes=800, hardware_profile_id="enterprise_8gpu_air"
      => delta_P ≈ 800 × 10.2 kW × PUE 1.03 / 1000 ≈ 8.4 MW per STARTING event.

    Against a 5 MW turbine + 2 MW BESS (7 MW total), shortfall ≈ 1.4 MW with
    dt_lead=0, so insufficient_reserve_alert fires immediately.

    reorder_window_s=0, ntp_jitter_s=0 → fully deterministic, first job drains
    in the same tick it arrives.
    """
    return KubeConfig(
        max_nodes=3000,
        min_nodes=0,
        hardware_profile_id="enterprise_8gpu_air",
        mean_job_nodes=800,
        job_node_std=30,
        min_job_nodes=400,
        mean_interarrival_s=20.0,
        mean_job_duration_s=600.0,
        min_job_duration_s=60.0,
        reorder_window_s=0.0,
        ntp_jitter_s=0.0,
        headroom_threshold_mw=50.0,   # tight: almost always active once load arrives
        rng_seed=rng_seed,
    )


async def _run_powercap_e2e(run_id: str) -> list:
    """
    Build and run a power-cap-stress scenario for 300 simulated seconds.

    Fleet: 5 MW turbine + 2 MW BESS — small so headroom shrinks fast.
    KubeDemandAgent: large jobs (mean 800 nodes) with dt_lead forced to 0.
    headroom_threshold_mw=50.0 means the cap almost always fires after tick 1.

    dt_lead is forced to 0 at the apply_workload_signal callsite so the
    arbitrator sees no turbine-ramp credit and the first STARTING event fires
    an alert.  This is deliberately the "no advance notice" worst case.

    Returns ctx.sink.rows — a list of TickResult objects.
    """
    hub = WebSocketHub()
    manager = RunManager(hub)

    ctx = build_run_context(
        run_id,
        job_id="kube-placeholder",
        node_count=0,
        turbine_rated_mw=5.0,
        bess_rated_mw=2.0,
        bess_usable_mwh=1.0,
        bess_grid_forming=False,
        end_sim_time=300.0,
    )

    ctx.sim_state.kube_agent = KubeDemandAgent(
        _tight_kube_cfg(rng_seed=7),
        site_id=ctx.sim_state.site.site_id,
    )

    # Force dt_lead=0: no turbine ramp credit → alert fires on every STARTING event.
    _original = ctx.sim_state.apply_workload_signal

    def _zero_lead_apply(signal, dt_lead_seconds):  # noqa: ANN001
        return _original(signal, dt_lead_seconds=0.0)

    ctx.sim_state.apply_workload_signal = _zero_lead_apply  # type: ignore[method-assign]

    await manager.start_run(ctx)
    await manager._tasks[ctx.run_id]
    return ctx.sink.rows


# ---------------------------------------------------------------------------
# TC-P1: Direct unit — eviction fires when headroom_mw < 0
# ---------------------------------------------------------------------------

class TestKubePowercapEviction(unittest.TestCase):
    """
    TC-P1: Directly inject an active job then call tick() with a KubeGridState
    whose headroom sum is negative.  The agent must:
      • reduce active_jobs from 1 → 0 (largest job evicted)
      • emit a SCALE WorkloadSignal reflecting the lower node count
    """

    def _make_agent_with_one_job(self) -> KubeDemandAgent:
        """Create an agent and pre-inject one running job (bypassing admission)."""
        cfg = KubeConfig(
            max_nodes=2000,
            min_nodes=0,
            rng_seed=1,
            headroom_threshold_mw=5.0,
        )
        agent = KubeDemandAgent(cfg, site_id="test-site")

        # Inject a running job directly so we control eviction timing
        agent._active_jobs.append(
            _ActiveJob(
                event_id="pre-loaded-job-1",
                node_count=600,
                hardware_profile_id="enterprise_8gpu_air",
                admitted_at=0.0,
                ends_at=9999.0,
            )
        )
        # Mark the agent as started so the first tick emits SCALE not STARTING
        agent._started = True
        agent._last_total_nodes = 600

        return agent

    def test_eviction_reduces_active_jobs(self):
        """
        TC-P1a: When headroom_mw < 0 the agent evicts the largest job, reducing
        active_jobs from 1 to 0 in the returned KubeMetrics.
        """
        agent = self._make_agent_with_one_job()

        # Pass a grid state with negative combined headroom (< 0 triggers eviction).
        # KubeGridState fields are unclamped — the simulation_core clamps before
        # storage, but the agent itself only reads the value; negative is valid here.
        critical_grid = KubeGridState(
            p_dispatch_required_mw=10.0,
            bess_soc_fraction=0.1,
            turbine_headroom_mw=-3.0,   # turbine is over-dispatched
            bess_headroom_mw=-2.0,       # BESS is over-dispatched
        )

        _signals, metrics = agent.tick(
            sim_time=50.0, dt_seconds=5.0, grid_state=critical_grid
        )

        self.assertEqual(
            metrics.active_jobs, 0,
            msg=(
                f"Expected active_jobs=0 after eviction (headroom=-5.0 MW < 0), "
                f"got {metrics.active_jobs}.  The eviction branch in tick() must "
                f"pop the largest job when headroom_mw < 0."
            ),
        )

    def test_eviction_emits_scale_signal(self):
        """
        TC-P1b: Eviction reduces total_nodes, so tick() must emit a SCALE
        WorkloadSignal reflecting the lower node count.  This is the job-end
        signal that operators and the arbitrator observe.
        """
        agent = self._make_agent_with_one_job()

        critical_grid = KubeGridState(
            p_dispatch_required_mw=10.0,
            bess_soc_fraction=0.1,
            turbine_headroom_mw=-3.0,
            bess_headroom_mw=-2.0,
        )

        signals, metrics = agent.tick(
            sim_time=50.0, dt_seconds=5.0, grid_state=critical_grid
        )

        self.assertEqual(
            len(signals), 1,
            msg=(
                f"Expected exactly 1 WorkloadSignal after eviction, got {len(signals)}. "
                f"The SCALE signal is the job-end marker visible on TickResult."
            ),
        )
        self.assertEqual(
            signals[0].event_type, WorkloadEventType.SCALE,
            msg=(
                f"Expected SCALE signal after eviction, got {signals[0].event_type}. "
                f"STARTING should only fire on tick 0 (not self._started)."
            ),
        )
        # After evicting the only job with min_nodes=0, total_nodes must be 0
        self.assertEqual(
            signals[0].node_count, 0,
            msg=(
                f"Expected node_count=0 (no jobs, min_nodes=0) in SCALE signal, "
                f"got {signals[0].node_count}."
            ),
        )

    def test_eviction_targets_largest_job(self):
        """
        TC-P1c: With two running jobs of different sizes, eviction must remove
        the LARGER one first (fastest headroom recovery).
        """
        cfg = KubeConfig(max_nodes=3000, min_nodes=0, rng_seed=2)
        agent = KubeDemandAgent(cfg, site_id="test-site")
        agent._active_jobs.extend([
            _ActiveJob("job-small", 200, "enterprise_8gpu_air", 0.0, 9999.0),
            _ActiveJob("job-large", 800, "enterprise_8gpu_air", 0.0, 9999.0),
        ])
        agent._started = True
        agent._last_total_nodes = 1000   # 200 + 800

        critical_grid = KubeGridState(
            p_dispatch_required_mw=15.0,
            bess_soc_fraction=0.05,
            turbine_headroom_mw=-4.0,
            bess_headroom_mw=-1.0,
        )

        _signals, metrics = agent.tick(
            sim_time=100.0, dt_seconds=5.0, grid_state=critical_grid
        )

        # After evicting the largest (800-node) job, 200 remain
        self.assertEqual(
            metrics.active_jobs, 1,
            msg=(
                f"Expected 1 active job after evicting the largest; got {metrics.active_jobs}."
            ),
        )
        self.assertEqual(
            metrics.admitted_nodes, 200,
            msg=(
                f"Expected admitted_nodes=200 (small job surviving) after eviction, "
                f"got {metrics.admitted_nodes}.  Eviction must target the largest job."
            ),
        )


# ---------------------------------------------------------------------------
# TC-P2: Direct unit — power-cap hold re-queues admissions
# ---------------------------------------------------------------------------

class TestKubePowercapHold(unittest.TestCase):
    """
    TC-P2: When headroom < headroom_threshold_mw, ready admissions must be
    re-queued (requeued_this_tick > 0) rather than admitted or silently dropped.

    No job should be lost — each re-queued event gets a retry_id that will be
    drained later when headroom recovers.
    """

    def _make_agent(self) -> KubeDemandAgent:
        agent = KubeDemandAgent(
            KubeConfig(
                max_nodes=2000,
                min_nodes=0,
                mean_interarrival_s=1000.0,   # no Poisson arrivals during test
                reorder_window_s=0.0,
                ntp_jitter_s=0.0,
                headroom_threshold_mw=10.0,   # cap triggers below 10 MW
                rng_seed=3,
            ),
            site_id="test-site",
        )
        # Skip the initial Poisson arrival: _next_arrival_sim_time starts at 0.0
        # which means the first tick() call would generate one arrival regardless
        # of mean_interarrival_s.  Push it far beyond the test window so we only
        # see the manually injected events.
        agent._next_arrival_sim_time = 99999.0
        return agent

    def test_jobs_requeued_not_admitted_under_cap(self):
        """
        TC-P2a: An admission that arrives when power_cap_active=True must be
        re-queued (requeued_this_tick=1) and active_jobs must stay at 0.
        """
        from core.kube_demand import _PendingAdmission

        agent = self._make_agent()

        # Pre-inject one pending admission into the reorder buffer (already ready)
        agent._reorder_buffer.append(
            _PendingAdmission(
                event_id="pa-001",
                node_count=400,
                hardware_profile_id="enterprise_8gpu_air",
                observed_at=0.0,
                event_timestamp=0.0,
                duration_s=300.0,
            )
        )
        agent._started = True
        agent._last_total_nodes = 0

        # Headroom = 3 MW < 10 MW threshold → power_cap_active=True
        low_headroom = KubeGridState(
            p_dispatch_required_mw=8.0,
            bess_soc_fraction=0.8,
            turbine_headroom_mw=2.0,
            bess_headroom_mw=1.0,
        )

        _signals, metrics = agent.tick(
            sim_time=15.0, dt_seconds=5.0, grid_state=low_headroom
        )

        self.assertTrue(
            metrics.power_cap_active,
            msg="Expected power_cap_active=True when headroom(3 MW) < threshold(10 MW).",
        )
        self.assertEqual(
            metrics.requeued_this_tick, 1,
            msg=(
                f"Expected requeued_this_tick=1 (job held by cap), "
                f"got {metrics.requeued_this_tick}."
            ),
        )
        self.assertEqual(
            metrics.active_jobs, 0,
            msg=(
                f"Expected active_jobs=0 (job re-queued, not admitted), "
                f"got {metrics.active_jobs}."
            ),
        )

    def test_held_job_admitted_after_headroom_recovers(self):
        """
        TC-P2b: After the cap was active, if we pass high headroom on the next
        tick the re-queued job (retry_id) must be admitted.

        This confirms re-queue is lossless — jobs come back once headroom recovers.
        """
        from core.kube_demand import _PendingAdmission

        agent = self._make_agent()

        # Tick 1: inject admission, apply cap → job is re-queued
        agent._reorder_buffer.append(
            _PendingAdmission(
                event_id="pa-002",
                node_count=300,
                hardware_profile_id="enterprise_8gpu_air",
                observed_at=0.0,
                event_timestamp=0.0,
                duration_s=300.0,
            )
        )
        agent._started = True
        agent._last_total_nodes = 0

        low_headroom = KubeGridState(
            p_dispatch_required_mw=5.0,
            bess_soc_fraction=0.9,
            turbine_headroom_mw=1.5,
            bess_headroom_mw=0.5,   # total 2 MW < 10 MW threshold
        )
        agent.tick(sim_time=15.0, dt_seconds=5.0, grid_state=low_headroom)

        # Tick 2 (sim_time=20): ample headroom → re-queued retry_id now ready
        # (retry has observed_at = tick1_time + 5.0 = 20.0; reorder_window=0
        #  so it is ready when sim_time >= 20.0)
        ample_headroom = KubeGridState(
            p_dispatch_required_mw=3.0,
            bess_soc_fraction=0.95,
            turbine_headroom_mw=15.0,
            bess_headroom_mw=5.0,   # total 20 MW >> 10 MW threshold
        )
        _signals, metrics2 = agent.tick(
            sim_time=20.0, dt_seconds=5.0, grid_state=ample_headroom
        )

        self.assertFalse(
            metrics2.power_cap_active,
            msg="Expected power_cap_active=False at tick 2 (headroom=20 MW > 10 MW threshold).",
        )
        self.assertEqual(
            metrics2.active_jobs, 1,
            msg=(
                f"Expected active_jobs=1 after headroom recovery (re-queued job admitted), "
                f"got {metrics2.active_jobs}.  Re-queue must be lossless."
            ),
        )


# ---------------------------------------------------------------------------
# TC-P3: E2E — alert still fires even when power-cap activates
# ---------------------------------------------------------------------------

class TestKubePowercapAlertNotMasked(unittest.TestCase):
    """
    TC-P3: End-to-end run with a tiny fleet and large Kube jobs.

    Scenario:
      • turbine=5 MW, BESS=2 MW (small fleet)
      • mean_job_nodes=800 → ~8.4 MW delta load per admission
      • headroom_threshold_mw=50 → cap almost always active after tick 1
      • dt_lead forced to 0 → no turbine ramp credit → alert must fire

    Verifies:
      TC-P3a: insufficient_reserve_alert fires at least once — load that reaches
              the arbitrator before the cap gate causes a real alert.
      TC-P3b: power_cap_active is True on at least one tick — confirms the cap
              activated (the scenario is not degenerate).
      TC-P3c: alert and power_cap_active can co-exist in the same run — the cap
              does NOT mask alerts; it only holds future admissions.
    """

    def _run(self):
        if not hasattr(self, "_rows"):
            self._rows = asyncio.run(_run_powercap_e2e("kube-powercap-e2e"))

    def test_alert_fires_despite_powercap(self):
        """
        TC-P3a: insufficient_reserve_alert must fire on at least one tick even
        though the power-cap is active for most of the run.
        """
        self._run()
        alert_ticks = [r for r in self._rows if r.insufficient_reserve_alert]
        self.assertGreater(
            len(alert_ticks), 0,
            msg=(
                f"No insufficient_reserve_alert fired across {len(self._rows)} ticks "
                f"with a 5+2 MW fleet and ~8.4 MW jobs (dt_lead=0).  "
                f"The power-cap must not suppress alerts for load already admitted."
            ),
        )

    def test_power_cap_activates_during_run(self):
        """
        TC-P3b: At least one tick must show power_cap_active=True, confirming
        the headroom gate engaged (the scenario is not degenerate).
        """
        self._run()
        cap_ticks = [
            r for r in self._rows
            if r.kube_metrics is not None and r.kube_metrics.power_cap_active
        ]
        self.assertGreater(
            len(cap_ticks), 0,
            msg=(
                f"power_cap_active never became True across {len(self._rows)} ticks.  "
                f"With headroom_threshold=50 MW and a 7 MW fleet this should activate "
                f"as soon as any load arrives."
            ),
        )

    def test_alert_and_power_cap_coexist(self):
        """
        TC-P3c: There must exist at least one tick where the power-cap is active
        AND the run has previously fired an alert — the two states co-exist in the
        same run.  This proves the cap path does not suppress real risk signals.
        """
        self._run()

        # Has ANY prior alert fired up to this point in the run?
        seen_alert = False
        cap_after_alert = False
        for row in self._rows:
            if row.insufficient_reserve_alert:
                seen_alert = True
            if seen_alert and row.kube_metrics is not None and row.kube_metrics.power_cap_active:
                cap_after_alert = True
                break

        self.assertTrue(
            cap_after_alert,
            msg=(
                "Expected the power-cap to be active on at least one tick that "
                "follows an insufficient_reserve_alert.  This confirms the cap gate "
                "and the alert path are independent — the cap does not mask risk."
            ),
        )

    def test_run_completed_full_duration(self):
        """
        TC-P3d: The run must complete at least 300 simulated seconds (60 ticks
        at 5 s/tick).  Guard against early termination hiding other failures.
        """
        self._run()
        self.assertGreaterEqual(
            len(self._rows), 60,
            msg=(
                f"Run produced {len(self._rows)} ticks; expected ≥ 60 "
                f"(300 s at 5 s/tick).  Check end_sim_time configuration."
            ),
        )


if __name__ == "__main__":
    unittest.main()
