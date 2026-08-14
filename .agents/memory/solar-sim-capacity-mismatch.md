---
name: solar-sim-capacity-mismatch
description: SolarSim (renewable/solar.py) has a fixed product-level rated capacity that can differ from a scenario's solar_rated_mw; the A0 pre-step override and C backstop must normalize by the ratio.
---

# SolarSim vs Scenario Solar Rated Capacity Mismatch

## The Rule
When `run_manager._drive()` injects the SolarSim's `live_aggregate_mw()` into physics `SolarModule.override_output_mw()` (section A0), and when it re-stamps `p_renewable_mw` in the tick result (section C backstop), it **must normalize** by the ratio of scenario solar_rated_mw to SolarSim total_rated_mw — not use the raw absolute MW.

## Why
`SolarSim` (from `renewable/solar.py`) is a fixed product-level demo configured from `renewable.config.CONFIG`. Its total rated capacity (`Σ b.rated_mw for b in solar_sim.state.blocks`) is independent of the scenario's `solar_rated_mw`. A scenario with `solar_rated_mw = 1.5 MW` against a SolarSim with 5.0 MW total rated would see `0.9 irradiance × 5.0 MW = 4.5 MW` injected — 3× the correct value. This inflates `p_renewable_mw`, suppresses `p_dispatch_required`, and starves downstream merit-order assets (fuel cell, BESS) of their dispatch residual.

## How to Apply
In `runtime/run_manager.py`, section A0:
```python
_solar_sim_raw_mw = self.solar_sim.live_aggregate_mw()
_solar_sim_rated_total = sum(b.rated_mw for b in self.solar_sim.state.blocks)
_scenario_solar_rated = sum(sm.config.rated_mw for sm in ctx.sim_state.solar_arrays)
if _solar_sim_rated_total > 0.0 and _scenario_solar_rated > 0.0:
    _pre_solar_mw = (_solar_sim_raw_mw / _solar_sim_rated_total) * _scenario_solar_rated
else:
    _pre_solar_mw = _solar_sim_raw_mw
for _sm in ctx.sim_state.solar_arrays:
    _sm.override_output_mw(_pre_solar_mw)
```

In section C backstop, use `_pre_solar_mw` (from A0) instead of calling `solar_sim.live_aggregate_mw()` again. Initialize `_pre_solar_mw: Optional[float] = None` before A0 so C can fall back safely when `irradiance_profile is None`.

## Downstream Effect
The inflated solar was also the root cause of fuel cell (and BESS) never dispatching: `_fc_remaining = max(0, _p_dispatch_droop_mw - turbine - bess)` was zero because turbines alone exceeded the under-estimated `p_dispatch_required_mw`. Fixing the solar normalization fixes FC dispatch automatically.

## Validation Signal
- In islanded scenarios, balance violations (D4 defect) appear immediately because the grid can't absorb the phantom surplus.
- VerdictBand correctly fires a deficit signal during overage bursts only after this fix — before, inflated solar masked the demand increase.
