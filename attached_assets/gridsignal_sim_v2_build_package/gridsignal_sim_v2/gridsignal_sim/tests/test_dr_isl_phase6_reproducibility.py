"""Phase 6 D4 deterministic seed and identity contract tests (TC-ISL-34–40)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import random
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

from api.schemas import ScenarioSpec
from core.physical_identity import physical_identity_hash
from runtime.run_manager import _advisory_wall_time
from runtime.scenario_factory import build_run_context_from_spec
from runtime.seed_resolution import (
    resolve_run_seed_manifest,
    seed_consumers_for_spec,
)


PACKAGE = Path(__file__).resolve().parents[1]


def _simple_spec() -> dict:
    return ScenarioSpec.model_validate(
        {
            "name": "TC-ISL-40 replay fixture",
            "island_mode": True,
            "turbine_units": [],
            "solar_rated_mw": 0.0,
            "pue_base": 1.0,
            "bess_units": [
                {
                    "asset_id": "bess-replay",
                    "rated_mw": 10.0,
                    "usable_mwh": 20.0,
                    "initial_soc_fraction": 1.0,
                    "grid_forming": True,
                }
            ],
        }
    ).model_dump(mode="json")


def test_tc_isl_34_null_root_is_drawn_once_and_recorded():
    with patch("runtime.seed_resolution.secrets.randbits", return_value=0xD4):
        first = resolve_run_seed_manifest(
            None,
            consumer_names={"fabric", "diesel:diesel-a"},
        )
        replay = resolve_run_seed_manifest(
            None,
            consumer_names={"fabric", "diesel:diesel-a", "diesel:diesel-b"},
            existing_manifest=first,
        )
    assert first["root_seed"] == 0xD4
    assert first["root_seed_drawn"] is True
    assert replay["root_seed"] == first["root_seed"]
    assert replay["consumer_seeds"]["fabric"] == first["consumer_seeds"]["fabric"]
    assert replay["consumer_sources"]["diesel:diesel-a"] == "derived_from_run_seed"
    assert "diesel:diesel-b" in replay["consumer_seeds"]


def test_tc_isl_35_consumer_seed_is_stable_across_hash_seeds():
    script = (
        "from runtime.seed_resolution import resolve_run_seed_manifest; "
        "m=resolve_run_seed_manifest(42, consumer_names={'fabric','kube:cluster-a'}); "
        "print(m['consumer_seeds'])"
    )
    outputs = []
    for hash_seed in ("1", "987654"):
        env = dict(os.environ, PYTHONHASHSEED=hash_seed)
        outputs.append(
            subprocess.check_output(
                [sys.executable, "-c", script],
                cwd=PACKAGE,
                env=env,
                text=True,
            ).strip()
        )
    assert outputs[0] == outputs[1]


def test_tc_isl_36_each_diesel_uses_its_recorded_derived_seed():
    source = (
        PACKAGE / "config" / "scenarios"
        / "scenario-100mw-fuel-cell-bess-diesel.json"
    )
    spec = ScenarioSpec.model_validate_json(source.read_bytes()).model_dump(
        mode="json"
    )
    ctx = build_run_context_from_spec(
        "tc-isl-36",
        spec,
        playback_speed=0.0,
        run_seed=42,
    )
    manifest = ctx.metadata["seed_manifest"]
    assert ctx.sim_state.diesel_units
    for unit in ctx.sim_state.diesel_units:
        unit_id = unit.config.asset_id
        expected = random.Random(
            manifest["consumer_seeds"][f"diesel:{unit_id}"]
        ).getstate()
        assert unit._rng.getstate() == expected


def test_tc_isl_37_fabric_seed_is_independent_of_python_hash():
    script = (
        "from runtime.seed_resolution import resolve_run_seed_manifest; "
        "print(resolve_run_seed_manifest(42, consumer_names={'fabric'})"
        "['consumer_seeds']['fabric'])"
    )
    outputs = []
    for hash_seed in ("3", "4567"):
        outputs.append(
            subprocess.check_output(
                [sys.executable, "-c", script],
                cwd=PACKAGE,
                env=dict(os.environ, PYTHONHASHSEED=hash_seed),
                text=True,
            ).strip()
        )
    assert outputs[0] == outputs[1]
    ctx = build_run_context_from_spec(
        "tc-isl-37",
        _simple_spec(),
        playback_speed=0.0,
        run_seed=42,
    )
    assert ctx.fabric_engine is not None
    assert ctx.fabric_engine._seed == ctx.metadata["seed_manifest"][
        "consumer_seeds"
    ]["fabric"]


def test_tc_isl_38_nonphysical_fields_are_excluded_from_identity():
    first = {
        "tick_index": 1,
        "frequency_hz": 60.0,
        "advisory_telemetry": {"proposal_id": "one"},
        "fabric_modal": {"window": 1},
        "wall_stamp_utc": 100.0,
        "insufficient_reserve_proposal_id": "a",
    }
    second = {
        **first,
        "advisory_telemetry": {"proposal_id": "two"},
        "fabric_modal": {"window": 2},
        "wall_stamp_utc": 200.0,
        "insufficient_reserve_proposal_id": "b",
    }
    assert physical_identity_hash([first]) == physical_identity_hash([second])
    assert physical_identity_hash([first]) != physical_identity_hash(
        [{**second, "frequency_hz": 61.0}]
    )


def test_tc_isl_39_advisory_cadence_uses_sim_time_outside_live_mode():
    ctx = SimpleNamespace(metadata={"execution_mode": "study"})
    with patch("runtime.run_manager._time_module.time", return_value=9999.0):
        assert _advisory_wall_time(ctx, 25.0) == 25.0
        ctx.metadata["execution_mode"] = "headless"
        assert _advisory_wall_time(ctx, 30.0) == 30.0
        ctx.metadata["execution_mode"] = "interactive"
        assert _advisory_wall_time(ctx, 35.0) == 9999.0


def test_tc_isl_40_replay_with_recorded_seed_has_identical_physical_hash():
    spec = _simple_spec()
    names, configured = seed_consumers_for_spec(spec)
    manifest = resolve_run_seed_manifest(
        42,
        consumer_names=names,
        configured_seeds=configured,
    )
    runs = []
    for _ in range(2):
        ctx = build_run_context_from_spec(
            "tc-isl-40",
            json.loads(json.dumps(spec)),
            playback_speed=0.0,
            run_seed=42,
            seed_manifest=manifest,
            execution_mode="headless",
        )
        ticks = [ctx.step() for _ in range(3)]
        runs.append(physical_identity_hash(ticks))
    assert runs[0] == runs[1]
