#!/usr/bin/env python3
"""Generate the separate early-wave Proxim8 queue-stress scenario."""

from __future__ import annotations

import copy
import argparse
import json
import math
import random
from pathlib import Path
from typing import Any


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = PACKAGE_ROOT / "config" / "scenarios"
SOURCE_PATH = SCENARIO_DIR / "proxim8-5mw-24h.json"
QUEUE_TEMPLATE_PATH = SCENARIO_DIR / "proxim8-5mw-24h-queue.json"
OUTPUT_PATH = SCENARIO_DIR / "proxim8-5mw-24h-queue-early.json"

# PROPOSED_HERE: the session begins at 09:00 local; simulation time has no
# configurable wall-clock start, so all daily timelines are rotated by this offset.
SESSION_START_LOCAL_HOUR = 9
# PROPOSED_HERE: convert the 09:00 local start to seconds for circular rotation.
SESSION_START_OFFSET_S = SESSION_START_LOCAL_HOUR * 3600
# PROPOSED_HERE: the first local 09:15 wave follows a 15-minute warm-up.
FIRST_LOCAL_WAVE_OFFSET_S = 900
# PROPOSED_HERE: waves remain one hour apart through local 18:15.
LOCAL_WAVE_INTERVAL_S = 3600
# PROPOSED_HERE: borrow at most 1,500 of the 2,800 background calls to enlarge
# the wave pool while retaining a background call in every rotated hour.
BORROWED_BACKGROUND_CALL_COUNT = 1500
# PROPOSED_HERE: isolate the seeded background-call selection from all workload draws.
BORROWED_BACKGROUND_SEED_OFFSET = 730000
# PROPOSED_HERE: the wave pool contains 7,200 original calls plus the borrowed subset.
EXPECTED_RAY_WAVE_CALL_COUNT = 8700
# PROPOSED_HERE: forty synchronized source chains define one wave-arrival batch.
RAY_WAVE_BATCH_SIZE = 40
# PROPOSED_HERE: iteration 6 was the closest trial that retained ten episodes
# and a 300-second episode while satisfying the fixed 8,700-call budget.
RAY_CALL_COUNT_BY_WAVE = (1360, 1280, 1200, 1200, 1000, 220, 560, 360, 520, 1000)
# PROPOSED_HERE: no inter-batch delay preserves the strongest cap pressure found.
RAY_INTERARRIVAL_BY_WAVE_S = (0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
# PROPOSED_HERE: one initial batch reproduces the synchronized no-gap calibration.
RAY_IMMEDIATE_BATCH_COUNT_BY_WAVE = (1, 1, 1, 1, 1, 1, 1, 1, 1, 1)
# PROPOSED_HERE: the calibration is bounded to twelve complete deterministic day runs.
CALIBRATION_MAX_ITERATIONS = 12
# PROPOSED_HERE: seeded duration targets span the requested short-to-long range.
CALIBRATION_TARGET_DURATIONS_S = (255, 270, 95, 345, 380, 240, 330, 245, 365, 100)
# PROPOSED_HERE: preserve every measured trial so the infeasible count tradeoff is auditable.
CALIBRATION_ITERATION_LOG: tuple[dict[str, Any], ...] = (
    {"iteration": 1, "calls_by_wave": (1360, 1280, 1200, 1200, 1200, 240, 120, 320, 440, 1340), "interarrival_s_by_wave": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0), "immediate_batches_by_wave": (1, 1, 1, 1, 1, 1, 1, 1, 1, 1), "measured_episode_durations_s": (60, 60, 60, 60, 70, 60, 50, 55, 55, 60)},
    {"iteration": 2, "calls_by_wave": (1300, 1200, 1100, 1100, 1100, 200, 600, 250, 350, 1500), "interarrival_s_by_wave": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0), "immediate_batches_by_wave": (1, 1, 1, 1, 1, 1, 1, 1, 1, 1), "measured_episode_durations_s": (55, 55, 50, 55, 65, 50, 370, 45, 45, 70)},
    {"iteration": 3, "calls_by_wave": (1284, 1204, 1124, 1124, 1124, 220, 600, 300, 420, 1300), "interarrival_s_by_wave": (5, 5, 5, 5, 5, 5, 0, 5, 5, 5), "immediate_batches_by_wave": (1, 1, 1, 1, 1, 1, 1, 1, 1, 1), "measured_episode_durations_s": (55, 370, 55, 45)},
    {"iteration": 4, "calls_by_wave": (1300, 1220, 1160, 1160, 1160, 220, 600, 300, 420, 1160), "interarrival_s_by_wave": (1, 1, 1, 1, 1, 1, 0, 1, 1, 1), "immediate_batches_by_wave": (1, 1, 1, 1, 1, 1, 1, 1, 1, 1), "measured_episode_durations_s": (50, 55, 50, 55, 65, 55, 370, 55, 55, 45)},
    {"iteration": 5, "calls_by_wave": (1360, 1280, 1200, 1200, 1000, 240, 600, 320, 440, 1060), "interarrival_s_by_wave": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0), "immediate_batches_by_wave": (1, 1, 1, 1, 1, 1, 1, 1, 1, 1), "measured_episode_durations_s": (60, 60, 60, 60, 55, 60, 370, 55, 55, 45)},
    {"iteration": 6, "calls_by_wave": (1360, 1280, 1200, 1200, 1000, 220, 560, 360, 520, 1000), "interarrival_s_by_wave": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0), "immediate_batches_by_wave": (1, 1, 1, 1, 1, 1, 1, 1, 1, 1), "measured_episode_durations_s": (60, 60, 60, 60, 55, 55, 340, 65, 70, 40)},
    {"iteration": 7, "calls_by_wave": (1360, 1280, 1200, 1200, 1000, 220, 560, 360, 520, 1000), "interarrival_s_by_wave": (2, 2, 2, 2, 2, 2, 0, 2, 2, 2), "immediate_batches_by_wave": (1, 1, 1, 1, 1, 1, 1, 1, 1, 1), "measured_episode_durations_s": (45, 40, 50, 50, 45, 55, 340, 70, 70, 35)},
    {"iteration": 8, "calls_by_wave": (1360, 1280, 1200, 1200, 1000, 220, 560, 360, 520, 1000), "interarrival_s_by_wave": (0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0, 0.5, 0.5, 0.5), "immediate_batches_by_wave": (1, 1, 1, 1, 1, 1, 1, 1, 1, 1), "measured_episode_durations_s": (55, 55, 55, 55, 55, 55, 340, 70, 70, 40)},
    {"iteration": 9, "calls_by_wave": (1360, 1280, 1200, 1200, 1000, 220, 560, 360, 520, 1000), "interarrival_s_by_wave": (5, 5, 5, 5, 5, 5, 0, 5, 5, 5), "immediate_batches_by_wave": (8, 8, 8, 8, 8, 8, 14, 8, 8, 8), "measured_episode_durations_s": (15, 15, 20, 20, 20, 55, 340, 65, 70, 5)},
    {"iteration": 10, "calls_by_wave": (1360, 1280, 1200, 1200, 1000, 220, 560, 360, 520, 1000), "interarrival_s_by_wave": (5, 5, 5, 5, 5, 5, 0, 5, 5, 5), "immediate_batches_by_wave": (15, 15, 15, 15, 15, 8, 14, 8, 8, 15), "measured_episode_durations_s": (30, 40, 40, 45, 55, 55, 340, 65, 70, 30)},
    {"iteration": 11, "calls_by_wave": (1360, 1280, 1200, 1200, 1000, 500, 320, 360, 480, 1000), "interarrival_s_by_wave": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0), "immediate_batches_by_wave": (1, 1, 1, 1, 1, 1, 1, 1, 1, 1), "measured_episode_durations_s": (60, 60, 60, 60, 55, 145, 180, 65, 65, 40)},
    {"iteration": 12, "calls_by_wave": (1360, 1280, 1200, 1200, 1000, 220, 560, 360, 520, 1000), "interarrival_s_by_wave": (5, 5, 5, 5, 5, 5, 0, 5, 5, 5), "immediate_batches_by_wave": (20, 20, 20, 20, 20, 6, 14, 8, 8, 20), "measured_episode_durations_s": (50, 60, 60, 60, 55, 55, 340, 65, 70, 40)},
)

