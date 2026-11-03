#!/usr/bin/env python3
"""Generate the opt-in Proxim8 queue-stress scenario without touching Proxim8."""

from __future__ import annotations

import json
import random
from collections import defaultdict
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
OUTPUT_PATH = PACKAGE_ROOT / "config" / "scenarios" / "proxim8-5mw-24h-queue.json"

# Every numeric assumption is tagged with its rationale. The seed itself was
# specified by the approved Proxim8 design; all queue-shaping values are
# illustrative, opt-in scenario assumptions.
N = {
    "SEED": 20261102,  # PROPOSED_HERE: fixed by the approved Proxim8 scenario request.
    "ZERO": 0,  # PROPOSED_HERE: zero-based index and no-delay sentinel.
    "ONE": 1,  # PROPOSED_HERE: index increment and single-node admission.
    "TWO": 2,  # PROPOSED_HERE: K8S session size for the requested minority share.
    "THREE": 3,  # PROPOSED_HERE: three business-day episode groups.
    "FOUR": 4,  # PROPOSED_HERE: first group has four episodes; remaining groups have three each.
    "TEN": 10,  # PROPOSED_HERE: required number of held queue episodes and Ray burst groups.
    "K8S_MIDNIGHT_CARRYOVER_COUNT": 5,  # PROPOSED_HERE: preserve the approved 24/7 inference carry-over sessions.
    "NINETEEN": 19,  # PROPOSED_HERE: two-node K8S jobs per 194-session near-cap cohort.
    "ONE_HUNDRED_SEVENTY_FOUR": 174,  # PROPOSED_HERE: single-node cohort jobs; with 19 doubles totals 212 nodes.
    "ONE_HUNDRED_NINETY_THREE": 193,  # PROPOSED_HERE: cohort size excluding its separate one-node anchor.
    "ONE_HUNDRED_NINETY_FOUR": 194,  # PROPOSED_HERE: one-node anchor plus cohort.
    "FOUR_HUNDRED_SIX": 406,  # PROPOSED_HERE: non-cohort K8S sessions after preserving five midnight carry-overs.
    "FIFTY": 50,  # PROPOSED_HERE: overnight remainder count.
    "TWO_HUNDRED_TWENTY": 220,  # PROPOSED_HERE: morning remainder count preserves business-day arrivals.
    "ONE_HUNDRED_THIRTY_SIX": 136,  # PROPOSED_HERE: evening remainder count; totals 406 with overnight and morning.
    "TEN_THOUSAND": 10000,  # PROPOSED_HERE: required Ray agentic-call count.
    "NINE_NINETY_NINE": 999,  # PROPOSED_HERE: calls in each of ten non-episode Ray bursts.
    "ONE_HUNDRED": 100,  # PROPOSED_HERE: calls per Ray burst chain.
    "SIXTY": 60,  # PROPOSED_HERE: lower queue-duration bound, one minute.
    "FOUR_HUNDRED_TWENTY": 420,  # PROPOSED_HERE: upper queue-duration bound, seven minutes.
    "FIVE": 5,  # PROPOSED_HERE: simulator tick and minimum inter-episode clearance.
    "TWENTY": 20,  # PROPOSED_HERE: gap before a replacement K8S session uses a released node.
    "TWENTY_FIVE": 25,  # PROPOSED_HERE: release-tick adjustment for the next episode start.
    "THIRTY_FIVE": 55,  # PROPOSED_HERE: leaves one full minute between replacement start and the next window.
    "THREE_HUNDRED": 300,  # PROPOSED_HERE: five-minute cohort prefill and minimum K8S session duration.
    "THREE_THOUSAND": 3000,  # PROPOSED_HERE: minimum source duration for a cohort that remains active through its window block.
    "SIXTY_FOUR_HUNDRED": 6400,  # PROPOSED_HERE: upper bound for background K8S arrival timestamps.
    "THREE_THOUSAND_SIX_HUNDRED": 3600,  # PROPOSED_HERE: seconds per hour and maximum source session duration.
    "EIGHTY_SIX_THOUSAND_FOUR_HUNDRED": 86400,  # PROPOSED_HERE: 24-hour scenario horizon.
    "ONE_THOUSAND": 1000,  # PROPOSED_HERE: required K8S session count.
    "ONE_THOUSAND_EIGHT_HUNDRED": 1800,  # PROPOSED_HERE: 30-minute window used to report intended episodes.
    "ONE_THOUSAND_EIGHT_HUNDRED_FIVE": 1805,  # PROPOSED_HERE: source-independent cohort timing reference.
    "SIX_HUNDRED": 600,  # PROPOSED_HERE: ten-minute clearance bucket for the mid-day arrival distribution.
    "NINE_HUNDRED": 900,  # PROPOSED_HERE: fifteen-minute Ray replacement duration candidate.
    "ONE_THOUSAND_NINE_HUNDRED": 1900,  # PROPOSED_HERE: K8S scheduler capacity exceeds the constructed workload.
    "FIVE_HUNDRED_TWELVE": 512,  # PROPOSED_HERE: K8S node inventory covers the 213-node cap cohort with headroom.
    "ONE_HUNDRED_TWENTY_EIGHT": 128,  # PROPOSED_HERE: Ray inventory covers the scheduled burst concurrency.
    "ONE_POINT_ZERO": 1.0,  # PROPOSED_HERE: single-cluster workload-share normalization.
    "HALF": 0.5,  # PROPOSED_HERE: equal workload share between K8S and Ray scheduler agents.
    "ZERO_FLOAT": 0.0,  # PROPOSED_HERE: disable the unrelated generation-side admission threshold.
    "ONE_MINUTE": 60,  # PROPOSED_HERE: time conversion and lower queue-window bound.
    "ONE_HOUR": 1,  # PROPOSED_HERE: overnight time conversion and first Ray burst hour.
    "TWO_HOURS": 2,  # PROPOSED_HERE: time conversion for evening arrivals.
    "THREE_HOURS": 3,  # PROPOSED_HERE: time conversion for the second Ray burst.
    "FOUR_HOURS": 4,  # PROPOSED_HERE: time conversion for the overnight K8S interval.
    "FIVE_HOURS": 5,  # PROPOSED_HERE: time conversion for the first safe arrival interval.
    "SIX_HOURS": 6,  # PROPOSED_HERE: business-day morning arrival interval.
    "SEVEN_HOURS": 7,  # PROPOSED_HERE: safe Ray burst time.
    "EIGHT_HOURS": 8,  # PROPOSED_HERE: safe Ray burst time.
    "NINE_HOURS": 9,  # PROPOSED_HERE: first queue-stress business-day block.
    "TEN_HOURS": 10,  # PROPOSED_HERE: safe Ray burst time.
    "ELEVEN_HOURS": 11,  # PROPOSED_HERE: safe Ray burst time.
    "TWELVE_HOURS": 12,  # PROPOSED_HERE: time conversion for the final safe pre-peak burst.
    "THIRTEEN_HOURS": 13,  # PROPOSED_HERE: afternoon load plateau begins.
    "FOURTEEN_HOURS": 14,  # PROPOSED_HERE: second queue-stress block.
    "SIXTEEN_HOURS": 16,  # PROPOSED_HERE: third queue-stress block.
    "SEVENTEEN_HOURS": 17,  # PROPOSED_HERE: queue-stress windows end before the evening taper.
    "EIGHTEEN_HOURS": 18,  # PROPOSED_HERE: safe evening Ray burst and Slurm evening starts.
    "NINETEEN_HOURS": 19,  # PROPOSED_HERE: safe evening Ray burst.
    "TWENTY_HOURS": 20,  # PROPOSED_HERE: safe evening Ray burst.
    "TWENTY_ONE_HOURS": 21,  # PROPOSED_HERE: evening K8S distribution end.
    "TWENTY_TWO_HOURS": 22,  # PROPOSED_HERE: safe Ray burst.
    "TWENTY_THREE_HOURS": 23,  # PROPOSED_HERE: evening K8S distribution end.
    "START_OFFSET_MAX_S": 180,  # PROPOSED_HERE: seeded block-start jitter, kept within the afternoon plateau.
    "COHORT_CLEARANCE_S": 60,  # PROPOSED_HERE: non-anchor jobs outlast the final held episode by one minute.
    "JSON_INDENT": 2,  # PROPOSED_HERE: repository scenario formatting.
    "CLOCK_WIDTH": 2,  # PROPOSED_HERE: fixed-width HH:MM:SS display.
}

