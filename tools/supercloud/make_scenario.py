#!/usr/bin/env python3
"""Generate scenario S10 from one real day of MIT SuperCloud GPU jobs.

DR-2026-10-19-SUPERCLOUD-INGEST §10.  "H100-equivalent shape" route, approved
2026-10-20:

* Workload = every real GPU job running during the chosen UTC day, one
  ``starting`` / ``job_end`` event pair per job, at the job's REAL start and
  end times (no replay, so IMPL-SC-1 does not apply).
* Each job's V100 count is scaled to H100-chassis equivalents on an existing
  hardware profile so the day's peak concurrent GPU demand equals
  ``--peak-mw`` of compute.  This keeps the real timing pattern -- arrivals,
  durations, synchronous whole-cluster gang starts -- but NOT V100 power
  physics.  The scale factor is a modelling choice (PROPOSED_HERE), not data.
* The power side (turbines, BESS, protection, PUE, lead time) is copied from a
  template scenario.  Every synthetic load source in the template is
  neutralised so only trace events drive compute demand: kube_config,
  load_config, cluster_gen_config, workload_floor_fraction, gpu_load_profile,
  and solar.

Licence: the source data is CC BY-NC-ND 4.0.  The generated scenario is an
adaptation of row-level data: keep it out of public repositories and load it
through POST /scenarios (editor/upload).  Only this generator is committed.

Usage:
    python3 tools/supercloud/make_scenario.py slurm-log.csv \
        --date 2021-08-11 --peak-mw 50 \
        --template <gridsignal_sim>/config/scenarios/demo-islanded-ramp.json \
        --out S10_supercloud_gpu_day.json
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from convert_to_kube_trace import (  # noqa: E402  (single source for parsing/encodings)
    TRES_CPU,
    TRES_GPU_TESLA,
    TRES_GPU_VOLTA,
    Quarantine,
    parse_row,
)

DAY_S = 86_400
# PROPOSED_HERE: scale target.  Matches the 50 MW design-manual site; it sets
# magnitude only.  Rationale: DR §10.  Override with --peak-mw.
DEFAULT_PEAK_MW = 50.0
DEFAULT_PROFILE = "hopper_8gpu_air"   # canonical H100 8-GPU chassis, 10.2 kW
DEFAULT_PARTITIONS = ("normal", "gaia", "test")
SCENARIO_NAME = "S10 — SuperCloud real GPU day (H100-equivalent shape)"

# PROPOSED_HERE: CPU package power per allocated core, scaled by the same
# chassis_per_gpu factor as the GPU trace. Sources/rationales: xeon-p8 uses
# Platinum 8260 (165 W / 24 cores = 6.875 W/core; Intel ARK, MIT Dataset
# paper Table II, and MIT SuperCloud systems page). normal and db use the
# higher documented Gold 6248 (150 W / 20 cores = 7.5 W/core) per Lloyd's
# 2026-10-23 ruling, labelled INFERRED because those partition mappings are
# not stated by a citable source. Package power only; no overhead is added.
CPU_WATTS_PER_CORE = {
    "xeon-p8": {
        "watts_per_core": 6.875,
        "status": "CITED",
        "source": (
            "Intel Xeon Platinum 8260 ARK "
            "(https://www.intel.com/content/www/us/en/products/sku/192474/"
            "intel-xeon-platinum-8260-processor-35-75m-cache-2-40-ghz/"
            "specifications.html; 165 W / 24 cores); MIT SuperCloud Dataset "
            "paper Table II (https://arxiv.org/abs/2108.02037); MIT SuperCloud "
            "systems page (https://mit-supercloud.github.io/supercloud-docs/"
            "systems-and-software/)"
        ),
    },
    "normal": {
        "watts_per_core": 7.5,
        "status": "INFERRED",
        "source": (
            "Lloyd ruling 2026-10-23; Intel Xeon Gold 6248 ARK "
            "(https://www.intel.com/content/www/us/en/products/sku/192446/"
            "intel-xeon-gold-6248-processor-27-5m-cache-2-50-ghz/"
            "specifications.html; 150 W / 20 cores); normal has all 154 GPU "
            "jobs, but partition mapping is not independently sourced"
        ),
    },
    "db": {
        "watts_per_core": 7.5,
        "status": "INFERRED",
        "source": (
            "Lloyd ruling 2026-10-23; same Xeon Gold 6248 ARK "
            "(https://www.intel.com/content/www/us/en/products/sku/192446/"
            "intel-xeon-gold-6248-processor-27-5m-cache-2-50-ghz/"
            "specifications.html; 150 W / 20 cores) basis as normal; "
            "partition mapping is not independently sourced"
        ),
    },
}
# PROPOSED_HERE: sensitivity case applies the cited xeon-p8 value to normal/db
# to quantify the effect of their inferred 7.5 W/core assumptions (Intel ARK:
# Platinum 8260, 165 W / 24 cores).
CPU_SENSITIVITY_WATTS_PER_CORE = 6.875

@dataclass(frozen=True)
class GpuJob:
    start_s: float      # seconds from window start, clipped at 0
    end_s: Optional[float]  # None if the job runs past the window end
    gpus: int
    started_before_window: bool


@dataclass(frozen=True)
class CpuJob:
    start_s: float
    end_s: float
    allocated_cores: int
    partition: str


def gpu_jobs_for_day(
    rows: Iterable[dict[str, str]],
    day: date,
    partitions: Iterable[str] = DEFAULT_PARTITIONS,
) -> tuple[list[GpuJob], Counter[str]]:
    """Real GPU jobs that overlap ``day`` (UTC), with times relative to 00:00."""
    lo = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())
    hi = lo + DAY_S
    parts = set(partitions)
    skipped: Counter[str] = Counter()
    jobs: list[GpuJob] = []
    for raw in rows:
        try:
            r = parse_row(raw)
        except Quarantine as q:
            skipped[f"parse:{q.reason}"] += 1
            continue
        gpus = r.tres_alloc.get(TRES_GPU_VOLTA, 0) + r.tres_alloc.get(TRES_GPU_TESLA, 0)
        if not gpus or r.partition not in parts:
            continue
        if r.time_start <= 0 or r.time_end < r.time_start:
            skipped["bad_times"] += 1
            continue
        if r.time_end <= lo or r.time_start >= hi:
            continue
        if r.time_end == r.time_start:
            skipped["zero_duration"] += 1
            continue
        jobs.append(GpuJob(
            start_s=float(max(r.time_start, lo) - lo),
            end_s=float(r.time_end - lo) if r.time_end < hi else None,
            gpus=gpus,
            started_before_window=r.time_start < lo,
        ))
    jobs.sort(key=lambda j: (j.start_s, j.end_s if j.end_s is not None else DAY_S))
    return jobs, skipped


def cpu_only_jobs_for_day(
    rows: Iterable[dict[str, str]],
    day: date,
) -> tuple[list[CpuJob], Counter[str]]:
    """CPU-only allocations from every partition that overlap one UTC day."""
    lo = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())
    hi = lo + DAY_S
    skipped: Counter[str] = Counter()
    jobs: list[CpuJob] = []
    for raw in rows:
        try:
            row = parse_row(raw)
        except Quarantine as quarantine:
            skipped[f"parse:{quarantine.reason}"] += 1
            continue
        if row.tres_alloc.get(TRES_GPU_TESLA, 0) or row.tres_alloc.get(TRES_GPU_VOLTA, 0):
            continue
        cores = int(row.tres_alloc.get(TRES_CPU, 0))
        if cores <= 0:
            continue
        if row.partition not in CPU_WATTS_PER_CORE:
            if row.time_start < hi and row.time_end > lo:
                raise ValueError(
                    f"CPU-only allocation uses unsupported partition {row.partition!r}"
                )
            continue
        if row.time_start <= 0 or row.time_end < row.time_start:
            skipped["bad_times"] += 1
            continue
        if row.time_end <= lo or row.time_start >= hi or row.time_end == row.time_start:
            continue
        jobs.append(
            CpuJob(
                start_s=float(max(row.time_start, lo) - lo),
                end_s=float(min(row.time_end, hi) - lo),
                allocated_cores=cores,
                partition=row.partition,
            )
        )
    jobs.sort(key=lambda job: (job.start_s, job.end_s, job.partition))
    return jobs, skipped


def _profile_from_power_events(
    power_events: dict[float, float],
) -> list[list[float]]:
    """Convert summed start/end deltas into a strict zero-order-hold profile."""
    profile: list[list[float]] = [[0.0, 0.0]]
    active_mw = 0.0
    for time_s, delta_mw in sorted(power_events.items()):
        active_mw += delta_mw
        if time_s == 0.0:
            profile[0][1] = active_mw
        else:
            profile.append([float(time_s), float(active_mw)])
    if not profile:
        return [[0.0, 0.0]]
    # Preserve strict timestamp ordering when a final event occurs at the
    # end-of-day boundary; no point after the run duration is emitted.
    return profile


def cpu_load_profile_mw(
    jobs: list[CpuJob],
    *,
    chassis_per_gpu: float,
    watts_per_core: dict[str, float] | None = None,
) -> list[list[float]]:
    """Create additive CPU package-load MW at each job start/end boundary."""
    rates = watts_per_core or {
        partition: float(values["watts_per_core"])
        for partition, values in CPU_WATTS_PER_CORE.items()
    }
    events: dict[float, float] = defaultdict(float)
    for job in jobs:
        power_mw = (
            job.allocated_cores
            * float(rates[job.partition])
            * float(chassis_per_gpu)
            / 1_000_000.0
        )
        events[job.start_s] += power_mw
        events[job.end_s] -= power_mw
    profile = _profile_from_power_events(dict(events))
    # Simultaneous floating-point event cancellation can leave a tiny negative
    # residual; CPU demand is physically non-negative and the schema requires it.
    return [[time_s, max(0.0, power_mw)] for time_s, power_mw in profile]


def _profile_summary(profile: list[list[float]]) -> dict[str, float]:
    """Time-weighted MW distribution and MWh for a zero-order-hold profile."""
    intervals: list[tuple[float, float, float]] = []
    for index, (start_s, load_mw) in enumerate(profile):
        end_s = profile[index + 1][0] if index + 1 < len(profile) else float(DAY_S)
        if end_s > start_s:
            intervals.append((start_s, end_s, load_mw))
    if not intervals:
        intervals = [(0.0, float(DAY_S), 0.0)]
    total_s = sum(end - start for start, end, _ in intervals)
    energy_mwh = sum((end - start) * mw / 3600.0 for start, end, mw in intervals)
    target_s = 0.95 * total_s
    cumulative_s = 0.0
    p95_mw = 0.0
    for _start, _end, mw in sorted(intervals, key=lambda interval: interval[2]):
        cumulative_s += _end - _start
        p95_mw = mw
        if cumulative_s >= target_s:
            break
    return {
        "min_mw": min(mw for _start, _end, mw in intervals),
        "mean_mw": energy_mwh / (total_s / 3600.0),
        "p95_mw": p95_mw,
        "max_mw": max(mw for _start, _end, mw in intervals),
        "energy_mwh": energy_mwh,
    }


def peak_concurrency(jobs: list[tuple[float, Optional[float], int]]) -> int:
    """Peak of summed weights; ends sort before starts at equal timestamps."""
    events = []
    for start, end, w in jobs:
        events.append((start, 1, w))
        if end is not None:
            events.append((end, -1, w))
    cur = peak = 0
    for _t, sign, w in sorted(events, key=lambda e: (e[0], e[1])):
        cur += sign * w
        peak = max(peak, cur)
    return peak


def build_scenario(
    jobs: list[GpuJob],
    template: dict[str, Any],
    *,
    day: date,
    peak_mw: float,
    rated_kw: float,
    profile_id: str = DEFAULT_PROFILE,
    name: str = SCENARIO_NAME,
    cpu_jobs: list[CpuJob] | None = None,
    gpu_partitions: tuple[str, ...] = DEFAULT_PARTITIONS,
    generator_commit: str | None = None,
    input_sha256: str | None = None,
    template_name: str | None = None,
    initial_soc_fraction: float | None = None,
    soc_derivation: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (scenario spec dict, aggregate build report)."""
    if not jobs:
        raise ValueError(f"no GPU jobs overlap {day.isoformat()}")
    peak_gpus = peak_concurrency([(j.start_s, j.end_s, j.gpus) for j in jobs])
    chassis_per_gpu = (peak_mw * 1000.0 / rated_kw) / peak_gpus
    events: list[dict[str, Any]] = []
    weighted = []
    gpu_power_events: dict[float, float] = defaultdict(float)
    for i, job in enumerate(jobs, start=1):
        chassis = max(1, round(job.gpus * chassis_per_gpu))
        gpu_mw = chassis * rated_kw / 1000.0
        gpu_power_events[job.start_s] += gpu_mw
        gpu_power_events[job.end_s if job.end_s is not None else float(DAY_S)] -= gpu_mw
        job_id = f"s10-job-{i:05d}"
        events.append({
            "event_id": f"evt-{job_id}-start", "job_id": job_id, "event_type": "starting",
            "timestamp": job.start_s, "node_count": chassis,
            "hardware_profile_id": profile_id, "scheduler_type": "SLURM",
        })
        if job.end_s is not None:
            events.append({
                "event_id": f"evt-{job_id}-end", "job_id": job_id, "event_type": "job_end",
                "timestamp": job.end_s, "node_count": 0,
                "hardware_profile_id": profile_id, "scheduler_type": "SLURM",
            })
        weighted.append((job.start_s, job.end_s, chassis))
    events.sort(key=lambda e: (e["timestamp"], e["event_type"] != "job_end"))
    peak_chassis = peak_concurrency(weighted)
    peak_compute_mw = round(peak_chassis * rated_kw / 1000.0, 3)

    spec = copy.deepcopy(template)
    spec.update({
        "name": name,
        "description": (
            f"Real GPU job timeline from the MIT SuperCloud TX-GAIA cluster for "
            f"{day.isoformat()} (UTC), replayed at its true start and end times. "
            f"{len(jobs)} GPU jobs; peak {peak_gpus} concurrent V100s scaled to "
            f"{peak_compute_mw} MW of H100-chassis-equivalent compute "
            f"(scale factor is a modelling choice, PROPOSED_HERE). This day "
            f"follows a maintenance drain: repeated whole-cluster gang jobs step "
            f"the site between near-zero and full GPU load within seconds, then "
            f"production work refills in the evening. Shape is real; V100 power "
            f"physics are not modelled. Source data CC BY-NC-ND 4.0 — internal use."
        ),
        "hardware_profile_id": profile_id,
        "end_sim_time": float(DAY_S),
        "workload_events": events,
        # Neutralise every synthetic load source so only trace events drive compute.
        "kube_config": None,
        "load_config": None,
        "cluster_gen_config": None,
        "stressor_gen_config": None,
        "param_sampling_config": None,
        "telemetry_corruption_config": None,
        "workload_floor_fraction": None,
        "gpu_load_profile": [],
        "solar_rated_mw": 0.0,
        "irradiance_steps": [[0.0, 1.0]],
        "design_peak_load_mw": peak_compute_mw,
        "assertions": [],
    })
    if initial_soc_fraction is not None:
        # PROPOSED_HERE: apply the D6a startup-surplus-derived initial SoC
        # supplied by the evidence run; do not tune it to a desired outcome.
        if not math.isfinite(initial_soc_fraction) or not 0.0 <= initial_soc_fraction <= 1.0:
            raise ValueError("initial_soc_fraction must be finite and in [0, 1]")
        bess_units = spec.get("bess_units") or []
        if not bess_units:
            raise ValueError("cannot set initial_soc_fraction without a BESS unit")
        for bess in bess_units:
            bess["initial_soc_fraction"] = float(initial_soc_fraction)
        spec["description"] += (
            " Initial BESS SoC fraction is PROPOSED_HERE and derived from the "
            "startup must-run surplus-energy rule in DR-2026-10-20-ISLAND-COLLAPSE "
            "D6a.4; evidence: "
            + json.dumps(soc_derivation or {}, sort_keys=True, separators=(",", ":"))
            + "."
        )
    for key in ("kube_clusters", "tenant_events", "tenant_budgets", "jobs"):
        if key in spec:
            spec[key] = [] if isinstance(spec[key], list) else None
    report = {
        "schema_version": "supercloud-s10-build-v1",
        "day_utc": day.isoformat(),
        "gpu_jobs": len(jobs),
        "jobs_started_before_window": sum(j.started_before_window for j in jobs),
        "jobs_running_past_window": sum(j.end_s is None for j in jobs),
        "events": len(events),
        "peak_concurrent_gpus": peak_gpus,
        "chassis_per_gpu": round(chassis_per_gpu, 4),
        "hardware_profile_id": profile_id,
        "rated_kw_per_chassis": rated_kw,
        "target_peak_mw": peak_mw,
        "peak_compute_mw_after_rounding": peak_compute_mw,
        "gpu_count_distribution": dict(Counter(j.gpus for j in jobs).most_common(12)),
    }
    if initial_soc_fraction is not None:
        report["initial_soc_fraction_override"] = float(initial_soc_fraction)
        report["soc_derivation"] = soc_derivation or {}
    if cpu_jobs is not None:
        cpu_profile = cpu_load_profile_mw(
            cpu_jobs,
            chassis_per_gpu=chassis_per_gpu,
        )
        gpu_profile = _profile_from_power_events(dict(gpu_power_events))
        cpu_stats = _profile_summary(cpu_profile)
        gpu_stats = _profile_summary(gpu_profile)
        cpu_by_partition: dict[str, dict[str, float | int]] = {}
        for partition in sorted(CPU_WATTS_PER_CORE):
            selected = [job for job in cpu_jobs if job.partition == partition]
            cpu_by_partition[partition] = {
                "jobs": len(selected),
                "core_hours": sum(
                    (job.end_s - job.start_s) * job.allocated_cores / 3600.0
                    for job in selected
                ),
                "allocated_cores_min": min(
                    (job.allocated_cores for job in selected), default=0
                ),
                "allocated_cores_max": max(
                    (job.allocated_cores for job in selected), default=0
                ),
            }
        low_rates = {
            partition: (
                CPU_SENSITIVITY_WATTS_PER_CORE
                if partition in {"normal", "db"}
                else float(values["watts_per_core"])
            )
            for partition, values in CPU_WATTS_PER_CORE.items()
        }
        sensitivity_profile = cpu_load_profile_mw(
            cpu_jobs,
            chassis_per_gpu=chassis_per_gpu,
            watts_per_core=low_rates,
        )
        sensitivity_stats = _profile_summary(sensitivity_profile)
        invocation = {
            "date_utc": day.isoformat(),
            "template": template_name or "unknown",
            "peak_mw": float(peak_mw),
            "profile": profile_id,
            "gpu_partitions": list(gpu_partitions),
            "gpu_partitions_status": "INFERRED; historical invocation was not saved",
            "cpu_partitions": "all active partitions",
            "cpu_power_by_partition": CPU_WATTS_PER_CORE,
            "generator_commit": generator_commit or "unknown",
            "input_sha256": input_sha256 or "unknown",
            "scale_factor_chassis_per_gpu": chassis_per_gpu,
            "power_scope": "CPU package power only; no memory, fans, or PSU overhead",
            "initial_soc_fraction_override": initial_soc_fraction,
            "initial_soc_by_bess": {
                str(unit.get("asset_id", index)): unit.get("initial_soc_fraction")
                for index, unit in enumerate(spec.get("bess_units") or [])
            },
            "soc_derivation": soc_derivation,
        }
        spec["non_gpu_load_profile_mw"] = cpu_profile
        spec["description"] += (
            " Additive CPU-only package-power load (D6a, PROPOSED_HERE); "
            "per-core power and cited/inferred labels are recorded in the "
            "invocation metadata: "
            + json.dumps(invocation, sort_keys=True, separators=(",", ":"))
            + "."
        )
        cpu_energy = float(cpu_stats["energy_mwh"])
        gpu_energy = float(gpu_stats["energy_mwh"])
        report.update(
            {
                "cpu_only_jobs": len(cpu_jobs),
                "cpu_only_jobs_by_partition": cpu_by_partition,
                "cpu_watts_per_core": CPU_WATTS_PER_CORE,
                "cpu_power_scope": "package power only; no memory, fans, or PSU overhead",
                "cpu_load_profile_mw": cpu_profile,
                "cpu_mw_profile_stats": cpu_stats,
                "gpu_mw_profile_stats": gpu_stats,
                "cpu_share_of_total_it_demand": (
                    cpu_energy / (cpu_energy + gpu_energy)
                    if cpu_energy + gpu_energy > 0.0
                    else 0.0
                ),
                "cpu_sensitivity_6_875_w_per_core": {
                    "normal_and_db_w_per_core": CPU_SENSITIVITY_WATTS_PER_CORE,
                    "cpu_mw_profile_stats": sensitivity_stats,
                    "cpu_energy_delta_mwh": sensitivity_stats["energy_mwh"] - cpu_energy,
                    "total_it_demand_delta_mwh": (
                        sensitivity_stats["energy_mwh"] - cpu_energy
                    ),
                },
                "invocation": invocation,
            }
        )
    return spec, report


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_head(repo: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        text=True,
        cwd=repo,
    ).strip()


