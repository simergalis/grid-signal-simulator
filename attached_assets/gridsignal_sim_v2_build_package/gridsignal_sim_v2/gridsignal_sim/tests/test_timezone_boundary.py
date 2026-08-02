"""
tests/test_timezone_boundary.py — TZ-1 through TZ-14

Regression tests for the UTC-vs-local-time timezone bug in solar_sim.py.

The original defect
-------------------
The physics fallback in _solar_fraction_at() used the raw UTC hour as the
local hour when computing sun elevation, giving zero solar output whenever
UTC time fell at night even if the *site's* local time was afternoon.

Concrete failure: Auckland, UTC+12, 04:00 UTC = 16:00 local.
  broken:  local_h = 4.0  → hour_angle = (4-12)*15 = -120°  → sin_elev < 0 → 0.0 MW
  fixed:   local_h = 16.0 → hour_angle = (16-12)*15 = +60°  → sin_elev > 0 → >0.0 MW

What these tests guard
-----------------------
TZ-1  _solar_fraction_at() — Auckland 04:00 UTC is afternoon locally (non-zero)
TZ-2  _solar_fraction_at() — same time with offset=0 (the pre-fix path) gives zero
TZ-3  _solar_fraction_at() — Auckland midnight UTC is solar-noon locally (peak)
TZ-4  _solar_fraction_at() — San Diego noon (UTC 20:00) is correctly computed
TZ-5  _solar_fraction_at() — London midnight is correctly night
TZ-6  _solar_fraction_at() — Tokyo 01:00 UTC = 10:00 local → morning solar
TZ-7  _physics_samples() — Auckland 04:00 UTC run has at least one non-zero sample
TZ-8  _physics_forecast() — Auckland 04:00 UTC with correct offset is non-zero at t=0
TZ-9  _parse_forecast() fallback — bad JSON with Auckland params uses site offset
TZ-10 generate_solar_forecast() — Auckland no-key path uses site offset (non-zero)
TZ-11 generate_solar_forecast() — San Diego midnight (UTC+8 noon equivalent)
TZ-12 Offset symmetry — UTC+12 peak earlier than UTC-8 in UTC clock terms
TZ-13 _solar_fraction_at() — summer solstice Southern hemisphere peak is at noon local
TZ-14 _parse_forecast() fallback — Singapore (UTC+8) afternoon is non-zero via physics
"""

from __future__ import annotations

import contextlib
import datetime
import math
import os
from unittest.mock import patch

import pytest

from runtime.solar_sim import (
    SolarForecast,
    _physics_forecast,
    _physics_samples,
    _solar_fraction_at,
    generate_solar_forecast,
)
from runtime.solar_sim import _parse_forecast  # noqa: PLC2701


# ---------------------------------------------------------------------------
# Site constants
# ---------------------------------------------------------------------------

# Auckland, New Zealand
_AUCKLAND_LAT   = -36.85
_AUCKLAND_UTC   = 12.0

# San Diego, CA (default site)
_SANDIEGO_LAT   = 32.72
_SANDIEGO_UTC   = -8.0

# Tokyo, Japan
_TOKYO_LAT      = 35.69
_TOKYO_UTC      = 9.0

# London, UK
_LONDON_LAT     = 51.51
_LONDON_UTC     = 0.0

# Singapore
_SINGAPORE_LAT  = 1.35
_SINGAPORE_UTC  = 8.0

# June solstice — Northern summer, Southern winter
_JUN_SOLSTICE = datetime.date(2026, 6, 21)
# December solstice — Northern winter, Southern summer
_DEC_SOLSTICE = datetime.date(2025, 12, 21)


def _utc(date: datetime.date, hour: int, minute: int = 0) -> datetime.datetime:
    return datetime.datetime(date.year, date.month, date.day, hour, minute, 0)


@contextlib.contextmanager
def _no_mistral_key():
    original = os.environ.pop("MISTRAL_API_KEY", None)
    try:
        yield
    finally:
        if original is not None:
            os.environ["MISTRAL_API_KEY"] = original


# ---------------------------------------------------------------------------
# TZ-1  Auckland 04:00 UTC is 16:00 local — afternoon, non-zero solar
# ---------------------------------------------------------------------------

