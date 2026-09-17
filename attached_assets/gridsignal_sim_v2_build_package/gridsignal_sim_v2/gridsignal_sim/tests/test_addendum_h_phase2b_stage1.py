"""Addendum H Phase 2b-1 registration and evidence checks.

TC numbering continues from Addendum H Phase 2a at TC-137.
"""

from __future__ import annotations

import json
from pathlib import Path

from api.schemas import ScenarioSpec
from runtime.phase2b_reference import expand_phase2b_reference_spec


ROOT = Path(__file__).parents[1]
RESULTS = ROOT.parents[3] / "docs" / "addendum-h-phase2b-results"
SCENARIOS = ROOT / "config" / "scenarios"


def _expanded(scenario_id: str) -> dict:
    raw = json.loads((SCENARIOS / f"{scenario_id}.json").read_text())
    ScenarioSpec.model_validate(raw)
    return expand_phase2b_reference_spec(raw)


def test_tc137_phase2b_reference_registration_and_topology() -> None:
    for scenario_id, family, days in (
        ("scenario-h1-k8s-ray-24h", "h1", 1),
        ("scenario-h1-k8s-ray-7d", "h1", 7),
        ("scenario-h2-slurm-24h", "h2", 1),
        ("scenario-h2-slurm-7d", "h2", 7),
    ):
        spec = _expanded(scenario_id)
        assert spec["end_sim_time"] == days * 86400.0
        assert sum(
            turbine.get("initial_state", "offline") == "spinning"
            for turbine in spec["turbine_units"]
        ) == 2
        assert len(spec["turbine_units"]) == 4
        assert len(spec["bess_units"]) == 1
        assert spec["bess_units"][0]["rated_mw"] == 30.0
        schedulers = {cluster["scheduler_type"] for cluster in spec["kube_clusters"]}
        assert schedulers == ({"K8S", "RAY"} if family == "h1" else {"SLURM"})
        assert ("slurm_config" in spec) is (family == "h2")


def test_tc138_cluster_timing_and_unique_ids() -> None:
    for scenario_id, family in (
        ("scenario-h1-k8s-ray-24h", "h1"),
        ("scenario-h1-k8s-ray-7d", "h1"),
        ("scenario-h2-slurm-24h", "h2"),
        ("scenario-h2-slurm-7d", "h2"),
    ):
        spec = _expanded(scenario_id)
        events = spec["workload_events"]
        assert len({event["event_id"] for event in events}) == len(events)
        starts = sorted(
            event["timestamp"]
            for event in events
            if event["event_type"] == "starting"
        )
        assert starts
        if family == "h1":
            expected_local_starts = {
                hour * 3600.0 + phase
                for hour in (8, 10, 12, 14, 16, 18)
                for phase in (30.0, 920.0, 1850.0, 2700.0)
            }
            assert all(
                (timestamp % 86400.0) in expected_local_starts
                for timestamp in starts
            )
        else:
            expected_local_starts = {
                hour * 3600.0 + 310.0
                for hour in (8, 10, 12, 14, 16, 18)
            }
            assert all(
                (timestamp % 86400.0) in expected_local_starts
                for timestamp in starts
            )
        if family == "h2":
            jobs = spec["slurm_config"]["jobs"]
            assert len({job["job_id"] for job in jobs}) == len(jobs)


def test_tc139_replayed_compute_trace_is_identical_tick_by_tick() -> None:
    manifest = json.loads((RESULTS / "stage1_summary.json").read_text())
    assert len(manifest["scenarios"]) == 2
    for scenario in manifest["scenarios"]:
        assert scenario["identical_compute_trace"] is True
        assert scenario["max_compute_trace_diff_mw"] <= 1e-9
        for run in scenario["runs"].values():
            assert run["compute_description"] == "scheduler-shaped GPU workload demand"


def test_tc140_24h_energy_balance_closes() -> None:
    manifest = json.loads((RESULTS / "stage1_summary.json").read_text())
    for scenario in manifest["scenarios"]:
        for run in scenario["runs"].values():
            assert run["energy_balance"]["closure_status"] is True
            # D4 is retained as a separate routing diagnostic.  Energy closure
            # uses the authoritative physical supply/load ledger.
            assert (
                run["energy_balance"]["max_abs_physical_ledger_defect_mw"]
                <= 1e-3
            )


def test_tc141_24h_start_stop_reconciliation() -> None:
    manifest = json.loads((RESULTS / "stage1_summary.json").read_text())
    for scenario in manifest["scenarios"]:
        for run in scenario["runs"].values():
            assert run["start_count_reconciled"] is True
            assert run["constraints_valid"] is True