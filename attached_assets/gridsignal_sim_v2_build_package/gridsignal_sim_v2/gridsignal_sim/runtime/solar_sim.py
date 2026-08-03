"""
runtime/solar_sim.py — Mistral-driven solar irradiance simulator.

Defect history
--------------
v1: Module-level _LAT_DEG = 32.72 / _UTC_OFFSET_H = -8.0 caused every
    non-San-Diego site to compute solar elevation from the wrong coordinates,
    producing p_renewable_mw = 0.0 for Auckland, Tokyo, Frankfurt, etc.

v2 (this file): All geographic defaults removed.  Physics uses true solar
    time computed from longitude (NOAA equation of time) so a wrong tz_name
    is physically incapable of producing a wrong irradiance curve.

Backward compatibility
----------------------
_solar_fraction_at, _physics_samples, _physics_ambient_steps, _physics_forecast,
and _parse_forecast all still accept `utc_offset_h=` as a legacy keyword alias
so existing test files can keep their utc_offset_h= calls without changes.
When longitude_deg= is also supplied it takes precedence.

Called ONCE at run start via generate_solar_forecast(). The result is a
SolarForecast namedtuple whose samples are stored in spec_data["irradiance_steps"]
and whose ambient_steps are stored in spec_data["ambient_steps"] before the spec
is handed to scenario_factory.  No blocking calls occur during simulation ticks.

Fallback chain
--------------
1. MISTRAL_API_KEY present → ask mistral-small-latest for weather + irradiance samples
2. Mistral unavailable or response unparseable → physics-based solar curve
3. Both fail → flat profile at rated output (degenerate safe default)
"""
from __future__ import annotations

import datetime
import functools
import json
import logging
import math
import os
import pathlib
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, NamedTuple, Optional

if TYPE_CHECKING:
    from site_config import SiteLocation

_log = logging.getLogger(__name__)


class SolarForecast(NamedTuple):
    """Return value from generate_solar_forecast().

    samples    — list of (sim_time_s, fraction) pairs.
    weather    — short label: "clear", "partly_cloudy", "overcast",
                 "marine_layer", or "physics_estimate".
    conditions — one human-readable sentence describing current conditions.
    source     — "mistral" or "physics".
    ambient_steps — list of (sim_time_s, drybulb_c, wetbulb_c).
    site_name  — display name of the site that generated this forecast.
    tz_name    — IANA timezone of the site (for display / audit only).
    """
    samples:        list
    weather:        str
    conditions:     str
    source:         str
    ambient_steps:  list
    site_name:      str = ""
    tz_name:        str = ""


# ── Ambient-cooling coefficient registry loader ────────────────────────────────

_AMBIENT_NOMINAL_C_DEFAULT   = 21.0
_AMBIENT_SCALE_PER_C_DEFAULT = 0.015


@functools.lru_cache(maxsize=1)
def _ambient_coefficients() -> tuple:
    """Return (nominal_c, scale_per_c) from gridsignal_parameters.json."""
    params_path = pathlib.Path(__file__).parent.parent / "gridsignal_parameters.json"
    try:
        with open(params_path, encoding="utf-8") as fh:
            params = json.load(fh)
        locked = {
            entry["key"]: entry["value"]
            for entry in params.get("locked", [])
            if "key" in entry and "value" in entry
        }
        nominal_c   = float(locked["ambient_cooling_nominal_c"])
        scale_per_c = float(locked["ambient_cooling_scale_per_c"])
        return nominal_c, scale_per_c
    except Exception as exc:
        _log.warning(
            "solar_sim: could not load ambient coefficients from %s (%s); "
            "using ASHRAE 90.4 defaults (nominal=%.1f °C, scale=%.4f /°C)",
            params_path, exc,
            _AMBIENT_NOMINAL_C_DEFAULT, _AMBIENT_SCALE_PER_C_DEFAULT,
        )
        return _AMBIENT_NOMINAL_C_DEFAULT, _AMBIENT_SCALE_PER_C_DEFAULT