WINDOW_GROUP_SIZES = (
    N["FOUR"],  # PROPOSED_HERE: first queue block contains four windows.
    N["THREE"],  # PROPOSED_HERE: second queue block contains three windows.
    N["THREE"],  # PROPOSED_HERE: third queue block contains three windows.
)
QUEUE_DURATION_CHOICES = tuple(range(
    N["SIXTY"],
    N["FOUR_HUNDRED_TWENTY"] + N["FIVE"],
    N["FIVE"],
))
BLOCK_HOURS = (
    N["THIRTEEN_HOURS"],  # PROPOSED_HERE: afternoon plateau start.
    N["FOURTEEN_HOURS"] + N["HALF"],  # PROPOSED_HERE: second block is separated from the first.
    N["SIXTEEN_HOURS"],  # PROPOSED_HERE: third block remains within the afternoon plateau.
)
RAY_BURST_HOURS = (
    N["ONE_HOUR"],  # PROPOSED_HERE: overnight burst.
    N["THREE_HOURS"],  # PROPOSED_HERE: overnight burst.
    N["FIVE_HOURS"],  # PROPOSED_HERE: overnight burst.
    N["EIGHT_HOURS"],  # PROPOSED_HERE: morning burst.
    N["TEN_HOURS"],  # PROPOSED_HERE: morning burst.
    N["TWELVE_HOURS"],  # PROPOSED_HERE: pre-peak business-day burst.
    N["EIGHTEEN_HOURS"],  # PROPOSED_HERE: evening burst after queue windows.
    N["NINETEEN_HOURS"],  # PROPOSED_HERE: evening burst.
    N["TWENTY_HOURS"],  # PROPOSED_HERE: evening burst.
    N["TWENTY_TWO_HOURS"],  # PROPOSED_HERE: late-evening burst.
)
SECONDS_PER_HOUR = N["THREE_THOUSAND_SIX_HUNDRED"]
TICK_SECONDS = N["FIVE"]


