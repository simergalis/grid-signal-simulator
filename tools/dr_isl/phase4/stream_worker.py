"""Bounded IPC only: ticks go to the comparison parent, never to disk."""
import argparse
import asyncio
import copy
import hashlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import random
import sys
from types import SimpleNamespace
from unittest.mock import patch

p = argparse.ArgumentParser()
p.add_argument("checkout", type=Path)
p.add_argument("scenario")
p.add_argument("arm")
p.add_argument("engine")
a = p.parse_args()
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PACKAGE = Path("attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim")
loader = importlib.util.spec_from_file_location("pins", ROOT / "tools/dr_isl/baseline_runner.py")
pins = importlib.util.module_from_spec(loader)
loader.loader.exec_module(pins)
if os.environ.get("PYTHONHASHSEED") != str(pins.SEED):
    os.execve(sys.executable, [sys.executable, __file__, *sys.argv[1:]],
              dict(os.environ, PYTHONHASHSEED=str(pins.SEED), PYTHONDONTWRITEBYTECODE="1"))
pkg = a.checkout / PACKAGE
sys.path.insert(0, str(pkg))
os.chdir(pkg)
import numpy as np
from api.schemas import ScenarioSpec
from core.asset_modules import BessModule
from core.dispatch import DispatchArbitrator
from runtime.fabric_engine import FabricEngine
from runtime.run_manager import InMemoryTimeseriesSink, RunContext, RunManager, WebSocketHub
from runtime.scenario_factory import build_run_context_from_spec
from study_harness import executor

active = None
recording = False
bases = {}
floors = {}
covers = []
last_observation = {}
physical = hashlib.sha256()
count = 0
original_build = build_run_context_from_spec
original_step = RunContext.step
original_fabric = FabricEngine.__init__
original_floor = DispatchArbitrator.soc_floor_mwh
original_cover = BessModule.cover_shortfall
metrics = {}


def emit(value):
    print(json.dumps(pins.plain(value), separators=(",", ":"), allow_nan=True), flush=True)


def build(run_id, spec, **kw):
    global active
    spec = copy.deepcopy(spec)
    pins.pin_spec(spec)
    active = original_build(run_id, spec, **kw)
    for i, unit in enumerate(active.sim_state.diesel_units):
        unit._rng.seed(pins.SEED + i)
    corruption = spec.get("telemetry_corruption_config")
    if corruption is not None:
        from runtime.telemetry_corruption import generate_corruption_schedule
        active.telemetry_corruption = generate_corruption_schedule(
            max(1, int(active.end_sim_time / 5)),
            seed=corruption.get("seed", pins.SEED),
            noise_sigma=float(corruption.get("noise_sigma", 0)),
            dropout_prob=float(corruption.get("dropout_prob", 0)),
            max_stale=int(corruption.get("max_stale", 0)),
        )
    return active


def fabric(self, *pos, **kw):
    kw["seed"] = pins.SEED
    return original_fabric(self, *pos, **kw)


def floor(self, bess):
    result = original_floor(self, bess)
    if recording:
        floors[bess.config.asset_id] = result
        bases[bess.config.asset_id] = copy.deepcopy(
            getattr(self, "reserve_floor_basis", {}).get(bess.config.asset_id, {})
        )
    return result


def cover(self, allocated_mw, fleet_covered, dt_seconds, power_ceiling_mw, soc_floor_mwh=0):
    before = self.soc_mwh
    on_bus = [
        u.config.asset_id for u in active.sim_state.turbines + active.sim_state.diesel_units
        if u.is_on_bus
    ]
    result = original_cover(self, allocated_mw, fleet_covered, dt_seconds,
                            power_ceiling_mw, soc_floor_mwh)
    if recording:
        covers.append(dict(unit=self.config.asset_id, requested_mw=allocated_mw,
                           output_mw=result, physical_floor_mwh=soc_floor_mwh,
                           before_mwh=before, after_mwh=self.soc_mwh, on_bus=on_bus))
    return result


