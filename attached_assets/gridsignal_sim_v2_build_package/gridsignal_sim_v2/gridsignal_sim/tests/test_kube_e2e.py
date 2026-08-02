"""
tests/test_kube_e2e.py — End-to-end validation of the Kubernetes dt_lead fix.

§9 / resolution-log item 5: the fix changes dt_lead from 0 to ramp_seconds
(default 45 s) on the Kubernetes path.  These tests confirm the alert frequency
drops to physically correct levels when the full simulation is run end-to-end,
and that non-Kube scripted scenarios are unaffected.

TC-E1: Run the Kube demo scenario (fixed, dt_lead=45 s) for 300 simulated
       seconds.  insufficient_reserve_alert must fire materially less often
       than the broken path (dt_lead=0).  With the chosen parameters the fixed
       path fires ZERO alerts; the broken path fires on every STARTING event.

TC-E2: bess_bridging_seconds must be strictly higher on the fixed path than
       on the broken path.  The broken path fires alerts with shortfall_mw>0;
       that drives bess_bridging_seconds to 0.  The fixed path has no pending
       shortfall, so the BESS has non-zero bridging headroom.

TC-E3: Run demo-20mw (non-Kube scripted scenario) to completion and confirm
       the outcome is unchanged — 0 alerts across 60 ticks.  Regression guard:
       the fix is surgical (only the Kube call site changed) and must not
       disturb scripted scenarios.
"""
from __future__ import annotations

import asyncio
import contextlib
import unittest
from typing import Any

from core.kube_demand import KubeConfig, KubeDemandAgent
from runtime.run_manager import RunManager, WebSocketHub
from runtime.scenario_factory import build_run_context


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _KUBE_CFG(*, rng_seed: int = 42) -> KubeConfig:
    """
    Calibrated KubeConfig for the E2E alert-rate comparison.

    mean_job_nodes=600 → delta_p ≈ 600 × 10.2 kW × PUE 1.03 / 1000 = 6.30 MW
    per typical STARTING event.

    With BESS ceiling=5 MW:
      dt_lead=45s → already_ramped = min(0.2 × 45, 6.30) = 6.30 MW
                    shortfall = max(0, 6.30 − 6.30 − 5.00) = 0.0  → no alert
      dt_lead=0s  → already_ramped = 0
                    shortfall = max(0, 6.30 − 5.00) = 1.30 MW     → alert!

    mean_interarrival_s=25 → ~12 STARTING events in 300 s.
    min_nodes=0  → no baseline load that could mask the differential.
    reorder_window_s=0, ntp_jitter_s=0 → fully deterministic timing.
    """
    return KubeConfig(
        max_nodes=3000,
        min_nodes=0,
        hardware_profile_id="enterprise_8gpu_air",
        mean_job_nodes=600,
        job_node_std=50,
        min_job_nodes=200,
        mean_interarrival_s=25.0,
        mean_job_duration_s=600.0,
        min_job_duration_s=60.0,
        reorder_window_s=0.0,
        ntp_jitter_s=0.0,
        rng_seed=rng_seed,
    )


async def _run_kube(
    run_id: str,
    *,
    force_dt_lead_zero: bool = False,
) -> list[Any]:
    """
    Build and run a Kubernetes-driven scenario for 300 simulated seconds.

    force_dt_lead_zero=True patches apply_workload_signal to always pass
    dt_lead=0, reproducing the pre-fix (broken) behaviour for comparison.

    Returns ctx.sink.rows — a list of TickResult objects.
    """
    hub = WebSocketHub()
    manager = RunManager(hub)

    # node_count=0: no scripted workload; kube_agent drives all compute load.
    # solar_rated_mw inherits from the proto-7 formula: 0.25 × 0 = 0 MW.
    # With no solar, p_renewable=0 so delta_p equals per_job_target_mw directly.
    ctx = build_run_context(
        run_id,
        job_id="kube-placeholder",
        node_count=0,
        turbine_rated_mw=20.0,
        # r_asset=0.2 MW/s (default): with dt_lead=45 s, turbine credit =
        # min(0.2 × 45, delta_p) = min(9.0, 6.3) = 6.3 MW → covers full step.
        bess_rated_mw=5.0,
        bess_usable_mwh=3.0,
        bess_grid_forming=False,   # no anchor reserve withheld
        end_sim_time=300.0,
    )

    # Attach the Kubernetes demand agent (same seed for both runs so the same
    # job schedule is presented to the arbitrator in both the fixed and broken
    # cases; only dt_lead_seconds differs).
    ctx.sim_state.kube_agent = KubeDemandAgent(
        _KUBE_CFG(rng_seed=42),
        site_id=ctx.sim_state.site.site_id,
    )

    if force_dt_lead_zero:
        # Reproduce the pre-fix behaviour: replace the instance's
        # apply_workload_signal so every Kube-path call sees dt_lead=0.
        # Python looks up instance attributes before class methods, so setting
        # an attribute here shadows the class method without modifying any class
        # state.  The scripted placeholder event (node_count=0) is also forced
        # to dt_lead=0, but with 0 nodes it adds no delta_p and has no effect
        # on alerts.
        _original = ctx.sim_state.apply_workload_signal

        def _zero_lead_apply(signal, dt_lead_seconds):  # noqa: ANN001
            return _original(signal, dt_lead_seconds=0.0)

        ctx.sim_state.apply_workload_signal = _zero_lead_apply  # type: ignore[method-assign]

    await manager.start_run(ctx)
    await manager._tasks[ctx.run_id]
    return ctx.sink.rows


