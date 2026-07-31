"""
RunManager / RunContext / WebSocketHub -- the concurrency layer.

Design Spec Section 4: this is where all the asyncio-based parallelism
in the system lives. Everything below the WorkloadSignal application
point (core/simulation_core.py, core/asset_modules.py, core/dispatch.py)
is synchronous, pure, and deterministic by design; nothing in this file
should reach into that layer except through evaluate_tick()'s plain
function-call boundary.

RunContext = one active scenario run's entire mutable state. Contexts
share nothing mutable with each other, which is what makes concurrent
runs safe without locks (Design Spec Section 4.2).

Step 9 additions:
  - TimeseriesSink Protocol gains get_eval_rows / get_dropped_ticks /
    get_tick_dicts so _drive can evaluate assertions without knowing
    the concrete sink type.
  - RunContext gains assertions, scenario_name, scenario_id fields.
  - CompletedRun dataclass holds the verdict + all tick dicts for the
    results / playback screen (GET /runs/{run_id}/result, /timeseries).
  - RunManager._completed keeps completed runs in memory until process
    restart (acceptable scope for Step 9; Step 11 will persist them).
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import time as _time_module
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional, Protocol

from core.models import TickResult, WorkloadSignal
from core.sim_clock import SimClock
from core.simulation_core import SimulationState, evaluate_tick
from core._plane_guard import _EVALUATE_TICK_PERMITTED

logger = logging.getLogger("gridsignal.run_manager")


# ---------------------------------------------------------------------------
# WebSocket abstraction (kept minimal so this module has no hard
# dependency on FastAPI/Starlette -- makes the concurrency logic
# testable without a real ASGI server, per Design Spec Section 12).
# ---------------------------------------------------------------------------

class WebSocketLike(Protocol):
    async def send_json(self, data: dict) -> None: ...


# Step 7 — back-pressure bound: one 4 Hz render frame (250 ms).
# If a browser tab is backgrounded its TCP receive buffer fills and
# ws.send_json() never resolves, blocking broadcast() indefinitely.
# Wrapping each send in asyncio.wait_for() caps the delay to one frame;
# a stalled socket is dropped via the same unsubscribe path as an exception.
#
# KNOWN BOUNDARY (Step 7): a dropped subscriber does NOT auto-recover.
# Until Step 8 adds snapshot-on-connect and the resync protocol
# (Design Spec §2.2), a backgrounded tab that returns will show a dead
# panel until the user reloads.  This is acceptable for Step 7 but must
# be a known boundary, not a surprise.
_SEND_TIMEOUT_S: float = 0.25


class WebSocketHub:
    """Per-run pub/sub. Design Spec Section 4.4: broadcast fans out
    concurrently to every subscriber of a run; a slow or dead
    connection doesn't block the others or the run loop itself."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[WebSocketLike]] = {}

    def subscribe(self, run_id: str, ws: WebSocketLike) -> None:
        self._subscribers.setdefault(run_id, set()).add(ws)

    def unsubscribe(self, run_id: str, ws: WebSocketLike) -> None:
        subs = self._subscribers.get(run_id)
        if subs:
            subs.discard(ws)
            if not subs:
                del self._subscribers[run_id]

    async def broadcast(self, run_id: str, tick_result: TickResult) -> None:
        subs = list(self._subscribers.get(run_id, ()))
        if not subs:
            return
        payload = _tick_result_to_dict(tick_result)

        async def _safe_send(ws: WebSocketLike) -> None:
            try:
                await asyncio.wait_for(ws.send_json(payload), timeout=_SEND_TIMEOUT_S)
            except (Exception, asyncio.TimeoutError):  # noqa: BLE001
                # TimeoutError: TCP buffer full (backgrounded tab) — drop now.
                # Exception:    dead socket — drop now.
                # Either path: subscriber is removed; broadcast() returns
                # within _SEND_TIMEOUT_S of starting, not indefinitely.
                logger.info("dropping stale subscriber for run %s (timeout or error)", run_id)
                self.unsubscribe(run_id, ws)

        await asyncio.gather(*(_safe_send(ws) for ws in subs))


