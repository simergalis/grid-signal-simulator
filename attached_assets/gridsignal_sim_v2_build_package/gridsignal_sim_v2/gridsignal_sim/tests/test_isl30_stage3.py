"""IMPL-ISL-30/31 stage-3 synthetic Slurm submit-time contract tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from api.schemas import ScenarioSpec
from runtime.scenario_factory import prepare_workload_timeline
from runtime.synthetic_queue_wait_cdf import (
    SYNTHETIC_QUEUE_WAIT_CDF_HISTOGRAM,
    SYNTHETIC_QUEUE_WAIT_CDF_VERSION,
)
from runtime.run_manager import _tick_result_to_dict
from study_harness.executor import (
    BASE_DEMO_SCENARIO_ID,
    STUDY_IDENTITY_VERSION,
    make_study_run_identity,
)
from study_harness.manifest import RunManifestCache
from runtime.scenario_factory import build_run_context_from_spec


def _event(
    event_id: str,
    event_type: str,
    timestamp: float,
    job_id: str,
    scheduler_type: str | None = "SLURM",
    submit_time_s: float | None = None,
) -> dict:
    event = {
        "event_id": event_id,
        "event_type": event_type,
        "timestamp": timestamp,
        "job_id": job_id,
        "scheduler_type": scheduler_type,
        "node_count": 40,
        "hardware_profile_id": "enterprise_8gpu_air",
        "workload_class": "training",
    }
    if submit_time_s is not None:
        event["submit_time_s"] = submit_time_s
    return event


def _timeline_spec(events: list[dict]) -> dict:
    return {
        "end_sim_time": 3600.0,
        "turbine_forecast_lead_seconds": 600.0,
        "turbine_forecast_announcement_cap_seconds": 1800.0,
        "workload_events": events,
    }


def _prepare(events: list[dict], root_seed: int = 42) -> dict:
    return prepare_workload_timeline(
        _timeline_spec(events),
        {"root_seed": root_seed},
    )


def test_tc_isl_90_slurm_waits_are_stable_across_processes_and_arms() -> None:
    """The keyed per-job CDF draw is process-stable and mode-independent."""
    events = [
        _event("start-job-a", "starting", 7200.0, "job-a"),
        _event("scale-job-a", "scale", 7260.0, "job-a"),
    ]
    baseline_prepared = _prepare(events)
    informed_prepared = _prepare(events)
    expected = baseline_prepared["workload_events"]
    assert expected == informed_prepared["workload_events"]
    assert expected[0]["submit_time_s"] == expected[1]["submit_time_s"]
    assert expected[0]["submit_time_s"] <= 7200.0

    assert sum(row[2] for row in SYNTHETIC_QUEUE_WAIT_CDF_HISTOGRAM) == 153
    assert sum(row[1] for row in SYNTHETIC_QUEUE_WAIT_CDF_HISTOGRAM) == 70756
    assert SYNTHETIC_QUEUE_WAIT_CDF_VERSION == "s10-2021-08-11-mw-weighted-v1"

    code = """
import json
from runtime.scenario_factory import prepare_workload_timeline
events = [
    {"event_id":"start-job-a","event_type":"starting","timestamp":7200.0,
     "job_id":"job-a","scheduler_type":"SLURM","node_count":40,
     "hardware_profile_id":"enterprise_8gpu_air","workload_class":"training"},
    {"event_id":"scale-job-a","event_type":"scale","timestamp":7260.0,
     "job_id":"job-a","scheduler_type":"SLURM","node_count":40,
     "hardware_profile_id":"enterprise_8gpu_air","workload_class":"training"},
]
spec = {"workload_events": events,
        "turbine_forecast_announcement_cap_seconds": 1800.0}
