"""Phase 8 end-to-end scenario coverage for the Ray control-plane phases."""

from __future__ import annotations

from dataclasses import dataclass

from core.infrastructure_admission import (
    InfrastructureAdmissionRequest,
    KubernetesAdmissionEngine,
    SlurmAdmissionEngine,
)
from core.ray_autoscaler import (
    RayAutoscaler,
    RayAutoscalingPolicy,
    RayAutoscalerEventState,
)
from core.ray_cluster_engine import RayClusterEngine, RayClusterLifecycleState
from core.ray_execution_scheduler import (
    RayExecutionScheduler,
    RayWorkloadState,
)
from core.ray_external_ingestion import (
    RayExternalIngestor,
    RayExternalSnapshot,
    RayExternalSource,
    RayExternalWorkloadObservation,
    RayObservedWorkloadState,
)
from core.ray_models import (
    InfrastructureBackend,
    PowerEnforcementPolicy,
    RayClusterSpec,
    RayMeasuredUsage,
    RayResourceRequest,
    RayWorkloadKind,
    RayWorkloadSpec,
)
from core.ray_observability import (
    RayIngestionFreshness,
    RayObservabilityCollector,
)
from core.ray_power_enforcement import (
    RayPowerAction,
    RayPowerEnforcementPolicySpec,
    RayPowerEnforcer,
)
from core.slurm_scheduler import SlurmNode, SlurmSchedulerEngine


@dataclass(frozen=True)
class RayScenarioCase:
    scenario_id: str
    purpose: str


SCENARIO_CASES = (
    RayScenarioCase(
        "phase8-kuberay-burst-power-and-observability",
        "A KubeRay burst scales, runs, reports measured power, and stays observable.",
    ),
    RayScenarioCase(
        "phase8-external-feed-stale",
        "A stale external feed is visible without creating a control action.",
    ),
    RayScenarioCase(
        "phase8-slurm-fixed-boundary",
        "A Slurm-backed Ray cluster remains fixed under pending demand.",
    ),
)


def _elastic_cluster(cluster_id: str) -> RayClusterSpec:
    return RayClusterSpec(
        ray_cluster_id=cluster_id,
        infrastructure_allocation_id=f"kubernetes:{cluster_id}",
        backend=InfrastructureBackend.KUBERNETES,
        head_resources=RayResourceRequest(cpu=1),
        worker_resources=RayResourceRequest(cpu=2),
        min_workers=0,
        max_workers=2,
    )


def _ready_kuberay(
    cluster: RayClusterSpec,
) -> RayClusterEngine:
    admission = KubernetesAdmissionEngine(
        resource_capacity=RayResourceRequest(cpu=5),
        admission_domain_id="phase8-domain",
        admission_queue_id="phase8-queue",
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
            admission_domain_id="phase8-domain",
            admission_queue_id="phase8-queue",
        ),
    )
    engine.advance(0)
    assert engine.status(cluster.ray_cluster_id).state is RayClusterLifecycleState.READY
    return engine


def _burst_scheduler(
    engine: RayClusterEngine,
    cluster: RayClusterSpec,
) -> RayExecutionScheduler:
    scheduler = RayExecutionScheduler(engine)
    scheduler.submit_workload(
        RayWorkloadSpec(
            workload_id="phase8-burst",
            ray_cluster_id=cluster.ray_cluster_id,
            kind=RayWorkloadKind.TRAINING,
            resource_request=RayResourceRequest(cpu=2),
            replicas=2,
            duration_s=None,
        )
    )
    return scheduler


def _external_snapshot(
    sequence: int,
    observed_at: float,
) -> RayExternalSnapshot:
    return RayExternalSnapshot(
        event_id=f"phase8-observation-{sequence}",
        source=RayExternalSource.RAY_STATE_API,
        cluster_id="phase8-kuberay",
        observed_at=observed_at,
        source_sequence=sequence,
        worker_count=2,
        workloads=(
            RayExternalWorkloadObservation(
                workload_id="phase8-burst",
                state=RayObservedWorkloadState.RUNNING,
                measured_usage=RayMeasuredUsage(gpu_power_kw=6.0),
            ),
        ),
    )


