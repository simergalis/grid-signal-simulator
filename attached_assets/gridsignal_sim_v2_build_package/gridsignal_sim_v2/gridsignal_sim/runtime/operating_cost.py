"""Opt-in, itemised run operating costs.

This module is deliberately separate from the simulator's dispatch cost model
and the existing §21.2 ``cost_breakdown`` estimate.  It reads completed-run
quantities and scenario-supplied prices only; it never feeds back into physics.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


# PROPOSED_HERE: conversion used only when pricing fuel with unlike heat-value
# bases. Rationale: common natural-gas LHV/HHV relationship; source for the
# definitions and heating-value distinction: DOE Hydrogen Analysis Resource
# Center, Lower and Higher Heating Values, https://h2tools.org/hyarc/calculator-tools/lower-and-higher-heating-values-fuels.
NATURAL_GAS_LHV_TO_HHV_MMBTU = 1.108

_FUEL_COMPONENTS = (
    "load_fuel_mmbtu",
    "no_load_fuel_mmbtu",
    "hot_standby_fuel_mmbtu",
    "start_fuel_mmbtu",
)


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result


def _interval_energy(
    tick_rows: Sequence[Mapping[str, Any]],
    field: str,
    interval_seconds: float,
    *,
    absolute: bool = False,
) -> float | None:
    if not tick_rows:
        return None
    total = 0.0
    for row in tick_rows:
        value = _number(row.get(field))
        if value is None:
            return None
        total += (abs(value) if absolute else value) * interval_seconds / 3600.0
    return total


def _line(
    *,
    key: str,
    label: str,
    quantity: float | None,
    quantity_unit: str,
    unit_price: float | None,
    unit_price_unit: str,
    provenance: str | None,
    quantity_provenance: str,
    conversion_factor: float | None = None,
    conversion_note: str | None = None,
) -> dict[str, Any]:
    amount = (
        quantity * unit_price
        if quantity is not None and unit_price is not None
        else None
    )
    return {
        "key": key,
        "label": label,
        "quantity": round(quantity, 9) if quantity is not None else None,
        "quantity_unit": quantity_unit,
        "unit_price": round(unit_price, 9) if unit_price is not None else None,
        "unit_price_unit": unit_price_unit,
        "amount_usd": round(amount, 6) if amount is not None else None,
        "provenance": {
            "quantity": quantity_provenance,
            "price": provenance,
        },
        "conversion_factor": conversion_factor,
        "conversion_note": conversion_note,
    }


def compute_operating_cost(
    inputs: Mapping[str, Any] | None,
    tick_rows: Sequence[Mapping[str, Any]],
    *,
    interval_seconds: float,
    turbine_fuel_by_unit_mmbtu: Mapping[str, float] | None,
    fuel_basis_by_unit: Mapping[str, str | None] | None,
    fuel_quantity_complete: bool,
    diesel_fuel_gallons: float | None,
    turbine_rated_mw: float | None,
    turbine_start_count: int | None,
) -> dict[str, Any] | None:
    """Return an itemized cost payload, or ``None`` when the block is absent."""
    if inputs is None:
        return None

    turbine_mwh = _interval_energy(tick_rows, "turbine_output_mw", interval_seconds)
    # PROPOSED_HERE: BESS degradation quantity is absolute AC-side throughput
    # (charge plus discharge), not cell-side energy. It is an explicit quantity
    # convention and remains separate from the existing charge/loss estimate.
    bess_throughput_mwh = _interval_energy(
        tick_rows, "bess_output_mw", interval_seconds, absolute=True
    )
    served_mwh = _interval_energy(tick_rows, "p_served_mw", interval_seconds)
    unserved_mwh = _interval_energy(tick_rows, "p_unserved_mw", interval_seconds)

    compute_mwh = _interval_energy(tick_rows, "p_compute_mw", interval_seconds)
    non_gpu_mwh = _interval_energy(
        tick_rows, "p_non_gpu_demand_mw", interval_seconds
    )
    if non_gpu_mwh is None and tick_rows and all(
        "p_non_gpu_demand_mw" not in row for row in tick_rows
    ):
        non_gpu_mwh = 0.0
    it_load_mwh = (
        compute_mwh + non_gpu_mwh
        if compute_mwh is not None and non_gpu_mwh is not None
        else None
    )
    duration_hours = len(tick_rows) * interval_seconds / 3600.0

    fuel_by_unit = {
        str(unit): float(value)
        for unit, value in (turbine_fuel_by_unit_mmbtu or {}).items()
    }
    fuel_basis = fuel_basis_by_unit or {}
    price_basis = inputs.get("gas_price_basis")
    converted_gas_mmbtu: float | None = None
    conversion_factor: float | None = None
    conversion_note: str | None = None
    conversion_pairs: set[tuple[str, str]] = set()
    if fuel_quantity_complete and fuel_by_unit and price_basis in {"LHV", "HHV"}:
        converted = 0.0
        factors: set[float] = set()
        complete_basis = True
        for unit, quantity in fuel_by_unit.items():
            source_basis = fuel_basis.get(unit)
            if source_basis not in {"LHV", "HHV"}:
                complete_basis = False
                break
            if source_basis == price_basis:
                factor = 1.0
            elif source_basis == "LHV" and price_basis == "HHV":
                factor = NATURAL_GAS_LHV_TO_HHV_MMBTU
            else:
                factor = 1.0 / NATURAL_GAS_LHV_TO_HHV_MMBTU
            converted += quantity * factor
            factors.add(factor)
            conversion_pairs.add((source_basis, price_basis))
        if complete_basis:
            converted_gas_mmbtu = converted
            conversion_factor = next(iter(factors)) if len(factors) == 1 else None
            if conversion_factor == 1.0:
                conversion_note = f"Fuel and price basis both {price_basis}; no conversion."
            elif len(factors) == 1:
                source_basis, target_basis = next(iter(conversion_pairs))
                conversion_note = (
                    f"PROPOSED_HERE: converted {source_basis} to {target_basis} "
                    "using natural-gas LHV/HHV factor "
                    f"{NATURAL_GAS_LHV_TO_HHV_MMBTU}."
                )
            else:
                conversion_note = (
                    "Per-unit heat-rate bases converted independently to the "
                    f"{price_basis} price basis."
                )

    gas_quantity_provenance = (
        "Completed turbine fuel telemetry by unit; accounting-only heat-rate model."
        if converted_gas_mmbtu is not None
        else "Quantity unavailable: all turbine fuel quantities and heat-rate bases are required."
    )
    gas_line = _line(
        key="turbine_gas_fuel",
        label="Turbine gas fuel",
        quantity=converted_gas_mmbtu,
        quantity_unit=f"MMBtu ({price_basis})" if price_basis in {"LHV", "HHV"} else "MMBtu (basis unknown)",
        unit_price=_number(inputs.get("gas_price_usd_per_mmbtu")),
        unit_price_unit=f"USD/MMBtu ({price_basis or 'basis unknown'})",
        provenance=inputs.get("gas_price_usd_per_mmbtu_provenance"),
        quantity_provenance=gas_quantity_provenance,
        conversion_factor=conversion_factor,
        conversion_note=conversion_note,
    )
    diesel_line = _line(
        key="diesel_fuel",
        label="Diesel fuel",
        quantity=diesel_fuel_gallons,
        quantity_unit="gal",
        unit_price=_number(inputs.get("diesel_price_usd_per_gal")),
        unit_price_unit="USD/gal",
        provenance=inputs.get("diesel_price_usd_per_gal_provenance"),
        quantity_provenance="Diesel fleet fuel-tank consumption delta; null when no diesel fleet is configured.",
    )
    vom_line = _line(
        key="turbine_variable_om",
        label="Turbine variable O&M",
        quantity=turbine_mwh,
        quantity_unit="MWh",
        unit_price=_number(inputs.get("turbine_variable_om_usd_per_mwh")),
        unit_price_unit="USD/MWh",
        provenance=inputs.get("turbine_variable_om_usd_per_mwh_provenance"),
        quantity_provenance="Integrated measured turbine output.",
    )
    rated_kw = (
        float(turbine_rated_mw) * 1000.0
        if turbine_rated_mw is not None
        else None
    )
    fom_quantity = (
        rated_kw * duration_hours / 8760.0
        if rated_kw is not None and tick_rows
        else None
    )
    fom_line = _line(
        key="turbine_fixed_om",
        label="Turbine fixed O&M allocation",
        quantity=fom_quantity,
        quantity_unit="kW-year",
        unit_price=_number(inputs.get("turbine_fixed_om_usd_per_kw_yr")),
        unit_price_unit="USD/kW-year",
        provenance=inputs.get("turbine_fixed_om_usd_per_kw_yr_provenance"),
        quantity_provenance="Rated turbine kW × run hours / 8,760 hours/year.",
    )
    start_line = _line(
        key="turbine_nonfuel_start",
        label="Turbine non-fuel start charge",
        quantity=(
            float(turbine_start_count)
            if turbine_start_count is not None
            else None
        ),
        quantity_unit="starts",
        unit_price=_number(inputs.get("turbine_start_cost_usd_per_start")),
        unit_price_unit="USD/start",
        provenance=inputs.get("turbine_start_cost_usd_per_start_provenance"),
        quantity_provenance="Completed-run turbine start counter; excludes start fuel, priced in the gas line.",
    )
    bess_line = _line(
        key="bess_degradation",
        label="BESS degradation",
        quantity=bess_throughput_mwh,
        quantity_unit="MWh AC throughput",
        unit_price=_number(inputs.get("bess_degradation_usd_per_mwh")),
        unit_price_unit="USD/MWh",
        provenance=inputs.get("bess_degradation_usd_per_mwh_provenance"),
        quantity_provenance="PROPOSED_HERE: sum of absolute signed BESS AC output over ticks.",
    )
    unserved_line = _line(
        key="unserved_energy",
        label="Unserved-energy value",
        quantity=unserved_mwh,
        quantity_unit="MWh",
        unit_price=_number(inputs.get("unserved_energy_value_usd_per_mwh")),
        unit_price_unit="USD/MWh",
        provenance=inputs.get("unserved_energy_value_usd_per_mwh_provenance"),
        quantity_provenance="Integrated D7 unserved-load telemetry.",
    )

    lines = [
        gas_line,
        diesel_line,
        vom_line,
        fom_line,
        start_line,
        bess_line,
        unserved_line,
    ]
    included = [line["key"] for line in lines if line["amount_usd"] is not None]
    excluded = [
        {"key": line["key"], "reason": "quantity or unit price is null"}
        for line in lines
        if line["amount_usd"] is None
    ]
    # These categories are outside the approved input block and are not silently
    # inferred from dispatch-ranking costs or the separate §21.2 estimate.
    excluded.extend(
        [
            {"key": "grid_import", "reason": "no operating-cost tariff input is configured"},
            {"key": "fuel_cell_fuel", "reason": "the requested gas line prices turbine fuel only"},
            {"key": "solar_or_ppa", "reason": "no source-specific contract input is configured"},
            {"key": "cooling_labor_and_other_site_om", "reason": "outside this energy-only input block"},
        ]
    )
    total = (
        sum(float(line["amount_usd"]) for line in lines if line["amount_usd"] is not None)
        if included
        else None
    )
    return {
        "currency": "USD",
        "currency_year": inputs.get("currency_year"),
        "currency_year_provenance": inputs.get("currency_year_provenance"),
        "lines": lines,
        "total_usd": round(total, 6) if total is not None else None,
        "total_includes": included,
        "total_excludes": excluded,
        "cost_per_mwh_served_usd": (
            round(total / served_mwh, 9)
            if total is not None and served_mwh is not None and served_mwh > 0
            else None
        ),
        "cost_per_mwh_it_load_usd": (
            round(total / it_load_mwh, 9)
            if total is not None and it_load_mwh is not None and it_load_mwh > 0
            else None
        ),
        "denominators": {
            "served_mwh": round(served_mwh, 9) if served_mwh is not None else None,
            "it_load_mwh": round(it_load_mwh, 9) if it_load_mwh is not None else None,
        },
    }
