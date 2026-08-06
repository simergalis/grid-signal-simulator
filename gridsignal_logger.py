#!/usr/bin/env python3
"""gridsignal_logger.py — 60-second telemetry + predictive-variable capture.

Usage (called by export.py):
    python3 gridsignal_logger.py --rows 600 --interval 0.1 --out /tmp/log.csv

Connects to the running GridSignal API via WebSocket, streams live tick data
for <rows> × <interval> seconds, and writes a CSV to <out>.

Column groups
─────────────
  Timing          wall_time, elapsed_s, sim_time_seconds, tick_index
  Gas turbines    synchronised_output_mw, turbine_output_mw, gt_setpoint_mw
  BESS            bess_output_mw, bess_setpoint_mw, bess_soc_pct,
                  bess_bridging_seconds
  Renewables      p_renewable_mw, solar_weather, solar_conditions
  Loads           p_compute_mw, p_cooling_mw, p_total_mw, net_demand_mw,
                  forecast_mw
  Physics         balance_residual_mw, frequency_hz
  Thermal heads.  absorbable_mw, rated_cooling_mw, time_to_limit_s,
                  approach_rate_mw_s
  Thermal pre-st. pre_staging_shift_mw, pre_staging_precool_mw
  BESS reserve    turbine_ramp_credit_mw, peak_shortfall_mw,
                  dt_lead_next_s, bridging_basis, insufficient_reserve_alert
  Confidence      confidence_lower_mw, confidence_upper_mw, data_quality_tags
  Workload step   step_phase, step_kind
  System          cpu_pct, mem_pct

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

# ── CLI args ──────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser(description="GridSignal telemetry logger")
ap.add_argument("--rows",     type=int,   default=600,  help="number of CSV rows")
ap.add_argument("--interval", type=float, default=0.1,  help="seconds between samples")
ap.add_argument("--out",      required=True,             help="output CSV path")
args = ap.parse_args()

PORT    = int(os.environ.get("PORT", 8080))
HTTP    = f"http://localhost:{PORT}"
WS_BASE = f"ws://localhost:{PORT}"

# ── Optional psutil ───────────────────────────────────────────────────────────
try:
    import psutil as _psutil  # type: ignore
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

# ── CSV columns (display order) ───────────────────────────────────────────────
COLUMNS = [
    # ── Timing ────────────────────────────────────────────────────────────────
    "wall_time",
    "elapsed_s",
    "run_id",
    "sim_time_seconds",
    "tick_index",

    # ── Gas turbine fleet ─────────────────────────────────────────────────────
    "synchronised_output_mw",   # loading-layer-managed units only
    "turbine_output_mw",        # all is_synchronised (incl. RAMPING/AT_TARGET)
    "gt_setpoint_mw",           # total dispatch requirement handed to fleet

    # ── BESS ──────────────────────────────────────────────────────────────────
    "bess_output_mw",           # actual output (positive = discharging)
    "bess_setpoint_mw",         # dispatch command this tick
    "bess_soc_pct",             # state of charge %
    "bess_bridging_seconds",    # how long BESS can sustain binding demand

    # ── Renewables ────────────────────────────────────────────────────────────
    "p_renewable_mw",           # solar output injected into energy balance
    "solar_weather",            # weather code (e.g. "clear", "overcast")
    "solar_conditions",         # human-readable Mistral conditions label

    # ── Loads & demand forecast ───────────────────────────────────────────────
    "p_compute_mw",             # GPU rack draw
    "p_cooling_mw",             # cooling plant draw (lags compute ~90 s)
    "p_total_mw",               # total site demand
    "net_demand_mw",            # p_total_mw − p_renewable_mw (what dispatch covers)
    "forecast_mw",              # queue-derived expected compute draw

    # ── Physics ───────────────────────────────────────────────────────────────
    "balance_residual_mw",      # generation − demand (should be ~0)
    "frequency_hz",             # grid frequency (droop response)

    # ── Thermal headroom ─────────────────────────────────────────────────────
    "absorbable_mw",            # rated − current cooling draw
    "rated_cooling_mw",         # cooling plant nameplate
    "time_to_limit_s",          # seconds until cooling headroom = 0 (86400 = ∞)
    "approach_rate_mw_s",       # MW/s rate of cooling load rise

    # ── Thermal pre-staging ──────────────────────────────────────────────────
    "pre_staging_shift_mw",     # MW gap reduced by discharge pre-staging
    "pre_staging_precool_mw",   # extra load drawn to charge thermal store

    # ── BESS reserve / predictive staging ────────────────────────────────────
    "turbine_ramp_credit_mw",   # MW turbines cover before demand step lands
    "peak_shortfall_mw",        # MW BESS must bridge (delta − credit)
    "dt_lead_next_s",           # seconds to next GPU full-TDP (0 = none in flight)
    "bridging_basis",           # predicted_peak | current_demand | no_load
    "insufficient_reserve_alert",  # True if BESS cannot cover peak_shortfall

    # ── Confidence band ───────────────────────────────────────────────────────
    "confidence_lower_mw",      # lower bound of demand confidence band
    "confidence_upper_mw",      # upper bound of demand confidence band
    "data_quality_tags",        # semicolon-separated active DQ flags

    # ── Workload step ─────────────────────────────────────────────────────────
    "step_phase",               # fractional position within ML training step [0,1]
    "step_kind",                # "training" | "checkpoint"

    # ── System metrics ────────────────────────────────────────────────────────
    "cpu_pct",
    "mem_pct",
]


def _f(tick: dict, *keys: str) -> Any:
    """Return the first matching key from tick, or empty string."""
    for k in keys:
        if k in tick:
            return tick[k]
    return ""


def _get_active_run() -> str | None:
    """Synchronously fetch the first active run_id from GET /runs."""
    try:
        with urllib.request.urlopen(f"{HTTP}/runs", timeout=8) as resp:
            data = json.loads(resp.read())
        ids = data.get("run_ids", [])
        return ids[0] if ids else None
    except Exception as exc:
        print(f"[logger] GET /runs failed: {exc}", file=sys.stderr)
        return None


def _build_row(*, run_id: str, tick: dict, elapsed: float, wall: str) -> dict:
    """Map one tick snapshot → one CSV row."""
    soc_frac = tick.get("bess_soc_fraction")
    soc_pct  = round(soc_frac * 100, 1) if isinstance(soc_frac, (int, float)) else ""

    dq_tags  = tick.get("data_quality_tags", [])
    dq_str   = ";".join(dq_tags) if isinstance(dq_tags, list) else str(dq_tags)

    cpu = _psutil.cpu_percent(interval=None) if _HAS_PSUTIL else ""
    mem = _psutil.virtual_memory().percent    if _HAS_PSUTIL else ""

    return {
        # Timing
        "wall_time":                wall,
        "elapsed_s":                round(elapsed, 3),
        "run_id":                   run_id,
        "sim_time_seconds":         _f(tick, "sim_time_seconds"),
        "tick_index":               _f(tick, "tick_index"),
        # Gas turbines
        "synchronised_output_mw":   _f(tick, "synchronised_output_mw"),
        "turbine_output_mw":        _f(tick, "turbine_output_mw"),
        "gt_setpoint_mw":           _f(tick, "gt_setpoint_mw"),
        # BESS
        "bess_output_mw":           _f(tick, "bess_output_mw"),
        "bess_setpoint_mw":         _f(tick, "bess_setpoint_mw"),
        "bess_soc_pct":             soc_pct,
        "bess_bridging_seconds":    _f(tick, "bess_bridging_seconds"),
        # Renewables
        "p_renewable_mw":           _f(tick, "p_renewable_mw"),
        "solar_weather":            _f(tick, "solar_weather"),
        "solar_conditions":         _f(tick, "solar_conditions"),
        # Loads & demand forecast
        "p_compute_mw":             _f(tick, "p_compute_mw"),
        "p_cooling_mw":             _f(tick, "p_cooling_mw"),
        "p_total_mw":               _f(tick, "p_total_mw"),
        "net_demand_mw":            _f(tick, "net_demand_mw"),
        "forecast_mw":              _f(tick, "forecast_mw"),
        # Physics
        "balance_residual_mw":      _f(tick, "balance_residual_mw"),
        "frequency_hz":             _f(tick, "frequency_hz"),
        # Thermal headroom
        "absorbable_mw":            _f(tick, "absorbable_mw"),
        "rated_cooling_mw":         _f(tick, "rated_cooling_mw"),
        "time_to_limit_s":          _f(tick, "time_to_limit_s"),
        "approach_rate_mw_s":       _f(tick, "approach_rate_mw_s"),
        # Thermal pre-staging
        "pre_staging_shift_mw":     _f(tick, "pre_staging_shift_mw"),
        "pre_staging_precool_mw":   _f(tick, "pre_staging_precool_mw"),
        # BESS reserve / predictive staging
        "turbine_ramp_credit_mw":   _f(tick, "turbine_ramp_credit_mw"),
        "peak_shortfall_mw":        _f(tick, "peak_shortfall_mw"),
        "dt_lead_next_s":           _f(tick, "dt_lead_next_s"),
        "bridging_basis":           _f(tick, "bridging_basis"),
        "insufficient_reserve_alert": _f(tick, "insufficient_reserve_alert"),
        # Confidence band
        "confidence_lower_mw":      _f(tick, "confidence_lower_mw"),
        "confidence_upper_mw":      _f(tick, "confidence_upper_mw"),
        "data_quality_tags":        dq_str,
        # Workload step
        "step_phase":               _f(tick, "step_phase"),
        "step_kind":                _f(tick, "step_kind"),
        # System
        "cpu_pct":                  cpu,
        "mem_pct":                  mem,
    }


async def _capture(run_id: str) -> None:
    """Connect to WS, sample at args.interval, write args.rows rows to CSV."""
    import websockets  # type: ignore

    ws_url = f"{WS_BASE}/ws/{run_id}"
    print(f"[logger] connecting to {ws_url}", file=sys.stderr)

    latest: dict = {}
    first_tick_event = asyncio.Event()

    async def _recv_loop(ws: Any) -> None:
        nonlocal latest
        async for raw in ws:
            try:
                latest = json.loads(raw)
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
                now     = time.monotonic()
                sleep_s = next_t - now
                if sleep_s > 0:
                    await asyncio.sleep(sleep_s)
                next_t += args.interval

                elapsed  = time.monotonic() - start
                wall_str = (datetime.datetime.utcnow()
                            .isoformat(timespec="milliseconds") + "Z")

                writer.writerow(_build_row(
                    run_id=run_id,
                    tick=latest,
                    elapsed=elapsed,
                    wall=wall_str,
                ))
                count += 1

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
