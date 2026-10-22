"""Regression coverage for the catalogue's explicit Phase A K8S demo."""

from __future__ import annotations

import json

from api.routes.scenarios import build_seeded_store
from core.kube_scheduler import KubeSchedulerEngine
from runtime.scenario_factory import build_run_context_from_spec


SCENARIO_ID = "scenario-kubernetes-scheduler-demo"


def test_catalogue_demo_constructs_phase_a_scheduler_and_has_real_queue_wait():
    record = build_seeded_store().get(SCENARIO_ID)
    assert record is not None

    spec = json.loads(record.spec_json)
    assert spec["name"] == "Kubernetes Scheduler - Resource Queue Demo"
    assert spec["workload_events"] == []
    assert spec.get("kube_config") is None
    assert len(spec["kube_clusters"]) == 1
    assert spec["kube_clusters"][0]["scheduler_type"] == "K8S"

    context = build_run_context_from_spec("phase-a-demo-test", spec)
    assert len(context.sim_state.kube_agents) == 1
    agent = context.sim_state.kube_agents[0]
    assert isinstance(agent._kube_scheduler, KubeSchedulerEngine)
    assert agent._kube_scheduler.nodes[0].gpu_type == "h100"

    created_at: dict[str, float] = {}
    queue_waits: list[float] = []
    peak_backoff = 0
    peak_unschedulable = 0
    matching_gpu_starts = 0
    active_queue_entries = 0

    # The demo deliberately offers jobs faster than its 48-node cluster can
    # finish them, while keeping the RNG deterministic for this assertion.
    for tick_index in range(0, 241):
        _, metrics = agent.tick(float(tick_index * 5), 5.0)
        peak_backoff = max(peak_backoff, metrics.backoff_queue_depth)
        peak_unschedulable = max(
            peak_unschedulable, metrics.unschedulable_pods
        )
        for event in metrics.scheduler_events:
            if event.stage == "pod_created":
                created_at[event.pod_id] = event.timestamp
            elif event.stage == "queue_entered" and event.reason == "activeQ":
                active_queue_entries += 1
            elif event.stage == "container_started":
                if event.pod_id in created_at:
                    queue_waits.append(event.timestamp - created_at[event.pod_id])
                matching_gpu_starts += 1

    assert active_queue_entries > 0
    assert matching_gpu_starts > 0
    assert max(queue_waits) > 0.0
    assert peak_backoff > 0
    assert peak_unschedulable > 0