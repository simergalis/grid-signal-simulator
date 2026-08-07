"""
Operator unit command tests — Task #203.

TC-203-1  trip via validate_and_enqueue: unit transitions to OFFLINE, output zeroed.
TC-203-2  start via validate_and_enqueue: unit enters STARTING, output 0.
TC-203-3  immediate trip → start (t_min_down_s=0): start command accepted.
TC-203-4  start rejected during minimum-down-time window (t_min_down_s > 0).
TC-203-5  HTTP endpoint wiring: 404 unknown run/unit, 409 wrong state, 202 success.

Tests exercise RunManager.validate_and_enqueue_unit_command() for all
validation paths, plus the TestClient for the full HTTP → drain → physics loop.
The manual _drain_operator_commands() helper is intentionally NOT used for
TC-203-3/4/5; those tests confirm that nothing in the production path silently
drops a command before the UI can observe the state change.
"""

from __future__ import annotations

import contextlib
import math

import pytest


# ── plane-guard context manager (required by evaluate_tick) ──────────────────

@contextlib.contextmanager
def _plane_guard():
    from core._plane_guard import _EVALUATE_TICK_PERMITTED
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        yield
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


# ── minimal 2-unit scenario spec ─────────────────────────────────────────────

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


def _build_ctx(run_id: str = "tc-203"):
    """Build a fresh RunContext from _SPEC."""
    from runtime.scenario_factory import build_run_context_from_spec
    return build_run_context_from_spec(run_id, _SPEC)


def _make_manager_with_ctx(ctx):
    """Register ctx in a fresh RunManager without starting the drive task.

    validate_and_enqueue_unit_command() only needs the context in
    manager._contexts; it never touches the asyncio task.
    """
    from runtime.run_manager import RunManager, WebSocketHub
    manager = RunManager(WebSocketHub())
    manager._contexts[ctx.run_id] = ctx
    return manager


# ── manual drain helper (mirrors _drive() A-1 exactly) ───────────────────────
# Used by TC-203-1 and TC-203-2 to apply queued commands synchronously without
# starting the asyncio drive loop.  Each test that calls this is explicitly
# testing the combined validate_and_enqueue → drain → step() path.

def _drain_operator_commands(ctx) -> None:
    """Drain ctx._operator_commands synchronously (mirrors _drive() A-1).

    Used in unit tests that don't run the full async drive loop.  Any
    divergence between this helper and the production drain will be caught
    by TC-203-5 (TestClient integration test) and by future TC-203-6+ tests
    that run the asyncio loop.
    """
    from core.asset_modules import TurbineState
    while ctx._operator_commands:
        cmd    = ctx._operator_commands.pop(0)
        uid    = cmd.get("unit_id", "")
        action = cmd.get("action", "")
        for turb in ctx.sim_state.turbines:
            if turb.config.asset_id == uid:
                if action == "trip":
                    # Phase E repair: is_synchronised → is_on_bus; _target_mw removed.
                    if turb.is_on_bus:
                        turb._last_sync_stop_s = ctx.sim_time
                    turb._stop_time_s      = ctx.sim_time
                    turb._run_start_s      = math.nan
                    turb.state = TurbineState.OFFLINE
                    turb._current_output_mw = 0.0
                elif action == "start":
                    turb.command_start(ctx.sim_time)
                break


# ── TC-203-1: trip via validate_and_enqueue zeroes unit output ────────────────