# PROPOSED_HERE: preserve the approved deterministic Proxim8 seed.
SEED = 20261102
# PROPOSED_HERE: ten early queue waves provide hourly stress points.
WAVE_COUNT = 10
# PROPOSED_HERE: the first wave begins 15 minutes after the 09:00 session start.
FIRST_WAVE_START_S = FIRST_LOCAL_WAVE_OFFSET_S
# PROPOSED_HERE: hourly starts match the approved local schedule.
WAVE_INTERVAL_S = LOCAL_WAVE_INTERVAL_S
# PROPOSED_HERE: a ten-minute lead lets K8S demand rise before each Ray wave.
K8S_LEAD_WINDOW_S = 600
# PROPOSED_HERE: front-load existing K8S sessions before the early waves so
# their still-active sessions raise the later-wave background without a single
# oversized cohort; these counts sum to the existing 995 movable sessions.
# PROPOSED_HERE: distribute K8S sessions nearly evenly to create a moderate
# pre-wave background at every hourly window while preserving all 995 sessions.
# PROPOSED_HERE: seed a stronger longest-target cohort while retaining enough
# sessions in each hourly wave to produce a measurable queue episode.
K8S_COUNTS_BY_WAVE = (112, 112, 112, 112, 212, 100, 60, 60, 60, 55)
# PROPOSED_HERE: seed larger existing sessions into the peak target, the
# next hourly window, and each later window to extend measured queue duration.
K8S_HIGH_NODE_WAVE_INDICES = (4, 4, 5, 6, 6, 7, 8, 9)
# PROPOSED_HERE: most waves retain eighteen calls per source chain.
RAY_BASE_CALLS_PER_CHAIN = 18
# PROPOSED_HERE: the near-cap background needs a reduced trigger wave.
RAY_HIGH_BACKGROUND_CALLS_PER_CHAIN = 13
# PROPOSED_HERE: the first and last waves receive slightly more queued work.
RAY_HIGH_CALLS_PER_CHAIN = 20
# PROPOSED_HERE: this seed's early and late stress windows need extra calls.
RAY_HIGH_CALL_WAVE_INDICES = (6, 7, 8, 9)
# PROPOSED_HERE: one higher-load wave offsets the extra first-wave call.
RAY_LOW_CALLS_PER_CHAIN = 17
# PROPOSED_HERE: reduce one existing wave's call allocation to preserve all 7,200.
RAY_LOW_CALL_WAVE_INDEX = 2
# PROPOSED_HERE: each source Ray chain keeps all of its original 180 calls.
RAY_CALLS_PER_CHAIN_TOTAL = 180
# PROPOSED_HERE: pairs of calls arrive two seconds apart inside each wave.
RAY_PAIR_SPACING_S = 2
# PROPOSED_HERE: use a separate random stream so duration draws cannot alter
# the established hourly wave starts or background-chain draws.
WAVE_TARGET_SEED_OFFSET = 52000
# PROPOSED_HERE: target episodes cover the requested one-to-seven-minute range.
MIN_WAVE_TARGET_S = 60
MAX_WAVE_TARGET_S = 420
# PROPOSED_HERE: target values are on the simulator's five-second tick grid.
WAVE_TARGET_STEP_S = 5
# PROPOSED_HERE: at least one target is short and one is five minutes or longer.
SHORT_WAVE_TARGET_CEILING_S = 120
LONG_WAVE_TARGET_FLOOR_S = 300
# PROPOSED_HERE: require enough distinct targets to prevent near-identical waves.
MIN_DISTINCT_WAVE_TARGETS = 6
# PROPOSED_HERE: bound deterministic redraws while finding qualifying targets.
MAX_WAVE_TARGET_DRAW_ATTEMPTS = 1000
# PROPOSED_HERE: keep the approved seed but isolate background randomness.
BACKGROUND_SEED_OFFSET = 310000
# PROPOSED_HERE: start with the first deterministic draw; later attempts are
# recorded when an earlier candidate creates an extra cap-held episode.
BACKGROUND_ATTEMPT = 1
# PROPOSED_HERE: retain 28 chains while randomizing their individual lengths.
BACKGROUND_CHAIN_COUNT = 28
# PROPOSED_HERE: each randomized background chain contains five to two hundred calls.
BACKGROUND_MIN_CHAIN_LENGTH = 5
BACKGROUND_MAX_CHAIN_LENGTH = 200
# PROPOSED_HERE: calls within a background chain are one to ten seconds apart.
BACKGROUND_MIN_GAP_S = 1
BACKGROUND_MAX_GAP_S = 10
# PROPOSED_HERE: all 24 hours receive at least one weighted background chain.
HOURS_PER_DAY = 24
# PROPOSED_HERE: unitless weights create a thin overnight tail, lighter shoulder
# hours, and the heaviest random chain starts during the business day.
BACKGROUND_HOUR_WEIGHTS = (
    0.02, 0.02, 0.02, 0.02, 0.03, 0.05,
    0.10, 0.18, 0.35, 0.65, 0.90, 1.00,
    1.05, 1.10, 1.15, 1.20, 1.20, 1.10,
    0.85, 0.60, 0.35, 0.18, 0.08, 0.04,
)
# PROPOSED_HERE: preserve the scenario's approved scheduler workload totals.
EXPECTED_K8S_COUNT = 1000
EXPECTED_RAY_COUNT = 10000
EXPECTED_RAY_BURST_COUNT = 7200
EXPECTED_SLURM_COUNT = 10
# PROPOSED_HERE: preserve five continuous-inference sessions at midnight.
MIDNIGHT_CARRY_OVER_K8S_COUNT = 5
# PROPOSED_HERE: the source Ray wave consists of forty reusable chains.
RAY_SOURCE_CHAIN_COUNT = 40
# PROPOSED_HERE: scheduled arrivals align to the simulator's five-second tick.
TICK_SECONDS = 5
# PROPOSED_HERE: hourly placement and a 24-hour simulation use these units.
SECONDS_PER_HOUR = 3600
SECONDS_PER_DAY = 86400
RAY_BURST_PREFIX = "ray-agentic-call-burst-"


