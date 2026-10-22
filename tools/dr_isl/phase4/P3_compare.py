"""Compare streaming base/candidate ticks; persist each completed pair."""
# PROPOSED_HERE: 120 s/60 s windows come from R1/TC-ISL-04; the 0.1 Hz
# nominal-recovery reporting band is an audit proxy, not a model parameter.
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

D = Path(__file__).resolve().parent
ROOT = D.parents[2]
BASE = Path("/tmp/DR-ISL-phase4-base")
loader = importlib.util.spec_from_file_location("pins", ROOT / "tools/dr_isl/baseline_runner.py")
pins = importlib.util.module_from_spec(loader)
loader.loader.exec_module(pins)


def save(name, value):
    data = (json.dumps(value, indent=2, allow_nan=True) + "\n").encode()
    if len(data) > 50_000_000:
        raise RuntimeError("STOP: output exceeds 50 MB " + name)
    (D / name).write_bytes(data)


class Stats:
    def __init__(self):
        self.data = dict(ticks=0, min_soc=1., frequency_min=float("inf"),
                         frequency_max=-float("inf"), frequency_min_time=None,
                         gt_min=float("inf"), gt_max=-float("inf"),
                         bess_min=float("inf"), bess_max=-float("inf"),
                         floor_min_mwh=float("inf"), floor_max_mwh=-float("inf"),
                         unserved_mwh=0., collapse=None, balance_failure_count=0,
                         first_balance_failure=None, first_floor=None,
                         first_discharge_floor=None, post_floor_window=[],
                         post_discharge_floor_window=[], first_advisory=None,
                         below_floor_hold_ticks=0, below_floor_discharge_ticks=0,
                         illegal_d2r_discharge_count=0, first_illegal_d2r_discharge=None,
                         basis_counts={})

    def add(self, row, obs):
        s = self.data
        s["ticks"] += 1
        s["min_soc"] = min(s["min_soc"], row["bess_soc_fraction"])
        if row["frequency_hz"] < s["frequency_min"]:
            s["frequency_min"], s["frequency_min_time"] = row["frequency_hz"], row["sim_time_seconds"]
        s["frequency_max"] = max(s["frequency_max"], row["frequency_hz"])
        for prefix, key in [("gt", "turbine_output_mw"), ("bess", "bess_output_mw")]:
            s[prefix + "_min"] = min(s[prefix + "_min"], row[key])
            s[prefix + "_max"] = max(s[prefix + "_max"], row[key])
        s["unserved_mwh"] += row["p_unserved_mw"] * 5 / 3600
        if row["island_collapsed"] and s["collapse"] is None:
            s["collapse"] = dict(tick=row["tick_index"], reason=row["collapse_reason"])
        balance = row["physical_balance"]
        if not obs["balance_passed"]:
            s["balance_failure_count"] += 1
            if s["first_balance_failure"] is None:
                s["first_balance_failure"] = dict(tick=row["tick_index"], terms=balance,
                                                  defect_mw=obs["balance_defect_mw"])
        snapshot = dict(tick=row["tick_index"], sim_time=row["sim_time_seconds"],
                        frequency_hz=row["frequency_hz"], gt_mw=row["turbine_output_mw"],
                        bess_mw=row["bess_output_mw"], soc=row["bess_soc_fraction"],
                        demand_mw=row["p_demand_mw"], solar_mw=row["p_renewable_mw"],
                        observation=obs)
        if row.get("bess_escalation_active") and s["first_advisory"] is None:
            s["first_advisory"] = dict(tick=row["tick_index"], sim_time=row["sim_time_seconds"],
                                       reason=row["bess_escalation_reason"])
        for unit, floor in obs["floors"].items():
            s["floor_min_mwh"] = min(s["floor_min_mwh"], floor)
            s["floor_max_mwh"] = max(s["floor_max_mwh"], floor)
            basis = obs["bases"].get(unit, {})
            key = "|".join(str(basis.get(k)) for k in ("winning_term", "basis", "unit_id"))
            s["basis_counts"][key] = s["basis_counts"].get(key, 0) + 1
            if obs["after"][unit] <= floor + 1e-9:
                if s["first_floor"] is None:
                    s["first_floor"] = snapshot
                if row["bess_output_mw"] > 0:
                    s["below_floor_discharge_ticks"] += 1
                    if s["first_discharge_floor"] is None:
                        s["first_discharge_floor"] = snapshot
                else:
                    s["below_floor_hold_ticks"] += 1
        for cover in obs["covers"]:
            basis = obs["bases"].get(cover["unit"], {})
            hard = basis.get("d2r_term_mwh", 0)
            if (cover["output_mw"] > 0 and not cover["on_bus"]
                    and cover["after_mwh"] < min(cover["before_mwh"], hard) - 1e-9):
                s["illegal_d2r_discharge_count"] += 1
                if s["first_illegal_d2r_discharge"] is None:
                    s["first_illegal_d2r_discharge"] = snapshot
        for anchor, window in [("first_floor", "post_floor_window"),
                               ("first_discharge_floor", "post_discharge_floor_window")]:
            if s[anchor] is not None and row["sim_time_seconds"] <= s[anchor]["sim_time"] + 120:
                s[window].append(snapshot)

    def finish(self, summary):
        self.data["summary"] = summary
        for anchor, window in [("first_floor", "post_floor_window"),
                               ("first_discharge_floor", "post_discharge_floor_window")]:
            rows = self.data[window]
            self.data[anchor + "_next120s_min_hz"] = min(
                (r["frequency_hz"] for r in rows), default=None)
        self.data["complete"] = self.data["ticks"] * 5 == summary["end_sim_time"]
        return self.data


