#!/usr/bin/env python3
"""Generate the opt-in Proxim8 queue-stress variant from original arrivals."""

from __future__ import annotations

import json
import random
import time
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
    "MIN_TARGET_DURATION_SECONDS": 60,  # PROPOSED_HERE: minimum one-minute queue-episode target.
    "MAX_TARGET_DURATION_SECONDS": 420,  # PROPOSED_HERE: maximum seven-minute queue-episode target.
    "BUSINESS_START_HOUR": 9,  # PROPOSED_HERE: earliest time in the requested business-day window.
    "BUSINESS_END_HOUR": 18,  # PROPOSED_HERE: exclusive end of the requested business-day window.
    "EARLY_ANCHOR_END_HOUR": 10,  # PROPOSED_HERE: ensure the first episode is drawn from the lighter morning curve.
    "LATE_ANCHOR_START_HOUR": 16,  # PROPOSED_HERE: ensure the last episode supports a six-hour span in the afternoon.
    "MIN_EPISODE_START_GAP_SECONDS": 1200,  # PROPOSED_HERE: require at least twenty minutes between episode starts.
    "MIN_EPISODE_START_SPAN_SECONDS": 21600,  # PROPOSED_HERE: require at least six hours between first and last episode starts.
    "MAX_START_SAMPLING_ATTEMPTS": 10000,  # PROPOSED_HERE: bounded deterministic rejection sampling for valid starts.
    "RAY_CALLS_PER_SPACING_GROUP": 2,  # PROPOSED_HERE: agentic API chains release two calls per short interval.
    "RAY_CALL_CADENCE_SECONDS": 2,  # PROPOSED_HERE: two-second gaps keep calls a few seconds apart and concentrate capacity pressure.
    "SECONDS_PER_MINUTE": 60,  # PROPOSED_HERE: time conversion.
    "SECONDS_PER_HOUR": 3600,  # PROPOSED_HERE: time conversion.
    "SECONDS_PER_DAY": 86400,  # PROPOSED_HERE: Proxim8's 24-hour horizon.
    "K8S_MAX_NODES": 1900,  # PROPOSED_HERE: keep node inventory above source demand so grid-cap admission is the tested queue.
    "K8S_AGENT_MAX_NODES": 1900,  # PROPOSED_HERE: keep cluster capacity above the source workload so grid-cap admission is the tested queue.
    "JSON_INDENT": 2,  # PROPOSED_HERE: match scenario JSON formatting.
}

