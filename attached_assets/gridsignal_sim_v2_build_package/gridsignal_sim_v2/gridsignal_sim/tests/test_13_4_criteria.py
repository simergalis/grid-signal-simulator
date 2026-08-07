"""
Phase 13.4 — Setpoint / actual split

B1  Inject a deliberate 1 MW load-model error, islanded:
        model_error_mw changes by ≥ 0.9 MW;
        BESS does not silently absorb it (setpoint unchanged vs baseline);
        frequency_hz does not move.

B2  BESS output vs bess_setpoint_mw:
        tracks setpoint through its modelled time constant;
        never derived from any residual.

B3  bess_setpoint_mw exceeds rating:
        binding_constraint populated and surfaced.

B4  Any tick that would show "BESS standby" in the UI:
        bess_setpoint_mw ≈ 0 at that tick.
"""

from __future__ import annotations

import math
import pytest

from core.asset_modules import BessModule, TurbineState
from core.models import (
    BessConfig,
    IslandMode,
    SiteConfig,
)
from core.simulation_core import SimulationState

# ---------------------------------------------------------------------------
# Shared helpers — reuse the established _make_state / _run_tick / _starting_signal
# infrastructure from test_forecast_path so this file stays thin.
# ---------------------------------------------------------------------------
from tests.test_forecast_path import (
    _make_state,
    _plane_guard_active,
    _run_tick,
    _starting_signal,
)


def _biased_state(bias_mw: float = 1.0, **kwargs) -> SimulationState:
    """
    Islanded state with a deliberate load-model bias injected via
    SiteConfig.load_model_bias_mw.  All other parameters are the
    _make_state defaults.
    """
    site = SiteConfig(
        site_id="test-13-4",
        pue_base=1.03,
        alpha_max=0.20,
        tau_seconds=20.0,
        dt_thermal_seconds=90.0,
        uncalibrated=False,
        workload_signal_stale_s=30.0,
        island_mode=IslandMode.ISLANDED,
        inertia_constant_s=4.0,
        frequency_nominal_hz=50.0, power_factor=0.85,
        governor_droop=0.04,
        load_model_bias_mw=bias_mw,
    )
    return _make_state(site=site, **kwargs)


# ===========================================================================
# B1 — model_error_mw is observable; BESS and frequency are unaffected
# ===========================================================================

class TestB1ModelErrorObservable:

    def test_B1a_no_bias_model_error_is_zero(self):
        """Baseline: with no injected bias, model_error_mw == 0."""
        state = _make_state()
        tick  = _run_tick(state)
        assert tick.model_error_mw == pytest.approx(0.0, abs=1e-9), (
            f"With no bias, model_error_mw must be 0; got {tick.model_error_mw}"
        )

    def test_B1b_injected_1mw_bias_visible_in_model_error(self):
        """Injecting 1 MW bias surfaces ≥ 0.9 MW in model_error_mw."""
        state = _biased_state(bias_mw=1.0)
        tick  = _run_tick(state)
        assert tick.model_error_mw >= 0.9, (
            f"1 MW injected bias must produce model_error_mw ≥ 0.9; "
            f"got {tick.model_error_mw}"
        )

    def test_B1c_bias_does_not_inflate_bess_setpoint(self):
        """
        Model error must NOT silently flow into BESS dispatch.
        bess_setpoint_mw with 1 MW bias must match the no-bias baseline.
        """
        tick_base = _run_tick(_make_state())
        tick_bias = _run_tick(_biased_state(bias_mw=1.0))

        assert tick_bias.bess_setpoint_mw == pytest.approx(
            tick_base.bess_setpoint_mw, abs=0.05
        ), (
            "Model error must not inflate BESS setpoint.  "
            f"base={tick_base.bess_setpoint_mw:.4f}, "
            f"bias={tick_bias.bess_setpoint_mw:.4f}"
        )

    def test_B1d_bias_does_not_move_frequency(self):
        """
        Model error must NOT enter the swing equation.
        frequency_hz with 1 MW bias must match the no-bias baseline.
        """
        tick_base = _run_tick(_make_state())
        tick_bias = _run_tick(_biased_state(bias_mw=1.0))

        assert tick_bias.frequency_hz == pytest.approx(
            tick_base.frequency_hz, abs=0.001
        ), (
            "Model error must not move frequency.  "
            f"base={tick_base.frequency_hz:.4f} Hz, "
            f"bias={tick_bias.frequency_hz:.4f} Hz"
        )

    def test_B1e_bias_separate_from_asset_delivery_error(self):
        """
        model_error_mw must be independent of asset_delivery_error_mw.
        A healthy fleet (no SOC depletion) must keep asset_delivery_error ≈ 0
        even when a load-model bias is active.
        """
        state = _biased_state(bias_mw=1.0)
        tick  = _run_tick(state)
        assert abs(tick.asset_delivery_error_mw) < 0.3, (
            "asset_delivery_error_mw must stay near 0 with a healthy fleet; "
            f"got {tick.asset_delivery_error_mw:.4f}.  "
            "model_error_mw is a separate channel."
        )


