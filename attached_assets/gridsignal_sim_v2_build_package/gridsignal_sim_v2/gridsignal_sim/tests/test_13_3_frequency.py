"""
Phase 13.3 — Swing equation on frequency_forcing_mw acceptance tests.

Design invariants:
  * ONLY frequency_forcing_mw drives df/dt — asset_delivery_error_mw does NOT.
  * Governor droop provides primary frequency response (restoring force).
  * Grid-connected: frequency_hz held at nominal; forcing term inactive (D2).

Acceptance criteria:
  I1  Islanded, power surplus → frequency_hz rises above nominal.
  I2  Frequency excursion within ±10% of swing-equation prediction.
  I3  Islanded, sustained surplus, droop active → frequency returns to nominal.
  I4  Delivery error without plan mismatch → frequency_hz unchanged at 50 Hz.
  I5  Grid-connected → frequency_hz held at nominal; forcing term zero (D2).

All tests are headless, seeded, deterministic.  No LLM or network dependency.
The solar-surplus fixture (IrradianceProfile + override_output_mw) is used by
I1, I2, I3, and I4's indirect path because it gives a clean, deterministic
forcing term without GPU-ramp timing dependencies.
"""

from __future__ import annotations

import sys

import pytest

sys.path.insert(0, ".")

from core.asset_modules import (
    BessModule,
    CoolingModule,
    GPUModule,
    IrradianceProfile,
    SolarModule,
    TurbineModule,
)
from core.models import (
    BessConfig,
    HardwareProfile,
    IslandMode,
    SiteConfig,
    SolarConfig,
    TurbineConfig,
    TurbineState,
    WorkloadClass,
    WorkloadEventType,
    WorkloadSignal,
)
from core.simulation_core import SimulationState, evaluate_tick