SCENARIO_ID = "proxim8-5mw-24h-queue"
RAY_SURGE_PREFIX = "ray-agentic-call-burst-"
DECISION_RECORD = "DR-2026-11-03-PROXIM8-QUEUE (PROPOSED_HERE)"
SURGE_METHOD = (
    "The former 16:35 Ray burst is rescheduled as seeded call chains across "
    "the 09:00–18:00 business-day window. Episode starts are sampled from "
    "the source K8S inference arrival-time curve, with an early and a late "
    "anchor to enforce the requested span. Uniform 60–420 second target "
    "durations determine the number of consecutive call pairs assigned "
    "to each chain episode; measured cap-held durations are reported separately. "
    "All moved calls retain their IDs, durations, node counts, profiles and "
    "model names."
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


def _clock_label(time_s: float) -> str:
    return time.strftime("%H:%M:%S", time.gmtime(int(time_s)))


def _ray_chain_groups(ray_surge: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for event in ray_surge:
        suffix = event["job_id"][len(RAY_SURGE_PREFIX) :]
        chain_id, call_id = suffix.split("-", N["ONE"])
        groups.setdefault(chain_id, []).append(event)
    for events in groups.values():
        events.sort(
            key=lambda event: int(
                event["job_id"][len(RAY_SURGE_PREFIX) :].split("-")[N["ONE"]]
            )
        )
    return dict(sorted(groups.items(), key=lambda item: int(item[N["ZERO"]])))


def _allocate_calls_per_episode(
    target_durations_s: list[int],
    calls_per_chain: int,
    rng: random.Random,
) -> list[int]:
    total_target_s = sum(target_durations_s)
    raw_allocations = [
        calls_per_chain * target / total_target_s
        for target in target_durations_s
    ]
    allocations = [int(value) for value in raw_allocations]
    remaining = calls_per_chain - sum(allocations)
    tie_breaks = [rng.random() for _ in raw_allocations]
    order = sorted(
        range(len(raw_allocations)),
        key=lambda index: (
            raw_allocations[index] - allocations[index],
            tie_breaks[index],
        ),
        reverse=True,
    )
    for index in order[:remaining]:
        allocations[index] += N["ONE"]
    return allocations


def _sample_episode_starts(
    rng: random.Random,
    k8s_starts: list[dict],
    max_chain_span_s: int,
) -> list[int]:
    window_start_s = N["BUSINESS_START_HOUR"] * N["SECONDS_PER_HOUR"]
    window_end_s = N["BUSINESS_END_HOUR"] * N["SECONDS_PER_HOUR"]
    early_end_s = N["EARLY_ANCHOR_END_HOUR"] * N["SECONDS_PER_HOUR"]
    late_start_s = N["LATE_ANCHOR_START_HOUR"] * N["SECONDS_PER_HOUR"]
    latest_start_s = window_end_s - max_chain_span_s
    source_times = [
        int(float(event["timestamp"]))
        for event in k8s_starts
        if window_start_s
        <= float(event["timestamp"])
        <= latest_start_s
    ]
    early_times = [value for value in source_times if value < early_end_s]
    late_times = [value for value in source_times if value >= late_start_s]
    if not early_times or not late_times:
        raise ValueError("K8S source arrivals do not cover both episode anchors")

    for _ in range(N["MAX_START_SAMPLING_ATTEMPTS"]):
        starts = [rng.choice(early_times), rng.choice(late_times)]
        attempts = 0
        while (
            len(starts) < N["TEN"]
            and attempts < N["MAX_START_SAMPLING_ATTEMPTS"]
        ):
            attempts += N["ONE"]
            candidate = rng.choice(source_times)
            if all(
                abs(candidate - existing)
                >= N["MIN_EPISODE_START_GAP_SECONDS"]
                for existing in starts
            ):
                starts.append(candidate)
        if len(starts) != N["TEN"]:
            continue
        starts.sort()
        gaps = [
            starts[index + N["ONE"]] - starts[index]
            for index in range(len(starts) - N["ONE"])
        ]
        if (
            starts[-N["ONE"]] - starts[N["ZERO"]]
            >= N["MIN_EPISODE_START_SPAN_SECONDS"]
            and len(set(gaps)) > N["ONE"]
        ):
            return starts
    raise ValueError("could not draw ten spread, non-even episode starts")


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
    target_durations_s = [
        rng.randrange(
            N["MIN_TARGET_DURATION_SECONDS"],
            N["MAX_TARGET_DURATION_SECONDS"] + N["FIVE"],
            N["FIVE"],
        )
        for _ in range(N["TEN"])
    ]
    chain_groups = _ray_chain_groups(ray_surge)
    if not chain_groups:
        raise ValueError("the source Ray burst has no chains")
    calls_per_chain = len(next(iter(chain_groups.values())))
    if any(len(events) != calls_per_chain for events in chain_groups.values()):
        raise ValueError("source Ray chains do not have equal call counts")
    if calls_per_chain * len(chain_groups) != N["RAY_SURGE_CALLS"]:
        raise ValueError("source Ray chain dimensions do not match the burst size")
    calls_per_episode_per_chain = _allocate_calls_per_episode(
        target_durations_s,
        calls_per_chain,
        rng,
    )
    max_chain_span_s = (
        (
            max(calls_per_episode_per_chain)
            - N["ONE"]
        )
        // N["RAY_CALLS_PER_SPACING_GROUP"]
    ) * N["RAY_CALL_CADENCE_SECONDS"]
    episode_start_times_s = _sample_episode_starts(
        rng,
        k8s_starts,
        max_chain_span_s,
    )
    ray_arrivals: list[dict] = []
    moved_jobs: list[dict] = []
    intended_episodes: list[dict] = []

    for episode_index, (start_s, target_s, calls_this_episode) in enumerate(
        zip(
            episode_start_times_s,
            target_durations_s,
            calls_per_episode_per_chain,
        )
    ):
        episode_jobs = 0
        max_offset = (
            calls_this_episode - N["ONE"]
        ) * N["RAY_CALL_CADENCE_SECONDS"]
        for chain_id, events in chain_groups.items():
            for call_offset, event in enumerate(events[:calls_this_episode]):
                original_s = float(event["timestamp"])
                arrival_s = (
                    start_s
                    + (
                        call_offset
                        // N["RAY_CALLS_PER_SPACING_GROUP"]
                    )
                    * N["RAY_CALL_CADENCE_SECONDS"]
                )
                ray_arrivals.append(
                    _scheduled_arrival(event, end_times, arrival_s)
                )
                moved_jobs.append(
                    {
                        "job_id": event["job_id"],
                        "original_time_s": original_s,
                        "new_time_s": arrival_s,
                    }
                )
                episode_jobs += N["ONE"]
            del events[:calls_this_episode]
        intended_episodes.append(
            {
                "episode": episode_index + N["ONE"],
                "arrival_start_s": start_s,
                "arrival_start_local": _clock_label(start_s),
                "target_duration_s": target_s,
                "calls_per_chain": calls_this_episode,
                "ray_calls": episode_jobs,
                "arrival_span_s": max_offset,
            }
        )

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
            "minimum_seconds": N["MIN_TARGET_DURATION_SECONDS"],
            "maximum_seconds": N["MAX_TARGET_DURATION_SECONDS"],
            "step_seconds": N["FIVE"],
            "target_durations_seconds": target_durations_s,
            "use": "seeded episode target; also proportionally allocates source calls to each chain segment",
        },
        "business_window_start_s": (
            N["BUSINESS_START_HOUR"] * N["SECONDS_PER_HOUR"]
        ),
        "business_window_end_s": (
            N["BUSINESS_END_HOUR"] * N["SECONDS_PER_HOUR"]
        ),
        "minimum_episode_start_gap_s": N["MIN_EPISODE_START_GAP_SECONDS"],
        "minimum_episode_start_span_s": N["MIN_EPISODE_START_SPAN_SECONDS"],
        "moved_job_count": len(moved_jobs),
        "maximum_observed_shift_seconds": max(
            abs(item["new_time_s"] - item["original_time_s"])
            for item in moved_jobs
        ),
        "episode_targets": intended_episodes,
        "moved_jobs": sorted(moved_jobs, key=lambda item: item["job_id"]),
        "proposed_here": [
            "Episode starts are sampled from source K8S arrivals; early and late anchors guarantee a non-even six-hour spread.",
            "Uniform target durations allocate the moved Ray-chain call counts; actual held durations are verified from simulation telemetry.",
            "Each original Ray call chain retains its call order; calls are released in pairs every two seconds within each episode.",
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
                "target_durations_seconds": scenario[
                    "provenance_proxim8_queue"
                ]["uniform_timing_draw"]["target_durations_seconds"],
                "episode_targets": scenario[
                    "provenance_proxim8_queue"
                ]["episode_targets"],
                "output": str(OUTPUT_PATH),
            },
            indent=N["JSON_INDENT"],
        )
    )


if __name__ == "__main__":
    main()
