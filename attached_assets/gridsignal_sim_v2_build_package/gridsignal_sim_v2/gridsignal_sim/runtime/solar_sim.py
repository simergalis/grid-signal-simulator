"""
runtime/solar_sim.py — Mistral-driven solar irradiance simulator for San Diego, CA.

Called ONCE at run start via generate_solar_forecast(). The result is a SolarForecast
namedtuple whose samples are stored in spec_data["irradiance_steps"] and whose
ambient_steps are stored in spec_data["ambient_steps"] before the spec is handed
to scenario_factory.  No blocking calls occur during simulation ticks.

Fallback chain
--------------
1. MISTRAL_API_KEY present → ask mistral-small-latest for weather + irradiance samples
2. Mistral unavailable or response unparseable → physics-based San Diego solar curve
3. Both fail → flat profile at rated output (degenerate safe default)

Why keep this in runtime/ (not api/)
-------------------------------------
The module is a pure computation helper that could equally be called from tests or
a standalone script.  Placing it in runtime/ avoids importing from the api/ plane
and keeps the dependency graph clean (§21.1).

San Diego parameters
--------------------
Lat 32.72°N, Lon 117.16°W.
UTC offset −8 h (PST — simplified, does not track DST).
Typical conditions: marine layer until ~10 am, clear afternoons, mild cloud events.
"""
from __future__ import annotations

import datetime
import json
import logging
import math
import os
import urllib.error
import urllib.request
from typing import NamedTuple, Optional


class SolarForecast(NamedTuple):
    """Return value from generate_solar_forecast().

    samples    — list of (sim_time_s, fraction) pairs.
    weather    — short label: "clear", "partly_cloudy", "overcast",
                 "marine_layer", or "physics_estimate".
    conditions — one human-readable sentence describing current conditions.
    source     — "mistral" or "physics".
    """
    samples:        list
    weather:        str
    conditions:     str
    source:         str
    ambient_steps:  list  # list of (sim_time_s, drybulb_c, wetbulb_c) — correlated with solar

_log = logging.getLogger(__name__)

# ── San Diego constants ────────────────────────────────────────────────────────
_LAT_DEG      = 32.72   # degrees North
_UTC_OFFSET_H = -8.0    # PST (UTC-8); simplified, no DST correction

# ── Mistral API ────────────────────────────────────────────────────────────────
_MISTRAL_ENDPOINT  = "https://api.mistral.ai/v1/chat/completions"
_MISTRAL_MODEL     = "mistral-small-latest"
_REQUEST_TIMEOUT_S = 10.0

def _build_system_prompt(
    site_name: str = "San Diego, CA",
    lat: float = 32.72,
    lon: float = -117.16,
    climate_hint: str = "",
) -> str:
    """Build a location-specific Mistral system prompt for the solar agent.

    When a climate_hint is supplied (from the geocoder) it is injected directly
    so Mistral uses real local conditions.  Without a hint Mistral falls back to
    its own training knowledge for the named location and coordinates.
    """
    lat_dir = "N" if lat >= 0 else "S"
    lon_dir = "E" if lon >= 0 else "W"
    loc_line = (
        f"in {site_name} "
        f"(latitude {abs(lat):.2f}°{lat_dir}, longitude {abs(lon):.2f}°{lon_dir})"
    )
    if climate_hint:
        climate_section = f"\n{site_name} solar/climate behaviour:\n{climate_hint}\n"
    else:
        climate_section = (
            f"\nGenerate realistic solar output fractions appropriate for {site_name} "
            f"at latitude {abs(lat):.1f}°{lat_dir}. Reflect the local climate accurately "
            f"(cloud cover patterns, humidity, seasonal insolation, any regional phenomena).\n"
        )
    return (
        f"You are a solar irradiance simulator for a fixed-mount photovoltaic installation\n"
        f"{loc_line}.\n\n"
        f"You receive the current local {site_name} time and a simulation duration in "
        f"seconds, and you must output realistic solar panel output fractions for that period.\n\n"
        f"Fraction = actual_output / rated_capacity, range [0.0, 1.0].\n"
        f"{climate_section}\n"
        f"Return ONLY valid JSON with no markdown fences and no explanation outside the JSON:\n"
        f"{{\n"
        f'  "weather": "<clear|partly_cloudy|overcast|marine_layer|rain|fog|thunderstorm>",\n'
        f'  "conditions": "<one sentence describing current conditions>",\n'
        f'  "samples": [[sim_time_s, fraction], ...],\n'
        f'  "ambient": [[sim_time_s, drybulb_c, wetbulb_c], ...]\n'
        f"}}\n\n"
        f"Provide 15-25 samples spanning sim_time_s = 0 to sim_duration_s (inclusive).\n"
        f"The first sample in both \"samples\" and \"ambient\" MUST be at sim_time_s = 0.\n"
        f"All sim_time_s values must be non-negative and <= sim_duration_s.\n"
        f"Fractions must be in [0.0, 1.0].\n\n"
        f"Ambient dry-bulb temperatures must be physically realistic for {site_name}.\n"
        f"Ambient temperature is physically correlated with solar fraction — generate them together.\n"
        f"Wet-bulb is typically 2-6 C below dry-bulb (adjust for local humidity).\n"
    )


