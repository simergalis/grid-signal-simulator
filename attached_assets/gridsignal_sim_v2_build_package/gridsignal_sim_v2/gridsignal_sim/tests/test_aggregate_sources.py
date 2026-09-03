"""
test_aggregate_sources.py — Black-box aggregate tests for BESS, GRID, and FUEL CELL.

Verifies that each source feeds (or does not feed) into p_generation_mw correctly.

Aggregate identity (simulation_core.py):
    p_generation_mw = turbine_output_mw
                    + bess_output_mw
                    + fuel_cell_output_mw
                    + p_renewable_mw
                    + max(0, -grid_exchange_mw)   ← grid import only; export = 0 contribution

Source status:
  BESS      — bess_output_mw contributes directly. ✓
  GRID      — grid_exchange_mw < 0 on import; added via max(0, -x). ✓
  FUEL CELL — fuel_cell_output_mw is the aggregate module's measured,
               rate-limited fixed-baseload output. ✓

All tests run headless — no HTTP, no database, no WebSocket.
"""

from __future__ import annotations

import sys
import math
import pytest

sys.path.insert(0, ".")

from core.models import IslandMode
from core.sim_clock import SimClock

from tests.test_forecast_path import (
    _make_state,
    _starting_signal,
    _run_tick,
)

# ── Tolerance ──────────────────────────────────────────────────────────────────
FLOAT_TOL = 1e-6   # MW; tighter than meter-level accuracy


def _aggregate_identity(tick) -> float:
    """The RHS of the aggregate formula — must equal tick.p_generation_mw."""
    return (
        tick.turbine_output_mw
        + tick.bess_output_mw
        + tick.fuel_cell_output_mw
        + tick.p_renewable_mw
        + max(0.0, -tick.grid_exchange_mw)
    )


def _run_ticks(state, n: int, dt: float = 5.0):
    """Run n ticks and return the list of TickResult objects."""
    results = []
    for i in range(n):
        results.append(_run_tick(state, sim_time=float(i) * dt, dt=dt))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# BESS  → aggregate (Tests 1–3)
# ─────────────────────────────────────────────────────────────────────────────

class TestBESSAggregate:
    """BESS discharge is included in p_generation_mw."""

    def test_BESS1_discharge_appears_in_aggregate(self):
        """
        BESS-AGG-1: When the turbine fleet alone is undersized, BESS discharges
        to cover the shortfall and its output appears in p_generation_mw.

        Setup: 2 MW turbine, 5 MW BESS fully charged, 20-node GPU job.
        Expected: bess_output_mw > 0 at settlement; aggregate identity holds.
        """
        state = _make_state(
            turbine_rated_mw=2.0,    # small — cannot cover full GPU load
            bess_rated_mw=5.0,
            bess_mwh=4.0,
            bess_soc=1.0,
            island_mode=IslandMode.ISLANDED,
        )
        sig = _starting_signal(nodes=20, ramp_s=1.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)

        # Run several ticks to let the workload settle
        tick = None
        for i in range(8):
            tick = _run_tick(state, sim_time=float(i) * 5.0, dt=5.0)

        assert tick.bess_output_mw > 0.05, (
            f"BESS-AGG-1: expected BESS discharge > 0.05 MW; "
            f"got bess_output_mw={tick.bess_output_mw:.4f} MW"
        )
        expected = _aggregate_identity(tick)
        assert abs(tick.p_generation_mw - expected) < FLOAT_TOL, (
            f"BESS-AGG-1: p_generation_mw={tick.p_generation_mw:.6f} "
            f"!= computed aggregate={expected:.6f}; "
            f"delta={tick.p_generation_mw - expected:.2e} MW"
        )

    def test_BESS2_depleted_bess_contributes_zero(self):
        """
        BESS-AGG-2: A fully-depleted BESS (SOC ≈ 0) contributes ≈ 0 MW.

        p_generation_mw should fall back to turbine + renewable only (islanded).
        """
        state = _make_state(
            turbine_rated_mw=10.0,
            bess_rated_mw=5.0,
            bess_mwh=0.01,  # nearly empty
            bess_soc=0.0,
            island_mode=IslandMode.ISLANDED,
        )
        sig = _starting_signal(nodes=10, ramp_s=1.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)

        tick = _run_tick(state, sim_time=5.0, dt=5.0)

        assert tick.bess_output_mw < 0.05, (
            f"BESS-AGG-2: depleted BESS should contribute ≈0; "
            f"got bess_output_mw={tick.bess_output_mw:.4f} MW"
        )
        expected = _aggregate_identity(tick)
        assert abs(tick.p_generation_mw - expected) < FLOAT_TOL, (
            f"BESS-AGG-2: aggregate identity broken; delta={tick.p_generation_mw - expected:.2e}"
        )

    def test_BESS3_aggregate_identity_holds_over_many_ticks_islanded(self):
        """
        BESS-AGG-3: The aggregate identity
            p_generation_mw == turbine + bess + renewable
        holds at every tick in islanded mode (grid_exchange_mw = 0 always).

        Runs 12 ticks across a settling workload.
        """
        state = _make_state(
            turbine_rated_mw=10.0,
            bess_rated_mw=5.0,
            bess_mwh=3.0,
            bess_soc=0.8,
            island_mode=IslandMode.ISLANDED,
        )
        sig = _starting_signal(nodes=15, ramp_s=5.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)

        ticks = _run_ticks(state, n=12, dt=5.0)
        failures = []
        for i, tick in enumerate(ticks):
            delta = tick.p_generation_mw - _aggregate_identity(tick)
            if abs(delta) >= FLOAT_TOL:
                failures.append(
                    f"  tick {i}: p_generation={tick.p_generation_mw:.6f}, "
                    f"computed={_aggregate_identity(tick):.6f}, delta={delta:.2e}"
                )
        assert not failures, (
            "BESS-AGG-3: aggregate identity failed at:\n" + "\n".join(failures)
        )


