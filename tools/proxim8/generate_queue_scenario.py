#!/usr/bin/env python3
"""Generate the opt-in Proxim8 queue-stress variant from original arrivals."""

from __future__ import annotations

import json
import random
from copy import deepcopy
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = (
    REPO_ROOT
    / "attached_assets"
    / "gridsignal_sim_v2_build_package"
    / "gridsignal_sim_v2"
    / "gridsignal_sim"
)
SOURCE_PATH = PACKAGE_ROOT / "config" / "scenarios" / "proxim8-5mw-24h.json"
OUTPUT_PATH = (
    PACKAGE_ROOT / "config" / "scenarios" / "proxim8-5mw-24h-queue.json"
)

# Each numeric assumption is named and carries its PROPOSED_HERE rationale.
N = {
    "SEED": 20261102,  # PROPOSED_HERE: fixed Proxim8 workload seed.
    "ZERO": 0,  # PROPOSED_HERE: first item/index and zero-based day origin.
    "ONE": 1,  # PROPOSED_HERE: index increment and positive arrival count.
    "FIVE": 5,  # PROPOSED_HERE: simulator tick and 5-second alignment.
    "TEN": 10,  # PROPOSED_HERE: required queue episodes and Ray cohorts.
    "K8S_SESSIONS": 1000,  # PROPOSED_HERE: preserve the Proxim8 inference count.
    "RAY_CALLS": 10000,  # PROPOSED_HERE: preserve the Proxim8 agentic-call count.
    "SLURM_JOBS": 10,  # PROPOSED_HERE: preserve the Proxim8 training-job count.
    "RAY_SURGE_CALLS": 7200,  # PROPOSED_HERE: original 16:35 Ray-chain cohort to reschedule.
    "MIN_DRAW_SECONDS": 60,  # PROPOSED_HERE: one-minute uniform draw lower bound.
    "MAX_DRAW_SECONDS": 420,  # PROPOSED_HERE: seven-minute uniform draw upper bound.
    "MAX_SHIFT_SECONDS": 1800,  # PROPOSED_HERE: approved thirty-minute movement limit.
    "MIN_SURGE_START_INTERVAL_SECONDS": 360,  # PROPOSED_HERE: six minutes separates 90-second waves; prior measured holds maxed at 355 seconds.
    "DURATION_TO_SPACING_DIVISOR": 45,  # PROPOSED_HERE: uniform timing draw adds at most 5 seconds to each six-minute start interval.
    "SURGE_START_HOUR": 16,  # PROPOSED_HERE: afternoon business-day surge window.
    "SURGE_START_MINUTE": 5,  # PROPOSED_HERE: earliest surge start is exactly at the approved 30-minute movement limit.
    "SURGE_START_SECOND": 0,  # PROPOSED_HERE: aligns target arrivals to the simulator's 5-second tick.
    "SECONDS_PER_MINUTE": 60,  # PROPOSED_HERE: time conversion.
    "SECONDS_PER_HOUR": 3600,  # PROPOSED_HERE: time conversion.
    "SECONDS_PER_DAY": 86400,  # PROPOSED_HERE: Proxim8's 24-hour horizon.
    "K8S_AGENT_MAX_NODES": 1900,  # PROPOSED_HERE: keep cluster capacity above the source workload so grid-cap admission is the tested queue.
    "JSON_INDENT": 2,  # PROPOSED_HERE: match scenario JSON formatting.
}

