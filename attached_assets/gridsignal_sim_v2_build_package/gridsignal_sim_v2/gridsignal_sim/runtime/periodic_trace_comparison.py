"""Read-only deterministic comparisons over an imported periodic trace."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


DEFAULT_BASELINE_RESERVE_PERCENT = 15.0
DEFAULT_PAS_PERCENTILE = 90.0
DEFAULT_PAS_CONFIDENCE_SCALE = 1.0
PLACEHOLDER_CONFIDENCE_PERCENT = 15.0
ROLLING_MAPE_WINDOW_SAMPLES = 5


def _finite_number(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be a finite number")
    return number


def _percentile(values: list[float], percentile: float) -> float:
    """Linear-interpolated percentile with deterministic edge handling."""
    if not values:
        raise ValueError("comparison requires at least one valid imported sample")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile / 100.0
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _confidence_percent(row: dict[str, Any]) -> tuple[float | None, str]:
    """Read an existing per-segment confidence value when one is carried.

    Phase-1 imports do not currently carry any of these optional fields.  The
    fallbacks make the comparison forward-compatible with a real forecast
    confidence band without creating a new confidence model here.
    """
    if row.get("confidence_band_percent") is not None:
        value = _finite_number(row["confidence_band_percent"], "confidence_band_percent")
        if value < 0:
            raise ValueError("confidence_band_percent must be >= 0")
        return value, "existing per-segment confidence"
    if row.get("confidence_plus_minus_fraction") is not None:
        value = _finite_number(
            row["confidence_plus_minus_fraction"],
            "confidence_plus_minus_fraction",
        )
        if value < 0:
            raise ValueError("confidence_plus_minus_fraction must be >= 0")
        return value * 100.0, "existing per-segment confidence"
    return None, "flat placeholder (not validated)"


def _rolling_mape(rows: list[dict[str, Any]]) -> tuple[float, list[dict[str, Any]]]:
    point_errors: list[float | None] = []
    for row in rows:
        predicted = _finite_number(row["predicted_mw"], "predicted_mw")
        actual = _finite_number(row["mw_measured"], "mw_measured")
        if actual == 0:
            point_errors.append(None)
        else:
            point_errors.append(abs(predicted - actual) / abs(actual) * 100.0)

    rolling: list[dict[str, Any]] = []
    defined_values: list[float] = []
    for index, row in enumerate(rows):
        values = [
            error for error in point_errors[max(0, index - ROLLING_MAPE_WINDOW_SAMPLES + 1):index + 1]
            if error is not None
        ]
        value = sum(values) / len(values) if values else None
        if value is not None:
            defined_values.append(value)
        rolling.append({
            "timestamp": row["timestamp"],
            "rolling_mape_percent": round(value, 6) if value is not None else None,
        })
    overall = sum(defined_values) / len(defined_values) if defined_values else 0.0
    return round(overall, 6), rolling


def compare_import_report(
    import_report: dict[str, Any],
    *,
    baseline_reserve_percent: float = DEFAULT_BASELINE_RESERVE_PERCENT,
    pas_percentile: float = DEFAULT_PAS_PERCENTILE,
    pas_confidence_scale: float = DEFAULT_PAS_CONFIDENCE_SCALE,
) -> dict[str, Any]:
    """Build a comparison report without mutating the import or simulator."""
    baseline_reserve_percent = _finite_number(
        baseline_reserve_percent,
        "baseline_reserve_percent",
    )
    pas_percentile = _finite_number(pas_percentile, "pas_percentile")
    pas_confidence_scale = _finite_number(
        pas_confidence_scale,
        "pas_confidence_scale",
    )
    if baseline_reserve_percent < 0:
        raise ValueError("baseline_reserve_percent must be >= 0")
    if not 0 <= pas_percentile <= 100:
        raise ValueError("pas_percentile must be between 0 and 100")
    if pas_confidence_scale < 0:
        raise ValueError("pas_confidence_scale must be >= 0")

    rows = list(import_report.get("accepted") or [])
    if not rows:
        raise ValueError("comparison requires at least one accepted imported sample")
    predicted_values = [
        _finite_number(row.get("predicted_mw"), "predicted_mw") for row in rows
    ]
    if any(value < 0 for value in predicted_values):
        raise ValueError("predicted_mw must be >= 0")

    baseline_firm_capacity = max(predicted_values)
    pas_firm_capacity = _percentile(predicted_values, pas_percentile)
    confidence_placeholder_used = False
    pas_reserve_series: list[dict[str, Any]] = []
    confidence_sources: set[str] = set()
    for row in rows:
        confidence, source = _confidence_percent(row)
        if confidence is None:
            confidence = PLACEHOLDER_CONFIDENCE_PERCENT
            confidence_placeholder_used = True
        confidence_sources.add(source)
        pas_reserve_series.append({
            "timestamp": row["timestamp"],
            "confidence_band_percent": round(confidence, 6),
            "scaling_factor": pas_confidence_scale,
            "reserve_percent": round(confidence * pas_confidence_scale, 6),
            "source": source,
        })

    pas_average_reserve = (
        sum(item["reserve_percent"] for item in pas_reserve_series)
        / len(pas_reserve_series)
    )
    rolling_mape, rolling_mape_series = _rolling_mape(rows)
    settings = {
        "baseline_reserve_percent": baseline_reserve_percent,
        "pas_percentile": pas_percentile,
        "pas_confidence_scale": pas_confidence_scale,
        "rolling_mape_window_samples": ROLLING_MAPE_WINDOW_SAMPLES,
    }
    identity = json.dumps(
        {"import_id": import_report["import_id"], "settings": settings},
        sort_keys=True,
        separators=(",", ":"),
    )
    comparison_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]

    capacity_difference_mw = baseline_firm_capacity - pas_firm_capacity
    capacity_difference_percent = (
        capacity_difference_mw / baseline_firm_capacity * 100.0
        if baseline_firm_capacity
        else 0.0
    )
    return {
        "comparison_id": comparison_id,
        "import_id": import_report["import_id"],
        "site_id": import_report.get("site_id"),
        "window": import_report.get("window", {"start": None, "end": None}),
        "valid_samples": len(rows),
        "settings": settings,
        "baseline": {
            "label": "Without PAS",
            "firm_capacity_mw": round(baseline_firm_capacity, 6),
            "average_reserve_percent": round(baseline_reserve_percent, 6),
            "exceeded_firm_capacity_timestamps": sum(
                value > baseline_firm_capacity for value in predicted_values
            ),
        },
        "pas": {
            "label": "With PAS",
            "firm_capacity_mw": round(pas_firm_capacity, 6),
            "average_reserve_percent": round(pas_average_reserve, 6),
            "exceeded_firm_capacity_timestamps": sum(
                value > pas_firm_capacity for value in predicted_values
            ),
            "reserve_series": pas_reserve_series,
            "confidence_source": (
                "flat placeholder (not validated)"
                if confidence_placeholder_used
                else "existing per-segment confidence"
            ),
            "confidence_placeholder_used": confidence_placeholder_used,
            "confidence_note": (
                "No per-segment confidence value was available on this historical "
                "import; PAS reserve uses a flat 15.0% placeholder multiplied by "
                "the configured scaling factor. This is not validated."
                if confidence_placeholder_used
                else "PAS reserve uses the existing per-segment confidence value."
            ),
        },
        "firm_capacity_difference_mw": round(capacity_difference_mw, 6),
        "firm_capacity_difference_percent": round(capacity_difference_percent, 6),
        "reserve_difference_percentage_points": round(
            pas_average_reserve - baseline_reserve_percent,
            6,
        ),
        "rolling_mape_percent": rolling_mape,
        "rolling_mape_window_samples": ROLLING_MAPE_WINDOW_SAMPLES,
        "rolling_mape_series": rolling_mape_series,
        "data_quality": {
            "total_rows": import_report.get("total_rows", 0),
            "accepted_rows": import_report.get("accepted_rows", 0),
            "quarantined_rows": import_report.get("quarantined_rows", 0),
            "quarantined_by_reason": import_report.get("quarantined_by_reason", {}),
            "conflict_count": import_report.get("conflict_count", 0),
        },
    }