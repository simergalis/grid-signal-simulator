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
import functools
import itertools
import logging
import os as _os
import statistics as _statistics
import time as _time_module
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace as _dc_replace
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional, Protocol

from core.models import TickResult, WorkloadSignal
from core.sim_clock import SimClock
from core.simulation_core import SimulationState, evaluate_tick
from core._plane_guard import _EVALUATE_TICK_PERMITTED

logger = logging.getLogger("gridsignal.run_manager")

# Maximum number of recent TickResult objects kept in RunContext.tick_history.
# 120 ticks × 5 s = 10 min of simulated history — enough for all six agents.
_TICK_HISTORY_MAXLEN: int = 120

# Inlet temperature bounds (PreStagingConfig defaults, PROTO-10).
_INLET_LO_C: float = 18.0
_INLET_HI_C: float = 24.0


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
        # Step 10 — §8.1 pre-staging shift applied this tick.
        # 0.0 when PreStagingEngine is not active or gap was zero.
        "pre_staging_shift_mw": round(tick.pre_staging_shift_mw, 4),
        # AB3 — fields present on TickResult but previously missing from the dict.
        # Serialised so consumers (playback, energy-summary, TC-68 audit) can see them.
        #
        # wall_stamp_utc is intentionally excluded: the existing test
        # test_websocket_subscriber_receives_tick_payload asserts it must NOT
        # appear in WebSocket payloads (runtime-internal; not part of the wire format).
        #
        # unrecognised_profile_alerts: frozenset[str] → sorted list for JSON stability.
        "unrecognised_profile_alerts": sorted(tick.unrecognised_profile_alerts),
        # curtailment_proposal_tiers: tuple[str, ...] — which curtailment tiers were proposed.
        "curtailment_proposal_tiers": list(tick.curtailment_proposal_tiers),
        # pms_fast_shed_active: True when PMS fast shed is in effect this tick.
        "pms_fast_shed_active": tick.pms_fast_shed_active,
        # pms_order_conflict: None or a string describing the detected conflict.
        "pms_order_conflict": tick.pms_order_conflict,
        # scada_commands_issued: count of SCADA commands issued this tick (TC-68).
        "scada_commands_issued": tick.scada_commands_issued,
        # W1c — thermal headroom (stamped onto TickResult before sink/broadcast).
        "rated_cooling_mw":   round(tick.rated_cooling_mw, 4),
        "absorbable_mw":      round(tick.absorbable_mw, 3),
        "time_to_limit_s":    round(tick.time_to_limit_s, 1),
        "approach_rate_mw_s": round(tick.approach_rate_mw_s, 6),
        # AE2: per-unit turbine specs — list of dicts for JSON serialisation.
        # Constant across ticks; carried on every payload so the fleet modal
        # can drive its display (unit count, rated MW, effective ramp) without
        # a separate API call.
        "turbine_units": list(tick.turbine_units),
        # Kubernetes demand agent metrics — null when kube_config is not active.
        # non-null only on runs with kube_config set in the ScenarioSpec.
        "kube_metrics": (
            {
                "utilization":      round(tick.kube_metrics.utilization, 4),
                "node_count":       tick.kube_metrics.node_count,
                "power_cap_active": tick.kube_metrics.power_cap_active,
                "headroom_mw":      round(tick.kube_metrics.headroom_mw, 3),
                "active_jobs":      tick.kube_metrics.active_jobs,
                "admitted_nodes":   tick.kube_metrics.admitted_nodes,
            }
            if tick.kube_metrics is not None
            else None
        ),
        # Solar weather metadata — stamped from RunContext at each tick (constant
        # per run).  Empty strings when solar is absent or run started via direct path.
        "solar_weather":    tick.solar_weather,
        "solar_conditions": tick.solar_conditions,
        # W2a: advisory telemetry — None when no registry is active (LP-1 / tests).
        # Keys: backend, agents_armed, proposals_total, proposals_pending,
        #        last_proposal_sim_time, per_agent (dict[str, float]).
        "advisory_telemetry": tick.advisory_telemetry,
        # Phase 10: fabric model modal-view — six plant-plane fields + link utilisation.
        # null when FabricEngine is not wired (headless tests, direct job-id path).
        "fabric": tick.fabric_modal,
        # GT-1: §7.4 contingency coverage — computed per tick after dispatch arbitration.
        # null when absent (legacy path); otherwise a dict with all ContingencyCoverage fields.
        "contingency_coverage": (
            {
                "state":                     tick.contingency_coverage.state.value,
                "tripped_unit_id":           tick.contingency_coverage.tripped_unit_id,
                "deficit_mw":                round(tick.contingency_coverage.deficit_mw, 3),
                "headroom_surviving_mw":     round(tick.contingency_coverage.headroom_surviving_mw, 3),
                "r_surviving_mw_per_s":      round(tick.contingency_coverage.r_surviving_mw_per_s, 4),
                "bess_bridging_available_mw": round(tick.contingency_coverage.bess_bridging_available_mw, 3),
                "bess_usable_energy_mwh":    round(tick.contingency_coverage.bess_usable_energy_mwh, 3),
                "power_test_passes":         tick.contingency_coverage.power_test_passes,
                "energy_test_passes":        tick.contingency_coverage.energy_test_passes,
                "closable":                  tick.contingency_coverage.closable,
                "time_to_close_s":           round(min(tick.contingency_coverage.time_to_close_s, 86400.0), 1),
                "shed_required_mw":          round(tick.contingency_coverage.shed_required_mw, 3),
                "ride_through_s":            round(min(tick.contingency_coverage.ride_through_s, 86400.0), 1),
                "dispatchable_mw":           round(tick.contingency_coverage.dispatchable_mw, 3),
                "renewable_mw":              round(tick.contingency_coverage.renewable_mw, 3),
            }
            if tick.contingency_coverage is not None
            else None
        ),
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