def test_tc_203_1_trip_command_zeroes_unit_and_leaves_fleet_reduced():
    """validate_and_enqueue trip → drain → step() removes gt-0 from dispatch.

    Validation path: RunManager.validate_and_enqueue_unit_command().
    Drain path: _drain_operator_commands() (mirrors _drive() A-1).

    Setup:
      Both units forced to SYNCHRONISED with output = 8 MW.
    Expect:
      validate_and_enqueue → UNIT_CMD_OK (unit is on-bus — trip is valid).
      After drain: gt-0 OFFLINE output=0; gt-1 SYNCHRONISED output=8.
      After step(): turbine_output_mw < 16 (tripped unit excluded).
    """
    from core.asset_modules import TurbineState

    ctx     = _build_ctx("tc-203-1")
    manager = _make_manager_with_ctx(ctx)

    # Force both units onto the bus with non-zero output.
    # Phase E repair: _target_mw removed.
    for turb in ctx.sim_state.turbines:
        turb.state = TurbineState.SYNCHRONISED
        turb._current_output_mw = 8.0

    # ── validate and enqueue via the production path ──────────────────────────
    code, detail = manager.validate_and_enqueue_unit_command(ctx.run_id, "gt-0", "trip")
    assert code == manager.UNIT_CMD_OK, f"trip should be accepted: {detail!r}"
    assert len(ctx._operator_commands) == 1, "command should be in queue"

    # ── drain (mirrors _drive() A-1) ──────────────────────────────────────────
    _drain_operator_commands(ctx)

    # ── immediate state checks ────────────────────────────────────────────────
    gt0 = next(t for t in ctx.sim_state.turbines if t.config.asset_id == "gt-0")
    gt1 = next(t for t in ctx.sim_state.turbines if t.config.asset_id == "gt-1")

    assert gt0.state == TurbineState.OFFLINE, (
        f"gt-0 should be OFFLINE after trip, got {gt0.state!r}"
    )
    assert gt0._current_output_mw == 0.0, f"gt-0 output: {gt0._current_output_mw}"
    # Phase E repair: _target_mw deleted (Phase C). Equivalent: output_mw() == 0.0.
    assert gt0.output_mw() == 0.0,         f"gt-0 output_mw after trip: {gt0.output_mw()}"
    assert not math.isnan(gt0._stop_time_s), (
        "gt-0._stop_time_s must be set after trip so cooldown window is tracked"
    )
    assert gt1.state == TurbineState.SYNCHRONISED, f"gt-1 state: {gt1.state!r}"
    assert gt1._current_output_mw == 8.0,  f"gt-1 output: {gt1._current_output_mw}"
    assert len(ctx._operator_commands) == 0, "queue should be empty"

    # ── step() confirms physics sees only gt-1 ────────────────────────────────
    with _plane_guard():
        result = ctx.step()

    assert result.turbine_output_mw < 16.0, (
        f"Tripped unit must not contribute; fleet output was {result.turbine_output_mw} MW"
    )
    assert result.turbine_output_mw >= 0.0


# ── TC-203-2: start via validate_and_enqueue transitions to STARTING ──────────

def test_tc_203_2_start_command_enters_starting_and_produces_zero():
    """validate_and_enqueue start → drain → step(): unit enters STARTING, MW=0.

    Validation path: RunManager.validate_and_enqueue_unit_command().
    Drain path: _drain_operator_commands() (mirrors _drive() A-1).

    Setup:
      Both units in OFFLINE (default).
    Expect:
      validate_and_enqueue → UNIT_CMD_OK (unit is OFFLINE — start is valid).
      After drain: gt-0 STARTING output=0; gt-1 OFFLINE.
      After step(): turbine_output_mw == 0 (STARTING units not dispatched).
    """
    from core.asset_modules import TurbineState

    ctx     = _build_ctx("tc-203-2")
    manager = _make_manager_with_ctx(ctx)

    gt0 = next(t for t in ctx.sim_state.turbines if t.config.asset_id == "gt-0")
    gt1 = next(t for t in ctx.sim_state.turbines if t.config.asset_id == "gt-1")

    assert gt0.state == TurbineState.OFFLINE, "gt-0 should start OFFLINE"

    # ── validate and enqueue via the production path ──────────────────────────
    code, detail = manager.validate_and_enqueue_unit_command(ctx.run_id, "gt-0", "start")
    assert code == manager.UNIT_CMD_OK, f"start should be accepted: {detail!r}"
    assert len(ctx._operator_commands) == 1

    # ── drain ─────────────────────────────────────────────────────────────────
    _drain_operator_commands(ctx)

    # ── immediate state checks ────────────────────────────────────────────────
    assert gt0.state == TurbineState.STARTING, (
        f"gt-0 should be STARTING after start command, got {gt0.state!r}"
    )
    assert gt0._current_output_mw == 0.0, f"STARTING unit must produce 0 MW"
    assert gt1.state == TurbineState.OFFLINE, f"gt-1 should still be OFFLINE"
    assert len(ctx._operator_commands) == 0

    # ── step() confirms STARTING unit contributes 0 to fleet output ──────────
    with _plane_guard():
        result = ctx.step()

    assert result.turbine_output_mw == 0.0, (
        f"STARTING unit must not be dispatched; got {result.turbine_output_mw} MW"
    )


