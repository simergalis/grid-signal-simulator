"""
tests/test_non_us_solar_e2e.py — Integration companion to test_no_hardcoded_location.py

Purpose
-------
Confirm that a full simulation run started with a non-US city location
(Frankfurt, Auckland) produces non-zero p_renewable_mw on at least one of the
first 3 WebSocket ticks during a daytime irradiance window.

Guard B in test_no_hardcoded_location.py verifies the physics irradiance curve
is correct in isolation (unit level).  SP-4 in test_solar_site_pipeline.py
confirms Auckland physics propagates through generate_solar_forecast →
build_run_context_from_spec → tick at the unit level.

This test closes the remaining integration gap: the complete
  HTTP POST /runs → generate_solar_forecast(site=<SiteLocation>)
                  → RunManager → WebSocket tick → p_renewable_mw
pipeline with a non-US SiteLocation configured in the process singleton.

Parametrize arms
----------------
Frankfurt — lat=50.11, lon=8.68, tz=Europe/Berlin
Auckland  — lat=-36.85, lon=174.76, tz=Pacific/Auckland

Design — spy + duration cap
----------------------------
runs.py forwards the body's end_sim_time (here 1e15, the standard TestClient
"run lives forever" sentinel) directly to generate_solar_forecast as the
physics sample count is n = round(sim_duration_s / 600) ≈ 1.67×10¹².
That many iterations hang the test.

Solution: patch generate_solar_forecast at the import in api.routes.runs with
a thin spy that:
  (a) caps sim_duration_s at 300 s so the physics fallback produces only
      2 samples (t=0 and t=300) — fast and deterministic,
  (b) records the keyword arguments so the test can assert that the correct
      SiteLocation (including non-US latitude/longitude) was forwarded,
  (c) calls through to the real function so the returned irradiance is
      physically non-zero at solar noon and p_renewable_mw > 0 on ticks.

The default irradiance_steps [(0.0, 1.0)] in the spec is intentionally kept,
which triggers _is_default_irr=True in runs.py and causes the patched
generate_solar_forecast to be called with the process-level SiteLocation —
the production code path this test is designed to exercise.
"""

from __future__ import annotations

import contextlib
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from site_config import SiteLocation, set_site_location


# ---------------------------------------------------------------------------
# Non-US test site definitions
# Coordinate literals are permitted in test_*.py files (Guard A exempts them;
# see test_no_hardcoded_location.py § "Guard A — AST scan").
# ---------------------------------------------------------------------------