def _model_bucket(job_id: str) -> str:
    lowered = job_id.lower()
    for model in (
        "mistral-large-2",
        "mixtral-8x22b",
        "cohere-command-r-plus",
        "cohere-command-r",
    ):
        if model in lowered:
            return model
    return "other"


def _round_robin_models(items: list[dict], count: int) -> list[dict]:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for item in sorted(items, key=lambda value: value["job_id"]):
        buckets[_model_bucket(item["job_id"])].append(item)
    selected = []
    model_names = sorted(buckets)
    while len(selected) < count:
        added = False
        for model in model_names:
            if buckets[model] and len(selected) < count:
                selected.append(buckets[model].pop(0))
                added = True
        if not added:
            raise ValueError(f"not enough model-balanced sessions for {count} jobs")
    return selected


def _take_one_node(
    candidates: list[dict],
    minimum_duration_s: float,
    rng: random.Random,
) -> dict:
    eligible = [
        item for item in candidates
        if item["node_count"] == N["ONE"]
        and item["duration_s"] >= minimum_duration_s
    ]
    if not eligible:
        raise ValueError(
            f"no one-node K8S source job lasts at least {minimum_duration_s} seconds"
        )
    shortest = min(item["duration_s"] for item in eligible)
    choices = [
        item for item in eligible
        if item["duration_s"] == shortest
    ]
    selected = rng.choice(choices)
    candidates.remove(selected)
    return selected


def _scheduled_job(item: dict, arrival_time_s: float) -> dict:
    return {
        "job_id": item["job_id"],
        "arrival_time_s": float(arrival_time_s),
        "duration_s": float(item["duration_s"]),
        "node_count": int(item["node_count"]),
        "hardware_profile_id": item["hardware_profile_id"],
    }


def _tick_aligned_random_time(
    rng: random.Random, start_s: int, end_s: int
) -> float:
    tick_count = (end_s - start_s) // TICK_SECONDS
    return float(
        start_s + rng.randrange(tick_count) * TICK_SECONDS
    )


def _clock(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, SECONDS_PER_HOUR)
    minutes, secs = divmod(remainder, N["ONE_MINUTE"])
    return ":".join(
        str(value).zfill(N["CLOCK_WIDTH"])
        for value in (hours, minutes, secs)
    )