out = prepare_workload_timeline(spec, {"root_seed": 42})
print(json.dumps(out["workload_events"], sort_keys=True, separators=(",", ":")))
"""
    package_root = Path(__file__).resolve().parents[1]
    outputs = []
    for hash_seed in ("1", "987654321"):
        env = dict(os.environ, PYTHONHASHSEED=hash_seed)
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=package_root,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        outputs.append(result.stdout.strip())
    expected_json = json.dumps(
        expected,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert outputs == [expected_json, expected_json]


def test_tc_isl_92_prepared_timeline_and_policy_change_identity_and_cache_key(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Submit-time timeline and its derivation inputs are identity inputs."""
    spec = _timeline_spec([_event("start-a", "starting", 7200.0, "job-a")])
    prepared = prepare_workload_timeline(spec, {"root_seed": 42})
    altered = json.loads(json.dumps(prepared))
    altered["workload_events"][0]["submit_time_s"] -= 1.0

    def identity(value: dict):
        return make_study_run_identity(
            scenario_id=BASE_DEMO_SCENARIO_ID,
            mode="baseline",
            spec=value,
            seed=42,
            tick_seconds=5.0,
            engine_commit="fixed-engine",
            harness_commit="fixed-harness",
        )

    first = identity(prepared)
    second = identity(altered)
    parameters = first.parameter_set
    assert STUDY_IDENTITY_VERSION == 4
    assert parameters["study_identity_version"] == 4
    assert parameters["workload_events_sha256"]
    assert parameters["synthetic_submit_time_policy_version"]
    assert parameters["synthetic_queue_wait_cdf_version"] == (
        SYNTHETIC_QUEUE_WAIT_CDF_VERSION
    )
    assert parameters["turbine_forecast_announcement_cap_seconds"] == 1800.0
    assert parameters["synthetic_queue_wait_root_seed"] == 42
    assert first.digest != second.digest

    cache = RunManifestCache(tmp_path / "cache")
    cache.put(first, {"status": "cached"})
    assert cache.get(first) == {"status": "cached"}
    assert cache.get(second) is None

    # MCP must prepare the same event timeline before its own cache lookup,
    # then pass that exact prepared spec to executor.run_mode.
    import mcp_server.server as server_module
    from concurrent.futures import Future
    from mcp_server.server import StudyService

    monkeypatch.setattr(server_module, "DATA_ROOT", tmp_path / "mcp-data")
    service = StudyService()
    original_pool = service._pool
    original_pool.shutdown(wait=True)

    class CapturePool:
        args = None

        def submit(self, *args, **_kwargs):
            self.args = args
            return Future()

    capture_pool = CapturePool()
    service._pool = capture_pool
    try:
        mcp_spec = service.executor._expanded_spec(
            BASE_DEMO_SCENARIO_ID, None, None
        )
        mcp_seed_manifest = service.executor.resolve_seed_manifest(mcp_spec, 42)
        mcp_spec = prepare_workload_timeline(mcp_spec, mcp_seed_manifest)
        mcp_identity = service._identity(
            scenario_id=BASE_DEMO_SCENARIO_ID,
            mode="baseline",
            parameter_overrides=None,
            seed=42,
            seed_manifest=mcp_seed_manifest,
            spec=mcp_spec,
        )
        service.executor.cache.put(
            mcp_identity,
            {"status": "PASS", "artifacts": {"paths": {}}},
        )
        cached = service.start(
            scenario_id=BASE_DEMO_SCENARIO_ID,
            mode="baseline",
            parameter_overrides=None,
            seed=42,
            reuse_cache=True,
            principal="tc-isl-92",
        )
        assert cached["cache_hit"] is True

        changed_events = [
            _event(
                "explicit-start",
                "starting",
                3600.0,
                "explicit-job",
                submit_time_s=1200.0,
            )
        ]
        miss = service.start(
            scenario_id=BASE_DEMO_SCENARIO_ID,
            mode="baseline",
            parameter_overrides={"workload_events": changed_events},
            seed=42,
            reuse_cache=True,
            principal="tc-isl-92",
        )
        assert miss["cache_hit"] is False
        assert miss["status"] == "QUEUED"
        assert capture_pool.args[-1]["workload_events"] == changed_events
    finally:
        service._pool = original_pool


