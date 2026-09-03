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
    ThermalState,
    TurbineConfig,
)
from api.routes.scenarios import _SEEDED
from runtime.scenario_factory import build_run_context_from_spec
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

        Phase E closeout Item 2: default changed from 0.0 (disabled sentinel)
        to 0.40 (CHOSEN catalogue value, read via _sp.value("p_min_stable_frac")).
        The enable switch is now structural (p_min_stable_frac > 0 → MSL floor active),
        not a 0.0-sentinel.  Scenarios needing no MSL floor must pass 0.0 explicitly.
        """
        cfg_default = TurbineConfig(asset_id="t0")
        assert cfg_default.p_min_stable_frac == pytest.approx(0.40), (
            f"p_min_stable_frac default must be 0.40 (CHOSEN catalogue value).  "
            f"Got {cfg_default.p_min_stable_frac}"
        )
        cfg_45 = TurbineConfig(asset_id="t1", p_min_stable_frac=0.45)
        assert cfg_45.p_min_stable_frac == pytest.approx(0.45), (
            f"p_min_stable_frac must accept 0.45.  Got {cfg_45.p_min_stable_frac}"
        )

    @pytest.mark.xfail(
        reason=(
            "Phase E Item 4 report — stage_target() deleted in Phase C; "
            "MSL floor enforcement belongs in Phase E loading policy (Item 7). "
            "Old: stage_target(2.0) clamped _target_mw to p_min_stable. "
            "New: apply_loading() enforces MSL floor (Phase E) — not yet implemented. "
            "Why: Phase C removed the RAMPING state machine; explicit staging replaced "
            "by rate-limited setpoint tracking in apply_loading()."
        ),
        strict=True,
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

    @pytest.mark.xfail(
        reason=(
            "Phase E Item 4 report — stage_target() deleted in Phase C. "
            "See test_R4_positive_target_below_floor_clamped_up for full rationale."
        ),
        strict=True,
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

    @pytest.mark.xfail(
        reason=(
            "Phase E Item 4 report — stage_target() deleted in Phase C. "
            "See test_R4_positive_target_below_floor_clamped_up for full rationale."
        ),
        strict=True,
    )
    def test_R4_exactly_at_floor_accepted(self):
        """A target exactly equal to p_min_stable must be accepted unchanged."""
        t = TurbineModule(TurbineConfig(asset_id="t0", rated_mw=10.0,
                                        p_min_stable_frac=0.45))
        t.stage_target(4.5, sim_time=0.0)
        assert t._target_mw == pytest.approx(4.5, abs=1e-9)

    @pytest.mark.xfail(
        reason=(
            "Phase E Item 4 report — stage_target() and advance() both deleted in "
            "Phase C; RAMPING state deleted.  MSL floor enforcement and setpoint "
            "tracking belong in Phase E loading policy.  "
            "See test_R4_positive_target_below_floor_clamped_up for full rationale."
        ),
        strict=True,
    )
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
        """TurbineConfig carries t_min_run_s.

        Phase E closeout Item 1: default changed from 0.0 (disable-sentinel) to
        1800.0 s (CHOSEN catalogue value, read via _sp.value("t_min_run_s")).
        The R5 enable switch is now min_run_enabled (True by default).
        A test needing the constraint off must set min_run_enabled=False explicitly.
        """
        assert TurbineConfig(asset_id="t0").t_min_run_s == pytest.approx(1800.0)

    @pytest.mark.xfail(
        reason=(
            "Phase E Item 4 report — stage_target() deleted in Phase C; "
            "t_min_run enforcement belongs in Phase E stop sequencing (Item 8). "
            "Old: stage_target(0.0, sim_time=50.0) deferred stop, held at p_min_stable. "
            "New: command_stop() will enforce t_min_run; not yet implemented. "
            "Why: Phase C replaced RAMPING/AT_TARGET with SYNCHRONISED; "
            "the stop-deferral logic must be rebuilt in Phase E."
        ),
        strict=True,
    )
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

    @pytest.mark.xfail(
        reason=(
            "Phase E Item 4 report — stage_target() deleted in Phase C. "
            "See test_R5_stop_before_min_run_holds_at_p_min_stable for full rationale."
        ),
        strict=True,
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

    @pytest.mark.xfail(
        reason=(
            "Phase E Item 4 report — stage_target() deleted in Phase C. "
            "_run_start_s is now set by command_start() (Phase E); not yet wired. "
            "See test_R5_stop_before_min_run_holds_at_p_min_stable for full rationale."
        ),
        strict=True,
    )
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
        """TurbineConfig carries t_min_down_s.

        Phase E closeout Item 1: default changed from 0.0 (disable-sentinel) to
        900.0 s (CHOSEN catalogue value, read via _sp.value("t_min_down_s")).
        The R6 enable switch is now min_down_enabled (True by default).
        A test needing the constraint off must set min_down_enabled=False explicitly.
        """
        assert TurbineConfig(asset_id="t0").t_min_down_s == pytest.approx(900.0)

    def test_R6_gt_mode_field_default(self):
        """TurbineConfig carries gt_mode, default 'frame'."""
        assert TurbineConfig(asset_id="t0").gt_mode == "frame"

    def test_R6_gt_mode_aero_accepted(self):
        """gt_mode='aero' must be accepted without error."""
        cfg = TurbineConfig(asset_id="t1", gt_mode="aero")
        assert cfg.gt_mode == "aero"

    @pytest.mark.xfail(
        reason=(
            "Phase E Item 4 report — stage_target() deleted in Phase C; "
            "t_min_down enforcement belongs in Phase E stop sequencing (Item 8). "
            "Old: stage_target(8.0, sim_time=500.0) was dropped inside cooling window. "
            "New: command_start() / command_stop() will enforce t_min_down; "
            "not yet implemented. "
            "Why: Phase C removed RAMPING state; cooling-window guard must be rebuilt "
            "in Phase E command_start()."
        ),
        strict=True,
    )
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

    @pytest.mark.xfail(
        reason=(
            "Phase E Item 4 report — stage_target() deleted (Phase C); "
            "TurbineState.RAMPING deleted (Phase C). "
            "Old: stage_target after cooling window → state == RAMPING. "
            "New: command_start() after cooling window → state == STARTING (Phase E). "
            "See test_R6_restart_inside_cooling_window_dropped for full rationale."
        ),
        strict=True,
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

    @pytest.mark.xfail(
        reason=(
            "Phase E Item 4 report — stage_target() deleted (Phase C). "
            "See test_R6_restart_inside_cooling_window_dropped for full rationale."
        ),
        strict=True,
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


# ===========================================================================
# Demo-20mw IP claim 4 — R5 prevents OFFLINE during checkpoint valley
# ===========================================================================

class TestDemo20mwIpClaim4:
    """
    IP claim 4 regression guard: the demo-20mw scenario sets
    p_min_stable_frac=0.45, t_min_run_s=1800, t_min_down_s=900 on its
    non-hot-standby turbines.  A valley dispatch command issued at t=120 s
    (the demo scenario's turbine-1 trip time, well inside the 1800 s
    minimum run window) must be blocked by R5 — the unit stays SYNCHRONISED
    and never transitions to OFFLINE.

    Uses command_start() / command_stop() — the Phase E API — not the
    deleted stage_target().
    """

    @staticmethod
    def _make_demo_turbine() -> TurbineModule:
        """Build a TurbineModule with the demo-20mw non-hot-standby config.

        Uses a HOT thermal start (hot_start_s=1.0) so the test advances
        to SYNCHRONISED in one tick without a 900 s cold-start loop.
        The R4–R6 constraints (p_min_stable_frac, t_min_run_s, t_min_down_s,
        min_run_enabled) match the demo scenario exactly.
        """
        cfg = TurbineConfig(
            asset_id="demo-gt",
            rated_mw=7.0,
            p_min_stable_frac=0.45,
            t_min_run_s=1800.0,
            t_min_down_s=900.0,
            min_run_enabled=True,
            min_down_enabled=True,
            initial_thermal_state=ThermalState.HOT,
            hot_start_s=1.0,   # fast start so test completes in one advance step
        )
        return TurbineModule(cfg)

    def test_demo20mw_r5_stop_before_min_run_deferred(self):
        """
        command_stop() at t=120 s (the demo trip time, inside t_min_run_s=1800 s)
        must be deferred: returns a non-None block reason and the unit remains
        SYNCHRONISED (not OFFLINE).

        This is the live exercise of IP claim 4: the loading layer calls
        command_stop() when a valley dispatch would take the turbine below its
        MSL floor, and R5 holds the unit on-bus rather than cycling it off.
        """
        t = self._make_demo_turbine()

        # Bring unit on-bus via HOT start
        t.command_start(sim_time=0.0)
        assert t.state == TurbineState.STARTING

        # Advance past the 1 s hot-start countdown → SYNCHRONISED
        t.advance(sim_time=0.0, dt_seconds=2.0)
        assert t.state == TurbineState.SYNCHRONISED, (
            f"Unit must reach SYNCHRONISED after hot start.  State: {t.state}"
        )

        # Attempt a controlled stop at t=120 s (demo trip time; < 1800 s min run)
        block_reason = t.command_stop(sim_time=120.0)

        assert block_reason is not None, (
            "R5 must defer the stop command at t=120 s (< t_min_run_s=1800 s).  "
            "command_stop() returned None, meaning the stop was accepted — "
            "IP claim 4 is not being exercised."
        )
        assert "r5_min_run_not_elapsed" in block_reason, (
            f"Block reason must identify R5.  Got: {block_reason!r}"
        )
        assert t.state == TurbineState.SYNCHRONISED, (
            f"Turbine must stay SYNCHRONISED when R5 defers the stop.  "
            f"Got state={t.state}"
        )
        assert t.state != TurbineState.OFFLINE, (
            "Turbine must not go OFFLINE during a checkpoint valley when "
            "t_min_run_s has not elapsed — IP claim 4 violated."
        )

    def test_demo20mw_r5_stop_after_min_run_accepted(self):
        """
        command_stop() after t_min_run_s=1800 s has elapsed must be accepted
        (returns None) and unit transitions to UNLOADING — confirming R5 only
        blocks premature stops and does not permanently prevent decommit.
        """
        t = self._make_demo_turbine()

        t.command_start(sim_time=0.0)
        t.advance(sim_time=0.0, dt_seconds=2.0)
        assert t.state == TurbineState.SYNCHRONISED

        # Stop well after the minimum run window
        block_reason = t.command_stop(sim_time=1900.0)

        assert block_reason is None, (
            f"Stop at t=1900 s (> t_min_run_s=1800 s) must be accepted.  "
            f"Got block_reason={block_reason!r}"
        )
        assert t.state == TurbineState.UNLOADING, (
            f"Unit must be UNLOADING after an accepted stop.  Got state={t.state}"
        )


# ===========================================================================
# Demo-20mw spec-path — factory pre-sync sets _run_start_s so R5 applies live
# ===========================================================================

class TestDemo20mwSpecPathR5:
    """
    Spec-path regression guard: build_run_context_from_spec must set
    _run_start_s = 0.0 on every pre-synchronised non-hot-standby turbine so
    that command_stop() enforces R5 (t_min_run_s=1800 s) on the live path.

    Background: build_run_context_from_spec pre-synchronizes non-hot-standby
    turbines by setting state=SYNCHRONISED directly (bypassing command_start +
    advance).  TurbineModule initialises _run_start_s to NaN, and command_stop()
    only enforces R5 when _run_start_s is non-NaN
    (`not math.isnan(self._run_start_s)`).  Without the factory fix, the NaN
    sentinel allows every decommit command — making IP claim 4 inoperative on
    the live spec path even though the config carries t_min_run_s=1800.

    These tests verify the factory fix and the end-to-end spec-path R5 contract.
    """

    @staticmethod
    def _get_demo_20mw_spec_dict() -> dict:
        """Return the demo-20mw ScenarioSpec as a plain dict (JSON-round-trip safe)."""
        spec_pairs = {sid: ss for sid, ss in _SEEDED}
        spec = spec_pairs.get("demo-20mw")
        assert spec is not None, "demo-20mw not found in _SEEDED; check api/routes/scenarios.py"
        return spec.model_dump()

    def test_spec_path_pre_sync_sets_run_start_s(self):
        """
        build_run_context_from_spec must set _run_start_s = 0.0 on every
        non-hot-standby turbine so R5 enforcement is active from t=0.

        Without this fix the factory left _run_start_s = NaN, which bypasses
        the `not math.isnan(self._run_start_s)` guard in command_stop() and
        allows any decommit regardless of how long the unit has been running.
        """
        spec_dict = self._get_demo_20mw_spec_dict()
        ctx = build_run_context_from_spec("test-ip4-factory", spec_dict)

        online_turbines = [
            t for t in ctx.sim_state.turbines
            if not t.config.hot_standby
        ]
        assert online_turbines, "demo-20mw must have at least one non-hot-standby turbine"

        for turb in online_turbines:
            assert not math.isnan(turb._run_start_s), (
                f"Turbine {turb.config.asset_id!r}: _run_start_s must not be NaN "
                "after factory pre-synchronisation.  NaN bypasses R5 in command_stop()."
            )
            assert turb._run_start_s == pytest.approx(0.0, abs=1e-9), (
                f"Turbine {turb.config.asset_id!r}: _run_start_s must be 0.0 "
                f"(pre-synchronised at run start).  Got {turb._run_start_s!r}"
            )

    def test_spec_path_r5_blocks_stop_before_min_run(self):
        """
        On the spec path, command_stop() at t=120 s (the demo turbine-1 trip
        time, inside t_min_run_s=1800 s) must be blocked by R5 and return a
        non-None block reason.

        This is the live-path IP claim 4 exercise: the commitment engine issues
        command_stop() on a non-hot-standby turbine early in the run, and R5
        defers it.  Before the factory fix (_run_start_s was NaN), the stop was
        silently accepted and the turbine entered UNLOADING at t=300 s.
        """
        spec_dict = self._get_demo_20mw_spec_dict()
        ctx = build_run_context_from_spec("test-ip4-r5", spec_dict)

        # Pick the first non-hot-standby turbine (matches turbine-0 in demo-20mw)
        online = [t for t in ctx.sim_state.turbines if not t.config.hot_standby]
        assert online, "demo-20mw must have at least one non-hot-standby turbine"
        target = online[0]

        assert target.state == TurbineState.SYNCHRONISED, (
            f"Factory must pre-synchronise non-hot-standby turbines.  "
            f"Got state={target.state}"
        )
        assert target.config.min_run_enabled, (
            "demo-20mw turbines must have min_run_enabled=True (R5 active)"
        )
        assert target.config.t_min_run_s == pytest.approx(1800.0, abs=1.0), (
            f"demo-20mw turbines must have t_min_run_s=1800 s.  "
            f"Got {target.config.t_min_run_s}"
        )
        assert target.config.p_min_stable_frac == pytest.approx(0.45, abs=1e-9), (
            f"demo-20mw non-hot-standby turbines must have p_min_stable_frac=0.45.  "
            f"Got {target.config.p_min_stable_frac}"
        )

        # Issue stop at t=120 s — should be blocked by R5 (elapsed 120 < 1800 s)
        block_reason = target.command_stop(sim_time=120.0)

        assert block_reason is not None, (
            "R5 must block command_stop() at t=120 s on the spec path.  "
            "command_stop() returned None — the fix to set _run_start_s=0.0 in "
            "build_run_context_from_spec is not in effect.  IP claim 4 is not "
            "being exercised on the live demo-20mw path."
        )
        assert "r5_min_run_not_elapsed" in block_reason, (
            f"Block reason must identify R5.  Got: {block_reason!r}"
        )
        assert target.state == TurbineState.SYNCHRONISED, (
            f"Turbine must remain SYNCHRONISED after R5 defers the stop.  "
            f"Got state={target.state}"
        )
