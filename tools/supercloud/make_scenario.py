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
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from convert_to_kube_trace import (  # noqa: E402  (single source for parsing/encodings)
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


@dataclass(frozen=True)
class GpuJob:
    start_s: float      # seconds from window start, clipped at 0
    end_s: Optional[float]  # None if the job runs past the window end
    gpus: int
    started_before_window: bool


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
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (scenario spec dict, aggregate build report)."""
    if not jobs:
        raise ValueError(f"no GPU jobs overlap {day.isoformat()}")
    peak_gpus = peak_concurrency([(j.start_s, j.end_s, j.gpus) for j in jobs])
    chassis_per_gpu = (peak_mw * 1000.0 / rated_kw) / peak_gpus
    events: list[dict[str, Any]] = []
    weighted = []
    for i, job in enumerate(jobs, start=1):
        chassis = max(1, round(job.gpus * chassis_per_gpu))
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
        "name": SCENARIO_NAME,
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
    return spec, report


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
    ap.add_argument("--out", type=Path, required=True, help="write OUTSIDE public repositories")
    args = ap.parse_args(argv)

    day = date.fromisoformat(args.date)
    with args.slurm_log.open(newline="", encoding="utf-8-sig") as fh:
        jobs, skipped = gpu_jobs_for_day(csv.DictReader(fh), day, args.partitions.split(","))
    template = json.loads(args.template.read_text(encoding="utf-8"))
    spec, report = build_scenario(
        jobs, template, day=day, peak_mw=args.peak_mw,
        rated_kw=_rated_kw(args.profile, args.sim_root), profile_id=args.profile,
    )
    report["skipped"] = dict(skipped)
    report["template"] = args.template.name
    args.out.write_text(json.dumps(spec, indent=1) + "\n", encoding="utf-8")
    args.out.with_suffix(".build.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
