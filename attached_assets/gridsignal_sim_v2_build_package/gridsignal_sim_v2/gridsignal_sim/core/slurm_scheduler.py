"""Small, deterministic Slurm scheduler model used by the simulator.

This module deliberately has no relationship with a Slurm client.  It is a
clock-driven model, which makes it useful both in scenario tests and when
replaying a scheduler trace.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from core.models import WorkloadClass, WorkloadEventType, WorkloadSignal


class SlurmSchedulerError(ValueError):
    """Base class for caller-correctable scheduler errors."""


class ImpossibleJobError(SlurmSchedulerError):
    """A request cannot be satisfied by the cluster, even when idle."""


class UnknownJobError(SlurmSchedulerError):
    pass


@dataclass(frozen=True)
class SlurmJobSpec:
    job_id: str
    arrival_time: float = 0.0
    duration: float = 1.0
    node_count: int = 1
    gpus_per_node: int = 0
    cpus_per_node: int = 0
    memory_mb_per_node: int = 0
    gpu_model: Optional[str] = None
    partition: Optional[str] = None
    features: frozenset[str] = frozenset()
    priority: float = 0.0
    qos: str = "normal"
    qos_weight: float = 1.0
    fair_share_usage: float = 0.0
    dependencies: tuple[str, ...] = ()
    reservation: Optional[str] = None
    hardware_profile_id: str = "slurm"
    workload_class: WorkloadClass = WorkloadClass.TRAINING
    site_id: str = "slurm-site"
    tenant_id: Optional[str] = None
    # Submission metadata only.  The simulator never shells out to execute it.
    command: Optional[str] = None
    environment: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.node_count < 1 or self.duration < 0:
            raise ImpossibleJobError("node_count must be positive and duration non-negative")
        if min(self.gpus_per_node, self.cpus_per_node, self.memory_mb_per_node) < 0:
            raise ImpossibleJobError("resource requests cannot be negative")
        object.__setattr__(self, "features", frozenset(self.features))


@dataclass(frozen=True)
class SlurmNode:
    node_id: str
    partition: Optional[str] = None
    gpus: int = 0
    gpu_model: Optional[str] = None
    cpus: int = 0
    memory_mb: int = 0
    features: frozenset[str] = frozenset()


@dataclass(frozen=True)
class SlurmAllocation:
    job_id: str
    node_ids: tuple[str, ...]
    start_time: float
    end_time: float
    gpus: int = 0
    cpus: int = 0
    memory_mb: int = 0


@dataclass(frozen=True)
class SlurmJobSummary:
    job_id: str
    state: str
    arrival_time: float
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    allocation: Optional[SlurmAllocation] = None
    reason: Optional[str] = None
    command: Optional[str] = None


@dataclass(frozen=True)
class SlurmMetrics:
    timestamp: float
    queued: int
    running: int
    completed: int
    cancelled: int
    allocated_nodes: int
    allocated_gpus: int
    allocated_cpus: int
    allocated_memory_mb: int


class SlurmSchedulerEngine:
    """Deterministic, isolated scheduler with an explicit simulated clock."""

    def __init__(
        self,
        nodes: Iterable[SlurmNode] = (),
        *,
        qos_weights: Optional[dict[str, float]] = None,
        reservations: Optional[dict[str, object]] = None,
        backfill: bool = True,
    ) -> None:
        self.nodes = tuple(sorted(nodes, key=lambda n: n.node_id))
        self.qos_weights = dict(qos_weights or {})
        self.reservations = dict(reservations or {})
        self.backfill = bool(backfill)
        self._jobs: dict[str, SlurmJobSpec] = {}
        self._state: dict[str, str] = {}
        self._allocations: dict[str, SlurmAllocation] = {}
        self._submitted: dict[str, int] = {}
        self._events: list[WorkloadSignal] = []
        self._times: dict[str, tuple[Optional[float], Optional[float]]] = {}
        self._sequence = 0
        self.time = 0.0

    @property
    def jobs(self) -> dict[str, SlurmJobSummary]:
        return {jid: self.summary(jid) for jid in sorted(self._jobs)}

    @property
    def allocations(self) -> dict[str, SlurmAllocation]:
        return dict(self._allocations)

    def submit(self, spec: SlurmJobSpec, now: Optional[float] = None) -> WorkloadSignal:
        when = spec.arrival_time if now is None else float(now)
        if spec.job_id in self._jobs:
            raise SlurmSchedulerError(f"job {spec.job_id!r} was already submitted")
        if not self._possible(spec):
            raise ImpossibleJobError(f"job {spec.job_id!r} cannot fit any cluster allocation")
        self._jobs[spec.job_id] = spec
        self._state[spec.job_id] = "PENDING"
        self._submitted[spec.job_id] = self._sequence
        self._sequence += 1
        self.time = max(self.time, when)
        event = self._signal(spec, WorkloadEventType.QUEUED, when)
        self._events.append(event)
        return event

    def advance(self, now: float) -> list[WorkloadSignal]:
        if now < self.time:
            raise SlurmSchedulerError("scheduler clock cannot move backwards")
        self.time = float(now)
        emitted: list[WorkloadSignal] = []
        for jid, alloc in sorted(tuple(self._allocations.items()), key=lambda x: (x[1].end_time, x[0])):
            if alloc.end_time <= self.time and self._state[jid] == "RUNNING":
                emitted.append(self._finish(jid, alloc.end_time))
        emitted.extend(self._schedule(self.time))
        self._events.extend(emitted)
        return emitted

    tick = advance

    def cancel(self, job_id: str, now: Optional[float] = None) -> WorkloadSignal:
        if job_id not in self._jobs:
            raise UnknownJobError(job_id)
        if self._state[job_id] in {"COMPLETED", "CANCELLED"}:
            raise SlurmSchedulerError(f"job {job_id!r} is terminal")
        when = self.time if now is None else float(now)
        self.time = max(self.time, when)
        self._allocations.pop(job_id, None)
        self._state[job_id] = "CANCELLED"
        event = self._signal(self._jobs[job_id], WorkloadEventType.CANCELLED, when)
        self._events.append(event)
        return event

    def summary(self, job_id: str) -> SlurmJobSummary:
        if job_id not in self._jobs:
            raise UnknownJobError(job_id)
        spec = self._jobs[job_id]
        alloc = self._allocations.get(job_id)
        start, end = self._times.get(job_id, (None, None))
        return SlurmJobSummary(
            job_id=job_id,
            state=self._state[job_id],
            arrival_time=spec.arrival_time,
            start_time=alloc.start_time if alloc else start,
            end_time=alloc.end_time if alloc else end,
            allocation=alloc,
            reason=self._blocked_reason(spec),
            command=spec.command,
        )

    def snapshot(self) -> tuple[SlurmJobSummary, ...]:
        return tuple(self.summary(j) for j in sorted(self._jobs))

    def metrics(self) -> SlurmMetrics:
        allocs = tuple(self._allocations.values())
        return SlurmMetrics(self.time, sum(v == "PENDING" for v in self._state.values()),
                            sum(v == "RUNNING" for v in self._state.values()),
                            sum(v == "COMPLETED" for v in self._state.values()),
                            sum(v == "CANCELLED" for v in self._state.values()),
                            len({n for a in allocs for n in a.node_ids}),
                            sum(a.gpus for a in allocs), sum(a.cpus for a in allocs),
                            sum(a.memory_mb for a in allocs))

    def events(self) -> tuple[WorkloadSignal, ...]:
        return tuple(self._events)

    def running_snapshot(self) -> tuple[SlurmJobSummary, ...]:
        """Return a stable, allocation-bearing view of currently running jobs."""
        return tuple(self.summary(j) for j in sorted(self._jobs)
                     if self._state[j] == "RUNNING")

    def pending_snapshot(self) -> tuple[SlurmJobSummary, ...]:
        return tuple(self.summary(j) for j in sorted(self._jobs)
                     if self._state[j] == "PENDING")

    def run_until(self, now: float) -> tuple[WorkloadSignal, ...]:
        return tuple(self.advance(now))

    get_metrics = metrics

    def _possible(self, s: SlurmJobSpec) -> bool:
        return len(self._matching_nodes(s)) >= s.node_count

    def _matching_nodes(self, s: SlurmJobSpec) -> list[SlurmNode]:
        return [n for n in self.nodes
                if (not s.partition or n.partition == s.partition)
                and (not s.gpu_model or n.gpu_model == s.gpu_model)
                and n.gpus >= s.gpus_per_node and n.cpus >= s.cpus_per_node
                and n.memory_mb >= s.memory_mb_per_node and s.features <= n.features]

    def _available(self, s: SlurmJobSpec, now: float) -> list[SlurmNode]:
        busy = {n for a in self._allocations.values() for n in a.node_ids}
        return [n for n in self._matching_nodes(s) if n.node_id not in busy
                and self._reservation_ok(s, n.node_id, now)]

    def _reservation_ok(self, s: SlurmJobSpec, node_id: str, now: float) -> bool:
        if not s.reservation:
            return not any(self._reservation_contains(r, node_id, now) for r in self.reservations.values())
        r = self.reservations.get(s.reservation)
        return r is not None and self._reservation_contains(r, node_id, now)

    @staticmethod
    def _reservation_contains(r: object, node_id: str, now: float) -> bool:
        if isinstance(r, tuple) and len(r) == 3:
            start, end, nodes = r
            return node_id in nodes and start <= now <= end
        if isinstance(r, dict):
            nodes = r.get("nodes", ())
            start = r.get("start", r.get("start_time", 0))
            end = r.get("end", r.get("end_time", float("inf")))
        else:
            nodes, start, end = getattr(r, "nodes", ()), getattr(r, "start", 0), getattr(r, "end", float("inf"))
        return node_id in nodes and start <= now <= end

    def _blocked_reason(self, s: SlurmJobSpec) -> Optional[str]:
        for dep in s.dependencies:
            name, _, _ = dep.partition(":")
            if name in self._jobs and self._state[name] in {"PENDING", "RUNNING"}:
                return "Dependency"
            if name not in self._jobs:
                return "DependencyNeverSatisfied"
            if name in self._jobs and name and self._state[name] == "CANCELLED" and dep.startswith("afterok"):
                return "DependencyNeverSatisfied"
        return None

    def _dependency_ready(self, s: SlurmJobSpec, now: float) -> bool:
        for dep in s.dependencies:
            kind, _, tail = dep.partition(":")
            base, _, delay = tail.partition("+")
            if base not in self._jobs:
                return False
            state = self._state[base]
            if kind == "afterok" and state != "COMPLETED": return False
            if kind in {"afterany", "aftercorr"} and state not in {"COMPLETED", "CANCELLED"}: return False
            if kind == "after" and state not in {"RUNNING", "COMPLETED", "CANCELLED"}: return False
            if delay and self.summary(base).end_time is not None and now < self.summary(base).end_time + float(delay):
                return False
        return True

    def _schedule(self, now: float) -> list[WorkloadSignal]:
        out: list[WorkloadSignal] = []
        ordered = sorted((s for s in self._jobs.values() if self._state[s.job_id] == "PENDING"
                          and s.arrival_time <= now),
                         key=lambda s: (-s.priority, -self.qos_weights.get(s.qos, s.qos_weight),
                                        s.fair_share_usage, -(now - s.arrival_time), self._submitted[s.job_id], s.job_id))
        for s in ordered:
            if not self._dependency_ready(s, now):
                continue
            available = self._available(s, now)
            if len(available) < s.node_count:
                # Conservative backfill is intentionally opt-out for simple
                # FIFO/priority demonstrations: once an eligible earlier job
                # cannot fit, later jobs wait rather than using its resources.
                if not self.backfill:
                    break
                continue
            chosen = tuple(n.node_id for n in available[:s.node_count])
            alloc = SlurmAllocation(s.job_id, chosen, now, now + s.duration,
                                    s.gpus_per_node * s.node_count, s.cpus_per_node * s.node_count,
                                    s.memory_mb_per_node * s.node_count)
            self._allocations[s.job_id] = alloc
            self._times[s.job_id] = (now, alloc.end_time)
            self._state[s.job_id] = "RUNNING"
            out.append(self._signal(s, WorkloadEventType.RUNNING, now))
        return out

    def _finish(self, job_id: str, when: float) -> WorkloadSignal:
        s = self._jobs[job_id]
        self._allocations.pop(job_id, None)
        self._times[job_id] = (self._times.get(job_id, (None, None))[0], when)
        self._state[job_id] = "COMPLETED"
        return self._signal(s, WorkloadEventType.JOB_END, when)

    def _signal(self, s: SlurmJobSpec, kind: WorkloadEventType, when: float) -> WorkloadSignal:
        return WorkloadSignal(event_id=f"slurm-{s.job_id}-{kind.value}-{int(when * 1000000)}",
                              job_id=s.job_id, event_type=kind, timestamp=when,
                              hardware_profile_id=s.hardware_profile_id, node_count=s.node_count,
                              workload_class=s.workload_class, site_id=s.site_id,
                              scheduler_type="slurm", scheduler_domain=s.partition,
                              tenant_id=s.tenant_id, gpus_per_unit=s.gpus_per_node or 1)