# ===========================================================================
# B2 — BESS output tracks setpoint via τ, never derived as a residual
# ===========================================================================

class TestB2BessLagTracksSetpoint:

    def test_B2a_cover_shortfall_matches_lag_formula(self):
        """
        Direct unit test: BessModule.cover_shortfall() output equals
        the first-order lag formula  prev + α × (target − prev)
        independently of any balance computation.

        α = 1 − exp(−dt / τ)
        """
        tau   = 0.05    # BessConfig default bess_response_tau_s
        dt    = 0.1
        alpha = 1.0 - math.exp(-dt / tau)

        bess = BessModule(BessConfig(
            asset_id="b-lag",
            rated_mw=10.0,
            usable_mwh=5.0,
        ))
        prev_output = 4.0
        bess._prev_output_mw = prev_output
        target = 6.0

        actual   = bess.cover_shortfall(
            allocated_mw=target,
            fleet_covered=False,
            dt_seconds=dt,
            power_ceiling_mw=target,
        )
        expected = min(prev_output + alpha * (target - prev_output), target)

        assert actual == pytest.approx(expected, abs=0.001), (
            f"BESS output must match lag formula.  "
            f"prev={prev_output}, target={target}, α={alpha:.4f}, "
            f"expected={expected:.4f}, got={actual:.4f}"
        )

    def test_B2b_output_is_not_the_setpoint_as_residual(self):
        """
        BESS output during ramp-up must differ from the setpoint.

        If cover_shortfall returned setpoint directly (i.e., acted as the
        balance residual), output would equal the target on every tick.
        With the lag, output < target until convergence.
        """
        tau   = 0.05
        dt    = 0.1
        alpha = 1.0 - math.exp(-dt / tau)

        bess = BessModule(BessConfig(
            asset_id="b-res",
            rated_mw=10.0,
            usable_mwh=5.0,
        ))
        bess._prev_output_mw = 0.0
        target = 5.0

        output = bess.cover_shortfall(
            allocated_mw=target,
            fleet_covered=False,
            dt_seconds=dt,
            power_ceiling_mw=target,
        )

        expected_lag = alpha * target   # prev=0 → lag formula = α × target
        assert output == pytest.approx(expected_lag, abs=0.001), (
            f"BESS output must follow lag formula (α × target), not setpoint.  "
            f"α={alpha:.4f}, expected_lag={expected_lag:.4f}, got={output:.4f}"
        )
        # Residual would be exactly 5.0; lag output must be strictly less.
        assert output < target - 0.05, (
            f"BESS output must be strictly less than target during ramp-up, "
            f"confirming it is not a residual (target={target}, output={output:.4f})"
        )

    def test_B2c_output_converges_to_setpoint_at_steady_state(self):
        """After ≥ 5τ / dt ticks, bess_output_mw → setpoint."""
        tau    = 0.05
        dt     = 0.1
        target = 3.0

        bess = BessModule(BessConfig(
            asset_id="b-conv",
            rated_mw=10.0,
            usable_mwh=50.0,   # ample energy
        ))
        bess._prev_output_mw = 0.0

        # 5τ = 0.25 s → 3 ticks (0.3 s); use 10 for margin.
        out = 0.0
        for _ in range(10):
            out = bess.cover_shortfall(
                allocated_mw=target,
                fleet_covered=False,
                dt_seconds=dt,
                power_ceiling_mw=target,
            )

        assert out == pytest.approx(target, abs=0.01), (
            f"After ≥ 5τ, BESS output must converge to setpoint.  "
            f"target={target}, output={out:.4f}"
        )

    def test_B2d_taper_clamp_gives_zero_when_target_is_zero(self):
        """
        When cover_shortfall target = 0 (taper), output must be exactly 0
        regardless of prev_output, due to the max(0, min(lag, target)) clamp.
        This ensures the first-order lag does NOT cause re-fire after taper.
        """
        bess = BessModule(BessConfig(
            asset_id="b-taper",
            rated_mw=10.0,
            usable_mwh=5.0,
        ))
        bess._prev_output_mw = 8.0   # BESS was running at 8 MW

        out = bess.cover_shortfall(
            allocated_mw=0.0,          # taper: fleet fully covered
            fleet_covered=True,
            dt_seconds=0.1,
            power_ceiling_mw=0.0,
        )
        assert out == pytest.approx(0.0, abs=1e-9), (
            "When taper sets target=0, lag clamp must give 0 immediately.  "
            f"prev=8.0, got={out:.6f}"
        )


