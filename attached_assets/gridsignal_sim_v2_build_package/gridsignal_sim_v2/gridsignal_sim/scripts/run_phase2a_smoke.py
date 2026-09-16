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
    spinning = 3 if mode == "baseline" else 2
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
            if source == "forecast_commitment":
                path = "forecast controller"
            elif source == "automatic_contingency":
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


def run_smoke(source: Path, output_dir: Path) -> dict[str, Any]:
    base = json.loads(source.read_text())
    runs: dict[str, dict[str, Any]] = {}
    for mode in ("baseline", "informed"):
        spec = _mode_spec(base, mode)
        ctx = build_run_context_from_spec(
            f"phase2a-smoke-{mode}", spec, playback_speed=0.0
        )
        ticks = [ctx.step() for _ in range(TICK_COUNT)]
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
        summary.update(
            {
                "mode": mode,
                "duration_seconds": TICK_COUNT * TICK_SECONDS,
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
            }
        )
        logs = [record.as_dict() for record in controller.log]
        runs[mode] = {
            "summary": summary,
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
        "report": "DR-2026-09-16-ACCEPTANCE",
        "preload_report": "DR-2026-09-16-PRELOAD",
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
    (output_dir / "smoke_results.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    for mode in ("baseline", "informed"):
        (output_dir / f"{mode}_commitment.log").write_text(
            "\n".join(
                json.dumps(record, sort_keys=True)
                for record in runs[mode]["commitment_logs"]
            )
            + "\n"
        )
    (output_dir / "prior_baseline_commitment.log").write_text(
        "\n".join(json.dumps(record, sort_keys=True) for record in prior_logs)
        + "\n"
    )
    summary_lines = [
        "Addendum H Phase 2a smoke summary",
        "=================================",
        f"Acceptance verdict: {comparison['acceptance_verdict']}",
        f"Energy no worse: {comparison['unserved_energy_no_worse']}",
        f"Peak power no worse: {comparison['peak_unserved_no_worse']}",
        f"No BESS anchor violations: {comparison['no_bess_anchor_violations']}",
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