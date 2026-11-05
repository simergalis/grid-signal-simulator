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

# PROPOSED_HERE: preserve the approved deterministic Proxim8 seed.
SEED = 20261102
# PROPOSED_HERE: ten early queue waves provide hourly stress points.
WAVE_COUNT = 10
# PROPOSED_HERE: the first queue wave begins fifteen minutes after midnight.
FIRST_WAVE_START_S = 900
# PROPOSED_HERE: hourly starts match the user's requested spacing.
WAVE_INTERVAL_S = 3600
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


def build_scenario(*, background_attempt: int | None = None) -> dict[str, Any]:
    attempt_number = (
        BACKGROUND_ATTEMPT if background_attempt is None else background_attempt
    )
    source = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    template = json.loads(QUEUE_TEMPLATE_PATH.read_text(encoding="utf-8"))
    if source.get("end_sim_time") != SECONDS_PER_DAY:
        raise ValueError("the source Proxim8 scenario is not a 24-hour run")
    if len(_start_events(source, "SLURM")) != EXPECTED_SLURM_COUNT:
        raise ValueError("the source Slurm count changed unexpectedly")
    rng = random.Random(SEED)
    target_durations = _draw_wave_targets()
    k8s_counts = _k8s_counts_for_targets(target_durations)
    ray_calls_by_wave = _ray_calls_for_targets(target_durations)
    k8s_arrivals, moved_k8s = _build_k8s_arrivals(
        source,
        rng,
        k8s_counts,
    )
    ray_arrivals, moved_ray, background_provenance = _build_ray_arrivals(
        source,
        background_attempt=attempt_number,
        calls_by_wave=ray_calls_by_wave,
        target_durations=target_durations,
    )

    scenario = copy.deepcopy(template)
    scenario["name"] = "Proxim8 — queue-stress early"
    scenario["description"] = (
        source["description"]
        + "\n\nQueue-stress early variant: ten Ray waves begin at 00:15, "
        "then hourly through 09:15. All 7,200 calls from the original "
        "16:35 Ray burst are redistributed across the waves; all other Ray "
        "calls are regenerated as seeded random chains across all 24 hours. "
        "The 995 non-midnight K8S sessions are moved into one-minute "
        "pre-wave windows under a front-loaded K8S background profile; Ray-call "
        "counts per wave use the seeded duration-target ranking. They retain "
        "their original IDs, models, durations, node counts and profiles; "
        "the five midnight carry-over sessions remain at 00:00. The approved "
        "lower pre-wave target is intentional: K8S sessions provide varied "
        "background levels while remaining below the 5.0 MW cap. "
        "DR-2026-11-03-PROXIM8-QUEUE (PROPOSED_HERE): early hourly waves and "
        "the seeded K8S reallocation are a separate scenario; no engine, "
        "admission, physics, cooling or dispatch behavior changes. "
        "DR-2026-11-04-PROXIM8-AGENTIC-RANDOM (PROPOSED_HERE): non-wave "
        "agentic calls use seeded weighted-hour chains with 5–200 calls and "
        "1–10 second gaps; wave starts remain hourly and duration targets "
        "are seeded per wave."
    )
    scenario["workload_events"] = [
        event
        for event in source["workload_events"]
        if event.get("scheduler_type") == "SLURM"
    ]
    for cluster in scenario["kube_clusters"]:
        if cluster["scheduler_type"] == "K8S":
            cluster["scheduled_arrivals"] = k8s_arrivals
        elif cluster["scheduler_type"] == "RAY":
            cluster["scheduled_arrivals"] = ray_arrivals
        else:
            raise ValueError(
                f"unexpected cluster scheduler {cluster['scheduler_type']}"
            )
    scenario.pop("provenance_proxim8_queue", None)
    scenario["provenance_proxim8_queue_early"] = {
        "seed": SEED,
        "decision_record": "DR-2026-11-03-PROXIM8-QUEUE (PROPOSED_HERE)",
        "surge_method": (
            "Keep source job identities and physical attributes. Move the "
            "995 non-midnight K8S sessions into one-minute windows before "
            "hourly Ray waves using the documented front-loaded count profile. "
            "Spread the original 7,200-call Ray "
            "burst redistributed sequentially across waves according to the "
            "seeded duration ranking. Other Ray arrival times are regenerated as seeded "
            "weighted-hour background chains; five midnight K8S carry-over "
            "sessions retain their source arrival times."
        ),
        "agentic_randomization_record": (
            "DR-2026-11-04-PROXIM8-AGENTIC-RANDOM (PROPOSED_HERE)"
        ),
        "background_method": (
            "The 2,800 non-wave Ray calls are regrouped into 28 seeded chains "
            "of 5–200 calls, with randomized 1–10 second gaps and weighted "
            "start hours. A thin overnight tail and all-hour coverage are "
            "retained; chain lengths, gaps and every old/new timestamp are "
            "recorded below."
        ),
        "first_wave_start_s": FIRST_WAVE_START_S,
        "wave_interval_s": WAVE_INTERVAL_S,
        "wave_count": WAVE_COUNT,
        "wave_start_times_s": [
            FIRST_WAVE_START_S + index * WAVE_INTERVAL_S
            for index in range(WAVE_COUNT)
        ],
        "k8s_lead_window_s": K8S_LEAD_WINDOW_S,
        "k8s_moved_count": len(moved_k8s),
        "k8s_counts_by_wave": list(k8s_counts),
        "target_durations_seconds": target_durations,
        "target_seed": SEED + WAVE_TARGET_SEED_OFFSET,
        "target_draw_attempt_limit": MAX_WAVE_TARGET_DRAW_ATTEMPTS,
        "ray_moved_count": len(moved_ray),
        "ray_calls_per_chain_by_wave": list(ray_calls_by_wave),
        "ray_call_count_by_wave": [
            calls * RAY_SOURCE_CHAIN_COUNT for calls in ray_calls_by_wave
        ],
        "ray_chain_count": len({
            event["job_id"][len(RAY_BURST_PREFIX) :].split("-", 1)[0]
            for event in _start_events(source, "RAY")
            if event["job_id"].startswith(RAY_BURST_PREFIX)
        }),
        "moved_job_count": len(moved_k8s) + len(moved_ray),
        "background_agentic_randomization": background_provenance,
        "moved_k8s_jobs": moved_k8s,
        "moved_ray_calls": moved_ray,
        "proposed_here": [
            "Ten waves at 00:15 and hourly: selected by user decision.",
            "K8S counts per wave: balanced for ten measured held episodes.",
            "Ten-minute K8S lead window: staged background before each wave.",
            "Target-ranked Ray calls per source chain vary by wave and sum to 180 per chain.",
            "Lower pre-wave demand target: approved by user to preserve counts and durations.",
            "Seeded target durations rank the per-wave Ray call counts; the front-loaded K8S profile retains all 995 movable sessions.",
            "Seeded weighted-hour background chains randomize only non-wave Ray arrival times; job IDs and physical attributes are unchanged.",
            "The recorded background attempt is the accepted deterministic redraw after checking held-queue telemetry.",
        ],
    }
    return scenario


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--background-attempt",
        type=int,
        default=BACKGROUND_ATTEMPT,
        help="one-based deterministic background draw attempt",
    )
    args = parser.parse_args()
    scenario = build_scenario(background_attempt=args.background_attempt)
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
    print(
        f"Wave targets: {provenance['target_durations_seconds']}; "
        f"K8S counts: {provenance['k8s_counts_by_wave']}"
    )
    print(
        f"Background attempt "
        f"{provenance['background_agentic_randomization']['attempt_number']}; "
        f"Ray calls per hour: "
        f"{provenance['background_agentic_randomization']['hourly_call_counts']}"
    )


if __name__ == "__main__":
    main()
