#!/usr/bin/env python3
"""Generate the deterministic Proxim8 24-hour scenario."""

from __future__ import annotations

import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]  # PROPOSED_HERE: this script is two directory levels below the workspace root.
PACKAGE_ROOT = (
    REPO_ROOT
    / "attached_assets"
    / "gridsignal_sim_v2_build_package"
    / "gridsignal_sim_v2"
    / "gridsignal_sim"
)
SCENARIO_PATH = PACKAGE_ROOT / "config" / "scenarios" / "proxim8-5mw-24h.json"

# Numeric constants carry PROPOSED_HERE rationale tags. The generator seed is
# fixed by the request; physical assumptions and workload timing are illustrative.
N = {
    "SEED": 20261102,  # PROPOSED_HERE: fixed by the approved user request for reproducible output.
    "ZERO": 0,  # PROPOSED_HERE: zero start, zero-count and no-output sentinel.
    "ONE": 1,  # PROPOSED_HERE: index and inclusive-bound increment.
    "ONE_FLOAT": 1.0,  # PROPOSED_HERE: identity coefficient in steady-state cooling scaling.
    "ZERO_FLOAT": 0.0,  # PROPOSED_HERE: exact zero-power initialization.
    "TWO_NODES": 2,  # PROPOSED_HERE: requested minority K8s session size.
    "KW_PER_MW": 1000.0,  # PROPOSED_HERE: kW-to-MW unit conversion.
    "LAST": -1,  # PROPOSED_HERE: select the last profile anchor.
    "SECOND": 1,  # PROPOSED_HERE: select a pair's second element.
    "MW_COLUMN": 1,  # PROPOSED_HERE: power column in the two-value building profile.
    "PROFILE_END_INCLUSIVE": 1,  # PROPOSED_HERE: include the final 24-hour profile sample.
    "ID_WIDTH": 4,  # PROPOSED_HERE: fixed-width readable job numbering.
    "SECONDS_PER_MINUTE": 60,  # PROPOSED_HERE: time conversion.
    "SECONDS_PER_HOUR": 3600,  # PROPOSED_HERE: time conversion.
    "HOURS_PER_DAY": 24,  # PROPOSED_HERE: requested run duration.
    "DAY_SECONDS": 86400,  # PROPOSED_HERE: requested end_sim_time.
    "TICK_SECONDS": 5,  # PROPOSED_HERE: generator estimate matches the simulator tick.
    "PROFILE_STEP_SECONDS": 300,  # PROPOSED_HERE: five-minute building-curve resolution.
    "GRID_CAP_MW": 5.0,  # PROPOSED_HERE: requested building-service limit.
    "GRID_FIRM_MW": 5.0,  # PROPOSED_HERE: matches the service cap.
    "GRID_ZERO_MW": 0.0,  # PROPOSED_HERE: no reserved or non-firm utility tranche.
    "GRID_PRICE_FALLBACK_MWH": 114.82,  # PROPOSED_HERE: sourced B-20 summer off-peak fallback; EDL reprices TOU.
    "PGE_SUMMER_PART_MWH": 142.27,  # PROPOSED_HERE audit tag: built-in B-20 value from economic_dispatch_loop.py.
    "PGE_SUMMER_PEAK_MWH": 177.02,  # PROPOSED_HERE audit tag: built-in B-20 value from economic_dispatch_loop.py.
    "PGE_WINTER_OFF_MWH": 114.60,  # PROPOSED_HERE audit tag: built-in B-20 value from economic_dispatch_loop.py.
    "PGE_WINTER_SUPER_OFF_MWH": 58.72,  # PROPOSED_HERE audit tag: built-in B-20 value from economic_dispatch_loop.py.
    "EDL_MONTH": 7,  # PROPOSED_HERE: July selects the existing summer TOU periods.
    "PUE_BASE": 1.3,  # PROPOSED_HERE: assumed air-cooled office GPU-room fit-out.
    "MODEL_NODE_RATED_KW": 10.2,  # PROPOSED_HERE audit tag: catalog hopper_8gpu_air chassis value from scenario_factory.py.
    "ALPHA_MAX": 0.20,  # PROPOSED_HERE estimator reference: current engine default; not written into the scenario.
    "COOLING_DELAY_SECONDS": 90,  # PROPOSED_HERE estimator reference: current engine default; not written into the scenario.
    "COOLING_TAU_SECONDS": 20,  # PROPOSED_HERE estimator reference: current engine default; not written into the scenario.
    "BUILDING_NIGHT_MW": 0.7,  # PROPOSED_HERE: requested overnight total building load.
    "BUILDING_MORNING_MW": 1.2,  # PROPOSED_HERE: intermediate point for the 06:00–09:00 ramp.
    "BUILDING_PEAK_MW": 1.6,  # PROPOSED_HERE: requested afternoon total building load.
    "BUILDING_EVENING_MW": 0.8,  # PROPOSED_HERE: requested total building load by 21:00.
    "HOUR_00": 0.0,  # PROPOSED_HERE: profile and workload midnight boundary.
    "HOUR_02": 2.0,  # PROPOSED_HERE: representative overnight report point.
    "HOUR_06": 6.0,  # PROPOSED_HERE: business-day ramp begins.
    "HOUR_07": 7.0,  # PROPOSED_HERE: representative morning report point.
    "HOUR_09": 9.0,  # PROPOSED_HERE: morning ramp endpoint.
    "HOUR_13": 13.0,  # PROPOSED_HERE: afternoon peak begins.
    "HOUR_15": 15.0,  # PROPOSED_HERE: representative afternoon report point.
    "HOUR_16": 16.0,  # PROPOSED_HERE: late-afternoon Ray burst hour.
    "HOUR_17": 17.0,  # PROPOSED_HERE: afternoon peak ends.
    "HOUR_18": 18.0,  # PROPOSED_HERE: evening training window.
    "HOUR_19": 19.0,  # PROPOSED_HERE: evening training window.
    "HOUR_20": 20.0,  # PROPOSED_HERE: evening training window.
    "HOUR_21": 21.0,  # PROPOSED_HERE: requested evening profile point.
    "HOUR_22": 22.0,  # PROPOSED_HERE: latest Slurm start with a two-hour minimum.
    "HOUR_24": 24.0,  # PROPOSED_HERE: end-of-day profile boundary.
    "SLURM_START_1_H": 0.5,  # PROPOSED_HERE: overnight training start.
    "SLURM_START_2_H": 2.5,  # PROPOSED_HERE: overnight training start.
    "SLURM_START_3_H": 4.5,  # PROPOSED_HERE: overnight training start.
    "SLURM_START_4_H": 18.0,  # PROPOSED_HERE: evening training start.
    "SLURM_START_5_H": 18.5,  # PROPOSED_HERE: evening training start.
    "SLURM_START_6_H": 19.0,  # PROPOSED_HERE: evening training start.
    "SLURM_START_7_H": 19.5,  # PROPOSED_HERE: evening training start.
    "SLURM_START_8_H": 20.0,  # PROPOSED_HERE: evening training start.
    "SLURM_START_9_H": 21.0,  # PROPOSED_HERE: evening training start.
    "SLURM_START_10_H": 22.0,  # PROPOSED_HERE: latest start retains two-hour duration.
    "BESS_MW": 1.0,  # PROPOSED_HERE: requested BESS power rating.
    "BESS_MWH": 2.0,  # PROPOSED_HERE: requested BESS energy rating.
    "BESS_INITIAL_SOC": 0.95,  # PROPOSED_HERE: requested initial state of charge.
    "BESS_ANCHOR_MW": 0.1,  # PROPOSED_HERE: small grid-forming anchor share of the 1 MW rating.
    "BESS_DISPATCH_DEPTH": 0.0,  # PROPOSED_HERE: no normal-operation reserve floor; grid recharging is available.
    "DIESEL_MW": 1.0,  # PROPOSED_HERE: disabled small-site backup placeholder rating.
    "SLURM_COUNT": 10,  # PROPOSED_HERE: requested training-job count.
    "SLURM_MIN_NODES": 8,  # PROPOSED_HERE: requested minimum training allocation.
    "SLURM_MAX_NODES": 32,  # PROPOSED_HERE: requested maximum training allocation.
    "SLURM_MIN_HOURS": 2,  # PROPOSED_HERE: requested minimum training duration.
    "SLURM_MAX_HOURS": 8,  # PROPOSED_HERE: requested maximum training duration.
    "SLURM_OVERNIGHT_COUNT": 3,  # PROPOSED_HERE: three overnight and seven evening starts.
    "K8S_COUNT": 1000,  # PROPOSED_HERE: requested inference-session count.
    "K8S_MIDNIGHT_CARRYOVER_COUNT": 5,  # PROPOSED_HERE: five K8S sessions model 24/7 inference carry-over from the previous day.
    "K8S_DOUBLE_SHARE": 0.10,  # PROPOSED_HERE: requested approximate ten-percent two-node share.
    "K8S_MIN_MINUTES": 5,  # PROPOSED_HERE: requested shortest inference session.
    "K8S_MAX_MINUTES": 60,  # PROPOSED_HERE: requested longest inference session.
    "K8S_PEAK_MIN_MINUTES": 55,  # PROPOSED_HERE: longer afternoon sessions raise concurrent load toward the 5 MW service cap.
    "K8S_OVERNIGHT_COUNT": 50,  # PROPOSED_HERE: low overnight session volume.
    "K8S_MORNING_COUNT": 100,  # PROPOSED_HERE: morning session volume.
    "K8S_LATE_MORNING_COUNT": 100,  # PROPOSED_HERE: moderate late-morning session volume before the afternoon peak.
    "K8S_AFTERNOON_COUNT": 650,  # PROPOSED_HERE: afternoon peak volume sized for roughly 4.0–4.6 MW before Ray burst.
    "K8S_EVENING_COUNT": 100,  # PROPOSED_HERE: evening taper session volume.
    "RAY_COUNT": 10000,  # PROPOSED_HERE: requested agentic API-call count.
    "RAY_PEAK_CHAINS": 40,  # PROPOSED_HERE: concurrent chains create a late-afternoon demand spike.
    "RAY_PEAK_CALLS_PER_CHAIN": 180,  # PROPOSED_HERE: a fifteen-minute burst at the selected cadence.
    "RAY_DAY_CHAINS": 28,  # PROPOSED_HERE: distributes remaining calls across the business day.
    "RAY_DAY_CALLS_PER_CHAIN": 100,  # PROPOSED_HERE: short call chains outside the principal burst.
    "RAY_CALL_SECONDS": 10,  # PROPOSED_HERE: minimum two-tick Ray call duration.
    "RAY_CADENCE_SECONDS": 5,  # PROPOSED_HERE: one-tick spacing within a chain.
    "RAY_DAY_CHAIN_SPACING_SECONDS": 1800,  # PROPOSED_HERE: half-hour chain spacing limits background concurrency.
    "RAY_PEAK_START_MINUTE": 35,  # PROPOSED_HERE: late-afternoon burst begins at minute 35.
    "PADDING_WIDTH": 4,  # PROPOSED_HERE: stable ID display width.
    "JSON_INDENT": 2,  # PROPOSED_HERE: readable JSON formatting.
    "MINUTES_ABOVE_CAP_LIMIT": 5.0,  # PROPOSED_HERE: cap threshold used in the demand report.
}