def _rated_kw(profile_id: str, sim_root: Optional[Path]) -> float:
    """Read rated_kw from the simulator's hardware library (single source)."""
    if sim_root is not None:
        sys.path.insert(0, str(sim_root))
    from runtime.scenario_factory import DEFAULT_HARDWARE_LIBRARY  # noqa: E402
    if profile_id not in DEFAULT_HARDWARE_LIBRARY:
        raise ValueError(f"unknown hardware profile {profile_id!r}")
    return float(DEFAULT_HARDWARE_LIBRARY[profile_id].rated_kw)


def main(argv: Optional[list[str]] = None) -> int:
    repo = HERE.parents[1]
    sim_default = repo / "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim"
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("slurm_log", type=Path)
    ap.add_argument("--date", required=True, help="UTC day, YYYY-MM-DD")
    ap.add_argument("--peak-mw", type=float, default=DEFAULT_PEAK_MW,
                    help=f"peak compute MW to scale to (PROPOSED_HERE, default {DEFAULT_PEAK_MW})")
    ap.add_argument("--template", type=Path,
                    default=sim_default / "config/scenarios/demo-islanded-ramp.json")
    ap.add_argument("--profile", default=DEFAULT_PROFILE)
    ap.add_argument("--partitions", default=",".join(DEFAULT_PARTITIONS))
    ap.add_argument("--sim-root", type=Path, default=sim_default)
    ap.add_argument("--name", default=SCENARIO_NAME, help="scenario display name")
    ap.add_argument(
        "--initial-soc-fraction",
        type=float,
        default=None,
        help="PROPOSED_HERE: derived D6a startup-surplus initial SoC fraction",
    )
    ap.add_argument(
        "--soc-derivation-json",
        type=Path,
        default=None,
        help="aggregate-only D6a startup-surplus derivation evidence",
    )
    ap.add_argument("--out", type=Path, required=True, help="write OUTSIDE public repositories")
    args = ap.parse_args(argv)

    day = date.fromisoformat(args.date)
    gpu_partitions = tuple(
        partition.strip()
        for partition in args.partitions.split(",")
        if partition.strip()
    )
    with args.slurm_log.open(newline="", encoding="utf-8-sig") as fh:
        jobs, skipped = gpu_jobs_for_day(csv.DictReader(fh), day, gpu_partitions)
    with args.slurm_log.open(newline="", encoding="utf-8-sig") as fh:
        cpu_jobs, cpu_skipped = cpu_only_jobs_for_day(csv.DictReader(fh), day)
    template = json.loads(args.template.read_text(encoding="utf-8"))
    input_sha256 = _file_sha256(args.slurm_log)
    generator_commit = _git_head(repo)
    soc_derivation = (
        json.loads(args.soc_derivation_json.read_text(encoding="utf-8"))
        if args.soc_derivation_json is not None
        else None
    )
    if args.soc_derivation_json is not None and not isinstance(soc_derivation, dict):
        raise ValueError("--soc-derivation-json must contain a JSON object")
    spec, report = build_scenario(
        jobs, template, day=day, peak_mw=args.peak_mw,
        rated_kw=_rated_kw(args.profile, args.sim_root), profile_id=args.profile,
        name=args.name, cpu_jobs=cpu_jobs, gpu_partitions=gpu_partitions,
        generator_commit=generator_commit, input_sha256=input_sha256,
        template_name=args.template.name,
        initial_soc_fraction=args.initial_soc_fraction,
        soc_derivation=soc_derivation,
    )
    report["skipped"] = dict(skipped)
    report["cpu_skipped"] = dict(cpu_skipped)
    report["template"] = args.template.name
    args.out.write_text(json.dumps(spec, indent=1) + "\n", encoding="utf-8")
    args.out.with_suffix(".build.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