# ── Physics-based fallback ─────────────────────────────────────────────────────

def _solar_fraction_at(
    utc_dt: datetime.datetime,
    lat_deg: float = _LAT_DEG,
    utc_offset_h: float = _UTC_OFFSET_H,
) -> float:
    """Compute flat-mount panel output fraction from sun-position physics."""
    local_h = (
        utc_dt.hour + utc_dt.minute / 60.0 + utc_dt.second / 3600.0 + utc_offset_h
    ) % 24.0

    # Solar hour angle: 0 at solar noon, ±15°/h
    hour_angle_rad = math.radians((local_h - 12.0) * 15.0)

    # Solar declination (rough approximation)
    day_of_year = utc_dt.timetuple().tm_yday
    decl_rad = math.radians(
        23.45 * math.sin(math.radians(360.0 / 365.0 * (day_of_year - 81)))
    )

    lat_rad = math.radians(lat_deg)
    sin_elev = (
        math.sin(lat_rad) * math.sin(decl_rad)
        + math.cos(lat_rad) * math.cos(decl_rad) * math.cos(hour_angle_rad)
    )
    if sin_elev <= 0.0:
        return 0.0

    # Flat-mount panel output ∝ sin(elevation); 1.05 accounts for diffuse sky.
    return min(1.0, sin_elev * 1.05)


def _physics_samples(
    sim_duration_s: float,
    utc_now: datetime.datetime,
    lat_deg: float = _LAT_DEG,
    utc_offset_h: float = _UTC_OFFSET_H,
) -> list[tuple[float, float]]:
    """Build irradiance samples from pure sun-position math — no API call."""
    n = max(20, min(120, int(sim_duration_s / 30)))
    step = sim_duration_s / n
    samples: list[tuple[float, float]] = []
    for i in range(n + 1):
        t = i * step
        f = _solar_fraction_at(
            utc_now + datetime.timedelta(seconds=t),
            lat_deg=lat_deg,
            utc_offset_h=utc_offset_h,
        )
        samples.append((round(t, 1), round(f, 4)))
    _log.info(
        "solar_sim: physics profile (lat=%.2f, utc%+.1f) — %d samples, "
        "t=0 fraction=%.3f, t=end fraction=%.3f",
        lat_deg, utc_offset_h, len(samples), samples[0][1], samples[-1][1],
    )
    return samples




def _ambient_fraction_to_temp(
    solar_fraction: float,
    local_h: float,
    base_temp_c: float = 14.0,
) -> tuple[float, float]:
    """Compute dry-bulb and wet-bulb ambient temperature from solar fraction and hour.

    Correlation model:
    - Night (solar=0): base_temp_c
    - Marine-layer mornings: +2 C above base (reduced by solar absence)
    - Clear afternoons: up to +10 C above base correlated with solar output
    Wet-bulb ≈ dry-bulb − 3 C (coastal humidity approximation).
    """
    drybulb = base_temp_c + solar_fraction * 10.0
    if 6.0 <= local_h <= 11.0 and solar_fraction < 0.4:
        drybulb += 2.0
    drybulb = round(min(base_temp_c + 20.0, max(base_temp_c - 4.0, drybulb)), 2)
    wetbulb = round(drybulb - 3.0, 2)
    return drybulb, wetbulb


