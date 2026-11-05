"""Read-only stranded-capacity metrics derived from compact study ticks."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable, Mapping


# PROPOSED_HERE, illustrative policies: none=0 MW, fixed_3mw=3 MW,
# pct10=10% of available capacity, and derate80=20% of available capacity.
RESERVE_POLICIES = ("none", "fixed_3mw", "pct10", "derate80")
FIXED_RESERVE_MW = 3.0  # PROPOSED_HERE: illustrative reserve policy.


def compute_stranded(
    tick_rows: Iterable[Mapping[str, Any]],
    *,
    p_avail_mw: float | None,
    reserve_policy: str = "fixed_3mw",
    tick_seconds: float,
) -> dict[str, Any]:
    """Summarize demand, reserve, recoverable and above-cap power by minute.

    Reserve policies are illustrative PROPOSED_HERE values; they do not alter
    simulator dispatch or physical results.
    """
    if p_avail_mw is None:
        return {
            "available": False,
            "reason": "no grid_import_limit_mw; no available-capacity basis defined",
        }
    if reserve_policy not in RESERVE_POLICIES:
        raise ValueError(
            f"unsupported reserve_policy {reserve_policy!r}; "
            f"expected one of {RESERVE_POLICIES}"
        )

    available = float(p_avail_mw)
    interval = float(tick_seconds)
    if not math.isfinite(available) or available < 0:
        raise ValueError("p_avail_mw must be finite and non-negative")
    if not math.isfinite(interval) or interval <= 0:
        raise ValueError("tick_seconds must be finite and positive")

    if reserve_policy == "none":
        reserve_mw = 0.0
    elif reserve_policy == "fixed_3mw":
        reserve_mw = FIXED_RESERVE_MW
    elif reserve_policy == "pct10":
        reserve_mw = 0.10 * available
    else:
        reserve_mw = 0.20 * available

    buckets: dict[
        int, list[tuple[float, float, float, float | None]]
    ] = defaultdict(list)
    demand_values: list[float] = []
    requested_values: list[float] = []
    energy_consumed_mwh = 0.0
    row_count = 0
    for row in tick_rows:
        try:
            timestamp = float(row["sim_time_seconds"])
            demand = float(row["p_total_mw"])
            bess_output = float(row["bess_output_mw"])
            unserved = float(row["p_unserved_mw"])
            requested_raw = row.get("requested_demand_mw")
            requested = (
                float(requested_raw) if requested_raw is not None else None
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                "each tick requires numeric sim_time_seconds, p_total_mw, "
                "bess_output_mw, and p_unserved_mw"
            ) from error
        numeric_values = [timestamp, demand, bess_output, unserved]
        if requested is not None:
            numeric_values.append(requested)
        if not all(math.isfinite(value) for value in numeric_values):
            raise ValueError("tick inputs must be finite numbers")
        minute = math.floor(timestamp / 60.0)
        buckets[minute].append(
            (demand, max(0.0, bess_output), unserved, requested)
        )
        demand_values.append(demand)
        if requested is not None:
            requested_values.append(requested)
        energy_consumed_mwh += demand * interval / 3600.0
        row_count += 1

    duration_hours = row_count * interval / 3600.0
    minute_rows: list[dict[str, Any]] = []
    stranded_values: list[float] = []
    scarce_candidates: list[int] = []
    above_cap_mwh = 0.0
    above_cap_bess_mwh = 0.0
    above_cap_unserved_mwh = 0.0

    for minute in sorted(buckets):
        values = buckets[minute]
        count = len(values)
        demand_mean = sum(value[0] for value in values) / count
        demand_max = max(value[0] for value in values)
        bess_positive_mean = sum(value[1] for value in values) / count
        # Keep the specified per-minute unserved resample available while the
        # above-cap split remains defined by excess less positive BESS output.
        unserved_mean = sum(value[2] for value in values) / count
        del unserved_mean
        minute_requested = [
            value[3] for value in values if value[3] is not None
        ]
        requested_max = (
            max(minute_requested) if minute_requested else None
        )

        consumed = min(demand_mean, available)
        stranded = available - consumed
        stranded_values.append(stranded)
        reserve_held = min(reserve_mw, stranded)
        recoverable = max(0.0, stranded - reserve_mw)
        above_cap = max(0.0, demand_mean - available)
        above_cap_bess = min(above_cap, bess_positive_mean)
        above_cap_unserved = max(0.0, above_cap - above_cap_bess)
        scarce = demand_mean > available - reserve_mw
        if scarce:
            scarce_candidates.append(minute)
        minute_rows.append(
            {
                "minute": minute,
                "t_start_s": minute * 60,
                "demand_mean_mw": demand_mean,
                "demand_max_mw": demand_max,
                "requested_demand_max_mw": requested_max,
                "consumed_mw": consumed,
                "reserve_held_mw": reserve_held,
                "recoverable_mw": recoverable,
                "above_cap_bess_mw": above_cap_bess,
                "above_cap_unserved_mw": above_cap_unserved,
                "scarce": scarce,
            }
        )
        above_cap_mwh += above_cap / 60.0
        above_cap_bess_mwh += above_cap_bess / 60.0
        above_cap_unserved_mwh += above_cap_unserved / 60.0

    # PROPOSED_HERE: suppress scarce bursts shorter than three minutes, then
    # merge kept episodes separated by fewer than five minutes.
    raw_runs: list[tuple[int, int]] = []
    if scarce_candidates:
        run_start = run_end = scarce_candidates[0]
        for minute in scarce_candidates[1:]:
            if minute == run_end + 1:
                run_end = minute
            else:
                raw_runs.append((run_start, run_end))
                run_start = run_end = minute
        raw_runs.append((run_start, run_end))

    kept_runs = [
        (start, end)
        for start, end in raw_runs
        if end - start + 1 >= 3
    ]
    merged_runs: list[tuple[int, int]] = []
    for start, end in kept_runs:
        if merged_runs and start - merged_runs[-1][1] - 1 < 5:
            prior_start, _ = merged_runs[-1]
            merged_runs[-1] = (prior_start, end)
        else:
            merged_runs.append((start, end))
    scarce_episodes = [
        {
            "start_minute": start,
            "end_minute": end,
            "length_minutes": end - start + 1,
        }
        for start, end in merged_runs
    ]
    kept_scarce_minutes = sum(
        end - start + 1 for start, end in kept_runs
    )

    minute_count = len(minute_rows)
    avg_stranded = (
        sum(stranded_values) / minute_count if minute_count else 0.0
    )
    avg_recoverable = (
        sum(row["recoverable_mw"] for row in minute_rows) / minute_count
        if minute_count
        else 0.0
    )
    recoverable_mwh = sum(
        row["recoverable_mw"] / 60.0 for row in minute_rows
    )
    utilization_pct = (
        energy_consumed_mwh / (available * duration_hours) * 100.0
        if available > 0 and duration_hours > 0
        else 0.0
    )
    recoverable_pct = (
        recoverable_mwh / (available * duration_hours) * 100.0
        if available > 0 and duration_hours > 0
        else 0.0
    )

    return {
        "p_avail_mw": available,
        "reserve_policy": reserve_policy,
        "p_res_mw": reserve_mw,
        "reserve_label": "illustrative",
        "energy_consumed_mwh": energy_consumed_mwh,
        "energy_available_mwh": available * duration_hours,
        "avg_demand_mw": (
            sum(demand_values) / row_count if row_count else 0.0
        ),
        "peak_demand_mw": max(demand_values) if demand_values else 0.0,
        "utilisation_of_cap_pct": utilization_pct,
        "minutes_above_cap": sum(
            row["demand_mean_mw"] > available for row in minute_rows
        ),
        "minutes_requested_above_cap": (
            sum(
                row["requested_demand_max_mw"] is not None
                and row["requested_demand_max_mw"] > available
                for row in minute_rows
            )
            if requested_values
            else None
        ),
        "peak_requested_demand_mw": (
            max(requested_values) if requested_values else None
        ),
        "above_cap_mwh": above_cap_mwh,
        "above_cap_bess_mwh": above_cap_bess_mwh,
        "above_cap_unserved_mwh": above_cap_unserved_mwh,
        "avg_stranded_mw": avg_stranded,
        "avg_recoverable_mw": avg_recoverable,
        "recoverable_mwh": recoverable_mwh,
        "recoverable_pct_of_cap": recoverable_pct,
        "scarce_minutes": kept_scarce_minutes,
        "scarce_episodes": scarce_episodes,
        "resample": "1-minute: mean for energy layers, max for demand line",
        "basis": "facility demand, not grid import",
        "series": minute_rows,
    }
