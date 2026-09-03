import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.app import create_app
from api.routes import reference_forecast as reference_forecast_routes
from api.routes.reference_forecast import (
    DATASET_ID,
    get_reference_forecast,
    get_reference_forecast_rows,
)


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return iter(self._values)


class _ReferenceForecastDb:
    def __init__(self):
        self.scenario = SimpleNamespace(
            dataset_id=DATASET_ID,
            display_name="SJ-2 52-week reference forecast",
            span_days=364,
            source_filename="equinix-sj-2-52wk-v1.csv",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.rows = [
            SimpleNamespace(
                day_of_year=1,
                hour_of_day=0,
                kubernetes_node_count=10,
                slurm_node_count=20,
                ray_rack_count=2,
            ),
            SimpleNamespace(
                day_of_year=1,
                hour_of_day=1,
                kubernetes_node_count=11,
                slurm_node_count=21,
                ray_rack_count=3,
            ),
        ]

    async def get(self, model, dataset_id):
        return self.scenario if dataset_id == DATASET_ID else None

    async def execute(self, statement):
        return _ScalarResult(self.rows)


def test_reference_forecast_router_is_registered_before_spa_fallback():
    app = create_app()
    reference_index = next(
        index
        for index, route in enumerate(app.routes)
        if getattr(route, "original_router", None) is reference_forecast_routes.router
    )
    fallback_index = next(
        index
        for index, route in enumerate(app.routes)
        if getattr(route, "path", None) == "/{full_path:path}"
    )

    assert any(
        route.path == "/api/reference-forecast/{dataset_id}"
        for route in reference_forecast_routes.router.routes
    )
    assert reference_index < fallback_index


def test_canonical_reference_forecast_returns_dataset_metadata_and_rows():
    db = _ReferenceForecastDb()

    response = asyncio.run(get_reference_forecast(DATASET_ID, db))

    assert response["dataset"]["dataset_id"] == DATASET_ID
    assert response["dataset"]["span_days"] == 364
    assert response["row_count"] == 2
    assert response["rows"][0]["hour_of_day"] == 0


def test_canonical_reference_forecast_rows_returns_hourly_history_with_derived_metrics(
    monkeypatch,
):
    db = _ReferenceForecastDb()

    async def fake_fetch_rows(*args, **kwargs):
        return [
            {
                "day_of_year": row.day_of_year,
                "hour_of_day": row.hour_of_day,
                "kubernetes_node_count": row.kubernetes_node_count,
                "slurm_node_count": row.slurm_node_count,
                "ray_rack_count": row.ray_rack_count,
            }
            for row in db.rows
        ]

    monkeypatch.setattr(reference_forecast_routes, "fetch_reference_forecast_rows", fake_fetch_rows)
    response = asyncio.run(
        get_reference_forecast_rows(
            DATASET_ID,
            start_day=1,
            start_hour=0,
            end_day=1,
            end_hour=1,
            db=db,
        )
    )

    assert response["dataset_id"] == DATASET_ID
    assert response["row_count"] == 2
    assert response["rows"][0]["total_gpus"] > 0
    assert response["rows"][0]["total_mw"] > 0
    assert response["mw_conversion"]["formula"].startswith("count × rated_kw")


def test_invalid_reference_forecast_dataset_returns_404():
    db = _ReferenceForecastDb()

    with pytest.raises(HTTPException) as error:
        asyncio.run(get_reference_forecast("unknown-dataset", db))

    assert error.value.status_code == 404
    assert error.value.detail == "Reference forecast dataset not found"