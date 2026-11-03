"""API tests for the completed-run stranded summary and minute series."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from study_harness.executor import S11B_SUPERCLOUD_REPLAY_SCENARIO_ID
from study_harness.stranded import compute_stranded


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def _wait_for_completed(client: TestClient, run_id: str, timeout_s: float = 20.0):
    deadline = time.monotonic() + timeout_s
    manager = client.app.state.run_manager
    while time.monotonic() < deadline:
        completed = manager.get_completed(run_id)
        if completed is not None and manager.get_context(run_id) is None:
            return completed
        time.sleep(0.01)
    raise AssertionError(f"short run {run_id} did not complete within {timeout_s}s")


def _short_s11b_run(client: TestClient):
    response = client.post(
        "/runs",
        json={
            "scenario_id": S11B_SUPERCLOUD_REPLAY_SCENARIO_ID,
            "end_sim_time": 60.0,
            "playback_speed": 0.0,
            "run_seed": 1729,
        },
    )
    assert response.status_code == 201, response.text
    run_id = response.json()["run_id"]
    return run_id, _wait_for_completed(client, run_id)


def test_tc_str_09_rest_endpoint_matches_shared_compute_stranded_on_short_run(client):
    """The REST response uses the shared helper on a real 60-second S11b run."""
    run_id, completed = _short_s11b_run(client)
    response = client.get(f"/runs/{run_id}/stranded?reserve_policy=fixed_3mw")

    assert response.status_code == 200, response.text
    actual = response.json()
    expected = compute_stranded(
        completed.tick_dicts,
        p_avail_mw=60.0,
        reserve_policy="fixed_3mw",
        tick_seconds=5.0,
    )
    expected["available"] = True
    assert actual == expected
    assert actual["series"]
    assert actual["p_avail_mw"] == 60.0
    assert actual["reserve_policy"] == "fixed_3mw"


class _ActiveTickSink:
    def __init__(self, rows):
        self.rows = rows

    async def get_tick_dicts(self, run_id):
        return self.rows


class _ActiveRunManager:
    def __init__(self, context):
        self.context = context

    def get_context(self, run_id):
        return self.context

    def get_completed(self, run_id):
        return None


def test_active_stranded_endpoint_returns_live_snapshot_from_run_sink(client):
    """Active snapshots use the run's configured cap and shared helper."""
    rows = [
        {
            "sim_time_seconds": 5.0 * tick,
            "p_total_mw": 10.0 + tick,
            "requested_demand_mw": 20.0 + tick,
            "bess_output_mw": 0.0,
            "p_unserved_mw": 0.0,
        }
        for tick in range(12)
    ]
    context = SimpleNamespace(
        sink=_ActiveTickSink(rows),
        sim_state=SimpleNamespace(
            site=SimpleNamespace(grid_import_limit_mw=60.0),
        ),
    )
    client.app.state.run_manager = _ActiveRunManager(context)

    response = client.get(
        "/runs/active-run/stranded?reserve_policy=fixed_3mw"
    )

    assert response.status_code == 200, response.text
    expected = compute_stranded(
        rows,
        p_avail_mw=60.0,
        reserve_policy="fixed_3mw",
        tick_seconds=5.0,
    )
    expected["available"] = True
    expected["series"][0]["requested_demand_max_mw"] = 31.0
    assert response.json() == expected
    assert response.json()["series"]


class _CompletedOnlyManager:
    def __init__(self, completed=None):
        self.completed = completed

    def get_context(self, run_id):
        return None

    def get_completed(self, run_id):
        return self.completed


class _ScenarioRecordStore:
    def __init__(self, cap):
        self.record = SimpleNamespace(
            spec_json=json.dumps({"grid_import_limit_mw": cap})
        )

    def get(self, scenario_id):
        return self.record


def _install_completed_fixture(client: TestClient, cap):
    rows = [
        {
            "sim_time_seconds": 5.0 * tick,
            "p_total_mw": 10.0 + tick,
            "bess_output_mw": 0.0,
            "p_unserved_mw": 0.0,
        }
        for tick in range(12)
    ]
    client.app.state.run_manager = _CompletedOnlyManager(
        SimpleNamespace(scenario_id="fixture", tick_dicts=rows)
    )
    client.app.state.scenario_store = _ScenarioRecordStore(cap)


def test_tc_str_05_scenario_without_cap_returns_unavailable_without_numeric_values(client):
    _install_completed_fixture(client, None)

    response = client.get("/runs/fixture-run/stranded")

    assert response.status_code == 200
    assert response.json() == {
        "available": False,
        "reason": "no grid_import_limit_mw; no available-capacity basis defined",
    }
    assert not any(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in response.json().values()
    )


def test_invalid_reserve_policy_returns_422(client):
    _install_completed_fixture(client, 60.0)

    response = client.get("/runs/fixture-run/stranded?reserve_policy=arbitrary")

    assert response.status_code == 422


def test_tc_str_07_response_contains_no_forbidden_terms(client):
    run_id, _ = _short_s11b_run(client)
    response = client.get(f"/runs/{run_id}/stranded?reserve_policy=fixed_3mw")

    assert response.status_code == 200, response.text
    serialized = json.dumps(response.json()).casefold()
    for forbidden in ("usd", "$", "gpu", "rsc"):
        assert forbidden not in serialized
