"""
tests/test_solar_preview_source.py — Regression tests for the solar preview source fix.

Background
----------
GET /solar-preview calls generate_solar_forecast(sim_duration_s=_PREVIEW_DURATION_S).
_parse_forecast() filters samples by: 0.0 <= t <= sim_duration_s * 1.05.

With the original _PREVIEW_DURATION_S = 60.0 the cutoff was 63 s.  Mistral
typically returns samples at natural intervals (e.g. every 60–120 s for a
10-minute window), so all samples landed beyond 63 s, were filtered out,
triggering the "no valid samples" ValueError and a physics fallback.

The fix raises _PREVIEW_DURATION_S to 600 s (cutoff 630 s), wide enough that
Mistral's default sample spacing always falls inside the window.

Test plan
---------
TC-PV-1  _PREVIEW_DURATION_S constant is ≥ 300 s (sentinel against regression).
TC-PV-2  _parse_forecast drops all samples when duration=60 and samples are at
         t=120, 240, 360 s — reproduces the original bug.
TC-PV-3  _parse_forecast keeps all samples when duration=600 and samples are at
         t=120, 240, 360, 480, 600 s — confirms the fix.
TC-PV-4  _parse_forecast still falls back to physics on malformed JSON.
TC-PV-5  GET /solar-preview returns source="mistral" when Mistral is stubbed
         with samples at natural 120 s intervals (Honolulu location).
TC-PV-6  GET /solar-preview returns source="mistral" for Auckland location.
TC-PV-7  GET /solar-preview returns source="mistral" for Tokyo location.
TC-PV-8  GET /solar-preview returns source="mistral" for San Diego location.
TC-PV-9  GET /solar-preview falls back to source="physics" when Mistral key absent.
"""

from __future__ import annotations

import datetime
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.routes.solar import _PREVIEW_DURATION_S
from runtime.solar_sim import _parse_forecast


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UTC_NOW = datetime.datetime(2026, 8, 11, 20, 0, 0)  # 20:00 UTC — daytime in most zones

def _make_raw(samples: list[tuple[float, float]], weather: str = "partly_cloudy") -> str:
    """Build a minimal Mistral-style JSON string."""
    return json.dumps({
        "weather": weather,
        "conditions": "Partly cloudy skies over the test site.",
        "samples": [[t, f] for t, f in samples],
        "ambient": [[t, 22.0, 18.0] for t, _ in samples],
    })


# ---------------------------------------------------------------------------
# TC-PV-1  _PREVIEW_DURATION_S sentinel
# ---------------------------------------------------------------------------

def test_preview_duration_constant_is_adequate() -> None:
    """TC-PV-1: _PREVIEW_DURATION_S must be ≥ 300 s so Mistral's default
    sample spacing (typically 60–120 s) stays inside the parse filter cutoff."""
    assert _PREVIEW_DURATION_S >= 300.0, (
        f"_PREVIEW_DURATION_S={_PREVIEW_DURATION_S} is too short — "
        "Mistral samples at natural 120 s intervals would be filtered out "
        "and the preview would always fall back to physics. Raise to ≥ 300 s."
    )


# ---------------------------------------------------------------------------
# TC-PV-2  Reproduces the original bug: duration=60 drops 120 s+ samples
# ---------------------------------------------------------------------------

def test_parse_forecast_drops_samples_beyond_old_cutoff() -> None:
    """TC-PV-2: With sim_duration_s=60, samples at t=120,240,360 are all
    filtered (t > 63 s) → 'no valid samples' → physics fallback.
    This reproduces the bug that _PREVIEW_DURATION_S=60 caused."""
    samples_beyond_63 = [(120.0, 0.8), (240.0, 0.75), (360.0, 0.7)]
    raw = _make_raw(samples_beyond_63)

    result = _parse_forecast(
        raw,
        sim_duration_s=60.0,
        utc_now=_UTC_NOW,
        lat_deg=32.72,
        utc_offset_h=-7.0,
    )
    # All samples filtered → physics fallback
    assert result.source == "physics", (
        f"Expected physics fallback when all samples exceed 63 s cutoff, got source={result.source!r}"
    )