SCENARIO_ID = "proxim8-5mw-24h-queue"
RAY_SURGE_PREFIX = "ray-agentic-call-burst-"
DECISION_RECORD = "DR-2026-11-03-PROXIM8-QUEUE (PROPOSED_HERE)"
SURGE_METHOD = (
    "Ten source-derived Ray cohorts are rescheduled into the afternoon. "
    "The fixed seed draws a uniform 60–420 second timing value for each "
    "cohort; each draw adjusts the spacing to the next cohort. The actual "
    "cap-held duration is measured from admission telemetry, not assumed "
    "to equal the draw. All 7,200 moved jobs retain their IDs, durations, "
    "node counts, profiles and model names, and each moves no more than "
    "30 minutes."
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _start_events(scenario: dict, scheduler: str) -> list[dict]:
    return [
        event
        for event in scenario["workload_events"]
        if event.get("event_type") == "starting"
        and event.get("scheduler_type") == scheduler
    ]


def _end_times(scenario: dict) -> dict[tuple[str, str], float]:
    return {
        (event["scheduler_type"], event["job_id"]): float(event["timestamp"])
        for event in scenario["workload_events"]
        if event.get("event_type") == "job_end"
    }


def _scheduled_arrival(event: dict, end_times: dict, arrival_s: float) -> dict:
    return {
        "job_id": event["job_id"],
        "arrival_time_s": float(arrival_s),
        "duration_s": float(
            end_times[(event["scheduler_type"], event["job_id"])]
            - float(event["timestamp"])
        ),
        "node_count": int(event["node_count"]),
        "hardware_profile_id": event["hardware_profile_id"],
    }


def _wave_spacing(duration_draw_s: int) -> int:
    extra_s = (
        (duration_draw_s - N["MIN_DRAW_SECONDS"])
        // N["DURATION_TO_SPACING_DIVISOR"]
    )
    extra_s = (extra_s // N["FIVE"]) * N["FIVE"]
    return N["MIN_SURGE_START_INTERVAL_SECONDS"] + extra_s


def build_scenario(source: dict, template: dict) -> dict:
    end_times = _end_times(source)
    slurm_starts = _start_events(source, "SLURM")
    k8s_starts = _start_events(source, "K8S")
    ray_starts = _start_events(source, "RAY")
    ray_surge = sorted(
        (
            event
            for event in ray_starts
            if event["job_id"].startswith(RAY_SURGE_PREFIX)
        ),
        key=lambda event: (float(event["timestamp"]), event["job_id"]),
    )
    if len(slurm_starts) != N["SLURM_JOBS"]:
        raise ValueError(f"expected {N['SLURM_JOBS']} Slurm jobs")
    if len(k8s_starts) != N["K8S_SESSIONS"]:
        raise ValueError(f"expected {N['K8S_SESSIONS']} K8S sessions")
    if len(ray_starts) != N["RAY_CALLS"]:
        raise ValueError(f"expected {N['RAY_CALLS']} Ray calls")
    if len(ray_surge) != N["RAY_SURGE_CALLS"]:
        raise ValueError(
            f"expected {N['RAY_SURGE_CALLS']} original afternoon Ray calls"
        )
    if N["SECONDS_PER_DAY"] != source["end_sim_time"]:
        raise ValueError("source scenario horizon changed unexpectedly")

    rng = random.Random(N["SEED"])
    duration_draws_s = [
        rng.randrange(
            N["MIN_DRAW_SECONDS"],
            N["MAX_DRAW_SECONDS"] + N["FIVE"],
            N["FIVE"],
        )
        for _ in range(N["TEN"])
    ]
    calls_per_wave, remainder = divmod(len(ray_surge), N["TEN"])
    if remainder:
        raise ValueError("Ray surge cohort cannot be divided evenly")

    first_start_s = (
        N["SURGE_START_HOUR"] * N["SECONDS_PER_HOUR"]
        + N["SURGE_START_MINUTE"] * N["SECONDS_PER_MINUTE"]
        + N["SURGE_START_SECOND"]
    )
    target_start_s = first_start_s
    ray_arrivals: list[dict] = []
    moved_jobs: list[dict] = []
    intended_windows: list[dict] = []

    for wave_index in range(N["TEN"]):
        group = ray_surge[
            wave_index * calls_per_wave : (wave_index + N["ONE"]) * calls_per_wave
        ]
        source_start_s = min(float(event["timestamp"]) for event in group)
        wave_arrival_s = []
        for event in group:
            original_s = float(event["timestamp"])
            arrival_s = target_start_s + original_s - source_start_s
            shift_s = abs(arrival_s - original_s)
            if shift_s > N["MAX_SHIFT_SECONDS"]:
                raise ValueError(
                    f"{event['job_id']} shifts {shift_s}s, above the limit"
                )
            ray_arrivals.append(_scheduled_arrival(event, end_times, arrival_s))
            moved_jobs.append(
                {
                    "job_id": event["job_id"],
                    "original_time_s": original_s,
                    "new_time_s": arrival_s,
                }
            )
            wave_arrival_s.append(arrival_s)

        duration_draw_s = duration_draws_s[wave_index]
        spacing_s = _wave_spacing(duration_draw_s)
        intended_windows.append(
            {
                "wave": wave_index + N["ONE"],
                "start_time_s": min(wave_arrival_s),
                "arrival_span_s": max(wave_arrival_s) - min(wave_arrival_s),
                "timing_draw_s": duration_draw_s,
                "spacing_to_next_wave_s": spacing_s,
                "jobs": calls_per_wave,
            }
        )
        target_start_s += spacing_s

    moved_ids = {item["job_id"] for item in moved_jobs}
    for event in ray_starts:
        if event["job_id"] not in moved_ids:
            ray_arrivals.append(
                _scheduled_arrival(
                    event, end_times, float(event["timestamp"])
                )
            )
    k8s_arrivals = [
        _scheduled_arrival(event, end_times, float(event["timestamp"]))
        for event in k8s_starts
    ]

    clusters = deepcopy(template["kube_clusters"])
    by_scheduler = {"K8S": k8s_arrivals, "RAY": ray_arrivals}
    for cluster in clusters:
        scheduler = cluster["scheduler_type"]
        cluster["scheduled_arrivals"] = sorted(
            by_scheduler[scheduler],
            key=lambda arrival: (
                arrival["arrival_time_s"],
                arrival["job_id"],
            ),
        )
        if scheduler == "K8S":
            cluster["max_nodes"] = N["K8S_AGENT_MAX_NODES"]

    scenario = deepcopy(template)
    scenario["name"] = SCENARIO_ID
    scenario["description"] = (
        source["description"]
        + "\n\nQueue-stress variant. "
        + SURGE_METHOD
        + f" Seed {N['SEED']}; {len(moved_jobs):,} moved jobs. "
        + f"{DECISION_RECORD}."
    )
    scenario["workload_events"] = [
        event
        for event in source["workload_events"]
        if event.get("scheduler_type") == "SLURM"
    ]
    scenario["kube_clusters"] = clusters
    scenario["provenance_proxim8_queue"] = {
        "seed": N["SEED"],
        "decision_record": DECISION_RECORD,
        "surge_method": SURGE_METHOD,
        "uniform_timing_draw": {
            "minimum_seconds": N["MIN_DRAW_SECONDS"],
            "maximum_seconds": N["MAX_DRAW_SECONDS"],
            "step_seconds": N["FIVE"],
            "draws_seconds": duration_draws_s,
            "use": "selects spacing to the next Ray cohort",
        },
        "max_allowed_shift_seconds": N["MAX_SHIFT_SECONDS"],
        "moved_job_count": len(moved_jobs),
        "maximum_observed_shift_seconds": max(
            abs(item["new_time_s"] - item["original_time_s"])
            for item in moved_jobs
        ),
        "intended_windows": intended_windows,
        "moved_jobs": sorted(moved_jobs, key=lambda item: item["job_id"]),
        "proposed_here": [
            "Ray cohort rescheduling preserves each moved job's source duration, node count, hardware profile and job ID.",
            "Uniform timing draws control surge spacing; actual held episodes are measured from simulation telemetry.",
            "The K8S node inventory is set above the source workload to isolate grid-cap admission from a scheduler inventory limit.",
        ],
    }
    return scenario


def main() -> None:
    source = _read_json(SOURCE_PATH)
    template = _read_json(OUTPUT_PATH)
    scenario = build_scenario(source, template)
    OUTPUT_PATH.write_text(
        json.dumps(scenario, indent=N["JSON_INDENT"], ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "scenario": SCENARIO_ID,
                "scheduler_counts": {
                    "SLURM": len(_start_events(source, "SLURM")),
                    "K8S": len(_start_events(source, "K8S")),
                    "RAY": len(_start_events(source, "RAY")),
                },
                "moved_job_count": scenario[
                    "provenance_proxim8_queue"
                ]["moved_job_count"],
                "maximum_shift_seconds": scenario[
                    "provenance_proxim8_queue"
                ]["maximum_observed_shift_seconds"],
                "timing_draws_seconds": scenario[
                    "provenance_proxim8_queue"
                ]["uniform_timing_draw"]["draws_seconds"],
                "intended_windows": scenario[
                    "provenance_proxim8_queue"
                ]["intended_windows"],
                "output": str(OUTPUT_PATH),
            },
            indent=N["JSON_INDENT"],
        )
    )


if __name__ == "__main__":
    main()
