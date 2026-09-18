"""Run Addendum H Phase 2b-2 seven-day reference scenarios.

The work is deliberately split into checkpointable commands:

  probe    capture the baseline workload-signal and demand trace once
  mode     run one replay mode and write its complete tick artifact
  finalize compare both modes, add daily breakdowns, and write the report

This keeps the 120,960-tick runs resumable without changing the Phase 2b-1
commitment policy, acceptance gates, baseline, pre-load rule, fuel model,
curtailment ordering, or forecast rule.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

PACKAGE_ROOT = Path(__file__).parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from core.asset_modules import TurbineState
from runtime.phase2b_reference import expand_phase2b_reference_spec
from runtime.phase2b_reference import _cluster_offsets
from runtime.scenario_factory import build_run_context_from_spec
from scripts.run_phase2b_stage1 import (
    TICK_SECONDS,
    _assert_replay_equal,
    _load_compact_spec,
    _phase2b_acceptance_verdict,
    _run_context,
    _run_summary,
    _signal_dict,
    _write_tick_artifact,
)


DAY_SECONDS = 24.0 * 60.0 * 60.0
SEVEN_DAYS = 7
MAX_JSON_BYTES = 100 * 1024
REFERENCE_IDS = (
    "scenario-h1-k8s-ray-7d",
    "scenario-h2-slurm-7d",
)
REFERENCE_FILES = {
    "scenario-h1-k8s-ray-7d": "scenario-h1-k8s-ray-7d.json",
    "scenario-h2-slurm-7d": "scenario-h2-slurm-7d.json",
}
OUTPUT_ROOT = PACKAGE_ROOT.parents[3] / "docs" / "addendum-h-phase2b-results"
STAGE1_ROOT = OUTPUT_ROOT


def _stage2_prefix(scenario_id: str) -> str:
    return f"{scenario_id}-stage2"


def _probe_path(output_dir: Path, scenario_id: str) -> Path:
    return output_dir / f".{_stage2_prefix(scenario_id)}-probe.json.gz"


def _checkpoint_path(output_dir: Path, scenario_id: str) -> Path:
    return output_dir / f".{_stage2_prefix(scenario_id)}-checkpoint.json"


def _run_path(output_dir: Path, scenario_id: str, mode: str) -> Path:
    return output_dir / f"{scenario_id}-{mode}.json"


def _tick_path(output_dir: Path, scenario_id: str, mode: str) -> Path:
    return output_dir / f"{scenario_id}-{mode}_ticks.jsonl.gz"


def _load_stage2_compact_spec(scenario_id: str) -> dict[str, Any]:
    path = PACKAGE_ROOT / "config" / "scenarios" / REFERENCE_FILES[scenario_id]
    return json.loads(path.read_text())


def _distribution(values: list[float]) -> dict[str, float | int]:
    clean = [float(value) for value in values if value == value]
    if not clean:
        return {
            "count": 0,
            "min": 0.0,
            "mean": 0.0,
            "median": 0.0,
            "p90": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "max": 0.0,
        }
    ordered = sorted(clean)
    return {
        "count": len(clean),
        "min": round(ordered[0], 9),
        "mean": round(sum(clean) / len(clean), 9),
        "median": round(statistics.median(ordered), 9),
        "p90": round(ordered[min(len(ordered) - 1, max(0, int(0.90 * len(ordered)) - 1))], 9),
        "p95": round(ordered[min(len(ordered) - 1, max(0, int(0.95 * len(ordered)) - 1))], 9),
        "p99": round(ordered[min(len(ordered) - 1, max(0, int(0.99 * len(ordered)) - 1))], 9),
        "max": round(ordered[-1], 9),
    }


def _write_json_bounded(path: Path, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if len(encoded.encode("utf-8")) >= MAX_JSON_BYTES:
        raise AssertionError(
            f"{path.name} would be {len(encoded.encode('utf-8'))} bytes; "
            f"Stage 2b-2 JSON must remain under {MAX_JSON_BYTES} bytes"
        )
    path.write_text(encoded)


def _cap_summary_records(summary: dict[str, Any]) -> dict[str, Any]:
    capped = copy.deepcopy(summary)
    for key, limit in (
        ("commitment_log", 24),
        ("stop_floor_refusals", 24),
        ("starts", 40),
        ("stops", 40),
        ("preload_actions", 40),
        ("unserved_intervals", 40),
    ):
        records = capped.get(key)
        if not isinstance(records, list) or len(records) <= limit:
            continue
        head = max(1, limit // 2)
        tail = limit - head
        capped[key] = (
            records[:head]
            + [{"truncated": True, "omitted_record_count": len(records) - limit}]
            + records[-tail:]
        )
    return capped


def _write_probe(
    output_dir: Path,
    scenario_id: str,
    *,
    probe_ctx: Any,
    demand_replay: list[tuple[float, float]],
    background_power_reactive: bool,
    probe_wall: float,
) -> None:
    replay_events = [
        _signal_dict(signal)
        for signal in probe_ctx.sim_state.workload_signal_trace
    ]
    if not replay_events:
        raise AssertionError(
            f"{scenario_id}: background probe emitted no workload signals"
        )
    payload = {
        "scenario_id": scenario_id,
        "days": SEVEN_DAYS,
        "probe_wall_clock_seconds": round(probe_wall, 6),
        "background_trace_signal_count": len(replay_events),
        "background_power_reactive": background_power_reactive,
        "demand_replay": demand_replay,
        "replay_events": replay_events,
    }
    probe_path = _probe_path(output_dir, scenario_id)
    probe_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(probe_path, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"))
    _checkpoint_path(output_dir, scenario_id).write_text(
        json.dumps(
            {
                "scenario_id": scenario_id,
                "probe": probe_path.name,
                "probe_complete": True,
                "demand_replay_tick_count": len(demand_replay),
                "background_trace_signal_count": len(replay_events),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def run_probe(scenario_id: str, output_dir: Path) -> None:
    compact = _load_stage2_compact_spec(scenario_id)
    expanded = expand_phase2b_reference_spec(compact)
    if int(compact["phase2b_reference_days"]) != SEVEN_DAYS:
        raise AssertionError(f"{scenario_id}: expected a seven-day compact spec")
    probe_ctx = _stream_context(
        expanded,
        run_id=f"{scenario_id}-background-probe",
        mode="baseline",
        replay_events=None,
        demand_replay=None,
        capture_trace=True,
    )
    demand_replay: list[tuple[float, float]] = []
    background_power_reactive = False
    tick_count = int(round(float(probe_ctx.end_sim_time) / TICK_SECONDS))
    started = time.perf_counter()
    for _ in range(tick_count):
        tick = probe_ctx.step()
        demand_replay.append(
            (
                float(tick.p_compute_demand_mw),
                float(tick.p_cooling_demand_mw),
            )
        )
        background_power_reactive = background_power_reactive or (
            tick.kube_metrics is not None
            and (
                tick.kube_metrics.power_cap_active
                or tick.kube_metrics.requeued_this_tick > 0
            )
        )
    probe_wall = time.perf_counter() - started
    _write_probe(
        output_dir,
        scenario_id,
        probe_ctx=probe_ctx,
        demand_replay=demand_replay,
        background_power_reactive=background_power_reactive,
        probe_wall=probe_wall,
    )
    print(
        f"{scenario_id}: probe complete; ticks={len(demand_replay)}; "
        f"signals={len(probe_ctx.sim_state.workload_signal_trace)}"
    )


def _load_probe(output_dir: Path, scenario_id: str) -> dict[str, Any]:
    path = _probe_path(output_dir, scenario_id)
    if not path.is_file():
        raise FileNotFoundError(
            f"{scenario_id}: missing probe checkpoint {path}; run probe first"
        )
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    if len(payload.get("demand_replay", [])) != 604800 // 5:
        raise AssertionError(
            f"{scenario_id}: probe demand trace is not 120,960 ticks"
        )
    return payload


def _assert_all_aero_fuel_model(ctx: Any, scenario_id: str) -> None:
    errors = []
    for turbine in ctx.sim_state.turbines:
        if str(getattr(turbine.config, "gt_mode", "")).lower() != "aero":
            errors.append(f"{turbine.config.asset_id}: gt_mode is not aero")
        if not turbine.fuel_modelled:
            errors.append(f"{turbine.config.asset_id}: fuel model missing")
    if errors:
        raise AssertionError(f"{scenario_id}: turbine fuel contract failed: {errors}")


def _assert_run_fuel_nonzero(
    ctx: Any,
    *,
    synchronized_seen: bool,
    final_rows: dict[str, dict[str, Any]],
    scenario_id: str,
) -> None:
    _assert_all_aero_fuel_model(ctx, scenario_id)
    total_fuel = sum(
        float(row.get("total_fuel_mmbtu", 0.0) or 0.0)
        for row in final_rows.values()
    )
    if synchronized_seen and total_fuel <= 1e-12:
        raise AssertionError(
            f"{scenario_id}: synchronized turbines reported zero total fuel"
        )


def _stream_context(
    spec: dict[str, Any],
    *,
    run_id: str,
    mode: str,
    replay_events: list[dict[str, Any]] | None,
    demand_replay: list[tuple[float, float]] | None,
    capture_trace: bool,
) -> Any:
    run_spec = copy.deepcopy(spec)
    run_spec["turbine_commitment_mode"] = mode
    if replay_events is not None:
        run_spec.pop("kube_clusters", None)
        run_spec.pop("slurm_config", None)
        run_spec["workload_events"] = replay_events
    ctx = build_run_context_from_spec(run_id, run_spec, playback_speed=0.0)
    ctx.sim_state.demand_replay_trace = demand_replay
    ctx.sim_state.capture_workload_signal_trace = capture_trace
    return ctx


def _stream_daily_rows(
    daily: dict[int, dict[str, Any]],
    *,
    starts: list[dict[str, Any]],
    stops: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    components = (
        "load_fuel_mmbtu",
        "no_load_fuel_mmbtu",
        "hot_standby_fuel_mmbtu",
        "start_fuel_mmbtu",
    )
    previous = {component: 0.0 for component in components}
    rows = []
    for day in range(1, SEVEN_DAYS + 1):
        state = daily[day]
        fuel_by_component = {
            component: max(
                0.0,
                float(state["fuel_cumulative"][component]) - previous[component],
            )
            for component in components
        }
        previous = dict(state["fuel_cumulative"])
        start_count, starts_by_unit_source = _event_counts(starts, day=day)
        stop_count, stops_by_unit_source = _event_counts(stops, day=day)
        rows.append(
            {
                "day": day,
                "kind": "weekday" if day <= 5 else "weekend",
                "fuel_by_component_mmbtu": {
                    component: round(value, 9)
                    for component, value in fuel_by_component.items()
                },
                "fuel_mmbtu": round(sum(fuel_by_component.values()), 9),
                "unserved_mwh": round(state["unserved_mwh"], 9),
                "curtailed_mwh": round(state["curtailed_mwh"], 9),
                "start_count": start_count,
                "stop_count": stop_count,
                "starts_by_unit_source": starts_by_unit_source,
                "stops_by_unit_source": stops_by_unit_source,
                "bess_soc_end": round(state["bess_soc_end"], 9),
            }
        )
    return rows


def _stream_run(
    *,
    scenario_id: str,
    mode: str,
    spec: dict[str, Any],
    replay_events: list[dict[str, Any]] | None,
    demand_replay: list[tuple[float, float]] | None,
    tick_path: Path,
) -> tuple[Any, dict[str, Any], float]:
    ctx = _stream_context(
        spec,
        run_id=f"{scenario_id}-{mode}",
        mode=mode,
        replay_events=replay_events,
        demand_replay=demand_replay,
        capture_trace=False,
    )
    tick_count = int(round(float(ctx.end_sim_time) / TICK_SECONDS))
    daily = {
        day: {
            "fuel_cumulative": {
                component: 0.0
                for component in (
                    "load_fuel_mmbtu",
                    "no_load_fuel_mmbtu",
                    "hot_standby_fuel_mmbtu",
                    "start_fuel_mmbtu",
                )
            },
            "unserved_mwh": 0.0,
            "curtailed_mwh": 0.0,
            "bess_soc_end": 0.0,
        }
        for day in range(1, SEVEN_DAYS + 1)
    }
    components = tuple(daily[1]["fuel_cumulative"])
    final_rows: dict[str, dict[str, Any]] = {}
    previous_by_unit: dict[str, dict[str, float]] = {}
    exposure_by_component = Counter()
    exposure_by_unit = Counter()
    attributable_by_unit = Counter()
    sync_counts = Counter()
    low_load_minutes = Counter()
    cluster_energy = {
        number: 0.0 for number, _ in _cluster_offsets(SEVEN_DAYS)
    }
    unserved_intervals: list[dict[str, float]] = []
    open_interval: dict[str, float] | None = None
    energy_unserved = 0.0
    energy_served = 0.0
    curtailment_mwh = 0.0
    peak_unserved = 0.0
    max_d4 = 0.0
    max_ledger = 0.0
    closure_status = True
    bess_soc_min = float("inf")
    bess_soc_max = 0.0
    final_tick: Any = None
    synchronized_seen = False
    forecast_errors: list[float] = []
    forecast_history_seen = 0
    last_forecast_identity: int | None = None
    turbine_by_id = {
        str(turbine.config.asset_id): turbine for turbine in ctx.sim_state.turbines
    }
    tick_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with gzip.open(tick_path, "wt", encoding="utf-8") as handle:
        for _ in range(tick_count):
            tick = ctx.step()
            final_tick = tick
            keep = {
                "tick_index": tick.tick_index,
                "sim_time_seconds": tick.sim_time_seconds,
                "p_compute_mw": tick.p_compute_demand_mw,
                "p_cooling_mw": tick.p_cooling_demand_mw,
                "p_total_mw": tick.p_demand_mw,
                "p_generation_mw": tick.p_generation_mw,
                "p_served_mw": tick.p_served_mw,
                "p_unserved_mw": tick.p_unserved_mw,
                "p_imbalance_mw": tick.p_imbalance_mw,
                "p_dispatch_curtailed_mw": tick.p_dispatch_curtailed_mw,
                "turbine_output_mw": tick.turbine_output_mw,
                "bess_output_mw": tick.bess_output_mw,
                "bess_soc_fraction": tick.bess_soc_fraction,
                "turbine_fuel_telemetry": tick.turbine_fuel_telemetry,
                "turbine_units": tick.turbine_units,
                "commitment_blocked_by": tick.commitment_blocked_by,
            }
            handle.write(json.dumps(keep, separators=(",", ":")) + "\n")
            day = _day_number(tick.sim_time_seconds)
            state = daily[day]
            unserved = max(0.0, float(tick.p_unserved_mw or 0.0))
            curtailed = max(0.0, float(tick.p_dispatch_curtailed_mw or 0.0))
            energy_unserved += unserved * TICK_SECONDS / 3600.0
            energy_served += max(0.0, float(tick.p_served_mw or 0.0)) * TICK_SECONDS / 3600.0
            curtailment_mwh += curtailed * TICK_SECONDS / 3600.0
            peak_unserved = max(peak_unserved, unserved)
            state["unserved_mwh"] += unserved * TICK_SECONDS / 3600.0
            state["curtailed_mwh"] += curtailed * TICK_SECONDS / 3600.0
            state["bess_soc_end"] = float(tick.bess_soc_fraction)
            bess_soc_min = min(bess_soc_min, float(tick.bess_soc_fraction))
            bess_soc_max = max(bess_soc_max, float(tick.bess_soc_fraction))
            current_values_by_unit: dict[str, dict[str, float]] = {}
            for telemetry in tick.turbine_fuel_telemetry:
                unit_id = str(telemetry.get("asset_id", "unknown"))
                current_values = {
                    component: float(telemetry.get(component, 0.0) or 0.0)
                    for component in components
                }
                current_values_by_unit[unit_id] = current_values
                final_rows[unit_id] = dict(telemetry)
                for component in components:
                    state["fuel_cumulative"][component] += 0.0
                prior = previous_by_unit.get(unit_id, {})
                increments = {
                    component: max(
                        0.0,
                        current_values[component] - prior.get(component, 0.0),
                    )
                    for component in components
                }
                previous_by_unit[unit_id] = current_values
                if curtailed > 1e-9:
                    for component, value in increments.items():
                        exposure_by_component[component] += value
                        exposure_by_unit[unit_id] += value
            for component in components:
                state["fuel_cumulative"][component] = sum(
                    values[component] for values in current_values_by_unit.values()
                )
            tick_sync_count = sum(
                1
                for unit in tick.turbine_units
                if str(unit.get("state", "")).lower()
                in {"synchronised", "synchronized", "unloading"}
            )
            sync_counts[tick_sync_count] += 1
            synchronized_seen = synchronized_seen or tick_sync_count > 0
            for unit in tick.turbine_units:
                state_name = str(unit.get("state", "")).lower()
                on_bus = state_name in {"synchronised", "synchronized", "unloading"}
                rated = float(unit.get("rated_mw", 0.0) or 0.0)
                output = float(unit.get("output_mw", 0.0) or 0.0)
                if on_bus and 0.0 < output < 0.5 * rated:
                    low_load_minutes[str(unit.get("asset_id"))] += TICK_SECONDS / 60.0
            if curtailed > 1e-9:
                on_bus = [
                    unit
                    for unit in tick.turbine_units
                    if bool(unit.get("breaker_closed"))
                    and str(unit.get("state", "")).lower()
                    in {"synchronised", "synchronized", "unloading"}
                ]
                basis = {
                    str(unit.get("asset_id")): max(
                        0.0, float(unit.get("output_mw", 0.0) or 0.0)
                    )
                    for unit in on_bus
                }
                basis_total = sum(basis.values())
                if basis_total <= 1e-9:
                    basis = {
                        str(unit.get("asset_id")): max(
                            0.0, float(unit.get("rated_mw", 0.0) or 0.0)
                        )
                        for unit in on_bus
                    }
                    basis_total = sum(basis.values())
                if basis_total > 1e-9:
                    for unit in on_bus:
                        unit_id = str(unit.get("asset_id"))
                        turbine = turbine_by_id.get(unit_id)
                        rated = float(unit.get("rated_mw", 0.0) or 0.0)
                        output = max(0.0, float(unit.get("output_mw", 0.0) or 0.0))
                        fuel = getattr(getattr(turbine, "config", None), "fuel", None)
                        if turbine is None or fuel is None or rated <= 0.0:
                            continue
                        allocated_mwh = (
                            curtailed * TICK_SECONDS / 3600.0
                            * basis.get(unit_id, 0.0)
                            / basis_total
                        )
                        attributable_by_unit[unit_id] += (
                            allocated_mwh
                            * fuel.heat_rate_btu_per_kwh(output / rated)
                            / 1000.0
                        )
            if open_interval is not None and unserved <= 1e-9:
                unserved_intervals.append(open_interval)
                open_interval = None
            elif unserved > 1e-9:
                if open_interval is None:
                    open_interval = {
                        "start_sim_time_s": float(tick.sim_time_seconds) - TICK_SECONDS,
                        "end_sim_time_s": float(tick.sim_time_seconds),
                        "peak_unserved_mw": unserved,
                    }
                else:
                    open_interval["end_sim_time_s"] = float(tick.sim_time_seconds)
                    open_interval["peak_unserved_mw"] = max(
                        open_interval["peak_unserved_mw"], unserved
                    )
            interval_start = float(tick.sim_time_seconds) - TICK_SECONDS
            for cluster_number, cluster_start in _cluster_offsets(SEVEN_DAYS):
                if cluster_start <= interval_start < cluster_start + 3300.0:
                    cluster_energy[cluster_number] += unserved * TICK_SECONDS / 3600.0
                    break
            ledger_defect = abs(
                float(tick.p_generation_mw)
                - float(tick.p_served_mw or 0.0)
                - float(tick.p_dispatch_curtailed_mw or 0.0)
            )
            max_ledger = max(max_ledger, ledger_defect)
            max_d4 = max(
                max_d4,
                abs(float(getattr(tick, "d4_balance_defect_mw", 0.0) or 0.0)),
            )
            closure_status = closure_status and (
                ledger_defect <= 1e-3
                or abs(float(tick.p_imbalance_mw or 0.0)) <= 1e-3
            )
            controller = ctx.turbine_commitment_controller
            latest_forecast = getattr(controller, "_latest_forecast", None)
            latest_identity = id(latest_forecast) if latest_forecast is not None else None
            if (
                latest_forecast is not None
                and latest_identity != last_forecast_identity
            ):
                forecast_errors.append(
                    float(tick.p_demand_mw or 0.0)
                    - float(latest_forecast.forecast_mw)
                )
                forecast_history_seen += 1
                last_forecast_identity = latest_identity
    if open_interval is not None:
        unserved_intervals.append(open_interval)
    wall = time.perf_counter() - started
    controller = ctx.turbine_commitment_controller
    logs = [record.as_dict() for record in controller.log]
    starts = [
        {
            "unit_id": record.get("unit_id"),
            "sim_time_s": record.get("sim_time_s"),
            "action": record.get("action"),
            "source": record.get("source"),
            "reason": record.get("reason"),
        }
        for record in logs
        if record.get("accepted")
        and record.get("changed_state")
        and record.get("action") in {"start", "release"}
    ]
    stops = [
        {
            "unit_id": record.get("unit_id"),
            "sim_time_s": record.get("sim_time_s"),
            "action": record.get("action"),
            "source": record.get("source"),
            "reason": record.get("reason"),
        }
        for record in logs
        if record.get("accepted")
        and record.get("changed_state")
        and record.get("action") in {"stop", "stop_complete"}
    ]
    proposal_records = [
        record for record in logs
        if str(record.get("action", "")).startswith("proposal_")
    ]
    proposal_summary = {
        "approved": sum(bool(record.get("accepted")) for record in proposal_records),
        "vetoed": sum(not bool(record.get("accepted")) for record in proposal_records),
        "by_action": {
            action: {
                "approved": sum(
                    record.get("action") == action and bool(record.get("accepted"))
                    for record in proposal_records
                ),
                "vetoed": sum(
                    record.get("action") == action and not bool(record.get("accepted"))
                    for record in proposal_records
                ),
            }
            for action in sorted({record.get("action") for record in proposal_records})
        },
    }
    _assert_run_fuel_nonzero(
        ctx,
        synchronized_seen=synchronized_seen,
        final_rows=final_rows,
        scenario_id=f"{scenario_id}-{mode}",
    )
    fuel_by_component = {
        component: sum(
            float(row.get(component, 0.0) or 0.0)
            for row in final_rows.values()
        )
        for component in components
    }
    fuel_by_unit = {}
    for unit_id, row in final_rows.items():
        fuel_by_unit[unit_id] = {
            component: float(row.get(component, 0.0) or 0.0)
            for component in components
        }
        fuel_by_unit[unit_id]["total_fuel_mmbtu"] = float(
            row.get("total_fuel_mmbtu", 0.0) or 0.0
        )
    actual_starts = {
        turbine.config.asset_id: int(getattr(turbine, "_start_count", 0))
        for turbine in ctx.sim_state.turbines
    }
    logged_starts = dict(getattr(controller, "start_counts", {}))
    forecast_misses = {
        "count": int(getattr(controller, "forecast_miss_count", 0)),
        "peak_mw": round(float(getattr(controller, "forecast_miss_peak_mw", 0.0)), 9),
    }
    forecast_quality = {
        "forecast_tick_count": forecast_history_seen,
        "matched_error_tick_count": len(forecast_errors),
        "signed_error_mw": _distribution(forecast_errors),
        "absolute_error_mw": _distribution([abs(value) for value in forecast_errors]),
        "miss_count": forecast_misses["count"],
        "miss_peak_mw": forecast_misses["peak_mw"],
    }
    daily_rows = _stream_daily_rows(
        daily,
        starts=starts,
        stops=stops,
    )
    summary = {
        "scenario_id": scenario_id,
        "mode": mode,
        "compute_description": "scheduler-shaped GPU workload demand",
        "trace_source": "baseline live background trace replay",
        "wall_clock_seconds": round(wall, 6),
        "tick_count": tick_count,
        "interval_seconds": TICK_SECONDS,
        "turbine_fuel_mmbtu": round(sum(fuel_by_component.values()), 9),
        "fuel_by_component_mmbtu": {
            key: round(value, 9) for key, value in fuel_by_component.items()
        },
        "fuel_by_unit_mmbtu": {
            key: {name: round(value, 9) for name, value in values.items()}
            for key, values in fuel_by_unit.items()
        },
        "preload_fuel_mmbtu": round(float(controller.preload_fuel_mmbtu), 9),
        "dispatch_curtailment_mwh": round(curtailment_mwh, 9),
        "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
            key: round(value, 9) for key, value in exposure_by_component.items()
        },
        "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
            key: round(value, 9) for key, value in exposure_by_unit.items()
        },
        "dispatch_curtailment_interval_exposure_fuel_mmbtu": round(
            sum(exposure_by_component.values()), 9
        ),
        "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
            key: round(value, 9) for key, value in attributable_by_unit.items()
        },
        "dispatch_curtailment_attributable_fuel_mmbtu": round(
            sum(attributable_by_unit.values()), 9
        ),
        "dispatch_curtailment_fuel_mmbtu": round(
            sum(exposure_by_component.values()), 9
        ),
        "starts": starts,
        "stops": stops,
        "start_count": sum(actual_starts.values()),
        "start_count_reconciled": actual_starts == {
            unit_id: logged_starts.get(unit_id, 0)
            for unit_id in actual_starts
        },
        "synchronized_count_distribution_ticks": dict(
            sorted((str(key), value) for key, value in sync_counts.items())
        ),
        "unit_minutes_below_50_percent": {
            key: round(value, 6) for key, value in sorted(low_load_minutes.items())
        },
        "energy_balance": {
            "closure_required": True,
            "closure_status": closure_status,
            "max_abs_d4_balance_defect_mw": round(max_d4, 9),
            "max_abs_physical_ledger_defect_mw": round(max_ledger, 9),
            "served_demand_mwh": round(energy_served, 9),
            "unserved_demand_mwh": round(energy_unserved, 9),
            "dispatch_curtailment_mwh": round(curtailment_mwh, 9),
        },
        "bess_soc_min": round(bess_soc_min, 9),
        "bess_soc_max": round(bess_soc_max, 9),
        "bess_soc_final": round(float(final_tick.bess_soc_fraction), 9),
        "unserved_mwh": round(energy_unserved, 9),
        "peak_unserved_mw": round(peak_unserved, 9),
        "unserved_intervals": unserved_intervals,
        "unserved_by_cluster": [
            {
                "cluster": cluster,
                "unserved_mwh": round(energy, 9),
                "had_unserved": energy > 1e-9,
            }
            for cluster, energy in sorted(cluster_energy.items())
        ],
        "hard_violations": sorted(
            str(reason)
            for reason in getattr(controller, "constraint_violation_reasons", [])
        ),
        "forecast_misses": forecast_misses,
        "forecast_quality": forecast_quality,
        "core_proposals": proposal_summary,
        "commitment_log": (
            logs[:60]
            + ([{"truncated": True, "omitted_record_count": len(logs) - 120}] if len(logs) > 120 else [])
            + (logs[-59:] if len(logs) > 120 else [])
        ),
        "commitment_log_record_count": len(logs),
        "preload_actions": list(controller.preload_actions),
        "preload_outcomes": [],
        "stop_floor_refusal_count": len(getattr(controller, "stop_floor_refusals", [])),
        "stop_floor_refusals": list(getattr(controller, "stop_floor_refusals", [])),
        "constraints_valid": bool(getattr(controller, "constraints_valid", True)),
        "fuel_guard": {
            "guard_status": "PASS",
            "active_modelled_units": sorted(final_rows),
            "active_unit_count": len(final_rows),
        },
        "daily_breakdown": daily_rows,
        "kube_power_reactive_ticks": 0,
        "kube_requeued_admissions": 0,
    }
    return ctx, summary, wall


def _day_number(sim_time_seconds: float) -> int:
    return min(
        SEVEN_DAYS,
        max(1, int((float(sim_time_seconds) - 1e-9) // DAY_SECONDS) + 1),
    )


def _event_counts(
    events: Iterable[dict[str, Any]],
    *,
    day: int,
) -> tuple[int, dict[str, int]]:
    by_unit_source: Counter[str] = Counter()
    for event in events:
        if _day_number(float(event.get("sim_time_s", 0.0))) != day:
            continue
        unit = str(event.get("unit_id", "unknown"))
        source = str(event.get("source", "unknown"))
        by_unit_source[f"{unit}|{source}"] += 1
    return sum(by_unit_source.values()), dict(sorted(by_unit_source.items()))


def _daily_breakdown(
    ticks: list[Any],
    *,
    starts: list[dict[str, Any]],
    stops: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    components = (
        "load_fuel_mmbtu",
        "no_load_fuel_mmbtu",
        "hot_standby_fuel_mmbtu",
        "start_fuel_mmbtu",
    )
    daily: dict[int, dict[str, Any]] = {
        day: {
            "day": day,
            "kind": "weekday" if day <= 5 else "weekend",
            "fuel_cumulative": {component: 0.0 for component in components},
            "unserved_mwh": 0.0,
            "curtailed_mwh": 0.0,
            "bess_soc_end": 0.0,
        }
        for day in range(1, SEVEN_DAYS + 1)
    }
    for tick in ticks:
        day = _day_number(tick.sim_time_seconds)
        row = daily[day]
        row["unserved_mwh"] += (
            max(0.0, float(tick.p_unserved_mw or 0.0))
            * TICK_SECONDS
            / 3600.0
        )
        row["curtailed_mwh"] += (
            max(0.0, float(tick.p_dispatch_curtailed_mw or 0.0))
            * TICK_SECONDS
            / 3600.0
        )
        row["bess_soc_end"] = float(tick.bess_soc_fraction)
        fuel_snapshot = {component: 0.0 for component in components}
        for telemetry in tick.turbine_fuel_telemetry:
            for component in components:
                fuel_snapshot[component] += float(
                    telemetry.get(component, 0.0) or 0.0
                )
        row["fuel_cumulative"] = fuel_snapshot

    previous_fuel = {component: 0.0 for component in components}
    for day in range(1, SEVEN_DAYS + 1):
        row = daily[day]
        fuel_by_component = {
            component: max(
                0.0,
                row["fuel_cumulative"][component] - previous_fuel[component],
            )
            for component in components
        }
        previous_fuel = dict(row["fuel_cumulative"])
        start_count, starts_by_unit_source = _event_counts(starts, day=day)
        stop_count, stops_by_unit_source = _event_counts(stops, day=day)
        row["fuel_by_component_mmbtu"] = {
            component: round(value, 9)
            for component, value in fuel_by_component.items()
        }
        row["fuel_mmbtu"] = round(sum(fuel_by_component.values()), 9)
        row["unserved_mwh"] = round(row["unserved_mwh"], 9)
        row["curtailed_mwh"] = round(row["curtailed_mwh"], 9)
        row["bess_soc_end"] = round(row["bess_soc_end"], 9)
        row["start_count"] = start_count
        row["stop_count"] = stop_count
        row["starts_by_unit_source"] = starts_by_unit_source
        row["stops_by_unit_source"] = stops_by_unit_source
        del row["fuel_cumulative"]
    return list(daily.values())


def run_mode(scenario_id: str, mode: str, output_dir: Path) -> None:
    if mode not in {"baseline", "informed"}:
        raise ValueError(f"unsupported mode: {mode}")
    compact = _load_stage2_compact_spec(scenario_id)
    expanded = expand_phase2b_reference_spec(compact)
    probe = _load_probe(output_dir, scenario_id)
    replay_spec = copy.deepcopy(expanded)
    replay_spec["workload_events"] = []
    tick_path = _tick_path(output_dir, scenario_id, mode)
    ctx, summary, wall = _stream_run(
        scenario_id=scenario_id,
        mode=mode,
        spec=replay_spec,
        replay_events=probe["replay_events"],
        demand_replay=[tuple(values) for values in probe["demand_replay"]],
        tick_path=tick_path,
    )
    summary.update(
        {
            "background_probe_wall_clock_seconds": probe[
                "probe_wall_clock_seconds"
            ],
            "background_trace_signal_count": probe[
                "background_trace_signal_count"
            ],
            "demand_replay_tick_count": len(probe["demand_replay"]),
            "replay_strategy": (
                "captured live workload-signal/demand trace; replayed per-tick "
                "compute and lagged cooling demand"
            ),
            "background_power_reactive": probe["background_power_reactive"],
        }
    )
    summary["tick_artifact"] = tick_path.name
    summary = _cap_summary_records(summary)
    _write_json_bounded(_run_path(output_dir, scenario_id, mode), summary)
    (output_dir / f"{scenario_id}-{mode}.txt").write_text(
        "\n".join(
            [
                f"{scenario_id} {mode}",
                f"compute: {summary['compute_description']}",
                f"ticks: {summary['tick_count']}",
                f"wall_clock_seconds: {summary['wall_clock_seconds']}",
                f"fuel_mmbtu: {summary['turbine_fuel_mmbtu']}",
                f"unserved_mwh: {summary['unserved_mwh']}",
                f"peak_unserved_mw: {summary['peak_unserved_mw']}",
                f"dispatch_curtailment_mwh: {summary['dispatch_curtailment_mwh']}",
                "dispatch_curtailment_interval_exposure_fuel_mmbtu: "
                f"{summary['dispatch_curtailment_interval_exposure_fuel_mmbtu']}",
                "dispatch_curtailment_attributable_fuel_mmbtu: "
                f"{summary['dispatch_curtailment_attributable_fuel_mmbtu']}",
                f"energy_balance: {json.dumps(summary['energy_balance'], sort_keys=True)}",
                f"starts: {json.dumps(summary['starts'], sort_keys=True)}",
                f"stops: {json.dumps(summary['stops'], sort_keys=True)}",
                f"hard_violations: {json.dumps(summary['hard_violations'])}",
            ]
        )
        + "\n"
    )
    checkpoint = json.loads(_checkpoint_path(output_dir, scenario_id).read_text())
    checkpoint[f"{mode}_complete"] = True
    checkpoint[f"{mode}_wall_clock_seconds"] = summary["wall_clock_seconds"]
    _checkpoint_path(output_dir, scenario_id).write_text(
        json.dumps(checkpoint, indent=2, sort_keys=True) + "\n"
    )
    print(
        f"{scenario_id} {mode}: complete; ticks={summary['tick_count']}; "
        f"fuel={summary['turbine_fuel_mmbtu']:.6f} MMBtu"
    )


def _stream_replay_diff(
    baseline_path: Path,
    informed_path: Path,
) -> tuple[bool, float]:
    max_diff = 0.0
    with gzip.open(baseline_path, "rt", encoding="utf-8") as base_handle:
        with gzip.open(informed_path, "rt", encoding="utf-8") as informed_handle:
            for index, (base_line, informed_line) in enumerate(
                zip(base_handle, informed_handle)
            ):
                base = json.loads(base_line)
                informed = json.loads(informed_line)
                max_diff = max(
                    max_diff,
                    abs(
                        float(base.get("p_compute_mw", 0.0))
                        - float(informed.get("p_compute_mw", 0.0))
                    ),
                )
                if index >= 120959:
                    break
            else:
                return False, float("inf")
    return max_diff <= 1e-9, max_diff


def _stage1_reference(scenario_family: str) -> dict[str, Any]:
    scenario_name = {
        "h1": "scenario-h1-k8s-ray-24h",
        "h2": "scenario-h2-slurm-24h",
    }[scenario_family]
    path = STAGE1_ROOT / f"{scenario_name}-summary.json"
    return json.loads(path.read_text())


def _daily_totals(rows: list[dict[str, Any]], *, label: str) -> dict[str, Any]:
    components = (
        "load_fuel_mmbtu",
        "no_load_fuel_mmbtu",
        "hot_standby_fuel_mmbtu",
        "start_fuel_mmbtu",
    )
    total = {
        "period": label,
        "fuel_by_component_mmbtu": {component: 0.0 for component in components},
        "fuel_mmbtu": 0.0,
        "unserved_mwh": 0.0,
        "curtailed_mwh": 0.0,
        "start_count": 0,
        "stop_count": 0,
    }
    for row in rows:
        for component in components:
            total["fuel_by_component_mmbtu"][component] += float(
                row["fuel_by_component_mmbtu"][component]
            )
        total["fuel_mmbtu"] += float(row["fuel_mmbtu"])
        total["unserved_mwh"] += float(row["unserved_mwh"])
        total["curtailed_mwh"] += float(row["curtailed_mwh"])
        total["start_count"] += int(row["start_count"])
        total["stop_count"] += int(row["stop_count"])
    total["fuel_by_component_mmbtu"] = {
        component: round(value, 9)
        for component, value in total["fuel_by_component_mmbtu"].items()
    }
    total["fuel_mmbtu"] = round(total["fuel_mmbtu"], 9)
    total["unserved_mwh"] = round(total["unserved_mwh"], 9)
    total["curtailed_mwh"] = round(total["curtailed_mwh"], 9)
    return total


def finalize_scenario(scenario_id: str, output_dir: Path) -> dict[str, Any]:
    compact = _load_stage2_compact_spec(scenario_id)
    family = str(compact["phase2b_reference_family"])
    run_paths = {
        mode: _run_path(output_dir, scenario_id, mode)
        for mode in ("baseline", "informed")
    }
    if not all(path.is_file() for path in run_paths.values()):
        raise FileNotFoundError(f"{scenario_id}: both mode JSONs are required")
    runs = {mode: json.loads(path.read_text()) for mode, path in run_paths.items()}
    trace_equal, max_diff = _stream_replay_diff(
        _tick_path(output_dir, scenario_id, "baseline"),
        _tick_path(output_dir, scenario_id, "informed"),
    )
    comparison = None
    for summary in runs.values():
        summary["identical_compute_trace"] = trace_equal
        summary["max_compute_trace_diff_mw"] = max_diff
        acceptance = _phase2b_acceptance_verdict(
            summary=summary,
            baseline=runs["baseline"],
            informed=runs["informed"],
            trace_equal=trace_equal,
        )
        summary.update(acceptance)
        comparison = acceptance["informed_vs_baseline"]
        _write_json_bounded(
            _run_path(output_dir, scenario_id, summary["mode"]),
            summary,
        )

    base = runs["baseline"]
    informed = runs["informed"]
    base_fuel = float(base["turbine_fuel_mmbtu"])
    informed_fuel = float(informed["turbine_fuel_mmbtu"])
    total_delta = informed_fuel - base_fuel
    attributable_delta = (
        float(base["dispatch_curtailment_attributable_fuel_mmbtu"])
        - float(informed["dispatch_curtailment_attributable_fuel_mmbtu"])
    )
    interval_delta = (
        float(base["dispatch_curtailment_interval_exposure_fuel_mmbtu"])
        - float(informed["dispatch_curtailment_interval_exposure_fuel_mmbtu"])
    )
    daily = {
        mode: runs[mode]["daily_breakdown"] for mode in ("baseline", "informed")
    }
    for mode in daily:
        daily[mode].append(
            _daily_totals(daily[mode][:5], label="weekday_total")
        )
        daily[mode].append(
            _daily_totals(daily[mode][5:7], label="weekend_total")
        )
    stage1 = _stage1_reference(family)
    stage1_delta = float(
        stage1["fuel_attribution"]["informed_minus_baseline_mmbtu"]
    )
    weekday_delta = (
        float(daily["informed"][0]["fuel_mmbtu"])
        - float(daily["baseline"][0]["fuel_mmbtu"])
    )
    weekday_comparison = {
        "stage1_24h_difference_mmbtu": stage1_delta,
        "seven_day_day1_difference_mmbtu": round(weekday_delta, 9),
        "difference_mmbtu": round(weekday_delta - stage1_delta, 9),
        "matches_within_1e-6": abs(weekday_delta - stage1_delta) <= 1e-6,
        "explanation": (
            "Day 1 uses the same six weekday cluster offsets and replay "
            "construction as the 24-hour reference."
        ),
    }
    aggregate = {
        "scenario_id": scenario_id,
        "days": SEVEN_DAYS,
        "identical_compute_trace": trace_equal,
        "max_compute_trace_diff_mw": max_diff,
        "informed_vs_baseline": comparison,
        "acceptance_verdict": (
            "PASS"
            if all(run["acceptance_verdict"] == "PASS" for run in runs.values())
            else "FAIL"
        ),
        "fuel_attribution": {
            "baseline_mmbtu": base_fuel,
            "informed_mmbtu": informed_fuel,
            "informed_minus_baseline_mmbtu": total_delta,
            "percent_change_vs_baseline": (
                100.0 * total_delta / base_fuel if base_fuel else 0.0
            ),
            "avoided_curtailment_interval_exposure_fuel_mmbtu": interval_delta,
            "avoided_curtailment_attributable_fuel_mmbtu": attributable_delta,
            "avoided_curtailment_fuel_mmbtu": attributable_delta,
            "share_of_fuel_difference_attributable_to_avoided_curtailment": (
                attributable_delta / (base_fuel - informed_fuel)
                if base_fuel != informed_fuel
                else 0.0
            ),
            "component_delta_mmbtu": {
                component: informed["fuel_by_component_mmbtu"].get(component, 0.0)
                - base["fuel_by_component_mmbtu"].get(component, 0.0)
                for component in base["fuel_by_component_mmbtu"]
            },
        },
        "weekday_reference_comparison": weekday_comparison,
        "daily_breakdown": daily,
        "runs": {
            mode: {
                "mode": mode,
                "acceptance_verdict": runs[mode]["acceptance_verdict"],
                "acceptance_gates": runs[mode]["acceptance_gates"],
                "turbine_fuel_mmbtu": runs[mode]["turbine_fuel_mmbtu"],
                "unserved_mwh": runs[mode]["unserved_mwh"],
                "bess_soc_final": runs[mode]["bess_soc_final"],
                "wall_clock_seconds": runs[mode]["wall_clock_seconds"],
                "daily_breakdown": daily[mode],
            }
            for mode in ("baseline", "informed")
        },
    }
    _write_json_bounded(
        output_dir / f"{scenario_id}-summary.json",
        aggregate,
    )
    return aggregate


def _format_daily_rows(
    scenario_id: str,
    mode: str,
    rows: list[dict[str, Any]],
) -> list[str]:
    lines = [f"### {scenario_id} / {mode}", "", "| Day | Kind | Fuel MMBtu | Unserved MWh | Curtailment MWh | Starts | Stops | BESS SoC end |", "|---:|---|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        day = row["day"] if "day" in row else row["period"]
        lines.append(
            f"| {day} | {row.get('kind', '') or row['period']} | "
            f"{row['fuel_mmbtu']:.6f} | {row['unserved_mwh']:.9f} | "
            f"{row['curtailed_mwh']:.9f} | {row['start_count']} | "
            f"{row['stop_count']} | "
            f"{row.get('bess_soc_end', 0.0):.9f} |"
        )
    return lines


def write_report(output_dir: Path, aggregates: list[dict[str, Any]]) -> None:
    lines = [
        "# Addendum H Phase 2b-2 Seven-Day Report",
        "",
        "Scope: H-1 and H-2 seven-day reference runs, baseline and informed modes. "
        "Phase 3 sensitivity sweeps were not started. Commitment policy, "
        "DR-2026-09-16-ACCEPTANCE, DR-2026-09-17-BASELINE, pre-load rule, "
        "fuel model, curtailment ordering, and forecast rule were unchanged.",
        "",
        "## Headline results",
        "",
        "| Scenario | Verdict | Baseline fuel | Informed fuel | Difference | Change | Attributable-curtailment share | Trace diff MW |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for aggregate in aggregates:
        attribution = aggregate["fuel_attribution"]
        lines.append(
            f"| {aggregate['scenario_id']} | **{aggregate['acceptance_verdict']}** | "
            f"{attribution['baseline_mmbtu']:.6f} | {attribution['informed_mmbtu']:.6f} | "
            f"{attribution['informed_minus_baseline_mmbtu']:.6f} | "
            f"{attribution['percent_change_vs_baseline']:.4f}% | "
            f"{attribution['share_of_fuel_difference_attributable_to_avoided_curtailment']:.6f} | "
            f"{aggregate['max_compute_trace_diff_mw']:.12g} |"
        )
    lines += [
        "",
        "The attributable-curtailment share uses curtailed MWh allocated pro rata "
        "across on-bus turbines at each unit's operating-point heat rate. "
        "Interval-exposure fuel remains separate.",
        "",
    ]
    for aggregate in aggregates:
        lines += [
            f"## {aggregate['scenario_id']}",
            "",
            f"Aggregate verdict: **{aggregate['acceptance_verdict']}**.",
            "",
        ]
        for mode in ("baseline", "informed"):
            run = json.loads(
                (output_dir / f"{aggregate['scenario_id']}-{mode}.json").read_text()
            )
            lines += [
                f"### {mode.capitalize()}",
                "",
                f"- Acceptance gates: `{json.dumps(run['acceptance_gates'], sort_keys=True)}`.",
                f"- Fuel: `{json.dumps(run['fuel_by_component_mmbtu'], sort_keys=True)}`; "
                f"total **{run['turbine_fuel_mmbtu']:.6f} MMBtu**; "
                f"pre-load tag **{run['preload_fuel_mmbtu']:.6f} MMBtu**.",
                f"- Curtailment: **{run['dispatch_curtailment_mwh']:.9f} MWh**; "
                f"interval-exposure fuel **{run['dispatch_curtailment_interval_exposure_fuel_mmbtu']:.6f} MMBtu**; "
                f"attributable fuel **{run['dispatch_curtailment_attributable_fuel_mmbtu']:.6f} MMBtu**.",
                f"- Starts: `{json.dumps(run['starts'], sort_keys=True)}`.",
                f"- Stops: `{json.dumps(run['stops'], sort_keys=True)}`.",
                f"- Reserve-floor refusals: **{run['stop_floor_refusal_count']}**; "
                "same-unit reserve-floor restart inside minimum-down window: **0 expected** "
                "(see stop-floor refusal evidence).",
                f"- Synchronized-count distribution: `{json.dumps(run['synchronized_count_distribution_ticks'], sort_keys=True)}`.",
                f"- Unit-minutes below 50%: `{json.dumps(run['unit_minutes_below_50_percent'], sort_keys=True)}`.",
                f"- Energy balance: `{json.dumps(run['energy_balance'], sort_keys=True)}`.",
                f"- BESS SoC: minimum **{run['bess_soc_min']:.9f}**, final **{run['bess_soc_final']:.9f}**.",
                f"- Unserved: **{run['unserved_mwh']:.9f} MWh**, peak **{run['peak_unserved_mw']:.9f} MW**, "
                f"intervals **{len(run['unserved_intervals'])}**; per-cluster: `{json.dumps(run['unserved_by_cluster'], sort_keys=True)}`.",
                f"- Forecast misses: `{json.dumps(run['forecast_misses'], sort_keys=True)}`.",
                f"- Core proposals: `{json.dumps(run['core_proposals'], sort_keys=True)}`.",
                f"- Wall-clock time: **{run['wall_clock_seconds']:.3f} s**.",
                "",
            ]
        attribution = aggregate["fuel_attribution"]
        lines += [
            "### Fuel attribution",
            "",
            f"- Component delta (informed − baseline): `{json.dumps(attribution['component_delta_mmbtu'], sort_keys=True)}`.",
            f"- Avoided-curtailment interval-exposure fuel: **{attribution['avoided_curtailment_interval_exposure_fuel_mmbtu']:.6f} MMBtu**.",
            f"- Avoided-curtailment attributable fuel: **{attribution['avoided_curtailment_attributable_fuel_mmbtu']:.6f} MMBtu**; "
            f"share **{attribution['share_of_fuel_difference_attributable_to_avoided_curtailment']:.6f}**.",
            "",
            "### Per-day breakdown",
            "",
        ]
        for mode in ("baseline", "informed"):
            lines += _format_daily_rows(
                aggregate["scenario_id"],
                mode,
                aggregate["daily_breakdown"][mode],
            )
            lines.append("")
        comparison = aggregate["weekday_reference_comparison"]
        lines += [
            "### Weekday versus Stage 2b-1",
            "",
            f"- Stage 1 24-hour informed-minus-baseline fuel difference: **{comparison['stage1_24h_difference_mmbtu']:.6f} MMBtu**.",
            f"- Seven-day day-1 weekday difference: **{comparison['seven_day_day1_difference_mmbtu']:.6f} MMBtu**.",
            f"- Matches within 1e-6 MMBtu: **{comparison['matches_within_1e-6']}**.",
            f"- Explanation: {comparison['explanation']}",
            "",
        ]
    lines += [
        "## Drift over the week",
        "",
        "The daily tables report BESS SoC at each day end. Compare those rows for "
        "a downward trend; no trend is inferred from the aggregate final value alone.",
        "",
    ]
    for aggregate in aggregates:
        informed_rows = aggregate["daily_breakdown"]["informed"]
        start_counts = [int(row["start_count"]) for row in informed_rows[:7]]
        lines.append(
            f"- {aggregate['scenario_id']} informed BESS SoC end-of-day: "
            + ", ".join(f"D{i + 1}={row['bess_soc_end']:.9f}" for i, row in enumerate(informed_rows[:7]))
            + f"; informed starts by day: {start_counts}."
        )
    lines += [
        "",
        "## Closure decision",
        "",
        "Stage 2b-2 can close only if both scenario aggregates and all acceptance "
        "gates are PASS, the trace-difference gate is within 1e-9 MW, and all "
        "fuel guards pass. Phase 3 sensitivity sweeps were not started.",
        "",
    ]
    report_path = output_dir / "stage2_report.md"
    report_path.write_text("\n".join(lines) + "\n")
    if report_path.stat().st_size >= MAX_JSON_BYTES:
        raise AssertionError("stage2_report.md must remain under 100 KB")


def finalize_all(output_dir: Path) -> int:
    aggregates = [
        finalize_scenario(scenario_id, output_dir)
        for scenario_id in REFERENCE_IDS
    ]
    manifest = {
        "stage": "2b-2",
        "compute_description": "scheduler-shaped GPU workload demand",
        "scenarios": aggregates,
    }
    _write_json_bounded(output_dir / "stage2_summary.json", manifest)
    (output_dir / "stage2_summary.txt").write_text(
        "\n".join(
            [
                "Addendum H Phase 2b-2",
                "====================",
                "Runs: H-1 and H-2 seven-day reference scenarios, baseline and informed.",
                "Demand approach: one baseline live background trace, replayed exactly in both modes.",
                *[
                    (
                        f"{item['scenario_id']}: {item['acceptance_verdict']}; "
                        f"trace_diff={item['max_compute_trace_diff_mw']:.12g} MW; "
                        f"fuel_delta={item['fuel_attribution']['informed_minus_baseline_mmbtu']:.6f} MMBtu; "
                        f"attributable_curtailment_share="
                        f"{item['fuel_attribution']['share_of_fuel_difference_attributable_to_avoided_curtailment']:.6f}"
                    )
                    for item in aggregates
                ],
            ]
        )
        + "\n"
    )
    write_report(output_dir, aggregates)
    return 0 if all(item["acceptance_verdict"] == "PASS" for item in aggregates) else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("probe", "mode", "finalize"))
    parser.add_argument("--scenario", choices=REFERENCE_IDS)
    parser.add_argument("--mode", choices=("baseline", "informed"))
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.command == "probe":
        if args.scenario is None:
            raise SystemExit("--scenario is required for probe")
        run_probe(args.scenario, args.output_dir)
        return 0
    if args.command == "mode":
        if args.scenario is None or args.mode is None:
            raise SystemExit("--scenario and --mode are required for mode")
        run_mode(args.scenario, args.mode, args.output_dir)
        return 0
    return finalize_all(args.output_dir)


if __name__ == "__main__":
    raise SystemExit(main())