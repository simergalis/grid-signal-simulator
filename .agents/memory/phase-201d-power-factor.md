---
name: Phase 201-D power_factor integration
description: power_factor field added to SiteConfig and ScenarioSpec; S_base formula updated; test re-baseline rules.
---

## Rule
`SiteConfig.power_factor: float` is REQUIRED (no default). Every SiteConfig construction site must pass it explicitly.

**Why:** pf=1 silently underestimates S_base by (1-pf)/pf ≈ 18% for a 0.85 pf machine, overstating df/dt. Without the field being required, tests pass with wrong physics.

## How to apply
- `core/models.py` — `power_factor: float` after `frequency_nominal_hz`; no default.
- `core/simulation_core.py` swing-eq block: `_s_base_mw = max(1.0, Σ rated_mw) / state.site.power_factor`
- `api/schemas.py` — `ScenarioSpec.power_factor: float = Field(default=0.85, ...)`; default allows backward compat with stored specs.
- `runtime/scenario_factory.py:build_run_context_from_spec` — fail-fast if `power_factor` absent from spec_data dict.
- `runtime/scenario_factory.py:build_run_context / build_load_test_context` — `power_factor: float = 0.85` function parameter (CHOSEN default, caller overrides for non-standard fleets).

## Test re-baseline rules (after power_factor=pf)
Any test computing an expected `df_predicted` from the swing equation must use:
```python
s_base_mva = max(1.0, turbine_rated_mw) / state.site.power_factor
df_predicted = forcing / (2 * H * s_base_mva) * f0 * dt
```
Tests affected: I2, I2b-explicit, I4b (test_13_2_balance_decomp.py), B5 (test_forecast_path.py).
NOT affected: I3/I3b (directional only, no hardcoded Hz), D1–D5 (source f_nom from config).

## Raw-dict spec helpers that need both fields
Any helper function that builds a plain dict for `build_run_context_from_spec()` must include:
```python
"frequency_nominal_hz": 60.0,   # WECC/ERCOT default; 50.0 for EU/APAC
"power_factor": 0.85,            # CHOSEN — typical gas turbine
```
Files already fixed: test_solar_site_pipeline._minimal_spec, test_solar_weather_propagation._build_spec + _base_spec_no_ambient, test_cooling_ambient_timezone._minimal_spec + _ca8_spec, test_turbine_payload_p0._MINIMAL_SPEC.

## Canonical value
`power_factor = 0.85` — CHOSEN, typical gas turbine. Mark as open parameter wherever used. No measured basis.