# ---------------------------------------------------------------------------
# TC-PV-3  Fix confirmed: duration=600 keeps 120 s+ samples
# ---------------------------------------------------------------------------

def test_parse_forecast_keeps_samples_within_600s_cutoff() -> None:
    """TC-PV-3: With sim_duration_s=600, samples at t=0,120,240,360,480,600
    all pass the filter (t ≤ 630) → source='mistral'."""
    samples_in_range = [
        (0.0,   0.85),
        (120.0, 0.82),
        (240.0, 0.79),
        (360.0, 0.76),
        (480.0, 0.73),
        (600.0, 0.70),
    ]
    raw = _make_raw(samples_in_range)

    result = _parse_forecast(
        raw,
        sim_duration_s=600.0,
        utc_now=_UTC_NOW,
        lat_deg=32.72,
        utc_offset_h=-7.0,
    )
    assert result.source == "mistral", (
        f"Expected mistral source with samples inside 630 s cutoff, got {result.source!r}"
    )
    assert result.weather == "partly_cloudy"
    assert len(result.samples) >= 5


# ---------------------------------------------------------------------------
# TC-PV-4  Physics fallback on malformed JSON
# ---------------------------------------------------------------------------

def test_parse_forecast_falls_back_on_malformed_json() -> None:
    """TC-PV-4: Malformed JSON still produces source='physics' (fallback chain
    must survive bad Mistral responses regardless of duration)."""
    result = _parse_forecast(
        "this is not json {{{",
        sim_duration_s=600.0,
        utc_now=_UTC_NOW,
        lat_deg=21.3,
        utc_offset_h=-10.0,
    )
    assert result.source == "physics"


# ---------------------------------------------------------------------------
# Shared HTTP fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def preview_client():
    """Single TestClient whose lifespan spans all HTTP preview tests."""
    with TestClient(create_app()) as client:
        yield client


