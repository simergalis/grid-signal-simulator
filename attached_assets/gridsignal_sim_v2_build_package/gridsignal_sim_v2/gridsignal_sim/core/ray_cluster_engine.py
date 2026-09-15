"""Ray cluster startup, readiness, and KubeRay worker scaling lifecycle.

This module consumes Phase 2 infrastructure admission results.  It models the
control-plane lifecycle up to a ready Ray cluster and models worker replica
requests for Phase 5. It does not schedule Ray tasks or actors, place Pods, or
enforce physical power.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Optional, Protocol

from .infrastructure_admission import (
    InfrastructureAdmissionEvent,
    InfrastructureAdmissionRequest,
    InfrastructureAdmissionState,
    KubernetesAdmissionEngine,
    SlurmAdmissionEngine,
)
from .ray_models import (
    InfrastructureAllocation,
    InfrastructureBackend,
    RayClusterSpec,
    RayContractError,
    RayResourceRequest,
)


class RayClusterLifecycleError(RayContractError):
    """Raised when a cluster lifecycle transition is invalid."""


class RayClusterLifecycleState(str, Enum):
    REQUESTED = "requested"
    ADMISSION_QUEUED = "admission_queued"
    ADMITTED = "admitted"
    HEAD_STARTING = "head_starting"
    HEAD_READY = "head_ready"
    WORKERS_STARTING = "workers_starting"
    READY = "ready"
    DRAINING = "draining"
    TERMINATED = "terminated"
    FAILED = "failed"


@dataclass(frozen=True)
class RayClusterLifecycleEvent:
    cluster_id: str
    state: RayClusterLifecycleState
    timestamp: float
    allocation_id: Optional[str] = None
    reason: Optional[str] = None
    registered_workers: int = 0
    ready_resources: RayResourceRequest = RayResourceRequest()


class RayWorkerScalingState(str, Enum):
    ADMISSION_QUEUED = "admission_queued"
    ADMITTED = "admitted"
    WORKERS_STARTING = "workers_starting"
    READY = "ready"
    SCALE_DOWN = "scale_down"
    WORKER_FAILED = "worker_failed"
    REJECTED = "rejected"


@dataclass(frozen=True)
class RayWorkerScalingEvent:
    cluster_id: str
    state: RayWorkerScalingState
    timestamp: float
    target_workers: int
    registered_workers: int
    request_id: Optional[str] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class RayClusterTiming:
    """Lifecycle timing metrics with admission and startup kept separate."""

    infrastructure_admission_delay: Optional[float] = None
    cluster_startup_delay: Optional[float] = None
    # Ray workload queueing belongs to Phase 4 and stays unset here.
    ray_workload_queue_delay: Optional[float] = None


@dataclass(frozen=True)
class RayClusterStatus:
    cluster_id: str
    state: RayClusterLifecycleState
    allocation: Optional[InfrastructureAllocation]
    registered_workers: int
    ready_resources: RayResourceRequest
    timing: RayClusterTiming


class _AdmissionEngine(Protocol):
    def submit(
        self, request: InfrastructureAdmissionRequest
    ) -> InfrastructureAdmissionEvent: ...

    def advance(self, now: float) -> tuple[InfrastructureAdmissionEvent, ...]: ...

    def release(
        self, request_id: str, now: Optional[float] = None
    ) -> InfrastructureAdmissionEvent: ...


@dataclass
class _ClusterRecord:
    spec: RayClusterSpec
    request: InfrastructureAdmissionRequest
    state: RayClusterLifecycleState
    allocation: Optional[InfrastructureAllocation] = None
    requested_at: float = 0.0
    admitted_at: Optional[float] = None
    ready_at: Optional[float] = None
    head_ready_at: Optional[float] = None
    workers_start_at: Optional[float] = None
    workers_register_at: Optional[float] = None
    initial_worker_count: int = 0
    started_workers: int = 0
    registered_workers: int = 0
    allocated_workers: int = 0
    scale_sequence: int = 0
    replacement_reuses_allocation: int = 0


@dataclass
class _WorkerScaleRecord:
    cluster_id: str
    request: InfrastructureAdmissionRequest
    delta_workers: int
    target_workers: int
    state: RayWorkerScalingState
    request_id: str
    replacement: bool = False
    reuses_allocation: bool = False
    admitted_at: Optional[float] = None
    workers_start_at: Optional[float] = None
    workers_register_at: Optional[float] = None


class RayClusterEngine:
    """Start admitted Ray clusters and expose readiness deterministically."""

    def __init__(
        self,
        *,
        kubernetes_admission: Optional[KubernetesAdmissionEngine] = None,
        slurm_admission: Optional[SlurmAdmissionEngine] = None,
        head_startup_delay_s: float = 1.0,
        worker_startup_delay_s: float = 1.0,
        worker_registration_delay_s: float = 1.0,
    ) -> None:
        self._admission: dict[InfrastructureBackend, _AdmissionEngine] = {}
        if kubernetes_admission is not None:
            self._admission[InfrastructureBackend.KUBERNETES] = (
                kubernetes_admission
            )
        if slurm_admission is not None:
            self._admission[InfrastructureBackend.SLURM] = slurm_admission
        if not self._admission:
            raise RayClusterLifecycleError(
                "at least one infrastructure admission engine is required"
            )
        for name, value in (
            ("head_startup_delay_s", head_startup_delay_s),
            ("worker_startup_delay_s", worker_startup_delay_s),
            ("worker_registration_delay_s", worker_registration_delay_s),
        ):
            if value < 0 or not math.isfinite(float(value)):
                raise RayClusterLifecycleError(
                    f"{name} must be finite and non-negative"
                )
        self.head_startup_delay_s = float(head_startup_delay_s)
        self.worker_startup_delay_s = float(worker_startup_delay_s)
        self.worker_registration_delay_s = float(worker_registration_delay_s)
        self._clusters: dict[str, _ClusterRecord] = {}
        self._events: list[RayClusterLifecycleEvent] = []
        self._scaling_records: dict[str, _WorkerScaleRecord] = {}
        self._scaling_events: list[RayWorkerScalingEvent] = []
        self.time = 0.0

    @property
    def events(self) -> tuple[RayClusterLifecycleEvent, ...]:
        return tuple(self._events)

    @property
    def scaling_events(self) -> tuple[RayWorkerScalingEvent, ...]:
        return tuple(self._scaling_events)

    def submit(
        self,
        spec: RayClusterSpec,
        admission_request: InfrastructureAdmissionRequest,
    ) -> RayClusterLifecycleEvent:
        """Submit the cluster's complete infrastructure allocation request."""
        if spec.ray_cluster_id in self._clusters:
            raise RayClusterLifecycleError(
                f"Ray cluster {spec.ray_cluster_id!r} was already submitted"
            )
        if admission_request.backend is not spec.backend:
            raise RayClusterLifecycleError(
                "cluster backend and admission request backend do not match"
            )
        if not spec.minimum_resources.fits_within(
            admission_request.resource_request
        ):
            raise RayClusterLifecycleError(
                "cluster initial resources exceed its admission request"
            )
        expected_allocation_id = (
            f"{spec.backend.value}:{admission_request.request_id}"
        )
        if spec.infrastructure_allocation_id != expected_allocation_id:
            raise RayClusterLifecycleError(
                "cluster infrastructure_allocation_id must match its admission "
                f"request ({expected_allocation_id!r})"
            )
        try:
            admission_engine = self._admission[spec.backend]
        except KeyError as exc:
            raise RayClusterLifecycleError(
                f"no admission engine configured for {spec.backend.value!r}"
            ) from exc
        if admission_request.submitted_at < self.time:
            raise RayClusterLifecycleError(
                "cluster lifecycle clock cannot move backwards"
            )
        self.time = max(self.time, admission_request.submitted_at)
        record = _ClusterRecord(
            spec=spec,
            request=admission_request,
            state=RayClusterLifecycleState.REQUESTED,
            requested_at=admission_request.submitted_at,
        )
        self._clusters[spec.ray_cluster_id] = record
        if spec.backend is InfrastructureBackend.SLURM:
            admission_event = admission_engine.submit_request(  # type: ignore[attr-defined]
                admission_request
            )
        else:
            admission_event = admission_engine.submit(admission_request)
        if admission_event.state is InfrastructureAdmissionState.REJECTED:
            record.state = RayClusterLifecycleState.FAILED
            return self._emit(
                record,
                RayClusterLifecycleState.FAILED,
                admission_event.timestamp,
                reason=admission_event.reason or "infrastructure admission rejected",
            )
        record.state = RayClusterLifecycleState.ADMISSION_QUEUED
        return self._emit(
            record,
            RayClusterLifecycleState.ADMISSION_QUEUED,
            admission_event.timestamp,
            reason="waiting for infrastructure admission",
        )

    def advance(self, now: float) -> tuple[RayClusterLifecycleEvent, ...]:
        """Advance admission and startup timers to ``now``."""
        if now < self.time:
            raise RayClusterLifecycleError(
                "cluster lifecycle clock cannot move backwards"
            )
        self.time = float(now)
        emitted: list[RayClusterLifecycleEvent] = []

        admission_events: dict[InfrastructureBackend, tuple[InfrastructureAdmissionEvent, ...]] = {}
        for backend, engine in self._admission.items():
            admission_events[backend] = engine.advance(self.time)
        for record in self._clusters.values():
            if record.state is not RayClusterLifecycleState.ADMISSION_QUEUED:
                continue
            for event in admission_events.get(record.spec.backend, ()):
                if event.request_id != record.request.request_id:
                    continue
                if event.state is InfrastructureAdmissionState.ADMITTED:
                    record.allocation = event.allocation
                    record.admitted_at = event.timestamp
                    record.state = RayClusterLifecycleState.ADMITTED
                    emitted.append(
                        self._emit(
                            record,
                            RayClusterLifecycleState.ADMITTED,
                            event.timestamp,
                            reason="infrastructure allocation admitted",
                        )
                    )
                    emitted.append(
                        self._start_head(record, event.timestamp)
                    )
                    break
                if event.state in {
                    InfrastructureAdmissionState.REJECTED,
                    InfrastructureAdmissionState.PREEMPTED,
                }:
                    record.state = RayClusterLifecycleState.FAILED
                    emitted.append(
                        self._emit(
                            record,
                            RayClusterLifecycleState.FAILED,
                            event.timestamp,
                            reason=event.reason or event.state.value,
                        )
                    )
                    break

        for scale in tuple(self._scaling_records.values()):
            if scale.state is not RayWorkerScalingState.ADMISSION_QUEUED:
                continue
            cluster = self._record(scale.cluster_id)
            for event in admission_events.get(cluster.spec.backend, ()):
                if event.request_id != scale.request_id:
                    continue
                if event.state is InfrastructureAdmissionState.ADMITTED:
                    scale.state = RayWorkerScalingState.ADMITTED
                    scale.admitted_at = event.timestamp
                    scale.workers_start_at = (
                        event.timestamp + self.worker_startup_delay_s
                    )
                    self._emit_scaling(
                        scale,
                        event.timestamp,
                        RayWorkerScalingState.ADMITTED,
                        reason="worker replica request admitted",
                    )
                    break
                if event.state in {
                    InfrastructureAdmissionState.REJECTED,
                    InfrastructureAdmissionState.PREEMPTED,
                }:
                    scale.state = RayWorkerScalingState.REJECTED
                    self._emit_scaling(
                        scale,
                        event.timestamp,
                        RayWorkerScalingState.REJECTED,
                        reason=event.reason or event.state.value,
                    )
                    break

        for record in self._clusters.values():
            emitted.extend(self._progress(record, self.time))
        for scale in tuple(self._scaling_records.values()):
            self._progress_scale(scale, self.time)
        return tuple(emitted)

    def begin_drain(
        self, cluster_id: str, now: Optional[float] = None
    ) -> RayClusterLifecycleEvent:
        record = self._record(cluster_id)
        when = self.time if now is None else float(now)
        self._check_time(when)
        if record.state not in {
            RayClusterLifecycleState.READY,
            RayClusterLifecycleState.HEAD_READY,
            RayClusterLifecycleState.WORKERS_STARTING,
        }:
            raise RayClusterLifecycleError(
                f"Ray cluster {cluster_id!r} cannot drain from {record.state.value}"
            )
        self.time = when
        record.state = RayClusterLifecycleState.DRAINING
        return self._emit(
            record,
            RayClusterLifecycleState.DRAINING,
            when,
            reason="cluster drain requested",
        )

    def terminate(
        self, cluster_id: str, now: Optional[float] = None
    ) -> RayClusterLifecycleEvent:
        record = self._record(cluster_id)
        when = self.time if now is None else float(now)
        self._check_time(when)
        if record.state not in {
            RayClusterLifecycleState.DRAINING,
            RayClusterLifecycleState.FAILED,
            RayClusterLifecycleState.ADMISSION_QUEUED,
        }:
            raise RayClusterLifecycleError(
                f"Ray cluster {cluster_id!r} cannot terminate from {record.state.value}"
            )
        self._release_worker_scales(record, when)
        if record.allocation is not None:
            self._admission[record.spec.backend].release(
                record.request.request_id, now=when
            )
        self.time = when
        record.state = RayClusterLifecycleState.TERMINATED
        return self._emit(
            record,
            RayClusterLifecycleState.TERMINATED,
            when,
            reason="cluster terminated",
        )

    def fail(
        self,
        cluster_id: str,
        reason: str,
        now: Optional[float] = None,
    ) -> RayClusterLifecycleEvent:
        record = self._record(cluster_id)
        when = self.time if now is None else float(now)
        self._check_time(when)
        if record.state in {
            RayClusterLifecycleState.TERMINATED,
            RayClusterLifecycleState.FAILED,
        }:
            raise RayClusterLifecycleError(
                f"Ray cluster {cluster_id!r} is already terminal"
            )
        if record.allocation is not None:
            self._release_worker_scales(record, when)
            self._admission[record.spec.backend].release(
                record.request.request_id, now=when
            )
        self.time = when
        record.state = RayClusterLifecycleState.FAILED
        return self._emit(record, record.state, when, reason=reason)

    def status(self, cluster_id: str) -> RayClusterStatus:
        record = self._record(cluster_id)
        return RayClusterStatus(
            cluster_id=cluster_id,
            state=record.state,
            allocation=record.allocation,
            registered_workers=record.registered_workers,
            ready_resources=self._ready_resources(record),
            timing=RayClusterTiming(
                infrastructure_admission_delay=(
                    record.admitted_at - record.requested_at
                    if record.admitted_at is not None
                    else None
                ),
                cluster_startup_delay=(
                    record.ready_at - record.admitted_at
                    if record.ready_at is not None
                    and record.admitted_at is not None
                    else None
                ),
            ),
        )

    def spec(self, cluster_id: str) -> RayClusterSpec:
        """Return the immutable spec owned by the lifecycle engine."""
        return self._record(cluster_id).spec

    def scaling_in_flight(self, cluster_id: str) -> bool:
        return any(
            scale.cluster_id == cluster_id
            and scale.state
            in {
                RayWorkerScalingState.ADMISSION_QUEUED,
                RayWorkerScalingState.ADMITTED,
                RayWorkerScalingState.WORKERS_STARTING,
            }
            for scale in self._scaling_records.values()
        )

    def request_worker_count(
        self, cluster_id: str, target_workers: int, now: Optional[float] = None
    ) -> RayWorkerScalingEvent:
        """Request a KubeRay worker replica count through admission."""
        record = self._record(cluster_id)
        when = self.time if now is None else float(now)
        self._check_time(when)
        if record.state is not RayClusterLifecycleState.READY:
            raise RayClusterLifecycleError(
                f"Ray cluster {cluster_id!r} is not ready for worker scaling"
            )
        if record.spec.backend is not InfrastructureBackend.KUBERNETES or not record.spec.elastic:
            raise RayClusterLifecycleError(
                "only elastic Kubernetes Ray clusters support worker scaling"
            )
        if not isinstance(target_workers, int):
            raise RayClusterLifecycleError("target_workers must be an integer")
        if not record.spec.min_workers <= target_workers <= record.spec.max_workers:
            raise RayClusterLifecycleError(
                f"target_workers must be between {record.spec.min_workers} and "
                f"{record.spec.max_workers}"
            )
        if self.scaling_in_flight(cluster_id):
            raise RayClusterLifecycleError(
                f"Ray cluster {cluster_id!r} already has a worker scale in flight"
            )
        if target_workers == record.allocated_workers:
            return self._record_scaling_event(
                cluster_id,
                RayWorkerScalingState.READY,
                when,
                target_workers,
                reason="worker count already at target",
            )
        if target_workers < record.allocated_workers:
            if target_workers < record.initial_worker_count:
                raise RayClusterLifecycleError(
                    "scale-down cannot remove the cluster's initial workers"
                )
            to_remove = record.allocated_workers - target_workers
            removable = [
                scale
                for scale in reversed(tuple(self._scaling_records.values()))
                if scale.cluster_id == cluster_id
                and scale.state is RayWorkerScalingState.READY
                and not scale.replacement
            ]
            removed = 0
            for scale in removable:
                if removed >= to_remove:
                    break
                self._admission[record.spec.backend].release(
                    scale.request_id, now=when
                )
                scale.state = RayWorkerScalingState.SCALE_DOWN
                removed += scale.delta_workers
                self._emit_scaling(
                    scale,
                    when,
                    RayWorkerScalingState.SCALE_DOWN,
                    reason="idle worker replicas released",
                )
            if removed != to_remove:
                raise RayClusterLifecycleError(
                    "requested scale-down exceeds dynamically added workers"
                )
            record.allocated_workers = target_workers
            record.registered_workers = min(record.registered_workers, target_workers)
            return self._record_scaling_event(
                cluster_id,
                RayWorkerScalingState.SCALE_DOWN,
                when,
                target_workers,
                reason="worker replicas scaled down",
            )
        return self._submit_worker_scale(
            record, target_workers - record.allocated_workers, target_workers, when
        )

    def report_worker_failure(
        self, cluster_id: str, count: int = 1, now: Optional[float] = None
    ) -> RayWorkerScalingEvent:
        """Report failed registered workers so the autoscaler can replace them."""
        record = self._record(cluster_id)
        when = self.time if now is None else float(now)
        self._check_time(when)
        if count < 1 or count > record.registered_workers:
            raise RayClusterLifecycleError(
                "failed worker count must be within registered worker count"
            )
        failed_scale_records = [
            scale
            for scale in reversed(tuple(self._scaling_records.values()))
            if scale.cluster_id == cluster_id
            and scale.state is RayWorkerScalingState.READY
            and not scale.replacement
        ][:count]
        if len(failed_scale_records) == count:
            for scale in failed_scale_records:
                self._admission[record.spec.backend].release(
                    scale.request_id, now=when
                )
                scale.state = RayWorkerScalingState.WORKER_FAILED
                record.allocated_workers -= scale.delta_workers
        else:
            # Initial elastic workers are part of the original admission
            # request and cannot be released individually. Their replacement
            # reuses that reserved logical footprint.
            record.replacement_reuses_allocation += count
        record.registered_workers -= count
        return self._record_scaling_event(
            cluster_id,
            RayWorkerScalingState.WORKER_FAILED,
            when,
            record.allocated_workers,
            reason=f"{count} worker replica(s) failed",
        )

    def request_worker_replacement(
        self, cluster_id: str, count: int = 1, now: Optional[float] = None
    ) -> RayWorkerScalingEvent:
        record = self._record(cluster_id)
        when = self.time if now is None else float(now)
        self._check_time(when)
        if record.spec.backend is not InfrastructureBackend.KUBERNETES or not record.spec.elastic:
            raise RayClusterLifecycleError(
                "only elastic Kubernetes Ray clusters support worker replacement"
            )
        if count < 1 or record.registered_workers + count > record.spec.max_workers:
            raise RayClusterLifecycleError(
                "worker replacement would exceed the cluster worker limit"
            )
        if self.scaling_in_flight(cluster_id):
            raise RayClusterLifecycleError(
                f"Ray cluster {cluster_id!r} already has a worker scale in flight"
            )
        reuse_allocation = record.replacement_reuses_allocation >= count
        if reuse_allocation:
            record.replacement_reuses_allocation -= count
        return self._submit_worker_scale(
            record,
            count,
            record.allocated_workers,
            when,
            replacement=True,
            reuses_allocation=reuse_allocation,
        )

    def _submit_worker_scale(
        self,
        record: _ClusterRecord,
        delta_workers: int,
        target_workers: int,
        when: float,
        *,
        replacement: bool = False,
        reuses_allocation: bool = False,
    ) -> RayWorkerScalingEvent:
        request_id = (
            f"{record.spec.ray_cluster_id}:worker-scale:{record.scale_sequence}"
        )
        record.scale_sequence += 1
        first_event: Optional[RayWorkerScalingEvent] = None
        for _ in range(delta_workers):
            request_id = (
                f"{record.spec.ray_cluster_id}:worker-scale:{record.scale_sequence}"
            )
            record.scale_sequence += 1
            request = InfrastructureAdmissionRequest(
                request_id=request_id,
                backend=InfrastructureBackend.KUBERNETES,
                resource_request=record.spec.worker_resources,
                admission_domain_id=record.request.admission_domain_id,
                admission_queue_id=record.request.admission_queue_id,
                capacity_budget_id=record.request.capacity_budget_id,
                tenant_id=record.request.tenant_id,
                priority=record.request.priority,
                submitted_at=when,
                preemptible=record.request.preemptible,
            )
            admission_event = self._admission[
                InfrastructureBackend.KUBERNETES
            ].submit(request)
            scale = _WorkerScaleRecord(
                cluster_id=record.spec.ray_cluster_id,
                request=request,
                delta_workers=1,
                target_workers=target_workers,
                state=RayWorkerScalingState.ADMISSION_QUEUED,
                request_id=request_id,
                replacement=replacement,
                reuses_allocation=reuses_allocation,
            )
            self._scaling_records[request_id] = scale
            if admission_event.state is InfrastructureAdmissionState.REJECTED:
                scale.state = RayWorkerScalingState.REJECTED
                current = self._emit_scaling(
                    scale,
                    admission_event.timestamp,
                    RayWorkerScalingState.REJECTED,
                    reason=admission_event.reason or "worker scale request rejected",
                )
            else:
                current = self._emit_scaling(
                    scale,
                    admission_event.timestamp,
                    RayWorkerScalingState.ADMISSION_QUEUED,
                    reason="worker replica request waiting for Kubernetes admission",
                )
            if first_event is None:
                first_event = current
        assert first_event is not None
        return first_event

    def _progress_scale(self, scale: _WorkerScaleRecord, now: float) -> None:
        if scale.state is RayWorkerScalingState.ADMITTED:
            scale.state = RayWorkerScalingState.WORKERS_STARTING
            self._emit_scaling(
                scale,
                scale.workers_start_at or now,
                RayWorkerScalingState.WORKERS_STARTING,
                reason="KubeRay worker Pods starting",
            )
        if (
            scale.state is RayWorkerScalingState.WORKERS_STARTING
            and scale.workers_start_at is not None
            and scale.workers_start_at <= now
        ):
            scale.workers_register_at = (
                scale.workers_start_at + self.worker_registration_delay_s
            )
            if self.worker_registration_delay_s:
                return
        if (
            scale.state is RayWorkerScalingState.WORKERS_STARTING
            and scale.workers_register_at is not None
            and scale.workers_register_at <= now
        ):
            record = self._record(scale.cluster_id)
            if not scale.reuses_allocation:
                record.allocated_workers += scale.delta_workers
            record.registered_workers += scale.delta_workers
            scale.state = RayWorkerScalingState.READY
            self._emit_scaling(
                scale,
                scale.workers_register_at,
                RayWorkerScalingState.READY,
                reason="KubeRay workers registered with Ray",
            )

    def _record_scaling_event(
        self,
        cluster_id: str,
        state: RayWorkerScalingState,
        timestamp: float,
        target_workers: int,
        *,
        request_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> RayWorkerScalingEvent:
        record = self._record(cluster_id)
        event = RayWorkerScalingEvent(
            cluster_id=cluster_id,
            state=state,
            timestamp=timestamp,
            target_workers=target_workers,
            registered_workers=record.registered_workers,
            request_id=request_id,
            reason=reason,
        )
        self._scaling_events.append(event)
        return event

    def _release_worker_scales(
        self, record: _ClusterRecord, when: float
    ) -> None:
        for scale in self._scaling_records.values():
            if (
                scale.cluster_id == record.spec.ray_cluster_id
                and scale.state
                in {
                    RayWorkerScalingState.ADMITTED,
                    RayWorkerScalingState.WORKERS_STARTING,
                    RayWorkerScalingState.READY,
                }
            ):
                self._admission[record.spec.backend].release(
                    scale.request_id, now=when
                )
                scale.state = RayWorkerScalingState.SCALE_DOWN

    def _emit_scaling(
        self,
        scale: _WorkerScaleRecord,
        timestamp: float,
        state: RayWorkerScalingState,
        *,
        reason: Optional[str] = None,
    ) -> RayWorkerScalingEvent:
        return self._record_scaling_event(
            scale.cluster_id,
            state,
            timestamp,
            scale.target_workers,
            request_id=scale.request_id,
            reason=reason,
        )

    def _progress(
        self, record: _ClusterRecord, now: float
    ) -> list[RayClusterLifecycleEvent]:
        emitted: list[RayClusterLifecycleEvent] = []
        if record.state is RayClusterLifecycleState.HEAD_STARTING:
            if record.head_ready_at is not None and record.head_ready_at <= now:
                record.state = RayClusterLifecycleState.HEAD_READY
                emitted.append(
                    self._emit(
                        record,
                        record.state,
                        record.head_ready_at,
                        reason="Ray head registered",
                    )
                )
                if record.initial_worker_count == 0:
                    emitted.extend(self._mark_ready(record, record.head_ready_at))
                else:
                    record.state = RayClusterLifecycleState.WORKERS_STARTING
                    record.workers_start_at = (
                        record.head_ready_at + self.worker_startup_delay_s
                    )
                    emitted.append(
                        self._emit(
                            record,
                            record.state,
                            record.head_ready_at,
                            reason="waiting for worker startup",
                        )
                    )
        if record.state is RayClusterLifecycleState.WORKERS_STARTING:
            if (
                record.workers_start_at is not None
                and record.workers_start_at <= now
                and record.started_workers == 0
            ):
                record.started_workers = record.initial_worker_count
                record.workers_register_at = (
                    record.workers_start_at
                    + self.worker_registration_delay_s
                )
                emitted.append(
                    self._emit(
                        record,
                        record.state,
                        record.workers_start_at,
                        reason="worker processes or Pods started",
                    )
                )
            if (
                record.workers_register_at is not None
                and record.workers_register_at <= now
                and record.registered_workers < record.started_workers
            ):
                record.registered_workers = record.started_workers
                emitted.extend(
                    self._mark_ready(record, record.workers_register_at)
                )
        return emitted

    def _start_head(
        self, record: _ClusterRecord, timestamp: float
    ) -> RayClusterLifecycleEvent:
        record.state = RayClusterLifecycleState.HEAD_STARTING
        record.head_ready_at = timestamp + self.head_startup_delay_s
        record.initial_worker_count = (
            record.spec.max_workers
            if record.spec.fixed_allocation
            else record.spec.min_workers
        )
        record.allocated_workers = record.initial_worker_count
        return self._emit(
            record,
            record.state,
            timestamp,
            reason="Ray head startup started",
        )

    def _mark_ready(
        self, record: _ClusterRecord, timestamp: float
    ) -> list[RayClusterLifecycleEvent]:
        record.state = RayClusterLifecycleState.READY
        record.ready_at = timestamp
        return [
            self._emit(
                record,
                record.state,
                timestamp,
                reason="Ray head and initial workers are ready",
            )
        ]

    def _ready_resources(
        self, record: _ClusterRecord
    ) -> RayResourceRequest:
        if record.state in {
            RayClusterLifecycleState.HEAD_READY,
            RayClusterLifecycleState.WORKERS_STARTING,
            RayClusterLifecycleState.READY,
            RayClusterLifecycleState.DRAINING,
        }:
            resources = record.spec.head_resources
            if record.registered_workers:
                resources = resources + record.spec.worker_resources.scaled(
                    record.registered_workers
                )
            return resources
        return RayResourceRequest()

    def _emit(
        self,
        record: _ClusterRecord,
        state: RayClusterLifecycleState,
        timestamp: float,
        *,
        reason: Optional[str] = None,
    ) -> RayClusterLifecycleEvent:
        event = RayClusterLifecycleEvent(
            cluster_id=record.spec.ray_cluster_id,
            state=state,
            timestamp=timestamp,
            allocation_id=(
                record.allocation.allocation_id
                if record.allocation is not None
                else None
            ),
            reason=reason,
            registered_workers=record.registered_workers,
            ready_resources=self._ready_resources(record),
        )
        self._events.append(event)
        return event

    def _record(self, cluster_id: str) -> _ClusterRecord:
        try:
            return self._clusters[cluster_id]
        except KeyError as exc:
            raise RayClusterLifecycleError(
                f"unknown Ray cluster {cluster_id!r}"
            ) from exc

    def _check_time(self, when: float) -> None:
        if when < self.time or not math.isfinite(when):
            raise RayClusterLifecycleError(
                "cluster lifecycle clock cannot move backwards or be non-finite"
            )