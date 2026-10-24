#!/usr/bin/env python3
"""Pinned in-memory RunManager runner for D6-F candidate comparisons.

Streams physical hashing and aggregate quantities from the in-memory run; it
does not write per-tick exports.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import random
import sys
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim"
SEED = 1729
WALL_CLOCK = 1792454400.0
DT_S = 5.0
TOP_LEVEL_FUEL_FIELDS = {
    "turbine_fuel_status",
    "turbine_fuel_type",
    "turbine_fuel_units",
    "turbine_fuel_modelled",
    "turbine_fuel_telemetry",
    "turbine_fuel_parameter_provenance",
    "turbine_total_fuel_mmbtu",
}
TURBINE_UNIT_FUEL_FIELDS = {
    "fuel_modelled",
    "fuel_status",
    "fuel_type",
    "fuel_units",
    "fuel_mmbtu_this_tick",
    "load_fuel_mmbtu",
    "no_load_fuel_mmbtu",
    "hot_standby_fuel_mmbtu",
    "start_fuel_mmbtu",
    "total_fuel_mmbtu",
    "fuel_parameter_provenance",
    "low_load_threshold_pct",
}


def plain(value):
    if dataclasses.is_dataclass(value):
        return plain(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted((plain(v) for v in value), key=lambda x: str(x))
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    if hasattr(value, "value"):
        return plain(value.value)
    return value


def nonfuel_tick(tick):
    row = plain(tick)
    for field in TOP_LEVEL_FUEL_FIELDS:
        row.pop(field, None)
    for unit in row.get("turbine_units", []):
        for field in TURBINE_UNIT_FUEL_FIELDS:
            unit.pop(field, None)
    return row


def energy(ticks, field, *, absolute=False):
    total = 0.0
    for tick in ticks:
        value = float(getattr(tick, field, 0.0) or 0.0)
        total += (abs(value) if absolute else value) * DT_S / 3600.0
    return total


def digest_rows(ticks, mapper):
    digest = hashlib.sha256()
    for tick in ticks:
        payload = json.dumps(
            mapper(tick),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=True,
        )
        digest.update(payload.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


async def run(spec_path: Path, scenario_id: str):
    spec_path = spec_path.resolve()
    sys.path.insert(0, str(PACKAGE))
    os.chdir(PACKAGE)
    from api.schemas import ScenarioSpec
    from core.physical_identity import PhysicalIdentityHasher
    from runtime.operating_cost import compute_operating_cost
    from runtime.run_manager import InMemoryTimeseriesSink, RunManager, WebSocketHub
    from runtime.scenario_factory import build_run_context_from_spec

    random.seed(SEED)
    np.random.seed(SEED)
    spec = ScenarioSpec.model_validate_json(spec_path.read_bytes()).model_dump(mode="json")
    with patch("time.time", return_value=WALL_CLOCK):
        ctx = build_run_context_from_spec(
            scenario_id,
            spec,
            playback_speed=0.0,
            run_seed=SEED,
            execution_mode="headless",
        )
        sink = InMemoryTimeseriesSink()
        ctx.sink = sink
        manager = RunManager(WebSocketHub())
        await manager.start_run(ctx)
        await manager._tasks[ctx.run_id]

    ticks = sink.rows
    final = ticks[-1] if ticks else None
    full_hasher = PhysicalIdentityHasher()
    for tick in ticks:
        full_hasher.update(tick)

    fuel_rows = list(getattr(final, "turbine_fuel_telemetry", ()) or ()) if final else []
    fuel_by_unit = {
        str(row["asset_id"]): float(row["total_fuel_mmbtu"])
        for row in fuel_rows
        if row.get("asset_id") is not None
        and row.get("fuel_modelled") is True
        and row.get("total_fuel_mmbtu") is not None
    }
    component_by_unit = {
        str(row["asset_id"]): {
            component: (
                float(row[component])
                if row.get(component) is not None
                else None
            )
            for component in (
                "load_fuel_mmbtu",
                "no_load_fuel_mmbtu",
                "hot_standby_fuel_mmbtu",
                "start_fuel_mmbtu",
                "total_fuel_mmbtu",
            )
        }
        for row in fuel_rows
        if row.get("asset_id") is not None
    }
    cost_rows = [
        {
            "turbine_output_mw": float(tick.turbine_output_mw),
            "bess_output_mw": float(tick.bess_output_mw),
            "p_served_mw": (
                float(tick.p_served_mw) if tick.p_served_mw is not None else None
            ),
            "p_unserved_mw": (
                float(tick.p_unserved_mw) if tick.p_unserved_mw is not None else None
            ),
            "p_compute_mw": float(tick.p_compute_demand_mw),
            **(
                {"p_non_gpu_demand_mw": float(tick.p_non_gpu_demand_mw)}
                if tick.p_non_gpu_demand_mw is not None
                else {}
            ),
        }
        for tick in ticks
    ]
    fuel_basis = {
        str(unit.get("asset_id") or f"turbine-{index}"): (
            (unit.get("fuel") or {}).get("heat_rate_basis")
        )
        for index, unit in enumerate(spec.get("turbine_units", []))
    }
    cost_inputs = spec.get("operating_cost_inputs")
    operating_cost = (
        compute_operating_cost(
            cost_inputs,
            cost_rows,
            interval_seconds=DT_S,
            turbine_fuel_by_unit_mmbtu=fuel_by_unit,
            fuel_basis_by_unit=fuel_basis,
            fuel_quantity_complete=(
                bool(fuel_rows)
                and all(row.get("fuel_modelled") is True for row in fuel_rows)
            ),
            diesel_fuel_gallons=None,
            turbine_rated_mw=sum(
                float(unit.get("rated_mw", 0.0))
                for unit in spec.get("turbine_units", [])
            ),
            turbine_start_count=sum(
                int(row.get("start_count", 0)) for row in fuel_rows
            ),
        )
        if cost_inputs is not None
        else None
    )

    return {
        "scenario_id": scenario_id,
        "spec_path": str(spec_path),
        "seed": SEED,
        "wall_clock": WALL_CLOCK,
        "tick_count": len(ticks),
        "physical_sha256": full_hasher.hexdigest(),
        "nonfuel_sha256": digest_rows(ticks, nonfuel_tick),
        "demand_mwh": energy(ticks, "p_demand_mw"),
        "served_mwh": energy(ticks, "p_served_mw"),
        "unserved_mwh": energy(ticks, "p_unserved_mw"),
        "dispatch_curtailment_mwh": energy(ticks, "p_dispatch_curtailed_mw"),
        "turbine_mwh": energy(ticks, "turbine_output_mw"),
        "bess_ac_throughput_mwh": energy(ticks, "bess_output_mw", absolute=True),
        "turbine_fuel_by_unit_mmbtu": fuel_by_unit,
        "turbine_fuel_components_by_unit_mmbtu": component_by_unit,
        "turbine_fuel_total_mmbtu": (
            sum(fuel_by_unit.values()) if fuel_by_unit else None
        ),
        "turbine_start_count": (
            int(getattr(final, "turbine_start_count", 0)) if final else 0
        ),
        "operating_cost": operating_cost,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("spec", type=Path)
    parser.add_argument("--scenario-id", default="S10_mit_supercloud_2021-08-11")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    import asyncio

    summary = asyncio.run(run(args.spec, args.scenario_id))
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
