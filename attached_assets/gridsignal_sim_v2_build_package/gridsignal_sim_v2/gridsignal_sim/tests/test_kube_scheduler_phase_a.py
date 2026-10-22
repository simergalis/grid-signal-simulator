"""Phase A acceptance tests for the kube-scheduler-shaped Kubernetes engine."""

from __future__ import annotations

from core.kube_scheduler import KubePod, KubeSchedulerEngine


def _pod(
    pod_id: str,
    *,
    priority: int = 0,
    created_at: float = 0.0,
    duration_s: float = 100.0,
    cpu_milli: int = 4_000,
    memory_mib: int = 4_000,
    gpu_count: int = 1,
) -> KubePod:
    return KubePod(
        pod_id=pod_id,
        workload_id=pod_id.split("-")[0],
        created_at=created_at,
        enqueue_time=created_at,
        priority=priority,
        cpu_milli=cpu_milli,
        memory_mib=memory_mib,
        gpu_count=gpu_count,
        duration_s=duration_s,
        hardware_profile_id="enterprise_8gpu_air",
    )


def test_active_queue_orders_by_priority_then_enqueue_time():
    engine = KubeSchedulerEngine(
        max_nodes=3,
        node_cpu_milli=8_000,
        node_memory_mib=8_000,
        node_gpu_count=1,
    )
    engine.submit(_pod("low-1", priority=10, created_at=0.0))
    engine.submit(_pod("high-1", priority=100, created_at=1.0))
    engine.submit(_pod("high-2", priority=100, created_at=2.0))

    tick = engine.tick(2.0)

    assert [pod.pod_id for pod in tick.started_pods] == [
        "high-1",
        "high-2",
        "low-1",
    ]
    attempts = [
        event.pod_id
        for event in tick.events
        if event.stage == "scheduling_attempt"
    ]
    assert attempts == ["high-1", "high-2", "low-1"]


def test_failed_pod_moves_backoff_then_unschedulable_and_reactivates_on_cluster_event():
    engine = KubeSchedulerEngine(
        max_nodes=1,
        node_cpu_milli=8_000,
        node_memory_mib=8_000,
        node_gpu_count=1,
        backoff_duration_s=10.0,
        max_backoff_retries=1,
    )
    engine.submit(_pod("owner", duration_s=100.0))
    engine.submit(_pod("waiting", created_at=0.0))

    first = engine.tick(0.0)
    assert [pod.pod_id for pod in first.started_pods] == ["owner"]
    assert len(engine.backoff_queue) == 1
    assert any(event.stage == "backoff_entered" for event in first.events)

    second = engine.tick(10.0)
    assert not second.started_pods
    assert len(engine.unschedulable_pods) == 1
    assert any(event.stage == "unschedulable_entered" for event in second.events)

    third = engine.tick(100.0)
    assert [pod.pod_id for pod in third.started_pods] == ["waiting"]
    assert any(event.stage == "cluster_event_requeue" for event in third.events)
    assert not engine.unschedulable_pods


def test_placement_checks_cpu_memory_and_gpu_capacity():
    engine = KubeSchedulerEngine(
        max_nodes=1,
        node_cpu_milli=8_000,
        node_memory_mib=8_000,
        node_gpu_count=1,
        backoff_duration_s=5.0,
        max_backoff_retries=0,
    )
    engine.submit(_pod("too-large-cpu", cpu_milli=8_001))
    tick = engine.tick(0.0)

    assert not tick.started_pods
    assert len(engine.unschedulable_pods) == 1
    assert engine.nodes[0].cpu_allocated_milli == 0
    assert engine.nodes[0].memory_allocated_mib == 0
    assert engine.nodes[0].gpu_allocated == 0


def test_lifecycle_events_have_stage_timestamps_and_node_identity():
    engine = KubeSchedulerEngine(
        max_nodes=1,
        node_cpu_milli=8_000,
        node_memory_mib=8_000,
        node_gpu_count=1,
    )
    submit_events = engine.submit(_pod("train-1", created_at=3.0))
    tick = engine.tick(5.0)

    all_events = (*submit_events, *tick.events)
    stages = [event.stage for event in all_events]
    assert stages[:2] == ["pod_created", "queue_entered"]
    assert stages[-4:] == [
        "scheduling_attempt",
        "node_selected",
        "bound",
        "container_started",
    ]
    lifecycle = all_events[-3:]
    assert all(event.node_id == "k8s-node-00000" for event in lifecycle)
    assert all(event.timestamp >= 5.0 for event in all_events[2:])
    assert all_events[-1].timestamp == 5.0