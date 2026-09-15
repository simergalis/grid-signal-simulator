"""Phase 3 Ray cluster startup and readiness tests."""

from __future__ import annotations

from core.infrastructure_admission import (
    InfrastructureAdmissionRequest,
    InfrastructureAdmissionState,
    KubernetesAdmissionEngine,
    SlurmAdmissionEngine,
)
from core.ray_cluster_engine import (
    RayClusterEngine,
    RayClusterLifecycleState,
)
from core.ray_models import InfrastructureBackend, RayClusterSpec, RayResourceRequest
from core.slurm_scheduler import SlurmNode, SlurmSchedulerEngine


def _kube_cluster(cluster_id: str, *, min_workers: int = 1) -> RayClusterSpec:
    return RayClusterSpec(
        ray_cluster_id=cluster_id,
        infrastructure_allocation_id=f"kubernetes:{cluster_id}",
        backend=InfrastructureBackend.KUBERNETES,
        head_resources=RayResourceRequest(cpu=2, memory_gib=4),
        worker_resources=RayResourceRequest(cpu=4, gpu=1, memory_gib=16),
        min_workers=min_workers,
        max_workers=max(1, min_workers + 1),
    )


def _kube_request(
    cluster: RayClusterSpec, *, submitted_at: float = 0.0
) -> InfrastructureAdmissionRequest:
    return InfrastructureAdmissionRequest(
        request_id=cluster.ray_cluster_id,
        backend=InfrastructureBackend.KUBERNETES,
        resource_request=cluster.maximum_resources,
        admission_domain_id="kueue-domain",
        admission_queue_id="ray",
        submitted_at=submitted_at,
    )


def _slurm_admission() -> SlurmAdmissionEngine:
    scheduler = SlurmSchedulerEngine(
        [
            SlurmNode(
                node_id="slurm-01",
                partition="gpu",
                gpus=4,
                gpu_model="h100",
                cpus=64,
                memory_mb=100_000,
            )
        ]
    )
    return SlurmAdmissionEngine(
        scheduler,
        admission_domain_id="slurm-domain",
    )


def test_kubernetes_cluster_reaches_ready_after_head_and_workers_register():
    cluster = _kube_cluster("ray-kube-1")
    admission = KubernetesAdmissionEngine(
        resource_capacity=RayResourceRequest(cpu=32, gpu=4, memory_gib=128),
        admission_domain_id="kueue-domain",
        admission_queue_id="ray",
    )
    engine = RayClusterEngine(
        kubernetes_admission=admission,
        head_startup_delay_s=1,
        worker_startup_delay_s=2,
        worker_registration_delay_s=3,
    )

    submitted = engine.submit(cluster, _kube_request(cluster))
    assert submitted.state is RayClusterLifecycleState.ADMISSION_QUEUED

    first = engine.advance(0)
    assert [event.state for event in first[:2]] == [
        RayClusterLifecycleState.ADMITTED,
        RayClusterLifecycleState.HEAD_STARTING,
    ]
    assert engine.status(cluster.ray_cluster_id).state is RayClusterLifecycleState.HEAD_STARTING

    head_ready = engine.advance(1)
    assert [event.state for event in head_ready] == [
        RayClusterLifecycleState.HEAD_READY,
        RayClusterLifecycleState.WORKERS_STARTING,
    ]
    assert engine.status(cluster.ray_cluster_id).registered_workers == 0

    worker_started = engine.advance(3)
    assert worker_started[-1].state is RayClusterLifecycleState.WORKERS_STARTING
    assert "started" in (worker_started[-1].reason or "")

    ready = engine.advance(6)
    assert ready[-1].state is RayClusterLifecycleState.READY
    status = engine.status(cluster.ray_cluster_id)
    assert status.registered_workers == 1
    assert status.ready_resources == RayResourceRequest(
        cpu=6,
        gpu=1,
        memory_gib=20,
    )
    assert status.timing.infrastructure_admission_delay == 0
    assert status.timing.cluster_startup_delay == 6
    assert status.timing.ray_workload_queue_delay is None


