"""Offline replay and comparison for Alibaba-style Kubernetes traces.

This module is intentionally separate from the synthetic ``KubeDemandAgent``.
It parses a node CSV and a pod CSV, feeds creation-time arrivals into the
Phase A scheduler, releases resources at ``deletion_time``, and compares the
simulated queue waits with the trace's ``scheduled_time`` values.

The replay is deliberately conservative:

* ``scheduled_time`` is comparison data only; it never drives admission.
* ``deletion_time`` is the simulated completion time.
* ``gpu_milli`` is rounded up to an integer GPU for this Phase A pass and is
  reported as a known limitation when it is fractional.
* gang admission, quota/borrowing, and preemption remain outside Phase A.
"""

from __future__ import annotations

import argparse
import csv
import heapq
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from core.kube_scheduler import KubeNode, KubePod, KubeSchedulerEngine


DEFAULT_QOS_PRIORITIES: dict[str, int] = {
    "guaranteed": 300,
    "burstable": 200,
    "besteffort": 100,
    "best-effort": 100,
}

NODE_ALIASES: dict[str, tuple[str, ...]] = {
    "node_id": ("node_id", "node", "name", "hostname", "host"),
    "cpu_milli": ("cpu_milli", "cpu", "cpu_capacity_milli", "available_cpu"),
    "memory_mib": ("memory_mib", "memory", "memory_capacity_mib", "available_memory"),
    "gpu_count": ("gpu_count", "num_gpu", "gpu", "gpus", "gpu_capacity"),
    "model": ("model", "gpu_type", "gpu_model", "gpu_spec"),
}

POD_ALIASES: dict[str, tuple[str, ...]] = {
    "pod_id": ("pod_id", "pod", "task_id", "task", "name"),
    "workload_id": ("workload_id", "job_id", "workload", "job", "task_id"),
    "cpu_milli": ("cpu_milli", "cpu", "requested_cpu"),
    "memory_mib": ("memory_mib", "memory", "requested_memory"),
    "num_gpu": ("num_gpu", "gpu_count", "gpu", "requested_gpu"),
    "gpu_milli": ("gpu_milli", "gpu_milli_request", "requested_gpu_milli"),
    "gpu_spec": ("gpu_spec", "gpu_type", "gpu_types", "model"),
    "qos": ("qos", "priority_class", "priority"),
    "creation_time": ("creation_time", "created_at", "submit_time"),
    "scheduled_time": ("scheduled_time", "scheduled_at"),
    "deletion_time": ("deletion_time", "deleted_at", "completion_time"),
    "actual_node_id": ("node_id", "assigned_node", "node_name", "host"),
}


@dataclass(frozen=True)
class KubeTraceNode:
    node_id: str
    cpu_milli: int
    memory_mib: int
    gpu_count: int
    model: str
    row_number: int


@dataclass(frozen=True)
class KubeTracePod:
    pod_id: str
    workload_id: str
    cpu_milli: int
    memory_mib: int
    num_gpu: int
    gpu_milli: float
    gpu_types: tuple[str, ...]
    qos: str
    priority: int
    creation_time: datetime
    scheduled_time: Optional[datetime]
    deletion_time: Optional[datetime]
    actual_node_id: Optional[str]
    row_number: int

    @property
    def replay_gpu_count(self) -> int:
        """Return the conservative integer GPU approximation used by Phase A."""
        milli_count = math.ceil(self.gpu_milli / 1000.0) if self.gpu_milli > 0 else 0
        return max(self.num_gpu, milli_count)

    @property
    def fractional_gpu_request(self) -> bool:
        return not math.isclose(self.gpu_milli % 1000.0, 0.0, abs_tol=1e-9)

    @property
    def gpu_shape(self) -> str:
        return "|".join(self.gpu_types) if self.gpu_types else "any"

    @property
    def resource_shape(self) -> str:
        return (
            f"cpu={self.cpu_milli};memory={self.memory_mib};"
            f"gpu={self.num_gpu};gpu_milli={self.gpu_milli:g}"
        )