# ── Mistral API ────────────────────────────────────────────────────────────────
_MISTRAL_ENDPOINT  = "https://api.mistral.ai/v1/chat/completions"
_MISTRAL_MODEL     = "mistral-small-latest"
_REQUEST_TIMEOUT_S = 10.0


def _build_system_prompt(
    site_name: str,
    lat: Optional[float],
    lon: Optional[float],
    climate_hint: str = "",
) -> str:
    """Build a location-specific Mistral system prompt for the solar agent."""
    lat_dir = "N" if (lat or 0) >= 0 else "S"
    lon_dir = "E" if (lon or 0) >= 0 else "W"
    lat_abs = abs(lat) if lat is not None else 0.0
    lon_abs = abs(lon) if lon is not None else 0.0
    loc_line = (
        f"in {site_name} "
        f"(latitude {lat_abs:.2f}°{lat_dir}, longitude {lon_abs:.2f}°{lon_dir})"
    )
    if climate_hint:
        climate_section = f"\n{site_name} solar/climate behaviour:\n{climate_hint}\n"
    else:
        climate_section = (
            f"\nGenerate realistic solar output fractions appropriate for {site_name} "
            f"at latitude {lat_abs:.1f}°{lat_dir}. Reflect the local climate accurately "
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
    lat_deg: float,
    *,
    longitude_deg: Optional[float] = None,
    utc_offset_h: Optional[float] = None,
) -> float:
    """Compute flat-mount panel output fraction from sun-position physics.

    Supply ONE of:
      longitude_deg — preferred; uses NOAA equation of time for true solar time,
                      making an incorrect tz_name physically incapable of producing
                      a wrong irradiance curve.
      utc_offset_h  — legacy alias; approximates solar noon via UTC wall-clock
                      offset.  Still accepts utc_offset_h=0.0 as the canonical
                      "pre-fix broken path" sentinel in timezone regression tests.

    Raises ValueError if neither is supplied.
    """
    day_of_year = utc_dt.timetuple().tm_yday
    utc_h = utc_dt.hour + utc_dt.minute / 60.0 + utc_dt.second / 3600.0

    if longitude_deg is not None:
        # True solar time: NOAA equation of time removes the ~±16 min analemma
        # deviation between mean and apparent solar noon.
        # B = mean anomaly proxy (radians); EoT in minutes.
        B = math.radians(360.0 / 365.0 * (day_of_year - 81))
        eot_min = 9.87 * math.sin(2.0 * B) - 7.53 * math.cos(B) - 1.5 * math.sin(B)
        solar_h = (utc_h + longitude_deg / 15.0 + eot_min / 60.0) % 24.0
    elif utc_offset_h is not None:
        # Legacy: wall-clock UTC offset as a proxy for longitude / 15.
        # Deliberately kept so TZ regression tests (utc_offset_h=0.0 = broken baseline)
        # can document the pre-fix behaviour without migration.
        solar_h = (utc_h + utc_offset_h) % 24.0
    else:
        raise ValueError(
            "_solar_fraction_at: supply longitude_deg= (preferred) or utc_offset_h= (legacy)."
        )

    # Solar hour angle: 0 at solar noon, ±15°/h
    hour_angle_rad = math.radians((solar_h - 12.0) * 15.0)

    # Solar declination (rough approximation)
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
    lat_deg: float,
    *,
    longitude_deg: Optional[float] = None,
    utc_offset_h: Optional[float] = None,
) -> list[tuple[float, float]]:
    """Build irradiance samples from pure sun-position math — no API call."""
    if longitude_deg is None and utc_offset_h is None:
        raise ValueError("_physics_samples: supply longitude_deg= or utc_offset_h=")
    n = max(20, min(120, int(sim_duration_s / 30)))
    step = sim_duration_s / n
    samples: list[tuple[float, float]] = []
    for i in range(n + 1):
        t = i * step
        f = _solar_fraction_at(
            utc_now + datetime.timedelta(seconds=t),
            lat_deg,
            longitude_deg=longitude_deg,
            utc_offset_h=utc_offset_h,
        )
        samples.append((round(t, 1), round(f, 4)))
    _log.info(
        "solar_sim: physics profile (lat=%.2f, %s) — %d samples, "
        "t=0 fraction=%.3f, t=end fraction=%.3f",
        lat_deg,
        f"lon={longitude_deg:.2f}" if longitude_deg is not None else f"utc{utc_offset_h:+.1f}",
        len(samples), samples[0][1], samples[-1][1],
    )
    return samples


