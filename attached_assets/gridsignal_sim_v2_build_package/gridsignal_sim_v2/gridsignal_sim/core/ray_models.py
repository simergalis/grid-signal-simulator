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


class KubernetesAdmissionProvider(str, Enum):
    """Batch admission layer above Kubernetes Pod placement."""

    KUEUE = "kueue"
    VOLCANO = "volcano"
    YUNIKORN = "yunikorn"
    LEGACY = "legacy"


class PowerEnforcementPolicy(str, Enum):
    """Simulated physical enforcement mode, separate from admission."""

    GPU_POWER_CAP = "gpu_power_cap"
    CPU_POWER_LIMIT = "cpu_power_limit"
    NODE_POWER_STATE = "node_power_state"
    CAPACITY_ONLY = "capacity_only"


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
    """Logical Ray resource vector used for placement and capacity validation.

    Ray CPU and memory values are scheduler bookkeeping, not hard runtime
    enforcement.  Physical usage is represented separately by
    :class:`RayMeasuredUsage`.
    """

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
class RayMeasuredUsage:
    """Observed or simulated physical usage, separate from Ray requests."""

    cpu_cores: float = 0.0
    memory_gib: float = 0.0
    gpu_utilization: float = 0.0
    gpu_power_kw: float = 0.0
    cpu_power_kw: float = 0.0

    def __post_init__(self) -> None:
        for name in ("cpu_cores", "memory_gib", "gpu_power_kw", "cpu_power_kw"):
            object.__setattr__(
                self, name, _validate_resource_value(name, getattr(self, name))
            )
        utilization = float(self.gpu_utilization)
        if not math.isfinite(utilization) or not 0.0 <= utilization <= 1.0:
            raise RayContractError(
                "gpu_utilization must be a finite number between 0 and 1"
            )
        object.__setattr__(self, "gpu_utilization", utilization)


