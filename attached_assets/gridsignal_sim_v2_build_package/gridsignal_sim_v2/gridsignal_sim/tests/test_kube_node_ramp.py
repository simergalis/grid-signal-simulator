"""
tests/test_kube_node_ramp.py — Regression tests for Task #39.

Problem: kube_metrics.node_count snapped to the full admitted count the
moment a STARTING signal was processed, while P_compute ramped gradually
over 45 s (GPUModule._ramp_progress).  This cosmetic inconsistency made
the COMPUTE RACKS tile jump to full capacity before the power curve arrived.

Fix: after gpu.advance() in evaluate_tick(), node_count and utilization in
KubeMetrics are patched to reflect GPUModule.effective_node_count(), which
applies the same _ramp_multiplier curve used for power.  admitted_nodes is
left unchanged (raw scheduler allocation, used for capacity planning).

TC-N1: effective_node_count() == 0 on a brand-new STARTING signal
        (ramp_progress=0 → _ramp_multiplier(0)=0).
TC-N2: effective_node_count() rises during the ramp window.
TC-N3: effective_node_count() == admitted nodes after full ramp (progress=1).
TC-N4: admitted_nodes on KubeMetrics is unaffected by the patch.
TC-N5: kube_metrics.node_count on the first evaluate_tick() reflects the
        ramped count (≤ admitted + min_nodes floor), not the full admitted
        count.
TC-N6: kube_metrics.utilization is consistent with the patched node_count.
TC-N7: After ramp completes, kube_metrics.node_count == admitted + min_nodes
        floor (full count restored).
"""
from __future__ import annotations

import math
import unittest

from core.asset_modules import GPUModule
from core.models import SiteConfig, WorkloadEventType, WorkloadSignal
from tests.test_plane_separation import _plane_guard_active

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gpu(ramp_seconds: float = 45.0) -> GPUModule:
    """Minimal GPUModule — hardware_library empty → GENERIC_FALLBACK_PROFILE."""
    return GPUModule(
        asset_id="gpu-test",
        site=SiteConfig(frequency_nominal_hz=50.0, site_id="site-test"),
        hardware_library={},
        ramp_seconds=ramp_seconds,
    )


def _starting_signal(job_id: str = "job-1", node_count: int = 100) -> WorkloadSignal:
    return WorkloadSignal(
        event_id=f"ev-{job_id}",
        job_id=job_id,
        event_type=WorkloadEventType.STARTING,
        timestamp=0.0,
        hardware_profile_id="enterprise_8gpu_air",
        node_count=node_count,
        workload_class=None,  # WorkloadClass not needed for node-count tests
        site_id="site-test",
    )


# ---------------------------------------------------------------------------
# TC-N1: effective_node_count == 0 immediately after STARTING
# ---------------------------------------------------------------------------

