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

# Explicit San Diego SiteLocation used for T4 temperature-range tests.
# Passing site= keeps the tests independent of the process-level location
# singleton (which a preceding API test may have set to a different city).
try:
    from site_config import SiteLocation as _SiteLocation
    _SAN_DIEGO = _SiteLocation(
        site_name="San Diego, CA",
        latitude_deg=32.72,
        longitude_deg=-117.16,
        tz_name="America/Los_Angeles",
        source="test",
        climate_hint="",
        ambient_temp_base_c=14.0,
    )
except ImportError:
    _SAN_DIEGO = None  # type: ignore[assignment]

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


# ---------------------------------------------------------------------------
# T4 — ambient_steps structural integrity
# ---------------------------------------------------------------------------
# UTC times that produce clearly distinct San Diego local times:
#   UTC 20:00  →  local 12:00 (solar noon, high irradiance, high ambient)
#   UTC 08:00  →  local 00:00 (solar midnight, zero irradiance, low ambient)
_NOON_UTC     = datetime.datetime(2026, 6, 21, 20, 0, 0)   # summer solstice noon local
_MIDNIGHT_UTC = datetime.datetime(2026, 6, 21,  8, 0, 0)   # local midnight


def test_ambient_steps_starts_at_t0():
    """Physics ambient_steps must have first entry at sim_time_s == 0."""
    with _no_mistral_key():
        forecast = generate_solar_forecast(300.0, utc_now=_NOON_UTC, site=_SAN_DIEGO)

    assert len(forecast.ambient_steps) > 0, "ambient_steps must be non-empty"
    first_t = forecast.ambient_steps[0][0]
    assert first_t == 0.0, (
        f"ambient_steps must start at t=0; got first t={first_t}"
    )


def test_ambient_steps_sorted():
    """Physics ambient_steps sim_time_s values must be non-decreasing."""
    with _no_mistral_key():
        forecast = generate_solar_forecast(300.0, utc_now=_NOON_UTC, site=_SAN_DIEGO)

    times = [t for t, _db, _wb in forecast.ambient_steps]
    assert times == sorted(times), (
        f"ambient_steps must be sorted by sim_time_s; found out-of-order entry"
    )


def test_ambient_steps_drybulb_in_san_diego_range_noon():
    """Noon dry-bulb values must lie within the physically plausible 10–30 °C band."""
    with _no_mistral_key():
        forecast = generate_solar_forecast(300.0, utc_now=_NOON_UTC, site=_SAN_DIEGO)

    for t, db, _wb in forecast.ambient_steps:
        assert 10.0 <= db <= 30.0, (
            f"drybulb out of plausible San Diego range at t={t}: {db} °C"
        )


def test_ambient_steps_drybulb_in_san_diego_range_midnight():
    """Midnight dry-bulb values must also lie within the 10–30 °C band."""
    with _no_mistral_key():
        forecast = generate_solar_forecast(300.0, utc_now=_MIDNIGHT_UTC, site=_SAN_DIEGO)

    for t, db, _wb in forecast.ambient_steps:
        assert 10.0 <= db <= 30.0, (
            f"drybulb out of plausible San Diego range at t={t}: {db} °C"
        )


def test_ambient_steps_wetbulb_in_san_diego_range():
    """Wet-bulb values must lie within 8–30 °C for both noon and midnight.

    San Diego base_temp_c = 14 °C.  At local midnight solar_fraction = 0, so
    drybulb = 14 °C and wetbulb = 11 °C.  The lower bound is 8 to give headroom
    for cooler sites (base < 14) while still catching physically absurd values.
    Uses site=_SAN_DIEGO explicitly to be independent of the process-level
    location singleton, which API tests may have set to a different city.
    """
    with _no_mistral_key():
        for utc in (_NOON_UTC, _MIDNIGHT_UTC):
            forecast = generate_solar_forecast(300.0, utc_now=utc, site=_SAN_DIEGO)
            for t, _db, wb in forecast.ambient_steps:
                assert 8.0 <= wb <= 30.0, (
                    f"wetbulb out of plausible San Diego range at t={t}: {wb} °C"
                )


