#!/usr/bin/env python3
"""Generate the opt-in Proxim8 queue-stress variant from original arrivals."""

from __future__ import annotations

import json
import random
import time
import argparse
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
    "LATE_ANCHOR_START_HOUR": 14,  # PROPOSED_HERE: start the nine larger surges after the business-day load ramp is established.
    "LATE_ANCHOR_END_HOUR": 17,  # PROPOSED_HERE: end the surge window before late-day demand falls below useful admission pressure.
    "EARLY_EPISODE_COUNT": 1,  # PROPOSED_HERE: one early high-volume surge establishes the business-day span.
    "LATE_EPISODE_COUNT": 9,  # PROPOSED_HERE: nine later surges provide repeated queue episodes during the afternoon.
    "WAVE_CALLS_PER_CHAIN": [57, 15, 13, 13, 15, 13, 15, 15, 11, 13],  # PROPOSED_HERE: iteration nine assigns all 180 calls per source chain while limiting wave-tail episodes.
    "MIN_EPISODE_START_GAP_SECONDS": 1200,  # PROPOSED_HERE: require at least twenty minutes between episode starts.
    "MIN_EPISODE_START_SPAN_SECONDS": 21600,  # PROPOSED_HERE: require at least six hours between first and last episode starts.
    "MAX_START_SAMPLING_ATTEMPTS": 10000,  # PROPOSED_HERE: bounded deterministic rejection sampling for valid starts.
    "RAY_CALLS_PER_SPACING_GROUP": 2,  # PROPOSED_HERE: agentic API chains release two calls per short interval.
    "WAVE_CADENCE_SECONDS": [2, 2, 3, 3, 2, 3, 2, 2, 3, 3],  # PROPOSED_HERE: 2–3 second pair spacing keeps each measured queue continuous.
    "SECONDS_PER_HOUR": 3600,  # PROPOSED_HERE: time conversion.
    "SECONDS_PER_DAY": 86400,  # PROPOSED_HERE: Proxim8's 24-hour horizon.
    "K8S_AGENT_MAX_NODES": 1900,  # PROPOSED_HERE: keep cluster capacity above the source workload so grid-cap admission is the tested queue.
    "RAY_AGENT_MAX_NODES": 1900,  # PROPOSED_HERE: let the grid-cap gate, not a 128-node scheduler ceiling, create the intended Ray queue.
    "BACKGROUND_CALL_COUNT": 2800,  # PROPOSED_HERE: randomize only the non-wave Ray calls.
    "BACKGROUND_CHAIN_COUNT": 28,  # PROPOSED_HERE: retain a useful number of independent background chains.
    "BACKGROUND_MIN_CHAIN_LENGTH": 5,  # PROPOSED_HERE: avoid negligible agentic chains.
    "BACKGROUND_MAX_CHAIN_LENGTH": 200,  # PROPOSED_HERE: cap each background chain at about two hundred calls.
    "BACKGROUND_MIN_GAP_SECONDS": 1,  # PROPOSED_HERE: allow tightly spaced API calls within a chain.
    "BACKGROUND_MAX_GAP_SECONDS": 10,  # PROPOSED_HERE: keep calls in a chain within a short agentic burst.
    "BACKGROUND_ATTEMPT": 1,  # PROPOSED_HERE: initial deterministic background draw; increment after rejected telemetry.
    "BACKGROUND_SEED_OFFSET": 310000,  # PROPOSED_HERE: isolate background draws from the existing wave schedule.
    "HOURS_PER_DAY": 24,  # PROPOSED_HERE: require background calls throughout every hour of the day.
    "JSON_INDENT": 2,  # PROPOSED_HERE: match scenario JSON formatting.
}