def _physics_ambient_steps(
    sim_duration_s: float,
    utc_now: "datetime.datetime",
    lat_deg: float = _LAT_DEG,
    utc_offset_h: float = _UTC_OFFSET_H,
    base_temp_c: float = 14.0,
) -> list[tuple[float, float, float]]:
    """Physics-based ambient temperature timeline correlated with solar output."""
    n = max(20, min(120, int(sim_duration_s / 30)))
    step = sim_duration_s / n
    result: list[tuple[float, float, float]] = []
    for i in range(n + 1):
        t = i * step
        dt = utc_now + datetime.timedelta(seconds=t)
        local_h = (
            dt.hour + dt.minute / 60.0 + dt.second / 3600.0 + utc_offset_h
        ) % 24.0
        solar_f = _solar_fraction_at(dt, lat_deg=lat_deg, utc_offset_h=utc_offset_h)
        drybulb, wetbulb = _ambient_fraction_to_temp(solar_f, local_h, base_temp_c=base_temp_c)
        result.append((round(t, 1), drybulb, wetbulb))
    return result


def _physics_forecast(
    sim_duration_s: float,
    utc_now: datetime.datetime,
    lat_deg: float = _LAT_DEG,
    utc_offset_h: float = _UTC_OFFSET_H,
    base_temp_c: float = 14.0,
) -> "SolarForecast":
    """Physics fallback: same samples as _physics_samples but wrapped in SolarForecast."""
    samples = _physics_samples(sim_duration_s, utc_now, lat_deg=lat_deg, utc_offset_h=utc_offset_h)
    ambient = _physics_ambient_steps(
        sim_duration_s, utc_now,
        lat_deg=lat_deg, utc_offset_h=utc_offset_h, base_temp_c=base_temp_c,
    )
    return SolarForecast(
        samples=samples,
        weather="physics_estimate",
        conditions=f"Physics estimate (lat={lat_deg:.1f}°, UTC{utc_offset_h:+.1f})",
        source="physics",
        ambient_steps=ambient,
    )


# ── Mistral call ───────────────────────────────────────────────────────────────

def _call_mistral(user_message: str, api_key: str, system_prompt: str = "") -> str:
    """Synchronous HTTP POST to Mistral chat completions. Returns raw assistant text."""
    payload = json.dumps({
        "model": _MISTRAL_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt or _build_system_prompt()},
            {"role": "user",   "content": user_message},
        ],
        "max_tokens": 700,
        # temperature > 0 gives varied weather across runs — intentional.
        # Determinism is preserved at the run level because samples are stored once
        # and used throughout the run; they are never regenerated mid-run.
        "temperature": 0.5,
    }).encode()
    req = urllib.request.Request(
        _MISTRAL_ENDPOINT,
        data=payload,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT_S) as resp:
            body = json.loads(resp.read())
        return body["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Mistral HTTP {exc.code}: {exc.read()[:300]}") from exc