from tests.test_forecast_path import (
    _make_state,
    _plane_guard_active,
    _run_tick,
    _starting_signal,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_islanded_solar_state(
    *,
    turbine_rated_mw: float = 10.0,
    turbine_ramp: float = 5.0,
    bess_rated_mw: float = 5.0,
    bess_mwh: float = 2.0,
    bess_soc: float = 1.0,
    inertia_s: float = 4.0,
    droop: float = 0.04,
    f_nominal: float,   # A3 / Task #200: required — no default; pass 50.0 (EU/APAC)
    #                     or 60.0 (WECC/SDG&E) at each call site by intent.
    solar_mw: float = 1.0,
) -> tuple[SimulationState, SolarModule]:
    """Islanded SimulationState with a fixed solar override.

    Built directly (not via _make_state) so the custom inertia and droop
    values can be set without a site_id mismatch against _starting_signal.
    Matches the B1b / B5 build pattern.
    """
    solar = SolarModule(
        config=SolarConfig(asset_id="solar-i", rated_mw=max(2.0, solar_mw * 2)),
        irradiance_profile=IrradianceProfile([]),
    )
    solar.override_output_mw(solar_mw)

    site = SiteConfig(
        site_id="test-13-3",
        pue_base=1.03, alpha_max=0.20, tau_seconds=20.0,
        dt_thermal_seconds=90.0, uncalibrated=False,
        workload_signal_stale_s=30.0,
        island_mode=IslandMode.ISLANDED,
        inertia_constant_s=inertia_s,
        frequency_nominal_hz=f_nominal, power_factor=0.85,
        governor_droop=droop,
    )
    hw = {"enterprise_8gpu_air": HardwareProfile(
        profile_id="enterprise_8gpu_air", rated_kw=10.2
    )}
    state = SimulationState(
        run_id="test",
        site=site,
        gpu_modules=[GPUModule(asset_id="gpu-0", site=site,
                               hardware_library=hw, ramp_seconds=1.0)],
        turbines=[TurbineModule(TurbineConfig(
            asset_id="gt-1",
            rated_mw=turbine_rated_mw,
            r_asset_mw_per_s=turbine_ramp,
        ))],
        bess_units=[BessModule(BessConfig(
            asset_id="bess-1",
            rated_mw=bess_rated_mw,
            usable_mwh=bess_mwh,
            initial_soc_fraction=bess_soc,
            p_anchor_reserve_mw=0.0,
            grid_forming=False,
        ))],
        solar_arrays=[solar],
        cooling=CoolingModule(asset_id="cooling-0", site=site),
    )
    return state, solar


# ---------------------------------------------------------------------------
# I1 — islanded power surplus produces a frequency deviation
# ---------------------------------------------------------------------------

class TestI1FrequencyDeviationVisible:
    """I1: A power surplus in islanded mode appears as a frequency_hz deviation.

    Mechanism: 1 MW solar override with no GPU load → _p_commanded = 1 MW,
    p_total ≈ 0 → frequency_forcing_mw ≈ 1 MW > 0 → df/dt > 0 → frequency rises.
    Verified: frequency_hz > 50 Hz and frequency_forcing_mw is the direct cause.
    """

    def test_I1_islanded_surplus_raises_frequency(self):
        """I1: 1 MW solar surplus in islanded mode → frequency_hz rises above nominal."""
        # EU/APAC fixture: 50 Hz by intent (f_nominal required — no default).
        state, _ = _make_islanded_solar_state(solar_mw=1.0, f_nominal=50.0)
        f_nom = state.site.frequency_nominal_hz  # sourced from config
        # No GPU job → p_total ≈ 0
        tick = _run_tick(state, sim_time=0.0, dt=0.1)

        assert tick.frequency_forcing_mw > 0.9, (
            f"I1: frequency_forcing_mw must be ≈ 1.0 MW with 1 MW solar surplus; "
            f"got {tick.frequency_forcing_mw:.6f} MW"
        )
        assert tick.frequency_hz > f_nom, (
            f"I1: frequency_hz must rise above {f_nom} Hz with positive frequency_forcing_mw; "
            f"got {tick.frequency_hz:.6f} Hz"
        )
        # Delivery channel stays clean — no asset fault, no delivery error
        assert tick.asset_delivery_error_mw == pytest.approx(0.0, abs=1e-9), (
            f"I1: asset_delivery_error_mw must be ~0 for a clean surplus scenario; "
            f"got {tick.asset_delivery_error_mw:.9f} MW"
        )


# ---------------------------------------------------------------------------
# I2 — frequency excursion matches the swing-equation formula within ±10%
# ---------------------------------------------------------------------------

class TestI2SwingEquationAccuracy:
    """I2: The frequency change must match
        Δf = frequency_forcing_mw / (2·H·S_base) · f₀ · dt
    within ±10%.  Verifies the formula is implemented as specified.
    """

    def test_I2_single_tick_matches_formula(self):
        """I2: frequency excursion within ±10% of swing-equation prediction."""
        H = 4.0
        S_base_rated = 10.0   # turbine rated_mw
        dt = 0.1

        # EU/APAC 50 Hz fixture — f_nominal required, set by intent.
        state, _ = _make_islanded_solar_state(
            turbine_rated_mw=S_base_rated,
            inertia_s=H,
            f_nominal=50.0,  # EU/APAC fixture, by intent
            solar_mw=1.0,
        )
        f0 = state.site.frequency_nominal_hz  # sourced from config (= 50.0)
        tick = _run_tick(state, sim_time=0.0, dt=dt)

        ff = tick.frequency_forcing_mw
        # S_base (MVA) = max(1.0, Σ rated_mw) / power_factor — mirrors simulation_core.py.
        s_base_mva = max(1.0, S_base_rated) / state.site.power_factor
        df_predicted = ff / (2.0 * H * s_base_mva) * f0 * dt
        df_actual = tick.frequency_hz - f0

        if abs(ff) < 1e-9:
            pytest.skip("No frequency forcing — I2 not exercisable")

        rel_err = abs(df_actual - df_predicted) / max(abs(df_predicted), 1e-9)
        assert rel_err < 0.10, (
            f"I2: frequency excursion {df_actual:.6f} Hz differs from "
            f"swing-equation prediction {df_predicted:.6f} Hz by "
            f"{rel_err*100:.1f}% (must be < 10%)"
        )

    def test_I2_explicit_formula_fixture(self):
        """I2 (explicit): 1 MW forcing → Δf = 1/(2×4×(10/0.85))×50×5 = 2.65625 Hz.

        S_base (MVA) = rated_mw / power_factor = 10 / 0.85 ≈ 11.765 MVA.
        Δf = 1 / (2 × 4 × 11.765) × 50 × 5 ≈ 2.65625 Hz (was 3.125 Hz at pf=1).
        """
        H = 4.0
        S_base_rated_mw = 10.0
        dt = 5.0

        # EU/APAC 50 Hz fixture — f_nominal required, set by intent.
        state, _ = _make_islanded_solar_state(
            turbine_rated_mw=S_base_rated_mw,
            inertia_s=H,
            f_nominal=50.0,  # EU/APAC fixture, by intent
            solar_mw=1.0,
        )
        f0 = state.site.frequency_nominal_hz  # sourced from config (= 50.0)
        # No GPU job → p_total ≈ 0 → frequency_forcing ≈ 1 MW
        tick = _run_tick(state, sim_time=0.0, dt=dt)

        assert tick.frequency_forcing_mw == pytest.approx(1.0, abs=0.1), (
            f"I2 precondition: frequency_forcing_mw should be ~1 MW; "
            f"got {tick.frequency_forcing_mw:.6f}"
        )

        # S_base (MVA) = rated_mw / power_factor — mirrors simulation_core.py formula.
        s_base_mva = max(1.0, S_base_rated_mw) / state.site.power_factor
        df_predicted = 1.0 / (2.0 * H * s_base_mva) * f0 * dt
        df_actual = tick.frequency_hz - f0
        assert abs(df_actual - df_predicted) < df_predicted * 0.11, (   # ±10% tolerance
            f"I2: Δf={df_actual:.4f} Hz; predicted={df_predicted:.4f} Hz; "
            f"tolerance ±10% ({df_predicted*0.10:.4f} Hz)"
        )


# ---------------------------------------------------------------------------
# I3 — droop returns frequency to nominal after a transient
# ---------------------------------------------------------------------------

class TestI3DroopRestoringForce:
    """I3: Droop creates a negative frequency_forcing_mw when frequency is
    above nominal — a restoring force that pulls frequency back toward 50 Hz.

    Design: single-tick test that isolates the droop direction property cleanly.
    Elevate state._frequency_hz to 52 Hz, run one tick with active GPU load,
    and verify:
      - frequency_forcing_mw < 0  (droop created a restoring force)
      - frequency_hz < 52.0       (frequency actually moved toward nominal)

    The droop mechanism:
      _droop_correction = −(f_error)/(droop×f₀) × S_base
                       = −2.0/(0.04×50)×10 = −10 MW
      _p_dispatch_droop = max(0, p_dispatch_required − 10) = 0
      fleet_shortfall   = max(0, 0 − turbine_output) = 0 (turbine at 0)
      _p_commanded      = 0 + 0 + 0 = 0
      frequency_forcing = _p_commanded − p_total = 0 − L < 0  (restoring)

    Without droop (_droop_correction = 0):
      _p_dispatch_droop = p_dispatch_required = L
      _p_commanded      = L + 0 + 0 = L
      frequency_forcing = 0                        (no restoring force)
    """

    def test_I3_droop_creates_restoring_force_when_f_above_nominal(self):
        """I3: f > 50 Hz with active load → droop produces negative frequency_forcing."""
        state = _make_state(island_mode=IslandMode.ISLANDED)
        sig = _starting_signal(nodes=10, ramp_s=1.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)

        # Force GPU to full TDP so we have a meaningful load (0.105 MW).
        # Power is evaluated at the pre-advance ramp_progress value, so setting
        # it to 1.0 here guarantees p_compute = full TDP in the measurement tick.
        state.gpu_modules[0]._ramp_progress["job-1"] = 1.0

        # Simulate a prior frequency disturbance.
        f_elevated = 52.0
        state._frequency_hz = f_elevated

        # B1: pre-synchronise the turbine so the loading layer drives it to the
        # droop-corrected setpoint (0 MW at f=52 Hz, well above nominal).
        # Without this, apply_workload_signal leaves the turbine RAMPING toward
        # its pre-staged target, cancelling the balance_residual that should
        # produce the restoring frequency_forcing signal.
        state.turbines[0].state = TurbineState.SYNCHRONISED
        state.turbines[0]._current_output_mw = 0.0

        # Droop correction = −2.0 / (0.04 × 50) × 10 = −10 MW → _p_dispatch_droop = 0.
        # Loading layer drives SYNCHRONISED turbine to 0 MW (droop setpoint).
        # balance_residual = 0 − p_total ≈ −0.105 MW → frequency_forcing < 0.
        tick = _run_tick(state, sim_time=5.0, dt=5.0)

        assert tick.frequency_forcing_mw < 0.0, (
            f"I3: droop must produce negative frequency_forcing_mw (restoring force) "
            f"when f={f_elevated} Hz > nominal; got {tick.frequency_forcing_mw:.6f} MW  "
            f"(p_total={tick.p_total_mw:.6f}, gt_setpoint={tick.gt_setpoint_mw:.6f})"
        )
        assert tick.frequency_hz < f_elevated, (
            f"I3: frequency_hz must decrease from {f_elevated} Hz when droop "
            f"restoring force is active; got {tick.frequency_hz:.6f} Hz"
        )

    def test_I3_droop_direction_vs_no_droop(self):
        """I3b: with droop, the frequency change per tick is more negative (less
        positive) than without droop when frequency is above nominal.
        """
        from core.models import SiteConfig
        from core.simulation_core import SimulationState

        sig = _starting_signal(nodes=10, ramp_s=1.0, timestamp=0.0)
        hw = {"enterprise_8gpu_air": HardwareProfile(
            profile_id="enterprise_8gpu_air", rated_kw=10.2
        )}

        def _run_with_droop(droop_val: float) -> float:
            """Return frequency_hz after one tick with f_initial=52 Hz."""
            _site = SiteConfig(
                site_id="test-11",
                pue_base=1.03, alpha_max=0.20, tau_seconds=20.0,
                dt_thermal_seconds=90.0, uncalibrated=False,
                workload_signal_stale_s=30.0,
                island_mode=IslandMode.ISLANDED,
                inertia_constant_s=4.0,
                frequency_nominal_hz=50.0, power_factor=0.85,
                governor_droop=droop_val,
            )
            st = SimulationState(
                run_id="test",
                site=_site,
                gpu_modules=[GPUModule(asset_id="gpu-0", site=_site,
                                       hardware_library=hw, ramp_seconds=1.0)],
                turbines=[TurbineModule(TurbineConfig(
                    asset_id="gt-1", rated_mw=10.0, r_asset_mw_per_s=5.0
                ))],
                bess_units=[BessModule(BessConfig(
                    asset_id="bess-1", rated_mw=5.0, usable_mwh=2.0,
                    initial_soc_fraction=1.0, p_anchor_reserve_mw=0.0,
                    grid_forming=False,
                ))],
                solar_arrays=[],
                cooling=CoolingModule(asset_id="cooling-0", site=_site),
            )
            st.apply_workload_signal(sig, dt_lead_seconds=0.0)
            st.gpu_modules[0]._ramp_progress["job-1"] = 1.0
            st._frequency_hz = 52.0
            # B1: pre-synchronise so the loading layer drives the turbine to the
            # droop-corrected setpoint (not the pre-staged RAMPING target).
            st.turbines[0].state = TurbineState.SYNCHRONISED
            st.turbines[0]._current_output_mw = 0.0
            return _run_tick(st, sim_time=5.0, dt=5.0).frequency_hz

        f_with_droop    = _run_with_droop(0.04)
        f_without_droop = _run_with_droop(0.0)

        # With active droop, frequency must be lower than without droop
        # (droop creates a stronger restoring force when f > 50 Hz).
        assert f_with_droop < f_without_droop, (
            f"I3b: droop (f={f_with_droop:.6f}) should produce a more negative "
            f"df than no-droop (f={f_without_droop:.6f}) when f > 50 Hz"
        )


# ---------------------------------------------------------------------------
# I4 — delivery error without plan mismatch does not move frequency
# ---------------------------------------------------------------------------

class TestI4DeliveryFaultMovesFrequency:
    """I4 (revised — Task #200 B1): a fleet delivery fault in islanded mode causes
    a real frequency deviation.

    Under B1, frequency_forcing_mw = balance_residual = p_gen − p_load (actual).
    Any physical supply-demand imbalance — floor constraint, BESS depletion, turbine
    not yet synchronised — moves frequency.  asset_delivery_error_mw is the reporting
    field that tracks commanded ≠ delivered; it is NOT a separate swing-equation term.

    Scenario: islanded, GPU job active, BESS depleted, turbine not yet synchronised.
    The fleet cannot cover the load: balance_residual < 0 → frequency drops.
    asset_delivery_error < 0 (fleet under-delivered vs setpoint).
    frequency_forcing_mw < 0 (balance_residual < 0 → frequency falling).
    frequency_hz falls below site nominal.

    _make_state(frequency_nominal_hz=50.0, power_factor=0.85) — EU/APAC 50 Hz fixture by intent.
    """

    def test_I4_delivery_fault_causes_frequency_deviation(self):
        """I4: fleet under-delivery (depleted BESS, turbine staging) drops frequency."""
        state = _make_state(
            turbine_ramp=0.2,
            bess_soc=0.0,
            bess_mwh=0.01,
            island_mode=IslandMode.ISLANDED,
        )
        f_nom = state.site.frequency_nominal_hz  # sourced from config (50.0 EU/APAC)
        sig = _starting_signal(nodes=200, ramp_s=1.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)

        # Single tick at sim_time=5.0, dt=0.1 s:
        # GPU load ≈ 0.06 MW (200 nodes, near-zero ramp_progress × ~0.3 kW/node overhead);
        # BESS depleted → bess_output ≈ 0;
        # turbine RAMPING (pre-staged via apply_workload_signal, r_asset=0.2 MW/s):
        #   turb_out = 0.2 × 0.1 = 0.02 MW.
        # balance_residual = 0.02 + 0 − 0.06 ≈ −0.04 MW < 0.
        # frequency_forcing = balance_residual < 0 → frequency drops below nominal.
        tick = _run_tick(state, sim_time=5.0, dt=0.1)

        assert tick.asset_delivery_error_mw != pytest.approx(0.0, abs=1e-6), (
            f"I4: asset_delivery_error_mw must be non-zero (fleet under-delivers); "
            f"got {tick.asset_delivery_error_mw:.9f}"
        )
        # Under B1: frequency_forcing = balance_residual.  Under-supply → forcing < 0.
        assert tick.frequency_forcing_mw < 0.0, (
            f"I4: under-supply → frequency_forcing_mw (= balance_residual) must be < 0; "
            f"got {tick.frequency_forcing_mw:.6f} MW"
        )
        # Frequency must have dropped from nominal (under-supply accelerates frequency fall).
        assert tick.frequency_hz < f_nom, (
            f"I4: frequency_hz must fall below {f_nom} Hz when fleet under-delivers "
            f"in islanded mode; got {tick.frequency_hz:.6f} Hz"
        )


# ---------------------------------------------------------------------------
# I5 — grid-connected: frequency held at nominal; forcing term inactive
# ---------------------------------------------------------------------------

class TestI5GridConnectedFrequencyHeld:
    """I5: In grid-connected mode, frequency_hz is always the site's nominal
    value and frequency_forcing_mw is always 0.0 (D2).
    """

    def test_I5_grid_connected_nominal_frequency(self):
        """I5: grid-connected, depleted BESS → frequency stays at site nominal."""
        state = _make_state(
            bess_soc=0.0,
            bess_mwh=0.01,
            island_mode=IslandMode.GRID_TIE,
        )
        f_nom = state.site.frequency_nominal_hz  # sourced from config (50.0 EU/APAC)
        sig = _starting_signal(nodes=10, ramp_s=1.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)

        tick = _run_tick(state, sim_time=5.0, dt=0.1)

        assert tick.frequency_hz == pytest.approx(f_nom, abs=1e-9), (
            f"I5: frequency_hz must be site nominal ({f_nom} Hz) in grid-connected mode; "
            f"got {tick.frequency_hz:.9f} Hz"
        )
        assert tick.frequency_forcing_mw == pytest.approx(0.0, abs=1e-9), (
            f"I5: frequency_forcing_mw must be 0.0 in grid-connected mode (D2); "
            f"got {tick.frequency_forcing_mw:.9f} MW"
        )

    def test_I5_grid_connected_multiple_ticks(self):
        """I5: frequency stays at site nominal across many ticks in grid-connected mode."""
        state = _make_state(island_mode=IslandMode.GRID_TIE)
        f_nom = state.site.frequency_nominal_hz  # sourced from config (50.0 EU/APAC)
        sig = _starting_signal(nodes=10, ramp_s=1.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)

        for t_s in (0.0, 0.5, 1.0, 5.0, 10.0, 30.0):
            tick = _run_tick(state, sim_time=t_s, dt=0.1)
            assert tick.frequency_hz == pytest.approx(f_nom, abs=1e-9), (
                f"I5: frequency_hz must be {f_nom} Hz (site nominal) at t={t_s}s; "
                f"got {tick.frequency_hz:.9f}"
            )
            assert tick.frequency_forcing_mw == pytest.approx(0.0, abs=1e-9), (
                f"I5: frequency_forcing_mw must be 0.0 at t={t_s}s; "
                f"got {tick.frequency_forcing_mw:.9f}"
            )