# ---------------------------------------------------------------------------
# TC-E1: Alert frequency drops to zero on the fixed path
# ---------------------------------------------------------------------------

class TestKubeE2EAlertRate(unittest.TestCase):

    def _run_both(self):
        """Run fixed and broken scenarios; cache results on the instance."""
        if not hasattr(self, "_rows_fixed"):
            self._rows_fixed  = asyncio.run(_run_kube("kube-e2e-fixed",  force_dt_lead_zero=False))
            self._rows_broken = asyncio.run(_run_kube("kube-e2e-broken", force_dt_lead_zero=True))

    def test_fixed_path_fires_fewer_alerts_than_broken(self):
        """
        TC-E1: Running the Kube scenario end-to-end (300 s) with dt_lead=45 s
        must produce materially fewer insufficient_reserve_alert ticks than
        the same scenario run with dt_lead=0.

        With mean_job_nodes=600 and BESS=5 MW:
          fixed  (dt_lead=45) — turbine credit covers the full 6.3 MW step
                                 → no shortfall → 0 alerts expected.
          broken (dt_lead=0)  — no turbine credit → 1.3 MW shortfall on every
                                 STARTING event → N > 0 alerts expected.
        """
        self._run_both()
        fixed_alerts  = sum(1 for r in self._rows_fixed  if r.insufficient_reserve_alert)
        broken_alerts = sum(1 for r in self._rows_broken if r.insufficient_reserve_alert)

        # Non-vacuous guard: the broken path must actually fire at least one
        # alert — if it doesn't, the test would pass trivially and prove nothing.
        self.assertGreater(
            broken_alerts, 0,
            msg=(
                f"Non-vacuous guard: expected the broken path (dt_lead=0) to fire "
                f"at least one alert in {len(self._rows_broken)} ticks. "
                f"If no STARTING events fired, the kube_agent schedule is empty "
                f"and this test cannot distinguish fixed from broken."
            ),
        )

        # Core assertion: fixed path fires strictly fewer alerts.
        self.assertLess(
            fixed_alerts, broken_alerts,
            msg=(
                f"§9 fix regression: fixed path fired {fixed_alerts} alert(s), "
                f"broken path fired {broken_alerts} alert(s) in "
                f"{len(self._rows_fixed)} ticks. "
                f"The dt_lead=45 turbine credit should eliminate alerts that "
                f"dt_lead=0 would fire."
            ),
        )

    def test_fixed_path_fires_zero_alerts(self):
        """
        TC-E1b: With the chosen parameters, the fixed path must fire zero
        insufficient_reserve_alert ticks across all 60 ticks.

        Parameters are calibrated so turbine ramp credit fully covers every
        STARTING event: already_ramped = min(0.2×45, 6.3) = 6.3 MW ≥ delta_p.
        Any alert on the fixed path is a regression.
        """
        self._run_both()
        fixed_alerts = sum(1 for r in self._rows_fixed if r.insufficient_reserve_alert)

        self.assertEqual(
            fixed_alerts, 0,
            msg=(
                f"Fixed path (dt_lead=45 s) fired {fixed_alerts} alert(s) — "
                f"expected 0.  Turbine ramp credit (min(0.2×45, 6.3) = 6.3 MW) "
                f"should cover the full delta_p so shortfall = 0."
            ),
        )

    def test_simulation_ran_for_at_least_300_seconds(self):
        """
        TC-E1c: Both runs must complete at least 300 simulated seconds (60
        ticks at 5 s/tick).  Guard against the run ending early due to a
        misconfigured end_sim_time.
        """
        self._run_both()
        self.assertGreaterEqual(
            len(self._rows_fixed), 60,
            msg=f"Fixed run only produced {len(self._rows_fixed)} ticks; expected ≥ 60.",
        )
        self.assertGreaterEqual(
            len(self._rows_broken), 60,
            msg=f"Broken run only produced {len(self._rows_broken)} ticks; expected ≥ 60.",
        )


# ---------------------------------------------------------------------------
# TC-E2: BESS bridging headroom is higher on the fixed path
# ---------------------------------------------------------------------------

