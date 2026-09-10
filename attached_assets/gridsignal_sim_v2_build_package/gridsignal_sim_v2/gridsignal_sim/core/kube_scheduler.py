"""A small, traceable kube-scheduler-shaped engine for the Kubernetes leg.

This is deliberately Phase A scope:

* one pod is the scheduling unit;
* activeQ, backoffQ, and unschedulablePods are explicit;
* PriorityClass ordering is priority descending, enqueue time ascending;
* placement consumes real CPU, memory, and GPU capacity from node inventory;
* no gang admission, quota, borrowing, or preemption is performed here.

The engine is synchronous so it can run inside ``evaluate_tick``.  It emits
immutable lifecycle events rather than hiding queue transitions in counters.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Optional

from .models import KubeSchedulerEvent


@dataclass
class KubeNode:
    node_id: str
    cpu_capacity_milli: int
    memory_capacity_mib: int
    gpu_capacity: int
    cpu_allocated_milli: int = 0
    memory_allocated_mib: int = 0
    gpu_allocated: int = 0

    def can_fit(self, pod: "KubePod") -> bool:
        return (
            self.cpu_allocated_milli + pod.cpu_milli <= self.cpu_capacity_milli
            and self.memory_allocated_mib + pod.memory_mib <= self.memory_capacity_mib
            and self.gpu_allocated + pod.gpu_count <= self.gpu_capacity
        )

    def allocate(self, pod: "KubePod") -> None:
        if not self.can_fit(pod):
            raise ValueError(f"pod {pod.pod_id} does not fit on node {self.node_id}")
        self.cpu_allocated_milli += pod.cpu_milli
        self.memory_allocated_mib += pod.memory_mib
        self.gpu_allocated += pod.gpu_count

    def release(self, pod: "KubePod") -> None:
        self.cpu_allocated_milli = max(0, self.cpu_allocated_milli - pod.cpu_milli)
        self.memory_allocated_mib = max(0, self.memory_allocated_mib - pod.memory_mib)
        self.gpu_allocated = max(0, self.gpu_allocated - pod.gpu_count)


@dataclass
class KubePod:
    pod_id: str
    workload_id: str
    created_at: float
    enqueue_time: float
    priority: int
    cpu_milli: int
    memory_mib: int
    gpu_count: int
    duration_s: float
    hardware_profile_id: str
    enqueue_sequence: int = 0
    attempts: int = 0
    node_id: Optional[str] = None
    started_at: Optional[float] = None
    ends_at: Optional[float] = None


@dataclass(frozen=True)
class KubeSchedulerTick:
    started_pods: tuple[KubePod, ...] = ()
    completed_pods: tuple[KubePod, ...] = ()
    events: tuple[KubeSchedulerEvent, ...] = ()


class KubeSchedulerEngine:
    """Synchronous single-pod scheduler with kube-scheduler queue semantics."""

    def __init__(
        self,
        *,
        max_nodes: int,
        node_cpu_milli: int,
        node_memory_mib: int,
        node_gpu_count: int,
        backoff_duration_s: float = 10.0,
        max_backoff_retries: int = 1,
        container_start_delay_s: float = 0.0,
    ) -> None:
        self.nodes = [
            KubeNode(
                node_id=f"k8s-node-{index:05d}",
                cpu_capacity_milli=node_cpu_milli,
                memory_capacity_mib=node_memory_mib,
                gpu_capacity=node_gpu_count,
            )
            for index in range(max_nodes)
        ]
        self.backoff_duration_s = max(0.0, backoff_duration_s)
        self.max_backoff_retries = max(0, max_backoff_retries)
        self.container_start_delay_s = max(0.0, container_start_delay_s)

        self.active_queue: list[KubePod] = []
        self._backoff_queue: list[tuple[float, int, KubePod]] = []
        self.unschedulable_pods: dict[str, KubePod] = {}
        self.running_pods: dict[str, KubePod] = {}
        self._enqueue_sequence = 0
        self._backoff_sequence = 0

    @property
    def backoff_queue(self) -> tuple[KubePod, ...]:
        return tuple(item[2] for item in sorted(self._backoff_queue))

    def submit(self, pod: KubePod) -> tuple[KubeSchedulerEvent, ...]:
        """Create a pod and enqueue it in activeQ."""
        self._enqueue_sequence += 1
        pod.enqueue_sequence = self._enqueue_sequence
        self.active_queue.append(pod)
        return (
            self._event(pod, "pod_created", pod.created_at),
            self._event(pod, "queue_entered", pod.enqueue_time, reason="activeQ"),
        )

    def tick(self, sim_time: float) -> KubeSchedulerTick:
        events: list[KubeSchedulerEvent] = []
        completed: list[KubePod] = []
        started: list[KubePod] = []

        # Completed containers release resources. This is the cluster event that
        # wakes unschedulable pods, matching the scheduler's event-driven retry.
        for pod_id, pod in list(self.running_pods.items()):
            if pod.ends_at is not None and pod.ends_at <= sim_time:
                node = self._node(pod.node_id)
                node.release(pod)
                completed.append(pod)
                del self.running_pods[pod_id]
                events.append(self._event(pod, "container_completed", sim_time, node_id=pod.node_id))

        # Backoff expiry moves pods back to activeQ. Ordering is restored by the
        # same priority/enqueue key used for normal activeQ pops.
        while self._backoff_queue and self._backoff_queue[0][0] <= sim_time:
            ready_at, _sequence, pod = heapq.heappop(self._backoff_queue)
            self.active_queue.append(pod)
            events.append(self._event(pod, "backoff_expired", sim_time, reason=f"ready_at={ready_at:.3f}"))
            events.append(self._event(pod, "queue_entered", sim_time, reason="activeQ"))

        if completed and self.unschedulable_pods:
            for pod in self.unschedulable_pods.values():
                self.active_queue.append(pod)
                events.append(self._event(pod, "cluster_event_requeue", sim_time, reason="node_resources_freed"))
                events.append(self._event(pod, "queue_entered", sim_time, reason="activeQ"))
            self.unschedulable_pods.clear()

        # A failed attempt is not allowed to starve higher-priority work that
        # follows it. Re-sort before every pop, just like a priority queue.
        while self.active_queue:
            self.active_queue.sort(key=lambda pod: (-pod.priority, pod.enqueue_time, pod.enqueue_sequence))
            pod = self.active_queue.pop(0)
            pod.attempts += 1
            events.append(self._event(pod, "scheduling_attempt", sim_time, attempt=pod.attempts))
            node = self._best_fit_node(pod)
            if node is None:
                if pod.attempts <= self.max_backoff_retries:
                    ready_at = sim_time + self.backoff_duration_s
                    self._backoff_sequence += 1
                    heapq.heappush(self._backoff_queue, (ready_at, self._backoff_sequence, pod))
                    events.append(self._event(pod, "backoff_entered", sim_time, reason="no_feasible_node"))
                else:
                    self.unschedulable_pods[pod.pod_id] = pod
                    events.append(self._event(pod, "unschedulable_entered", sim_time, reason="no_feasible_node"))
                continue

            node.allocate(pod)
            pod.node_id = node.node_id
            pod.started_at = sim_time + self.container_start_delay_s
            pod.ends_at = pod.started_at + pod.duration_s
            self.running_pods[pod.pod_id] = pod
            events.append(self._event(pod, "node_selected", sim_time, node_id=node.node_id))
            events.append(self._event(pod, "bound", sim_time, node_id=node.node_id))
            events.append(
                self._event(
                    pod,
                    "container_started",
                    pod.started_at,
                    node_id=node.node_id,
                    reason="post_binding",
                )
            )
            started.append(pod)

        return KubeSchedulerTick(
            started_pods=tuple(started),
            completed_pods=tuple(completed),
            events=tuple(events),
        )

    def _best_fit_node(self, pod: KubePod) -> Optional[KubeNode]:
        candidates = [node for node in self.nodes if node.can_fit(pod)]
        if not candidates:
            return None
        # Prefer the node with the least remaining GPU capacity, then CPU and
        # memory. This is deterministic and reduces fragmentation.
        return min(
            candidates,
            key=lambda node: (
                node.gpu_capacity - node.gpu_allocated - pod.gpu_count,
                node.cpu_capacity_milli - node.cpu_allocated_milli - pod.cpu_milli,
                node.memory_capacity_mib - node.memory_allocated_mib - pod.memory_mib,
                node.node_id,
            ),
        )

    def _node(self, node_id: Optional[str]) -> KubeNode:
        if node_id is None:
            raise ValueError("running pod has no node assignment")
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        raise KeyError(node_id)

    @staticmethod
    def _event(
        pod: KubePod,
        stage: str,
        timestamp: float,
        *,
        node_id: Optional[str] = None,
        reason: Optional[str] = None,
        attempt: int = 0,
    ) -> KubeSchedulerEvent:
        return KubeSchedulerEvent(
            event_id=f"{pod.pod_id}:{stage}:{timestamp:.6f}",
            pod_id=pod.pod_id,
            workload_id=pod.workload_id,
            stage=stage,
            timestamp=timestamp,
            node_id=node_id,
            reason=reason,
            attempt=attempt,
        )