"""Phase 5 KubeRay autoscaling feedback-loop tests."""

from __future__ import annotations

from core.infrastructure_admission import (
    InfrastructureAdmissionRequest,
    KubernetesAdmissionEngine,
)
from core.ray_autoscaler import (
    RayAutoscaler,
    RayAutoscalerEventState,
    RayAutoscalingError,
    RayAutoscalingPolicy,
)
from core.ray_cluster_engine import (
    RayClusterEngine,
    RayClusterLifecycleState,
    RayWorkerScalingState,
)
from core.ray_execution_scheduler import RayExecutionScheduler, RayWorkloadState
from core.ray_models import (
    InfrastructureBackend,
    RayClusterSpec,
    RayResourceRequest,
    RayWorkloadKind,
    RayWorkloadSpec,
)
from core.slurm_scheduler import SlurmNode, SlurmSchedulerEngine
from core.infrastructure_admission import SlurmAdmissionEngine


def _elastic_cluster(cluster_id: str = "kuberay") -> RayClusterSpec:
    return RayClusterSpec(
        ray_cluster_id=cluster_id,
        infrastructure_allocation_id=f"kubernetes:{cluster_id}",
        backend=InfrastructureBackend.KUBERNETES,
        head_resources=RayResourceRequest(cpu=1),
        worker_resources=RayResourceRequest(cpu=2),
        min_workers=0,
        max_workers=2,
    )


def _ready_cluster(
    cluster: RayClusterSpec, *, capacity_cpu: float = 5
) -> RayClusterEngine:
    admission = KubernetesAdmissionEngine(
        resource_capacity=RayResourceRequest(cpu=capacity_cpu),
        admission_domain_id="domain",
        admission_queue_id="ray",
    )
    engine = RayClusterEngine(
        kubernetes_admission=admission,
        head_startup_delay_s=0,
        worker_startup_delay_s=0,
        worker_registration_delay_s=0,
    )
    engine.submit(
        cluster,
        InfrastructureAdmissionRequest(
            request_id=cluster.ray_cluster_id,
            backend=InfrastructureBackend.KUBERNETES,
            resource_request=cluster.minimum_resources,
            admission_domain_id="domain",
            admission_queue_id="ray",
        ),
    )
    engine.advance(0)
    assert engine.status(cluster.ray_cluster_id).state is RayClusterLifecycleState.READY
    return engine


def _scheduler_with_pending_work(
    engine: RayClusterEngine, cluster: RayClusterSpec
) -> RayExecutionScheduler:
    scheduler = RayExecutionScheduler(engine)
    scheduler.submit_workload(
        RayWorkloadSpec(
            workload_id="distributed",
            ray_cluster_id=cluster.ray_cluster_id,
            kind=RayWorkloadKind.TRAINING,
            resource_request=RayResourceRequest(cpu=2),
            replicas=2,
            duration_s=None,
        )
    )
    return scheduler


def test_pending_ray_work_scales_kuberay_through_admission_then_registers():
    cluster = _elastic_cluster()
    engine = _ready_cluster(cluster)
    scheduler = _scheduler_with_pending_work(engine, cluster)
    autoscaler = RayAutoscaler(
        engine,
        scheduler,
        {
            cluster.ray_cluster_id: RayAutoscalingPolicy(
                scale_down_idle_delay_s=100
            )
        },
    )

    requested = autoscaler.advance(0)
    assert requested[0].state is RayAutoscalerEventState.SCALE_REQUESTED
    assert requested[0].target_workers == 2
    assert engine.status(cluster.ray_cluster_id).registered_workers == 0

    autoscaler.advance(0)
    assert engine.status(cluster.ray_cluster_id).registered_workers == 2
    assert scheduler.workload_status("distributed").state is RayWorkloadState.RUNNING
    assert engine.scaling_events[-1].state is RayWorkerScalingState.READY


def test_scale_up_delay_and_idle_delay_are_respected():
    cluster = _elastic_cluster()
    engine = _ready_cluster(cluster)
    scheduler = _scheduler_with_pending_work(engine, cluster)
    autoscaler = RayAutoscaler(
        engine,
        scheduler,
        {
            cluster.ray_cluster_id: RayAutoscalingPolicy(
                scale_up_delay_s=2,
                scale_down_idle_delay_s=2,
            )
        },
    )

    assert autoscaler.advance(0) == ()
    assert autoscaler.advance(1) == ()
    assert autoscaler.advance(2)[0].state is RayAutoscalerEventState.SCALE_REQUESTED
    autoscaler.advance(2)
    assert engine.status(cluster.ray_cluster_id).registered_workers == 2

    scheduler.cancel_workload("distributed", now=3)
    autoscaler.advance(3)
    assert autoscaler.advance(4) == ()
    down = autoscaler.advance(5)
    assert down[0].state is RayAutoscalerEventState.SCALE_DOWN
    assert down[0].target_workers == 0
    autoscaler.advance(5)
    assert engine.status(cluster.ray_cluster_id).registered_workers == 0