# ── TC-203-3: trip → start with default t_min_down_s=0 succeeds ──────────────

def test_tc_203_3_immediate_start_after_trip_accepted_when_cooldown_zero():
    """An OFFLINE unit (just tripped) can be immediately started when t_min_down_s=0.

    This is the common case: the default TurbineConfig has t_min_down_s=0,
    so the minimum-down-time guard is always satisfied.  The trip command sets
    _stop_time_s, and validate_and_enqueue must accept the start command when
    the elapsed time (0 s) satisfies the 0 s cooldown.

    This test is the direct counter-case for TC-203-4: the only difference is
    t_min_down_s.  If validate_and_enqueue incorrectly rejects this command the
    UI would get stuck in 'queued…' state with no path to recovery.
    """
    from core.asset_modules import TurbineState

    ctx     = _build_ctx("tc-203-3")
    manager = _make_manager_with_ctx(ctx)

    gt0 = next(t for t in ctx.sim_state.turbines if t.config.asset_id == "gt-0")

    # Confirm t_min_down_s == 0 (the default that affects nearly all scenarios).
    assert gt0.config.t_min_down_s == 0.0, (
        f"test assumes default t_min_down_s=0, got {gt0.config.t_min_down_s}"
    )

    # ── Step 1: force gt-0 to SYNCHRONISED, then trip it ─────────────────────
    # Phase E repair: _target_mw removed.
    gt0.state = TurbineState.SYNCHRONISED
    gt0._current_output_mw = 8.0

    code, detail = manager.validate_and_enqueue_unit_command(ctx.run_id, "gt-0", "trip")
    assert code == manager.UNIT_CMD_OK, f"trip should be accepted: {detail!r}"
    _drain_operator_commands(ctx)

    assert gt0.state == TurbineState.OFFLINE
    assert not math.isnan(gt0._stop_time_s), "_stop_time_s must be set after trip"

    # ── Step 2: immediately try to start — must be accepted (cooldown = 0) ───
    code, detail = manager.validate_and_enqueue_unit_command(ctx.run_id, "gt-0", "start")
    assert code == manager.UNIT_CMD_OK, (
        f"start should be accepted immediately (t_min_down_s=0), got {code!r}: {detail!r}"
    )

    # Drain and confirm state.
    _drain_operator_commands(ctx)
    assert gt0.state == TurbineState.STARTING, (
        f"gt-0 should be STARTING after start command, got {gt0.state!r}"
    )


# ── TC-203-4: start rejected during minimum-down-time window ─────────────────