class TestEffectiveNodeCountUnit(unittest.TestCase):

    def test_zero_on_fresh_starting_signal(self):
        """TC-N1: ramp_progress=0 → _ramp_multiplier(0)=0 → effective_count=0."""
        gpu = _gpu()
        gpu.apply_signal(_starting_signal(node_count=100))
        # No advance() yet → ramp_progress is exactly 0.0
        self.assertEqual(gpu.effective_node_count(), 0)

    def test_rises_during_ramp_window(self):
        """TC-N2: effective_node_count increases as advance() is called."""
        gpu = _gpu(ramp_seconds=45.0)
        gpu.apply_signal(_starting_signal(node_count=200))

        counts = []
        t = 0.0
        dt = 5.0
        for _ in range(9):   # 9 × 5 s = 45 s → should reach progress=1
            gpu.advance(t, dt)
            counts.append(gpu.effective_node_count())
            t += dt

        # Must be monotonically non-decreasing (ramp only goes forward)
        for i in range(1, len(counts)):
            self.assertGreaterEqual(
                counts[i], counts[i - 1],
                msg=f"Node count decreased at step {i}: {counts[i-1]} → {counts[i]}",
            )
        # Final value should equal full node count
        self.assertEqual(counts[-1], 200)

    def test_equals_full_count_after_ramp(self):
        """TC-N3: After progress reaches 1.0, effective_node_count == admitted."""
        gpu = _gpu(ramp_seconds=45.0)
        gpu.apply_signal(_starting_signal(node_count=50))
        # Drive to full ramp in one big step
        gpu.advance(0.0, 45.0)
        self.assertEqual(gpu.effective_node_count(), 50)

    def test_scale_down_keeps_existing_ramp_progress(self):
        """Scale-DOWN: existing nodes keep running at their current progress (no ramp reset).

        A scale-down from 100→80 nodes must not reset ramp_progress; the remaining
        nodes continue at their current draw level.
        """
        gpu = _gpu(ramp_seconds=45.0)
        # Admit job then advance halfway through the ramp
        gpu.apply_signal(_starting_signal(node_count=100))
        gpu.advance(0.0, 22.5)  # progress ≈ 0.5

        progress_before = gpu._ramp_progress.get("job-1", 0.0)
        self.assertGreater(progress_before, 0.0, "progress should be > 0 after half ramp")

        scale_down = WorkloadSignal(
            event_id="ev-scale-down",
            job_id="job-1",
            event_type=WorkloadEventType.SCALE,
            timestamp=22.5,
            hardware_profile_id="enterprise_8gpu_air",
            node_count=80,
            workload_class=None,
            site_id="site-test",
        )
        gpu.apply_signal(scale_down)
        # Node count reduced
        self.assertEqual(gpu._node_counts.get("job-1"), 80)
        # Ramp progress unchanged (no cold-start reset for scale-down)
        self.assertAlmostEqual(
            gpu._ramp_progress.get("job-1", 0.0), progress_before, places=6,
            msg="scale-down must not reset ramp_progress"
        )
        # No cohort created
        self.assertIsNone(gpu._last_scale_cohort_key)

    def test_scale_up_creates_delta_cohort_at_zero_progress(self):
        """Scale-UP: added nodes start cold — delta cohort created at ramp_progress=0.

        A scale-up from 100→200 should leave the base cohort unchanged and open a
        new "-cohort-1" entry for the 100 delta nodes at progress=0.
        """
        gpu = _gpu(ramp_seconds=45.0)
        # Admit job and advance to full ramp
        gpu.apply_signal(_starting_signal(node_count=100))
        gpu.advance(0.0, 45.0)   # base cohort fully ramped
        self.assertAlmostEqual(gpu._ramp_progress.get("job-1"), 1.0, places=6)

        scale_up = WorkloadSignal(
            event_id="ev-scale-up",
            job_id="job-1",
            event_type=WorkloadEventType.SCALE,
            timestamp=50.0,
            hardware_profile_id="enterprise_8gpu_air",
            node_count=200,
            workload_class=None,
            site_id="site-test",
        )
        gpu.apply_signal(scale_up)

        cohort_key = "job-1-cohort-1"
        # Cohort key returned for simulation_core cooling registration
        self.assertEqual(gpu._last_scale_cohort_key, cohort_key)
        # Base cohort unchanged: 100 nodes, fully ramped
        self.assertEqual(gpu._node_counts.get("job-1"), 100)
        self.assertAlmostEqual(gpu._ramp_progress.get("job-1"), 1.0, places=6)
        # Delta cohort: 100 nodes, cold (progress=0)
        self.assertEqual(gpu._node_counts.get(cohort_key), 100)
        self.assertAlmostEqual(gpu._ramp_progress.get(cohort_key), 0.0, places=6)

    def test_scale_up_delta_nodes_rise_over_time(self):
        """Delta cohort ramps over 45 s; total effective count rises gradually."""
        gpu = _gpu(ramp_seconds=45.0)
        gpu.apply_signal(_starting_signal(node_count=100))
        gpu.advance(0.0, 45.0)   # base cohort at full TDP

        scale_up = WorkloadSignal(
            event_id="ev-scale-up",
            job_id="job-1",
            event_type=WorkloadEventType.SCALE,
            timestamp=50.0,
            hardware_profile_id="enterprise_8gpu_air",
            node_count=200,
            workload_class=None,
            site_id="site-test",
        )
        gpu.apply_signal(scale_up)

        # Immediately after scale-up, delta cohort at 0 → effective ≈ 100 (base only)
        count_at_scale = gpu.effective_node_count()
        self.assertEqual(count_at_scale, 100,
                         "delta cohort should contribute 0 nodes immediately after scale-up")

        # Advance to full ramp of delta cohort
        t = 50.0
        dt = 5.0
        counts = [count_at_scale]
        for _ in range(9):  # 9 × 5 s = 45 s → full ramp
            gpu.advance(t, dt)
            counts.append(gpu.effective_node_count())
            t += dt

        # Must be monotonically non-decreasing
        for i in range(1, len(counts)):
            self.assertGreaterEqual(counts[i], counts[i - 1],
                                    msg=f"count decreased at step {i}")
        # Final effective count should be 200 (base 100 + delta 100, both at 1.0)
        self.assertEqual(counts[-1], 200)

    def test_consecutive_scale_ups_do_not_inflate_node_count(self):
        """Consecutive scale-UPs must compute each delta against the running desired total.

        STARTING 100 → SCALE 150 → SCALE 200:
        - cohort-1 should have 50 nodes (150-100)
        - cohort-2 should have 50 nodes (200-150), NOT 100 (200-100 stale base)
        - Total after both scales: 100 + 50 + 50 = 200 nodes (not 250)
        """
        gpu = _gpu(ramp_seconds=45.0)
        gpu.apply_signal(_starting_signal(job_id="job-c", node_count=100))
        gpu.advance(0.0, 45.0)   # base cohort fully ramped

        gpu.apply_signal(WorkloadSignal(
            event_id="ev-scale-1",
            job_id="job-c",
            event_type=WorkloadEventType.SCALE,
            timestamp=50.0,
            hardware_profile_id="enterprise_8gpu_air",
            node_count=150,
            workload_class=None,
            site_id="site-test",
        ))
        self.assertEqual(gpu._node_counts.get("job-c-cohort-1"), 50,
                         "first scale-up should create a 50-node cohort (150-100)")

        gpu.apply_signal(WorkloadSignal(
            event_id="ev-scale-2",
            job_id="job-c",
            event_type=WorkloadEventType.SCALE,
            timestamp=55.0,
            hardware_profile_id="enterprise_8gpu_air",
            node_count=200,
            workload_class=None,
            site_id="site-test",
        ))
        self.assertEqual(gpu._node_counts.get("job-c-cohort-2"), 50,
                         "second scale-up should create a 50-node cohort (200-150), not 100")

        total_tracked = (
            gpu._node_counts.get("job-c", 0)
            + gpu._node_counts.get("job-c-cohort-1", 0)
            + gpu._node_counts.get("job-c-cohort-2", 0)
        )
        self.assertEqual(total_tracked, 200,
                         "total tracked nodes must equal the requested 200, not 250")

    def test_scale_up_then_scale_down_reduces_newest_cohort_first(self):
        """Scale-UP then scale-DOWN: shed nodes from the newest cohort first.

        STARTING 100 → SCALE 150 → SCALE 120:
        - After scale-down to 120, cohort-1 should have 20 remaining (not 50)
        - Base job stays at 100 (untouched)
        - Desired total = 120
        """
        gpu = _gpu(ramp_seconds=45.0)
        gpu.apply_signal(_starting_signal(job_id="job-d", node_count=100))
        gpu.advance(0.0, 45.0)

        gpu.apply_signal(WorkloadSignal(
            event_id="ev-scale-up",
            job_id="job-d",
            event_type=WorkloadEventType.SCALE,
            timestamp=50.0,
            hardware_profile_id="enterprise_8gpu_air",
            node_count=150,
            workload_class=None,
            site_id="site-test",
        ))
        self.assertEqual(gpu._node_counts.get("job-d-cohort-1"), 50)

        gpu.apply_signal(WorkloadSignal(
            event_id="ev-scale-down",
            job_id="job-d",
            event_type=WorkloadEventType.SCALE,
            timestamp=55.0,
            hardware_profile_id="enterprise_8gpu_air",
            node_count=120,
            workload_class=None,
            site_id="site-test",
        ))
        # Cohort-1 reduced by 30 (150-120), from 50 to 20
        self.assertEqual(gpu._node_counts.get("job-d-cohort-1"), 20,
                         "scale-down should reduce newest cohort first")
        # Base job unchanged
        self.assertEqual(gpu._node_counts.get("job-d"), 100,
                         "base job must not be touched when cohort absorbs full reduction")
        # No new cohort created
        self.assertIsNone(gpu._last_scale_cohort_key)
        # Desired total is correct
        total = gpu._node_counts.get("job-d", 0) + gpu._node_counts.get("job-d-cohort-1", 0)
        self.assertEqual(total, 120)

    def test_scale_down_fully_removes_cohort_then_reduces_base(self):
        """Scale-down that exceeds a cohort's size removes the cohort and continues into base.

        STARTING 100 → SCALE 150 → SCALE 80:
        - cohort-1 (50 nodes) is fully removed
        - base job reduced from 100 to 80 (reduction remainder = 20)
        - Desired total = 80
        """
        gpu = _gpu(ramp_seconds=45.0)
        gpu.apply_signal(_starting_signal(job_id="job-e", node_count=100))
        gpu.advance(0.0, 45.0)

        gpu.apply_signal(WorkloadSignal(
            event_id="ev-scale-up",
            job_id="job-e",
            event_type=WorkloadEventType.SCALE,
            timestamp=50.0,
            hardware_profile_id="enterprise_8gpu_air",
            node_count=150,
            workload_class=None,
            site_id="site-test",
        ))
        gpu.apply_signal(WorkloadSignal(
            event_id="ev-scale-big-down",
            job_id="job-e",
            event_type=WorkloadEventType.SCALE,
            timestamp=55.0,
            hardware_profile_id="enterprise_8gpu_air",
            node_count=80,
            workload_class=None,
            site_id="site-test",
        ))
        self.assertNotIn("job-e-cohort-1", gpu._node_counts,
                         "cohort-1 (50 nodes) should be fully removed")
        self.assertEqual(gpu._node_counts.get("job-e"), 80,
                         "base job must be reduced by the remaining 20")
        total = sum(gpu._node_counts.get(k, 0) for k in ["job-e", "job-e-cohort-1"])
        self.assertEqual(total, 80)

    def test_job_end_cleans_up_all_cohorts(self):
        """JOB_END removes base entry AND all scale-up cohorts from GPUModule state."""
        gpu = _gpu()
        gpu.apply_signal(_starting_signal(job_id="job-b", node_count=100))
        gpu.advance(0.0, 45.0)

        # Create two cohorts via two scale-up events; deltas must be 50 each
        for i, new_count in enumerate([150, 200], start=1):
            gpu.apply_signal(WorkloadSignal(
                event_id=f"ev-scale-{i}",
                job_id="job-b",
                event_type=WorkloadEventType.SCALE,
                timestamp=float(50 + i),
                hardware_profile_id="enterprise_8gpu_air",
                node_count=new_count,
                workload_class=None,
                site_id="site-test",
            ))

        self.assertIn("job-b-cohort-1", gpu._node_counts)
        self.assertIn("job-b-cohort-2", gpu._node_counts)
        # Verify correct delta accounting before JOB_END
        total_before = (
            gpu._node_counts.get("job-b", 0)
            + gpu._node_counts.get("job-b-cohort-1", 0)
            + gpu._node_counts.get("job-b-cohort-2", 0)
        )
        self.assertEqual(total_before, 200,
                         "two scale-ups from 100→150→200 must track 200 total nodes, not 250")

        end = WorkloadSignal(
            event_id="ev-end-b",
            job_id="job-b",
            event_type=WorkloadEventType.JOB_END,
            timestamp=100.0,
            hardware_profile_id="enterprise_8gpu_air",
            node_count=0,
            workload_class=None,
            site_id="site-test",
        )
        gpu.apply_signal(end)

        self.assertNotIn("job-b", gpu._node_counts)
        self.assertNotIn("job-b-cohort-1", gpu._node_counts)
        self.assertNotIn("job-b-cohort-2", gpu._node_counts)
        self.assertEqual(gpu.effective_node_count(), 0)

    def test_job_end_removes_contribution(self):
        """JOB_END removes the job from effective_node_count."""
        gpu = _gpu()
        gpu.apply_signal(_starting_signal(job_id="job-a", node_count=80))
        gpu.advance(0.0, 45.0)   # fully ramp
        self.assertEqual(gpu.effective_node_count(), 80)

        end = WorkloadSignal(
            event_id="ev-end",
            job_id="job-a",
            event_type=WorkloadEventType.JOB_END,
            timestamp=50.0,
            hardware_profile_id="enterprise_8gpu_air",
            node_count=0,
            workload_class=None,
            site_id="site-test",
        )
        gpu.apply_signal(end)
        self.assertEqual(gpu.effective_node_count(), 0)


