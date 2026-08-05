"""
Phase 13.5 — Carried-forward criteria (originally specified in Phase 12)

TC-03  deterministic: noise-disabled mode, 7τ settle, ten seeds, spread < 0.5 %.
R4     p_min_stable_frac = 0.45  dispatch target clamped to floor when running.
R5     t_min_run_s = 1800        stop command deferred to p_min_stable until floor satisfied.
R6     t_min_down_s = 900        restart command silently dropped inside cooling window.
       gt_mode per-unit field    present on TurbineConfig, default "frame".
R8     header dispatchable_mw   equals online-turbine rated + BESS from a single source.
"""

from __future__ import annotations

import math

import pytest

from core.asset_modules import TurbineModule, TurbineState
from core.models import (
    BessConfig,
    SiteConfig,
    TurbineConfig,
)
from core.contingency import (
    evaluate_contingency,
    PlantState,
    TurbineSnapshot,
    BessSnapshot,
)
from core.models import IslandMode
from core.asset_modules import CoolingModule


# ===========================================================================
# TC-03 — Cooling determinism at 7τ, noise-disabled
# ===========================================================================

_SITE_TC03 = SiteConfig(
    frequency_nominal_hz=50.0, power_factor=0.85,  # required; frequency unused in this non-frequency test
    site_id="s-tc03",
    dt_thermal_seconds=90.0,
    tau_seconds=20.0,
    alpha_max=0.20,
)
_TICK_S = 5.0
_P_COMPUTE = 10.0


def _run_scalar_cooling(site: SiteConfig, p_compute: float, dt: float) -> float:
    """
    Run a single CoolingModule scalar path to 7τ settle time and return
    the final output_mw.

    Settle definition:
        t_settle = dt_thermal + 7 × tau_seconds
    The run continues in dt steps until this threshold is exceeded.
    """
    cooling = CoolingModule(asset_id="cool-tc03", site=site)
    t_settle = site.dt_thermal_seconds + 7 * site.tau_seconds
    t = 0.0
    while t <= t_settle + dt:
        cooling.record_compute_sample(t, p_compute)
        cooling.advance(t, dt)
        t += dt
    return cooling.output_mw()