def _parse_forecast(
    raw: str,
    *,
    sim_duration_s: float,
    utc_now: datetime.datetime,
    lat_deg: float = _LAT_DEG,
    utc_offset_h: float = _UTC_OFFSET_H,
    base_temp_c: float = 14.0,
) -> "SolarForecast":
    """Parse Mistral JSON → SolarForecast. Falls back to physics on any parse error.

    lat_deg / utc_offset_h / base_temp_c must be the *site* values, not the
    San Diego defaults.  They are forwarded to _physics_forecast and
    _physics_ambient_steps so that a parse failure for a Tokyo or Auckland site
    still produces a geographically correct physics curve rather than silently
    reverting to the San Diego night-time baseline.
    """
    try:
        text = raw.strip()
        # Strip markdown code fences if the model wrapped the response
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(ln for ln in lines if not ln.startswith("```")).strip()

        data: dict = json.loads(text)
        raw_samples: list = data["samples"]

        samples: list[tuple[float, float]] = []
        for item in raw_samples:
            t = float(item[0])
            f = max(0.0, min(1.0, float(item[1])))
            # 5% tolerance on duration (Mistral sometimes rounds end time slightly)
            if 0.0 <= t <= sim_duration_s * 1.05:
                samples.append((round(t, 1), round(f, 4)))

        if not samples:
            raise ValueError("no valid samples after filtering")

        # Guarantee a t=0 anchor
        if samples[0][0] > 0.0:
            samples.insert(0, (0.0, samples[0][1]))

        samples = sorted(samples)
        weather    = str(data.get("weather", "unknown"))
        conditions = str(data.get("conditions", ""))
        _log.info(
            "solar_sim: Mistral → weather=%r (%s), %d samples, "
            "t=0 fraction=%.3f, t_end fraction=%.3f",
            weather, conditions, len(samples),
            samples[0][1], samples[-1][1],
        )
        # Parse correlated ambient temperature steps
        raw_ambient: list = data.get("ambient", [])
        ambient_steps: list[tuple[float, float, float]] = []
        for item in raw_ambient:
            try:
                ta = float(item[0])
                db = float(item[1])
                wb = float(item[2])
                if 0.0 <= ta <= sim_duration_s * 1.05:
                    ambient_steps.append((round(ta, 1), round(db, 2), round(wb, 2)))
            except (IndexError, TypeError, ValueError):
                continue
        # Guarantee a t=0 anchor
        if ambient_steps and ambient_steps[0][0] > 0.0:
            ambient_steps.insert(0, (0.0, ambient_steps[0][1], ambient_steps[0][2]))
        ambient_steps = sorted(ambient_steps)
        if not ambient_steps:
            _log.info("solar_sim: no ambient steps from Mistral — using physics fallback for ambient")
            ambient_steps = _physics_ambient_steps(
                sim_duration_s, utc_now,
                lat_deg=lat_deg, utc_offset_h=utc_offset_h, base_temp_c=base_temp_c,
            )

        return SolarForecast(
            samples=samples,
            weather=weather,
            conditions=conditions,
            source="mistral",
            ambient_steps=ambient_steps,
        )

    except Exception as exc:
        _log.warning(
            "solar_sim: Mistral response parse failed (%s) — using physics fallback "
            "(lat=%.2f, utc%+.1f)", exc, lat_deg, utc_offset_h,
        )
        return _physics_forecast(
            sim_duration_s, utc_now,
            lat_deg=lat_deg, utc_offset_h=utc_offset_h, base_temp_c=base_temp_c,
        )


def _parse_samples(
    raw: str,
    *,
    sim_duration_s: float,
    utc_now: datetime.datetime,
) -> list[tuple[float, float]]:
    """Backward-compat shim: parse Mistral JSON → sample list only."""
    return _parse_forecast(raw, sim_duration_s=sim_duration_s, utc_now=utc_now).samples


# ── Public API ─────────────────────────────────────────────────────────────────

