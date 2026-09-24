"""Addendum H Phase 2b reference-scenario expansion.

The four Phase 2b reference entries are intentionally compact catalogue
records.  At run construction they expand from the unchanged Phase 2a base
scenario, copy only the requested scheduler family, and give every copied
workload identity a cluster-qualified ID.

This module describes workload demand only as scheduler-shaped GPU workload
demand.  It does not claim to reproduce a real Kubernetes, Slurm, or Ray
scheduler.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


_SCENARIO_DIR = Path(__file__).resolve().parents[1] / "config" / "scenarios"
_DEFAULT_BASE = "scenario-uneven-multisched-01.json"
_DAY_SECONDS = 24.0 * 60.0 * 60.0
_CLUSTER_BLOCK_HOURS = (8, 10, 12, 14, 16, 18)
_WEEKEND_BLOCK_HOURS = (8, 12, 16)


def _cluster_offsets(days: int) -> list[tuple[int, float]]:
    offsets: list[tuple[int, float]] = []
    cluster_number = 0
    for day in range(days):
        hours = _WEEKEND_BLOCK_HOURS if day >= 5 else _CLUSTER_BLOCK_HOURS
        for hour in hours:
            cluster_number += 1
            offsets.append(
                (cluster_number, day * _DAY_SECONDS + hour * 3600.0)
            )
    return offsets


def apply_study_fuel_model(
    turbine_units: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return a copied turbine fleet with the existing study fuel overlay."""
    # IMPL-H58: keep the Phase 2b aeroderivative overlay in the study layer.
    return [
        {**copy.deepcopy(turbine), "gt_mode": "aero"}
        for turbine in turbine_units
    ]


def _copy_workload_event(
    event: dict[str, Any],
    *,
    family: str,
    cluster_number: int,
    offset_s: float,
) -> dict[str, Any]:
    copied = copy.deepcopy(event)
    prefix = f"phase2b-{family}-c{cluster_number:02d}-"
    original_event_id = str(event.get("event_id", "event"))
    original_job_id = str(event.get("job_id", "job"))
    copied["event_id"] = prefix + original_event_id
    copied["job_id"] = prefix + original_job_id
    copied["timestamp"] = float(event["timestamp"]) + offset_s
    for key in ("ray_cluster_id", "infrastructure_allocation_id", "ray_workload_id"):
        if copied.get(key) is not None:
            copied[key] = prefix + str(copied[key])
    return copied


def _copy_slurm_job(
    job: dict[str, Any],
    *,
    family: str,
    cluster_number: int,
    offset_s: float,
) -> dict[str, Any]:
    copied = copy.deepcopy(job)
    prefix = f"phase2b-{family}-c{cluster_number:02d}-"
    copied["job_id"] = prefix + str(job["job_id"])
    copied["job_name"] = prefix + str(job.get("job_name", job["job_id"]))
    copied["arrival_time"] = float(job.get("arrival_time", 0.0)) + offset_s
    return copied


def expand_phase2b_reference_spec(spec_data: dict[str, Any]) -> dict[str, Any]:
    """Expand a compact H-1/H-2 catalogue entry into a normal run spec."""
    family = spec_data.get("phase2b_reference_family")
    if family is None:
        return spec_data
    if family not in {"h1", "h2"}:
        raise ValueError(f"unsupported Phase 2b reference family: {family!r}")

    base_name = str(
        spec_data.get("phase2b_reference_base_scenario", _DEFAULT_BASE)
    )
    base_path = _SCENARIO_DIR / base_name
    if not base_path.is_file():
        raise FileNotFoundError(f"Phase 2b base scenario not found: {base_path}")
    base = json.loads(base_path.read_text())
    days = int(spec_data.get("phase2b_reference_days", 1))
    if days not in {1, 7}:
        raise ValueError("Phase 2b reference horizon must be 1 or 7 days")

    expanded = copy.deepcopy(base)
    # These records are intentionally metadata-only.  Do not overlay the
    # Pydantic model's defaulted empty arrays or policy defaults when callers
    # pass model_dump() rather than the original compact JSON.
    expanded["name"] = str(spec_data.get("name", expanded["name"]))
    # Keep this override in the expansion layer so the unchanged Phase 2a base
    # scenario remains unchanged on disk.
    expanded["turbine_units"] = apply_study_fuel_model(
        base.get("turbine_units", [])
    )

    expanded["end_sim_time"] = days * _DAY_SECONDS
    expanded["description"] = (
        f"Addendum H {family.upper()} reference scenario with "
        f"scheduler-shaped GPU workload demand over {days} day(s), "
        "derived from scenario-uneven-multisched-01."
    )
    offsets = _cluster_offsets(days)
    allowed_scheduler = {"K8S", "RAY"} if family == "h1" else {"SLURM"}

    expanded["kube_clusters"] = [
        copy.deepcopy(cluster)
        for cluster in base.get("kube_clusters", [])
        if str(cluster.get("scheduler_type", "")).upper() in allowed_scheduler
    ]
    expanded["workload_events"] = [
        _copy_workload_event(
            event,
            family=family,
            cluster_number=cluster_number,
            offset_s=offset_s,
        )
        for cluster_number, offset_s in offsets
        for event in base.get("workload_events", [])
        if str(event.get("scheduler_type", "")).upper() in allowed_scheduler
    ]

    if family == "h1":
        expanded.pop("slurm_config", None)
    else:
        slurm = copy.deepcopy(base.get("slurm_config"))
        if slurm is None:
            raise ValueError("H-2 reference requires the base slurm_config")
        slurm["jobs"] = [
            _copy_slurm_job(
                job,
                family=family,
                cluster_number=cluster_number,
                offset_s=offset_s,
            )
            for cluster_number, offset_s in offsets
            for job in base.get("slurm_config", {}).get("jobs", [])
        ]
        expanded["slurm_config"] = slurm

    expanded.pop("phase2b_reference_base_scenario", None)
    expanded.pop("phase2b_reference_family", None)
    expanded.pop("phase2b_reference_days", None)
    return expanded