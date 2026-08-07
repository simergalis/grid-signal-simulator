---
name: spec2-surplus-inertia
description: Key decisions and traps from GS_prompt_surplus_and_inertia implementation (§INV-CURT, §INV-INERTIA, S9 rerun, ScenarioSpec thresholds).
---

## Summary

All 6 spec-2 items delivered. Suite: 13 failed / 987 passed / 16 xfailed (net −1 failure vs pre-spec-2 baseline).

## §INV-CURT

Proportional OF curtailment block inserted in `evaluate_tick()` after `solar.advance()`, before `p_dispatch_required_mw`:

```python
curt_fraction = clamp((f − of_warning_hz) / (of_trip_hz − of_warning_hz), 0, 1)
p_renewable_curtailed_mw = curt_fraction × p_renewable_mw
p_renewable_mw -= p_renewable_curtailed_mw
```

Uses `state._frequency_hz` (previous tick — causal). Only fires when `island_mode == ISLANDED` AND both thresholds are non-None AND `f > of_warning_hz`. Was never triggered in S9 rerun (f stayed at 60.0 Hz ≤ 60.5 Hz of_warning throughout zero-machine phase).

## §INV-INERTIA: S_base on-bus turbines only

**Old:** `max(1.0, Σ all turbines) / pf`  
**New:** `Σ on-bus turbines / pf` (SYNCHRONISED + UNLOADING only)

**THE TRAP — `_sync_ceiling_mw` must be decoupled:** The old `_sync_ceiling_mw = _s_base_mw × pf` gave 0 when no on-bus turbines, starving the BESS setpoint. After fix: `_sync_ceiling_mw = Σ ALL turbine rated_mw` (dispatch ceiling, not inertia figure).

**Zero-machine guard:**
```python
if _s_base_mw == 0:
    if any(b.config.grid_forming for b in state.bess_units):
        freeze frequency  # GF-BESS stiff reference
    else:
        use virtual S_base = 1.0/pf  # backward compat for non-GF fixtures (e.g. B1b)
```

**THE TRAP — I2 test fixture:** `_make_islanded_solar_state` had OFFLINE turbine; old formula counted it. After fix: turbine pre-forced to SYNCHRONISED + `p_min_stable_frac=0.0`. Without `p_min_stable_frac=0`, the loading layer holds turbine at MSL=4MW even when fleet_target=0, inflating frequency_forcing from 1 MW to 5 MW (BESS setpoint clamped to max(0,…) can't absorb the surplus).

## S9 Rerun

Corrected irradiance: 13-step ZOH dawn ramp 0→15 MW over t=0–300 s.

- **Zero-machine phase (t=0–900 s):** GF-BESS freezes frequency at 60 Hz, covers demand via discharge.
- **Collapse:** tick 181, t=905 s, `island_collapse_uf`, f=57.0 Hz.
  - GT-0 synchronised at t=900 s; output=1 MW at collapse (dispatch ordering gap, F-4).
  - BESS=17 MW (rated 18, anchor reserve 1 MW), solar=15 MW, demand=54.37 MW.
  - Shortfall=21.37 MW → Δf=45.4 Hz/tick → single-tick collapse.
- **§INV-CURT:** `p_renewable_curtailed_mw = 0.0` throughout (OF risk never arose).
- **All 9 invariants pass.**

## F-4: Dispatch ordering gap (new finding)

Turbine transitions STARTING→SYNCHRONISED inside `advance()`, AFTER `_entry_states` snapshot. Loading layer uses entry_state=STARTING → turbine excluded → setpoint=0 on transition tick. Next tick ramps 1 step, not to MSL. Effect: ~7 ticks below MSL after synchronisation. I-2 assertion patched with 7-tick grace period. Root cause: dispatch→advance ordering not fixable without restructuring tick eval. Tracked as Task #247.

## ScenarioSpec threshold fields

5 `Optional[float] = None` fields added to `api/schemas.py::ScenarioSpec`:  
`uf_warning_hz`, `ufls_stage1_hz`, `island_collapse_hz`, `of_warning_hz`, `of_trip_hz`.  
Factory passes them through to SiteConfig unchanged. Backward compatible.

**Why:** Allows per-scenario threshold override from the API; hardcoded 57/60.5/62 Hz defaults remain in SiteConfig when fields are None.

## Pre-existing failures (13 total after spec 2)

test_13_3 I3a/I3b (droop runaway), test_f5 (dt_lead), test_forecast_path B1a/B5/B5b (OFFLINE gate), test_formulas d10 (hot_start catalogue), test_kube_oscillation ×4, test_operator tc_203_3, test_telemetry tc_gt2_f.