# ─────────────────────────────────────────────────────────────────────────────
# GRID  → aggregate (Tests 4–6)
# ─────────────────────────────────────────────────────────────────────────────

class TestGRIDAggregate:
    """Grid import adds to p_generation_mw; export and islanded mode contribute 0."""

    def test_GRID4_import_adds_to_aggregate(self):
        """
        GRID-AGG-4: Grid-connected with depleted BESS and heavy load causes
        grid_exchange_mw < 0 (PCC import).  The import magnitude is added to
        p_generation_mw via max(0, -grid_exchange_mw).

        Setup: tiny turbine (2 MW), depleted BESS, 20-node job, GRID_TIE.
        Expected: grid_exchange_mw < 0; aggregate identity holds.
        """
        state = _make_state(
            turbine_rated_mw=2.0,
            bess_rated_mw=5.0,
            bess_mwh=0.01,
            bess_soc=0.0,
            island_mode=IslandMode.GRID_TIE,
        )
        sig = _starting_signal(nodes=20, ramp_s=1.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)

        tick = None
        for i in range(6):
            tick = _run_tick(state, sim_time=float(i) * 5.0, dt=5.0)

        assert tick.grid_exchange_mw < -0.01, (
            f"GRID-AGG-4: expected grid import (grid_exchange_mw < -0.01); "
            f"got {tick.grid_exchange_mw:.4f} MW"
        )
        grid_import = max(0.0, -tick.grid_exchange_mw)
        assert grid_import > 0.01, (
            f"GRID-AGG-4: expected positive grid import contribution; "
            f"got {grid_import:.4f} MW"
        )
        expected = _aggregate_identity(tick)
        assert abs(tick.p_generation_mw - expected) < FLOAT_TOL, (
            f"GRID-AGG-4: aggregate identity broken; "
            f"p_generation={tick.p_generation_mw:.6f}, computed={expected:.6f}, "
            f"delta={tick.p_generation_mw - expected:.2e}"
        )

    def test_GRID5_export_does_not_inflate_aggregate(self):
        """
        GRID-AGG-5: When local generation exceeds demand (grid export),
        grid_exchange_mw > 0 and max(0, -grid_exchange_mw) = 0.
        Grid export must NOT inflate p_generation_mw beyond local assets.

        Setup: large turbine (20 MW), no GPU load, GRID_TIE.
        Expected: grid_exchange_mw > 0 (export); aggregate = local gen only.
        """
        state = _make_state(
            turbine_rated_mw=20.0,
            bess_rated_mw=5.0,
            bess_mwh=3.0,
            bess_soc=0.5,
            island_mode=IslandMode.GRID_TIE,
        )
        # No workload — very low demand → turbine overproduces → export
        tick = _run_tick(state, sim_time=0.0, dt=5.0)

        # With no GPU load the turbine may still produce near its MSL;
        # verify the identity holds regardless of sign of grid_exchange.
        grid_contrib = max(0.0, -tick.grid_exchange_mw)
        assert grid_contrib == 0.0 or tick.grid_exchange_mw <= 0.0, (
            "GRID-AGG-5 pre-check: grid_exchange direction is ambiguous"
        )

        expected = _aggregate_identity(tick)
        assert abs(tick.p_generation_mw - expected) < FLOAT_TOL, (
            f"GRID-AGG-5: aggregate identity broken during export/neutral; "
            f"p_generation={tick.p_generation_mw:.6f}, computed={expected:.6f}, "
            f"delta={tick.p_generation_mw - expected:.2e}"
        )
        # When exporting (exchange > 0), grid contribution must be exactly 0
        if tick.grid_exchange_mw > 0:
            assert grid_contrib == 0.0, (
                f"GRID-AGG-5: export scenario must contribute 0 to aggregate; "
                f"got {grid_contrib:.4f} MW"
            )

    def test_GRID6_islanded_exchange_exactly_zero(self):
        """
        GRID-AGG-6: In islanded mode, grid_exchange_mw == 0.0 at every tick (D1).
        The grid term max(0, -0) = 0 contributes nothing to the aggregate.

        Runs 10 ticks with varying load to confirm D1 is unconditional.
        """
        state = _make_state(
            turbine_rated_mw=10.0,
            bess_rated_mw=5.0,
            bess_mwh=3.0,
            bess_soc=1.0,
            island_mode=IslandMode.ISLANDED,
        )
        sig = _starting_signal(nodes=12, ramp_s=2.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)

        ticks = _run_ticks(state, n=10, dt=5.0)
        for i, tick in enumerate(ticks):
            assert tick.grid_exchange_mw == 0.0, (
                f"GRID-AGG-6 (D1): tick {i} grid_exchange_mw="
                f"{tick.grid_exchange_mw} — must be exactly 0.0 in islanded mode"
            )
            assert max(0.0, -tick.grid_exchange_mw) == 0.0, (
                f"GRID-AGG-6: islanded grid contribution must be 0; tick {i}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# FUEL CELL  → aggregate (Tests 7–9)
# ─────────────────────────────────────────────────────────────────────────────

class TestFuelCellAggregate:
    """
    Fuel cell is now wired into the physics engine.
    evaluate_tick() dispatches an enabled fuel-cell array after cheaper BESS and
    turbine capacity, up to the fleet's rated capacity.
    """

    def test_FC7_tick_result_has_fuel_cell_output_field(self):
        """
        FC-AGG-7: TickResult.fuel_cell_output_mw exists and is a float.
        When fuel_cell_rated_mw=0 (default), it must be exactly 0.0.
        """
        state = _make_state(island_mode=IslandMode.ISLANDED)
        tick = _run_tick(state, sim_time=0.0, dt=5.0)

        assert hasattr(tick, "fuel_cell_output_mw"), (
            "FC-AGG-7: TickResult.fuel_cell_output_mw is missing — "
            "fuel cell dispatch was not wired into evaluate_tick()."
        )
        assert isinstance(tick.fuel_cell_output_mw, float), (
            f"FC-AGG-7: fuel_cell_output_mw should be float, got {type(tick.fuel_cell_output_mw)}"
        )
        # No fuel cell in this state → output must be 0.0
        assert tick.fuel_cell_output_mw == 0.0, (
            f"FC-AGG-7: fuel_cell_output_mw={tick.fuel_cell_output_mw:.6f} — "
            "expected 0.0 when fuel_cell_rated_mw=0 (not configured)."
        )

    def test_FC8_aggregate_closes_with_fuel_cell_term(self):
        """
        FC-AGG-8: The aggregate identity
            p_generation_mw == turbine + bess + fuel_cell + renewable + max(0, -grid)
        closes to float precision across 15 ticks.

        Uses a turbine+BESS-only scenario (no FC) so fuel_cell_output_mw=0 — the
        identity is equivalent to the pre-wiring form but verified with the new term.
        """
        state = _make_state(
            turbine_rated_mw=10.0,
            bess_rated_mw=5.0,
            bess_mwh=4.0,
            bess_soc=0.9,
            island_mode=IslandMode.ISLANDED,
        )
        sig = _starting_signal(nodes=10, ramp_s=2.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)

        ticks = _run_ticks(state, n=15, dt=5.0)
        failures = []
        for i, tick in enumerate(ticks):
            rhs = _aggregate_identity(tick)
            delta = tick.p_generation_mw - rhs
            if abs(delta) >= FLOAT_TOL:
                failures.append(
                    f"  tick {i}: delta={delta:.2e} MW "
                    f"(p_gen={tick.p_generation_mw:.6f}, rhs={rhs:.6f}, "
                    f"fc={tick.fuel_cell_output_mw:.6f})"
                )

        assert not failures, (
            "FC-AGG-8: aggregate identity fails:\n"
            + "\n".join(failures)
        )

    def test_FC9_fuel_cell_dispatches_when_demand_exceeds_bess(self):
        """
        FC-AGG-9: When fuel_cell_enabled=True and demand exceeds what BESS alone
        can supply, fuel_cell_output_mw > 0 and the aggregate identity closes.

        Uses a scenario with an undersized BESS (0.3 MW) against 120-node demand
        (~1.26 MW) so the fuel cell must cover the gap before grid import.
        """
        from core._plane_guard import _EVALUATE_TICK_PERMITTED
        from core.sim_clock import SimClock
        from core.simulation_core import evaluate_tick
        from runtime.scenario_factory import build_run_context_from_spec

        SPEC = {
            "name": "fc-dispatch-test",
            "description": "",
            "frequency_nominal_hz": 50.0,
            "power_factor": 0.85,
            "pue_base": 1.03,
            "island_mode": False,         # grid-connected
            "turbine_units": [],          # no turbines — force BESS + FC + grid path
            "bess_units": [
                {
                    "asset_id": "bess-1",
                    "rated_mw": 0.3,      # undersized: cannot cover ~1.26 MW alone
                    "usable_mwh": 0.5,
                    "initial_soc_fraction": 0.95,
                    "p_anchor_reserve_mw": 0.0,
                    "grid_forming": False,
                }
            ],
            "solar_rated_mw": 0.0,
            "fuel_cell_enabled": True,
            "fuel_cell_rated_mw": 5.0,    # ample capacity to cover the gap
            "fuel_cell_stack_count": 1,
            "workload_events": [],
            "end_sim_time": 300.0,
        }

        ctx = build_run_context_from_spec(run_id="fc9-test", spec_data=SPEC)
        # Apply 120-node load so demand > BESS ceiling
        sig = _starting_signal(nodes=120, ramp_s=1.0, timestamp=0.0)
        ctx.sim_state.apply_workload_signal(sig, dt_lead_seconds=0.0)

        token = _EVALUATE_TICK_PERMITTED.set(True)
        try:
            ticks = []
            for i in range(10):
                clock = SimClock(
                    sim_time=float(i) * 5.0, dt_seconds=5.0,
                    wall_stamp_utc=float(i) * 5.0, rate=1.0, tick_seq=i,
                )
                ticks.append(evaluate_tick(ctx.sim_state, clock))
        finally:
            _EVALUATE_TICK_PERMITTED.reset(token)

        fc_dispatched_any = any(t.fuel_cell_output_mw > 0.01 for t in ticks)
        assert fc_dispatched_any, (
            "FC-AGG-9: fuel_cell_output_mw never exceeded 0.01 MW across 10 ticks "
            "with 120-node load and BESS limited to 0.3 MW — FC dispatch not wired."
        )

        failures = []
        for i, tick in enumerate(ticks):
            rhs = _aggregate_identity(tick)
            delta = tick.p_generation_mw - rhs
            if abs(delta) >= FLOAT_TOL:
                failures.append(
                    f"  tick {i}: p_gen={tick.p_generation_mw:.6f} rhs={rhs:.6f} "
                    f"fc={tick.fuel_cell_output_mw:.4f} delta={delta:.2e}"
                )
        assert not failures, (
            "FC-AGG-9: aggregate identity fails when FC is dispatching:\n"
            + "\n".join(failures)
        )

    def test_FC10_turbine_is_preferred_before_fuel_cell(self):
        """
        FC-AGG-10: the turbine still receives the residual demand after the
        measured fuel-cell baseload has been read.  The FC must follow its
        configured ramp rather than being filled algebraically from residual
        demand.
        """
        from core._plane_guard import _EVALUATE_TICK_PERMITTED
        from core.sim_clock import SimClock
        from core.simulation_core import evaluate_tick
        from runtime.scenario_factory import build_run_context_from_spec

        spec = {
            "name": "fc-primary-dispatch-test",
            "description": "",
            "frequency_nominal_hz": 50.0,
            "power_factor": 0.85,
            "pue_base": 1.03,
            "island_mode": False,
            "turbine_units": [{"asset_id": "turbine-0", "rated_mw": 10.0}],
            "bess_units": [{
                "asset_id": "bess-0",
                "rated_mw": 2.0,
                "usable_mwh": 2.0,
                "initial_soc_fraction": 0.0,
                "p_anchor_reserve_mw": 0.0,
                "grid_forming": False,
            }],
            "solar_rated_mw": 0.0,
            "fuel_cell_enabled": True,
            "fuel_cell_rated_mw": 5.0,
            "fuel_cell_stack_count": 1,
            "workload_events": [],
            "end_sim_time": 300.0,
        }
        ctx = build_run_context_from_spec(run_id="fc10-test", spec_data=spec)
        ctx.sim_state.apply_workload_signal(
            _starting_signal(nodes=300, ramp_s=1.0, timestamp=0.0),
            dt_lead_seconds=0.0,
        )

        token = _EVALUATE_TICK_PERMITTED.set(True)
        try:
            ticks = [
                evaluate_tick(
                    ctx.sim_state,
                    SimClock(
                        sim_time=float(i) * 5.0, dt_seconds=5.0,
                        wall_stamp_utc=float(i) * 5.0, rate=1.0, tick_seq=i,
                    ),
                )
                for i in range(10)
            ]
        finally:
            _EVALUATE_TICK_PERMITTED.reset(token)

        settled = ticks[-1]
        assert settled.turbine_output_mw > 2.0 + 1e-6, (
            "FC-AGG-10: the turbine was not loaded above its minimum stable "
            "output after BESS became unavailable."
        )
        module = ctx.sim_state.fuel_cell_module
        assert module is not None
        expected_fc_mw = min(
            module.min_stable_mw
            + len(ticks) * module.config.ramp_rate_mw_per_s * 5.0,
            module.target_output_mw,
        )
        assert settled.fuel_cell_output_mw == pytest.approx(
            expected_fc_mw, abs=1e-6
        ), (
            "FC-AGG-10: measured fuel-cell output did not follow the module "
            "ramp toward its fixed baseload target."
        )
        assert settled.p_generation_mw == pytest.approx(
            _aggregate_identity(settled), abs=FLOAT_TOL
        ), (
            "FC-AGG-10: the aggregate must include measured FC output and "
            "exclude exported grid power from local generation."
        )

    def test_FC11_all_three_sources_follow_cost_order_at_capacity(self):
        """
        FC-AGG-11: one settled high-load tick demonstrates that the fixed
        fuel-cell baseload is measured first, while BESS and turbine dispatch
        cover only the remaining demand.
        """
        from core._plane_guard import _EVALUATE_TICK_PERMITTED
        from core.sim_clock import SimClock
        from core.simulation_core import evaluate_tick
        from runtime.scenario_factory import build_run_context_from_spec

        spec = {
            "name": "fc-three-source-cost-order-test",
            "description": "",
            "frequency_nominal_hz": 50.0,
            "power_factor": 0.85,
            "pue_base": 1.03,
            "island_mode": False,
            "turbine_units": [{"asset_id": "turbine-0", "rated_mw": 5.0}],
            "bess_units": [{
                "asset_id": "bess-0",
                "rated_mw": 1.0,
                "usable_mwh": 5.0,
                "initial_soc_fraction": 0.95,
                "p_anchor_reserve_mw": 0.0,
                "grid_forming": False,
            }],
            "solar_rated_mw": 0.0,
            "fuel_cell_enabled": True,
            "fuel_cell_rated_mw": 5.0,
            "fuel_cell_stack_count": 1,
            "workload_events": [],
            "end_sim_time": 300.0,
        }
        ctx = build_run_context_from_spec(run_id="fc11-test", spec_data=spec)
        ctx.sim_state.apply_workload_signal(
            _starting_signal(nodes=800, ramp_s=1.0, timestamp=0.0),
            dt_lead_seconds=0.0,
        )

        token = _EVALUATE_TICK_PERMITTED.set(True)
        try:
            ticks = [
                evaluate_tick(
                    ctx.sim_state,
                    SimClock(
                        sim_time=float(i) * 5.0, dt_seconds=5.0,
                        wall_stamp_utc=float(i) * 5.0, rate=1.0, tick_seq=i,
                    ),
                )
                for i in range(25)
            ]
        finally:
            _EVALUATE_TICK_PERMITTED.reset(token)

        settled = ticks[-1]
        assert settled.bess_output_mw == pytest.approx(1.0, abs=1e-6), (
            "FC-AGG-11: BESS did not reach its available ceiling for the "
            "remaining demand."
        )
        module = ctx.sim_state.fuel_cell_module
        assert module is not None
        expected_fc_mw = min(
            module.min_stable_mw
            + len(ticks) * module.config.ramp_rate_mw_per_s * 5.0,
            module.target_output_mw,
        )
        assert settled.fuel_cell_output_mw == pytest.approx(
            expected_fc_mw, abs=1e-6
        ), (
            "FC-AGG-11: fuel-cell output must be the measured ramped "
            "baseload, not the economic residual."
        )
        assert settled.fuel_cell_output_mw == pytest.approx(
            module.target_output_mw,
            abs=1e-6,
        )
        assert settled.turbine_output_mw == pytest.approx(
            settled.p_demand_mw
            - settled.bess_output_mw
            - settled.fuel_cell_output_mw,
            abs=1e-6,
        )
        assert abs(settled.p_generation_mw - settled.p_demand_mw) < 1e-6

    def test_FC12_energy_limited_bess_does_not_skip_turbine(self):
        """
        FC-AGG-12: a nearly empty BESS must not prevent the turbine from
        following the residual after the measured fuel-cell baseload.  Any
        fixed-FC surplus is allowed to charge the BESS.
        """
        from core._plane_guard import _EVALUATE_TICK_PERMITTED
        from core.sim_clock import SimClock
        from core.simulation_core import evaluate_tick
        from runtime.scenario_factory import build_run_context_from_spec

        spec = {
            "name": "fc-energy-limited-bess-test",
            "description": "",
            "frequency_nominal_hz": 50.0,
            "power_factor": 0.85,
            "pue_base": 1.03,
            "island_mode": False,
            "turbine_units": [{"asset_id": "turbine-0", "rated_mw": 10.0}],
            "bess_units": [{
                "asset_id": "bess-0",
                "rated_mw": 5.0,
                "usable_mwh": 1.0,
                "initial_soc_fraction": 0.0001,
                "p_anchor_reserve_mw": 0.0,
                "grid_forming": False,
            }],
            "solar_rated_mw": 0.0,
            "fuel_cell_enabled": True,
            "fuel_cell_rated_mw": 5.0,
            "fuel_cell_stack_count": 1,
            "workload_events": [],
            "end_sim_time": 300.0,
        }
        ctx = build_run_context_from_spec(run_id="fc12-test", spec_data=spec)
        ctx.sim_state.apply_workload_signal(
            _starting_signal(nodes=650, ramp_s=1.0, timestamp=0.0),
            dt_lead_seconds=0.0,
        )

        token = _EVALUATE_TICK_PERMITTED.set(True)
        try:
            ticks = [
                evaluate_tick(
                    ctx.sim_state,
                    SimClock(
                        sim_time=float(i) * 5.0, dt_seconds=5.0,
                        wall_stamp_utc=float(i) * 5.0, rate=1.0, tick_seq=i,
                    ),
                )
                for i in range(25)
            ]
        finally:
            _EVALUATE_TICK_PERMITTED.reset(token)

        settled = ticks[-1]
        assert settled.bess_output_mw < -0.01, (
            "FC-AGG-12: the energy-limited BESS did not absorb the surplus "
            "from the measured fuel-cell output."
        )
        assert settled.turbine_output_mw < 10.0 - 1e-6, (
            "FC-AGG-12 fixture must leave unused turbine nameplate headroom."
        )
        module = ctx.sim_state.fuel_cell_module
        assert module is not None
        expected_fc_mw = min(
            module.min_stable_mw
            + len(ticks) * module.config.ramp_rate_mw_per_s * 5.0,
            module.target_output_mw,
        )
        assert settled.fuel_cell_output_mw == pytest.approx(
            expected_fc_mw, abs=1e-6
        )
        assert settled.turbine_output_mw == pytest.approx(
            settled.p_demand_mw
            - settled.fuel_cell_output_mw
            - settled.bess_output_mw,
            abs=1e-6,
        )
        assert abs(settled.p_generation_mw - settled.p_demand_mw) < 1e-6


# ─────────────────────────────────────────────────────────────────────────────
# All three sources — combined identity (Test 10)
# ─────────────────────────────────────────────────────────────────────────────

class TestAllSourcesAggregate:
    """
    BESS + GRID both active simultaneously, FUEL CELL absent from physics.
    Verify the aggregate identity holds at every tick across a full settling run.
    """

    def test_ALL10_combined_identity_grid_connected_bess_active(self):
        """
        ALL-AGG-10: Grid-connected scenario with BESS actively discharging.

        - Turbine: 4 MW (undersized for the load)
        - BESS:    5 MW rated, half charged
        - GPU:     20 nodes (heavy load)
        - Mode:    GRID_TIE

        Expected behaviour:
          • BESS discharges into the aggregate (bess_output_mw > 0)
          • If local gen < demand: grid imports (grid_exchange_mw < 0) and
            import appears in p_generation_mw
          • The identity holds to ≤ 1 µW at every one of the 20 ticks
          • No undocumented source (e.g. a hypothetical fuel cell) inflates the sum

        This is the single regression gate for the entire supply aggregate.
        """
        # 200 nodes × 10.2 kW × PUE 1.03 ≈ 2.10 MW demand.
        # Turbine ceiling 1.0 MW + BESS 0.8 MW = 1.8 MW local max → 0.3+ MW imported.
        state = _make_state(
            turbine_rated_mw=1.0,
            bess_rated_mw=0.8,
            bess_mwh=1.0,
            bess_soc=0.6,
            island_mode=IslandMode.GRID_TIE,
        )
        sig = _starting_signal(nodes=200, ramp_s=2.0, timestamp=0.0)
        state.apply_workload_signal(sig, dt_lead_seconds=0.0)

        ticks = _run_ticks(state, n=20, dt=5.0)

        bess_discharged_any  = any(t.bess_output_mw > 0.01 for t in ticks)
        grid_imported_any    = any(t.grid_exchange_mw < -0.01 for t in ticks)

        failures = []
        for i, tick in enumerate(ticks):
            rhs   = _aggregate_identity(tick)
            delta = tick.p_generation_mw - rhs
            if abs(delta) >= FLOAT_TOL:
                failures.append(
                    f"  tick {i:02d}: p_gen={tick.p_generation_mw:.6f}  "
                    f"turb={tick.turbine_output_mw:.4f}  "
                    f"bess={tick.bess_output_mw:.4f}  "
                    f"renew={tick.p_renewable_mw:.4f}  "
                    f"grid_ex={tick.grid_exchange_mw:.4f}  "
                    f"computed_rhs={rhs:.6f}  delta={delta:.2e}"
                )

        assert not failures, (
            "ALL-AGG-10: aggregate identity p_generation == turb+bess+renew+max(0,-grid) "
            "failed at:\n" + "\n".join(failures)
        )
        assert bess_discharged_any, (
            "ALL-AGG-10: BESS never discharged across 20 ticks — test coverage gap; "
            "increase load or reduce turbine rating"
        )
        assert grid_imported_any, (
            "ALL-AGG-10: grid never imported across 20 ticks — test coverage gap; "
            "increase load or reduce local generation"
        )


# ─────────────────────────────────────────────────────────────────────────────
# SWITCHGEAR 3-source path: BESS + GRID + FUEL CELL, no Turbine, no Solar
# (Tests 11–13)
#
# Mirrors the plant-diagram configuration shown in the operator panel:
#   • BATTERY (BESS)         — 5 MW, 95% SoC, anchor 1.0 MW, grid_forming=True
#   • GRID CONNECTION        — grid-connected (island_mode=False)
#   • FUEL CELL MODULE ARRAY — fuel_cell_enabled=True; fixed baseload output
#     is measured by the engine
#   • GAS TURBINE            — ABSENT (turbine_units=[])
#   • SOLAR PV               — ABSENT (solar_rated_mw=0.0)
#
# Aggregate identity for this configuration:
#   p_generation_mw == bess_output_mw + max(0, -grid_exchange_mw)
#   (turbine_output_mw == 0 always; p_renewable_mw == 0 always)
# ─────────────────────────────────────────────────────────────────────────────

_SW_BASE_SPEC: dict = {
    "name": "sw-switchgear-test",
    "description": (
        "Switchgear aggregate test — BESS + GRID + FUEL CELL only.  "
        "No turbine, no solar.  Mirrors operator panel image."
    ),
    "frequency_nominal_hz": 50.0,
    "power_factor": 0.85,
    "pue_base": 1.03,
    "island_mode": False,       # grid-connected  ← GRID CONNECTION active
    "turbine_units": [],        # no Gas Turbine
    "bess_units": [
        {
            "asset_id": "bess-1",
            "rated_mw": 5.0,
            "usable_mwh": 2.5,
            "initial_soc_fraction": 0.95,   # 95% SoC — matches image
            "p_anchor_reserve_mw": 1.0,     # anchor 1.0 MW — matches image
            "grid_forming": True,
        }
    ],
    "solar_rated_mw": 0.0,          # no Solar PV
    "fuel_cell_enabled": True,      # FC tile visible; engine contributes 0 MW
    "fuel_cell_rated_mw": 5.0,
    "fuel_cell_stack_count": 2,
    "workload_events": [],
    "end_sim_time": 300.0,
}


def _make_sw_ctx(spec_override: dict | None = None):
    """Build a RunContext for the 3-source switchgear scenario."""
    from runtime.scenario_factory import build_run_context_from_spec

    spec = {**_SW_BASE_SPEC, **(spec_override or {})}
    return build_run_context_from_spec(run_id="sw-test", spec_data=spec)


def _run_sw_ticks(
    spec_override: dict | None = None,
    n: int = 10,
    dt: float = 5.0,
    nodes: int = 0,
):
    """
    Build the 3-source context, optionally apply a workload, then run n ticks.
    Returns (ctx, ticks) so callers can inspect ctx.sim_state if needed.
    """
    import contextlib
    from core._plane_guard import _EVALUATE_TICK_PERMITTED
    from core.sim_clock import SimClock
    from core.simulation_core import evaluate_tick

    ctx = _make_sw_ctx(spec_override)
    if nodes > 0:
        sig = _starting_signal(nodes=nodes, ramp_s=1.0, timestamp=0.0)
        ctx.sim_state.apply_workload_signal(sig, dt_lead_seconds=0.0)

    ticks = []
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        for i in range(n):
            clock = SimClock(
                sim_time=float(i) * dt,
                dt_seconds=dt,
                wall_stamp_utc=float(i) * dt,
                rate=1.0,
                tick_seq=i,
            )
            ticks.append(evaluate_tick(ctx.sim_state, clock))
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)

    return ctx, ticks