def pair(scenario, arm, repetition, gate):
    label = f"P3_{gate}_{scenario}_{arm}_{repetition}"
    save("STATUS.json", {"item": "P3", "state": "RUNNING", "case": label})
    logs, jobs = [], []
    result = dict(scenario=scenario, arm=arm, repetition=repetition, gate=gate,
                  first_physical_difference=None)
    stats = [Stats(), Stats()]
    try:
        for version, checkout in [("base", BASE), ("candidate", ROOT)]:
            log = (D / (label + "." + version + ".stderr.txt")).open("w")
            logs.append(log)
            job = subprocess.Popen(
                [sys.executable, str(D / "stream_worker.py"), str(checkout),
                 scenario, arm, "ae49aaa" if version == "base" else "phase4-working-candidate"],
                stdout=subprocess.PIPE, stderr=log, text=True, bufsize=1)
            jobs.append(job)
        while True:
            raw = [j.stdout.readline() for j in jobs]
            if any(not r for r in raw):
                raise RuntimeError("Worker ended before summary; see durable stderr")
            messages = [json.loads(r) for r in raw]
            if any(m["kind"] == "summary" for m in messages):
                if not all(m["kind"] == "summary" for m in messages):
                    raise RuntimeError("Stream lengths differ")
                result["runs"] = {v: stats[i].finish(messages[i])
                                  for i, v in enumerate(("base", "candidate"))}
                break
            b, c = [m["physical"] for m in messages]
            for i, msg in enumerate(messages):
                stats[i].add(msg["physical"], msg["observation"])
            if result["first_physical_difference"] is None and pins.encoded(b) != pins.encoded(c):
                result["first_physical_difference"] = dict(
                    tick=b["tick_index"],
                    fields={k: dict(base=b.get(k), candidate=c.get(k)) for k in b.keys() | c.keys()
                            if pins.encoded(b.get(k)) != pins.encoded(c.get(k))})
        result["return_codes"] = [j.wait() for j in jobs]
        if result["return_codes"] != [0, 0]:
            raise RuntimeError("Worker failed")
        bs, cs = messages
        result["physical_identical"] = bs["physical_sha256"] == cs["physical_sha256"]
        result["compact_identical"] = (bs["record"].get("audit_compact_sha256")
                                       == cs["record"].get("audit_compact_sha256"))
        result["metric_differences"] = {
            k: dict(base=bs["metrics"].get(k), candidate=cs["metrics"].get(k))
            for k in bs["metrics"].keys() | cs["metrics"].keys()
            if pins.encoded(bs["metrics"].get(k)) != pins.encoded(cs["metrics"].get(k))
        }
        result["metrics_identical"] = not result["metric_differences"]
        save(label + ".json", result)
        print(json.dumps(dict(case=label, physical_identical=result["physical_identical"],
                              metrics_identical=result["metrics_identical"])), flush=True)
        return result
    except BaseException as exc:
        result["tooling_error"] = repr(exc)
        save(label + ".json", result)
        raise
    finally:
        for job in jobs:
            if job.poll() is None:
                job.terminate()
        for log in logs:
            log.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("gate", choices=["R1", "R3", "R4"])
    args = parser.parse_args()
    if args.gate == "R1":
        cases = [(s, "app", r) for s in ["demo-islanded-ramp", "S10_mit_supercloud_2021-08-11"]
                 for r in [1, 2]]
    elif args.gate == "R3":
        cases = [(s, "app", 1) for s in [
            "scenario-equinix-sj-1", "scenario-turbine-01",
            "scenario-hybrid-ai-100mw-addendum-i", "scenario-100mw-fuel-cell-bess-diesel",
            "scenario-fc100-islanded-v2", "scenario-fc100-islanded-zero-hot-v2"]]
    else:
        cases = [(s, arm, r) for s in ["scenario-uneven-multisched-01",
                                      "scenario-h1-k8s-ray-24h", "scenario-h2-slurm-24h"]
                 for arm in ["baseline", "informed"] for r in [1, 2]]
    completed = []
    for scenario, arm, rep in cases:
        result = pair(scenario, arm, rep, args.gate)
        if args.gate == "R3":
            reference = json.loads((D / "P3_R3_REFERENCE_HASHES.json").read_text())[scenario]
            actual = {v: result["runs"][v]["summary"]["physical_sha256"]
                      for v in ("base", "candidate")}
            save(f"P3_R3_{scenario}_reference_check.json",
                 {"reference": reference, "actual": actual,
                  "identical": all(h == reference for h in actual.values())})
            if any(h != reference for h in actual.values()):
                save("P3_STOP.json", {"gate": "R3", "scenario": scenario,
                                      "reason": "Historical physical hash mismatch",
                                      "reference": reference, "actual": actual})
                return 2
        completed.append({"scenario": scenario, "arm": arm, "repetition": rep})
        save("P3_" + args.gate + "_PROGRESS.json", completed)
        if args.gate in ("R3", "R4") and (
            not result["physical_identical"] or not result["metrics_identical"]
            or not result["compact_identical"]
            or (args.gate == "R4" and any(
                result["runs"][v]["summary"]["record"]["status"] != "PASS"
                for v in ("base", "candidate")))
        ):
            save("P3_STOP.json", {"gate": args.gate, "case": completed[-1],
                                  "reason": "Protected physical/metric/compact change",
                                  "evidence": f"P3_{args.gate}_{scenario}_{arm}_{rep}.json"})
            return 2
    save("P3_" + args.gate + "_COMPLETE.json", {"completed": completed})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
