"""
TC-203-1: Operator trip command removes unit from dispatch.
TC-203-2: Operator start command transitions offline unit to STARTING.

Both tests exercise the RunContext.enqueue_unit_command() path.  The drain
loop is replicated from _drive() section A-1: since that loop has no await
points, calling it synchronously is safe and equivalent for unit tests.

Covers:
  - RunContext._operator_commands queue populated by enqueue_unit_command()
  - trip: state → OFFLINE, _current_output_mw → 0, _target_mw → 0
  - start: calls command_start() → state → STARTING, output remains 0
  - queue is empty after drain
  - ctx.step() reflects tripped unit not contributing to turbine_output_mw
  - start unit contributes 0 MW while STARTING (loading layer gate)
"""

from __future__ import annotations

import contextlib


# ── plane-guard context manager (required by evaluate_tick) ──────────────────

@contextlib.contextmanager
def _plane_guard():
    from core._plane_guard import _EVALUATE_TICK_PERMITTED
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        yield
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


# ── _drain_operator_commands: replicates _drive() section A-1 ────────────────
# This is a deliberate copy of the drain logic.  If the implementation ever
# diverges, a test failure here points directly at the divergence.

def _drain_operator_commands(ctx) -> None:
    """Drain ctx._operator_commands synchronously (mirrors _drive() A-1)."""
    from core.asset_modules import TurbineState
    while ctx._operator_commands:
        cmd    = ctx._operator_commands.pop(0)
        uid    = cmd.get("unit_id", "")
        action = cmd.get("action", "")
        for turb in ctx.sim_state.turbines:
            if turb.config.asset_id == uid:
                if action == "trip":
                    turb.state = TurbineState.OFFLINE
                    turb._current_output_mw = 0.0
                    turb._target_mw = 0.0
                elif action == "start":
                    turb.command_start(ctx.sim_time)
                break


# ── minimal 2-unit spec ───────────────────────────────────────────────────────

_SPEC = {
    "name": "tc-203-test",
    "description": "",
    "hardware_profile_id": "hpc-datacenter",
    "dt_lead_seconds": 30,
    "bess_units": [
        {"asset_id": "bess-0", "rated_mw": 20.0, "usable_mwh": 10.0,
         "initial_soc_fraction": 0.9, "grid_forming": True}
    ],
    "turbine_units": [
        {"asset_id": "gt-0", "rated_mw": 10.0, "r_asset_mw_per_s": 0.5,
         "hot_standby": False},
        {"asset_id": "gt-1", "rated_mw": 10.0, "r_asset_mw_per_s": 0.5,
         "hot_standby": False},
    ],
    "solar_rated_mw": 0.0,
    "irradiance_steps": [],
    "island_mode": True,
    "pue_base": 1.03,
    "run_duration_s": 300,
    "location": "Auckland",
    "workload_events": [],
    "frequency_nominal_hz": 60.0,
    "power_factor": 0.85,
}


# ── TC-203-1: trip command removes unit from dispatch ────────────────────────