# ---------------------------------------------------------------------------
# §21.2 cost model bridge (AB2)
# Keeps core/ imports out of api/ (plane separation rule).
# api/routes/runs.py calls compute_run_cost_from_completed(); runtime/ → core/
# is the allowed direction.
# ---------------------------------------------------------------------------

_COST_CFG_DEFAULTS: dict = {
    "grid_import_price_per_mwh":       120.0,    # CHOSEN PROTO-21-COST: representative spot
    "turbine_capital_per_mw_year":     45_000.0, # CHOSEN PROTO-21-COST: gas turbine capex amort.
    "turbine_variable_per_mwh":        55.0,     # CHOSEN PROTO-21-COST: fuel + variable O&M
    "storage_roundtrip_efficiency":    0.88,     # matches RT_EFF in energy-summary
    "storage_charge_price_per_mwh":    60.0,     # CHOSEN PROTO-21-COST: off-peak charge cost
    "storage_discharge_price_per_mwh": 0.0,      # CHOSEN PROTO-21-COST: BESS negligible var cost
}


def compute_run_cost_from_completed(
    completed: "CompletedRun",
    generation_mwh: float,
    grid_import_mwh: float,
    storage_charge_mwh: float,
    duration_hours: float,
) -> tuple[dict, dict]:
    """Compute §21.2 cost breakdown from a completed run.

    Returns (cost_breakdown_dict, cost_model_config_dict).
    runtime/ → core/ is the allowed import direction; api/ must not import
    from core/ directly (plane separation rule).
    """
    from core.cost_model import CostModelConfig, CostModelEngine  # lazy — plane-safe

    cfg = CostModelConfig(**_COST_CFG_DEFAULTS)
    engine = CostModelEngine(cfg)
    result = engine.compute_run_cost(
        grid_import_mwh    = grid_import_mwh,
        generation_mwh     = generation_mwh,
        storage_charge_mwh = storage_charge_mwh,
        run_duration_hours = duration_hours,
        turbine_rated_mw   = completed.turbine_rated_mw,
    )
    return (
        {
            "grid_import_cost":         result.grid_import_cost,
            "generation_cost":          result.generation_cost,
            "storage_cost":             result.storage_cost,
            "total_cost":               result.total_cost,
            "generation_duty_fraction": result.generation_duty_fraction,
            "grid_fraction":            result.grid_fraction,
        },
        _COST_CFG_DEFAULTS,
    )


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
    # Solar weather metadata — set by runs.py after generate_solar_forecast();
    # empty strings on direct job-id path or when solar is absent.
    solar_weather:    str = ""
    solar_conditions: str = ""

    # W1 — advisory, telemetry, procurement wiring (all Optional so existing
    # tests that call build_run_context() directly are unaffected).
    # Types are Any to avoid circular runtime/ → advisory/ imports at module
    # load time; the concrete types are instantiated in scenario_factory.py.
    registry: Optional[Any] = None            # AgentRegistry
    tick_history: list = field(default_factory=list)  # recent TickResults for agents

    telemetry_ingestor: Optional[Any] = None  # NetworkTelemetryIngestor
    corroborator: Optional[Any] = None        # FabricCorroborator

    price_curve: Optional[Any] = None         # SyntheticPriceCurve
    grid_capacity: list = field(default_factory=list)  # list[GridCapacity]

    # Thermal state — updated each tick by _update_thermal_state().
    # Preserved on RunContext so the /thermal endpoint can read it at any tick.
    _inlet_temp_c: float = 21.0          # synthetic inlet temperature (°C)
    _last_cooling_mw: float = 0.0        # cooling load at previous tick
    _approach_rate_mw_s: float = 0.0     # MW/s rate of change (positive = rising)
    _rated_cooling_mw: float = 5.0       # rated cooling capacity; set by factory

    # AB2: sum of all turbine rated_mw; set by build_run_context_from_spec
    # for §21.2 cost model in the energy-summary endpoint.  0.0 = unknown.
    turbine_rated_mw: float = 0.0

    # AE2: per-unit turbine specs as plain dicts — stamped onto every TickResult
    # so the fleet modal can drive its display from live data without a separate
    # API call.  Set by build_run_context_from_spec from spec_data["turbine_units"].
    # Empty tuple for contexts built without a spec (tests, load test).
    turbine_unit_specs: tuple = field(default_factory=tuple)

    # AD1: optional engine instances — instantiated by build_run_context_from_spec
    # when the corresponding *_config field is set in ScenarioSpec.
    # Types are Any to avoid circular imports at module load time.
    # All three are observe-only: they read TickResult fields but never write
    # to sim_state, so they do NOT affect the dispatch trace hash.
    procurement_layer: Optional[Any] = None       # ProcurementLayer (TC-47, TC-52)
    maintenance_layer: Optional[Any] = None       # MaintenanceLayer (TC-58, TC-59, TC-60)
    ramp_relaxation_engine: Optional[Any] = None  # RampRelaxationEngine (TC-75, TC-76)

    # Phase 10: FabricEngine — None when not wired (headless tests, direct path).
    fabric_engine: Optional[Any] = None            # FabricEngine

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
    # AB2: turbine fleet rated capacity (MW); used by energy-summary cost model.
    turbine_rated_mw: float = 0.0


