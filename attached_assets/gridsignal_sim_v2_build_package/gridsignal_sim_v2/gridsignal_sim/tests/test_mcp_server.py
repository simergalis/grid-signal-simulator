from __future__ import annotations

import copy
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import mcp_server.server as server_module
from mcp_server.server import (
    RateLimiter,
    RunState,
    StudyService,
    app,
    service,
)


READ_TOKEN = "test-read-principal"
RUN_TOKEN = "test-run-principal"


def _call(client: TestClient, name: str, arguments: dict, token: str) -> dict:
    response = client.post(
        "/",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "jsonrpc": "2.0",
            "id": name,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )
    assert response.status_code == 200
    envelope = response.json()["result"]["structuredContent"]
    return envelope


def test_mcp_tools_are_reachable_over_streamable_http(
    monkeypatch,
) -> None:
    monkeypatch.setenv("GRIDSIGNAL_MCP_READ_TOKEN", READ_TOKEN)
    monkeypatch.setenv("GRIDSIGNAL_MCP_RUN_TOKEN", RUN_TOKEN)
    with TestClient(app) as client:
        initialized = client.post(
            "/",
            headers={"Authorization": f"Bearer {READ_TOKEN}"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-03-26"},
            },
        )
        assert initialized.status_code == 200
        assert initialized.json()["result"]["capabilities"]["tools"] == {}

        scenarios = _call(client, "list_scenarios", {}, READ_TOKEN)
        assert scenarios["scenarios"]["total"] == 5
        assert scenarios["scenarios"]["returned"] == 5
        assert scenarios["scenarios"]["has_more"] is False

        metrics = _call(
            client,
            "get_run_metrics",
            {
                "run_id": "scenario-h1-k8s-ray-24h-baseline",
                "section": "fuel",
            },
            READ_TOKEN,
        )
        components = metrics["fuel"]["fuel_by_component_mmbtu"]
        assert sum(components.values()) == pytest.approx(
            metrics["fuel"]["turbine_fuel_mmbtu"]
        )
        assert metrics["reconciliation"]["fuel_reconciled"] is True

        commitment = _call(
            client,
            "get_commitment_log",
            {"run_id": "scenario-h1-k8s-ray-7d-baseline"},
            READ_TOKEN,
        )
        assert commitment["entries"]["total"] == 288
        assert commitment["entries"]["has_more"] is True

        incomplete = _call(
            client,
            "get_commitment_log",
            {
                "run_id": "scenario-h1-k8s-ray-7d-baseline",
                "action": "start",
            },
            READ_TOKEN,
        )
        assert incomplete["error"]["type"] == "INCOMPLETE_SOURCE_LIST"

        ticks = _call(
            client,
            "get_ticks",
            {
                "run_id": "scenario-h1-k8s-ray-24h-baseline",
                "start_seconds": 0,
                "end_seconds": 600,
                "stride": 120,
                "fields": ["tick_index", "p_compute_mw"],
            },
            READ_TOKEN,
        )
        assert ticks["ticks"]["returned"] == 1

        comparison = _call(
            client,
            "compare_runs",
            {
                "baseline_run_id": "scenario-h1-k8s-ray-24h-baseline",
                "informed_run_id": "scenario-h1-k8s-ray-24h-informed",
            },
            READ_TOKEN,
        )
        assert comparison["verdict"] == "PASS"

        denied = _call(
            client,
            "start_run",
            {
                "scenario_id": "scenario-h1-k8s-ray-24h",
                "mode": "informed",
            },
            READ_TOKEN,
        )
        assert denied["error"]["type"] == "UNAUTHORIZED"


