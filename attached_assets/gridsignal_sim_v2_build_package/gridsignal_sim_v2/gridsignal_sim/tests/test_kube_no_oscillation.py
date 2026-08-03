"""
tests/test_kube_no_oscillation.py — §6.2 anti-oscillation acceptance test.

TC-NO1 (RED against current code): power_cap_active shall not toggle more than
MAX_TOGGLES times within any 300-second simulation window.

A toggle is a power_cap_active transition False→True or True→False between
consecutive ticks.  With TICK_INTERVAL_SIM_SECONDS = 5.0 s and the current
re-queue delay hardcoded to 5.0 s, the cap state alternates every tick —
producing ~50+ toggles in 300 s.

Why this matters (per §6.2 checkpoint-valley spec):
  • A 91 % drop in compute draw lasting 5 s with recovery within 45 s
    classifies as a checkpoint valley.  Under the current oscillation EVERY
    tick qualifies, permanently arming turbine pre-staging from a stimulus
    that looks nothing like a real 10–30 s checkpoint plateau.
  • Δt_thermal = 90 s and τ = 20 s cannot track a 5 s cycle at all — the
    cooling double-lag (differentiator #3) is completely invisible.
  • The turbine at r_asset = 0.2 MW/s needs ~91 s to cover an 18 MW swing;
    it never participates, cycling the BESS at 0.1 Hz.

The test is intentionally RED against the current codebase.  It documents
the anti-oscillation constraint so that any future fix can be verified
against a concrete, reproducible threshold.

Two tests are provided:
  TC-NO1 — end-to-end oscillation count in 300 s (RED, documents the bug).
  TC-NO2 — arrivals_this_tick and requeued_this_tick are correctly populated
            (GREEN, verifies the new KubeMetrics fields work before any fix).
"""
from __future__ import annotations

import unittest

from core.kube_demand import KubeConfig, KubeDemandAgent, KubeGridState


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Any fix that achieves this toggle rate passes TC-NO1.
#: Rationale: up to 3 cap activations in a 300-second run is consistent with
#: a normal cluster ramp-up (one initial cap event) plus at most two demand
#: surges.  The oscillation pathology produces 40–60 toggles.
MAX_TOGGLES = 5

#: Simulation parameters
TICK_DT_S = 5.0
N_TICKS   = 60          # 60 × 5 s = 300 s


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent(
    *,
    mean_interarrival_s: float = 5.0,   # ~1 job per tick — maximises admission pressure
    mean_job_duration_s: float = 20.0,  # short — jobs complete within a few ticks
    min_job_duration_s:  float = 10.0,
    max_nodes:           int   = 500,
    min_nodes:           int   = 50,
    mean_job_nodes:      int   = 200,
    rng_seed:            int   = 42,
) -> KubeDemandAgent:
    cfg = KubeConfig(
        max_nodes=max_nodes,
        min_nodes=min_nodes,
        mean_interarrival_s=mean_interarrival_s,
        mean_job_nodes=mean_job_nodes,
        job_node_std=50.0,
        min_job_nodes=50,
        mean_job_duration_s=mean_job_duration_s,
        min_job_duration_s=min_job_duration_s,
        headroom_threshold_mw=2.5,
        reorder_window_s=0.0,   # drain immediately — no buffering delay in tests
        ntp_jitter_s=0.0,       # deterministic timestamps
        rng_seed=rng_seed,
    )
    return KubeDemandAgent(cfg, site_id="site-test")


