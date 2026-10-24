#!/usr/bin/env python3
"""Compact RunManager-path S10 candidate runner for DR-ISL D6a.

Mirrors tools/dr_isl/baseline_runner.py pinning and execution order, while
accepting candidate spec paths and retaining only summary metrics/hashes.
No tick export is written.
"""

import argparse
import asyncio
import dataclasses
import json
import os
from pathlib import Path
import random
import sys
from unittest.mock import patch

SEED = 1729
WALL_CLOCK = 1792454400.0
DT_S = 5.0
PACKAGE = Path(__file__).resolve().parents[3] / (
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim"
)


def plain(value):
    if dataclasses.is_dataclass(value):
        return plain(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(key): plain(child) for key, child in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=lambda item: str(item))
    if isinstance(value, (tuple, list)):
        return [plain(child) for child in value]
    if hasattr(value, "value"):
        return plain(value.value)
    return value


def pin_spec(value):
    if isinstance(value, dict):
        for key, child in list(value.items()):
            if key in {"seed", "rng_seed"} and child is None:
                value[key] = SEED
            else:
                pin_spec(child)
        if isinstance(value.get("kube_config"), dict):
            value["kube_config"]["rng_seed"] = SEED
        for key, seed_key in (
            ("cluster_gen_config", "rng_seed"),
            ("stressor_gen_config", "rng_seed"),
            ("param_sampling_config", "seed"),
            ("telemetry_corruption_config", "seed"),
        ):
            if isinstance(value.get(key), dict) and value[key].get(seed_key) is None:
                value[key][seed_key] = SEED
    elif isinstance(value, list):
        for child in value:
            pin_spec(child)


def energy(ticks, field):
    return sum(float(getattr(tick, field, 0.0) or 0.0) * DT_S / 3600.0 for tick in ticks)


