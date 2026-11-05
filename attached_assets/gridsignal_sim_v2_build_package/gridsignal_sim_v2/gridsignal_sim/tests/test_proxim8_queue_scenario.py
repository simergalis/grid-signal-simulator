import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from api.schemas import ScenarioSpec
from api.routes.scenarios import build_seeded_store
from core.physical_identity import PhysicalIdentityHasher
from mcp_server import server as server_module
from runtime.run_manager import TICK_INTERVAL_SIM_SECONDS
from runtime.scenario_factory import build_run_context_from_spec
from study_harness.executor import (
    PROXIM8_QUEUE_SCENARIO_ID,
    STUDY_CLASS_SCENARIO_JSON,
    study_class_for_scenario,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ID = PROXIM8_QUEUE_SCENARIO_ID
SCENARIO_PATH = PACKAGE_ROOT / "config" / "scenarios" / f"{SCENARIO_ID}.json"
ORIGINAL_SCENARIO_PATH = (
    PACKAGE_ROOT / "config" / "scenarios" / "proxim8-5mw-24h.json"
)
ORIGINAL_GENERATOR_PATH = (
    PACKAGE_ROOT.parents[3] / "tools" / "proxim8" / "generate_scenario.py"
)
ORIGINAL_TEST_PATH = PACKAGE_ROOT / "tests" / "test_proxim8_scenario.py"
SCENARIO_DIRECTORY = PACKAGE_ROOT / "config" / "scenarios"
PINNED_CLOCK = 1792454400.0
TICK_SECONDS = 5
EXPECTED_PHYSICAL_HASHES = {
    "proxim8-5mw-24h": (
        "747432cf23b3da38d773c24f805d9dbc150e33ea870e4440f1c4ab3e28b7ddb0"
    ),
    "S11_mit_supercloud_2021-08-11_bchydro": (
        "ea327a8d96a79de0160dc7519b6ff615b2863afe53c28224f649cb745a6bf189"
    ),
    "scenario-uneven-multisched-01": (
        "bb2327da8e4c68e621e0ad13ebfda0fd732f34bfb98c743256165b7f8bf3f488"
    ),
}


def _events_by_scheduler(raw: dict, scheduler: str, event_type: str) -> list[dict]:
    return [
        event
        for event in raw["workload_events"]
        if event.get("scheduler_type") == scheduler
        and event.get("event_type") == event_type
    ]


def _source_job_pairs(raw: dict, scheduler: str) -> dict[str, tuple[dict, float]]:
    ends = {
        event["job_id"]: float(event["timestamp"])
        for event in _events_by_scheduler(raw, scheduler, "job_end")
    }
    return {
        event["job_id"]: (
            event,
            ends[event["job_id"]] - float(event["timestamp"]),
        )
        for event in _events_by_scheduler(raw, scheduler, "starting")
    }


def test_queue_variant_is_separate_registered_and_preserves_source_jobs() -> None:
    raw = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    source = json.loads(ORIGINAL_SCENARIO_PATH.read_text(encoding="utf-8"))
    spec = ScenarioSpec.model_validate(raw)
    clusters = {cluster.scheduler_type: cluster for cluster in spec.kube_clusters}
    provenance = raw["provenance_proxim8_queue"]
    moved_jobs = {
        item["job_id"]: item for item in provenance["moved_jobs"]
    }

    assert spec.end_sim_time == 86400
    assert spec.grid_import_limit_mw == 5.0
    assert len(_events_by_scheduler(raw, "SLURM", "starting")) == 10
    assert set(clusters) == {"K8S", "RAY"}
    assert len(clusters["K8S"].scheduled_arrivals) == 1000
    assert len(clusters["RAY"].scheduled_arrivals) == 10000
    assert clusters["K8S"].grid_cap_admission_enabled is True
    assert clusters["RAY"].grid_cap_admission_enabled is True
    assert clusters["K8S"].arrival_mode == "scheduled"
    assert clusters["RAY"].arrival_mode == "scheduled"
    assert SCENARIO_ID in server_module.STUDY_SCENARIOS
    assert SCENARIO_ID in server_module.SCENARIO_IDS
    assert study_class_for_scenario(SCENARIO_ID) == STUDY_CLASS_SCENARIO_JSON
    assert build_seeded_store().get(SCENARIO_ID) is not None
    assert "DR-2026-11-03-PROXIM8-QUEUE" in spec.description
    assert "7,200 moved Ray calls" in spec.description
    assert provenance["decision_record"].startswith(
        "DR-2026-11-03-PROXIM8-QUEUE"
    )
    assert len(moved_jobs) == 7200
    assert provenance["moved_call_count"] == 7200
    targets = provenance["episode_targets"]
    assert all(
        target["arrival_start_local"] in spec.description
        for target in targets
    )
    assert len(targets) == 10
    assert len(
        provenance["uniform_timing_draw"]["target_durations_seconds"]
    ) == 10
    assert all(
        60 <= value <= 420
        for value in provenance["uniform_timing_draw"][
            "target_durations_seconds"
        ]
    )
    target_starts = [item["arrival_start_s"] for item in targets]
    assert all(9 * 3600 <= value < 18 * 3600 for value in target_starts)
    assert all(
        target_starts[index + 1] - target_starts[index] >= 1200
        for index in range(len(target_starts) - 1)
    )
    assert target_starts[-1] - target_starts[0] >= 6 * 3600
    assert len({
        target_starts[index + 1] - target_starts[index]
        for index in range(len(target_starts) - 1)
    }) > 1

    source_slurm = [
        event
        for event in source["workload_events"]
        if event.get("scheduler_type") == "SLURM"
    ]
    queue_slurm = [
        event
        for event in raw["workload_events"]
        if event.get("scheduler_type") == "SLURM"
    ]
    assert queue_slurm == source_slurm

    expected_moved_ids = {
        event["job_id"]
        for event in _events_by_scheduler(source, "RAY", "starting")
        if event["job_id"].startswith("ray-agentic-call-burst-")
    }
    assert set(moved_jobs) == expected_moved_ids
    for scheduler in ("K8S", "RAY"):
        expected = _source_job_pairs(source, scheduler)
        arrivals = {
            item.job_id: item
            for item in clusters[scheduler].scheduled_arrivals
        }
        assert set(arrivals) == set(expected)
        for job_id, (event, duration_s) in expected.items():
            actual = arrivals[job_id]
            original_time = float(event["timestamp"])
            assert actual.duration_s == duration_s
            assert actual.node_count == event["node_count"]
            assert actual.hardware_profile_id == event["hardware_profile_id"]
            if job_id in moved_jobs:
                moved = moved_jobs[job_id]
                assert moved["original_time_s"] == original_time
                assert moved["new_time_s"] == actual.arrival_time_s
                assert 9 * 3600 <= actual.arrival_time_s < 18 * 3600
            else:
                assert actual.arrival_time_s == original_time

    midnight_arrivals = [
        arrival
        for arrival in clusters["K8S"].scheduled_arrivals
        if arrival.job_id in {
            "k8s-inf-cohere-command-r-0005",
            "k8s-inf-mistral-large-2-0001",
            "k8s-inf-mixtral-8x22b-0002",
            "k8s-inf-mixtral-8x22b-0003",
            "k8s-inf-mixtral-8x22b-0004",
        }
    ]
    assert len(midnight_arrivals) == 5
    assert all(arrival.arrival_time_s == 0.0 for arrival in midnight_arrivals)

    # Byte-level guards for the original Proxim8 scenario, generator and test.
    assert hashlib.sha256(ORIGINAL_SCENARIO_PATH.read_bytes()).hexdigest() == (
        "34f46b58e92c83398bf73be5feb4db874e2e1cfc5f320f00cf2ed36f402b9ecc"
    )
    assert hashlib.sha256(ORIGINAL_GENERATOR_PATH.read_bytes()).hexdigest() == (
        "b95c0ba7dafa532a00847b3cc4dae88a9b5c66362a18d939e886d4a14043a4d3"
    )
    assert hashlib.sha256(ORIGINAL_TEST_PATH.read_bytes()).hexdigest() == (
        "dc8fb9c04534b4d0bd03f7181d9f03f353adfa2b295f6f96d42e906115f1c685"
    )


@pytest.fixture(scope="module")
def measured_queue_run() -> dict:
    raw = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    spec = ScenarioSpec.model_validate(raw)
    episodes = []
    current = None
    peak_demand_mw = 0.0
    peak_grid_import_mw = 0.0
    unserved_mwh = 0.0
    held_slurm = []
    held_job_ids = set()
    tick_rows = []

    with patch(
        "runtime.run_manager._time_module.time",
        return_value=PINNED_CLOCK,
    ):
        ctx = build_run_context_from_spec(
            "proxim8-5mw-24h-queue-test",
            spec.model_dump(mode="json"),
            run_seed=20261102,
        )
        for _ in range(int(spec.end_sim_time / TICK_SECONDS)):
            tick = ctx.step()
            metrics = tick.kube_metrics
            held = [
                job
                for job in metrics.pending_jobs
                if "-gridcap-retry-" in job.event_id
            ]
            peak_demand_mw = max(peak_demand_mw, tick.p_demand_mw)
            peak_grid_import_mw = max(
                peak_grid_import_mw,
                max(0.0, -tick.grid_exchange_mw),
            )
            unserved_mwh += tick.p_unserved_mw * TICK_SECONDS / 3600.0
            tick_rows.append({
                "sim_time_seconds": tick.sim_time_seconds,
                "p_demand_mw": tick.p_demand_mw,
                "requested_demand_mw": tick.requested_demand_mw,
                "grid_import_mw": max(0.0, -tick.grid_exchange_mw),
                "held_count": len(held),
            })

            if held:
                for job in held:
                    held_job_ids.add(
                        job.event_id.split("-gridcap-retry-")[0]
                    )
                    if job.scheduler_type == "SLURM":
                        held_slurm.append(job.event_id)
                if current is None:
                    current = {
                        "start_time_s": tick.sim_time_seconds,
                        "held_ticks": 0,
                        "peak_queue_depth": 0,
                        "max_wait_s": 0.0,
                        "job_ids": set(),
                        "schedulers": set(),
                    }
                current["held_ticks"] += 1
                current["peak_queue_depth"] = max(
                    current["peak_queue_depth"],
                    len(held),
                )
                current["max_wait_s"] = max(
                    current["max_wait_s"],
                    max(
                        tick.sim_time_seconds - job.queued_since_s
                        for job in held
                    ),
                )
                current["job_ids"].update(
                    job.event_id.split("-gridcap-retry-")[0]
                    for job in held
                )
                current["schedulers"].update(
                    job.scheduler_type for job in held
                )
            elif current is not None:
                current["duration_s"] = (
                    current["held_ticks"] * TICK_SECONDS
                )
                current["end_time_s"] = tick.sim_time_seconds
                current["job_ids"] = sorted(current["job_ids"])
                current["schedulers"] = sorted(current["schedulers"])
                episodes.append(current)
                current = None
        if current is not None:
            current["duration_s"] = current["held_ticks"] * TICK_SECONDS
            current["end_time_s"] = spec.end_sim_time
            current["job_ids"] = sorted(current["job_ids"])
            current["schedulers"] = sorted(current["schedulers"])
            episodes.append(current)

        arrivals_consumed = all(
            agent._scheduled_arrival_index == len(agent._scheduled_arrivals)
            for agent in ctx.sim_state.kube_agents
        )

    return {
        "raw": raw,
        "end_sim_time": spec.end_sim_time,
        "episodes": episodes,
        "ticks": tick_rows,
        "peak_demand_mw": peak_demand_mw,
        "peak_grid_import_mw": peak_grid_import_mw,
        "unserved_mwh": unserved_mwh,
        "held_slurm": held_slurm,
        "held_job_ids": held_job_ids,
        "arrivals_consumed": arrivals_consumed,
    }


def test_queue_variant_has_ten_measured_cap_hold_episodes(
    measured_queue_run: dict,
) -> None:
    raw = measured_queue_run["raw"]
    episodes = measured_queue_run["episodes"]
    assert len(episodes) == 10, episodes
    assert all(60 <= episode["duration_s"] <= 420 for episode in episodes)
    assert all(episode["peak_queue_depth"] >= 5 for episode in episodes)
    assert all(episode["schedulers"] == ["RAY"] for episode in episodes)
    assert all(
        episodes[index + 1]["start_time_s"]
        - episodes[index]["start_time_s"] >= 1200
        for index in range(len(episodes) - 1)
    )
    assert episodes[-1]["start_time_s"] - episodes[0]["start_time_s"] >= 6 * 3600
    target_durations = raw["provenance_proxim8_queue"]["uniform_timing_draw"][
        "target_durations_seconds"
    ]
    targets = raw["provenance_proxim8_queue"]["episode_targets"]
    assert [target["target_duration_s"] for target in targets] == target_durations
    for episode, target in zip(episodes, targets):
        assert (
            target["arrival_start_s"]
            <= episode["start_time_s"]
            <= target["arrival_start_s"] + 120
        )
        episode["target_duration_s"] = target["target_duration_s"]
    assert all(
        episodes[index]["end_time_s"]
        < episodes[index + 1]["start_time_s"]
        for index in range(len(episodes) - 1)
    )
    for episode in episodes:
        assert episode["end_time_s"] <= measured_queue_run["end_sim_time"]
    assert measured_queue_run["held_slurm"] == []
    ray_job_ids = {
        arrival.job_id
        for cluster in ScenarioSpec.model_validate(
            json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
        ).kube_clusters
        if cluster.scheduler_type == "RAY"
        for arrival in cluster.scheduled_arrivals
    }
    assert measured_queue_run["held_job_ids"]
    assert measured_queue_run["held_job_ids"] <= ray_job_ids
    assert measured_queue_run["peak_grid_import_mw"] <= 5.0 + 1e-6
    assert measured_queue_run["unserved_mwh"] >= 0.0
    assert measured_queue_run["arrivals_consumed"]


def test_requested_demand_tracks_cap_held_jobs(
    measured_queue_run: dict,
) -> None:
    ticks = measured_queue_run["ticks"]
    assert ticks
    assert all(row["requested_demand_mw"] is not None for row in ticks)
    assert all(
        row["requested_demand_mw"] + 1e-6 >= row["p_demand_mw"]
        for row in ticks
    )
    assert all(row["p_demand_mw"] <= 5.0 + 1e-6 for row in ticks)
    assert all(row["grid_import_mw"] <= 5.0 + 1e-6 for row in ticks)
    episodes = measured_queue_run["episodes"]
    for episode in episodes:
        episode_rows = [
            row
            for row in ticks
            if episode["start_time_s"]
            <= row["sim_time_seconds"]
            < episode["end_time_s"]
        ]
        assert episode_rows
        assert any(row["requested_demand_mw"] > 5.0 for row in episode_rows), episode
    assert all(
        row["requested_demand_mw"] <= 5.0 + 1e-6
        for row in ticks
        if not any(
            episode["start_time_s"]
            <= row["sim_time_seconds"]
            < episode["end_time_s"]
            for episode in episodes
        )
    )
    assert all(
        abs(row["requested_demand_mw"] - row["p_demand_mw"]) <= 1e-9
        for row in ticks
        if row["held_count"] == 0
    )


def test_requested_demand_is_absent_for_original_proxim8() -> None:
    raw = json.loads(ORIGINAL_SCENARIO_PATH.read_text(encoding="utf-8"))
    spec = ScenarioSpec.model_validate(raw)
    with patch(
        "runtime.run_manager._time_module.time",
        return_value=PINNED_CLOCK,
    ):
        ctx = build_run_context_from_spec(
            "proxim8-5mw-24h-no-cap-admission-test",
            spec.model_dump(mode="json"),
            run_seed=20261102,
        )
        tick = ctx.step()
    assert tick.requested_demand_mw is None
    from runtime.run_manager import _tick_result_to_dict

    assert "requested_demand_mw" not in _tick_result_to_dict(tick)


def test_slow_non_regression_hashes_for_unmodified_scenarios() -> None:
    for scenario_id, expected_hash in EXPECTED_PHYSICAL_HASHES.items():
        raw = json.loads(
            (SCENARIO_DIRECTORY / f"{scenario_id}.json").read_text(
                encoding="utf-8"
            )
        )
        spec = ScenarioSpec.model_validate(raw)
        hasher = PhysicalIdentityHasher()
        with patch(
            "runtime.run_manager._time_module.time",
            return_value=PINNED_CLOCK,
        ):
            ctx = build_run_context_from_spec(
                f"queue-pre-{scenario_id}",
                spec.model_dump(mode="json"),
                run_seed=1729,
            )
            for _ in range(int(spec.end_sim_time / TICK_SECONDS)):
                hasher.update(ctx.step())
        assert hasher.hexdigest() == expected_hash, scenario_id
