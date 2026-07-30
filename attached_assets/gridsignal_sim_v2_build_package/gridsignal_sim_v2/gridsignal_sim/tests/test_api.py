"""
tests/test_api.py — Step 6: FastAPI endpoint acceptance tests.

v2.5 TC-36 … TC-42.

REST tests (TC-36 … TC-41) use FastAPI's TestClient, which drives the
ASGI app — including the lifespan that creates the process-singleton
RunManager and WebSocketHub — in a background thread.  Each test wraps
the client in ``with TestClient(create_app()) as client:`` so every
test gets a fresh lifespan (fresh RunManager, fresh WebSocketHub) and
cannot interfere with siblings.

TC-42 (WebSocket) also uses TestClient.  httpx does not speak the
WebSocket protocol; TestClient's websocket_connect() does.

No test here constructs a SimClock, calls evaluate_tick(), or creates a
RunManager outside the lifespan — the invariant enforced in api/app.py.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.app import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _long_run_body(**overrides) -> dict:
    """A run body that takes long enough to still be active mid-test."""
    return {
        "job_id": "api-test-job",
        "node_count": 5,
        "end_sim_time": 14400.0,   # 4 simulated hours at max speed — won't finish during a test
        "playback_speed": 0.0,
        **overrides,
    }


# ---------------------------------------------------------------------------
# TC-36 — POST /runs returns 201 + run_id
# ---------------------------------------------------------------------------

def test_tc36_post_run_returns_201_and_run_id() -> None:
    """TC-36: POST /runs must return HTTP 201 and a body containing run_id."""
    with TestClient(create_app()) as client:
        resp = client.post("/runs", json=_long_run_body())
    assert resp.status_code == 201
    body = resp.json()
    assert "run_id" in body
    assert isinstance(body["run_id"], str)
    assert body["run_id"].startswith("run-")


# ---------------------------------------------------------------------------
# TC-37 — GET /runs lists the new run
# ---------------------------------------------------------------------------

def test_tc37_get_runs_lists_active_run() -> None:
    """TC-37: after POST /runs the run_id appears in GET /runs."""
    with TestClient(create_app()) as client:
        post_resp = client.post("/runs", json=_long_run_body())
        run_id = post_resp.json()["run_id"]

        list_resp = client.get("/runs")

    assert list_resp.status_code == 200
    assert run_id in list_resp.json()["run_ids"]


# ---------------------------------------------------------------------------
# TC-38 — GET /runs/{run_id} reports active=True while run is in flight
# ---------------------------------------------------------------------------

def test_tc38_get_run_status_active() -> None:
    """TC-38: a run that has not finished must report active=True."""
    with TestClient(create_app()) as client:
        run_id = client.post("/runs", json=_long_run_body()).json()["run_id"]
        status_resp = client.get(f"/runs/{run_id}")

    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["run_id"] == run_id
    assert body["active"] is True


# ---------------------------------------------------------------------------
# TC-39 — GET /runs/{run_id} returns 404 for unknown run_id
# ---------------------------------------------------------------------------

def test_tc39_get_run_status_not_found() -> None:
    """TC-39: a run_id that was never started must return HTTP 404."""
    with TestClient(create_app()) as client:
        resp = client.get("/runs/run-does-not-exist")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TC-40 — DELETE /runs/{run_id} cancels and removes the run
# ---------------------------------------------------------------------------

def test_tc40_delete_run_cancels_and_removes() -> None:
    """TC-40: DELETE /runs/{run_id} must return 204 and remove the run
    from GET /runs."""
    with TestClient(create_app()) as client:
        run_id = client.post("/runs", json=_long_run_body()).json()["run_id"]

        delete_resp = client.delete(f"/runs/{run_id}")
        assert delete_resp.status_code == 204

        list_resp = client.get("/runs")
        assert run_id not in list_resp.json()["run_ids"]


# ---------------------------------------------------------------------------
# TC-41 — DELETE /runs/{run_id} returns 404 for unknown run_id
# ---------------------------------------------------------------------------

def test_tc41_delete_run_not_found() -> None:
    """TC-41: DELETE on an unknown run_id must return HTTP 404."""
    with TestClient(create_app()) as client:
        resp = client.delete("/runs/run-does-not-exist")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TC-42 — POST /runs with invalid body returns 422
# ---------------------------------------------------------------------------

def test_tc42_post_run_invalid_body_returns_422() -> None:
    """TC-42: a request body missing the required job_id and node_count
    must be rejected with HTTP 422 (Pydantic validation error)."""
    with TestClient(create_app()) as client:
        resp = client.post("/runs", json={})   # missing job_id and node_count
    assert resp.status_code == 422
    # Pydantic provides field-level error detail
    errors = resp.json()["detail"]
    fields_with_errors = {e["loc"][-1] for e in errors}
    assert "job_id" in fields_with_errors
    assert "node_count" in fields_with_errors


# ---------------------------------------------------------------------------
# TC-43 — WebSocket subscriber receives at least one tick in correct format
# ---------------------------------------------------------------------------

def test_tc43_websocket_receives_tick_payload() -> None:
    """TC-43: a WebSocket subscriber connected to /ws/{run_id} must receive
    at least one tick payload containing the expected fields.

    The run is started at max speed (playback_speed=0) with a long
    end_sim_time so it is still active when the WebSocket connects.
    The test receives one message and validates its schema — no timing
    assumptions beyond "a tick arrives within the TestClient's implicit
    timeout".

    Invariant check: the payload must not contain wall_stamp_utc
    (that field is runtime-internal / persistence-only and must not be
    broadcast to subscribers per Design Spec Section 4.4).
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

    # wall_stamp_utc must NOT be broadcast (it's runtime-internal only)
    assert "wall_stamp_utc" not in data, (
        "wall_stamp_utc is a runtime-internal field and must not appear "
        "in WebSocket tick payloads"
    )