async def run_one(
    label: str,
    scenario_id: str,
    spec_path: Path,
    repetition: int,
    max_ticks=None,
):
    global DT_S
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(PACKAGE))
    os.chdir(PACKAGE)
    import numpy as np

    from api.schemas import ScenarioSpec
    from core.physical_identity import PhysicalIdentityHasher
    from core.simulation_core import SimulationState
    from runtime.run_manager import (
        InMemoryTimeseriesSink,
        RunManager,
        RunContext,
        TICK_INTERVAL_SIM_SECONDS,
        WebSocketHub,
    )
    from runtime.scenario_factory import build_run_context_from_spec
    DT_S = float(TICK_INTERVAL_SIM_SECONDS)

    random.seed(SEED)
    np.random.seed(SEED)
    spec = ScenarioSpec.model_validate_json(spec_path.read_bytes()).model_dump(mode="json")
    pin_spec(spec)

    # Match the established baseline runner: wall time is pinned for factory
    # construction as well as RunManager execution.
    with patch("time.time", return_value=WALL_CLOCK):
        ctx = build_run_context_from_spec(
            scenario_id,
            spec,
            playback_speed=0.0,
            run_seed=SEED,
            execution_mode="headless",
        )
        if max_ticks is not None:
            ctx.end_sim_time = min(
                float(ctx.end_sim_time), int(max_ticks) * DT_S
            )
        corruption = spec.get("telemetry_corruption_config")
        if corruption is not None:
            from runtime.telemetry_corruption import generate_corruption_schedule

            ctx.telemetry_corruption = generate_corruption_schedule(
                max(1, int(ctx.end_sim_time / TICK_INTERVAL_SIM_SECONDS)),
                seed=corruption.get("seed", SEED),
                noise_sigma=float(corruption.get("noise_sigma", 0.0)),
                dropout_prob=float(corruption.get("dropout_prob", 0.0)),
                max_stale=int(corruption.get("max_stale", 0)),
            )
        sink = InMemoryTimeseriesSink()
        ctx.sink = sink
        initial_turbine_states = {
            str(turbine.config.asset_id): str(turbine.state.value)
            for turbine in ctx.sim_state.turbines
        }
        manager = RunManager(WebSocketHub())
        await manager.start_run(ctx)
        await manager._tasks[ctx.run_id]

    ticks = sink.rows
    hasher = PhysicalIdentityHasher()
    for tick in ticks:
        hasher.update(tick)

    demand = [float(tick.p_demand_mw) for tick in ticks]
    unserved = [float(tick.p_unserved_mw or 0.0) for tick in ticks]
    frequency = [float(tick.frequency_hz) for tick in ticks]
    collapse_ticks = [tick for tick in ticks if tick.island_collapsed]
    controller = getattr(ctx, "turbine_commitment_controller", None)
    refusal_list = list(getattr(controller, "stop_floor_refusals", []) or [])
    transitions = []
    prior_states = dict(initial_turbine_states)
    for tick in ticks:
        for unit in tick.turbine_units:
            asset_id = str(unit.get("asset_id", ""))
            state = str(unit.get("state", ""))
            previous = prior_states.get(asset_id, state)
            if state != previous:
                transitions.append(
                    {
                        "unit": asset_id,
                        "from": previous,
                        "to": state,
                        "tick": tick.tick_index,
                        "sim_time_s": tick.sim_time_seconds,
                    }
                )
                prior_states[asset_id] = state

    turbine_start_events = [
        event
        for event in transitions
        if event["to"].lower() == "starting"
    ]
    turbine_stop_events = [
        event
        for event in transitions
        if event["to"].lower() in {"unloading", "offline"}
    ]
    min_stable = [
        sum(
            float(unit.get("msl_mw", 0.0))
            for unit in tick.turbine_units
            if unit.get("breaker_closed")
        )
        for tick in ticks
    ]
    first_exceed = None
    startup_surplus_mwh = 0.0
    for index, tick in enumerate(ticks):
        if float(tick.p_demand_mw) > min_stable[index] + 1e-12:
            first_exceed = {
                "tick": tick.tick_index,
                "sim_time_s": tick.sim_time_seconds,
                "demand_mw": tick.p_demand_mw,
                "on_bus_turbine_msl_mw": min_stable[index],
            }
            break
        startup_surplus_mwh += max(
            0.0, float(tick.p_dispatch_curtailed_mw or 0.0)
        ) * DT_S / 3600.0

    final = ticks[-1] if ticks else None
    bess = list(ctx.sim_state.bess_units)
    final_fuel_rows = (
        list(getattr(final, "turbine_fuel_telemetry", ()) or ())
        if final is not None
        else []
    )
    modelled_final_fuel_rows = [
        row
        for row in final_fuel_rows
        if row.get("fuel_modelled")
        and row.get("total_fuel_mmbtu") is not None
    ]
    turbine_fuel_mmbtu = (
        sum(float(row["total_fuel_mmbtu"]) for row in modelled_final_fuel_rows)
        if modelled_final_fuel_rows
        else (
            float(final.turbine_total_fuel_mmbtu)
            if final is not None and final.turbine_total_fuel_mmbtu is not None
            else None
        )
    )
    summary = {
        "case": label,
        "scenario_id": scenario_id,
        "repetition": repetition,
        "source_spec": str(spec_path),
        "seed": SEED,
        "wall_clock": WALL_CLOCK,
        "physical_sha256": hasher.hexdigest(),
        "tick_count": len(ticks),
        "duration_s": float(final.sim_time_seconds) if final else 0.0,
        "demand_mwh": energy(ticks, "p_demand_mw"),
        "served_mwh": energy(ticks, "p_served_mw"),
        "unserved_mwh": energy(ticks, "p_unserved_mw"),
        "peak_demand_mw": max(demand, default=0.0),
        "peak_unserved_mw": max(unserved, default=0.0),
        "dispatch_curtailment_mwh": energy(ticks, "p_dispatch_curtailed_mw"),
        "turbine_fuel_mmbtu": turbine_fuel_mmbtu,
        "turbine_fuel_status": (
            str(final.turbine_fuel_status) if final is not None else "not_modelled"
        ),
        "turbine_fuel_modelled": (
            bool(final.turbine_fuel_modelled) if final is not None else False
        ),
        "turbine_fuel_units": [
            {
                "asset_id": row.get("asset_id"),
                "fuel_modelled": bool(row.get("fuel_modelled")),
                "total_fuel_mmbtu": row.get("total_fuel_mmbtu"),
            }
            for row in final_fuel_rows
        ],
        "turbine_start_count": int(final.turbine_start_count) if final else 0,
        "turbine_start_events": turbine_start_events,
        "turbine_stop_events": turbine_stop_events,
        "start_stop_transitions": transitions,
        "bess_soc_start_fraction": (
            float(bess[0].config.initial_soc_fraction) if bess else None
        ),
        "bess_soc_min_fraction": min(
            (float(tick.bess_soc_fraction) for tick in ticks), default=0.0
        ),
        "bess_soc_max_fraction": max(
            (float(tick.bess_soc_fraction) for tick in ticks), default=0.0
        ),
        "bess_soc_end_fraction": (
            float(final.bess_soc_fraction) if final else None
        ),
        "bess_usable_mwh": sum(float(unit.config.usable_mwh) for unit in bess),
        "reserve_floor_refusal_count": len(refusal_list),
        "reserve_floor_refusals": plain(refusal_list),
        "frequency_min_hz": min(frequency, default=0.0),
        "frequency_max_hz": max(frequency, default=0.0),
        "invalid_frequency_tick_count": sum(
            not bool(tick.frequency_valid) for tick in ticks
        ),
        "invalid_frequency_fraction": (
            sum(not bool(tick.frequency_valid) for tick in ticks) / len(ticks)
            if ticks
            else 0.0
        ),
        "balance_failure_count": sum(
            not bool(tick.physical_balance and tick.physical_balance.passed)
            for tick in ticks
        ),
        "first_balance_failure_tick": next(
            (
                tick.tick_index
                for tick in ticks
                if not bool(tick.physical_balance and tick.physical_balance.passed)
            ),
            None,
        ),
        "island_collapsed": bool(collapse_ticks),
        "collapse_time_s": (
            collapse_ticks[0].sim_time_seconds if collapse_ticks else None
        ),
        "collapse_reason": (
            collapse_ticks[0].collapse_reason if collapse_ticks else None
        ),
        "startup_surplus_window": {
            "first_demand_exceeds_on_bus_turbine_msl": first_exceed,
            "dispatch_curtailment_energy_before_exceed_mwh": startup_surplus_mwh,
        },
        "seed_manifest": plain(ctx.metadata.get("seed_manifest"))
        if isinstance(ctx.metadata, dict)
        else None,
    }
    return summary


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", action="append", nargs=2, required=True)
    parser.add_argument(
        "--scenario-id",
        default="S10_mit_supercloud_2021-08-11",
        help="canonical app scenario ID, identical for current and candidate specs",
    )
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--max-ticks", type=int)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("--repetitions must be positive")

    output = Path(args.out).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "pinning": {
            "seed": SEED,
            "python_numpy_seed": SEED,
            "wall_clock": WALL_CLOCK,
            "dt_s": DT_S,
        },
        "runs": [],
    }
    for label, path in args.case:
        for repetition in range(1, args.repetitions + 1):
            summary = await run_one(
                label,
                args.scenario_id,
                Path(path).resolve(),
                repetition,
                max_ticks=args.max_ticks,
            )
            document["runs"].append(summary)
            output.write_text(
                json.dumps(document, indent=2, allow_nan=True) + "\n",
                encoding="utf-8",
            )
            print(json.dumps(summary, sort_keys=True, allow_nan=True), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
