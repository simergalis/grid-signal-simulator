"""Phase 4 logical Ray execution scheduler tests."""

from __future__ import annotations

import pytest

from core.infrastructure_admission import (
    InfrastructureAdmissionRequest,
    KubernetesAdmissionEngine,
)
from core.ray_cluster_engine import RayClusterEngine, RayClusterLifecycleState
from core.ray_execution_scheduler import (
    RayExecutionError,
    RayExecutionScheduler,
    RayPlacementGroupState,
    RayWorkloadState,
)
from core.ray_models import (
    InfrastructureBackend,
    RayClusterSpec,
    RayPlacementGroupSpec,
    RayPlacementStrategy,
    RayResourceRequest,
    RayWorkloadKind,
    RayWorkloadSpec,
)


def _cluster(cluster_id: str, *, workers: int = 1) -> RayClusterSpec:
    return RayClusterSpec(
        ray_cluster_id=cluster_id,
        infrastructure_allocation_id=f"kubernetes:{cluster_id}",
        backend=InfrastructureBackend.KUBERNETES,
        head_resources=RayResourceRequest(cpu=1, memory_gib=2),
        worker_resources=RayResourceRequest(cpu=2, gpu=1, memory_gib=4),
        min_workers=workers,
        max_workers=workers or 1,
    )


def _ready_engine(*clusters: RayClusterSpec) -> RayClusterEngine:
    admission = KubernetesAdmissionEngine(
        resource_capacity=RayResourceRequest(cpu=32, gpu=8, memory_gib=128),
        admission_domain_id="domain",
        admission_queue_id="ray",
    )
    engine = RayClusterEngine(
        kubernetes_admission=admission,
        head_startup_delay_s=0,
        worker_startup_delay_s=0,
        worker_registration_delay_s=0,
    )
    for cluster in clusters:
        engine.submit(
            cluster,
            InfrastructureAdmissionRequest(
                request_id=cluster.ray_cluster_id,
                backend=InfrastructureBackend.KUBERNETES,
                resource_request=cluster.maximum_resources,
                admission_domain_id="domain",
                admission_queue_id="ray",
            ),
        )
    engine.advance(0)
    assert all(
        engine.status(cluster.ray_cluster_id).state is RayClusterLifecycleState.READY
        for cluster in clusters
    )
    return engine


def test_workloads_wait_for_dependencies_and_transition_through_phases():
    cluster = _cluster("ray-phase", workers=1)
    scheduler = RayExecutionScheduler(_ready_engine(cluster))

    scheduler.submit_workload(
        RayWorkloadSpec(
            workload_id="producer",
            ray_cluster_id=cluster.ray_cluster_id,
            kind=RayWorkloadKind.TASK,
            resource_request=RayResourceRequest(cpu=1),
            duration_s=2,
            phase_durations=(1, 1),
        )
    )
    scheduler.submit_workload(
        RayWorkloadSpec(
            workload_id="consumer",
            ray_cluster_id=cluster.ray_cluster_id,
            kind=RayWorkloadKind.ACTOR,
            resource_request=RayResourceRequest(cpu=1),
            duration_s=None,
            dependencies=("producer",),
        )
    )

    started = scheduler.advance(0)
    assert [event.state for event in started] == [RayWorkloadState.RUNNING]
    assert scheduler.workload_status("consumer").state is RayWorkloadState.BLOCKED

    phase = scheduler.advance(1)
    assert phase[-1].phase_index == 1
    assert scheduler.workload_status("producer").state is RayWorkloadState.RUNNING

    completed = scheduler.advance(2)
    assert scheduler.workload_status("producer").state is RayWorkloadState.SUCCEEDED
    assert scheduler.workload_status("consumer").state is RayWorkloadState.RUNNING
    assert completed[-1].workload_id == "consumer"
    assert completed[-1].reason == "logical resources placed"


def test_placement_group_is_gang_admitted_and_does_not_double_count_workload():
    cluster = _cluster("ray-pg", workers=2)
    scheduler = RayExecutionScheduler(_ready_engine(cluster))
    group = scheduler.submit_placement_group(
        RayPlacementGroupSpec(
            placement_group_id="pg",
            ray_cluster_id=cluster.ray_cluster_id,
            bundles=(
                RayResourceRequest(cpu=1),
                RayResourceRequest(cpu=1),
            ),
            strategy=RayPlacementStrategy.STRICT_SPREAD,
        )
    )
    assert group.state is RayPlacementGroupState.QUEUED

    scheduler.submit_workload(
        RayWorkloadSpec(
            workload_id="distributed",
            ray_cluster_id=cluster.ray_cluster_id,
            kind=RayWorkloadKind.TRAINING,
            resource_request=RayResourceRequest(cpu=0.5),
            replicas=2,
            placement_group_id="pg",
            duration_s=1,
        )
    )
    scheduler.advance(0)
    assert scheduler.placement_group_status("pg").state is RayPlacementGroupState.PLACED
    assert scheduler.workload_status("distributed").state is RayWorkloadState.RUNNING
    assert scheduler.used_resources(cluster.ray_cluster_id).cpu == 2

    scheduler.advance(1)
    assert scheduler.workload_status("distributed").state is RayWorkloadState.SUCCEEDED
    released = scheduler.release_placement_group("pg", now=2)
    assert released.state is RayPlacementGroupState.RELEASED
    assert scheduler.used_resources(cluster.ray_cluster_id).cpu == 0


def test_spillback_preserves_requested_cluster_and_retries_after_release():
    source = _cluster("source", workers=0)
    alternate = _cluster("alternate", workers=0)
    scheduler = RayExecutionScheduler(_ready_engine(source, alternate))

    scheduler.submit_workload(
        RayWorkloadSpec(
            workload_id="occupier",
            ray_cluster_id=source.ray_cluster_id,
            kind=RayWorkloadKind.ACTOR,
            resource_request=RayResourceRequest(cpu=1),
            duration_s=None,
        )
    )
    scheduler.advance(0)
    scheduler.submit_workload(
        RayWorkloadSpec(
            workload_id="spillable",
            ray_cluster_id=source.ray_cluster_id,
            kind=RayWorkloadKind.TASK,
            resource_request=RayResourceRequest(cpu=0.5),
            duration_s=None,
            max_retries=1,
        ),
        spillback_cluster_ids=(alternate.ray_cluster_id,),
    )
    scheduler.advance(1)
    status = scheduler.workload_status("spillable")
    assert status.state is RayWorkloadState.RUNNING
    assert status.cluster_id == source.ray_cluster_id
    assert status.placement_cluster_id == alternate.ray_cluster_id

    retry = scheduler.fail_workload("spillable", "simulated worker failure", now=2)
    assert retry.state is RayWorkloadState.RETRYING
    assert scheduler.workload_status("spillable").state is RayWorkloadState.QUEUED
    scheduler.advance(3)
    assert scheduler.workload_status("spillable").attempt == 2
    assert scheduler.workload_status("spillable").placement_cluster_id == alternate.ray_cluster_id


def test_execution_requires_phase_three_ready_cluster():
    cluster = _cluster("not-ready", workers=1)
    engine = _ready_engine(cluster)
    engine.begin_drain(cluster.ray_cluster_id, now=1)
    scheduler = RayExecutionScheduler(engine)
    with pytest.raises(RayExecutionError, match="not ready"):
        scheduler.submit_workload(
            RayWorkloadSpec(
                workload_id="rejected",
                ray_cluster_id=cluster.ray_cluster_id,
                kind=RayWorkloadKind.TASK,
                resource_request=RayResourceRequest(cpu=1),
            )
        )