def test_ambient_steps_wetbulb_below_drybulb():
    """Wet-bulb must be strictly below dry-bulb (coastal humidity model)."""
    with _no_mistral_key():
        forecast = generate_solar_forecast(300.0, utc_now=_NOON_UTC, site=_SAN_DIEGO)

    for t, db, wb in forecast.ambient_steps:
        assert wb < db, (
            f"wetbulb ({wb} °C) must be < drybulb ({db} °C) at t={t}"
        )


def test_noon_drybulb_higher_than_midnight():
    """Physics model: noon San Diego ambient must exceed midnight ambient."""
    with _no_mistral_key():
        noon_fc = generate_solar_forecast(300.0, utc_now=_NOON_UTC, site=_SAN_DIEGO)
        midnight_fc = generate_solar_forecast(300.0, utc_now=_MIDNIGHT_UTC, site=_SAN_DIEGO)

    noon_avg = sum(db for _, db, _ in noon_fc.ambient_steps) / len(noon_fc.ambient_steps)
    midnight_avg = sum(db for _, db, _ in midnight_fc.ambient_steps) / len(midnight_fc.ambient_steps)
    assert noon_avg > midnight_avg, (
        f"noon avg drybulb ({noon_avg:.2f} °C) must exceed "
        f"midnight avg ({midnight_avg:.2f} °C)"
    )


# ---------------------------------------------------------------------------
# T4e — ambient_alpha_scale unit tests
# ---------------------------------------------------------------------------

def test_ambient_alpha_scale_empty_returns_one():
    """ambient_alpha_scale([]) must return exactly 1.0 (no-op for runs without solar)."""
    from runtime.solar_sim import ambient_alpha_scale
    assert ambient_alpha_scale([]) == 1.0


def test_ambient_alpha_scale_nominal_temp():
    """ambient_alpha_scale at 21 °C (ASHRAE 90.4 moderate-climate nominal) must return 1.0."""
    from runtime.solar_sim import ambient_alpha_scale
    steps = [(0.0, 21.0, 18.0), (60.0, 21.0, 18.0)]
    result = ambient_alpha_scale(steps)
    assert abs(result - 1.0) < 1e-9, f"expected 1.0 at nominal temp (21 °C), got {result}"


def test_ambient_alpha_scale_at_14c_ashrae_boundary():
    """ambient_alpha_scale at 14 °C must match ASHRAE coefficient: 1.5 %/°C below 21 °C nominal.

    Expected: 1.0 + 0.015 × (14 − 21) = 0.895
    """
    from runtime.solar_sim import ambient_alpha_scale
    steps = [(0.0, 14.0, 11.0), (60.0, 14.0, 11.0)]
    result = ambient_alpha_scale(steps)
    expected = 1.0 + 0.015 * (14.0 - 21.0)  # 0.895
    assert abs(result - expected) < 1e-9, (
        f"expected {expected:.4f} at 14 °C (ASHRAE lower boundary), got {result:.6f}"
    )


def test_ambient_alpha_scale_at_24c_ashrae_boundary():
    """ambient_alpha_scale at 24 °C must match ASHRAE coefficient: 1.5 %/°C above 21 °C nominal.

    Expected: 1.0 + 0.015 × (24 − 21) = 1.045
    """
    from runtime.solar_sim import ambient_alpha_scale
    steps = [(0.0, 24.0, 21.0), (60.0, 24.0, 21.0)]
    result = ambient_alpha_scale(steps)
    expected = 1.0 + 0.015 * (24.0 - 21.0)  # 1.045
    assert abs(result - expected) < 1e-9, (
        f"expected {expected:.4f} at 24 °C (ASHRAE upper boundary), got {result:.6f}"
    )


def test_ambient_alpha_scale_hot_day_above_one():
    """ambient_alpha_scale for a hot day (drybulb > 19 °C) must exceed 1.0."""
    from runtime.solar_sim import ambient_alpha_scale
    hot_steps = [(0.0, 22.0, 19.0), (60.0, 22.0, 19.0)]
    result = ambient_alpha_scale(hot_steps)
    assert result > 1.0, f"hot-day scale should exceed 1.0; got {result}"


def test_ambient_alpha_scale_cold_night_below_one():
    """ambient_alpha_scale for a cool night (drybulb < 19 °C) must be below 1.0."""
    from runtime.solar_sim import ambient_alpha_scale
    cold_steps = [(0.0, 14.0, 11.0), (60.0, 14.0, 11.0)]
    result = ambient_alpha_scale(cold_steps)
    assert result < 1.0, f"cold-night scale should be below 1.0; got {result}"