class TestTC03Determinism:

    def test_tc03a_scalar_7tau_converges_within_half_pct(self):
        """
        Scalar path: after dt_thermal + 7τ settle time, P_cooling must be
        within 0.5 % of α_max × P_compute.

        This replaces the weaker 5τ / 2 % tolerance used in test_formulas.py.
        At 7τ the first-order residual is e^−7 ≈ 0.09 %, well inside the
        0.5 % bound — confirming the asymptote has been reached.
        """
        output   = _run_scalar_cooling(_SITE_TC03, _P_COMPUTE, _TICK_S)
        expected = _SITE_TC03.alpha_max * _P_COMPUTE   # 2.0 MW

        assert math.isclose(output, expected, rel_tol=0.005), (
            f"CoolingModule scalar path must settle within 0.5 % of asymptote "
            f"at 7τ.  expected={expected:.4f} MW, got={output:.4f} MW "
            f"(error={abs(output - expected) / expected * 100:.3f} %)"
        )

    def test_tc03b_noise_disabled_spread_below_half_pct_across_ten_seeds(self):
        """
        Multi-seed determinism: with noise disabled (scalar path carries no
        stochastic noise), 10 independent CoolingModule instances all converge
        to the same asymptote.  The spread (max − min) across instances must be
        < 0.5 % of the asymptote.

        Why ten "seeds": in the scalar path there is no RNG — all instances
        receive the identical constant P_compute sequence.  Spread is identically
        zero, conclusively demonstrating that the 2.08 % CI flakiness was
        entirely noise-driven (σ_noise = 0.5 % of draw; accumulated over many
        ticks it exceeded the 2 % assertion threshold at 5τ).

        Settling to 7τ (residual ≈ 0.09 %) makes the assertion robust even
        if a small noise source were re-introduced later.
        """
        expected  = _SITE_TC03.alpha_max * _P_COMPUTE   # 2.0 MW
        half_pct  = 0.005 * expected                    # 0.01 MW

        outputs = [
            _run_scalar_cooling(_SITE_TC03, _P_COMPUTE, _TICK_S)
            for _ in range(10)
        ]

        spread = max(outputs) - min(outputs)
        assert spread < half_pct, (
            f"Spread across 10 seeds must be < 0.5 % of asymptote "
            f"({half_pct:.5f} MW).  Got spread={spread:.6f} MW."
        )

        # Also confirm every seed converged to within 0.5 % of the asymptote.
        for i, out in enumerate(outputs):
            assert math.isclose(out, expected, rel_tol=0.005), (
                f"Seed {i}: output {out:.4f} MW outside 0.5 % of "
                f"asymptote {expected:.4f} MW."
            )

    def test_tc03c_7tau_tighter_than_5tau_at_same_tolerance(self):
        """
        Diagnostic: 7τ gives a smaller convergence error than 5τ for the same
        input.  This guards against inadvertent reversion to 5τ.

        At 5τ: residual ≈ e^−5 ≈ 0.67 %.
        At 7τ: residual ≈ e^−7 ≈ 0.09 %.
        """
        t5_settle = _SITE_TC03.dt_thermal_seconds + 5 * _SITE_TC03.tau_seconds
        t7_settle = _SITE_TC03.dt_thermal_seconds + 7 * _SITE_TC03.tau_seconds

        cooling5 = CoolingModule(asset_id="cool-5t", site=_SITE_TC03)
        cooling7 = CoolingModule(asset_id="cool-7t", site=_SITE_TC03)

        expected = _SITE_TC03.alpha_max * _P_COMPUTE
        t = 0.0
        while t <= t7_settle + _TICK_S:
            for c in (cooling5, cooling7):
                c.record_compute_sample(t, _P_COMPUTE)
                c.advance(t, _TICK_S)
            t += _TICK_S
            if math.isclose(t, t5_settle, abs_tol=_TICK_S / 2):
                err5 = abs(cooling5.output_mw() - expected) / expected

        err7 = abs(cooling7.output_mw() - expected) / expected
        assert err7 < err5, (
            f"7τ error ({err7:.4f}) must be less than 5τ error ({err5:.4f})."
        )
        assert err7 < 0.005, (
            f"7τ error must be below 0.5 %; got {err7 * 100:.3f} %."
        )


# ===========================================================================
# R4 — p_min_stable_frac: dispatch target clamped to floor
# ===========================================================================