def test_run_token_can_discover_read_tools_for_one_connector(
    monkeypatch,
) -> None:
    """A remote MCP connector uses one bearer token for discovery and calls."""
    monkeypatch.setenv("GRIDSIGNAL_MCP_READ_TOKEN", READ_TOKEN)
    monkeypatch.setenv("GRIDSIGNAL_MCP_RUN_TOKEN", RUN_TOKEN)
    with TestClient(app) as client:
        listed = client.post(
            "/",
            headers={"Authorization": f"Bearer {RUN_TOKEN}"},
            json={
                "jsonrpc": "2.0",
                "id": "run-token-tools",
                "method": "tools/list",
                "params": {},
            },
        )
        assert listed.status_code == 200
        tool_names = {
            tool["name"] for tool in listed.json()["result"]["tools"]
        }
        assert {"get_scenario", "start_run"} <= tool_names

        scenarios = _call(client, "list_scenarios", {}, RUN_TOKEN)
        assert scenarios["scenarios"]["total"] == 5


def test_mcp_cache_hit_and_build_parity_error(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("GRIDSIGNAL_MCP_READ_TOKEN", READ_TOKEN)
    monkeypatch.setenv("GRIDSIGNAL_MCP_RUN_TOKEN", RUN_TOKEN)
    identity = service._identity(
        scenario_id="scenario-h1-k8s-ray-24h",
        mode="informed",
        parameter_overrides=None,
        seed=None,
    )
    cached_record = {
        "scenario_id": "scenario-h1-k8s-ray-24h",
        "mode": "informed",
        "engine_commit": identity.engine_commit,
        "harness_commit": identity.harness_commit,
        "status": "PASS",
        "turbine_fuel_mmbtu": 1.0,
        "fuel_by_component_mmbtu": {"load_fuel_mmbtu": 1.0},
        "fuel_reconciled": True,
        "energy_balance": {"closure_status": True},
        "constraints_valid": True,
        "hard_violations": [],
        "unserved_mwh": 0.0,
        "peak_unserved_mw": 0.0,
        "compute_trace_sha256": "same",
    }
    service.executor.cache = service.executor.cache.__class__(tmp_path)
    service.executor.cache.put(identity, cached_record)
    with TestClient(app) as client:
        result = _call(
            client,
            "start_run",
            {
                "scenario_id": "scenario-h1-k8s-ray-24h",
                "mode": "informed",
                "reuse_cache": True,
            },
            RUN_TOKEN,
        )
        assert result["cache_hit"] is True
        assert result["status"] == "COMPLETED"

        baseline = copy.deepcopy(cached_record)
        informed = copy.deepcopy(cached_record)
        baseline["engine_commit"] = "engine-a"
        informed["engine_commit"] = "engine-b"
        baseline_id = "mcp-test-baseline-parity"
        informed_id = "mcp-test-informed-parity"
        service._runs[baseline_id] = RunState(
            baseline_id,
            "scenario-h1-k8s-ray-24h",
            "baseline",
            "b",
            status="COMPLETED",
            record=baseline,
        )
        service._runs[informed_id] = RunState(
            informed_id,
            "scenario-h1-k8s-ray-24h",
            "informed",
            "i",
            status="COMPLETED",
            record=informed,
        )
        parity = _call(
            client,
            "compare_runs",
            {
                "baseline_run_id": baseline_id,
                "informed_run_id": informed_id,
            },
            READ_TOKEN,
        )
        assert parity["error"]["type"] == "BUILD_PARITY_MISMATCH"
        assert parity["error"]["baseline_engine_commit"] == "engine-a"
        assert parity["error"]["informed_engine_commit"] == "engine-b"


def _isolated_service(monkeypatch, tmp_path: Path) -> StudyService:
    monkeypatch.setattr(server_module, "DATA_ROOT", tmp_path / "study-data")
    isolated = StudyService()
    monkeypatch.setattr(server_module, "service", isolated)
    return isolated


def _wait_for_run(client: TestClient, run_id: str) -> dict:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        status = _call(
            client,
            "get_run_status",
            {"run_id": run_id},
            READ_TOKEN,
        )
        if status["status"] in {"COMPLETED", "FAILED"}:
            return status
        time.sleep(0.02)
    pytest.fail(f"run {run_id} did not finish within 90 seconds")


def test_tc160_list_scenarios_marks_all_five_study_classes(
    monkeypatch,
) -> None:
    monkeypatch.setenv("GRIDSIGNAL_MCP_READ_TOKEN", READ_TOKEN)
    monkeypatch.setenv("GRIDSIGNAL_MCP_RUN_TOKEN", RUN_TOKEN)
    with TestClient(app) as client:
        result = _call(client, "list_scenarios", {}, READ_TOKEN)["scenarios"]

        assert result["total"] == result["returned"] == 5
        by_id = {item["scenario_id"]: item for item in result["items"]}
        assert set(by_id) == set(server_module.STUDY_SCENARIOS)
        assert all(item["study_supported"] is True for item in by_id.values())
        for scenario_id in server_module.REFERENCE_SCENARIOS:
            assert by_id[scenario_id]["kind"] == "addendum_h"
            assert by_id[scenario_id]["study_class"] == "addendum_h"
        base = by_id[server_module.BASE_SCENARIO]
        assert base["kind"] == "base"
        assert base["study_class"] == "base_demo"

        # Committed H records predate the field; responses derive the class
        # from the harness mapping without rewriting their stored artifacts.
        legacy_id = "scenario-h1-k8s-ray-24h-baseline"
        status = _call(
            client,
            "get_run_status",
            {"run_id": legacy_id},
            READ_TOKEN,
        )
        metrics = _call(
            client,
            "get_run_metrics",
            {"run_id": legacy_id, "section": "fuel"},
            READ_TOKEN,
        )
        assert status["study_class"] == "addendum_h"
        assert metrics["study_class"] == "addendum_h"


def test_tc161_start_run_accepts_the_base_demo_scenario(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("GRIDSIGNAL_MCP_READ_TOKEN", READ_TOKEN)
    monkeypatch.setenv("GRIDSIGNAL_MCP_RUN_TOKEN", RUN_TOKEN)
    isolated = _isolated_service(monkeypatch, tmp_path)
    try:
        with TestClient(app) as client:
            result = _call(
                client,
                "start_run",
                {
                    "scenario_id": server_module.BASE_SCENARIO,
                    "mode": "baseline",
                    "parameter_overrides": {"end_sim_time": 5.0},
                    "reuse_cache": True,
                },
                RUN_TOKEN,
            )
            assert result["run_id"].startswith(
                f"{server_module.BASE_SCENARIO}-baseline-"
            )
            completed = _wait_for_run(client, result["run_id"])
            assert completed["status"] == "COMPLETED", completed.get("error")
            assert completed["study_class"] == "base_demo"
            metrics = _call(
                client,
                "get_run_metrics",
                {"run_id": result["run_id"], "section": "energy"},
                READ_TOKEN,
            )
            assert metrics["study_class"] == "base_demo"
    finally:
        isolated._pool.shutdown(wait=True)


def test_tc162_cross_class_compare_returns_typed_mismatch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("GRIDSIGNAL_MCP_READ_TOKEN", READ_TOKEN)
    monkeypatch.setenv("GRIDSIGNAL_MCP_RUN_TOKEN", RUN_TOKEN)
    isolated = _isolated_service(monkeypatch, tmp_path)
    baseline_id = "tc162-base-baseline"
    informed_id = "tc162-h-informed"
    isolated._runs[baseline_id] = RunState(
        baseline_id,
        server_module.BASE_SCENARIO,
        "baseline",
        "base-identity",
        status="COMPLETED",
        record={"study_class": "base_demo"},
    )
    isolated._runs[informed_id] = RunState(
        informed_id,
        server_module.REFERENCE_SCENARIOS[0],
        "informed",
        "h-identity",
        status="COMPLETED",
        record={"study_class": "addendum_h"},
    )
    try:
        with TestClient(app) as client:
            result = _call(
                client,
                "compare_runs",
                {
                    "baseline_run_id": baseline_id,
                    "informed_run_id": informed_id,
                },
                READ_TOKEN,
            )
        assert result["error"]["type"] == "STUDY_CLASS_MISMATCH"
        assert result["error"]["baseline_study_class"] == "base_demo"
        assert result["error"]["informed_study_class"] == "addendum_h"
        assert result["error"]["baseline_run_id"] == baseline_id
        assert result["error"]["informed_run_id"] == informed_id
    finally:
        isolated._pool.shutdown(wait=True)


def test_tc163_base_demo_comparison_includes_claim_note(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("GRIDSIGNAL_MCP_READ_TOKEN", READ_TOKEN)
    monkeypatch.setenv("GRIDSIGNAL_MCP_RUN_TOKEN", RUN_TOKEN)
    isolated = _isolated_service(monkeypatch, tmp_path)
    record = {
        "study_class": "base_demo",
        "engine_commit": "same-engine",
        "harness_commit": "same-harness",
        "energy_balance": {"closure_status": True},
        "hard_violations": [],
        "constraints_valid": True,
        "fuel_reconciled": True,
        "fuel_by_component_mmbtu": {"load_fuel_mmbtu": 1.0},
        "turbine_fuel_mmbtu": 1.0,
        "compute_trace_sha256": "same-trace",
        "unserved_mwh": 0.0,
        "peak_unserved_mw": 0.0,
    }
    baseline_id = "tc163-base-baseline"
    informed_id = "tc163-base-informed"
    for run_id, mode in ((baseline_id, "baseline"), (informed_id, "informed")):
        isolated._runs[run_id] = RunState(
            run_id,
            server_module.BASE_SCENARIO,
            mode,
            f"{mode}-identity",
            status="COMPLETED",
            record=copy.deepcopy(record),
        )
    try:
        with TestClient(app) as client:
            result = _call(
                client,
                "compare_runs",
                {
                    "baseline_run_id": baseline_id,
                    "informed_run_id": informed_id,
                },
                READ_TOKEN,
            )
        assert result["study_class"] == "base_demo"
        assert result["verdict"] == "PASS"
        assert result["claim_note"] == (
            "This is the legacy demo, not an Addendum H scenario; "
            "the Addendum H acceptance gate still applies as a diagnostic."
        )
    finally:
        isolated._pool.shutdown(wait=True)


def test_tc164_shared_identity_and_cache_match_for_every_study_scenario(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("GRIDSIGNAL_MCP_READ_TOKEN", READ_TOKEN)
    monkeypatch.setenv("GRIDSIGNAL_MCP_RUN_TOKEN", RUN_TOKEN)
    isolated = _isolated_service(monkeypatch, tmp_path)
    isolated._rate_limiter = RateLimiter(100)
    try:
        with TestClient(app) as client:
            for scenario_id in server_module.STUDY_SCENARIOS:
                for mode in ("baseline", "informed"):
                    arguments = {
                        "scenario_id": scenario_id,
                        "mode": mode,
                        "parameter_overrides": {"end_sim_time": 5.0},
                        "reuse_cache": True,
                    }
                    identity = isolated._identity(
                        scenario_id=scenario_id,
                        mode=mode,
                        parameter_overrides=arguments["parameter_overrides"],
                        seed=None,
                    )
                    started = _call(
                        client,
                        "start_run",
                        arguments,
                        RUN_TOKEN,
                    )
                    completed = _wait_for_run(client, started["run_id"])
                    assert completed["status"] == "COMPLETED", (
                        scenario_id,
                        mode,
                        completed.get("error"),
                    )
                    record = isolated._runs[started["run_id"]].record
                    assert record is not None
                    assert record["identity_digest"] == identity.digest
                    assert started["run_id"].endswith(
                        f"-{record['identity_digest'][:16]}"
                    )
                    assert record["study_class"] == (
                        server_module.study_class_for_scenario(scenario_id)
                    )

                    cached = _call(
                        client,
                        "start_run",
                        arguments,
                        RUN_TOKEN,
                    )
                    assert cached["run_id"] == started["run_id"]
                    assert cached["cache_hit"] is True
                    assert cached["estimated_wall_clock_seconds"] == 0.0
    finally:
        isolated._pool.shutdown(wait=True)