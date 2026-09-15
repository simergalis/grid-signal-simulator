"""Phase 1 Ray contract models.

These models describe the identity and resource boundaries between an
infrastructure scheduler and a Ray runtime.  They intentionally contain no
queueing, lifecycle, autoscaling, or host-execution behavior; those belong to
later Ray simulator phases.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum


class RayContractError(ValueError):
    """Raised when a Ray contract would violate an accounting invariant."""


class InfrastructureBackend(str, Enum):
    KUBERNETES = "kubernetes"
    SLURM = "slurm"


class RayWorkloadKind(str, Enum):
    JOB = "job"
    TASK = "task"
    ACTOR = "actor"
    TRAINING = "training"
    INFERENCE = "inference"
    DATA_PROCESSING = "data_processing"
    HYPERPARAMETER_TRIAL = "hyperparameter_trial"


class RayPlacementStrategy(str, Enum):
    PACK = "pack"
    SPREAD = "spread"
    STRICT_PACK = "strict_pack"
    STRICT_SPREAD = "strict_spread"


def _validate_resource_value(name: str, value: float) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise RayContractError(f"{name} must be a finite non-negative number")
    return value


@dataclass(frozen=True)
class RayResourceRequest:
    """A Ray resource vector used for placement and capacity validation."""

    cpu: float = 0.0
    gpu: float = 0.0
    memory_gib: float = 0.0
    object_store_memory_gib: float = 0.0
    custom_resources: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "cpu",
            "gpu",
            "memory_gib",
            "object_store_memory_gib",
        ):
            object.__setattr__(
                self, name, _validate_resource_value(name, getattr(self, name))
            )
        normalized: dict[str, float] = {}
        for name, value in dict(self.custom_resources).items():
            if not str(name):
                raise RayContractError("custom resource names must not be empty")
            normalized[str(name)] = _validate_resource_value(
                f"custom_resources[{name!r}]", value
            )
        object.__setattr__(self, "custom_resources", normalized)

    def __add__(self, other: "RayResourceRequest") -> "RayResourceRequest":
        if not isinstance(other, RayResourceRequest):
            return NotImplemented
        names = set(self.custom_resources) | set(other.custom_resources)
        return RayResourceRequest(
            cpu=self.cpu + other.cpu,
            gpu=self.gpu + other.gpu,
            memory_gib=self.memory_gib + other.memory_gib,
            object_store_memory_gib=(
                self.object_store_memory_gib + other.object_store_memory_gib
            ),
            custom_resources={
                name: self.custom_resources.get(name, 0.0)
                + other.custom_resources.get(name, 0.0)
                for name in names
            },
        )

    def scaled(self, factor: int) -> "RayResourceRequest":
        if factor < 0:
            raise RayContractError("resource scale factor must be non-negative")
        return RayResourceRequest(
            cpu=self.cpu * factor,
            gpu=self.gpu * factor,
            memory_gib=self.memory_gib * factor,
            object_store_memory_gib=self.object_store_memory_gib * factor,
            custom_resources={
                name: value * factor
                for name, value in self.custom_resources.items()
            },
        )

    def fits_within(self, capacity: "RayResourceRequest") -> bool:
        if not isinstance(capacity, RayResourceRequest):
            raise TypeError("capacity must be a RayResourceRequest")
        scalar_fields = (
            ("cpu", self.cpu, capacity.cpu),
            ("gpu", self.gpu, capacity.gpu),
            ("memory_gib", self.memory_gib, capacity.memory_gib),
            (
                "object_store_memory_gib",
                self.object_store_memory_gib,
                capacity.object_store_memory_gib,
            ),
        )
        if any(requested > available for _, requested, available in scalar_fields):
            return False
        return all(
            requested <= capacity.custom_resources.get(name, 0.0)
            for name, requested in self.custom_resources.items()
        )


@dataclass(frozen=True)
class InfrastructureAllocation:
    """Capacity allocated by Kubernetes or Slurm for one Ray cluster."""

    allocation_id: str
    backend: InfrastructureBackend
    resource_capacity: RayResourceRequest
    tenant_id: str | None = None

    def __post_init__(self) -> None:
        if not self.allocation_id:
            raise RayContractError("allocation_id must not be empty")


@dataclass(frozen=True)
class RayClusterSpec:
    """A Ray runtime bound to exactly one infrastructure allocation."""

    ray_cluster_id: str
    infrastructure_allocation_id: str
    backend: InfrastructureBackend
    worker_resources: RayResourceRequest
    min_workers: int = 0
    max_workers: int = 1
    head_resources: RayResourceRequest = field(
        default_factory=lambda: RayResourceRequest(cpu=1.0)
    )
    tenant_id: str | None = None

    def __post_init__(self) -> None:
        if not self.ray_cluster_id:
            raise RayContractError("ray_cluster_id must not be empty")
        if not self.infrastructure_allocation_id:
            raise RayContractError(
                "infrastructure_allocation_id must not be empty"
            )
        if self.min_workers < 0:
            raise RayContractError("min_workers must be non-negative")
        if self.max_workers < 1 or self.max_workers < self.min_workers:
            raise RayContractError(
                "max_workers must be at least min_workers and at least one"
            )

    @property
    def maximum_resources(self) -> RayResourceRequest:
        """Head plus worst-case worker resources for this cluster."""
        return self.head_resources + self.worker_resources.scaled(self.max_workers)


@dataclass(frozen=True)
class RayWorkloadSpec:
    """One application-level Ray workload bound to a Ray cluster."""

    workload_id: str
    ray_cluster_id: str
    kind: RayWorkloadKind
    resource_request: RayResourceRequest
    parent_workload_id: str | None = None
    placement_group_id: str | None = None
    dependencies: tuple[str, ...] = ()
    replicas: int = 1

    def __post_init__(self) -> None:
        if not self.workload_id:
            raise RayContractError("workload_id must not be empty")
        if not self.ray_cluster_id:
            raise RayContractError("ray_cluster_id must not be empty")
        if self.replicas < 1:
            raise RayContractError("replicas must be at least one")
        if len(set(self.dependencies)) != len(self.dependencies):
            raise RayContractError("workload dependencies must be unique")

    @property
    def aggregate_resources(self) -> RayResourceRequest:
        return self.resource_request.scaled(self.replicas)


@dataclass(frozen=True)
class RayPlacementGroupSpec:
    """A gang of resource bundles that must be validated as one request."""

    placement_group_id: str
    ray_cluster_id: str
    bundles: tuple[RayResourceRequest, ...]
    strategy: RayPlacementStrategy = RayPlacementStrategy.PACK

    def __post_init__(self) -> None:
        if not self.placement_group_id:
            raise RayContractError("placement_group_id must not be empty")
        if not self.ray_cluster_id:
            raise RayContractError("ray_cluster_id must not be empty")
        if not self.bundles:
            raise RayContractError("placement groups require at least one bundle")

    @property
    def aggregate_resources(self) -> RayResourceRequest:
        result = RayResourceRequest()
        for bundle in self.bundles:
            result = result + bundle
        return result


def validate_ray_bindings(
    allocations: Iterable[InfrastructureAllocation],
    clusters: Iterable[RayClusterSpec],
    workloads: Iterable[RayWorkloadSpec] = (),
    placement_groups: Iterable[RayPlacementGroupSpec] = (),
) -> None:
    """Validate parent identity and capacity ownership.

    This is a Phase 1 contract check, not a scheduler.  It catches the two
    dangerous forms of double counting before a later runtime engine exists:

    * two Ray clusters claiming the same infrastructure allocation;
    * a Ray cluster or workload claiming more resources than its parent.
    """

    allocation_by_id: dict[str, InfrastructureAllocation] = {}
    for allocation in allocations:
        if allocation.allocation_id in allocation_by_id:
            raise RayContractError(
                f"duplicate infrastructure allocation: {allocation.allocation_id!r}"
            )
        allocation_by_id[allocation.allocation_id] = allocation

    cluster_by_id: dict[str, RayClusterSpec] = {}
    allocation_owner: dict[str, str] = {}
    for cluster in clusters:
        if cluster.ray_cluster_id in cluster_by_id:
            raise RayContractError(
                f"duplicate Ray cluster: {cluster.ray_cluster_id!r}"
            )
        allocation = allocation_by_id.get(cluster.infrastructure_allocation_id)
        if allocation is None:
            raise RayContractError(
                f"Ray cluster {cluster.ray_cluster_id!r} references unknown "
                f"infrastructure allocation {cluster.infrastructure_allocation_id!r}"
            )
        if allocation.backend is not cluster.backend:
            raise RayContractError(
                f"Ray cluster {cluster.ray_cluster_id!r} backend "
                f"{cluster.backend.value!r} does not match allocation "
                f"{allocation.backend.value!r}"
            )
        previous_owner = allocation_owner.get(allocation.allocation_id)
        if previous_owner is not None:
            raise RayContractError(
                f"infrastructure allocation {allocation.allocation_id!r} is "
                f"already claimed by Ray cluster {previous_owner!r}"
            )
        if not cluster.maximum_resources.fits_within(
            allocation.resource_capacity
        ):
            raise RayContractError(
                f"Ray cluster {cluster.ray_cluster_id!r} maximum resources "
                "exceed its infrastructure allocation"
            )
        cluster_by_id[cluster.ray_cluster_id] = cluster
        allocation_owner[allocation.allocation_id] = cluster.ray_cluster_id

    for workload in workloads:
        cluster = cluster_by_id.get(workload.ray_cluster_id)
        if cluster is None:
            raise RayContractError(
                f"Ray workload {workload.workload_id!r} references unknown "
                f"Ray cluster {workload.ray_cluster_id!r}"
            )
        if not workload.aggregate_resources.fits_within(
            cluster.maximum_resources
        ):
            raise RayContractError(
                f"Ray workload {workload.workload_id!r} exceeds the maximum "
                f"resource capacity of cluster {cluster.ray_cluster_id!r}"
            )

    for placement_group in placement_groups:
        cluster = cluster_by_id.get(placement_group.ray_cluster_id)
        if cluster is None:
            raise RayContractError(
                f"placement group {placement_group.placement_group_id!r} "
                f"references unknown Ray cluster {placement_group.ray_cluster_id!r}"
            )
        if not placement_group.aggregate_resources.fits_within(
            cluster.maximum_resources
        ):
            raise RayContractError(
                f"placement group {placement_group.placement_group_id!r} "
                "exceeds its Ray cluster capacity"
            )


def validate_active_ray_workload_capacity(
    clusters: Iterable[RayClusterSpec],
    workloads: Iterable[RayWorkloadSpec],
) -> None:
    """Validate a snapshot of concurrently active Ray workload demand."""

    cluster_by_id = {cluster.ray_cluster_id: cluster for cluster in clusters}
    totals: dict[str, RayResourceRequest] = defaultdict(RayResourceRequest)
    for workload in workloads:
        if workload.ray_cluster_id not in cluster_by_id:
            raise RayContractError(
                f"active workload {workload.workload_id!r} references unknown "
                f"Ray cluster {workload.ray_cluster_id!r}"
            )
        totals[workload.ray_cluster_id] = (
            totals[workload.ray_cluster_id] + workload.aggregate_resources
        )
    for cluster_id, total in totals.items():
        if not total.fits_within(cluster_by_id[cluster_id].maximum_resources):
            raise RayContractError(
                f"active Ray workloads exceed cluster {cluster_id!r} capacity"
            )