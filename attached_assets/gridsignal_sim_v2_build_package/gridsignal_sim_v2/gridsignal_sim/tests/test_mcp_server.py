from __future__ import annotations

import copy
import subprocess
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
from runtime.scenario_factory import prepare_workload_timeline
import runtime.seed_resolution as seed_resolution_module


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
    """TC-SSH08-09: committed H rows with unknown provenance refuse comparison."""
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
        # Proxim8 is an additive JSON-backed MCP scenario.
        assert scenarios["scenarios"]["total"] == 9
        assert scenarios["scenarios"]["returned"] == 9
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
        assert comparison["error"]["type"] == "PROVENANCE_UNKNOWN"
        assert comparison["error"]["baseline_run_id"] == (
            "scenario-h1-k8s-ray-24h-baseline"
        )
        assert comparison["error"]["informed_run_id"] == (
            "scenario-h1-k8s-ray-24h-informed"
        )
        assert comparison["error"]["baseline_engine_commit"] == "unknown"
        assert comparison["error"]["informed_engine_commit"] == "unknown"
        assert comparison["error"]["baseline_harness_commit"] == "unknown"
        assert comparison["error"]["informed_harness_commit"] == "unknown"

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
        # Proxim8 is the ninth additive MCP study-list entry.
        assert scenarios["scenarios"]["total"] == 9


def test_mcp_cache_hit_and_build_parity_error(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """TC-SSH08-06: distinct known commits still return BUILD_PARITY_MISMATCH."""
    monkeypatch.setenv("GRIDSIGNAL_MCP_READ_TOKEN", READ_TOKEN)
    monkeypatch.setenv("GRIDSIGNAL_MCP_RUN_TOKEN", RUN_TOKEN)
    identity = service._identity(
        scenario_id="scenario-h1-k8s-ray-24h",
        mode="informed",
        parameter_overrides=None,
        # D4 includes the resolved seed in the cache identity; 6c's cache-hit
        # case must therefore use the same explicit seed as the request.
        seed=42,  # PROPOSED_HERE: deterministic explicit cache-key fixture.
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
                "seed": 42,  # PROPOSED_HERE: matches the cached identity.
                "reuse_cache": True,
            },
            RUN_TOKEN,
        )
        assert result["cache_hit"] is True
        assert result["status"] == "COMPLETED"

        baseline = copy.deepcopy(cached_record)
        informed = copy.deepcopy(cached_record)
        repo_root = Path(__file__).resolve().parents[5]
        current_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            cwd=repo_root,
        ).strip()
        previous_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD^"],
            text=True,
            cwd=repo_root,
        ).strip()
        baseline["engine_commit"] = current_commit
        informed["engine_commit"] = previous_commit
        baseline["harness_commit"] = current_commit
        informed["harness_commit"] = current_commit
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
        assert parity["error"]["baseline_engine_commit"] == current_commit
        assert parity["error"]["informed_engine_commit"] == previous_commit
        assert parity["error"]["baseline_harness_commit"] == current_commit
        assert parity["error"]["informed_harness_commit"] == current_commit