def _start_events(spec: dict[str, Any], scheduler: str) -> list[dict[str, Any]]:
    return [
        event
        for event in spec["workload_events"]
        if event.get("scheduler_type") == scheduler
        and event.get("event_type") == "starting"
    ]


def _end_times(spec: dict[str, Any], scheduler: str) -> dict[str, float]:
    return {
        event["job_id"]: float(event["timestamp"])
        for event in spec["workload_events"]
        if event.get("scheduler_type") == scheduler
        and event.get("event_type") == "job_end"
    }


def _scheduled_arrival(
    event: dict[str, Any],
    *,
    original_time_s: float,
    arrival_time_s: float,
    end_time_s: float,
) -> dict[str, Any]:
    return {
        "job_id": event["job_id"],
        "arrival_time_s": arrival_time_s,
        "duration_s": end_time_s - original_time_s,
        "node_count": int(event["node_count"]),
        "hardware_profile_id": event["hardware_profile_id"],
    }


def _provenance_move(
    event: dict[str, Any],
    *,
    original_time_s: float,
    new_time_s: float,
    end_time_s: float,
) -> dict[str, Any]:
    return {
        "job_id": event["job_id"],
        "original_time_s": original_time_s,
        "new_time_s": new_time_s,
        "duration_s": end_time_s - original_time_s,
        "node_count": int(event["node_count"]),
        "hardware_profile_id": event["hardware_profile_id"],
    }


def _rotate_daily_time(timestamp_s: float) -> float:
    return float((float(timestamp_s) - SESSION_START_OFFSET_S) % SECONDS_PER_DAY)


def _rotate_daily_profile(
    profile: list[list[float]],
) -> list[list[float]]:
    """Rotate a 5-minute periodic profile while retaining its endpoint."""
    rotated = sorted(
        (
            _rotate_daily_time(float(timestamp_s)),
            float(mw),
        )
        for timestamp_s, mw in profile
        if float(timestamp_s) < SECONDS_PER_DAY
    )
    if not rotated or rotated[0][0] != 0.0:
        raise ValueError("daily load profile must contain the rotated start point")
    return [[timestamp_s, mw] for timestamp_s, mw in rotated] + [
        [float(SECONDS_PER_DAY), rotated[0][1]]
    ]


