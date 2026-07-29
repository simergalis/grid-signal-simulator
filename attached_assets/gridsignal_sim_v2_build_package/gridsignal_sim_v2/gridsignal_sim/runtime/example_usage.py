"""
Runnable example: start 3 concurrent scenario runs on one RunManager
and print each run's final tick. Demonstrates Design Spec Section 4.2's
isolation model end-to-end without any web framework in the loop.

Run with:
    PYTHONPATH=. python runtime/example_usage.py
"""

from __future__ import annotations

import asyncio

from runtime.scenario_factory import build_run_context
from runtime.run_manager import RunManager, WebSocketHub


async def main() -> None:
    hub = WebSocketHub()
    manager = RunManager(hub)

    contexts = [
        build_run_context("demo-20mw", job_id="job-big", node_count=200, end_sim_time=300.0),
        build_run_context("demo-5mw", job_id="job-small", node_count=50, dt_lead_seconds=60.0, end_sim_time=300.0),
        build_run_context("demo-baseline", job_id="job-idle", node_count=1, end_sim_time=300.0),
    ]

    await asyncio.gather(*(manager.start_run(c) for c in contexts))
    await asyncio.gather(*(manager._tasks[c.run_id] for c in contexts))

    for ctx in contexts:
        last = ctx.sink.rows[-1]
        print(
            f"[{ctx.run_id}] ticks={len(ctx.sink.rows)} "
            f"final P_total={last.p_total_mw:.3f} MW "
            f"turbine={last.turbine_output_mw:.3f} MW "
            f"bess={last.bess_output_mw:.3f} MW "
            f"alerts_seen={any(r.insufficient_reserve_alert for r in ctx.sink.rows)}"
        )


if __name__ == "__main__":
    asyncio.run(main())
