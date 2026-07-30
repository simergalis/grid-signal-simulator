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
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import time as _time_module
from dataclasses import dataclass, field
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
    }


# ---------------------------------------------------------------------------
# Persistence hook (Design Spec Section 6) -- abstracted behind a
# Protocol so the concurrency layer doesn't hard-depend on SQLAlchemy.
# ---------------------------------------------------------------------------

class TimeseriesSink(Protocol):
    async def append(self, tick: TickResult) -> None: ...
    async def finalize(self, run_id: str, verdict: Optional[str]) -> None: ...


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


# ---------------------------------------------------------------------------
# RunContext
# ---------------------------------------------------------------------------

TICK_INTERVAL_SIM_SECONDS = 5.0  # source spec Section 3.1 evaluation cadence


@dataclass
class RunContext:
    """One active scenario run's isolated state. No field on this
    class is ever shared with another RunContext instance."""

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
# RunManager
# ---------------------------------------------------------------------------

class RunManager:
    """Owns one asyncio.Task per active run. This is the component that
    satisfies the >=5-concurrent-users NFR (functional spec Section 11)
    -- see Design Spec Section 4.2 for the isolation argument."""

    def __init__(self, ws_hub: WebSocketHub) -> None:
        self._ws_hub = ws_hub
        self._contexts: dict[str, RunContext] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._run_id_counter = itertools.count(1)

    def active_run_ids(self) -> list[str]:
        return list(self._contexts.keys())

    def get_context(self, run_id: str) -> Optional[RunContext]:
        return self._contexts.get(run_id)

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
            verdict = None  # TODO: compute pass/fail against scenario assertions (functional spec Section 6/7.2)
            await ctx.sink.finalize(ctx.run_id, verdict)
            self._contexts.pop(ctx.run_id, None)
            self._tasks.pop(ctx.run_id, None)