def _rotate_scheduled_arrivals(
    arrivals: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rotated: list[dict[str, Any]] = []
    moves: list[dict[str, Any]] = []
    for arrival in arrivals:
        original_time_s = float(arrival["arrival_time_s"])
        new_time_s = _rotate_daily_time(original_time_s)
        rotated.append({**arrival, "arrival_time_s": new_time_s})
        moves.append({
            "job_id": arrival["job_id"],
            "original_time_s": original_time_s,
            "new_time_s": new_time_s,
            "duration_s": float(arrival["duration_s"]),
            "node_count": int(arrival["node_count"]),
            "hardware_profile_id": arrival["hardware_profile_id"],
        })
    rotated.sort(key=lambda row: (row["arrival_time_s"], row["job_id"]))
    moves.sort(key=lambda row: row["job_id"])
    return rotated, moves


def _rotate_slurm_events(
    events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    starts = {
        event["job_id"]: float(event["timestamp"])
        for event in events
        if event.get("event_type") == "starting"
        and event.get("scheduler_type") == "SLURM"
    }
    rotated: list[dict[str, Any]] = []
    moves: list[dict[str, Any]] = []
    for event in events:
        original_time_s = float(event["timestamp"])
        new_time_s = _rotate_daily_time(original_time_s)
        if event.get("event_type") == "job_end":
            start_time = starts.get(event["job_id"])
            if start_time is not None:
                new_start = _rotate_daily_time(start_time)
                if new_time_s <= new_start:
                    new_time_s += SECONDS_PER_DAY
            # The session ends at 24 hours; jobs crossing that boundary are
            # naturally truncated, so their post-session end event is omitted.
            if new_time_s >= SECONDS_PER_DAY:
                moves.append({
                    "job_id": event["job_id"],
                    "event_type": event.get("event_type"),
                    "original_time_s": original_time_s,
                    "new_time_s": None,
                    "truncated_after_session": True,
                })
                continue
        rotated_event = {**event, "timestamp": new_time_s}
        rotated.append(rotated_event)
        moves.append({
            "job_id": event["job_id"],
            "event_type": event.get("event_type"),
            "original_time_s": original_time_s,
            "new_time_s": new_time_s,
            "truncated_after_session": False,
        })
    rotated.sort(key=lambda row: (float(row["timestamp"]), row.get("job_id", "")))
    return rotated, moves


def _borrow_background_calls(
    background: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if len(background) != EXPECTED_RAY_COUNT - EXPECTED_RAY_BURST_COUNT:
        raise ValueError("expected exactly 2,800 random background calls")

    remaining_by_hour = [0] * HOURS_PER_DAY
    for event in background:
        hour = int(
            _rotate_daily_time(float(event["arrival_time_s"])) // SECONDS_PER_HOUR
        )
        remaining_by_hour[hour] += 1
    initial_by_hour = list(remaining_by_hour)
    rng = random.Random(SEED + BORROWED_BACKGROUND_SEED_OFFSET)
    randomized = sorted(background, key=lambda event: rng.random())
    borrowed: list[dict[str, Any]] = []
    for event in randomized:
        if len(borrowed) == BORROWED_BACKGROUND_CALL_COUNT:
            break
        hour = int(
            _rotate_daily_time(float(event["arrival_time_s"])) // SECONDS_PER_HOUR
        )
        # Preserve at least one random background arrival in every represented hour.
        if remaining_by_hour[hour] > 1:
            borrowed.append(event)
            remaining_by_hour[hour] -= 1

    if len(borrowed) != BORROWED_BACKGROUND_CALL_COUNT:
        raise ValueError(
            "not enough background calls to borrow while preserving hourly coverage"
        )
    borrowed_ids = {str(event["job_id"]) for event in borrowed}
    remaining = [
        event for event in background if str(event["job_id"]) not in borrowed_ids
    ]
    borrowed_by_hour = [
        initial_by_hour[hour] - remaining_by_hour[hour]
        for hour in range(HOURS_PER_DAY)
    ]
    remaining_by_hour_actual = [
        sum(
            int(
                _rotate_daily_time(float(event["arrival_time_s"]))
                // SECONDS_PER_HOUR
            )
            == hour
            for event in remaining
        )
        for hour in range(HOURS_PER_DAY)
    ]
    if sum(count > 0 for count in remaining_by_hour_actual) < 20:
        raise ValueError("remaining background calls must cover at least 20 hours")

    borrowed.sort(key=lambda event: str(event["job_id"]))
    remaining.sort(
        key=lambda event: (
            float(event["arrival_time_s"]),
            str(event["job_id"]),
        )
    )
    return borrowed, remaining, {
        "selection_seed": SEED + BORROWED_BACKGROUND_SEED_OFFSET,
        "selection_method": (
            "seeded random ordering across rotated hours, accepting a call only "
            "while at least one background call remains in its hour"
        ),
        "original_background_call_count": len(background),
        "borrowed_call_count": len(borrowed),
        "borrowed_hourly_call_counts": borrowed_by_hour,
        "remaining_background_call_count": len(remaining),
        "remaining_hourly_call_counts": remaining_by_hour_actual,
    }


def _build_early_ray_arrivals(
    business_scenario: dict[str, Any],
    *,
    target_durations: list[int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    ray_cluster = next(
        cluster for cluster in business_scenario["kube_clusters"]
        if cluster.get("scheduler_type") == "RAY"
    )
    source_arrivals = ray_cluster["scheduled_arrivals"]
    original_wave_calls: list[dict[str, Any]] = []
    background: list[dict[str, Any]] = []
    for arrival in source_arrivals:
        if str(arrival["job_id"]).startswith(RAY_BURST_PREFIX):
            original_wave_calls.append(arrival)
        else:
            background.append(arrival)
    original_wave_calls.sort(key=lambda row: str(row["job_id"]))
    if len(original_wave_calls) != EXPECTED_RAY_BURST_COUNT:
        raise ValueError("business-day queue must contain 7,200 original wave calls")

    borrowed, remaining_background, borrowing = _borrow_background_calls(background)
    if len(RAY_CALL_COUNT_BY_WAVE) != WAVE_COUNT or sum(
        RAY_CALL_COUNT_BY_WAVE
    ) != EXPECTED_RAY_WAVE_CALL_COUNT:
        raise ValueError("per-wave allocation must total 8,700 calls")
    if len(RAY_INTERARRIVAL_BY_WAVE_S) != WAVE_COUNT:
        raise ValueError("each wave requires a within-wave spacing value")
    if len(RAY_IMMEDIATE_BATCH_COUNT_BY_WAVE) != WAVE_COUNT:
        raise ValueError("each wave requires an initial synchronized-batch count")

    # Interleave the original burst calls and seeded borrowers so borrowers
    # contribute to waves throughout the day instead of being placed at the end.
    wave_pool: list[tuple[dict[str, Any], str]] = []
    for index in range(max(len(original_wave_calls), len(borrowed))):
        if index < len(original_wave_calls):
            wave_pool.append((original_wave_calls[index], "original_wave"))
        if index < len(borrowed):
            wave_pool.append((borrowed[index], "borrowed_background"))

    arrivals: list[dict[str, Any]] = []
    moved_wave: list[dict[str, Any]] = []
    borrowed_records: list[dict[str, Any]] = []
    cursor = 0
    for wave_index in range(WAVE_COUNT):
        wave_start_s = FIRST_WAVE_START_S + wave_index * WAVE_INTERVAL_S
        wave_call_count = RAY_CALL_COUNT_BY_WAVE[wave_index]
        interarrival_s = RAY_INTERARRIVAL_BY_WAVE_S[wave_index]
        immediate_batches = RAY_IMMEDIATE_BATCH_COUNT_BY_WAVE[wave_index]
        wave_jobs = wave_pool[cursor : cursor + wave_call_count]
        if len(wave_jobs) != wave_call_count:
            raise ValueError(f"incomplete Ray wave {wave_index + 1}")
        for position, (event, source_kind) in enumerate(wave_jobs):
            original_time_s = float(event["arrival_time_s"])
            rotated_time_s = _rotate_daily_time(original_time_s)
            batch_index = position // RAY_WAVE_BATCH_SIZE
            new_time_s = float(
                wave_start_s
                + max(0, batch_index - immediate_batches + 1) * interarrival_s
            )
            arrivals.append({**event, "arrival_time_s": new_time_s})
            move = {
                "job_id": event["job_id"],
                "source_kind": source_kind,
                "original_time_s": original_time_s,
                "new_time_s": new_time_s,
                "duration_s": float(event["duration_s"]),
                "node_count": int(event["node_count"]),
                "hardware_profile_id": event["hardware_profile_id"],
                "wave_number": wave_index + 1,
                "wave_target_duration_s": target_durations[wave_index],
                "wave_interarrival_s": interarrival_s,
                "wave_immediate_batches": immediate_batches,
            }
            if source_kind == "borrowed_background":
                move["rotated_background_time_s"] = rotated_time_s
                borrowed_records.append(move.copy())
            moved_wave.append(move)
        cursor += wave_call_count

    if cursor != len(wave_pool):
        raise ValueError("wave allocation did not consume the complete Ray pool")

    background_rotations: list[dict[str, Any]] = []
    for event in remaining_background:
        original_time_s = float(event["arrival_time_s"])
        new_time_s = _rotate_daily_time(original_time_s)
        arrivals.append({**event, "arrival_time_s": new_time_s})
        background_rotations.append({
            "job_id": event["job_id"],
            "original_time_s": original_time_s,
            "new_time_s": new_time_s,
        })
    arrivals.sort(key=lambda row: (row["arrival_time_s"], row["job_id"]))
    moved_wave.sort(key=lambda row: row["job_id"])
    background_rotations.sort(key=lambda row: row["job_id"])
    source_draw = copy.deepcopy(
        business_scenario["provenance_proxim8_queue"][
            "background_agentic_randomization"
        ]
    )
    remaining_hourly_counts = [
        sum(
            int(move["new_time_s"] // SECONDS_PER_HOUR) == hour
            for move in background_rotations
        )
        for hour in range(HOURS_PER_DAY)
    ]
    background_provenance = {
        "source_draw": source_draw,
        **borrowing,
        "rotated_call_count": len(background_rotations),
        "rotated_hourly_call_counts": remaining_hourly_counts,
        "borrowed_calls": borrowed_records,
        "rotated_calls": background_rotations,
    }
    return arrivals, moved_wave, background_provenance


def _draw_wave_targets() -> list[int]:
    rng = random.Random(SEED + WAVE_TARGET_SEED_OFFSET)
    for _ in range(MAX_WAVE_TARGET_DRAW_ATTEMPTS):
        targets = [
            rng.randrange(
                MIN_WAVE_TARGET_S,
                MAX_WAVE_TARGET_S + WAVE_TARGET_STEP_S,
                WAVE_TARGET_STEP_S,
            )
            for _ in range(WAVE_COUNT)
        ]
        if (
            min(targets) <= SHORT_WAVE_TARGET_CEILING_S
            and max(targets) >= LONG_WAVE_TARGET_FLOOR_S
            and len(set(targets)) >= MIN_DISTINCT_WAVE_TARGETS
        ):
            return targets
    raise ValueError("could not draw qualifying varied early-wave targets")


def _k8s_counts_for_targets(targets: list[int]) -> tuple[int, ...]:
    if len(targets) != WAVE_COUNT:
        raise ValueError("one seeded target is required for each K8S cohort")
    if sum(K8S_COUNTS_BY_WAVE) != (
        EXPECTED_K8S_COUNT - MIDNIGHT_CARRY_OVER_K8S_COUNT
    ):
        raise ValueError("K8S cohorts must preserve the 995 movable sessions")
    return K8S_COUNTS_BY_WAVE


def _ray_calls_for_targets(targets: list[int]) -> tuple[int, ...]:
    ranked_indices = sorted(
        range(WAVE_COUNT),
        key=lambda index: (-targets[index], index),
    )
    calls = [RAY_BASE_CALLS_PER_CHAIN] * WAVE_COUNT
    high_background_index = ranked_indices[0]
    calls[high_background_index] = RAY_HIGH_BACKGROUND_CALLS_PER_CHAIN
    calls[0] = RAY_HIGH_CALLS_PER_CHAIN
    for index in RAY_HIGH_CALL_WAVE_INDICES:
        if index != high_background_index:
            calls[index] = RAY_HIGH_CALLS_PER_CHAIN - 1
    calls[RAY_LOW_CALL_WAVE_INDEX] = RAY_LOW_CALLS_PER_CHAIN
    if sum(calls) != RAY_CALLS_PER_CHAIN_TOTAL:
        raise ValueError("per-wave Ray allocation changed the source-chain total")
    return tuple(calls)


def _random_chain_lengths(rng: random.Random) -> list[int]:
    remaining = EXPECTED_RAY_COUNT - EXPECTED_RAY_BURST_COUNT
    lengths: list[int] = []
    for index in range(BACKGROUND_CHAIN_COUNT):
        slots_after = BACKGROUND_CHAIN_COUNT - index - 1
        minimum = max(
            BACKGROUND_MIN_CHAIN_LENGTH,
            remaining - BACKGROUND_MAX_CHAIN_LENGTH * slots_after,
        )
        maximum = min(
            BACKGROUND_MAX_CHAIN_LENGTH,
            remaining - BACKGROUND_MIN_CHAIN_LENGTH * slots_after,
        )
        length = remaining if slots_after == 0 else rng.randint(minimum, maximum)
        lengths.append(length)
        remaining -= length
    if remaining != 0 or sum(lengths) != EXPECTED_RAY_COUNT - EXPECTED_RAY_BURST_COUNT:
        raise ValueError("background chain partition changed the Ray call count")
    if not all(
        BACKGROUND_MIN_CHAIN_LENGTH <= length <= BACKGROUND_MAX_CHAIN_LENGTH
        for length in lengths
    ):
        raise ValueError("background chain length is outside the proposed range")
    return lengths


def _weighted_chain_hours(rng: random.Random) -> list[int]:
    if len(BACKGROUND_HOUR_WEIGHTS) != HOURS_PER_DAY:
        raise ValueError("one background weight is required for each hour")
    available = list(range(HOURS_PER_DAY))
    chosen: list[int] = []
    for _ in range(HOURS_PER_DAY):
        weights = [BACKGROUND_HOUR_WEIGHTS[hour] for hour in available]
        hour = rng.choices(available, weights=weights, k=1)[0]
        chosen.append(hour)
        available.remove(hour)
    for _ in range(BACKGROUND_CHAIN_COUNT - HOURS_PER_DAY):
        chosen.append(
            rng.choices(
                range(HOURS_PER_DAY),
                weights=BACKGROUND_HOUR_WEIGHTS,
                k=1,
            )[0]
        )
    return chosen


def _build_random_background(
    events: list[dict[str, Any]],
    ends: dict[str, float],
    *,
    attempt_number: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    expected_background_count = EXPECTED_RAY_COUNT - EXPECTED_RAY_BURST_COUNT
    if len(events) != expected_background_count:
        raise ValueError("unexpected non-wave Ray call count")
    if attempt_number < 1:
        raise ValueError("background attempt numbers are one-based")
    attempt_seed = SEED + BACKGROUND_SEED_OFFSET + attempt_number
    rng = random.Random(attempt_seed)
    lengths = _random_chain_lengths(rng)
    hours = _weighted_chain_hours(rng)
    ordered = sorted(
        events,
        key=lambda event: (float(event["timestamp"]), event["job_id"]),
    )
    cursor = 0
    arrivals: list[dict[str, Any]] = []
    moved_calls: list[dict[str, Any]] = []
    hourly_counts = [0] * HOURS_PER_DAY

    for chain_index, (length, hour) in enumerate(zip(lengths, hours), start=1):
        chain_events = ordered[cursor : cursor + length]
        cursor += length
        gaps = [
            rng.randint(BACKGROUND_MIN_GAP_S, BACKGROUND_MAX_GAP_S)
            for _ in range(length - 1)
        ]
        offsets = [0]
        for gap in gaps:
            offsets.append(offsets[-1] + gap)
        latest_start_offset = SECONDS_PER_HOUR - 1 - offsets[-1]
        chain_start_s = hour * SECONDS_PER_HOUR + rng.randint(
            0, latest_start_offset
        )
        chain_id = f"ray-agentic-background-{chain_index:02d}"
        for position, (event, offset) in enumerate(
            zip(chain_events, offsets),
            start=1,
        ):
            original_time_s = float(event["timestamp"])
            new_time_s = float(chain_start_s + offset)
            arrivals.append(
                _scheduled_arrival(
                    event,
                    original_time_s=original_time_s,
                    arrival_time_s=new_time_s,
                    end_time_s=ends[event["job_id"]],
                )
            )
            moved_calls.append({
                "job_id": event["job_id"],
                "original_time_s": original_time_s,
                "new_time_s": new_time_s,
                "chain_id": chain_id,
                "chain_position": position,
                "chain_length": length,
                "gap_before_s": 0 if position == 1 else gaps[position - 2],
            })
            hourly_counts[int(new_time_s // SECONDS_PER_HOUR)] += 1
    if cursor != len(ordered) or any(count == 0 for count in hourly_counts):
        raise ValueError("background draw did not cover all calls and hours")
    return arrivals, {
        "seed": attempt_seed,
        "attempt_number": attempt_number,
        "rejected_attempt_count": attempt_number - 1,
        "call_count": len(moved_calls),
        "chain_lengths": lengths,
        "hourly_weights": list(BACKGROUND_HOUR_WEIGHTS),
        "hourly_call_counts": hourly_counts,
        "calls": sorted(moved_calls, key=lambda item: item["job_id"]),
    }


def _build_k8s_arrivals(
    source: dict[str, Any],
    rng: random.Random,
    counts_by_wave: tuple[int, ...],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    starts = _start_events(source, "K8S")
    ends = _end_times(source, "K8S")
    carry_over = [
        event for event in starts if float(event["timestamp"]) == 0.0
    ]
    movable = [
        event for event in starts if float(event["timestamp"]) != 0.0
    ]
    if len(starts) != EXPECTED_K8S_COUNT:
        raise ValueError(f"expected {EXPECTED_K8S_COUNT} K8S starts")
    if len(carry_over) != MIDNIGHT_CARRY_OVER_K8S_COUNT:
        raise ValueError("expected exactly five midnight carry-over sessions")
    if sum(counts_by_wave) != len(movable):
        raise ValueError("K8S wave allocations must cover every movable session")

    rng.shuffle(movable)
    high_node_events = [
        event for event in movable if int(event["node_count"]) > 1
    ]
    single_node_events = [
        event for event in movable if int(event["node_count"]) <= 1
    ]
    wave_groups: list[list[dict[str, Any]]] = [
        [] for _ in range(WAVE_COUNT)
    ]
    remaining_by_wave = list(counts_by_wave)
    for position, event in enumerate(high_node_events):
        preferred_wave = K8S_HIGH_NODE_WAVE_INDICES[
            position % len(K8S_HIGH_NODE_WAVE_INDICES)
        ]
        if remaining_by_wave[preferred_wave] > 0:
            wave_groups[preferred_wave].append(event)
            remaining_by_wave[preferred_wave] -= 1
        else:
            available = [
                wave_index
                for wave_index, remaining in enumerate(remaining_by_wave)
                if remaining > 0
            ]
            chosen_wave = rng.choice(available)
            wave_groups[chosen_wave].append(event)
            remaining_by_wave[chosen_wave] -= 1
    for event in single_node_events:
        available = [
            wave_index
            for wave_index, remaining in enumerate(remaining_by_wave)
            if remaining > 0
        ]
        if not available:
            raise ValueError("K8S wave allocation ran out of slots")
        chosen_wave = rng.choice(available)
        wave_groups[chosen_wave].append(event)
        remaining_by_wave[chosen_wave] -= 1
    if any(remaining_by_wave):
        raise ValueError("K8S wave allocation left empty slots")

    arrivals: list[dict[str, Any]] = []
    moved: list[dict[str, Any]] = []
    for wave_index, wave_count in enumerate(counts_by_wave):
        wave_start = FIRST_WAVE_START_S + wave_index * WAVE_INTERVAL_S
        window_start = max(0, wave_start - K8S_LEAD_WINDOW_S)
        next_window_start = (
            wave_start + WAVE_INTERVAL_S - K8S_LEAD_WINDOW_S
        )
        wave_events = wave_groups[wave_index]
        if len(wave_events) != wave_count:
            raise ValueError("K8S wave group differs from its declared count")
        for event in wave_events:
            original_time_s = float(event["timestamp"])
            duration_s = ends[event["job_id"]] - original_time_s
            earliest_while_active = wave_start - duration_s + TICK_SECONDS
            latest_before_wave = wave_start - TICK_SECONDS
            latest_before_next_window = next_window_start - duration_s
            earliest_arrival = max(window_start, earliest_while_active)
            latest_arrival = min(
                latest_before_wave,
                latest_before_next_window,
            )
            first_tick = math.ceil(earliest_arrival / TICK_SECONDS)
            last_tick = math.floor(latest_arrival / TICK_SECONDS)
            if first_tick > last_tick:
                raise ValueError(
                    "K8S event cannot be placed active at its wave and "
                    "finished before the next lead window"
                )
            arrival_time_s = rng.randint(first_tick, last_tick) * TICK_SECONDS
            arrivals.append(
                _scheduled_arrival(
                    event,
                    original_time_s=original_time_s,
                    arrival_time_s=float(arrival_time_s),
                    end_time_s=ends[event["job_id"]],
                )
            )
            moved.append(
                _provenance_move(
                    event,
                    original_time_s=original_time_s,
                    new_time_s=float(arrival_time_s),
                    end_time_s=ends[event["job_id"]],
                )
            )

    for event in carry_over:
        original_time_s = float(event["timestamp"])
        arrivals.append(
            _scheduled_arrival(
                event,
                original_time_s=original_time_s,
                arrival_time_s=original_time_s,
                end_time_s=ends[event["job_id"]],
            )
        )
    arrivals.sort(key=lambda row: (row["arrival_time_s"], row["job_id"]))
    moved.sort(key=lambda row: row["job_id"])
    return arrivals, moved


def _build_ray_arrivals(
    source: dict[str, Any],
    *,
    background_attempt: int,
    calls_by_wave: tuple[int, ...],
    target_durations: list[int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    starts = _start_events(source, "RAY")
    ends = _end_times(source, "RAY")
    chains: dict[str, list[dict[str, Any]]] = {}
    for event in starts:
        job_id = event["job_id"]
        if job_id.startswith(RAY_BURST_PREFIX):
            chain_id, _ = job_id[len(RAY_BURST_PREFIX) :].split("-", 1)
            chains.setdefault(chain_id, []).append(event)
    for events in chains.values():
        events.sort(key=lambda event: int(event["job_id"].rsplit("-", 1)[1]))

    if (
        len(starts) != EXPECTED_RAY_COUNT
        or len(chains) != RAY_SOURCE_CHAIN_COUNT
    ):
        raise ValueError("unexpected Ray source count or burst-chain count")
    if sum(map(len, chains.values())) != EXPECTED_RAY_BURST_COUNT:
        raise ValueError("unexpected number of source Ray burst calls")

    arrivals: list[dict[str, Any]] = []
    moved: list[dict[str, Any]] = []
    cursors = {chain_id: 0 for chain_id in chains}
    moved_ids: set[str] = set()
    for wave_index in range(WAVE_COUNT):
        wave_start = FIRST_WAVE_START_S + wave_index * WAVE_INTERVAL_S
        for chain_id, events in chains.items():
            cursor = cursors[chain_id]
            calls_this_wave = calls_by_wave[wave_index]
            wave_events = events[
                cursor : cursor + calls_this_wave
            ]
            if len(wave_events) != calls_this_wave:
                raise ValueError(f"incomplete source chain {chain_id}")
            for offset, event in enumerate(wave_events):
                original_time_s = float(event["timestamp"])
                arrival_time_s = float(
                    wave_start
                    + (offset // 2) * RAY_PAIR_SPACING_S
                )
                arrivals.append(
                    _scheduled_arrival(
                        event,
                        original_time_s=original_time_s,
                        arrival_time_s=arrival_time_s,
                        end_time_s=ends[event["job_id"]],
                    )
                )
                moved.append(
                    _provenance_move(
                        event,
                        original_time_s=original_time_s,
                        new_time_s=arrival_time_s,
                        end_time_s=ends[event["job_id"]],
                    )
                )
                moved[-1]["wave_number"] = wave_index + 1
                moved[-1]["wave_target_duration_s"] = (
                    target_durations[wave_index]
                )
                moved_ids.add(event["job_id"])
            cursors[chain_id] += calls_this_wave

    background_events = [
        event for event in starts if event["job_id"] not in moved_ids
    ]
    background_arrivals, background_provenance = _build_random_background(
        background_events,
        ends,
        attempt_number=background_attempt,
    )
    arrivals.extend(background_arrivals)
    if len(moved) != EXPECTED_RAY_BURST_COUNT:
        raise ValueError("not all original Ray burst calls were moved")
    arrivals.sort(key=lambda row: (row["arrival_time_s"], row["job_id"]))
    moved.sort(key=lambda row: row["job_id"])
    return arrivals, moved, background_provenance


def build_scenario() -> dict[str, Any]:
    baseline = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    business = json.loads(QUEUE_TEMPLATE_PATH.read_text(encoding="utf-8"))
    if baseline.get("end_sim_time") != SECONDS_PER_DAY:
        raise ValueError("the source Proxim8 scenario is not a 24-hour run")
    if len(_start_events(baseline, "SLURM")) != EXPECTED_SLURM_COUNT:
        raise ValueError("the source Slurm count changed unexpectedly")

    target_durations = _draw_wave_targets()
    if tuple(target_durations) != CALIBRATION_TARGET_DURATIONS_S:
        raise ValueError("seeded duration targets differ from the recorded calibration")
    k8s_cluster = next(
        cluster for cluster in business["kube_clusters"]
        if cluster.get("scheduler_type") == "K8S"
    )
    rotated_k8s, moved_k8s = _rotate_scheduled_arrivals(
        k8s_cluster["scheduled_arrivals"]
    )
    ray_arrivals, moved_ray, background_provenance = _build_early_ray_arrivals(
        business,
        target_durations=target_durations,
    )
    rotated_slurm, moved_slurm = _rotate_slurm_events(
        business["workload_events"]
    )

    scenario = copy.deepcopy(business)
    scenario["name"] = "Proxim8 — queue-stress early"
    scenario["description"] = (
        baseline["description"]
        + "\n\nQueue-stress early variant (DR-2026-11-05-PROXIM8-EARLY-0900, "
        "PROPOSED_HERE): the session starts at local 09:00. The complete "
        "business-day timeline is rotated by nine hours: Slurm and K8S keep "
        "their original local arrival times. Of the 2,800 seeded random Ray "
        "background calls, 1,500 are selected across the rotated day and moved "
        "into the wave pool; 1,300 remain random background arrivals, with "
        "calls left in every hour. The building non-GPU load curve is rotated "
        "by the same amount. The five "
        "K8S midnight carry-over sessions therefore appear at the session's "
        "15:00 mark. The 7,200 former Ray burst calls plus 1,500 borrowed "
        "background calls form ten stress waves at "
        "local 09:15, 10:15, and hourly through 18:15. The engine has no "
        "session-start-hour field: PG&E B-20 TOU periods still use simulated "
        "hours from midnight, so tariff periods are offset from local time by "
        "nine hours in this variant (PROPOSED_HERE). No physics, admission, "
        "cooling, dispatch, or engine behavior is changed. The 12-trial "
        "calibration did not meet the 60-second minimum on every wave; the "
        "best trial is diagnostic only and is not acceptance-ready."
    )
    scenario["non_gpu_load_profile_mw"] = _rotate_daily_profile(
        baseline["non_gpu_load_profile_mw"]
    )
    scenario["workload_events"] = rotated_slurm
    for cluster in scenario["kube_clusters"]:
        if cluster["scheduler_type"] == "K8S":
            cluster["scheduled_arrivals"] = rotated_k8s
        elif cluster["scheduler_type"] == "RAY":
            cluster["scheduled_arrivals"] = ray_arrivals
        else:
            raise ValueError(
                f"unexpected cluster scheduler {cluster['scheduler_type']}"
            )

    wave_times = [
        FIRST_WAVE_START_S + index * WAVE_INTERVAL_S
        for index in range(WAVE_COUNT)
    ]
    scenario.pop("provenance_proxim8_queue", None)
    scenario["provenance_proxim8_queue_early"] = {
        "seed": SEED,
        "decision_record": (
            "DR-2026-11-05-PROXIM8-EARLY-0900 (PROPOSED_HERE)"
        ),
        "timeline_source": "proxim8-5mw-24h-queue.json",
        "clock_rotation": {
            "session_start_local_hour": SESSION_START_LOCAL_HOUR,
            "rotation_seconds": SESSION_START_OFFSET_S,
            "mapping": "(source_time - 09:00) modulo 24 hours",
            "edl_time_basis": (
                "EDL hour is sim_time_seconds // 3600 % 24; no scenario "
                "session-start-hour override exists, so B-20 is 9 hours "
                "behind site local time."
            ),
        },
        "wave_count": WAVE_COUNT,
        "wave_start_times_sim_seconds": wave_times,
        "wave_start_times_local": [
            f"{SESSION_START_LOCAL_HOUR + (FIRST_LOCAL_WAVE_OFFSET_S // 3600) + index:02d}:"
            f"{(FIRST_LOCAL_WAVE_OFFSET_S % 3600) // 60:02d}"
            for index in range(WAVE_COUNT)
        ],
        "target_durations_seconds": target_durations,
        "target_seed": SEED + WAVE_TARGET_SEED_OFFSET,
        "original_ray_wave_call_count": EXPECTED_RAY_BURST_COUNT,
        "borrowed_background_call_count": BORROWED_BACKGROUND_CALL_COUNT,
        "ray_call_count_by_wave": list(RAY_CALL_COUNT_BY_WAVE),
        "ray_interarrival_by_wave_s": list(RAY_INTERARRIVAL_BY_WAVE_S),
        "ray_immediate_batch_count_by_wave": list(
            RAY_IMMEDIATE_BATCH_COUNT_BY_WAVE
        ),
        "calibration_max_iterations": CALIBRATION_MAX_ITERATIONS,
        "calibration_status": (
            "infeasible_after_12_trials: best_trial_6_has_three_episodes_"
            "below_60_seconds"
        ),
        "selected_calibration_iteration": 6,
        "calibration_iteration_log": [
            {
                "iteration": entry["iteration"],
                "calls_by_wave": list(entry["calls_by_wave"]),
                "interarrival_s_by_wave": list(entry["interarrival_s_by_wave"]),
                "immediate_batches_by_wave": list(
                    entry["immediate_batches_by_wave"]
                ),
                "measured_episode_durations_s": list(
                    entry["measured_episode_durations_s"]
                ),
            }
            for entry in CALIBRATION_ITERATION_LOG
        ],
        "best_trial_episode_summary": {
            "measured_durations_s": [60, 60, 60, 60, 55, 55, 340, 65, 70, 40],
            "peak_held_jobs": [1128, 1065, 992, 995, 823, 182, 536, 306, 443, 796],
            "peak_requested_demand_mw": [
                22.328, 21.367, 20.236, 20.284, 17.622,
                7.770, 13.460, 9.691, 11.831, 14.513,
            ],
            "peak_drawn_demand_mw": [
                4.400, 4.441, 4.470, 4.470, 4.543,
                4.880, 4.941, 4.822, 4.786, 4.249,
            ],
        },
        "ray_wave_call_count": len(moved_ray),
        "ray_calls_by_sim_hour": [
            sum(
                int(float(event["arrival_time_s"]) // SECONDS_PER_HOUR) == hour
                for event in ray_arrivals
            )
            for hour in range(HOURS_PER_DAY)
        ],
        "ray_background_rotation": background_provenance,
        "k8s_rotated_count": len(moved_k8s),
        "k8s_rotated_arrivals": moved_k8s,
        "slurm_rotated_events": moved_slurm,
        "moved_ray_calls": moved_ray,
        "moved_job_count": (
            len(moved_k8s)
            + len(moved_ray)
            + len(background_provenance["rotated_calls"])
            + sum(
                item["event_type"] == "starting"
                for item in moved_slurm
            )
        ),
        "proposed_here": [
            "Session local start 09:00; all original-day inputs are rotated by nine hours.",
            "The five midnight K8S carry-over sessions rotate to the following-night position.",
            "Ten Ray wave starts are 09:15 through 18:15 local, one hour apart.",
            "Exactly 1,500 background Ray calls are selected by a separate seeded draw and moved into the ten waves; remaining background calls stay spread across at least 20 hours.",
            "The 7,200 original wave calls plus borrowed background calls are allocated by per-wave counts and within-wave spacing.",
            "PG&E B-20 uses sim time from midnight, so its periods are offset by nine hours from local time.",
        ],
    }
    return scenario


def main() -> None:
    scenario = build_scenario()
    OUTPUT_PATH.write_text(
        json.dumps(scenario, ensure_ascii=False, indent=2, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT_PATH}")
    for cluster in scenario["kube_clusters"]:
        print(
            f"{cluster['scheduler_type']} arrivals: "
            f"{len(cluster['scheduled_arrivals'])}"
        )
    provenance = scenario["provenance_proxim8_queue_early"]
    print(f"Wave targets: {provenance['target_durations_seconds']}")
    print(f"Ray calls by wave: {provenance['ray_call_count_by_wave']}")
    print(f"Calibration status: {provenance['calibration_status']}")
    print(
        "Calibration iterations: "
        f"{len(provenance['calibration_iteration_log'])}"
    )
    print(f"Rotated background counts per hour: {provenance['ray_background_rotation']['rotated_hourly_call_counts']}")


if __name__ == "__main__":
    main()
