"""Read-only routes for persisted reference forecast datasets."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db import fetch_reference_forecast_rows, get_db_session
from runtime.persistence import ReferenceForecastResolved, ReferenceForecastScenario
from runtime.reference_forecast import reference_forecast_conversion_context

router = APIRouter(prefix="/api/reference-forecast", tags=["reference-forecast"])

DATASET_ID = "equinix-sj-2-52wk-v1"
MAX_ROWS = 10_000


@router.get("/{dataset_id}")
async def get_reference_forecast(
    dataset_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    if dataset_id != DATASET_ID:
        raise HTTPException(404, "Reference forecast dataset not found")

    scenario = await db.get(ReferenceForecastScenario, dataset_id)
    if scenario is None:
        raise HTTPException(404, "Reference forecast dataset not found")

    result = await db.execute(
        select(ReferenceForecastResolved)
        .where(ReferenceForecastResolved.dataset_id == dataset_id)
        .order_by(
            ReferenceForecastResolved.day_of_year,
            ReferenceForecastResolved.hour_of_day,
        )
        .limit(MAX_ROWS)
    )
    rows = [
        {
            "day_of_year": row.day_of_year,
            "hour_of_day": row.hour_of_day,
            "kubernetes_node_count": row.kubernetes_node_count,
            "slurm_node_count": row.slurm_node_count,
            "ray_rack_count": row.ray_rack_count,
        }
        for row in result.scalars()
    ]

    return {
        "dataset": {
            "dataset_id": scenario.dataset_id,
            "display_name": scenario.display_name,
            "span_days": scenario.span_days,
            "source_filename": scenario.source_filename,
            "created_at": scenario.created_at.isoformat(),
        },
        "rows": rows,
        "row_count": len(rows),
        "truncated": len(rows) == MAX_ROWS,
    }


@router.get("/{dataset_id}/rows")
async def get_reference_forecast_rows(
    dataset_id: str,
    start_day: int = Query(..., ge=1, le=366),
    start_hour: int = Query(..., ge=0, le=23),
    end_day: int = Query(..., ge=1, le=366),
    end_hour: int = Query(..., ge=0, le=23),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    if dataset_id != DATASET_ID:
        raise HTTPException(404, "Reference forecast dataset not found")
    if (start_day, start_hour) > (end_day, end_hour):
        raise HTTPException(400, "Reference forecast range must start before it ends")

    scenario = await db.get(ReferenceForecastScenario, dataset_id)
    if scenario is None:
        raise HTTPException(404, "Reference forecast dataset not found")
    if (
        start_day < 1
        or end_day < 1
        or start_day > scenario.span_days
        or end_day > scenario.span_days
    ):
        raise HTTPException(
            400,
            f"Reference forecast range exceeds dataset span of {scenario.span_days} days",
        )

    rows = await fetch_reference_forecast_rows(
        db,
        dataset_id,
        start_day,
        start_hour,
        end_day,
        end_hour,
    )
    profiles, pue_base = reference_forecast_conversion_context()
    # This intentionally uses PARAM-06's generic catalogue default (currently
    # 1.03), not an Equinix SJ-2 calibration. Revisit when SJ-2 has a real PUE.

    def with_derived_metrics(row: dict[str, int]) -> dict[str, Any]:
        kubernetes_mw = (
            row["kubernetes_node_count"] * profiles["kubernetes"].rated_kw * pue_base / 1000.0
        )
        slurm_mw = (
            row["slurm_node_count"] * profiles["slurm"].rated_kw * pue_base / 1000.0
        )
        ray_mw = (
            row["ray_rack_count"] * profiles["ray"].rated_kw * pue_base / 1000.0
        )
        kubernetes_gpus = (
            row["kubernetes_node_count"] * profiles["kubernetes"].gpus_per_unit
        )
        slurm_gpus = row["slurm_node_count"] * profiles["slurm"].gpus_per_unit
        ray_gpus = row["ray_rack_count"] * profiles["ray"].gpus_per_unit
        return {
            **row,
            "kubernetes_mw": round(kubernetes_mw, 6),
            "slurm_mw": round(slurm_mw, 6),
            "ray_mw": round(ray_mw, 6),
            "total_mw": round(kubernetes_mw + slurm_mw + ray_mw, 6),
            "kubernetes_gpus": kubernetes_gpus,
            "slurm_gpus": slurm_gpus,
            "ray_gpus": ray_gpus,
            "total_gpus": kubernetes_gpus + slurm_gpus + ray_gpus,
        }

    return {
        "dataset_id": dataset_id,
        "start": {"day_of_year": start_day, "hour_of_day": start_hour},
        "end": {"day_of_year": end_day, "hour_of_day": end_hour},
        "rows": [with_derived_metrics(row) for row in rows],
        "row_count": len(rows),
        "mw_conversion": {
            "pue_base": pue_base,
            "formula": "count × rated_kw × pue_base / 1000 = MW",
            "profile_mapping": {
                domain: {
                    "profile_id": profile.profile_id,
                    "rated_kw": profile.rated_kw,
                    "gpus_per_unit": profile.gpus_per_unit,
                    "mapping_basis": (
                        "best match by GPU count and profile description; "
                        "not an exact source-label/profile-ID match"
                    ),
                }
                for domain, profile in profiles.items()
            },
            "assumptions": [
                "Kubernetes and Slurm source counts labelled H100 chassis use enterprise_8gpu_air.",
                "Ray source counts labelled GB200 NVL72 rack use nextgen_rack_liquid.",
                "MW figures use the generic PARAM-06 PUE_base default, not a site-calibrated SJ-2 PUE.",
            ],
        },
    }