def test_ambient_alpha_scale_clamped_to_bounds():
    """ambient_alpha_scale must be clamped to [0.80, 1.20] for extreme temps."""
    from runtime.solar_sim import ambient_alpha_scale
    # Extreme hot
    very_hot = [(0.0, 60.0, 55.0)]
    assert ambient_alpha_scale(very_hot) <= 1.20, "hot clamp violated"
    # Extreme cold
    very_cold = [(0.0, -30.0, -35.0)]
    assert ambient_alpha_scale(very_cold) >= 0.80, "cold clamp violated"


def test_ambient_alpha_scale_registry_matches_runtime():
    """The coefficient values in gridsignal_parameters.json must equal what ambient_alpha_scale() uses.

    Guards against the ParameterModal showing an ASHRAE coefficient that differs
    from what the physics engine actually applies to alpha_max each run.
    """
    import json, pathlib
    from runtime.solar_sim import _ambient_coefficients

    params_path = (
        pathlib.Path(__file__).parent.parent / "gridsignal_parameters.json"
    )
    with open(params_path, encoding="utf-8") as fh:
        params = json.load(fh)
    locked = {
        entry["key"]: entry["value"]
        for entry in params.get("locked", [])
        if "key" in entry and "value" in entry
    }

    registry_nominal = locked["ambient_cooling_nominal_c"]
    registry_scale   = locked["ambient_cooling_scale_per_c"]

    # Clear the cache so this test always re-reads from disk.
    _ambient_coefficients.cache_clear()
    runtime_nominal, runtime_scale = _ambient_coefficients()

    assert abs(registry_nominal - runtime_nominal) < 1e-9, (
        f"Registry nominal ({registry_nominal} °C) != runtime nominal ({runtime_nominal} °C); "
        "update solar_sim.py defaults to match gridsignal_parameters.json"
    )
    assert abs(registry_scale - runtime_scale) < 1e-9, (
        f"Registry scale ({registry_scale} /°C) != runtime scale ({runtime_scale} /°C); "
        "update solar_sim.py defaults to match gridsignal_parameters.json"
    )


# ---------------------------------------------------------------------------
# T5 — ambient temperature shapes p_cooling_mw end-to-end
# ---------------------------------------------------------------------------

def _make_ambient_steps(drybulb_c: float, duration_s: float = 300.0) -> list:
    """Synthetic flat ambient_steps at a fixed drybulb temperature."""
    wetbulb_c = drybulb_c - 3.0
    n = 10
    step = duration_s / n
    return [(round(i * step, 1), round(drybulb_c, 2), round(wetbulb_c, 2))
            for i in range(n + 1)]


def _build_spec(ambient_drybulb_c: float, run_id: str) -> dict:
    """Build a minimal ScenarioSpec dict with the given constant ambient temperature.

    Uses:
    - dt_thermal_seconds=5.0   so cooling appears after just 1 tick (5 s)
    - tau_seconds=5.0          so alpha settles quickly (≈1 – e^-1 per tau)
    - alpha_max=0.20           baseline before ambient adjustment
    - 50 nodes                 so compute load is large enough to make
                               cooling clearly non-zero within a few ticks
    - turbine rated 30 MW      ample headroom; no reserve constraint fires
    - grid_tie (island=False)  avoids anchor-reserve complications in this test
    """
    return {
        "name": f"ambient-cooling-test-{run_id}",
        "end_sim_time": 300.0,
        "dt_thermal_seconds": 5.0,
        "tau_seconds": 5.0,
        "alpha_max": 0.20,
        "island_mode": False,
        "turbine_units": [
            {"asset_id": "t-0", "rated_mw": 30.0, "r_asset_mw_per_s": 10.0}
        ],
        "bess_units": [
            {
                "asset_id": "b-0", "rated_mw": 5.0, "usable_mwh": 2.0,
                "initial_soc_fraction": 1.0, "grid_forming": False,
            }
        ],
        "workload_events": [
            {
                "event_type": "starting",
                "timestamp": 0.0,
                "job_id": "job-ambient",
                "node_count": 50,
                "hardware_profile_id": "enterprise_8gpu_air",
            }
        ],
        "ambient_steps": _make_ambient_steps(ambient_drybulb_c),
    }