def _tick_result_to_dict(tick: TickResult) -> dict:
    import math as _math  # local import — _tick_result_to_dict is in the runtime layer;
    # math is a stdlib module so there is no plane-separation concern, but keeping
    # the import local avoids polluting the module namespace.
    return {
        "run_id": tick.run_id,
        "tick_index": tick.tick_index,
        "sim_time_seconds": tick.sim_time_seconds,
        "p_compute_mw": round(tick.p_compute_mw, 4),
        "p_cooling_mw": round(tick.p_cooling_mw, 4),
        "p_total_mw": round(tick.p_total_mw, 4),
        "net_demand_mw": round(tick.net_demand_mw, 4),
        "turbine_output_mw": round(tick.turbine_output_mw, 4),
        "bess_output_mw": round(tick.bess_output_mw, 4),
        "bess_soc_fraction": round(tick.bess_soc_fraction, 4),
        "confidence_lower_mw": round(tick.confidence.lower_bound_mw, 4),
        "confidence_upper_mw": round(tick.confidence.upper_bound_mw, 4),
        "data_quality_tags": sorted(t.value for t in tick.confidence.tags),
        "insufficient_reserve_alert": tick.insufficient_reserve_alert,
        "checkpoint_states": tick.checkpoint_states,
        # Step 7 additions — required by live dashboard panels.
        # p_renewable_mw: ForecastChart 4th trace; not recoverable from net_demand_mw
        #   after the lossy clamp max(0, p_total − p_renewable).
        "p_renewable_mw": round(tick.p_renewable_mw, 4),
        # bess_bridging_seconds: AssetReservePanel "bridging capability in seconds".
        #   math.inf (net_demand_mw == 0 → no load) is capped at 86 400 s (24 h)
        #   for JSON safety; the UI renders this as "full reserve".
        "bess_bridging_seconds": round(min(tick.bess_bridging_seconds, 86400.0), 1),
        # dt_lead_next_s: HeroPanel countdown — seconds to next GPU full-TDP.
        #   0.0 when no job is currently ramping.
        "dt_lead_next_s": round(tick.dt_lead_next_s, 2),
        # bridging_basis: which demand figure is binding for bess_bridging_seconds.
        #   "predicted_peak" — staged prediction's peak shortfall is binding.
        #   "current_demand" — current net_demand_mw is binding.
        #   "no_load"        — net demand is zero; no bridging required.
        "bridging_basis": tick.bridging_basis,
    }


# ---------------------------------------------------------------------------
# Persistence hook (Design Spec Section 6) -- abstracted behind a
# Protocol so the concurrency layer doesn't hard-depend on SQLAlchemy.
#
# Step 9 additions to the Protocol:
#   get_eval_rows  — flush pending writes, return lightweight EvalRow tuples
#                    for verdict evaluation.
#   get_dropped_ticks — number of ticks lost due to write-queue pressure.
#   get_tick_dicts — flush pending writes, return full tick dicts for playback.
# ---------------------------------------------------------------------------

from runtime.verdict import EvalRow, VerdictResult, evaluate_verdict  # noqa: E402 — runtime→runtime OK


class TimeseriesSink(Protocol):
    async def append(self, tick: TickResult) -> None: ...
    async def finalize(self, run_id: str, verdict: Optional[str]) -> None: ...
    async def get_eval_rows(self, run_id: str) -> list[EvalRow]: ...
    def get_dropped_ticks(self) -> int: ...
    async def get_tick_dicts(self, run_id: str) -> list[dict]: ...


class InMemoryTimeseriesSink:
    """Stub used for tests and local dev; swap for the real
    SQLAlchemy-async-backed sink (runtime/persistence.py, not included
    in this skeleton) in production."""

    def __init__(self) -> None:
        self.rows: list[TickResult] = []
        self.finalized: dict[str, Optional[str]] = {}

    async def append(self, tick: TickResult) -> None:
        self.rows.append(tick)

    async def finalize(self, run_id: str, verdict: Optional[str]) -> None:
        self.finalized[run_id] = verdict

    async def get_eval_rows(self, run_id: str) -> list[EvalRow]:
        """Convert in-memory TickResult rows to lightweight EvalRows."""
        return [
            EvalRow(
                tick_index=r.tick_index,
                p_total_mw=r.p_total_mw,
                bess_soc_fraction=r.bess_soc_fraction,
                insufficient_reserve_alert=r.insufficient_reserve_alert,
            )
            for r in self.rows
        ]

    def get_dropped_ticks(self) -> int:
        """InMemory never drops ticks — queue is unbounded."""
        return 0

    async def get_tick_dicts(self, run_id: str) -> list[dict]:
        """Return all ticks as serialisation dicts (same format as WS broadcast)."""
        return [_tick_result_to_dict(r) for r in self.rows]


# ---------------------------------------------------------------------------
# RunContext
# ---------------------------------------------------------------------------