@pytest.fixture(autouse=True)
def _stub_mistral_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep Mistral-path tests deterministic and free of external API calls.

    A placeholder key opens the forecast's Mistral branch, whose _call_mistral
    request is stubbed in each test below. The location geocoder is made to
    fail locally so resolve_location uses its built-in city table rather than
    depending on a real key or live response text.
    """
    monkeypatch.setenv("MISTRAL_API_KEY", "test-mistral-key")

    def _offline_geocoder(*_args, **_kwargs):
        raise RuntimeError("live Mistral geocoding is disabled in tests")

    monkeypatch.setattr(
        "api.routes.location._geocode_via_mistral",
        _offline_geocoder,
    )


def _stub_mistral_response(samples: list[tuple[float, float]], weather: str = "partly_cloudy") -> str:
    """Return a Mistral-style JSON string to be injected via _call_mistral stub."""
    return _make_raw(samples, weather)


def _assert_mistral_request_uses_selected_site(
    mistral_call,
    *,
    site_name: str,
    latitude_deg: float,
    longitude_deg: float,
    local_time: str,
) -> None:
    """Confirm the forecast request carries the location selected through the API."""
    mistral_call.assert_called_once()
    user_message, api_key = mistral_call.call_args.args
    system_prompt = mistral_call.call_args.kwargs["system_prompt"]

    lat_dir = "N" if latitude_deg >= 0 else "S"
    lon_dir = "E" if longitude_deg >= 0 else "W"
    assert api_key == "test-mistral-key"
    assert f"Current {site_name} local time: {local_time}" in user_message
    assert f"in {site_name} " in system_prompt
    assert (
        f"latitude {abs(latitude_deg):.2f}°{lat_dir}, "
        f"longitude {abs(longitude_deg):.2f}°{lon_dir}"
    ) in system_prompt


# Natural sample grid for _PREVIEW_DURATION_S=600 (every 60 s → well inside 630 s cutoff)
_NATURAL_SAMPLES = [(float(t), 0.80 - t / 6000.0) for t in range(0, 601, 60)]


# ---------------------------------------------------------------------------
# TC-PV-5  Honolulu (UTC-10): mistral source after location change
# ---------------------------------------------------------------------------

def test_preview_returns_mistral_source_honolulu(preview_client: TestClient) -> None:
    """TC-PV-5: After PUT /api/location to Honolulu, GET /solar-preview must
    return source='mistral' when Mistral is stubbed with 120 s-interval samples."""
    # Set location to Honolulu
    r = preview_client.put(
        "/api/location",
        json={"address": "Honolulu, HI"},
        headers={"X-Admin-Secret": "test-secret"},
    )
    assert r.status_code == 200, (
        f"Location update must be available in CI; got {r.status_code}: {r.text}"
    )
    assert r.json()["site_name"] == "Honolulu, HI"

    stub_raw = _stub_mistral_response(_NATURAL_SAMPLES)

    with patch("runtime.solar_sim._call_mistral", return_value=stub_raw) as mistral_call:
        resp = preview_client.get(
            "/solar-preview",
            params={"utc_now": "2026-06-21T00:00:00"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "mistral", (
        f"Expected source='mistral' for Honolulu, got {body['source']!r}. "
        f"weather={body.get('weather')!r}"
    )
    assert body["site_name"] == "Honolulu, HI"
    assert body["lat"] == pytest.approx(21.31)
    assert body["utc_offset_h"] == pytest.approx(-10.0)
    assert body["local_time"] == "14:00"
    _assert_mistral_request_uses_selected_site(
        mistral_call,
        site_name="Honolulu, HI",
        latitude_deg=21.31,
        longitude_deg=-157.86,
        local_time="14:00",
    )


# ---------------------------------------------------------------------------
# TC-PV-6  Auckland (UTC+12): mistral source
# ---------------------------------------------------------------------------

def test_preview_returns_mistral_source_auckland(preview_client: TestClient) -> None:
    """TC-PV-6: Auckland location with stubbed Mistral returns source='mistral'."""
    r = preview_client.put(
        "/api/location",
        json={"address": "Auckland, New Zealand"},
        headers={"X-Admin-Secret": "test-secret"},
    )
    assert r.status_code == 200, (
        f"Location update must be available in CI; got {r.status_code}: {r.text}"
    )
    assert r.json()["site_name"] == "Auckland, New Zealand"

    stub_raw = _stub_mistral_response(_NATURAL_SAMPLES, "clear")

    with patch("runtime.solar_sim._call_mistral", return_value=stub_raw) as mistral_call:
        resp = preview_client.get(
            "/solar-preview",
            params={"utc_now": "2026-06-21T00:00:00"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "mistral", (
        f"Expected source='mistral' for Auckland, got {body['source']!r}"
    )
    assert body["site_name"] == "Auckland, New Zealand"
    assert body["lat"] == pytest.approx(-36.85)
    assert body["utc_offset_h"] == pytest.approx(12.0)
    assert body["local_time"] == "12:00"
    _assert_mistral_request_uses_selected_site(
        mistral_call,
        site_name="Auckland, New Zealand",
        latitude_deg=-36.85,
        longitude_deg=174.76,
        local_time="12:00",
    )


# ---------------------------------------------------------------------------
# TC-PV-7  Tokyo (UTC+9): mistral source
# ---------------------------------------------------------------------------

def test_preview_returns_mistral_source_tokyo(preview_client: TestClient) -> None:
    """TC-PV-7: Tokyo location with stubbed Mistral returns source='mistral'."""
    r = preview_client.put(
        "/api/location",
        json={"address": "Tokyo, Japan"},
        headers={"X-Admin-Secret": "test-secret"},
    )
    assert r.status_code == 200, (
        f"Location update must be available in CI; got {r.status_code}: {r.text}"
    )
    assert r.json()["site_name"] == "Tokyo, Japan"

    stub_raw = _stub_mistral_response(_NATURAL_SAMPLES, "overcast")

    with patch("runtime.solar_sim._call_mistral", return_value=stub_raw) as mistral_call:
        resp = preview_client.get(
            "/solar-preview",
            params={"utc_now": "2026-06-21T00:00:00"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "mistral", (
        f"Expected source='mistral' for Tokyo, got {body['source']!r}"
    )
    assert body["site_name"] == "Tokyo, Japan"
    assert body["lat"] == pytest.approx(35.68)
    assert body["utc_offset_h"] == pytest.approx(9.0)
    assert body["local_time"] == "09:00"
    _assert_mistral_request_uses_selected_site(
        mistral_call,
        site_name="Tokyo, Japan",
        latitude_deg=35.68,
        longitude_deg=139.69,
        local_time="09:00",
    )


# ---------------------------------------------------------------------------
# TC-PV-8  San Diego (UTC-7): mistral source (baseline — must not regress)
# ---------------------------------------------------------------------------

def test_preview_returns_mistral_source_san_diego(preview_client: TestClient) -> None:
    """TC-PV-8: San Diego (original default site) still returns source='mistral'
    after the duration fix — baseline regression guard."""
    r = preview_client.put(
        "/api/location",
        json={"address": "San Diego, CA"},
        headers={"X-Admin-Secret": "test-secret"},
    )
    assert r.status_code == 200, (
        f"Location update must be available in CI; got {r.status_code}: {r.text}"
    )
    assert r.json()["site_name"] == "San Diego, CA"

    stub_raw = _stub_mistral_response(_NATURAL_SAMPLES, "clear")

    with patch("runtime.solar_sim._call_mistral", return_value=stub_raw) as mistral_call:
        resp = preview_client.get(
            "/solar-preview",
            params={"utc_now": "2026-06-21T00:00:00"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "mistral", (
        f"San Diego baseline regressed: expected source='mistral', got {body['source']!r}"
    )
    assert body["site_name"] == "San Diego, CA"
    assert body["lat"] == pytest.approx(32.72)
    assert body["utc_offset_h"] == pytest.approx(-7.0)
    assert body["local_time"] == "17:00"
    _assert_mistral_request_uses_selected_site(
        mistral_call,
        site_name="San Diego, CA",
        latitude_deg=32.72,
        longitude_deg=-117.16,
        local_time="17:00",
    )


# ---------------------------------------------------------------------------
# TC-PV-9  San Jose full state name resolves through the built-in fallback
# ---------------------------------------------------------------------------

def test_location_resolves_san_jose_full_state_name(preview_client: TestClient) -> None:
    """A common autocomplete-free entry must work when Mistral is unavailable."""
    response = preview_client.put(
        "/api/location",
        json={"address": "San Jose, California"},
        headers={"X-Admin-Secret": "test-secret"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "builtin"
    assert body["site_name"] == "San Jose, CA"
    assert body["lat"] == pytest.approx(37.3382)
    assert body["lon"] == pytest.approx(-121.8863)
    assert body["tz_name"] == "America/Los_Angeles"


# ---------------------------------------------------------------------------
# TC-PV-10  Physics fallback when MISTRAL_API_KEY is absent
# ---------------------------------------------------------------------------

def test_preview_falls_back_to_physics_without_api_key(preview_client: TestClient) -> None:
    """TC-PV-9: When MISTRAL_API_KEY is absent, GET /solar-preview must return
    source='physics' (fallback chain must remain intact after the duration fix)."""
    with patch.dict("os.environ", {}, clear=False):
        # Patch the key lookup inside solar_sim so it sees no key
        with patch("runtime.solar_sim.os.environ.get", return_value=None):
            resp = preview_client.get("/solar-preview")

    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "physics", (
        f"Expected physics fallback without API key, got {body['source']!r}"
    )
