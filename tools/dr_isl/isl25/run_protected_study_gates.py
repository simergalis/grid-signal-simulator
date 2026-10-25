#!/usr/bin/env python3
"""Run the protected seed-42 study pairs and compare them to D6c evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = (
    ROOT
    / "attached_assets"
    / "gridsignal_sim_v2_build_package"
    / "gridsignal_sim_v2"
    / "gridsignal_sim"
)
OUTPUT = ROOT / "tools/dr_isl/isl25/PROTECTED_STUDY_GATES_PROGRESS.json"
SCENARIOS = (
    "scenario-uneven-multisched-01",
    "scenario-h1-k8s-ray-24h",
    "scenario-h2-slurm-24h",
)


def write_progress(value: dict) -> None:
    OUTPUT.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def main() -> int:
    sys.path.insert(0, str(PACKAGE))
    from study_harness.executor import StudyRunExecutor, make_study_run_identity

    expected_data = json.loads(
        (ROOT / "tools/dr_isl/d6c/ACCEPTANCE_STUDY_GATES.json").read_text()
    )
    expected = {row["scenario_id"]: row for row in expected_data["scenarios"]}
    identities_data = json.loads(
        (ROOT / "tools/dr_isl/isl25/BASE_IDENTITIES_BEFORE.json").read_text()
    )
    identities = {
        (row["scenario_id"], row["mode"]): row
        for row in identities_data["runs"]
    }
    executor = StudyRunExecutor(output_dir=Path("/tmp/isl25-protected-study-runs"))
    progress: dict = {
        "seed": 42,
        "cache": "fresh temporary directory; no prior run can be reused",
        "reference": "tools/dr_isl/d6c/ACCEPTANCE_STUDY_GATES.json",
        "runs": [],
    }
    write_progress(progress)

    for scenario_id in SCENARIOS:
        pair = executor.run_pair(
            scenario_id=scenario_id,
            seed=42,
            allow_guard_failures=False,
        )
        scenario_result = {
            "scenario_id": scenario_id,
            "study_class": pair["study_class"],
            "arms": {},
            "comparison": pair["comparison"],
            "failures": [],
        }
        reference_scenario = expected[scenario_id]
        for mode in ("baseline", "informed"):
            record = pair["runs"][mode]
            reference_arm = reference_scenario[mode]
            expected_identity = identities[(scenario_id, mode)]
            if record.get("physical_identity_sha256") != reference_arm[
                "physical_identity_sha256"
            ]:
                scenario_result["failures"].append(
                    {
                        "gate": "physical_identity_sha256",
                        "mode": mode,
                        "expected": reference_arm["physical_identity_sha256"],
                        "actual": record.get("physical_identity_sha256"),
                    }
                )
            if record.get("identity_digest") != expected_identity["identity_digest"]:
                scenario_result["failures"].append(
                    {
                        "gate": "identity_digest",
                        "mode": mode,
                        "expected": expected_identity["identity_digest"],
                        "actual": record.get("identity_digest"),
                    }
                )
            expected_metrics = reference_arm["metrics_current"]
            metric_differences = {
                field: {
                    "expected": expected_value,
                    "actual": record.get(field),
                }
                for field, expected_value in expected_metrics.items()
                if record.get(field) != expected_value
            }
            if metric_differences:
                scenario_result["failures"].append(
                    {
                        "gate": "d6c_metrics",
                        "mode": mode,
                        "differences": metric_differences,
                    }
                )
            scenario_result["arms"][mode] = {
                "identity_digest": record.get("identity_digest"),
                "physical_identity_sha256": record.get(
                    "physical_identity_sha256"
                ),
                "metrics": {
                    field: record.get(field)
                    for field in expected_metrics
                },
                "metric_differences": metric_differences,
                "status": record.get("status"),
                "tick_count": record.get("tick_count"),
            }

        conditions = pair["comparison"].get("conditions", {})
        condition_count = len(conditions) if isinstance(conditions, dict) else 0
        if condition_count != 10:
            scenario_result["failures"].append(
                {
                    "gate": "condition_count",
                    "expected": 10,
                    "actual": condition_count,
                }
            )
        if pair["comparison"].get("verdict") != "PASS":
            scenario_result["failures"].append(
                {
                    "gate": "compare_verdict",
                    "expected": "PASS",
                    "actual": pair["comparison"].get("verdict"),
                }
            )
        progress["runs"].append(scenario_result)
        progress["last_completed_scenario"] = scenario_id
        progress["status"] = (
            "STOP" if scenario_result["failures"] else "IN_PROGRESS"
        )
        write_progress(progress)
        print(
            scenario_id,
            "verdict=" + str(pair["comparison"].get("verdict")),
            "conditions=" + str(condition_count),
            "failures=" + str(len(scenario_result["failures"])),
            flush=True,
        )
        if scenario_result["failures"]:
            return 1

    progress["status"] = "PASS"
    write_progress(progress)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