TICK_INTERVAL_SIM_SECONDS = 5.0  # source spec Section 3.1 evaluation cadence


@dataclass
class RunContext:
    """One active scenario run's isolated state. No field on this
    class is ever shared with another RunContext instance.

    Step 9 additions:
      assertions   — list of AssertionSpec objects (from runtime.verdict);
                     empty list → verdict is INCONCLUSIVE.
      scenario_name — human-readable name, surfaced in the results screen.
      scenario_id   — stable scenario ID if started via POST /runs with a
                      stored scenario; None for the direct job_id path.
    """

    run_id: str
    sim_state: SimulationState
    events: list[WorkloadSignal]           # sorted ascending by timestamp
    dt_lead_seconds: float
    end_sim_time: float                    # scenario duration, e.g. 4h = 14400s
    playback_speed: float = 1.0            # 1.0 = real-time-equivalent, up to "max"
    sink: TimeseriesSink = field(default_factory=InMemoryTimeseriesSink)
    sim_time: float = 0.0
    _next_event_idx: int = 0
    cancelled: bool = False
    # Step 9 — verdict evaluation inputs
    assertions: list = field(default_factory=list)  # list[AssertionSpec]
    scenario_name: str = ""
    scenario_id: Optional[str] = None

    def is_complete(self) -> bool:
        return self.cancelled or self.sim_time >= self.end_sim_time

    def _apply_due_events(self) -> None:
        while (
            self._next_event_idx < len(self.events)
            and self.events[self._next_event_idx].timestamp <= self.sim_time
        ):
            signal = self.events[self._next_event_idx]
            self.sim_state.apply_workload_signal(signal, self.dt_lead_seconds)
            self._next_event_idx += 1

    def step(self) -> TickResult:
        """Advance exactly one tick and return the result. Synchronous
        and deterministic -- see core/simulation_core.py.

        Step 4 — runtime purity sentinel: set _EVALUATE_TICK_PERMITTED True
        for the duration of evaluate_tick(), then reset it unconditionally.
        The sentinel is defined in core/_plane_guard.py (so evaluate_tick can
        check it without importing runtime/); it is SET HERE by the runtime
        caller, never inside core/ itself — self-signing would defeat the guard.

        Step 5 — SimClock injection: construct the SimClock here (the only
        place in the runtime that reads the wall clock) and pass it into
        evaluate_tick().  core/ never reads the wall clock directly — the
        static gate in scripts/check_plane_separation.py enforces this.
        wall_stamp_utc is a UTC Unix timestamp (time.time()) so the persistence
        layer can record both clocks alongside every RunTimeseries row, enabling
        forecast-error attribution against real latency (v2.5 §22.8).
        """
        self._apply_due_events()
        clock = SimClock(
            sim_time=self.sim_time,
            dt_seconds=TICK_INTERVAL_SIM_SECONDS,
            wall_stamp_utc=_time_module.time(),
            rate=self.playback_speed,
            tick_seq=self.sim_state.tick_index,
        )
        _token = _EVALUATE_TICK_PERMITTED.set(True)
        try:
            result = evaluate_tick(self.sim_state, clock)
        finally:
            _EVALUATE_TICK_PERMITTED.reset(_token)
        self.sim_time += TICK_INTERVAL_SIM_SECONDS
        return result

    def wall_clock_sleep_seconds(self) -> float:
        """How long the RunManager should await between ticks. At
        playback_speed == "max" (represented as 0 or None by callers),
        this returns 0 and the run proceeds as fast as the event loop
        can schedule it -- still cooperatively, still yielding to
        sibling runs via the awaited sleep(0)."""
        if self.playback_speed <= 0:
            return 0.0
        return TICK_INTERVAL_SIM_SECONDS / self.playback_speed


# ---------------------------------------------------------------------------
# CompletedRun — in-memory store for results / playback screen (Step 9)
# ---------------------------------------------------------------------------

@dataclass
class CompletedRun:
    """Holds the result of a finished run for the results screen.

    Kept in RunManager._completed until process restart.  The verdict
    JSON string is also persisted to the Scenario ORM row via finalize()
    for long-term durability; tick_dicts are in-memory only (Step 11 will
    add a proper archived-run table).

    tick_dicts mirrors the format produced by _tick_result_to_dict() so
    the timeseries endpoint can stream them with gap_before flags without
    any further transformation.
    """
    run_id: str
    scenario_id: Optional[str]
    scenario_name: str
    completed_at: datetime
    verdict: VerdictResult
    tick_dicts: list[dict]   # ordered by tick_index; gap_before added by endpoint
    dropped_ticks: int