SLURM_START_HOURS = tuple(
    N[f"SLURM_START_{index}_H"]
    for index in range(N["ONE"], N["SLURM_COUNT"] + N["ONE"])
)
K8S_WINDOWS = (
    ("overnight", N["HOUR_00"], N["HOUR_06"], N["K8S_OVERNIGHT_COUNT"]),
    ("morning", N["HOUR_06"], N["HOUR_09"], N["K8S_MORNING_COUNT"]),
    ("late_morning", N["HOUR_09"], N["HOUR_13"], N["K8S_LATE_MORNING_COUNT"]),
    ("afternoon", N["HOUR_13"], N["HOUR_17"], N["K8S_AFTERNOON_COUNT"]),
    ("evening", N["HOUR_17"], N["HOUR_21"], N["K8S_EVENING_COUNT"]),
)

MODEL_IDS = (
    "mistral-large-2",
    "mixtral-8x22b",
    "cohere-command-r-plus",
    "cohere-command-r",
)


def _hour(hour: float) -> int:
    return int(hour * N["SECONDS_PER_HOUR"])


def _target_building_total_mw(hour: float) -> float:
    anchors = (
        (N["HOUR_00"], N["BUILDING_NIGHT_MW"]),
        (N["HOUR_06"], N["BUILDING_NIGHT_MW"]),
        (N["HOUR_09"], N["BUILDING_MORNING_MW"]),
        (N["HOUR_13"], N["BUILDING_PEAK_MW"]),
        (N["HOUR_17"], N["BUILDING_PEAK_MW"]),
        (N["HOUR_21"], N["BUILDING_EVENING_MW"]),
        (N["HOUR_24"], N["BUILDING_NIGHT_MW"]),
    )
    for (left_h, left_mw), (right_h, right_mw) in zip(
        anchors,
        anchors[N["ONE"] :],
    ):
        if left_h <= hour <= right_h:
            fraction = (hour - left_h) / (right_h - left_h)
            return left_mw + (right_mw - left_mw) * fraction
    return anchors[N["LAST"]][N["SECOND"]]


