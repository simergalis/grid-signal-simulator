#!/usr/bin/env python3
"""Generate the separate early-wave Proxim8 queue-stress scenario."""

from __future__ import annotations

import copy
import json
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
# PROPOSED_HERE: arrivals are staged over ten minutes immediately before each wave.
K8S_LEAD_WINDOW_S = 600
# PROPOSED_HERE: the allocation redistributes all 995 non-midnight sessions while
# balancing measured 60-second minimum episodes under the accepted lower baseline.
K8S_COUNTS_BY_WAVE = (130, 120, 100, 110, 110, 89, 89, 79, 89, 79)
# PROPOSED_HERE: all forty source Ray chains contribute eighteen existing calls
# to each wave; no call is added, removed, or rewritten.
RAY_CALLS_PER_CHAIN_PER_WAVE = 18
# PROPOSED_HERE: pairs of calls arrive two seconds apart inside each wave.
RAY_PAIR_SPACING_S = 2
EXPECTED_K8S_COUNT = 1000
EXPECTED_RAY_COUNT = 10000
EXPECTED_RAY_BURST_COUNT = 7200
EXPECTED_SLURM_COUNT = 10
TICK_SECONDS = 5
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


def _build_k8s_arrivals(
    source: dict[str, Any],
    rng: random.Random,
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
    if len(carry_over) != 5:
        raise ValueError("expected exactly five midnight carry-over sessions")
    if sum(K8S_COUNTS_BY_WAVE) != len(movable):
        raise ValueError("K8S wave allocations must cover every movable session")

    rng.shuffle(movable)
    arrivals: list[dict[str, Any]] = []
    moved: list[dict[str, Any]] = []
    cursor = 0
    for wave_index, wave_count in enumerate(K8S_COUNTS_BY_WAVE):
        wave_start = FIRST_WAVE_START_S + wave_index * WAVE_INTERVAL_S
        window_start = wave_start - K8S_LEAD_WINDOW_S
        wave_events = movable[cursor : cursor + wave_count]
        cursor += wave_count
        for position, event in enumerate(wave_events):
            # Distribute deterministically in the lead window and align to the
            # engine's five-second tick. The clamp guarantees arrival before
            # the Ray wave even when integer division lands on its boundary.
            arrival_time_s = (
                (window_start + position * K8S_LEAD_WINDOW_S // wave_count)
                // TICK_SECONDS
                * TICK_SECONDS
            )
            arrival_time_s = min(arrival_time_s, wave_start - TICK_SECONDS)
            original_time_s = float(event["timestamp"])
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
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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

    if len(starts) != EXPECTED_RAY_COUNT or len(chains) != 40:
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
            wave_events = events[
                cursor : cursor + RAY_CALLS_PER_CHAIN_PER_WAVE
            ]
            if len(wave_events) != RAY_CALLS_PER_CHAIN_PER_WAVE:
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
                moved_ids.add(event["job_id"])
            cursors[chain_id] += RAY_CALLS_PER_CHAIN_PER_WAVE

    for event in starts:
        if event["job_id"] in moved_ids:
            continue
        original_time_s = float(event["timestamp"])
        arrivals.append(
            _scheduled_arrival(
                event,
                original_time_s=original_time_s,
                arrival_time_s=original_time_s,
                end_time_s=ends[event["job_id"]],
            )
        )
    if len(moved) != EXPECTED_RAY_BURST_COUNT:
        raise ValueError("not all original Ray burst calls were moved")
    arrivals.sort(key=lambda row: (row["arrival_time_s"], row["job_id"]))
    moved.sort(key=lambda row: row["job_id"])
    return arrivals, moved


def build_scenario() -> dict[str, Any]:
    source = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    template = json.loads(QUEUE_TEMPLATE_PATH.read_text(encoding="utf-8"))
    rng = random.Random(SEED)
    k8s_arrivals, moved_k8s = _build_k8s_arrivals(source, rng)
    ray_arrivals, moved_ray = _build_ray_arrivals(source)

    scenario = copy.deepcopy(template)
    scenario["name"] = "Proxim8 — queue-stress early"
    scenario["description"] = (
        source["description"]
        + "\n\nQueue-stress early variant: ten Ray waves begin at 00:15, "
        "then hourly through 09:15. All 7,200 calls from the original "
        "16:35 Ray burst are redistributed across the waves; all other Ray "
        "calls remain at their source times. The 995 non-midnight K8S "
        "sessions are moved into ten-minute pre-wave windows and retain "
        "their original IDs, models, durations, node counts and profiles; "
        "the five midnight carry-over sessions remain at 00:00. The approved "
        "lower pre-wave target is intentional: with the fixed 1,000-session "
        "count and source durations, pre-wave demand remains below the "
        "5.0 MW cap, while requested demand exceeds the cap during each "
        "Ray wave and the admission gate holds jobs. DR-2026-11-03-PROXIM8-"
        "QUEUE (PROPOSED_HERE): early hourly waves and the seeded K8S "
        "reallocation are a separate scenario; no engine, admission, "
        "physics, cooling or dispatch behavior changes."
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
            "Keep the source K8S/Ray jobs and their physical attributes. "
            "Move the 995 non-midnight K8S sessions into ten-minute windows "
            "before hourly Ray waves; spread the original 7,200-call Ray "
            "burst evenly as 18 sequential calls from each of 40 chains "
            "per wave. Other Ray arrivals and the five midnight K8S "
            "carry-over sessions retain their source arrival times."
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
        "k8s_counts_by_wave": list(K8S_COUNTS_BY_WAVE),
        "ray_moved_count": len(moved_ray),
        "ray_calls_per_chain_per_wave": RAY_CALLS_PER_CHAIN_PER_WAVE,
        "ray_chain_count": len({
            event["job_id"][len(RAY_BURST_PREFIX) :].split("-", 1)[0]
            for event in _start_events(source, "RAY")
            if event["job_id"].startswith(RAY_BURST_PREFIX)
        }),
        "moved_job_count": len(moved_k8s) + len(moved_ray),
        "moved_k8s_jobs": moved_k8s,
        "moved_ray_calls": moved_ray,
        "proposed_here": [
            "Ten waves at 00:15 and hourly: selected by user decision.",
            "K8S counts per wave: balanced for ten measured held episodes.",
            "Ten-minute K8S lead window: staged background before each wave.",
            "18 Ray calls per source chain per wave: preserves all 7,200 calls.",
            "Lower pre-wave demand target: approved by user to preserve counts and durations.",
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


if __name__ == "__main__":
    main()
