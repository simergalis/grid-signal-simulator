---
name: Generation Architecture
description: Pre-run generator design — five generators that materialise timelines before t=0; constraints, patterns, and wiring.
---

# Generation Architecture

## Core rule
All generators run as concurrent asyncio tasks (asyncio.gather) BEFORE the tick loop starts.
No generator is called during a tick — this preserves reproducibility and keeps network calls out of the NFR-2 control path.

## Constraint: Random ≠ AI
- Use seeded RNG for distributions you can specify (arrival times, sensor noise, SOC start)
- Use LLM only where the value is correlated structure over time a distribution cannot produce (weather, cluster traffic patterns, compound fault sequences)

## Constraint: Validate before materialise
Every generated value is validated against gridsignal_parameters.json via `generation_validator.validate_generated_value()`.
Out-of-range values are REJECTED and logged — never silently clamped. Clamping hides generation defects.

## Five generators (all in runtime/)

| File | LLM? | What it produces | Fallback |
|---|---|---|---|
| solar_sim.py | Mistral | irradiance_steps + **ambient_steps** (drybulb/wetbulb, correlated) | physics (San Diego model) |
| cluster_gen.py | Mistral | STARTING/JOB_END/SCALE events — bursty cluster traffic | seeded RNG Poisson |
| stressor_gen.py | Mistral | SOLAR_STEP events — compound fault sequences | seeded RNG random cloud fronts |
| param_sampler.py | RNG only | Physics params drawn from [min,max] ranges (§6.1 sensitivity) | n/a |
| telemetry_corruption.py | RNG only | Per-tick noise/dropout/staleness manifest | n/a |

## Wiring point: api/routes/runs.py
`start_run()` runs all five generators with `asyncio.gather(_run_solar(), _run_cluster(), _run_stressor(), _run_param_sampler())`.
Materialised events are merged into `spec_data["workload_events"]` (sorted by timestamp) before `build_run_context_from_spec()` is called.
`ctx.telemetry_corruption` is set after context creation for the tick loop.

## GenerationBlock (api/schemas.py)
Stored on RunContext and persisted in spec_data["generation_block"]. Fields:
- `seed`, `generated_at` (ISO-8601), `generators_used` (list)
- `solar_source`, `cluster_source`, `stressor_source` — "mistral"/"rng"/"none"
- `param_sampler_note`, `corruption_note` — human-readable summaries

**Why:** Distinguishes a scenario definition from a materialised spec. A run_id + generation_block is sufficient to replay any run (F10 from verification report).

## ScenarioSpec new fields (all Optional, default None)
- `ambient_steps` — injected by runs.py from solar_sim, not user-settable
- `cluster_gen_config: ClusterGenConfigSpec`
- `stressor_gen_config: StressorGenConfigSpec`
- `param_sampling_config: ParamSamplingConfigSpec`
- `telemetry_corruption_config: TelemetryCorruptionConfigSpec`
- `generation_block: GenerationBlock`

## THE TRAP: SolarForecast is now a 5-field NamedTuple
Old: (samples, weather, conditions, source)
New: (samples, weather, conditions, source, ambient_steps)
`generate_irradiance_samples()` shim still works (returns .samples).
Mistral path extended to request `"ambient": [[t, drybulb, wetbulb], ...]` in the same JSON response — one call, two correlated outputs.
Physics ambient fallback: `_physics_ambient_steps()` correlates temp with solar fraction (drybulb = 14 + fraction×10 + morning offset).

## param_sampler: key→field translation
gridsignal_parameters.json key → ScenarioSpec field:
  "dt_thermal" → "dt_thermal_seconds" / "plant_dt_thermal_seconds"
  "alpha_max"  → "alpha_max" / "plant_alpha_max"
  "tau"        → "tau_seconds" / "plant_tau_seconds"
  "r_asset"    → "_sampled_r_asset_mw_per_s" (caller must apply to TurbineUnitSpec)

## _NEVER_SAMPLE exclusion set
Keys excluded from param sampling (conformance constants, fleet sizing, site-calibration values):
band_pct_calibrated, band_mult_*, anchor_reserve_pct, soc_pct, bess_rated_mw, p_renewable_mw