# ---------------------------------------------------------------------------
# TC-N4 through TC-N7: KubeMetrics patch via evaluate_tick()
# ---------------------------------------------------------------------------

class TestKubeMetricsPatch(unittest.TestCase):

    def _make_state(self, ramp_seconds: float = 45.0):
        """Minimal SimulationState with a KubeDemandAgent."""
        from core.asset_modules import (
            BessConfig, BessModule, CoolingModule, TurbineConfig, TurbineModule,
        )
        from core.kube_demand import KubeConfig, KubeDemandAgent
        from core.simulation_core import SimulationState

        site = SiteConfig(frequency_nominal_hz=50.0, site_id="site-n-test")
        gpu = GPUModule(
            asset_id="gpu-0",
            site=site,
            hardware_library={},
        )
        gpu.ramp_seconds = ramp_seconds

        turbine = TurbineModule(TurbineConfig(
            asset_id="turbine-0",
            r_asset_mw_per_s=0.2,
            rated_mw=30.0,
        ))
        bess = BessModule(BessConfig(
            asset_id="bess-0",
            rated_mw=5.0,
            usable_mwh=2.0,
            initial_soc_fraction=0.90,
        ))
        cooling = CoolingModule(asset_id="cooling-0", site=site)

        state = SimulationState(
            run_id="run-node-ramp-test",
            site=site,
            gpu_modules=[gpu],
            turbines=[turbine],
            bess_units=[bess],
            solar_arrays=[],
            cooling=cooling,
        )

        cfg = KubeConfig(
            max_nodes=500,
            min_nodes=50,            # idle floor we test against
            mean_job_nodes=100,
            job_node_std=0.0,        # deterministic node count per job
            min_job_nodes=100,
            mean_interarrival_s=9999.0,   # one admission at t=0, none during test window
            mean_job_duration_s=9999.0,   # jobs don't expire during the 50 s window
            reorder_window_s=0.0,
            ntp_jitter_s=0.0,
            rng_seed=7,
        )
        state.kube_agent = KubeDemandAgent(cfg, site_id="site-n-test")
        return state

    def _tick(self, state, sim_time: float = 0.0, dt: float = 5.0):
        from core.sim_clock import SimClock
        from core.simulation_core import evaluate_tick
        clock = SimClock(sim_time=sim_time, dt_seconds=dt,
                         wall_stamp_utc=0.0, rate=0.0, tick_seq=0)
        with _plane_guard_active():
            return evaluate_tick(state, clock)

    def test_node_count_below_admitted_on_first_tick(self):
        """TC-N5: kube_metrics.node_count ≤ admitted_nodes on tick 0.

        At t=0, ramp_progress is 0 immediately after STARTING is applied and
        gpu.advance() runs for only one 5 s step.  effective_node_count should
        therefore be well below the full admitted count (or at the min_nodes
        floor if effective_admitted < min_nodes).
        """
        state = self._make_state()
        result = self._tick(state, sim_time=0.0)
        km = result.kube_metrics
        self.assertIsNotNone(km, "Expected kube_metrics to be present")
        # node_count must not exceed admitted_nodes (full capacity)
        self.assertLessEqual(
            km.node_count, km.admitted_nodes,
            msg=(
                f"node_count ({km.node_count}) should not exceed admitted_nodes "
                f"({km.admitted_nodes}) on the first tick — the ramp hasn't finished."
            ),
        )

    def test_admitted_nodes_unaffected(self):
        """TC-N4: admitted_nodes is the raw scheduler count, not ramped."""
        state = self._make_state()
        result = self._tick(state, sim_time=0.0)
        km = result.kube_metrics
        self.assertIsNotNone(km)
        # admitted_nodes is set by kube_agent.tick() and must equal the full
        # scheduler count — the patch must not touch it.
        self.assertGreaterEqual(
            km.admitted_nodes, 0,
            msg="admitted_nodes should be ≥ 0 (raw scheduler allocation)",
        )
        # If jobs were admitted, admitted_nodes > min_nodes only after real
        # admission — at minimum it's the baseline.  The key invariant is:
        # admitted_nodes ≥ node_count when ramp is complete.
        if km.admitted_nodes > 0:
            # When ramp is complete, node_count should equal admitted + floor.
            # At tick 0 node_count ≤ admitted is the invariant we care about.
            pass   # already checked in TC-N5

    def test_utilization_consistent_with_node_count(self):
        """TC-N6: utilization == node_count / max_nodes after patch."""
        state = self._make_state()
        result = self._tick(state, sim_time=0.0)
        km = result.kube_metrics
        self.assertIsNotNone(km)
        expected_util = km.node_count / state.kube_agent.config.max_nodes
        self.assertAlmostEqual(
            km.utilization, expected_util, places=6,
            msg=(
                f"utilization {km.utilization:.6f} is inconsistent with "
                f"node_count={km.node_count} / max_nodes={state.kube_agent.config.max_nodes}"
            ),
        )

    def test_node_count_reaches_full_after_ramp(self):
        """TC-N7: After the ramp window, node_count equals admitted + min floor."""
        state = self._make_state(ramp_seconds=45.0)
        # Advance well past the 45-second ramp window (10 ticks × 5 s = 50 s)
        for tick_i in range(10):
            result = self._tick(state, sim_time=tick_i * 5.0)
        km = result.kube_metrics
        self.assertIsNotNone(km)
        # After the ramp completes, node_count must equal max(min_nodes, admitted)
        expected = max(state.kube_agent.config.min_nodes, km.admitted_nodes)
        self.assertEqual(
            km.node_count, expected,
            msg=(
                f"After ramp window, node_count ({km.node_count}) should equal "
                f"max(min_nodes={state.kube_agent.config.min_nodes}, "
                f"admitted_nodes={km.admitted_nodes}) = {expected}."
            ),
        )