@dataclass(frozen=True)
class KubeTraceDataset:
    nodes: tuple[KubeTraceNode, ...]
    pods: tuple[KubeTracePod, ...]
    quarantined: tuple[dict[str, Any], ...]
    node_file: str
    pod_file: str

    def parser_report(self) -> dict[str, Any]:
        by_file = Counter(item["file"] for item in self.quarantined)
        return {
            "node_file": self.node_file,
            "pod_file": self.pod_file,
            "node_rows": len(self.nodes),
            "pod_rows": len(self.pods),
            "accepted_rows": len(self.nodes) + len(self.pods),
            "quarantined_rows": len(self.quarantined),
            "quarantined_by_file": dict(sorted(by_file.items())),
            "quarantined": list(self.quarantined),
        }


def _normalise_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _column_map(fieldnames: Optional[list[str]], aliases: Mapping[str, tuple[str, ...]], path: Path) -> dict[str, str]:
    if not fieldnames:
        raise ValueError(f"{path}: CSV must include a header row")
    normalised = {_normalise_header(field): field for field in fieldnames}
    result: dict[str, str] = {}
    for canonical, choices in aliases.items():
        for choice in choices:
            if choice in normalised:
                result[canonical] = normalised[choice]
                break
    return result


def _raw(row: Mapping[str, str], columns: Mapping[str, str], name: str) -> str:
    column = columns.get(name)
    return (row.get(column, "") if column else "").strip()


def _required_columns(columns: Mapping[str, str], names: Iterable[str], path: Path) -> None:
    missing = [name for name in names if name not in columns]
    if missing:
        raise ValueError(f"{path}: CSV is missing required columns: {', '.join(missing)}")


def _integer(raw: str, field: str, *, allow_blank: bool = False) -> int:
    if not raw and allow_blank:
        return 0
    if not raw:
        raise ValueError(f"{field} is required")
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if not math.isfinite(value) or not value.is_integer():
        raise ValueError(f"{field} must be an integer")
    value_int = int(value)
    if value_int < 0:
        raise ValueError(f"{field} must be >= 0")
    return value_int


def _number(raw: str, field: str, *, allow_blank: bool = False) -> float:
    if not raw and allow_blank:
        return 0.0
    if not raw:
        raise ValueError(f"{field} is required")
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field} must be finite and >= 0")
    return value


def _timestamp(raw: str, field: str, *, allow_blank: bool = False) -> Optional[datetime]:
    if not raw and allow_blank:
        return None
    if not raw:
        raise ValueError(f"{field} is required")
    try:
        numeric = float(raw)
        if math.isfinite(numeric):
            # Alibaba exports are commonly Unix seconds; accept milliseconds too.
            if abs(numeric) >= 100_000_000_000:
                numeric /= 1000.0
            return datetime.fromtimestamp(numeric, tz=timezone.utc)
    except ValueError:
        pass
    candidate = raw.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(raw.strip(), fmt)
                break
            except ValueError:
                parsed = None
        if parsed is None:
            raise ValueError(f"{field} must be ISO-8601 or Unix timestamp")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _gpu_types(raw: str) -> tuple[str, ...]:
    if not raw or raw.lower() in {"none", "any", "-", "null"}:
        return ()
    return tuple(dict.fromkeys(part.strip() for part in re.split(r"[|,;]", raw) if part.strip()))


def _qos_priority(qos: str, overrides: Mapping[str, int]) -> int:
    normalised = qos.strip().lower().replace("_", "-")
    normalised_overrides = {
        str(name).strip().lower().replace("_", "-"): int(priority)
        for name, priority in overrides.items()
    }
    if normalised in normalised_overrides:
        return normalised_overrides[normalised]
    try:
        return int(float(normalised))
    except ValueError:
        return 0


def _quarantine(file_name: str, row_number: int, reason: str) -> dict[str, Any]:
    return {"file": file_name, "row": row_number, "reason": reason}


