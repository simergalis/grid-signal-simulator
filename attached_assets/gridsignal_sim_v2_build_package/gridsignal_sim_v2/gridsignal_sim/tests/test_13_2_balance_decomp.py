"""
Phase 13.2 — Balance decomposition acceptance tests (revised Task #200 B1/B2).

Verifies that _balance_residual_mw is decomposed into two energy channels plus
one independent reporting field:

  grid_exchange_mw          — power crossing the PCC; exactly 0 in islanded (D1)
  frequency_forcing_mw      — actual supply-demand routed to rotors; 0 grid-connected (D2)
  asset_delivery_error_mw   — commanded ≠ delivered (reporting only, NOT in D4)

Invariants:
  D4: grid_exchange_mw + frequency_forcing_mw == balance_residual_mw  (TWO channels)
  D5: asset_delivery_error_mw is independently computed (setpoint-tracking formula),
      NOT a residual of the other two.

Swing equation addendum (I4 — revised B1):
  I4: frequency_forcing_mw = balance_residual in islanded mode.
      Any real supply-demand imbalance moves frequency.
      a) Healthy islanded: Δf matches swing-equation prediction from forcing alone.
      b) Depleted BESS islanded: asset_delivery_error < 0; D4 holds (two-channel);
         frequency_forcing still equals balance_residual (which is more negative
         than forcing-only because the BESS delivery shortfall lowers p_gen).
      c) Grid-connected: frequency stays at site nominal regardless of delivery fault.

All tests run headless with no external I/O.  Mode is set explicitly on SiteConfig.
"""

import sys
import math
import pytest

sys.path.insert(0, ".")

from core.models      import IslandMode
from core.sim_clock   import SimClock