# ---------------------------------------------------------------------------
# RunManager
# ---------------------------------------------------------------------------

def _ingest_synthetic_telemetry(ctx: RunContext, tick: TickResult) -> None:
    """W1b: synthesise fabric switch telemetry from the current compute load
    and pass it through NetworkTelemetryIngestor + FabricCorroborator.

    Scale: 1 MW compute ≈ 200 Mbps RX throughput (CHOSEN — PROTO-W1).
    At 5+ MW the spine port exceeds the 1 Gbps FabricCorroborator.TRAFFIC_RISE_THRESHOLD_BPS,
    which triggers fabric-rise detection and allows corroboration to proceed.

    Imports are lazy to avoid a circular runtime/ → advisory/ dependency at
    module load time (advisory/ imports from runtime/advisory_gate, not run_manager).
    """
    from core.network_telemetry import NetworkTelemetry, ClockDiscipline  # local — lazy

    rx_bps = max(0.0, tick.p_compute_mw * 200_000_000.0)   # 200 Mbps per MW
    tx_bps = rx_bps * 0.93
    t = tick.tick_index  # unique per tick — used for deduplication event_id

    spine = NetworkTelemetry(
        event_id=f"nt-spine-{t}",
        switch_id="sw-spine-01",
        site_id=ctx.sim_state.site.site_id,
        interface_id="Ethernet1/1",
        throughput_rx_bps=rx_bps,
        throughput_tx_bps=tx_bps,
        error_counters={},
        optical_power_tx_dbm=-3.2,
        optical_power_rx_dbm=-5.1,
        sample_interval_ms=5000.0,
        timestamp=tick.sim_time_seconds,
        clock_discipline=ClockDiscipline.PTP,
        observed_skew_ms=0.4,
    )
    leaf = NetworkTelemetry(
        event_id=f"nt-leaf-{t}",
        switch_id="sw-leaf-01",
        site_id=ctx.sim_state.site.site_id,
        interface_id="Ethernet1/5",
        throughput_rx_bps=rx_bps * 0.38,
        throughput_tx_bps=tx_bps * 0.38,
        error_counters={},
        optical_power_tx_dbm=-6.0,
        optical_power_rx_dbm=-8.2,
        sample_interval_ms=5000.0,
        timestamp=tick.sim_time_seconds,
        clock_discipline=ClockDiscipline.NTP,
        observed_skew_ms=320.0,
    )
    for rec in (spine, leaf):
        ctx.telemetry_ingestor.ingest(rec, tick.sim_time_seconds)
        if ctx.corroborator is not None:
            ctx.corroborator.ingest_telemetry(rec, tick.sim_time_seconds)


