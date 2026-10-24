#!/usr/bin/env python3
"""Run the existing-scenario hash gate on the pinned direct-ctx.step() path."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import random
import sys
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim"
OUTPUT = ROOT / "tools/dr_isl/d6f/EXISTING_SCENARIO_HASHES.json"
SEED = 1729
WALL_CLOCK = 1792454400.0
SCENARIOS = (
    "scenario-equinix-sj-1",
    "demo-islanded-ramp",
    "S10_mit_supercloud_2021-08-11",
    "scenario-turbine-01",
    "scenario-hybrid-ai-100mw-addendum-i",
    "scenario-100mw-fuel-cell-bess-diesel",
    "scenario-fc100-islanded-v2",
    "scenario-fc100-islanded-zero-hot-v2",
)


async def main() -> None:
    sys.path.insert(0, str(PACKAGE))
    from api.schemas import ScenarioSpec
    from core.physical_identity import PhysicalIdentityHasher
    from runtime.scenario_factory import build_run_context_from_spec

    prior = {
        item["scenario_id"]: item
        for item in json.loads(
            (ROOT / "tools/dr_isl/d6/D6AX_EXISTING_CONTEXT_HASHES.json").read_text()
        )["cases"]
    }
    rows = []
    for scenario_id in SCENARIOS:
        source = PACKAGE / "config/scenarios" / f"{scenario_id}.json"
        raw = json.loads(source.read_text())
        spec = ScenarioSpec.model_validate(raw).model_dump(mode="json")
        pin_spec(spec)
        random.seed(SEED)
        np.random.seed(SEED)
        with patch("time.time", return_value=WALL_CLOCK):
            ctx = build_run_context_from_spec(
                scenario_id,
                spec,
                playback_speed=0.0,
                run_seed=SEED,
                execution_mode="headless",
            )
            hasher = PhysicalIdentityHasher()
            failures = 0
            ticks = 0
            while ctx.sim_time < ctx.end_sim_time:
                tick = ctx.step()
                if tick is None:
                    break
                hasher.update(tick)
                failures += int(not tick.physical_balance.passed)
                ticks += 1
        result = {
            "scenario_id": scenario_id,
            "tick_count": ticks,
            "physical_sha256": hasher.hexdigest(),
            "balance_failure_count": failures,
            "expected_phase_d6a_sha256": prior[scenario_id]["physical_sha256"],
        }
        result["hash_matches"] = (
            result["physical_sha256"] == result["expected_phase_d6a_sha256"]
        )
        rows.append(result)
        print(
            scenario_id,
            result["physical_sha256"],
            "matches_saved_baseline=" + str(result["hash_matches"]),
            "ticks=" + str(ticks),
            flush=True,
        )
    OUTPUT.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")


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


if __name__ == "__main__":
    asyncio.run(main())