_NON_US_SITES = [
    {
        "label": "Frankfurt",
        "lat": 50.11,
        "lon": 8.68,
        "tz": "Europe/Berlin",
        # CET = UTC+1; local solar noon ≈ 12:00 → UTC ≈ 11
        "solar_noon_utc_h": 11,
        # EU grid runs at 50 Hz
        "frequency_hz": 50.0,
    },
    {
        "label": "Auckland",
        "lat": -36.85,
        "lon": 174.76,
        "tz": "Pacific/Auckland",
        # NZST = UTC+12; local solar noon ≈ 12:00 → UTC ≈ 0
        "solar_noon_utc_h": 0,
        # NZ grid runs at 50 Hz
        "frequency_hz": 50.0,
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _no_mistral_key():
    """Remove MISTRAL_API_KEY for the duration of the block.

    Ensures the spy/real generate_solar_forecast uses the deterministic
    physics fallback (no network call, no API key required).
    """
    original = os.environ.pop("MISTRAL_API_KEY", None)
    try:
        yield
    finally:
        if original is not None:
            os.environ["MISTRAL_API_KEY"] = original


def _make_solar_spec(city: dict):
    """Build a minimal ScenarioSpec with solar enabled for the given city.

    irradiance_steps is intentionally omitted (defaults to [(0.0, 1.0)]).
    This single-entry default triggers _is_default_irr=True in runs.py,
    causing the handler to call generate_solar_forecast — the production
    path this test is designed to exercise.

    solar_origin_utc_hour pins the UTC hour to the city's solar noon so
    the physics fallback computes a high irradiance fraction regardless of
    when the test suite actually runs.

    frequency_nominal_hz=city["frequency_hz"]
        EU/APAC sites run at 50 Hz; the ScenarioSpec validator enforces this.
    """
    from api.schemas import BessUnitSpec, ScenarioSpec, TurbineUnitSpec

    return ScenarioSpec(
        name=f"e2e-solar-{city['label'].lower()}",
        description=f"Non-US solar E2E integration test — {city['label']}.",
        solar_rated_mw=5.0,
        # Default irradiance_steps → _is_default_irr=True → generate_solar_forecast called.
        # (Do not set irradiance_steps here — the default [(0.0, 1.0)] must remain.)
        solar_origin_utc_hour=city["solar_noon_utc_h"],
        frequency_nominal_hz=city["frequency_hz"],
        bess_units=[
            BessUnitSpec(
                asset_id="bess-0",
                rated_mw=5.0,
                usable_mwh=2.5,
                grid_forming=True,
            )
        ],
        turbine_units=[
            TurbineUnitSpec(
                asset_id="turbine-0",
                rated_mw=20.0,
                r_asset_mw_per_s=5.0,
            )
        ],
        workload_events=[
            {
                "event_type": "starting",
                "timestamp": 0.0,
                "job_id": "job-solar-e2e",
                "node_count": 50,
                "hardware_profile_id": "enterprise_8gpu_air",
            }
        ],
    )


# ---------------------------------------------------------------------------
# Parametrized E2E test
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("city", _NON_US_SITES, ids=lambda c: c["label"])
def test_non_us_solar_run_produces_nonzero_renewable(city: dict) -> None:
    """A run started with a non-US location must call generate_solar_forecast
    with the correct SiteLocation and produce p_renewable_mw > 0 on at least
    one of the first 3 WebSocket ticks.

    What is verified
    ----------------
    1. The site_config singleton is set to the target non-US city before the run.
    2. POST /runs causes the production runs.py handler to call
       generate_solar_forecast with site= carrying the correct latitude and
       longitude for the configured city (not a hardcoded San Diego value).
    3. The WebSocket delivers at least 3 tick payloads.
    4. At least one tick carries p_renewable_mw > 0, confirming the forecast
       irradiance propagates all the way through to the broadcast payload.

    Regression value
    ----------------
    The pre-refactor defect set p_renewable_mw=0 for non-US cities because
    SolarSim used hardcoded San Diego coordinates (lat=32.72, lon=-117.16).
    This test fails against that code in two ways:
      • The spy assertion catches that the wrong latitude/longitude was passed.
      • Even if the coordinates were right, p_renewable_mw would be wrong
        because the physics would compute the wrong solar elevation.

    Guard B in test_no_hardcoded_location.py confirms the physics irradiance
    curve is correct at the unit level.  This test is the integration companion:
    it confirms the full path from HTTP request → site_config singleton →
    runs.py → generate_solar_forecast(site=) → irradiance_steps → TickResult
    → WebSocket p_renewable_mw.

    Spy design
    ----------
    generate_solar_forecast is patched at the import in api.routes.runs.
    The spy wrapper caps sim_duration_s at 300 s to avoid generating
    round(1e15 / 600) ≈ 1.67×10¹² physics samples (which would hang the test
    when end_sim_time=1e15 is used to keep the run alive for WS collection).
    After capping, the spy calls through to the real function so the returned
    irradiance is physically correct (non-zero at solar noon).

    Diagnosis guide (if this test fails)
    -------------------------------------
    • If "generate_solar_forecast not called" assertion fires:
        → _is_default_irr logic in runs.py is broken or the scenario spec
          has irradiance_steps that are not the default sentinel.

    • If site= kwarg is None or has wrong lat/lon:
        → The SiteLocation singleton is not being read (get_site_location()),
          or runs.py is not forwarding it as site= to generate_solar_forecast.
          Check the _run_solar() closure in api/routes/runs.py.

    • If p_renewable_mw is zero on all ticks despite non-zero spy irradiance:
        → The IrradianceProfile is not wired into SolarModule, or
          the solar forecast result is being discarded before spec injection.
          Check SP-1 in test_solar_site_pipeline.py for the isolated wiring test.
    """
    from runtime.solar_sim import generate_solar_forecast as _real_gsf

    target_loc = SiteLocation(
        site_name=city["label"],
        latitude_deg=city["lat"],
        longitude_deg=city["lon"],
        tz_name=city["tz"],
        source="configured",
    )

    # Thread-safe enough under CPython's GIL for a single appended item.
    captured_calls: list[dict] = []

    def _spy(sim_duration_s: float, rated_mw: float = 4.99, **kwargs):
        """Spy wrapper: caps duration, records kwargs, calls real function."""
        captured_calls.append({"sim_duration_s": sim_duration_s, **kwargs})
        # Cap so physics produces only 2 samples (t=0 and t=300) — fast.
        return _real_gsf(min(float(sim_duration_s), 300.0), rated_mw, **kwargs)

    with _no_mistral_key(), patch(
        "api.routes.runs.generate_solar_forecast", side_effect=_spy
    ):
        # Set the site_config singleton to the target city BEFORE the TestClient
        # lifespan starts, then re-set after because the lifespan may read
        # gridsignal_site.json and overwrite the singleton.
        # The autouse _reset_site_location_singleton fixture in conftest.py
        # restores the original value after the test, keeping siblings clean.
        set_site_location(target_loc)

        with TestClient(create_app()) as client:
            # Re-set after the lifespan in case gridsignal_site.json overwrote it.
            set_site_location(target_loc)

            # Register the solar scenario.  Default irradiance_steps remain
            # unchanged so _is_default_irr=True in runs.py → spy is invoked.
            store = client.app.state.scenario_store
            spec = _make_solar_spec(city)
            record = store.create(spec)
            scenario_id = record.scenario_id

            # Start the run at maximum speed.  end_sim_time=1e15 keeps the run
            # alive during the WS receive loop; the spy caps the duration passed
            # to generate_solar_forecast so it doesn't hang.
            resp = client.post(
                "/runs",
                json={
                    "scenario_id": scenario_id,
                    "playback_speed": 0.0,
                    "end_sim_time": 1e15,
                },
            )
            assert resp.status_code == 201, (
                f"{city['label']}: POST /runs failed ({resp.status_code}): {resp.text}"
            )
            run_id = resp.json()["run_id"]

            # Receive 3 WebSocket tick payloads.
            ticks_received: list[dict] = []
            with client.websocket_connect(f"/ws/{run_id}") as ws:
                for _ in range(3):
                    tick = ws.receive_json()
                    ticks_received.append(tick)

    # ── Assert generate_solar_forecast was called via the production path ──

    assert len(captured_calls) >= 1, (
        f"{city['label']}: generate_solar_forecast was never called by POST /runs. "
        "Check that irradiance_steps in the spec is the default [(0.0, 1.0)] "
        "and that _is_default_irr=True triggers _run_solar() in api/routes/runs.py."
    )

    call_kwargs = captured_calls[0]
    site_arg: SiteLocation | None = call_kwargs.get("site")  # type: ignore[assignment]

    assert site_arg is not None, (
        f"{city['label']}: generate_solar_forecast was called without site= kwarg. "
        "runs.py must forward site=_effective_loc to generate_solar_forecast. "
        "A missing site= causes the function to fall back to the San Diego default, "
        "which could produce zero irradiance at the wrong UTC hour."
    )
    assert abs(site_arg.latitude_deg - city["lat"]) < 1e-6, (
        f"{city['label']}: generate_solar_forecast received latitude {site_arg.latitude_deg:.4f} "
        f"instead of {city['lat']}. "
        "The SiteLocation singleton is not being propagated to the forecast call. "
        "This would cause the wrong solar elevation angle and zero renewable output "
        "for sites far from the hardcoded default."
    )
    assert abs(site_arg.longitude_deg - city["lon"]) < 1e-6, (
        f"{city['label']}: generate_solar_forecast received longitude {site_arg.longitude_deg:.4f} "
        f"instead of {city['lon']}. "
        "Incorrect longitude shifts the solar noon UTC time and can cause zero "
        "irradiance at the time-of-day the run actually executes."
    )

    # ── Assert non-zero p_renewable_mw on at least one WS tick ───────────

    assert len(ticks_received) >= 3, (
        f"{city['label']}: expected ≥3 WS ticks; received {len(ticks_received)}. "
        "The run may have completed or the WebSocket closed early."
    )

    p_renewable_values = [t.get("p_renewable_mw", 0.0) for t in ticks_received]

    assert any(v > 0.0 for v in p_renewable_values), (
        f"{city['label']}: p_renewable_mw was zero (or absent) on all 3 ticks.\n"
        f"  Values: {[round(v, 4) for v in p_renewable_values]}\n"
        f"  Site confirmed in spy: lat={site_arg.latitude_deg}, lon={site_arg.longitude_deg}\n"
        f"  solar_noon_utc_h={city['solar_noon_utc_h']}\n"
        "Most likely cause: the IrradianceProfile is not being applied by SolarModule, "
        "or the physics returned all-zero fractions at the pinned UTC hour. "
        "Check SP-1 in test_solar_site_pipeline.py for the isolated wiring test."
    )