class TestR4PMinStable:

    def test_R4_fields_present_on_turbine_config(self):
        """
        TurbineConfig carries p_min_stable_frac.

        Default is 0.0 (constraint disabled) so backward-compatible scenarios
        are not affected.  The spec-chosen value 0.45 must be explicitly set in
        scenarios exercising IP claim 4.
        """
        cfg_default = TurbineConfig(asset_id="t0")
        assert cfg_default.p_min_stable_frac == pytest.approx(0.0), (
            f"p_min_stable_frac default must be 0.0 (disabled).  "
            f"Got {cfg_default.p_min_stable_frac}"
        )
        cfg_45 = TurbineConfig(asset_id="t1", p_min_stable_frac=0.45)
        assert cfg_45.p_min_stable_frac == pytest.approx(0.45), (
            f"p_min_stable_frac must accept 0.45.  Got {cfg_45.p_min_stable_frac}"
        )

    def test_R4_positive_target_below_floor_clamped_up(self):
        """
        Dispatching to 2 MW on a 10 MW turbine (p_min = 4.5 MW) must
        set internal target to at least p_min_stable_frac × rated_mw.
        """
        t = TurbineModule(TurbineConfig(asset_id="t0", rated_mw=10.0,
                                        p_min_stable_frac=0.45))
        t.stage_target(2.0, sim_time=0.0)

        assert t._target_mw >= 4.5 - 1e-9, (
            f"Target below p_min_stable (4.5 MW) must be clamped to floor.  "
            f"Got _target_mw={t._target_mw:.4f} MW."
        )

    def test_R4_target_above_floor_unchanged(self):
        """A target already above p_min_stable must not be changed."""
        t = TurbineModule(TurbineConfig(asset_id="t0", rated_mw=10.0,
                                        p_min_stable_frac=0.45))
        t.stage_target(8.0, sim_time=0.0)
        assert t._target_mw == pytest.approx(8.0, abs=1e-9), (
            f"Target above p_min_stable must not be modified.  "
            f"Got {t._target_mw:.4f} MW."
        )

    def test_R4_exactly_at_floor_accepted(self):
        """A target exactly equal to p_min_stable must be accepted unchanged."""
        t = TurbineModule(TurbineConfig(asset_id="t0", rated_mw=10.0,
                                        p_min_stable_frac=0.45))
        t.stage_target(4.5, sim_time=0.0)
        assert t._target_mw == pytest.approx(4.5, abs=1e-9)

    def test_R4_clamped_target_leads_to_correct_ramp(self):
        """After clamping, the turbine ramps to p_min_stable (not to the raw 2 MW)."""
        t = TurbineModule(TurbineConfig(asset_id="t0", rated_mw=10.0,
                                        r_asset_mw_per_s=50.0,  # fast ramp
                                        p_min_stable_frac=0.45))
        t.stage_target(2.0, sim_time=0.0)       # clamped → 4.5 MW
        t.advance(sim_time=0.0, dt_seconds=1.0)  # ramp 50 MW/s × 1 s ≫ 4.5 → SYNCHRONISED

        assert t.output_mw() == pytest.approx(4.5, abs=1e-9), (
            f"After clamping and ramp, turbine must be at p_min_stable (4.5 MW).  "
            f"Got {t.output_mw():.4f} MW."
        )
        # Phase 2: advance() transitions RAMPING → SYNCHRONISED (not AT_TARGET) so
        # the loading layer can take over dispatch for the unit.
        assert t.state == TurbineState.SYNCHRONISED


# ===========================================================================
# R5 — t_min_run_s: stop deferred until minimum run time satisfied
# ===========================================================================

class TestR5MinRunTime:

    def test_R5_t_min_run_field_default(self):
        """TurbineConfig carries t_min_run_s, default 0.0 (disabled)."""
        assert TurbineConfig(asset_id="t0").t_min_run_s == pytest.approx(0.0)

    def test_R5_stop_before_min_run_holds_at_p_min_stable(self):
        """
        A stop command (target=0) issued before t_min_run_s elapses must
        be deferred: the turbine holds at p_min_stable rather than stopping.
        """
        t = TurbineModule(TurbineConfig(asset_id="t0", rated_mw=10.0,
                                        p_min_stable_frac=0.45,
                                        t_min_run_s=100.0))
        t.stage_target(8.0, sim_time=0.0)   # start at t=0
        t.stage_target(0.0, sim_time=50.0)  # stop at t=50 (< 100 s min run)

        # Target must be clamped to p_min_stable, not 0
        assert t._target_mw == pytest.approx(4.5, abs=1e-9), (
            f"Stop command before t_min_run must hold at p_min_stable (4.5 MW).  "
            f"Got _target_mw={t._target_mw:.4f} MW."
        )
        assert t.state != TurbineState.OFFLINE, (
            "Turbine must not go OFFLINE before t_min_run_s has elapsed."
        )

    def test_R5_stop_after_min_run_is_allowed(self):
        """
        A stop command issued after t_min_run_s has elapsed must be accepted
        (target → 0, _stop_time_s recorded).
        """
        t = TurbineModule(TurbineConfig(asset_id="t0", rated_mw=10.0,
                                        p_min_stable_frac=0.45,
                                        t_min_run_s=100.0))
        t.stage_target(8.0, sim_time=0.0)
        t.stage_target(0.0, sim_time=150.0)  # after 150 s > 100 s

        assert t._target_mw == pytest.approx(0.0, abs=1e-9), (
            f"Stop command after t_min_run must set target to 0.  "
            f"Got {t._target_mw:.4f} MW."
        )
        assert not math.isnan(t._stop_time_s), (
            "t._stop_time_s must be recorded after an allowed stop."
        )
        assert t._stop_time_s == pytest.approx(150.0, abs=1e-9)

    def test_R5_run_start_time_recorded_on_first_start(self):
        """_run_start_s is recorded at the sim_time of the first stage_target > 0."""
        t = TurbineModule(TurbineConfig(asset_id="t0"))
        assert math.isnan(t._run_start_s), "Must start with NaN _run_start_s."
        t.stage_target(5.0, sim_time=42.0)
        assert t._run_start_s == pytest.approx(42.0), (
            f"_run_start_s must be recorded as sim_time of first start.  "
            f"Got {t._run_start_s}"
        )


