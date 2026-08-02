"""
End-to-end tests for the S1–S8 fabric stress scenarios launched via the
Scenario Builder path (POST /runs with a fabric-sN scenario_id).

Each test:
 1. Seeds the ScenarioStore and fetches the scenario spec.
 2. Builds a RunContext via build_run_context_from_spec(), which wires a
    FabricEngine with the scenario's declared seed, fixture, constants, and
    profiles.
 3. Manually drives the run loop for a small number of ticks so the
    FabricEngine accumulates TickResult objects.
 4. Calls evaluate_scenario_assertions() and confirms the verdict.

These tests intentionally run in-process (no uvicorn) so they complete in
seconds and can gate CI.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import json as _json

from api.routes.scenarios import build_seeded_store          # noqa: E402
from runtime.scenario_factory import build_run_context_from_spec  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_spec(scenario_id: str) -> dict:
    """Return the spec_data dict for a scenario from the seeded store."""
    store = build_seeded_store()
    rec = store.get(scenario_id)
    assert rec is not None, f"Scenario '{scenario_id}' not found in store"
    # ScenarioRecord stores the spec as a JSON string in spec_json
    return _json.loads(rec.spec_json)


def _drive_fabric_ticks(ctx, n_ticks: int = 16) -> None:
    """Advance the FabricEngine for n_ticks with 5 s dt_s."""
    fe = ctx.fabric_engine
    assert fe is not None, "FabricEngine was not wired into RunContext"
    for i in range(n_ticks):
        fe.step(sim_time_s=float(i * 5), dt_s=5.0)


def _build_and_drive(scenario_id: str, n_ticks: int = 16):
    spec_data = _get_spec(scenario_id)
    ctx = build_run_context_from_spec(
        run_id=f"test-{scenario_id}",
        spec_data=spec_data,
    )
    _drive_fabric_ticks(ctx, n_ticks=n_ticks)
    return ctx


# ---------------------------------------------------------------------------
# Confirm S1–S8 are discoverable via GET /scenarios
# ---------------------------------------------------------------------------

def test_all_fabric_scenarios_in_store():
    """All 8 fabric scenarios are seeded into the ScenarioStore."""
    store = build_seeded_store()
    ids = {sid for sid in store._data}
    fabric_ids = {f"fabric-s{i}" for i in range(1, 9)}
    missing = fabric_ids - ids
    assert not missing, f"Missing scenario IDs: {missing}"


def test_fabric_scenario_names():
    """Each fabric scenario has a descriptive name starting with S<N>:."""
    store = build_seeded_store()
    for i in range(1, 9):
        sid = f"fabric-s{i}"
        rec = store.get(sid)
        assert rec is not None
        assert rec.name.startswith(f"S{i}:"), (
            f"Expected name starting with 'S{i}:', got '{rec.name}'"
        )


# ---------------------------------------------------------------------------
# S1: Baseline Training
# ---------------------------------------------------------------------------

def test_s1_baseline_training_all_pass():
    """S1 assertions all PASS: weight_load phase present, no corroboration,
    latency < 1000 ms."""
    ctx = _build_and_drive("fabric-s1")
    fe = ctx.fabric_engine
    assert fe.has_fabric_assertions
    results = fe.evaluate_scenario_assertions()
    assert results, "Expected at least one assertion result for S1"
    fails = [r for r in results if r.status != "PASS"]
    assert not fails, f"S1 assertions failed: {[(r.check, r.detail) for r in fails]}"


# ---------------------------------------------------------------------------
# S2: Checkpoint ECMP Hotspot
# ---------------------------------------------------------------------------

def test_s2_checkpoint_ecmp_hotspot_all_pass():
    """S2 assertions: checkpoint phase present, storage congestion >= 1 link,
    compute quiesces, corroboration fired, elephant flow present."""
    # S2 needs a run long enough to reach the checkpoint phase (20 s training
    # then checkpoint); drive 80 ticks × 0.25 s = 20 s at dt=0.25 s.
    spec_data = _get_spec("fabric-s2")
    ctx = build_run_context_from_spec(
        run_id="test-fabric-s2",
        spec_data=spec_data,
    )
    fe = ctx.fabric_engine
    sc = fe._fabric_scenario
    assert sc is not None, "S2 Scenario not loaded"
    # Drive enough ticks to cover the checkpoint phase (scenario dt_s=0.25 s)
    n = max(int(sc.duration_s / sc.dt_s), 60)
    for i in range(n):
        fe.step(sim_time_s=i * sc.dt_s, dt_s=sc.dt_s)

    assert fe.has_fabric_assertions
    results = fe.evaluate_scenario_assertions()
    fails = [r for r in results if r.status != "PASS"]
    assert not fails, f"S2 assertions failed: {[(r.check, r.detail) for r in fails]}"


# ---------------------------------------------------------------------------
# S5: Gray Failure (gray_loss_elevated)
# ---------------------------------------------------------------------------

def test_s5_gray_failure_all_pass():
    """S5 gray_loss_elevated assertion: loss on degraded link >= injected floor."""
    spec_data = _get_spec("fabric-s5")
    ctx = build_run_context_from_spec(
        run_id="test-fabric-s5",
        spec_data=spec_data,
    )
    fe = ctx.fabric_engine
    sc = fe._fabric_scenario
    assert sc is not None, "S5 Scenario not loaded"
    # Drive all ticks (30 s / 0.25 s = 120 ticks)
    n = int(sc.duration_s / sc.dt_s)
    for i in range(n):
        fe.step(sim_time_s=i * sc.dt_s, dt_s=sc.dt_s)

    assert fe.has_fabric_assertions
    results = fe.evaluate_scenario_assertions()
    assert results, "No assertion results for S5"
    fails = [r for r in results if r.status != "PASS"]
    assert not fails, f"S5 gray_loss_elevated failed: {[(r.check, r.detail) for r in fails]}"


# ---------------------------------------------------------------------------
# S7: Slow Checkpoint (uses non-default traffic profile)
# ---------------------------------------------------------------------------

def test_s7_slow_checkpoint_uses_correct_profile():
    """S7 loads workload_traffic_profiles_slow_checkpoint.json (not the default)."""
    spec_data = _get_spec("fabric-s7")
    ctx = build_run_context_from_spec(
        run_id="test-fabric-s7-profile",
        spec_data=spec_data,
    )
    fe = ctx.fabric_engine
    sc = fe._fabric_scenario
    assert sc is not None, "S7 Scenario not loaded"
    assert "slow_checkpoint" in sc.profiles_file, (
        f"S7 should use the slow_checkpoint profile, got: {sc.profiles_file}"
    )


def test_s7_slow_checkpoint_all_pass():
    """S7 assertions: checkpoint phase present, compute quiesces, corroboration fires."""
    spec_data = _get_spec("fabric-s7")
    ctx = build_run_context_from_spec(
        run_id="test-fabric-s7",
        spec_data=spec_data,
    )
    fe = ctx.fabric_engine
    sc = fe._fabric_scenario
    assert sc is not None, "S7 Scenario not loaded"
    # Drive all ticks (100 s / 0.25 s = 400 ticks)
    n = int(sc.duration_s / sc.dt_s)
    for i in range(n):
        fe.step(sim_time_s=i * sc.dt_s, dt_s=sc.dt_s)

    assert fe.has_fabric_assertions
    results = fe.evaluate_scenario_assertions()
    fails = [r for r in results if r.status != "PASS"]
    assert not fails, f"S7 assertions failed: {[(r.check, r.detail) for r in fails]}"


# ---------------------------------------------------------------------------
# S3, S4, S6, S8: Quick smoke test (PASS verdict)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("scenario_id", [
    "fabric-s3",
    "fabric-s4",
    "fabric-s6",
    "fabric-s8",
])
def test_smoke_scenario_all_pass(scenario_id):
    """S3/S4/S6/S8 assertion verdicts are all PASS when run to completion."""
    spec_data = _get_spec(scenario_id)
    ctx = build_run_context_from_spec(
        run_id=f"test-{scenario_id}",
        spec_data=spec_data,
    )
    fe = ctx.fabric_engine
    sc = fe._fabric_scenario
    assert sc is not None, f"{scenario_id} Scenario not loaded"
    n = int(sc.duration_s / sc.dt_s)
    for i in range(n):
        fe.step(sim_time_s=i * sc.dt_s, dt_s=sc.dt_s)

    assert fe.has_fabric_assertions
    results = fe.evaluate_scenario_assertions()
    fails = [r for r in results if r.status != "PASS"]
    assert not fails, (
        f"{scenario_id} assertions failed: {[(r.check, r.detail) for r in fails]}"
    )


# ---------------------------------------------------------------------------
# Seed determinism: same scenario → same assertion outcomes
# ---------------------------------------------------------------------------

def test_fabric_scenario_deterministic():
    """Running the same fabric scenario twice yields identical assertion results."""
    spec_data = _get_spec("fabric-s2")

    def _run():
        ctx = build_run_context_from_spec(
            run_id="test-determinism",
            spec_data=spec_data,
        )
        fe = ctx.fabric_engine
        sc = fe._fabric_scenario
        n = int(sc.duration_s / sc.dt_s)
        for i in range(n):
            fe.step(sim_time_s=i * sc.dt_s, dt_s=sc.dt_s)
        return [(r.check, r.status, r.detail) for r in fe.evaluate_scenario_assertions()]

    run_a = _run()
    run_b = _run()
    assert run_a == run_b, "Assertion results differed between two runs of the same scenario"
