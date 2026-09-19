"""Run or replay the S1 study harness.

Examples:
    python scripts/run_study_harness_s1.py --validate-committed
    python scripts/run_study_harness_s1.py --run scenario-h1-k8s-ray-24h
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from study_harness.executor import (  # noqa: E402
    StudyRunExecutor,
    validate_committed_artifact,
)


RESULTS_ROOT = PACKAGE_ROOT.parents[3] / "docs" / "addendum-h-phase2b-results"
COMMITTED_RUNS = (
    ("scenario-h1-k8s-ray-7d", "baseline"),
    ("scenario-h1-k8s-ray-7d", "informed"),
    ("scenario-h2-slurm-7d", "baseline"),
    ("scenario-h2-slurm-7d", "informed"),
)


def _paths(scenario_id: str, mode: str) -> tuple[Path, Path]:
    stem = RESULTS_ROOT / f"{scenario_id}-{mode}"
    return stem.with_suffix(".json"), Path(str(stem) + "_ticks.jsonl.gz")


def _assertions(result: dict[str, Any]) -> list[dict[str, Any]]:
    if result["status"] == "FAIL":
        return [
            {
                "name": failure["type"],
                "status": "FAIL",
                "message": failure["message"],
            }
            for failure in result["guards_fired"]
        ]
    metrics = result["metrics"]
    return [
        {
            "name": "fuel_component_reconciliation",
            "status": "PASS" if metrics["fuel_reconciled"] else "FAIL",
        },
        {
            "name": "start_fuel_tier_reconciliation",
            "status": (
                "PASS"
                if metrics["start_fuel_reconciliation"]["passed"]
                else "FAIL"
            ),
        },
        {
            "name": "curtailment_measures_range_checked",
            "status": "PASS",
            "interval_exposure_fuel_mmbtu": metrics[
                "dispatch_curtailment_interval_exposure_fuel_mmbtu"
            ],
            "attributable_fuel_mmbtu": metrics[
                "dispatch_curtailment_attributable_fuel_mmbtu"
            ],
        },
        {
            "name": "run_local_unserved_energy",
            "status": "PASS",
            "unserved_mwh": metrics["unserved_mwh"],
        },
        {
            "name": "deduplicated_commitment_counts",
            "status": "PASS",
            "distinct_event_count": metrics["commitment"][
                "distinct_event_count"
            ],
            "suppressed_repeat_count": metrics["commitment"][
                "suppressed_repeat_count"
            ],
        },
        {
            "name": "same_unit_restart_window_count",
            "status": "PASS",
            "count": metrics["commitment"][
                "same_unit_restart_within_min_down_window_count"
            ],
        },
        {
            "name": "forecast_miss_accounting",
            "status": "PASS",
            "count": metrics["forecast"]["miss_count"],
        },
    ]


def validate_committed() -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    for scenario_id, mode in COMMITTED_RUNS:
        record_path, tick_path = _paths(scenario_id, mode)
        result = validate_committed_artifact(
            record_path=record_path,
            tick_path=tick_path,
        )
        run = {
            "scenario_id": scenario_id,
            "mode": mode,
            "status": result["status"],
            "assertions": _assertions(result),
            "guards_fired": result["guards_fired"],
        }
        if result["metrics"] is not None:
            run["metrics"] = {
                "tick_count": result["metrics"]["tick_count"],
                "turbine_fuel_mmbtu": result["metrics"][
                    "turbine_fuel_mmbtu"
                ],
                "unserved_mwh": result["metrics"]["unserved_mwh"],
                "dispatch_curtailment_mwh": result["metrics"][
                    "dispatch_curtailment_mwh"
                ],
            }
        runs.append(run)
    return {
        "study": "GS-DES-SSH-001 S1",
        "simulation": "replay only; no simulation was performed",
        "runs": runs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-committed", action="store_true")
    parser.add_argument("--run", dest="scenario_id")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.validate_committed:
        result = validate_committed()
    elif args.scenario_id:
        result = StudyRunExecutor(
            output_dir=Path("study-harness-output")
        ).run_pair(scenario_id=args.scenario_id)
    else:
        parser.error("choose --validate-committed or --run")
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded)
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())