def _non_hvac_input_mw(hour: float) -> float:
    # Engine steady-state relation is total = input + alpha_max * lagged input.
    return _target_building_total_mw(hour) / (N["ONE_FLOAT"] + N["ALPHA_MAX"])


def _profile_value(profile: list[list[float]], time_s: float) -> float:
    value = profile[N["ZERO"]][N["MW_COLUMN"]]
    for point_time_s, point_mw in profile:
        if point_time_s > time_s:
            break
        value = point_mw
    return value


def _make_profile() -> list[list[float]]:
    samples = N["DAY_SECONDS"] // N["PROFILE_STEP_SECONDS"]
    return [
        [
            float(min(index * N["PROFILE_STEP_SECONDS"], N["DAY_SECONDS"])),
            _non_hvac_input_mw(
                min(index * N["PROFILE_STEP_SECONDS"], N["DAY_SECONDS"])
                / N["SECONDS_PER_HOUR"]
            ),
        ]
        for index in range(samples + N["PROFILE_END_INCLUSIVE"])
    ]


def _add_job(
    events: list[dict[str, object]],
    *,
    job_id: str,
    scheduler_type: str,
    cluster_id: str,
    workload_class: str,
    start_s: int,
    duration_s: int,
    nodes: int,
) -> None:
    common: dict[str, object] = {
        "job_id": job_id,
        "scheduler_type": scheduler_type,
        "cluster_id": cluster_id,
        "workload_class": workload_class,
        "hardware_profile_id": "hopper_8gpu_air",
    }
    events.append(
        {
            **common,
            "event_id": f"{job_id}-start",
            "event_type": "starting",
            "timestamp": float(start_s),
            "node_count": nodes,
        }
    )
    events.append(
        {
            **common,
            "event_id": f"{job_id}-end",
            "event_type": "job_end",
            "timestamp": float(start_s + duration_s),
            "node_count": N["ZERO"],
        }
    )