# ---------------------------------------------------------------------------
# RunManager
# ---------------------------------------------------------------------------

class RunManager:
    """Owns one asyncio.Task per active run. This is the component that
    satisfies the >=5-concurrent-users NFR (functional spec Section 11)
    -- see Design Spec Section 4.2 for the isolation argument.

    Step 9: _completed holds finished runs for GET /runs/{id}/result
    and GET /runs/{id}/timeseries.
    """

    def __init__(self, ws_hub: WebSocketHub) -> None:
        self._ws_hub = ws_hub
        self._contexts: dict[str, RunContext] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._run_id_counter = itertools.count(1)
        # Step 9: completed runs stored for results/playback screen.
        self._completed: dict[str, CompletedRun] = {}

    def active_run_ids(self) -> list[str]:
        return list(self._contexts.keys())

    def get_context(self, run_id: str) -> Optional[RunContext]:
        return self._contexts.get(run_id)

    def get_completed(self, run_id: str) -> Optional[CompletedRun]:
        """Return a completed run's data, or None if not found."""
        return self._completed.get(run_id)

    async def start_run(self, ctx: RunContext) -> str:
        self._contexts[ctx.run_id] = ctx
        task = asyncio.create_task(self._drive(ctx), name=f"run-{ctx.run_id}")
        self._tasks[ctx.run_id] = task
        return ctx.run_id

    async def cancel_run(self, run_id: str) -> None:
        ctx = self._contexts.get(run_id)
        if ctx:
            ctx.cancelled = True
        task = self._tasks.get(run_id)
        if task:
            await task  # let _drive's own cleanup (finally block) run

    async def _drive(self, ctx: RunContext) -> None:
        try:
            while not ctx.is_complete():
                tick_result = ctx.step()                          # sync, in-budget (Design Spec 4.3)
                await ctx.sink.append(tick_result)                  # I/O -- yields to sibling runs
                await self._ws_hub.broadcast(ctx.run_id, tick_result)  # I/O -- yields to sibling runs

                sleep_s = ctx.wall_clock_sleep_seconds()
                await asyncio.sleep(sleep_s if sleep_s > 0 else 0)   # always yield at least once
        except asyncio.CancelledError:
            logger.info("run %s cancelled mid-flight", ctx.run_id)
            raise
        finally:
            # Step 9: evaluate assertions and store the completed run.
            # Two-phase design:
            #   1. get_eval_rows/get_tick_dicts (flushes sink queue if needed)
            #   2. evaluate_verdict (pure, in-process)
            #   3. finalize (writes verdict to persistence layer)
            #   4. store CompletedRun in _completed for the results API
            verdict_result: Optional[VerdictResult] = None
            verdict_json: Optional[str] = None
            dropped: int = 0
            tick_dicts: list[dict] = []

            try:
                eval_rows = await ctx.sink.get_eval_rows(ctx.run_id)
                dropped = ctx.sink.get_dropped_ticks()
                # expected_last_tick_index: the tick_index of the final tick
                # in a run that completed normally.  Equals end_sim_time / dt,
                # because tick_index starts at 1 and increments each step.
                expected_last = round(ctx.end_sim_time / TICK_INTERVAL_SIM_SECONDS)
                verdict_result = evaluate_verdict(
                    ctx.assertions,
                    eval_rows,
                    dropped_ticks=dropped,
                    expected_last_tick_index=expected_last,
                )
                verdict_json = verdict_result.to_json()
            except Exception:
                logger.exception("run %s: verdict evaluation failed", ctx.run_id)

            try:
                tick_dicts = await ctx.sink.get_tick_dicts(ctx.run_id)
            except Exception:
                logger.exception("run %s: get_tick_dicts failed", ctx.run_id)

            await ctx.sink.finalize(ctx.run_id, verdict_json)

            # Store for the results/playback screen.
            self._completed[ctx.run_id] = CompletedRun(
                run_id=ctx.run_id,
                scenario_id=ctx.scenario_id,
                scenario_name=ctx.scenario_name,
                completed_at=datetime.now(timezone.utc),
                verdict=verdict_result or VerdictResult(
                    overall="INCONCLUSIVE",
                    tick_count=0,
                    dropped_ticks=dropped,
                    gap_count=0,
                ),
                tick_dicts=tick_dicts,
                dropped_ticks=dropped,
            )

            self._contexts.pop(ctx.run_id, None)
            self._tasks.pop(ctx.run_id, None)
