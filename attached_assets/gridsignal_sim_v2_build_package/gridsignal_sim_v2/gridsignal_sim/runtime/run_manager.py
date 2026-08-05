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
import csv as _csv
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

from core.asset_modules import TurbineState as _TurbineState   # runtime → core OK
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

    async def notify_run_complete(self, run_id: str) -> None:
        """Send a run_complete sentinel to every subscriber then close their sockets.

        Called by _drive() when the run exits normally (sim_time >= end_sim_time).
        Without this, the WS handler (ws.py receive_text loop) keeps the connection
        open indefinitely and the client freezes on the last tick.

        Cancelled runs are NOT notified — the frontend's Stop button already
        calls handleRunStopped directly, which unmounts useTickStream cleanly.
        """
        subs = list(self._subscribers.pop(run_id, ()))
        if not subs:
            return
        payload = {"type": "run_complete", "run_id": run_id}

        async def _send_and_close(ws: WebSocketLike) -> None:
            try:
                await asyncio.wait_for(ws.send_json(payload), timeout=_SEND_TIMEOUT_S)
            except Exception:  # noqa: BLE001
                pass
            try:
                await asyncio.wait_for(ws.close(), timeout=_SEND_TIMEOUT_S)
            except Exception:  # noqa: BLE001
                pass

        await asyncio.gather(*(_send_and_close(ws) for ws in subs))

    async def broadcast(self, run_id: str, tick_result: TickResult) -> None:
        subs = list(self._subscribers.get(run_id, ()))
        if not subs:
            return
        payload = _tick_result_to_dict(tick_result)
        # Phase 10 §12.10 — stamp wall-clock emit time so the frontend can
        # return it to POST /api/session/observe-tick for a server-side round-trip
        # measurement.  Stamped once here (not in _tick_result_to_dict) so the
        # timestamp is as close as possible to the actual send.  All subscribers
        # share the same payload dict — the stamp must be set before the gather.
        # Serialised as a *string* to avoid JavaScript safe-integer loss on
        # long-running hosts (monotonic_ns > 2^53 after ~104 days of uptime).
        import time as _t
        payload["t_emit_ns"] = str(_t.monotonic_ns())

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
        # turbine_ramp_credit_mw / peak_shortfall_mw: staging breakdown for
        #   AssetReservePanel — visible while a Kube STARTING ramp is in-flight
        #   (dt_lead_next_s > 0).  Both 0.0 between ramps.
        "turbine_ramp_credit_mw": round(tick.turbine_ramp_credit_mw, 3),
        "peak_shortfall_mw":      round(tick.peak_shortfall_mw, 3),
        # dt_lead_next_s: HeroPanel countdown — seconds to next GPU full-TDP.
        #   0.0 when no job is currently ramping.
        "dt_lead_next_s": round(tick.dt_lead_next_s, 2),
        # bridging_basis: which demand figure is binding for bess_bridging_seconds.
        #   "predicted_peak" — staged prediction's peak shortfall is binding.
        #   "current_demand" — current net_demand_mw is binding.
        #   "no_load"        — net demand is zero; no bridging required.
        "bridging_basis": tick.bridging_basis,
        # Step 10 — §8.1 pre-staging two-phase fields.
        # pre_staging_shift_mw: MW of gap reduced (discharge phase).
        # pre_staging_precool_mw: MW of extra load drawn to charge thermal store.
        "pre_staging_shift_mw": round(tick.pre_staging_shift_mw, 4),
        "pre_staging_precool_mw": round(tick.pre_staging_precool_mw, 4),
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
        # AE2 + Phase 2: per-unit turbine specs + dynamic Phase 2 state.
        # Static fields (asset_id, rated_mw, r_asset_mw_per_s, breaker_closed,
        # hot_standby, gt_mode, r_asset_rated_mw_per_s) come from turbine_unit_specs.
        # Dynamic Phase 2 fields (state, time_to_online_s, thermal_state,
        # start_phase, out_of_service_reason) are overlaid from state.turbines
        # each tick so the fleet modal shows live unit states without a separate call.
        "turbine_units": list(tick.turbine_units),
        # Phase 2: units_synchronised_count — derive from is_synchronised property
        # (uses TurbineState enum, not the legacy breaker_closed flag).
        # Backward compat: for runs where turbine_units still use breaker_closed,
        # fall back to the breaker_closed key.
        "units_synchronised_count": sum(
            1 for u in tick.turbine_units
            if u.get("state") in ("synchronised", "ramping", "at_target")
            or (u.get("state") is None and u.get("breaker_closed", True))
        ),
        # synchronised_output_mw: fleet output attributed to on-bus units.
        # Guard uses the same logic as units_synchronised_count for consistency:
        #   Phase 2 — live state in (synchronised, ramping, at_target) → on bus.
        #   Phase 0 fallback — breaker_closed (static spec, default True).
        # turbine_output_mw already equals the on-bus total because the loading
        # layer only dispatches SYNCHRONISED-state units; off-bus units produce 0.
        "synchronised_output_mw": round(
            tick.turbine_output_mw
            if any(
                u.get("state") in ("synchronised", "ramping", "at_target")
                or (u.get("state") is None and u.get("breaker_closed", True))
                for u in tick.turbine_units
            )
            else 0.0,
            4,
        ),
        # Kubernetes demand agent metrics — null when kube_config is not active.
        # non-null only on runs with kube_config set in the ScenarioSpec.
        "kube_metrics": (
            {
                "utilization":        round(tick.kube_metrics.utilization, 4),
                "node_count":         tick.kube_metrics.node_count,
                "power_cap_active":   tick.kube_metrics.power_cap_active,
                "headroom_mw":        round(tick.kube_metrics.headroom_mw, 3),
                "active_jobs":        tick.kube_metrics.active_jobs,
                "admitted_nodes":     tick.kube_metrics.admitted_nodes,
                "arrivals_this_tick": tick.kube_metrics.arrivals_this_tick,
                "requeued_this_tick": tick.kube_metrics.requeued_this_tick,
            }
            if tick.kube_metrics is not None
            else None
        ),
        # Solar weather metadata — stamped from RunContext at each tick (constant
        # per run).  Empty strings when solar is absent or run started via direct path.
        "solar_weather":    tick.solar_weather,
        "solar_conditions": tick.solar_conditions,
        # PROTO-32-AMB: ambient temperature metadata — constant per run.
        # 0.0 / 1.0 when ambient_steps were absent (no solar forecast).
        "ambient_avg_c":       round(tick.ambient_avg_c, 2),
        "ambient_alpha_scale": round(tick.ambient_alpha_scale, 4),
        # W2a: advisory telemetry — None when no registry is active (LP-1 / tests).
        # Keys: backend, agents_armed, proposals_total, proposals_pending,
        #        last_proposal_sim_time, per_agent (dict[str, float]).
        "advisory_telemetry": tick.advisory_telemetry,
        # Phase 10: fabric model modal-view — six plant-plane fields + link utilisation.
        # null when FabricEngine is not wired (headless tests, direct job-id path).
        "fabric": tick.fabric_modal,
        # §7.4 solar bank telemetry — SLD tile sub-field.
        # p_expected_mw: what the plant should produce at current measured POA.
        # banks_reporting: banks with live telemetry (20 = all, old model default).
        "p_expected_mw":   round(tick.p_expected_mw, 4) if tick.p_expected_mw is not None else None,
        "banks_reporting": tick.banks_reporting,  # None = not tracked on this run path (SolarSim has the honest figure)
        # SD-1: site identity — allows the WS header to render from the
        # authoritative server-side tick rather than client-held state.
        "site_lat":          tick.site_lat,
        "site_lon":          tick.site_lon,
        "site_utc_offset_h": tick.site_utc_offset_h,
        "site_name":         tick.site_name,
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
        # ── Phase 11.1: Forecast path (single source of truth) ───────────────
        # forecast_mw: queue-derived compute forecast (Section 4 formula).
        # Used by the Forecast Quality panel as the displayed predicted peak;
        # the header PREDICTED PEAK should also read this field so that the
        # two displays are bit-identical (F4 criterion).
        "forecast_mw": round(tick.forecast_mw, 4),
        # ── Phase 11.3: Dispatch truthfulness ────────────────────────────────
        # bess_setpoint_mw: commanded BESS output before SOC/power clipping.
        # gt_setpoint_mw:   total dispatch requirement handed to turbine fleet.
        # balance_residual_mw REMOVED (Branch B): D4 asserted inline in evaluate_tick();
        #   value not broadcast.  Read the three decomposition channels below instead.
        # frequency_hz: 50 Hz nominal ± swing-equation deviation (islanded only).
        "bess_setpoint_mw":    round(tick.bess_setpoint_mw, 4),
        "gt_setpoint_mw":      round(tick.gt_setpoint_mw, 4),
        "frequency_hz":        round(tick.frequency_hz, 4),
        # ── Phase 13.2: Balance decomposition ────────────────────────────────
        # Three independent channels.  D4 invariant asserted in evaluate_tick().
        # grid_exchange_mw:          PCC flow — exactly 0 in islanded mode (D1).
        # frequency_forcing_mw:      dispatch-plan inertial pressure — 0 grid-connected (D2).
        # asset_delivery_error_mw:   physical shortfall (asset setpoint tracking); ~0 steady-state (D3).
        # channel_source for all three: derived (see models.py TickResult docstring).
        "grid_exchange_mw":          round(tick.grid_exchange_mw, 5),
        "frequency_forcing_mw":      round(tick.frequency_forcing_mw, 5),
        "asset_delivery_error_mw":   round(tick.asset_delivery_error_mw, 5),
        # ── Phase 13.4: setpoint/actual split ────────────────────────────────
        # model_error_mw: load-model bias observable (B1 — 0.0 in production).
        # binding_constraint: "bess_power_saturated" when setpoint > fleet rating (B3).
        "model_error_mw":            round(tick.model_error_mw, 5),
        "binding_constraint":        tick.binding_constraint,
        # ── Phase 11.6: Cooling thermal lag (Section 8 thermal model) ────────
        # compute_inlet_temp_c: inlet air temperature derived from lagged
        # cooling output; inherits dt_thermal lag (≥ 0.99 lag-1 autocorr C3).
        "compute_inlet_temp_c": round(tick.compute_inlet_temp_c, 3),
        # ── Phase 1b: loading-layer outputs ──────────────────────────────────
        # sub_msl_surplus_mw: > 0 when fleet demand < Σ msl_i; 0 in normal operation.
        #   In islanded mode surplus enters frequency_forcing_mw (overfrequency).
        # ramp_capability_mw: fleet ramp over the runtime lead horizon (dt_lead_next_s).
        #   Replaces the Phase 0.5 display-level cap in turbineFleet.ts.
        # d4_balance_defect_mw: D4 power balance defect; 0.0 in normal operation.
        #   Non-zero signals an accounting error; the run continues.
        "sub_msl_surplus_mw":    round(tick.sub_msl_surplus_mw, 4),
        "ramp_capability_mw":    round(tick.ramp_capability_mw, 4),
        "d4_balance_defect_mw":  round(tick.d4_balance_defect_mw, 9),
        # ── Task #174: Stochastic step timing (kube path only) ───────────────
        # step_phase: fractional position within the current ML training step.
        # step_kind: "training" or "checkpoint".
        "step_phase": round(tick.step_phase, 4),
        "step_kind":  tick.step_kind,
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
    # PROTO-32-AMB: ambient temperature metadata — set by build_run_context_from_spec
    # when ambient_steps are present.  0.0 / 1.0 on direct path or runs without solar.
    ambient_avg_c:      float = 0.0   # average dry-bulb °C across the run window
    ambient_alpha_scale: float = 1.0  # factor applied to site.alpha_max (>1 = hotter)

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

    # SD-1: site identity — stamped onto every TickResult so the WS header
    # physically cannot drift from the physics after a server restart or
    # sleep/wake cycle.  Defaults match SiteLocation defaults (San Diego).
    # Set from spec_data["site_latitude/utc_offset_h/name"] by scenario_factory.
    # Defaults are 0.0 / "" so Guard A's float-literal scan never sees San Diego
    # coordinates here; scenario_factory always stamps the real values before t=0.
    site_lat:          float = field(default_factory=float)   # 0.0 until scenario_factory writes
    site_lon:          float = field(default_factory=float)   # 0.0 until scenario_factory writes
    site_utc_offset_h: float = field(default_factory=float)   # 0.0 until scenario_factory writes
    site_name:         str   = ""

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

    # Three-tier Mistral solar aggregation: IrradianceProfile (from
    # core.asset_modules) for the run's irradiance_steps.  Set by
    # scenario_factory; None on direct job-id path and headless tests.
    # _drive() calls .fraction_at(sim_time) each tick and passes the result
    # to solar_sim.set_mistral_fraction() before live_aggregate_mw().
    irradiance_profile: Optional[Any] = None       # IrradianceProfile

    # GT-2: telemetry corruption wiring.
    # telemetry_corruption is set by api/routes/runs.py after build_run_context_from_spec()
    # when the spec includes a telemetry_corruption_config block.  None = clean run (default).
    # _corruption_rng: per-run Random instance for noise draws (seeded from schedule seed).
    # _bess_soc_history: rolling list of clean SoC MWh values used to satisfy staleness
    # lookbacks (entry.staleness > 0 needs the reading from N ticks ago).
    telemetry_corruption: Optional[Any] = None          # TelemetryCorruptionSchedule
    _corruption_rng: Optional[Any] = field(default=None, repr=False)
    _bess_soc_history: list = field(default_factory=list)  # clean SoC MWh, chronological

    # Operator unit command queue — list of dicts {"unit_id": str, "action": str}.
    # Commands are enqueued by POST /runs/{run_id}/units/{unit_id}/command and
    # drained by _drive() before each tick.  A plain list is safe here because
    # _drive() and the endpoint handler both run in the same asyncio event loop
    # (no true concurrency at the Python level within one loop iteration; control
    # transfers only at await points, and the drain loop contains none).
    _operator_commands: list = field(default_factory=list)

    def is_complete(self) -> bool:
        return self.cancelled or self.sim_time >= self.end_sim_time

    def enqueue_unit_command(self, unit_id: str, action: str) -> None:
        """Queue an operator unit command for the next tick.

        Called by POST /runs/{run_id}/units/{unit_id}/command.
        The command is processed by _drive() before evaluate_tick() runs,
        so the physics engine sees the new state immediately:
          trip  → MW drop visible in the next WebSocket broadcast.
          start → STARTING state visible on next tick; SYNCHRONISED after ramp.
        """
        self._operator_commands.append({"unit_id": unit_id, "action": action})

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