def _grid_state_feedback(admitted_nodes: int, min_nodes: int) -> KubeGridState:
    """Simulate the physics feedback loop:

    When admitted_nodes > idle baseline the turbine is loaded and headroom
    collapses below headroom_threshold_mw (2.5 MW), activating the power cap.
    When nodes fall back to the idle baseline the turbine has headroom again.

    This reproduces the oscillation cycle WITHOUT a full evaluate_tick pipeline:
      1. Jobs admit on a low-pressure tick → admitted_nodes rises.
      2. Next tick reads high admitted_nodes → low headroom → power_cap=True.
      3. New arrivals are held and re-queued for exactly TICK_INTERVAL_SIM_SECONDS.
      4. Current jobs expire → admitted_nodes falls → headroom returns.
      5. Held jobs drain on the next tick → admit → admitted_nodes spikes → goto 2.
    """
    if admitted_nodes > min_nodes:
        # Jobs running: turbine fully loaded, BESS nearly depleted.
        return KubeGridState(
            p_dispatch_required_mw=20.0,
            bess_soc_fraction=0.10,
            turbine_headroom_mw=0.5,
            bess_headroom_mw=0.5,  # total = 1.0 MW < 2.5 MW threshold
        )
    else:
        # Cluster idle: ample turbine headroom.
        return KubeGridState(
            p_dispatch_required_mw=2.0,
            bess_soc_fraction=0.90,
            turbine_headroom_mw=12.0,
            bess_headroom_mw=5.0,  # total = 17.0 MW >> threshold
        )


def _count_toggles(cap_trace: list[bool]) -> int:
    """Count False↔True transitions in a boolean sequence."""
    return sum(
        1 for i in range(1, len(cap_trace))
        if cap_trace[i] != cap_trace[i - 1]
    )


# ---------------------------------------------------------------------------
# TC-NO1 — anti-oscillation assertion (currently RED)
# ---------------------------------------------------------------------------

class TestKubePowerCapNoOscillation(unittest.TestCase):

    def test_power_cap_toggle_count_within_300s(self):
        """
        TC-NO1 (RED against current code): power_cap_active must not toggle
        more than MAX_TOGGLES times in a 300-second window.

        Uses a dynamic grid-state feedback loop to reproduce the real oscillation
        without a full evaluate_tick pipeline:
          • When admitted_nodes > min_nodes the grid state carries low headroom
            (1.0 MW < 2.5 MW threshold) → power_cap_active=True.
          • When jobs expire and admitted_nodes falls back to min_nodes the grid
            state carries high headroom → power_cap_active=False.
          • The 5 s re-queue delay lets held jobs drain on the very next tick,
            which immediately re-admits them, collapses headroom again, and repeats.

        With the current hardcode this test FAILS.  That is the point: it documents
        the §6.2 anti-oscillation requirement as a machine-checkable assertion.
        """
        agent = _make_agent()

        cap_trace: list[bool] = []
        prev_admitted = 0
        for tick in range(N_TICKS):
            grid = _grid_state_feedback(prev_admitted, min_nodes=50)
            _, metrics = agent.tick(float(tick * TICK_DT_S), TICK_DT_S, grid)
            cap_trace.append(metrics.power_cap_active)
            prev_admitted = metrics.admitted_nodes

        toggles = _count_toggles(cap_trace)

        self.assertLessEqual(
            toggles,
            MAX_TOGGLES,
            f"power_cap_active toggled {toggles} times in {N_TICKS * TICK_DT_S:.0f} s "
            f"(limit {MAX_TOGGLES}).  "
            "The 5 s re-queue delay equals TICK_INTERVAL_SIM_SECONDS, locking "
            "the oscillation to the tick rate.  Every toggle produces a §6.2 "
            "checkpoint valley that permanently arms turbine pre-staging.  "
            "Fix: replace the hardcoded 5.0 with a delay that is not an "
            "integer multiple of TICK_INTERVAL_SIM_SECONDS, or implement "
            "exponential backoff on repeated power-cap holds.",
        )

    def test_oscillation_is_reproducible_across_seeds(self):
        """
        TC-NO1b (RED): the oscillation is not a random-seed artefact.

        Three independent seeds all exceed MAX_TOGGLES under the current code,
        guarding against a fix that only happens to suppress oscillation for
        one particular RNG sequence.
        """
        for seed in (42, 7, 2025):
            with self.subTest(seed=seed):
                agent = _make_agent(rng_seed=seed)

                cap_trace: list[bool] = []
                prev_admitted = 0
                for tick in range(N_TICKS):
                    grid = _grid_state_feedback(prev_admitted, min_nodes=50)
                    _, metrics = agent.tick(
                        float(tick * TICK_DT_S), TICK_DT_S, grid
                    )
                    cap_trace.append(metrics.power_cap_active)
                    prev_admitted = metrics.admitted_nodes

                toggles = _count_toggles(cap_trace)
                self.assertLessEqual(
                    toggles,
                    MAX_TOGGLES,
                    f"seed={seed}: power_cap_active toggled {toggles} times "
                    f"(limit {MAX_TOGGLES})",
                )