def test_tc_isl_41_explicit_seed_reuses_cache(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """TC-ISL-41: repeated explicit-seed requests reuse the same cached run."""
    monkeypatch.setenv("GRIDSIGNAL_MCP_READ_TOKEN", READ_TOKEN)
    monkeypatch.setenv("GRIDSIGNAL_MCP_RUN_TOKEN", RUN_TOKEN)
    isolated = _isolated_service(monkeypatch, tmp_path)
    isolated._rate_limiter = RateLimiter(100)
    arguments = {
        "scenario_id": "scenario-h1-k8s-ray-24h",
        "mode": "informed",
        "parameter_overrides": {"end_sim_time": 5.0},
        "seed": 42,
        "reuse_cache": True,
    }
    try:
        with TestClient(app) as client:
            first = _call(client, "start_run", arguments, RUN_TOKEN)
            assert first["cache_hit"] is False
            assert first["cache_bypass_reason"] is None
            assert _wait_for_run(client, first["run_id"])["status"] == "COMPLETED"

            second = _call(client, "start_run", arguments, RUN_TOKEN)
            assert second["cache_hit"] is True
            assert second["cache_bypass_reason"] is None
            assert second["run_id"] == first["run_id"]
    finally:
        isolated._pool.shutdown(wait=True)


def test_tc_isl_42_null_seed_requests_run_fresh_and_record_distinct_seeds(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """TC-ISL-42: null-seed requests bypass lookup and record each fresh seed."""
    monkeypatch.setenv("GRIDSIGNAL_MCP_READ_TOKEN", READ_TOKEN)
    monkeypatch.setenv("GRIDSIGNAL_MCP_RUN_TOKEN", RUN_TOKEN)
    isolated = _isolated_service(monkeypatch, tmp_path)
    isolated._rate_limiter = RateLimiter(100)
    # PROPOSED_HERE: distinct synthetic draws make fresh null-seed behavior
    # deterministic in this test.
    draws = iter((61001, 61002))
    # PROPOSED_HERE: fixed synthetic root draw for the recorded-seed replay.
    monkeypatch.setattr(
        seed_resolution_module.secrets,
        "randbits",
        lambda bit_count: next(draws),
    )
    arguments = {
        "scenario_id": "scenario-h1-k8s-ray-24h",
        "mode": "informed",
        "parameter_overrides": {"end_sim_time": 5.0},
        "reuse_cache": True,
    }
    try:
        with TestClient(app) as client:
            first = _call(client, "start_run", arguments, RUN_TOKEN)
            assert first["cache_hit"] is False
            assert first["cache_bypass_reason"] == "seed_not_provided"
            assert _wait_for_run(client, first["run_id"])["status"] == "COMPLETED"
            first_seed = isolated._runs[first["run_id"]].record["seed_manifest"][
                "root_seed"
            ]

            second = _call(client, "start_run", arguments, RUN_TOKEN)
            assert second["cache_hit"] is False
            assert second["cache_bypass_reason"] == "seed_not_provided"
            assert _wait_for_run(client, second["run_id"])["status"] == "COMPLETED"
            second_seed = isolated._runs[second["run_id"]].record["seed_manifest"][
                "root_seed"
            ]

            assert first_seed == 61001
            assert second_seed == 61002
            assert first_seed != second_seed
            assert first["run_id"] != second["run_id"]
    finally:
        isolated._pool.shutdown(wait=True)


def test_tc_isl_43_recorded_null_seed_can_replay_from_cache(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """TC-ISL-43: an explicit recorded seed can reuse its earlier null-seed run."""
    monkeypatch.setenv("GRIDSIGNAL_MCP_READ_TOKEN", READ_TOKEN)
    monkeypatch.setenv("GRIDSIGNAL_MCP_RUN_TOKEN", RUN_TOKEN)
    isolated = _isolated_service(monkeypatch, tmp_path)
    isolated._rate_limiter = RateLimiter(100)
    monkeypatch.setattr(
        seed_resolution_module.secrets,
        "randbits",
        lambda bit_count: 62003,
    )
    arguments = {
        "scenario_id": "scenario-h1-k8s-ray-24h",
        "mode": "informed",
        "parameter_overrides": {"end_sim_time": 5.0},
        "reuse_cache": True,
    }
    try:
        with TestClient(app) as client:
            first = _call(client, "start_run", arguments, RUN_TOKEN)
            assert first["cache_hit"] is False
            assert first["cache_bypass_reason"] == "seed_not_provided"
            assert _wait_for_run(client, first["run_id"])["status"] == "COMPLETED"
            recorded_seed = isolated._runs[first["run_id"]].record["seed_manifest"][
                "root_seed"
            ]
            assert recorded_seed == 62003

            replay = _call(
                client,
                "start_run",
                {**arguments, "seed": recorded_seed},
                RUN_TOKEN,
            )
            assert replay["cache_hit"] is True
            assert replay["cache_bypass_reason"] is None
            assert replay["run_id"] == first["run_id"]
    finally:
        isolated._pool.shutdown(wait=True)


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


def test_tc160_list_scenarios_marks_all_nine_study_scenarios(
    monkeypatch,
) -> None:
    monkeypatch.setenv("GRIDSIGNAL_MCP_READ_TOKEN", READ_TOKEN)
    monkeypatch.setenv("GRIDSIGNAL_MCP_RUN_TOKEN", RUN_TOKEN)
    with TestClient(app) as client:
        result = _call(client, "list_scenarios", {}, READ_TOKEN)["scenarios"]

        # Existing entries keep their positions; Proxim8 follows S11b.
        assert result["total"] == result["returned"] == 9
        by_id = {item["scenario_id"]: item for item in result["items"]}
        assert set(by_id) == set(server_module.STUDY_SCENARIOS)
        assert all(item["study_supported"] is True for item in by_id.values())
        for scenario_id in server_module.REFERENCE_SCENARIOS:
            assert by_id[scenario_id]["kind"] == "addendum_h"
            assert by_id[scenario_id]["study_class"] == "addendum_h"
        base = by_id[server_module.BASE_SCENARIO]
        assert base["kind"] == "base"
        assert base["study_class"] == "base_demo"
        s10 = by_id[server_module.SUPER_CLOUD_REPLAY_SCENARIO_ID]
        assert s10["kind"] == "supercloud_replay"
        assert s10["study_class"] == "supercloud_replay"

        # Committed H records predate the field; responses derive the class
        # without backfilling provenance into stored artifacts.
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
        assert status["engine_commit"] == "unknown"
        assert status["harness_commit"] == "unknown"
        assert metrics["engine_commit"] == "unknown"
        assert metrics["harness_commit"] == "unknown"


def test_tc_isl_65_s10_list_and_get_scenario_use_tracked_source(
    monkeypatch,
) -> None:
    """TC-ISL-65: MCP discovers S10 and returns its own tracked JSON."""
    monkeypatch.setenv("GRIDSIGNAL_MCP_READ_TOKEN", READ_TOKEN)
    monkeypatch.setenv("GRIDSIGNAL_MCP_RUN_TOKEN", RUN_TOKEN)
    with TestClient(app) as client:
        listing = _call(client, "list_scenarios", {}, READ_TOKEN)["scenarios"]
        items = listing["items"]
        assert [item["scenario_id"] for item in items] == list(
            server_module.STUDY_SCENARIOS
        )
        s10 = next(
            item
            for item in items
            if item["scenario_id"] == "S10_mit_supercloud_2021-08-11"
        )
        assert s10["kind"] == "supercloud_replay"
        assert s10["study_class"] == "supercloud_replay"

        result = _call(
            client,
            "get_scenario",
            {"scenario_id": "S10_mit_supercloud_2021-08-11"},
            READ_TOKEN,
        )
        assert result["source"] == str(
            server_module._scenario_path(
                "S10_mit_supercloud_2021-08-11"
            ).relative_to(server_module.REPO_ROOT)
        )
        assert result["spec"]["name"] == "S10_mit_supercloud_2021-08-11"
        assert len(result["spec"]["workload_events"]) == 239
        assert len(result["spec"]["non_gpu_load_profile_mw"]) == 320


def test_tc_s11_06_s11_list_and_get_scenario_use_tracked_source(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """TC-S11-06: MCP and executor load S11's own tracked JSON."""
    monkeypatch.setenv("GRIDSIGNAL_MCP_READ_TOKEN", READ_TOKEN)
    monkeypatch.setenv("GRIDSIGNAL_MCP_RUN_TOKEN", RUN_TOKEN)
    s11_id = "S11_mit_supercloud_2021-08-11_bchydro"
    with TestClient(app) as client:
        listing = _call(client, "list_scenarios", {}, READ_TOKEN)["scenarios"]
        s11 = next(
            item for item in listing["items"] if item["scenario_id"] == s11_id
        )
        assert s11["study_supported"] is True
        assert s11["study_class"] == "supercloud_replay"

        result = _call(
            client,
            "get_scenario",
            {"scenario_id": s11_id},
            READ_TOKEN,
        )
        assert result["source"].endswith(
            "config/scenarios/S11_mit_supercloud_2021-08-11_bchydro.json"
        )
        assert result["spec"]["island_mode"] is False
        assert result["spec"]["grid_import_limit_mw"] == 80
        assert result["spec"]["turbine_units"] == []
        assert result["spec"]["diesel_power_block"]["enabled"] is False
        assert len(result["spec"]["workload_events"]) == 239

    # IMPL-S11-06: the replay executor must expand each scenario's own inputs.
    from study_harness.executor import StudyRunExecutor

    executor = StudyRunExecutor(output_dir=tmp_path / "s11-06-expansion")
    s11_spec = executor._expanded_spec(s11_id, None, None)
    assert s11_spec["island_mode"] is False
    assert s11_spec["grid_import_limit_mw"] == 80
    assert s11_spec["turbine_units"] == []
    s11b_id = "S11b_mit_supercloud_2021-08-11_bchydro_60mw"
    s11b_spec = executor._expanded_spec(s11b_id, None, None)
    assert s11b_spec["island_mode"] is False
    assert s11b_spec["grid_import_limit_mw"] == 60
    assert s11b_spec["turbine_units"] == []
    s10_spec = executor._expanded_spec(
        "S10_mit_supercloud_2021-08-11",
        None,
        None,
    )
    assert s10_spec["island_mode"] is True
    assert len(s10_spec["turbine_units"]) == 5


def test_tc_s11b_list_and_get_scenario_use_tracked_source(
    monkeypatch,
) -> None:
    """TC-S11-07: MCP discovers S11b and returns its tracked JSON."""
    monkeypatch.setenv("GRIDSIGNAL_MCP_READ_TOKEN", READ_TOKEN)
    monkeypatch.setenv("GRIDSIGNAL_MCP_RUN_TOKEN", RUN_TOKEN)
    s11b_id = "S11b_mit_supercloud_2021-08-11_bchydro_60mw"
    with TestClient(app) as client:
        listing = _call(client, "list_scenarios", {}, READ_TOKEN)["scenarios"]
        s11b = next(
            item
            for item in listing["items"]
            if item["scenario_id"] == s11b_id
        )
        assert s11b["study_supported"] is True
        assert s11b["study_class"] == "supercloud_replay"

        result = _call(
            client,
            "get_scenario",
            {"scenario_id": s11b_id},
            READ_TOKEN,
        )
        assert result["source"].endswith(
            "config/scenarios/S11b_mit_supercloud_2021-08-11_bchydro_60mw.json"
        )
        assert result["spec"]["island_mode"] is False
        assert result["spec"]["grid_import_limit_mw"] == 60
        assert result["spec"]["turbine_units"] == []
        assert result["spec"]["diesel_power_block"]["enabled"] is False
        assert len(result["spec"]["workload_events"]) == 239


def test_tc_isl_66_s10_start_run_metrics_and_compare_are_reachable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """TC-ISL-66: both S10 arms use the normal MCP run and metrics tools."""
    monkeypatch.setenv("GRIDSIGNAL_MCP_READ_TOKEN", READ_TOKEN)
    monkeypatch.setenv("GRIDSIGNAL_MCP_RUN_TOKEN", RUN_TOKEN)
    isolated = _isolated_service(monkeypatch, tmp_path)
    isolated._rate_limiter = RateLimiter(100)
    run_ids: dict[str, str] = {}
    try:
        with TestClient(app) as client:
            for mode in ("baseline", "informed"):
                started = _call(
                    client,
                    "start_run",
                    {
                        "scenario_id": "S10_mit_supercloud_2021-08-11",
                        "mode": mode,
                        "parameter_overrides": {"end_sim_time": 5.0},
                        "seed": 42,
                        "reuse_cache": False,
                    },
                    RUN_TOKEN,
                )
                run_ids[mode] = started["run_id"]
                completed = _wait_for_run(client, started["run_id"])
                assert completed["status"] == "COMPLETED", completed.get("error")
                assert completed["study_class"] == "supercloud_replay"
                metrics = _call(
                    client,
                    "get_run_metrics",
                    {"run_id": started["run_id"], "section": "energy"},
                    READ_TOKEN,
                )
                assert metrics["study_class"] == "supercloud_replay"
                assert "operating_cost" in metrics["energy"]
                assert metrics["energy"]["frequency_feedback_configured"] is False

            comparison = _call(
                client,
                "compare_runs",
                {
                    "baseline_run_id": run_ids["baseline"],
                    "informed_run_id": run_ids["informed"],
                },
                READ_TOKEN,
            )
            assert comparison["study_class"] == "supercloud_replay"
            assert comparison["verdict"] in {"PASS", "FAIL"}
            assert len(comparison["conditions"]["items"]) == 10
            assert (
                comparison["frequency_inputs"][
                    "baseline_frequency_feedback_configured"
                ]
                is False
            )
            assert (
                comparison["frequency_inputs"][
                    "informed_frequency_feedback_configured"
                ]
                is False
            )
    finally:
        isolated._pool.shutdown(wait=True)


def test_tc_isl_70_unprotected_s10_invalid_ticks_are_informational(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """TC-ISL-70: S10 keeps all ten gates with feedback=False frequency validity."""
    monkeypatch.setenv("GRIDSIGNAL_MCP_READ_TOKEN", READ_TOKEN)
    isolated = _isolated_service(monkeypatch, tmp_path)
    baseline_id = "tc-isl-70-s10-baseline"
    informed_id = "tc-isl-70-s10-informed"
    for run_id, mode in ((baseline_id, "baseline"), (informed_id, "informed")):
        record = _comparison_record("same-engine", "same-harness")
        record.update(
            {
                "study_class": "supercloud_replay",
                "frequency_feedback_configured": False,
                "protection_configured": False,
                "invalid_frequency_tick_count": 12,
                "invalid_frequency_fraction": 0.25,
            }
        )
        isolated._runs[run_id] = RunState(
            run_id,
            server_module.SUPER_CLOUD_REPLAY_SCENARIO_ID,
            mode,
            f"{mode}-identity",
            status="COMPLETED",
            record=record,
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
        assert result["verdict"] == "PASS"
        assert len(result["conditions"]["items"]) == 10
        assert all(item["passed"] for item in result["conditions"]["items"])
        assert result["frequency_inputs"]["baseline_invalid_frequency_tick_count"] == 12
        assert result["frequency_inputs"]["informed_invalid_frequency_fraction"] == 0.25
    finally:
        isolated._pool.shutdown(wait=True)


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
        # IMPL-ISL-22: fixtures must provide known frequency inputs to pass
        # the fail-closed study-validity gate.
        "frequency_feedback_configured": False,
        "protection_configured": False,
        "invalid_frequency_tick_count": 0,
        "invalid_frequency_fraction": 0.0,
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
        assert result["claim_note"] == "demonstration scenario; not an Addendum H study result"
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
                        # D4: the resolved seed is part of run/cache identity;
                        # an explicit seed makes this cache replay intentional.
                        "seed": 42,
                        "reuse_cache": True,
                    }
                    expanded_spec = isolated.executor._expanded_spec(
                        scenario_id,
                        arguments["parameter_overrides"],
                        None,
                    )
                    seed_manifest = isolated.executor.resolve_seed_manifest(
                        expanded_spec,
                        arguments["seed"],
                    )
                    # IMPL-ISL-30/31: identity/cache inputs include the shared,
                    # seed-prepared Slurm timeline, not the unprepared source.
                    prepared_spec = prepare_workload_timeline(
                        expanded_spec,
                        seed_manifest,
                    )
                    identity = isolated._identity(
                        scenario_id=scenario_id,
                        mode=mode,
                        parameter_overrides=arguments["parameter_overrides"],
                        seed=arguments["seed"],
                        seed_manifest=seed_manifest,
                        spec=prepared_spec,
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


def _comparison_record(engine_commit: str, harness_commit: str) -> dict:
    return {
        "study_class": "base_demo",
        "engine_commit": engine_commit,
        "harness_commit": harness_commit,
        "energy_balance": {"closure_status": True},
        "constraints_valid": True,
        "hard_violations": [],
        "fuel_by_component_mmbtu": {},
        "turbine_fuel_mmbtu": 0.0,
        "fuel_reconciled": True,
        "start_count_reconciled": True,
        "compute_trace_sha256": "same-compute-trace",
        "unserved_mwh": 0.0,
        "peak_unserved_mw": 0.0,
        # IMPL-ISL-22: comparison fixtures provide all four frequency fields.
        "frequency_feedback_configured": False,
        "protection_configured": False,
        "invalid_frequency_tick_count": 0,
        "invalid_frequency_fraction": 0.0,
    }


def test_tc_ssh08_05_identical_real_commits_still_compare(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """TC-SSH08-05: known identical commits continue through compare_runs."""
    monkeypatch.setenv("GRIDSIGNAL_MCP_READ_TOKEN", READ_TOKEN)
    isolated = _isolated_service(monkeypatch, tmp_path)
    repo_root = Path(__file__).resolve().parents[5]
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        text=True,
        cwd=repo_root,
    ).strip()
    baseline_id = "tc-ssh08-05-baseline"
    informed_id = "tc-ssh08-05-informed"
    isolated._runs[baseline_id] = RunState(
        baseline_id,
        server_module.BASE_SCENARIO,
        "baseline",
        "baseline-seed",
        status="COMPLETED",
        record=_comparison_record(commit, commit),
    )
    isolated._runs[informed_id] = RunState(
        informed_id,
        server_module.BASE_SCENARIO,
        "informed",
        "informed-seed",
        status="COMPLETED",
        record=_comparison_record(commit, commit),
    )

    try:
        with TestClient(app) as client:
            comparison = _call(
                client,
                "compare_runs",
                {
                    "baseline_run_id": baseline_id,
                    "informed_run_id": informed_id,
                },
                READ_TOKEN,
            )
        assert comparison["verdict"] == "PASS"
        assert comparison["study_class"] == "base_demo"
        conditions = {
            item["name"]: item
            for item in comparison["conditions"]["items"]
        }
        assert conditions["build_parity"]["passed"] is True
        assert conditions["build_parity"]["inputs"]["baseline_engine_commit"] == (
            commit
        )
        assert conditions["build_parity"]["inputs"]["baseline_harness_commit"] == (
            commit
        )
    finally:
        isolated._pool.shutdown(wait=True)


@pytest.mark.parametrize(
    ("side", "field"),
    [
        pytest.param("baseline", "engine_commit", id="baseline-engine"),
        pytest.param("informed", "engine_commit", id="informed-engine"),
        pytest.param("baseline", "harness_commit", id="baseline-harness"),
        pytest.param("informed", "harness_commit", id="informed-harness"),
    ],
)
def test_tc_ssh08_07_compare_runs_returns_typed_unknown_provenance(
    monkeypatch,
    tmp_path: Path,
    side: str,
    field: str,
) -> None:
    """TC-SSH08-07: unknown provenance returns IDs and all four commit values."""
    monkeypatch.setenv("GRIDSIGNAL_MCP_READ_TOKEN", READ_TOKEN)
    isolated = _isolated_service(monkeypatch, tmp_path)
    baseline = _comparison_record("a" * 40, "b" * 40)
    informed = _comparison_record("a" * 40, "b" * 40)
    target = baseline if side == "baseline" else informed
    target[field] = "unknown"
    baseline_id = "tc-ssh08-07-baseline"
    informed_id = "tc-ssh08-07-informed"
    isolated._runs[baseline_id] = RunState(
        baseline_id,
        server_module.BASE_SCENARIO,
        "baseline",
        "baseline-seed",
        status="COMPLETED",
        record=baseline,
    )
    isolated._runs[informed_id] = RunState(
        informed_id,
        server_module.BASE_SCENARIO,
        "informed",
        "informed-seed",
        status="COMPLETED",
        record=informed,
    )

    try:
        with TestClient(app) as client:
            response = _call(
                client,
                "compare_runs",
                {
                    "baseline_run_id": baseline_id,
                    "informed_run_id": informed_id,
                },
                READ_TOKEN,
            )
        assert response["error"]["type"] == "PROVENANCE_UNKNOWN"
        assert response["error"]["baseline_run_id"] == baseline_id
        assert response["error"]["informed_run_id"] == informed_id
        assert response["error"]["baseline_engine_commit"] == baseline.get(
            "engine_commit", ""
        )
        assert response["error"]["informed_engine_commit"] == informed.get(
            "engine_commit", ""
        )
        assert response["error"]["baseline_harness_commit"] == baseline.get(
            "harness_commit", ""
        )
        assert response["error"]["informed_harness_commit"] == informed.get(
            "harness_commit", ""
        )
    finally:
        isolated._pool.shutdown(wait=True)


def test_tc_ssh08_08_run_status_and_metrics_include_both_commits(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """TC-SSH08-08: run status and metric responses expose provenance."""
    monkeypatch.setenv("GRIDSIGNAL_MCP_READ_TOKEN", READ_TOKEN)
    isolated = _isolated_service(monkeypatch, tmp_path)
    run_id = "tc-ssh08-08-run"
    engine_commit = "a" * 40
    harness_commit = "b" * 40
    isolated._runs[run_id] = RunState(
        run_id,
        server_module.BASE_SCENARIO,
        "baseline",
        "test-seed",
        status="COMPLETED",
        record=_comparison_record(engine_commit, harness_commit),
    )

    try:
        with TestClient(app) as client:
            status = _call(
                client,
                "get_run_status",
                {"run_id": run_id},
                READ_TOKEN,
            )
            metrics = _call(
                client,
                "get_run_metrics",
                {"run_id": run_id, "section": "fuel"},
                READ_TOKEN,
            )
        assert status["study_class"] == "base_demo"
        assert status["engine_commit"] == engine_commit
        assert status["harness_commit"] == harness_commit
        assert metrics["engine_commit"] == engine_commit
        assert metrics["harness_commit"] == harness_commit
    finally:
        isolated._pool.shutdown(wait=True)