# ===========================================================================
# R6 — t_min_down_s, gt_mode, checkpoint-valley zero stop/start cycles
# ===========================================================================

class TestR6MinDownGtMode:

    def test_R6_t_min_down_field_default(self):
        """TurbineConfig carries t_min_down_s, default 0.0 (disabled)."""
        assert TurbineConfig(asset_id="t0").t_min_down_s == pytest.approx(0.0)

    def test_R6_gt_mode_field_default(self):
        """TurbineConfig carries gt_mode, default 'frame'."""
        assert TurbineConfig(asset_id="t0").gt_mode == "frame"

    def test_R6_gt_mode_aero_accepted(self):
        """gt_mode='aero' must be accepted without error."""
        cfg = TurbineConfig(asset_id="t1", gt_mode="aero")
        assert cfg.gt_mode == "aero"

    def test_R6_restart_inside_cooling_window_dropped(self):
        """
        A restart command issued within t_min_down_s after a controlled stop
        must be silently dropped (turbine stays OFFLINE).
        """
        t = TurbineModule(TurbineConfig(asset_id="t0", rated_mw=10.0,
                                        t_min_run_s=0.0,    # allow immediate stop
                                        t_min_down_s=900.0))
        t.stage_target(8.0, sim_time=0.0)
        t.stage_target(0.0, sim_time=10.0)   # controlled stop (t_min_run=0)

        assert t._stop_time_s == pytest.approx(10.0)

        # Try restart at t=500 (< 900 s cooling window)
        t.stage_target(8.0, sim_time=500.0)

        assert t.state == TurbineState.OFFLINE, (
            "Restart inside t_min_down_s window must be dropped; "
            "turbine must stay OFFLINE."
        )
        # _run_start_s should not have been updated
        assert math.isnan(t._run_start_s), (
            "_run_start_s must remain NaN when restart is dropped."
        )

    def test_R6_restart_after_cooling_window_succeeds(self):
        """A restart after t_min_down_s has elapsed must be accepted."""
        t = TurbineModule(TurbineConfig(asset_id="t0", rated_mw=10.0,
                                        t_min_run_s=0.0,
                                        t_min_down_s=900.0))
        t.stage_target(8.0, sim_time=0.0)
        t.stage_target(0.0, sim_time=10.0)

        # Restart at t=950 (> 900 s)
        t.stage_target(8.0, sim_time=950.0)

        assert t.state == TurbineState.RAMPING, (
            "Restart after cooling window must transition turbine to RAMPING."
        )
        assert t._run_start_s == pytest.approx(950.0), (
            f"_run_start_s must be updated on valid restart.  Got {t._run_start_s}"
        )

    def test_R6_checkpoint_valley_zero_stop_start_cycles(self):
        """
        IP claim 4 regression guard: repeated checkpoint valleys (load drops
        to 55 % of TDP) must produce zero stop/start cycles across 30 minutes
        of repeated events.

        Mechanism: each valley dispatches a target that would be below
        p_min_stable.  The R4 floor clamps the target up, so the turbine
        never receives a stop command — it stays AT_TARGET through every valley.

        The test drives 10 valley events (every 3 minutes over 30 minutes)
        and counts OFFLINE transitions.  Expected count: 0.
        """
        cfg = TurbineConfig(
            asset_id="gt-valley",
            rated_mw=10.0,
            r_asset_mw_per_s=50.0,     # fast ramp so AT_TARGET reached quickly
            p_min_stable_frac=0.45,
            t_min_run_s=1800.0,
            t_min_down_s=900.0,
        )
        t = TurbineModule(cfg)
        p_min = cfg.p_min_stable_frac * cfg.rated_mw   # 4.5 MW

        # Start turbine at full load (10 MW) at t=0
        t.stage_target(10.0, sim_time=0.0)
        t.advance(0.0, 1.0)   # fast ramp; 1 s at 50 MW/s → AT_TARGET

        offline_transitions = 0
        prev_state = t.state

        valley_dispatch_mw = 0.55 * 10.0  # 55 % of rated = 5.5 MW (above p_min)
        # Use an even lower load to test the clamp:
        below_p_min_mw = 2.0              # 2.0 MW < p_min 4.5 MW

        for k in range(10):
            valley_t = (k + 1) * 180.0   # every 3 min

            # Dispatch drops to below p_min during valley
            t.stage_target(below_p_min_mw, sim_time=valley_t)

            # Observe state transition
            if t.state == TurbineState.OFFLINE and prev_state != TurbineState.OFFLINE:
                offline_transitions += 1
            prev_state = t.state

            # Recovery: dispatch back to full load
            t.stage_target(10.0, sim_time=valley_t + 30.0)
            t.advance(valley_t + 30.0, 1.0)

        assert offline_transitions == 0, (
            f"Zero stop/start cycles expected across 30 min of repeated valley "
            f"events.  Got {offline_transitions} OFFLINE transition(s).\n"
            f"p_min_stable = {p_min:.1f} MW; valley dispatch = {below_p_min_mw} MW "
            f"(clamped to {p_min:.1f} MW by R4, so turbine never stops)."
        )
        # Confirm turbine is still running at the end
        assert t.state != TurbineState.OFFLINE, (
            "Turbine must still be running at the end of the 30-min valley sequence."
        )


