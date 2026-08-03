---
name: solar-sim-mistral
description: Mistral-driven San Diego solar PV simulation — architecture, injection point, fallback chain, and why the factory stays untouched.
---

# Solar PV simulation via Mistral (San Diego, CA)

## Rule
`generate_solar_forecast()` (preferred) or `generate_irradiance_samples()` (shim) are called
ONCE at run start in the API layer, not inside the factory. The factory
(`scenario_factory.build_run_context_from_spec`) stays deterministic — it reads whatever
`irradiance_steps` is in spec_data.

**Why:** The determinism gate and all unit tests call the factory directly (no API),
so they never hit Mistral. If the call were inside the factory, every determinism
run would get a different solar profile and fail.

## SolarForecast return type
`generate_solar_forecast()` returns a `SolarForecast` namedtuple:
  - `samples`    — list of (sim_time_s, fraction) pairs
  - `weather`    — "clear" | "partly_cloudy" | "overcast" | "marine_layer" | "physics_estimate"
  - `conditions` — one human-readable sentence (e.g. "Marine layer reducing output 35%")
  - `source`     — "mistral" or "physics"

`generate_irradiance_samples()` is a backward-compat shim that returns `forecast.samples` only.

## Injection point
`api/routes/runs.py` — scenario_id path, between `spec_data = json.loads(...)` and
`build_run_context_from_spec(...)`.

Trigger condition: `solar_rated_mw > 0` AND `irradiance_steps` == bare default
`[[0.0, 1.0]]` (len=1, t=0, f=1.0). Any explicitly set `irradiance_steps` (e.g.
TC-33 step-drop scenario) passes through untouched.

After the call, `forecast.weather` and `forecast.conditions` are stored on:
  - `ctx.solar_weather` and `ctx.solar_conditions` (RunContext)
  - Stamped onto every TickResult via the thermal `_dc_replace()` call in the run loop
  - Serialised by `_tick_result_to_dict()` as `"solar_weather"` / `"solar_conditions"`
  - Declared on `TickPayload` in `frontend/src/types.ts`
  - Rendered in renewable.ts as a "Conditions" stat row

## Key file
`gridsignal_sim/runtime/solar_sim.py`

Public API:
  - `generate_solar_forecast(sim_duration_s, rated_mw, *, utc_now=None)` → SolarForecast
  - `generate_irradiance_samples(sim_duration_s, rated_mw, *, utc_now=None)` → list (shim)

## Fallback chain
1. MISTRAL_API_KEY present → `mistral-small-latest`, temperature=0.5 (varied weather)
2. API call fails / parse error → physics-based San Diego curve, weather="physics_estimate"
3. Both fail → degenerate flat profile

## Physics fallback
San Diego lat=32.72°N, UTC-8 (PST, no DST correction).
`_solar_fraction_at(utc_dt)` → sin(elevation) × 1.05, clamped [0,1].
Physics fallback sets: weather="physics_estimate", conditions="Physics estimate (San Diego)", source="physics".

## Observed behavior
- Nighttime (21:00 PST): all fractions = 0.0 → p_renewable_mw = 0.0 ✓
- Morning marine layer (06:00 PST): 2–13%
- Solar noon (12:00 PST): up to 98%

## THE TRAP: wrong server
The solar code is in the FastAPI Python server (`artifacts/gridsignal: web`).
The `artifacts/api-server` workflow is a DIFFERENT Node.js server. Restarting the
wrong one leaves old code running — solar output stays flat at rated_mw.

## THE TRAP: nighttime PST = fraction 0 for all scenarios without utc_hour override
Only `demo-solar-peak` had `solar_origin_utc_hour=20`. Every other solar scenario
(demo-20mw, fabric-stress variants, etc.) used real wall-clock UTC. At nighttime PST
(roughly 20:00–06:00 local), `generate_solar_forecast` physics fallback returns
elevation < 0 → fraction = 0.0 → p_renewable_mw = 0 for the entire run.
**Fix (runs.py)**: auto-noon fallback — when `solar_origin_utc_hour` is absent AND
the site's local hour is outside 06:00–20:00, compute `utc_hour = int((12 − utc_offset) % 24)`
and apply it before calling `generate_solar_forecast`. Scenarios that need explicit
nighttime solar must set `irradiance_steps` directly (bypasses the forecast call).

## THE TRAP: cold-start zeros after any run
`SolarSim._mistral_fraction_received_at` is set by `set_mistral_fraction()` during a
run. After `clear_run_sync()` it resets to None — but until then (or if clear_run_sync
is missed) the Mistral path runs with the last fraction (often 0.0). The cold-start
POA fallback in `live_aggregate_mw()` only fires when `_mistral_fraction_received_at is
None`. Guard: confirm `clear_run_sync()` is called on run end in run_manager.py line ~1196.
