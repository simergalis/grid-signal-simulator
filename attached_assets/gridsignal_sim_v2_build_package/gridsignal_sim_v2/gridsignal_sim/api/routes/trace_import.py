"""Unified Periodic Trace Import API."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from runtime.periodic_trace_import import TraceDomainConfig, import_periodic_trace
from runtime.trace_site_capacity import SITE_TRACE_DOMAIN_CAPACITY
from api.db import load_trace_import_report, persist_trace_import_report

router = APIRouter(prefix="/api/scenario-planner", tags=["scenario-planner"])
MAX_TRACE_BYTES = 5 * 1024 * 1024


def _normalise_domain(value: object) -> str | None:
    normalised = str(value or "").strip().lower()
    return {
        "k8s": "kubernetes",
        "kubernetes": "kubernetes",
        "slurm": "slurm",
        "ray": "ray",
    }.get(normalised)


def _domain_configs(raw: dict[str, Any]) -> dict[str, TraceDomainConfig]:
    result = {
        "kubernetes": TraceDomainConfig(),
        "slurm": TraceDomainConfig(),
        "ray": TraceDomainConfig(),
    }
    kube = raw.get("kube_config")
    if isinstance(kube, dict):
        result["kubernetes"] = TraceDomainConfig(
            configured=True,
            max_units=int(kube["max_nodes"]) if kube.get("max_nodes") is not None else None,
        )
    for cluster in raw.get("kube_clusters", []) or []:
        scheduler = _normalise_domain(cluster.get("scheduler_type"))
        if scheduler is None:
            continue
        previous = result[scheduler]
        cluster_max = int(cluster["max_nodes"]) if cluster.get("max_nodes") is not None else None
        total_max = (
            (previous.max_units or 0) + (cluster_max or 0)
            if previous.max_units is not None and cluster_max is not None
            else cluster_max
        )
        result[scheduler] = TraceDomainConfig(
            configured=True,
            max_units=total_max,
            unit=str(cluster.get("capacity_unit", "node")),
        )

    inference_domains = set()
    for event in raw.get("workload_events", []) or []:
        if str(event.get("workload_class", "")).lower() == "inference":
            domain = _normalise_domain(event.get("scheduler_domain"))
            if domain is not None:
                inference_domains.add(domain)
    return {
        name: TraceDomainConfig(
            configured=config.configured,
            max_units=config.max_units,
            unit=config.unit,
            inference=name in inference_domains,
        )
        for name, config in result.items()
    }


def _scenario_inference_domains(raw: dict[str, Any]) -> set[str]:
    return {
        domain
        for event in raw.get("workload_events", []) or []
        if str(event.get("workload_class", "")).lower() == "inference"
        if (domain := _normalise_domain(event.get("scheduler_domain"))) is not None
    }


@router.post("/import-trace")
async def import_trace(request: Request) -> dict[str, Any]:
    """Import a CSV trace; row-level data errors never reject other rows."""
    scenario_id = request.query_params.get("scenario_id")
    raw_spec: dict[str, Any] = {}
    if scenario_id:
        record = request.app.state.scenario_store.get(scenario_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Scenario {scenario_id!r} not found")
        raw_spec = json.loads(record.spec_json)
    body = await request.body()
    if len(body) > MAX_TRACE_BYTES:
        raise HTTPException(status_code=413, detail="CSV file exceeds 5 MiB import limit")
    try:
        csv_text = body.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded") from exc
    if not csv_text.strip():
        raise HTTPException(status_code=400, detail="CSV file is empty")
    configured_pue = raw_spec.get("pue_base")
    pue = float(configured_pue) if configured_pue is not None else 1.37
    try:
        report = import_periodic_trace(
            csv_text,
            pue=pue,
            site_domain_configs=SITE_TRACE_DOMAIN_CAPACITY,
            inference_domains=_scenario_inference_domains(raw_spec),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await persist_trace_import_report(report)
    return report


@router.get("/import-trace/{import_id}")
async def get_imported_trace(import_id: str, request: Request) -> dict[str, Any]:
    report = await load_trace_import_report(import_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Imported trace not found")
    return report