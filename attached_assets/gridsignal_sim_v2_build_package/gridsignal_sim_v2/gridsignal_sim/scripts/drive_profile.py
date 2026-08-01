"""
drive_profile.py — per-section wall-clock diagnostic for _drive().

Instruments every section of the _drive() hot path using monkey-patching
(no source changes) and runs a single 4h max-speed load-test context —
the same configuration as `load_test.py --matrix` at 1x scale.

Usage:
    PYTHONPATH=. python scripts/drive_profile.py

Prints p50 / p95 / total for each section plus unmeasured overhead.
"""
from __future__ import annotations

import asyncio
import statistics
import sys
import time
from typing import Any

import runtime.scenario_factory as scenario_factory
import runtime.run_manager as run_manager_module
from runtime.run_manager import RunManager, WebSocketHub
from core.simulation_core import evaluate_tick as _uninstrumented_evaluate_tick

# ---------------------------------------------------------------------------
# Section accumulator
# ---------------------------------------------------------------------------
_times: dict[str, list[float]] = {}


def _record(name: str, elapsed_s: float) -> None:
    _times.setdefault(name, []).append(elapsed_s)


# ---------------------------------------------------------------------------
# Patch module-level sync functions referenced by _drive()
# These are looked up in run_manager's global namespace at call time, so
# replacing the attribute is sufficient — no source changes needed.
# ---------------------------------------------------------------------------

def _mk_sync_wrapper(name: str, fn: Any):
    def _w(*a, **kw):
        t0 = time.perf_counter()
        r = fn(*a, **kw)
        _record(name, time.perf_counter() - t0)
        return r
    return _w


def _mk_async_wrapper(name: str, fn: Any):
    async def _w(*a, **kw):
        t0 = time.perf_counter()
        r = await fn(*a, **kw)
        _record(name, time.perf_counter() - t0)
        return r
    return _w


# evaluate_tick
run_manager_module.evaluate_tick = _mk_sync_wrapper(
    "A_evaluate_tick", _uninstrumented_evaluate_tick
)

# _update_thermal_state and _ingest_synthetic_telemetry are module-level
# functions called by name inside _drive()'s module scope.
_raw_thermal = run_manager_module._update_thermal_state
_raw_ingest  = run_manager_module._ingest_synthetic_telemetry
run_manager_module._update_thermal_state      = _mk_sync_wrapper("B_thermal_update", _raw_thermal)
run_manager_module._ingest_synthetic_telemetry = _mk_sync_wrapper("D_telemetry_ingest", _raw_ingest)


# ---------------------------------------------------------------------------
# Instrumented RunManager — wraps instance-method calls AFTER context is built
# ---------------------------------------------------------------------------

class ProfiledRunManager(RunManager):

    def _instrument_ctx(self, ctx) -> None:
        """Wrap per-tick instance methods on ctx and hub objects."""

        # ── sink.append (async) ───────────────────────────────────────────
        _raw_append = ctx.sink.append
        ctx.sink.append = _mk_async_wrapper("C_sink_append", _raw_append)

        # ── ws_hub.broadcast (async) ──────────────────────────────────────
        _raw_broadcast = self._ws_hub.broadcast
        self._ws_hub.broadcast = _mk_async_wrapper("C_ws_broadcast", _raw_broadcast)

        # ── registry (W1a) — sync ─────────────────────────────────────────
        if ctx.registry is not None:
            _raw_reg_tick    = ctx.registry.tick
            _raw_reg_run_all = ctx.registry.run_all
            ctx.registry.tick    = _mk_sync_wrapper("E_registry_tick",    _raw_reg_tick)
            ctx.registry.run_all = _mk_sync_wrapper("E_registry_run_all", _raw_reg_run_all)

        # ── corroborator (W1b) — sync ─────────────────────────────────────
        if ctx.corroborator is not None:
            _raw_corr_chk = ctx.corroborator.apply_checkpoint_start
            ctx.corroborator.apply_checkpoint_start = _mk_sync_wrapper(
                "D_corroborator_checkpoint", _raw_corr_chk
            )

        # ── AD1 layers — sync (may not be set in load-test context) ──────
        if ctx.procurement_layer is not None:
            ctx.procurement_layer.evaluate_tick = _mk_sync_wrapper(
                "F_procurement", ctx.procurement_layer.evaluate_tick
            )
        if ctx.maintenance_layer is not None:
            ctx.maintenance_layer.evaluate_tick = _mk_sync_wrapper(
                "F_maintenance", ctx.maintenance_layer.evaluate_tick
            )
        if ctx.ramp_relaxation_engine is not None:
            ctx.ramp_relaxation_engine.evaluate = _mk_sync_wrapper(
                "F_ramp_relaxation", ctx.ramp_relaxation_engine.evaluate
            )

    async def _drive(self, ctx) -> None:
        self._instrument_ctx(ctx)
        # asyncio.sleep is the last thing in the loop; wrap it via a local counter.
        # We patch the module attribute on run_manager so _drive's loop picks it up.
        _raw_sleep = asyncio.sleep
        _sleep_times: list[float] = []

        async def _p_sleep(s, **kw):
            t0 = time.perf_counter()
            await _raw_sleep(s, **kw)
            elapsed = time.perf_counter() - t0
            _record("G_asyncio_sleep", elapsed)

        # Patch asyncio.sleep in run_manager_module's namespace so _drive's body
        # sees the wrapper when it calls `asyncio.sleep(...)`.
        import asyncio as _asyncio_mod
        _saved_sleep = _asyncio_mod.sleep
        _asyncio_mod.sleep = _p_sleep

        try:
            await super()._drive(ctx)
        finally:
            _asyncio_mod.sleep = _saved_sleep