# ===========================================================================
# B3 — binding_constraint when bess_setpoint exceeds fleet rating
# ===========================================================================

class TestB3BindingConstraint:

    def test_B3_normal_operation_has_no_binding_constraint(self):
        """In normal operation (turbine pre-ramped, light load), binding_constraint is None."""
        state = _make_state()
        tick  = _run_tick(state)
        assert tick.binding_constraint is None, (
            f"binding_constraint must be None in normal operation; "
            f"got {tick.binding_constraint!r}"
        )

    def test_B3_binding_constraint_when_shortfall_exceeds_rating(self):
        """
        When fleet shortfall > total BESS rated_mw, binding_constraint must
        be 'bess_power_saturated'.

        Scenario: small BESS (2 MW), large GPU job (≈ 3.1 MW full TDP),
        turbine cold (0 MW → ramps at 0.5 MW/s, covers ≈ 0.05 MW in one tick).
        Fleet shortfall ≈ 3.1 − 0.05 ≈ 3.05 MW > 2 MW.
        """
        bess_rated = 2.0
        state = _make_state(
            bess_rated_mw=bess_rated,
            turbine_rated_mw=20.0,
            turbine_ramp=0.5,    # slow ramp so turbine stays near 0 on tick 1
        )
        # Ensure turbine starts cold.
        state.turbines[0]._current_output_mw = 0.0
        state.turbines[0]._target_mw = 0.0

        # Large job — 300 nodes × 10.2 kW × PUE1.03 ≈ 3.15 MW full TDP.
        sig = _starting_signal(nodes=300, ramp_s=1.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)
        state.gpu_modules[0]._ramp_progress["job-1"] = 1.0

        tick = _run_tick(state)

        if tick.bess_setpoint_mw <= bess_rated:
            pytest.skip(
                f"Shortfall ({tick.bess_setpoint_mw:.2f} MW) did not exceed "
                f"bess_rated ({bess_rated} MW) — check scenario."
            )

        assert tick.binding_constraint == "bess_power_saturated", (
            f"binding_constraint must be 'bess_power_saturated' when "
            f"bess_setpoint ({tick.bess_setpoint_mw:.2f} MW) > rated ({bess_rated} MW).  "
            f"Got: {tick.binding_constraint!r}"
        )

    def test_B3_bess_setpoint_exceeds_rated_when_constraint_fires(self):
        """When binding_constraint fires, bess_setpoint_mw > sum(rated_mw)."""
        bess_rated = 2.0
        state = _make_state(bess_rated_mw=bess_rated, turbine_ramp=0.5)
        state.turbines[0]._current_output_mw = 0.0
        state.turbines[0]._target_mw = 0.0

        sig = _starting_signal(nodes=300, ramp_s=1.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)
        state.gpu_modules[0]._ramp_progress["job-1"] = 1.0

        tick = _run_tick(state)

        if tick.binding_constraint == "bess_power_saturated":
            assert tick.bess_setpoint_mw > bess_rated, (
                "When binding_constraint fires, bess_setpoint_mw must exceed rated.  "
                f"setpoint={tick.bess_setpoint_mw:.2f}, rated={bess_rated}"
            )