@dataclass(frozen=True)
class InfrastructureAllocation:
    """Capacity allocated by Kubernetes or Slurm for one Ray cluster."""

    allocation_id: str
    backend: InfrastructureBackend
    resource_capacity: RayResourceRequest
    tenant_id: str | None = None
    admission_domain_id: str | None = None
    admission_queue_id: str | None = None
    capacity_budget_id: str | None = None

    def __post_init__(self) -> None:
        if not self.allocation_id:
            raise RayContractError("allocation_id must not be empty")
        try:
            object.__setattr__(self, "backend", InfrastructureBackend(self.backend))
        except ValueError as exc:
            raise RayContractError("unsupported infrastructure backend") from exc
        if (self.admission_domain_id is None) != (
            self.admission_queue_id is None
        ):
            raise RayContractError(
                "admission_domain_id and admission_queue_id must be provided together"
            )
        if self.capacity_budget_id is not None and self.admission_queue_id is None:
            raise RayContractError(
                "capacity_budget_id requires an admission_queue_id"
            )


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
    admission_provider: KubernetesAdmissionProvider | None = None
    # None derives the Rev 2 default: KubeRay is elastic, Slurm is fixed.
    elastic: bool | None = None
    power_enforcement_policy: PowerEnforcementPolicy = (
        PowerEnforcementPolicy.CAPACITY_ONLY
    )

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
        try:
            object.__setattr__(self, "backend", InfrastructureBackend(self.backend))
        except ValueError as exc:
            raise RayContractError("unsupported infrastructure backend") from exc
        if self.admission_provider is not None:
            try:
                object.__setattr__(
                    self,
                    "admission_provider",
                    KubernetesAdmissionProvider(self.admission_provider),
                )
            except ValueError as exc:
                raise RayContractError(
                    "unsupported Kubernetes admission provider"
                ) from exc
            if self.backend is not InfrastructureBackend.KUBERNETES:
                raise RayContractError(
                    "admission_provider is only valid for Kubernetes Ray clusters"
                )
        elif self.backend is InfrastructureBackend.KUBERNETES:
            object.__setattr__(
                self, "admission_provider", KubernetesAdmissionProvider.LEGACY
            )
        if self.elastic is None:
            object.__setattr__(
                self,
                "elastic",
                self.backend is InfrastructureBackend.KUBERNETES,
            )
        try:
            object.__setattr__(
                self,
                "power_enforcement_policy",
                PowerEnforcementPolicy(self.power_enforcement_policy),
            )
        except ValueError as exc:
            raise RayContractError(
                "unsupported power enforcement policy"
            ) from exc

    @property
    def maximum_resources(self) -> RayResourceRequest:
        """Head plus worst-case worker resources for this cluster."""
        return self.head_resources + self.worker_resources.scaled(self.max_workers)

    @property
    def minimum_resources(self) -> RayResourceRequest:
        """Head plus the initial worker footprint before KubeRay scaling."""
        worker_count = self.max_workers if self.fixed_allocation else self.min_workers
        return self.head_resources + self.worker_resources.scaled(worker_count)

    @property
    def fixed_allocation(self) -> bool:
        """Whether this cluster has a fixed infrastructure footprint by default."""
        return not bool(self.elastic)


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
    assigned_gpu_ids: tuple[str, ...] = ()
    measured_usage: RayMeasuredUsage | None = None
    duration_s: float | None = 1.0
    max_retries: int = 0
    phase_durations: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if not self.workload_id:
            raise RayContractError("workload_id must not be empty")
        if not self.ray_cluster_id:
            raise RayContractError("ray_cluster_id must not be empty")
        if self.replicas < 1:
            raise RayContractError("replicas must be at least one")
        if self.duration_s is not None:
            duration = float(self.duration_s)
            if not math.isfinite(duration) or duration < 0.0:
                raise RayContractError(
                    "duration_s must be finite and non-negative or None"
                )
            object.__setattr__(self, "duration_s", duration)
        if self.max_retries < 0:
            raise RayContractError("max_retries must be non-negative")
        normalized_phases = tuple(float(duration) for duration in self.phase_durations)
        if any(
            not math.isfinite(duration) or duration <= 0.0
            for duration in normalized_phases
        ):
            raise RayContractError(
                "phase_durations must contain finite positive durations"
            )
        object.__setattr__(self, "phase_durations", normalized_phases)
        if len(set(self.dependencies)) != len(self.dependencies):
            raise RayContractError("workload dependencies must be unique")
        if len(set(self.assigned_gpu_ids)) != len(self.assigned_gpu_ids):
            raise RayContractError("assigned GPU IDs must be unique")
        if any(not gpu_id for gpu_id in self.assigned_gpu_ids):
            raise RayContractError("assigned GPU IDs must not be empty")
        try:
            object.__setattr__(self, "kind", RayWorkloadKind(self.kind))
        except ValueError as exc:
            raise RayContractError("unsupported Ray workload kind") from exc

    @property
    def aggregate_resources(self) -> RayResourceRequest:
        return self.resource_request.scaled(self.replicas)

    @property
    def logical_requested_resources(self) -> RayResourceRequest:
        """Explicit alias separating logical requests from measured usage."""
        return self.resource_request


@dataclass(frozen=True)
class RayPlacementGroupSpec:
    """A gang of resource bundles that must be validated as one request."""

    placement_group_id: str
    ray_cluster_id: str
    bundles: tuple[RayResourceRequest, ...]
    strategy: RayPlacementStrategy = RayPlacementStrategy.PACK
    locality: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.placement_group_id:
            raise RayContractError("placement_group_id must not be empty")
        if not self.ray_cluster_id:
            raise RayContractError("ray_cluster_id must not be empty")
        if not self.bundles:
            raise RayContractError("placement groups require at least one bundle")
        try:
            object.__setattr__(
                self, "strategy", RayPlacementStrategy(self.strategy)
            )
        except ValueError as exc:
            raise RayContractError("unsupported Ray placement strategy") from exc
        normalized_locality = tuple(str(slot) for slot in self.locality)
        if len(set(normalized_locality)) != len(normalized_locality):
            raise RayContractError("placement group locality must be unique")
        if any(not slot for slot in normalized_locality):
            raise RayContractError("placement group locality labels must not be empty")
        object.__setattr__(self, "locality", normalized_locality)

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