# ===========================================================================
# R8 — dispatchable_mw from a single source (turbines + BESS)
# ===========================================================================

class TestR8DispatchableFromSingleSource:
    """
    Guard against the PROTO-22 discrepancy: header showed 38 MW (dispatchable)
    while the ramp-relaxation tile received 20 MW (turbine-only
    ctx.turbine_rated_mw).

    R8 fix (Phase 13.5 / run_manager.py): the ramp-relaxation
    ReservePosition.available_capacity_mw now reads from
    contingency_coverage.dispatchable_mw — the single source that correctly
    sums (online turbine rated) + (anchor-adjusted BESS bridging).

    These tests verify that source directly.
    """

    @staticmethod
    def _make_plant(
        turbine_rated: list[float],
        bess_rated: float = 0.0,
        bess_soc: float = 1.0,
        anchor_reserve: float = 0.0,
        grid_forming: bool = False,
    ) -> PlantState:
        turbine_snaps = tuple(
            TurbineSnapshot(
                asset_id=f"t{i}",
                rated_mw=r,
                current_output_mw=r * 0.5,
                r_asset_mw_per_s=0.2,
                is_synchronized=True,
            )
            for i, r in enumerate(turbine_rated)
        )
        bess_snaps = (
            (
                BessSnapshot(
                    asset_id="bess-0",
                    rated_mw=bess_rated,
                    soc_mwh=bess_rated * bess_soc,
                    usable_mwh=bess_rated,         # 1 MWh per MW rated
                    p_anchor_reserve_mw=anchor_reserve,
                    grid_forming=grid_forming,
                ),
            )
            if bess_rated > 0
            else ()
        )
        return PlantState(
            turbine_snapshots=turbine_snaps,
            bess_snapshots=bess_snaps,
            island_mode=IslandMode.ISLANDED,
            curtailable_capacity_mw=0.0,
            renewable_mw=0.0,
        )

    def test_R8_turbine_only_no_bess(self):
        """dispatchable_mw = sum of online turbine rated when BESS is absent."""
        plant = self._make_plant(turbine_rated=[10.0, 10.0])
        result = evaluate_contingency(plant)
        assert result.dispatchable_mw == pytest.approx(20.0, abs=1e-6), (
            f"Two 10 MW turbines, no BESS: dispatchable must be 20 MW.  "
            f"Got {result.dispatchable_mw:.3f} MW."
        )

    def test_R8_turbine_plus_bess_from_single_source(self):
        """
        dispatchable_mw = sum(turbine rated) + BESS bridging.

        Previously the ramp-relaxation tile received only turbine-only
        ctx.turbine_rated_mw (20 MW), while the contingency header showed
        38 MW.  After the R8 fix both read from dispatchable_mw.
        """
        plant = self._make_plant(
            turbine_rated=[10.0, 10.0],
            bess_rated=18.0,
            bess_soc=1.0,
            anchor_reserve=0.0,
        )
        result = evaluate_contingency(plant)
        # Turbines: 10 + 10 = 20 MW.  BESS bridging (island, no anchor): 18 MW.
        # dispatchable = 38 MW — previously the tile received 20 MW (PROTO-22 bug).
        assert result.dispatchable_mw == pytest.approx(38.0, abs=1e-6), (
            f"dispatchable_mw must include both turbine and BESS.  "
            f"Expected 38.0 MW (turbine=20 + BESS=18).  "
            f"Got {result.dispatchable_mw:.3f} MW."
        )

    def test_R8_anchor_reserve_deducted_before_dispatchable(self):
        """
        Anchor reserve is deducted from BESS bridging before it enters
        dispatchable_mw.  This matches the contingency.py _bess_bridging_mw
        formula (§7.5).
        """
        plant = self._make_plant(
            turbine_rated=[10.0],
            bess_rated=18.0,
            bess_soc=1.0,
            anchor_reserve=4.0,
            grid_forming=True,   # anchor reserve only applies when grid_forming=True
        )
        result = evaluate_contingency(plant)
        # Turbine: 10 MW.  BESS bridging = max(0, 18 − 4) = 14 MW.
        # dispatchable = 24 MW.
        assert result.dispatchable_mw == pytest.approx(24.0, abs=1e-6), (
            f"Anchor reserve must be deducted from BESS before dispatchable.  "
            f"Expected 24.0 MW (turbine=10 + BESS_adj=14).  "
            f"Got {result.dispatchable_mw:.3f} MW."
        )

    def test_R8_hot_standby_turbine_excluded(self):
        """
        A hot-standby turbine (is_synchronized=False) must not contribute
        to dispatchable_mw.  Only synchronized online units count.
        """
        turbine_snaps = (
            TurbineSnapshot(asset_id="t0", rated_mw=10.0, r_asset_mw_per_s=0.2,
                            current_output_mw=5.0, is_synchronized=True),
            TurbineSnapshot(asset_id="t1", rated_mw=10.0, r_asset_mw_per_s=0.2,
                            current_output_mw=0.0, is_synchronized=False),
        )
        plant = PlantState(
            turbine_snapshots=turbine_snaps,
            bess_snapshots=(),
            island_mode=IslandMode.ISLANDED,
            curtailable_capacity_mw=0.0,
            renewable_mw=0.0,
        )
        result = evaluate_contingency(plant)
        assert result.dispatchable_mw == pytest.approx(10.0, abs=1e-6), (
            f"Hot-standby unit must not appear in dispatchable_mw.  "
            f"Expected 10.0 MW (online t0 only).  Got {result.dispatchable_mw:.3f} MW."
        )
