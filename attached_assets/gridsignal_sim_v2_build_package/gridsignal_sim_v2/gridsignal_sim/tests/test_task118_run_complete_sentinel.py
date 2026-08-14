"""
test_task118_run_complete_sentinel.py

Task 118: Confirm a run that reaches its time limit returns the dashboard
to the ready state.

The run_complete sentinel fix (notify_run_complete → useTickStream) is the
only thing preventing the UI from freezing after a natural run end.  If it
regresses, operators are stuck on a dead screen with no way to start a new
run except a page reload.

Coverage:
  1. A short run (end_sim_time=5.0) drives to natural completion and the
     subscribed mock socket receives exactly one {"type": "run_complete"}
     message with the correct run_id.
  2. After notify_run_complete() the hub has evicted the subscriber — a
     subsequent broadcast() call does NOT reach it.
  3. The hub also evicts the latest-tick cache entry for the run on
     completion, so stale data cannot be served via GET /latest-tick.
  4. A cancelled run does NOT send run_complete (the frontend Stop button
     already calls handleRunStopped directly; a duplicate sentinel would
     cause a second reset).
"""

from __future__ import annotations

import asyncio

import pytest

from runtime.run_manager import RunManager, WebSocketHub
from runtime.scenario_factory import build_run_context


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _RecordingSocket:
    """Minimal WebSocketLike that records every payload sent to it and
    tracks how many times send_json() was called after run_complete."""

    def __init__(self) -> None:
        self.received: list[dict] = []
        self._run_complete_seen = False
        self.calls_after_run_complete: int = 0

    async def send_json(self, data: dict) -> None:
        if self._run_complete_seen:
            self.calls_after_run_complete += 1
        self.received.append(data)
        if data.get("type") == "run_complete":
            self._run_complete_seen = True

    async def close(self) -> None:
        pass  # no-op — real browser socket would close the WS frame


async def _drive_to_completion(manager: RunManager, ctx) -> None:
    """Start a run and wait for it to finish naturally."""
    await manager.start_run(ctx)
    task = manager._tasks[ctx.run_id]
    await task


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_complete_sentinel_is_sent_on_natural_end():
    """After end_sim_time is reached the subscribed socket must receive
    a {'type': 'run_complete', 'run_id': <id>} message (Assertion 1)."""
    hub = WebSocketHub()
    ws = _RecordingSocket()

    run_id = "t118-natural-end"
    hub.subscribe(run_id, ws)

    manager = RunManager(hub)
    ctx = build_run_context(run_id, job_id="job-t118", node_count=4, end_sim_time=5.0)
    await _drive_to_completion(manager, ctx)

    # At least one run_complete message must have been received.
    run_complete_msgs = [m for m in ws.received if m.get("type") == "run_complete"]
    assert run_complete_msgs, (
        "No run_complete sentinel received; useTickStream will never close "
        "the socket and the UI will freeze after the run ends."
    )
    assert len(run_complete_msgs) == 1, (
        f"Expected exactly 1 run_complete message, got {len(run_complete_msgs)}."
    )

    msg = run_complete_msgs[0]
    assert msg.get("run_id") == run_id, (
        f"run_complete run_id mismatch: expected {run_id!r}, got {msg.get('run_id')!r}"
    )


@pytest.mark.asyncio
async def test_subscriber_evicted_so_broadcast_does_not_reach_it():
    """After notify_run_complete() the hub removes the subscriber from
    its registry.  A broadcast() issued after run completion must not
    reach the subscriber (Assertion 2)."""
    hub = WebSocketHub()
    ws = _RecordingSocket()

    run_id = "t118-evict-after-complete"
    hub.subscribe(run_id, ws)

    manager = RunManager(hub)
    ctx = build_run_context(run_id, job_id="job-t118", node_count=4, end_sim_time=5.0)
    await _drive_to_completion(manager, ctx)

    # Confirm eviction from hub registry.
    subs_after = hub._subscribers.get(run_id, set())
    assert ws not in subs_after, (
        "Subscriber was not removed from the hub after run_complete; "
        "future broadcasts or a re-used run_id would reach a dead socket."
    )

    # Directly test that broadcast() no longer reaches this subscriber.
    # We manufacture a dummy tick payload and broadcast it on the same run_id.
    # If the subscriber is truly evicted, calls_after_run_complete stays 0.
    from core.models import TickResult, ConfidenceBand
    dummy_tick = TickResult(
        run_id=run_id,
        tick_index=9999,
        sim_time_seconds=9999.0,
        p_compute_demand_mw=0.0,
        p_cooling_demand_mw=0.0,
        p_demand_mw=0.0,
        net_demand_mw=0.0,
        turbine_output_mw=0.0,
        bess_output_mw=0.0,
        bess_soc_fraction=1.0,
        confidence=ConfidenceBand(point_estimate_mw=0.0, plus_minus_fraction=0.05),
    )
    await hub.broadcast(run_id, dummy_tick)

    assert ws.calls_after_run_complete == 0, (
        f"broadcast() reached the subscriber {ws.calls_after_run_complete} time(s) "
        "after run_complete was sent; the hub must evict subscribers atomically in "
        "notify_run_complete() before any further broadcast() can run."
    )


@pytest.mark.asyncio
async def test_latest_tick_cache_evicted_on_completion():
    """The hub's latest-tick cache entry must be cleared when the run
    finishes so GET /latest-tick cannot serve stale data after completion
    (Assertion 3, FLAG-3 invariant)."""
    hub = WebSocketHub()
    ws = _RecordingSocket()

    run_id = "t118-cache-evict"
    hub.subscribe(run_id, ws)

    manager = RunManager(hub)
    ctx = build_run_context(run_id, job_id="job-t118", node_count=4, end_sim_time=5.0)
    await _drive_to_completion(manager, ctx)

    cached = hub.get_latest_tick(run_id)
    assert cached is None, (
        f"Latest-tick cache still holds an entry for {run_id!r} after run completion; "
        "this would serve stale physics data to REST pollers."
    )


@pytest.mark.asyncio
async def test_cancelled_run_does_not_send_run_complete():
    """A cancelled run must NOT send a run_complete sentinel.  The
    frontend's Stop button already calls handleRunStopped directly;
    sending a second sentinel would trigger a double reset (Assertion 4)."""
    hub = WebSocketHub()
    ws = _RecordingSocket()

    run_id = "t118-cancel-no-sentinel"
    hub.subscribe(run_id, ws)

    manager = RunManager(hub)
    # Long run so we can cancel it cleanly before natural end.
    ctx = build_run_context(
        run_id,
        job_id="job-t118",
        node_count=4,
        end_sim_time=3600.0,
        playback_speed=1.0,
    )
    await manager.start_run(ctx)

    # Give the run loop a moment to start.
    await asyncio.sleep(0.05)
    await manager.cancel_run(run_id)

    run_complete_msgs = [m for m in ws.received if m.get("type") == "run_complete"]
    assert run_complete_msgs == [], (
        f"Cancelled run sent {len(run_complete_msgs)} run_complete message(s); "
        "the frontend Stop button already handles teardown — a duplicate sentinel "
        "causes a spurious second state reset."
    )