def build_queue_scenario() -> dict:
    source = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    rng = random.Random(N["SEED"])
    end_by_job = {
        event["job_id"]: event
        for event in source["workload_events"]
        if event.get("event_type") == "job_end"
        and event.get("scheduler_type") in {"K8S", "RAY"}
    }
    slurm_events = [
        event
        for event in source["workload_events"]
        if event.get("scheduler_type") == "SLURM"
    ]
    k8s_jobs = []
    ray_jobs = []
    carryover_jobs = []
    for event in source["workload_events"]:
        if (
            event.get("event_type") != "starting"
            or event.get("scheduler_type") not in {"K8S", "RAY"}
        ):
            continue
        end_event = end_by_job[event["job_id"]]
        item = {
            "job_id": event["job_id"],
            "duration_s": float(end_event["timestamp"] - event["timestamp"]),
            "node_count": int(event["node_count"]),
            "hardware_profile_id": event["hardware_profile_id"],
        }
        if event["scheduler_type"] == "K8S":
            if float(event["timestamp"]) == N["ZERO_FLOAT"]:
                item["arrival_time_s"] = N["ZERO_FLOAT"]
                carryover_jobs.append(item)
            else:
                k8s_jobs.append(item)
        else:
            ray_jobs.append(item)

    if len(carryover_jobs) != N["K8S_MIDNIGHT_CARRYOVER_COUNT"]:
        raise ValueError("the source Proxim8 midnight carry-over count changed")
    if len(k8s_jobs) + len(carryover_jobs) != N["ONE_THOUSAND"]:
        raise ValueError("the source Proxim8 K8S session count changed")
    if len(ray_jobs) != N["TEN_THOUSAND"]:
        raise ValueError("the source Proxim8 Ray call count changed")

    # Draw independent, tick-aligned uniform durations for the ten windows.
    episode_durations = [
        rng.choice(QUEUE_DURATION_CHOICES)
        for _ in range(N["TEN"])
    ]
    source_k8s = list(k8s_jobs)
    scheduled_k8s = [
        _scheduled_job(item, item["arrival_time_s"])
        for item in carryover_jobs
    ]
    episodes = []
    cursor = N["ZERO"]
    block_last_release = []

    for block_index, block_size in enumerate(WINDOW_GROUP_SIZES):
        block_start_s = (
            int(BLOCK_HOURS[block_index] * SECONDS_PER_HOUR)
            + rng.randrange(N["START_OFFSET_MAX_S"] // TICK_SECONDS)
            * TICK_SECONDS
        )
        start_times = []
        release_times = []
        first_duration = episode_durations[cursor]
        first_start = block_start_s
        first_release = first_start + first_duration - TICK_SECONDS

        # The initial one-node session is active before the cohort fills the
        # remaining 212 nodes; its source duration is preserved.
        first_anchor = _take_one_node(
            source_k8s,
            first_duration + N["THREE_HUNDRED"],
            rng,
        )
        first_anchor_start = first_release - first_anchor["duration_s"]
        if first_anchor_start > block_start_s - N["THREE_HUNDRED"]:
            raise ValueError("initial anchor does not precede the K8S cohort")
        scheduled_k8s.append(_scheduled_job(first_anchor, first_anchor_start))

        start_times.append(first_start)
        release_times.append(first_release)
        replacement_jobs = []
        for local_index in range(N["ONE"], block_size):
            episode_index = cursor + local_index
            duration = episode_durations[episode_index]
            replacement = _take_one_node(
                source_k8s,
                duration + N["THIRTY_FIVE"],
                rng,
            )
            replacement_start = (
                release_times[-1] + N["TWENTY"]
            )
            replacement_release = (
                replacement_start + replacement["duration_s"]
            )
            next_start = (
                replacement_release - duration + TICK_SECONDS
            )
            if next_start < replacement_start + N["SIXTY"]:
                raise ValueError("replacement cannot remain active to the next window")
            replacement_jobs.append(replacement)
            start_times.append(next_start)
            release_times.append(replacement_release)

        # The base cohort has 174 single-node and 19 two-node sessions (212
        # nodes); the separate anchor makes 213 nodes, just under the 5 MW cap.
        required_cohort_duration = (
            release_times[-1]
            + N["COHORT_CLEARANCE_S"]
            - (block_start_s - N["THREE_HUNDRED"])
        )
        eligible = [
            item for item in source_k8s
            if item["duration_s"] >= required_cohort_duration
        ]
        long_single = [
            item for item in eligible
            if item["node_count"] == N["ONE"]
        ]
        long_double = [
            item for item in eligible
            if item["node_count"] == N["TWO"]
        ]
        singles = _round_robin_models(
            long_single, N["ONE_HUNDRED_SEVENTY_FOUR"]
        )
        doubles = _round_robin_models(long_double, N["NINETEEN"])
        for item in singles + doubles:
            source_k8s.remove(item)
            scheduled_k8s.append(_scheduled_job(
                item, block_start_s - N["THREE_HUNDRED"]
            ))

        for local_index, duration in enumerate(
            episode_durations[cursor:cursor + block_size]
        ):
            episode = {
                "episode": cursor + local_index + N["ONE"],
                "start_time_s": start_times[local_index],
                "end_time_s": start_times[local_index] + duration,
                "duration_s": duration,
                "trigger_ray_job_id": None,
            }
            episodes.append(episode)
        for local_index, replacement in enumerate(replacement_jobs):
            scheduled_k8s.append(_scheduled_job(
                replacement,
                release_times[local_index] + N["TWENTY"],
            ))
        block_last_release.append(release_times[-1])
        cursor += block_size

    if cursor != N["TEN"]:
        raise ValueError("queue episode groups must total ten")

    # The ten queued calls are drawn from the same seeded Ray call population.
    ray_jobs.sort(key=lambda item: item["job_id"])
    trigger_jobs = ray_jobs[:N["TEN"]]
    other_ray_jobs = ray_jobs[N["TEN"]:]
    for episode, item in zip(episodes, trigger_jobs):
        episode["trigger_ray_job_id"] = item["job_id"]
        scheduled_ray = _scheduled_job(item, episode["start_time_s"])
        episode.setdefault("_trigger", scheduled_ray)

    # The remaining 406 K8S sessions retain their original node counts and
    # durations, but are spread across safe overnight, morning and evening
    # periods so the ten cap-held episodes remain isolated.
    rng.shuffle(source_k8s)
    carry_count = len(carryover_jobs)
    noncohort_count = len(source_k8s)
    if noncohort_count != N["FOUR_HUNDRED_SIX"]:
        raise ValueError(
            f"expected {N['FOUR_HUNDRED_SIX']} remaining K8S jobs, got {noncohort_count}"
        )
    remainder_groups = (
        (
            N["FIFTY"],
            N["ONE_HOUR"] * SECONDS_PER_HOUR,
            N["FIVE_HOURS"] * SECONDS_PER_HOUR,
        ),
        (
            N["TWO_HUNDRED_TWENTY"],
            N["SIX_HOURS"] * SECONDS_PER_HOUR,
            N["ELEVEN_HOURS"] * SECONDS_PER_HOUR,
        ),
        (
            N["ONE_HUNDRED_THIRTY_SIX"],
            N["EIGHTEEN_HOURS"] * SECONDS_PER_HOUR,
            N["TWENTY_THREE_HOURS"] * SECONDS_PER_HOUR,
        ),
    )
    remainder_cursor = N["ZERO"]
    for group_count, start_s, end_s in remainder_groups:
        for item in source_k8s[remainder_cursor:remainder_cursor + group_count]:
            arrival = _tick_aligned_random_time(rng, start_s, end_s)
            scheduled_k8s.append(_scheduled_job(item, arrival))
        remainder_cursor += group_count
    if remainder_cursor != len(source_k8s):
        raise ValueError("non-cohort K8S arrival counts do not balance")

    # The other 9,990 Ray calls run in ten short, separate burst chains outside
    # the queue windows. Each call remains a 10-second two-tick service event.
    scheduled_ray = []
    for index, item in enumerate(other_ray_jobs):
        burst_index = index // N["NINE_NINETY_NINE"]
        index_in_burst = index % N["NINE_NINETY_NINE"]
        chain_index = index_in_burst // N["ONE_HUNDRED"]
        call_index = index_in_burst % N["ONE_HUNDRED"]
        arrival = (
            RAY_BURST_HOURS[burst_index] * SECONDS_PER_HOUR
            + chain_index * TICK_SECONDS
            + call_index * TICK_SECONDS
        )
        scheduled_ray.append(_scheduled_job(item, arrival))
    for episode in episodes:
        scheduled_ray.append(episode.pop("_trigger"))

    scheduled_k8s.sort(
        key=lambda item: (item["arrival_time_s"], item["job_id"])
    )
    scheduled_ray.sort(
        key=lambda item: (item["arrival_time_s"], item["job_id"])
    )

    scenario = dict(source)
    scenario["name"] = "Proxim8 — queue stress"
    scenario["description"] = (
        source["description"]
        + " DR-2026-11-03-PROXIM8-QUEUE (PROPOSED_HERE): K8S and Ray "
        "arrivals use opt-in scheduled admission against previous-tick "
        "facility-demand headroom at the 5 MW grid cap; BESS is excluded from "
        "admission power. Ten seeded uniform 60–420 s queue windows are "
        "recorded below; Slurm remains scripted with its original starts. "
        f"Seed {N['SEED']}; intended windows: "
        + "; ".join(
            f"{_clock(item['start_time_s'])}–{_clock(item['end_time_s'])} "
            f"({item['duration_s']} s)"
            for item in episodes
        )
        + "."
    )
    scenario["workload_events"] = slurm_events
    scenario["kube_clusters"] = [
        {
            "cluster_id": "proxim8-k8s",
            "tenant_id": "proxim8",
            "scheduler_type": "K8S",
            "capacity_unit": "node",
            "workload_share": N["HALF"],
            "hardware_profile_id": "hopper_8gpu_air",
            "workload_class": "inference",
            "max_nodes": N["FIVE_HUNDRED_TWELVE"],
            "min_nodes": N["ONE"],
            "min_job_nodes": N["ONE"],
            "max_job_nodes": N["TWO"],
            "arrival_mode": "scheduled",
            "scheduled_arrivals": scheduled_k8s,
            "grid_cap_admission_enabled": True,
            "headroom_threshold_mw": N["ZERO_FLOAT"],
            "power_cap_hysteresis_s": N["ZERO_FLOAT"],
            "reorder_window_s": N["ZERO_FLOAT"],
            "rng_seed": N["SEED"],
        },
        {
            "cluster_id": "proxim8-ray",
            "tenant_id": "proxim8",
            "scheduler_type": "RAY",
            "capacity_unit": "node",
            "workload_share": N["HALF"],
            "hardware_profile_id": "hopper_8gpu_air",
            "workload_class": "other",
            "max_nodes": N["ONE_HUNDRED_TWENTY_EIGHT"],
            "min_nodes": N["ONE"],
            "min_job_nodes": N["ONE"],
            "max_job_nodes": N["ONE"],
            "arrival_mode": "scheduled",
            "scheduled_arrivals": scheduled_ray,
            "grid_cap_admission_enabled": True,
            "headroom_threshold_mw": N["ZERO_FLOAT"],
            "power_cap_hysteresis_s": N["ZERO_FLOAT"],
            "reorder_window_s": N["ZERO_FLOAT"],
            "rng_seed": N["SEED"],
        },
    ]
    scenario["provenance_proxim8_queue"] = {
        "seed": N["SEED"],
        "decision_record": "DR-2026-11-03-PROXIM8-QUEUE",
        "queue_duration_distribution": (
            "uniform discrete 60–420 seconds in 5-second steps"
        ),
        "intended_windows": episodes,
        "proposed_here": (
            "Ten seeded isolated queue windows; 213 K8S nodes plus building "
            "load form the near-cap background; one Ray call is held per window."
        ),
    }
    return scenario


def main() -> None:
    scenario = build_queue_scenario()
    OUTPUT_PATH.write_text(
        json.dumps(scenario, indent=N["JSON_INDENT"], ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT_PATH}")
    print(f"slurm_workload_events={len(scenario['workload_events'])}")
    print(f"k8s_scheduled_arrivals={len(scenario['kube_clusters'][0]['scheduled_arrivals'])}")
    print(f"ray_scheduled_arrivals={len(scenario['kube_clusters'][1]['scheduled_arrivals'])}")
    print(json.dumps(
        scenario["provenance_proxim8_queue"]["intended_windows"],
        indent=N["JSON_INDENT"],
    ))


if __name__ == "__main__":
    main()
