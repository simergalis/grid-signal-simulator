"""
tests/test_step16_wiring.py — W1/W2 endpoint acceptance tests.

Verifies the six advisory/monitoring endpoints wired in W1 (run-loop
agent/telemetry/thermal wiring) and W2 (advisory, procurement,
network-telemetry, thermal, energy-summary REST surfaces).

Test count: 13  (8 sync TestClient + 5 async completed-run)

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

from api.app import create_app
from api.routes.scenarios import build_seeded_store
from runtime.run_manager import RunManager, WebSocketHub
from runtime.scenario_factory import build_run_context


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
