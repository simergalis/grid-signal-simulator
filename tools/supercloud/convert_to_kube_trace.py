#!/usr/bin/env python3
"""Convert MIT SuperCloud slurm-log.csv into the kube_trace_replay CSV contract.

DR-2026-10-19-SUPERCLOUD-INGEST, Gate 3.  Output loads unchanged through
``runtime.kube_trace_replay.load_kube_trace``; no new replay engine is added
(DR D1).  Encodings are those confirmed at Gate 1 (DR §8):

* ``time_*``      Unix epoch seconds.
* ``tres_req``    ``id=count,...``; 1=cpu, 2=mem (MB), 1001=gpu:tesla, 1002=gpu:volta.
* ``mem_req``     bit 63 set -> (mem_req - 2**63) MB per CPU x cpus_req;
                  bit 63 clear -> MB per node x nodes_alloc.  Slurm MB == MiB.
* ``state``       numeric slurmdbd enum; values > 0xFF carry flag bits.
* ``nodelist``    Python-list string, e.g. "['r9189566-n911952']".

Column mapping (DR §5 as amended at Gate 2):

    pod_id          "sc-<id_job>"                    (id_job unique, H8)
    workload_id     "sc-arr-<id_array_job>" for array tasks, else pod_id
    cpu_milli       tres_req cpu x 1000
    memory_mib      decoded mem_req, cross-checked against tres_req mem
    num_gpu         tres_req 1001 + 1002;  gpu_milli = num_gpu x 1000
    gpu_spec        "V100" for 1002;  empty for CPU-only pods
    qos             Slurm multifactor priority, as an integer string
    creation_time   time_eligible   (not time_submit: dependency/begin holds
                                     are not resource wait)
    scheduled_time  time_start      (comparison only in the replay)
    deletion_time   time_end
    node_id         the single nodelist entry

Quarantined rows are written with a reason, never silently dropped.  Rows
outside --partitions / --start..--end are counted as out of scope.

Node inventory is DERIVED, not hard-coded: per node, the peak concurrent CPU,
memory and GPU allocation observed in the trace (sweep line over tres_alloc,
multi-node jobs split evenly across their nodes).  This is a lower bound on
true capacity; see DR §9.

Licence: CC BY-NC-ND 4.0.  Output CSVs contain row-level (anonymised) data:
write them outside the repository.  Only summary.json is aggregate-only.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

MEM_PER_CPU_FLAG = 1 << 63
ARRAY_TASK_NONE = 4294967294        # Slurm NO_VAL for id_array_task
TIMELIMIT_INFINITE = 4294967295     # Slurm INFINITE
TRES_CPU, TRES_MEM, TRES_GPU_TESLA, TRES_GPU_VOLTA = 1, 2, 1001, 1002
STATE_NAMES = {
    0: "PENDING", 1: "RUNNING", 2: "SUSPENDED", 3: "COMPLETED", 4: "CANCELLED",
    5: "FAILED", 6: "TIMEOUT", 7: "NODE_FAIL", 8: "PREEMPTED", 9: "BOOT_FAIL",
    10: "DEADLINE", 11: "OUT_OF_MEMORY",
}
TERMINAL_STATES = {3, 4, 5, 6, 7, 8, 9, 10, 11}
GPU_MODEL_VOLTA = "V100"
NODELIST_RE = re.compile(r"'([^']+)'")

POD_COLUMNS = (
    "pod_id", "workload_id", "cpu_milli", "memory_mib", "num_gpu", "gpu_milli",
    "gpu_spec", "qos", "creation_time", "scheduled_time", "deletion_time",
    "node_id",
    # Pass-through analysis columns; load_kube_trace ignores unknown headers.
    "partition", "job_type", "slurm_state", "dnn_model", "runtime_s",
    "timelimit_min", "in_window",
)
NODE_COLUMNS = ("node_id", "cpu_milli", "memory_mib", "gpu_count", "model")


class Quarantine(ValueError):
    """A row the converter refuses to emit, with a stable reason code."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class SlurmRow:
    id_job: str
    id_array_job: str
    id_array_task: int
    nodes_alloc: int
    nodes: tuple[str, ...]
    cpus_req: int
    mem_req: int
    partition: str
    priority: int
    state: int
    timelimit: int
    time_eligible: int
    time_start: int
    time_end: int
    tres_req: dict[int, int]
    tres_alloc: dict[int, int]
    job_type: str