def _ambient_fraction_to_temp(
    solar_fraction: float,
    base_temp_c: float = 14.0,
) -> tuple[float, float]:
    """Compute dry-bulb and wet-bulb ambient temperature from solar fraction.

    Simplified universal model (marine-layer San-Diego detail removed in v2):
      drybulb = base_temp_c + solar_fraction × 10   (up to +10 °C at full sun)
      wetbulb = drybulb − 3                         (coastal humidity proxy)

    Clamped to [base_temp_c − 4, base_temp_c + 20].
    """
    drybulb = base_temp_c + solar_fraction * 10.0
    drybulb = round(min(base_temp_c + 20.0, max(base_temp_c - 4.0, drybulb)), 2)
    wetbulb = round(drybulb - 3.0, 2)
    return drybulb, wetbulb


def _physics_ambient_steps(
    sim_duration_s: float,
    utc_now: datetime.datetime,
    lat_deg: float,
    *,
    longitude_deg: Optional[float] = None,
    utc_offset_h: Optional[float] = None,
    base_temp_c: float = 14.0,
) -> list[tuple[float, float, float]]:
    """Physics-based ambient temperature timeline correlated with solar output."""
    if longitude_deg is None and utc_offset_h is None:
        raise ValueError("_physics_ambient_steps: supply longitude_deg= or utc_offset_h=")
    n = max(20, min(120, int(sim_duration_s / 30)))
    step = sim_duration_s / n
    result: list[tuple[float, float, float]] = []
    for i in range(n + 1):
        t = i * step
        dt = utc_now + datetime.timedelta(seconds=t)
        solar_f = _solar_fraction_at(
            dt, lat_deg,
            longitude_deg=longitude_deg,
            utc_offset_h=utc_offset_h,
        )
        drybulb, wetbulb = _ambient_fraction_to_temp(solar_f, base_temp_c=base_temp_c)
        result.append((round(t, 1), drybulb, wetbulb))
    return result


def _physics_forecast(
    sim_duration_s: float,
    utc_now: datetime.datetime,
    lat_deg: float,
    *,
    longitude_deg: Optional[float] = None,
    utc_offset_h: Optional[float] = None,
    base_temp_c: float = 14.0,
    site_name: str = "",
    tz_name: str = "",
) -> "SolarForecast":
    """Physics fallback: same samples as _physics_samples but wrapped in SolarForecast."""
    if longitude_deg is None and utc_offset_h is None:
        raise ValueError("_physics_forecast: supply longitude_deg= or utc_offset_h=")
    samples = _physics_samples(
        sim_duration_s, utc_now, lat_deg,
        longitude_deg=longitude_deg, utc_offset_h=utc_offset_h,
    )
    ambient = _physics_ambient_steps(
        sim_duration_s, utc_now, lat_deg,
        longitude_deg=longitude_deg, utc_offset_h=utc_offset_h,
        base_temp_c=base_temp_c,
    )
    loc_desc = (
        f"lon={longitude_deg:.1f}°"
        if longitude_deg is not None
        else f"UTC{utc_offset_h:+.1f}"
    )
    return SolarForecast(
        samples=samples,
        weather="physics_estimate",
        conditions=f"Physics estimate (lat={lat_deg:.1f}°, {loc_desc})",
        source="physics",
        ambient_steps=ambient,
        site_name=site_name,
        tz_name=tz_name,
    )