def generate_solar_forecast(
    sim_duration_s: float,
    rated_mw: float = 4.99,
    *,
    utc_now: Optional[datetime.datetime] = None,
    site_latitude: float = _LAT_DEG,
    site_longitude: float = -117.16,
    site_utc_offset_h: float = _UTC_OFFSET_H,
    site_name: str = "San Diego, CA",
    climate_hint: str = "",
    ambient_temp_base_c: float = 14.0,
) -> SolarForecast:
    """
    Generate a solar forecast (samples + weather metadata) for one run.

    Calls Mistral (mistral-small-latest) once with the current local time
    and simulation duration to produce a weather-aware irradiance curve.

    Returns a ``SolarForecast`` namedtuple with:
    - ``samples``    — list of (sim_time_s, fraction) pairs
    - ``weather``    — short label ("clear", "partly_cloudy", …, "physics_estimate")
    - ``conditions`` — one sentence describing current conditions
    - ``source``     — "mistral" or "physics"

    Falls back silently to a physics-based solar curve if:
    - ``MISTRAL_API_KEY`` is not set in the environment
    - The API call fails or times out
    - The response cannot be parsed into valid samples

    Parameters
    ----------
    sim_duration_s : float
        Total simulation duration in seconds.
    rated_mw : float
        Panel rated capacity in MW — included in the Mistral prompt for context.
    utc_now : datetime.datetime | None
        Current UTC time. Defaults to now. Override in tests for determinism.
    site_latitude : float
        Site latitude in degrees North (default 32.72 = San Diego).
        Used by the physics fallback for solar elevation calculations.
    site_utc_offset_h : float
        UTC offset in hours (default -8.0 = PST). Used to compute local solar time.
    ambient_temp_base_c : float
        Nighttime dry-bulb base temperature in °C (default 14.0).
        Used by the physics fallback ambient model.
    """
    if utc_now is None:
        utc_now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    api_key: Optional[str] = os.environ.get("MISTRAL_API_KEY") or None
    if not api_key:
        _log.info(
            "solar_sim: MISTRAL_API_KEY absent — using physics-based curve "
            "(lat=%.2f, UTC%+.1f, base_temp=%.1f C)",
            site_latitude, site_utc_offset_h, ambient_temp_base_c,
        )
        return _physics_forecast(
            sim_duration_s, utc_now,
            lat_deg=site_latitude,
            utc_offset_h=site_utc_offset_h,
            base_temp_c=ambient_temp_base_c,
        )

    local_dt   = utc_now + datetime.timedelta(hours=site_utc_offset_h)
    local_time = local_dt.strftime("%H:%M")

    user_msg = (
        f"Current {site_name} local time: {local_time}\n"
        f"Simulation duration: {sim_duration_s:.0f} seconds\n"
        f"Panel rated capacity: {rated_mw:.2f} MW\n"
    )

    _sys_prompt = _build_system_prompt(
        site_name=site_name,
        lat=site_latitude,
        lon=site_longitude,
        climate_hint=climate_hint,
    )

    try:
        raw = _call_mistral(user_msg, api_key, system_prompt=_sys_prompt)
    except Exception as exc:
        _log.warning("solar_sim: Mistral call failed (%s) — using physics fallback", exc)
        return _physics_forecast(
            sim_duration_s, utc_now,
            lat_deg=site_latitude,
            utc_offset_h=site_utc_offset_h,
            base_temp_c=ambient_temp_base_c,
        )

    return _parse_forecast(
        raw,
        sim_duration_s=sim_duration_s,
        utc_now=utc_now,
        lat_deg=site_latitude,
        utc_offset_h=site_utc_offset_h,
        base_temp_c=ambient_temp_base_c,
    )


def generate_irradiance_samples(
    sim_duration_s: float,
    rated_mw: float = 4.99,
    *,
    utc_now: Optional[datetime.datetime] = None,
) -> list[tuple[float, float]]:
    """Backward-compat shim — returns samples only.  Prefer generate_solar_forecast()."""
    return generate_solar_forecast(
        sim_duration_s, rated_mw, utc_now=utc_now
    ).samples


def ambient_alpha_scale(ambient_steps: list) -> float:
    """Compute a scaling factor for SiteConfig.alpha_max from ambient temperature.

    Physical rationale: higher ambient dry-bulb temperature reduces HVAC
    coefficient-of-performance, so the cooling system consumes a larger
    fraction of compute power to maintain the same inlet temperature.

    Model: linear ±1 %/°C from the San Diego nominal (19 °C mid-range,
    midpoint of the 14–24 °C daytime range).  Clamped to [0.80, 1.20]
    to prevent extreme extrapolation outside the San Diego climate envelope.

    PROTO-32-AMB: linear coefficient has no measured basis; calibrate against
    facility ASHRAE data before production use.

    Returns 1.0 when ambient_steps is empty — backward-compatible: runs
    that were started without a solar forecast or ambient timeline are
    unaffected (alpha_max stays at its spec-defined default).
    """
    if not ambient_steps:
        return 1.0
    drybulbs = [float(db) for _, db, _ in ambient_steps]
    avg_drybulb = sum(drybulbs) / len(drybulbs)
    _NOMINAL_C   = 19.0   # mid-range of San Diego daytime dry-bulb (°C)
    _SCALE_PER_C = 0.010  # 1 %/°C deviation from nominal — PROTO-32-AMB
    return max(0.80, min(1.20, 1.0 + _SCALE_PER_C * (avg_drybulb - _NOMINAL_C)))