class TestKubeE2EBridgingHeadroom(unittest.TestCase):

    def _run_both(self):
        if not hasattr(self, "_rows_fixed"):
            self._rows_fixed  = asyncio.run(_run_kube("kube-e2e-brid-fixed",  force_dt_lead_zero=False))
            self._rows_broken = asyncio.run(_run_kube("kube-e2e-brid-broken", force_dt_lead_zero=True))

    def test_mean_bridging_seconds_higher_on_fixed_path(self):
        """
        TC-E2a: The mean bess_bridging_seconds across all ticks must be
        strictly higher on the fixed path than on the broken path.

        Broken path: every STARTING event fires an alert with shortfall_mw>0.
        When shortfall > BESS power ceiling, bess_bridging_seconds collapses to
        0.0 (BESS cannot sustain the predicted peak).  This drags the broken
        mean toward zero.

        Fixed path: no pending shortfall → bess_bridging_seconds reflects actual
        net_demand_mw headroom → strictly positive and higher than the broken mean.
        """
        self._run_both()

        def _mean(rows):
            vals = [min(r.bess_bridging_seconds, 86400.0) for r in rows]
            return sum(vals) / len(vals) if vals else 0.0

        mean_fixed  = _mean(self._rows_fixed)
        mean_broken = _mean(self._rows_broken)

        self.assertGreater(
            mean_fixed, mean_broken,
            msg=(
                f"Expected mean bess_bridging_seconds(fixed={mean_fixed:.1f} s) "
                f"> mean bess_bridging_seconds(broken={mean_broken:.1f} s). "
                f"Broken-path alerts should depress bridging seconds to 0 when "
                f"peak_shortfall > BESS power ceiling."
            ),
        )

    def test_broken_path_has_zero_bridging_at_alert_ticks(self):
        """
        TC-E2b: On the broken path, ticks where insufficient_reserve_alert
        is True must have bess_bridging_seconds == 0.0.

        When shortfall_mw > BESS power ceiling, the BESS cannot bridge the
        predicted peak — bridging_seconds must collapse to 0, not show a
        misleading positive duration.
        """
        self._run_both()
        alert_ticks = [r for r in self._rows_broken if r.insufficient_reserve_alert]

        # Need at least one alert tick to make this assertion non-vacuous.
        self.assertGreater(
            len(alert_ticks), 0,
            msg="No alert ticks on the broken path; cannot check bridging_seconds.",
        )
        for tick in alert_ticks:
            self.assertAlmostEqual(
                tick.bess_bridging_seconds, 0.0, places=9,
                msg=(
                    f"Alert tick (sim_time={tick.sim_time_seconds:.1f} s) has "
                    f"bess_bridging_seconds={tick.bess_bridging_seconds:.3f} s; "
                    f"expected 0.0 when shortfall > BESS power ceiling."
                ),
            )


# ---------------------------------------------------------------------------
# TC-E3: Non-Kube scripted scenario regression guard (demo-20mw)
# ---------------------------------------------------------------------------

class TestDemo20MWRegression(unittest.TestCase):
    """
    Run demo-20mw (no kube_agent, scripted single STARTING event) and confirm
    the §9 fix does not affect non-Kube scenarios.

    Expected outcome (unchanged from pre-fix):
      - 0 insufficient_reserve_alert across 60 ticks
      - exactly 60 ticks (300 s / 5 s interval)
    """

    def _run_demo_20mw(self):
        if not hasattr(self, "_rows"):
            async def _go():
                hub = WebSocketHub()
                manager = RunManager(hub)
                ctx = build_run_context(
                    "demo-20mw-regression",
                    job_id="job-big",
                    node_count=1900,
                    turbine_rated_mw=25.0,
                    bess_rated_mw=18.0,
                    bess_usable_mwh=8.0,
                    bess_grid_forming=True,
                    end_sim_time=300.0,
                )
                await manager.start_run(ctx)
                await manager._tasks[ctx.run_id]
                return ctx.sink.rows
            self._rows = asyncio.run(_go())

    def test_demo_20mw_no_alerts(self):
        """TC-E3a: demo-20mw must never fire insufficient_reserve_alert."""
        self._run_demo_20mw()
        alert_count = sum(1 for r in self._rows if r.insufficient_reserve_alert)
        self.assertEqual(
            alert_count, 0,
            msg=(
                f"demo-20mw fired {alert_count} alert(s) — regression. "
                f"The §9 fix must not affect the scripted (non-Kube) path. "
                f"18 MW BESS with 17 MW bridging headroom should cover peak shortfall."
            ),
        )

    def test_demo_20mw_tick_count(self):
        """TC-E3b: demo-20mw must produce exactly 60 ticks (300 s / 5 s interval)."""
        self._run_demo_20mw()
        self.assertEqual(
            len(self._rows), 60,
            msg=(
                f"demo-20mw produced {len(self._rows)} tick(s); expected 60. "
                f"end_sim_time=300 s at 5 s/tick should give exactly 60 ticks."
            ),
        )


if __name__ == "__main__":
    unittest.main()
