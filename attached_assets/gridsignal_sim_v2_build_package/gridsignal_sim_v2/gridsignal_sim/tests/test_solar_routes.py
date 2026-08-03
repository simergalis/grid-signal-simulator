"""
tests/test_solar_routes.py — Route-level tests for the three solar API endpoints.

These tests exercise the FastAPI wiring end-to-end via TestClient with the full
app lifespan, so the SolarSim singleton is created in _lifespan() exactly as it
is in production.

All five tests share a single TestClient (module-scoped fixture) to avoid the
asyncpg pool-teardown race that occurs when multiple TestClient instances are
created sequentially in one pytest session.  The same pattern is safe here
because the solar endpoints do not mutate shared RunManager state.

Covers:
  GET  /api/solar/state   — JSON shape (TC-SOL-R1)
  GET  /api/solar/config  — site-only subset (TC-SOL-R2)
  POST /api/solar/inject/poi      — zeroes p_renewable_mw (TC-SOL-R3)
  POST /api/solar/inject/unknown  — returns 400 (TC-SOL-R4)
  GET  /solar-console     — 200 + text/html content-type (TC-SOL-R5)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.app import create_app


# ---------------------------------------------------------------------------
# Shared client — one lifespan for the whole module avoids the asyncpg
# pool-teardown race that fires when multiple TestClient instances are created
# sequentially (same pattern as test_api.py in this suite).
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def solar_client():
    """Yield a TestClient whose lifespan spans the entire module."""
    with TestClient(create_app()) as client:
        yield client


# ---------------------------------------------------------------------------
# TC-SOL-R1  /api/solar/state returns expected JSON shape
# ---------------------------------------------------------------------------

def test_solar_state_returns_expected_json_shape(solar_client: TestClient) -> None:
    """GET /api/solar/state must return HTTP 200 with all top-level keys
    required by the Renewable Supply Console (spec §7.2).

    Top-level keys required: site, atmosphere, power, fleet, blocks,
    exposure, reserve, log.

    Sub-key spot-checks verify the critical scalars rather than every field,
    so the test stays meaningful without mirroring the full snapshot contract.
    """
    resp = solar_client.get("/api/solar/state")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()

    # Required top-level shape keys (spec §7.2 / solar.py snapshot())
    required_keys = {"site", "atmosphere", "power", "fleet", "blocks", "exposure", "reserve", "log"}
    missing = required_keys - body.keys()
    assert not missing, f"/api/solar/state missing top-level keys: {missing}"

    # site sub-keys
    site = body["site"]
    for key in ("id", "plant_rated_ac_mw", "banks", "bank_rated_ac_mw", "bess_rated_mw"):
        assert key in site, f"site missing key '{key}'"

    # atmosphere sub-keys
    atm = body["atmosphere"]
    for key in ("poa", "cloud_factor", "module_temp_c"):
        assert key in atm, f"atmosphere missing key '{key}'"

    # power sub-keys
    pwr = body["power"]
    for key in ("p_renewable_mw", "p_expected_mw", "banks_reporting", "banks_total"):
        assert key in pwr, f"power missing key '{key}'"
    assert isinstance(pwr["p_renewable_mw"], float)
    assert isinstance(pwr["banks_total"], int)
    assert pwr["banks_total"] > 0

    # fleet sub-keys
    flt = body["fleet"]
    for key in ("bess_soc", "bess_bridging_mw", "fleet_ramp_mw_per_s"):
        assert key in flt, f"fleet missing key '{key}'"

    # blocks must be a non-empty list; each entry must carry 'id' and 'state'
    blocks = body["blocks"]
    assert isinstance(blocks, list), "blocks must be a list"
    assert len(blocks) > 0, "blocks must not be empty"
    for b in blocks:
        assert "id" in b, f"bank entry missing 'id': {b}"
        assert "state" in b, f"bank entry missing 'state': {b}"

    # exposure sub-keys
    exp = body["exposure"]
    for key in ("largest_bank_mw", "largest_feeder_mw", "plant_loss_mw"):
        assert key in exp, f"exposure missing key '{key}'"

    # reserve must contain at least n1 and plant contingency results
    rsv = body["reserve"]
    for key in ("n1", "plant"):
        assert key in rsv, f"reserve missing key '{key}'"
    for key in ("passes", "gap_s", "peak_shortfall_mw"):
        assert key in rsv["n1"], f"reserve.n1 missing key '{key}'"

    # log must be a list (may be empty at t=0)
    assert isinstance(body["log"], list), "log must be a list"


# ---------------------------------------------------------------------------
# TC-SOL-R2  /api/solar/config returns site-only subset
# ---------------------------------------------------------------------------

def test_solar_config_returns_site_subset(solar_client: TestClient) -> None:
    """GET /api/solar/config must return HTTP 200 with the same 'site' object
    that /api/solar/state embeds, without the other simulation-level keys."""
    config_resp = solar_client.get("/api/solar/config")
    state_resp  = solar_client.get("/api/solar/state")

    assert config_resp.status_code == 200, (
        f"Expected 200 from /api/solar/config, got {config_resp.status_code}"
    )
    config_body = config_resp.json()
    state_site  = state_resp.json()["site"]

    # /config must contain all the keys that /state['site'] contains
    missing = state_site.keys() - config_body.keys()
    assert not missing, (
        f"/api/solar/config missing keys present in /state['site']: {missing}"
    )

    # Scalar site constants must agree between the two endpoints (same singleton)
    for key in ("id", "plant_rated_ac_mw", "banks", "bank_rated_ac_mw"):
        assert config_body[key] == state_site[key], (
            f"Mismatch for site.{key}: config={config_body[key]} state={state_site[key]}"
        )

    # /config must NOT expose simulation-level keys from the full snapshot
    assert "atmosphere" not in config_body, "/api/solar/config must not include 'atmosphere'"
    assert "power"      not in config_body, "/api/solar/config must not include 'power'"


# ---------------------------------------------------------------------------
# TC-SOL-R3  POST /api/solar/inject/poi zeroes p_renewable_mw
# ---------------------------------------------------------------------------

def test_solar_inject_poi_zeroes_p_renewable(solar_client: TestClient) -> None:
    """POST /api/solar/inject/poi must disconnect all banks (state → out),
    causing p_renewable_mw to drop to 0.0 in the very next /state call.

    The POI breaker open is the sizing contingency (spec §5): the entire array
    disconnects simultaneously, so counted_output_mw() returns 0 for every
    bank (state == 'out') and p_renewable_mw becomes exactly 0.0.
    """
    inject_resp = solar_client.post("/api/solar/inject/poi")
    assert inject_resp.status_code == 200, (
        f"POST /api/solar/inject/poi returned {inject_resp.status_code}: {inject_resp.text}"
    )

    state_resp = solar_client.get("/api/solar/state")
    assert state_resp.status_code == 200

    body = state_resp.json()
    p_renewable = body["power"]["p_renewable_mw"]
    assert p_renewable == 0.0, (
        f"Expected p_renewable_mw == 0.0 after POI inject, got {p_renewable}"
    )

    # Every bank must be in the 'out' state — POI inject sets them all at once
    for bank in body["blocks"]:
        assert bank["state"] == "out", (
            f"Bank {bank['id']} is in state '{bank['state']}', "
            f"expected 'out' after POI inject"
        )


# ---------------------------------------------------------------------------
# TC-SOL-R4  POST /api/solar/inject/unknown returns 400
# ---------------------------------------------------------------------------

def test_solar_inject_unknown_stressor_returns_400(solar_client: TestClient) -> None:
    """POST /api/solar/inject/<unknown> must return HTTP 400 with a detail
    message that names the unknown kind so operators can debug bad console calls.
    """
    resp = solar_client.post("/api/solar/inject/unknown_stressor_xyz")

    assert resp.status_code == 400, (
        f"Expected 400 for unknown stressor, got {resp.status_code}: {resp.text}"
    )
    detail = resp.json().get("detail", "")
    assert "unknown_stressor_xyz" in detail, (
        f"400 detail should name the bad stressor; got: {detail!r}"
    )


# ---------------------------------------------------------------------------
# TC-SOL-R5  GET /solar-console returns 200 with text/html
# ---------------------------------------------------------------------------

def test_solar_console_returns_html(solar_client: TestClient) -> None:
    """GET /solar-console must return HTTP 200 with a text/html content-type.

    The route serves the standalone Renewable Supply Console HTML file
    (renewable/console.html).  This test confirms the file is present on disk
    and that the route wiring is correct end-to-end.
    """
    resp = solar_client.get("/solar-console")

    assert resp.status_code == 200, (
        f"GET /solar-console returned {resp.status_code}: {resp.text[:200]}"
    )
    content_type = resp.headers.get("content-type", "")
    assert "text/html" in content_type, (
        f"Expected text/html content-type from /solar-console, got: {content_type!r}"
    )
