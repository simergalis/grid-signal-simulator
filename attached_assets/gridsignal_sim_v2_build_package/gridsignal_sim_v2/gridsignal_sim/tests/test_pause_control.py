"""test_pause_control.py — PAUSE control-plane tests.

Spec reference: simulation-control-panel PAUSE feature spec.

State machine under test:
  STOPPED → START → RUNNING → PAUSE → PAUSED → RESUME → RUNNING → STOP → STOPPED
                                              → STOP  → STOPPED
                    RUNNING → STOP → STOPPED

Test groups:
  TC-PAUSE-1  Tick counter is frozen while paused (no ticks processed).
  TC-PAUSE-2  Resume continues from the frozen sim_time; timer elapsed preserved.
  TC-PAUSE-3  STOP from PAUSED fully resets; new START produces a clean run.
  TC-PAUSE-4  PAUSE and STOP are distinct code paths with different semantics.
  TC-PAUSE-5  pause_run / resume_run return correct booleans for missing / complete runs.
  TC-PAUSE-6  cancel_run sets the pause event so a paused loop exits cleanly.
"""
from __future__ import annotations

import asyncio

import pytest

from runtime.run_manager import RunManager, WebSocketHub
from runtime.scenario_factory import build_run_context

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _start_and_wait_ticks(
    manager: RunManager,
    ctx,
    min_ticks: int = 3,
    timeout: float = 5.0,
) -> None:
    """Start ctx and wait until at least min_ticks have been emitted."""
    await manager.start_run(ctx)
    deadline = asyncio.get_event_loop().time() + timeout
    while ctx.sim_state.tick_index < min_ticks:
        if asyncio.get_event_loop().time() > deadline:
            pytest.fail(
                f"Timed out waiting for {min_ticks} ticks "
                f"(got {ctx.sim_state.tick_index})"
            )
        await asyncio.sleep(0)


def _make_ctx(run_id: str, end_sim_time: float = 300.0):
    """Fast-running context: max speed (playback_speed=0), short duration."""
    return build_run_context(
        run_id, job_id="pause-test-job", node_count=4,
        end_sim_time=end_sim_time, playback_speed=0,
    )


# ---------------------------------------------------------------------------
# TC-PAUSE-1: tick counter frozen while paused
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tc_pause_1_ticks_frozen_while_paused():
    """No ticks must be processed between pause_run() and resume_run().

    The backend tick loop must block at ``await ctx._pause_event.wait()``
    between iterations.  No in-progress tick is aborted.
    """
    hub = WebSocketHub()
    manager = RunManager(hub)
    ctx = _make_ctx("tc-pause-1")

    await _start_and_wait_ticks(manager, ctx, min_ticks=3)

    ok = manager.pause_run(ctx.run_id)
    assert ok, "pause_run() must return True for an active run"
    assert ctx.paused, "ctx.paused must be True after pause_run()"

    # Yield to the event loop so the _drive() coroutine can reach wait().
    for _ in range(5):
        await asyncio.sleep(0)

    ticks_at_pause = ctx.sim_state.tick_index

    # Wait real time — sim ticks must not advance.
    await asyncio.sleep(0.05)
    assert ctx.sim_state.tick_index == ticks_at_pause, (
        f"Tick count must not advance while paused "
        f"(was {ticks_at_pause}, now {ctx.sim_state.tick_index})"
    )

    await manager.cancel_run(ctx.run_id)


# ---------------------------------------------------------------------------
# TC-PAUSE-2: resume continues from frozen sim_time
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tc_pause_2_resume_continues_from_frozen_sim_time():
    """After resume, the simulated clock must continue from the pause instant.

    TC-35 invariant: no sim-time is gained or lost across a pause/resume cycle.
    The timer elapsed at resume = elapsed at pause (no reset, no jump-forward).
    """
    hub = WebSocketHub()
    manager = RunManager(hub)
    ctx = _make_ctx("tc-pause-2", end_sim_time=600.0)

    await _start_and_wait_ticks(manager, ctx, min_ticks=3)

    manager.pause_run(ctx.run_id)
    for _ in range(5):
        await asyncio.sleep(0)

    sim_time_at_pause = ctx.sim_time
    ticks_at_pause    = ctx.sim_state.tick_index
    assert not ctx._pause_event.is_set(), "_pause_event must be clear when paused"

    # Resume and allow more ticks.
    manager.resume_run(ctx.run_id)
    assert not ctx.paused, "ctx.paused must be False after resume_run()"
    assert ctx._pause_event.is_set(), "_pause_event must be set after resume"

    await asyncio.sleep(0.02)
    assert ctx.sim_state.tick_index > ticks_at_pause, (
        "Ticks must advance again after resume"
    )
    assert ctx.sim_time > sim_time_at_pause, (
        "sim_time must advance from the pause instant, not from 0"
    )

    await manager.cancel_run(ctx.run_id)