# PROPOSED_HERE: relative hourly weights keep a thin overnight tail, lighter
# morning/evening activity, and the heaviest background traffic during business
# hours; weighted sampling without replacement also guarantees an arrival in
# every hour.
BACKGROUND_HOUR_WEIGHTS = (
    0.02, 0.02, 0.02, 0.02, 0.03, 0.05,
    0.10, 0.18, 0.35, 0.65, 0.90, 1.00,
    1.05, 1.10, 1.15, 1.20, 1.20, 1.10,
    0.85, 0.60, 0.35, 0.18, 0.08, 0.04,
)

SCENARIO_ID = "proxim8-5mw-24h-queue"
RAY_SURGE_PREFIX = "ray-agentic-call-burst-"
DECISION_RECORD = "DR-2026-11-03-PROXIM8-QUEUE (PROPOSED_HERE)"
AGENTIC_RANDOMIZATION_RECORD = (
    "DR-2026-11-04-PROXIM8-AGENTIC-RANDOM (PROPOSED_HERE)"
)
SURGE_METHOD = (
    "The former 16:35 Ray burst is rescheduled as one concentrated early "
    "chain wave and nine seeded afternoon call-chain waves. Starts are sampled "
    "from the source K8S inference arrival-time curve across 09:00–18:00, "
    "with a morning anchor, at least twenty minutes between starts, and a "
    "six-hour minimum span. Uniform 60–420 second target durations are recorded "
    "independently; the test reports measured cap-held durations from telemetry. "
    "Each wave has its own seeded-calibration call count and pair cadence. "
    "All moved calls retain their IDs, durations, node counts, profiles and "
    "model names."
)
BACKGROUND_METHOD = (
    "The 2,800 non-wave Ray calls are regrouped into seeded chains of "
    "5–200 calls with randomized 1–10 second gaps. Chain starts use a "
    "business-day weighted hourly distribution with a thin overnight tail."
)

# PROPOSED_HERE: retain the bounded, measured calibration history; only the
# wave call counts and within-wave cadence varied, while background attempt 1
# and every other workload input remained unchanged.
CALIBRATION_ITERATIONS = [
    {"iteration": 1, "calls_per_chain": [45, 15, 15, 15, 15, 15, 15, 15, 15, 15], "cadence_seconds": [2, 2, 2, 2, 2, 2, 2, 2, 2, 2], "measured_episode_durations_s": [145, 195, 240, 10, 390, 10, 285, 450, 5, 210, 150, 195, 10, 330, 10]},
    {"iteration": 2, "calls_per_chain": [45, 15, 15, 15, 15, 15, 15, 15, 15, 15], "cadence_seconds": [3, 3, 3, 3, 3, 3, 3, 3, 3, 3], "measured_episode_durations_s": [145, 195, 240, 10, 390, 10, 285, 450, 5, 210, 150, 195, 10, 330, 10]},
    {"iteration": 3, "calls_per_chain": [45, 15, 15, 15, 15, 15, 15, 15, 15, 15], "cadence_seconds": [4, 4, 4, 4, 4, 4, 4, 4, 4, 4], "measured_episode_durations_s": [145, 195, 240, 10, 390, 10, 285, 450, 5, 210, 150, 195, 10, 330, 10]},
    {"iteration": 4, "calls_per_chain": [45, 15, 15, 15, 15, 15, 15, 15, 15, 15], "cadence_seconds": [6, 6, 6, 6, 6, 6, 6, 6, 6, 6], "measured_episode_durations_s": [25, 25, 25, 40, 195, 240, 10, 390, 10, 285, 450, 5, 210, 150, 195, 10, 330, 10]},
    {"iteration": 5, "calls_per_chain": [51, 15, 14, 14, 15, 13, 15, 15, 14, 14], "cadence_seconds": [2, 2, 2, 2, 2, 2, 2, 2, 2, 2], "measured_episode_durations_s": [170, 195, 225, 360, 10, 285, 405, 210, 150, 180, 10, 315]},
    {"iteration": 6, "calls_per_chain": [55, 15, 13, 13, 15, 13, 15, 15, 13, 13], "cadence_seconds": [2, 2, 3, 3, 2, 3, 2, 2, 3, 3], "measured_episode_durations_s": [185, 195, 210, 345, 285, 405, 210, 150, 165, 5, 300]},
    {"iteration": 7, "calls_per_chain": [56, 15, 13, 13, 15, 13, 15, 15, 13, 12], "cadence_seconds": [2, 2, 3, 3, 2, 3, 2, 2, 3, 3], "measured_episode_durations_s": [190, 195, 210, 345, 285, 405, 210, 150, 165, 5, 300, 5]},
    {"iteration": 8, "calls_per_chain": [56, 15, 13, 13, 15, 13, 15, 15, 12, 13], "cadence_seconds": [2, 2, 3, 3, 2, 3, 2, 2, 3, 3], "measured_episode_durations_s": [190, 195, 210, 345, 285, 405, 210, 150, 150, 5, 300]},
    {"iteration": 9, "calls_per_chain": [57, 15, 13, 13, 15, 13, 15, 15, 11, 13], "cadence_seconds": [2, 2, 3, 3, 2, 3, 2, 2, 3, 3], "measured_episode_durations_s": [190, 195, 210, 345, 285, 405, 210, 150, 135, 300]},
]


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


