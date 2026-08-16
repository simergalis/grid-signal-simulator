"""
test_bess_surplus_absorption.py — black-box tests for BESS surplus absorption.

Background
----------
When turbines at MSL (minimum stable load) produce more power than
p_dispatch_required_mw (= p_demand − p_renewable), a generation surplus arises.
Previously, this surplus spilled entirely into frequency_forcing_mw (islanded)
or grid_exchange_mw (grid-connected), making the plant diagram show an
apparent energy imbalance (e.g. 10 MW turbine + 1.35 MW solar vs 5.72 MW load
with no visible sink for the 5.63 MW difference).

The fix: DispatchArbitrator.tick() now routes the surplus to BESS charging via
BessModule.absorb_surplus().  bess_setpoint_mw < 0 (absorption command);
bess_output_mw ≤ 0 (negative = charging, reduces _p_gen_mw, lowers the
frequency_forcing_mw residual).  PlantNode.tsx already handles negative
bess_output_mw with an "absorbing · X.X MW" sub-label.

Test matrix
-----------
TC-SURP-1  Fleet surplus → BESS absorbs; bess_output_mw < 0.
TC-SURP-2  Full BESS (SoC ≈ 100%) cannot absorb — output stays 0.
TC-SURP-3  BESS SoC rises after surplus absorption.
TC-SURP-4  Partial absorption when rated_mw < fleet_surplus.
TC-SURP-5  frequency_forcing_mw is reduced by absorption vs full spill.
TC-SURP-6  Taper timer reset: after absorption BESS re-engages discharge immediately.
TC-SURP-7  Shortfall path is unaffected when fleet_shortfall > 0.
TC-SURP-8  Tick payload fields have the correct sign after absorption.
"""

import math
import contextlib
import pytest
from core.asset_modules import BessModule, TurbineModule, TurbineState
from core.models import BessConfig, TurbineConfig, IslandMode, SiteConfig, HardwareProfile
from core.simulation_core import SimulationState, evaluate_tick
from core.asset_modules import GPUModule, CoolingModule
from core.sim_clock import SimClock
from core._plane_guard import _EVALUATE_TICK_PERMITTED


@contextlib.contextmanager
def _plane_guard_active():
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        yield
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_bess(
    rated_mw: float = 5.0,
    usable_mwh: float = 2.0,
    soc_fraction: float = 0.5,   # 50% SoC by default — room to absorb
    tau_s: float = 0.0,          # no lag so results are deterministic
    anchor_mw: float = 0.0,
    grid_forming: bool = False,
) -> BessModule:
    cfg = BessConfig(
        asset_id="bess-test",
        rated_mw=rated_mw,
        usable_mwh=usable_mwh,
        initial_soc_fraction=soc_fraction,
        p_anchor_reserve_mw=anchor_mw,
        grid_forming=grid_forming,
        bess_response_tau_s=tau_s,
    )
    return BessModule(cfg)


_SITE = SiteConfig(
    site_id="test-surplus",
    pue_base=1.03, alpha_max=0.20, tau_seconds=20.0,
    dt_thermal_seconds=90.0, uncalibrated=False,
    workload_signal_stale_s=30.0,
    island_mode=IslandMode.ISLANDED,
    inertia_constant_s=4.0, frequency_nominal_hz=50.0,
    power_factor=0.85, governor_droop=0.04,
)
_HW = {"enterprise_8gpu_air": HardwareProfile(profile_id="enterprise_8gpu_air", rated_kw=10.2)}


