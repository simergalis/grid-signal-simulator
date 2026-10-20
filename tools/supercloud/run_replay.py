#!/usr/bin/env python3
"""Run converted SuperCloud traces through the existing kube_trace_replay engine.

DR-2026-10-19-SUPERCLOUD-INGEST, Gate 3.  This is an analysis wrapper, not a
second replay implementation: it calls ``load_kube_trace`` and
``replay_kube_trace`` unchanged, then summarises the per-pod rows the engine
returns.  Per-event and per-pod detail is dropped so the written report is
aggregate-only (licence: CC BY-NC-ND; DR D4).

Bias measurement (DR §9, IMPL-SC-1): the engine ends every pod at the trace's
absolute ``deletion_time``.  For a Slurm job that means

    simulated runtime - actual runtime = actual_wait - simulated_wait

so a pod the simulator starts early runs long (occupancy inflated) and one it
starts late runs short (occupancy truncated).  This script reports that error
in GPU-hours so the effect on contention can be judged before results are read.

Usage:
    python3 tools/supercloud/run_replay.py --nodes nodes.csv --pods pods.csv \
        --output replay_summary.json
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Optional

REPO = Path(__file__).resolve().parents[2]
SIM_ROOT = REPO / "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim"
sys.path.insert(0, str(SIM_ROOT))

from runtime.kube_trace_replay import load_kube_trace, replay_kube_trace  # noqa: E402


def _pct(values: list[float], q: float) -> Optional[float]:
    if not values:
        return None
    v = sorted(values)
    k = (len(v) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return round(v[lo] + (v[hi] - v[lo]) * (k - lo), 3)


def _stats(values: Iterable[Optional[float]]) -> dict[str, Any]:
    v = [float(x) for x in values if x is not None]
    if not v:
        return {"n": 0}
    return {
        "n": len(v),
        "mean": round(sum(v) / len(v), 3),
        "p50": _pct(v, 0.5), "p90": _pct(v, 0.9), "p99": _pct(v, 0.99),
        "max": round(max(v), 3),
    }


def summarise(report: dict[str, Any], extra: dict[str, dict[str, str]]) -> dict[str, Any]:
    pods = report["pods"]
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in pods:
        meta = extra.get(p["pod_id"], {})
        if meta.get("in_window", "1") != "1":
            continue  # warm-start pods shape the cluster but are not scored
        is_gpu = int(meta.get("num_gpu", "0") or 0) > 0
        groups["all"].append(p)
        groups["gpu" if is_gpu else "cpu"].append(p)
        if meta.get("dnn_model"):
            groups["labelled_dnn"].append(p)
        groups[f"job_type:{meta.get('job_type', '?')}"].append(p)

    def block(rows: list[dict[str, Any]]) -> dict[str, Any]:
        both = [r for r in rows if r["actual_wait_s"] is not None and r["simulated_wait_s"] is not None]
        early = late = 0.0
        gpu_actual = 0.0
        for r in both:
            meta = extra.get(r["pod_id"], {})
            gpus = int(meta.get("num_gpu", "0") or 0)
            runtime = float(meta.get("runtime_s", "0") or 0)
            err = r["actual_wait_s"] - r["simulated_wait_s"]   # sim runtime - actual runtime
            gpu_actual += gpus * runtime
            if err > 0:
                early += gpus * err
            else:
                late += gpus * -err
        return {
            "pods": len(rows),
            "simulated_scheduled": sum(r["simulated_scheduled"] for r in rows),
            "simulated_unschedulable": sum(r["simulated_unschedulable"] for r in rows),
            "simulated_expired": sum(r["simulated_expired"] for r in rows),
            "queue_wait_s": {
                "actual": _stats(r["actual_wait_s"] for r in rows),
                "simulated": _stats(r["simulated_wait_s"] for r in rows),
                "delta_sim_minus_actual": _stats(r["wait_delta_s"] for r in rows),
            },
            "completion_time_bias": {
                "pods_started_earlier_than_actual": sum(1 for r in both if r["actual_wait_s"] > r["simulated_wait_s"]),
                "pods_started_later_than_actual": sum(1 for r in both if r["actual_wait_s"] < r["simulated_wait_s"]),
                "gpu_hours_actual": round(gpu_actual / 3600, 2),
                "gpu_hours_inflated_by_early_start": round(early / 3600, 2),
                "gpu_hours_truncated_by_late_start": round(late / 3600, 2),
            },
        }

    return {
        "schema_version": "supercloud-replay-summary-v1",
        "origin": report["origin"],
        "input": {k: report["input"][k] for k in ("node_rows", "pod_rows", "quarantined_rows")},
        "replay": report["replay"],
        "placement": report["placement"],
        "limitations": report["limitations"],
        "scheduler_event_count": report["scheduler_event_count"],
        "scored": {name: block(rows) for name, rows in sorted(groups.items())},
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--nodes", type=Path, required=True)
    ap.add_argument("--pods", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--backoff-duration-s", type=float, default=10.0)
    ap.add_argument("--max-backoff-retries", type=int, default=1)
    args = ap.parse_args(argv)

    with args.pods.open(newline="", encoding="utf-8") as fh:
        extra = {r["pod_id"]: r for r in csv.DictReader(fh)}
    t0 = time.monotonic()
    dataset = load_kube_trace(args.nodes, args.pods)
    report = replay_kube_trace(
        dataset,
        backoff_duration_s=args.backoff_duration_s,
        max_backoff_retries=args.max_backoff_retries,
    )
    summary = summarise(report, extra)
    summary["wall_clock_s"] = round(time.monotonic() - t0, 1)
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"pods={summary['input']['pod_rows']} nodes={summary['input']['node_rows']} "
          f"wall={summary['wall_clock_s']}s -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
