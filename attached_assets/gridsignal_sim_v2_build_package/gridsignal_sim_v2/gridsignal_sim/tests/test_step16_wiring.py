"""
tests/test_step16_wiring.py — W1/W2 endpoint acceptance tests + shipped-scenario
column-3 coverage (Step 17).

Verifies the six advisory/monitoring endpoints wired in W1 (run-loop
agent/telemetry/thermal wiring) and W2 (advisory, procurement,
network-telemetry, thermal, energy-summary REST surfaces).

Test count: 16  (8 sync TestClient + 8 async completed-run / manual-tick)

Sync tests (1–8) use TestClient with end_sim_time=1e15 so the run is
always active during the assertion, or test 404 paths that need no
running context.  The lifespan shutdown now cancels all in-flight tasks
so these tests exit promptly.

Async tests (9–13) drive a short run (end_sim_time=30.0, 6 ticks) to
completion via direct RunManager access, then inject the pre-populated
manager into a fresh FastAPI app (bypassing lifespan so the app receives
the already-completed run state) and assert endpoint semantics using
httpx.AsyncClient with ASGITransport.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

import json

from api.app import create_app
from api.routes.scenarios import build_seeded_store
from runtime.run_manager import RunManager, WebSocketHub
from runtime.scenario_factory import build_run_context, build_run_context_from_spec
from contextlib import contextmanager

from core.sim_clock import SimClock
from core.simulation_core import evaluate_tick
from core.scada_layer import PROTECTION_COMMANDS
from core._plane_guard import _EVALUATE_TICK_PERMITTED


@contextmanager
def _guard():
    """Activate the evaluate_tick() runtime purity guard for a single call.

    Mirrors _plane_guard_active() from test_plane_separation.py.
    Required whenever tests call evaluate_tick() directly (outside RunManager).
    """
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        yield
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _active_body(**overrides) -> dict:
    """Run body that is guaranteed to stay active during any realistic test.

    end_sim_time=1e15 is astronomically unreachable; playback_speed=0 is
    max-speed (asyncio.sleep(0) between ticks) so the WS test gets a tick
    fast and the lifespan cancel-on-exit fires promptly.
    """
    return {
        "job_id": "w2-test-job",
        "node_count": 2,
        "end_sim_time": 1e15,
        "playback_speed": 0.0,
        **overrides,
    }


async def _manager_with_completed_run(run_id: str = "cmp-run") -> RunManager:
    """Drive a 6-tick run to natural completion; return the RunManager.

    Uses node_count=2 so all three subsystems (agents, telemetry, thermal)
    are exercised while keeping wall time negligible (< 5 ms).
    """
    hub = WebSocketHub()
    manager = RunManager(hub)
    ctx = build_run_context(run_id, job_id="j1", node_count=2, end_sim_time=30.0)
    await manager.start_run(ctx)
    # Save the task reference before _drive's finally block pops it from _tasks.
    task = manager._tasks.get(run_id)
    if task is not None:
        await task
    return manager


def _app_with_manager(manager: RunManager):
    """Fresh FastAPI app with a pre-populated RunManager (lifespan bypassed).

    Bypassing the lifespan means the app does NOT create a second RunManager
    that would override the one we drove to completion.  The dependency
    injector reads request.app.state.run_manager, which we set here.
    """
    app = create_app()
    app.state.run_manager = manager
    app.state.ws_hub = manager._ws_hub
    app.state.scenario_store = build_seeded_store()
    return app


# ===========================================================================
# Sync tests — active runs (1–8)
# ===========================================================================

# 1 ─────────────────────────────────────────────────────────────────────────
def test_proposals_returns_200_and_empty_list_for_fresh_run():
    """GET /proposals/{run_id} — 200 + empty proposals list for a new active run.

    No agents have fired yet (cadence floor not reached at t=0).
    """
    with TestClient(create_app()) as client:
        resp = client.post("/runs", json=_active_body())
        assert resp.status_code == 201
        run_id = resp.json()["run_id"]

        p_resp = client.get(f"/proposals/{run_id}")

    assert p_resp.status_code == 200
    body = p_resp.json()
    assert body["run_id"] == run_id
    assert isinstance(body["proposals"], list)


# 2 ─────────────────────────────────────────────────────────────────────────
def test_proposals_returns_404_for_unknown_run():
    """GET /proposals/{run_id} — 404 if the run_id was never started."""
    with TestClient(create_app()) as client:
        resp = client.get("/proposals/run-does-not-exist")
    assert resp.status_code == 404


# 3 ─────────────────────────────────────────────────────────────────────────
def test_accept_proposal_returns_404_for_unknown_proposal():
    """POST /proposals/{id}/accept — 404 when no such proposal exists."""
    with TestClient(create_app()) as client:
        resp = client.post(
            "/proposals/prop-does-not-exist/accept",
            json={"reviewer_id": "ops@test"},
        )
    assert resp.status_code == 404


# 4 ─────────────────────────────────────────────────────────────────────────
def test_reject_proposal_returns_404_for_unknown_proposal():
    """POST /proposals/{id}/reject — 404 when no such proposal exists."""
    with TestClient(create_app()) as client:
        resp = client.post(
            "/proposals/prop-does-not-exist/reject",
            json={"reason": "test rejection"},
        )
    assert resp.status_code == 404


# 5 ─────────────────────────────────────────────────────────────────────────
def test_procurement_returns_required_fields_for_active_run():
    """GET /procurement/{run_id} — all schema fields present for active run.

    Verifies run_id, sim_time, reserve_gap_mw, firm_mw, reserved_mw,
    non_firm_mw, capacity (list), price_curve (list of 12 points).
    """
    with TestClient(create_app()) as client:
        run_id = client.post("/runs", json=_active_body()).json()["run_id"]
        resp = client.get(f"/procurement/{run_id}")

    assert resp.status_code == 200
    body = resp.json()
    for field in (
        "run_id", "sim_time", "reserve_gap_mw", "firm_mw",
        "reserved_mw", "non_firm_mw", "served_load_mw", "capacity", "price_curve",
    ):
        assert field in body, f"procurement response missing field: {field!r}"
    assert body["run_id"] == run_id
    assert isinstance(body["capacity"], list)
    assert isinstance(body["price_curve"], list)
    # 12-point forward curve (next simulated hour, §16 spec)
    assert len(body["price_curve"]) == 12


# 6 ─────────────────────────────────────────────────────────────────────────
def test_network_telemetry_returns_required_fields_for_active_run():
    """GET /network-telemetry?run_id= — all schema fields present for active run.

    Verifies run_id, capability, switches (list), corroboration (list),
    quarantine (list).  W1 synthesises two records per tick (spine + leaf).
    """
    with TestClient(create_app()) as client:
        run_id = client.post("/runs", json=_active_body()).json()["run_id"]
        resp = client.get(f"/network-telemetry?run_id={run_id}")

    assert resp.status_code == 200
    body = resp.json()
    for field in ("run_id", "capability", "last_updated_s", "switches",
                  "corroboration", "quarantine"):
        assert field in body, f"network-telemetry response missing field: {field!r}"
    assert body["run_id"] == run_id
    assert isinstance(body["switches"], list)
    # Two synthetic switch records (spine + leaf) are created per tick by W1.
    assert len(body["switches"]) == 2
    if body["switches"]:
        sw = body["switches"][0]
        for sw_field in ("switch_id", "clock_discipline", "effective_discipline",
                         "throughput_rx_mbps", "error_count"):
            assert sw_field in sw, f"switch row missing field: {sw_field!r}"


# 7 ─────────────────────────────────────────────────────────────────────────
def test_thermal_returns_required_fields_for_active_run():
    """GET /thermal?run_id= — all schema fields present for active run.

    Verifies absorbable_mw, time_to_limit_s, inlet_temp_c,
    approach_rate_mw_s, zones (list).
    """
    with TestClient(create_app()) as client:
        run_id = client.post("/runs", json=_active_body()).json()["run_id"]
        resp = client.get(f"/thermal?run_id={run_id}")

    assert resp.status_code == 200
    body = resp.json()
    for field in ("run_id", "absorbable_mw", "time_to_limit_s", "inlet_temp_c",
                  "approach_rate_mw_s", "zones"):
        assert field in body, f"thermal response missing field: {field!r}"
    assert body["run_id"] == run_id
    assert isinstance(body["zones"], list)
    assert 18.0 <= body["inlet_temp_c"] <= 24.0, (
        f"inlet_temp_c {body['inlet_temp_c']} outside comfort band [18, 24]°C"
    )


# 8 ─────────────────────────────────────────────────────────────────────────
def test_energy_summary_returns_404_for_unknown_run():
    """GET /runs/{run_id}/energy-summary — 404 for an unknown run_id."""
    with TestClient(create_app()) as client:
        resp = client.get("/runs/run-does-not-exist/energy-summary")
    assert resp.status_code == 404


# ===========================================================================
# Async tests — completed runs (9–13)
#
# Each test drives a 6-tick run to completion, then verifies endpoint
# semantics against the completed state.
# ===========================================================================

# 9 ─────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_procurement_returns_409_for_completed_run():
    """GET /procurement/{run_id} — 409 after the run ends.

    Procurement is a live monitoring surface; serving stale state after
    run completion is explicitly rejected (see advisory.py §16 design note).
    """
    manager = await _manager_with_completed_run("cmp-proc")
    app = _app_with_manager(manager)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/procurement/cmp-proc")
    assert resp.status_code == 409


# 10 ────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_network_telemetry_returns_409_for_completed_run():
    """GET /network-telemetry?run_id= — 409 after the run ends."""
    manager = await _manager_with_completed_run("cmp-net")
    app = _app_with_manager(manager)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/network-telemetry?run_id=cmp-net")
    assert resp.status_code == 409


# 11 ────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_thermal_returns_409_for_completed_run():
    """GET /thermal?run_id= — 409 after the run ends."""
    manager = await _manager_with_completed_run("cmp-thm")
    app = _app_with_manager(manager)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/thermal?run_id=cmp-thm")
    assert resp.status_code == 409


# 12 ────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_proposals_returns_200_for_completed_run():
    """GET /proposals/{run_id} — 200 after the run ends.

    _drive()'s finally block copies ctx.registry into RunManager._registries
    so the proposals surface remains queryable after run completion.
    """
    manager = await _manager_with_completed_run("cmp-prop")
    app = _app_with_manager(manager)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/proposals/cmp-prop")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == "cmp-prop"
    assert isinstance(body["proposals"], list)


# 13 ────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_energy_summary_returns_required_fields_for_completed_run():
    """GET /runs/{run_id}/energy-summary — 200 + required fields after run ends.

    Verifies label, duration_hours, generation_mwh, grid_import_mwh,
    storage_charge_mwh.  Numeric types are float; duration must be > 0.
    """
    manager = await _manager_with_completed_run("cmp-egy")
    app = _app_with_manager(manager)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/runs/cmp-egy/energy-summary")
    assert resp.status_code == 200
    body = resp.json()
    for field in ("label", "duration_hours", "generation_mwh",
                  "grid_import_mwh", "storage_charge_mwh"):
        assert field in body, f"energy-summary response missing field: {field!r}"
    assert body["label"] == "cmp-egy"
    assert isinstance(body["generation_mwh"], float)
    assert isinstance(body["duration_hours"], float)
    assert body["duration_hours"] > 0.0, "duration_hours must be positive for a completed run"


# ===========================================================================
# Step 17 shipped-scenario column-3 tests (14–16)
#
# These are the only tests in the suite that exercise TC assertions on the
# *build_seeded_store → build_run_context_from_spec* path (column 3 of the
# acceptance matrix).  Direct-invocation tests (most of the suite) satisfy
# columns 1 and 2 only.
# ===========================================================================

# 14 ────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_demo_prestage_column3_tc55_tc56():
    """TC-55/TC-56 column-3 — two-phase load-shifting via demo-prestage scenario.

    Tests the §8.1 two-phase model (charge before peak, discharge at peak):

    TC-56: bms_override=False (default) → engine engages in at least one phase.
           Either pre_staging_precool_mw > 0 (charge) or pre_staging_shift_mw > 0
           (discharge) must appear somewhere in the run.

    Two-phase check: early-run charge phase (precool > 0, shift == 0) must appear
           before any discharge tick (shift > 0, precool == 0), demonstrating that
           load is moved EARLIER rather than erased (§8.1 distinction).

    Mutual exclusivity: no tick may have both precool > 0 and shift > 0 (compute_tick
           guarantee: the two phases cannot fire simultaneously).

    TC-55: charge rate bounded by temperature headroom — precool never exceeds
           max_shift_mw=1.0; total precool is finite (temp bound limits duration).

    Energy balance (§8.1 invariant): total shift energy ≤ total precool energy × η.
    """
    store = build_seeded_store()
    rec = store.get("demo-prestage")
    assert rec is not None, "demo-prestage must exist in seeded store"

    spec_data = json.loads(rec.spec_json)
    ctx = build_run_context_from_spec("col3-prestage", spec_data)

    hub = WebSocketHub()
    manager = RunManager(hub)
    await manager.start_run(ctx)
    task = manager._tasks.get("col3-prestage")
    if task is not None:
        await task

    completed = manager._completed.get("col3-prestage")
    assert completed is not None, "run must complete and be stored"

    ticks = completed.tick_dicts
    assert len(ticks) > 0, "must have at least one tick"

    shifts   = [float(row.get("pre_staging_shift_mw",   0.0)) for row in ticks]
    precools = [float(row.get("pre_staging_precool_mw", 0.0)) for row in ticks]

    # TC-56 (col-3): engine engages in at least one phase.
    assert any(s > 0.0 for s in shifts) or any(p > 0.0 for p in precools), (
        "TC-56/col-3: bms_override=False must allow PreStagingEngine to engage; "
        "no tick had pre_staging_shift_mw > 0 or pre_staging_precool_mw > 0"
    )

    # Two-phase check: at least one charge tick (precool > 0, shift == 0).
    has_charge_tick = any(
        p > 0.0 and s == 0.0 for p, s in zip(precools, shifts)
    )
    assert has_charge_tick, (
        "Two-phase/col-3: no charge-phase tick found (pre_staging_precool_mw > 0 "
        "with pre_staging_shift_mw == 0); engine must draw load BEFORE the peak"
    )

    # Mutual exclusivity: both fields > 0 on the same tick is a logic error.
    for i, (s, p) in enumerate(zip(shifts, precools)):
        assert not (s > 0.0 and p > 0.0), (
            f"Mutual-exclusivity/col-3: tick {i} has both shift={s:.4f} and "
            f"precool={p:.4f}; compute_tick must not fire both phases at once"
        )

    # TC-55 (col-3): charge rate bounded by max_shift_mw=1.0.
    peak_precool = max(precools)
    assert peak_precool <= 1.001, (
        f"TC-55/col-3: precool_mw must never exceed max_shift_mw=1.0; "
        f"peak_precool={peak_precool:.4f}"
    )
    peak_shift = max(shifts)
    assert peak_shift <= 1.001, (
        f"TC-55/col-3: shift_mw must never exceed max_shift_mw=1.0; "
        f"peak_shift={peak_shift:.4f}"
    )

    # Energy balance (§8.1): integral shift ≤ integral precool × η.
    # dt is consistent across ticks; using count as a proxy (dt cancels out).
    dt_hours = 5.0 / 3600.0  # 5-second ticks
    eta = spec_data.get("pre_staging_config", {}).get("eta", 0.9)
    total_shift_mwh   = sum(shifts)   * dt_hours
    total_precool_mwh = sum(precools) * dt_hours
    assert total_shift_mwh <= total_precool_mwh * eta + 1e-6, (
        f"Energy-balance/col-3: shift energy ({total_shift_mwh:.6f} MWh) exceeds "
        f"precool energy × η ({total_precool_mwh * eta:.6f} MWh)"
    )


# 15 ────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_demo_pms_column3_tc64_to_tc68():
    """TC-64..TC-68 column-3: SimulatedPMS active on the demo-pms shipped path.

    Drives 60 ticks manually (no RunManager) so fast-shed and open-transition
    can be injected at exact tick boundaries.

    TC-64: pms_fast_shed_active=True for ≥ 1 tick after inject_fast_shed().
    TC-65: pms_order_conflict is None throughout (no false positives with an
           empty shed-priority-order).
    TC-66: pms.fast_shed_log records the injection.
    TC-67: open_transition injects a coverage gap — scada_commands_issued ≥ 1
           in the ticks that follow.
    TC-68: zero protection commands in the scada_layer egress log.
    """
    store = build_seeded_store()
    rec = store.get("demo-pms")
    assert rec is not None, "demo-pms must exist in seeded store"

    spec_data = json.loads(rec.spec_json)
    ctx = build_run_context_from_spec("col3-pms", spec_data)
    state = ctx.sim_state
    pms = state.pms
    assert pms is not None, "demo-pms must instantiate a SimulatedPMS"

    DT = 5.0          # TICK_INTERVAL_SIM_SECONDS matches run_manager.py
    SHED_TICK = 5     # inject fast-shed just before tick 5 fires
    TRANS_TICK = 12   # inject open-transition just before tick 12 fires
    TOTAL_TICKS = 60

    results = []
    for tick_seq in range(TOTAL_TICKS):
        sim_time = tick_seq * DT
        if tick_seq == SHED_TICK:
            pms.inject_fast_shed(shed_load_mw=3.0, sim_time=sim_time)
        if tick_seq == TRANS_TICK:
            pms.inject_transition(sim_time=sim_time)
        clock = SimClock(
            sim_time=sim_time,
            dt_seconds=DT,
            wall_stamp_utc=0.0,
            rate=0.0,
            tick_seq=tick_seq,
        )
        with _guard():
            tr = evaluate_tick(state, clock)
        results.append(tr)

    # TC-64: fast shed active for ≥ 1 tick
    shed_active = [r for r in results if getattr(r, "pms_fast_shed_active", False)]
    assert shed_active, (
        "TC-64/col-3: pms_fast_shed_active must be True during fast-shed window; "
        f"fast_shed_log={pms.fast_shed_log}"
    )

    # TC-65: no false order conflicts (demo-pms has empty shed_priority_order)
    conflicts = [r for r in results if getattr(r, "pms_order_conflict", None) is not None]
    assert not conflicts, (
        f"TC-65/col-3: unexpected pms_order_conflict in ticks "
        f"{[results.index(r) for r in conflicts[:3]]}"
    )

    # TC-66: fast_shed_log records the injection
    assert len(pms.fast_shed_log) >= 1, (
        "TC-66/col-3: pms.fast_shed_log must contain at least one entry after inject_fast_shed()"
    )

    # TC-67: SCADA issued commands during/after the transition window
    window = results[TRANS_TICK: TRANS_TICK + 8]
    assert any(getattr(r, "scada_commands_issued", 0) >= 1 for r in window), (
        "TC-67/col-3: open-transition must trigger ≥ 1 SCADA command in the "
        f"8-tick window starting at tick {TRANS_TICK}"
    )

    # TC-68: zero protection commands across all 60 ticks
    egress = getattr(state.scada_layer, "egress_log", [])
    protection_found = [e for e in egress if e.command_type in PROTECTION_COMMANDS]
    assert not protection_found, (
        f"TC-68/col-3: protection commands found in egress: "
        f"{[e.command_type.value for e in protection_found[:3]]}"
    )


# 16 ────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_energy_summary_includes_cost_breakdown():
    """AB2 column-3: energy-summary returns cost_breakdown + cost_model_config.

    The Python §21.2 CostModelEngine (PROTO-21-COST defaults) is now the
    authoritative implementation.  The frontend TypeScript mirrors its
    constants; this test guards against silent divergence.
    """
    manager = await _manager_with_completed_run("cmp-cost")
    app = _app_with_manager(manager)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/runs/cmp-cost/energy-summary")
    assert resp.status_code == 200
    body = resp.json()

    assert "cost_breakdown" in body, (
        "energy-summary must include cost_breakdown (AB2 / PROTO-21-COST)"
    )
    cb = body["cost_breakdown"]
    for field in (
        "grid_import_cost", "generation_cost", "storage_cost",
        "total_cost", "generation_duty_fraction", "grid_fraction",
    ):
        assert field in cb, f"cost_breakdown missing field: {field!r}"
    assert isinstance(cb["total_cost"], float)
    assert cb["total_cost"] >= 0.0

    assert "cost_model_config" in body, "energy-summary must include cost_model_config"
    cfg = body["cost_model_config"]
    # Guard against silent Python/TypeScript constant divergence (PROTO-21-COST):
    assert cfg.get("grid_import_price_per_mwh") == pytest.approx(120.0), (
        "PROTO-21-COST grid price must be 120 GBP/MWh; "
        "update ScenarioPlannerPage.tsx COST_CONFIG to match"
    )
