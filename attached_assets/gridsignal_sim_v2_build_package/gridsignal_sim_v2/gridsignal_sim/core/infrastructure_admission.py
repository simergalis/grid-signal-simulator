"""Phase 2 infrastructure admission engines.

Infrastructure admission is deliberately separate from Ray lifecycle and
application scheduling:

* Kubernetes admission decides whether a RayCluster/RayJob-sized allocation
  may enter the cluster.  Pod placement remains the responsibility of
  :mod:`core.kube_scheduler`.
* Slurm admission is an adapter over the existing deterministic Slurm queue.
  Partition, QOS, reservation, GRES, dependency, and preemption policy remain
  owned by :class:`core.slurm_scheduler.SlurmSchedulerEngine`.

No engine in this module starts Ray processes or schedules Ray tasks.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional

from .models import WorkloadEventType
from .ray_models import (
    InfrastructureAllocation,
    InfrastructureBackend,
    KubernetesAdmissionProvider,
    RayContractError,
    RayResourceRequest,
)
from .slurm_scheduler import SlurmJobSpec, SlurmSchedulerEngine, SlurmSchedulerError


class InfrastructureAdmissionError(RayContractError):
    """Raised when an admission request or transition is invalid."""


class InfrastructureAdmissionState(str, Enum):
    QUEUED = "queued"
    ADMITTED = "admitted"
    REJECTED = "rejected"
    PREEMPTED = "preempted"
    RELEASED = "released"


@dataclass(frozen=True)
class InfrastructureAdmissionRequest:
    """An atomic infrastructure allocation request.

    ``resource_request`` is the complete allocation, not one Pod or Ray task.
    A gang request is therefore admitted atomically: this phase never admits
    only part of the requested allocation.
    """

    request_id: str
    backend: InfrastructureBackend
    resource_request: RayResourceRequest
    admission_domain_id: str
    admission_queue_id: str
    capacity_budget_id: Optional[str] = None
    tenant_id: Optional[str] = None
    priority: int = 0
    submitted_at: float = 0.0
    gang_id: Optional[str] = None
    gang_size: int = 1
    preemptible: bool = True

    def __post_init__(self) -> None:
        if not self.request_id:
            raise InfrastructureAdmissionError("request_id must not be empty")
        try:
            object.__setattr__(self, "backend", InfrastructureBackend(self.backend))
        except ValueError as exc:
            raise InfrastructureAdmissionError(
                "unsupported infrastructure backend"
            ) from exc
        if not self.admission_domain_id:
            raise InfrastructureAdmissionError(
                "admission_domain_id must not be empty"
            )
        if not self.admission_queue_id:
            raise InfrastructureAdmissionError(
                "admission_queue_id must not be empty"
            )
        if self.capacity_budget_id is not None and not self.capacity_budget_id:
            raise InfrastructureAdmissionError(
                "capacity_budget_id must not be empty when provided"
            )
        if self.gang_size < 1:
            raise InfrastructureAdmissionError("gang_size must be at least one")
        if not math.isfinite(float(self.submitted_at)):
            raise InfrastructureAdmissionError("submitted_at must be finite")


@dataclass(frozen=True)
class InfrastructureAdmissionEvent:
    """Stable result emitted by either infrastructure admission path."""

    request_id: str
    backend: InfrastructureBackend
    state: InfrastructureAdmissionState
    timestamp: float
    reason: Optional[str] = None
    allocation: Optional[InfrastructureAllocation] = None
    preempted_request_ids: tuple[str, ...] = ()


def _subtract(
    left: RayResourceRequest, right: RayResourceRequest
) -> RayResourceRequest:
    """Subtract a used vector while preserving a non-negative resource vector."""

    names = set(left.custom_resources) | set(right.custom_resources)
    return RayResourceRequest(
        cpu=max(0.0, left.cpu - right.cpu),
        gpu=max(0.0, left.gpu - right.gpu),
        memory_gib=max(0.0, left.memory_gib - right.memory_gib),
        object_store_memory_gib=max(
            0.0, left.object_store_memory_gib - right.object_store_memory_gib
        ),
        custom_resources={
            name: max(
                0.0,
                left.custom_resources.get(name, 0.0)
                - right.custom_resources.get(name, 0.0),
            )
            for name in names
            if left.custom_resources.get(name, 0.0)
            - right.custom_resources.get(name, 0.0)
            > 0.0
        },
    )


def _add(
    left: RayResourceRequest, right: RayResourceRequest
) -> RayResourceRequest:
    return left + right


class KubernetesAdmissionEngine:
    """Deterministic batch admission above Kubernetes Pod placement.

    The engine models queue, quota, capacity budget, priority, gang
    atomicity, optional preemption, and admission delay.  It does not place
    Pods; a later lifecycle phase can pass an admitted allocation to the
    existing ``KubeSchedulerEngine``.
    """

    def __init__(
        self,
        *,
        provider: KubernetesAdmissionProvider = KubernetesAdmissionProvider.LEGACY,
        resource_capacity: RayResourceRequest,
        admission_domain_id: str = "kubernetes",
        admission_queue_id: Optional[str] = None,
        queue_quotas: Optional[Mapping[str, RayResourceRequest]] = None,
        capacity_budgets: Optional[Mapping[str, RayResourceRequest]] = None,
        admission_delay_s: float = 0.0,
        preemption_enabled: bool = False,
    ) -> None:
        try:
            self.provider = KubernetesAdmissionProvider(provider)
        except ValueError as exc:
            raise InfrastructureAdmissionError(
                "unsupported Kubernetes admission provider"
            ) from exc
        if not admission_domain_id:
            raise InfrastructureAdmissionError(
                "admission_domain_id must not be empty"
            )
        if admission_queue_id is not None and not admission_queue_id:
            raise InfrastructureAdmissionError(
                "admission_queue_id must not be empty when provided"
            )
        if admission_delay_s < 0 or not math.isfinite(float(admission_delay_s)):
            raise InfrastructureAdmissionError(
                "admission_delay_s must be finite and non-negative"
            )
        self.resource_capacity = resource_capacity
        self.admission_domain_id = admission_domain_id
        self.admission_queue_id = admission_queue_id
        self.queue_quotas = dict(queue_quotas or {})
        self.capacity_budgets = dict(capacity_budgets or {})
        self.admission_delay_s = float(admission_delay_s)
        self.preemption_enabled = bool(preemption_enabled)

        self._requests: dict[str, InfrastructureAdmissionRequest] = {}
        self._states: dict[str, InfrastructureAdmissionState] = {}
        self._allocations: dict[str, InfrastructureAllocation] = {}
        self._submitted_sequence: dict[str, int] = {}
        self._sequence = 0
        self._used = RayResourceRequest()
        self._queue_used: dict[str, RayResourceRequest] = {}
        self._budget_used: dict[str, RayResourceRequest] = {}
        self._events: list[InfrastructureAdmissionEvent] = []
        self.time = 0.0

    @property
    def used_resources(self) -> RayResourceRequest:
        return self._used

    @property
    def available_resources(self) -> RayResourceRequest:
        return _subtract(self.resource_capacity, self._used)

    @property
    def events(self) -> tuple[InfrastructureAdmissionEvent, ...]:
        return tuple(self._events)

    def state(self, request_id: str) -> InfrastructureAdmissionState:
        try:
            return self._states[request_id]
        except KeyError as exc:
            raise InfrastructureAdmissionError(
                f"unknown admission request {request_id!r}"
            ) from exc

    def submit(
        self, request: InfrastructureAdmissionRequest
    ) -> InfrastructureAdmissionEvent:
        if request.backend is not InfrastructureBackend.KUBERNETES:
            raise InfrastructureAdmissionError(
                "KubernetesAdmissionEngine only accepts Kubernetes requests"
            )
        if request.admission_domain_id != self.admission_domain_id:
            raise InfrastructureAdmissionError(
                "request admission domain does not match this engine"
            )
        if (
            self.admission_queue_id is not None
            and request.admission_queue_id != self.admission_queue_id
        ):
            raise InfrastructureAdmissionError(
                "request admission queue does not match this engine"
            )
        if request.request_id in self._requests:
            raise InfrastructureAdmissionError(
                f"admission request {request.request_id!r} was already submitted"
            )
        self._requests[request.request_id] = request
        self._states[request.request_id] = InfrastructureAdmissionState.QUEUED
        self._submitted_sequence[request.request_id] = self._sequence
        self._sequence += 1
        self.time = max(self.time, request.submitted_at)
        if not request.resource_request.fits_within(self.resource_capacity):
            return self._record(
                InfrastructureAdmissionEvent(
                    request_id=request.request_id,
                    backend=request.backend,
                    state=InfrastructureAdmissionState.REJECTED,
                    timestamp=request.submitted_at,
                    reason="request exceeds Kubernetes admission capacity",
                )
            )
        if (
            request.capacity_budget_id is not None
            and request.capacity_budget_id not in self.capacity_budgets
        ):
            return self._record(
                InfrastructureAdmissionEvent(
                    request_id=request.request_id,
                    backend=request.backend,
                    state=InfrastructureAdmissionState.REJECTED,
                    timestamp=request.submitted_at,
                    reason="unknown Kubernetes capacity budget",
                )
            )
        quota = self.queue_quotas.get(request.admission_queue_id)
        if quota is not None and not request.resource_request.fits_within(quota):
            return self._record(
                InfrastructureAdmissionEvent(
                    request_id=request.request_id,
                    backend=request.backend,
                    state=InfrastructureAdmissionState.REJECTED,
                    timestamp=request.submitted_at,
                    reason="request exceeds Kubernetes queue quota",
                )
            )
        return self._record(
            InfrastructureAdmissionEvent(
                request_id=request.request_id,
                backend=request.backend,
                state=InfrastructureAdmissionState.QUEUED,
                timestamp=request.submitted_at,
                reason="admission queue",
            )
        )

    def advance(self, now: float) -> tuple[InfrastructureAdmissionEvent, ...]:
        if now < self.time:
            raise InfrastructureAdmissionError(
                "admission clock cannot move backwards"
            )
        self.time = float(now)
        emitted: list[InfrastructureAdmissionEvent] = []
        pending = sorted(
            (
                request
                for request in self._requests.values()
                if self._states[request.request_id]
                is InfrastructureAdmissionState.QUEUED
                and request.submitted_at + self.admission_delay_s <= self.time
            ),
            key=lambda request: (
                -request.priority,
                request.submitted_at,
                self._submitted_sequence[request.request_id],
                request.request_id,
            ),
        )
        for request in pending:
            if self._can_admit(request):
                emitted.append(self._admit(request, self.time))
                continue
            if self.preemption_enabled:
                victims = self._select_preemption_victims(request)
                if victims:
                    for victim in victims:
                        emitted.append(self._preempt(victim, self.time))
                    emitted.append(self._admit(request, self.time, victims))
        return tuple(emitted)

    def release(
        self, request_id: str, now: Optional[float] = None
    ) -> InfrastructureAdmissionEvent:
        request = self._request(request_id)
        state = self._states[request_id]
        when = self.time if now is None else float(now)
        if when < self.time:
            raise InfrastructureAdmissionError(
                "admission clock cannot move backwards"
            )
        self.time = max(self.time, when)
        if state is not InfrastructureAdmissionState.ADMITTED:
            raise InfrastructureAdmissionError(
                f"admission request {request_id!r} is not admitted"
            )
        self._used = _subtract(self._used, request.resource_request)
        self._queue_used[request.admission_queue_id] = _subtract(
            self._queue_used.get(request.admission_queue_id, RayResourceRequest()),
            request.resource_request,
        )
        if request.capacity_budget_id is not None:
            self._budget_used[request.capacity_budget_id] = _subtract(
                self._budget_used.get(
                    request.capacity_budget_id, RayResourceRequest()
                ),
                request.resource_request,
            )
        self._states[request_id] = InfrastructureAdmissionState.RELEASED
        allocation = self._allocations.pop(request_id)
        return self._record(
            InfrastructureAdmissionEvent(
                request_id=request_id,
                backend=request.backend,
                state=InfrastructureAdmissionState.RELEASED,
                timestamp=self.time,
                allocation=allocation,
                reason="allocation released",
            )
        )

    def allocation(self, request_id: str) -> Optional[InfrastructureAllocation]:
        return self._allocations.get(request_id)

    def _can_admit(self, request: InfrastructureAdmissionRequest) -> bool:
        if not request.resource_request.fits_within(self.available_resources):
            return False
        quota = self.queue_quotas.get(request.admission_queue_id)
        if quota is not None:
            queue_used = self._queue_used.get(
                request.admission_queue_id, RayResourceRequest()
            )
            if not _add(
                queue_used, request.resource_request
            ).fits_within(quota):
                return False
        if request.capacity_budget_id is not None:
            budget_used = self._budget_used.get(
                request.capacity_budget_id, RayResourceRequest()
            )
            if not _add(
                budget_used, request.resource_request
            ).fits_within(self.capacity_budgets[request.capacity_budget_id]):
                return False
        return True

    def _select_preemption_victims(
        self, request: InfrastructureAdmissionRequest
    ) -> tuple[InfrastructureAdmissionRequest, ...]:
        quota = self.queue_quotas.get(request.admission_queue_id)
        queue_used = self._queue_used.get(
            request.admission_queue_id, RayResourceRequest()
        )
        if quota is not None and not _add(
            queue_used, request.resource_request
        ).fits_within(quota):
            return ()
        if request.capacity_budget_id is not None:
            budget_used = self._budget_used.get(
                request.capacity_budget_id, RayResourceRequest()
            )
            if not _add(
                budget_used, request.resource_request
            ).fits_within(self.capacity_budgets[request.capacity_budget_id]):
                return ()
        simulated = self._used
        victims: list[InfrastructureAdmissionRequest] = []
        candidates = sorted(
            (
                candidate
                for candidate in self._requests.values()
                if self._states[candidate.request_id]
                is InfrastructureAdmissionState.ADMITTED
                and candidate.preemptible
                and candidate.priority < request.priority
            ),
            key=lambda candidate: (
                candidate.priority,
                candidate.submitted_at,
                candidate.request_id,
            ),
        )
        for candidate in candidates:
            simulated = _subtract(simulated, candidate.resource_request)
            victims.append(candidate)
            if request.resource_request.fits_within(
                _subtract(self.resource_capacity, simulated)
            ):
                return tuple(victims)
        return ()

    def _admit(
        self,
        request: InfrastructureAdmissionRequest,
        timestamp: float,
        victims: tuple[InfrastructureAdmissionRequest, ...] = (),
    ) -> InfrastructureAdmissionEvent:
        allocation = InfrastructureAllocation(
            allocation_id=f"kubernetes:{request.request_id}",
            backend=InfrastructureBackend.KUBERNETES,
            resource_capacity=request.resource_request,
            tenant_id=request.tenant_id,
            admission_domain_id=request.admission_domain_id,
            admission_queue_id=request.admission_queue_id,
            capacity_budget_id=request.capacity_budget_id,
        )
        self._used = _add(self._used, request.resource_request)
        self._queue_used[request.admission_queue_id] = _add(
            self._queue_used.get(request.admission_queue_id, RayResourceRequest()),
            request.resource_request,
        )
        if request.capacity_budget_id is not None:
            self._budget_used[request.capacity_budget_id] = _add(
                self._budget_used.get(
                    request.capacity_budget_id, RayResourceRequest()
                ),
                request.resource_request,
            )
        self._states[request.request_id] = InfrastructureAdmissionState.ADMITTED
        self._allocations[request.request_id] = allocation
        return self._record(
            InfrastructureAdmissionEvent(
                request_id=request.request_id,
                backend=request.backend,
                state=InfrastructureAdmissionState.ADMITTED,
                timestamp=timestamp,
                allocation=allocation,
                preempted_request_ids=tuple(v.request_id for v in victims),
                reason="gang admitted atomically"
                if request.gang_id is not None
                else "capacity admitted",
            )
        )

    def _preempt(
        self,
        request: InfrastructureAdmissionRequest,
        timestamp: float,
    ) -> InfrastructureAdmissionEvent:
        self._used = _subtract(self._used, request.resource_request)
        self._queue_used[request.admission_queue_id] = _subtract(
            self._queue_used.get(request.admission_queue_id, RayResourceRequest()),
            request.resource_request,
        )
        if request.capacity_budget_id is not None:
            self._budget_used[request.capacity_budget_id] = _subtract(
                self._budget_used.get(
                    request.capacity_budget_id, RayResourceRequest()
                ),
                request.resource_request,
            )
        self._states[request.request_id] = InfrastructureAdmissionState.PREEMPTED
        allocation = self._allocations.pop(request.request_id)
        return self._record(
            InfrastructureAdmissionEvent(
                request_id=request.request_id,
                backend=request.backend,
                state=InfrastructureAdmissionState.PREEMPTED,
                timestamp=timestamp,
                allocation=allocation,
                reason="preempted by higher-priority admission request",
            )
        )

    def _request(self, request_id: str) -> InfrastructureAdmissionRequest:
        try:
            return self._requests[request_id]
        except KeyError as exc:
            raise InfrastructureAdmissionError(
                f"unknown admission request {request_id!r}"
            ) from exc

    def _record(
        self, event: InfrastructureAdmissionEvent
    ) -> InfrastructureAdmissionEvent:
        if (
            event.request_id not in self._states
            or event.state is InfrastructureAdmissionState.REJECTED
        ):
            self._states[event.request_id] = event.state
        self._events.append(event)
        return event


class SlurmAdmissionEngine:
    """Expose the existing Slurm pending queue through admission contracts."""

    def __init__(
        self,
        scheduler: SlurmSchedulerEngine,
        *,
        admission_domain_id: str = "slurm",
        admission_queue_id: Optional[str] = None,
        capacity_budget_id: Optional[str] = None,
    ) -> None:
        if not admission_domain_id:
            raise InfrastructureAdmissionError(
                "admission_domain_id must not be empty"
            )
        self.scheduler = scheduler
        self.admission_domain_id = admission_domain_id
        self.admission_queue_id = admission_queue_id
        self.capacity_budget_id = capacity_budget_id
        self._specs: dict[str, SlurmJobSpec] = {}
        self._states: dict[str, InfrastructureAdmissionState] = {}
        self._allocations: dict[str, InfrastructureAllocation] = {}
        self._events: list[InfrastructureAdmissionEvent] = []
        self.time = scheduler.time

    @property
    def events(self) -> tuple[InfrastructureAdmissionEvent, ...]:
        return tuple(self._events)

    def state(self, request_id: str) -> InfrastructureAdmissionState:
        try:
            return self._states[request_id]
        except KeyError as exc:
            raise InfrastructureAdmissionError(
                f"unknown admission request {request_id!r}"
            ) from exc

    def submit(
        self, spec: SlurmJobSpec, now: Optional[float] = None
    ) -> InfrastructureAdmissionEvent:
        if spec.job_id in self._specs:
            raise InfrastructureAdmissionError(
                f"admission request {spec.job_id!r} was already submitted"
            )
        when = spec.arrival_time if now is None else float(now)
        self._specs[spec.job_id] = spec
        try:
            self.scheduler.submit(spec, now=when)
        except SlurmSchedulerError as exc:
            event = InfrastructureAdmissionEvent(
                request_id=spec.job_id,
                backend=InfrastructureBackend.SLURM,
                state=InfrastructureAdmissionState.REJECTED,
                timestamp=when,
                reason=str(exc),
            )
            self._states[spec.job_id] = InfrastructureAdmissionState.REJECTED
            self._events.append(event)
            return event
        self._states[spec.job_id] = InfrastructureAdmissionState.QUEUED
        self.time = max(self.time, when)
        return self._record(
            InfrastructureAdmissionEvent(
                request_id=spec.job_id,
                backend=InfrastructureBackend.SLURM,
                state=InfrastructureAdmissionState.QUEUED,
                timestamp=when,
                reason="Slurm pending queue",
            )
        )

    def submit_request(
        self,
        request: InfrastructureAdmissionRequest,
        *,
        allocation_duration_s: float = 1_000_000_000.0,
    ) -> InfrastructureAdmissionEvent:
        """Translate a generic Ray allocation into a Slurm admission request."""
        if request.backend is not InfrastructureBackend.SLURM:
            raise InfrastructureAdmissionError(
                "SlurmAdmissionEngine only accepts Slurm requests"
            )
        if request.admission_domain_id != self.admission_domain_id:
            raise InfrastructureAdmissionError(
                "request admission domain does not match this engine"
            )
        if allocation_duration_s <= 0 or not math.isfinite(
            float(allocation_duration_s)
        ):
            raise InfrastructureAdmissionError(
                "allocation_duration_s must be finite and positive"
            )
        return self.submit(
            SlurmJobSpec(
                job_id=request.request_id,
                arrival_time=request.submitted_at,
                duration=float(allocation_duration_s),
                gpus_per_node=math.ceil(request.resource_request.gpu),
                cpus_per_node=math.ceil(request.resource_request.cpu),
                memory_mb_per_node=math.ceil(
                    request.resource_request.memory_gib * 1024.0
                ),
                partition=request.admission_queue_id,
                priority=float(request.priority),
                tenant_id=request.tenant_id,
                preemptible=request.preemptible,
            ),
            now=request.submitted_at,
        )

    def advance(self, now: float) -> tuple[InfrastructureAdmissionEvent, ...]:
        if now < self.time:
            raise InfrastructureAdmissionError(
                "admission clock cannot move backwards"
            )
        self.time = float(now)
        emitted: list[InfrastructureAdmissionEvent] = []
        for signal in self.scheduler.advance(now):
            if signal.event_type is WorkloadEventType.RUNNING:
                emitted.append(self._admit(signal.job_id, signal.timestamp))
            elif signal.event_type in {
                WorkloadEventType.JOB_END,
                WorkloadEventType.CANCELLED,
                WorkloadEventType.JOB_FAILED,
                WorkloadEventType.JOB_TIMEOUT,
            }:
                if self._states.get(signal.job_id) is InfrastructureAdmissionState.ADMITTED:
                    emitted.append(
                        self._release(
                            signal.job_id,
                            signal.timestamp,
                            reason=signal.event_type.value,
                        )
                    )
            elif signal.event_type is WorkloadEventType.JOB_PREEMPTED:
                if signal.job_id in self._states:
                    allocation = self._allocations.pop(signal.job_id, None)
                    requeued = self.scheduler.summary(signal.job_id).state == "PENDING"
                    state = (
                        InfrastructureAdmissionState.QUEUED
                        if requeued
                        else InfrastructureAdmissionState.PREEMPTED
                    )
                    self._states[signal.job_id] = state
                    emitted.append(
                        self._record(
                            InfrastructureAdmissionEvent(
                                request_id=signal.job_id,
                                backend=InfrastructureBackend.SLURM,
                                state=state,
                                timestamp=signal.timestamp,
                                allocation=allocation,
                                reason=(
                                    "Slurm preemption policy requeued job"
                                    if requeued
                                    else "Slurm preemption policy"
                                ),
                            )
                        )
                    )
        return tuple(emitted)

    def release(
        self, request_id: str, now: Optional[float] = None
    ) -> InfrastructureAdmissionEvent:
        if request_id not in self._specs:
            raise InfrastructureAdmissionError(
                f"unknown admission request {request_id!r}"
            )
        if self._states.get(request_id) is not InfrastructureAdmissionState.ADMITTED:
            raise InfrastructureAdmissionError(
                f"admission request {request_id!r} is not admitted"
            )
        when = self.time if now is None else float(now)
        self.scheduler.cancel(request_id, now=when)
        self.time = max(self.time, when)
        return self._release(request_id, self.time, reason="released by caller")

    def allocation(self, request_id: str) -> Optional[InfrastructureAllocation]:
        return self._allocations.get(request_id)

    def _admit(
        self, request_id: str, timestamp: float
    ) -> InfrastructureAdmissionEvent:
        summary = self.scheduler.summary(request_id)
        allocation = summary.allocation
        if allocation is None:
            raise InfrastructureAdmissionError(
                f"Slurm job {request_id!r} became running without allocation"
            )
        spec = self._specs[request_id]
        queue_id = self.admission_queue_id or spec.partition or spec.qos
        ray_allocation = InfrastructureAllocation(
            allocation_id=f"slurm:{request_id}",
            backend=InfrastructureBackend.SLURM,
            resource_capacity=RayResourceRequest(
                cpu=allocation.cpus,
                gpu=allocation.gpus,
                memory_gib=allocation.memory_mb / 1024.0,
            ),
            tenant_id=spec.tenant_id,
            admission_domain_id=self.admission_domain_id,
            admission_queue_id=queue_id,
            capacity_budget_id=self.capacity_budget_id,
        )
        self._allocations[request_id] = ray_allocation
        self._states[request_id] = InfrastructureAdmissionState.ADMITTED
        return self._record(
            InfrastructureAdmissionEvent(
                request_id=request_id,
                backend=InfrastructureBackend.SLURM,
                state=InfrastructureAdmissionState.ADMITTED,
                timestamp=timestamp,
                allocation=ray_allocation,
                reason="Slurm allocation granted",
            )
        )

    def _release(
        self, request_id: str, timestamp: float, *, reason: str
    ) -> InfrastructureAdmissionEvent:
        allocation = self._allocations.pop(request_id, None)
        self._states[request_id] = InfrastructureAdmissionState.RELEASED
        return self._record(
            InfrastructureAdmissionEvent(
                request_id=request_id,
                backend=InfrastructureBackend.SLURM,
                state=InfrastructureAdmissionState.RELEASED,
                timestamp=timestamp,
                allocation=allocation,
                reason=reason,
            )
        )

    def _record(
        self, event: InfrastructureAdmissionEvent
    ) -> InfrastructureAdmissionEvent:
        self._events.append(event)
        return event