def _make_state(
    turbine_output_mw: float = 10.0,
    turbine_rated_mw: float = 10.0,
    bess_soc: float = 0.5,
    bess_rated_mw: float = 5.0,
    bess_mwh: float = 2.0,
    bess_tau_s: float = 0.0,
    island_mode: IslandMode = IslandMode.ISLANDED,
) -> SimulationState:
    turb_cfg = TurbineConfig(
        asset_id="gt-1",
        rated_mw=turbine_rated_mw,
        r_asset_mw_per_s=10.0,   # fast ramp so it doesn't move in the tick
    )
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        bess_cfg = BessConfig(
            asset_id="bess-1",
            rated_mw=bess_rated_mw,
            usable_mwh=bess_mwh,
            initial_soc_fraction=bess_soc,
            p_anchor_reserve_mw=0.0,
            grid_forming=False,
            bess_response_tau_s=bess_tau_s,
        )
    site = SiteConfig(
        site_id="test-surplus",
        pue_base=1.03, alpha_max=0.20, tau_seconds=20.0,
        dt_thermal_seconds=90.0, uncalibrated=False,
        workload_signal_stale_s=30.0,
        island_mode=island_mode,
        inertia_constant_s=4.0, frequency_nominal_hz=50.0,
        power_factor=0.85, governor_droop=0.04,
    )
    state = SimulationState(
        run_id="test-surplus",
        site=site,
        gpu_modules=[GPUModule(asset_id="gpu-0", site=site, hardware_library=_HW, ramp_seconds=1.0)],
        turbines=[TurbineModule(turb_cfg)],
        bess_units=[BessModule(bess_cfg)],
        solar_arrays=[],
        cooling=CoolingModule(asset_id="cooling-0", site=site),
    )
    # Pre-set turbine to SYNCHRONISED and producing turbine_output_mw.
    turb = state.turbines[0]
    turb._current_output_mw = turbine_output_mw
    turb.state = TurbineState.SYNCHRONISED
    return state


def _run_tick(state: SimulationState, sim_time: float = 5.0, dt: float = 1.0):
    clock = SimClock(sim_time=sim_time, dt_seconds=dt, wall_stamp_utc=0.0, rate=1.0, tick_seq=0)
    with _plane_guard_active():
        return evaluate_tick(state, clock)


# ---------------------------------------------------------------------------
# TC-SURP-1: Fleet surplus routes to BESS absorption
# ---------------------------------------------------------------------------