# ---------------------------------------------------------------------------
# GT-2: telemetry corruption — recompute contingency_coverage with noisy SoC
# ---------------------------------------------------------------------------

def _apply_soc_corruption(ctx: "RunContext", tick_result: "TickResult") -> "TickResult":
    """Apply the pre-generated corruption schedule to BESS SoC and recompute
    contingency_coverage.  Returns a new TickResult (via _dc_replace) with the
    corrupted ContingencyCoverage.

    Design:
    - The clean physics SoC drives dispatch (unchanged).  Corruption is applied at
      the reporting layer only, simulating a noisy meter or stale sensor reading.
    - bess_soc_fraction on TickResult is NOT altered (that's the physics value used
      by agents and the verdict engine).  Only contingency_coverage.bess_usable_energy_mwh
      and the downstream energy-test / state fields change.
    - Dropout (entry.dropout=True) → suppress the corrupted re-computation entirely;
      the tick carries the last clean contingency_coverage without update.
    """
    # Lazy imports — core/ and runtime/ are allowed; avoid import cycles with api/
    from runtime.telemetry_corruption import apply_corruption   # runtime → runtime OK
    from core.contingency import (                               # runtime → core OK
        BessSnapshot, PlantState, TurbineSnapshot, evaluate_contingency,
    )
    from core.asset_modules import TurbineState                 # runtime → core OK

    # tick_index is 1-based; schedule is 0-based.
    entry = ctx.telemetry_corruption.for_tick(tick_result.tick_index - 1)  # type: ignore[union-attr]

    # Fast path — no corruption scheduled for this tick.
    if entry.noise_sigma == 0.0 and not entry.dropout and entry.staleness == 0:
        _update_soc_history(ctx, tick_result)
        return tick_result

    # Initialise the per-run noise RNG on first use.
    if ctx._corruption_rng is None:
        import random as _random
        ctx._corruption_rng = _random.Random(
            ctx.telemetry_corruption.seed  # type: ignore[union-attr]
        )

    # Current clean BESS SoC (MWh) — sum across all units (single-unit common case).
    clean_soc_mwh: float = sum(b.soc_mwh for b in ctx.sim_state.bess_units)

    # Stale value: reading from N ticks ago, or None if history is too short.
    stale_val: Optional[float] = (
        ctx._bess_soc_history[-entry.staleness]
        if entry.staleness > 0 and len(ctx._bess_soc_history) >= entry.staleness
        else None
    )

    # Record clean value BEFORE applying (so the caller doesn't see today's value
    # when looking back 1 tick — they should see last tick's clean reading).
    _update_soc_history(ctx, tick_result)

    corrupted_soc_mwh, suppressed = apply_corruption(
        clean_soc_mwh,
        entry,
        stale_value=stale_val,
        rng=ctx._corruption_rng,
    )

    if suppressed or corrupted_soc_mwh is None:
        # Dropout: leave contingency_coverage untouched.
        return tick_result

    # Clamp to [0, total_usable_mwh]: a noisy meter can't report < 0 or > nameplate.
    total_usable: float = sum(b.config.usable_mwh for b in ctx.sim_state.bess_units)
    corrupted_soc_mwh = max(0.0, min(total_usable, corrupted_soc_mwh))

    if abs(corrupted_soc_mwh - clean_soc_mwh) < 1e-9:
        return tick_result  # No effective change after clamping.

    # Scale each BESS unit's SoC proportionally so sum == corrupted_soc_mwh.
    # Single-unit case: trivial.  Multi-unit: proportional split preserves relative charge.
    scale: float = corrupted_soc_mwh / clean_soc_mwh if clean_soc_mwh > 0.0 else 0.0
    corrupted_bess: tuple = tuple(
        BessSnapshot(
            asset_id=b.config.asset_id,
            rated_mw=b.config.rated_mw,
            soc_mwh=(b.soc_mwh * scale if clean_soc_mwh > 0.0 else 0.0),
            usable_mwh=b.config.usable_mwh,
            p_anchor_reserve_mw=b.config.p_anchor_reserve_mw,
            grid_forming=b.config.grid_forming,
        )
        for b in ctx.sim_state.bess_units
    )

    # Rebuild turbine snapshots from current sim_state (valid between ticks).
    turbine_snaps: tuple = tuple(
        TurbineSnapshot(
            asset_id=t.config.asset_id,
            current_output_mw=t.output_mw(),
            rated_mw=t.config.rated_mw,
            r_asset_mw_per_s=t.config.r_asset_mw_per_s,
            is_synchronized=(t.state != TurbineState.OFFLINE),
        )
        for t in ctx.sim_state.turbines
    )

    corrupted_plant = PlantState(
        turbine_snapshots=turbine_snaps,
        bess_snapshots=corrupted_bess,
        island_mode=ctx.sim_state.site.island_mode,
        curtailable_capacity_mw=ctx.sim_state.curtailment_ladder.total_capacity_mw(),
        renewable_mw=tick_result.p_renewable_mw,
    )

    corrupted_coverage = evaluate_contingency(corrupted_plant)
    return _dc_replace(tick_result, contingency_coverage=corrupted_coverage)