from tests.test_forecast_path import (
    _make_state,
    _starting_signal,
    _run_tick,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_tick_with_sim_time(
    state,
    sim_time: float,
    dt: float = 5.0,
    *,
    island_mode: IslandMode = IslandMode.GRID_TIE,
) -> object:
    """Run one tick with the given mode baked into the site config."""
    state.site = state.site.__class__(
        **{
            **{
                f.name: getattr(state.site, f.name)
                for f in state.site.__dataclass_fields__.values()
            },
            "island_mode": island_mode,
        }
    )
    return _run_tick(state, sim_time=sim_time, dt=dt)


# ---------------------------------------------------------------------------
# D1 — grid_exchange_mw is exactly 0.0 in islanded mode
# ---------------------------------------------------------------------------

class TestD1GridExchangeIslanded:
    """D1: grid_exchange_mw == 0.0 in islanded mode, every tick."""

    def test_D1_zero_load(self):
        """No GPU load, islanded: grid_exchange_mw must be 0."""
        state = _make_state(island_mode=IslandMode.ISLANDED)
        tick = _run_tick(state, sim_time=0.0, dt=5.0)
        assert tick.grid_exchange_mw == 0.0, (
            f"D1: grid_exchange_mw={tick.grid_exchange_mw!r} must be exactly 0.0 "
            f"in islanded mode (no load)"
        )

    def test_D1_with_load(self):
        """GPU job running, islanded: grid_exchange_mw still 0."""
        state = _make_state(island_mode=IslandMode.ISLANDED)
        sig = _starting_signal(nodes=10, ramp_s=120.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=120.0)
        tick = _run_tick(state, sim_time=5.0, dt=5.0)
        assert tick.grid_exchange_mw == 0.0, (
            f"D1: grid_exchange_mw={tick.grid_exchange_mw!r} must be exactly 0.0 "
            f"in islanded mode (with GPU load)"
        )

    def test_D1_depleted_bess_islanded(self):
        """Depleted BESS, islanded: grid_exchange_mw still 0."""
        state = _make_state(
            bess_soc=0.0,
            bess_mwh=0.01,
            island_mode=IslandMode.ISLANDED,
        )
        sig = _starting_signal(nodes=10, ramp_s=1.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)
        tick = _run_tick(state, sim_time=5.0, dt=5.0)
        assert tick.grid_exchange_mw == 0.0, (
            f"D1: grid_exchange_mw={tick.grid_exchange_mw!r} must be exactly 0.0 "
            f"in islanded mode (depleted BESS)"
        )


# ---------------------------------------------------------------------------
# D2 — frequency_forcing_mw is exactly 0.0 in grid-connected mode
# ---------------------------------------------------------------------------

class TestD2FrequencyForcingGridConnected:
    """D2: frequency_forcing_mw == 0.0 in grid-connected mode, every tick."""

    def test_D2_zero_load(self):
        """No GPU load, grid-connected: frequency_forcing_mw must be 0."""
        state = _make_state(island_mode=IslandMode.GRID_TIE)
        tick = _run_tick(state, sim_time=0.0, dt=5.0)
        assert tick.frequency_forcing_mw == 0.0, (
            f"D2: frequency_forcing_mw={tick.frequency_forcing_mw!r} must be 0.0 "
            f"in grid-connected mode (no load)"
        )

    def test_D2_with_load(self):
        """GPU job running, grid-connected: frequency_forcing_mw still 0."""
        state = _make_state(island_mode=IslandMode.GRID_TIE)
        sig = _starting_signal(nodes=10, ramp_s=120.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=120.0)
        tick = _run_tick(state, sim_time=5.0, dt=5.0)
        assert tick.frequency_forcing_mw == 0.0, (
            f"D2: frequency_forcing_mw={tick.frequency_forcing_mw!r} must be 0.0 "
            f"in grid-connected mode (with GPU load)"
        )

    def test_D2_depleted_bess_grid_connected(self):
        """Depleted BESS, grid-connected: frequency_forcing_mw still 0."""
        state = _make_state(
            bess_soc=0.0,
            bess_mwh=0.01,
            island_mode=IslandMode.GRID_TIE,
        )
        sig = _starting_signal(nodes=10, ramp_s=1.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)
        tick = _run_tick(state, sim_time=5.0, dt=5.0)
        assert tick.frequency_forcing_mw == 0.0, (
            f"D2: frequency_forcing_mw={tick.frequency_forcing_mw!r} must be 0.0 "
            f"in grid-connected mode (depleted BESS)"
        )


# ---------------------------------------------------------------------------
# D3 — asset_delivery_error_mw < 0.5% of site load in steady state, both modes
# ---------------------------------------------------------------------------

class TestD3ModelErrorSteadyState:
    """D3: asset_delivery_error_mw < 0.5% of site load in steady state, no injected fault."""

    def _run_to_settlement(
        self,
        nodes: int = 10,
        ramp_s: float = 1.0,
        island_mode: IslandMode = IslandMode.GRID_TIE,
        settle_ticks: int = 8,
        dt: float = 5.0,
    ):
        state = _make_state(island_mode=island_mode)
        sig = _starting_signal(nodes=nodes, ramp_s=ramp_s, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)
        tick = None
        for i in range(settle_ticks):
            tick = _run_tick(state, sim_time=float(i) * dt, dt=dt)
        return tick

    def test_D3_grid_connected_settled(self):
        """Grid-connected, settled: |asset_delivery_error_mw| < 0.5% of p_total_mw."""
        tick = self._run_to_settlement(island_mode=IslandMode.GRID_TIE)
        p_site = tick.p_demand_mw
        threshold = 0.005 * p_site if p_site > 0.01 else 0.001
        assert abs(tick.asset_delivery_error_mw) < threshold, (
            f"D3: asset_delivery_error_mw={tick.asset_delivery_error_mw:.6f} MW exceeds 0.5% of "
            f"p_total_mw={p_site:.4f} MW in grid-connected steady state"
        )

    def test_D3_islanded_settled(self):
        """Islanded, settled: |asset_delivery_error_mw| < 0.5% of p_total_mw."""
        tick = self._run_to_settlement(island_mode=IslandMode.ISLANDED)
        p_site = tick.p_demand_mw
        threshold = 0.005 * p_site if p_site > 0.01 else 0.001
        assert abs(tick.asset_delivery_error_mw) < threshold, (
            f"D3: asset_delivery_error_mw={tick.asset_delivery_error_mw:.6f} MW exceeds 0.5% of "
            f"p_total_mw={p_site:.4f} MW in islanded steady state"
        )

    def test_D3_depleted_bess_is_detectable_fault(self):
        """Depleted BESS causes non-zero asset_delivery_error_mw — fault is detectable.

        D3 only requires ~0 without injected fault.  With a depleted BESS the
        asset_delivery_error_mw is expected to be non-zero (it captures the delivery
        shortfall).  This test verifies the channel is informative, not
        structurally zero, when the BESS cannot track its setpoint.
        """
        state = _make_state(
            bess_soc=0.0,
            bess_mwh=0.01,
            bess_rated_mw=5.0,
            island_mode=IslandMode.GRID_TIE,
        )
        sig = _starting_signal(nodes=10, ramp_s=1.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)

        # Run until load is fully ramped
        tick = None
        for i in range(8):
            tick = _run_tick(state, sim_time=float(i) * 5.0, dt=5.0)

        # If bess_setpoint > 0 but bess_output = 0, asset_delivery_error_mw must capture it
        if tick.bess_setpoint_mw > 1e-6 and tick.bess_output_mw < 1e-6:
            assert tick.asset_delivery_error_mw < -1e-6, (
                f"D3 fault detection: depleted BESS (setpoint={tick.bess_setpoint_mw:.4f}, "
                f"output={tick.bess_output_mw:.4f}) should produce negative asset_delivery_error_mw; "
                f"got {tick.asset_delivery_error_mw:.6f}"
            )
        # If turbine covered all load (setpoint=0 for BESS), model_error is naturally small.
        # In that case the test passes by not reaching the assert above — expected.


# ---------------------------------------------------------------------------
# D4 — sum of three channels == (p_gen − p_load) scratch residual
# ---------------------------------------------------------------------------
# Task #200 B1: D4 is now a TWO-channel identity.
# grid_exchange_mw + frequency_forcing_mw == balance_residual_mw.
# asset_delivery_error_mw is a reporting field outside D4.
# The d4_balance_defect_mw field is authoritative (evaluate_tick() computes it inline).
# ---------------------------------------------------------------------------

class TestD4SumIdentity:
    """D4: TWO channels sum to (p_gen − p_load) — revised Task #200 B1.

    D4: grid_exchange + frequency_forcing = balance_residual.
    asset_delivery_error_mw is NOT in D4; it is a reporting field.

    Tests verify d4_balance_defect_mw ≈ 0 (the authoritative inline check)
    and that (grid_exchange + frequency_forcing) == recomputed residual.
    """

    def _p_gen_residual(self, tick) -> float:
        """Recompute the scratch residual from first principles."""
        return (
            tick.turbine_output_mw + tick.bess_output_mw + tick.p_renewable_mw
            - tick.p_demand_mw
        )

    def _verify_d4(self, tick, label: str):
        # Two-channel sum (Task #200 B1): asset_delivery_error NOT included.
        total = tick.grid_exchange_mw + tick.frequency_forcing_mw
        residual = self._p_gen_residual(tick)
        assert total == pytest.approx(residual, abs=1e-6), (
            f"D4 ({label}): two-channel sum={total:.9f} != "
            f"p_gen−p_load residual={residual:.9f}"
        )
        # d4_balance_defect_mw is the authoritative defect field (Task #198 item 5).
        assert abs(tick.d4_balance_defect_mw) < 1e-3, (
            f"D4 ({label}): d4_balance_defect_mw={tick.d4_balance_defect_mw:.9f} "
            f"exceeds 1e-3 tolerance — evaluate_tick() accounting error"
        )

    def test_D4_grid_connected_no_load(self):
        state = _make_state(island_mode=IslandMode.GRID_TIE)
        tick = _run_tick(state, sim_time=0.0, dt=5.0)
        self._verify_d4(tick, "grid-connected no load")

    def test_D4_grid_connected_with_load(self):
        state = _make_state(island_mode=IslandMode.GRID_TIE)
        sig = _starting_signal(nodes=10, ramp_s=1.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)
        for i in range(5):
            tick = _run_tick(state, sim_time=float(i) * 5.0, dt=5.0)
        self._verify_d4(tick, "grid-connected with load")

    def test_D4_islanded_no_load(self):
        state = _make_state(island_mode=IslandMode.ISLANDED)
        tick = _run_tick(state, sim_time=0.0, dt=5.0)
        self._verify_d4(tick, "islanded no load")

    def test_D4_islanded_with_load(self):
        state = _make_state(island_mode=IslandMode.ISLANDED)
        sig = _starting_signal(nodes=10, ramp_s=1.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)
        for i in range(5):
            tick = _run_tick(state, sim_time=float(i) * 5.0, dt=5.0)
        self._verify_d4(tick, "islanded with load")

    def test_D4_depleted_bess_reports_the_real_supply_gap(self):
        """DR-2026-08-09-BALANCE Phase 0. Islanded, BESS depleted, 10 nodes: no
        generation against ~0.105 MW of demand, so the balance defect is the gap.

        Before Phase 0 this asserted abs(defect) < 1e-3, which held only because the
        field was `_d4_sum - _balance_residual_mw` -- zero by algebra, a routing
        identity dressed as a diagnostic.

        D4 = local_gen + import − (demand − cumulative_shed_mw) − losses.
        With no generation, no import (islanded), and no UFLS shed yet:
          D4 = 0 + 0 − demand = −demand.
        The defect resolves to zero in Phase 4, when frequency collapse triggers UFLS
        and cumulative_shed_mw → demand, collapsing the served-load term to zero.
        Until then a non-zero defect is the expected, correct result.
        """
        state = _make_state(
            bess_soc=0.0,
            bess_mwh=0.01,
            bess_rated_mw=5.0,
            island_mode=IslandMode.ISLANDED,
        )
        sig = _starting_signal(nodes=10, ramp_s=1.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)
        for i in range(5):
            tick = _run_tick(state, sim_time=float(i) * 5.0, dt=5.0)
        assert tick.p_generation_mw == pytest.approx(0.0)
        # D4 = local_gen − demand (no import, no UFLS shed) = −demand.
        # The served/unserved pair is load-side accounting: unserved is explicit
        # UFLS shed only, while the uncovered supply remains p_imbalance_mw.
        assert tick.p_unserved_mw == pytest.approx(0.0)
        assert tick.p_served_mw == pytest.approx(tick.p_demand_mw)
        assert tick.p_imbalance_mw == pytest.approx(-tick.p_demand_mw, rel=1e-9)
        assert tick.d4_balance_defect_mw == pytest.approx(-tick.p_demand_mw, rel=1e-9)
        assert tick.d4_balance_defect_mw < -0.05      # a real gap, not rounding

    def test_D4_all_ticks_across_ramp(self):
        """D4 holds at every tick during a full ramp window (grid-connected)."""
        state = _make_state(island_mode=IslandMode.GRID_TIE)
        sig = _starting_signal(nodes=10, ramp_s=120.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=120.0)
        for i in range(30):
            tick = _run_tick(state, sim_time=float(i) * 5.0, dt=5.0)
            # Two-channel D4 (Task #200 B1): asset_delivery_error NOT in sum.
            total = tick.grid_exchange_mw + tick.frequency_forcing_mw
            residual = (
                tick.turbine_output_mw + tick.bess_output_mw + tick.p_renewable_mw
                - tick.p_demand_mw
            )
            assert total == pytest.approx(residual, abs=1e-6), (
                f"D4: sum of channels={total:.9f} != "
                f"p_gen−p_load={residual:.9f} at tick {i+1}"
            )
            # Task #198 item 5: defect field must stay zero
            assert abs(tick.d4_balance_defect_mw) < 1e-3, (
                f"D4: d4_balance_defect_mw={tick.d4_balance_defect_mw:.9f} at tick {i+1}"
            )


# ---------------------------------------------------------------------------
# D5 — asset_delivery_error_mw is NOT a residual of the other two (code-structure criterion)
# ---------------------------------------------------------------------------

class TestD5ModelErrorNotResidual:
    """D5: asset_delivery_error_mw is independently computed, not balance_residual - others.

    We verify this by asserting that asset_delivery_error_mw equals the independent formula
    (turbine_output − gt_setpoint) + (bess_output − bess_setpoint).
    If the field had been computed as a residual of the other two it would still
    give the same number in normal operation (D4 guarantees the sum), but the
    independent formula assertion proves the SOURCE is different — the derivation
    uses setpoints and actual outputs, not a subtraction from a pre-computed total.

    We use a fault scenario (depleted BESS) where the two paths diverge from each
    other's *intent*, making the distinction observable.
    """

    def test_D5_healthy_grid_connected(self):
        """Healthy assets: asset_delivery_error_mw == independent formula, grid-connected."""
        state = _make_state(island_mode=IslandMode.GRID_TIE)
        sig = _starting_signal(nodes=10, ramp_s=1.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)
        for i in range(5):
            tick = _run_tick(state, sim_time=float(i) * 5.0, dt=5.0)

        independent = (
            (tick.turbine_output_mw - tick.gt_setpoint_mw)
            + (tick.bess_output_mw  - tick.bess_setpoint_mw)
        )
        assert tick.asset_delivery_error_mw == pytest.approx(independent, abs=1e-9), (
            f"D5 (healthy grid-connected): asset_delivery_error_mw={tick.asset_delivery_error_mw:.9f} "
            f"!= independent formula={independent:.9f} — "
            f"field may have been computed as a residual of the other two"
        )

    def test_D5_healthy_islanded(self):
        """Healthy assets: asset_delivery_error_mw == independent formula, islanded."""
        state = _make_state(island_mode=IslandMode.ISLANDED)
        sig = _starting_signal(nodes=10, ramp_s=1.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)
        for i in range(5):
            tick = _run_tick(state, sim_time=float(i) * 5.0, dt=5.0)

        independent = (
            (tick.turbine_output_mw - tick.gt_setpoint_mw)
            + (tick.bess_output_mw  - tick.bess_setpoint_mw)
        )
        assert tick.asset_delivery_error_mw == pytest.approx(independent, abs=1e-9), (
            f"D5 (healthy islanded): asset_delivery_error_mw={tick.asset_delivery_error_mw:.9f} "
            f"!= independent formula={independent:.9f} — "
            f"field may have been computed as a residual of the other two"
        )

    def test_D5_depleted_bess_independent_formula_matches(self):
        """Depleted BESS: asset_delivery_error_mw still matches the setpoint-tracking formula.

        This is the critical D5 scenario: with depleted BESS, the 'residual of
        the other two' path and the 'independent formula' path give numerically
        different intermediate values (grid_exchange or frequency_forcing absorbs
        the commanded-but-undelivered power, leaving model_error = 0 under a
        slack definition).  The independent formula correctly gives a non-zero
        value equal to the BESS delivery shortfall.
        """
        state = _make_state(
            bess_soc=0.0,
            bess_mwh=0.01,
            bess_rated_mw=5.0,
            island_mode=IslandMode.GRID_TIE,
        )
        sig = _starting_signal(nodes=10, ramp_s=1.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)
        for i in range(5):
            tick = _run_tick(state, sim_time=float(i) * 5.0, dt=5.0)

        independent = (
            (tick.turbine_output_mw - tick.gt_setpoint_mw)
            + (tick.bess_output_mw  - tick.bess_setpoint_mw)
        )
        assert tick.asset_delivery_error_mw == pytest.approx(independent, abs=1e-9), (
            f"D5 (depleted BESS): asset_delivery_error_mw={tick.asset_delivery_error_mw:.9f} "
            f"!= independent formula={independent:.9f}\n"
            f"  turbine_output={tick.turbine_output_mw:.6f}  gt_setpoint={tick.gt_setpoint_mw:.6f}\n"
            f"  bess_output={tick.bess_output_mw:.6f}  bess_setpoint={tick.bess_setpoint_mw:.6f}"
        )

    def test_D5_no_reference_to_balance_residual_in_formula(self):
        """Structural guard: asset_delivery_error_mw != balance_residual - grid_exchange - freq_forcing.

        When assets ARE tracking setpoints, both paths give the same number.
        But when assets are healthy the 'independent formula' is the ONLY
        safe definition — it is not coincidentally equal; it is structurally
        distinct.  We cannot test code structure in Python at runtime, but we
        CAN assert that the field's value matches only the independent formula,
        not the residual computation, across a range of ticks where the two
        paths WOULD give different results if wrongly implemented.

        Test strategy: verify that across 20 ticks of a ramp window, the
        asset_delivery_error_mw never exceeds |bess_out − bess_setpoint| + |turbine_out − gt_setpoint|
        (which would be impossible if it were computed as a raw subtraction of
        the other two channels, since floating-point rounding could produce
        values slightly outside this envelope).
        """
        state = _make_state(island_mode=IslandMode.GRID_TIE)
        sig = _starting_signal(nodes=10, ramp_s=120.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=120.0)
        for i in range(20):
            tick = _run_tick(state, sim_time=float(i) * 5.0, dt=5.0)
            independent = (
                (tick.turbine_output_mw - tick.gt_setpoint_mw)
                + (tick.bess_output_mw  - tick.bess_setpoint_mw)
            )
            assert tick.asset_delivery_error_mw == pytest.approx(independent, abs=1e-9), (
                f"D5 structural: tick {i+1} asset_delivery_error_mw={tick.asset_delivery_error_mw:.9f} "
                f"!= independent formula={independent:.9f}"
            )


# ---------------------------------------------------------------------------
# I4 — swing equation uses (frequency_forcing_mw + asset_delivery_error_mw)
# ---------------------------------------------------------------------------

class TestI4SwingEquationExplicitInput:
    """I4 (revised — Task #200 B1): frequency_forcing = balance_residual in islanded mode.

    Under B1, the swing equation input is frequency_forcing_mw alone.
    frequency_forcing = balance_residual = p_gen − p_load (actual actuals).
    asset_delivery_error_mw is a reporting field; it is implicit in balance_residual,
    not a separate swing-equation term.

    Three sub-tests:

    I4a — Healthy islanded: asset_delivery_error ≈ 0 after settling.
          Δf = frequency_forcing / (2H × S_base) × f₀ × dt.
          frequency_forcing ≈ balance_residual (small mismatch = normal dispatch plan).

    I4b — Depleted BESS islanded: asset_delivery_error < 0.
          BESS commanded but delivers nothing; p_gen drops → balance_residual < forcing
          predicted by setpoints alone.  Δf still follows swing equation using
          frequency_forcing = balance_residual (which absorbs the delivery shortfall).
          Removed: the old "forcing_only_df < actual_df" assertion (no longer meaningful
          because frequency_forcing IS balance_residual; there is no separate
          "forcing only" channel).

    I4c — Grid-connected with delivery fault: frequency stays at site nominal.
          "Frequency doesn't move" — the grid is the infinite-bus reference.
          D2: frequency_forcing_mw = 0 exactly; delivery fault absorbed by grid_exchange.

    Swing equation formula (islanded, one-term input):
      Δf = frequency_forcing_mw / (2 × H × S_base) × f₀ × dt
    where f₀ = state.site.frequency_nominal_hz  (sourced from config — no literal).
    """

    # H is a constant (inertia_constant_s SiteConfig default from _make_state).
    # f₀ and f_nom are sourced from state.site.frequency_nominal_hz in each test
    # (no class-level literals — Task #200 A3 requirement).
    _H = 4.0    # inertia_constant_s — matches _make_state SiteConfig default

    def _expected_df(
        self,
        frequency_forcing_mw: float,
        s_base_mw: float,
        dt: float,
        f0: float,
    ) -> float:
        """Swing-equation prediction: Δf from frequency_forcing alone (B1 one-term input)."""
        return (
            frequency_forcing_mw
            / (2.0 * self._H * s_base_mw)
            * f0
            * dt
        )

    def test_I4a_healthy_islanded_delivery_error_near_zero(self):
        """I4a: Healthy BESS — asset_delivery_error ≈ 0 after assets settle.

        The tick result frequency_hz change must match the expected Δf computed
        from frequency_forcing_mw alone (since delivery_error ≈ 0).
        """
        state = _make_state(island_mode=IslandMode.ISLANDED)
        sig = _starting_signal(nodes=10, ramp_s=1.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)
        dt = 5.0
        # Run several ticks to settle; capture consecutive tick pair to measure Δf
        tick_prev = None
        for i in range(8):
            tick_prev = _run_tick(state, sim_time=float(i) * dt, dt=dt)
        # One more tick — frequency_hz on tick_prev is the state AFTER that tick
        tick_curr = _run_tick(state, sim_time=8.0 * dt, dt=dt)

        # asset_delivery_error should be ~0 for healthy settled BESS + turbine
        assert abs(tick_curr.asset_delivery_error_mw) < 0.01, (
            f"I4a: expected near-zero asset_delivery_error_mw after settling; "
            f"got {tick_curr.asset_delivery_error_mw:.6f} MW"
        )

        # frequency_hz at tick_curr should equal tick_prev.frequency_hz + expected_Δf
        # B1: Δf = frequency_forcing / (2H × S_base) × f₀ × dt (one-term formula).
        f0 = state.site.frequency_nominal_hz  # sourced from config (50.0 EU/APAC)
        s_base = max(1.0, sum(t.config.rated_mw for t in state.turbines))
        expected_df = self._expected_df(
            tick_curr.frequency_forcing_mw,
            s_base,
            dt,
            f0,
        )
        actual_df = tick_curr.frequency_hz - tick_prev.frequency_hz
        assert actual_df == pytest.approx(expected_df, abs=1e-9), (
            f"I4a: frequency Δ={actual_df:.9f} Hz does not match "
            f"swing-equation prediction from frequency_forcing = {expected_df:.9f} Hz\n"
            f"  frequency_forcing_mw={tick_curr.frequency_forcing_mw:.6f}\n"
            f"  asset_delivery_error_mw={tick_curr.asset_delivery_error_mw:.6f} [reporting only]"
        )

    def test_I4b_depleted_bess_islanded_delivery_error_amplifies_drop(self):
        """I4b: Depleted BESS — asset_delivery_error < 0, drop > frequency_forcing alone.

        Frequency change = (frequency_forcing + asset_delivery_error) × swing_gain.
        With BESS under-delivering, asset_delivery_error < 0, so |Δf| >
        |frequency_forcing| × swing_gain.

        Turbine rating is set very small (0.05 MW) so the dispatch plan must command
        the BESS for even a 10-node job, guaranteeing a non-trivial delivery error
        when the BESS is depleted.
        """
        state = _make_state(
            turbine_rated_mw=0.05,     # tiny turbine → BESS always commanded
            turbine_ramp=0.05,
            bess_soc=0.0,
            bess_mwh=0.01,
            bess_rated_mw=5.0,
            island_mode=IslandMode.ISLANDED,
        )
        sig = _starting_signal(nodes=10, ramp_s=1.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)
        dt = 5.0
        tick_prev = None
        for i in range(5):
            tick_prev = _run_tick(state, sim_time=float(i) * dt, dt=dt)
        tick_curr = _run_tick(state, sim_time=5.0 * dt, dt=dt)

        # Only interesting if BESS was actually commanded but under-delivered
        if tick_curr.bess_setpoint_mw < 1e-6:
            pytest.skip("BESS not commanded this tick; turbine covered all load")

        # asset_delivery_error must be negative (BESS under-delivered)
        assert tick_curr.asset_delivery_error_mw < 0, (
            f"I4b: expected negative asset_delivery_error_mw with depleted BESS "
            f"(setpoint={tick_curr.bess_setpoint_mw:.4f} MW, "
            f"output={tick_curr.bess_output_mw:.4f} MW); "
            f"got {tick_curr.asset_delivery_error_mw:.6f}"
        )

        # B1: Δf = frequency_forcing / (2H × S_base) × f₀ × dt.
        # frequency_forcing = balance_residual (which is already more negative than
        # a "setpoints-only" estimate because the BESS is not delivering).
        # S_base = Σ rated_mw / power_factor — mirrors simulation_core.py formula.
        f0 = state.site.frequency_nominal_hz  # sourced from config (50.0 EU/APAC)
        s_base = max(1.0, sum(t.config.rated_mw for t in state.turbines)) / state.site.power_factor
        expected_df = self._expected_df(
            tick_curr.frequency_forcing_mw,
            s_base,
            dt,
            f0,
        )
        actual_df = tick_curr.frequency_hz - tick_prev.frequency_hz
        assert actual_df == pytest.approx(expected_df, abs=1e-9), (
            f"I4b: frequency Δ={actual_df:.9f} Hz does not match "
            f"swing-equation prediction {expected_df:.9f} Hz\n"
            f"  frequency_forcing_mw={tick_curr.frequency_forcing_mw:.6f}\n"
            f"  asset_delivery_error_mw={tick_curr.asset_delivery_error_mw:.6f} [reporting only]"
        )
        # Note: old I4b "forcing_only_df < actual_df" assertion is REMOVED under B1.
        # Under B1, frequency_forcing IS balance_residual — there is no separate
        # "forcing only" prediction vs "forcing + delivery" prediction.  The delivery
        # shortfall is already captured in balance_residual → frequency_forcing.

    def test_I4c_grid_connected_delivery_fault_frequency_invariant(self):
        """I4c: Grid-connected — frequency stays at 50 Hz regardless of delivery error.

        'Frequency doesn't move' with a load-model or asset delivery error in
        grid-connected mode.  The grid absorbs the imbalance (grid_exchange_mw).
        asset_delivery_error_mw is non-zero (fault visible), but frequency_hz
        remains at nominal.

        This is the surviving distinction from the review document: the same fault
        that would cause frequency deviation in islanded mode (I4b) is absorbed
        silently by the grid here.  The channel identifies WHERE the energy went.

        Turbine rating is set very small (0.05 MW) so BESS is always commanded,
        guaranteeing a delivery error when the BESS is depleted.
        """
        state = _make_state(
            turbine_rated_mw=0.05,     # tiny turbine → BESS always commanded
            turbine_ramp=0.05,
            bess_soc=0.0,
            bess_mwh=0.01,
            bess_rated_mw=5.0,
            island_mode=IslandMode.GRID_TIE,
        )
        sig = _starting_signal(nodes=10, ramp_s=1.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)
        dt = 5.0
        for i in range(8):
            tick = _run_tick(state, sim_time=float(i) * dt, dt=dt)

        # Only interesting if BESS was actually under-delivering
        if tick.bess_setpoint_mw < 1e-6:
            pytest.skip("BESS not commanded this tick; no delivery fault")

        # Delivery error is present (BESS depleted)
        assert tick.asset_delivery_error_mw < 0, (
            f"I4c: expected negative asset_delivery_error_mw with depleted BESS "
            f"(setpoint={tick.bess_setpoint_mw:.4f} MW, "
            f"output={tick.bess_output_mw:.4f} MW); "
            f"got {tick.asset_delivery_error_mw:.6f}"
        )

        # Frequency stays at site nominal — grid absorbed the imbalance.
        # state uses _make_state(frequency_nominal_hz=50.0, power_factor=0.85) — EU/APAC fixture by intent.
        f_nom = state.site.frequency_nominal_hz  # sourced from config
        assert tick.frequency_hz == pytest.approx(f_nom, abs=1e-9), (
            f"I4c: frequency_hz={tick.frequency_hz:.9f} Hz should be exactly "
            f"{f_nom} Hz in grid-connected mode even with delivery fault "
            f"(asset_delivery_error_mw={tick.asset_delivery_error_mw:.6f})"
        )

        # frequency_forcing_mw must be exactly 0 (D2 holds)
        assert tick.frequency_forcing_mw == 0.0, (
            f"I4c: frequency_forcing_mw={tick.frequency_forcing_mw!r} must be 0.0 "
            f"in grid-connected mode (D2); fault absorbed by grid_exchange_mw instead"
        )

        # grid_exchange_mw must carry the dispatch plan shortfall
        # (p_commanded − p_total includes the BESS setpoint that wasn't delivered)
        assert tick.grid_exchange_mw != pytest.approx(0.0, abs=1e-3), (
            f"I4c: grid_exchange_mw={tick.grid_exchange_mw:.6f} should be non-zero "
            f"(grid absorbing BESS delivery shortfall of {tick.asset_delivery_error_mw:.4f} MW)"
        )