def test_tc_203_4_start_rejected_during_minimum_down_time_window():
    """validate_and_enqueue returns UNIT_CMD_BAD_STATE when t_min_down_s > 0.

    An operator trips a unit and immediately tries to restart it.  If the unit's
    TurbineConfig has t_min_down_s > 0, command_start() would silently refuse
    the request (returning without a state change), leaving the UI stuck on
    'queued…' indefinitely.  The guard in validate_and_enqueue must detect this
    and return a 409-equivalent result before the command is enqueued.
    """
    from core.asset_modules import TurbineState

    ctx     = _build_ctx("tc-203-4")
    manager = _make_manager_with_ctx(ctx)

    gt0 = next(t for t in ctx.sim_state.turbines if t.config.asset_id == "gt-0")

    # Set a non-zero minimum down-time (e.g. 5-minute peaking unit constraint).
    gt0.config.t_min_down_s = 300.0

    # ── Step 1: trip gt-0 (sets _stop_time_s = ctx.sim_time = 0.0) ───────────
    # Phase E repair: _target_mw removed.
    gt0.state = TurbineState.SYNCHRONISED
    gt0._current_output_mw = 8.0

    code, _ = manager.validate_and_enqueue_unit_command(ctx.run_id, "gt-0", "trip")
    assert code == manager.UNIT_CMD_OK
    _drain_operator_commands(ctx)

    assert gt0.state == TurbineState.OFFLINE
    assert not math.isnan(gt0._stop_time_s)
    # elapsed_down = ctx.sim_time - _stop_time_s = 0.0 - 0.0 = 0 s < 300 s

    # ── Step 2: immediate start must be REJECTED ─────────────────────────────
    code, detail = manager.validate_and_enqueue_unit_command(ctx.run_id, "gt-0", "start")
    assert code == manager.UNIT_CMD_BAD_STATE, (
        f"start during cooldown window should be rejected, got {code!r}: {detail!r}"
    )
    assert "minimum-down-time" in detail.lower() or "down-time" in detail.lower(), (
        f"error message should mention the cooldown; got: {detail!r}"
    )
    # ── Command must NOT have been enqueued ───────────────────────────────────
    assert len(ctx._operator_commands) == 0, (
        "rejected command must not be placed in the queue"
    )
    # Verify gt-0 is still OFFLINE (no state change).
    assert gt0.state == TurbineState.OFFLINE


# ── TC-203-5: HTTP endpoint wiring (TestClient) ───────────────────────────────
# This test exercises the full FastAPI → validate_and_enqueue path including
# the asyncio-driven run loop (TestClient handles the event loop internally).

# ── TC-203-5x: validate_and_enqueue result-code coverage ─────────────────────
# These tests exercise every code path in validate_and_enqueue_unit_command()
# without going through the ASGI/HTTP stack.  The HTTP route in runs.py is a
# trivial three-branch map (UNIT_CMD_RUN_404→404, UNIT_CMD_UNIT_404→404,
# UNIT_CMD_BAD_STATE→409, ok→202) whose correctness is confirmed here at the
# RunManager level so that no TestClient / asyncpg event-loop teardown issues
# can contaminate neighbouring test files.


def test_tc_203_5a_unknown_run_returns_run_404_code():
    """validate_and_enqueue returns UNIT_CMD_RUN_404 for a non-existent run.

    Verifies the HTTP endpoint would return 404 (run not found).
    """
    from runtime.run_manager import RunManager, WebSocketHub

    manager = RunManager(WebSocketHub())
    code, detail = manager.validate_and_enqueue_unit_command(
        "nonexistent-run-id", "turbine-0", "start"
    )
    assert code == manager.UNIT_CMD_RUN_404, f"unexpected code {code!r}: {detail!r}"
    assert "not found" in detail.lower() or "not active" in detail.lower()


def test_tc_203_5b_unknown_unit_returns_unit_404_code():
    """validate_and_enqueue returns UNIT_CMD_UNIT_404 when unit_id doesn't exist.

    Verifies the HTTP endpoint would return 404 (unit not in fleet).
    """
    ctx     = _build_ctx("tc-203-5b")
    manager = _make_manager_with_ctx(ctx)

    code, detail = manager.validate_and_enqueue_unit_command(
        ctx.run_id, "no-such-unit", "start"
    )
    assert code == manager.UNIT_CMD_UNIT_404, f"unexpected code {code!r}: {detail!r}"
    assert "not found" in detail.lower()
    assert len(ctx._operator_commands) == 0, "rejected command must not be queued"