def _int(raw: str, field: str) -> int:
    try:
        return int(raw.strip())
    except (AttributeError, ValueError):
        raise Quarantine("malformed_field", f"{field}={raw!r}") from None


def parse_tres(raw: str, field: str) -> dict[int, int]:
    """Parse ``id=count,id=count``; quarantine anything else."""
    raw = (raw or "").strip()
    if not raw:
        raise Quarantine("malformed_tres", f"{field} is empty")
    out: dict[int, int] = {}
    for part in raw.split(","):
        key, sep, value = part.strip().partition("=")
        if not sep or not key.isdigit() or not value.isdigit():
            raise Quarantine("malformed_tres", f"{field}={raw!r}")
        out[int(key)] = int(value)
    return out


def parse_nodelist(raw: str) -> tuple[str, ...]:
    return tuple(NODELIST_RE.findall(raw or ""))


def decode_memory_mib(mem_req: int, cpus_req: int, nodes_alloc: int) -> int:
    """Total job memory in MiB from slurmdbd ``mem_req`` (DR §8, H4 refined)."""
    if mem_req >= MEM_PER_CPU_FLAG:
        return (mem_req - MEM_PER_CPU_FLAG) * cpus_req
    return mem_req * max(1, nodes_alloc)


def gpu_counts(tres: dict[int, int]) -> tuple[int, int]:
    return tres.get(TRES_GPU_TESLA, 0), tres.get(TRES_GPU_VOLTA, 0)


def parse_row(row: dict[str, str]) -> SlurmRow:
    nodes = parse_nodelist(row.get("nodelist", ""))
    parsed = SlurmRow(
        id_job=(row.get("id_job") or "").strip(),
        id_array_job=(row.get("id_array_job") or "").strip(),
        id_array_task=_int(row.get("id_array_task", ""), "id_array_task"),
        nodes_alloc=_int(row.get("nodes_alloc", ""), "nodes_alloc"),
        nodes=nodes,
        cpus_req=_int(row.get("cpus_req", ""), "cpus_req"),
        mem_req=_int(row.get("mem_req", ""), "mem_req"),
        partition=(row.get("partition") or "").strip(),
        priority=_int(row.get("priority", ""), "priority"),
        state=_int(row.get("state", ""), "state"),
        timelimit=_int(row.get("timelimit", ""), "timelimit"),
        time_eligible=_int(row.get("time_eligible", ""), "time_eligible"),
        time_start=_int(row.get("time_start", ""), "time_start"),
        time_end=_int(row.get("time_end", ""), "time_end"),
        tres_req=parse_tres(row.get("tres_req", ""), "tres_req"),
        tres_alloc=parse_tres(row.get("tres_alloc", ""), "tres_alloc"),
        job_type=(row.get("job_type") or "").strip(),
    )
    if not parsed.id_job:
        raise Quarantine("malformed_field", "id_job is empty")
    if len(nodes) != parsed.nodes_alloc:
        raise Quarantine("nodelist_mismatch", f"nodes_alloc={parsed.nodes_alloc} entries={len(nodes)}")
    return parsed


def check_row(r: SlurmRow) -> None:
    """Apply the Gate 2 quarantine rules to a parsed row."""
    if r.state > 0xFF:
        raise Quarantine("state_flag_bits", f"state={r.state}")
    if r.state not in TERMINAL_STATES:
        raise Quarantine("non_terminal_state", f"state={r.state}")
    if r.time_start <= 0:
        raise Quarantine("never_started")
    if not (r.time_eligible <= r.time_start <= r.time_end):
        raise Quarantine("time_order", "eligible<=start<=end violated")
    if r.nodes_alloc != 1:
        raise Quarantine("multi_node", f"nodes_alloc={r.nodes_alloc}")  # CAV-SC-2
    tesla, volta = gpu_counts(r.tres_req)
    if tesla:
        raise Quarantine("gpu_type_tesla_ambiguous", f"tesla={tesla}")
    if TRES_CPU not in r.tres_req:
        raise Quarantine("missing_tres_cpu")
    decoded = decode_memory_mib(r.mem_req, r.cpus_req, r.nodes_alloc)
    tres_mem = r.tres_req.get(TRES_MEM)
    if tres_mem is not None and tres_mem != decoded:
        raise Quarantine("memory_decode_mismatch", f"decoded={decoded} tres={tres_mem}")