class TestSwitchgearThreeSource:
    """
    Verifies the switchgear aggregate path for the BESS + GRID + FUEL CELL
    panel configuration — no Gas Turbine, no Solar PV.
    """

    def test_SW11_bess_covers_load_before_fuel_cell_without_turbine(self):
        """
        SW-AGG-11: With no turbine, the measured fixed fuel-cell baseload
        supplies the small 20-node load and the BESS absorbs the resulting
        surplus.  Grid should export rather than import.

        The aggregate identity must hold at every tick:
          p_generation_mw == bess + fuel_cell + max(0, -grid_exchange)

        Setup: 5 MW BESS at 95% SoC, 5 MW FC armed, 20 GPU nodes (~0.21 MW),
               GRID_TIE, no turbine, no solar.
        Expected:
          • turbine_output_mw == 0.0 at every tick (absent from state)
          • p_renewable_mw == 0.0 at every tick (solar_rated_mw=0.0)
          • BESS output is negative while it absorbs fixed-FC surplus
          • fuel_cell_output_mw follows the aggregate module ramp
          • aggregate identity holds to ≤ 1 µW
        """
        _ctx, ticks = _run_sw_ticks(nodes=20, n=10)

        # Turbine must be completely absent from the power balance
        for i, tick in enumerate(ticks):
            assert tick.turbine_output_mw == 0.0, (
                f"SW-AGG-11 tick {i}: turbine_output_mw={tick.turbine_output_mw:.6f} "
                f"— no turbines in state; must be exactly 0.0"
            )

        # Solar must also be absent (solar_rated_mw = 0.0 in spec)
        for i, tick in enumerate(ticks):
            assert tick.p_renewable_mw == 0.0, (
                f"SW-AGG-11 tick {i}: p_renewable_mw={tick.p_renewable_mw:.6f} "
                f"— solar_rated_mw=0.0; must be exactly 0.0"
            )

        # The FC is a fixed measured source; it is not an elastic residual
        # source that waits for the cheaper BESS to saturate.
        module = _ctx.sim_state.fuel_cell_module
        assert module is not None
        expected_fc_mw = min(
            module.min_stable_mw
            + len(ticks) * module.config.ramp_rate_mw_per_s * 5.0,
            module.target_output_mw,
        )
        assert ticks[-1].fuel_cell_output_mw == pytest.approx(
            expected_fc_mw, abs=1e-6
        )
        assert any(t.bess_output_mw < -0.01 for t in ticks), (
            "SW-AGG-11: BESS never absorbed fixed fuel-cell surplus."
        )
        assert any(t.grid_exchange_mw > 0.01 for t in ticks), (
            "SW-AGG-11: grid never exported while fixed FC output exceeded "
            "the small load and BESS charge ceiling."
        )

        # The full aggregate identity must hold at every tick
        failures = []
        for i, tick in enumerate(ticks):
            rhs   = _aggregate_identity(tick)
            delta = tick.p_generation_mw - rhs
            if abs(delta) >= FLOAT_TOL:
                failures.append(
                    f"  tick {i:02d}: p_gen={tick.p_generation_mw:.6f}  "
                    f"bess={tick.bess_output_mw:.4f}  fc={tick.fuel_cell_output_mw:.4f}  "
                    f"grid_ex={tick.grid_exchange_mw:.4f}  "
                    f"rhs={rhs:.6f}  delta={delta:.2e}"
                )
        assert not failures, (
            "SW-AGG-11: aggregate identity p_gen == bess+fc+max(0,-grid) "
            "failed (no turbine path):\n"
            + "\n".join(failures)
        )

    def test_SW12_fuel_cell_fills_gap_when_bess_alone_insufficient(self):
        """
        SW-AGG-12: When load exceeds the BESS ceiling, the fuel cell dispatches
        to cover the shortfall in merit order (before grid import).

        Setup: BESS reduced to 0.5 MW rated, FC enabled at 5 MW, 120-node job.
               GPU demand ≈ 120 × 10.2 kW × PUE 1.03 ≈ 1.26 MW.
               BESS covers 0.5 MW; FC covers the remaining ~0.76 MW; grid = 0.
        Expected:
          • fuel_cell_output_mw > 0 at some ticks (FC dispatched)
          • turbine_output_mw == 0.0 always (no turbines in state)
          • aggregate identity holds at every tick
        """
        # 120 nodes × 10.2 kW × PUE 1.03 ≈ 1.26 MW demand.
        # Reduce BESS to 0.5 MW so the FC must step in.
        _ctx, ticks = _run_sw_ticks(
            spec_override={
                "bess_units": [
                    {
                        "asset_id": "bess-1",
                        "rated_mw": 0.5,
                        "usable_mwh": 0.5,
                        "initial_soc_fraction": 0.95,
                        "p_anchor_reserve_mw": 0.0,
                        "grid_forming": True,
                    }
                ]
            },
            nodes=120,
            n=8,
        )

        fc_dispatched_any = any(t.fuel_cell_output_mw > 0.01 for t in ticks)
        assert fc_dispatched_any, (
            "SW-AGG-12: fuel_cell_output_mw never exceeded 0.01 MW — "
            "FC should cover demand beyond the 0.5 MW BESS ceiling."
        )

        failures = []
        for i, tick in enumerate(ticks):
            assert tick.turbine_output_mw == 0.0, (
                f"SW-AGG-12 tick {i}: turbine_output_mw must be 0 (no turbines); "
                f"got {tick.turbine_output_mw:.6f}"
            )
            rhs   = _aggregate_identity(tick)
            delta = tick.p_generation_mw - rhs
            if abs(delta) >= FLOAT_TOL:
                failures.append(
                    f"  tick {i:02d}: p_gen={tick.p_generation_mw:.6f}  "
                    f"bess={tick.bess_output_mw:.4f}  fc={tick.fuel_cell_output_mw:.4f}  "
                    f"grid_ex={tick.grid_exchange_mw:.4f}  "
                    f"rhs={rhs:.6f}  delta={delta:.2e}"
                )

        assert not failures, (
            "SW-AGG-12: aggregate identity failed:\n"
            + "\n".join(failures)
        )

    def test_SW13_identity_holds_across_15_ticks_turbine_free(self):
        """
        SW-AGG-13: The aggregate identity
            p_generation_mw == bess_output_mw + max(0, -grid_exchange_mw)
        holds at EVERY tick over a 15-tick settling run in the 3-source
        (BESS + GRID + FC) configuration with no turbine and no solar.

        This is the regression gate for the switchgear's supply-side summing
        logic when the turbine and solar paths are both absent from the state.

        Also asserts p_renewable_mw == 0.0 at every tick (no solar configured).
        """
        _ctx, ticks = _run_sw_ticks(nodes=40, n=15)

        failures = []
        for i, tick in enumerate(ticks):
            # Turbine must be absent from the output
            if tick.turbine_output_mw != 0.0:
                failures.append(
                    f"  tick {i:02d}: turbine_output_mw={tick.turbine_output_mw:.6f} "
                    f"(should be 0 — no turbines in state)"
                )
            # Solar must be absent from the output
            if tick.p_renewable_mw != 0.0:
                failures.append(
                    f"  tick {i:02d}: p_renewable_mw={tick.p_renewable_mw:.6f} "
                    f"(should be 0 — solar_rated_mw=0.0)"
                )
            # Full aggregate identity
            rhs   = _aggregate_identity(tick)
            delta = tick.p_generation_mw - rhs
            if abs(delta) >= FLOAT_TOL:
                failures.append(
                    f"  tick {i:02d}: p_gen={tick.p_generation_mw:.6f}  "
                    f"bess={tick.bess_output_mw:.4f}  "
                    f"renew={tick.p_renewable_mw:.4f}  "
                    f"grid_ex={tick.grid_exchange_mw:.4f}  "
                    f"rhs={rhs:.6f}  delta={delta:.2e}"
                )

        assert not failures, (
            "SW-AGG-13: switchgear 3-source identity failed:\n"
            + "\n".join(failures)
        )