# ---------------------------------------------------------------------------
# Fake WebSocket subscriber (broadcast needs at least one subscriber to do work)
# ---------------------------------------------------------------------------

class _FakeSock:
    async def send_json(self, data):
        pass


# ---------------------------------------------------------------------------
# Report helper
# ---------------------------------------------------------------------------

def _report(wall_s: float, ticks: int) -> None:
    print(f"\n{'='*70}")
    print(f"  _drive() per-section profile — 1 run, 4 h scenario, max speed")
    print(f"  total wall clock : {wall_s:.3f} s   ({ticks} ticks)")
    print(f"{'='*70}")
    print(f"  {'Section':<32}  {'n':>5}  {'total':>8}  {'p50 ms':>8}  {'p95 ms':>8}")
    print(f"  {'-'*32}  {'-'*5}  {'-'*8}  {'-'*8}  {'-'*8}")

    measured_total = 0.0
    for name in sorted(_times):
        samples = _times[name]
        n = len(samples)
        total_s = sum(samples)
        measured_total += total_s
        srt = sorted(samples)
        p50_ms = statistics.median(srt) * 1000
        p95_ms = srt[min(n - 1, int(0.95 * n))] * 1000
        print(f"  {name:<32}  {n:>5}  {total_s:>8.3f}s  {p50_ms:>8.3f}  {p95_ms:>8.3f}")

    print(f"  {'-'*32}  {'-'*5}  {'-'*8}")
    print(f"  {'Sum of measured sections':<32}  {'':>5}  {measured_total:>8.3f}s")
    print(f"  {'Unmeasured overhead':<32}  {'':>5}  {wall_s - measured_total:>8.3f}s")
    print(f"{'='*70}\n")

    # Highlight the biggest section
    biggest = max(_times, key=lambda k: sum(_times[k]))
    pct = 100 * sum(_times[biggest]) / wall_s
    print(f"  Largest section: {biggest} — {sum(_times[biggest]):.3f}s ({pct:.1f}% of wall clock)\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    hub = WebSocketHub()
    mgr = ProfiledRunManager(hub)

    ctx = scenario_factory.build_load_test_context(
        "profile-run",
        gpu_module_count=50,
        turbine_count=8,
        bess_count=4,
        solar_count=4,
        end_sim_time=14400.0,
        playback_speed=0.0,
    )

    # Register a fake subscriber so broadcast actually serialises one payload
    # (same as load_test.py — keeps the measurement realistic).
    fake_sock = _FakeSock()
    hub.subscribe(ctx.run_id, fake_sock)

    print(f"  Starting profiled _drive(): 1 run × 4 h × max speed")
    print(f"  registry enabled={ctx.registry.enabled}, "
          f"router={type(ctx.registry._router).__name__}, "
          f"has_agent={ctx.registry._router.has_agent}")
    print(f"  telemetry_ingestor={ctx.telemetry_ingestor is not None}, "
          f"corroborator={ctx.corroborator is not None}")
    print(f"  AD1: procurement={ctx.procurement_layer is not None}, "
          f"maintenance={ctx.maintenance_layer is not None}, "
          f"ramp={ctx.ramp_relaxation_engine is not None}")
    print()

    t_start = time.perf_counter()
    await mgr.start_run(ctx)
    task = mgr._tasks.get("profile-run")
    if task is not None:
        await task
    wall_s = time.perf_counter() - t_start

    ticks = len(_times.get("A_evaluate_tick", []))
    _report(wall_s, ticks)


if __name__ == "__main__":
    asyncio.run(main())