def to_pod(r: SlurmRow, model_label: Optional[str], window_start: Optional[int]) -> dict[str, Any]:
    _, volta = gpu_counts(r.tres_req)
    pod_id = f"sc-{r.id_job}"
    is_array = r.id_array_task != ARRAY_TASK_NONE
    return {
        "pod_id": pod_id,
        "workload_id": f"sc-arr-{r.id_array_job}" if is_array else pod_id,
        "cpu_milli": r.tres_req[TRES_CPU] * 1000,
        "memory_mib": decode_memory_mib(r.mem_req, r.cpus_req, r.nodes_alloc),
        "num_gpu": volta,
        "gpu_milli": volta * 1000,
        "gpu_spec": GPU_MODEL_VOLTA if volta else "",
        "qos": str(r.priority),
        "creation_time": r.time_eligible,
        "scheduled_time": r.time_start,
        "deletion_time": r.time_end,
        "node_id": r.nodes[0],
        "partition": r.partition,
        "job_type": r.job_type,
        "slurm_state": STATE_NAMES.get(r.state, str(r.state)),
        "dnn_model": model_label or "",
        "runtime_s": r.time_end - r.time_start,
        "timelimit_min": "" if r.timelimit == TIMELIMIT_INFINITE else r.timelimit,
        "in_window": int(window_start is None or r.time_eligible >= window_start),
    }


def _mode(values: Iterable[int]) -> int:
    counts = Counter(values)
    return counts.most_common(1)[0][0] if counts else 0


