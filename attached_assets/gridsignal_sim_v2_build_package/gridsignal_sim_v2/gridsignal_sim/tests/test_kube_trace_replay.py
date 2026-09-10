"""Offline Alibaba-style Kubernetes trace replay tests."""

from __future__ import annotations

import json

from runtime.kube_trace_replay import load_kube_trace, replay_kube_trace


NODE_HEADER = "node_id,cpu_milli,memory_mib,gpu_count,model\n"
POD_HEADER = (
    "pod_id,workload_id,cpu_milli,memory_mib,num_gpu,gpu_milli,gpu_spec,"
    "qos,creation_time,scheduled_time,deletion_time,node_id\n"
)


def _write_trace(tmp_path, nodes: str, pods: str):
    node_path = tmp_path / "nodes.csv"
    pod_path = tmp_path / "pods.csv"
    node_path.write_text(NODE_HEADER + nodes, encoding="utf-8")
    pod_path.write_text(POD_HEADER + pods, encoding="utf-8")
    return node_path, pod_path


def test_loader_quarantines_bad_rows_without_discarding_valid_rows(tmp_path):
    node_path, pod_path = _write_trace(
        tmp_path,
        "n1,8000,16000,1,V100M32\n"
        "n1,8000,16000,1,V100M32\n"
        "n2,not-a-number,16000,1,V100M16\n",
        "p1,w1,4000,4000,1,1000,V100M32,Guaranteed,"
        "2026-01-01T00:00:00Z,,2026-01-01T00:00:10Z,n1\n"
        "p2,w2,4000,4000,1,1000,V100M32,Guaranteed,"
        "not-a-time,,2026-01-01T00:00:10Z,n1\n",
    )

    dataset = load_kube_trace(node_path, pod_path)

    assert [node.node_id for node in dataset.nodes] == ["n1"]
    assert [pod.pod_id for pod in dataset.pods] == ["p1"]
    assert len(dataset.quarantined) == 3
    assert dataset.parser_report()["quarantined_rows"] == 3


def test_loader_accepts_alibaba_node_ids_and_explicit_relative_millisecond_timestamps(tmp_path):
    node_path = tmp_path / "nodes.csv"
    pod_path = tmp_path / "pods.csv"
    node_path.write_text(
        "sn,cpu_milli,memory_mib,gpu,model\n"
        "node-a,8000,16000,1,V100M32\n",
        encoding="utf-8",
    )
    pod_path.write_text(
        "name,cpu_milli,memory_mib,num_gpu,gpu_milli,gpu_spec,qos,"
        "pod_phase,creation_time,deletion_time,scheduled_time\n"
        "pod-a,4000,4000,1,1000,,BE,Running,1000,5000,2000\n",
        encoding="utf-8",
    )

    dataset = load_kube_trace(node_path, pod_path, timestamp_unit="milliseconds")

    assert dataset.nodes[0].node_id == "node-a"
    assert dataset.pods[0].qos == "BE"
    assert dataset.pods[0].priority == 100
    assert dataset.pods[0].scheduled_time is not None
    assert (
        dataset.pods[0].scheduled_time - dataset.pods[0].creation_time
    ).total_seconds() == 1.0


def test_loader_defaults_relative_alibaba_numeric_timestamps_to_seconds(tmp_path):
    node_path = tmp_path / "nodes.csv"
    pod_path = tmp_path / "pods.csv"
    node_path.write_text(
        "node_id,cpu_milli,memory_mib,gpu_count,model\n"
        "node-a,8000,16000,1,V100M32\n",
        encoding="utf-8",
    )
    pod_path.write_text(
        "pod_id,cpu_milli,memory_mib,num_gpu,gpu_milli,gpu_spec,qos,"
        "creation_time,scheduled_time,deletion_time\n"
        "pod-a,4000,4000,1,1000,V100M32,Guaranteed,1000,2000,5000\n",
        encoding="utf-8",
    )

    dataset = load_kube_trace(node_path, pod_path)

    assert (
        dataset.pods[0].scheduled_time - dataset.pods[0].creation_time
    ).total_seconds() == 1000.0


