"""Pure S1 metric collection and guard implementation.

All cumulative-counter arithmetic for study artifacts lives here.  The
executor only forwards engine ticks and controller metadata to this module.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .errors import (
    AttributableHeatRateError,
    FuelComponentReconciliationError,
    FuelModelAbsentError,
    StartFuelReconciliationError,
)


FUEL_COMPONENTS = (
    "load_fuel_mmbtu",
    "no_load_fuel_mmbtu",
    "hot_standby_fuel_mmbtu",
    "start_fuel_mmbtu",
)
FUEL_TOLERANCE_MMBTU = 1e-6
# PROPOSED_HERE: harness policy reflecting the engine's observed release charge.
HOT_STANDBY_RELEASE_CHARGED = True
# PROPOSED_HERE: broad guard bounds the current aeroderivative heat-rate curve.
PLAUSIBLE_HEAT_RATE_MIN_BTU_PER_KWH = 1_000.0
PLAUSIBLE_HEAT_RATE_MAX_BTU_PER_KWH = 20_000.0
DAY_SECONDS = 86_400.0
TICK_SECONDS_DEFAULT = 5.0
ON_BUS_STATES = {"synchronised", "synchronized", "unloading"}


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return float(default)


def _telemetry(tick: Any) -> list[dict[str, Any]]:
    rows = _get(tick, "turbine_fuel_telemetry", ()) or ()
    return [dict(row) for row in rows]


def _units(tick: Any) -> list[dict[str, Any]]:
    rows = _get(tick, "turbine_units", ()) or ()
    return [dict(row) for row in rows]


def _day_number(sim_time_seconds: float) -> int:
    # Tick timestamps are interval-end timestamps.  86400 seconds is still
    # the last interval of day 1, not the first interval of day 2.
    return max(1, int((max(0.0, sim_time_seconds - 1e-9)) // DAY_SECONDS) + 1)


def _component_snapshot(rows: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    return {
        component: sum(_number(row.get(component)) for row in rows)
        for component in FUEL_COMPONENTS
    }


def _count_compacted_events(
    records: Iterable[Mapping[str, Any]],
    *,
    actions: set[str],
) -> int:
    count = 0
    for record in records:
        if record.get("truncated"):
            count += int(record.get("omitted_record_count", 0) or 0)
        elif str(record.get("action", "")) in actions:
            count += 1
    return count


def _signature(record: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        record.get("unit_id"),
        record.get("action"),
        record.get("source"),
        record.get("sim_time_s"),
        record.get("reason"),
        record.get("refusal_reason"),
        record.get("accepted"),
        record.get("changed_state"),
        record.get("from_state"),
        record.get("to_state"),
        record.get("thermal_tier"),
    )


def _deduplicate_records(
    records: Iterable[Mapping[str, Any]],
) -> tuple[int, int, bool, int]:
    """Return distinct events and suppressed repeats.

    Existing controller records may already carry a suppressed-repeat count.
    Raw executor records are deduplicated by event signature here as well.
    """
    distinct = 0
    suppressed = 0
    complete = True
    omitted = 0
    previous: tuple[Any, ...] | None = None
    for record in records:
        if record.get("truncated"):
            complete = False
            omitted += int(record.get("omitted_record_count", 0) or 0)
            continue
        explicit = int(record.get("suppressed_repeat_count", 0) or 0)
        signature = _signature(record)
        if signature == previous:
            suppressed += 1 + explicit
        else:
            distinct += 1
            suppressed += explicit
            previous = signature
    return distinct, suppressed, complete, omitted


def _reported_start_events(run_record: Mapping[str, Any]) -> int:
    starts = run_record.get("starts", ()) or ()
    actions = {"start"}
    if HOT_STANDBY_RELEASE_CHARGED:
        actions.add("release")
    return _count_compacted_events(starts, actions=actions)


def _reported_start_tier_sum(run_record: Mapping[str, Any]) -> float | None:
    starts = [
        record
        for record in (run_record.get("starts", ()) or ())
        if not record.get("truncated")
    ]
    if not starts or not all("tier_fuel_mmbtu" in record for record in starts):
        return None
    return sum(_number(record.get("tier_fuel_mmbtu")) for record in starts)


def _heat_rate(
    *,
    unit_id: str,
    load_fuel_this_tick: float,
    output_mw: float,
    tick_seconds: float,
) -> float:
    if output_mw <= 1e-9 or load_fuel_this_tick <= 1e-12:
        return 0.0
    energy_mwh = output_mw * tick_seconds / 3600.0
    # Operating-point heat rate is the load-fuel curve.  No-load, standby,
    # and start fuel are separate accounting components and must not be
    # folded into the rate used to price curtailed energy.
    return load_fuel_this_tick / energy_mwh * 1000.0


@dataclass
class MetricsCollector:
    """Streaming state holder; all study arithmetic remains in this module."""

    tick_seconds: float = TICK_SECONDS_DEFAULT

    def __post_init__(self) -> None:
        self.tick_count = 0
        self.last_tick: Any = None
        self.last_telemetry: dict[str, dict[str, Any]] = {}
        self.previous_cumulative: dict[str, dict[str, float]] = {}
        self.previous_start_count: dict[str, int] = {}
        self.previous_start_fuel: dict[str, float] = {}
        self.measured_start_events: list[dict[str, Any]] = []
        self.forecast_errors: list[float] = []
        self.unserved_mwh = 0.0
        self.peak_unserved_mw = 0.0
        self.served_mwh = 0.0
        self.curtailed_mwh = 0.0
        self.max_ledger_defect_mw = 0.0
        self.energy_balance_closed = True
        self.bess_min = float("inf")
        self.bess_max = 0.0
        self.daily: dict[int, dict[str, Any]] = {}
        self.unserved_intervals: list[dict[str, float]] = []
        self.open_unserved: dict[str, float] | None = None
        self.exposure_by_component: Counter[str] = Counter()
        self.exposure_by_unit: Counter[str] = Counter()
        self.attributable_by_unit: Counter[str] = Counter()
        self.sync_counts: Counter[int] = Counter()
        self.compute_trace = hashlib.sha256()
        self.compute_trace_count = 0
        self._last_forecast_identity: Any = None

    def add(self, tick: Any) -> None:
        self.tick_count += 1
        self.last_tick = tick
        sim_time = _number(_get(tick, "sim_time_seconds"))
        compute = _number(
            _get(tick, "p_compute_demand_mw", _get(tick, "p_compute_mw"))
        )
        self.compute_trace.update(
            f"{self.tick_count}:{compute:.17g}\n".encode("utf-8")
        )
        self.compute_trace_count += 1
        rows = _telemetry(tick)
        current = {str(row.get("asset_id")): row for row in rows}
        increments_by_unit: dict[str, dict[str, float]] = {}
        self.last_telemetry.update(current)

        for row in rows:
            unit_id = str(row.get("asset_id"))
            current_components = {
                component: _number(row.get(component))
                for component in FUEL_COMPONENTS
            }
            previous = self.previous_cumulative.get(unit_id, {})
            increments = {
                component: max(
                    0.0,
                    current_components[component] - previous.get(component, 0.0),
                )
                for component in FUEL_COMPONENTS
            }
            increments_by_unit[unit_id] = increments
            self.previous_cumulative[unit_id] = current_components
            current_start_count = int(_number(row.get("start_count")))
            current_start_fuel = _number(row.get("start_fuel_mmbtu"))
            prior_count = self.previous_start_count.get(unit_id, 0)
            prior_fuel = self.previous_start_fuel.get(unit_id, 0.0)
            count_delta = current_start_count - prior_count
            fuel_delta = max(0.0, current_start_fuel - prior_fuel)
            if count_delta > 0 or fuel_delta > 1e-12:
                per_event_fuel = fuel_delta / max(1, count_delta)
                for _ in range(max(1, count_delta)):
                    self.measured_start_events.append(
                        {
                            "sim_time_s": sim_time,
                            "unit_id": unit_id,
                            "tier_fuel_mmbtu": per_event_fuel,
                            "charged": per_event_fuel > 1e-12,
                        }
                    )
            self.previous_start_count[unit_id] = current_start_count
            self.previous_start_fuel[unit_id] = current_start_fuel

            if _number(_get(tick, "p_dispatch_curtailed_mw")) > 1e-9:
                for component, value in increments.items():
                    self.exposure_by_component[component] += value
                self.exposure_by_unit[unit_id] += sum(increments.values())

        synchronized_ids: set[str] = set()
        for unit in _units(tick):
            unit_id = str(unit.get("asset_id"))
            state = str(unit.get("state", "")).lower()
            if (
                bool(unit.get("breaker_closed"))
                and state in ON_BUS_STATES
            ):
                synchronized_ids.add(unit_id)
                row = current.get(unit_id)
                if row is None or not bool(row.get("fuel_modelled")):
                    raise FuelModelAbsentError(sorted(synchronized_ids))
        self.sync_counts[len(synchronized_ids)] += 1

        unserved = max(0.0, _number(_get(tick, "p_unserved_mw")))
        served = max(0.0, _number(_get(tick, "p_served_mw")))
        curtailed = max(0.0, _number(_get(tick, "p_dispatch_curtailed_mw")))
        self.unserved_mwh += unserved * self.tick_seconds / 3600.0
        self.served_mwh += served * self.tick_seconds / 3600.0
        self.curtailed_mwh += curtailed * self.tick_seconds / 3600.0
        self.peak_unserved_mw = max(self.peak_unserved_mw, unserved)
        if self.open_unserved is not None and unserved <= 1e-9:
            self.unserved_intervals.append(self.open_unserved)
            self.open_unserved = None
        elif unserved > 1e-9:
            if self.open_unserved is None:
                self.open_unserved = {
                    "start_sim_time_s": sim_time - self.tick_seconds,
                    "end_sim_time_s": sim_time,
                    "peak_unserved_mw": unserved,
                }
            else:
                self.open_unserved["end_sim_time_s"] = sim_time
                self.open_unserved["peak_unserved_mw"] = max(
                    self.open_unserved["peak_unserved_mw"], unserved
                )

        generation = _number(_get(tick, "p_generation_mw"))
        ledger_defect = abs(generation - served - curtailed)
        self.max_ledger_defect_mw = max(self.max_ledger_defect_mw, ledger_defect)
        imbalance = abs(_number(_get(tick, "p_imbalance_mw")))
        self.energy_balance_closed = self.energy_balance_closed and (
            ledger_defect <= 1e-3 or imbalance <= 1e-3
        )

        soc = _number(_get(tick, "bess_soc_fraction"))
        self.bess_min = min(self.bess_min, soc)
        self.bess_max = max(self.bess_max, soc)
        day = self.daily.setdefault(
            _day_number(sim_time),
            {
                "fuel_cumulative": {
                    component: 0.0 for component in FUEL_COMPONENTS
                },
                "unserved_mwh": 0.0,
                "curtailed_mwh": 0.0,
                "bess_soc_end": soc,
            },
        )
        day["fuel_cumulative"] = _component_snapshot(current.values())
        day["unserved_mwh"] += unserved * self.tick_seconds / 3600.0
        day["curtailed_mwh"] += curtailed * self.tick_seconds / 3600.0
        day["bess_soc_end"] = soc

        forecast = _get(tick, "forecast_mw")
        if forecast is not None:
            miss = _number(_get(tick, "p_total_mw")) - _number(forecast)
            if miss > 0.0:
                self.forecast_errors.append(miss)

        if curtailed > 1e-9:
            on_bus = [
                unit
                for unit in _units(tick)
                if bool(unit.get("breaker_closed"))
                and str(unit.get("state", "")).lower() in ON_BUS_STATES
            ]
            basis = {
                str(unit.get("asset_id")): max(
                    0.0,
                    _number(unit.get("output_mw")),
                )
                for unit in on_bus
            }
            total_basis = sum(basis.values())
            if total_basis <= 1e-9:
                basis = {
                    str(unit.get("asset_id")): max(
                        0.0,
                        _number(unit.get("rated_mw")),
                    )
                    for unit in on_bus
                }
                total_basis = sum(basis.values())
            for unit in on_bus:
                unit_id = str(unit.get("asset_id"))
                output = max(0.0, _number(unit.get("output_mw")))
                if total_basis <= 1e-9 or output <= 1e-9:
                    continue
                row = current.get(unit_id)
                if row is None or not bool(row.get("fuel_modelled")):
                    raise FuelModelAbsentError([unit_id])
                heat_rate = _heat_rate(
                    unit_id=unit_id,
                    load_fuel_this_tick=increments_by_unit.get(
                        unit_id, {}
                    ).get("load_fuel_mmbtu", 0.0),
                    output_mw=output,
                    tick_seconds=self.tick_seconds,
                )
                if not (
                    PLAUSIBLE_HEAT_RATE_MIN_BTU_PER_KWH
                    <= heat_rate
                    <= PLAUSIBLE_HEAT_RATE_MAX_BTU_PER_KWH
                ):
                    raise AttributableHeatRateError(
                        unit_id=unit_id,
                        heat_rate_btu_per_kwh=heat_rate,
                        minimum_btu_per_kwh=PLAUSIBLE_HEAT_RATE_MIN_BTU_PER_KWH,
                        maximum_btu_per_kwh=PLAUSIBLE_HEAT_RATE_MAX_BTU_PER_KWH,
                    )
                allocated_mwh = (
                    curtailed
                    * self.tick_seconds
                    / 3600.0
                    * basis.get(unit_id, 0.0)
                    / total_basis
                )
                self.attributable_by_unit[unit_id] += (
                    allocated_mwh * heat_rate / 1000.0
                )

    def finalize(
        self,
        *,
        run_record: Mapping[str, Any] | None = None,
        commitment_log: Iterable[Mapping[str, Any]] | None = None,
        minimum_down_seconds_by_unit: Mapping[str, float] | None = None,
    ) -> dict[str, Any]:
        record = dict(run_record or {})
        if self.open_unserved is not None:
            self.unserved_intervals.append(self.open_unserved)
            self.open_unserved = None
        final_rows = list(self.last_telemetry.values())
        components = _component_snapshot(final_rows)
        computed_total = sum(components.values())
        reported_components = record.get("fuel_by_component_mmbtu")
        if isinstance(reported_components, Mapping):
            reported_component_sum = sum(
                _number(reported_components.get(component))
                for component in FUEL_COMPONENTS
            )
        else:
            reported_component_sum = computed_total
        reported_total = _number(
            record.get("turbine_fuel_mmbtu"), computed_total
        )
        if (
            abs(reported_component_sum - reported_total)
            > FUEL_TOLERANCE_MMBTU
            or abs(computed_total - reported_total) > FUEL_TOLERANCE_MMBTU
        ):
            raise FuelComponentReconciliationError(
                reported_total_mmbtu=reported_total,
                component_sum_mmbtu=reported_component_sum,
                computed_total_mmbtu=computed_total,
            )

        measured_start_fuel = components["start_fuel_mmbtu"]
        recorded_event_count = _reported_start_events(record)
        measured_event_count = len(self.measured_start_events)
        tier_sum = _reported_start_tier_sum(record)
        reported_start_fuel = _number(
            (reported_components or {}).get(
                "start_fuel_mmbtu", measured_start_fuel
            )
        )
        start_fuel_matches = (
            abs(measured_start_fuel - reported_start_fuel)
            <= FUEL_TOLERANCE_MMBTU
        )
        if tier_sum is not None:
            start_fuel_matches = (
                abs(tier_sum - measured_start_fuel) <= FUEL_TOLERANCE_MMBTU
            )
        if (
            abs(
                reported_start_fuel
                - measured_start_fuel
            )
            > FUEL_TOLERANCE_MMBTU
            or recorded_event_count != measured_event_count
            or not start_fuel_matches
        ):
            raise StartFuelReconciliationError(
                reported_start_fuel_mmbtu=reported_start_fuel,
                measured_start_fuel_mmbtu=measured_start_fuel,
                recorded_event_count=recorded_event_count,
                measured_event_count=measured_event_count,
                release_charged=HOT_STANDBY_RELEASE_CHARGED,
            )

        log = list(commitment_log or record.get("commitment_log", ()) or ())
        (
            distinct_count,
            suppressed_count,
            commitment_log_complete,
            commitment_log_omitted,
        ) = _deduplicate_records(log)
        refusal_records = record.get("stop_floor_refusals", ()) or ()
        (
            refusal_distinct,
            refusal_suppressed,
            refusal_log_complete,
            refusal_log_omitted,
        ) = _deduplicate_records(refusal_records)
        if record.get("stop_floor_refusal_count") is not None:
            refusal_total = int(record["stop_floor_refusal_count"])
        else:
            refusal_total = len(refusal_records)
        restart_count = _same_unit_restart_count(
            record,
            minimum_down_seconds_by_unit or {},
        )
        daily_rows = _daily_rows(self.daily)
        return {
            "tick_count": self.tick_count,
            "interval_seconds": self.tick_seconds,
            "fuel_by_component_mmbtu": {
                key: round(value, 9) for key, value in components.items()
            },
            "turbine_fuel_mmbtu": round(computed_total, 9),
            "fuel_reconciled": True,
            "start_fuel_reconciliation": {
                "release_charged": HOT_STANDBY_RELEASE_CHARGED,
                "recorded_event_count": recorded_event_count,
                "measured_event_count": measured_event_count,
                "measured_start_fuel_mmbtu": round(measured_start_fuel, 9),
                "tier_sum_mmbtu": (
                    round(tier_sum, 9) if tier_sum is not None else None
                ),
                "passed": True,
            },
            "dispatch_curtailment_mwh": round(self.curtailed_mwh, 9),
            "dispatch_curtailment_interval_exposure_fuel_mmbtu": round(
                sum(self.exposure_by_component.values()), 9
            ),
            "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
                key: round(value, 9)
                for key, value in self.exposure_by_component.items()
            },
            "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
                key: round(value, 9)
                for key, value in self.exposure_by_unit.items()
            },
            "dispatch_curtailment_attributable_fuel_mmbtu": round(
                sum(self.attributable_by_unit.values()), 9
            ),
            "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
                key: round(value, 9)
                for key, value in self.attributable_by_unit.items()
            },
            "unserved_mwh": round(self.unserved_mwh, 9),
            "peak_unserved_mw": round(self.peak_unserved_mw, 9),
            "served_mwh": round(self.served_mwh, 9),
            "unserved_intervals": self.unserved_intervals,
            "energy_balance": {
                "closure_status": self.energy_balance_closed,
                "max_abs_physical_ledger_defect_mw": round(
                    self.max_ledger_defect_mw, 9
                ),
                "served_demand_mwh": round(self.served_mwh, 9),
                "unserved_demand_mwh": round(self.unserved_mwh, 9),
            },
            "bess_soc_min": round(
                0.0 if self.bess_min == float("inf") else self.bess_min,
                9,
            ),
            "bess_soc_max": round(self.bess_max, 9),
            "bess_soc_final": round(
                _number(_get(self.last_tick, "bess_soc_fraction")), 9
            ),
            "commitment": {
                "distinct_event_count": (
                    distinct_count if commitment_log_complete else None
                ),
                "visible_distinct_event_count": distinct_count,
                "suppressed_repeat_count": suppressed_count,
                "log_complete": commitment_log_complete,
                "omitted_record_count": commitment_log_omitted,
                "reserve_floor_refusal_count": refusal_total,
                "reserve_floor_distinct_event_count": (
                    refusal_distinct if refusal_log_complete else None
                ),
                "reserve_floor_visible_distinct_event_count": refusal_distinct,
                "reserve_floor_suppressed_repeat_count": refusal_suppressed,
                "reserve_floor_log_complete": refusal_log_complete,
                "reserve_floor_omitted_record_count": refusal_log_omitted,
                "same_unit_restart_within_min_down_window_count": restart_count,
            },
            "forecast": {
                "miss_count": (
                    int(record.get("forecast_misses", {}).get("count", 0))
                    if record.get("forecast_misses")
                    else len(self.forecast_errors)
                ),
                "miss_peak_mw": round(
                    max(
                        self.forecast_errors
                        or [
                            _number(
                                (record.get("forecast_misses") or {}).get(
                                    "peak_mw", 0.0
                                )
                            )
                        ]
                    ),
                    9,
                ),
            },
            "compute_trace_sha256": self.compute_trace.hexdigest(),
            "compute_trace_count": self.compute_trace_count,
            "daily_breakdown": daily_rows,
            "constraints_valid": bool(record.get("constraints_valid", True)),
            "hard_violations": list(record.get("hard_violations", []) or []),
        }


def _same_unit_restart_count(
    record: Mapping[str, Any],
    minimum_down_seconds_by_unit: Mapping[str, float],
) -> int:
    events = [
        item
        for item in (record.get("commitment_log", ()) or ())
        if not item.get("truncated")
    ]
    stops: dict[str, float] = {}
    count = 0
    for item in sorted(events, key=lambda value: _number(value.get("sim_time_s"))):
        unit_id = str(item.get("unit_id"))
        timestamp = _number(item.get("sim_time_s"))
        action = str(item.get("action", ""))
        if action in {"stop", "stop_complete"} and item.get("changed_state"):
            stops[unit_id] = timestamp
        elif action in {"start", "release"} and item.get("changed_state"):
            minimum_down = _number(minimum_down_seconds_by_unit.get(unit_id))
            if (
                unit_id in stops
                and minimum_down > 0.0
                and timestamp - stops[unit_id] < minimum_down
            ):
                count += 1
    return count


def _daily_rows(daily: Mapping[int, Mapping[str, Any]]) -> list[dict[str, Any]]:
    previous = {component: 0.0 for component in FUEL_COMPONENTS}
    rows: list[dict[str, Any]] = []
    for day in sorted(daily):
        value = daily[day]
        cumulative = value["fuel_cumulative"]
        deltas = {
            component: max(
                0.0,
                _number(cumulative.get(component))
                - previous[component],
            )
            for component in FUEL_COMPONENTS
        }
        previous = {
            component: _number(cumulative.get(component))
            for component in FUEL_COMPONENTS
        }
        rows.append(
            {
                "day": day,
                "kind": "weekday" if day <= 5 else "weekend",
                "fuel_by_component_mmbtu": {
                    key: round(value, 9) for key, value in deltas.items()
                },
                "fuel_mmbtu": round(sum(deltas.values()), 9),
                "unserved_mwh": round(_number(value.get("unserved_mwh")), 9),
                "curtailed_mwh": round(_number(value.get("curtailed_mwh")), 9),
                "bess_soc_end": round(
                    _number(value.get("bess_soc_end")), 9
                ),
            }
        )
    return rows


def collect_metrics(
    ticks: Iterable[Any],
    *,
    run_record: Mapping[str, Any] | None = None,
    commitment_log: Iterable[Mapping[str, Any]] | None = None,
    tick_seconds: float = TICK_SECONDS_DEFAULT,
    minimum_down_seconds_by_unit: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    collector = MetricsCollector(tick_seconds=float(tick_seconds))
    for tick in ticks:
        collector.add(tick)
    result = collector.finalize(
        run_record=run_record,
        commitment_log=commitment_log,
        minimum_down_seconds_by_unit=minimum_down_seconds_by_unit,
    )
    if run_record:
        for key in ("scenario_id", "mode", "engine_commit", "harness_commit"):
            if key in run_record:
                result[key] = run_record[key]
    return result