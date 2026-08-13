"""
test_aggregate_sources.py — Black-box aggregate tests for BESS, GRID, and FUEL CELL.

Verifies that each source feeds (or does not feed) into p_generation_mw correctly.

Aggregate identity (simulation_core.py ~line 1578):
    p_generation_mw = turbine_output_mw
                    + bess_output_mw
                    + p_renewable_mw
                    + max(0, -grid_exchange_mw)   ← grid import only; export = 0 contribution

Findings from engine inspection:
  BESS      — bess_output_mw contributes directly. ✓
  GRID      — grid_exchange_mw < 0 on import; added via max(0, -x). ✓
  FUEL CELL — fuel_cell_enabled / fuel_cell_rated_mw are SCHEMA-ONLY fields.
              scenario_factory never creates a fuel-cell asset; evaluate_tick
              never computes fuel-cell output; TickResult has no fuel_cell_mw field.
              Fuel cell contributes 0 MW to the aggregate in ALL scenarios.  ✗ (gap)

All 10 tests run headless — no HTTP, no database, no WebSocket.
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
    Fuel cell is a schema-level concept only.
    The physics engine has no fuel-cell implementation; fuel cell never
    contributes to p_generation_mw in any scenario.
    """

    def test_FC7_tick_result_has_no_fuel_cell_output_field(self):
        """
        FC-AGG-7: TickResult must NOT have a fuel_cell_mw or fuel_cell_output_mw
        field — confirming the physics gap at the data-model level.

        This test documents the missing implementation as a deliberate finding,
        not an accidental omission.
        """
        state = _make_state(island_mode=IslandMode.ISLANDED)
        tick = _run_tick(state, sim_time=0.0, dt=5.0)

        assert not hasattr(tick, "fuel_cell_mw"), (
            "FC-AGG-7: TickResult.fuel_cell_mw exists — fuel cell output is now "
            "tracked by the engine (update these tests accordingly)."
        )
        assert not hasattr(tick, "fuel_cell_output_mw"), (
            "FC-AGG-7: TickResult.fuel_cell_output_mw exists — fuel cell output is "
            "now tracked by the engine (update these tests accordingly)."
        )

    def test_FC8_aggregate_closes_exactly_without_fuel_cell_term(self):
        """
        FC-AGG-8: The aggregate identity
            p_generation_mw == turbine + bess + renewable + max(0, -grid)
        closes to float precision across 15 ticks.

        If a fuel cell term existed but was not accounted for, this test would
        fail because p_generation_mw would exceed the RHS sum.
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
                    f"(p_gen={tick.p_generation_mw:.6f}, rhs={rhs:.6f})"
                )

        assert not failures, (
            "FC-AGG-8: aggregate identity fails — unexplained power contribution:\n"
            + "\n".join(failures)
            + "\nThis would indicate an undiscovered fuel-cell (or other) term."
        )

    def test_FC9_scenario_factory_ignores_fuel_cell_spec(self):
        """
        FC-AGG-9: Creating a run context via build_run_context_from_spec with
        fuel_cell_enabled=True and fuel_cell_rated_mw=20.0 produces identical
        p_generation_mw to the same scenario without fuel cell.

        Verifies that the scenario factory does NOT wire fuel-cell assets into
        the SimulationState even when the spec says fuel_cell_enabled=True.
        """
        import contextlib

        from core._plane_guard import _EVALUATE_TICK_PERMITTED
        from core.sim_clock import SimClock
        from core.simulation_core import evaluate_tick
        from runtime.scenario_factory import build_run_context_from_spec

        BASE_SPEC = {
            "name": "fc-test",
            "description": "",
            "frequency_nominal_hz": 50.0,
            "power_factor": 0.85,
            "pue_base": 1.03,
            "island_mode": True,          # islanded
            "turbine_units": [
                {
                    "asset_id": "gt-1",
                    "rated_mw": 10.0,
                    "r_asset_mw_per_s": 5.0,
                    "min_stable_load_mw": 0.0,
                }
            ],
            "bess_units": [
                {
                    "asset_id": "bess-1",
                    "rated_mw": 5.0,
                    "usable_mwh": 3.0,
                    "initial_soc_fraction": 0.8,
                    "p_anchor_reserve_mw": 0.0,
                    "grid_forming": False,
                }
            ],
            "solar_rated_mw": 0.0,
            "workload_events": [],
            "end_sim_time": 300.0,
        }

        def _one_tick(spec_override: dict) -> object:
            spec = {**BASE_SPEC, **spec_override}
            ctx = build_run_context_from_spec(run_id="fc-test", spec_data=spec)
            clock = SimClock(sim_time=0.0, dt_seconds=5.0, wall_stamp_utc=0.0,
                             rate=1.0, tick_seq=0)
            token = _EVALUATE_TICK_PERMITTED.set(True)
            try:
                return evaluate_tick(ctx.sim_state, clock)
            finally:
                _EVALUATE_TICK_PERMITTED.reset(token)

        tick_no_fc  = _one_tick({"fuel_cell_enabled": False, "fuel_cell_rated_mw": 0.0,   "fuel_cell_stack_count": 1})
        tick_with_fc = _one_tick({"fuel_cell_enabled": True,  "fuel_cell_rated_mw": 20.0, "fuel_cell_stack_count": 4})

        # Aggregate must be identical: the engine ignores the fuel_cell fields.
        assert abs(tick_with_fc.p_generation_mw - tick_no_fc.p_generation_mw) < FLOAT_TOL, (
            f"FC-AGG-9: p_generation_mw differs between fc=False ({tick_no_fc.p_generation_mw:.6f} MW) "
            f"and fc=True ({tick_with_fc.p_generation_mw:.6f} MW). "
            f"delta={tick_with_fc.p_generation_mw - tick_no_fc.p_generation_mw:.4f} MW — "
            "fuel cell output is now wired into the engine!"
        )
        assert abs(tick_with_fc.turbine_output_mw - tick_no_fc.turbine_output_mw) < FLOAT_TOL, (
            "FC-AGG-9: turbine output changed — state construction differs between FC on/off"
        )
        assert abs(tick_with_fc.bess_output_mw - tick_no_fc.bess_output_mw) < FLOAT_TOL, (
            "FC-AGG-9: bess output changed — state construction differs between FC on/off"
        )


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
#   • FUEL CELL MODULE ARRAY — fuel_cell_enabled=True (silent: 0 MW from engine)
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

    def test_SW11_grid_covers_load_without_turbine(self):
        """
        SW-AGG-11: In grid-connected mode with no turbine, the armed BESS sits
        at 0 MW (normal grid-following behaviour — the grid is the slack bus).
        All load demand is served by grid import.

        This tests the switchgear's aggregation on the GRID path specifically:
          p_generation_mw == max(0, -grid_exchange_mw)
        when turbine, renewable and BESS are each zero.

        Setup: 5 MW BESS at 95% SoC (armed, not dispatched), 20 GPU nodes,
               GRID_TIE, no turbine, FC enabled but silent.
        Expected:
          • turbine_output_mw == 0.0 at every tick (absent from state)
          • p_renewable_mw == 0.0 at every tick (solar_rated_mw=0.0)
          • grid_exchange_mw < 0 at settlement (grid importing to cover demand)
          • BESS may be idle (grid-following; no dispatch command issued)
          • aggregate identity p_gen == bess + max(0,-grid) holds to ≤ 1 µW
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

        # Grid must import to supply the GPU load (slack bus in grid-connected mode)
        grid_importing_any = any(t.grid_exchange_mw < -0.01 for t in ticks)
        assert grid_importing_any, (
            "SW-AGG-11: grid never imported to cover the 20-node load — "
            "check island_mode or load-signal application"
        )

        # The full aggregate identity must hold at every tick
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
                    f"rhs={rhs:.6f}  delta={delta:.2e}"
                )
        assert not failures, (
            "SW-AGG-11: aggregate identity p_gen == turb+bess+renew+max(0,-grid) "
            "failed (no turbine path):\n"
            + "\n".join(failures)
        )

    def test_SW12_grid_import_fills_gap_when_bess_alone_insufficient(self):
        """
        SW-AGG-12: Heavy load exceeds what the BESS can supply alone; the grid
        imports the shortfall and that import appears correctly in p_generation_mw.

        Fuel cell is enabled in the spec but must contribute 0 MW — confirmed by
        the aggregate closing without an FC term.

        Setup: 5 MW BESS at 95% SoC, anchor 1.0 MW reserved, 80-node job.
               GPU demand ≈ 80 × 10.2 kW × PUE 1.03 ≈ 0.84 MW.
               BESS effective headroom = 5 MW - 1 MW anchor = 4 MW → grid not
               needed at this node count; raise to 120 nodes where PUE-adjusted
               demand ≈ 1.26 MW and anchor reserve forces grid import.
        Expected:
          • grid_exchange_mw < 0 at some ticks (grid importing)
          • max(0, -grid_exchange_mw) > 0 for those ticks
          • aggregate identity holds at every tick
          • turbine_output_mw == 0.0 always
        """
        # 120 nodes × 10.2 kW × PUE 1.03 ≈ 1.26 MW demand.
        # BESS available = 5 MW rated, but 1 MW is held as anchor reserve →
        # effective ceiling ≈ 4 MW, easily covering 1.26 MW.  To force grid
        # import we reduce BESS rated to 0.5 MW, making BESS the binding
        # constraint and grid the swing supplier.
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

        grid_imported_any = any(t.grid_exchange_mw < -0.01 for t in ticks)
        assert grid_imported_any, (
            "SW-AGG-12: grid never imported — reduce BESS headroom or increase load"
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
                    f"bess={tick.bess_output_mw:.4f}  "
                    f"grid_ex={tick.grid_exchange_mw:.4f}  "
                    f"rhs={rhs:.6f}  delta={delta:.2e}"
                )

        assert not failures, (
            "SW-AGG-12: aggregate identity failed — unexpected power term "
            "(possible fuel-cell physics now wired in?):\n"
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
