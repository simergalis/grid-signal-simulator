"""Deterministic Unified Periodic Trace Import.

This module deliberately has no simulator or model dependencies.  Imported
periodic observations are steady-state records, not workload events.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Mapping


REQUIRED_COLUMNS = (
    "site_id",
    "date",
    "time",
    "mw_measured",
    "measurement_source",
    "kubernetes_node_count",
    "kubernetes_request_rate",
    "slurm_node_count",
    "slurm_request_rate",
    "ray_node_count",
    "ray_request_rate",
)

REQUIRED_VALUE_COLUMNS = (
    "site_id",
    "date",
    "time",
    "mw_measured",
    "measurement_source",
    "kubernetes_node_count",
    "slurm_node_count",
    "ray_node_count",
)


@dataclass(frozen=True)
class TraceDomainConfig:
    configured: bool = False
    max_units: int | None = None
    unit: str = "node"
    inference: bool = False


def _number(raw: str, field: str) -> float:
    if raw.strip() == "":
        raise ValueError(f"{field} is required")
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError(f"{field} must be a finite number")
    return value


def _integer(raw: str, field: str) -> int:
    if raw.strip() == "":
        raise ValueError(f"{field} is required")
    # Do not accept 1.0 as an integer: the CSV contract says integer.
    value = int(raw.strip())
    if str(value) != raw.strip() and not (
        raw.strip().startswith("+") and str(value) == raw.strip()[1:]
    ):
        raise ValueError(f"{field} must be an integer")
    return value


def _timestamp(date_raw: str, time_raw: str) -> tuple[str, datetime]:
    try:
        value = datetime.strptime(
            f"{date_raw.strip()} {time_raw.strip()}",
            "%Y-%m-%d %H:%M:%S",
        )
    except ValueError as exc:
        raise ValueError("date/time must be a real YYYY-MM-DD HH:MM:SS timestamp") from exc
    return value.isoformat(timespec="seconds"), value


def _reason(row_number: int, message: str) -> dict[str, Any]:
    return {"row": row_number, "reason": message}


def import_periodic_trace(
    csv_text: str,
    *,
    pue: float = 1.37,
    domains: dict[str, TraceDomainConfig] | None = None,
    site_domain_configs: Mapping[str, Mapping[str, TraceDomainConfig]] | None = None,
    inference_domains: set[str] | frozenset[str] | None = None,
) -> dict[str, Any]:
    """Parse and calculate one trace without mutating simulator state.

    The first valid occurrence of a timestamp is authoritative; later valid
    occurrences are conflicts. Invalid rows are quarantined before duplicate
    handling, so a later valid row can still be accepted.
    """
    domains = domains or {}
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None:
        raise ValueError("CSV must include a header row")
    missing = [column for column in REQUIRED_COLUMNS if column not in reader.fieldnames]
    if missing:
        raise ValueError(f"CSV is missing required columns: {', '.join(missing)}")

    rows = list(reader)
    site_ids = {
        value for row in rows
        if (value := (row.get("site_id") or "").strip())
    }
    sources = {
        value for row in rows
        if (value := (row.get("measurement_source") or "").strip())
    }
    if len(site_ids) > 1:
        raise ValueError("CSV may contain only one site_id value")
    if len(sources) > 1:
        raise ValueError("CSV may contain only one measurement_source value")

    site_id = next(iter(site_ids), None)
    warnings: list[str] = []
    if site_domain_configs is not None:
        configured_domains = site_domain_configs.get(site_id or "")
        if configured_domains is None:
            domains = {}
            warnings.append(
                "Domain-cap validation could not be performed for "
                f"site_id {site_id!r}: no site-level capacity configuration is available."
            )
            site_capacity_validation = {
                "status": "not_configured",
                "site_id": site_id,
                "configured_domains": [],
            }
        else:
            domains = dict(configured_domains)
            site_capacity_validation = {
                "status": "validated",
                "site_id": site_id,
                "configured_domains": sorted(configured_domains),
            }
    else:
        site_capacity_validation = {
            "status": "not_requested",
            "site_id": site_id,
            "configured_domains": sorted(domains),
        }

    if inference_domains is not None:
        domains = {
            name: replace(
                domains.get(name, TraceDomainConfig()),
                inference=name in inference_domains,
            )
            for name in ("kubernetes", "slurm", "ray")
        }

    accepted: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    seen_valid_timestamps: dict[tuple[str, str, str], int] = {}
    reason_counts: dict[str, int] = {}

    for row_number, raw in enumerate(rows, start=2):
        site_id = (raw.get("site_id") or "").strip()
        date_raw = (raw.get("date") or "").strip()
        time_raw = (raw.get("time") or "").strip()
        timestamp_key = (site_id, date_raw, time_raw)

        failures: list[str] = []
        if not site_id:
            failures.append("site_id is required")
        if not date_raw:
            failures.append("date is required")
        if not time_raw:
            failures.append("time is required")
        try:
            timestamp, _ = _timestamp(date_raw, time_raw)
        except ValueError as exc:
            timestamp = None
            if date_raw and time_raw:
                failures.append(str(exc))

        source = (raw.get("measurement_source") or "").strip()
        if not source:
            failures.append("measurement_source is required")

        try:
            measured = _number(raw.get("mw_measured", ""), "mw_measured")
            if measured < 0:
                failures.append("mw_measured must be >= 0")
        except (ValueError, TypeError) as exc:
            measured = None
            failures.append(str(exc))

        counts: dict[str, int | None] = {}
        rates: dict[str, float | None] = {}
        for domain_name in ("kubernetes", "slurm", "ray"):
            count_field = f"{domain_name}_node_count"
            rate_field = f"{domain_name}_request_rate"
            try:
                count = _integer(raw.get(count_field, ""), count_field)
                counts[domain_name] = count
                if count < 0:
                    failures.append(f"{count_field} must be >= 0")
                config = domains.get(domain_name, TraceDomainConfig())
                if config.max_units is not None and count > config.max_units:
                    failures.append(
                        f"{count_field} exceeds configured maximum "
                        f"{config.max_units} {config.unit}s"
                    )
            except (ValueError, TypeError) as exc:
                counts[domain_name] = None
                failures.append(str(exc))

            rate_raw = raw.get(rate_field, "")
            config = domains.get(domain_name, TraceDomainConfig())
            if config.inference and rate_raw.strip() == "":
                failures.append(f"{rate_field} is required for configured inference workload")
                rates[domain_name] = None
            elif rate_raw.strip() == "":
                rates[domain_name] = None
            else:
                try:
                    rates[domain_name] = _number(rate_raw, rate_field)
                except (ValueError, TypeError) as exc:
                    rates[domain_name] = None
                    failures.append(str(exc))

        if failures:
            for failure in failures:
                reason_counts[failure] = reason_counts.get(failure, 0) + 1
            quarantined.append(_reason(row_number, "; ".join(failures)))
            continue

        if timestamp_key in seen_valid_timestamps:
            conflicts.append({
                "row": row_number,
                "conflict_with_row": seen_valid_timestamps[timestamp_key],
                "timestamp": f"{date_raw} {time_raw}",
                "reason": "duplicate timestamp; first valid row is authoritative",
            })
            continue
        seen_valid_timestamps[timestamp_key] = row_number

        # Counts are known here because failures above quarantine malformed rows.
        predicted_mw = (
            (
                (counts["kubernetes"] or 0) + (counts["slurm"] or 0)
            ) * 10.2
            + (counts["ray"] or 0) * 126.0
        ) / 1000.0 * pue
        accepted.append({
            "row": row_number,
            "site_id": site_id,
            "timestamp": timestamp,
            "date": date_raw,
            "time": time_raw,
            "mw_measured": measured,
            "measurement_source": source,
            "kubernetes_node_count": counts["kubernetes"],
            "kubernetes_request_rate": rates["kubernetes"],
            "slurm_node_count": counts["slurm"],
            "slurm_request_rate": rates["slurm"],
            "ray_node_count": counts["ray"],
            "ray_request_rate": rates["ray"],
            "predicted_mw": round(predicted_mw, 6),
        })

    timestamps = [
        datetime.fromisoformat(row["timestamp"]) for row in accepted
    ]
    window = {
        "start": min(timestamps).isoformat(timespec="seconds") if timestamps else None,
        "end": max(timestamps).isoformat(timespec="seconds") if timestamps else None,
    }
    import_id = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()[:16]
    return {
        "import_id": import_id,
        "site_id": site_id,
        "measurement_source": next(iter(sources), None),
        "pue": pue,
        "warnings": warnings,
        "site_capacity_validation": site_capacity_validation,
        "total_rows": len(rows),
        "accepted_rows": len(accepted),
        "quarantined_rows": len(quarantined),
        "quarantined_by_reason": reason_counts,
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
        "quarantined": quarantined,
        "window": window,
        "accepted": accepted,
    }