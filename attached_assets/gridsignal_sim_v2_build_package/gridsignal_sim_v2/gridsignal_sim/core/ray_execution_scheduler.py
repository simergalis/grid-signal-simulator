"""Phase 4 logical Ray execution scheduler.

The scheduler starts only on Phase 3 ``READY`` clusters.  It owns logical
placement, dependencies, placement-group admission, retries, spillback, and
workload phase transitions.  It does not allocate physical nodes, admit
Kubernetes or Slurm capacity, enforce CPU/memory/power, or autoscale.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence

from .ray_cluster_engine import (
    RayClusterEngine,
    RayClusterLifecycleError,
    RayClusterLifecycleState,
)
from .ray_models import (
    RayClusterSpec,
    RayContractError,
    RayPlacementGroupSpec,
    RayPlacementStrategy,
    RayResourceRequest,
    RayWorkloadKind,
    RayWorkloadSpec,
)


class RayExecutionError(RayContractError):
    """Raised when a logical Ray execution transition is invalid."""


class RayWorkloadState(str, Enum):
    QUEUED = "queued"
    BLOCKED = "blocked"
    RUNNING = "running"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RayPlacementGroupState(str, Enum):
    QUEUED = "queued"
    PLACED = "placed"
    RELEASED = "released"
    FAILED = "failed"


@dataclass(frozen=True)
class RayWorkloadEvent:
    workload_id: str
    state: RayWorkloadState
    timestamp: float
    cluster_id: str
    placement_cluster_id: Optional[str] = None
    attempt: int = 0
    phase_index: Optional[int] = None
    reason: Optional[str] = None
    assigned_slots: tuple[str, ...] = ()


@dataclass(frozen=True)
class RayPlacementGroupEvent:
    placement_group_id: str
    state: RayPlacementGroupState
    timestamp: float
    cluster_id: str
    assignments: tuple[str, ...] = ()
    reason: Optional[str] = None


@dataclass(frozen=True)
class RayWorkloadStatus:
    workload_id: str
    state: RayWorkloadState
    cluster_id: str
    placement_cluster_id: Optional[str]
    attempt: int
    phase_index: Optional[int]
    assigned_slots: tuple[str, ...]
    started_at: Optional[float]
    finished_at: Optional[float]


@dataclass(frozen=True)
class RayPlacementGroupStatus:
    placement_group_id: str
    state: RayPlacementGroupState
    cluster_id: str
    assignments: tuple[str, ...]


@dataclass
class _Slot:
    slot_id: str
    capacity: RayResourceRequest
    used: RayResourceRequest = field(default_factory=RayResourceRequest)


@dataclass
class _PlacementRuntime:
    spec: RayPlacementGroupSpec
    state: RayPlacementGroupState
    assignments: tuple[str, ...] = ()
    bundle_used: list[RayResourceRequest] = field(default_factory=list)


@dataclass
class _WorkloadRuntime:
    spec: RayWorkloadSpec
    state: RayWorkloadState
    spillback_cluster_ids: tuple[str, ...] = ()
    placement_cluster_id: Optional[str] = None
    attempt: int = 0
    phase_index: Optional[int] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    ends_at: Optional[float] = None
    assigned_slots: tuple[str, ...] = ()
    normal_assignments: tuple[tuple[str, RayResourceRequest], ...] = ()
    placement_assignments: tuple[tuple[str, int, RayResourceRequest], ...] = ()


@dataclass
class _ClusterRuntime:
    spec: RayClusterSpec
    slots: dict[str, _Slot]


def _subtract(left: RayResourceRequest, right: RayResourceRequest) -> RayResourceRequest:
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


class RayExecutionScheduler:
    """Deterministic logical scheduler for ready Ray clusters."""

    def __init__(self, cluster_engine: RayClusterEngine) -> None:
        self.cluster_engine = cluster_engine
        self._clusters: dict[str, _ClusterRuntime] = {}
        self._workloads: dict[str, _WorkloadRuntime] = {}
        self._placements: dict[str, _PlacementRuntime] = {}
        self._workload_sequence: dict[str, int] = {}
        self._placement_sequence: dict[str, int] = {}
        self._sequence = 0
        self._placement_sequence_value = 0
        self._events: list[RayWorkloadEvent] = []
        self._placement_events: list[RayPlacementGroupEvent] = []
        self.time = 0.0

    @property
    def events(self) -> tuple[RayWorkloadEvent, ...]:
        return tuple(self._events)

    @property
    def placement_events(self) -> tuple[RayPlacementGroupEvent, ...]:
        return tuple(self._placement_events)

    def submit_placement_group(
        self, spec: RayPlacementGroupSpec
    ) -> RayPlacementGroupEvent:
        if spec.placement_group_id in self._placements:
            raise RayExecutionError(
                f"placement group {spec.placement_group_id!r} was already submitted"
            )
        self._require_ready_cluster(spec.ray_cluster_id)
        runtime = _PlacementRuntime(
            spec=spec,
            state=RayPlacementGroupState.QUEUED,
            bundle_used=[RayResourceRequest() for _ in spec.bundles],
        )
        self._placements[spec.placement_group_id] = runtime
        self._placement_sequence[spec.placement_group_id] = (
            self._placement_sequence_value
        )
        self._placement_sequence_value += 1
        return self._emit_placement(
            runtime,
            self.time,
            reason="waiting for logical placement",
        )

    def submit_workload(
        self,
        spec: RayWorkloadSpec,
        *,
        spillback_cluster_ids: Sequence[str] = (),
    ) -> RayWorkloadEvent:
        if spec.workload_id in self._workloads:
            raise RayExecutionError(
                f"Ray workload {spec.workload_id!r} was already submitted"
            )
        self._require_ready_cluster(spec.ray_cluster_id)
        if spec.workload_id in spec.dependencies:
            raise RayExecutionError("a workload cannot depend on itself")
        candidates = tuple(dict.fromkeys((spec.ray_cluster_id, *spillback_cluster_ids)))
        for cluster_id in candidates:
            self._require_ready_cluster(cluster_id)
        runtime = _WorkloadRuntime(
            spec=spec,
            state=RayWorkloadState.QUEUED,
            spillback_cluster_ids=tuple(candidates[1:]),
        )
        self._workloads[spec.workload_id] = runtime
        self._workload_sequence[spec.workload_id] = self._sequence
        self._sequence += 1
        if not self._dependencies_ready(runtime):
            runtime.state = RayWorkloadState.BLOCKED
            reason = "waiting for workload dependencies"
        elif spec.placement_group_id is not None and (
            spec.placement_group_id not in self._placements
            or self._placements[spec.placement_group_id].state
            is not RayPlacementGroupState.PLACED
        ):
            runtime.state = RayWorkloadState.BLOCKED
            reason = "waiting for placement group"
        else:
            reason = "waiting for logical capacity"
        return self._emit_workload(
            runtime,
            self.time,
            reason=reason,
            placement_cluster_id=None,
        )

    def advance(self, now: float) -> tuple[RayWorkloadEvent, ...]:
        if now < self.time or not math.isfinite(float(now)):
            raise RayExecutionError(
                "execution scheduler clock cannot move backwards or be non-finite"
            )
        self.time = float(now)
        emitted: list[RayWorkloadEvent] = []
        self._refresh_ready_clusters()
        for runtime in tuple(self._workloads.values()):
            emitted.extend(self._progress_running(runtime, self.time))

        progress = True
        while progress:
            progress = False
            for placement in self._pending_placements():
                event = self._try_place_group(placement, self.time)
                if event is not None:
                    progress = True
            for runtime in self._pending_workloads():
                if not self._dependencies_ready(runtime):
                    runtime.state = RayWorkloadState.BLOCKED
                    continue
                if runtime.spec.placement_group_id is not None:
                    group = self._placements.get(runtime.spec.placement_group_id)
                    if group is None or group.state is not RayPlacementGroupState.PLACED:
                        continue
                event = self._try_start_workload(runtime, self.time)
                if event is not None:
                    emitted.append(event)
                    progress = True
        return tuple(emitted)

    def fail_workload(
        self, workload_id: str, reason: str, now: Optional[float] = None
    ) -> RayWorkloadEvent:
        runtime = self._workload(workload_id)
        when = self.time if now is None else float(now)
        self._check_time(when)
        if runtime.state is not RayWorkloadState.RUNNING:
            raise RayExecutionError(
                f"workload {workload_id!r} is not running"
            )
        self._release_workload_resources(runtime)
        runtime.finished_at = when
        if runtime.attempt <= runtime.spec.max_retries:
            runtime.state = RayWorkloadState.RETRYING
            event = self._emit_workload(
                runtime,
                when,
                reason=reason,
                placement_cluster_id=runtime.placement_cluster_id,
            )
            runtime.state = RayWorkloadState.QUEUED
            return event
        runtime.state = RayWorkloadState.FAILED
        return self._emit_workload(
            runtime,
            when,
            reason=reason,
            placement_cluster_id=runtime.placement_cluster_id,
        )

    def cancel_workload(
        self, workload_id: str, now: Optional[float] = None
    ) -> RayWorkloadEvent:
        runtime = self._workload(workload_id)
        when = self.time if now is None else float(now)
        self._check_time(when)
        if runtime.state in {
            RayWorkloadState.SUCCEEDED,
            RayWorkloadState.FAILED,
            RayWorkloadState.CANCELLED,
        }:
            raise RayExecutionError(
                f"workload {workload_id!r} is terminal"
            )
        if runtime.state is RayWorkloadState.RUNNING:
            self._release_workload_resources(runtime)
        runtime.state = RayWorkloadState.CANCELLED
        runtime.finished_at = when
        return self._emit_workload(
            runtime,
            when,
            reason="cancelled",
            placement_cluster_id=runtime.placement_cluster_id,
        )

    def release_placement_group(
        self, placement_group_id: str, now: Optional[float] = None
    ) -> RayPlacementGroupEvent:
        runtime = self._placement(placement_group_id)
        when = self.time if now is None else float(now)
        self._check_time(when)
        if runtime.state is not RayPlacementGroupState.PLACED:
            raise RayExecutionError(
                f"placement group {placement_group_id!r} is not placed"
            )
        if any(
            workload.state in {
                RayWorkloadState.RUNNING,
                RayWorkloadState.QUEUED,
                RayWorkloadState.BLOCKED,
                RayWorkloadState.RETRYING,
            }
            and workload.spec.placement_group_id == placement_group_id
            for workload in self._workloads.values()
        ):
            raise RayExecutionError(
                "placement group cannot be released while workloads use it"
            )
        cluster = self._clusters[runtime.spec.ray_cluster_id]
        for slot_id, bundle in zip(runtime.assignments, runtime.spec.bundles):
            cluster.slots[slot_id].used = _subtract(
                cluster.slots[slot_id].used, bundle
            )
        runtime.state = RayPlacementGroupState.RELEASED
        return self._emit_placement(
            runtime,
            when,
            reason="placement group released",
        )

    def workload_status(self, workload_id: str) -> RayWorkloadStatus:
        runtime = self._workload(workload_id)
        return RayWorkloadStatus(
            workload_id=workload_id,
            state=runtime.state,
            cluster_id=runtime.spec.ray_cluster_id,
            placement_cluster_id=runtime.placement_cluster_id,
            attempt=runtime.attempt,
            phase_index=runtime.phase_index,
            assigned_slots=runtime.assigned_slots,
            started_at=runtime.started_at,
            finished_at=runtime.finished_at,
        )

    def placement_group_status(
        self, placement_group_id: str
    ) -> RayPlacementGroupStatus:
        runtime = self._placement(placement_group_id)
        return RayPlacementGroupStatus(
            placement_group_id=placement_group_id,
            state=runtime.state,
            cluster_id=runtime.spec.ray_cluster_id,
            assignments=runtime.assignments,
        )

    def used_resources(self, cluster_id: str) -> RayResourceRequest:
        self._require_ready_cluster(cluster_id)
        runtime = self._clusters[cluster_id]
        total = RayResourceRequest()
        for slot in runtime.slots.values():
            total = total + slot.used
        return total

    def pending_resource_demand(self, cluster_id: str) -> RayResourceRequest:
        """Return ready-to-run logical demand still waiting on this cluster."""
        self._require_ready_cluster(cluster_id)
        total = RayResourceRequest()
        for runtime in self._workloads.values():
            if runtime.spec.ray_cluster_id != cluster_id:
                continue
            if runtime.state not in {
                RayWorkloadState.QUEUED,
                RayWorkloadState.BLOCKED,
            }:
                continue
            if not self._dependencies_ready(runtime):
                continue
            group = (
                self._placements.get(runtime.spec.placement_group_id)
                if runtime.spec.placement_group_id is not None
                else None
            )
            if group is None:
                total = total + runtime.spec.aggregate_resources
            elif group.state is RayPlacementGroupState.QUEUED:
                # The bundle reservation already represents this workload's
                # physical demand; do not count the workload a second time.
                continue
            elif group.state is not RayPlacementGroupState.PLACED:
                total = total + runtime.spec.aggregate_resources
        for group in self._placements.values():
            if (
                group.spec.ray_cluster_id == cluster_id
                and group.state is RayPlacementGroupState.QUEUED
            ):
                total = total + group.spec.aggregate_resources
        return total

    def worker_used_resources(self, cluster_id: str) -> RayResourceRequest:
        """Return logical usage on worker slots, excluding the Ray head."""
        self._require_ready_cluster(cluster_id)
        runtime = self._clusters[cluster_id]
        total = RayResourceRequest()
        for slot_id, slot in runtime.slots.items():
            if slot_id.startswith("worker-"):
                total = total + slot.used
        return total

    def sync_cluster(self, cluster_id: str) -> None:
        """Synchronize logical worker slots after a KubeRay scale event."""
        self._require_ready_cluster(cluster_id)
        status = self.cluster_engine.status(cluster_id)
        runtime = self._clusters[cluster_id]
        current = len([slot for slot_id, slot in runtime.slots.items() if slot_id.startswith("worker-")])
        if status.registered_workers > current:
            for index in range(current, status.registered_workers):
                slot_id = f"worker-{index}"
                runtime.slots[slot_id] = _Slot(slot_id, runtime.spec.worker_resources)
        elif status.registered_workers < current:
            for index in range(current - 1, status.registered_workers - 1, -1):
                slot_id = f"worker-{index}"
                slot = runtime.slots.get(slot_id)
                if slot is not None and slot.used != RayResourceRequest():
                    raise RayExecutionError(
                        f"cannot remove busy Ray worker slot {slot_id!r}"
                    )
                runtime.slots.pop(slot_id, None)

    def _try_place_group(
        self, runtime: _PlacementRuntime, timestamp: float
    ) -> Optional[RayPlacementGroupEvent]:
        if runtime.state is not RayPlacementGroupState.QUEUED:
            return None
        cluster = self._clusters[runtime.spec.ray_cluster_id]
        candidates = [
            slot
            for slot in cluster.slots.values()
            if not runtime.spec.locality or slot.slot_id in runtime.spec.locality
        ]
        assignments = self._choose_bundle_slots(runtime.spec, candidates)
        if assignments is None:
            return None
        for slot_id, bundle in zip(assignments, runtime.spec.bundles):
            slot = cluster.slots[slot_id]
            slot.used = slot.used + bundle
        runtime.assignments = assignments
        runtime.state = RayPlacementGroupState.PLACED
        return self._emit_placement(
            runtime,
            timestamp,
            reason="placement group admitted atomically",
        )

    def _choose_bundle_slots(
        self, spec: RayPlacementGroupSpec, candidates: list[_Slot]
    ) -> Optional[tuple[str, ...]]:
        if not candidates:
            return None
        simulated = {slot.slot_id: slot.used for slot in candidates}

        def fits(slot_id: str, bundle: RayResourceRequest) -> bool:
            slot = next(slot for slot in candidates if slot.slot_id == slot_id)
            return bundle.fits_within(_subtract(slot.capacity, simulated[slot_id]))

        if spec.strategy is RayPlacementStrategy.STRICT_PACK:
            for slot in candidates:
                used = simulated[slot.slot_id]
                if _sum_resources(spec.bundles).fits_within(
                    _subtract(slot.capacity, used)
                ):
                    return tuple(slot.slot_id for _ in spec.bundles)
            return None

        assignments: list[str] = []
        remaining = list(candidates)
        for index, bundle in enumerate(spec.bundles):
            options = remaining if spec.strategy is RayPlacementStrategy.STRICT_SPREAD else candidates
            chosen: Optional[_Slot] = None
            if spec.strategy is RayPlacementStrategy.SPREAD:
                options = sorted(
                    options,
                    key=lambda slot: (
                        slot.slot_id in assignments,
                        slot.slot_id,
                    ),
                )
            else:
                options = list(options)
            for slot in options:
                if fits(slot.slot_id, bundle):
                    chosen = slot
                    break
            if chosen is None:
                return None
            assignments.append(chosen.slot_id)
            simulated[chosen.slot_id] = simulated[chosen.slot_id] + bundle
            if spec.strategy is RayPlacementStrategy.STRICT_SPREAD:
                remaining = [
                    slot for slot in remaining if slot.slot_id != chosen.slot_id
                ]
        return tuple(assignments)

    def _try_start_workload(
        self, runtime: _WorkloadRuntime, timestamp: float
    ) -> Optional[RayWorkloadEvent]:
        if runtime.state not in {
            RayWorkloadState.QUEUED,
            RayWorkloadState.BLOCKED,
        }:
            return None
        if runtime.spec.placement_group_id is not None:
            group = self._placements.get(runtime.spec.placement_group_id)
            candidates = (
                (group.spec.ray_cluster_id,)
                if group is not None
                else (runtime.spec.ray_cluster_id,)
            )
        else:
            candidates = (
                runtime.spec.ray_cluster_id,
                *self._spillback_candidates(runtime.spec),
            )
        for cluster_id in dict.fromkeys(candidates):
            cluster = self._clusters.get(cluster_id)
            if cluster is None:
                continue
            placement = (
                self._placements.get(runtime.spec.placement_group_id)
                if runtime.spec.placement_group_id is not None
                else None
            )
            if placement is not None:
                assignments = self._place_in_group(runtime.spec, placement)
                if assignments is None:
                    continue
                runtime.placement_assignments = assignments
                runtime.assigned_slots = tuple(item[0] for item in assignments)
            else:
                assignments = self._place_normal(cluster, runtime.spec)
                if assignments is None:
                    continue
                runtime.normal_assignments = assignments
                runtime.assigned_slots = tuple(item[0] for item in assignments)
            runtime.placement_cluster_id = cluster_id
            runtime.state = RayWorkloadState.RUNNING
            runtime.attempt += 1
            runtime.started_at = timestamp
            runtime.finished_at = None
            runtime.phase_index = 0 if runtime.spec.phase_durations else None
            duration = (
                sum(runtime.spec.phase_durations)
                if runtime.spec.phase_durations
                else runtime.spec.duration_s
            )
            runtime.ends_at = (
                None if duration is None else timestamp + duration
            )
            reason = (
                "spillback placement"
                if cluster_id != runtime.spec.ray_cluster_id
                else "logical resources placed"
            )
            return self._emit_workload(
                runtime,
                timestamp,
                reason=reason,
                placement_cluster_id=cluster_id,
            )
        runtime.state = RayWorkloadState.QUEUED
        return None

    def _place_normal(
        self, cluster: _ClusterRuntime, spec: RayWorkloadSpec
    ) -> Optional[tuple[tuple[str, RayResourceRequest], ...]]:
        simulated = {slot_id: slot.used for slot_id, slot in cluster.slots.items()}
        assignments: list[tuple[str, RayResourceRequest]] = []
        for _ in range(spec.replicas):
            chosen = None
            for slot in cluster.slots.values():
                if spec.resource_request.fits_within(
                    _subtract(slot.capacity, simulated[slot.slot_id])
                ):
                    chosen = slot
                    break
            if chosen is None:
                return None
            simulated[chosen.slot_id] = (
                simulated[chosen.slot_id] + spec.resource_request
            )
            assignments.append((chosen.slot_id, spec.resource_request))
        for slot_id, resources in assignments:
            cluster.slots[slot_id].used = cluster.slots[slot_id].used + resources
        return tuple(assignments)

    def _place_in_group(
        self, spec: RayWorkloadSpec, group: _PlacementRuntime
    ) -> Optional[tuple[tuple[str, int, RayResourceRequest], ...]]:
        if spec.replicas > len(group.spec.bundles):
            return None
        simulated = list(group.bundle_used)
        assignments: list[tuple[str, int, RayResourceRequest]] = []
        for index in range(spec.replicas):
            bundle = group.spec.bundles[index]
            if not spec.resource_request.fits_within(
                _subtract(bundle, simulated[index])
            ):
                return None
            simulated[index] = simulated[index] + spec.resource_request
            assignments.append(
                (group.assignments[index], index, spec.resource_request)
            )
        group.bundle_used[:] = simulated
        return tuple(assignments)

    def _progress_running(
        self, runtime: _WorkloadRuntime, now: float
    ) -> list[RayWorkloadEvent]:
        if runtime.state is not RayWorkloadState.RUNNING:
            return []
        emitted: list[RayWorkloadEvent] = []
        if runtime.spec.phase_durations and runtime.started_at is not None:
            elapsed = now - runtime.started_at
            cumulative = 0.0
            phase = runtime.phase_index or 0
            while phase < len(runtime.spec.phase_durations) - 1:
                cumulative += runtime.spec.phase_durations[phase]
                if elapsed < cumulative:
                    break
                phase += 1
                runtime.phase_index = phase
                emitted.append(
                    self._emit_workload(
                        runtime,
                        runtime.started_at + cumulative,
                        reason="workload phase advanced",
                        placement_cluster_id=runtime.placement_cluster_id,
                    )
                )
        if runtime.ends_at is not None and runtime.ends_at <= now:
            self._release_workload_resources(runtime)
            runtime.state = RayWorkloadState.SUCCEEDED
            runtime.finished_at = runtime.ends_at
            emitted.append(
                self._emit_workload(
                    runtime,
                    runtime.ends_at,
                    reason="workload completed",
                    placement_cluster_id=runtime.placement_cluster_id,
                )
            )
        return emitted

    def _release_workload_resources(self, runtime: _WorkloadRuntime) -> None:
        if runtime.normal_assignments and runtime.placement_cluster_id:
            cluster = self._clusters[runtime.placement_cluster_id]
            for slot_id, resources in runtime.normal_assignments:
                cluster.slots[slot_id].used = _subtract(
                    cluster.slots[slot_id].used, resources
                )
        if runtime.placement_assignments and runtime.spec.placement_group_id:
            group = self._placements[runtime.spec.placement_group_id]
            for _slot_id, bundle_index, resources in runtime.placement_assignments:
                group.bundle_used[bundle_index] = _subtract(
                    group.bundle_used[bundle_index], resources
                )
        runtime.normal_assignments = ()
        runtime.placement_assignments = ()
        runtime.assigned_slots = ()

    def _refresh_ready_clusters(self) -> None:
        for cluster_id in tuple(self._workloads_cluster_ids()):
            self._ensure_cluster_runtime(cluster_id)
        for placement in self._placements.values():
            self._ensure_cluster_runtime(placement.spec.ray_cluster_id)

    def _ensure_cluster_runtime(self, cluster_id: str) -> None:
        status = self.cluster_engine.status(cluster_id)
        if status.state is not RayClusterLifecycleState.READY:
            return
        if cluster_id in self._clusters:
            return
        spec = self.cluster_engine.spec(cluster_id)
        slots = {
            "head": _Slot("head", spec.head_resources),
        }
        for index in range(status.registered_workers):
            slot_id = f"worker-{index}"
            slots[slot_id] = _Slot(slot_id, spec.worker_resources)
        self._clusters[cluster_id] = _ClusterRuntime(spec=spec, slots=slots)

    def _pending_placements(self) -> list[_PlacementRuntime]:
        return [
            runtime
            for _id, runtime in sorted(
                self._placements.items(),
                key=lambda item: self._placement_sequence[item[0]],
            )
            if runtime.state is RayPlacementGroupState.QUEUED
        ]

    def _pending_workloads(self) -> list[_WorkloadRuntime]:
        return [
            runtime
            for _id, runtime in sorted(
                self._workloads.items(),
                key=lambda item: self._workload_sequence[item[0]],
            )
            if runtime.state in {
                RayWorkloadState.QUEUED,
                RayWorkloadState.BLOCKED,
            }
        ]

    def _dependencies_ready(self, runtime: _WorkloadRuntime) -> bool:
        return all(
            self._workloads.get(dependency) is not None
            and self._workloads[dependency].state is RayWorkloadState.SUCCEEDED
            for dependency in runtime.spec.dependencies
        )

    def _spillback_candidates(self, spec: RayWorkloadSpec) -> tuple[str, ...]:
        return self._workloads[spec.workload_id].spillback_cluster_ids

    def _emit_workload(
        self,
        runtime: _WorkloadRuntime,
        timestamp: float,
        *,
        reason: Optional[str],
        placement_cluster_id: Optional[str],
    ) -> RayWorkloadEvent:
        event = RayWorkloadEvent(
            workload_id=runtime.spec.workload_id,
            state=runtime.state,
            timestamp=timestamp,
            cluster_id=runtime.spec.ray_cluster_id,
            placement_cluster_id=placement_cluster_id,
            attempt=runtime.attempt,
            phase_index=runtime.phase_index,
            reason=reason,
            assigned_slots=runtime.assigned_slots,
        )
        self._events.append(event)
        return event

    def _emit_placement(
        self,
        runtime: _PlacementRuntime,
        timestamp: float,
        *,
        reason: Optional[str],
    ) -> RayPlacementGroupEvent:
        event = RayPlacementGroupEvent(
            placement_group_id=runtime.spec.placement_group_id,
            state=runtime.state,
            timestamp=timestamp,
            cluster_id=runtime.spec.ray_cluster_id,
            assignments=runtime.assignments,
            reason=reason,
        )
        self._placement_events.append(event)
        return event

    def _require_ready_cluster(self, cluster_id: str) -> None:
        try:
            status = self.cluster_engine.status(cluster_id)
        except RayClusterLifecycleError as exc:
            raise RayExecutionError(str(exc)) from exc
        if status.state is not RayClusterLifecycleState.READY:
            raise RayExecutionError(
                f"Ray cluster {cluster_id!r} is not ready"
            )
        self._ensure_cluster_runtime(cluster_id)

    def _workload(self, workload_id: str) -> _WorkloadRuntime:
        try:
            return self._workloads[workload_id]
        except KeyError as exc:
            raise RayExecutionError(
                f"unknown Ray workload {workload_id!r}"
            ) from exc

    def _placement(self, placement_group_id: str) -> _PlacementRuntime:
        try:
            return self._placements[placement_group_id]
        except KeyError as exc:
            raise RayExecutionError(
                f"unknown placement group {placement_group_id!r}"
            ) from exc

    def _workloads_cluster_ids(self) -> set[str]:
        return {
            runtime.spec.ray_cluster_id for runtime in self._workloads.values()
        }

    def _check_time(self, when: float) -> None:
        if when < self.time or not math.isfinite(when):
            raise RayExecutionError(
                "execution scheduler clock cannot move backwards or be non-finite"
            )


def _sum_resources(resources: Sequence[RayResourceRequest]) -> RayResourceRequest:
    total = RayResourceRequest()
    for resource in resources:
        total = total + resource
    return total