def _baseline_spec(submit_time_s: float) -> dict:
    spec = ScenarioSpec(
        name="isl30-stage3-baseline-parity",
        frequency_nominal_hz=60.0,
        power_factor=0.85,
        island_mode=True,
        end_sim_time=60.0,
        initial_spinning_count=2,
        turbine_units=[
            {
                "asset_id": f"turbine-{index}",
                "rated_mw": 10.0,
                "r_asset_mw_per_s": 0.5,
                "hot_standby": False,
                "initial_state": "spinning",
                "thermal_state": "hot",
                "hot_start_s": 300.0,
                "warm_start_s": 360.0,
                "cold_start_s": 600.0,
                "min_run_enabled": False,
                "min_down_enabled": False,
            }
            for index in range(2)
        ],
        workload_events=[
            _event(
                "start-job-a",
                "starting",
                0.0,
                "job-a",
                submit_time_s=submit_time_s,
            )
        ],
        turbine_commitment_mode="baseline",
    )
    return spec.model_dump(mode="json")


def test_tc_isl_93_synthetic_submit_metadata_does_not_change_baseline_physics() -> None:
    """Conventional dispatch ignores forecast submit metadata."""
    first = build_run_context_from_spec(
        "tc-isl-93-a",
        _baseline_spec(0.0),
        run_seed=42,
    )
    second = build_run_context_from_spec(
        "tc-isl-93-b",
        _baseline_spec(-1200.0),
        run_seed=42,
    )
    physical_fields = (
        "p_compute_demand_mw",
        "p_cooling_demand_mw",
        "p_total_mw",
        "p_generation_mw",
        "p_served_mw",
        "p_unserved_mw",
        "p_dispatch_curtailed_mw",
        "turbine_output_mw",
        "bess_output_mw",
        "bess_soc_fraction",
        "frequency_hz",
        "frequency_valid",
        "turbine_start_count",
    )
    first_rows = [
        _tick_result_to_dict(first.step())
        for _ in range(3)
    ]
    second_rows = [
        _tick_result_to_dict(second.step())
        for _ in range(3)
    ]
    assert [
        {field: row[field] for field in physical_fields}
        for row in first_rows
    ] == [
        {field: row[field] for field in physical_fields}
        for row in second_rows
    ]


def test_tc_isl_94_only_slurm_gets_synthetic_submit_and_s10_is_preserved() -> None:
    """K8s/Ray keep legacy lead; authored S10 submit values are untouched."""
    events = [
        _event("slurm-start", "starting", 7200.0, "slurm-job"),
        _event("kube-start", "starting", 7200.0, "kube-job", "K8S"),
        _event("ray-start", "starting", 7200.0, "ray-job", "RAY"),
    ]
    prepared = _prepare(events)["workload_events"]
    by_id = {event["event_id"]: event for event in prepared}
    assert "submit_time_s" in by_id["slurm-start"]
    assert "submit_time_s" not in by_id["kube-start"]
    assert "submit_time_s" not in by_id["ray-start"]

    s10_path = (
        Path(__file__).resolve().parents[1]
        / "config"
        / "scenarios"
        / "S10_mit_supercloud_2021-08-11.json"
    )
    s10_spec = json.loads(s10_path.read_text(encoding="utf-8"))
    s10_prepared = prepare_workload_timeline(
        s10_spec,
        {"root_seed": 42},
    )
    assert s10_prepared["workload_events"] == s10_spec["workload_events"]
    s10_start = next(
        event
        for event in s10_prepared["workload_events"]
        if event.get("job_id") == "s10-job-00009"
        and event.get("event_type") == "starting"
    )
    assert s10_start["submit_time_s"] == 13812.0
