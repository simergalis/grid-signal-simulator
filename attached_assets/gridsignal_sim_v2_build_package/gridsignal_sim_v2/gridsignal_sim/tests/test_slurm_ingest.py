"""Slurm ingestion adapter and live physics tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import create_app
from api.routes.ingest import hardware_profile_from_tres
from core.models import WorkloadEventType
from runtime.run_manager import RunManager, WebSocketHub
from runtime.scenario_factory import build_run_context_from_spec


_JOB = {
    "job_id": 481516,
    "name": "distributed-training",
    "user_name": "customer-user",
    "job_state": ["RUNNING"],
    "partition": "gpu",
    "nodes": "gpu-node[014-029]",
    "node_count": 16,
    "cpus": 1536,
    "tres_req_str": "cpu=1536,mem=184320G,gres/gpu=128,gres/gpu:h100=128",
    "tres_alloc_str": "cpu=1536,mem=184320G,gres/gpu=128,gres/gpu:h100=128",
    "account": "customer-a",
}
_PENDING_JOB = {
    **_JOB,
    "job_id": 481519,
    "job_state": ["PENDING"],
    "node_count": 0,
    "tres_alloc_str": None,
}
_INGEST_HEADERS = {"X-Admin-Key": "test-ingest-key"}


def _enable_ingest_key(monkeypatch) -> None:
    """Use the existing server-to-server admin-key gate in endpoint tests."""
    import api.routes.admin_routes as admin_routes

    monkeypatch.setattr(admin_routes, "_ADMIN_SECRET", _INGEST_HEADERS["X-Admin-Key"])


def _spec() -> dict:
    return {
        "name": "slurm-ingest-test",
        "hardware_profile_id": "enterprise_8gpu_air",
        "dt_lead_seconds": 30.0,
        "bess_units": [],
        "turbine_units": [],
        "solar_rated_mw": 0.0,
        "irradiance_steps": [],
        "island_mode": False,
        "pue_base": 1.03,
        "run_duration_s": 300.0,
        "workload_events": [],
        "frequency_nominal_hz": 60.0,
        "power_factor": 0.85,
    }


def test_h100_tres_maps_to_canonical_profile() -> None:
    assert hardware_profile_from_tres(_JOB["tres_alloc_str"]) == (
        "h100-sxm5-8way-nvl4"
    )


def test_running_ingest_changes_compute_load_on_next_tick() -> None:
    ctx = build_run_context_from_spec("run-slurm-physics", _spec())
    manager = RunManager(WebSocketHub())
    manager._contexts[ctx.run_id] = ctx

    from core.models import WorkloadClass, WorkloadSignal

    signal = WorkloadSignal(
        event_id="slurm-481516-running",
        job_id="slurm-481516",
        event_type=WorkloadEventType.RUNNING,
        timestamp=ctx.sim_time,
        hardware_profile_id="h100-sxm5-8way-nvl4",
        node_count=16,
        workload_class=WorkloadClass.TRAINING,
        site_id=ctx.sim_state.site.site_id,
    )
    assert manager.ingest_workload_signal(ctx.run_id, signal)[0] == "accepted"
    tick = ctx.step()
    assert tick.p_compute_demand_mw > 0.0
    assert ctx.sim_state.gpu_modules[0]._node_counts["slurm-481516"] == 16


def test_terminal_slurm_fallback_removes_running_job_on_next_tick() -> None:
    ctx = build_run_context_from_spec("run-slurm-terminal", _spec())
    manager = RunManager(WebSocketHub())
    manager._contexts[ctx.run_id] = ctx

    from runtime.slurm_ingest import translate_slurm_job

    running = translate_slurm_job(
        job_id=481521,
        job_state=["RUNNING"],
        node_count=16,
        tres_req_str=_JOB["tres_req_str"],
        tres_alloc_str=_JOB["tres_alloc_str"],
        site_id=ctx.sim_state.site.site_id,
        timestamp=ctx.sim_time,
    )
    assert manager.ingest_workload_signal(ctx.run_id, running)[0] == "accepted"
    ctx.step()
    assert "slurm-481521" in ctx.sim_state.gpu_modules[0]._node_counts

    terminal = translate_slurm_job(
        job_id=481521,
        job_state=["COMPLETING"],
        node_count=0,
        tres_req_str=_JOB["tres_req_str"],
        tres_alloc_str="cpu=0,mem=0,node=0",
        site_id=ctx.sim_state.site.site_id,
        timestamp=ctx.sim_time,
    )
    assert terminal.event_type == WorkloadEventType.JOB_END
    assert manager.ingest_workload_signal(ctx.run_id, terminal)[0] == "accepted"
    ctx.step()
    assert "slurm-481521" not in ctx.sim_state.gpu_modules[0]._node_counts


def test_slurm_endpoint_returns_translated_event_and_dedupes_poll_retry(monkeypatch) -> None:
    _enable_ingest_key(monkeypatch)
    with TestClient(create_app()) as client:
        run = client.post(
            "/runs",
            json={
                "job_id": "existing-job",
                "node_count": 1,
                "end_sim_time": 1e15,
                "playback_speed": 0.0,
            },
        )
        assert run.status_code == 201
        run_id = run.json()["run_id"]

        first = client.post(
            f"/api/ingest/slurm?run_id={run_id}",
            json=_JOB,
            headers=_INGEST_HEADERS,
        )
        retry = client.post(
            f"/api/ingest/slurm?run_id={run_id}",
            json=_JOB,
            headers=_INGEST_HEADERS,
        )

    assert first.status_code == 200
    event = first.json()
    assert event["job_id"] == "slurm-481516"
    assert event["event_type"] == "running"
    assert event["hardware_profile_id"] == "h100-sxm5-8way-nvl4"
    assert event["site_id"].startswith("site-for-")
    assert event["scheduler_type"] == "slurm"
    assert event["gpus_per_unit"] == 8
    assert retry.status_code == 200
    assert retry.json()["event_id"] == event["event_id"]


def test_slurm_endpoint_maps_required_states(monkeypatch) -> None:
    _enable_ingest_key(monkeypatch)
    with TestClient(create_app()) as client:
        run = client.post(
            "/runs",
            json={
                "job_id": "state-test-job",
                "node_count": 1,
                "end_sim_time": 1e15,
                "playback_speed": 0.0,
            },
        )
        run_id = run.json()["run_id"]
        responses = [
            client.post(
                f"/api/ingest/slurm?run_id={run_id}",
                json=payload,
                headers=_INGEST_HEADERS,
            )
            for payload in (
                _PENDING_JOB,
                _JOB,
                {**_JOB, "job_state": ["COMPLETING"]},
            )
        ]

    assert [response.status_code for response in responses] == [200, 200, 200], [
        response.json() for response in responses
    ]
    assert [response.json()["event_type"] for response in responses] == [
        "queued",
        "running",
        "job_end",
    ]
    assert responses[0].json()["node_count"] == 16


def test_slurm_endpoint_requires_server_to_server_authentication(monkeypatch) -> None:
    _enable_ingest_key(monkeypatch)
    with TestClient(create_app()) as client:
        run = client.post(
            "/runs",
            json={
                "job_id": "auth-test-job",
                "node_count": 1,
                "end_sim_time": 1e15,
                "playback_speed": 0.0,
            },
        )
        response = client.post(
            f"/api/ingest/slurm?run_id={run.json()['run_id']}",
            json=_JOB,
        )

    assert response.status_code == 403


def test_slurm_endpoint_reports_unmapped_state_hardware_and_topology(monkeypatch) -> None:
    _enable_ingest_key(monkeypatch)
    with TestClient(create_app()) as client:
        run = client.post(
            "/runs",
            json={
                "job_id": "invalid-test-job",
                "node_count": 1,
                "end_sim_time": 1e15,
                "playback_speed": 0.0,
            },
        )
        run_id = run.json()["run_id"]
        bad_state = client.post(
            f"/api/ingest/slurm?run_id={run_id}",
            json={**_JOB, "job_state": ["UNKNOWN"]},
            headers=_INGEST_HEADERS,
        )
        bad_hardware = client.post(
            f"/api/ingest/slurm?run_id={run_id}",
            json={
                **_JOB,
                "job_id": 481517,
                "tres_alloc_str": "gres/gpu:a100=8",
            },
            headers=_INGEST_HEADERS,
        )
        incompatible_allocation = client.post(
            f"/api/ingest/slurm?run_id={run_id}",
            json={
                **_JOB,
                "job_id": 481518,
                "node_count": 1,
                "tres_alloc_str": "gres/gpu:h100=4",
            },
            headers=_INGEST_HEADERS,
        )
        missing_pending_tres = client.post(
            f"/api/ingest/slurm?run_id={run_id}",
            json={
                **_PENDING_JOB,
                "job_id": 481520,
                "tres_req_str": None,
            },
            headers=_INGEST_HEADERS,
        )

    assert bad_state.status_code == 422
    assert bad_state.json()["detail"]["code"] == "unmapped_job_state"
    assert bad_hardware.status_code == 422
    assert bad_hardware.json()["detail"]["code"] == "unmapped_hardware"
    assert incompatible_allocation.status_code == 422
    assert incompatible_allocation.json()["detail"]["code"] == "incompatible_allocation"
    assert missing_pending_tres.status_code == 422
    assert missing_pending_tres.json()["detail"]["code"] == "missing_resource_request"


def test_slurm_endpoint_refuses_delayed_running_after_job_end(monkeypatch) -> None:
    _enable_ingest_key(monkeypatch)
    with TestClient(create_app()) as client:
        run = client.post(
            "/runs",
            json={
                "job_id": "ordering-test-job",
                "node_count": 1,
                "end_sim_time": 1e15,
                "playback_speed": 0.0,
            },
        )
        run_id = run.json()["run_id"]
        ended = client.post(
            f"/api/ingest/slurm?run_id={run_id}",
            json={**_JOB, "job_state": ["COMPLETING"]},
            headers=_INGEST_HEADERS,
        )
        delayed_running = client.post(
            f"/api/ingest/slurm?run_id={run_id}",
            json=_JOB,
            headers=_INGEST_HEADERS,
        )

    assert ended.status_code == 200
    assert delayed_running.status_code == 409
    assert delayed_running.json()["detail"]["code"] == "stale_event"