def _make_events() -> list[dict[str, object]]:
    rng = random.Random(N["SEED"])
    events: list[dict[str, object]] = []

    for index, start_hour in enumerate(SLURM_START_HOURS):
        start_s = _hour(start_hour)
        nodes = rng.randint(N["SLURM_MIN_NODES"], N["SLURM_MAX_NODES"])
        duration_h = rng.randint(N["SLURM_MIN_HOURS"], N["SLURM_MAX_HOURS"])
        duration_s = min(
            duration_h * N["SECONDS_PER_HOUR"],
            N["DAY_SECONDS"] - start_s,
        )
        job_id = (
            "slurm-training-"
            + str(index + N["ONE"]).zfill(N["PADDING_WIDTH"])
        )
        _add_job(
            events,
            job_id=job_id,
            scheduler_type="SLURM",
            cluster_id="proxim8-slurm",
            workload_class="training",
            start_s=start_s,
            duration_s=duration_s,
            nodes=nodes,
        )

    double_node_count = round(N["K8S_COUNT"] * N["K8S_DOUBLE_SHARE"])
    double_node_indices = set(
        rng.sample(range(N["K8S_COUNT"]), double_node_count)
    )
    k8s_index = N["ZERO"]
    for window_name, first_hour, last_hour, group_count in K8S_WINDOWS:
        first_s = _hour(first_hour)
        last_s = _hour(last_hour)
        for _ in range(group_count):
            sampled_start_s = rng.randrange(first_s, last_s, N["TICK_SECONDS"])
            if (
                window_name == "overnight"
                and k8s_index < N["K8S_MIDNIGHT_CARRYOVER_COUNT"]
            ):
                # Keep the seeded draw above so all other generated fields
                # remain reproducible; move only selected overnight starts.
                start_s = N["ZERO"]
            else:
                start_s = sampled_start_s
            min_duration = (
                N["K8S_PEAK_MIN_MINUTES"]
                if window_name == "afternoon"
                else N["K8S_MIN_MINUTES"]
            )
            duration_minutes = rng.randint(min_duration, N["K8S_MAX_MINUTES"])
            model_id = rng.choice(MODEL_IDS)
            nodes = (
                N["TWO_NODES"]
                if k8s_index in double_node_indices
                else N["ONE"]
            )
            job_id = (
                f"k8s-inf-{model_id}-"
                + str(k8s_index + N["ONE"]).zfill(N["PADDING_WIDTH"])
            )
            _add_job(
                events,
                job_id=job_id,
                scheduler_type="K8S",
                cluster_id="proxim8-k8s",
                workload_class="inference",
                start_s=start_s,
                duration_s=duration_minutes * N["SECONDS_PER_MINUTE"],
                nodes=nodes,
            )
            k8s_index += N["ONE"]

    ray_jobs: list[tuple[str, int]] = []
    peak_start_s = (
        N["HOUR_16"] * N["SECONDS_PER_HOUR"]
        + N["RAY_PEAK_START_MINUTE"] * N["SECONDS_PER_MINUTE"]
    )
    for chain in range(N["RAY_PEAK_CHAINS"]):
        for call in range(N["RAY_PEAK_CALLS_PER_CHAIN"]):
            ray_jobs.append(
                (
                    f"ray-agentic-call-burst-{chain + N['ONE']}-{call + N['ONE']}",
                    peak_start_s + call * N["RAY_CADENCE_SECONDS"],
                )
            )
    for chain in range(N["RAY_DAY_CHAINS"]):
        chain_start_s = (
            N["HOUR_06"] * N["SECONDS_PER_HOUR"]
            + chain * N["RAY_DAY_CHAIN_SPACING_SECONDS"]
        )
        for call in range(N["RAY_DAY_CALLS_PER_CHAIN"]):
            ray_jobs.append(
                (
                    f"ray-agentic-call-day-{chain + N['ONE']}-{call + N['ONE']}",
                    chain_start_s + call * N["RAY_CADENCE_SECONDS"],
                )
            )
    if len(ray_jobs) != N["RAY_COUNT"]:
        raise ValueError(
            f"Ray generator produced {len(ray_jobs)} calls; expected {N['RAY_COUNT']}"
        )
    for job_id, start_s in ray_jobs:
        _add_job(
            events,
            job_id=job_id,
            scheduler_type="RAY",
            cluster_id="proxim8-ray",
            workload_class="other",
            start_s=start_s,
            duration_s=N["RAY_CALL_SECONDS"],
            nodes=N["ONE"],
        )

    events.sort(
        key=lambda event: (
            float(event["timestamp"]),
            N["ZERO"] if event["event_type"] == "starting" else N["ONE"],
            str(event["event_id"]),
        )
    )
    return events