def send_tick(tick):
    global count
    row = pins.plain(tick)
    row = {k: v for k, v in row.items() if k not in pins.EXCLUDED}
    physical.update(pins.encoded(row))
    count += 1
    emit(dict(kind="tick", physical=row, observation=last_observation))


def step(self, *pos, **kw):
    global covers, floors, bases, last_observation
    if not recording:
        return original_step(self, *pos, **kw)
    covers, floors, bases = [], {}, {}
    before = {b.config.asset_id: b.soc_mwh for b in self.sim_state.bess_units}
    tick = original_step(self, *pos, **kw)
    last_observation = dict(
        before=before,
        after={b.config.asset_id: b.soc_mwh for b in self.sim_state.bess_units},
        floors=floors, bases=bases, covers=covers,
        balance_passed=tick.physical_balance.passed,
        balance_defect_mw=tick.physical_balance.defect_mw,
        on_bus=[u.config.asset_id for u in self.sim_state.turbines + self.sim_state.diesel_units
                if u.is_on_bus],
    )
    if a.arm != "app":
        send_tick(tick)
    return tick


class Sink(InMemoryTimeseriesSink):
    async def append(self, tick):
        # The original sink API/finalization remain; only retained output rows
        # are replaced with streaming. No simulation/control input is changed.
        send_tick(tick)


class Writer:
    def write(self, *, identity, record, summary, tick_rows):
        global metrics
        metrics = copy.deepcopy(summary)
        digest = hashlib.sha256()
        for row in tick_rows:
            digest.update(pins.encoded(row))
        record["audit_compact_sha256"] = digest.hexdigest()
        return SimpleNamespace(as_dict=lambda: {})


class Cache:
    def put(self, identity, record):
        return record


async def run():
    global recording
    random.seed(pins.SEED)
    np.random.seed(pins.SEED)
    if a.arm == "app":
        spec = ScenarioSpec.model_validate_json(
            (pkg / "config/scenarios" / (a.scenario + ".json")).read_bytes()
        ).model_dump(mode="json")
        ctx = build(a.scenario, spec, playback_speed=0)
        ctx.sink = Sink()
        recording = True
        manager = RunManager(WebSocketHub())
        await manager.start_run(ctx)
        await manager._tasks[ctx.run_id]
        record = {}
    else:
        ex = executor.StudyRunExecutor(
            output_dir=HERE / "unused-output", engine_commit=a.engine,
            harness_commit="ae49aaa",
        )
        ex.writer, ex.cache = Writer(), Cache()
        spec = ex._expanded_spec(a.scenario, None, None)
        pins.pin_spec(spec)
        replay, demand = ex._probe(spec, run_id=f"{a.scenario}-study-s1-probe")
        recording = True
        record = ex._run_mode(
            scenario_id=a.scenario, mode=a.arm, spec=spec, replay_events=replay,
            demand_replay=demand,
            seed=None if a.scenario.startswith("scenario-h") else 42,
            # Capture, never suppress, a native guard failure for the STOP
            # report's complete before/after table. The parent requires PASS.
            allow_guard_failure=True, reuse_cache=False,
        )
    emit(dict(kind="summary", physical_sha256=physical.hexdigest(), ticks=count,
              metrics=metrics, record=record,
              end_sim_time=active.end_sim_time,
              build_warnings=active.metadata.get("build_warnings"),
              final_floor_basis=active.metadata.get("bess_reserve_floor_basis"),
              floor_history_count=len(active.metadata.get("bess_reserve_floor_history", []))))


logging.basicConfig(level=logging.CRITICAL)
with patch("time.time", return_value=pins.WALL_CLOCK), \
     patch.object(FabricEngine, "__init__", fabric), \
     patch.object(DispatchArbitrator, "soc_floor_mwh", floor), \
     patch.object(BessModule, "cover_shortfall", cover), \
     patch.object(RunContext, "step", step), \
     patch.object(executor, "build_run_context_from_spec", build):
    asyncio.run(run())
