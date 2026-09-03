"""Read-only PAS sizing comparisons for retained trace imports."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from runtime.periodic_trace_comparison import (
    DEFAULT_BASELINE_RESERVE_PERCENT,
    DEFAULT_PAS_CONFIDENCE_SCALE,
    DEFAULT_PAS_PERCENTILE,
    compare_import_report,
)
from api.db import (
    load_trace_comparison_report,
    load_trace_import_report,
    persist_trace_comparison_report,
)

router = APIRouter(prefix="/api/scenario-planner", tags=["scenario-planner"])


@router.post("/compare-trace/{import_id}")
async def compare_trace(import_id: str, request: Request) -> dict[str, Any]:
    import_report = await load_trace_import_report(import_id)
    if import_report is None:
        raise HTTPException(status_code=404, detail="Imported trace not found")
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Comparison settings must be a JSON object")
    try:
        report = compare_import_report(
            import_report,
            baseline_reserve_percent=body.get(
                "baseline_reserve_percent",
                DEFAULT_BASELINE_RESERVE_PERCENT,
            ),
            pas_percentile=body.get("pas_percentile", DEFAULT_PAS_PERCENTILE),
            pas_confidence_scale=body.get(
                "pas_confidence_scale",
                DEFAULT_PAS_CONFIDENCE_SCALE,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await persist_trace_comparison_report(report)
    return report


@router.get("/compare-trace/{comparison_id}")
async def get_trace_comparison(comparison_id: str, request: Request) -> dict[str, Any]:
    report = await load_trace_comparison_report(comparison_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Trace comparison not found")
    return report