def load_kube_trace(
    node_csv: Path | str,
    pod_csv: Path | str,
    *,
    qos_priorities: Mapping[str, int] | None = None,
) -> KubeTraceDataset:
    """Parse node/pod CSVs and quarantine malformed rows independently."""
    node_path = Path(node_csv)
    pod_path = Path(pod_csv)
    priorities = {**DEFAULT_QOS_PRIORITIES, **(qos_priorities or {})}
    quarantined: list[dict[str, Any]] = []

    with node_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = _column_map(reader.fieldnames, NODE_ALIASES, node_path)
        _required_columns(columns, ("node_id", "cpu_milli", "memory_mib", "gpu_count", "model"), node_path)
        nodes: list[KubeTraceNode] = []
        seen_nodes: set[str] = set()
        for row_number, row in enumerate(reader, start=2):
            try:
                node_id = _raw(row, columns, "node_id")
                if not node_id:
                    raise ValueError("node_id is required")
                if node_id in seen_nodes:
                    raise ValueError(f"duplicate node_id {node_id!r}")
                node = KubeTraceNode(
                    node_id=node_id,
                    cpu_milli=_integer(_raw(row, columns, "cpu_milli"), "cpu_milli"),
                    memory_mib=_integer(_raw(row, columns, "memory_mib"), "memory_mib"),
                    gpu_count=_integer(_raw(row, columns, "gpu_count"), "gpu_count"),
                    model=_raw(row, columns, "model") or "unknown",
                    row_number=row_number,
                )
                seen_nodes.add(node_id)
                nodes.append(node)
            except ValueError as exc:
                quarantined.append(_quarantine(node_path.name, row_number, str(exc)))

    with pod_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = _column_map(reader.fieldnames, POD_ALIASES, pod_path)
        _required_columns(
            columns,
            (
                "pod_id",
                "cpu_milli",
                "memory_mib",
                "num_gpu",
                "gpu_milli",
                "gpu_spec",
                "qos",
                "creation_time",
                "scheduled_time",
                "deletion_time",
            ),
            pod_path,
        )
        pods: list[KubeTracePod] = []
        seen_pods: set[str] = set()
        for row_number, row in enumerate(reader, start=2):
            try:
                pod_id = _raw(row, columns, "pod_id")
                if not pod_id:
                    raise ValueError("pod_id is required")
                if pod_id in seen_pods:
                    raise ValueError(f"duplicate pod_id {pod_id!r}")
                creation = _timestamp(_raw(row, columns, "creation_time"), "creation_time")
                scheduled = _timestamp(
                    _raw(row, columns, "scheduled_time"), "scheduled_time", allow_blank=True
                )
                deletion = _timestamp(
                    _raw(row, columns, "deletion_time"), "deletion_time", allow_blank=True
                )
                assert creation is not None
                if scheduled is not None and scheduled < creation:
                    raise ValueError("scheduled_time precedes creation_time")
                if deletion is not None and deletion < creation:
                    raise ValueError("deletion_time precedes creation_time")
                if scheduled is not None and deletion is not None and scheduled > deletion:
                    raise ValueError("scheduled_time follows deletion_time")
                qos = _raw(row, columns, "qos") or "unknown"
                actual_node_id = _raw(row, columns, "actual_node_id") or None
                pod = KubeTracePod(
                    pod_id=pod_id,
                    workload_id=_raw(row, columns, "workload_id") or pod_id,
                    cpu_milli=_integer(_raw(row, columns, "cpu_milli"), "cpu_milli"),
                    memory_mib=_integer(_raw(row, columns, "memory_mib"), "memory_mib"),
                    num_gpu=_integer(_raw(row, columns, "num_gpu"), "num_gpu", allow_blank=True),
                    gpu_milli=_number(_raw(row, columns, "gpu_milli"), "gpu_milli", allow_blank=True),
                    gpu_types=_gpu_types(_raw(row, columns, "gpu_spec")),
                    qos=qos,
                    priority=_qos_priority(qos, priorities),
                    creation_time=creation,
                    scheduled_time=scheduled,
                    deletion_time=deletion,
                    actual_node_id=actual_node_id,
                    row_number=row_number,
                )
                seen_pods.add(pod_id)
                pods.append(pod)
            except (AssertionError, ValueError) as exc:
                quarantined.append(_quarantine(pod_path.name, row_number, str(exc)))

    if not nodes:
        raise ValueError("node trace contains no valid rows")
    if not pods:
        raise ValueError("pod trace contains no valid rows")
    return KubeTraceDataset(
        nodes=tuple(nodes),
        pods=tuple(sorted(pods, key=lambda pod: (pod.creation_time, pod.row_number))),
        quarantined=tuple(quarantined),
        node_file=str(node_path),
        pod_file=str(pod_path),
    )