def _run_n_ticks(ctx, n: int) -> list:
    """Advance RunContext by n ticks; return list of TickResult objects."""
    from core._plane_guard import _EVALUATE_TICK_PERMITTED
    results = []
    for _ in range(n):
        token = _EVALUATE_TICK_PERMITTED.set(True)
        try:
            results.append(ctx.step())
        finally:
            _EVALUATE_TICK_PERMITTED.reset(token)
    return results


def test_ambient_alpha_max_higher_in_hot_run():
    """Hot ambient_steps must produce a higher site.alpha_max than cold ambient_steps
    when both pass through build_run_context_from_spec().

    This directly tests the PROTO-32-AMB wiring in scenario_factory.
    """
    from runtime.scenario_factory import build_run_context_from_spec

    hot_ctx  = build_run_context_from_spec("amb-hot",  _build_spec(22.0, "hot"))
    cold_ctx = build_run_context_from_spec("amb-cold", _build_spec(14.0, "cold"))

    hot_alpha  = hot_ctx.sim_state.cooling.site.alpha_max
    cold_alpha = cold_ctx.sim_state.cooling.site.alpha_max

    assert hot_alpha > cold_alpha, (
        f"hot ambient (22 °C) should yield higher alpha_max than cold (14 °C); "
        f"got hot={hot_alpha:.4f}, cold={cold_alpha:.4f}"
    )


def test_p_cooling_mw_higher_in_hot_ambient_run():
    """Runs with hot ambient_steps must produce higher p_cooling_mw than cold runs.

    Drives two short RunContexts past the thermal lag (dt_thermal=5 s, so
    cooling is active from tick 2 onward) and asserts that the hot run's
    final p_cooling_mw exceeds the cold run's — confirming the ambient_steps
    pipeline (SolarForecast → spec_data → factory → alpha_max → cooling) is live.
    """
    from runtime.scenario_factory import build_run_context_from_spec

    hot_ctx  = build_run_context_from_spec("p-hot",  _build_spec(22.0, "hot2"))
    cold_ctx = build_run_context_from_spec("p-cold", _build_spec(14.0, "cold2"))

    # 12 ticks = 60 s simulated; thermal lag is 5 s, tau is 5 s → alpha is at
    # ~99 % of alpha_max by tick 12 (elapsed since threshold ≈ 55 s ≈ 11·τ).
    n_ticks = 12
    hot_ticks  = _run_n_ticks(hot_ctx,  n_ticks)
    cold_ticks = _run_n_ticks(cold_ctx, n_ticks)

    hot_last  = hot_ticks[-1].p_cooling_mw
    cold_last = cold_ticks[-1].p_cooling_mw

    assert hot_last > 0.0, (
        f"hot run must produce non-zero cooling by tick {n_ticks}; got {hot_last}"
    )
    assert cold_last > 0.0, (
        f"cold run must produce non-zero cooling by tick {n_ticks}; got {cold_last}"
    )
    assert hot_last > cold_last, (
        f"hot ambient run (22 °C) must produce higher p_cooling_mw than cold (14 °C); "
        f"got hot={hot_last:.5f} MW, cold={cold_last:.5f} MW"
    )


def test_p_cooling_mw_differs_between_noon_and_midnight_physics_forecast():
    """End-to-end pipeline: physics SolarForecast.ambient_steps at noon vs midnight
    must produce different p_cooling_mw after a few ticks, confirming the full chain
    (generate_solar_forecast → spec_data["ambient_steps"] → factory → ticks) is live.
    """
    from runtime.scenario_factory import build_run_context_from_spec

    with _no_mistral_key():
        noon_fc     = generate_solar_forecast(300.0, utc_now=_NOON_UTC)
        midnight_fc = generate_solar_forecast(300.0, utc_now=_MIDNIGHT_UTC)

    def _spec_from_forecast(fc, tag: str) -> dict:
        spec = _build_spec(0.0, tag)   # drybulb placeholder; overwritten below
        spec["ambient_steps"] = [[t, db, wb] for t, db, wb in fc.ambient_steps]
        return spec

    noon_ctx     = build_run_context_from_spec(
        "pf-noon",     _spec_from_forecast(noon_fc,     "noon"))
    midnight_ctx = build_run_context_from_spec(
        "pf-midnight", _spec_from_forecast(midnight_fc, "midnight"))

    n_ticks  = 12
    noon_ticks     = _run_n_ticks(noon_ctx,     n_ticks)
    midnight_ticks = _run_n_ticks(midnight_ctx, n_ticks)

    noon_cooling     = noon_ticks[-1].p_cooling_mw
    midnight_cooling = midnight_ticks[-1].p_cooling_mw

    # Noon San Diego (summer) is hotter than local midnight → noon cooling > midnight.
    assert noon_cooling != midnight_cooling, (
        f"p_cooling_mw must differ between noon and midnight ambient runs; "
        f"both returned {noon_cooling:.5f} MW"
    )
    assert noon_cooling > midnight_cooling, (
        f"noon (high-ambient) run must have higher p_cooling_mw than midnight; "
        f"got noon={noon_cooling:.5f} MW, midnight={midnight_cooling:.5f} MW"
    )


