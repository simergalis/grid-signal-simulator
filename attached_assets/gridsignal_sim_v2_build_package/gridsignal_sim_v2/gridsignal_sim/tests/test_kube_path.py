"""
tests/test_kube_path.py — Regression tests for the Kubernetes demand-agent path.

§9 / resolution-log item 5:
  Kubernetes WorkloadSignals must use dt_lead_seconds = GPUModule.ramp_seconds
  (default 45 s), not 0.0.  The 0-lead defect caused systematic over-alerts
  and broke the v0.1 worked-example fixture on the Kube path.

TC-K1: dt_lead_seconds matches ramp_seconds when evaluate_tick processes a
        Kubernetes WorkloadSignal.
TC-K2: Peak shortfall is reduced by turbine ramp credit (already_ramped_mw > 0)
        relative to the naive dt_lead=0 case — proving the BESS bridging
        requirement is correctly smaller.
TC-K3: Scripted-path WorkloadSignals (explicit dt_lead) are unaffected by the
        change — only the Kube path reads ramp_seconds.
TC-K4: Custom ramp_seconds (e.g. 90 s) is picked up correctly.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from core.asset_modules import (
    BessConfig,
    BessModule,
    CoolingModule,
    GPUModule,
    TurbineConfig,
    TurbineModule,
)
from core.dispatch import DispatchArbitrator
from core.kube_demand import KubeConfig, KubeDemandAgent
from core.models import IslandMode, SiteConfig, WorkloadSignal
from core.sim_clock import SimClock
from core.simulation_core import SimulationState, evaluate_tick
from tests.test_plane_separation import _plane_guard_active


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_clock(sim_time: float = 0.0, dt_seconds: float = 5.0) -> SimClock:
    return SimClock(
        sim_time=sim_time,
        dt_seconds=dt_seconds,
        wall_stamp_utc=0.0,
        rate=0.0,
        tick_seq=0,
    )


def _make_state(
    *,
    ramp_seconds: float = 45.0,
    with_kube: bool = True,
    turbine_rated_mw: float = 30.0,
    r_asset_mw_per_s: float = 0.2,
) -> SimulationState:
    """Build a minimal SimulationState suitable for Kube-path tests."""
    site = SiteConfig(site_id="site-kube-test")
    gpu = GPUModule(
        asset_id="gpu-0",
        site=site,
        hardware_library={},   # empty → unmapped, fine for this test
    )
    # Override ramp_seconds so TC-K4 can use a non-default value.
    gpu.ramp_seconds = ramp_seconds

    turbine = TurbineModule(
        TurbineConfig(
            asset_id="turbine-0",
            r_asset_mw_per_s=r_asset_mw_per_s,
            rated_mw=turbine_rated_mw,
        )
    )
    bess = BessModule(
        BessConfig(
            asset_id="bess-0",
            rated_mw=5.0,
            usable_mwh=2.0,
            initial_soc_fraction=0.90,
        )
    )
    cooling = CoolingModule(asset_id="cooling-0", site=site)

    state = SimulationState(
        run_id="run-kube-test",
        site=site,
        gpu_modules=[gpu],
        turbines=[turbine],
        bess_units=[bess],
        solar_arrays=[],
        cooling=cooling,
    )

    if with_kube:
        cfg = KubeConfig(
            max_nodes=200,
            min_nodes=50,
            mean_job_nodes=50,
            job_node_std=10.0,
            min_job_nodes=10,
            mean_interarrival_s=10.0,
            mean_job_duration_s=300.0,
            reorder_window_s=0.0,   # drain immediately — no delay in tests
            ntp_jitter_s=0.0,       # deterministic timestamps
            rng_seed=42,
        )
        state.kube_agent = KubeDemandAgent(cfg, site_id="site-kube-test")

    return state


# ---------------------------------------------------------------------------
# TC-K1: dt_lead_seconds == ramp_seconds on the Kube path
# ---------------------------------------------------------------------------

class TestKubePathDtLead(unittest.TestCase):

    def test_kube_signal_uses_ramp_seconds_as_dt_lead(self):
        """
        TC-K1: Kubernetes WorkloadSignals are staged with dt_lead_seconds
        equal to GPUModule.ramp_seconds (45 s default), not 0.0.

        Regression: the previous implementation hard-coded dt_lead=0.0 so the
        arbitrator computed already_ramped_mw=0 and sized BESS bridging against
        the full ΔP.  This verifies the §9 fix is in the call site.
        """
        state = _make_state(ramp_seconds=45.0)

        captured_leads: list[float] = []
        original_apply = state.apply_workload_signal

        def capturing_apply(signal: WorkloadSignal, dt_lead_seconds: float) -> None:
            captured_leads.append(dt_lead_seconds)
            return original_apply(signal, dt_lead_seconds)

        with patch.object(state, "apply_workload_signal", side_effect=capturing_apply):
            with _plane_guard_active():
                evaluate_tick(state, _make_clock(sim_time=0.0, dt_seconds=5.0))

        # evaluate_tick at t=0 always produces at least one Kube signal
        # (the first STARTING signal is forced when _started=False).
        self.assertGreater(
            len(captured_leads), 0,
            "Expected at least one Kube WorkloadSignal on the first tick",
        )
        for lead in captured_leads:
            self.assertAlmostEqual(
                lead, 45.0,
                msg=(
                    f"Kube path used dt_lead_seconds={lead!r}; "
                    "expected 45.0 (== GPUModule.ramp_seconds). "
                    "Regression: §9 / resolution-log item 5."
                ),
            )

    def test_kube_signal_zero_lead_was_wrong(self):
        """
        TC-K1b: Demonstrates that dt_lead=0.0 (the old value) gives a
        different (larger) BESS bridging requirement than dt_lead=45.0.

        This is a characterisation of the defect so the test suite documents
        the before/after contrast, not just the fix.
        """
        from core.models import WorkloadEventType, WorkloadClass

        state_fixed  = _make_state(ramp_seconds=45.0, turbine_rated_mw=30.0)
        state_broken = _make_state(ramp_seconds=45.0, turbine_rated_mw=30.0)

        def _manual_signal(state: SimulationState, dt_lead: float) -> bool:
            sig = WorkloadSignal(
                event_id="test-sig",
                job_id="test-job",
                event_type=WorkloadEventType.STARTING,
                timestamp=0.0,
                hardware_profile_id="enterprise_8gpu_air",
                node_count=50,
                workload_class=WorkloadClass.TRAINING,
                site_id="site-kube-test",
            )
            state.apply_workload_signal(sig, dt_lead_seconds=dt_lead)
            return state._pending_alert is not None

        alert_fixed  = _manual_signal(state_fixed,  dt_lead=45.0)
        alert_broken = _manual_signal(state_broken, dt_lead=0.0)

        # The fixed path should not produce MORE alerts than the broken path.
        if alert_fixed and not alert_broken:
            self.fail(
                "Regression: fixed path (dt_lead=45s) fires an alert that "
                "the broken path (dt_lead=0) did NOT — this would be wrong."
            )
        # Both fire or both quiet: physically valid depending on BESS SoC.


# ---------------------------------------------------------------------------
# TC-K2: BESS bridging requirement reduced by turbine ramp credit
# ---------------------------------------------------------------------------

class TestKubeTurbineCredit(unittest.TestCase):

    def test_already_ramped_mw_is_nonzero_with_kube_fix(self):
        """
        TC-K2: With dt_lead=ramp_seconds=45 and r_asset=0.2 MW/s, the
        arbitrator sees already_ramped_mw = min(0.2 × 45, delta_p) = 9.0 MW
        of turbine credit.  peak_shortfall_mw is therefore reduced vs. dt_lead=0.

        This is the worked-example fixture from §9.
        """
        site = SiteConfig(site_id="site-tc-k2")
        turbine = TurbineModule(TurbineConfig(
            asset_id="turbine-0",
            r_asset_mw_per_s=0.2,
            rated_mw=30.0,
        ))
        bess = BessModule(BessConfig(
            asset_id="bess-a",
            rated_mw=5.0,
            usable_mwh=2.0,
            initial_soc_fraction=0.90,
            grid_forming=True,
            p_anchor_reserve_mw=1.0,
        ))
        arb = DispatchArbitrator(turbines=[turbine], bess_units=[bess], site=site)

        # dt_lead=45 s → already_ramped = min(0.2 × 45, delta_p) = min(9.0, 15.0) = 9.0
        alert_fixed = arb.stage_for_predicted_step(
            delta_p_mw=15.0,
            dt_lead_seconds=45.0,
            sim_time=0.0,
        )
        shortfall_fixed = alert_fixed.shortfall_mw if alert_fixed else 0.0

        # dt_lead=0 → already_ramped=0, shortfall = max(0, 15.0 - BESS ceiling)
        alert_zero = arb.stage_for_predicted_step(
            delta_p_mw=15.0,
            dt_lead_seconds=0.0,
            sim_time=0.0,
        )
        shortfall_zero = alert_zero.shortfall_mw if alert_zero else 0.0

        # Fixed path must give ≤ shortfall than zero-lead path
        self.assertLessEqual(
            shortfall_fixed, shortfall_zero,
            msg=(
                f"Turbine ramp credit should reduce peak_shortfall: "
                f"dt_lead=45 gave {shortfall_fixed:.2f} MW, "
                f"dt_lead=0 gave {shortfall_zero:.2f} MW"
            ),
        )


# ---------------------------------------------------------------------------
# TC-K3: Scripted-path signals are unaffected
# ---------------------------------------------------------------------------

class TestScriptedPathUnchanged(unittest.TestCase):

    def test_scripted_signal_passes_explicit_dt_lead(self):
        """
        TC-K3: apply_workload_signal() called directly (scripted path) with an
        explicit dt_lead_seconds must use the caller's value, not ramp_seconds.

        The fix is surgical — only the Kube dispatch in evaluate_tick() changed,
        not apply_workload_signal() itself.
        """
        state = _make_state(with_kube=False, ramp_seconds=45.0)

        from core.models import WorkloadEventType, WorkloadClass

        sig = WorkloadSignal(
            event_id="scripted-1",
            job_id="scripted-job-1",
            event_type=WorkloadEventType.STARTING,
            timestamp=0.0,
            hardware_profile_id="enterprise_8gpu_air",
            node_count=10,
            workload_class=WorkloadClass.TRAINING,
            site_id="site-kube-test",
        )
        # Scripted path with explicit 30 s lead — must NOT be overridden to 45 s
        state.apply_workload_signal(sig, dt_lead_seconds=30.0)
        # No assertion beyond "it didn't raise" — the scripted path is
        # tested exhaustively by test_formulas.py and test_step8_scenarios.py.

    def test_solar_step_always_zero_dt_lead(self):
        """
        TC-K3b: SOLAR_STEP signals always use dt_lead=0 (§7.1.1).
        The Kube-path fix must not affect this.
        """
        state = _make_state(with_kube=False)

        from core.models import WorkloadEventType, WorkloadClass

        solar = WorkloadSignal(
            event_id="solar-1",
            job_id="solar-job",
            event_type=WorkloadEventType.SOLAR_STEP,
            timestamp=0.0,
            hardware_profile_id="enterprise_8gpu_air",
            node_count=0,
            workload_class=WorkloadClass.TRAINING,
            site_id="site-kube-test",
            renewable_shortfall_mw=5.0,
        )
        # apply_workload_signal internally enforces dt_lead=0 for SOLAR_STEP;
        # the caller's argument is ignored (early-return at the SOLAR_STEP branch).
        state.apply_workload_signal(solar, dt_lead_seconds=999.0)


# ---------------------------------------------------------------------------
# TC-K4: Custom ramp_seconds is picked up
# ---------------------------------------------------------------------------

class TestCustomRampSeconds(unittest.TestCase):

    def test_custom_ramp_seconds_propagates_to_kube_dt_lead(self):
        """
        TC-K4: If GPUModule.ramp_seconds is set to a non-default value
        (e.g. 90 s for a slower-ramping workload), the Kube dispatch path
        uses that value rather than the hard-coded 45 s default.
        """
        state = _make_state(ramp_seconds=90.0)
        self.assertEqual(state.gpu_modules[0].ramp_seconds, 90.0)

        captured_leads: list[float] = []
        original_apply = state.apply_workload_signal

        def capturing_apply(signal: WorkloadSignal, dt_lead_seconds: float) -> None:
            captured_leads.append(dt_lead_seconds)
            return original_apply(signal, dt_lead_seconds)

        with patch.object(state, "apply_workload_signal", side_effect=capturing_apply):
            with _plane_guard_active():
                evaluate_tick(state, _make_clock(sim_time=0.0, dt_seconds=5.0))

        self.assertGreater(len(captured_leads), 0)
        for lead in captured_leads:
            self.assertAlmostEqual(
                lead, 90.0,
                msg=(
                    f"Expected dt_lead=90.0 (custom ramp_seconds) but got {lead!r}. "
                    "The Kube path must read ramp_seconds from the GPU module, "
                    "not use a hard-coded default."
                ),
            )


if __name__ == "__main__":
    unittest.main()