def test_scenario_kuberay_burst_power_and_observability_covers_phases_3_to_7():
    cluster = _elastic_cluster("phase8-kuberay")
    engine = _ready_kuberay(cluster)
    scheduler = _burst_scheduler(engine, cluster)
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
    autoscaler.advance(0)
    assert engine.status(cluster.ray_cluster_id).registered_workers == 2
    assert scheduler.workload_status("phase8-burst").state is RayWorkloadState.RUNNING

    power = RayPowerEnforcer(
        {
            cluster.ray_cluster_id: RayPowerEnforcementPolicySpec(
                policy=PowerEnforcementPolicy.GPU_POWER_CAP,
                gpu_power_cap_kw=100.0,
                power_budget_kw=5.0,
            )
        }
    )
    power.observe_usage(
        cluster.ray_cluster_id,
        "phase8-burst",
        RayMeasuredUsage(gpu_power_kw=6.0),
    )
    power_events = power.enforce(cluster.ray_cluster_id, now=0)
    assert power_events[0].action is RayPowerAction.BUDGET_THROTTLED

    ingestor = RayExternalIngestor()
    ingestor.ingest(_external_snapshot(1, 0.0), sim_time=0.0)
    report = RayObservabilityCollector(
        ingestor,
        cluster_engine=engine,
        autoscaler=autoscaler,
        power_enforcer=power,
        stale_after_s=10.0,
    ).collect(cluster.ray_cluster_id, now=1.0)

    assert report.ingestion_freshness is RayIngestionFreshness.FRESH
    assert report.lifecycle_state is RayClusterLifecycleState.READY
    assert report.registered_workers == 2
    assert report.running_workloads == 1
    assert report.power_over_budget is True
    assert report.effective_power_kw == 5.0
    assert report.event_counts["autoscaler_events"] >= 1
    assert report.event_counts["power_events"] == 1


def test_scenario_stale_external_feed_is_visible_without_control_mutation():
    ingestor = RayExternalIngestor()
    ingestor.ingest(_external_snapshot(1, 0.0), sim_time=0.0)
    collector = RayObservabilityCollector(ingestor, stale_after_s=2.0)

    report = collector.collect("phase8-kuberay", now=3.0)

    assert report.ingestion_freshness is RayIngestionFreshness.STALE
    assert report.ingestion_lag_s == 3.0
    assert report.autoscaling_in_flight is None
    assert report.event_counts["external_accepted"] == 1


def test_scenario_slurm_fixed_boundary_does_not_autoscale_pending_work():
    cluster = RayClusterSpec(
        ray_cluster_id="phase8-slurm",
        infrastructure_allocation_id="slurm:phase8-slurm",
        backend=InfrastructureBackend.SLURM,
        worker_resources=RayResourceRequest(cpu=2),
        min_workers=1,
        max_workers=1,
    )
    slurm_admission = SlurmAdmissionEngine(
        SlurmSchedulerEngine(
            [
                SlurmNode(
                    node_id="phase8-node",
                    partition="gpu",
                    gpus=0,
                    gpu_model=None,
                    cpus=8,
                    memory_mb=16_000,
                )
            ]
        ),
        admission_domain_id="phase8-slurm-domain",
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
            admission_domain_id="phase8-slurm-domain",
            admission_queue_id="gpu",
        ),
    )
    engine.advance(0)
    scheduler = RayExecutionScheduler(engine)
    scheduler.submit_workload(
        RayWorkloadSpec(
            workload_id="phase8-slurm-work",
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
    assert scheduler.workload_status("phase8-slurm-work").state is RayWorkloadState.QUEUED