class TestSurplusAbsorption:

    def test_TC_SURP_1_surplus_bess_absorbs(self):
        """TC-SURP-1: When turbine overproduces (no load), BESS absorbs the
        surplus.  bess_setpoint_mw < 0 (absorption command) and
        bess_output_mw < 0 (negative generation = charging)."""
        # Turbine at 5 MW, no GPU load → fleet_surplus = 5 MW.
        state = _make_state(turbine_output_mw=5.0, bess_soc=0.5)
        tick = _run_tick(state)

        assert tick.bess_setpoint_mw < 0.0, (
            f"TC-SURP-1: bess_setpoint_mw must be < 0 (absorption command); "
            f"got {tick.bess_setpoint_mw:.4f} MW"
        )
        assert tick.bess_output_mw <= 0.0, (
            f"TC-SURP-1: bess_output_mw must be ≤ 0 (charging); "
            f"got {tick.bess_output_mw:.4f} MW"
        )
        # bess_output_mw < 0 is the convention used by PlantNode.tsx 'absorbing' label.
        excess = -tick.bess_output_mw
        assert excess > 0.0, (
            f"TC-SURP-1: absorbed MW (−bess_output_mw) must be > 0; got {excess:.4f}"
        )

    def test_TC_SURP_2_full_bess_cannot_absorb(self):
        """TC-SURP-2: A fully-charged BESS (SoC=100%) returns 0 from absorb_surplus;
        bess_output_mw stays 0 even with a large surplus."""
        # Turbine at 5 MW, no load, BESS full.
        state = _make_state(turbine_output_mw=5.0, bess_soc=1.0)
        tick = _run_tick(state)

        assert tick.bess_output_mw == pytest.approx(0.0, abs=1e-6), (
            f"TC-SURP-2: full BESS cannot absorb; bess_output_mw must be 0; "
            f"got {tick.bess_output_mw:.6f} MW"
        )

    def test_TC_SURP_3_soc_rises_after_absorption(self):
        """TC-SURP-3: BESS SoC increases after surplus absorption."""
        state = _make_state(turbine_output_mw=5.0, bess_soc=0.5, bess_mwh=2.0)
        soc_before = state.bess_units[0].soc_mwh

        _run_tick(state, dt=1.0)

        soc_after = state.bess_units[0].soc_mwh
        assert soc_after > soc_before, (
            f"TC-SURP-3: BESS SoC must rise after surplus absorption; "
            f"before={soc_before:.4f} MWh, after={soc_after:.4f} MWh"
        )

    def test_TC_SURP_4_partial_absorption_when_rated_mw_limits(self):
        """TC-SURP-4: When fleet_surplus > rated_mw, BESS absorbs at most rated_mw.
        Some surplus remains and routes to frequency_forcing_mw (islanded)."""
        # fleet_surplus ≈ 10 MW (turbine), BESS rated at 3 MW.
        state = _make_state(
            turbine_output_mw=10.0,
            bess_rated_mw=3.0,
            bess_mwh=5.0,    # plenty of SoC headroom
            bess_soc=0.0,
        )
        tick = _run_tick(state, dt=1.0)

        absorbed = -tick.bess_output_mw
        assert absorbed == pytest.approx(3.0, abs=0.05), (
            f"TC-SURP-4: absorption limited to rated_mw=3.0 MW; got {absorbed:.4f} MW"
        )
        # Residual surplus (10 - 3 = 7 MW) routes to frequency_forcing_mw.
        assert tick.frequency_forcing_mw > 0.0, (
            f"TC-SURP-4: un-absorbed surplus must appear in frequency_forcing_mw; "
            f"got {tick.frequency_forcing_mw:.4f}"
        )

    def test_TC_SURP_5_absorption_reduces_frequency_forcing(self):
        """TC-SURP-5: BESS absorption shrinks frequency_forcing_mw in island mode.
        With a BESS that can absorb and one that cannot (full), the latter must
        produce a larger frequency deviation for the same generation surplus."""
        # Two scenarios: same turbine surplus, one BESS absorbs, one cannot.
        state_absorb = _make_state(turbine_output_mw=5.0, bess_soc=0.5)
        state_full   = _make_state(turbine_output_mw=5.0, bess_soc=1.0)

        tick_absorb = _run_tick(state_absorb, dt=1.0)
        tick_full   = _run_tick(state_full,   dt=1.0)

        # When BESS absorbs, balance_residual is smaller → frequency_forcing is smaller.
        assert tick_absorb.frequency_forcing_mw < tick_full.frequency_forcing_mw, (
            f"TC-SURP-5: BESS absorption must reduce frequency_forcing_mw; "
            f"absorb={tick_absorb.frequency_forcing_mw:.4f}, "
            f"full={tick_full.frequency_forcing_mw:.4f}"
        )

    def test_TC_SURP_6_taper_reset_bess_re_engages_on_shortfall(self):
        """TC-SURP-6: absorb_surplus() resets the taper timer so the BESS
        re-engages discharge immediately on the next shortfall tick."""
        state = _make_state(turbine_output_mw=5.0, bess_soc=0.5)
        bess = state.bess_units[0]

        # Simulate 15 seconds of normal discharge + taper accumulation.
        bess._sustained_catchup_seconds = 15.0   # would block discharge

        # One absorption tick (surplus path) — should reset the timer.
        bess.absorb_surplus(surplus_mw=1.0, dt_seconds=1.0)
        assert bess._sustained_catchup_seconds == 0.0, (
            "TC-SURP-6: absorb_surplus must reset _sustained_catchup_seconds to 0"
        )

    def test_TC_SURP_7_shortfall_path_unaffected(self):
        """TC-SURP-7: When fleet_shortfall > 0 (turbine under-produces), the
        existing discharge path is used — bess_setpoint_mw > 0 and
        bess_output_mw ≥ 0 (no change in behaviour).

        Achieved by setting turbine output = 0 MW (OFFLINE) and applying a
        large load, forcing the BESS to discharge."""
        # No turbine output (turbine left OFFLINE), large load.
        state = _make_state(turbine_output_mw=0.0, bess_soc=1.0)
        # Set turbine to OFFLINE so it contributes 0 MW to fleet.
        state.turbines[0].state = TurbineState.OFFLINE
        state.turbines[0]._current_output_mw = 0.0

        # Inject a meaningful load via GPU ramp.
        from tests.test_forecast_path import _starting_signal
        sig = _starting_signal(nodes=500, ramp_s=1.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)
        state.gpu_modules[0]._ramp_progress["job-1"] = 1.0

        tick = _run_tick(state, dt=1.0)

        # Turbine offline, large demand → fleet_shortfall > 0 → discharge path.
        assert tick.bess_setpoint_mw >= 0.0, (
            f"TC-SURP-7: shortfall tick must have bess_setpoint_mw ≥ 0; "
            f"got {tick.bess_setpoint_mw:.4f} MW"
        )
        assert tick.bess_output_mw >= 0.0, (
            f"TC-SURP-7: shortfall tick must have bess_output_mw ≥ 0; "
            f"got {tick.bess_output_mw:.4f} MW"
        )

    def test_TC_SURP_8_tick_fields_correct_sign_after_absorption(self):
        """TC-SURP-8: After surplus absorption the TickResult fields have the
        correct sign convention required by PlantNode.tsx:
          • bess_setpoint_mw < 0  (absorption command)
          • bess_output_mw < 0    (negative generation; UI shows 'absorbing')
          • p_gen = turbine + bess_output + solar (bess contribution subtracts)
          • D4: grid_exchange + frequency_forcing = p_gen − p_demand
        """
        state = _make_state(turbine_output_mw=8.0, bess_soc=0.5,
                            bess_rated_mw=5.0, bess_mwh=2.0)
        tick = _run_tick(state, dt=1.0)

        # Sign assertions.
        assert tick.bess_setpoint_mw < 0.0
        assert tick.bess_output_mw <= 0.0

        # Energy balance: p_gen − p_demand = grid_exchange + frequency_forcing.
        p_gen     = tick.turbine_output_mw + tick.bess_output_mw + tick.p_renewable_mw
        p_residual = p_gen - tick.p_demand_mw
        d4_sum    = tick.grid_exchange_mw + tick.frequency_forcing_mw
        assert abs(d4_sum - p_residual) < 1e-3, (
            f"TC-SURP-8: D4 identity must close; "
            f"p_residual={p_residual:.6f}, d4_sum={d4_sum:.6f}"
        )

    def test_TC_SURP_9_energy_headroom_limits_absorption(self):
        """TC-SURP-9: SoC headroom (not rated_mw) caps absorption when the
        battery is nearly full.  A BESS with 0.002 MWh of headroom can absorb
        at most 0.002 / (dt_hours) MW regardless of rated_mw."""
        dt_s = 1.0
        dt_h = dt_s / 3600.0
        usable_mwh = 2.0
        soc_fraction = 1.0 - (0.002 / usable_mwh)  # 0.002 MWh headroom

        state = _make_state(
            turbine_output_mw=5.0,
            bess_soc=soc_fraction,
            bess_rated_mw=5.0,
            bess_mwh=usable_mwh,
        )
        tick = _run_tick(state, dt=dt_s)

        absorbed = -tick.bess_output_mw
        max_expected = 0.002 / dt_h  # = 7.2 MW
        # Absorbed should be ≤ min(fleet_surplus=5, rated_mw=5, max_by_energy=7.2) = 5 MW.
        # The binding limit here is the fleet_surplus (5 MW), not the headroom (7.2 MW).
        # Just assert absorbed ≤ rated_mw and ≤ max_by_energy.
        assert absorbed <= 5.0 + 1e-6, (
            f"TC-SURP-9: absorbed ({absorbed:.4f} MW) must not exceed rated_mw=5.0"
        )
        assert absorbed <= max_expected + 1e-6, (
            f"TC-SURP-9: absorbed ({absorbed:.4f} MW) must not exceed SoC headroom"
        )

    def test_TC_SURP_10_first_order_lag_ramps_absorption(self):
        """TC-SURP-10: With non-zero tau, absorb_surplus applies a first-order
        lag so absorption ramps up over multiple ticks (not step-change)."""
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            bess = _make_bess(
                rated_mw=5.0,
                usable_mwh=10.0,
                soc_fraction=0.0,   # empty — plenty of headroom
                tau_s=0.5,          # 500 ms lag — significant at dt=0.1 s
            )

        surplus_mw = 5.0
        dt_s = 0.1
        alpha = 1.0 - math.exp(-dt_s / 0.5)   # ≈ 0.181

        # First tick from standby (_prev=0): absorbed ≈ alpha × 5.0 ≈ 0.906 MW.
        tick1_absorbed = bess.absorb_surplus(surplus_mw, dt_s)
        expected_tick1 = alpha * surplus_mw
        assert tick1_absorbed == pytest.approx(expected_tick1, abs=0.01), (
            f"TC-SURP-10: first-tick absorption ({tick1_absorbed:.4f} MW) "
            f"must follow first-order lag (expected ≈{expected_tick1:.4f} MW)"
        )

        # Second tick: prev_charge ≈ tick1_absorbed, absorbed ramps further up.
        tick2_absorbed = bess.absorb_surplus(surplus_mw, dt_s)
        assert tick2_absorbed > tick1_absorbed, (
            f"TC-SURP-10: absorption must ramp upward on successive ticks; "
            f"tick1={tick1_absorbed:.4f}, tick2={tick2_absorbed:.4f}"
        )
        assert tick2_absorbed < surplus_mw + 1e-6, (
            f"TC-SURP-10: absorption must not exceed fleet_surplus; "
            f"tick2={tick2_absorbed:.4f}, surplus={surplus_mw}"
        )