def test_admission_quota_and_power_budget_can_reject_scale_up():
    cluster = _elastic_cluster("limited")
    engine = _ready_cluster(cluster, capacity_cpu=1)
    scheduler = _scheduler_with_pending_work(engine, cluster)
    autoscaler = RayAutoscaler(
        engine,
        scheduler,
        {
            cluster.ray_cluster_id: RayAutoscalingPolicy(
                scale_down_idle_delay_s=100
            )
        },
    )
    rejected = autoscaler.advance(0)
    assert rejected[0].state is RayAutoscalerEventState.ADMISSION_REJECTED

    power_cluster = _elastic_cluster("power")
    power_engine = _ready_cluster(power_cluster)
    power_scheduler = _scheduler_with_pending_work(power_engine, power_cluster)
    power_autoscaler = RayAutoscaler(
        power_engine,
        power_scheduler,
        {
            power_cluster.ray_cluster_id: RayAutoscalingPolicy(
                power_budget_kw=0.5,
                worker_power_kw=1.0,
            )
        },
    )
    power_rejected = power_autoscaler.advance(0)
    assert power_rejected[0].state is RayAutoscalerEventState.POWER_REJECTED


def test_failed_worker_is_replaced_via_a_new_admission_request():
    cluster = _elastic_cluster("replacement")
    engine = _ready_cluster(cluster)
    scheduler = _scheduler_with_pending_work(engine, cluster)
    autoscaler = RayAutoscaler(
        engine,
        scheduler,
        {
            cluster.ray_cluster_id: RayAutoscalingPolicy(
                scale_down_idle_delay_s=100
            )
        },
    )
    autoscaler.advance(0)
    autoscaler.advance(0)
    scheduler.cancel_workload("distributed", now=1)
    autoscaler.advance(1)

    replacement = autoscaler.report_worker_failure(cluster.ray_cluster_id, now=2)
    assert replacement[0].state is RayAutoscalerEventState.SCALE_REQUESTED
    assert engine.status(cluster.ray_cluster_id).registered_workers == 1
    autoscaler.advance(2)
    assert engine.status(cluster.ray_cluster_id).registered_workers == 2


def test_slurm_clusters_are_not_entered_into_kuberay_autoscaling():
    cluster = RayClusterSpec(
        ray_cluster_id="slurm-ray",
        infrastructure_allocation_id="slurm:slurm-ray",
        backend=InfrastructureBackend.SLURM,
        worker_resources=RayResourceRequest(cpu=2),
        min_workers=1,
        max_workers=1,
    )
    slurm_admission = SlurmAdmissionEngine(
        SlurmSchedulerEngine(
            [
                SlurmNode(
                    node_id="slurm-01",
                    partition="gpu",
                    gpus=0,
                    gpu_model=None,
                    cpus=8,
                    memory_mb=16_000,
                )
            ]
        ),
        admission_domain_id="slurm-domain",
    )
    engine = RayClusterEngine(
        slurm_admission=slurm_admission,
        head_startup_delay_s=0,
        worker_startup_delay_s=0,
        worker_registration_delay_s=0,
    )
    engine.submit(
        cluster,
        InfrastructureAdmissionRequest(
            request_id=cluster.ray_cluster_id,
            backend=InfrastructureBackend.SLURM,
            resource_request=cluster.minimum_resources,
            admission_domain_id="slurm-domain",
            admission_queue_id="gpu",
        ),
    )
    engine.advance(0)
    scheduler = RayExecutionScheduler(engine)
    scheduler.submit_workload(
        RayWorkloadSpec(
            workload_id="slurm-pending",
            ray_cluster_id=cluster.ray_cluster_id,
            kind=RayWorkloadKind.TASK,
            resource_request=RayResourceRequest(cpu=3),
            duration_s=None,
        )
    )
    autoscaler = RayAutoscaler(
        engine,
        scheduler,
        {cluster.ray_cluster_id: RayAutoscalingPolicy()},
    )
    assert autoscaler.advance(0) == ()
    assert cluster.fixed_allocation is True