def derive_nodes(rows: Iterable[SlurmRow]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Derive the node inventory from the trace (DR §9).

    Capacity is the peak *concurrent* allocation per node over single-node
    jobs only.  Multi-node jobs are excluded from the peak because Slurm does
    not split them evenly (1,471 of 6,561 do not even divide by node count),
    and an even split inflated peaks above the hardware class.  Each node's
    class is its majority partition; a node is lifted to its class's modal
    capacity where its own observed peak is lower, and nodes seen only in
    multi-node jobs take the class capacity outright.  The result is a lower
    bound on true capacity, not a hardware spec.
    """
    rows = list(rows)
    events: dict[str, list[tuple[int, int, int, int, int]]] = defaultdict(list)
    partitions: dict[str, Counter[str]] = defaultdict(Counter)
    gpu_seen: dict[str, Counter[int]] = defaultdict(Counter)
    for r in rows:
        for node in r.nodes:
            partitions[node][r.partition] += 1
        if r.nodes_alloc != 1 or r.time_start <= 0 or r.time_end < r.time_start or not r.nodes:
            continue
        node = r.nodes[0]
        tesla, volta = gpu_counts(r.tres_alloc)
        cpu = r.tres_alloc.get(TRES_CPU, 0)
        mem = r.tres_alloc.get(TRES_MEM, 0)
        # End (-1) sorts before start (+1) at equal timestamps: a job that ends
        # at t frees capacity for one that starts at t.
        events[node].append((r.time_start, 1, cpu, mem, tesla + volta))
        events[node].append((r.time_end, -1, cpu, mem, tesla + volta))
        if tesla:
            gpu_seen[node][TRES_GPU_TESLA] += 1
        if volta:
            gpu_seen[node][TRES_GPU_VOLTA] += 1

    observed: dict[str, list[int]] = {}
    for node, evs in events.items():
        cur = [0, 0, 0]
        peak = [0, 0, 0]
        for _t, sign, cpu, mem, gpu in sorted(evs, key=lambda e: (e[0], e[1])):
            cur = [cur[0] + sign * cpu, cur[1] + sign * mem, cur[2] + sign * gpu]
            peak = [max(p, c) for p, c in zip(peak, cur)]
        observed[node] = peak

    node_class = {node: counts.most_common(1)[0][0] for node, counts in partitions.items()}
    class_capacity: dict[str, list[int]] = {}
    for cls in set(node_class.values()):
        members = [observed[n] for n in observed if node_class[n] == cls]
        class_capacity[cls] = [_mode(m[i] for m in members) for i in range(3)]

    out = []
    lifted = class_only = 0
    for node in sorted(partitions):
        cls = node_class[node]
        base = class_capacity.get(cls, [0, 0, 0])
        own = observed.get(node)
        if own is None:
            cap = list(base)
            class_only += 1
        else:
            cap = [max(o, b) for o, b in zip(own, base)]
            lifted += cap != own
        seen = gpu_seen.get(node, Counter())
        if cap[2] == 0:
            model = "none"
        elif seen[TRES_GPU_TESLA] > seen[TRES_GPU_VOLTA]:
            model = "tesla"
        else:
            model = GPU_MODEL_VOLTA
        out.append({
            "node_id": node,
            "cpu_milli": cap[0] * 1000,
            "memory_mib": cap[1],
            "gpu_count": cap[2],
            "model": model,
        })
    basis = {
        "capacity_basis": "peak concurrent single-node allocation, lifted to partition-class mode (lower bound)",
        "class_capacity_cpu_mem_gpu": {k: v for k, v in sorted(class_capacity.items())},
        "nodes_observed_directly": len(observed),
        "nodes_lifted_to_class": lifted,
        "nodes_class_only": class_only,
    }
    return out, basis


def _epoch(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def load_labels(path: Optional[Path]) -> dict[str, str]:
    if path is None:
        return {}
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return {row["id_job"].strip(): row["model"].strip() for row in csv.DictReader(fh)}


def iter_rows(path: Path) -> Iterator[tuple[int, dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for row_number, row in enumerate(csv.DictReader(fh), start=2):
            yield row_number, row


def convert(
    slurm_log: Path,
    out_dir: Path,
    *,
    labels_path: Optional[Path] = None,
    partitions: Optional[set[str]] = None,
    start: Optional[int] = None,
    end: Optional[int] = None,
) -> dict[str, Any]:
    """Write nodes.csv, pods.csv, quarantine.csv and summary.json to ``out_dir``."""
    labels = load_labels(labels_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    in_scope: list[SlurmRow] = []
    inventory_rows: list[SlurmRow] = []  # partition-scoped, whole trace (hardware is not windowed)
    pods: list[dict[str, Any]] = []
    quarantine_rows: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    gpu_reasons: Counter[str] = Counter()
    labelled_reasons: Counter[str] = Counter()
    out_of_scope: Counter[str] = Counter()
    source_rows = 0
    scoped_quarantined = 0

    for row_number, raw in iter_rows(slurm_log):
        source_rows += 1
        try:
            r = parse_row(raw)
        except Quarantine as q:
            reasons[q.reason] += 1
            quarantine_rows.append({"row": row_number, "id_job": raw.get("id_job", ""),
                                    "reason": q.reason, "detail": q.detail})
            continue
        if partitions is not None and r.partition not in partitions:
            out_of_scope["partition"] += 1
            continue
        inventory_rows.append(r)
        # Keep jobs that overlap the window so the cluster starts warm.
        if end is not None and r.time_eligible >= end:
            out_of_scope["after_window"] += 1
            continue
        if start is not None and r.time_end <= start:
            out_of_scope["before_window"] += 1
            continue
        in_scope.append(r)
        is_gpu = any(gpu_counts(r.tres_req))
        try:
            check_row(r)
        except Quarantine as q:
            scoped_quarantined += 1
            reasons[q.reason] += 1
            if is_gpu:
                gpu_reasons[q.reason] += 1
            if r.id_job in labels:
                labelled_reasons[q.reason] += 1
            quarantine_rows.append({"row": row_number, "id_job": r.id_job,
                                    "reason": q.reason, "detail": q.detail})
            continue
        pods.append(to_pod(r, labels.get(r.id_job), start))

    nodes, node_basis = derive_nodes(inventory_rows)
    # CAV-SC-7 (resolved at Gate 3): a GPU request is unplaceable only if it
    # exceeds every node in the derived inventory.  Checked after derivation
    # because capacity is a property of the whole trace, not of one row.
    max_node_gpus = max((n["gpu_count"] for n in nodes), default=0)
    kept: list[dict[str, Any]] = []
    for pod in pods:
        if pod["num_gpu"] > max_node_gpus:
            scoped_quarantined += 1
            reasons["gpu_count_exceeds_inventory"] += 1
            gpu_reasons["gpu_count_exceeds_inventory"] += 1
            if pod["dnn_model"]:
                labelled_reasons["gpu_count_exceeds_inventory"] += 1
            quarantine_rows.append({"row": "", "id_job": pod["pod_id"][3:],
                                    "reason": "gpu_count_exceeds_inventory",
                                    "detail": f"gpus={pod['num_gpu']} max_node={max_node_gpus}"})
        else:
            kept.append(pod)
    pods = kept
    with (out_dir / "nodes.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, NODE_COLUMNS)
        w.writeheader()
        w.writerows(nodes)
    with (out_dir / "pods.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, POD_COLUMNS)
        w.writeheader()
        w.writerows(pods)
    with (out_dir / "quarantine.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, ("row", "id_job", "reason", "detail"))
        w.writeheader()
        w.writerows(quarantine_rows)

    summary = {
        "schema_version": "supercloud-kube-convert-v1",
        "source": slurm_log.name,
        "filters": {
            "partitions": sorted(partitions) if partitions else None,
            "start_epoch": start, "end_epoch": end,
        },
        "source_rows": source_rows,
        "out_of_scope": dict(out_of_scope),
        "in_scope_rows": len(in_scope),
        "pods_emitted": len(pods),
        "pods_in_window": sum(p["in_window"] for p in pods),
        "gpu_pods_emitted": sum(1 for p in pods if p["num_gpu"]),
        "labelled_pods_emitted": sum(1 for p in pods if p["dnn_model"]),
        "quarantined": sum(reasons.values()),
        "quarantine_by_reason": dict(reasons.most_common()),
        "gpu_quarantine_by_reason": dict(gpu_reasons.most_common()),
        "labelled_quarantine_by_reason": dict(labelled_reasons.most_common()),
        "nodes": {
            "count": len(nodes),
            "gpu_nodes": sum(1 for n in nodes if n["gpu_count"]),
            "gpu_count_distribution": dict(Counter(n["gpu_count"] for n in nodes).most_common()),
            "cpu_cores_distribution": dict(Counter(n["cpu_milli"] // 1000 for n in nodes).most_common(10)),
            "total_gpus": sum(n["gpu_count"] for n in nodes),
            **node_basis,
        },
    }
    # Accounting identity (TC-SC-02): every in-scope row is a pod or a quarantine.
    if len(in_scope) != len(pods) + scoped_quarantined:
        raise AssertionError("accounting identity violated: in_scope != pods + quarantined")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("slurm_log", type=Path)
    ap.add_argument("--out-dir", type=Path, required=True, help="write OUTSIDE the repository")
    ap.add_argument("--labels", type=Path, help="labelled_jobids.csv (id_job,model)")
    ap.add_argument("--partitions", help="comma-separated Slurm partitions to keep")
    ap.add_argument("--start", help="window start, ISO-8601 (UTC if no offset)")
    ap.add_argument("--end", help="window end, ISO-8601 (UTC if no offset)")
    args = ap.parse_args(argv)
    summary = convert(
        args.slurm_log, args.out_dir,
        labels_path=args.labels,
        partitions=set(args.partitions.split(",")) if args.partitions else None,
        start=_epoch(args.start), end=_epoch(args.end),
    )
    print(json.dumps({k: summary[k] for k in (
        "source_rows", "in_scope_rows", "pods_emitted", "gpu_pods_emitted", "quarantined",
        "quarantine_by_reason")}, indent=2))
    print(f"nodes={summary['nodes']['count']} gpu_nodes={summary['nodes']['gpu_nodes']} -> {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