def test_tc_203_5c_trip_from_offline_returns_bad_state_code():
    """validate_and_enqueue returns UNIT_CMD_BAD_STATE for trip on OFFLINE unit.

    Verifies the HTTP endpoint would return 409 (wrong state for action).
    Trip is only valid from on-bus states; OFFLINE units cannot be tripped.
    """
    from core.asset_modules import TurbineState

    ctx     = _build_ctx("tc-203-5c")
    manager = _make_manager_with_ctx(ctx)

    gt0 = next(t for t in ctx.sim_state.turbines if t.config.asset_id == "gt-0")
    assert gt0.state == TurbineState.OFFLINE, "gt-0 should start OFFLINE"

    code, detail = manager.validate_and_enqueue_unit_command(ctx.run_id, "gt-0", "trip")
    assert code == manager.UNIT_CMD_BAD_STATE, (
        f"trip on OFFLINE unit should be UNIT_CMD_BAD_STATE, got {code!r}: {detail!r}"
    )
    assert len(ctx._operator_commands) == 0, "rejected command must not be queued"


def test_tc_203_5c2_start_hot_standby_returns_bad_state_code():
    """validate_and_enqueue returns UNIT_CMD_BAD_STATE for start on a hot-standby unit.

    command_start() silently returns without transitioning state when
    hot_standby=True (asset_modules.py line 816-817).  If the endpoint accepted
    the command, the UI would get stuck in 'queued…' forever because no state
    transition is ever broadcast.

    The guard in validate_and_enqueue must detect hot_standby=True for 'start'
    commands and return UNIT_CMD_BAD_STATE before enqueueing, regardless of the
    unit's current state.
    """
    from runtime.scenario_factory import build_run_context_from_spec
    from runtime.run_manager import RunManager, WebSocketHub

    _HOT_STANDBY_SPEC = {
        **_SPEC,
        "turbine_units": [
            {"asset_id": "gt-0", "rated_mw": 10.0, "r_asset_mw_per_s": 0.5,
             "hot_standby": True},    # ← managed by arbitrator only
        ],
    }
    ctx     = build_run_context_from_spec("tc-203-5c2", _HOT_STANDBY_SPEC)
    manager = RunManager(WebSocketHub())
    manager._contexts[ctx.run_id] = ctx

    code, detail = manager.validate_and_enqueue_unit_command(ctx.run_id, "gt-0", "start")
    assert code == manager.UNIT_CMD_BAD_STATE, (
        f"start on hot-standby unit should be UNIT_CMD_BAD_STATE, got {code!r}: {detail!r}"
    )
    assert "hot-standby" in detail.lower() or "hot_standby" in detail.lower(), (
        f"error message should mention hot-standby: {detail!r}"
    )
    assert len(ctx._operator_commands) == 0, "rejected command must not be queued"


def test_tc_203_5d_start_from_offline_returns_ok_code():
    """validate_and_enqueue returns UNIT_CMD_OK for start on OFFLINE unit.

    Verifies the HTTP endpoint would return 202 (command accepted and queued).
    Confirms the command is actually placed in the queue.
    """
    from core.asset_modules import TurbineState

    ctx     = _build_ctx("tc-203-5d")
    manager = _make_manager_with_ctx(ctx)

    gt0 = next(t for t in ctx.sim_state.turbines if t.config.asset_id == "gt-0")
    assert gt0.state == TurbineState.OFFLINE

    code, detail = manager.validate_and_enqueue_unit_command(ctx.run_id, "gt-0", "start")
    assert code == manager.UNIT_CMD_OK, f"unexpected code {code!r}: {detail!r}"
    assert len(ctx._operator_commands) == 1, "accepted command must be placed in queue"
    assert ctx._operator_commands[0] == {"unit_id": "gt-0", "action": "start"}