def _estimate_nameplate_demand(
    profile: list[list[float]],
    events: list[dict[str, object]],
) -> tuple[float, int, int, dict[str, float], dict[str, float]]:
    """Estimate full-nameplate workload demand plus per-job cooling envelopes."""
    starts: dict[int, list[dict[str, object]]] = defaultdict(list)
    ends: dict[int, list[dict[str, object]]] = defaultdict(list)
    end_time_by_job: dict[str, int] = {}
    for event in events:
        event_time = int(float(event["timestamp"]))
        job_id = str(event["job_id"])
        if event["event_type"] == "starting":
            starts[event_time].append(event)
        else:
            ends[event_time].append(event)
            end_time_by_job[job_id] = event_time

    active: dict[str, tuple[int, int, float]] = {}
    peak_mw = float("-inf")
    peak_time_s = N["ZERO"]
    above_cap_ticks = N["ZERO"]
    sample_times = {
        _hour(N["HOUR_02"]): "overnight_02",
        _hour(N["HOUR_07"]): "morning_07",
        _hour(N["HOUR_15"]): "afternoon_15",
    }
    sampled_demand: dict[str, float] = {}
    afternoon_total = N["ZERO_FLOAT"]
    afternoon_ticks = N["ZERO"]
    afternoon_min = float("inf")
    afternoon_max = float("-inf")
    for time_s in range(N["ZERO"], N["DAY_SECONDS"], N["TICK_SECONDS"]):
        for event in ends.get(time_s, []):
            active.pop(str(event["job_id"]), None)
        for event in starts.get(time_s, []):
            job_id = str(event["job_id"])
            start_s = int(float(event["timestamp"]))
            power_mw = (
                int(event["node_count"])
                * N["MODEL_NODE_RATED_KW"]
                * N["PUE_BASE"]
                / N["KW_PER_MW"]
            )
            active[job_id] = (start_s, end_time_by_job[job_id], power_mw)

        building_input = _profile_value(profile, float(time_s))
        lag_time_s = time_s - N["COOLING_DELAY_SECONDS"]
        building_cooling = N["ZERO_FLOAT"]
        if lag_time_s >= N["ZERO"]:
            elapsed_building = time_s - N["COOLING_DELAY_SECONDS"]
            alpha_building = N["ALPHA_MAX"] * (
                N["ONE_FLOAT"]
                - math.exp(-elapsed_building / N["COOLING_TAU_SECONDS"])
            )
            building_cooling = alpha_building * _profile_value(
                profile,
                float(lag_time_s),
            )

        gpu_base = sum(power for _start, _end, power in active.values())
        gpu_cooling = N["ZERO_FLOAT"]
        for start_s, end_s, power_mw in active.values():
            if start_s <= lag_time_s < end_s and time_s >= (
                start_s + N["COOLING_DELAY_SECONDS"]
            ):
                elapsed = time_s - start_s - N["COOLING_DELAY_SECONDS"]
                alpha = N["ALPHA_MAX"] * (
                    N["ONE_FLOAT"]
                    - math.exp(-elapsed / N["COOLING_TAU_SECONDS"])
                )
                gpu_cooling += alpha * power_mw

        demand = building_input + building_cooling + gpu_base + gpu_cooling
        if demand > peak_mw:
            peak_mw = demand
            peak_time_s = time_s
        if demand > N["GRID_CAP_MW"]:
            above_cap_ticks += N["ONE"]
        if time_s in sample_times:
            sampled_demand[sample_times[time_s]] = demand
        if _hour(N["HOUR_13"]) <= time_s < _hour(N["HOUR_17"]):
            afternoon_total += demand
            afternoon_ticks += N["ONE"]
            afternoon_min = min(afternoon_min, demand)
            afternoon_max = max(afternoon_max, demand)

    seconds_above = above_cap_ticks * N["TICK_SECONDS"]
    minutes_above = seconds_above / N["SECONDS_PER_MINUTE"]
    afternoon_summary = {
        "mean_mw": afternoon_total / afternoon_ticks,
        "min_mw": afternoon_min,
        "max_mw": afternoon_max,
    }
    return (
        peak_mw,
        peak_time_s,
        int(round(minutes_above * N["SECONDS_PER_MINUTE"])),
        sampled_demand,
        afternoon_summary,
    )


