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

    # Node counts corrected to match scenario names.
    # enterprise_8gpu_air at 10.2 kW/node × PUE 1.03:
    #   1900 nodes → 1900 × 10.2 × 1.03 / 1000 ≈ 19.96 MW  ("demo-20mw")
    #    476 nodes →  476 × 10.2 × 1.03 / 1000 ≈  5.00 MW  ("demo-5mw")
    # The old counts (200 / 50) produced ~2.1 MW / ~0.5 MW — the names were wrong.
    #
    # D10 / PROTO-8: demo-20mw turbine_rated_mw raised to 25 MW so the turbine
    # can reach steady-state P_dispatch_required (~19 MW) and allow BESS to taper
    # to standby — demonstrating the full §7.2 arc (ramp → bridge → catchup → taper).
    # Default 10 MW cap prevented taper from ever firing (turbine saturated below load).
    #
    # demo-alert: same load but small BESS (usable_mwh=0.2, PROTO-8 — CHOSEN).
    # max_sustainable_seconds(13.96 MW) = (0.2/13.96)×3600 ≈ 52s < gap_s ≈ 70s
    # → InsufficientReserveAlert fires.  Keeps the §7.3 alert path exercisable in
    # the shipped scenarios (TC-10 is the unit test; this is the end-to-end case).
    contexts = [
        # Step 3 Item 4 (anchor reserve): demo-20mw and demo-alert both designate
        # their BESS as the islanded grid-forming anchor (bess_grid_forming=True).
        # With p_anchor_reserve_mw=1.0 MW (BessConfig default):
        #   demo-20mw: bridging_available = 15.0 - 1.0 = 14.0 MW
        #              peak_shortfall ≈ 13.97 MW < 14.0 MW → NO ALERT  ✓
        #   demo-alert: bridging_available = 5.0 - 1.0 = 4.0 MW
        #               peak_shortfall ≈ 13.97 MW > 4.0 MW → ALERT     ✓
        # No resize needed: the 15 MW / 8 MWh BESS retains sufficient headroom
        # even after the 1 MW anchor deduction.
        build_run_context("demo-20mw", job_id="job-big", node_count=1900,
                          turbine_rated_mw=25.0, bess_rated_mw=15.0,
                          bess_usable_mwh=8.0,   # PROTO-8: 15 MW / 8 MWh ≈ 1.9C — plausible C-rate
                          bess_grid_forming=True, # anchor unit, 1 MW reserve withheld
                          end_sim_time=300.0),
        build_run_context("demo-5mw", job_id="job-small", node_count=476,
                          dt_lead_seconds=60.0, end_sim_time=300.0),
        build_run_context("demo-baseline", job_id="job-idle", node_count=1,
                          end_sim_time=300.0),
        build_run_context("demo-alert", job_id="job-alert", node_count=1900,
                          turbine_rated_mw=25.0, bess_usable_mwh=2.5,
                          bess_grid_forming=True, # anchor unit; bridging_available=4 MW < shortfall
                          end_sim_time=300.0),  # PROTO-8: 5 MW / 2.5 MWh = 2C; power ceiling fires alert
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
