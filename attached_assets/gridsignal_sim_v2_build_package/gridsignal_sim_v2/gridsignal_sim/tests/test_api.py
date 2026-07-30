"""
tests/test_api.py — Step 6: FastAPI endpoint acceptance tests.

These tests verify the simulator's HTTP/WebSocket API wiring added in
Step 6.  They are NOT v2.5 Addendum A acceptance tests; the TC-xx labels
that appeared in the previous draft were incorrect (see note below).

NOTE ON TC NUMBERING
--------------------
v2.5 Addendum A §16.8 / §16.9 test IDs TC-36 through TC-43 are reserved
acceptance criteria against the full production spec surface:

  TC-34  restart preserves 15-minute dedupe window (§17.1)    → deferred Step 10
  TC-35  restart preserves grace-period elapsed time           → DONE (Step 5)
  TC-36  restart yields to measured state, not reconstructed   → deferred Step 10
  TC-41  curtailment ladder ordering mandatory                 → deferred Step 9
  TC-42  C/D tiers never execute autonomously                  → deferred Step 9
  TC-43  degraded forecasts never curtail autonomously         → deferred Step 9

None of those behaviours (dedupe window, grace-period reconciliation,
curtailment ladder) exist in the codebase yet.  Applying those IDs to the
HTTP CRUD tests below would have marked them covered in Step 17's
traceability sweep.  The tests are renamed to describe what they actually
verify, and the deferred cases are noted above so Step 9 / Step 10 know
what they must close.

REST tests use FastAPI's TestClient (sync, handles lifespan correctly)
so every test gets a fresh RunManager and WebSocketHub and cannot
interfere with siblings.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.app import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _long_run_body(**overrides) -> dict:
    """A run body guaranteed to still be active during any realistic test.

    ``playback_speed=0`` is the max-speed sentinel (wall_clock_sleep = 0 s).
    At that speed 14 400 simulated seconds requires only 2 880 ticks and can
    finish in milliseconds — fast enough to be gone before a follow-up GET.
    ``end_sim_time=1e15`` is astronomically unreachable (2e14 ticks) so the
    run is always in-flight when the test inspects it.
    """
    return {
        "job_id": "api-test-job",
        "node_count": 5,
        "end_sim_time": 1e15,      # never reachable during a test
        "playback_speed": 0.0,     # max speed so the WS test gets a tick fast
        **overrides,
    }


# ---------------------------------------------------------------------------
# POST /runs returns 201 + run_id
# ---------------------------------------------------------------------------

def test_post_run_returns_201_and_run_id() -> None:
    """POST /runs must return HTTP 201 and a body containing a run_id string."""
    with TestClient(create_app()) as client:
        resp = client.post("/runs", json=_long_run_body())
    assert resp.status_code == 201
    body = resp.json()
    assert "run_id" in body
    assert isinstance(body["run_id"], str)
    assert body["run_id"].startswith("run-")


# ---------------------------------------------------------------------------
# GET /runs lists the new run
# ---------------------------------------------------------------------------

def test_get_runs_lists_active_run() -> None:
    """After POST /runs the run_id must appear in GET /runs."""
    with TestClient(create_app()) as client:
        post_resp = client.post("/runs", json=_long_run_body())
        run_id = post_resp.json()["run_id"]

        list_resp = client.get("/runs")

    assert list_resp.status_code == 200
    assert run_id in list_resp.json()["run_ids"]


# ---------------------------------------------------------------------------
# GET /runs/{run_id} reports active=True while run is in flight
# ---------------------------------------------------------------------------

def test_get_run_status_active() -> None:
    """A run that has not finished must report active=True."""
    with TestClient(create_app()) as client:
        run_id = client.post("/runs", json=_long_run_body()).json()["run_id"]
        status_resp = client.get(f"/runs/{run_id}")

    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["run_id"] == run_id
    assert body["active"] is True


# ---------------------------------------------------------------------------
# GET /runs/{run_id} returns 404 for unknown run_id
# ---------------------------------------------------------------------------

def test_get_run_status_not_found() -> None:
    """A run_id that was never started must return HTTP 404."""
    with TestClient(create_app()) as client:
        resp = client.get("/runs/run-does-not-exist")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /runs/{run_id} cancels and removes the run
# ---------------------------------------------------------------------------

def test_delete_run_cancels_and_removes() -> None:
    """DELETE /runs/{run_id} must return 204 and remove the run
    from GET /runs."""
    with TestClient(create_app()) as client:
        run_id = client.post("/runs", json=_long_run_body()).json()["run_id"]

        delete_resp = client.delete(f"/runs/{run_id}")
        assert delete_resp.status_code == 204

        list_resp = client.get("/runs")
        assert run_id not in list_resp.json()["run_ids"]


# ---------------------------------------------------------------------------
# DELETE /runs/{run_id} returns 404 for unknown run_id
# ---------------------------------------------------------------------------

def test_delete_run_not_found() -> None:
    """DELETE on an unknown run_id must return HTTP 404."""
    with TestClient(create_app()) as client:
        resp = client.delete("/runs/run-does-not-exist")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /runs with invalid body returns 422
# ---------------------------------------------------------------------------

def test_post_run_invalid_body_returns_422() -> None:
    """A request body missing required fields must be rejected with 422.

    Pydantic validation must name both missing fields (job_id and
    node_count) in the error detail."""
    with TestClient(create_app()) as client:
        resp = client.post("/runs", json={})   # missing job_id and node_count
    assert resp.status_code == 422
    errors = resp.json()["detail"]
    fields_with_errors = {e["loc"][-1] for e in errors}
    assert "job_id" in fields_with_errors
    assert "node_count" in fields_with_errors


# ---------------------------------------------------------------------------
# WebSocket subscriber receives at least one tick in correct format
# ---------------------------------------------------------------------------

def test_websocket_subscriber_receives_tick_payload() -> None:
    """A WebSocket subscriber connected to /ws/{run_id} must receive at
    least one tick payload containing the expected fields.

    The run is started at max speed (playback_speed=0) with a long
    end_sim_time so it is still active when the WebSocket connects.

    Invariant check: wall_stamp_utc must NOT appear in the broadcast
    payload — it is a runtime-internal / persistence-only field and is
    explicitly excluded from WebSocket output (Design Spec §4.4).
    """
    with TestClient(create_app()) as client:
        run_id = client.post("/runs", json=_long_run_body()).json()["run_id"]

        with client.websocket_connect(f"/ws/{run_id}") as ws:
            data = ws.receive_json()

    # Required fields from _tick_result_to_dict in runtime/run_manager.py
    required = {
        "run_id", "tick_index", "sim_time_seconds",
        "p_compute_mw", "p_cooling_mw", "p_total_mw", "net_demand_mw",
        "turbine_output_mw", "bess_output_mw", "bess_soc_fraction",
        "confidence_lower_mw", "confidence_upper_mw",
        "data_quality_tags", "insufficient_reserve_alert", "checkpoint_states",
    }
    missing = required - data.keys()
    assert not missing, f"Tick payload missing keys: {missing}"
    assert data["run_id"] == run_id
    assert isinstance(data["tick_index"], int)
    assert isinstance(data["p_total_mw"], float)

    # wall_stamp_utc must NOT be broadcast (runtime-internal only)
    assert "wall_stamp_utc" not in data, (
        "wall_stamp_utc is a runtime-internal field and must not appear "
        "in WebSocket tick payloads"
    )