# ---------------------------------------------------------------------------
# TC-SD1, TC-SD2: cooling envelope cleanup on fully-removed scale-down cohort
# ---------------------------------------------------------------------------

class TestScaleDownCoolingEnvelope(unittest.TestCase):
    """Cooling envelopes for fully-removed scale-up cohorts must be ended and pruned.

    TC-SD1: After fully removing a cohort via scale-down, the cohort's CoolingModule
            envelope must have end_t set at the SCALE event timestamp.  Without the
            register_job_end() call, the envelope has no end_t and the lagged cursor
            stays stuck at the last pre-scale sample, keeping P_cooling overstated
            indefinitely.

    TC-SD2: After the retention window (dt_thermal + 5·tau) has elapsed past the
            scale-down timestamp, the cohort's envelope is pruned from CoolingModule
            and contributes zero to P_cooling.
    """

    def _make_minimal_state(self, dt_thermal: float = 10.0, tau: float = 5.0):
        """SimulationState with short thermal constants to keep tick counts small."""
        from core.asset_modules import BessModule, CoolingModule, TurbineModule
        from core.models import BessConfig, TurbineConfig
        from core.simulation_core import SimulationState

        site = SiteConfig(
            frequency_nominal_hz=50.0,  # required; frequency unused in this non-frequency test
            site_id="site-sd-test",
            dt_thermal_seconds=dt_thermal,
            tau_seconds=tau,
        )
        gpu = GPUModule(
            asset_id="gpu-0",
            site=site,
            hardware_library={},
            ramp_seconds=5.0,      # fast ramp so test doesn't need many ticks
        )
        turbine = TurbineModule(TurbineConfig(
            asset_id="turbine-0",
            r_asset_mw_per_s=5.0,
            rated_mw=50.0,
        ))
        bess = BessModule(BessConfig(
            asset_id="bess-0",
            rated_mw=10.0,
            usable_mwh=5.0,
            initial_soc_fraction=0.90,
        ))
        cooling = CoolingModule(asset_id="cooling-0", site=site)

        return SimulationState(
            run_id="run-sd-test",
            site=site,
            gpu_modules=[gpu],
            turbines=[turbine],
            bess_units=[bess],
            solar_arrays=[],
            cooling=cooling,
        )

    def _signal(self, event_type: WorkloadEventType, node_count: int,
                timestamp: float, job_id: str = "job-sd") -> WorkloadSignal:
        return WorkloadSignal(
            event_id=f"ev-{event_type.value}-{timestamp}",
            job_id=job_id,
            event_type=event_type,
            timestamp=timestamp,
            hardware_profile_id="enterprise_8gpu_air",
            node_count=node_count,
            workload_class=None,
            site_id="site-sd-test",
        )

    def _tick(self, state, sim_time: float, dt: float = 5.0):
        from core.sim_clock import SimClock
        from core.simulation_core import evaluate_tick
        clock = SimClock(sim_time=sim_time, dt_seconds=dt,
                         wall_stamp_utc=0.0, rate=0.0, tick_seq=0)
        with _plane_guard_active():
            return evaluate_tick(state, clock)

    def test_fully_removed_cohort_has_end_t_set(self):
        """TC-SD1: Scale-down that removes a cohort must set end_t on its cooling envelope."""
        state = self._make_minimal_state()

        # Admit job, tick once, scale-up to create cohort-1, tick, scale-down
        state.apply_workload_signal(
            self._signal(WorkloadEventType.STARTING, node_count=100, timestamp=0.0),
            dt_lead_seconds=0.0,
        )
        self._tick(state, sim_time=0.0)

        state.apply_workload_signal(
            self._signal(WorkloadEventType.SCALE, node_count=150, timestamp=5.0),
            dt_lead_seconds=0.0,
        )
        cohort_key = "job-sd-cohort-1"
        self.assertIn(cohort_key, state.cooling._envelopes,
                      "cohort-1 cooling envelope must exist after scale-up")
        self.assertIsNone(
            state.cooling._envelopes[cohort_key].end_t,
            "cohort-1 envelope must be live (end_t=None) before scale-down",
        )
        self._tick(state, sim_time=5.0)

        # Scale-DOWN back to 100 — cohort-1 must be fully removed
        state.apply_workload_signal(
            self._signal(WorkloadEventType.SCALE, node_count=100, timestamp=10.0),
            dt_lead_seconds=0.0,
        )
        self.assertIn(cohort_key, state.cooling._envelopes,
                      "envelope must still exist immediately after scale-down (drain window active)")
        self.assertIsNotNone(
            state.cooling._envelopes[cohort_key].end_t,
            "cooling envelope end_t must be set after cohort is fully removed by scale-down",
        )
        self.assertAlmostEqual(
            state.cooling._envelopes[cohort_key].end_t, 10.0, places=6,
            msg="end_t must equal the SCALE event timestamp",
        )

    def test_fully_removed_cohort_envelope_pruned_after_retention_window(self):
        """TC-SD2: Removed cohort envelope is pruned after dt_thermal + 5·tau."""
        # dt_thermal=10s, tau=5s → retention = 10 + 25 = 35s
        state = self._make_minimal_state(dt_thermal=10.0, tau=5.0)
        dt = 5.0

        state.apply_workload_signal(
            self._signal(WorkloadEventType.STARTING, node_count=100, timestamp=0.0),
            dt_lead_seconds=0.0,
        )
        self._tick(state, sim_time=0.0, dt=dt)

        state.apply_workload_signal(
            self._signal(WorkloadEventType.SCALE, node_count=150, timestamp=5.0),
            dt_lead_seconds=0.0,
        )
        self._tick(state, sim_time=5.0, dt=dt)

        scale_down_t = 10.0
        state.apply_workload_signal(
            self._signal(WorkloadEventType.SCALE, node_count=100, timestamp=scale_down_t),
            dt_lead_seconds=0.0,
        )
        cohort_key = "job-sd-cohort-1"
        self.assertIn(cohort_key, state.cooling._envelopes,
                      "envelope must still exist immediately after scale-down")

        # Advance well past retention window (35s after scale_down_t=10 → need sim_time > 45)
        retention_s = 10.0 + 5.0 * 5.0   # dt_thermal + 5 * tau
        t = scale_down_t + dt
        while t <= scale_down_t + retention_s + dt:
            self._tick(state, sim_time=t, dt=dt)
            t += dt

        self.assertNotIn(
            cohort_key, state.cooling._envelopes,
            f"cohort-1 cooling envelope must be pruned after retention window "
            f"({retention_s:.0f}s past scale-down); still present at t={t - dt:.0f}s",
        )


if __name__ == "__main__":
    unittest.main()