def _update_soc_history(ctx: "RunContext", tick_result: "TickResult") -> None:
    """Append the current clean BESS SoC MWh to the rolling staleness history.
    Bounded to 60 entries (5 minutes at 5 s/tick) — more than any realistic
    max_stale setting.
    """
    clean_soc_mwh: float = sum(b.soc_mwh for b in ctx.sim_state.bess_units)
    ctx._bess_soc_history.append(clean_soc_mwh)
    if len(ctx._bess_soc_history) > 60:
        ctx._bess_soc_history.pop(0)


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
        # Task #122: wired by app.py lifespan so _drive() can push the run's
        # p_renewable_mw into SolarSim each tick.
        self.solar_sim: Any = None

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

    # ------------------------------------------------------------------
    # Operator unit commands — called by POST /runs/{id}/units/{id}/command
    # ------------------------------------------------------------------

    # Result codes returned by validate_and_enqueue_unit_command so the
    # api/ layer never needs to import from core/.
    UNIT_CMD_OK          = "ok"
    UNIT_CMD_RUN_404     = "run_not_found"
    UNIT_CMD_UNIT_404    = "unit_not_found"
    UNIT_CMD_BAD_STATE   = "bad_state"

    def validate_and_enqueue_unit_command(
        self,
        run_id: str,
        unit_id: str,
        action: str,
    ) -> tuple[str, str]:
        """Validate and queue an operator unit command.

        Returns a (result_code, detail) pair.  result_code is one of the
        UNIT_CMD_* class constants; detail is a human-readable error string
        (empty on success).

        All core/ imports are local so api/ can call this method without
        violating the plane-separation rule.
        """
        ctx = self._contexts.get(run_id)
        if ctx is None:
            return self.UNIT_CMD_RUN_404, f"Run {run_id!r} not found or not active."

        # Locate the turbine for state validation.
        turbine = None
        for _t in ctx.sim_state.turbines:
            if _t.config.asset_id == unit_id:
                turbine = _t
                break

        if turbine is None:
            return self.UNIT_CMD_UNIT_404, f"Unit {unit_id!r} not found in run {run_id!r}."

        # Validate action against current state.
        from core.asset_modules import TurbineState as _TS   # runtime → core OK
        _ON_BUS    = {_TS.SYNCHRONISED, _TS.RAMPING, _TS.AT_TARGET}
        _STARTABLE = {_TS.OFFLINE}

        if action == "trip" and turbine.state not in _ON_BUS:
            return self.UNIT_CMD_BAD_STATE, (
                f"Unit {unit_id!r} is in state {turbine.state.value!r} — "
                "trip is only valid for on-bus units "
                "(synchronised / ramping / at_target)."
            )
        if action == "start" and turbine.state not in _STARTABLE:
            return self.UNIT_CMD_BAD_STATE, (
                f"Unit {unit_id!r} is in state {turbine.state.value!r} — "
                "start is only valid from OFFLINE."
            )

        ctx.enqueue_unit_command(unit_id, action)
        return self.UNIT_CMD_OK, ""

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

        # Kube debug CSV — written automatically whenever kube_metrics is present.
        # One row per tick: sim_time, arrivals, requeued, admitted_nodes, headroom_mw,
        # power_cap_active, p_compute_mw.  Flushed every tick so a live tail works.
        # Path: /tmp/kube_debug_<run_id>.csv — readable without authentication.
        _kube_csv_file = None
        _kube_csv_writer = None

        # AC3: per-section timing. Activate with GS_PROFILE_DRIVE=1.
        # Reports p50 + p95 per section at run completion (via logger.info).
        # Off by default — the boolean check costs ~10 ns per guard when False.
        _profiling: bool = bool(_os.environ.get("GS_PROFILE_DRIVE"))
        _sec: dict[str, list[float]] = {}
        _drive_t0: float = _time_module.perf_counter()

        try:
            while not ctx.is_complete():
                # ── A-1: operator unit commands ───────────────────────────
                # Drain commands queued by POST /runs/{id}/units/{id}/command.
                # Applied BEFORE evaluate_tick() so the physics engine sees
                # the state change in this tick:
                #   trip  → fleet output drops in the same-tick broadcast.
                #   start → unit enters STARTING; ramps to SYNCHRONISED naturally.
                # No await points in this loop — asyncio cannot interleave
                # another coroutine mid-drain, so no mutex is needed.
                while ctx._operator_commands:
                    _cmd        = ctx._operator_commands.pop(0)
                    _cmd_uid    = _cmd.get("unit_id", "")
                    _cmd_action = _cmd.get("action", "")
                    for _turb in ctx.sim_state.turbines:
                        if _turb.config.asset_id == _cmd_uid:
                            if _cmd_action == "trip":
                                _turb.state = _TurbineState.OFFLINE
                                _turb._current_output_mw = 0.0
                                _turb._target_mw = 0.0
                                logger.info(
                                    "operator command: TRIP turbine %r "
                                    "at sim_time=%.1f (run=%s)",
                                    _cmd_uid, ctx.sim_time, ctx.run_id,
                                )
                            elif _cmd_action == "start":
                                _turb.command_start(ctx.sim_time)
                                logger.info(
                                    "operator command: START turbine %r "
                                    "at sim_time=%.1f (run=%s)",
                                    _cmd_uid, ctx.sim_time, ctx.run_id,
                                )
                            break

                # ── A0: three-tier solar pre-step injection ───────────────
                # Inject the Mistral bank-aggregated MW into every SolarModule
                # BEFORE evaluate_tick() runs so net_demand_mw and dispatch
                # decisions use the per-bank enabled value — not rated_mw * fraction.
                # SolarSim.set_mistral_fraction() is called here (not in section C)
                # so the fraction is stable for the entire tick.
                if self.solar_sim is not None and ctx.irradiance_profile is not None:
                    _pre_frac = ctx.irradiance_profile.fraction_at(ctx.sim_time)
                    self.solar_sim.set_mistral_fraction(_pre_frac)
                    _pre_solar_mw = self.solar_sim.live_aggregate_mw()
                    for _sm in ctx.sim_state.solar_arrays:
                        _sm.override_output_mw(_pre_solar_mw)

                # ── A: evaluate_tick ──────────────────────────────────────
                if _profiling: _t0 = _time_module.perf_counter()
                tick_result = ctx.step()                           # sync, in-budget (Design Spec 4.3)
                if _profiling: _sec.setdefault("A_evaluate_tick", []).append(_time_module.perf_counter() - _t0)

                # ── A1: kube debug CSV ────────────────────────────────────
                # Written every tick when kube_metrics is present.  One line:
                #   sim_time, arrivals, requeued, admitted_nodes, headroom_mw,
                #   power_cap_active, p_compute_mw
                # Path: /tmp/kube_debug_<run_id>.csv — flushed immediately so
                # `tail -f` works live.  Five consecutive lines reveal whether
                # nodes decay through completion events or reassignment from
                # scratch, which determines the correct oscillation fix.
                if tick_result.kube_metrics is not None:
                    if _kube_csv_writer is None:
                        _kube_csv_path = f"/tmp/kube_debug_{ctx.run_id}.csv"
                        _kube_csv_file = open(_kube_csv_path, "w", newline="")  # noqa: WPS515
                        _kube_csv_writer = _csv.writer(_kube_csv_file)
                        _kube_csv_writer.writerow([
                            "sim_time_s", "arrivals", "requeued",
                            "admitted_nodes", "headroom_mw",
                            "power_cap_active", "p_compute_mw",
                        ])
                        logger.info(
                            "run %s: kube debug CSV → %s",
                            ctx.run_id, _kube_csv_path,
                        )
                    _km = tick_result.kube_metrics
                    _kube_csv_writer.writerow([
                        round(tick_result.sim_time_seconds - 5.0, 1),
                        _km.arrivals_this_tick,
                        _km.requeued_this_tick,
                        _km.admitted_nodes,
                        round(_km.headroom_mw, 3),
                        1 if _km.power_cap_active else 0,
                        round(tick_result.p_compute_mw, 4),
                    ])
                    _kube_csv_file.flush()  # type: ignore[union-attr]

                # ── A2: telemetry corruption (GT-2) ───────────────────────
                # Recompute contingency_coverage with a noisy BESS SoC reading
                # when a TelemetryCorruptionSchedule is attached to the context.
                # The clean physics SoC used for dispatch is preserved; only the
                # contingency_coverage field is replaced on tick_result.
                # Runs only when telemetry_corruption is set (spec-path runs with
                # telemetry_corruption_config); all other runs (tests, load tests,
                # direct job-id path) are unaffected.
                if ctx.telemetry_corruption is not None and tick_result.contingency_coverage is not None:
                    if _profiling: _t0 = _time_module.perf_counter()
                    tick_result = _apply_soc_corruption(ctx, tick_result)
                    if _profiling: _sec.setdefault("A2_soc_corruption", []).append(_time_module.perf_counter() - _t0)
                elif ctx.telemetry_corruption is not None:
                    # contingency_coverage is None (no turbines) — still track history.
                    _update_soc_history(ctx, tick_result)

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
                    # AE2 + Phase 2: per-unit turbine specs overlaid with dynamic
                    # Phase 2 state fields (state, time_to_online_s, thermal_state,
                    # start_phase, out_of_service_reason).  Static spec fields come
                    # from ctx.turbine_unit_specs; dynamic fields are built from
                    # ctx.sim_state.turbines.  The two lists share the same ordering
                    # (both derived from the same ScenarioSpec turbine_units list).
                    turbine_units=tuple(
                        {
                            **static_spec,
                            # Phase 2 live state overlay — keys match TurbineState values.
                            "state": t.state.value,
                            "time_to_online_s": (
                                round(t._time_to_online_s, 1)
                                if t.state.value == "starting" else None
                            ),
                            "thermal_state": t._thermal_state.value if hasattr(t, "_thermal_state") else None,
                            "start_phase": t._start_phase if t.state.value == "starting" else None,
                            "out_of_service_reason": t._out_of_service_reason,
                        }
                        for static_spec, t in zip(ctx.turbine_unit_specs, ctx.sim_state.turbines)
                    ) if (
                        ctx.sim_state is not None
                        and len(ctx.sim_state.turbines) == len(ctx.turbine_unit_specs)
                    ) else ctx.turbine_unit_specs,
                    # Solar weather metadata — constant per run, stamped so the
                    # Solar PV modal can surface the Mistral forecast label without
                    # a separate endpoint.  Empty strings on direct job-id path.
                    solar_weather=ctx.solar_weather,
                    solar_conditions=ctx.solar_conditions,
                    # PROTO-32-AMB: ambient temperature — constant per run.
                    ambient_avg_c=ctx.ambient_avg_c,
                    ambient_alpha_scale=ctx.ambient_alpha_scale,
                    # SD-1: site identity — constant per run, stamped so the WS header
                    # renders from authoritative server-side data rather than
                    # client-held state that diverges silently after a server restart.
                    site_lat=ctx.site_lat,
                    site_lon=ctx.site_lon,
                    site_utc_offset_h=ctx.site_utc_offset_h,
                    site_name=ctx.site_name,
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
                # Safety backstop: re-stamp p_renewable_mw from the live
                # aggregate.  The fraction was already pushed in A0 (pre-step),
                # so live_aggregate_mw() returns the same value that was
                # injected into solar_arrays — no second fraction lookup needed.
                if self.solar_sim is not None:
                    tick_result = _dc_replace(
                        tick_result,
                        p_renewable_mw=self.solar_sim.live_aggregate_mw(),
                    )

                if _profiling: _t0 = _time_module.perf_counter()
                await ctx.sink.append(tick_result)                 # I/O -- yields to sibling runs
                if _profiling: _sec.setdefault("C_sink_append", []).append(_time_module.perf_counter() - _t0)

                if _profiling: _t0 = _time_module.perf_counter()
                await self._ws_hub.broadcast(ctx.run_id, tick_result)  # I/O -- yields
                if _profiling: _sec.setdefault("C_ws_broadcast", []).append(_time_module.perf_counter() - _t0)

                # ── C2: solar-sim run sync (Task #122) ────────────────────
                # Push the run's aggregate p_renewable_mw into the standalone
                # SolarSim so the bank-fleet panel and the SLD tile show the
                # same plant total.  Pure in-process call (<1 µs); no I/O.
                if self.solar_sim is not None:
                    self.solar_sim.update_from_run(tick_result.p_renewable_mw)

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
                # R8 fix (Phase 13.5): available_capacity_mw now reads from
                # contingency_coverage.dispatchable_mw — the single source of
                # truth for (online turbine rated) + (anchor-adj BESS bridging).
                # This resolves the prior PROTO-22 discrepancy where the header
                # showed 38 MW (dispatchable) while the ramp-relaxation tile
                # received 20 MW (turbine-only ctx.turbine_rated_mw).
                if ctx.ramp_relaxation_engine is not None:
                    if _profiling: _t0 = _time_module.perf_counter()
                    from core.ramp_relaxation import ReservePosition  # lazy
                    ctx.ramp_relaxation_engine.evaluate(
                        ReservePosition(
                            # R8: use dispatchable_mw (turbines + BESS) from the
                            # single contingency source; fall back to output sum
                            # only if contingency_coverage is absent (e.g. no
                            # online turbines).
                            available_capacity_mw=(
                                tick_result.contingency_coverage.dispatchable_mw
                                if tick_result.contingency_coverage is not None
                                else (
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
            # Close kube debug CSV if it was opened for this run.
            if _kube_csv_file is not None:
                try:
                    _kube_csv_file.close()
                    logger.info(
                        "run %s: kube debug CSV closed (/tmp/kube_debug_%s.csv)",
                        ctx.run_id, ctx.run_id,
                    )
                except Exception:  # noqa: BLE001
                    pass

            # Task #122: restore SolarSim to standalone physics output now that
            # the run is over, so the bank panel keeps showing live numbers
            # between runs rather than the last tick's run-loop value.
            if self.solar_sim is not None:
                self.solar_sim.clear_run_sync()

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
                    # Phase 10: if the run has a fabric stress scenario, merge its
                    # fabric-specific assertion results into the overall verdict.
                    if ctx.fabric_engine is not None:
                        try:
                            fabric_results = ctx.fabric_engine.evaluate_scenario_assertions()
                            if fabric_results:
                                # Merge: add fabric assertion results and recompute overall.
                                all_results = list(verdict_result.assertions) + fabric_results
                                statuses = {r.status for r in all_results}
                                if "FAIL" in statuses:
                                    new_overall = "FAIL"
                                elif "INCONCLUSIVE" in statuses or not all_results:
                                    new_overall = "INCONCLUSIVE"
                                else:
                                    new_overall = "PASS"
                                verdict_result = VerdictResult(
                                    overall=new_overall,
                                    tick_count=verdict_result.tick_count,
                                    dropped_ticks=verdict_result.dropped_ticks,
                                    gap_count=verdict_result.gap_count,
                                    assertions=all_results,
                                )
                        except Exception:
                            logger.exception(
                                "run %s: fabric assertion evaluation failed", ctx.run_id
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

            # Notify WS subscribers that the run finished naturally.
            # Done AFTER verdict/CompletedRun are stored so the client's
            # immediate GET /runs/{id}/result call finds the data ready.
            # Cancelled runs skip this — the Stop button already called
            # handleRunStopped on the frontend side.
            if not _skip_verdict:
                try:
                    await self._ws_hub.notify_run_complete(ctx.run_id)
                except Exception:  # noqa: BLE001
                    logger.warning("run %s: notify_run_complete failed", ctx.run_id)