def _cooling_report_points(profile: list[list[float]]) -> list[dict[str, float | int]]:
    rows = []
    report_hours = (
        N["HOUR_02"],
        N["HOUR_07"],
        N["HOUR_15"],
        N["HOUR_21"],
    )
    for hour in report_hours:
        time_s = _hour(hour)
        input_mw = _profile_value(profile, float(time_s))
        lag_time_s = time_s - N["COOLING_DELAY_SECONDS"]
        cooling_mw = N["ZERO_FLOAT"]
        if lag_time_s >= N["ZERO"]:
            elapsed = time_s - N["COOLING_DELAY_SECONDS"]
            alpha = N["ALPHA_MAX"] * (
                N["ONE_FLOAT"] - math.exp(-elapsed / N["COOLING_TAU_SECONDS"])
            )
            cooling_mw = alpha * _profile_value(profile, float(lag_time_s))
        rows.append(
            {
                "hour": int(hour),
                "input_non_hvac_mw": input_mw,
                "engine_modelled_cooling_mw": cooling_mw,
                "total_building_mw": input_mw + cooling_mw,
            }
        )
    return rows


def _description() -> str:
    return (
        f"Proxim8 is an illustrative {N['HOURS_PER_DAY']}-hour distributed-inference site in an "
        "existing Campbell, California office building sharing a PG&E service "
        f"with t={N['ZERO']} at local midnight on a business weekday, capped at "
        f"{N['GRID_CAP_MW']} MW. It has {N['SLURM_COUNT']} Slurm training jobs, "
        f"{N['K8S_COUNT']:,} Kubernetes inference sessions serving Mistral and "
        f"Cohere LLMs, and {N['RAY_COUNT']:,} short Ray agentic API calls; all use "
        "hopper_8gpu_air. The seeded workload generator uses seed "
        f"{N['SEED']}. DR-2026-11-02-PROXIM8-MIDNIGHT (PROPOSED_HERE): "
        f"{N['K8S_MIDNIGHT_CARRYOVER_COUNT']} overnight Kubernetes sessions start "
        "at midnight as 24/7 inference carry-over from the previous day. "
        "Physical sizing, workload timing, BESS sizing, office PUE, "
        "building curve and diesel placeholder are PROPOSED_HERE, illustrative "
        "assumptions rather than measured Proxim8 data. "
        "DR-2026-11-02-PROXIM8-COOLING (PROPOSED_HERE): "
        "non_gpu_load_profile_mw is building non-HVAC electricity "
        "(lighting, elevators and tenant plug loads); the existing engine "
        "cooling envelope adds modelled HVAC on top without changing alpha_max "
        "or other cooling parameters. The curve is scaled using the actual "
        "steady-state relation input + alpha_max × lagged input, so at "
        f"alpha_max={N['ALPHA_MAX']} its input is target/("
        f"{N['ONE']}+alpha_max): about {N['BUILDING_NIGHT_MW']} MW total "
        f"overnight, ramping {int(N['HOUR_06'])}:00–{int(N['HOUR_09'])}:00, "
        f"about {N['BUILDING_PEAK_MW']} MW "
        f"{int(N['HOUR_13'])}:00–{int(N['HOUR_17'])}:00, and "
        f"{N['BUILDING_EVENING_MW']} MW by {int(N['HOUR_21'])}:00. A "
        f"{N['BESS_MW']} MW / {N['BESS_MWH']} MWh grid-forming BESS starts at "
        f"{N['BESS_INITIAL_SOC']:.0%} SoC and can recharge from grid "
        "headroom; no SoC-floor workaround is needed. "
        "No turbines, solar or fuel cells are configured; the diesel block is "
        "disabled. The built-in PG&E Schedule B-20 TOU rates are selected with "
        f"the July calendar month; {N['GRID_PRICE_FALLBACK_MWH']} USD/MWh is "
        "the flat operating-cost fallback."
    )