def test_tz1_auckland_utc04_is_afternoon_solar():
    """The exact regression: Auckland 04:00 UTC = 16:00 local on June solstice.

    With the correct UTC offset, solar elevation is positive (afternoon).
    Before the fix, the raw UTC hour (4) was used as local time → night → 0.
    """
    dt = _utc(_JUN_SOLSTICE, 4)  # 04:00 UTC = 16:00 Auckland local
    fraction = _solar_fraction_at(dt, lat_deg=_AUCKLAND_LAT, utc_offset_h=_AUCKLAND_UTC)
    assert fraction > 0.0, (
        f"Auckland 04:00 UTC (= 16:00 local) on June solstice must yield positive "
        f"solar fraction; got {fraction:.4f}. "
        "This is the UTC-vs-local timezone regression."
    )


# ---------------------------------------------------------------------------
# TZ-2  Without the offset, the same call returns zero (documents the old bug)
# ---------------------------------------------------------------------------

def test_tz2_auckland_utc04_without_offset_is_zero():
    """Documents the pre-fix behaviour: treating UTC as local time gives night.

    utc_offset_h=0 means local_h = UTC hour = 4.0 → well before sunrise at
    lat=-36.85 in June → sin_elev < 0 → fraction = 0.0.

    This test pins the broken baseline so it's clear why TZ-1 matters.
    """
    dt = _utc(_JUN_SOLSTICE, 4)
    fraction_no_tz = _solar_fraction_at(dt, lat_deg=_AUCKLAND_LAT, utc_offset_h=0.0)
    assert fraction_no_tz == 0.0, (
        f"Without offset correction, Auckland 04:00 UTC should yield 0.0 "
        f"(night in UTC); got {fraction_no_tz:.4f}."
    )


# ---------------------------------------------------------------------------
# TZ-3  Auckland midnight UTC = local noon — near-peak solar fraction
# ---------------------------------------------------------------------------

def test_tz3_auckland_utc00_is_local_noon():
    """00:00 UTC = 12:00 Auckland local — solar should be near maximum for the season."""
    dt = _utc(_JUN_SOLSTICE, 0)  # 00:00 UTC = 12:00 Auckland
    fraction = _solar_fraction_at(dt, lat_deg=_AUCKLAND_LAT, utc_offset_h=_AUCKLAND_UTC)

    # December solstice noon should be even higher for Southern hemisphere
    dt_summer = _utc(_DEC_SOLSTICE, 0)
    fraction_summer = _solar_fraction_at(dt_summer, lat_deg=_AUCKLAND_LAT, utc_offset_h=_AUCKLAND_UTC)

    # Both should be above zero (noon is always day)
    assert fraction > 0.0, (
        f"Auckland 00:00 UTC (= 12:00 local) June solstice must be positive; "
        f"got {fraction:.4f}"
    )
    assert fraction_summer > fraction, (
        f"Auckland summer noon (Dec) should exceed winter noon (Jun); "
        f"got summer={fraction_summer:.4f}, winter={fraction:.4f}"
    )


# ---------------------------------------------------------------------------
# TZ-4  San Diego: 20:00 UTC = 12:00 local — solar noon, high fraction
# ---------------------------------------------------------------------------

def test_tz4_sandiego_utc20_is_local_noon():
    """San Diego 20:00 UTC = 12:00 local on June solstice — near-peak fraction."""
    dt = _utc(_JUN_SOLSTICE, 20)  # 20:00 UTC = 12:00 San Diego PDT (UTC-8)
    fraction = _solar_fraction_at(dt, lat_deg=_SANDIEGO_LAT, utc_offset_h=_SANDIEGO_UTC)
    assert fraction > 0.5, (
        f"San Diego 20:00 UTC (= noon local) June solstice should give high solar "
        f"fraction; got {fraction:.4f}"
    )


# ---------------------------------------------------------------------------
# TZ-5  London midnight is correctly night
# ---------------------------------------------------------------------------

def test_tz5_london_midnight_is_night():
    """00:00 UTC = 00:00 London local (offset=0) — must be zero solar (midnight)."""
    dt = _utc(_JUN_SOLSTICE, 0)
    fraction = _solar_fraction_at(dt, lat_deg=_LONDON_LAT, utc_offset_h=_LONDON_UTC)
    assert fraction == 0.0, (
        f"London 00:00 UTC = midnight local — fraction must be 0.0; got {fraction:.4f}"
    )