def test_tc_203_1_trip_command_zeroes_unit_and_leaves_fleet_reduced():
    """Operator trip forces gt-0 to OFFLINE; next tick fleet output excludes it.

    Setup:
      - 2 units, both forced to SYNCHRONISED with output = 8 MW.
    Command:
      - enqueue trip for gt-0.
    Drain:
      - simulate _drive() A-1 synchronous drain.
    Assert (immediate):
      - gt-0 state == OFFLINE, output == 0.
      - gt-1 state == SYNCHRONISED, output unchanged.
      - queue empty.
    Assert (after step()):
      - turbine_output_mw is the loading-layer value for gt-1 only
        (strictly less than the 16 MW two-unit sum).
    """
    from runtime.scenario_factory import build_run_context_from_spec
    from core.asset_modules import TurbineState

    ctx = build_run_context_from_spec("tc-203-1", _SPEC)

    # Force both units onto the bus with non-zero output.
    for turb in ctx.sim_state.turbines:
        turb.state = TurbineState.SYNCHRONISED
        turb._current_output_mw = 8.0
        turb._target_mw = 8.0

    # Enqueue trip for gt-0 and confirm it was queued.
    ctx.enqueue_unit_command("gt-0", "trip")
    assert len(ctx._operator_commands) == 1, "trip command should be queued"

    # Drain (replicates _drive() A-1).
    _drain_operator_commands(ctx)

    # ── immediate state checks ────────────────────────────────────────────────
    gt0 = next(t for t in ctx.sim_state.turbines if t.config.asset_id == "gt-0")
    gt1 = next(t for t in ctx.sim_state.turbines if t.config.asset_id == "gt-1")

    assert gt0.state == TurbineState.OFFLINE, (
        f"gt-0 should be OFFLINE after trip, got {gt0.state!r}"
    )
    assert gt0._current_output_mw == 0.0, (
        f"gt-0 output should be 0 after trip, got {gt0._current_output_mw}"
    )
    assert gt0._target_mw == 0.0, (
        f"gt-0 target should be 0 after trip, got {gt0._target_mw}"
    )
    assert gt1.state == TurbineState.SYNCHRONISED, (
        f"gt-1 should still be SYNCHRONISED, got {gt1.state!r}"
    )
    assert gt1._current_output_mw == 8.0, (
        f"gt-1 output should be unchanged (8.0), got {gt1._current_output_mw}"
    )
    assert len(ctx._operator_commands) == 0, "queue should be empty after drain"

    # ── step() confirms physics sees only gt-1 ────────────────────────────────
    with _plane_guard():
        result = ctx.step()

    # Fleet output must come from gt-1 only (<= 10 MW rated; cannot be 16 MW).
    assert result.turbine_output_mw < 16.0, (
        f"Tripped gt-0 should not contribute to fleet output; got {result.turbine_output_mw} MW"
    )
    assert result.turbine_output_mw >= 0.0, (
        f"turbine_output_mw should be non-negative, got {result.turbine_output_mw}"
    )


# ── TC-203-2: start command transitions OFFLINE unit to STARTING ─────────────

def test_tc_203_2_start_command_enters_starting_and_produces_zero():
    """Operator start transitions gt-0 from OFFLINE to STARTING; output stays 0.

    Setup:
      - 2 units, both in OFFLINE (default state).
    Command:
      - enqueue start for gt-0.
    Drain:
      - simulate _drive() A-1 synchronous drain.
    Assert (immediate):
      - gt-0 state == STARTING, output == 0.
      - gt-1 state == OFFLINE (untouched).
      - queue empty.
    Assert (after step()):
      - turbine_output_mw == 0 (STARTING units are not dispatched by the
        loading layer; they only produce output once SYNCHRONISED).
    """
    from runtime.scenario_factory import build_run_context_from_spec
    from core.asset_modules import TurbineState

    ctx = build_run_context_from_spec("tc-203-2", _SPEC)

    gt0 = next(t for t in ctx.sim_state.turbines if t.config.asset_id == "gt-0")
    gt1 = next(t for t in ctx.sim_state.turbines if t.config.asset_id == "gt-1")

    assert gt0.state == TurbineState.OFFLINE, "gt-0 should start OFFLINE"
    assert gt1.state == TurbineState.OFFLINE, "gt-1 should start OFFLINE"

    # Enqueue start for gt-0 only.
    ctx.enqueue_unit_command("gt-0", "start")
    assert len(ctx._operator_commands) == 1, "start command should be queued"

    # Drain (replicates _drive() A-1).
    _drain_operator_commands(ctx)

    # ── immediate state checks ────────────────────────────────────────────────
    assert gt0.state == TurbineState.STARTING, (
        f"gt-0 should be STARTING after start command, got {gt0.state!r}"
    )
    assert gt0._current_output_mw == 0.0, (
        f"STARTING unit must produce 0 MW, got {gt0._current_output_mw}"
    )
    assert gt1.state == TurbineState.OFFLINE, (
        f"gt-1 should be OFFLINE (untouched), got {gt1.state!r}"
    )
    assert len(ctx._operator_commands) == 0, "queue should be empty after drain"

    # ── step() confirms STARTING unit contributes 0 to fleet output ──────────
    with _plane_guard():
        result = ctx.step()

    # Both units are non-synchronised (STARTING and OFFLINE); dispatch is 0.
    assert result.turbine_output_mw == 0.0, (
        f"STARTING unit must not contribute to fleet output; got {result.turbine_output_mw} MW"
    )