def build_scenario() -> dict[str, object]:
    profile = _make_profile()
    events = _make_events()
    return {
        "name": "Proxim8",
        "description": _description(),
        "site_name": "Proxim8 distributed-inference site, Campbell, CA",
        "workload_events": events,
        "hardware_profile_id": "hopper_8gpu_air",
        "end_sim_time": N["DAY_SECONDS"],
        "island_mode": False,
        "grid_import_limit_mw": N["GRID_CAP_MW"],
        "grid_import_price_per_mwh": N["GRID_PRICE_FALLBACK_MWH"],
        "edl_calendar_month": N["EDL_MONTH"],
        "procurement_config": {
            "firm_available_mw": N["GRID_FIRM_MW"],
            "reserved_available_mw": N["GRID_ZERO_MW"],
            "non_firm_available_mw": N["GRID_ZERO_MW"],
            "price_curve_seed": N["SEED"],
        },
        "bess_units": [
            {
                "asset_id": "bess-proxim8",
                "rated_mw": N["BESS_MW"],
                "usable_mwh": N["BESS_MWH"],
                "initial_soc_fraction": N["BESS_INITIAL_SOC"],
                "grid_forming": True,
                "p_anchor_reserve_mw": N["BESS_ANCHOR_MW"],
                "authority_tier": "autonomous",
            }
        ],
        "ui_bess_rated_mw": N["BESS_MW"],
        "ui_bess_usable_mwh": N["BESS_MWH"],
        "bess_normal_dispatch_depth_fraction": N["BESS_DISPATCH_DEPTH"],
        "turbine_units": [],
        "solar_rated_mw": N["ZERO_FLOAT"],
        "pue_base": N["PUE_BASE"],
        "non_gpu_load_profile_mw": profile,
        "diesel_power_block": {
            "enabled": False,
            "target_capacity_mw": N["DIESEL_MW"],
            "unit_rating_mw": N["DIESEL_MW"],
            "authority_tier": "advisory_only",
        },
        "operating_cost_inputs": {
            "diesel_price_usd_per_gal": None,
            "diesel_price_usd_per_gal_provenance": (
                "Not configured because the diesel block is disabled."
            ),
            "currency_year": "2026 USD",
            "currency_year_provenance": (
                "PROPOSED_HERE: PG&E B-20 rates are in USD; the flat grid price "
                "is the operating-cost fallback."
            ),
        },
        "grid_tariff_reference": {
            "utility": "Pacific Gas & Electric",
            "rate_schedule": "Schedule B-20 TOU",
            "service_location": "Campbell, California",
            "currency": "USD",
            "summer_off_peak_usd_per_mwh": N["GRID_PRICE_FALLBACK_MWH"],
            "summer_part_peak_usd_per_mwh": N["PGE_SUMMER_PART_MWH"],
            "summer_peak_usd_per_mwh": N["PGE_SUMMER_PEAK_MWH"],
            "winter_off_peak_usd_per_mwh": N["PGE_WINTER_OFF_MWH"],
            "winter_super_off_peak_usd_per_mwh": N["PGE_WINTER_SUPER_OFF_MWH"],
            "source": (
                "core/economic_dispatch_loop.py pge_price_for_period; "
                "Cal. P.U.C. Sheet 61081-E, effective 2026-03-01."
            ),
            "consumed_by_simulator": False,
            "dispatch_tou_consumed_by_edl": True,
        },
        "provenance_proxim8": {
            "generator_seed": N["SEED"],
            "cooling_decision": (
                "DR-2026-11-02-PROXIM8-COOLING (PROPOSED_HERE): building HVAC "
                "uses the existing engine cooling envelope on top of non-HVAC load."
            ),
            "generation_note": (
                "Scripted start/end events only; no kube_config, kube_clusters, "
                "or slurm_config."
            ),
        },
    }