# ---------------------------------------------------------------------------
# T6 — param-sampler × ambient_steps interaction
#
# These tests guard the PROTO-32-AMB wiring in scenario_factory.py against two
# specific failure modes that a future re-ordering of writes could introduce:
#
#   (a) Double-adjustment: ambient scale applied on top of a value that was
#       already pre-scaled (e.g. if someone pre-multiplied alpha_max before
#       storing it in spec_data).  site.alpha_max must NOT equal
#       sampled_alpha × scale × scale.
#
#   (b) Scale skipped: ambient_steps present but site.alpha_max equals the raw
#       sampled value with no scaling applied.
#
# The param_sampler writes alpha_max / plant_alpha_max into spec_data as plain
# floats; build_run_context_from_spec() then reads whichever is present and
# multiplies by ambient_alpha_scale() ONCE.  These tests confirm that contract.
# ---------------------------------------------------------------------------

# Hot ambient at 25 °C — scale will be > 1.0 and clearly != 1.0
_HOT_AMB_C = 25.0
_HOT_AMB_STEPS = _make_ambient_steps(_HOT_AMB_C)


def _base_spec_no_ambient(alpha_max_engine: float) -> dict:
    """Minimal spec without ambient_steps; sets alpha_max to simulate param_sampler output."""
    return {
        "name": "param-sampler-ambient-test",
        "end_sim_time": 60.0,
        "alpha_max": alpha_max_engine,
        "island_mode": False,
        "turbine_units": [
            {"asset_id": "t-0", "rated_mw": 30.0, "r_asset_mw_per_s": 10.0}
        ],
        "bess_units": [
            {
                "asset_id": "b-0", "rated_mw": 5.0, "usable_mwh": 2.0,
                "initial_soc_fraction": 1.0, "grid_forming": False,
            }
        ],
        "workload_events": [],
    }


def test_param_sampler_alpha_max_with_ambient_steps_applies_scale_once():
    """spec_data with a sampled alpha_max + hot ambient_steps must yield
    site.alpha_max == sampled_alpha × ambient_scale (applied exactly once).

    Verifies the PROTO-32-AMB wiring does not skip the ambient adjustment
    when alpha_max was written by the param_sampler.
    """
    from runtime.scenario_factory import build_run_context_from_spec
    from runtime.solar_sim import ambient_alpha_scale

    sampled_alpha = 0.23   # value as if drawn by sample_run_parameters(["alpha_max"])
    spec = _base_spec_no_ambient(sampled_alpha)
    spec["ambient_steps"] = _HOT_AMB_STEPS

    ctx = build_run_context_from_spec("ps-amb-once", spec)
    actual_alpha = ctx.sim_state.site.alpha_max

    scale = ambient_alpha_scale(_HOT_AMB_STEPS)
    expected = sampled_alpha * scale

    assert abs(actual_alpha - expected) < 1e-9, (
        f"site.alpha_max should be sampled_alpha × scale = "
        f"{sampled_alpha} × {scale:.6f} = {expected:.6f}; got {actual_alpha:.6f}"
    )


