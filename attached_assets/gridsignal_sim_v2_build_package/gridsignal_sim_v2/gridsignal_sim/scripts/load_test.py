"""
Load-testing script for the concurrency layer -- Design Spec Section 9
("Load harness ... opens 5+ concurrent runs and 5+ WebSocket
subscribers simultaneously; assert each run's own tick-latency NFR
holds throughout and no run's ticks stall waiting on another's") and
Section 12 ("determinism-under-load ... run on every merge to the
run-management code path").

This is a standalone script, not a pytest module: pytest's
test_concurrency.py (tests/) proves the concurrency *behaviors* exist
(isolation, no head-of-line blocking, determinism); this script proves
they hold *at and beyond NFR scale*, with real numbers, and is meant to
be run manually or wired into CI as a slower, periodic gate (Design
Spec Section 12, "run on every merge to the run-management code path
specifically, since it's slower than the pure-formula unit tests").

Usage:
    PYTHONPATH=. python scripts/load_test.py
    PYTHONPATH=. python scripts/load_test.py --runs 5 --stress 2
    PYTHONPATH=. python scripts/load_test.py --matrix          # 1x/2x/4x headroom sweep
    PYTHONPATH=. python scripts/load_test.py --report-json out.json

Exit code is non-zero if any NFR budget is violated, so this can be
used as a CI gate directly.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

import core.scenario_factory as scenario_factory
import runtime.run_manager as run_manager_module
from core.models import TickResult
from core.simulation_core import evaluate_tick as _uninstrumented_evaluate_tick
from runtime.run_manager import RunManager, WebSocketHub


# ---------------------------------------------------------------------------
# NFR budgets -- Design Spec Section 9 / functional spec Section 11.
# Keep these as named constants so a report can be read against them
# without cross-referencing the spec by hand.
# ---------------------------------------------------------------------------

TICK_LATENCY_BUDGET_MS = 1000.0        # "within 1 second of the tick being computed"
FOUR_HOUR_SCENARIO_WALL_CLOCK_BUDGET_S = 30.0  # "completes in under 30 seconds ... at max speed"
DEFAULT_CONCURRENT_RUNS = 5             # ">= 5 concurrent users"
DEFAULT_GPU_MODULES = 50
DEFAULT_TURBINES = 8
DEFAULT_BESS = 4
DEFAULT_SOLAR = 4
DEFAULT_DURATION_HOURS = 4.0
STALL_RATIO_BUDGET = 3.0                # heuristic: slowest run shouldn't take >3x the fastest


# ---------------------------------------------------------------------------
# Instrumentation: measure evaluate_tick()'s own sync compute time
# (Design Spec Section 4.3's claim) and each tick's end-to-end delivery
# latency to a WebSocket subscriber, without modifying core/ or
# runtime/ -- this wraps the name run_manager.py resolves at call time.
# ---------------------------------------------------------------------------

@dataclass
class _Instrumentation:
    compute_durations_s: list[float] = field(default_factory=list)
    computed_at: dict[tuple[str, int], float] = field(default_factory=dict)
    delivered_latencies_s: list[float] = field(default_factory=list)

    def reset(self) -> None:
        self.compute_durations_s.clear()
        self.computed_at.clear()
        self.delivered_latencies_s.clear()


_instr = _Instrumentation()


def _instrumented_evaluate_tick(state, sim_time, dt_seconds) -> TickResult:
    start = time.perf_counter()
    result = _uninstrumented_evaluate_tick(state, sim_time, dt_seconds)
    elapsed = time.perf_counter() - start
    _instr.compute_durations_s.append(elapsed)
    _instr.computed_at[(result.run_id, result.tick_index)] = time.perf_counter()
    return result


run_manager_module.evaluate_tick = _instrumented_evaluate_tick  # patch the name run_manager.py calls


class LatencyRecordingSocket:
    """Stands in for a real WebSocket client (Design Spec Section 4.4 /
    Section 12's WebSocketLike Protocol). Records the wall-clock delay
    between evaluate_tick() finishing and this "client" receiving the
    broadcast -- the number the 1-second dashboard-latency NFR is
    actually about."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id

    async def send_json(self, data: dict) -> None:
        received_at = time.perf_counter()
        key = (self.run_id, data["tick_index"])
        computed_at = _instr.computed_at.get(key)
        if computed_at is not None:
            _instr.delivered_latencies_s.append(received_at - computed_at)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

@dataclass
class LoadTestReport:
    label: str
    concurrent_runs: int
    gpu_modules_per_run: int
    turbines_per_run: int
    bess_per_run: int
    solar_per_run: int
    total_ticks: int
    total_wall_clock_s: float
    per_run_wall_clock_s: dict[str, float]
    tick_latency_ms: dict[str, float]      # p50/p95/p99/max
    evaluate_tick_us: dict[str, float]     # p50/p95/p99/max, in microseconds
    nfr_violations: list[str]

    @property
    def passed(self) -> bool:
        return not self.nfr_violations

    def print_summary(self) -> None:
        status = "PASS" if self.passed else "FAIL"
        print(f"\n=== Load test: {self.label} [{status}] ===")
        print(f"  concurrent runs:        {self.concurrent_runs}")
        print(f"  assets/run:              {self.gpu_modules_per_run} GPU / "
              f"{self.turbines_per_run} turbine / {self.bess_per_run} BESS / {self.solar_per_run} solar")
        print(f"  total ticks evaluated:   {self.total_ticks}")
        print(f"  total wall clock:        {self.total_wall_clock_s:.3f}s")
        print(f"  per-run wall clock:      "
              f"min={min(self.per_run_wall_clock_s.values()):.3f}s  "
              f"max={max(self.per_run_wall_clock_s.values()):.3f}s")
        print(f"  tick delivery latency:   p50={self.tick_latency_ms['p50']:.3f}ms  "
              f"p95={self.tick_latency_ms['p95']:.3f}ms  p99={self.tick_latency_ms['p99']:.3f}ms  "
              f"max={self.tick_latency_ms['max']:.3f}ms   (budget: {TICK_LATENCY_BUDGET_MS:.0f}ms)")
        print(f"  evaluate_tick() compute: p50={self.evaluate_tick_us['p50']:.1f}us  "
              f"p95={self.evaluate_tick_us['p95']:.1f}us  p99={self.evaluate_tick_us['p99']:.1f}us  "
              f"max={self.evaluate_tick_us['max']:.1f}us")
        if self.nfr_violations:
            print("  NFR VIOLATIONS:")
            for v in self.nfr_violations:
                print(f"    - {v}")


def _percentiles(values_s: list[float]) -> dict:
    if not values_s:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
    ordered = sorted(values_s)

    def pct(p: float) -> float:
        idx = min(len(ordered) - 1, int(round(p * (len(ordered) - 1))))
        return ordered[idx]

    return {"p50": pct(0.50), "p95": pct(0.95), "p99": pct(0.99), "max": ordered[-1]}


# ---------------------------------------------------------------------------
# Core load-test runner
# ---------------------------------------------------------------------------

async def run_load_test(
    *,
    label: str,
    concurrent_runs: int,
    gpu_modules: int,
    turbines: int,
    bess: int,
    solar: int,
    duration_hours: float,
    playback_speed: float,
    verbose: bool = False,
) -> LoadTestReport:
    _instr.reset()

    hub = WebSocketHub()
    manager = RunManager(hub)
    end_sim_time = duration_hours * 3600.0

    contexts = [
        scenario_factory.build_load_test_context(
            f"{label}-run-{i}",
            gpu_module_count=gpu_modules,
            turbine_count=turbines,
            bess_count=bess,
            solar_count=solar,
            end_sim_time=end_sim_time,
            playback_speed=playback_speed,
        )
        for i in range(concurrent_runs)
    ]
    for ctx in contexts:
        hub.subscribe(ctx.run_id, LatencyRecordingSocket(ctx.run_id))

    per_run_wall_clock_s: dict[str, float] = {}

    async def _run_and_time(ctx) -> None:
        start = time.perf_counter()
        await manager.start_run(ctx)
        await manager._tasks[ctx.run_id]
        per_run_wall_clock_s[ctx.run_id] = time.perf_counter() - start
        if verbose:
            print(f"    [{ctx.run_id}] done in {per_run_wall_clock_s[ctx.run_id]:.3f}s "
                  f"({len(ctx.sink.rows)} ticks)")

    overall_start = time.perf_counter()
    await asyncio.gather(*(_run_and_time(c) for c in contexts))
    overall_wall_clock_s = time.perf_counter() - overall_start

    total_ticks = sum(len(c.sink.rows) for c in contexts)
    tick_latency_ms = {k: v * 1000.0 for k, v in _percentiles(_instr.delivered_latencies_s).items()}
    evaluate_tick_us = {k: v * 1_000_000.0 for k, v in _percentiles(_instr.compute_durations_s).items()}

    violations: list[str] = []

    if tick_latency_ms["p99"] > TICK_LATENCY_BUDGET_MS:
        violations.append(
            f"tick delivery latency p99 ({tick_latency_ms['p99']:.1f}ms) exceeds "
            f"{TICK_LATENCY_BUDGET_MS:.0f}ms budget (functional spec Section 11, Latency)"
        )

    if duration_hours >= 3.9 and overall_wall_clock_s > FOUR_HOUR_SCENARIO_WALL_CLOCK_BUDGET_S:
        violations.append(
            f"4h-scale scenario took {overall_wall_clock_s:.1f}s wall-clock, exceeds "
            f"{FOUR_HOUR_SCENARIO_WALL_CLOCK_BUDGET_S:.0f}s budget (functional spec Section 11, Run duration)"
        )

    if per_run_wall_clock_s:
        fastest = min(per_run_wall_clock_s.values())
        slowest = max(per_run_wall_clock_s.values())
        if fastest > 0 and (slowest / fastest) > STALL_RATIO_BUDGET:
            violations.append(
                f"run completion times vary {slowest / fastest:.1f}x across concurrent runs "
                f"(slowest={slowest:.3f}s, fastest={fastest:.3f}s) -- possible head-of-line "
                f"stall between runs (Design Spec Section 4.2/4.4)"
            )

    return LoadTestReport(
        label=label,
        concurrent_runs=concurrent_runs,
        gpu_modules_per_run=gpu_modules,
        turbines_per_run=turbines,
        bess_per_run=bess,
        solar_per_run=solar,
        total_ticks=total_ticks,
        total_wall_clock_s=overall_wall_clock_s,
        per_run_wall_clock_s=per_run_wall_clock_s,
        tick_latency_ms=tick_latency_ms,
        evaluate_tick_us=evaluate_tick_us,
        nfr_violations=violations,
    )


async def run_stress_matrix(base_runs: int, duration_hours: float, playback_speed: float) -> list[LoadTestReport]:
    """Design Spec Section 9: 'run the 5-concurrent-user test at 2x and
    4x the specified asset counts to characterize headroom ... without
    treating that headroom as a new committed NFR.' Only the 1x report
    counts toward NFR pass/fail; 2x/4x are headroom characterization."""
    reports = []
    for multiplier in (1, 2, 4):
        report = await run_load_test(
            label=f"{multiplier}x",
            concurrent_runs=base_runs,
            gpu_modules=DEFAULT_GPU_MODULES * multiplier,
            turbines=DEFAULT_TURBINES * multiplier,
            bess=DEFAULT_BESS * multiplier,
            solar=DEFAULT_SOLAR * multiplier,
            duration_hours=duration_hours,
            playback_speed=playback_speed,
        )
        report.print_summary()
        if multiplier > 1:
            report.nfr_violations = [v for v in report.nfr_violations]  # kept for visibility only
        reports.append(report)
    return reports


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--runs", type=int, default=DEFAULT_CONCURRENT_RUNS,
                   help=f"concurrent scenario runs (default: {DEFAULT_CONCURRENT_RUNS}, the NFR floor)")
    p.add_argument("--gpu-modules", type=int, default=DEFAULT_GPU_MODULES)
    p.add_argument("--turbines", type=int, default=DEFAULT_TURBINES)
    p.add_argument("--bess", type=int, default=DEFAULT_BESS)
    p.add_argument("--solar", type=int, default=DEFAULT_SOLAR)
    p.add_argument("--duration-hours", type=float, default=DEFAULT_DURATION_HOURS)
    p.add_argument("--speed", type=float, default=0.0, help="playback speed; 0 = max speed (default)")
    p.add_argument("--stress", type=float, default=1.0,
                   help="multiplies gpu/turbine/bess/solar counts (single run, not the full matrix)")
    p.add_argument("--matrix", action="store_true", help="run the 1x/2x/4x headroom sweep (Section 9)")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--report-json", type=str, default=None, help="write machine-readable report(s) here")
    return p.parse_args(argv)


async def _main_async(args: argparse.Namespace) -> int:
    if args.matrix:
        reports = await run_stress_matrix(args.runs, args.duration_hours, args.speed)
        exit_ok = reports[0].passed  # only the 1x (NFR-exact) report gates pass/fail
    else:
        report = await run_load_test(
            label="single-run",
            concurrent_runs=args.runs,
            gpu_modules=int(args.gpu_modules * args.stress),
            turbines=max(1, int(args.turbines * args.stress)),
            bess=max(1, int(args.bess * args.stress)),
            solar=max(1, int(args.solar * args.stress)),
            duration_hours=args.duration_hours,
            playback_speed=args.speed,
            verbose=args.verbose,
        )
        report.print_summary()
        reports = [report]
        exit_ok = report.passed

    if args.report_json:
        with open(args.report_json, "w") as f:
            json.dump([asdict(r) for r in reports], f, indent=2)
        print(f"\nWrote machine-readable report to {args.report_json}")

    return 0 if exit_ok else 1


def main() -> None:
    args = _parse_args()
    exit_code = asyncio.run(_main_async(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
