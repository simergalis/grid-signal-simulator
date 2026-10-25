#!/usr/bin/env python3
"""Run the protected seed-42 study pairs and compare them to D6c evidence."""

from __future__ import annotations

import argparse
import hashlib
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


SUMMARY_MARKER = "large metric value represented by exact canonical SHA-256"


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def summarize_large_metric(value: object) -> dict:
    encoded = canonical_json_bytes(value)
    return {
        "__summary__": SUMMARY_MARKER,
        "canonical_json_sha256": hashlib.sha256(encoded).hexdigest(),
        "count": len(value) if isinstance(value, (list, dict)) else None,
        "serialized_bytes": len(encoded),
        "type": type(value).__name__,
    }


def comparable_metric_value(value: object, expected: object) -> object:
    if isinstance(expected, dict) and expected.get("__summary__") == SUMMARY_MARKER:
        return summarize_large_metric(value)
    return value


def write_progress(value: dict, output: Path) -> None:
    output.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        action="append",
        choices=SCENARIOS,
        help="Run only this protected scenario; may be provided more than once.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT,
        help="Progress JSON path (defaults to PROTECTED_STUDY_GATES_PROGRESS.json).",
    )
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    scenarios = tuple(args.scenario) if args.scenario else SCENARIOS

    sys.path.insert(0, str(PACKAGE))
    from study_harness.executor import StudyRunExecutor

    expected_data = json.loads(
        (ROOT / "tools/dr_isl/d6c/ACCEPTANCE_STUDY_GATES.json").read_text()
    )
    expected = {row["scenario_id"]: row for row in expected_data["scenarios"]}
    identity_diagnosis = json.loads(
        (ROOT / "tools/dr_isl/isl25/IDENTITY_DIAGNOSIS.json").read_text()
    )
    normalized_payloads = {
        (row["scenario_id"], row["mode"]): row["payload_before"]
        for row in identity_diagnosis["results"]
    }
    executor = StudyRunExecutor(output_dir=Path("/tmp/isl25-protected-study-runs"))
    progress: dict = {
        "seed": 42,
        "cache": "fresh temporary directory; no prior run can be reused",
        "reference": "tools/dr_isl/d6c/ACCEPTANCE_STUDY_GATES.json",
        "identity_reference": "IDENTITY_DIAGNOSIS.json payload_before with both commit fields normalized",
        "canonical_large_metric_encoding": {
            "sort_keys": True,
            "separators": [",", ":"],
            "ensure_ascii": False,
            "allow_nan": False,
        },
        "runs": [],
    }
    write_progress(progress, output)

    for scenario_id in scenarios:
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
            normalized_reference = normalized_payloads[(scenario_id, mode)]
            actual_identity = record.get("identity")
            normalized_actual = dict(actual_identity or {})
            normalized_actual["engine_commit"] = normalized_reference[
                "engine_commit"
            ]
            normalized_actual["harness_commit"] = normalized_reference[
                "harness_commit"
            ]
            actual_identity_bytes = canonical_json_bytes(normalized_actual)
            expected_identity_bytes = canonical_json_bytes(normalized_reference)
            normalized_identity_digest = hashlib.sha256(
                actual_identity_bytes
            ).hexdigest()
            identity_matches = actual_identity_bytes == expected_identity_bytes
            if not identity_matches:
                scenario_result["failures"].append(
                    {
                        "gate": "normalized_identity_payload",
                        "mode": mode,
                        "expected_sha256": hashlib.sha256(
                            expected_identity_bytes
                        ).hexdigest(),
                        "actual_sha256": normalized_identity_digest,
                    }
                )
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
            expected_metrics = reference_arm["metrics_current"]
            actual_metrics = {
                field: comparable_metric_value(record.get(field), expected_value)
                for field, expected_value in expected_metrics.items()
            }
            metric_differences = {
                field: {
                    "expected": expected_value,
                    "actual": actual_metrics[field],
                }
                for field, expected_value in expected_metrics.items()
                if actual_metrics[field] != expected_value
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
                "raw_identity_digest": record.get("identity_digest"),
                "normalized_identity_sha256": normalized_identity_digest,
                "normalized_identity_matches_reference": identity_matches,
                "raw_commit_fields": {
                    "engine_commit": (actual_identity or {}).get("engine_commit"),
                    "harness_commit": (actual_identity or {}).get("harness_commit"),
                },
                "physical_identity_sha256": record.get(
                    "physical_identity_sha256"
                ),
                "metrics": actual_metrics,
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
        write_progress(progress, output)
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
    write_progress(progress, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