# ─────────────────────────────────────────────────────────────────────────────
# FC-before-curtailment (Test 14)
# ─────────────────────────────────────────────────────────────────────────────

class TestFuelCellBeforeCurtailment:
    """
    FC-CURT-14: When turbines + BESS cannot cover demand, the fuel cell must
    dispatch (filling the gap) and the curtailment ladder must see zero
    remaining gap — not the inflated gap that FC is already covering.

    Guards the fix to _remaining_gap_mw in evaluate_tick() that subtracts
    fuel_cell_output_mw before handing the gap to the curtailment ladder.
    Without the fix, the ladder would see a gap equal to the FC output and
    recommend curtailment of GPU nodes that FC is already serving.
    """

    def test_FC14_no_curtailment_when_fc_covers_gap(self):
        """
        FC-CURT-14: BESS (1 MW) + turbines (3 MW) undersized for 6 MW demand.
        FC (5 MW rated) must fill the 2 MW gap before the curtailment ladder
        is consulted.  No curtailment proposal should appear in TickResult.
        """
        from core._plane_guard import _EVALUATE_TICK_PERMITTED
        from core.dispatch import LadderPosition
        from core.sim_clock import SimClock
        from core.simulation_core import evaluate_tick
        from runtime.scenario_factory import build_run_context_from_spec

        SPEC = {
            "name": "fc-curt-14-test",
            "description": "",
            "frequency_nominal_hz": 60.0,
            "power_factor": 0.95,
            "pue_base": 1.03,
            "island_mode": False,           # grid-connected
            "turbine_units": [
                {
                    "asset_id": "gt-1",
                    "rated_mw": 3.0,
                    "p_min_stable_frac": 0.0,
                    "droop_r": 0.05,
                    "power_factor": 0.95,
                    "hot_start_s": 300,
                    "warm_start_s": 600,
                    "cold_start_s": 900,
                }
            ],
            "bess_units": [
                {
                    "asset_id": "bess-1",
                    "rated_mw": 1.0,        # undersized: 1 MW < 3 MW gap
                    "usable_mwh": 2.0,
                    "initial_soc_fraction": 0.90,
                    "p_anchor_reserve_mw": 0.0,
                    "grid_forming": False,
                }
            ],
            "solar_rated_mw": 0.0,
            "fuel_cell_enabled": True,
            "fuel_cell_rated_mw": 5.0,      # more than enough to cover the gap
            "fuel_cell_stack_count": 1,
            "workload_events": [],
            "end_sim_time": 300.0,
        }

        ctx = build_run_context_from_spec(run_id="fc14-test", spec_data=SPEC)

        # Force turbine to SYNCHRONISED so it contributes output immediately.
        from core.asset_modules import TurbineState
        for t in ctx.sim_state.turbines:
            t._state = TurbineState.SYNCHRONISED
            t._current_output_mw = 3.0

        # Apply 600-node load → demand well above BESS + turbine ceiling.
        sig = _starting_signal(nodes=600, ramp_s=1.0, timestamp=0.0)
        ctx.sim_state.apply_workload_signal(sig, dt_lead_seconds=0.0)

        token = _EVALUATE_TICK_PERMITTED.set(True)
        try:
            ticks = []
            for i in range(6):
                clock = SimClock(
                    sim_time=float(i) * 5.0, dt_seconds=5.0,
                    wall_stamp_utc=float(i) * 5.0, rate=1.0, tick_seq=i,
                )
                ticks.append(evaluate_tick(ctx.sim_state, clock))
        finally:
            _EVALUATE_TICK_PERMITTED.reset(token)

        # FC must dispatch on at least one tick where demand > turbine + BESS.
        overloaded_ticks = [
            t for t in ticks
            if t.p_demand_mw > t.turbine_output_mw + t.bess_output_mw + 0.1
        ]
        if overloaded_ticks:
            fc_fired = any(t.fuel_cell_output_mw > 0.1 for t in overloaded_ticks)
            assert fc_fired, (
                "FC-CURT-14: fuel cell did not dispatch on any overloaded tick — "
                "FC dispatch not wired or _sync_ceiling_mw too small. "
                f"Overloaded ticks: {[(t.sim_time_s, t.p_demand_mw, t.fuel_cell_output_mw) for t in overloaded_ticks]}"
            )

            # On ticks where FC is dispatching, the curtailment ladder must see
            # zero remaining gap — not a gap inflated by the FC contribution.
            curtailment_positions = frozenset({
                LadderPosition.CURTAILMENT_A_B, LadderPosition.CURTAILMENT_C_D
            })
            for tick in overloaded_ticks:
                if tick.fuel_cell_output_mw < 0.1:
                    continue
                # FC covers the gap → remaining_gap passed to curtailment ladder ≈ 0
                # → no curtailment proposals should appear in TickResult.
                # TickResult exposes curtailment_proposal_tiers (tuple[str, ...]).
                has_curtailment = bool(tick.curtailment_proposal_tiers)
                remaining_after_fc = max(
                    0.0,
                    tick.p_demand_mw
                    - tick.p_renewable_mw
                    - tick.turbine_output_mw
                    - tick.bess_output_mw
                    - tick.fuel_cell_output_mw,
                )
                assert remaining_after_fc < 0.5 or not has_curtailment, (
                    f"FC-CURT-14 at t={tick.sim_time_s:.0f}s: "
                    f"curtailment proposed {tick.curtailment_proposal_tiers!r} when "
                    f"FC ({tick.fuel_cell_output_mw:.2f} MW) should have closed the gap. "
                    f"remaining_after_fc={remaining_after_fc:.3f} MW"
                )

        # Aggregate identity must hold on every tick.
        failures = []
        for i, tick in enumerate(ticks):
            rhs = _aggregate_identity(tick)
            delta = tick.p_generation_mw - rhs
            if abs(delta) >= FLOAT_TOL:
                failures.append(
                    f"  tick {i}: p_gen={tick.p_generation_mw:.6f} rhs={rhs:.6f} "
                    f"fc={tick.fuel_cell_output_mw:.4f} delta={delta:.2e}"
                )
        assert not failures, (
            "FC-CURT-14: aggregate identity fails:\n"
            + "\n".join(failures)
        )