def _seconds_since(origin: datetime, value: Optional[datetime]) -> Optional[float]:
    return None if value is None else (value - origin).total_seconds()


def _percentile(values: Iterable[float], fraction: float) -> Optional[float]:
    ordered = sorted(values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return round(ordered[0], 6)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    value = ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return round(value, 6)


def _stats(values: Iterable[float]) -> dict[str, Any]:
    values = list(values)
    return {
        "count": len(values),
        "p50_s": _percentile(values, 0.50),
        "p95_s": _percentile(values, 0.95),
        "p99_s": _percentile(values, 0.99),
    }


def _group_stats(rows: Iterable[dict[str, Any]], key: str, wait_key: str) -> dict[str, Any]:
    groups: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        wait = row.get(wait_key)
        if wait is not None:
            groups[str(row[key])].append(float(wait))
    return {name: _stats(values) for name, values in sorted(groups.items())}


def replay_kube_trace(
    dataset: KubeTraceDataset,
    *,
    backoff_duration_s: float = 10.0,
    max_backoff_retries: int = 1,
    qos_priorities: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Replay creation/deletion events through the Phase A scheduler."""
    if not dataset.pods:
        raise ValueError("cannot replay an empty pod trace")
    origin = min(pod.creation_time for pod in dataset.pods)
    nodes = [
        KubeNode(
            node_id=node.node_id,
            cpu_capacity_milli=node.cpu_milli,
            memory_capacity_mib=node.memory_mib,
            gpu_capacity=node.gpu_count,
            gpu_type=node.model,
        )
        for node in dataset.nodes
    ]
    engine = KubeSchedulerEngine(
        max_nodes=len(nodes),
        node_cpu_milli=1,
        node_memory_mib=1,
        node_gpu_count=0,
        backoff_duration_s=backoff_duration_s,
        max_backoff_retries=max_backoff_retries,
        node_inventory=nodes,
    )

    relative_creation = {
        pod.pod_id: _seconds_since(origin, pod.creation_time) or 0.0
        for pod in dataset.pods
    }
    relative_deletion = {
        pod.pod_id: _seconds_since(origin, pod.deletion_time)
        for pod in dataset.pods
    }
    pod_by_id = {pod.pod_id: pod for pod in dataset.pods}
    pending = list(dataset.pods)
    pending_index = 0
    initial_times = {
        relative_creation[pod.pod_id]
        for pod in dataset.pods
    }
    initial_times.update(
        value for value in relative_deletion.values() if value is not None
    )
    times: list[tuple[float, int]] = []
    sequence = 0
    for value in sorted(initial_times):
        heapq.heappush(times, (value, sequence))
        sequence += 1
    all_events: list[Any] = []
    while times:
        sim_time, _ = heapq.heappop(times)
        while pending_index < len(pending) and relative_creation[pending[pending_index].pod_id] <= sim_time:
            trace_pod = pending[pending_index]
            deletion = relative_deletion[trace_pod.pod_id]
            duration = (
                max(0.0, deletion - relative_creation[trace_pod.pod_id])
                if deletion is not None
                else 1_000_000_000.0
            )
            all_events.extend(engine.submit(KubePod(
                pod_id=trace_pod.pod_id,
                workload_id=trace_pod.workload_id,
                created_at=relative_creation[trace_pod.pod_id],
                enqueue_time=relative_creation[trace_pod.pod_id],
                priority=trace_pod.priority,
                cpu_milli=trace_pod.cpu_milli,
                memory_mib=trace_pod.memory_mib,
                gpu_count=trace_pod.replay_gpu_count,
                duration_s=duration,
                hardware_profile_id=f"trace:{trace_pod.gpu_shape}",
                gpu_types=trace_pod.gpu_types,
                completion_time=deletion,
            )))
            pending_index += 1

        # A zero-duration backoff can require another scheduler pass at the
        # same timestamp. The loop terminates because retry limits are finite.
        while True:
            scheduler_tick = engine.tick(sim_time)
            all_events.extend(scheduler_tick.events)
            wakeup = engine.next_wakeup_time
            if wakeup is not None and wakeup <= sim_time:
                continue
            if wakeup is not None:
                heapq.heappush(times, (wakeup, sequence))
                sequence += 1
            break

    node_selected: dict[str, float] = {}
    event_by_pod: dict[str, list[Any]] = defaultdict(list)
    for event in all_events:
        event_by_pod[event.pod_id].append(event)
        if event.stage == "node_selected" and event.pod_id not in node_selected:
            node_selected[event.pod_id] = event.timestamp

    qos_override = {**DEFAULT_QOS_PRIORITIES, **(qos_priorities or {})}
    pod_rows: list[dict[str, Any]] = []
    for trace_pod in dataset.pods:
        actual_time = _seconds_since(origin, trace_pod.scheduled_time)
        simulated_time = node_selected.get(trace_pod.pod_id)
        actual_wait = (
            actual_time - relative_creation[trace_pod.pod_id]
            if actual_time is not None else None
        )
        simulated_wait = (
            simulated_time - relative_creation[trace_pod.pod_id]
            if simulated_time is not None else None
        )
        stages = [event.stage for event in event_by_pod[trace_pod.pod_id]]
        simulated_node = next(
            (event.node_id for event in event_by_pod[trace_pod.pod_id] if event.stage == "node_selected"),
            None,
        )
        pod_rows.append({
            "pod_id": trace_pod.pod_id,
            "workload_id": trace_pod.workload_id,
            "qos": trace_pod.qos,
            "priority": _qos_priority(trace_pod.qos, qos_override),
            "gpu_shape": trace_pod.gpu_shape,
            "resource_shape": trace_pod.resource_shape,
            "actual_node_id": trace_pod.actual_node_id,
            "simulated_node_id": simulated_node,
            "actual_scheduled": trace_pod.scheduled_time is not None,
            "simulated_scheduled": simulated_time is not None,
            "actual_wait_s": None if actual_wait is None else round(actual_wait, 6),
            "simulated_wait_s": None if simulated_wait is None else round(simulated_wait, 6),
            "wait_delta_s": (
                None if actual_wait is None or simulated_wait is None
                else round(simulated_wait - actual_wait, 6)
            ),
            "simulated_unschedulable": "unschedulable_entered" in stages,
            "simulated_expired": "pod_expired" in stages,
            "fractional_gpu_request": trace_pod.fractional_gpu_request,
            "gpu_milli": trace_pod.gpu_milli,
            "events": [
                {
                    "stage": event.stage,
                    "timestamp_s": round(event.timestamp, 6),
                    "node_id": event.node_id,
                    "reason": event.reason,
                    "attempt": event.attempt,
                }
                for event in event_by_pod[trace_pod.pod_id]
            ],
        })

    actual_scheduled = sum(row["actual_scheduled"] for row in pod_rows)
    simulated_scheduled = sum(row["simulated_scheduled"] for row in pod_rows)
    both_scheduled = sum(
        row["actual_scheduled"] and row["simulated_scheduled"] for row in pod_rows
    )
    placement_comparable = sum(
        row["actual_node_id"] is not None for row in pod_rows
    )
    placement_mismatch = sum(
        row["actual_node_id"] is not None
        and row["simulated_node_id"] is not None
        and row["actual_node_id"] != row["simulated_node_id"]
        for row in pod_rows
    )
    workload_sizes = Counter(row["workload_id"] for row in pod_rows)
    fractional_count = sum(row["fractional_gpu_request"] for row in pod_rows)
    limitations = {
        "integer_gpu_counts": {
            "affected_pods": fractional_count,
            "description": "gpu_milli requests are conservatively rounded up to integer GPUs",
        },
        "gang_admission": {
            "affected_pods": sum(
                workload_sizes[row["workload_id"]] > 1 for row in pod_rows
            ),
            "description": "multi-pod workloads are scheduled independently",
        },
        "quota_borrowing": {
            "affected_pods": None,
            "status": "not_observable_from_trace",
            "description": "the CSVs do not declare tenant quota or borrowing policy",
        },
        "preemption": {
            "affected_pods": None,
            "status": "not_observable_from_trace",
            "description": "Phase A does not preempt lower-priority running pods",
        },
    }
    return {
        "schema_version": "kube-trace-replay-v1",
        "origin": origin.isoformat(),
        "input": dataset.parser_report(),
        "replay": {
            "node_count": len(dataset.nodes),
            "pod_count": len(dataset.pods),
            "backoff_duration_s": backoff_duration_s,
            "max_backoff_retries": max_backoff_retries,
            "gpu_milli_policy": "ceil_to_integer_gpu",
        },
        "queue_wait": {
            "actual": _stats(row["actual_wait_s"] for row in pod_rows if row["actual_wait_s"] is not None),
            "simulated": _stats(row["simulated_wait_s"] for row in pod_rows if row["simulated_wait_s"] is not None),
            "by_qos": {
                "actual": _group_stats(pod_rows, "qos", "actual_wait_s"),
                "simulated": _group_stats(pod_rows, "qos", "simulated_wait_s"),
            },
            "by_gpu_shape": {
                "actual": _group_stats(pod_rows, "gpu_shape", "actual_wait_s"),
                "simulated": _group_stats(pod_rows, "gpu_shape", "simulated_wait_s"),
            },
            "by_resource_shape": {
                "actual": _group_stats(pod_rows, "resource_shape", "actual_wait_s"),
                "simulated": _group_stats(pod_rows, "resource_shape", "simulated_wait_s"),
            },
        },
        "placement": {
            "actual_scheduled": actual_scheduled,
            "simulated_scheduled": simulated_scheduled,
            "both_scheduled": both_scheduled,
            "actual_scheduled_simulated_unschedulable": sum(
                row["actual_scheduled"] and not row["simulated_scheduled"] for row in pod_rows
            ),
            "actual_unscheduled_simulated_scheduled": sum(
                not row["actual_scheduled"] and row["simulated_scheduled"] for row in pod_rows
            ),
            "both_unscheduled": sum(
                not row["actual_scheduled"] and not row["simulated_scheduled"] for row in pod_rows
            ),
            "actual_node_comparison": (
                "available" if placement_comparable else "not_available_in_pod_csv"
            ),
            "node_ids_compared": placement_comparable,
            "node_id_mismatches": placement_mismatch,
        },
        "limitations": limitations,
        "scheduler_event_count": len(all_events),
        "scheduler_events": [
            {
                "event_id": event.event_id,
                "pod_id": event.pod_id,
                "workload_id": event.workload_id,
                "stage": event.stage,
                "timestamp_s": round(event.timestamp, 6),
                "node_id": event.node_id,
                "reason": event.reason,
                "attempt": event.attempt,
            }
            for event in all_events
        ],
        "pods": pod_rows,
    }


def _parse_qos_overrides(values: list[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"--qos-priority must use NAME=INTEGER, got {value!r}")
        name, priority = value.split("=", 1)
        result[name.strip().lower().replace("_", "-")] = int(priority)
    return result


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nodes", required=True, type=Path, help="node inventory CSV")
    parser.add_argument("--pods", required=True, type=Path, help="pod/task trace CSV")
    parser.add_argument("--output", type=Path, help="write JSON report here; stdout otherwise")
    parser.add_argument("--backoff-duration-s", type=float, default=10.0)
    parser.add_argument("--max-backoff-retries", type=int, default=1)
    parser.add_argument(
        "--qos-priority",
        action="append",
        default=[],
        metavar="NAME=INTEGER",
        help="override a QoS-to-priority mapping; may be repeated",
    )
    args = parser.parse_args(argv)
    try:
        priorities = _parse_qos_overrides(args.qos_priority)
        dataset = load_kube_trace(args.nodes, args.pods, qos_priorities=priorities)
        report = replay_kube_trace(
            dataset,
            backoff_duration_s=args.backoff_duration_s,
            max_backoff_retries=args.max_backoff_retries,
            qos_priorities=priorities,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())