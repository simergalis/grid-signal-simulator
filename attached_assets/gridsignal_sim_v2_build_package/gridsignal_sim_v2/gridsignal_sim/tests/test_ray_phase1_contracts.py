"""Phase 1 Ray contract and compatibility tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.schemas import (
    InfrastructureAllocationSpec,
    RayClusterSpec,
    RayMeasuredUsageSpec,
    RayResourceRequestSpec,
    RayWorkloadSpec as WireRayWorkloadSpec,
    WorkloadEventSpec,
)
from core.models import WorkloadClass, WorkloadEventType, WorkloadSignal
from core.ray_models import (
    InfrastructureAllocation,
    InfrastructureBackend,
    RayClusterSpec as CoreRayClusterSpec,
    RayContractError,
    RayMeasuredUsage,
    RayResourceRequest,
    RayWorkloadKind,
    RayWorkloadSpec,
    validate_active_ray_workload_capacity,
    validate_ray_bindings,
)


def _allocation() -> InfrastructureAllocation:
    return InfrastructureAllocation(
        allocation_id="alloc-k8s-1",
        backend=InfrastructureBackend.KUBERNETES,
        resource_capacity=RayResourceRequest(
            cpu=64,
            gpu=8,
            memory_gib=512,
        ),
    )


def _cluster() -> CoreRayClusterSpec:
    return CoreRayClusterSpec(
        ray_cluster_id="ray-k8s-1",
        infrastructure_allocation_id="alloc-k8s-1",
        backend=InfrastructureBackend.KUBERNETES,
        head_resources=RayResourceRequest(cpu=2, memory_gib=8),
        worker_resources=RayResourceRequest(cpu=8, gpu=1, memory_gib=64),
        min_workers=1,
        max_workers=7,
    )


def test_resource_vectors_add_and_scale_without_losing_custom_resources():
    left = RayResourceRequest(cpu=2, gpu=1, custom_resources={"nvlink": 1})
    right = RayResourceRequest(cpu=3, gpu=2, custom_resources={"rdma": 2})

    total = left + right

    assert total.cpu == 5
    assert total.gpu == 3
    assert total.custom_resources == {"nvlink": 1.0, "rdma": 2.0}
    assert total.scaled(2).custom_resources == {"nvlink": 2.0, "rdma": 4.0}


def test_nested_ray_contract_binds_one_cluster_to_one_matching_allocation():
    validate_ray_bindings([_allocation()], [_cluster()])


def test_refined_defaults_mark_kuberay_elastic_and_slurm_fixed():
    kube_cluster = _cluster()
    slurm_cluster = CoreRayClusterSpec(
        ray_cluster_id="ray-slurm-1",
        infrastructure_allocation_id="alloc-slurm-1",
        backend=InfrastructureBackend.SLURM,
        worker_resources=RayResourceRequest(cpu=8, gpu=1),
    )

    assert kube_cluster.elastic is True
    assert kube_cluster.fixed_allocation is False
    assert slurm_cluster.elastic is False
    assert slurm_cluster.fixed_allocation is True


def test_refined_contract_rejects_partial_admission_identity():
    with pytest.raises(RayContractError, match="admission_domain_id"):
        InfrastructureAllocation(
            allocation_id="alloc-invalid",
            backend=InfrastructureBackend.KUBERNETES,
            resource_capacity=RayResourceRequest(gpu=1),
            admission_domain_id="domain-1",
        )


def test_refined_contract_keeps_logical_request_separate_from_measured_usage():
    usage = RayMeasuredUsage(
        cpu_cores=14.0,
        memory_gib=96.0,
        gpu_utilization=0.72,
        gpu_power_kw=8.4,
    )
    workload = RayWorkloadSpec(
        workload_id="task-measured",
        ray_cluster_id="ray-k8s-1",
        kind=RayWorkloadKind.TASK,
        resource_request=RayResourceRequest(cpu=1, gpu=1, memory_gib=8),
        assigned_gpu_ids=("gpu-7",),
        measured_usage=usage,
    )

    assert workload.logical_requested_resources.cpu == 1
    assert workload.measured_usage is usage
    assert workload.assigned_gpu_ids == ("gpu-7",)


def test_nested_ray_contract_rejects_duplicate_allocation_claims():
    first = _cluster()
    second = CoreRayClusterSpec(
        ray_cluster_id="ray-k8s-2",
        infrastructure_allocation_id=first.infrastructure_allocation_id,
        backend=first.backend,
        worker_resources=first.worker_resources,
        max_workers=1,
    )

    with pytest.raises(RayContractError, match="already claimed"):
        validate_ray_bindings([_allocation()], [first, second])


def test_nested_ray_contract_rejects_capacity_that_exceeds_parent():
    oversized = CoreRayClusterSpec(
        ray_cluster_id="ray-k8s-oversized",
        infrastructure_allocation_id="alloc-k8s-1",
        backend=InfrastructureBackend.KUBERNETES,
        worker_resources=RayResourceRequest(cpu=16, gpu=2, memory_gib=128),
        max_workers=7,
    )

    with pytest.raises(RayContractError, match="maximum resources"):
        validate_ray_bindings([_allocation()], [oversized])


def test_active_ray_workloads_cannot_collectively_exceed_cluster_capacity():
    first = RayWorkloadSpec(
        workload_id="task-1",
        ray_cluster_id="ray-k8s-1",
        kind=RayWorkloadKind.TASK,
        resource_request=RayResourceRequest(gpu=4),
    )
    second = RayWorkloadSpec(
        workload_id="task-2",
        ray_cluster_id="ray-k8s-1",
        kind=RayWorkloadKind.TASK,
        resource_request=RayResourceRequest(gpu=4),
    )
    validate_ray_bindings([_allocation()], [_cluster()], [first, second])

    third = RayWorkloadSpec(
        workload_id="task-3",
        ray_cluster_id="ray-k8s-1",
        kind=RayWorkloadKind.TASK,
        resource_request=RayResourceRequest(gpu=1),
    )
    with pytest.raises(RayContractError, match="active Ray workloads"):
        validate_active_ray_workload_capacity(
            [_cluster()], [first, second, third]
        )


def test_legacy_workload_signal_stays_valid_without_nested_identity():
    signal = WorkloadSignal(
        event_id="legacy-1",
        job_id="job-1",
        event_type=WorkloadEventType.STARTING,
        timestamp=0.0,
        hardware_profile_id="enterprise_8gpu_air",
        node_count=1,
        workload_class=WorkloadClass.TRAINING,
        site_id="site-1",
    )

    assert signal.infrastructure_allocation_id is None
    assert signal.ray_cluster_id is None


def test_workload_signal_rejects_partial_nested_identity():
    with pytest.raises(ValueError, match="provided together"):
        WorkloadSignal(
            event_id="ray-1",
            job_id="job-1",
            event_type=WorkloadEventType.STARTING,
            timestamp=0.0,
            hardware_profile_id="enterprise_8gpu_air",
            node_count=1,
            workload_class=WorkloadClass.TRAINING,
            site_id="site-1",
            ray_cluster_id="ray-k8s-1",
        )


def test_wire_schema_accepts_nested_ray_identity_and_resource_contracts():
    event = WorkloadEventSpec(
        event_type="starting",
        timestamp=0,
        infrastructure_allocation_id="alloc-k8s-1",
        ray_cluster_id="ray-k8s-1",
        ray_workload_id="task-1",
        admission_domain_id="kueue-domain",
        admission_queue_id="gpu-queue",
        capacity_budget_id="budget-1",
        admission_provider="kueue",
        power_enforcement_policy="gpu_power_cap",
    )
    cluster = RayClusterSpec(
        ray_cluster_id="ray-k8s-1",
        infrastructure_allocation_id="alloc-k8s-1",
        backend="kubernetes",
        worker_resources=RayResourceRequestSpec(cpu=8, gpu=1),
        max_workers=4,
    )

    assert event.ray_workload_id == "task-1"
    assert event.admission_provider == "kueue"
    assert cluster.worker_resources.gpu == 1


def test_wire_schema_exposes_refined_resource_and_cluster_policies():
    allocation = InfrastructureAllocationSpec(
        allocation_id="alloc-k8s-1",
        backend="kubernetes",
        resource_capacity=RayResourceRequestSpec(cpu=64, gpu=8),
        admission_domain_id="kueue-domain",
        admission_queue_id="gpu-queue",
        capacity_budget_id="budget-1",
    )
    cluster = RayClusterSpec(
        ray_cluster_id="ray-k8s-1",
        infrastructure_allocation_id=allocation.allocation_id,
        backend="kubernetes",
        worker_resources=RayResourceRequestSpec(cpu=8, gpu=1),
        admission_provider="kueue",
        power_enforcement_policy="gpu_power_cap",
    )
    workload = WireRayWorkloadSpec(
        workload_id="task-1",
        ray_cluster_id=cluster.ray_cluster_id,
        kind="task",
        resource_request=RayResourceRequestSpec(cpu=1, gpu=1),
        assigned_gpu_ids=["gpu-1"],
        measured_usage=RayMeasuredUsageSpec(
            cpu_cores=0.8,
            gpu_utilization=0.75,
            gpu_power_kw=8.0,
        ),
    )

    assert allocation.admission_queue_id == "gpu-queue"
    assert cluster.elastic is None  # backend-derived default is core behavior
    assert workload.measured_usage.gpu_utilization == 0.75


def test_wire_schema_rejects_partial_nested_ray_identity():
    with pytest.raises(ValidationError, match="provided together"):
        WorkloadEventSpec(
            event_type="starting",
            timestamp=0,
            ray_cluster_id="ray-k8s-1",
        )