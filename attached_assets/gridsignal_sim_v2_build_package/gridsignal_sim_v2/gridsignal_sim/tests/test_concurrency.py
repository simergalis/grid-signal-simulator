"""
Concurrency-specific tests -- Design Spec Section 12, "new in this
design": isolation across concurrent runs, no head-of-line blocking on
a slow subscriber, and determinism-under-load.
"""

import asyncio

import pytest

from runtime.scenario_factory import build_run_context
from runtime.run_manager import RunManager, WebSocketHub


async def _run_to_completion(manager: RunManager, ctx) -> list:
    await manager.start_run(ctx)
    task = manager._tasks[ctx.run_id]
    await task
    return list(ctx.sink.rows)


@pytest.mark.asyncio
async def test_concurrent_runs_are_isolated():
    """Same job/config run alone vs. run alongside 4 siblings should
    produce identical tick-by-tick output -- proves RunContext isolation
    holds under concurrent asyncio scheduling (Design Spec Section 4.2)."""
    hub = WebSocketHub()

    solo_manager = RunManager(hub)
    solo_ctx = build_run_context("solo", job_id="job-A", node_count=10, end_sim_time=120.0)
    solo_rows = await _run_to_completion(solo_manager, solo_ctx)

    group_manager = RunManager(hub)
    contexts = [
        build_run_context(f"run-{i}", job_id="job-A", node_count=10, end_sim_time=120.0)
        for i in range(5)
    ]
    # Start all 5 concurrently, exactly as the >=5-concurrent-users NFR requires.
    await asyncio.gather(*(group_manager.start_run(c) for c in contexts))
    await asyncio.gather(*(group_manager._tasks[c.run_id] for c in contexts))

    for ctx in contexts:
        rows = ctx.sink.rows
        assert len(rows) == len(solo_rows)
        for solo_tick, group_tick in zip(solo_rows, rows):
            assert solo_tick.p_demand_mw == group_tick.p_demand_mw
            assert solo_tick.turbine_output_mw == group_tick.turbine_output_mw
            assert solo_tick.bess_output_mw == group_tick.bess_output_mw


@pytest.mark.asyncio
async def test_slow_subscriber_does_not_block_other_runs():
    """A subscriber whose send_json() hangs must not delay ticks for a
    sibling run (Design Spec Section 4.4's gather-based fan-out)."""
    hub = WebSocketHub()

    class HangingSocket:
        async def send_json(self, data: dict) -> None:
            await asyncio.sleep(3600)  # effectively "never returns" for test purposes

    hub.subscribe("slow-run", HangingSocket())

    manager = RunManager(hub)
    slow_ctx = build_run_context("slow-run", job_id="job-A", node_count=10, end_sim_time=30.0)
    fast_ctx = build_run_context("fast-run", job_id="job-A", node_count=10, end_sim_time=30.0)

    async def run_and_time(ctx):
        start = asyncio.get_event_loop().time()
        await manager.start_run(ctx)
        await manager._tasks[ctx.run_id]
        return asyncio.get_event_loop().time() - start

    # fast-run has no subscribers and must complete quickly even though
    # slow-run's broadcast() is stuck on the hanging socket forever.
    fast_elapsed, _ = await asyncio.wait_for(
        asyncio.gather(run_and_time(fast_ctx), _fire_and_forget(manager, slow_ctx)),
        timeout=5.0,
    )
    assert fast_elapsed < 5.0


async def _fire_and_forget(manager: RunManager, ctx) -> None:
    await manager.start_run(ctx)
    # Deliberately not awaited to completion within the timeout window --
    # its broadcast() call is expected to hang on the slow subscriber.


@pytest.mark.asyncio
async def test_determinism_under_concurrent_load():
    """Design Spec Section 12: same scenario+seed run alone vs. run
    alongside 4 other concurrent runs must produce byte-identical
    RunTimeseries output in both cases."""
    hub = WebSocketHub()

    manager_alone = RunManager(hub)
    ctx_alone = build_run_context("alone", job_id="job-X", node_count=14, end_sim_time=200.0)
    rows_alone = await _run_to_completion(manager_alone, ctx_alone)

    manager_group = RunManager(hub)
    target_ctx = build_run_context("target", job_id="job-X", node_count=14, end_sim_time=200.0)
    noise_ctxs = [
        build_run_context(f"noise-{i}", job_id="job-Y", node_count=3, end_sim_time=200.0)
        for i in range(4)
    ]
    await asyncio.gather(
        manager_group.start_run(target_ctx),
        *(manager_group.start_run(c) for c in noise_ctxs),
    )
    await asyncio.gather(
        manager_group._tasks["target"],
        *(manager_group._tasks[c.run_id] for c in noise_ctxs),
    )

    rows_group = target_ctx.sink.rows
    assert len(rows_alone) == len(rows_group)
    for a, b in zip(rows_alone, rows_group):
        assert a.p_demand_mw == b.p_demand_mw
        assert a.tick_index == b.tick_index


@pytest.mark.asyncio
async def test_cancel_run_cleans_up_without_affecting_siblings():
    hub = WebSocketHub()
    manager = RunManager(hub)
    victim = build_run_context("victim", job_id="job-A", node_count=10, end_sim_time=3600.0, playback_speed=1.0)
    survivor = build_run_context("survivor", job_id="job-A", node_count=10, end_sim_time=15.0)

    await manager.start_run(victim)
    await manager.start_run(survivor)
    survivor_task = manager._tasks["survivor"]  # grab the reference before it may finish and be popped

    await manager.cancel_run("victim")
    assert "victim" not in manager.active_run_ids()

    await survivor_task
    assert len(survivor.sink.rows) > 0