def _random_chain_lengths(rng: random.Random) -> list[int]:
    remaining = N["BACKGROUND_CALL_COUNT"]
    lengths: list[int] = []
    for index in range(N["BACKGROUND_CHAIN_COUNT"]):
        slots_after = N["BACKGROUND_CHAIN_COUNT"] - index - N["ONE"]
        minimum = max(
            N["BACKGROUND_MIN_CHAIN_LENGTH"],
            remaining - N["BACKGROUND_MAX_CHAIN_LENGTH"] * slots_after,
        )
        maximum = min(
            N["BACKGROUND_MAX_CHAIN_LENGTH"],
            remaining - N["BACKGROUND_MIN_CHAIN_LENGTH"] * slots_after,
        )
        length = remaining if slots_after == N["ZERO"] else rng.randint(
            minimum, maximum
        )
        lengths.append(length)
        remaining -= length
    if remaining != N["ZERO"] or sum(lengths) != N["BACKGROUND_CALL_COUNT"]:
        raise ValueError("background chain partition does not preserve call count")
    if not all(
        N["BACKGROUND_MIN_CHAIN_LENGTH"]
        <= length
        <= N["BACKGROUND_MAX_CHAIN_LENGTH"]
        for length in lengths
    ):
        raise ValueError("background chain length is outside the proposed range")
    return lengths


def _weighted_chain_hours(rng: random.Random) -> list[int]:
    if len(BACKGROUND_HOUR_WEIGHTS) != N["HOURS_PER_DAY"]:
        raise ValueError("one background weight is required for each hour")
    available = list(range(N["HOURS_PER_DAY"]))
    chosen: list[int] = []
    for _ in range(N["HOURS_PER_DAY"]):
        weights = [BACKGROUND_HOUR_WEIGHTS[hour] for hour in available]
        hour = rng.choices(available, weights=weights, k=N["ONE"])[N["ZERO"]]
        chosen.append(hour)
        available.remove(hour)
    for _ in range(N["BACKGROUND_CHAIN_COUNT"] - N["HOURS_PER_DAY"]):
        chosen.append(
            rng.choices(
                range(N["HOURS_PER_DAY"]),
                weights=BACKGROUND_HOUR_WEIGHTS,
                k=N["ONE"],
            )[N["ZERO"]]
        )
    return chosen


