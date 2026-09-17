"""Run and persist the Addendum H Phase 2a acceptance smoke comparison.

The smoke is intentionally headless.  Kubernetes and Slurm services are
removed from both modes because their wall-clock scheduling is stochastic and
would make the controller comparison non-reproducible.  Scripted workload
events, turbine physics, BESS physics, and the 5-second integration remain
active.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
import gzip
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from runtime.run_manager import _tick_result_to_dict
from runtime.scenario_factory import build_run_context_from_spec
from runtime.turbine_commitment import (
    summarize_unserved_ticks,
    unserved_comparison_verdict,
)


DEFAULT_SOURCE = PACKAGE_ROOT / "config/scenarios/scenario-uneven-multisched-01.json"
DEFAULT_OUTPUT = PACKAGE_ROOT / "test-results/addendum_h_phase2a"
TICK_SECONDS = 5.0
TICK_COUNT = 1440


def _mode_spec(base: dict[str, Any], mode: str) -> dict[str, Any]:
    spec = copy.deepcopy(base)
    # DR-2026-09-17-BASELINE: both modes use the same physical topology.
    spinning = 2
    spec["end_sim_time"] = TICK_COUNT * TICK_SECONDS
    spec["initial_spinning_count"] = spinning
    spec.pop("kube_clusters", None)
    spec.pop("slurm_config", None)
    for index, turbine in enumerate(spec["turbine_units"]):
        turbine.update(
            {
                "gt_mode": "aero",
                "min_run_enabled": True,
                "min_down_enabled": True,
                "hot_standby": index >= spinning,
                "initial_state": "offline" if index >= spinning else "spinning",
            }
        )
    spec["island_mode"] = True
    spec["turbine_commitment_mode"] = mode
    return spec


def _prior_baseline_spec(base: dict[str, Any]) -> dict[str, Any]:
    """Recreate the earlier baseline that produced ten starts."""
    spec = copy.deepcopy(base)
    spec["end_sim_time"] = TICK_COUNT * TICK_SECONDS
    spec["initial_spinning_count"] = 3
    spec.pop("kube_clusters", None)
    spec.pop("slurm_config", None)
    for index, turbine in enumerate(spec["turbine_units"]):
        turbine.update(
            {
                "gt_mode": "aero",
                "min_run_enabled": False,
                "min_down_enabled": False,
                "hot_standby": index == 3,
                "initial_state": "offline" if index == 3 else "spinning",
            }
        )
    spec["turbine_commitment_mode"] = "baseline"
    return spec


def _start_explanation(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    explanation: list[dict[str, Any]] = []
    for record in logs:
        if (
            record.get("accepted")
            and record.get("changed_state")
            and record.get("action") in {"start", "release"}
        ):
            source = str(record.get("source", "unknown"))
            if source in {"forecast_commitment", "core_commitment"}:
                path = "forecast controller"
            elif source in {"automatic_contingency", "automatic_cascade"}:
                path = "automatic/cascade"
            elif source == "operator":
                path = "operator"
            else:
                path = f"other production path ({source})"
            explanation.append(
                {
                    "sim_time_s": record.get("sim_time_s"),
                    "unit_id": record.get("unit_id"),
                    "action": record.get("action"),
                    "source": source,
                    "path": path,
                    "reason": record.get("reason", ""),
                }
            )
    return explanation


def _extended_metrics(
    ticks: list[Any],
    controller: Any,
    logs: list[dict[str, Any]],
    preload_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build compact, auditable attribution metrics from the completed run."""
    fuel_by_component = Counter()
    fuel_by_unit = defaultdict(Counter)
    dispatch_fuel_by_component = Counter()
    dispatch_fuel_by_unit = defaultdict(float)
    below_threshold_minutes: dict[str, float] = {}
    for tick in ticks:
        dispatch_active = float(tick.p_dispatch_curtailed_mw or 0.0) > 1e-9
        for row in tick.turbine_fuel_telemetry:
            unit_id = str(row.get("asset_id", "unknown"))
            for component in (
                "load_fuel_mmbtu",
                "no_load_fuel_mmbtu",
                "hot_standby_fuel_mmbtu",
                "start_fuel_mmbtu",
            ):
                value = float(row.get(component, 0.0) or 0.0)
                fuel_by_component[component] += value
                fuel_by_unit[unit_id][component] += value
                if dispatch_active:
                    dispatch_fuel_by_component[component] += value
                    dispatch_fuel_by_unit[unit_id] += value
            # This field is cumulative per unit, so the final row is the
            # authoritative unit-minute total rather than a value to sum per tick.
            below_threshold_minutes[unit_id] = float(
                row.get("minutes_below_low_load_threshold", 0.0) or 0.0
            )

    sync_counts = [
        sum(1 for unit in tick.turbine_units
            if str(unit.get("state", "")).lower()
            in {"synchronised", "synchronized", "unloading"})
        for tick in ticks
    ]
    sync_distribution = {
        str(count): sync_counts.count(count)
        for count in sorted(set(sync_counts))
    }

    start_actions = [
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
    stop_actions = [
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

    preload_reach: list[dict[str, Any]] = []
    for action in preload_actions:
        burst_time = float(action.get("burst_sim_time_s", 0.0))
        onset_tick = next(
            (tick for tick in ticks if tick.sim_time_seconds >= burst_time),
            None,
        )
        actual_output = (
            float(onset_tick.turbine_output_mw) if onset_tick is not None else None
        )
        target = float(action.get("target_mw", 0.0))
        preload_reach.append(
            {
                "burst_sim_time_s": burst_time,
                "action_sim_time_s": action.get("sim_time_s"),
                "target_mw": target,
                "actual_turbine_output_mw_at_onset": actual_output,
                "reached": (
                    actual_output is not None
                    and actual_output + 1e-6 >= target
                ),
            }
        )

    return {
        "fuel_by_component_mmbtu": {
            component: round(value, 6)
            for component, value in sorted(fuel_by_component.items())
        },
        "fuel_by_unit_mmbtu": {
            unit_id: {
                component: round(value, 6)
                for component, value in sorted(components.items())
            }
            for unit_id, components in sorted(fuel_by_unit.items())
        },
        "dispatch_curtailment_fuel_by_component_mmbtu": {
            component: round(value, 6)
            for component, value in sorted(dispatch_fuel_by_component.items())
        },
        "dispatch_curtailment_fuel_by_unit_mmbtu": {
            unit_id: round(value, 6)
            for unit_id, value in sorted(dispatch_fuel_by_unit.items())
        },
        "preload_fuel_mmbtu": round(float(controller.preload_fuel_mmbtu), 6),
        "unit_minutes_below_50_percent": {
            unit_id: round(value, 6)
            for unit_id, value in sorted(below_threshold_minutes.items())
        },
        "start_transitions": start_actions,
        "stop_transitions": stop_actions,
        "synchronized_count_distribution_ticks": sync_distribution,
        "unserved_intervals": list(controller.unserved_intervals),
        "forecast_misses": {
            "count": int(controller.forecast_miss_count),
            "peak_mw": round(float(controller.forecast_miss_peak_mw), 6),
        },
        "core_proposals": proposal_summary,
        "preload_targets_at_burst_onset": preload_reach,
    }


def run_smoke(source: Path, output_dir: Path) -> dict[str, Any]:
    base = json.loads(source.read_text())
    runs: dict[str, dict[str, Any]] = {}
    for mode in ("baseline", "informed"):
        spec = _mode_spec(base, mode)
        wall_start = time.perf_counter()
        ctx = build_run_context_from_spec(
            f"phase2a-smoke-{mode}", spec, playback_speed=0.0
        )
        ticks = []
        synchronized_counts = []
        for _ in range(TICK_COUNT):
            ticks.append(ctx.step())
            synchronized_counts.append(
                sum(1 for turbine in ctx.sim_state.turbines if turbine.is_on_bus)
            )
        wall_elapsed = time.perf_counter() - wall_start
        controller = ctx.turbine_commitment_controller
        tick_dicts = [_tick_result_to_dict(tick) for tick in ticks]
        summary = summarize_unserved_ticks(ticks, dt_seconds=TICK_SECONDS)
        violations = list(controller.constraint_violation_reasons)
        anchor_violations = [
            reason for reason in violations if "bess_anchor_reserve_power" in reason
        ]
        actual_starts = {
            turbine.config.asset_id: int(getattr(turbine, "_start_count", 0))
            for turbine in ctx.sim_state.turbines
        }
        logged_starts = dict(controller.start_counts)
        dt_hours = TICK_SECONDS / 3600.0
        energy_balance = {
            "turbine_generation_mwh": round(
                sum(max(0.0, float(tick.turbine_output_mw)) for tick in ticks)
                * dt_hours,
                6,
            ),
            "bess_discharge_mwh": round(
                sum(max(0.0, float(tick.bess_output_mw)) for tick in ticks)
                * dt_hours,
                6,
            ),
            "bess_charge_mwh": round(
                sum(max(0.0, -float(tick.bess_output_mw)) for tick in ticks)
                * dt_hours,
                6,
            ),
            "served_demand_mwh": round(
                sum(max(0.0, float(tick.p_served_mw or 0.0)) for tick in ticks)
                * dt_hours,
                6,
            ),
            "unserved_demand_mwh": round(
                sum(max(0.0, float(tick.p_unserved_mw or 0.0)) for tick in ticks)
                * dt_hours,
                6,
            ),
            "surplus_mwh": round(
                sum(
                    max(
                        0.0,
                        float(tick.p_imbalance_mw or 0.0),
                    )
                    for tick in ticks
                )
                * dt_hours,
                6,
            ),
            "curtailment_mwh": round(
                sum(max(0.0, float(tick.p_renewable_curtailed_mw or 0.0)) for tick in ticks)
                * dt_hours,
                6,
            ),
            "dispatch_curtailment_mwh": round(
                sum(
                    max(0.0, float(tick.p_dispatch_curtailed_mw or 0.0))
                    for tick in ticks
                )
                * dt_hours,
                6,
            ),
        }
        energy_balance["closure_status"] = all(
            abs(
                float(tick.p_generation_mw)
                - float(tick.p_served_mw or 0.0)
                - float(tick.p_dispatch_curtailed_mw or 0.0)
            )
            <= 1e-3
            or abs(float(tick.p_imbalance_mw or 0.0)) <= 1e-3
            for tick in ticks
        )
        # Capture the authoritative per-tick state before the next run starts.
        # Tick payloads are not needed for the report, but the statistics are.
        synchronized_summary = {
            "min": min(synchronized_counts, default=0),
            "max": max(synchronized_counts, default=0),
            "mean": round(
                sum(synchronized_counts) / len(synchronized_counts), 6
                if synchronized_counts else 0.0,
            ),
            "ticks_at_or_above_initial": sum(
                count >= spec["initial_spinning_count"]
                for count in synchronized_counts
            ),
            "ticks_below_floor": sum(
                count < 1 for count in synchronized_counts
            ),
        }
        summary.update(
            {
                "mode": mode,
                "duration_seconds": TICK_COUNT * TICK_SECONDS,
                "wall_clock_duration_seconds": round(wall_elapsed, 6),
                "tick_seconds": TICK_SECONDS,
                "tick_count": len(ticks),
                "initial_spinning_count": spec["initial_spinning_count"],
                "hot_standby_count": sum(
                    1 for turbine in spec["turbine_units"] if turbine["hot_standby"]
                ),
                "island_mode": spec["island_mode"],
                "turbine_min_run_enabled": all(
                    turbine["min_run_enabled"] for turbine in spec["turbine_units"]
                ),
                "turbine_min_down_enabled": all(
                    turbine["min_down_enabled"] for turbine in spec["turbine_units"]
                ),
                "turbine_gt_modes": sorted(
                    {str(turbine.get("gt_mode", "")) for turbine in spec["turbine_units"]}
                ),
                "headless_services_removed": ["kube_clusters", "slurm_config"],
                "turbine_fuel_mmbtu": ticks[-1].turbine_total_fuel_mmbtu,
                "turbine_start_count": ticks[-1].turbine_start_count,
                "actual_start_counts": actual_starts,
                "logged_start_counts": logged_starts,
                "start_count_reconciled": actual_starts
                == {
                    unit_id: logged_starts.get(unit_id, 0)
                    for unit_id in actual_starts
                },
                "commitment_log_count": len(controller.log),
                "refusal_log_count": sum(
                    not record.accepted for record in controller.log
                ),
                "preload_action_count": len(controller.preload_actions),
                "preload_fuel_mmbtu": controller.preload_fuel_mmbtu,
                "forecast_miss_count": controller.forecast_miss_count,
                "forecast_miss_peak_mw": controller.forecast_miss_peak_mw,
                "constraints_valid": controller.constraints_valid,
                "hard_violation_reasons": violations,
                "bess_anchor_violations": anchor_violations,
                "energy_balance": energy_balance,
                "synchronized_count_statistics": synchronized_summary,
                "suppressed_refusal_repeat_count": controller.suppressed_refusal_count,
            }
        )
        logs = [record.as_dict() for record in controller.log]
        extended_metrics = _extended_metrics(
            ticks, controller, logs, list(controller.preload_actions)
        )
        runs[mode] = {
            "summary": summary,
            "extended_metrics": extended_metrics,
            "start_explanation": _start_explanation(logs),
            "commitment_logs": logs,
            "preload_actions": list(controller.preload_actions),
            "ticks": tick_dicts,
        }

    comparison = unserved_comparison_verdict(
        runs["baseline"]["summary"], runs["informed"]["summary"]
    )
    comparison["no_bess_anchor_violations"] = not any(
        runs[mode]["summary"]["bess_anchor_violations"]
        for mode in ("baseline", "informed")
    )
    comparison["acceptance_verdict"] = (
        "PASS"
        if comparison["verdict"] == "PASS"
        and comparison["no_bess_anchor_violations"]
        and all(
            runs[mode]["summary"]["constraints_valid"]
            and runs[mode]["summary"]["start_count_reconciled"]
            for mode in ("baseline", "informed")
        )
        else "FAIL"
    )
    prior_ctx = build_run_context_from_spec(
        "phase2a-prior-baseline-reference",
        _prior_baseline_spec(base),
        playback_speed=0.0,
    )
    prior_ticks = [prior_ctx.step() for _ in range(TICK_COUNT)]
    prior_controller = prior_ctx.turbine_commitment_controller
    prior_logs = [record.as_dict() for record in prior_controller.log]
    prior_reference = {
        "reason": (
            "The prior baseline disabled minimum run and down time, so the "
            "controller repeatedly stopped and restarted the same units."
        ),
        "start_count": prior_ticks[-1].turbine_start_count,
        "start_explanation": _start_explanation(prior_logs),
        "commitment_logs": prior_logs,
        "unserved": summarize_unserved_ticks(
            prior_ticks, dt_seconds=TICK_SECONDS
        ),
    }
    report = {
        "report": "DR-2026-09-17-ACCEPTANCE",
        "preload_report": "DR-2026-09-17-PRELOAD",
        "baseline_policy": (
            "Measured core commitment only; no forecast input, forecast-controller "
            "commit/decommit/preload actions, or minimum synchronized floor."
        ),
        "fixture_source": str(source),
        "fixture_note": (
            "Headless deterministic comparison: kube_clusters and slurm_config "
            "are removed identically from both modes; scripted workload events "
            "remain unchanged."
        ),
        "comparison": comparison,
        "runs": runs,
        "prior_baseline_reference": prior_reference,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    # Keep the JSON report reviewable and below the acceptance size limit.  Full
    # per-tick evidence is retained in compact gzip JSONL artifacts; the report
    # contains the mode summaries, controller logs, and the artifact names.
    persisted_report = copy.deepcopy(report)
    for mode in ("baseline", "informed"):
        tick_path = output_dir / f"{mode}_ticks.jsonl.gz"
        with gzip.open(tick_path, "wt", encoding="utf-8") as handle:
            for tick in runs[mode]["ticks"]:
                handle.write(json.dumps({
                    "tick_index": tick["tick_index"],
                    "sim_time_seconds": tick["sim_time_seconds"],
                    "p_demand_mw": tick["p_demand_mw"],
                    "p_generation_mw": tick["p_generation_mw"],
                    "p_served_mw": tick["p_served_mw"],
                    "p_unserved_mw": tick["p_unserved_mw"],
                    "p_imbalance_mw": tick["p_imbalance_mw"],
                    "p_dispatch_curtailed_mw": tick["p_dispatch_curtailed_mw"],
                    "turbine_output_mw": tick["turbine_output_mw"],
                    "bess_output_mw": tick["bess_output_mw"],
                    "units_on_bus_count": tick["units_on_bus_count"],
                }, separators=(",", ":")) + "\n")
        persisted_report["runs"][mode].pop("ticks", None)
        persisted_report["runs"][mode]["tick_artifact"] = tick_path.name
    persisted_report["prior_baseline_reference"].pop("commitment_logs", None)
    (output_dir / "smoke_results.json").write_text(
        json.dumps(persisted_report, indent=2, sort_keys=True) + "\n"
    )
    for mode in ("baseline", "informed"):
        (output_dir / f"{mode}_commitment.log").write_text(
            "\n".join(
                json.dumps(record, sort_keys=True)
                for record in runs[mode]["commitment_logs"]
            )
            + "\n"
        )
    stale_prior_log = output_dir / "prior_baseline_commitment.log"
    if stale_prior_log.exists():
        stale_prior_log.unlink()
    summary_lines = [
        "Addendum H Phase 2a smoke summary",
        "=================================",
        f"Acceptance verdict: {comparison['acceptance_verdict']}",
        f"Energy no worse: {comparison['unserved_energy_no_worse']}",
        f"Peak power no worse: {comparison['peak_unserved_no_worse']}",
        f"No BESS anchor violations: {comparison['no_bess_anchor_violations']}",
        "Per-tick evidence is stored as baseline_ticks.jsonl.gz and informed_ticks.jsonl.gz.",
        "Wall-clock duration is recorded per mode in smoke_results.json.",
        "",
        "mode      unserved MWh   peak unserved MW   fuel MMBtu   starts   refusals   preloads   hard violations",
    ]
    for mode in ("baseline", "informed"):
        item = runs[mode]["summary"]
        summary_lines.append(
            f"{mode:<9} {item['unserved_energy_mwh']:>13.6f}"
            f" {item['peak_unserved_mw']:>17.6f}"
            f" {float(item['turbine_fuel_mmbtu'] or 0.0):>12.6f}"
            f" {item['turbine_start_count']:>8}"
            f" {item['refusal_log_count']:>10}"
            f" {item['preload_action_count']:>10}"
            f" {len(item['hard_violation_reasons']):>16}"
        )
        summary_lines.append(
            "  energy balance: " + json.dumps(item["energy_balance"], sort_keys=True)
        )
        summary_lines.append(
            "  synchronized-count statistics: "
            + json.dumps(item["synchronized_count_statistics"], sort_keys=True)
        )
        summary_lines.append(
            f"  suppressed refusal repeats: {item['suppressed_refusal_repeat_count']}"
        )
        summary_lines.append(
            f"  wall-clock seconds: {item['wall_clock_duration_seconds']:.6f}"
        )
        summary_lines.append(f"  start explanation: {json.dumps(runs[mode]['start_explanation'])}")
    summary_lines.extend(
        [
            "",
            "Prior baseline (reference only; minimum run/down disabled):",
            json.dumps(prior_reference["start_explanation"]),
        ]
    )
    summary_lines.extend(
        [
            "",
            "Informed minus baseline fuel MMBtu: "
            f"{(float(runs['informed']['summary']['turbine_fuel_mmbtu'] or 0.0) - float(runs['baseline']['summary']['turbine_fuel_mmbtu'] or 0.0)):.6f}",
            "Informed preload fuel MMBtu: "
            f"{float(runs['informed']['summary']['preload_fuel_mmbtu']):.6f}",
        ]
    )
    (output_dir / "smoke_summary.txt").write_text("\n".join(summary_lines) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = run_smoke(args.source, args.output_dir)
    print(
        json.dumps(
            {
                "acceptance_verdict": report["comparison"]["acceptance_verdict"],
                "output_dir": str(args.output_dir),
                "summary": str(args.output_dir / "smoke_summary.txt"),
                "results": str(args.output_dir / "smoke_results.json"),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()