# ── Mistral call ───────────────────────────────────────────────────────────────

def _call_mistral(user_message: str, api_key: str, system_prompt: str = "") -> str:
    """Synchronous HTTP POST to Mistral chat completions. Returns raw assistant text."""
    payload = json.dumps({
        "model": _MISTRAL_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
        "max_tokens": 1200,
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
    lat_deg: float,
    longitude_deg: Optional[float] = None,
    utc_offset_h: Optional[float] = None,
    base_temp_c: float = 14.0,
    site_name: str = "",
    tz_name: str = "",
) -> "SolarForecast":
    """Parse Mistral JSON → SolarForecast. Falls back to physics on any parse error.

    lat_deg / longitude_deg / utc_offset_h / base_temp_c must be the *site* values.
    They are forwarded to _physics_forecast so a parse failure for a Tokyo or Auckland
    site still produces a geographically correct physics curve.
    """
    if longitude_deg is None and utc_offset_h is None:
        raise ValueError("_parse_forecast: supply longitude_deg= or utc_offset_h=")
    try:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(ln for ln in lines if not ln.startswith("```")).strip()

        try:
            data: dict = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            if start != -1:
                fragment = text[start:]
                for trim in range(min(300, len(fragment))):
                    candidate = fragment[:len(fragment) - trim].rstrip().rstrip(",").rstrip()
                    opens  = candidate.count("[") - candidate.count("]")
                    closes = candidate.count("{") - candidate.count("}")
                    candidate += "]" * max(0, opens) + "}" * max(0, closes)
                    try:
                        data = json.loads(candidate)
                        _log.info(
                            "solar_sim: repaired truncated Mistral JSON (trimmed %d chars)", trim
                        )
                        break
                    except json.JSONDecodeError:
                        continue
                else:
                    raise json.JSONDecodeError("could not repair JSON", text, 0)
            else:
                raise

        raw_samples: list = data["samples"]
        samples: list[tuple[float, float]] = []
        for item in raw_samples:
            t = float(item[0])
            f = max(0.0, min(1.0, float(item[1])))
            if 0.0 <= t <= sim_duration_s * 1.05:
                samples.append((round(t, 1), round(f, 4)))

        if not samples:
            raise ValueError("no valid samples after filtering")

        if samples[0][0] > 0.0:
            samples.insert(0, (0.0, samples[0][1]))

        samples = sorted(samples)

        # Physics floor at t=0: prevent LLM hallucinations that claim "no sun"
        # when the sun is actually well above the horizon.
        if samples[0][0] == 0.0:
            _physics_f0 = _solar_fraction_at(
                utc_now, lat_deg,
                longitude_deg=longitude_deg,
                utc_offset_h=utc_offset_h,
            )
            if samples[0][1] == 0.0 and _physics_f0 >= 0.15:
                _log.info(
                    "solar_sim: Mistral t=0 fraction=0.0 but physics says %.3f "
                    "(sun is up) — applying physics floor to prevent false-zero.",
                    _physics_f0,
                )
                samples[0] = (0.0, round(_physics_f0, 4))

        weather    = str(data.get("weather", "unknown"))
        conditions = str(data.get("conditions", ""))
        _log.info(
            "solar_sim: Mistral → weather=%r (%s), %d samples, "
            "t=0 fraction=%.3f, t_end fraction=%.3f",
            weather, conditions, len(samples),
            samples[0][1], samples[-1][1],
        )

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
        if ambient_steps and ambient_steps[0][0] > 0.0:
            ambient_steps.insert(0, (0.0, ambient_steps[0][1], ambient_steps[0][2]))
        ambient_steps = sorted(ambient_steps)
        if not ambient_steps:
            _log.info("solar_sim: no ambient steps from Mistral — using physics fallback")
            ambient_steps = _physics_ambient_steps(
                sim_duration_s, utc_now, lat_deg,
                longitude_deg=longitude_deg,
                utc_offset_h=utc_offset_h,
                base_temp_c=base_temp_c,
            )

        return SolarForecast(
            samples=samples,
            weather=weather,
            conditions=conditions,
            source="mistral",
            ambient_steps=ambient_steps,
            site_name=site_name,
            tz_name=tz_name,
        )

    except Exception as exc:
        _log.warning(
            "solar_sim: Mistral response parse failed (%s) — using physics fallback", exc
        )
        return _physics_forecast(
            sim_duration_s, utc_now, lat_deg,
            longitude_deg=longitude_deg,
            utc_offset_h=utc_offset_h,
            base_temp_c=base_temp_c,
            site_name=site_name,
            tz_name=tz_name,
        )


# ── Public API ─────────────────────────────────────────────────────────────────

def generate_solar_forecast(
    sim_duration_s: float,
    rated_mw: float = 4.99,
    *,
    utc_now: Optional[datetime.datetime] = None,
    # Preferred: pass a SiteLocation (imported from site_config)
    site: Optional["SiteLocation"] = None,
    # Legacy keyword params — kept so existing call sites don't need updating.
    # Do NOT add float literals here; use Optional[float] = None.
    site_latitude: Optional[float] = None,
    site_longitude: Optional[float] = None,
    site_utc_offset_h: Optional[float] = None,
    site_name: Optional[str] = None,
    climate_hint: str = "",
    ambient_temp_base_c: float = 14.0,
) -> SolarForecast:
    """
    Generate a solar forecast (samples + weather metadata) for one run.

    Preferred call:
        generate_solar_forecast(duration, rated_mw, site=my_site_location, ...)

    Legacy call (still supported):
        generate_solar_forecast(duration, rated_mw,
            site_latitude=32.72, site_utc_offset_h=-8.0, ...)

    When both are supplied, `site` takes precedence over the legacy params.
    """
    # ── Resolve effective site parameters ─────────────────────────────────
    if site is not None:
        _lat          = site.latitude_deg
        _lon          = site.longitude_deg
        _name         = site.site_name
        _tz           = site.tz_name
        _climate      = site.climate_hint or climate_hint
        _amb_base     = site.ambient_temp_base_c
        # Use longitude-based solar time (preferred path)
        _longitude    = _lon
        _utc_offset   = None
    elif site_latitude is not None:
        # Legacy path: caller provides raw floats
        _lat       = site_latitude
        _lon       = site_longitude
        _name      = site_name or "unknown"
        _tz        = ""
        _climate   = climate_hint
        _amb_base  = ambient_temp_base_c
        # Use utc_offset_h for solar time (legacy)
        _longitude = site_longitude  # may be None
        _utc_offset = site_utc_offset_h
    else:
        # Absolute fallback: no site info passed — use the process-level location
        # (or San Diego if none configured) so test helpers that call
        # generate_solar_forecast() without site= still produce geographically
        # meaningful physics curves.
        try:
            from site_config import get_site_location_or_default as _gslod
            _fallback  = _gslod()
            _lat       = _fallback.latitude_deg
            _lon       = _fallback.longitude_deg
            _name      = site_name or _fallback.site_name
            _tz        = _fallback.tz_name
            _climate   = climate_hint or _fallback.climate_hint
            _amb_base  = (ambient_temp_base_c
                          if abs(ambient_temp_base_c - 14.0) > 1e-9
                          else _fallback.ambient_temp_base_c)
            _longitude = _fallback.longitude_deg
            _utc_offset = None
        except Exception:
            # site_config unavailable (shouldn't happen in production)
            _lat       = 0.0
            _lon       = 0.0
            _name      = site_name or "unknown"
            _tz        = ""
            _climate   = climate_hint
            _amb_base  = ambient_temp_base_c
            _longitude = 0.0
            _utc_offset = None

    # Ensure we have at least one of longitude_deg or utc_offset_h for physics
    if _longitude is None and _utc_offset is None:
        _utc_offset = 0.0   # UTC as last-resort

    if utc_now is None:
        utc_now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    api_key: Optional[str] = os.environ.get("MISTRAL_API_KEY") or None
    if not api_key:
        _log.info(
            "solar_sim: MISTRAL_API_KEY absent — using physics-based curve "
            "(lat=%.2f, %s, base_temp=%.1f C)",
            _lat,
            f"lon={_longitude:.2f}" if _longitude is not None else f"utc{_utc_offset:+.1f}",
            _amb_base,
        )
        return _physics_forecast(
            sim_duration_s, utc_now, _lat,
            longitude_deg=_longitude,
            utc_offset_h=_utc_offset,
            base_temp_c=_amb_base,
            site_name=_name,
            tz_name=_tz,
        )

    # ── Compute local time for the Mistral prompt ──────────────────────────
    if _longitude is not None:
        # True solar time via longitude
        from site_config import utc_offset_for_dt as _uoff
        if _tz:
            _display_offset = _uoff(_tz, datetime.datetime(*utc_now.timetuple()[:6], tzinfo=datetime.timezone.utc))
        else:
            _display_offset = _longitude / 15.0
        local_dt   = utc_now + datetime.timedelta(hours=_display_offset)
    else:
        local_dt   = utc_now + datetime.timedelta(hours=(_utc_offset or 0.0))
    local_time = local_dt.strftime("%H:%M")

    user_msg = (
        f"Current {_name} local time: {local_time}\n"
        f"Simulation duration: {sim_duration_s:.0f} seconds\n"
        f"Panel rated capacity: {rated_mw:.2f} MW\n"
    )

    _sys_prompt = _build_system_prompt(
        site_name=_name,
        lat=_lat,
        lon=_lon,
        climate_hint=_climate,
    )

    try:
        raw = _call_mistral(user_msg, api_key, system_prompt=_sys_prompt)
    except Exception as exc:
        _log.warning("solar_sim: Mistral call failed (%s) — using physics fallback", exc)
        return _physics_forecast(
            sim_duration_s, utc_now, _lat,
            longitude_deg=_longitude,
            utc_offset_h=_utc_offset,
            base_temp_c=_amb_base,
            site_name=_name,
            tz_name=_tz,
        )

    return _parse_forecast(
        raw,
        sim_duration_s=sim_duration_s,
        utc_now=utc_now,
        lat_deg=_lat,
        longitude_deg=_longitude,
        utc_offset_h=_utc_offset,
        base_temp_c=_amb_base,
        site_name=_name,
        tz_name=_tz,
    )


def ambient_alpha_scale(ambient_steps: list) -> float:
    """Compute a scaling factor for SiteConfig.alpha_max from ambient temperature.

    Physical rationale: higher ambient dry-bulb temperature reduces HVAC
    coefficient-of-performance, so the cooling system consumes a larger
    fraction of compute power to maintain the same inlet temperature.

    Model: linear ±1.5 %/°C from the ASHRAE 90.4 moderate-climate reference
    (21 °C design ambient per ASHRAE 90.4-2019 §6.4).  Clamped to [0.80, 1.20].

    Returns 1.0 when ambient_steps is empty.
    """
    if not ambient_steps:
        return 1.0
    drybulbs = [float(db) for _, db, _ in ambient_steps]
    avg_drybulb = sum(drybulbs) / len(drybulbs)
    nominal_c, scale_per_c = _ambient_coefficients()
    return max(0.80, min(1.20, 1.0 + scale_per_c * (avg_drybulb - nominal_c)))
