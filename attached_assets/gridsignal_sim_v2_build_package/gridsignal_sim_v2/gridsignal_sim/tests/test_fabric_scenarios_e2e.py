"""
End-to-end tests for the fabric regression scenarios launched via the
Scenario Builder path (POST /runs with a regression-test-* scenario_id).

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
# Confirm fabric regression scenarios are discoverable via GET /scenarios
# ---------------------------------------------------------------------------

def test_all_fabric_scenarios_in_store():
    """All 8 fabric scenarios are seeded into the ScenarioStore."""
    store = build_seeded_store()
    ids = {sid for sid in store._data}
    fabric_ids = {
        "regression-test-healthy-training-baseline",
        "regression-test-checkpoint-storage-hotspot",
        "regression-test-clean-job-termination",
        "regression-test-control-path-latency-isolation",
        "regression-test-gray-link-failure",
        "regression-test-degraded-fabric-observability",
        "regression-test-slow-checkpoint",
        "regression-test-transceiver-degradation",
    }
    missing = fabric_ids - ids
    assert not missing, f"Missing scenario IDs: {missing}"


def test_fabric_scenario_names():
    """Each fabric scenario is clearly marked as a regression test."""
    store = build_seeded_store()
    for sid in (
        "regression-test-healthy-training-baseline",
        "regression-test-checkpoint-storage-hotspot",
        "regression-test-clean-job-termination",
        "regression-test-control-path-latency-isolation",
        "regression-test-gray-link-failure",
        "regression-test-degraded-fabric-observability",
        "regression-test-slow-checkpoint",
        "regression-test-transceiver-degradation",
    ):
        rec = store.get(sid)
        assert rec is not None
        assert rec.name.startswith("Regression test —"), (
            f"Expected a regression-test display name, got '{rec.name}'"
        )


# ---------------------------------------------------------------------------
# Healthy training baseline
# ---------------------------------------------------------------------------

def test_healthy_training_baseline_all_pass():
    """Baseline assertions all PASS: weight_load phase present, no corroboration,
    latency < 1000 ms."""
    ctx = _build_and_drive("regression-test-healthy-training-baseline")
    fe = ctx.fabric_engine
    assert fe.has_fabric_assertions
    results = fe.evaluate_scenario_assertions()
    assert results, "Expected at least one baseline assertion result"
    fails = [r for r in results if r.status != "PASS"]
    assert not fails, f"Baseline assertions failed: {[(r.check, r.detail) for r in fails]}"


# ---------------------------------------------------------------------------
# Checkpoint storage hotspot
# ---------------------------------------------------------------------------

def test_checkpoint_storage_hotspot_all_pass():
    """Hotspot assertions: checkpoint phase present, storage congestion >= 1 link,
    compute quiesces, corroboration fired, elephant flow present."""
    # This regression scenario needs a run long enough to reach checkpoint (20 s training
    # then checkpoint); drive 80 ticks × 0.25 s = 20 s at dt=0.25 s.
    spec_data = _get_spec("regression-test-checkpoint-storage-hotspot")
    ctx = build_run_context_from_spec(
        run_id="test-checkpoint-storage-hotspot",
        spec_data=spec_data,
    )
    fe = ctx.fabric_engine
    sc = fe._fabric_scenario
    assert sc is not None, "Checkpoint storage hotspot scenario not loaded"
    # Drive enough ticks to cover the checkpoint phase (scenario dt_s=0.25 s)
    n = max(int(sc.duration_s / sc.dt_s), 60)
    for i in range(n):
        fe.step(sim_time_s=i * sc.dt_s, dt_s=sc.dt_s)

    assert fe.has_fabric_assertions
    results = fe.evaluate_scenario_assertions()
    fails = [r for r in results if r.status != "PASS"]
    assert not fails, f"Hotspot assertions failed: {[(r.check, r.detail) for r in fails]}"


# ---------------------------------------------------------------------------
# Gray link failure (gray_loss_elevated)
# ---------------------------------------------------------------------------

def test_gray_link_failure_all_pass():
    """gray_loss_elevated assertion: loss on degraded link >= injected floor."""
    spec_data = _get_spec("regression-test-gray-link-failure")
    ctx = build_run_context_from_spec(
        run_id="test-gray-link-failure",
        spec_data=spec_data,
    )
    fe = ctx.fabric_engine
    sc = fe._fabric_scenario
    assert sc is not None, "Gray link failure scenario not loaded"
    # Drive all ticks (30 s / 0.25 s = 120 ticks)
    n = int(sc.duration_s / sc.dt_s)
    for i in range(n):
        fe.step(sim_time_s=i * sc.dt_s, dt_s=sc.dt_s)

    assert fe.has_fabric_assertions
    results = fe.evaluate_scenario_assertions()
    assert results, "No assertion results for gray link failure"
    fails = [r for r in results if r.status != "PASS"]
    assert not fails, f"Gray link failure assertions failed: {[(r.check, r.detail) for r in fails]}"


# ---------------------------------------------------------------------------
# Slow checkpoint (uses non-default traffic profile)
# ---------------------------------------------------------------------------

def test_slow_checkpoint_uses_correct_profile():
    """The slow-checkpoint scenario loads its dedicated traffic profile."""
    spec_data = _get_spec("regression-test-slow-checkpoint")
    ctx = build_run_context_from_spec(
        run_id="test-slow-checkpoint-profile",
        spec_data=spec_data,
    )
    fe = ctx.fabric_engine
    sc = fe._fabric_scenario
    assert sc is not None, "Slow checkpoint scenario not loaded"
    assert "slow_checkpoint" in sc.profiles_file, (
        f"Slow checkpoint should use its dedicated profile, got: {sc.profiles_file}"
    )


def test_slow_checkpoint_all_pass():
    """Slow checkpoint assertions: checkpoint phase, compute quiescence, corroboration."""
    spec_data = _get_spec("regression-test-slow-checkpoint")
    ctx = build_run_context_from_spec(
        run_id="test-slow-checkpoint",
        spec_data=spec_data,
    )
    fe = ctx.fabric_engine
    sc = fe._fabric_scenario
    assert sc is not None, "Slow checkpoint scenario not loaded"
    # Drive all ticks (100 s / 0.25 s = 400 ticks)
    n = int(sc.duration_s / sc.dt_s)
    for i in range(n):
        fe.step(sim_time_s=i * sc.dt_s, dt_s=sc.dt_s)

    assert fe.has_fabric_assertions
    results = fe.evaluate_scenario_assertions()
    fails = [r for r in results if r.status != "PASS"]
    assert not fails, f"Slow checkpoint assertions failed: {[(r.check, r.detail) for r in fails]}"


# ---------------------------------------------------------------------------
# Remaining fabric regression scenarios: quick smoke test (PASS verdict)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("scenario_id", [
    "regression-test-clean-job-termination",
    "regression-test-control-path-latency-isolation",
    "regression-test-degraded-fabric-observability",
    "regression-test-transceiver-degradation",
])
def test_smoke_scenario_all_pass(scenario_id):
    """The remaining regression scenario verdicts are PASS when run to completion."""
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
    spec_data = _get_spec("regression-test-checkpoint-storage-hotspot")

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