# ---------------------------------------------------------------------------
# TZ-6  Tokyo 01:00 UTC = 10:00 local — morning solar
# ---------------------------------------------------------------------------

def test_tz6_tokyo_utc01_is_morning():
    """Tokyo 01:00 UTC = 10:00 local on June solstice — clear morning, non-zero."""
    dt = _utc(_JUN_SOLSTICE, 1)
    fraction = _solar_fraction_at(dt, lat_deg=_TOKYO_LAT, utc_offset_h=_TOKYO_UTC)
    assert fraction > 0.0, (
        f"Tokyo 01:00 UTC (= 10:00 local) June solstice must be positive; "
        f"got {fraction:.4f}"
    )
    # Also verify the pre-fix UTC path gives a different (wrong) answer
    fraction_no_tz = _solar_fraction_at(dt, lat_deg=_TOKYO_LAT, utc_offset_h=0.0)
    # 01:00 UTC is night everywhere without an offset
    assert fraction_no_tz == 0.0, (
        f"Without offset, Tokyo 01:00 UTC should be night; got {fraction_no_tz:.4f}"
    )


# ---------------------------------------------------------------------------
# TZ-7  _physics_samples() — Auckland run at 04:00 UTC has non-zero samples
# ---------------------------------------------------------------------------

def test_tz7_physics_samples_auckland_utc04_nonempty():
    """_physics_samples() with Auckland offset must contain at least one non-zero
    solar fraction for a 300 s run starting at 04:00 UTC (= 16:00 local).

    Before the fix, ALL samples would be zero because the UTC hour (4) was
    treated as local time, placing the entire 5-minute window in the night.
    """
    dt = _utc(_JUN_SOLSTICE, 4)
    samples = _physics_samples(300.0, dt, lat_deg=_AUCKLAND_LAT, utc_offset_h=_AUCKLAND_UTC)

    assert len(samples) > 0, "_physics_samples must produce at least one sample"
    nonzero = [f for _, f in samples if f > 0.0]
    assert len(nonzero) > 0, (
        f"Auckland 04:00 UTC run must have at least one non-zero solar sample; "
        f"all {len(samples)} samples were zero. "
        "This is the UTC-vs-local timezone regression in _physics_samples()."
    )


# ---------------------------------------------------------------------------
# TZ-8  _physics_forecast() — Auckland 04:00 UTC, first sample is non-zero
# ---------------------------------------------------------------------------

def test_tz8_physics_forecast_auckland_utc04_nonzero():
    """_physics_forecast() for Auckland at 04:00 UTC must have a non-zero t=0 sample."""
    dt = _utc(_JUN_SOLSTICE, 4)
    fc = _physics_forecast(300.0, dt, lat_deg=_AUCKLAND_LAT, utc_offset_h=_AUCKLAND_UTC)

    assert isinstance(fc, SolarForecast)
    assert fc.source == "physics"
    first_fraction = fc.samples[0][1]
    assert first_fraction > 0.0, (
        f"_physics_forecast() for Auckland at 04:00 UTC must have a non-zero "
        f"first sample; got {first_fraction:.4f}. "
        "If zero, the UTC offset was not applied in the fallback."
    )


# ---------------------------------------------------------------------------
# TZ-9  _parse_forecast() fallback — bad JSON + Auckland params uses site offset
# ---------------------------------------------------------------------------

def test_tz9_parse_forecast_fallback_uses_site_utc_offset():
    """When _parse_forecast() receives invalid JSON it falls back to _physics_forecast.

    The fallback must use the supplied lat_deg / utc_offset_h, not San Diego
    defaults, so that Auckland at 04:00 UTC still produces non-zero samples.

    This tests the three edits made in solar_sim.py to propagate site params
    through to _parse_forecast().
    """
    dt = _utc(_JUN_SOLSTICE, 4)  # 04:00 UTC = 16:00 Auckland local

    # Inject deliberate parse failure → forces physics fallback path
    fc = _parse_forecast(
        "not valid json {{{",
        sim_duration_s=300.0,
        utc_now=dt,
        lat_deg=_AUCKLAND_LAT,
        utc_offset_h=_AUCKLAND_UTC,
    )

    assert fc.source == "physics", (
        f"Expected physics fallback from bad JSON; got source={fc.source!r}"
    )
    nonzero = [f for _, f in fc.samples if f > 0.0]
    assert len(nonzero) > 0, (
        f"After bad-JSON fallback, Auckland 04:00 UTC run must have non-zero "
        f"solar samples. Got all-zero samples — site utc_offset was not propagated "
        "to _parse_forecast()."
    )


