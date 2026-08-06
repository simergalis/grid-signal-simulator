#!/usr/bin/env python3
"""gridsignal_logger.py — 60-second telemetry capture for "Log Test".

Usage (called by export.py):
    python3 gridsignal_logger.py --rows 600 --interval 0.1 --out /tmp/log.csv

Connects to the running GridSignal API via WebSocket, streams live tick data
for <rows> × <interval> seconds, and writes a CSV to <out>.  Each row
captures the latest known sim state plus wall-clock and system metrics.

Exit 0 on success, non-zero on failure (export.py checks returncode).
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import datetime
import json
import os
import sys
import time
import urllib.request
from typing import Any

# ── CLI args ─────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser(description="GridSignal telemetry logger")
ap.add_argument("--rows",     type=int,   default=600,  help="number of CSV rows to write")
ap.add_argument("--interval", type=float, default=0.1,  help="seconds between samples")
ap.add_argument("--out",      required=True,             help="output CSV path")
args = ap.parse_args()

PORT    = int(os.environ.get("PORT", 8080))
HTTP    = f"http://localhost:{PORT}"
WS_BASE = f"ws://localhost:{PORT}"

# ── Optional psutil for CPU / memory rows ────────────────────────────────────
try:
    import psutil as _psutil  # type: ignore
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

# ── CSV columns (in display order) ──────────────────────────────────────────
COLUMNS = [
    # Timing
    "wall_time",
    "elapsed_s",
    "run_id",
    "sim_time_seconds",
    "tick_index",
    # Gas turbine fleet
    "synchronised_output_mw",
    "turbine_output_mw",
    # BESS
    "bess_output_mw",
    "bess_setpoint_mw",
    "bess_soc_pct",
    "bess_bridging_seconds",
    # Renewables
    "p_renewable_mw",
    # Loads
    "p_compute_mw",
    "p_cooling_mw",
    "p_total_mw",
    "net_demand_mw",
    # Physics
    "balance_residual_mw",
    "frequency_hz",
    # Thermal headroom
    "absorbable_mw",
    "rated_cooling_mw",
    # System
    "cpu_pct",
    "mem_pct",
]


def _field(tick: dict, *keys: str) -> Any:
    """Return the first key found in tick, or empty string."""
    for k in keys:
        if k in tick:
            return tick[k]
    return ""


def _get_active_run() -> str | None:
    """Synchronously fetch the first active run_id from GET /runs."""
    try:
        req = urllib.request.Request(f"{HTTP}/runs")
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        ids = data.get("run_ids", [])
        return ids[0] if ids else None
    except Exception as exc:
        print(f"[logger] GET /runs failed: {exc}", file=sys.stderr)
        return None


def _row(
    *,
    run_id: str,
    tick: dict,
    elapsed: float,
    wall: str,
) -> dict:
    """Build one CSV row from the latest tick snapshot."""
    soc_frac = tick.get("bess_soc_fraction")
    soc_pct  = round(soc_frac * 100, 1) if isinstance(soc_frac, (int, float)) else ""

    cpu = _psutil.cpu_percent(interval=None) if _HAS_PSUTIL else ""
    mem = _psutil.virtual_memory().percent    if _HAS_PSUTIL else ""

    return {
        "wall_time":              wall,
        "elapsed_s":              round(elapsed, 3),
        "run_id":                 run_id,
        "sim_time_seconds":       _field(tick, "sim_time_seconds"),
        "tick_index":             _field(tick, "tick_index"),
        "synchronised_output_mw": _field(tick, "synchronised_output_mw"),
        "turbine_output_mw":      _field(tick, "turbine_output_mw"),
        "bess_output_mw":         _field(tick, "bess_output_mw"),
        "bess_setpoint_mw":       _field(tick, "bess_setpoint_mw"),
        "bess_soc_pct":           soc_pct,
        "bess_bridging_seconds":  _field(tick, "bess_bridging_seconds"),
        "p_renewable_mw":         _field(tick, "p_renewable_mw"),
        "p_compute_mw":           _field(tick, "p_compute_mw"),
        "p_cooling_mw":           _field(tick, "p_cooling_mw"),
        "p_total_mw":             _field(tick, "p_total_mw"),
        "net_demand_mw":          _field(tick, "net_demand_mw"),
        "balance_residual_mw":    _field(tick, "balance_residual_mw"),
        "frequency_hz":           _field(tick, "frequency_hz"),
        "absorbable_mw":          _field(tick, "absorbable_mw"),
        "rated_cooling_mw":       _field(tick, "rated_cooling_mw"),
        "cpu_pct":                cpu,
        "mem_pct":                mem,
    }


async def _capture(run_id: str) -> None:
    """Connect to WS, sample at args.interval, write args.rows rows to CSV."""
    import websockets  # type: ignore

    ws_url = f"{WS_BASE}/ws/{run_id}"
    print(f"[logger] connecting to {ws_url}", file=sys.stderr)

    # Shared state updated by the receive loop.
    latest: dict = {}
    last_tick_index: Any = None
    first_tick_event = asyncio.Event()

    async def _recv_loop(ws: Any) -> None:
        nonlocal latest, last_tick_index
        async for raw in ws:
            try:
                msg = json.loads(raw)
                latest = msg
                if msg.get("tick_index") != last_tick_index:
                    last_tick_index = msg.get("tick_index")
                    first_tick_event.set()
            except Exception:
                pass

    async with websockets.connect(ws_url, ping_interval=15, open_timeout=10) as ws:
        recv_task = asyncio.create_task(_recv_loop(ws))

        # Prime psutil CPU counter (first call always returns 0.0).
        if _HAS_PSUTIL:
            _psutil.cpu_percent(interval=None)

        # Wait up to 20 s for the first tick before starting the clock.
        try:
            await asyncio.wait_for(first_tick_event.wait(), timeout=20.0)
        except asyncio.TimeoutError:
            recv_task.cancel()
            print("[logger] no tick received within 20 s — is a run active?",
                  file=sys.stderr)
            sys.exit(1)

        start  = time.monotonic()
        next_t = start
        count  = 0

        with open(args.out, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=COLUMNS)
            writer.writeheader()

            while count < args.rows:
                now      = time.monotonic()
                sleep_s  = next_t - now
                if sleep_s > 0:
                    await asyncio.sleep(sleep_s)
                next_t  += args.interval

                elapsed  = time.monotonic() - start
                wall_str = (datetime.datetime.utcnow()
                            .isoformat(timespec="milliseconds") + "Z")

                writer.writerow(_row(
                    run_id=run_id,
                    tick=latest,
                    elapsed=elapsed,
                    wall=wall_str,
                ))
                count += 1

                # Print progress every 60 rows (~6 s).
                if count % 60 == 0:
                    print(f"[logger] {count}/{args.rows} rows", file=sys.stderr)

        recv_task.cancel()
        try:
            await recv_task
        except asyncio.CancelledError:
            pass

    print(f"[logger] done — {count} rows → {args.out!r}", file=sys.stderr)


def main() -> None:
    run_id = _get_active_run()
    if run_id is None:
        print("[logger] no active run found — start a run before using Log Test",
              file=sys.stderr)
        sys.exit(1)

    print(f"[logger] active run: {run_id!r}  rows={args.rows}  interval={args.interval}s",
          file=sys.stderr)
    asyncio.run(_capture(run_id))


if __name__ == "__main__":
    main()