def _update_thermal_state(ctx: RunContext, tick: TickResult) -> None:
    """W1c: update the in-RunContext thermal state after each tick.

    Computes approach_rate from the delta between consecutive ticks and
    tracks a synthetic inlet temperature that rises linearly with cooling
    utilisation (18°C–24°C band, PROTO-10 defaults).
    """
    current_mw = tick.p_cooling_mw
    ctx._approach_rate_mw_s = (current_mw - ctx._last_cooling_mw) / TICK_INTERVAL_SIM_SECONDS
    ctx._last_cooling_mw = current_mw

    if ctx._rated_cooling_mw > 0:
        utilisation = min(1.0, current_mw / ctx._rated_cooling_mw)
    else:
        utilisation = 0.5
    # Temperature rises to 85% of the comfort band ceiling at full utilisation.
    ctx._inlet_temp_c = _INLET_LO_C + utilisation * (_INLET_HI_C - _INLET_LO_C) * 0.85


# AD2: dedicated bounded executor for advisory (LLM) calls.
#
# asyncio.to_thread() uses the loop's default ThreadPoolExecutor
# (min(32, cpu_count+4)).  With 5 concurrent runs and 6 agents each,
# tick 1 can submit up to 30 tasks simultaneously — enough to saturate
# the default pool on a Replit container and exhaust available HTTP
# sockets.  A dedicated 4-worker pool keeps the LLM call count bounded:
# cadence floors (FLOOR_WALL_S / CEILING_WALL_S) mean steady-state
# throughput is far below 4/s, and the tick-1 stampede (6 agents × N
# runs) queues harmlessly rather than saturating shared infrastructure.
# thread_name_prefix makes advisory threads identifiable in thread dumps.
_ADVISORY_EXECUTOR = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="advisory",
)