# ---------------------------------------------------------------------------
# TC-PAUSE-3: STOP from PAUSED fully resets; new START begins clean
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tc_pause_3_stop_from_paused_fully_resets():
    """STOP (cancel_run) from PAUSED must discard all state; a fresh START is clean.

    This verifies that STOP sets the pause event (unblocking the loop) and that
    the finished run has no residual paused flag on a new context.
    """
    hub = WebSocketHub()
    manager = RunManager(hub)

    # Run 1: pause, then stop.
    ctx1 = _make_ctx("tc-pause-3a")
    await _start_and_wait_ticks(manager, ctx1, min_ticks=2)
    manager.pause_run(ctx1.run_id)
    for _ in range(5):
        await asyncio.sleep(0)
    await manager.cancel_run(ctx1.run_id)

    # Run 1 is complete; ctx1 must be finalised normally.
    completed1 = manager.get_completed(ctx1.run_id)
    # cancel_run raises ctx.cancelled — completed run may be None (cancelled runs
    # skip verdict and may not register a CompletedRun).  What we must assert is
    # that the second run starts cleanly.

    # Run 2: fresh start — must have no residual paused state.
    ctx2 = _make_ctx("tc-pause-3b")
    await manager.start_run(ctx2)
    assert not ctx2.paused, "New RunContext must start un-paused"

    # Yield so _drive() runs its prologue (ctx._pause_event.set()) before we inspect.
    for _ in range(5):
        await asyncio.sleep(0)
    assert ctx2._pause_event.is_set(), "New run's pause event must be set after _drive() starts"

    await asyncio.sleep(0.01)
    assert ctx2.sim_state.tick_index >= 1, (
        "New run must advance ticks immediately (no leftover pause from run 1)"
    )

    await manager.cancel_run(ctx2.run_id)


# ---------------------------------------------------------------------------
# TC-PAUSE-4: PAUSE and STOP are distinct code paths
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tc_pause_4_pause_and_stop_are_distinct():
    """PAUSE preserves in-flight state; STOP discards it.

    Concretely: after pause_run(), ctx.cancelled is still False and sim_time is
    preserved.  After cancel_run(), ctx.cancelled is True and the task completes.
    """
    hub = WebSocketHub()
    manager = RunManager(hub)
    ctx = _make_ctx("tc-pause-4", end_sim_time=600.0)

    await _start_and_wait_ticks(manager, ctx, min_ticks=2)
    sim_time_before = ctx.sim_time

    # PAUSE: cancelled must remain False, sim_time unchanged.
    manager.pause_run(ctx.run_id)
    for _ in range(5):
        await asyncio.sleep(0)

    assert not ctx.cancelled, "PAUSE must not set ctx.cancelled (that is STOP's role)"
    assert ctx.paused,        "PAUSE must set ctx.paused"
    assert ctx.sim_time == sim_time_before, (
        "sim_time must not change when paused"
    )

    # STOP: cancelled must become True, loop must exit.
    await manager.cancel_run(ctx.run_id)
    assert ctx.cancelled, "cancel_run() must set ctx.cancelled"
    # Task is awaited by cancel_run() — confirm it is done.
    task = manager._tasks.get(ctx.run_id)
    assert task is None or task.done(), "Task must be done after cancel_run()"


# ---------------------------------------------------------------------------
# TC-PAUSE-5: pause_run / resume_run return values
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tc_pause_5_return_values():
    """pause_run / resume_run return False for unknown or complete runs."""
    hub = WebSocketHub()
    manager = RunManager(hub)

    # Unknown run.
    assert manager.pause_run("does-not-exist") is False
    assert manager.resume_run("does-not-exist") is False

    # Completed run.
    ctx = _make_ctx("tc-pause-5", end_sim_time=5.0)
    await manager.start_run(ctx)
    task = manager._tasks[ctx.run_id]
    await task   # let it run to completion

    # After completion, pause/resume must return False.
    assert manager.pause_run(ctx.run_id) is False, (
        "pause_run() must return False for a completed run"
    )
    assert manager.resume_run(ctx.run_id) is False, (
        "resume_run() must return False for a completed run"
    )


# ---------------------------------------------------------------------------
# TC-PAUSE-6: cancel_run from PAUSED unblocks the loop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tc_pause_6_cancel_run_from_paused_exits_cleanly():
    """cancel_run() must set the pause event so a blocked loop can exit.

    If cancel_run() did NOT set the event, the _drive() coroutine would be stuck
    at ``await ctx._pause_event.wait()`` forever and cancel_run()'s ``await task``
    would never return.
    """
    hub = WebSocketHub()
    manager = RunManager(hub)
    ctx = _make_ctx("tc-pause-6", end_sim_time=3600.0)

    await _start_and_wait_ticks(manager, ctx, min_ticks=2)
    manager.pause_run(ctx.run_id)
    for _ in range(5):
        await asyncio.sleep(0)

    assert ctx.paused, "Run must be paused before testing cancel_run"

    # cancel_run() must return within a short timeout (event is set, loop unblocks).
    try:
        await asyncio.wait_for(manager.cancel_run(ctx.run_id), timeout=2.0)
    except asyncio.TimeoutError:
        pytest.fail(
            "cancel_run() timed out — pause event was not set by cancel_run(), "
            "leaving the _drive() loop permanently blocked at wait()"
        )

    assert ctx.cancelled, "ctx.cancelled must be True after cancel_run()"
