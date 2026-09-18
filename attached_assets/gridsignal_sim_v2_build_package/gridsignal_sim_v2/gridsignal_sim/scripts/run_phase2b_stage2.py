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


def _write_json_bounded(path: Path, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if len(encoded.encode("utf-8")) >= MAX_JSON_BYTES:
        raise AssertionError(
            f"{path.name} would be {len(encoded.encode('utf-8'))} bytes; "
            f"Stage 2b-2 JSON must remain under {MAX_JSON_BYTES} bytes"
        )
    path.write_text(encoded)


def _write_probe(
    output_dir: Path,
    scenario_id: str,
    *,
    probe_ctx: Any,
    probe_ticks: list[Any],
    probe_wall: float,
) -> None:
    demand_replay = [
        (
            float(tick.p_compute_demand_mw),
            float(tick.p_cooling_demand_mw),
        )
        for tick in probe_ticks
    ]
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
        "background_power_reactive": any(
            tick.kube_metrics is not None
            and (
                tick.kube_metrics.power_cap_active
                or tick.kube_metrics.requeued_this_tick > 0
            )
            for tick in probe_ticks
        ),
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
    probe_ctx, probe_ticks, probe_wall = _run_context(
        expanded,
        run_id=f"{scenario_id}-background-probe",
        mode="baseline",
        capture_trace=True,
    )
    _write_probe(
        output_dir,
        scenario_id,
        probe_ctx=probe_ctx,
        probe_ticks=probe_ticks,
        probe_wall=probe_wall,
    )
    print(
        f"{scenario_id}: probe complete; ticks={len(probe_ticks)}; "
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


def _assert_run_fuel_nonzero(ctx: Any, ticks: list[Any], scenario_id: str) -> None:
    _assert_all_aero_fuel_model(ctx, scenario_id)
    synchronized_seen = any(
        any(
            bool(unit.get("breaker_closed"))
            and str(unit.get("state", "")).lower()
            in {"synchronised", "synchronized", "unloading"}
            for unit in tick.turbine_units
        )
        for tick in ticks
    )
    final_rows = {
        str(row.get("asset_id")): row
        for row in (ticks[-1].turbine_fuel_telemetry if ticks else ())
    }
    total_fuel = sum(
        float(row.get("total_fuel_mmbtu", 0.0) or 0.0)
        for row in final_rows.values()
    )
    if synchronized_seen and total_fuel <= 1e-12:
        raise AssertionError(
            f"{scenario_id}: synchronized turbines reported zero total fuel"
        )


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
    ctx, ticks, wall = _run_context(
        replay_spec,
        run_id=f"{scenario_id}-{mode}",
        mode=mode,
        replay_events=probe["replay_events"],
        demand_replay=[
            tuple(values) for values in probe["demand_replay"]
        ],
    )
    _assert_run_fuel_nonzero(ctx, ticks, f"{scenario_id}-{mode}")
    summary = _run_summary(
        scenario_id=scenario_id,
        mode=mode,
        ctx=ctx,
        ticks=ticks,
        wall_seconds=wall,
        days=SEVEN_DAYS,
        trace_source="baseline live background trace replay",
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
    summary["daily_breakdown"] = _daily_breakdown(
        ticks,
        starts=summary["starts"],
        stops=summary["stops"],
    )
    tick_path = _tick_path(output_dir, scenario_id, mode)
    _write_tick_artifact(tick_path, ticks)
    summary["tick_artifact"] = tick_path.name
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