def _build_random_background(
    events: list[dict],
    end_times: dict,
    *,
    attempt_number: int,
) -> tuple[list[dict], dict]:
    if len(events) != N["BACKGROUND_CALL_COUNT"]:
        raise ValueError(
            f"expected {N['BACKGROUND_CALL_COUNT']} non-wave Ray calls"
        )
    if attempt_number < N["ONE"]:
        raise ValueError("background attempt numbers are one-based")

    attempt_seed = (
        N["SEED"] + N["BACKGROUND_SEED_OFFSET"] + attempt_number
    )
    rng = random.Random(attempt_seed)
    lengths = _random_chain_lengths(rng)
    chain_hours = _weighted_chain_hours(rng)
    ordered_events = sorted(
        events,
        key=lambda event: (float(event["timestamp"]), event["job_id"]),
    )
    arrivals: list[dict] = []
    moved_calls: list[dict] = []
    hourly_counts = [N["ZERO"]] * N["HOURS_PER_DAY"]
    cursor = N["ZERO"]

    for chain_index, (chain_length, hour) in enumerate(
        zip(lengths, chain_hours),
        start=N["ONE"],
    ):
        chain_events = ordered_events[cursor : cursor + chain_length]
        cursor += chain_length
        gaps = [
            rng.randint(
                N["BACKGROUND_MIN_GAP_SECONDS"],
                N["BACKGROUND_MAX_GAP_SECONDS"],
            )
            for _ in range(chain_length - N["ONE"])
        ]
        offsets = [N["ZERO"]]
        for gap in gaps:
            offsets.append(offsets[-N["ONE"]] + gap)
        latest_start_offset = (
            N["SECONDS_PER_HOUR"] - N["ONE"] - offsets[-N["ONE"]]
        )
        chain_start_s = (
            hour * N["SECONDS_PER_HOUR"]
            + rng.randint(N["ZERO"], latest_start_offset)
        )
        chain_id = f"ray-agentic-background-{chain_index:02d}"

        for position, (event, offset) in enumerate(
            zip(chain_events, offsets),
            start=N["ONE"],
        ):
            original_s = float(event["timestamp"])
            arrival_s = float(chain_start_s + offset)
            arrivals.append(_scheduled_arrival(event, end_times, arrival_s))
            moved_calls.append(
                {
                    "job_id": event["job_id"],
                    "original_time_s": original_s,
                    "new_time_s": arrival_s,
                    "chain_id": chain_id,
                    "chain_position": position,
                    "chain_length": chain_length,
                    "gap_before_s": (
                        N["ZERO"] if position == N["ONE"] else gaps[position - 2]
                    ),
                }
            )
            hourly_counts[int(arrival_s // N["SECONDS_PER_HOUR"])] += N["ONE"]

    if cursor != len(ordered_events):
        raise ValueError("background chains did not consume every source call")
    if any(count == N["ZERO"] for count in hourly_counts):
        raise ValueError("background draw must include every hour")
    return arrivals, {
        "seed": attempt_seed,
        "attempt_number": attempt_number,
        "rejected_attempt_count": attempt_number - N["ONE"],
        "call_count": len(moved_calls),
        "chain_lengths": lengths,
        "hourly_weights": list(BACKGROUND_HOUR_WEIGHTS),
        "hourly_call_counts": hourly_counts,
        "calls": sorted(moved_calls, key=lambda item: item["job_id"]),
    }


def _allocate_calls_per_episode(
    calls_per_chain: int,
) -> list[int]:
    allocations = list(N["WAVE_CALLS_PER_CHAIN"])
    if len(allocations) != N["TEN"]:
        raise ValueError("one call allocation is required for each wave")
    if sum(allocations) != calls_per_chain:
        raise ValueError("the seeded episode allocation must preserve each source chain")
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
    late_end_s = N["LATE_ANCHOR_END_HOUR"] * N["SECONDS_PER_HOUR"]
    latest_start_s = window_end_s - max_chain_span_s
    source_times = [
        int(float(event["timestamp"]))
        for event in k8s_starts
        if window_start_s
        <= float(event["timestamp"])
        <= latest_start_s
    ]
    early_times = [value for value in source_times if value < early_end_s]
    late_times = [
        value
        for value in source_times
        if late_start_s <= value < late_end_s
    ]
    if N["EARLY_EPISODE_COUNT"] + N["LATE_EPISODE_COUNT"] != N["TEN"]:
        raise ValueError("early and late episode counts must total ten")
    if not early_times or len(late_times) < N["LATE_EPISODE_COUNT"]:
        raise ValueError("K8S source arrivals do not cover both episode anchors")

    for _ in range(N["MAX_START_SAMPLING_ATTEMPTS"]):
        starts = [
            rng.choice(early_times)
            for _ in range(N["EARLY_EPISODE_COUNT"])
        ]
        attempts = 0
        while (
            len(starts) < N["TEN"]
            and attempts < N["MAX_START_SAMPLING_ATTEMPTS"]
        ):
            attempts += N["ONE"]
            candidate = rng.choice(
                early_times
                if len(starts) < N["EARLY_EPISODE_COUNT"]
                else late_times
            )
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


def build_scenario(
    source: dict,
    template: dict,
    *,
    background_attempt: int | None = None,
) -> dict:
    attempt_number = (
        N["BACKGROUND_ATTEMPT"]
        if background_attempt is None
        else background_attempt
    )
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
    calls_per_episode_per_chain = _allocate_calls_per_episode(calls_per_chain)
    if len(N["WAVE_CADENCE_SECONDS"]) != N["TEN"]:
        raise ValueError("one cadence is required for each wave")
    max_chain_span_s = max(
        (
            (calls_this_episode - N["ONE"])
            // N["RAY_CALLS_PER_SPACING_GROUP"]
        ) * cadence_s
        for calls_this_episode, cadence_s in zip(
            calls_per_episode_per_chain,
            N["WAVE_CADENCE_SECONDS"],
        )
    )
    episode_start_times_s = _sample_episode_starts(
        rng,
        k8s_starts,
        max_chain_span_s,
    )
    ray_arrivals: list[dict] = []
    moved_jobs: list[dict] = []
    intended_episodes: list[dict] = []

    for episode_index, (start_s, target_s, calls_this_episode, cadence_s) in enumerate(
        zip(
            episode_start_times_s,
            target_durations_s,
            calls_per_episode_per_chain,
            N["WAVE_CADENCE_SECONDS"],
        )
    ):
        episode_jobs = 0
        max_offset = (
            (
                calls_this_episode - N["ONE"]
            )
            // N["RAY_CALLS_PER_SPACING_GROUP"]
        ) * cadence_s
        for chain_id, events in chain_groups.items():
            for call_offset, event in enumerate(events[:calls_this_episode]):
                original_s = float(event["timestamp"])
                arrival_s = (
                    start_s
                    + (
                        call_offset
                        // N["RAY_CALLS_PER_SPACING_GROUP"]
                    )
                    * cadence_s
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
                "cadence_seconds": cadence_s,
                "arrival_span_s": max_offset,
            }
        )

    moved_ids = {item["job_id"] for item in moved_jobs}
    background_source_events = [
        event for event in ray_starts if event["job_id"] not in moved_ids
    ]
    background_arrivals, background_provenance = _build_random_background(
        background_source_events,
        end_times,
        attempt_number=attempt_number,
    )
    ray_arrivals.extend(background_arrivals)
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
        elif scheduler == "RAY":
            cluster["max_nodes"] = N["RAY_AGENT_MAX_NODES"]

    scenario = deepcopy(template)
    scenario["name"] = SCENARIO_ID
    seeded_target_summary = ", ".join(
        f"{episode['arrival_start_local']} ({episode['target_duration_s']} s)"
        for episode in intended_episodes
    )
    scenario["description"] = (
        source["description"]
        + "\n\nQueue-stress variant. "
        + SURGE_METHOD
        + f" Seed {N['SEED']}; {len(moved_jobs):,} moved Ray calls. "
        + BACKGROUND_METHOD
        + f" Randomization attempt {attempt_number}; "
        + f"{background_provenance['call_count']:,} background calls recorded."
        + "Seeded episode targets (local start / seconds): "
        + seeded_target_summary
        + ". "
        + f"{DECISION_RECORD}."
        + f" {AGENTIC_RANDOMIZATION_RECORD}."
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
        "agentic_randomization_record": AGENTIC_RANDOMIZATION_RECORD,
        "surge_method": SURGE_METHOD,
        "background_method": BACKGROUND_METHOD,
        "background_agentic_randomization": background_provenance,
        "uniform_timing_draw": {
            "minimum_seconds": N["MIN_TARGET_DURATION_SECONDS"],
            "maximum_seconds": N["MAX_TARGET_DURATION_SECONDS"],
            "step_seconds": N["FIVE"],
            "target_durations_seconds": target_durations_s,
            "use": "seeded target for measured telemetry comparison; calls are allocated by the documented one-early/nine-afternoon surge design",
        },
        "business_window_start_s": (
            N["BUSINESS_START_HOUR"] * N["SECONDS_PER_HOUR"]
        ),
        "business_window_end_s": (
            N["BUSINESS_END_HOUR"] * N["SECONDS_PER_HOUR"]
        ),
        "minimum_episode_start_gap_s": N["MIN_EPISODE_START_GAP_SECONDS"],
        "minimum_episode_start_span_s": N["MIN_EPISODE_START_SPAN_SECONDS"],
        "moved_call_count": len(moved_jobs),
        "maximum_observed_shift_seconds": max(
            abs(item["new_time_s"] - item["original_time_s"])
            for item in moved_jobs
        ),
        "episode_targets": intended_episodes,
        "calibration_iterations": CALIBRATION_ITERATIONS,
        "moved_jobs": sorted(moved_jobs, key=lambda item: item["job_id"]),
        "proposed_here": [
            "Episode starts are sampled from source K8S arrivals; early and late anchors guarantee a non-even six-hour spread.",
            "Uniform target durations are comparison targets; actual held durations are verified from simulation telemetry.",
            "Each original Ray call chain retains its call order; each wave releases calls in pairs at its recorded cadence.",
            "K8S and RAY node inventories are set above source demand so the grid-cap rule, not scheduler inventory, produces the held queues.",
            "Background chain lengths and gaps are seeded; the hourly weights create business-day traffic and retain a thin overnight tail.",
            "Background attempt numbers identify the deterministic re-draw used when a candidate produces extra held episodes.",
        ],
    }
    return scenario


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--background-attempt",
        type=int,
        default=N["BACKGROUND_ATTEMPT"],
        help="one-based deterministic background draw attempt",
    )
    args = parser.parse_args()
    source = _read_json(SOURCE_PATH)
    template = _read_json(OUTPUT_PATH)
    scenario = build_scenario(
        source,
        template,
        background_attempt=args.background_attempt,
    )
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
                "moved_call_count": scenario[
                    "provenance_proxim8_queue"
                ]["moved_call_count"],
                "maximum_shift_seconds": scenario[
                    "provenance_proxim8_queue"
                ]["maximum_observed_shift_seconds"],
                "target_durations_seconds": scenario[
                    "provenance_proxim8_queue"
                ]["uniform_timing_draw"]["target_durations_seconds"],
                "episode_targets": scenario[
                    "provenance_proxim8_queue"
                ]["episode_targets"],
                "background_attempt": scenario[
                    "provenance_proxim8_queue"
                ]["background_agentic_randomization"]["attempt_number"],
                "background_rejected_attempts": scenario[
                    "provenance_proxim8_queue"
                ]["background_agentic_randomization"][
                    "rejected_attempt_count"
                ],
                "ray_calls_per_hour": scenario[
                    "provenance_proxim8_queue"
                ]["background_agentic_randomization"][
                    "hourly_call_counts"
                ],
                "output": str(OUTPUT_PATH),
            },
            indent=N["JSON_INDENT"],
        )
    )


if __name__ == "__main__":
    main()