def test_admission_delay_and_cluster_startup_delay_are_separate():
    cluster = _kube_cluster("ray-delayed")
    admission = KubernetesAdmissionEngine(
        resource_capacity=RayResourceRequest(cpu=32, gpu=4, memory_gib=128),
        admission_domain_id="kueue-domain",
        admission_delay_s=3,
    )
    engine = RayClusterEngine(
        kubernetes_admission=admission,
        head_startup_delay_s=2,
        worker_startup_delay_s=0,
        worker_registration_delay_s=0,
    )

    engine.submit(cluster, _kube_request(cluster, submitted_at=2))
    assert engine.advance(4) == ()
    engine.advance(5)
    engine.advance(7)

    timing = engine.status(cluster.ray_cluster_id).timing
    assert timing.infrastructure_admission_delay == 3
    assert timing.cluster_startup_delay == 2


def test_zero_worker_kuberay_cluster_is_ready_when_head_is_ready():
    cluster = _kube_cluster("ray-head-only", min_workers=0)
    admission = KubernetesAdmissionEngine(
        resource_capacity=RayResourceRequest(cpu=16, gpu=2, memory_gib=64),
        admission_domain_id="kueue-domain",
        admission_queue_id="ray",
    )
    engine = RayClusterEngine(
        kubernetes_admission=admission,
        head_startup_delay_s=0,
    )

    engine.submit(cluster, _kube_request(cluster))
    events = engine.advance(0)

    assert events[-1].state is RayClusterLifecycleState.READY
    status = engine.status(cluster.ray_cluster_id)
    assert status.registered_workers == 0
    assert status.ready_resources == cluster.head_resources


def test_slurm_cluster_uses_fixed_allocation_and_reaches_ready():
    admission = _slurm_admission()
    cluster = RayClusterSpec(
        ray_cluster_id="ray-slurm-1",
        infrastructure_allocation_id="slurm:ray-slurm-1",
        backend=InfrastructureBackend.SLURM,
        head_resources=RayResourceRequest(cpu=2, memory_gib=4),
        worker_resources=RayResourceRequest(cpu=8, gpu=1, memory_gib=16),
        min_workers=0,
        max_workers=1,
    )
    request = InfrastructureAdmissionRequest(
        request_id="ray-slurm-1",
        backend=InfrastructureBackend.SLURM,
        resource_request=cluster.maximum_resources,
        admission_domain_id="slurm-domain",
        admission_queue_id="gpu",
    )
    engine = RayClusterEngine(
        slurm_admission=admission,
        head_startup_delay_s=0,
        worker_startup_delay_s=0,
        worker_registration_delay_s=0,
    )

    engine.submit(cluster, request)
    events = engine.advance(0)

    assert events[-1].state is RayClusterLifecycleState.READY
    status = engine.status(cluster.ray_cluster_id)
    assert status.allocation is not None
    assert status.allocation.backend is InfrastructureBackend.SLURM
    assert status.registered_workers == 1
    assert status.ready_resources.gpu == 1


def test_ready_cluster_drains_then_releases_infrastructure_allocation():
    cluster = _kube_cluster("ray-drain")
    admission = KubernetesAdmissionEngine(
        resource_capacity=RayResourceRequest(cpu=32, gpu=4, memory_gib=128),
        admission_domain_id="kueue-domain",
        admission_queue_id="ray",
    )
    engine = RayClusterEngine(
        kubernetes_admission=admission,
        head_startup_delay_s=0,
        worker_startup_delay_s=0,
        worker_registration_delay_s=0,
    )
    engine.submit(cluster, _kube_request(cluster))
    engine.advance(0)

    draining = engine.begin_drain(cluster.ray_cluster_id, now=1)
    terminated = engine.terminate(cluster.ray_cluster_id, now=2)

    assert draining.state is RayClusterLifecycleState.DRAINING
    assert terminated.state is RayClusterLifecycleState.TERMINATED
    assert engine.status(cluster.ray_cluster_id).state is RayClusterLifecycleState.TERMINATED
    assert admission.state(cluster.ray_cluster_id) is InfrastructureAdmissionState.RELEASED