def test_tz9b_parse_forecast_fallback_wrong_offset_gives_zero():
    """Complement: same call with utc_offset_h=0 (the pre-fix default) gives zeros.

    Confirms TZ-9 really is testing the offset propagation and not an accidental pass.
    """
    dt = _utc(_JUN_SOLSTICE, 4)
    fc_broken = _parse_forecast(
        "not valid json {{{",
        sim_duration_s=300.0,
        utc_now=dt,
        lat_deg=_AUCKLAND_LAT,
        utc_offset_h=0.0,   # simulate the old hardcoded default
    )
    nonzero = [f for _, f in fc_broken.samples if f > 0.0]
    assert len(nonzero) == 0, (
        "With utc_offset_h=0 and Auckland lat, 04:00 UTC should give all-zero solar "
        f"samples (confirms TZ-9 is sensitive to the offset). Got {len(nonzero)} non-zero."
    )


# ---------------------------------------------------------------------------
# TZ-10  generate_solar_forecast() — Auckland no-key path uses site offset
# ---------------------------------------------------------------------------

def test_tz10_generate_solar_forecast_auckland_physics_path():
    """generate_solar_forecast() with no API key uses physics; site offset must apply.

    With site_utc_offset_h=+12 and utc_now=04:00 UTC, the physics fallback
    should produce non-zero samples (16:00 Auckland local = afternoon).
    """
    dt = _utc(_JUN_SOLSTICE, 4)
    with _no_mistral_key():
        fc = generate_solar_forecast(
            300.0,
            utc_now=dt,
            site_latitude=_AUCKLAND_LAT,
            site_utc_offset_h=_AUCKLAND_UTC,
            site_name="Auckland, NZ",
        )

    assert fc.source == "physics"
    nonzero = [f for _, f in fc.samples if f > 0.0]
    assert len(nonzero) > 0, (
        f"generate_solar_forecast() with Auckland site_utc_offset_h=+12 at 04:00 UTC "
        f"must produce non-zero physics-fallback samples; got all-zero. "
        "The site_utc_offset_h is not being passed to the physics path."
    )


# ---------------------------------------------------------------------------
# TZ-11  generate_solar_forecast() — San Diego at actual midnight is dark
# ---------------------------------------------------------------------------

def test_tz11_sandiego_midnight_is_dark():
    """San Diego 04:00 UTC = 20:00 local (evening). Fraction should still be non-zero
    around sunset, but 12:00 UTC = 04:00 local = true night → must be zero."""
    dt_night = _utc(_JUN_SOLSTICE, 12)  # 12:00 UTC = 04:00 San Diego = night
    with _no_mistral_key():
        fc = generate_solar_forecast(
            300.0,
            utc_now=dt_night,
            site_latitude=_SANDIEGO_LAT,
            site_utc_offset_h=_SANDIEGO_UTC,
            site_name="San Diego, CA",
        )

    # At 04:00 San Diego local (= 12:00 UTC), all 300 s of the run are deep night
    nonzero = [f for _, f in fc.samples if f > 0.0]
    assert len(nonzero) == 0, (
        f"San Diego 12:00 UTC (= 04:00 local) — all samples must be zero; "
        f"got {len(nonzero)} non-zero samples."
    )


# ---------------------------------------------------------------------------
# TZ-12  Offset symmetry — UTC+12 peak arrives 20 hours before UTC-8 peak (UTC clock)
# ---------------------------------------------------------------------------

