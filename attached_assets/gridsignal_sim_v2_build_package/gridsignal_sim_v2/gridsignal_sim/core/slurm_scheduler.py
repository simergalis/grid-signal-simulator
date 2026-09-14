"""Small, deterministic Slurm scheduler model used by the simulator.

This module deliberately has no relationship with a Slurm client.  It is a
clock-driven model, which makes it useful both in scenario tests and when
replaying a scheduler trace.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace as dataclass_replace
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
    job_name: Optional[str] = None
    user: str = "simulator"
    account: Optional[str] = None
    time_limit_s: Optional[float] = None
    deadline: Optional[float] = None
    ntasks: int = 1
    cpus_per_task: int = 1
    memory_mb_per_cpu: Optional[int] = None
    tmp_disk_mb: int = 0
    gres: tuple[tuple[str, int], ...] = ()
    topology: Optional[str] = None
    exclusive: bool = False
    oversubscribe: bool = False
    licenses: tuple[tuple[str, int], ...] = ()
    burst_buffer: Optional[str] = None
    burst_buffer_mb: int = 0
    tres_per_job: tuple[tuple[str, float], ...] = ()
    requeue: bool = False
    preemptible: bool = True
    checkpoint_interval_s: Optional[float] = None
    checkpoint_signal_s: Optional[float] = None
    array_start: Optional[int] = None
    array_end: Optional[int] = None
    array_step: int = 1
    array_parent_id: Optional[str] = None
    array_task_id: Optional[int] = None
    array_max_concurrent: Optional[int] = None
    hetero_group_id: Optional[str] = None
    hetero_component: Optional[int] = None
    federation: Optional[str] = None
    cluster: Optional[str] = None

    def __post_init__(self) -> None:
        if self.node_count < 1 or self.duration < 0:
            raise ImpossibleJobError("node_count must be positive and duration non-negative")
        if min(
            self.gpus_per_node,
            self.cpus_per_node,
            self.memory_mb_per_node,
            self.ntasks,
            self.cpus_per_task,
            self.tmp_disk_mb,
            self.burst_buffer_mb,
        ) < 0:
            raise ImpossibleJobError("resource requests cannot be negative")
        if self.ntasks < 1 or self.cpus_per_task < 1:
            raise ImpossibleJobError("ntasks and cpus_per_task must be positive")
        if self.memory_mb_per_cpu is not None and self.memory_mb_per_cpu < 0:
            raise ImpossibleJobError("memory_mb_per_cpu cannot be negative")
        if self.time_limit_s is not None and self.time_limit_s < 0:
            raise ImpossibleJobError("time_limit_s cannot be negative")
        if self.deadline is not None and self.deadline < self.arrival_time:
            raise ImpossibleJobError("deadline cannot precede arrival_time")
        if self.checkpoint_interval_s is not None and self.checkpoint_interval_s <= 0:
            raise ImpossibleJobError("checkpoint_interval_s must be positive")
        if self.checkpoint_signal_s is not None and self.checkpoint_signal_s < 0:
            raise ImpossibleJobError("checkpoint_signal_s cannot be negative")
        if self.array_step <= 0:
            raise ImpossibleJobError("array_step must be positive")
        if (self.array_start is None) != (self.array_end is None):
            raise ImpossibleJobError("array_start and array_end must be supplied together")
        if self.array_start is not None and self.array_end is not None and self.array_end < self.array_start:
            raise ImpossibleJobError("array_end must not precede array_start")
        object.__setattr__(self, "features", frozenset(self.features))
        object.__setattr__(self, "gres", tuple(sorted((str(k), int(v)) for k, v in dict(self.gres).items())))
        object.__setattr__(self, "licenses", tuple(sorted((str(k), int(v)) for k, v in dict(self.licenses).items())))
        object.__setattr__(self, "tres_per_job", tuple(sorted((str(k), float(v)) for k, v in dict(self.tres_per_job).items())))


@dataclass(frozen=True)
class SlurmNode:
    node_id: str
    partition: Optional[str] = None
    gpus: int = 0
    gpu_model: Optional[str] = None
    cpus: int = 0
    memory_mb: int = 0
    features: frozenset[str] = frozenset()
    state: str = "IDLE"
    topology: tuple[tuple[str, str], ...] = ()
    gres: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "features", frozenset(self.features))
        object.__setattr__(self, "topology", tuple(sorted((str(k), str(v)) for k, v in dict(self.topology).items())))
        object.__setattr__(self, "gres", tuple(sorted((str(k), int(v)) for k, v in dict(self.gres).items())))


@dataclass(frozen=True)
class SlurmAllocation:
    job_id: str
    node_ids: tuple[str, ...]
    start_time: float
    end_time: float
    gpus: int = 0
    cpus: int = 0
    memory_mb: int = 0
    gpus_per_node: int = 0
    cpus_per_node: int = 0
    memory_mb_per_node: int = 0
    exclusive: bool = False
    licenses: tuple[tuple[str, int], ...] = ()
    burst_buffer: Optional[str] = None
    burst_buffer_mb: int = 0


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
    array_parent_id: Optional[str] = None
    array_task_id: Optional[int] = None
    preemptions: int = 0


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
    preempted: int = 0
    requeued: int = 0
    allocated_licenses: dict[str, int] = field(default_factory=dict)
    burst_buffer_mb: int = 0


class SlurmSchedulerEngine:
    """Deterministic, isolated scheduler with an explicit simulated clock."""

    def __init__(
        self,
        nodes: Iterable[SlurmNode] = (),
        *,
        qos_weights: Optional[dict[str, float]] = None,
        reservations: Optional[dict[str, object]] = None,
        backfill: bool = True,
        config: Optional[dict[str, object]] = None,
    ) -> None:
        self.nodes = tuple(sorted(nodes, key=lambda n: n.node_id))
        self.qos_weights = dict(qos_weights or {})
        self.reservations = dict(reservations or {})
        self.backfill = bool(backfill)
        self.config = dict(config or {})
        self.cluster_name = str(self.config.get("cluster_name", "sim-cluster"))
        self.preempt_mode = str(self.config.get("preempt_mode", "off"))
        self._partitions = {
            str(policy.get("name")): policy
            for policy in self.config.get("partitions", [])
            if isinstance(policy, dict)
        }
        self._qos_policies = {
            str(policy.get("name")): policy
            for policy in self.config.get("qos", [])
            if isinstance(policy, dict)
        }
        self._account_policies = {
            str(policy.get("name")): policy
            for policy in self.config.get("accounts", [])
            if isinstance(policy, dict)
        }
        self._license_capacity = {
            str(license_.get("name")): int(license_.get("count", 0))
            for license_ in self.config.get("licenses", [])
            if isinstance(license_, dict)
        }
        self._license_used: dict[str, int] = {}
        self._burst_buffers = {
            str(buffer.get("name")): int(buffer.get("capacity_mb", 0))
            for buffer in self.config.get("burst_buffers", [])
            if isinstance(buffer, dict)
        }
        self._burst_buffer_used: dict[str, int] = {}
        self._jobs: dict[str, SlurmJobSpec] = {}
        self._state: dict[str, str] = {}
        self._allocations: dict[str, SlurmAllocation] = {}
        self._submitted: dict[str, int] = {}
        self._events: list[WorkloadSignal] = []
        self._times: dict[str, tuple[Optional[float], Optional[float]]] = {}
        self._preemptions: dict[str, int] = {}
        self._requeued = 0
        self._checkpoint_cursor: dict[str, float] = {}
        self._fairshare_usage: dict[str, float] = {}
        self._sequence = 0
        self.time = 0.0

    @property
    def jobs(self) -> dict[str, SlurmJobSummary]:
        return {jid: self.summary(jid) for jid in sorted(self._jobs)}

    @property
    def allocations(self) -> dict[str, SlurmAllocation]:
        return dict(self._allocations)

    def submit_array(
        self,
        spec: SlurmJobSpec,
        *,
        start: int,
        end: int,
        step: int = 1,
        max_concurrent: Optional[int] = None,
        now: Optional[float] = None,
    ) -> tuple[WorkloadSignal, ...]:
        """Expand and queue a deterministic job array."""
        if step <= 0 or end < start:
            raise SlurmSchedulerError("invalid job array range")
        signals = []
        parent_id = spec.array_parent_id or spec.job_id
        for task_id in range(start, end + 1, step):
            task_spec = dataclass_replace(
                spec,
                job_id=f"{parent_id}_{task_id}",
                array_parent_id=parent_id,
                array_task_id=task_id,
                array_max_concurrent=max_concurrent,
            )
            signals.append(self.submit(task_spec, now=now))
        return tuple(signals)

    def submit(self, spec: SlurmJobSpec, now: Optional[float] = None) -> WorkloadSignal:
        when = spec.arrival_time if now is None else float(now)
        if spec.job_id in self._jobs:
            raise SlurmSchedulerError(f"job {spec.job_id!r} was already submitted")
        if not self._possible(spec):
            raise ImpossibleJobError(f"job {spec.job_id!r} cannot fit any cluster allocation")
        self._validate_submission_policy(spec)
        self._jobs[spec.job_id] = spec
        self._state[spec.job_id] = "PENDING"
        self._submitted[spec.job_id] = self._sequence
        self._sequence += 1
        self.time = max(self.time, when)
        event = self._signal(spec, WorkloadEventType.QUEUED, when)
        self._events.append(event)
        return event

    def _validate_submission_policy(self, spec: SlurmJobSpec) -> None:
        if spec.cluster and spec.cluster != self.cluster_name:
            raise SlurmSchedulerError(
                f"job {spec.job_id!r} targets cluster {spec.cluster!r}, "
                f"but this scheduler is {self.cluster_name!r}"
            )
        if spec.federation and spec.federation != self.cluster_name:
            federation = self.config.get("federation") or {}
            siblings = federation.get("sibling_clusters", []) if isinstance(federation, dict) else []
            if not federation or spec.federation not in {self.cluster_name, *siblings}:
                raise SlurmSchedulerError(
                    f"job {spec.job_id!r} targets an unknown federation cluster"
                )
        partition = self._partitions.get(spec.partition or "")
        if partition:
            if partition.get("state", "UP") != "UP":
                raise SlurmSchedulerError(f"partition {spec.partition!r} is not available")
            allowed_accounts = set(partition.get("allow_accounts", []))
            if allowed_accounts and (spec.account or "") not in allowed_accounts:
                raise SlurmSchedulerError(f"account is not allowed in partition {spec.partition!r}")
            allowed_qos = set(partition.get("allow_qos", []))
            if allowed_qos and spec.qos not in allowed_qos:
                raise SlurmSchedulerError(f"QOS {spec.qos!r} is not allowed in partition {spec.partition!r}")
            max_time = partition.get("max_time_s")
            if max_time is not None and self._effective_duration(spec) > float(max_time):
                raise SlurmSchedulerError(f"job exceeds partition {spec.partition!r} time limit")
        qos = self._qos_policies.get(spec.qos)
        if qos:
            max_wall = qos.get("max_wall_time_s")
            if max_wall is not None and self._effective_duration(spec) > float(max_wall):
                raise SlurmSchedulerError(f"job exceeds QOS {spec.qos!r} time limit")
            allowed = set(qos.get("allowed_accounts", []))
            if allowed and (spec.account or "") not in allowed:
                raise SlurmSchedulerError(f"account is not allowed by QOS {spec.qos!r}")
        account = self._account_policies.get(spec.account or "")
        if account:
            allowed_qos = set(account.get("allowed_qos", []))
            if allowed_qos and spec.qos not in allowed_qos:
                raise SlurmSchedulerError(f"QOS {spec.qos!r} is not allowed for account {spec.account!r}")
        for dependency in spec.dependencies:
            kind, separator, target = dependency.partition(":")
            if not separator or kind not in {"afterok", "afterany", "aftercorr", "after"} or not target:
                raise SlurmSchedulerError(f"unsupported dependency expression {dependency!r}")
        if spec.burst_buffer and spec.burst_buffer not in self._burst_buffers:
            raise SlurmSchedulerError(f"unknown burst buffer {spec.burst_buffer!r}")
        if self._license_capacity:
            unknown = {name for name, _ in spec.licenses if name not in self._license_capacity}
            if unknown:
                raise SlurmSchedulerError(f"unknown license(s): {sorted(unknown)!r}")

    @staticmethod
    def _effective_duration(spec: SlurmJobSpec) -> float:
        return float(spec.time_limit_s if spec.time_limit_s is not None else spec.duration)

    @staticmethod
    def _requested_resources(spec: SlurmJobSpec) -> tuple[int, int, int]:
        gres = dict(spec.gres)
        gpus = spec.gpus_per_node or gres.get("gpu", 0)
        if not gpus:
            gpus = sum(value for key, value in gres.items() if key.startswith("gpu:"))
        tasks_per_node = (spec.ntasks + spec.node_count - 1) // spec.node_count
        cpus = spec.cpus_per_node or tasks_per_node * spec.cpus_per_task
        memory = spec.memory_mb_per_node
        if not memory and spec.memory_mb_per_cpu is not None:
            memory = tasks_per_node * spec.cpus_per_task * spec.memory_mb_per_cpu
        return int(gpus), int(cpus), int(memory)

    @staticmethod
    def _node_resource_capacity(node: SlurmNode) -> tuple[int, int, int]:
        gres = dict(node.gres)
        gpus = node.gpus or gres.get("gpu", 0)
        if not gpus:
            gpus = sum(value for key, value in gres.items() if key.startswith("gpu:"))
        # Legacy scenario nodes omitted CPU/memory because the previous model
        # treated those dimensions as unconstrained. Preserve that contract
        # while honoring explicit Slurm values.
        cpus = node.cpus if node.cpus > 0 else 10**12
        memory = node.memory_mb if node.memory_mb > 0 else 10**12
        return int(gpus), int(cpus), int(memory)

    def _used_on_node(self, node_id: str) -> tuple[int, int, int, bool]:
        gpus = cpus = memory = 0
        exclusive = False
        for allocation in self._allocations.values():
            if node_id in allocation.node_ids:
                gpus += allocation.gpus_per_node
                cpus += allocation.cpus_per_node
                memory += allocation.memory_mb_per_node
                exclusive = exclusive or allocation.exclusive
        return gpus, cpus, memory, exclusive

    def advance(self, now: float) -> list[WorkloadSignal]:
        if now < self.time:
            raise SlurmSchedulerError("scheduler clock cannot move backwards")
        self.time = float(now)
        emitted: list[WorkloadSignal] = []
        for jid, allocation in sorted(self._allocations.items()):
            spec = self._jobs[jid]
            interval = spec.checkpoint_interval_s
            next_checkpoint = self._checkpoint_cursor.get(jid)
            if interval and next_checkpoint is None:
                next_checkpoint = allocation.start_time + interval
            while (
                interval
                and next_checkpoint is not None
                and next_checkpoint <= self.time
                and next_checkpoint < allocation.end_time
            ):
                emitted.append(self._signal(spec, WorkloadEventType.CHECKPOINT_START, next_checkpoint))
                emitted.append(self._signal(spec, WorkloadEventType.CHECKPOINT_END, next_checkpoint))
                next_checkpoint += interval
            if next_checkpoint is not None:
                self._checkpoint_cursor[jid] = next_checkpoint
        for jid, alloc in sorted(tuple(self._allocations.items()), key=lambda x: (x[1].end_time, x[0])):
            if alloc.end_time <= self.time and self._state[jid] == "RUNNING":
                emitted.append(self._finish(jid, alloc.end_time))
        emitted.extend(self._preempt_for_pending(self.time))
        emitted.extend(self._schedule(self.time))
        self._events.extend(emitted)
        return emitted

    tick = advance

    def cancel(self, job_id: str, now: Optional[float] = None) -> WorkloadSignal:
        if job_id not in self._jobs:
            raise UnknownJobError(job_id)
        if self._state[job_id] in {"COMPLETED", "CANCELLED", "PREEMPTED"}:
            raise SlurmSchedulerError(f"job {job_id!r} is terminal")
        when = self.time if now is None else float(now)
        self.time = max(self.time, when)
        self._allocations.pop(job_id, None)
        self._release_resources(self._jobs[job_id])
        self._state[job_id] = "CANCELLED"
        event = self._signal(self._jobs[job_id], WorkloadEventType.CANCELLED, when)
        self._events.append(event)
        return event

    def _preempt_for_pending(self, now: float) -> list[WorkloadSignal]:
        if self.preempt_mode == "off":
            return []
        emitted: list[WorkloadSignal] = []
        pending = sorted(
            (spec for spec in self._jobs.values() if self._state[spec.job_id] == "PENDING"),
            key=lambda spec: (-spec.priority, spec.job_id),
        )
        for spec in pending:
            if self._available(spec, now):
                continue
            victims = sorted(
                (
                    self._jobs[jid]
                    for jid in self._allocations
                    if self._jobs[jid].preemptible
                    and self._jobs[jid].priority < spec.priority
                ),
                key=lambda candidate: (candidate.priority, candidate.job_id),
            )
            if not victims:
                continue
            victim = victims[0]
            policy = self._qos_policies.get(spec.qos, {})
            mode = str(policy.get("preempt_mode", self.preempt_mode))
            if mode == "off":
                continue
            emitted.append(self._preempt(victim.job_id, now, mode == "requeue"))
            if mode == "requeue":
                emitted.append(self._signal(victim, WorkloadEventType.QUEUED, now))
        return emitted

    def _preempt(self, job_id: str, when: float, requeue: bool) -> WorkloadSignal:
        spec = self._jobs[job_id]
        self._allocations.pop(job_id, None)
        self._release_resources(spec)
        self._preemptions[job_id] = self._preemptions.get(job_id, 0) + 1
        if requeue or spec.requeue:
            self._state[job_id] = "PENDING"
            self._requeued += 1
        else:
            self._state[job_id] = "PREEMPTED"
        return self._signal(spec, WorkloadEventType.CANCELLED, when)

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
            array_parent_id=spec.array_parent_id,
            array_task_id=spec.array_task_id,
            preemptions=self._preemptions.get(job_id, 0),
        )

    def snapshot(self) -> tuple[SlurmJobSummary, ...]:
        return tuple(self.summary(j) for j in sorted(self._jobs))

    def metrics(self) -> SlurmMetrics:
        allocs = tuple(self._allocations.values())
        return SlurmMetrics(
            self.time,
            sum(v == "PENDING" for v in self._state.values()),
            sum(v == "RUNNING" for v in self._state.values()),
            sum(v == "COMPLETED" for v in self._state.values()),
            sum(v == "CANCELLED" for v in self._state.values()),
            len({n for a in allocs for n in a.node_ids}),
            sum(a.gpus for a in allocs),
            sum(a.cpus for a in allocs),
            sum(a.memory_mb for a in allocs),
            preempted=sum(v == "PREEMPTED" for v in self._state.values()),
            requeued=self._requeued,
            allocated_licenses=dict(self._license_used),
            burst_buffer_mb=sum(self._burst_buffer_used.values()),
        )

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
        nodes = self._matching_nodes(s, include_unavailable=True)
        if len(nodes) < s.node_count:
            return False
        gpus, cpus, memory = self._requested_resources(s)
        if any(
            gpus > self._node_resource_capacity(node)[0]
            or cpus > self._node_resource_capacity(node)[1]
            or memory > self._node_resource_capacity(node)[2]
            for node in nodes
        ):
            return False
        for name, amount in s.licenses:
            if self._license_capacity and amount > self._license_capacity.get(name, 0):
                return False
        if s.burst_buffer and s.burst_buffer_mb > self._burst_buffers.get(s.burst_buffer, 0):
            return False
        return True

    def _matching_nodes(
        self,
        s: SlurmJobSpec,
        *,
        include_unavailable: bool = False,
    ) -> list[SlurmNode]:
        partition = self._partitions.get(s.partition or "")
        allowed_nodes = set(partition.get("nodes", [])) if partition else set()
        gpus, cpus, memory = self._requested_resources(s)
        return [
            node
            for node in self.nodes
            if (not s.partition or node.partition == s.partition)
            and (not allowed_nodes or node.node_id in allowed_nodes)
            and (include_unavailable or node.state in {"IDLE", "MIXED"})
            and (not s.gpu_model or node.gpu_model == s.gpu_model)
            and gpus <= self._node_resource_capacity(node)[0]
            and cpus <= self._node_resource_capacity(node)[1]
            and memory <= self._node_resource_capacity(node)[2]
            and s.features <= node.features
            and (
                not s.topology
                or dict(node.topology).get("name") == s.topology
                or s.topology in node.features
            )
        ]

    def _available(
        self,
        s: SlurmJobSpec,
        now: float,
        blocked_nodes: frozenset[str] = frozenset(),
    ) -> list[SlurmNode]:
        gpus, cpus, memory = self._requested_resources(s)
        available = []
        for node in self._matching_nodes(s):
            if node.node_id in blocked_nodes:
                continue
            used_gpus, used_cpus, used_memory, used_exclusive = self._used_on_node(node.node_id)
            if used_exclusive or s.exclusive:
                if used_gpus or used_cpus or used_memory:
                    continue
            if used_gpus + gpus > self._node_resource_capacity(node)[0]:
                continue
            if used_cpus + cpus > self._node_resource_capacity(node)[1]:
                continue
            if used_memory + memory > self._node_resource_capacity(node)[2]:
                continue
            if not self._reservation_ok(s, node.node_id, now):
                continue
            available.append(node)
        if not self._licenses_available(s) or not self._burst_buffer_available(s):
            return []
        return available

    def _licenses_available(self, spec: SlurmJobSpec) -> bool:
        return all(
            self._license_used.get(name, 0) + amount <= self._license_capacity.get(name, 0)
            for name, amount in spec.licenses
        )

    def _burst_buffer_available(self, spec: SlurmJobSpec) -> bool:
        if not spec.burst_buffer:
            return spec.burst_buffer_mb == 0
        return (
            self._burst_buffer_used.get(spec.burst_buffer, 0) + spec.burst_buffer_mb
            <= self._burst_buffers.get(spec.burst_buffer, 0)
        )

    def _acquire_resources(self, spec: SlurmJobSpec) -> None:
        for name, amount in spec.licenses:
            self._license_used[name] = self._license_used.get(name, 0) + amount
        if spec.burst_buffer:
            self._burst_buffer_used[spec.burst_buffer] = (
                self._burst_buffer_used.get(spec.burst_buffer, 0) + spec.burst_buffer_mb
            )

    def _release_resources(self, spec: SlurmJobSpec) -> None:
        for name, amount in spec.licenses:
            self._license_used[name] = max(0, self._license_used.get(name, 0) - amount)
        if spec.burst_buffer:
            self._burst_buffer_used[spec.burst_buffer] = max(
                0,
                self._burst_buffer_used.get(spec.burst_buffer, 0) - spec.burst_buffer_mb,
            )

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
                         key=lambda s: (
                             -s.priority * self._qos_priority_factor(s),
                             self._fair_share_key(s),
                             -(now - s.arrival_time),
                             self._submitted[s.job_id],
                             s.job_id,
                         ))
        handled_heterogeneous: set[str] = set()
        for s in ordered:
            if s.hetero_group_id:
                if s.hetero_group_id in handled_heterogeneous:
                    continue
                handled_heterogeneous.add(s.hetero_group_id)
                components = sorted(
                    (
                        candidate
                        for candidate in self._jobs.values()
                        if candidate.hetero_group_id == s.hetero_group_id
                        and self._state[candidate.job_id] == "PENDING"
                    ),
                    key=lambda candidate: (
                        candidate.hetero_component if candidate.hetero_component is not None else 0,
                        candidate.job_id,
                    ),
                )
                if (
                    not components
                    or any(component.arrival_time > now for component in components)
                    or any(not self._dependency_ready(component, now) for component in components)
                ):
                    continue
                chosen_by_component: list[tuple[SlurmJobSpec, tuple[str, ...]]] = []
                blocked_nodes: set[str] = set()
                can_start = True
                for component in components:
                    if self._array_at_capacity(component) or not self._policy_capacity_available(component):
                        can_start = False
                        break
                    available = self._available(component, now, frozenset(blocked_nodes))
                    if len(available) < component.node_count:
                        can_start = False
                        break
                    chosen = tuple(node.node_id for node in available[:component.node_count])
                    blocked_nodes.update(chosen)
                    chosen_by_component.append((component, chosen))
                if not can_start:
                    if not self.backfill:
                        break
                    continue
                for component, chosen in chosen_by_component:
                    out.append(self._start_job(component, chosen, now))
                continue
            if not self._dependency_ready(s, now):
                continue
            if self._array_at_capacity(s):
                continue
            if not self._policy_capacity_available(s):
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
            out.append(self._start_job(s, chosen, now))
        return out

    def _start_job(
        self,
        spec: SlurmJobSpec,
        node_ids: tuple[str, ...],
        now: float,
    ) -> WorkloadSignal:
        gpus, cpus, memory = self._requested_resources(spec)
        allocation = SlurmAllocation(
            job_id=spec.job_id,
            node_ids=node_ids,
            start_time=now,
            end_time=now + self._effective_duration(spec),
            gpus=gpus * spec.node_count,
            cpus=cpus * spec.node_count,
            memory_mb=memory * spec.node_count,
            gpus_per_node=gpus,
            cpus_per_node=cpus,
            memory_mb_per_node=memory,
            exclusive=spec.exclusive,
            licenses=spec.licenses,
            burst_buffer=spec.burst_buffer,
            burst_buffer_mb=spec.burst_buffer_mb,
        )
        self._allocations[spec.job_id] = allocation
        self._acquire_resources(spec)
        self._times[spec.job_id] = (now, allocation.end_time)
        self._checkpoint_cursor.pop(spec.job_id, None)
        self._state[spec.job_id] = "RUNNING"
        owner = spec.account or spec.user
        self._fairshare_usage[owner] = (
            self._fairshare_usage.get(owner, 0.0) + self._effective_duration(spec)
        )
        return self._signal(spec, WorkloadEventType.RUNNING, now)

    def _finish(self, job_id: str, when: float) -> WorkloadSignal:
        s = self._jobs[job_id]
        self._allocations.pop(job_id, None)
        self._release_resources(s)
        self._times[job_id] = (self._times.get(job_id, (None, None))[0], when)
        self._state[job_id] = "COMPLETED"
        return self._signal(s, WorkloadEventType.JOB_END, when)

    def _qos_priority_factor(self, spec: SlurmJobSpec) -> float:
        policy = self._qos_policies.get(spec.qos, {})
        return float(policy.get("priority_factor", self.qos_weights.get(spec.qos, spec.qos_weight)))

    def _fair_share_key(self, spec: SlurmJobSpec) -> float:
        owner = spec.account or spec.user
        policy = self._account_policies.get(owner, {})
        weight = float(policy.get("fairshare_weight", 1.0))
        return (spec.fair_share_usage + self._fairshare_usage.get(owner, 0.0)) / max(weight, 1e-9)

    def _array_at_capacity(self, spec: SlurmJobSpec) -> bool:
        if not spec.array_parent_id or not spec.array_max_concurrent:
            return False
        running = sum(
            1
            for job_id, state in self._state.items()
            if state == "RUNNING"
            and self._jobs[job_id].array_parent_id == spec.array_parent_id
        )
        return running >= spec.array_max_concurrent

    def _policy_capacity_available(self, spec: SlurmJobSpec) -> bool:
        qos = self._qos_policies.get(spec.qos, {})
        account = self._account_policies.get(spec.account or "", {})
        for policy in (qos, account):
            max_jobs = policy.get("max_jobs")
            if max_jobs is not None:
                active = sum(
                    1
                    for job_id, state in self._state.items()
                    if state in {"RUNNING", "PENDING"}
                    and (
                        self._jobs[job_id].qos == spec.qos
                        if policy is qos
                        else (self._jobs[job_id].account or self._jobs[job_id].user) == (spec.account or spec.user)
                    )
                )
                if active > int(max_jobs):
                    return False
            max_tres = policy.get("max_tres", {})
            for tres_name, limit in max_tres.items():
                used = sum(
                    dict(self._jobs[job_id].tres_per_job).get(str(tres_name), 0.0)
                    for job_id, state in self._state.items()
                    if state == "RUNNING"
                    and (
                        self._jobs[job_id].qos == spec.qos
                        if policy is qos
                        else (self._jobs[job_id].account or self._jobs[job_id].user)
                        == (spec.account or spec.user)
                    )
                )
                if used + dict(spec.tres_per_job).get(str(tres_name), 0.0) > float(limit):
                    return False
        return True

    def _signal(self, s: SlurmJobSpec, kind: WorkloadEventType, when: float) -> WorkloadSignal:
        return WorkloadSignal(event_id=f"slurm-{s.job_id}-{kind.value}-{int(when * 1000000)}",
                              job_id=s.job_id, event_type=kind, timestamp=when,
                              hardware_profile_id=s.hardware_profile_id, node_count=s.node_count,
                              workload_class=s.workload_class, site_id=s.site_id,
                              scheduler_type="slurm", scheduler_domain=s.partition,
                              tenant_id=s.tenant_id, gpus_per_unit=s.gpus_per_node or 1)