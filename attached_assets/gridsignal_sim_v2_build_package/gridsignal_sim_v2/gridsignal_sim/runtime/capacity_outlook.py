"""Deterministic historical day-of-week capacity projection."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timedelta
from typing import Any

from runtime.periodic_trace_comparison import _percentile, _finite_number

DEFAULT_PERCENTILE = 90.0
DEFAULT_HORIZON_DAYS = 7
HORIZONS = frozenset({7, 30})

# Firm capacity is the sum of firm fuel-cell output and the site's PCC import
# ceiling for the seeded site archetypes.  turbine-01 is intentionally absent:
# its existing scenario-specific capacity must not be changed by this feature.
SITE_FIRM_CAPACITY_MW = {
    "equinix-sj-1": 29.0,
    "equinix-sj-2": 29.0,
}


def build_capacity_outlook(
    import_report: dict[str, Any],
    *,
    percentile: float = DEFAULT_PERCENTILE,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    firm_capacity_mw: float | None = None,
    start_date: str | None = None,
) -> dict[str, Any]:
    percentile = _finite_number(percentile, "percentile")
    if not 0 <= percentile <= 100:
        raise ValueError("percentile must be between 0 and 100")
    try:
        horizon_days = int(horizon_days)
    except (TypeError, ValueError) as exc:
        raise ValueError("horizon_days must be 7 or 30") from exc
    if horizon_days not in HORIZONS:
        raise ValueError("horizon_days must be 7 or 30")

    rows = list(import_report.get("accepted") or [])
    if not rows:
        raise ValueError("capacity outlook requires at least one accepted imported sample")
    by_weekday: dict[int, list[float]] = {i: [] for i in range(7)}
    for row in rows:
        try:
            stamp = str(row["timestamp"])
            value = _finite_number(row["predicted_mw"], "predicted_mw")
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("accepted rows must contain valid timestamp and predicted_mw") from exc
        if value < 0:
            raise ValueError("predicted_mw must be >= 0")
        by_weekday[datetime.fromisoformat(stamp).weekday()].append(value)

    weekday_values = {
        str((weekday + 1) % 7): round(_percentile(values, percentile), 6)
        if values else None
        for weekday, values in by_weekday.items()
    }
    if any(value is None for value in weekday_values.values()):
        missing = [name for name, value in weekday_values.items() if value is None]
        raise ValueError(f"capacity outlook has no samples for weekday(s): {', '.join(missing)}")

    if start_date:
        try:
            first_day = date.fromisoformat(start_date)
        except ValueError as exc:
            raise ValueError("start_date must be YYYY-MM-DD") from exc
    else:
        window_end = (import_report.get("window") or {}).get("end")
        if not window_end:
            raise ValueError("import report has no window end date")
        first_day = datetime.fromisoformat(str(window_end)).date() + timedelta(days=1)

    site_id = import_report.get("site_id")
    firm = (
        _finite_number(firm_capacity_mw, "firm_capacity_mw")
        if firm_capacity_mw is not None
        else SITE_FIRM_CAPACITY_MW.get(site_id, max(float(v) for v in weekday_values.values()))
    )
    if firm < 0:
        raise ValueError("firm_capacity_mw must be >= 0")
    series = []
    shortfalls = []
    for offset in range(horizon_days):
        day = first_day + timedelta(days=offset)
        sunday_index = (day.weekday() + 1) % 7
        projected = float(weekday_values[str(sunday_index)])
        item = {"date": day.isoformat(), "weekday": sunday_index, "projected_mw": round(projected, 6)}
        series.append(item)
        if projected > firm:
            shortfalls.append(item)

    settings = {"percentile": percentile, "horizon_days": horizon_days}
    identity = json.dumps(
        {"import_id": import_report["import_id"], "settings": settings, "firm_capacity_mw": firm, "start_date": first_day.isoformat()},
        sort_keys=True, separators=(",", ":"),
    )
    return {
        "outlook_id": hashlib.sha256(identity.encode()).hexdigest()[:16],
        "site_id": site_id,
        "import_id": import_report["import_id"],
        "settings": settings,
        "percentile": percentile,
        "horizon_days": horizon_days,
        "start_date": first_day.isoformat(),
        "weekday_percentiles": weekday_values,
        "projected_series": series,
        "firm_capacity_mw": round(firm, 6),
        "shortfall_days": shortfalls,
    }