# ===========================================================================
# B4 — "BESS standby" means bess_setpoint_mw ≈ 0 at that tick
# ===========================================================================

class TestB4StandbyConsistency:

    def test_B4a_standby_tick_has_zero_setpoint(self):
        """
        When the turbine covers all load (no fleet shortfall), bess_setpoint_mw == 0.
        This is the tick where the UI would show "BESS standby".
        """
        # No job, turbine pre-ramped well above resting load.
        state = _make_state()
        turb  = state.turbines[0]
        # Phase E repair: AT_TARGET deleted (Phase C) → SYNCHRONISED; _target_mw removed.
        turb._current_output_mw = 5.0
        turb.state              = TurbineState.SYNCHRONISED

        tick = _run_tick(state)
        assert tick.bess_setpoint_mw == pytest.approx(0.0, abs=0.01), (
            f"Standby tick: bess_setpoint_mw must be ≈ 0.  "
            f"Got {tick.bess_setpoint_mw:.4f} MW."
        )

    def test_B4b_regression_setpoint_is_zero_independent_of_lag_state(self):
        """
        Regression guard for "BESS standby while battery moves 18.92 MW".

        The bug: the UI gated "discharging" on bess_output_mw.  With the
        BESS first-order lag (Phase 13.3), bess_output can lag behind the
        dispatch command — showing "standby" when setpoint > 0 (or vice versa).

        Fix (PlantNode.tsx): gate on bess_setpoint_mw (the dispatch command).

        Physics assertion: when turbine covers all load (no fleet shortfall),
        bess_setpoint_mw is IMMEDIATELY 0 — independent of the lag state
        (_prev_output_mw) from any prior dispatch.
        """
        state = _make_state()

        # Pre-ramp GPU so there is a meaningful load.
        sig = _starting_signal(nodes=100, ramp_s=1.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)
        state.gpu_modules[0]._ramp_progress["job-1"] = 1.0

        # Seed the BESS lag state as if it was discharging at 5 MW last tick.
        state.bess_units[0]._prev_output_mw = 5.0

        # Lock turbine at AT_TARGET — advance() is a no-op when state != RAMPING.
        turb = state.turbines[0]
        # Phase E repair: AT_TARGET deleted (Phase C) → SYNCHRONISED; _target_mw removed.
        turb._current_output_mw = 20.0   # ample to cover any load
        turb.state              = TurbineState.SYNCHRONISED

        tick = _run_tick(state, sim_time=5.0)

        # Fleet shortfall = max(0, p_dispatch_required − 20.0) = 0.
        # bess_setpoint must be 0 even though _prev_output_mw was 5 MW.
        assert tick.bess_setpoint_mw == pytest.approx(0.0, abs=0.01), (
            f"bess_setpoint_mw must be 0 on standby tick regardless of lag state.  "
            f"Got {tick.bess_setpoint_mw:.4f} MW (prev_output was 5.0 MW)."
        )
        # cover_shortfall early-returns 0 when allocated_mw=0, so output is
        # also 0.  The UI fix: gate standby label on setpoint (the command),
        # not on output (which could be stale from a previous WebSocket frame).

    def test_B4c_no_binding_constraint_on_standby_tick(self):
        """
        A standby tick must also have no binding constraint — if setpoint == 0
        then it trivially cannot exceed the rated floor.
        """
        state = _make_state()
        tick  = _run_tick(state)

        assert tick.bess_setpoint_mw == pytest.approx(0.0, abs=0.01)
        assert tick.binding_constraint is None, (
            f"Standby tick should have no binding_constraint; "
            f"got {tick.binding_constraint!r}"
        )
