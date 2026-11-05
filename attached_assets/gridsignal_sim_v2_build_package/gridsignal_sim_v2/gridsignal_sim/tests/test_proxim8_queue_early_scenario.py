import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from api.routes.scenarios import build_seeded_store
from api.schemas import ScenarioSpec
from core.physical_identity import PhysicalIdentityHasher
from mcp_server import server as server_module
from runtime.run_manager import TICK_INTERVAL_SIM_SECONDS
from runtime.scenario_factory import build_run_context_from_spec
from study_harness.executor import (
    PROXIM8_QUEUE_EARLY_SCENARIO_ID,
    STUDY_CLASS_SCENARIO_JSON,
    study_class_for_scenario,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ID = PROXIM8_QUEUE_EARLY_SCENARIO_ID
SCENARIO_PATH = PACKAGE_ROOT / "config" / "scenarios" / f"{SCENARIO_ID}.json"
SOURCE_PATH = PACKAGE_ROOT / "config" / "scenarios" / "proxim8-5mw-24h.json"
SOURCE_GENERATOR_PATH = (
    PACKAGE_ROOT.parents[3] / "tools" / "proxim8" / "generate_scenario.py"
)
SOURCE_TEST_PATH = PACKAGE_ROOT / "tests" / "test_proxim8_scenario.py"
OLD_QUEUE_PATH = (
    PACKAGE_ROOT / "config" / "scenarios" / "proxim8-5mw-24h-queue.json"
)
OLD_QUEUE_TEST_PATH = PACKAGE_ROOT / "tests" / "test_proxim8_queue_scenario.py"
BUSINESS_QUEUE_PATH = OLD_QUEUE_PATH
DAY_SECONDS = 86400
ROTATION_SECONDS = 9 * 3600
PINNED_CLOCK = 1792454400.0
SEED = 20261102
TICK_SECONDS = TICK_INTERVAL_SIM_SECONDS
EXPECTED_SOURCE_HASHES = {
    "proxim8-5mw-24h.json": (
        "34f46b58e92c83398bf73be5feb4db874e2e1cfc5f320f00cf2ed36f402b9ecc"
    ),
    "generate_scenario.py": (
        "b95c0ba7dafa532a00847b3cc4dae88a9b5c66362a18d939e886d4a14043a4d3"
    ),
    "test_proxim8_scenario.py": (
        "dc8fb9c04534b4d0bd03f7181d9f03f353adfa2b295f6f96d42e906115f1c685"
    ),
    "proxim8-5mw-24h-queue.json": (
        "436e5e555ee2d6671be2562463a935466832ad256935486b913bffd4ca67d9ed"
    ),
    "test_proxim8_queue_scenario.py": (
        "a1e535b03e5872b4c736a30843b63680b4e5afaa4624ed0c51b5ae34656e1273"
    ),
}


def _source_events(raw: dict, scheduler: str, event_type: str) -> list[dict]:
    return [
        event
        for event in raw["workload_events"]
        if event.get("scheduler_type") == scheduler
        and event.get("event_type") == event_type
    ]


def _source_pairs(raw: dict, scheduler: str) -> dict[str, tuple[dict, float]]:
    ends = {
        event["job_id"]: float(event["timestamp"])
        for event in _source_events(raw, scheduler, "job_end")
    }
    return {
        event["job_id"]: (
            event,
            ends[event["job_id"]] - float(event["timestamp"]),
        )
        for event in _source_events(raw, scheduler, "starting")
    }


def _scheduled_arrivals(raw: dict, scheduler: str) -> dict[str, dict]:
    return {
        arrival["job_id"]: arrival
        for cluster in raw["kube_clusters"]
        if cluster.get("scheduler_type") == scheduler
        for arrival in cluster["scheduled_arrivals"]
    }


def _rotated_time(timestamp_s: float) -> float:
    return float((float(timestamp_s) - ROTATION_SECONDS) % DAY_SECONDS)


def _is_cap_held(job) -> bool:
    return "-gridcap-retry-" in job.event_id


def _measure_run() -> dict:
    raw = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    spec = ScenarioSpec.model_validate(raw)
    episodes = []
    current = None
    ticks = []
    peak_demand_mw = 0.0
    peak_requested_demand_mw = 0.0
    peak_grid_import_mw = 0.0
    unserved_mwh = 0.0
    min_soc_fraction = 1.0
    end_soc_fraction = 0.0
    held_slurm = []
    held_job_ids = set()

    with patch(
        "runtime.run_manager._time_module.time",
        return_value=PINNED_CLOCK,
    ):
        ctx = build_run_context_from_spec(
            "proxim8-5mw-24h-queue-early-test",
            spec.model_dump(mode="json"),
            run_seed=SEED,
        )
        for _ in range(int(spec.end_sim_time / TICK_SECONDS)):
            tick = ctx.step()
            metrics = tick.kube_metrics
            held = [
                job for job in (metrics.pending_jobs if metrics else [])
                if _is_cap_held(job)
            ]
            demand_mw = float(tick.p_demand_mw)
            requested_mw = (
                float(tick.requested_demand_mw)
                if tick.requested_demand_mw is not None
                else demand_mw
            )
            grid_import_mw = max(0.0, -float(tick.grid_exchange_mw))
            peak_demand_mw = max(peak_demand_mw, demand_mw)
            peak_requested_demand_mw = max(
                peak_requested_demand_mw, requested_mw
            )
            peak_grid_import_mw = max(peak_grid_import_mw, grid_import_mw)
            unserved_mwh += float(tick.p_unserved_mw) * TICK_SECONDS / 3600.0
            min_soc_fraction = min(
                min_soc_fraction, float(tick.bess_soc_fraction)
            )
            end_soc_fraction = float(tick.bess_soc_fraction)

            ticks.append({
                "time_s": float(tick.sim_time_seconds),
                "demand_mw": demand_mw,
                "requested_mw": requested_mw,
                "grid_import_mw": grid_import_mw,
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
                        "start_time_s": float(tick.sim_time_seconds),
                        "held_ticks": 0,
                        "peak_queue_depth": 0,
                        "max_wait_s": 0.0,
                        "peak_requested_demand_mw": 0.0,
                        "peak_drawn_demand_mw": 0.0,
                        "job_ids": set(),
                        "schedulers": set(),
                    }
                current["held_ticks"] += 1
                current["peak_queue_depth"] = max(
                    current["peak_queue_depth"], len(held)
                )
                current["max_wait_s"] = max(
                    current["max_wait_s"],
                    max(
                        float(tick.sim_time_seconds) - float(job.queued_since_s)
                        for job in held
                    ),
                )
                current["peak_requested_demand_mw"] = max(
                    current["peak_requested_demand_mw"], requested_mw
                )
                current["peak_drawn_demand_mw"] = max(
                    current["peak_drawn_demand_mw"], demand_mw
                )
                current["job_ids"].update(
                    job.event_id.split("-gridcap-retry-")[0]
                    for job in held
                )
                current["schedulers"].update(
                    job.scheduler_type for job in held
                )
            elif current is not None:
                current["duration_s"] = current["held_ticks"] * TICK_SECONDS
                current["end_time_s"] = float(tick.sim_time_seconds)
                current["job_ids"] = sorted(current["job_ids"])
                current["schedulers"] = sorted(current["schedulers"])
                episodes.append(current)
                current = None

        if current is not None:
            current["duration_s"] = current["held_ticks"] * TICK_SECONDS
            current["end_time_s"] = float(spec.end_sim_time)
            current["job_ids"] = sorted(current["job_ids"])
            current["schedulers"] = sorted(current["schedulers"])
            episodes.append(current)

        arrivals_consumed = all(
            agent._scheduled_arrival_index == len(agent._scheduled_arrivals)
            for agent in ctx.sim_state.kube_agents
        )

    return {
        "raw": raw,
        "spec": spec,
        "episodes": episodes,
        "ticks": ticks,
        "peak_demand_mw": peak_demand_mw,
        "peak_requested_demand_mw": peak_requested_demand_mw,
        "peak_grid_import_mw": peak_grid_import_mw,
        "unserved_mwh": unserved_mwh,
        "min_soc_fraction": min_soc_fraction,
        "end_soc_fraction": end_soc_fraction,
        "held_slurm": held_slurm,
        "held_job_ids": held_job_ids,
        "arrivals_consumed": arrivals_consumed,
    }


def test_queue_early_is_registered_and_preserves_source_jobs() -> None:
    raw = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    original = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    source = json.loads(BUSINESS_QUEUE_PATH.read_text(encoding="utf-8"))
    spec = ScenarioSpec.model_validate(raw)
    clusters = {cluster.scheduler_type: cluster for cluster in spec.kube_clusters}
    provenance = raw["provenance_proxim8_queue_early"]
    moved_k8s = {
        item["job_id"]: item for item in provenance["k8s_rotated_arrivals"]
    }
    moved_ray = {item["job_id"]: item for item in provenance["moved_ray_calls"]}
    rotated_background = {
        item["job_id"]: item
        for item in provenance["ray_background_rotation"]["rotated_calls"]
    }

    assert spec.end_sim_time == 86400
    assert spec.grid_import_limit_mw == 5.0
    assert len(_source_events(raw, "SLURM", "starting")) == 10
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
    assert "DR-2026-11-05-PROXIM8-EARLY-0900" in spec.description
    assert "session starts at local 09:00" in spec.description
    assert "offset from local time by nine hours" in spec.description
    assert provenance["seed"] == SEED
    assert len(moved_k8s) == 1000
    assert provenance["k8s_rotated_count"] == 1000
    assert provenance["ray_wave_call_count"] == 7200
    assert len(moved_ray) == 7200
    assert len(rotated_background) == 2800
    assert provenance["moved_job_count"] == 11010
    assert len(provenance["wave_start_times_sim_seconds"]) == 10

    source_slurm = [
        event for event in source["workload_events"]
        if event.get("scheduler_type") == "SLURM"
    ]
    actual_slurm = [
        event for event in raw["workload_events"]
        if event.get("scheduler_type") == "SLURM"
    ]
    source_starts = {
        event["job_id"]: event
        for event in source_slurm
        if event["event_type"] == "starting"
    }
    actual_starts = {
        event["job_id"]: event
        for event in actual_slurm
        if event["event_type"] == "starting"
    }
    assert set(actual_starts) == set(source_starts)
    assert all(
        actual_starts[job_id]["timestamp"] == _rotated_time(event["timestamp"])
        for job_id, event in source_starts.items()
    )
    source_ends = {
        event["job_id"]: event
        for event in source_slurm
        if event["event_type"] == "job_end"
    }
    actual_ends = {
        event["job_id"]: event
        for event in actual_slurm
        if event["event_type"] == "job_end"
    }
    for job_id, event in source_ends.items():
        expected_end = _rotated_time(event["timestamp"])
        expected_start = _rotated_time(source_starts[job_id]["timestamp"])
        if expected_end <= expected_start:
            expected_end += DAY_SECONDS
        if expected_end >= DAY_SECONDS:
            assert job_id not in actual_ends
        else:
            assert actual_ends[job_id]["timestamp"] == expected_end

    wave_starts = provenance["wave_start_times_sim_seconds"]
    assert wave_starts == [900 + index * 3600 for index in range(10)]
    assert provenance["wave_start_times_local"] == [
        f"{hour:02d}:15" for hour in range(9, 19)
    ]
    expected_k8s = _scheduled_arrivals(source, "K8S")
    expected_ray = _scheduled_arrivals(source, "RAY")
    for scheduler, expected, moved in (
        ("K8S", expected_k8s, moved_k8s),
        ("RAY", expected_ray, {**moved_ray, **rotated_background}),
    ):
        arrivals = {
            item.job_id: item for item in clusters[scheduler].scheduled_arrivals
        }
        assert set(arrivals) == set(expected)
        for job_id, event in expected.items():
            actual = arrivals[job_id]
            original_time = float(event["arrival_time_s"])
            assert actual.duration_s == event["duration_s"]
            assert actual.node_count == event["node_count"]
            assert actual.hardware_profile_id == event["hardware_profile_id"]
            move = moved[job_id]
            assert move["original_time_s"] == original_time
            assert move["new_time_s"] == actual.arrival_time_s
            if scheduler == "K8S" or job_id in rotated_background:
                assert actual.arrival_time_s == _rotated_time(original_time)

    carryover_ids = {
        job_id for job_id, event in expected_k8s.items()
        if float(event["arrival_time_s"]) == 0.0
    }
    assert len(carryover_ids) == 5
    assert all(
        clusters["K8S"].scheduled_arrivals[
            next(
                index
                for index, arrival in enumerate(clusters["K8S"].scheduled_arrivals)
                if arrival.job_id == job_id
            )
        ].arrival_time_s == 15 * 3600
        for job_id in carryover_ids
    )

    # Original Proxim8 files and the business-day scenario remain unchanged.
    for path, expected_name in (
        (SOURCE_PATH, "proxim8-5mw-24h.json"),
        (SOURCE_GENERATOR_PATH, "generate_scenario.py"),
        (SOURCE_TEST_PATH, "test_proxim8_scenario.py"),
        (OLD_QUEUE_PATH, "proxim8-5mw-24h-queue.json"),
        (OLD_QUEUE_TEST_PATH, "test_proxim8_queue_scenario.py"),
    ):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == (
            EXPECTED_SOURCE_HASHES[expected_name]
        )


@pytest.fixture(scope="module")
def measured_queue_early_run() -> dict:
    return _measure_run()


def test_queue_early_has_ten_measured_held_episodes(
    measured_queue_early_run: dict,
) -> None:
    result = measured_queue_early_run
    episodes = result["episodes"]
    assert len(episodes) == 10, episodes
    assert all(60 <= episode["duration_s"] <= 420 for episode in episodes)
    durations = {episode["duration_s"] for episode in episodes}
    assert len(durations) >= 6, durations
    assert min(durations) <= 120
    assert max(durations) >= 300
    assert all(episode["peak_queue_depth"] >= 5 for episode in episodes)
    assert all(episode["schedulers"] == ["RAY"] for episode in episodes)
    assert 15 * 60 <= episodes[0]["start_time_s"] <= 20 * 60
    assert episodes[-1]["start_time_s"] - episodes[0]["start_time_s"] >= 8 * 3600
    assert all(
        3540
        <= episodes[index + 1]["start_time_s"]
        - episodes[index]["start_time_s"]
        <= 3660
        for index in range(len(episodes) - 1)
    )
    assert all(
        episodes[index]["end_time_s"] < episodes[index + 1]["start_time_s"]
        for index in range(len(episodes) - 1)
    )
    assert all(
        episode["peak_requested_demand_mw"] > 5.0
        for episode in episodes
    )
    assert all(episode["peak_drawn_demand_mw"] <= 5.0 + 1e-6 for episode in episodes)
    assert result["held_slurm"] == []
    assert result["held_job_ids"]
    assert result["peak_demand_mw"] <= 5.0 + 1e-6
    assert result["peak_grid_import_mw"] <= 5.0 + 1e-6
    assert result["unserved_mwh"] == pytest.approx(0.0, abs=1e-9)
    assert result["arrivals_consumed"]
    assert all(
        row["requested_mw"] + 1e-6 >= row["demand_mw"]
        for row in result["ticks"]
    )
    for episode in episodes:
        episode_ticks = [
            row for row in result["ticks"]
            if episode["start_time_s"] <= row["time_s"] < episode["end_time_s"]
        ]
        assert any(row["requested_mw"] > 5.0 for row in episode_ticks), episode
    assert all(
        row["requested_mw"] <= 5.0 + 1e-6
        for row in result["ticks"]
        if not any(
            episode["start_time_s"] <= row["time_s"] < episode["end_time_s"]
            for episode in episodes
        )
    )


def test_early_variant_does_not_change_source_proxim8() -> None:
    source = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    assert len(_source_events(source, "SLURM", "starting")) == 10
    assert len(_source_events(source, "K8S", "starting")) == 1000
    assert len(_source_events(source, "RAY", "starting")) == 10000
    assert hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest() == (
        EXPECTED_SOURCE_HASHES["proxim8-5mw-24h.json"]
    )
