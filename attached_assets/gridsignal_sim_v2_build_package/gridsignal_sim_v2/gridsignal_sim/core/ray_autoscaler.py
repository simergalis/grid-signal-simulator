"""Phase 5 KubeRay autoscaling feedback loop.

This module turns pending logical Ray demand into worker-replica requests. Every
request is sent through the Kubernetes admission engine owned by
``RayClusterEngine``. Slurm-backed clusters are intentionally ineligible.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional

from .ray_cluster_engine import (
    RayClusterEngine,
    RayClusterLifecycleError,
    RayClusterLifecycleState,
    RayWorkerScalingEvent,
    RayWorkerScalingState,
)
from .ray_execution_scheduler import RayExecutionScheduler
from .ray_models import InfrastructureBackend, RayContractError, RayResourceRequest


class RayAutoscalingError(RayContractError):
    """Raised when an autoscaling policy or feedback transition is invalid."""


class RayAutoscalerEventState(str, Enum):
    OBSERVED = "observed"
    SCALE_REQUESTED = "scale_requested"
    SCALE_READY = "scale_ready"
    SCALE_DOWN = "scale_down"
    WORKER_FAILED = "worker_failed"
    POWER_REJECTED = "power_rejected"
    ADMISSION_REJECTED = "admission_rejected"


@dataclass(frozen=True)
class RayWorkerGroupAutoscalingPolicy:
    """Optional per-worker-group limits layered over a Ray cluster limit."""

    worker_group_id: str
    min_workers: int
    max_workers: int

    def __post_init__(self) -> None:
        if not self.worker_group_id:
            raise RayAutoscalingError("worker_group_id must not be empty")
        if self.min_workers < 0 or self.max_workers < self.min_workers:
            raise RayAutoscalingError(
                "worker-group limits must be non-negative and ordered"
            )


@dataclass(frozen=True)
class RayAutoscalingPolicy:
    """Deterministic KubeRay feedback and delay policy."""

    min_workers: Optional[int] = None
    max_workers: Optional[int] = None
    worker_groups: Mapping[str, RayWorkerGroupAutoscalingPolicy] = field(
        default_factory=dict
    )
    scale_up_delay_s: float = 0.0
    scale_down_idle_delay_s: float = 0.0
    power_budget_kw: Optional[float] = None
    worker_power_kw: float = 0.0
    power_action: str = "reject"

    def __post_init__(self) -> None:
        if self.min_workers is not None and self.min_workers < 0:
            raise RayAutoscalingError("min_workers must be non-negative")
        if (
            self.min_workers is not None
            and self.max_workers is not None
            and self.max_workers < self.min_workers
        ):
            raise RayAutoscalingError("max_workers must be at least min_workers")
        for name, value in (
            ("scale_up_delay_s", self.scale_up_delay_s),
            ("scale_down_idle_delay_s", self.scale_down_idle_delay_s),
            ("worker_power_kw", self.worker_power_kw),
        ):
            if not math.isfinite(float(value)) or value < 0.0:
                raise RayAutoscalingError(f"{name} must be finite and non-negative")
        if self.power_budget_kw is not None and (
            not math.isfinite(float(self.power_budget_kw))
            or self.power_budget_kw < 0.0
        ):
            raise RayAutoscalingError(
                "power_budget_kw must be finite and non-negative or None"
            )
        if self.power_action not in {"reject", "throttle"}:
            raise RayAutoscalingError("power_action must be 'reject' or 'throttle'")


@dataclass(frozen=True)
class RayAutoscalerEvent:
    cluster_id: str
    state: RayAutoscalerEventState
    timestamp: float
    current_workers: int
    target_workers: int
    pending_demand: RayResourceRequest = RayResourceRequest()
    request_id: Optional[str] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class RayAutoscalerStatus:
    cluster_id: str
    registered_workers: int
    pending_demand: RayResourceRequest
    scale_in_flight: bool
    pending_since: Optional[float]
    idle_since: Optional[float]


class RayAutoscaler:
    """Feed Phase 4 pending demand into KubeRay worker admission."""

    def __init__(
        self,
        cluster_engine: RayClusterEngine,
        execution_scheduler: RayExecutionScheduler,
        policies: Mapping[str, RayAutoscalingPolicy],
    ) -> None:
        if not policies:
            raise RayAutoscalingError("at least one cluster autoscaling policy is required")
        self.cluster_engine = cluster_engine
        self.execution_scheduler = execution_scheduler
        self.policies = dict(policies)
        self._pending_since: dict[str, float] = {}
        self._idle_since: dict[str, float] = {}
        self._events: list[RayAutoscalerEvent] = []
        self.time = 0.0

    @property
    def events(self) -> tuple[RayAutoscalerEvent, ...]:
        return tuple(self._events)

    def advance(self, now: float) -> tuple[RayAutoscalerEvent, ...]:
        if now < self.time or not math.isfinite(float(now)):
            raise RayAutoscalingError(
                "autoscaler clock cannot move backwards or be non-finite"
            )
        self.time = float(now)
        self.cluster_engine.advance(self.time)
        for cluster_id in self.policies:
            status = self.cluster_engine.status(cluster_id)
            if status.state is not RayClusterLifecycleState.READY:
                continue
            self.execution_scheduler.sync_cluster(cluster_id)
            self.execution_scheduler.advance(self.time)
        emitted: list[RayAutoscalerEvent] = []
        for cluster_id, policy in self.policies.items():
            emitted.extend(self._reconcile_cluster(cluster_id, policy, self.time))
        return tuple(emitted)

    def report_worker_failure(
        self, cluster_id: str, count: int = 1, now: Optional[float] = None
    ) -> tuple[RayAutoscalerEvent, ...]:
        when = self.time if now is None else float(now)
        self._check_time(when)
        policy = self._policy(cluster_id)
        failed = self.cluster_engine.report_worker_failure(
            cluster_id, count=count, now=when
        )
        self.execution_scheduler.sync_cluster(cluster_id)
        status = self.cluster_engine.status(cluster_id)
        if (
            policy.power_budget_kw is not None
            and (status.registered_workers + count) * policy.worker_power_kw
            > policy.power_budget_kw
        ):
            return (
                self._emit(
                    cluster_id,
                    RayAutoscalerEventState.POWER_REJECTED,
                    when,
                    status.registered_workers,
                    status.registered_workers + count,
                    RayResourceRequest(),
                    reason="worker replacement exceeds the power budget",
                ),
            )
        replacement = self.cluster_engine.request_worker_replacement(
            cluster_id, count=count, now=when
        )
        state = (
            RayAutoscalerEventState.SCALE_REQUESTED
            if replacement.state is RayWorkerScalingState.ADMISSION_QUEUED
            else RayAutoscalerEventState.ADMISSION_REJECTED
        )
        event = self._emit(
            cluster_id,
            state,
            when,
            status.registered_workers,
            status.registered_workers + count,
            RayResourceRequest(),
            request_id=replacement.request_id,
            reason=replacement.reason,
        )
        return (event,)

    def status(self, cluster_id: str) -> RayAutoscalerStatus:
        policy = self._policy(cluster_id)
        del policy
        cluster = self.cluster_engine.status(cluster_id)
        return RayAutoscalerStatus(
            cluster_id=cluster_id,
            registered_workers=cluster.registered_workers,
            pending_demand=self.execution_scheduler.pending_resource_demand(cluster_id),
            scale_in_flight=self.cluster_engine.scaling_in_flight(cluster_id),
            pending_since=self._pending_since.get(cluster_id),
            idle_since=self._idle_since.get(cluster_id),
        )

    def _reconcile_cluster(
        self, cluster_id: str, policy: RayAutoscalingPolicy, now: float
    ) -> list[RayAutoscalerEvent]:
        cluster = self.cluster_engine.status(cluster_id)
        spec = self.cluster_engine.spec(cluster_id)
        if spec.backend is not InfrastructureBackend.KUBERNETES or not spec.elastic:
            # Slurm-backed Ray remains fixed to its admitted allocation.
            return []
        demand = self.execution_scheduler.pending_resource_demand(cluster_id)
        current = cluster.registered_workers
        minimum, maximum = self._limits(cluster_id, policy)
        if demand != RayResourceRequest():
            self._idle_since.pop(cluster_id, None)
            self._pending_since.setdefault(cluster_id, now)
            if (
                now - self._pending_since[cluster_id] >= policy.scale_up_delay_s
                and not self.cluster_engine.scaling_in_flight(cluster_id)
            ):
                desired = min(
                    maximum,
                    max(current + 1, self._workers_for_demand(spec.worker_resources, demand)),
                )
                if desired > current:
                    return self._request_scale(
                        cluster_id, desired, demand, policy, now
                    )
            return []

        self._pending_since.pop(cluster_id, None)
        if self.execution_scheduler.worker_used_resources(cluster_id) == RayResourceRequest():
            self._idle_since.setdefault(cluster_id, now)
            if (
                current > minimum
                and now - self._idle_since[cluster_id]
                >= policy.scale_down_idle_delay_s
                and not self.cluster_engine.scaling_in_flight(cluster_id)
            ):
                scale = self.cluster_engine.request_worker_count(
                    cluster_id, minimum, now=now
                )
                event = self._emit(
                    cluster_id,
                    RayAutoscalerEventState.SCALE_DOWN,
                    now,
                    current,
                    minimum,
                    demand,
                    request_id=scale.request_id,
                    reason=scale.reason,
                )
                return [event]
        else:
            self._idle_since.pop(cluster_id, None)
        return []

    def _request_scale(
        self,
        cluster_id: str,
        desired: int,
        demand: RayResourceRequest,
        policy: RayAutoscalingPolicy,
        now: float,
    ) -> list[RayAutoscalerEvent]:
        current = self.cluster_engine.status(cluster_id).registered_workers
        if (
            policy.power_budget_kw is not None
            and desired * policy.worker_power_kw > policy.power_budget_kw
        ):
            return [
                self._emit(
                    cluster_id,
                    RayAutoscalerEventState.POWER_REJECTED,
                    now,
                    current,
                    desired,
                    demand,
                    reason="worker scale-up exceeds the power budget",
                )
            ]
        scale = self.cluster_engine.request_worker_count(
            cluster_id, desired, now=now
        )
        state = (
            RayAutoscalerEventState.SCALE_REQUESTED
            if scale.state is RayWorkerScalingState.ADMISSION_QUEUED
            else RayAutoscalerEventState.ADMISSION_REJECTED
        )
        return [
            self._emit(
                cluster_id,
                state,
                now,
                current,
                desired,
                demand,
                request_id=scale.request_id,
                reason=scale.reason,
            )
        ]

    def _limits(
        self, cluster_id: str, policy: RayAutoscalingPolicy
    ) -> tuple[int, int]:
        spec = self.cluster_engine.spec(cluster_id)
        group = policy.worker_groups.get("default")
        minimum = (
            policy.min_workers
            if policy.min_workers is not None
            else spec.min_workers
        )
        maximum = (
            policy.max_workers
            if policy.max_workers is not None
            else spec.max_workers
        )
        if group is not None:
            minimum, maximum = group.min_workers, group.max_workers
        if minimum < spec.min_workers or maximum > spec.max_workers:
            raise RayAutoscalingError(
                "autoscaling policy must remain within the Ray cluster limits"
            )
        return minimum, maximum

    @staticmethod
    def _workers_for_demand(
        worker_resources: RayResourceRequest, demand: RayResourceRequest
    ) -> int:
        requirements = (
            (demand.cpu, worker_resources.cpu),
            (demand.gpu, worker_resources.gpu),
            (demand.memory_gib, worker_resources.memory_gib),
            (demand.object_store_memory_gib, worker_resources.object_store_memory_gib),
        )
        needed = 1
        for requested, per_worker in requirements:
            if requested <= 0:
                continue
            if per_worker <= 0:
                return 0
            needed = max(needed, math.ceil(requested / per_worker))
        for name, requested in demand.custom_resources.items():
            per_worker = worker_resources.custom_resources.get(name, 0.0)
            if requested > 0 and per_worker <= 0:
                return 0
            if requested > 0:
                needed = max(needed, math.ceil(requested / per_worker))
        return needed

    def _emit(
        self,
        cluster_id: str,
        state: RayAutoscalerEventState,
        timestamp: float,
        current_workers: int,
        target_workers: int,
        demand: RayResourceRequest,
        *,
        request_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> RayAutoscalerEvent:
        event = RayAutoscalerEvent(
            cluster_id=cluster_id,
            state=state,
            timestamp=timestamp,
            current_workers=current_workers,
            target_workers=target_workers,
            pending_demand=demand,
            request_id=request_id,
            reason=reason,
        )
        self._events.append(event)
        return event

    def _policy(self, cluster_id: str) -> RayAutoscalingPolicy:
        try:
            return self.policies[cluster_id]
        except KeyError as exc:
            raise RayAutoscalingError(
                f"no autoscaling policy for Ray cluster {cluster_id!r}"
            ) from exc

    def _check_time(self, when: float) -> None:
        if when < self.time or not math.isfinite(when):
            raise RayAutoscalingError(
                "autoscaler clock cannot move backwards or be non-finite"
            )


KubeRayAutoscaler = RayAutoscaler