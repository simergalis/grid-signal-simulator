"""Run Addendum H Phase 2b-1 reference scenarios.

This stage captures one live baseline workload-signal trace with the restored
background agents, then replays that exact trace in both commitment modes.
The replay is deliberate: the Kube-shaped agents inspect prior-tick headroom
and can requeue admissions, so letting each mode generate its own background
trace would confound controller behavior with demand behavior.

The simulator remains a deterministic model of scheduler-shaped GPU workload
demand.  This runner does not claim to reproduce real Kubernetes, Slurm, or
Ray scheduler behavior.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import gzip
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from core.asset_modules import TurbineState
from runtime.phase2b_reference import (
    _cluster_offsets,
    expand_phase2b_reference_spec,
)
from runtime.run_manager import _tick_result_to_dict
from runtime.scenario_factory import build_run_context_from_spec
from runtime.turbine_commitment import unserved_comparison_verdict
from scripts.run_phase2a_smoke import _extended_metrics


TICK_SECONDS = 5.0
REFERENCE_IDS = {
    "scenario-h1-k8s-ray-24h": "scenario-h1-k8s-ray-24h.json",
    "scenario-h2-slurm-24h": "scenario-h2-slurm-24h.json",
}
OUTPUT_ROOT = PACKAGE_ROOT.parents[3] / "docs" / "addendum-h-phase2b-results"


def _load_compact_spec(scenario_id: str) -> dict[str, Any]:
    path = PACKAGE_ROOT / "config" / "scenarios" / REFERENCE_IDS[scenario_id]
    return json.loads(path.read_text())


def _phase2b_fuel_guard(
    scenario_id: str,
    ctx: Any,
    ticks: list[Any],
) -> dict[str, Any]:
    """Fail loudly instead of reporting an unmodelled turbine as zero fuel."""
    active_units = [
        turbine for turbine in ctx.sim_state.turbines if turbine.is_on_bus
    ]
    missing_model = [
        turbine.config.asset_id
        for turbine in active_units
        if not turbine.fuel_modelled
    ]
    if missing_model:
        raise AssertionError(
            f"{scenario_id}: synchronized turbine(s) missing fuel model: "
            f"{sorted(missing_model)}"
        )
    final_rows = {
        str(row.get("asset_id")): row
        for row in (ticks[-1].turbine_fuel_telemetry if ticks else ())
    }
    missing_rows = [
        turbine.config.asset_id
        for turbine in active_units
        if (
            turbine.config.asset_id not in final_rows
            or not bool(final_rows[turbine.config.asset_id].get("fuel_modelled"))
        )
    ]
    if missing_rows:
        raise AssertionError(
            f"{scenario_id}: synchronized turbine(s) missing final fuel "
            f"telemetry: {sorted(missing_rows)}"
        )
    zero_fuel = [
        turbine.config.asset_id
        for turbine in active_units
        if float(final_rows[turbine.config.asset_id].get("total_fuel_mmbtu", 0.0) or 0.0)
        <= 1e-12
    ]
    if zero_fuel:
        raise AssertionError(
            f"{scenario_id}: synchronized turbine(s) finished with zero "
            f"fuel telemetry: {sorted(zero_fuel)}"
        )
    return {
        "guard_status": "PASS",
        "active_modelled_units": sorted(
            turbine.config.asset_id for turbine in active_units
        ),
        "active_unit_count": len(active_units),
    }


def _distribution(values: list[float]) -> dict[str, float | int]:
    clean = [float(value) for value in values if value == value]
    if not clean:
        return {
            "count": 0,
            "min": 0.0,
            "mean": 0.0,
            "median": 0.0,
            "p95": 0.0,
            "max": 0.0,
        }
    ordered = sorted(clean)
    p95_index = min(len(ordered) - 1, max(0, int(0.95 * len(ordered)) - 1))
    return {
        "count": len(clean),
        "min": round(min(clean), 9),
        "mean": round(statistics.fmean(clean), 9),
        "median": round(statistics.median(clean), 9),
        "p95": round(ordered[p95_index], 9),
        "max": round(max(clean), 9),
    }


def _forecast_quality(controller: Any, ticks: list[Any]) -> dict[str, Any]:
    history = list(getattr(controller, "forecast_history", []))
    errors = [
        float(tick.p_demand_mw or 0.0) - float(forecast.forecast_mw)
        for tick, forecast in zip(ticks, history)
    ]
    return {
        "forecast_tick_count": len(history),
        "matched_error_tick_count": len(errors),
        "signed_error_mw": _distribution(errors),
        "absolute_error_mw": _distribution([abs(value) for value in errors]),
        "miss_count": int(getattr(controller, "forecast_miss_count", 0)),
        "miss_peak_mw": round(
            float(getattr(controller, "forecast_miss_peak_mw", 0.0)), 9
        ),
    }


def _signal_dict(signal: Any) -> dict[str, Any]:
    raw = dataclasses.asdict(signal)
    raw["event_type"] = signal.event_type.value
    raw["workload_class"] = signal.workload_class.value
    # Replay through the ordinary scripted-event path.  Removing cluster
    # grouping preserves the exact aggregate signal stream rather than asking
    # the factory to aggregate the already-aggregated Kube signals again.
    for key in ("cluster_id", "scheduler_type", "capacity_unit"):
        raw.pop(key, None)
    return {
        key: value
        for key, value in raw.items()
        if value is not None
        and key
        in {
            "event_id",
            "job_id",
            "event_type",
            "timestamp",
            "hardware_profile_id",
            "node_count",
            "workload_class",
            "site_id",
            "queue_depth",
            "request_rate",
            "scheduler_domain",
            "renewable_shortfall_mw",
            "tenant_id",
            "model_id",
            "gpu_ids",
            "phase_kind",
            "phase_index",
            "gpu_utilization",
            "gpu_memory_mb",
            "gpu_power_multiplier",
            "infrastructure_allocation_id",
            "ray_cluster_id",
            "ray_workload_id",
            "admission_domain_id",
            "admission_queue_id",
            "capacity_budget_id",
            "admission_provider",
            "power_enforcement_policy",
        }
    }


def _run_context(
    spec: dict[str, Any],
    *,
    run_id: str,
    mode: str,
    replay_events: list[dict[str, Any]] | None = None,
    demand_replay: list[tuple[float, float]] | None = None,
    capture_trace: bool = False,
) -> tuple[Any, list[Any], float]:
    run_spec = copy.deepcopy(spec)
    run_spec["turbine_commitment_mode"] = mode
    if replay_events is not None:
        run_spec.pop("kube_clusters", None)
        run_spec.pop("slurm_config", None)
        run_spec["workload_events"] = replay_events
    ctx = build_run_context_from_spec(run_id, run_spec, playback_speed=0.0)
    ctx.sim_state.demand_replay_trace = demand_replay
    ctx.sim_state.capture_workload_signal_trace = capture_trace
    tick_count = int(round(float(ctx.end_sim_time) / TICK_SECONDS))
    started = time.perf_counter()
    ticks = [ctx.step() for _ in range(tick_count)]
    elapsed = time.perf_counter() - started
    if len(ticks) != tick_count:
        raise AssertionError(f"{run_id}: expected {tick_count} ticks, got {len(ticks)}")
    return ctx, ticks, elapsed


def _compact_commitment_log(controller: Any) -> list[dict[str, Any]]:
    records = []
    for record in controller.log:
        raw = record.as_dict()
        action = str(raw.get("action", ""))
        if raw.get("changed_state") or action.startswith("proposal_"):
            records.append(
                {
                    "sim_time_s": raw.get("sim_time_s"),
                    "unit_id": raw.get("unit_id"),
                    "action": raw.get("action"),
                    "source": raw.get("source"),
                    "accepted": raw.get("accepted"),
                    "changed_state": raw.get("changed_state"),
                    "reason": raw.get("reason", ""),
                    "refusal_reason": raw.get("refusal_reason", ""),
                }
            )
    if len(records) <= 120:
        return records
    return (
        records[:60]
        + [
            {
                "truncated": True,
                "omitted_record_count": len(records) - 120,
                "reason": "summary is capped; tick evidence and counts remain complete",
            }
        ]
        + records[-59:]
    )


def _cluster_unserved(
    ticks: list[Any],
    *,
    days: int,
) -> list[dict[str, Any]]:
    offsets = _cluster_offsets(days)
    result = []
    for cluster_number, start_s in offsets:
        end_s = start_s + 3300.0
        energy = sum(
            max(0.0, float(tick.p_unserved_mw or 0.0))
            * TICK_SECONDS
            / 3600.0
            for tick in ticks
            if start_s <= float(tick.sim_time_seconds) - TICK_SECONDS < end_s
        )
        result.append(
            {
                "cluster": cluster_number,
                "start_s": start_s,
                "end_s": end_s,
                "unserved_mwh": round(energy, 9),
                "had_unserved": energy > 1e-9,
            }
        )
    return result


def _run_summary(
    *,
    scenario_id: str,
    mode: str,
    ctx: Any,
    ticks: list[Any],
    wall_seconds: float,
    days: int,
    trace_source: str,
) -> dict[str, Any]:
    controller = ctx.turbine_commitment_controller
    fuel_guard = _phase2b_fuel_guard(scenario_id, ctx, ticks)
    logs = (
        [record.as_dict() for record in controller.log]
        if controller is not None
        else []
    )
    preload_actions = (
        list(controller.preload_actions) if controller is not None else []
    )
    metrics = _extended_metrics(ticks, controller, logs, preload_actions)
    final = ticks[-1]
    dispatch_curtailment_mwh = sum(
        max(0.0, float(tick.p_dispatch_curtailed_mw or 0.0))
        * TICK_SECONDS
        / 3600.0
        for tick in ticks
    )
    max_d4_defect = max(
        (abs(float(getattr(tick, "d4_balance_defect_mw", 0.0) or 0.0)) for tick in ticks),
        default=0.0,
    )
    max_ledger_defect = max(
        (
            abs(
                float(tick.p_generation_mw)
                - float(tick.p_served_mw or 0.0)
                - float(tick.p_dispatch_curtailed_mw or 0.0)
            )
            for tick in ticks
        ),
        default=0.0,
    )
    curtailment_values = [
        max(0.0, float(tick.p_dispatch_curtailed_mw or 0.0))
        for tick in ticks
    ]
    d4_values = [
        abs(float(getattr(tick, "d4_balance_defect_mw", 0.0) or 0.0))
        for tick in ticks
    ]
    hard_violations = set(
        str(reason)
        for reason in (
            list(getattr(controller, "constraint_violation_reasons", []))
            if controller is not None
            else []
        )
    )
    sync_counts = Counter(
        sum(
            1
            for unit in tick.turbine_units
            if str(unit.get("state", "")).lower()
            in {"synchronised", "synchronized", "unloading"}
        )
        for tick in ticks
    )
    low_load_minutes: dict[str, float] = Counter()
    for tick in ticks:
        for turbine in ctx.sim_state.turbines:
            if (
                turbine.state in {TurbineState.SYNCHRONISED, TurbineState.UNLOADING}
                and 0.0 < turbine._current_output_mw
                < 0.5 * turbine.config.rated_mw
            ):
                low_load_minutes[turbine.config.asset_id] += TICK_SECONDS / 60.0

    balance = {
        "closure_required": True,
        # Use the same authoritative physical-ledger criterion as the Phase 2a
        # acceptance smoke. D4 remains a diagnostic routing observation rather
        # than a Stage 2b energy-closure gate.
        "closure_status": all(
            abs(
                float(tick.p_generation_mw)
                - float(tick.p_served_mw or 0.0)
                - float(tick.p_dispatch_curtailed_mw or 0.0)
            )
            <= 1e-3
            or abs(float(tick.p_imbalance_mw or 0.0)) <= 1e-3
            for tick in ticks
        ),
        "max_abs_d4_balance_defect_mw": round(max_d4_defect, 9),
        "max_abs_physical_ledger_defect_mw": round(max_ledger_defect, 9),
        "d4_balance_defect_mw_distribution": _distribution(d4_values),
        "served_demand_mwh": round(
            sum(float(tick.p_served_mw or 0.0) for tick in ticks)
            * TICK_SECONDS
            / 3600.0,
            9,
        ),
        "unserved_demand_mwh": round(
            sum(max(0.0, float(tick.p_unserved_mw or 0.0)) for tick in ticks)
            * TICK_SECONDS
            / 3600.0,
            9,
        ),
        "dispatch_curtailment_mwh": round(dispatch_curtailment_mwh, 9),
        "dispatch_curtailment_mw_distribution": _distribution(
            [value for value in curtailment_values if value > 1e-9]
        ),
    }
    proposal_summary = metrics.get("proposal_summary", {"approved": 0, "vetoed": 0})
    return {
        "scenario_id": scenario_id,
        "mode": mode,
        "compute_description": "scheduler-shaped GPU workload demand",
        "trace_source": trace_source,
        "wall_clock_seconds": round(wall_seconds, 6),
        "tick_count": len(ticks),
        "interval_seconds": TICK_SECONDS,
        "turbine_fuel_mmbtu": metrics["turbine_fuel_mmbtu"],
        "fuel_by_component_mmbtu": metrics["fuel_by_component_mmbtu"],
        "preload_fuel_mmbtu": metrics["preload_fuel_mmbtu"],
        "dispatch_curtailment_mwh": round(dispatch_curtailment_mwh, 9),
        "dispatch_curtailment_fuel_by_component_mmbtu": metrics[
            "dispatch_curtailment_fuel_by_component_mmbtu"
        ],
        "dispatch_curtailment_fuel_mmbtu": round(
            sum(metrics["dispatch_curtailment_fuel_by_component_mmbtu"].values()),
            9,
        ),
        "fuel_by_unit_mmbtu": metrics["fuel_by_unit_mmbtu"],
        "starts": metrics["start_transitions"],
        "stops": metrics["stop_transitions"],
        "start_count": int(final.turbine_start_count),
        "synchronized_count_distribution_ticks": dict(
            sorted((str(k), int(v)) for k, v in sync_counts.items())
        ),
        "unit_minutes_below_50_percent": {
            key: round(value, 6) for key, value in sorted(low_load_minutes.items())
        },
        "energy_balance": balance,
        "bess_soc_min": round(min(float(t.bess_soc_fraction) for t in ticks), 9),
        "bess_soc_max": round(max(float(t.bess_soc_fraction) for t in ticks), 9),
        "bess_soc_final": round(float(final.bess_soc_fraction), 9),
        "unserved_mwh": round(
            sum(max(0.0, float(t.p_unserved_mw or 0.0)) for t in ticks)
            * TICK_SECONDS
            / 3600.0,
            9,
        ),
        "peak_unserved_mw": round(
            max((float(t.p_unserved_mw or 0.0) for t in ticks), default=0.0), 9
        ),
        "unserved_intervals": metrics["unserved_intervals"],
        "unserved_by_cluster": _cluster_unserved(ticks, days=days),
        "hard_violations": sorted(hard_violations),
        "forecast_misses": metrics["forecast_misses"],
        "core_proposals": proposal_summary,
        "commitment_log": _compact_commitment_log(controller),
        "commitment_log_record_count": len(logs),
        "preload_outcomes": metrics.get("preload_reach", []),
        "preload_actions": preload_actions,
        "fuel_guard": fuel_guard,
        "forecast_quality": _forecast_quality(controller, ticks),
        "stop_floor_refusals": list(
            getattr(controller, "stop_floor_refusals", [])
        ),
        "constraints_valid": bool(
            getattr(controller, "constraints_valid", True)
        ),
        "start_count_reconciled": bool(
            metrics.get("start_count_reconciled", True)
        ),
        "kube_power_reactive_ticks": sum(
            1
            for tick in ticks
            if tick.kube_metrics is not None
            and bool(tick.kube_metrics.power_cap_active)
        ),
        "kube_requeued_admissions": sum(
            int(tick.kube_metrics.requeued_this_tick)
            for tick in ticks
            if tick.kube_metrics is not None
        ),
    }


def _write_tick_artifact(path: Path, ticks: list[Any]) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for tick in ticks:
            row = _tick_result_to_dict(tick)
            keep = {
                key: row.get(key)
                for key in (
                    "tick_index",
                    "sim_time_seconds",
                    "p_compute_mw",
                    "p_cooling_mw",
                    "p_total_mw",
                    "p_generation_mw",
                    "p_served_mw",
                    "p_unserved_mw",
                    "p_imbalance_mw",
                    "p_dispatch_curtailed_mw",
                    "turbine_output_mw",
                    "bess_output_mw",
                    "bess_soc_fraction",
                    "turbine_fuel_telemetry",
                    "turbine_units",
                    "kube_metrics",
                    "commitment_block",
                )
            }
            handle.write(json.dumps(keep, separators=(",", ":")) + "\n")


def _assert_replay_equal(
    baseline_ticks: list[Any],
    informed_ticks: list[Any],
) -> tuple[bool, float]:
    if len(baseline_ticks) != len(informed_ticks):
        return False, float("inf")
    max_diff = max(
        (
            abs(
                float(base.p_compute_demand_mw)
                - float(informed.p_compute_demand_mw)
            )
            for base, informed in zip(baseline_ticks, informed_ticks)
        ),
        default=0.0,
    )
    return max_diff <= 1e-9, max_diff


def _phase2b_acceptance_verdict(
    *,
    summary: dict[str, Any],
    baseline: dict[str, Any],
    informed: dict[str, Any],
    trace_equal: bool,
) -> dict[str, Any]:
    """Apply the stage-1 gates, including the Phase 2a comparison gate."""
    comparison = unserved_comparison_verdict(
        {
            "unserved_energy_mwh": baseline["unserved_mwh"],
            "peak_unserved_mw": baseline["peak_unserved_mw"],
        },
        {
            "unserved_energy_mwh": informed["unserved_mwh"],
            "peak_unserved_mw": informed["peak_unserved_mw"],
        },
    )
    gates = {
        "identical_compute_trace": trace_equal,
        "physical_ledger_closure": bool(
            summary["energy_balance"]["closure_status"]
        ),
        "no_hard_violations": not summary["hard_violations"],
        "start_count_reconciled": summary["start_count_reconciled"],
        "constraints_valid": summary["constraints_valid"],
        "informed_unserved_energy_no_worse": comparison[
            "unserved_energy_no_worse"
        ],
        "informed_peak_unserved_no_worse": comparison[
            "peak_unserved_no_worse"
        ],
    }
    return {
        "informed_vs_baseline": comparison,
        "acceptance_gates": gates,
        "acceptance_verdict": "PASS" if all(gates.values()) else "FAIL",
    }


def run_scenario(scenario_id: str, output_dir: Path) -> dict[str, Any]:
    compact = _load_compact_spec(scenario_id)
    expanded = expand_phase2b_reference_spec(compact)
    days = int(compact["phase2b_reference_days"])

    # Probe the restored background path once in baseline mode.  This is the
    # demand trace that both final controller modes replay.
    probe_ctx, probe_ticks, probe_wall = _run_context(
        expanded,
        run_id=f"{scenario_id}-background-probe",
        mode="baseline",
        capture_trace=True,
    )
    replay_events = [_signal_dict(signal) for signal in probe_ctx.sim_state.workload_signal_trace]
    if not replay_events:
        raise AssertionError(f"{scenario_id}: background probe emitted no workload signals")
    demand_replay = [
        (
            float(tick.p_compute_demand_mw),
            float(tick.p_cooling_demand_mw),
        )
        for tick in probe_ticks
    ]
    replay_spec = copy.deepcopy(expanded)
    replay_spec["workload_events"] = []

    runs: dict[str, dict[str, Any]] = {}
    tick_sets: dict[str, list[Any]] = {}
    for mode in ("baseline", "informed"):
        ctx, ticks, wall = _run_context(
            replay_spec,
            run_id=f"{scenario_id}-{mode}",
            mode=mode,
            replay_events=[],
            demand_replay=demand_replay,
        )
        tick_sets[mode] = ticks
        summary = _run_summary(
            scenario_id=scenario_id,
            mode=mode,
            ctx=ctx,
            ticks=ticks,
            wall_seconds=wall,
            days=days,
            trace_source="baseline live background trace replay",
        )
        summary["background_probe_wall_clock_seconds"] = round(probe_wall, 6)
        summary["background_trace_signal_count"] = len(replay_events)
        summary["demand_replay_tick_count"] = len(demand_replay)
        summary["replay_strategy"] = (
            "captured live workload-signal/demand trace; replayed per-tick "
            "compute and lagged cooling demand"
        )
        summary["background_power_reactive"] = any(
            tick.kube_metrics is not None
            and (
                tick.kube_metrics.power_cap_active
                or tick.kube_metrics.requeued_this_tick > 0
            )
            for tick in probe_ticks
        )
        tick_path = output_dir / f"{scenario_id}-{mode}_ticks.jsonl.gz"
        _write_tick_artifact(tick_path, ticks)
        summary["tick_artifact"] = tick_path.name
        runs[mode] = summary
        (output_dir / f"{scenario_id}-{mode}.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n"
        )
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
                    f"dispatch_curtailment_fuel_mmbtu: {summary['dispatch_curtailment_fuel_mmbtu']}",
                    f"energy_balance: {json.dumps(summary['energy_balance'], sort_keys=True)}",
                    f"starts: {json.dumps(summary['starts'], sort_keys=True)}",
                    f"stops: {json.dumps(summary['stops'], sort_keys=True)}",
                    f"hard_violations: {json.dumps(summary['hard_violations'])}",
                ]
            )
            + "\n"
        )

    trace_equal, max_diff = _assert_replay_equal(
        tick_sets["baseline"], tick_sets["informed"]
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
        (output_dir / f"{summary['scenario_id']}-{summary['mode']}.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n"
        )

    base_fuel = float(runs["baseline"]["turbine_fuel_mmbtu"])
    informed_fuel = float(runs["informed"]["turbine_fuel_mmbtu"])
    fuel_delta = informed_fuel - base_fuel
    avoided_curtailment_fuel = (
        runs["baseline"]["dispatch_curtailment_fuel_mmbtu"]
        - runs["informed"]["dispatch_curtailment_fuel_mmbtu"]
    )
    aggregate = {
        "scenario_id": scenario_id,
        "days": days,
        "background_power_reactive": runs["baseline"]["background_power_reactive"],
        "background_trace_signal_count": len(replay_events),
        "background_probe_wall_clock_seconds": round(probe_wall, 6),
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
            "informed_minus_baseline_mmbtu": fuel_delta,
            "percent_change_vs_baseline": (
                100.0 * fuel_delta / base_fuel if base_fuel else 0.0
            ),
            "avoided_curtailment_fuel_mmbtu": avoided_curtailment_fuel,
            "share_of_fuel_difference_attributable_to_avoided_curtailment": (
                avoided_curtailment_fuel / (base_fuel - informed_fuel)
                if base_fuel != informed_fuel
                else 0.0
            ),
            "component_delta_mmbtu": {
                component: runs["informed"]["fuel_by_component_mmbtu"].get(component, 0.0)
                - runs["baseline"]["fuel_by_component_mmbtu"].get(component, 0.0)
                for component in runs["baseline"]["fuel_by_component_mmbtu"]
            },
        },
        "runs": {
            mode: {
                key: run[key]
                for key in (
                    "scenario_id",
                    "mode",
                    "compute_description",
                    "tick_count",
                    "tick_artifact",
                    "identical_compute_trace",
                    "max_compute_trace_diff_mw",
                    "acceptance_verdict",
                     "acceptance_gates",
                     "informed_vs_baseline",
                    "energy_balance",
                    "start_count_reconciled",
                    "constraints_valid",
                    "unserved_mwh",
                    "peak_unserved_mw",
                    "turbine_fuel_mmbtu",
                    "dispatch_curtailment_mwh",
                    "hard_violations",
                    "core_proposals",
                    "forecast_misses",
                    "background_power_reactive",
                    "background_trace_signal_count",
                    "replay_strategy",
                     "fuel_guard",
                     "forecast_quality",
                     "stop_floor_refusals",
                )
            }
            for mode, run in runs.items()
        },
    }
    (output_dir / f"{scenario_id}-summary.json").write_text(
        json.dumps(aggregate, indent=2, sort_keys=True) + "\n"
    )
    return aggregate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = [
        run_scenario(scenario_id, args.output_dir)
        for scenario_id in REFERENCE_IDS
    ]
    manifest = {
        "stage": "2b-1",
        "compute_description": "scheduler-shaped GPU workload demand",
        "scenarios": results,
    }
    (args.output_dir / "stage1_summary.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    (args.output_dir / "stage1_summary.txt").write_text(
        "\n".join(
            [
                "Addendum H Phase 2b-1",
                "====================",
                "Runs: H-1 and H-2 24-hour reference scenarios, baseline and informed.",
                "Demand approach: one baseline live background trace, replayed exactly in both modes.",
                *[
                    (
                        f"{item['scenario_id']}: {item['acceptance_verdict']}; "
                        f"trace_diff={item['max_compute_trace_diff_mw']:.12g} MW; "
                        f"fuel_delta={item['fuel_attribution']['informed_minus_baseline_mmbtu']:.6f} MMBtu"
                    )
                    for item in results
                ],
            ]
        )
        + "\n"
    )
    return 0 if all(item["acceptance_verdict"] == "PASS" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())