def test_gpu_spec_selects_compatible_heterogeneous_node(tmp_path):
    node_path, pod_path = _write_trace(
        tmp_path,
        "n16,8000,16000,1,V100M16\n"
        "n32,8000,16000,1,V100M32\n",
        "p16,w16,4000,4000,1,1000,V100M16,Guaranteed,"
        "2026-01-01T00:00:00Z,2026-01-01T00:00:00Z,2026-01-01T00:00:10Z,\n"
        "p32,w32,4000,4000,1,1000,V100M32,Burstable,"
        "2026-01-01T00:00:00Z,2026-01-01T00:00:00Z,2026-01-01T00:00:10Z,\n",
    )

    report = replay_kube_trace(load_kube_trace(node_path, pod_path))
    placements = {row["pod_id"]: row["simulated_node_id"] for row in report["pods"]}

    assert placements == {"p16": "n16", "p32": "n32"}
    assert report["placement"]["simulated_scheduled"] == 2


def test_deletion_time_releases_node_and_requeues_waiting_pod(tmp_path):
    node_path, pod_path = _write_trace(
        tmp_path,
        "n1,8000,16000,1,V100M32\n",
        "p1,w1,4000,4000,1,1000,V100M32,Guaranteed,"
        "2026-01-01T00:00:00Z,2026-01-01T00:00:00Z,2026-01-01T00:00:05Z,\n"
        "p2,w2,4000,4000,1,1000,V100M32,Burstable,"
        "2026-01-01T00:00:01Z,2026-01-01T00:00:05Z,2026-01-01T00:00:10Z,\n",
    )

    report = replay_kube_trace(
        load_kube_trace(node_path, pod_path),
        max_backoff_retries=0,
    )
    rows = {row["pod_id"]: row for row in report["pods"]}

    assert rows["p2"]["simulated_scheduled"] is True
    assert rows["p2"]["simulated_wait_s"] == 4.0
    assert any(
        event["stage"] == "container_completed"
        for event in rows["p1"]["events"]
    )
    assert any(
        event["stage"] == "cluster_event_requeue"
        for event in rows["p2"]["events"]
    )


def test_fractional_gpu_requests_are_reported_and_rounded_conservatively(tmp_path):
    node_path, pod_path = _write_trace(
        tmp_path,
        "n1,8000,16000,1,V100M32\n",
        "p1,w1,4000,4000,0,500,V100M32,Guaranteed,"
        "2026-01-01T00:00:00Z,,2026-01-01T00:00:10Z,\n",
    )

    report = replay_kube_trace(load_kube_trace(node_path, pod_path))

    assert report["limitations"]["integer_gpu_counts"]["affected_pods"] == 1
    assert report["pods"][0]["fractional_gpu_request"] is True
    assert report["pods"][0]["simulated_scheduled"] is True


def test_report_contains_wait_breakdowns_and_json_is_serializable(tmp_path):
    node_path, pod_path = _write_trace(
        tmp_path,
        "n1,8000,16000,1,V100M32\n",
        "p1,w1,4000,4000,1,1000,V100M32,Guaranteed,"
        "2026-01-01T00:00:00Z,2026-01-01T00:00:00Z,2026-01-01T00:00:10Z,\n"
        "p2,w2,4000,4000,1,1000,V100M32,Burstable,"
        "2026-01-01T00:00:01Z,,2026-01-01T00:00:10Z,\n",
    )

    report = replay_kube_trace(load_kube_trace(node_path, pod_path))
    encoded = json.dumps(report)

    assert encoded
    assert set(report["queue_wait"]["actual"]["p50_s"] for _ in [0]) == {0.0}
    assert "Guaranteed" in report["queue_wait"]["by_qos"]["actual"]
    assert "V100M32" in report["queue_wait"]["by_gpu_shape"]["simulated"]