def _report_drive_profile(
    run_id: str,
    sec: dict[str, list[float]],
    total_wall_s: float,
) -> None:
    """AC3: print a per-section timing table to the run_manager logger.

    Activated by setting GS_PROFILE_DRIVE=1 in the environment before
    starting the server (or load test).  Sections are named with a
    sortable prefix so they print in hot-path order.  p50 and p95 are
    reported to catch both the typical-case cost and the tail spike —
    a mean-only instrument missed the ~6 s LLM-call tail for three
    sessions.
    """
    n_ticks = len(sec.get("A_evaluate_tick", []))
    lines = [
        f"GS_PROFILE_DRIVE  run={run_id!r}  ticks={n_ticks}  "
        f"wall={total_wall_s:.3f}s",
        f"  {'Section':<36}  {'n':>5}  {'total':>8}  {'p50 ms':>8}  {'p95 ms':>8}",
        f"  {'-'*36}  {'-'*5}  {'-'*8}  {'-'*8}  {'-'*8}",
    ]
    measured = 0.0
    for name in sorted(sec):
        samples = sec[name]
        n = len(samples)
        tot = sum(samples)
        measured += tot
        srt = sorted(samples)
        p50_ms = _statistics.median(srt) * 1000
        p95_ms = srt[min(n - 1, int(0.95 * n))] * 1000
        lines.append(
            f"  {name:<36}  {n:>5}  {tot:>8.3f}s  {p50_ms:>8.3f}  {p95_ms:>8.3f}"
        )
    lines.append(
        f"  {'unmeasured overhead':<36}  {'':>5}  "
        f"{total_wall_s - measured:>8.3f}s"
    )
    logger.info("\n".join(lines))


