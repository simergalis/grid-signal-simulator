#!/usr/bin/env python3
# DR-ISL pinned seeder-path baseline runner (no application code changes).
# Pinning: fabric hash/seed 1729; wall clock 1792454400.0; Python/NumPy 1729;
# configured kube seeds 1729; per-diesel RNG 1729+i; generator/corruption seeds
# 1729 when absent/null (Phase 0b reconstruction). Seeder-path execution does
# not call the API's external/LLM generators; configured corruption is seeded.
# Hash contract: SHA-256 over ticks in order, each one UTF-8 compact sorted-key
# JSON object plus LF; exclude exactly advisory_telemetry, fabric_modal,
# wall_stamp_utc, insufficient_reserve_proposal_id. NaN allowed.
"""Run from any checkout; all generated output defaults to /tmp, never the repo."""

import argparse
import asyncio
import dataclasses
import hashlib
import json
import logging
import os
from pathlib import Path
import random
import sys
from unittest.mock import patch

PACKAGE = Path("attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim")
EXCLUDED = frozenset({
    "advisory_telemetry", "fabric_modal", "wall_stamp_utc",
    "insufficient_reserve_proposal_id",
})
SEED = 1729
WALL_CLOCK = 1792454400.0


def plain(value):
    if dataclasses.is_dataclass(value):
        return plain(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(key): plain(child) for key, child in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted((plain(child) for child in value),
                      key=lambda item: json.dumps(item, sort_keys=True, allow_nan=True))
    if isinstance(value, (tuple, list)):
        return [plain(child) for child in value]
    if hasattr(value, "value"):
        return plain(value.value)
    return value


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=True).encode("utf-8") + b"\n"


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
            ("cluster_gen_config", "rng_seed"), ("stressor_gen_config", "rng_seed"),
            ("param_sampling_config", "seed"), ("telemetry_corruption_config", "seed"),
        ):
            if isinstance(value.get(key), dict) and value[key].get(seed_key) is None:
                value[key][seed_key] = SEED
    elif isinstance(value, list):
        for child in value:
            pin_spec(child)


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario_id")
    parser.add_argument("--repetitions", "-n", type=int, default=2)
    parser.add_argument("--package-root", type=Path,
                        default=Path(__file__).resolve().parents[2] / PACKAGE)
    parser.add_argument("--output-dir", type=Path,
                        default=Path("/tmp/DR-ISL-baselines"))
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("--repetitions must be positive")
    args.package_root = args.package_root.resolve()
    args.output_dir = args.output_dir.resolve()
    if args.output_dir.is_relative_to(args.package_root):
        parser.error("output directory must be outside the application package")
    return args


async def run(args):
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(args.package_root))
    os.chdir(args.package_root)
    import numpy as np
    from api.schemas import ScenarioSpec
    from core.simulation_core import SimulationState
    from runtime.fabric_engine import FabricEngine
    from runtime.run_manager import (
        InMemoryTimeseriesSink, RunManager, WebSocketHub, TICK_INTERVAL_SIM_SECONDS,
    )
    from runtime.scenario_factory import build_run_context_from_spec

    args.output_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=str(args.output_dir / "engine.log"), level=logging.ERROR)
    original_fabric = FabricEngine.__init__
    original_apply = SimulationState.apply_workload_signal
    events = []

    def fabric(self, *positional, **kwargs):
        kwargs["seed"] = SEED
        return original_fabric(self, *positional, **kwargs)

    def apply(self, signal, *positional, **kwargs):
        events.append({"observed_tick_index": self.tick_index + 1,
                       "event": plain(signal)})
        return original_apply(self, signal, *positional, **kwargs)

    summaries = []
    for repetition in range(1, args.repetitions + 1):
        random.seed(SEED)
        np.random.seed(SEED)
        events.clear()
        source = args.package_root / "config/scenarios" / (args.scenario_id + ".json")
        spec = ScenarioSpec.model_validate_json(source.read_bytes()).model_dump(mode="json")
        pin_spec(spec)
        with patch("time.time", return_value=WALL_CLOCK), \
                patch.object(FabricEngine, "__init__", fabric), \
                patch.object(SimulationState, "apply_workload_signal", apply):
            ctx = build_run_context_from_spec(args.scenario_id, spec, playback_speed=0.0)
            for index, unit in enumerate(ctx.sim_state.diesel_units):
                unit._rng.seed(SEED + index)
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
            manager = RunManager(WebSocketHub())
            await manager.start_run(ctx)
            await manager._tasks[ctx.run_id]
        digest = hashlib.sha256()
        failures = []
        prefix = args.output_dir / f"{args.scenario_id}.{repetition}"
        with Path(str(prefix) + ".ticks.jsonl").open("wb") as output:
            for tick in sink.rows:
                row = plain(tick)
                output.write(encoded(row))
                digest.update(encoded({key: val for key, val in row.items()
                                       if key not in EXCLUDED}))
                if not tick.physical_balance.passed:
                    failures.append(tick.tick_index)
        Path(str(prefix) + ".events.json").write_text(json.dumps(events, indent=2))
        Path(str(prefix) + ".spec.json").write_text(json.dumps(spec, indent=2))
        summary = {
            "scenario_id": args.scenario_id, "repetition": repetition,
            "physical_sha256": digest.hexdigest(), "tick_count": len(sink.rows),
            "failing_tick_count": len(failures), "failing_ticks": failures,
            "spec_island_mode": spec["island_mode"],
            "verification_modes": sorted({
                tick.physical_balance.verification_mode for tick in sink.rows}),
            "tolerances_mw": sorted({
                tick.physical_balance.tolerance_mw for tick in sink.rows}),
            "hash_exclusions": sorted(EXCLUDED),
        }
        Path(str(prefix) + ".summary.json").write_text(json.dumps(summary, indent=2))
        summaries.append(summary)
        print(json.dumps(summary, sort_keys=True, allow_nan=True), flush=True)
    return summaries


def main():
    args = arguments()
    if os.environ.get("PYTHONHASHSEED") != str(SEED):
        env = dict(os.environ, PYTHONHASHSEED=str(SEED),
                   PYTHONDONTWRITEBYTECODE="1")
        os.execve(sys.executable, [sys.executable, __file__, *sys.argv[1:]], env)
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