def test_tz12_offset_shifts_peak_utc_clock():
    """Auckland noon (local 12:00 = 00:00 UTC) precedes San Diego noon (20:00 UTC).

    Checks that `generate_solar_forecast()` correctly shifts peak output on the UTC
    clock by the difference in UTC offsets (20 h for Auckland vs San Diego).
    """
    # Find peak solar fraction for Auckland: local noon = 00:00 UTC
    auckland_noon_utc   = _utc(_JUN_SOLSTICE, 0)
    auckland_off_peak   = _utc(_JUN_SOLSTICE, 20)   # 08:00 local — pre-dawn

    f_auckland_noon = _solar_fraction_at(
        auckland_noon_utc, lat_deg=_AUCKLAND_LAT, utc_offset_h=_AUCKLAND_UTC
    )
    f_auckland_offpeak = _solar_fraction_at(
        auckland_off_peak, lat_deg=_AUCKLAND_LAT, utc_offset_h=_AUCKLAND_UTC
    )

    # Auckland noon should be above off-peak
    assert f_auckland_noon > f_auckland_offpeak, (
        f"Auckland: noon (UTC 00:00) fraction {f_auckland_noon:.4f} must exceed "
        f"off-peak (UTC 20:00) fraction {f_auckland_offpeak:.4f}"
    )

    # Find peak for San Diego: local noon = 20:00 UTC
    sandiego_noon_utc  = _utc(_JUN_SOLSTICE, 20)
    sandiego_offpeak   = _utc(_JUN_SOLSTICE, 0)    # 16:00 UTC-8 = 08:00 local — pre-dawn

    f_sd_noon = _solar_fraction_at(
        sandiego_noon_utc, lat_deg=_SANDIEGO_LAT, utc_offset_h=_SANDIEGO_UTC
    )
    f_sd_offpeak = _solar_fraction_at(
        sandiego_offpeak, lat_deg=_SANDIEGO_LAT, utc_offset_h=_SANDIEGO_UTC
    )

    assert f_sd_noon > f_sd_offpeak, (
        f"San Diego: noon (UTC 20:00) fraction {f_sd_noon:.4f} must exceed "
        f"off-peak (UTC 00:00) fraction {f_sd_offpeak:.4f}"
    )


# ---------------------------------------------------------------------------
# TZ-13  Southern hemisphere summer noon matches expected physics
# ---------------------------------------------------------------------------

def test_tz13_auckland_summer_noon_high_fraction():
    """Auckland December solstice (Southern summer) noon must give a high fraction.

    local noon = 12:00 = UTC 00:00 (Dec 21).
    At lat=-36.85, Dec solstice: declination ≈ -23.45° → sin_elev at noon ≈ 0.77
    """
    dt = _utc(_DEC_SOLSTICE, 0)   # 00:00 UTC = 12:00 Auckland
    fraction = _solar_fraction_at(dt, lat_deg=_AUCKLAND_LAT, utc_offset_h=_AUCKLAND_UTC)

    # sin_elev ≈ sin(-36.85)*sin(-23.45) + cos(-36.85)*cos(-23.45)*cos(0)
    # ≈ (-0.599)*(-0.398) + (0.801)*(0.917)*1.0 ≈ 0.238 + 0.735 ≈ 0.73
    # fraction = min(1.0, 0.73 * 1.05) ≈ 0.77
    assert fraction > 0.6, (
        f"Auckland December solstice noon (UTC 00:00) should have fraction > 0.6; "
        f"got {fraction:.4f}"
    )


# ---------------------------------------------------------------------------
# TZ-14  _parse_forecast() fallback — Singapore (UTC+8) afternoon is non-zero
# ---------------------------------------------------------------------------

def test_tz14_singapore_utc_afternoon_physics_fallback():
    """Singapore UTC+8: 02:00 UTC = 10:00 local → morning solar via physics fallback."""
    dt = _utc(_JUN_SOLSTICE, 2)  # 02:00 UTC = 10:00 Singapore local
    fc = _parse_forecast(
        "bad json",
        sim_duration_s=300.0,
        utc_now=dt,
        lat_deg=_SINGAPORE_LAT,
        utc_offset_h=_SINGAPORE_UTC,
    )

    assert fc.source == "physics"
    nonzero = [f for _, f in fc.samples if f > 0.0]
    assert len(nonzero) > 0, (
        f"Singapore 02:00 UTC (= 10:00 local) physics fallback must have non-zero "
        f"solar samples; got all-zero. "
        "The site utc_offset was not propagated to _parse_forecast()."
    )
