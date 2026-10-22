"""Evaluate durable protected-record evidence without starting simulations."""
import json
from pathlib import Path
import sys

D = Path(__file__).resolve().parent
ROOT = D.parents[2]
P = ROOT / "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim"
sys.path.insert(0, str(P))
from study_harness.acceptance import compare_metrics

PRODUCTION = {
    "baseline": dict(dispatch_curtailment_mwh=8.136511735,
                     turbine_fuel_mmbtu=714.363019086,
                     unserved_mwh=0.351692658, peak_unserved_mw=22.309362466),
    "informed": dict(dispatch_curtailment_mwh=5.278943188,
                     turbine_fuel_mmbtu=665.398247704,
                     unserved_mwh=0.020719074, peak_unserved_mw=7.523250570),
}
result = dict(checks=[], compare_runs={}, h2_baseline_reconciliation={})
all_ok = True
for scenario in ["scenario-uneven-multisched-01", "scenario-h1-k8s-ray-24h",
                 "scenario-h2-slurm-24h"]:
    records = {v: {} for v in ("base", "candidate")}
    for arm in ("baseline", "informed"):
        pairs = [json.loads((D / f"P3_R4_{scenario}_{arm}_{r}.json").read_text())
                 for r in (1, 2)]
        for version in ("base", "candidate"):
            summaries = [p["runs"][version]["summary"] for p in pairs]
            first, second = summaries
            checks = dict(
                scenario=scenario, arm=arm, version=version,
                physical_sha256=[s["physical_sha256"] for s in summaries],
                compact_sha256=[s["record"]["audit_compact_sha256"] for s in summaries],
                repetitions_physical_identical=first["physical_sha256"] == second["physical_sha256"],
                repetitions_compact_identical=first["record"]["audit_compact_sha256"] ==
                                               second["record"]["audit_compact_sha256"],
                repetitions_metrics_identical=first["metrics"] == second["metrics"],
                metric_count=len(first["metrics"]),
                base_candidate_identical=all(p["physical_identical"] and p["compact_identical"]
                                              and p["metrics_identical"] for p in pairs),
                native_status=[s["record"]["status"] for s in summaries],
            )
            if scenario == "scenario-uneven-multisched-01":
                checks["production_reference"] = PRODUCTION[arm]
                checks["production_actual"] = {k: first["metrics"][k] for k in PRODUCTION[arm]}
                checks["production_identical_at_9dp"] = all(
                    round(first["metrics"][k], 9) == v for k, v in PRODUCTION[arm].items())
                all_ok &= checks["production_identical_at_9dp"]
            if scenario == "scenario-h2-slurm-24h" and arm == "baseline":
                payload = first["metrics"]["start_fuel_reconciliation"]
                result["h2_baseline_reconciliation"][version] = {
                    "payload": payload,
                    "measured_start_event_count": first["record"]["measured_start_event_count"],
                    "constraints_valid": first["metrics"]["constraints_valid"],
                    "hard_violations": first["metrics"]["hard_violations"],
                }
                all_ok &= (payload["passed"] and first["record"]["measured_start_event_count"] == 11
                           and first["metrics"]["constraints_valid"]
                           and not first["metrics"]["hard_violations"])
            all_ok &= (checks["repetitions_physical_identical"]
                       and checks["repetitions_compact_identical"]
                       and checks["repetitions_metrics_identical"]
                       and checks["base_candidate_identical"]
                       and checks["native_status"] == ["PASS", "PASS"])
            result["checks"].append(checks)
            records[version][arm] = first["record"]
    for version in ("base", "candidate"):
        verdict = compare_metrics(records[version]["baseline"], records[version]["informed"])
        result["compare_runs"][scenario + "/" + version] = verdict
        all_ok &= verdict["verdict"] == "PASS"
result["passed"] = bool(all_ok)
(D / "P3_R4_EVALUATION.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"R4_passed": bool(all_ok), "completed_checks": len(result["checks"]),
                  "compare_runs": {k: v["verdict"] for k, v in result["compare_runs"].items()}}))
raise SystemExit(0 if all_ok else 2)
