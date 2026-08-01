"""
tests/test_solar_weather_propagation.py — Solar weather data propagation tests.

Covers three end-to-end paths:

T1 — Physics fallback (no MISTRAL_API_KEY):
    generate_solar_forecast() must return SolarForecast with
    weather="physics_estimate" and source="physics" when the env var is absent.

T2 — Tick payload serialisation:
    A TickResult carrying solar_weather / solar_conditions must expose both keys
    in the dict produced by _tick_result_to_dict().  This guards the wire format
    used by WebSocket subscribers (and indirectly the Conditions row in the panel).

T3 — Mistral path propagation (mocked API call):
    When MISTRAL_API_KEY is present and _call_mistral returns a well-formed JSON
    response, generate_solar_forecast() must carry the weather label and
    conditions sentence through to the returned SolarForecast namedtuple with
    source="mistral".
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime
import json
import os
from unittest.mock import patch

import pytest

from runtime.solar_sim import SolarForecast, generate_solar_forecast
from runtime.run_manager import _tick_result_to_dict


# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------

_FIXED_UTC = datetime.datetime(2026, 6, 21, 18, 0, 0)  # San Diego noon-ish

@contextlib.contextmanager
def _no_mistral_key():
    """Temporarily remove MISTRAL_API_KEY from the environment."""
    original = os.environ.pop("MISTRAL_API_KEY", None)
    try:
        yield
    finally:
        if original is not None:
            os.environ["MISTRAL_API_KEY"] = original


# ---------------------------------------------------------------------------
# T1 — Physics fallback when MISTRAL_API_KEY is absent
# ---------------------------------------------------------------------------

def test_physics_fallback_weather_label():
    """generate_solar_forecast() with no key must return weather='physics_estimate'."""
    with _no_mistral_key():
        forecast = generate_solar_forecast(300.0, utc_now=_FIXED_UTC)

    assert forecast.weather == "physics_estimate", (
        f"expected 'physics_estimate', got {forecast.weather!r}"
    )


def test_physics_fallback_source_label():
    """generate_solar_forecast() with no key must return source='physics'."""
    with _no_mistral_key():
        forecast = generate_solar_forecast(300.0, utc_now=_FIXED_UTC)

    assert forecast.source == "physics", (
        f"expected source='physics', got {forecast.source!r}"
    )


def test_physics_fallback_returns_solar_forecast_namedtuple():
    """Return value must be a SolarForecast with non-empty samples and ambient_steps."""
    with _no_mistral_key():
        forecast = generate_solar_forecast(300.0, utc_now=_FIXED_UTC)

    assert isinstance(forecast, SolarForecast)
    assert len(forecast.samples) > 0, "physics fallback must produce at least one sample"
    assert len(forecast.ambient_steps) > 0, "physics fallback must produce ambient_steps"
    # All samples must be (sim_time_s, fraction) with fraction in [0, 1]
    for t, f in forecast.samples:
        assert 0.0 <= f <= 1.0, f"fraction out of range at t={t}: {f}"


def test_physics_fallback_conditions_nonempty():
    """Physics fallback conditions string must be non-empty."""
    with _no_mistral_key():
        forecast = generate_solar_forecast(300.0, utc_now=_FIXED_UTC)

    assert forecast.conditions, "physics fallback must set a non-empty conditions string"


# ---------------------------------------------------------------------------
# T2 — Tick payload serialisation: solar_weather / solar_conditions in dict
# ---------------------------------------------------------------------------

def _make_minimal_tick_result(solar_weather: str = "", solar_conditions: str = ""):
    """Build a minimal TickResult with solar weather fields set.

    Uses evaluate_tick to get a real TickResult, then replaces the two solar
    fields with the given values.  This is the same pattern as test_step7_payload.py
    (uses _plane_guard_active so the plane guard is satisfied).
    """
    import contextlib
    from core.asset_modules import (
        BessModule, CoolingModule, GPUModule,
        IrradianceProfile, SolarModule, TurbineModule,
    )
    from core.models import (
        BessConfig, HardwareProfile, IslandMode,
        SiteConfig, SolarConfig, TurbineConfig,
    )
    from core.sim_clock import SimClock
    from core.simulation_core import SimulationState, evaluate_tick
    from core._plane_guard import _EVALUATE_TICK_PERMITTED

    site = SiteConfig(
        site_id="solar-test-site", pue_base=1.03, uncalibrated=False,
        island_mode=IslandMode.ISLANDED,
    )
    hw = {"profile_a": HardwareProfile("profile_a", rated_kw=10.0)}
    state = SimulationState(
        run_id="solar-test-run",
        site=site,
        gpu_modules=[GPUModule(asset_id="gpu-0", site=site, hardware_library=hw)],
        turbines=[TurbineModule(
            config=TurbineConfig(asset_id="t-0", rated_mw=10.0, r_asset_mw_per_s=0.5)
        )],
        bess_units=[BessModule(
            config=BessConfig(
                asset_id="bess-0", rated_mw=5.0, usable_mwh=2.0,
                initial_soc_fraction=1.0, grid_forming=False,
            )
        )],
        solar_arrays=[SolarModule(
            config=SolarConfig(asset_id="solar-0", rated_mw=5.0),
            irradiance_profile=IrradianceProfile([(0.0, 1.0)]),
        )],
        cooling=CoolingModule(asset_id="cool-0", site=site),
    )
    clock = SimClock(sim_time=0.0, dt_seconds=5.0, wall_stamp_utc=None, rate=1.0, tick_seq=0)

    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        tick = evaluate_tick(state, clock)
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)

    # Stamp the solar weather metadata (mirrors what RunContext._drive() does)
    return dataclasses.replace(tick, solar_weather=solar_weather, solar_conditions=solar_conditions)


def test_solar_weather_key_present_in_tick_dict():
    """_tick_result_to_dict must include 'solar_weather' key."""
    tick = _make_minimal_tick_result(
        solar_weather="physics_estimate",
        solar_conditions="Physics estimate (San Diego)",
    )
    payload = _tick_result_to_dict(tick)
    assert "solar_weather" in payload, "'solar_weather' must appear in serialised tick dict"


def test_solar_conditions_key_present_in_tick_dict():
    """_tick_result_to_dict must include 'solar_conditions' key."""
    tick = _make_minimal_tick_result(
        solar_weather="physics_estimate",
        solar_conditions="Physics estimate (San Diego)",
    )
    payload = _tick_result_to_dict(tick)
    assert "solar_conditions" in payload, "'solar_conditions' must appear in serialised tick dict"


def test_solar_weather_value_propagated_to_tick_dict():
    """The solar_weather value set on TickResult must appear verbatim in the dict."""
    tick = _make_minimal_tick_result(
        solar_weather="clear",
        solar_conditions="Sunny afternoon with no cloud cover.",
    )
    payload = _tick_result_to_dict(tick)
    assert payload["solar_weather"] == "clear", (
        f"expected 'clear', got {payload['solar_weather']!r}"
    )
    assert payload["solar_conditions"] == "Sunny afternoon with no cloud cover.", (
        f"unexpected conditions: {payload['solar_conditions']!r}"
    )


def test_solar_weather_empty_string_when_not_set():
    """When solar weather is not stamped (default), both keys are present but empty."""
    tick = _make_minimal_tick_result()  # defaults: solar_weather="", solar_conditions=""
    payload = _tick_result_to_dict(tick)
    assert payload["solar_weather"] == "", (
        f"expected empty string, got {payload['solar_weather']!r}"
    )
    assert payload["solar_conditions"] == "", (
        f"expected empty string, got {payload['solar_conditions']!r}"
    )


# ---------------------------------------------------------------------------
# T3 — Mistral path: weather and conditions propagated when API is mocked
# ---------------------------------------------------------------------------

def _mistral_json_response(
    weather: str = "clear",
    conditions: str = "Clear sky, peak output expected.",
    sim_duration_s: float = 300.0,
    n_samples: int = 5,
) -> str:
    """Build a minimal but valid Mistral JSON response string."""
    step = sim_duration_s / (n_samples - 1)
    samples = [[round(i * step, 1), round(0.8 + 0.01 * i, 4)] for i in range(n_samples)]
    ambient = [[round(i * step, 1), round(22.0 + 0.1 * i, 2), round(19.0 + 0.1 * i, 2)]
               for i in range(n_samples)]
    return json.dumps({
        "weather":    weather,
        "conditions": conditions,
        "samples":    samples,
        "ambient":    ambient,
    })


def test_mistral_weather_label_propagates():
    """When _call_mistral returns 'partly_cloudy', forecast.weather must be 'partly_cloudy'."""
    mock_response = _mistral_json_response(weather="partly_cloudy",
                                           conditions="Intermittent cloud cover expected.")
    with patch.dict(os.environ, {"MISTRAL_API_KEY": "fake-key-for-test"}):
        with patch("runtime.solar_sim._call_mistral", return_value=mock_response):
            forecast = generate_solar_forecast(300.0, utc_now=_FIXED_UTC)

    assert forecast.weather == "partly_cloudy", (
        f"expected 'partly_cloudy', got {forecast.weather!r}"
    )


def test_mistral_conditions_propagates():
    """When _call_mistral returns a conditions string, it must appear on SolarForecast."""
    expected_conditions = "Intermittent cloud cover expected."
    mock_response = _mistral_json_response(weather="partly_cloudy",
                                           conditions=expected_conditions)
    with patch.dict(os.environ, {"MISTRAL_API_KEY": "fake-key-for-test"}):
        with patch("runtime.solar_sim._call_mistral", return_value=mock_response):
            forecast = generate_solar_forecast(300.0, utc_now=_FIXED_UTC)

    assert forecast.conditions == expected_conditions, (
        f"expected {expected_conditions!r}, got {forecast.conditions!r}"
    )


def test_mistral_source_label_is_mistral():
    """SolarForecast from a successful mocked Mistral call must have source='mistral'."""
    mock_response = _mistral_json_response()
    with patch.dict(os.environ, {"MISTRAL_API_KEY": "fake-key-for-test"}):
        with patch("runtime.solar_sim._call_mistral", return_value=mock_response):
            forecast = generate_solar_forecast(300.0, utc_now=_FIXED_UTC)

    assert forecast.source == "mistral", (
        f"expected source='mistral', got {forecast.source!r}"
    )


def test_mistral_samples_returned_from_response():
    """Samples from Mistral response must be carried on SolarForecast."""
    mock_response = _mistral_json_response(n_samples=5)
    with patch.dict(os.environ, {"MISTRAL_API_KEY": "fake-key-for-test"}):
        with patch("runtime.solar_sim._call_mistral", return_value=mock_response):
            forecast = generate_solar_forecast(300.0, utc_now=_FIXED_UTC)

    assert len(forecast.samples) >= 5, (
        f"expected at least 5 samples from mock response, got {len(forecast.samples)}"
    )


def test_mistral_api_error_falls_back_to_physics():
    """When _call_mistral raises, generate_solar_forecast() must fall back to physics."""
    with patch.dict(os.environ, {"MISTRAL_API_KEY": "fake-key-for-test"}):
        with patch("runtime.solar_sim._call_mistral",
                   side_effect=RuntimeError("Mistral HTTP 503: unavailable")):
            forecast = generate_solar_forecast(300.0, utc_now=_FIXED_UTC)

    assert forecast.source == "physics", (
        f"expected physics fallback on API error, got source={forecast.source!r}"
    )
    assert forecast.weather == "physics_estimate", (
        f"expected 'physics_estimate' on API error, got {forecast.weather!r}"
    )


def test_mistral_bad_json_falls_back_to_physics():
    """When _call_mistral returns unparseable JSON, forecast must use physics fallback."""
    with patch.dict(os.environ, {"MISTRAL_API_KEY": "fake-key-for-test"}):
        with patch("runtime.solar_sim._call_mistral", return_value="not valid json {{{"):
            forecast = generate_solar_forecast(300.0, utc_now=_FIXED_UTC)

    assert forecast.source == "physics", (
        f"expected physics fallback on bad JSON, got source={forecast.source!r}"
    )