def _clock(time_s: int) -> str:
    hours, remainder = divmod(time_s, N["SECONDS_PER_HOUR"])
    minutes, _seconds = divmod(remainder, N["SECONDS_PER_MINUTE"])
    return f"{hours:02d}:{minutes:02d}"


def main() -> None:
    scenario = build_scenario()
    SCENARIO_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCENARIO_PATH.write_text(
        json.dumps(
            scenario,
            ensure_ascii=False,
            indent=N["JSON_INDENT"],
        )
        + "\n",
        encoding="utf-8",
    )
    starts = [
        event
        for event in scenario["workload_events"]
        if event["event_type"] == "starting"
    ]
    counts = Counter(event["scheduler_type"] for event in starts)
    (
        peak_mw,
        peak_time_s,
        above_cap_seconds,
        sampled_demand,
        afternoon_summary,
    ) = _estimate_nameplate_demand(
        scenario["non_gpu_load_profile_mw"],
        scenario["workload_events"],
    )
    print(f"scenario_path={SCENARIO_PATH}")
    print(f"generator_seed={N['SEED']}")
    print(f"event_records={len(scenario['workload_events'])}")
    print(f"job_counts_by_scheduler={json.dumps(dict(sorted(counts.items())))}")
    print(
        "building_curve_points="
        + json.dumps(
            _cooling_report_points(scenario["non_gpu_load_profile_mw"]),
            sort_keys=True,
        )
    )
    print(
        "nameplate_demand_estimate="
        + json.dumps(
            {
                "peak_mw": peak_mw,
                "peak_time": _clock(peak_time_s),
                "minutes_above_5mw": (
                    above_cap_seconds / N["SECONDS_PER_MINUTE"]
                ),
                "method": (
                    "5-second nameplate estimate with PUE-inclusive job power "
                    "and per-job delayed alpha cooling; not a simulation result"
                ),
            },
            sort_keys=True,
        )
    )
    print(
        "combined_demand_samples="
        + json.dumps(
            {
                "at_02_00_mw": sampled_demand["overnight_02"],
                "at_07_00_mw": sampled_demand["morning_07"],
                "at_15_00_mw": sampled_demand["afternoon_15"],
                "afternoon_13_00_to_17_00_mw": afternoon_summary,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