class RunManager:
    """Owns one asyncio.Task per active run. This is the component that
    satisfies the >=5-concurrent-users NFR (functional spec Section 11)
    -- see Design Spec Section 4.2 for the isolation argument.

    Step 9: _completed holds finished runs for GET /runs/{id}/result
    and GET /runs/{id}/timeseries.
    W1: _registries holds AgentRegistry instances preserved after run
    completion so that GET /proposals/{run_id} works for completed runs.
    """

    def __init__(self, ws_hub: WebSocketHub) -> None:
        self._ws_hub = ws_hub
        self._contexts: dict[str, RunContext] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._run_id_counter = itertools.count(1)
        # Step 9: completed runs stored for results/playback screen.
        self._completed: dict[str, CompletedRun] = {}
        # W1: advisorry registries preserved post-run for /proposals endpoint.
        self._registries: dict[str, Any] = {}

    def active_run_ids(self) -> list[str]:
        return list(self._contexts.keys())

    def get_context(self, run_id: str) -> Optional[RunContext]:
        return self._contexts.get(run_id)

    def get_registry(self, run_id: str) -> Optional[Any]:
        """Return the AgentRegistry for a run (active or completed).

        Active runs: read from the RunContext directly.
        Completed runs: read from _registries (preserved in _drive's finally block).
        Returns None if the run has no registry (test-only contexts) or is unknown.
        """
        ctx = self._contexts.get(run_id)
        if ctx is not None:
            return ctx.registry
        return self._registries.get(run_id)

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
        # W1b: pre-register all STARTING events with the corroborator so
        # fabric traffic rises can be matched against known predicted starts.
        if ctx.corroborator is not None:
            for evt in ctx.events:
                if getattr(evt.event_type, "value", str(evt.event_type)) == "starting":
                    ctx.corroborator.register_predicted_start(
                        evt.job_id,
                        evt.timestamp,
                    )

        # Tracks external task.cancel() so finally can skip verdict drain.
        _cancelled_externally = False

        # AC3: per-section timing. Activate with GS_PROFILE_DRIVE=1.
        # Reports p50 + p95 per section at run completion (via logger.info).
        # Off by default — the boolean check costs ~10 ns per guard when False.
        _profiling: bool = bool(_os.environ.get("GS_PROFILE_DRIVE"))
        _sec: dict[str, list[float]] = {}
        _drive_t0: float = _time_module.perf_counter()

        try:
            while not ctx.is_complete():
                # ── A: evaluate_tick ──────────────────────────────────────
                if _profiling: _t0 = _time_module.perf_counter()
                tick_result = ctx.step()                           # sync, in-budget (Design Spec 4.3)
                if _profiling: _sec.setdefault("A_evaluate_tick", []).append(_time_module.perf_counter() - _t0)

                # ── B: thermal state (BEFORE sink/broadcast) ──────────────
                # Enrich the frozen TickResult with thermal fields via
                # dataclasses.replace() — TickResult is frozen=True so direct
                # attribute assignment would raise FrozenInstanceError.
                # The replaced instance replaces the local name; the original
                # object emitted by evaluate_tick() is discarded.  This happens
                # BEFORE sink.append() / broadcast() so both the stored
                # timeseries row and the live WebSocket payload carry thermal data.
                if _profiling: _t0 = _time_module.perf_counter()
                _update_thermal_state(ctx, tick_result)
                _th_rated    = ctx._rated_cooling_mw
                _th_absorb   = max(0.0, _th_rated - tick_result.p_cooling_mw)
                _th_approach = ctx._approach_rate_mw_s
                tick_result  = _dc_replace(
                    tick_result,
                    rated_cooling_mw=_th_rated,
                    absorbable_mw=_th_absorb,
                    approach_rate_mw_s=_th_approach,
                    time_to_limit_s=(
                        min(_th_absorb / _th_approach, 86_400.0)
                        if _th_approach > 1e-6 else 86_400.0
                    ),
                    # AE2: per-unit turbine specs from RunContext — constant
                    # across ticks but stamped each tick so every TickResult in
                    # tick_history carries the data the fleet modal needs.
                    turbine_units=ctx.turbine_unit_specs,
                    # Solar weather metadata — constant per run, stamped so the
                    # Solar PV modal can surface the Mistral forecast label without
                    # a separate endpoint.  Empty strings on direct job-id path.
                    solar_weather=ctx.solar_weather,
                    solar_conditions=ctx.solar_conditions,
                    # W2a: advisory telemetry — snapshot from the gate *before* this
                    # tick's run_all() (section E).  Reflects proposals from ticks 0…t−1.
                    # None when no registry is wired (LP-1 / headless tests).
                    advisory_telemetry=(
                        ctx.registry.telemetry_snapshot()
                        if ctx.registry is not None else None
                    ),
                )
                if _profiling: _sec.setdefault("B_thermal_update", []).append(_time_module.perf_counter() - _t0)

                # ── B2: fabric model tick (Phase 10) ──────────────────────
                # Runs synchronously; the fabric model is pure arithmetic over
                # a seeded PRNG and returns in <1 ms for the 608-link topology.
                # Non-blocking by design (Engine §22.7 — no I/O in this path).
                if ctx.fabric_engine is not None:
                    if _profiling: _t0 = _time_module.perf_counter()
                    ctx.fabric_engine.update_from_tick(tick_result)
                    _fab_result = ctx.fabric_engine.step(
                        sim_time_s=tick_result.sim_time_seconds,
                        dt_s=TICK_INTERVAL_SIM_SECONDS,
                        asset_class="turbine",
                    )
                    _fabric_modal = ctx.fabric_engine.modal_view() if _fab_result else None
                    tick_result = _dc_replace(tick_result, fabric_modal=_fabric_modal)
                    if _profiling: _sec.setdefault("B2_fabric_tick", []).append(_time_module.perf_counter() - _t0)

                # ── C: sink + broadcast ───────────────────────────────────
                if _profiling: _t0 = _time_module.perf_counter()
                await ctx.sink.append(tick_result)                 # I/O -- yields to sibling runs
                if _profiling: _sec.setdefault("C_sink_append", []).append(_time_module.perf_counter() - _t0)

                if _profiling: _t0 = _time_module.perf_counter()
                await self._ws_hub.broadcast(ctx.run_id, tick_result)  # I/O -- yields
                if _profiling: _sec.setdefault("C_ws_broadcast", []).append(_time_module.perf_counter() - _t0)

                # ── E: advisory agents (W1a) ──────────────────────────────
                # Keep tick_history bounded; agents call run_all() on the
                # recent window.  TC-48 guarantee: agents write only to the
                # gate (proposals), never to sim_state, so dispatch is
                # bit-identical whether agents are on or off.
                #
                # AC1(b): run_all() may make synchronous LLM HTTP calls via
                # requests / urllib.  Off-loading to asyncio.to_thread() keeps
                # the event loop free so sibling runs continue to tick, WS
                # frames are sent, and HTTP requests are served during the call.
                # Pass list(tick_history) so the worker thread cannot see
                # mutations made by this loop after the await returns.
                if ctx.registry is not None:
                    ctx.tick_history.append(tick_result)
                    if len(ctx.tick_history) > _TICK_HISTORY_MAXLEN:
                        ctx.tick_history.pop(0)
                    if _profiling: _t0 = _time_module.perf_counter()
                    ctx.registry.tick(tick_result.sim_time_seconds)
                    if _profiling: _sec.setdefault("E_registry_tick", []).append(_time_module.perf_counter() - _t0)
                    _job_id = ctx.events[0].job_id if ctx.events else ""
                    # AD2: use the bounded _ADVISORY_EXECUTOR (max_workers=4) rather
                    # than the default pool.  asyncio.to_thread() has no executor
                    # parameter so we use loop.run_in_executor() + functools.partial
                    # to forward keyword arguments.
                    if _profiling: _t0 = _time_module.perf_counter()
                    await asyncio.get_running_loop().run_in_executor(
                        _ADVISORY_EXECUTOR,
                        functools.partial(
                            ctx.registry.run_all,
                            list(ctx.tick_history),
                            wall_time=_time_module.time(),
                            sim_time=tick_result.sim_time_seconds,
                            site_id=ctx.sim_state.site.site_id,
                            job_id=_job_id,
                        ),
                    )
                    if _profiling: _sec.setdefault("E_registry_run_all", []).append(_time_module.perf_counter() - _t0)

                # ── D: network telemetry + corroboration (W1b) ───────────
                if ctx.telemetry_ingestor is not None:
                    if _profiling: _t0 = _time_module.perf_counter()
                    _ingest_synthetic_telemetry(ctx, tick_result)
                    if _profiling: _sec.setdefault("D_telemetry_ingest", []).append(_time_module.perf_counter() - _t0)
                if ctx.corroborator is not None:
                    # checkpoint_states: job_id → state string from TickResult.
                    # "running" = scheduler confirmed the job started (TC-51).
                    if _profiling: _t0 = _time_module.perf_counter()
                    for _jid, _st in tick_result.checkpoint_states.items():
                        if _st == "running":
                            ctx.corroborator.apply_checkpoint_start(
                                _jid, tick_result.sim_time_seconds
                            )
                    if _profiling: _sec.setdefault("D_corroborator", []).append(_time_module.perf_counter() - _t0)

                # ── W1c: thermal state — already updated before sink/broadcast above.

                # ── F: AD1 procurement evaluation (TC-47, TC-52) ─────────
                # Observe-only: does NOT write to sim_state; dispatch trace
                # hash is unaffected.
                if ctx.procurement_layer is not None:
                    if _profiling: _t0 = _time_module.perf_counter()
                    _gap = max(
                        0.0,
                        tick_result.net_demand_mw
                        - tick_result.turbine_output_mw
                        - tick_result.bess_output_mw,
                    )
                    ctx.procurement_layer.evaluate_tick(
                        reserve_gap_mw=_gap,
                        served_load_mw=tick_result.net_demand_mw,
                        sim_time=tick_result.sim_time_seconds,
                    )
                    if _profiling: _sec.setdefault("F_procurement", []).append(_time_module.perf_counter() - _t0)

                # ── F: AD1 maintenance evaluation (TC-58, TC-59, TC-60) ──
                # Observe-only: accumulates observation ticks, validates a
                # synthetic maintenance window, proposes rating changes.
                if ctx.maintenance_layer is not None:
                    if _profiling: _t0 = _time_module.perf_counter()
                    ctx.maintenance_layer.evaluate_tick(
                        sim_time=tick_result.sim_time_seconds,
                        net_demand_mw=tick_result.net_demand_mw,
                        available_capacity_mw=(
                            tick_result.turbine_output_mw
                            + tick_result.bess_output_mw
                        ),
                    )
                    if _profiling: _sec.setdefault("F_maintenance", []).append(_time_module.perf_counter() - _t0)

                # ── F: AD1 ramp relaxation evaluation (TC-75, TC-76) ─────
                # Observe-only: evaluate() returns a SiteRampPolicy but the
                # policy is advisory only — ramp caps are not applied to
                # TurbineModule, so the dispatch trace hash is unaffected.
                #
                # PROTO-22 (CHOSEN, no measured basis): available_capacity_mw
                # is set to turbine_rated_mw only, omitting BESS bridging and
                # renewable contribution.  This overstates headroom and works
                # against TC-75's conservative upper-bound intent.  A production
                # deployment must include all dispatchable sources.  See the
                # RampRelaxationEngine.evaluate() docstring for full rationale.
                if ctx.ramp_relaxation_engine is not None:
                    if _profiling: _t0 = _time_module.perf_counter()
                    from core.ramp_relaxation import ReservePosition  # lazy
                    ctx.ramp_relaxation_engine.evaluate(
                        ReservePosition(
                            # PROTO-22: turbine_rated_mw proxy — see note above.
                            available_capacity_mw=(
                                ctx.turbine_rated_mw
                                or (
                                    tick_result.turbine_output_mw
                                    + tick_result.bess_output_mw
                                )
                            ),
                            current_demand_mw=tick_result.net_demand_mw,
                            # +10% pessimistic upper-bound forecast.
                            forecast_upper_bound_mw=(
                                tick_result.net_demand_mw * 1.10
                            ),
                        ),
                        gridSignal_connected=True,
                    )
                    if _profiling: _sec.setdefault("F_ramp_relax", []).append(_time_module.perf_counter() - _t0)

                # ── G: sleep / yield ──────────────────────────────────────
                sleep_s = ctx.wall_clock_sleep_seconds()
                if _profiling: _t0 = _time_module.perf_counter()
                await asyncio.sleep(sleep_s if sleep_s > 0 else 0)  # always yield
                if _profiling: _sec.setdefault("G_sleep", []).append(_time_module.perf_counter() - _t0)

        except asyncio.CancelledError:
            _cancelled_externally = True
            logger.info("run %s cancelled mid-flight", ctx.run_id)
            raise
        finally:
            # Cancelled runs (external task.cancel() or ctx.cancelled=True) skip
            # verdict evaluation.  The sink may hold millions of rows from an
            # end_sim_time=1e15 test run; draining them would hang shutdown.
            _skip_verdict = _cancelled_externally or ctx.cancelled

            if not _skip_verdict:
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
                    turbine_rated_mw=ctx.turbine_rated_mw,
                )

            # AC3: emit section profile if flag was set for this run.
            if _profiling and _sec:
                _report_drive_profile(
                    ctx.run_id,
                    _sec,
                    _time_module.perf_counter() - _drive_t0,
                )

            # Always: preserve registry so /proposals works after run ends,
            # and remove the run from the active maps.
            if ctx.registry is not None:
                self._registries[ctx.run_id] = ctx.registry

            self._contexts.pop(ctx.run_id, None)
            self._tasks.pop(ctx.run_id, None)
