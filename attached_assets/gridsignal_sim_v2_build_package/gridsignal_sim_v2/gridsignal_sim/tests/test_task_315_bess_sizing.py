"""Task 315 — scenario detail contract for operator BESS sizing."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app


@pytest.fixture
def client(monkeypatch):
    # The JSON scenario seeder resolves config/scenarios relative to this
    # backend directory, regardless of where pytest was invoked.
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    with TestClient(create_app()) as test_client:
        yield test_client


def test_demo_islanded_ramp_exposes_50mw_50mwh_bess_hints(client):
    response = client.get("/scenarios/demo-islanded-ramp")

    assert response.status_code == 200
    spec = response.json()["spec"]
    assert spec["ui_bess_rated_mw"] == pytest.approx(50.0)
    assert spec["ui_bess_usable_mwh"] == pytest.approx(50.0)


def test_demo_20mw_leaves_bess_hints_unset_for_ui_default(client):
    response = client.get("/scenarios/demo-20mw")

    assert response.status_code == 200
    spec = response.json()["spec"]
    assert spec["ui_bess_rated_mw"] is None
    assert spec["ui_bess_usable_mwh"] is None