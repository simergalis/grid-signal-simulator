"""Phase 2 infrastructure admission tests."""

from __future__ import annotations

from core.infrastructure_admission import (
    InfrastructureAdmissionRequest,
    InfrastructureAdmissionState,
    KubernetesAdmissionEngine,
    SlurmAdmissionEngine,
)
from core.ray_models import (
    InfrastructureBackend,
    KubernetesAdmissionProvider,
    RayResourceRequest,
)
from core.slurm_scheduler import SlurmJobSpec, SlurmNode, SlurmSchedulerEngine


def _kube_request(
    request_id: str,
    *,
    gpu: float = 1,
    priority: int = 0,
    submitted_at: float = 0.0,
    queue: str = "ray",
    budget: str | None = None,
    gang_id: str | None = None,
    gang_size: int = 1,
    preemptible: bool = True,
) -> InfrastructureAdmissionRequest:
    return InfrastructureAdmissionRequest(
        request_id=request_id,
        backend=InfrastructureBackend.KUBERNETES,
        resource_request=RayResourceRequest(gpu=gpu),
        admission_domain_id="kueue-domain",
        admission_queue_id=queue,
        capacity_budget_id=budget,
        priority=priority,
        submitted_at=submitted_at,
        gang_id=gang_id,
        gang_size=gang_size,
        preemptible=preemptible,
    )


def _slurm_engine() -> SlurmSchedulerEngine:
    return SlurmSchedulerEngine(
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


def test_kubernetes_admission_waits_for_delay_and_preserves_priority():
    engine = KubernetesAdmissionEngine(
        provider=KubernetesAdmissionProvider.KUEUE,
        resource_capacity=RayResourceRequest(gpu=2),
        admission_domain_id="kueue-domain",
        admission_delay_s=5,
    )
    engine.submit(_kube_request("low", priority=1))
    engine.submit(_kube_request("high", priority=10))

    assert engine.advance(4) == ()
    events = engine.advance(5)

    assert [event.request_id for event in events] == ["high", "low"]
    assert all(
        event.state is InfrastructureAdmissionState.ADMITTED for event in events
    )
    assert events[0].allocation is not None
    assert events[0].allocation.admission_queue_id == "ray"


def test_kubernetes_admission_enforces_queue_quota_and_capacity_budget():
    engine = KubernetesAdmissionEngine(
        provider=KubernetesAdmissionProvider.VOLCANO,
        resource_capacity=RayResourceRequest(gpu=4),
        admission_domain_id="kueue-domain",
        queue_quotas={"ray": RayResourceRequest(gpu=3)},
        capacity_budgets={"tenant-budget": RayResourceRequest(gpu=2)},
    )
    engine.submit(_kube_request("first", gpu=2, budget="tenant-budget"))
    oversized_queue = engine.submit(
        _kube_request("queue-too-large", gpu=4, queue="ray")
    )
    unknown_budget = engine.submit(
        _kube_request("unknown-budget", gpu=1, budget="missing")
    )

    assert engine.advance(0)[0].state is InfrastructureAdmissionState.ADMITTED
    assert oversized_queue.state is InfrastructureAdmissionState.REJECTED
    assert "queue quota" in (oversized_queue.reason or "")
    assert unknown_budget.state is InfrastructureAdmissionState.REJECTED
    assert engine.state("unknown-budget") is InfrastructureAdmissionState.REJECTED


def test_kubernetes_gang_request_is_admitted_as_one_allocation():
    engine = KubernetesAdmissionEngine(
        resource_capacity=RayResourceRequest(gpu=2),
        admission_domain_id="kueue-domain",
    )
    queued = engine.submit(
        _kube_request("gang", gpu=2, gang_id="training-gang", gang_size=4)
    )

    assert queued.state is InfrastructureAdmissionState.QUEUED
    admitted = engine.advance(0)
    assert len(admitted) == 1
    assert admitted[0].reason == "gang admitted atomically"
    assert admitted[0].allocation is not None
    assert admitted[0].allocation.resource_capacity.gpu == 2


def test_kubernetes_admission_can_preempt_lower_priority_allocation():
    engine = KubernetesAdmissionEngine(
        resource_capacity=RayResourceRequest(gpu=2),
        admission_domain_id="kueue-domain",
        preemption_enabled=True,
    )
    engine.submit(_kube_request("low", priority=1))
    engine.advance(0)
    engine.submit(_kube_request("high", gpu=2, priority=10))

    events = engine.advance(1)

    assert [event.state for event in events] == [
        InfrastructureAdmissionState.PREEMPTED,
        InfrastructureAdmissionState.ADMITTED,
    ]
    assert events[1].preempted_request_ids == ("low",)
    assert engine.state("low") is InfrastructureAdmissionState.PREEMPTED


def test_kubernetes_release_frees_capacity_for_pending_request():
    engine = KubernetesAdmissionEngine(
        resource_capacity=RayResourceRequest(gpu=1),
        admission_domain_id="kueue-domain",
    )
    engine.submit(_kube_request("running"))
    engine.submit(_kube_request("waiting"))
    engine.advance(0)
    assert engine.state("waiting") is InfrastructureAdmissionState.QUEUED

    engine.release("running", now=1)
    events = engine.advance(1)

    assert events[0].request_id == "waiting"
    assert events[0].state is InfrastructureAdmissionState.ADMITTED


def test_slurm_adapter_exposes_queue_allocation_and_release_contract():
    adapter = SlurmAdmissionEngine(_slurm_engine())
    queued = adapter.submit(
        SlurmJobSpec(
            job_id="slurm-ray-1",
            duration=2,
            gpus_per_node=2,
            cpus_per_node=16,
            memory_mb_per_node=20_480,
            partition="gpu",
        )
    )
    assert queued.state is InfrastructureAdmissionState.QUEUED

    admitted = adapter.advance(0)
    assert len(admitted) == 1
    assert admitted[0].state is InfrastructureAdmissionState.ADMITTED
    assert admitted[0].allocation is not None
    assert admitted[0].allocation.backend is InfrastructureBackend.SLURM
    assert admitted[0].allocation.admission_queue_id == "gpu"
    assert admitted[0].allocation.resource_capacity.memory_gib == 20.0

    released = adapter.advance(2)
    assert released[0].state is InfrastructureAdmissionState.RELEASED
    assert adapter.state("slurm-ray-1") is InfrastructureAdmissionState.RELEASED


def test_slurm_adapter_preserves_existing_policy_rejection():
    scheduler = _slurm_engine()
    adapter = SlurmAdmissionEngine(scheduler)
    rejected = adapter.submit(
        SlurmJobSpec(
            job_id="bad-partition",
            partition="offline",
            gpus_per_node=1,
        )
    )

    assert rejected.state is InfrastructureAdmissionState.REJECTED
    assert adapter.state("bad-partition") is InfrastructureAdmissionState.REJECTED