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
        "b993ff13ec6607e7cee6839f9b761d61a95eecf267c888ced8f233cf03415775"
    ),
    "test_proxim8_queue_scenario.py": (
        "3257909adc7e53560e6cd716799359dd628e9efa3d31982d333b44c684713944"
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
    source = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    spec = ScenarioSpec.model_validate(raw)
    clusters = {cluster.scheduler_type: cluster for cluster in spec.kube_clusters}
    provenance = raw["provenance_proxim8_queue_early"]
    moved_k8s = {item["job_id"]: item for item in provenance["moved_k8s_jobs"]}
    moved_ray = {item["job_id"]: item for item in provenance["moved_ray_calls"]}

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
    assert "DR-2026-11-03-PROXIM8-QUEUE" in spec.description
    assert "00:15" in spec.description and "hourly through 09:15" in spec.description
    assert provenance["seed"] == SEED
    assert provenance["k8s_counts_by_wave"] == [
        130, 120, 100, 110, 110, 89, 89, 79, 89, 79
    ]
    assert provenance["k8s_moved_count"] == 995
    assert provenance["ray_moved_count"] == 7200
    assert provenance["moved_job_count"] == 8195
    assert len(moved_k8s) == 995
    assert len(moved_ray) == 7200
    assert len(provenance["wave_start_times_s"]) == 10

    source_slurm = [
        event for event in source["workload_events"]
        if event.get("scheduler_type") == "SLURM"
    ]
    actual_slurm = [
        event for event in raw["workload_events"]
        if event.get("scheduler_type") == "SLURM"
    ]
    assert actual_slurm == source_slurm

    wave_starts = provenance["wave_start_times_s"]
    assert wave_starts == [900 + index * 3600 for index in range(10)]
    for scheduler, moved in (("K8S", moved_k8s), ("RAY", moved_ray)):
        expected = _source_pairs(source, scheduler)
        arrivals = {
            item.job_id: item for item in clusters[scheduler].scheduled_arrivals
        }
        assert set(arrivals) == set(expected)
        for job_id, (event, duration_s) in expected.items():
            actual = arrivals[job_id]
            original_time = float(event["timestamp"])
            assert actual.duration_s == duration_s
            assert actual.node_count == event["node_count"]
            assert actual.hardware_profile_id == event["hardware_profile_id"]
            if job_id in moved:
                move = moved[job_id]
                assert move["original_time_s"] == original_time
                assert move["new_time_s"] == actual.arrival_time_s
            else:
                assert actual.arrival_time_s == original_time

    midnight_ids = {
        event["job_id"]
        for event in _source_events(source, "K8S", "starting")
        if float(event["timestamp"]) == 0.0
    }
    assert len(midnight_ids) == 5
    assert all(
        next(arrival for arrival in clusters["K8S"].scheduled_arrivals
             if arrival.job_id == job_id).arrival_time_s == 0.0
        for job_id in midnight_ids
    )

    # The original queue-stress scenario must remain at its b28dcc4 bytes.
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
    assert all(episode["peak_queue_depth"] >= 5 for episode in episodes)
    assert all(episode["schedulers"] == ["RAY"] for episode in episodes)
    assert all(
        episodes[index + 1]["start_time_s"]
        - episodes[index]["start_time_s"] >= 3600
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


def test_early_variant_does_not_change_source_proxim8() -> None:
    source = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    assert len(_source_events(source, "SLURM", "starting")) == 10
    assert len(_source_events(source, "K8S", "starting")) == 1000
    assert len(_source_events(source, "RAY", "starting")) == 10000
    assert hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest() == (
        EXPECTED_SOURCE_HASHES["proxim8-5mw-24h.json"]
    )