# ---------------------------------------------------------------------------
# TC-NO2 — new KubeMetrics fields are correctly populated (GREEN)
# ---------------------------------------------------------------------------

class TestKubeMetricsNewFields(unittest.TestCase):

    def test_arrivals_this_tick_increments_on_poisson_events(self):
        """
        TC-NO2a: arrivals_this_tick counts Poisson arrivals observed this tick.

        mean_interarrival_s=1 → at least one arrival per 5-second tick.
        """
        agent = _make_agent(mean_interarrival_s=1.0)
        _, metrics = agent.tick(0.0, TICK_DT_S, None)

        self.assertGreaterEqual(
            metrics.arrivals_this_tick,
            1,
            "Expected at least one Poisson arrival on the first tick "
            "(mean_interarrival_s=1.0, dt=5.0 s)",
        )

    def test_arrivals_this_tick_is_zero_when_no_arrivals(self):
        """
        TC-NO2b: arrivals_this_tick = 0 when no Poisson events fire.

        With mean_interarrival_s=1000 and dt=5 s the next arrival is far in
        the future; the first tick should observe zero arrivals
        (the first arrival is at t=0.0 so tick 0 picks it up — use tick 1).
        """
        agent = _make_agent(mean_interarrival_s=1000.0, rng_seed=99)
        # Tick 0 always starts with _next_arrival_sim_time=0 so one arrival fires.
        agent.tick(0.0, TICK_DT_S, None)
        # Tick 1: next arrival is ~1000 s away; no arrivals this tick.
        _, metrics = agent.tick(TICK_DT_S, TICK_DT_S, None)

        self.assertEqual(
            metrics.arrivals_this_tick,
            0,
            f"Expected 0 arrivals on tick 1 with mean_interarrival_s=1000, "
            f"got {metrics.arrivals_this_tick}",
        )

    def test_requeued_this_tick_nonzero_when_power_cap_active(self):
        """
        TC-NO2c: requeued_this_tick > 0 when power_cap blocks admission.

        Inject a low-headroom grid state from tick 0; jobs arriving that tick
        should be power-cap held, incrementing requeued_this_tick.
        """
        # High arrival rate so at least one job enters the reorder buffer
        # and gets drained on the same tick (reorder_window_s=0).
        agent = _make_agent(mean_interarrival_s=1.0, rng_seed=42)
        grid  = _grid_state_feedback(admitted_nodes=200, min_nodes=50)  # force low headroom

        _, metrics = agent.tick(0.0, TICK_DT_S, grid)

        self.assertGreaterEqual(
            metrics.requeued_this_tick,
            1,
            "Expected at least one requeue when power_cap_active and "
            f"arrivals_this_tick={metrics.arrivals_this_tick} (headroom=0.5 MW)",
        )

    def test_requeued_zero_when_headroom_ample(self):
        """
        TC-NO2d: requeued_this_tick = 0 when headroom is well above threshold.
        """
        agent = _make_agent(mean_interarrival_s=1.0, rng_seed=42)
        grid  = KubeGridState(
            p_dispatch_required_mw=2.0,
            bess_soc_fraction=0.9,
            turbine_headroom_mw=15.0,
            bess_headroom_mw=5.0,
        )

        _, metrics = agent.tick(0.0, TICK_DT_S, grid)

        self.assertEqual(
            metrics.requeued_this_tick,
            0,
            f"Expected 0 requeued with ample headroom, got {metrics.requeued_this_tick}",
        )


if __name__ == "__main__":
    unittest.main()
