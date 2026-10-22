"""V1–V3 paired streaming audit; persist each completed case, stop on first delta."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

D = Path(__file__).resolve().parent
ROOT = D.parents[2]
BASE = Path("/tmp/DR-ISL-phase5-base")
NEW = {"invalid_frequency_tick_count", "invalid_frequency_fraction", "protection_configured"}
EXCLUDED_FLAGS = {"frequency_valid", "protection_configured"}
scenarios = [
    ("scenario-uneven-multisched-01", "baseline"),
    ("scenario-uneven-multisched-01", "informed"),
    ("scenario-h1-k8s-ray-24h", "baseline"),
    ("scenario-h1-k8s-ray-24h", "informed"),
    ("scenario-h2-slurm-24h", "baseline"),
    ("scenario-h2-slurm-24h", "informed"),
] + [(s, "app") for s in [
    "S10_mit_supercloud_2021-08-11", "demo-islanded-ramp", "scenario-equinix-sj-1",
    "scenario-turbine-01", "scenario-hybrid-ai-100mw-addendum-i",
    "scenario-100mw-fuel-cell-bess-diesel", "scenario-fc100-islanded-v2",
    "scenario-fc100-islanded-zero-hot-v2",
]]


def save(path, value):
    data = json.dumps(value, indent=2, allow_nan=True) + "\n"
    assert len(data.encode()) < 50_000_000
    tmp = path.with_suffix(".tmp")
    tmp.write_text(data)
    tmp.replace(path)


def read(proc):
    line = proc.stdout.readline()
    if not line:
        raise RuntimeError("worker ended before summary; see bounded stderr evidence")
    return json.loads(line)


def pair(scenario, arm):
    name = f"{scenario}_{arm}"
    procs, logs = [], []
    for checkout, label in [(BASE, "base"), (ROOT, "candidate")]:
        log = (D / f"{name}.{label}.stderr.txt").open("w")
        logs.append(log)
        procs.append(subprocess.Popen(
            [sys.executable, str(D / "stream_worker.py"), str(checkout), scenario, arm,
             "fd87fc7" if label == "base" else "phase5-candidate"],
            stdout=subprocess.PIPE, stderr=log, text=True,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1")))
    result = dict(scenario=scenario, arm=arm, ticks=0, first_difference=None,
                  invalid_frequency_tick_count=0, first_invalid_tick=None,
                  frequency_min=None, frequency_max=None, protection_configured=None)
    summaries = None
    try:
        while True:
            messages = [read(p) for p in procs]
            if all(m["kind"] == "summary" for m in messages):
                summaries = messages
                break
            if any(m["kind"] != "tick" for m in messages):
                result["first_difference"] = {"kind": "unequal tick counts", "messages": messages}
                break
            before, after = [m["physical"] for m in messages]
            result["ticks"] += 1
            if before != after:
                result["first_difference"] = {
                    "tick": result["ticks"],
                    "fields": {k: [before.get(k), after.get(k)]
                               for k in before.keys() | after.keys() if before.get(k) != after.get(k)},
                }
                break
            reporting = messages[1]["reporting"]
            f = after["frequency_hz"]
            result["frequency_min"] = f if result["frequency_min"] is None else min(f, result["frequency_min"])
            result["frequency_max"] = f if result["frequency_max"] is None else max(f, result["frequency_max"])
            result["protection_configured"] = reporting["protection_configured"]
            if reporting["frequency_valid"] is False:
                result["invalid_frequency_tick_count"] += 1
                if result["first_invalid_tick"] is None:
                    result["first_invalid_tick"] = dict(
                        tick=result["ticks"], sim_time_seconds=after["sim_time_seconds"], frequency_hz=f)
        if summaries is not None:
            for p in procs:
                if p.wait() != 0:
                    raise RuntimeError("worker failed after output")
            result["summaries"] = dict(zip(["base", "candidate"], summaries))
            bm, cm = [s["metrics"] or {} for s in summaries]
            filtered = {k: v for k, v in cm.items() if k not in NEW}
            result["existing_metrics_count"] = len(bm)
            result["existing_metric_differences"] = {
                k: [bm.get(k), filtered.get(k)] for k in bm.keys() | filtered.keys()
                if bm.get(k) != filtered.get(k)}
            result["physical_identical"] = summaries[0]["physical_sha256"] == summaries[1]["physical_sha256"]
            if arm != "app":
                result["compact_identical_excluding_new_flags"] = (
                    summaries[0]["record"]["audit_compact_sha256"] ==
                    summaries[1]["record"]["audit_compact_sha256"])
                result["added_metrics"] = {k: cm[k] for k in NEW}
            result["passed"] = result["physical_identical"] and not result["existing_metric_differences"]
            if arm != "app":
                result["passed"] &= result["compact_identical_excluding_new_flags"]
                result["passed"] &= summaries[1]["record"]["status"] == "PASS"
        else:
            result["passed"] = False
        result["invalid_frequency_fraction"] = result["invalid_frequency_tick_count"] / result["ticks"]
        save(D / f"{name}.json", result)
        return result
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for log in logs:
            log.close()


results = []
for scenario, arm in scenarios:
    save(D / "STATUS.json", dict(state="RUNNING", item="V1/V2", scenario=scenario, arm=arm))
    result = pair(scenario, arm)
    results.append({k: result[k] for k in result if k != "summaries"})
    save(D / "V1_V2_PROGRESS.json", results)
    print(json.dumps(dict(scenario=scenario, arm=arm, passed=result["passed"],
                          invalid_ticks=result["invalid_frequency_tick_count"])), flush=True)
    if not result["passed"]:
        save(D / "STOP.json", result)
        raise SystemExit(2)

sys.path.insert(0, str(ROOT / "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim"))
from study_harness.acceptance import compare_metrics
verdicts = {}
for scenario in ["scenario-uneven-multisched-01", "scenario-h1-k8s-ray-24h", "scenario-h2-slurm-24h"]:
    arms = [json.loads((D / f"{scenario}_{arm}.json").read_text()) for arm in ["baseline", "informed"]]
    for version in ["base", "candidate"]:
        records = [x["summaries"][version]["record"] for x in arms]
        verdicts[f"{scenario}/{version}"] = compare_metrics(*records)
save(D / "V3_COMPARE_RUNS.json", verdicts)
passed = all(v["verdict"] == "PASS" and all(v["conditions"].values()) for v in verdicts.values())
save(D / "V1_V3_COMPLETE.json", dict(passed=passed, cases=results, compare_runs=verdicts))
raise SystemExit(0 if passed else 2)