def test_param_sampler_alpha_max_with_ambient_steps_not_unscaled():
    """site.alpha_max must NOT equal the raw sampled value when ambient_steps is present.

    Guards against the scale being silently skipped (e.g. ambient_steps block
    moved after the site construction without updating site.alpha_max).
    """
    from runtime.scenario_factory import build_run_context_from_spec

    sampled_alpha = 0.23
    spec = _base_spec_no_ambient(sampled_alpha)
    spec["ambient_steps"] = _HOT_AMB_STEPS

    ctx = build_run_context_from_spec("ps-amb-not-raw", spec)
    actual_alpha = ctx.sim_state.site.alpha_max

    assert abs(actual_alpha - sampled_alpha) > 1e-6, (
        f"site.alpha_max ({actual_alpha:.6f}) must not equal the raw sampled value "
        f"({sampled_alpha}) when hot ambient_steps are present — ambient scale was skipped"
    )


def test_param_sampler_alpha_max_with_ambient_steps_not_double_scaled():
    """site.alpha_max must NOT equal sampled_alpha × scale × scale.

    Guards against a double-application where both the param_sampler pre-adjusts
    alpha and scenario_factory also applies ambient_alpha_scale(), or the factory
    applies the scale twice.
    """
    from runtime.scenario_factory import build_run_context_from_spec
    from runtime.solar_sim import ambient_alpha_scale

    sampled_alpha = 0.23
    spec = _base_spec_no_ambient(sampled_alpha)
    spec["ambient_steps"] = _HOT_AMB_STEPS

    ctx = build_run_context_from_spec("ps-amb-no-double", spec)
    actual_alpha = ctx.sim_state.site.alpha_max

    scale = ambient_alpha_scale(_HOT_AMB_STEPS)
    double_scaled = sampled_alpha * scale * scale

    assert abs(actual_alpha - double_scaled) > 1e-6, (
        f"site.alpha_max ({actual_alpha:.6f}) equals sampled_alpha × scale² = "
        f"{double_scaled:.6f}, indicating the ambient scale was applied twice"
    )


def test_plant_alpha_max_with_ambient_steps_applies_scale_once():
    """When plant_alpha_max is explicitly set in spec_data alongside ambient_steps,
    site.alpha_max must equal plant_alpha_max × ambient_scale (plant side wins,
    scale applied once).

    Covers the edge case from the task spec: plant_alpha_max explicitly present.
    """
    from runtime.scenario_factory import build_run_context_from_spec
    from runtime.solar_sim import ambient_alpha_scale

    plant_alpha = 0.26   # plant-side value (as if drawn by param_sampler plant split)
    engine_alpha = 0.21  # engine-side value — must NOT be used for site.alpha_max
    spec = _base_spec_no_ambient(engine_alpha)
    spec["plant_alpha_max"] = plant_alpha
    spec["ambient_steps"] = _HOT_AMB_STEPS

    ctx = build_run_context_from_spec("ps-plant-amb", spec)
    actual_alpha = ctx.sim_state.site.alpha_max

    scale = ambient_alpha_scale(_HOT_AMB_STEPS)
    expected = plant_alpha * scale

    assert abs(actual_alpha - expected) < 1e-9, (
        f"site.alpha_max should be plant_alpha_max × scale = "
        f"{plant_alpha} × {scale:.6f} = {expected:.6f}; got {actual_alpha:.6f}"
    )


def test_plant_alpha_max_takes_priority_over_engine_alpha_max():
    """When both plant_alpha_max and alpha_max are in spec_data (as param_sampler
    writes for a split parameter), plant_alpha_max must win and be used as the
    baseline for ambient scaling — not the engine-side alpha_max.
    """
    from runtime.scenario_factory import build_run_context_from_spec
    from runtime.solar_sim import ambient_alpha_scale

    plant_alpha = 0.26
    engine_alpha = 0.21
    spec = _base_spec_no_ambient(engine_alpha)
    spec["plant_alpha_max"] = plant_alpha
    spec["ambient_steps"] = _HOT_AMB_STEPS

    ctx = build_run_context_from_spec("ps-plant-priority", spec)
    actual_alpha = ctx.sim_state.site.alpha_max

    scale = ambient_alpha_scale(_HOT_AMB_STEPS)
    engine_scaled = engine_alpha * scale

    assert abs(actual_alpha - engine_scaled) > 1e-6, (
        f"site.alpha_max ({actual_alpha:.6f}) equals engine_alpha × scale = "
        f"{engine_scaled:.6f}; plant_alpha_max ({plant_alpha}) should have taken priority"
    )
