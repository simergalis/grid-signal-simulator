---
name: Operator-adjustable parameters
description: Five categories of operator-configurable values exposed via the ⚙ Parameters modal (PARAM-28 through PARAM-34).
---

## What was added

Seven new parameters added to `gridsignal_parameters.json` (PARAM-28–34):

| ID | key | group | default | backend effect |
|----|-----|-------|---------|----------------|
| PARAM-28 | site_latitude | site | 32.72 | Passed to generate_solar_forecast() → physics solar elevation |
| PARAM-29 | site_utc_offset_h | site | -8.0 | Passed to generate_solar_forecast() → local solar time |
| PARAM-30 | ambient_temp_base_c | site | 14.0 | Passed to generate_solar_forecast() → physics ambient model |
| PARAM-31 | soc_floor_pct | storage | 10 | Returned in StartRunResponse; stored in runMeta; AssetReservePanel reads it |
| PARAM-32 | soc_ceil_pct | storage | 95 | Same as above |
| PARAM-33 | advisory_interval_s | advisory | 60 | Stored in scenario spec; NOT yet wired to per-agent cadence |
| PARAM-34 | advisory_max_mw | advisory | 20 | AdvisoryGate(max_proposal_mw=...) via AgentRegistry |

## Key wiring decisions

**advisory_max_mw** — fully wired end-to-end:
- `AdvisoryGate.__init__` now takes `max_proposal_mw=MAX_PROPOSAL_MW`; stores as `self._max_proposal_mw`
- `AgentRegistry.__init__` takes `max_proposal_mw=20.0`; passes to `AdvisoryGate(...)`
- `scenario_factory.py` reads `spec_data.get("advisory_max_mw", 20.0)` and passes to `AgentRegistry`

**advisory_interval_s** — stored in scenario spec but NOT wired to per-agent cadence. The cadence is handled by a "cadence floor" inside each `BaseAdvisoryAgent`; threading it through would require changing each agent's `__init__`. This is a known gap — implement in a follow-up.

**soc_floor_pct / soc_ceil_pct** — display-only:
- Saved in scenario spec via ScenarioBuilder → specWithPhysics
- Read from spec_data in `runs.py`; returned in `StartRunResponse` alongside `run_id`
- `App.handleRunStarted` receives them as optional args; stores in `runMeta`
- `AssetReservePanel.SocBar` reads from `useTickStore(s => s.runMeta)` with fallback to 10/95

**solar site params** — fully wired through physics fallback:
- `generate_solar_forecast()` now accepts `site_latitude`, `site_utc_offset_h`, `ambient_temp_base_c` (all optional with San Diego defaults)
- Threaded into `_solar_fraction_at()`, `_physics_ambient_steps()`, `_ambient_fraction_to_temp()`
- Both the Mistral-absent and Mistral-exception fallback paths pass these params
- The Mistral prompt still says "San Diego" in the text — future work to make it dynamic

## ParameterModal groups

`GROUP_ORDER = ['site', 'timing', 'thermal', 'storage', 'advisory', 'confidence']`

Two new groups added:
- `site` — site_latitude, site_utc_offset_h, ambient_temp_base_c
- `advisory` — advisory_interval_s, advisory_max_mw

`soc_floor_pct` and `soc_ceil_pct` appear in the existing `storage` group.

## Files changed

Backend: `runtime/solar_sim.py`, `runtime/advisory_gate.py`, `advisory/agent_registry.py`, `runtime/scenario_factory.py`, `api/routes/runs.py`, `api/schemas.py`

Frontend: `parameters.json`, `types.ts` (ScenarioSpec + RunMeta), `ParameterModal.tsx` (PhysicsParams + PARAM_MAP + GROUP_ORDER + GROUP_LABELS + defaultPhysicsParams), `ScenarioBuilder.tsx` (load-seed + save-merge), `AssetReservePanel.tsx` (SocBar reads runMeta), `DemoBar.tsx`, `RunControlBar.tsx`, `App.tsx`

## Why advisory_interval_s is not wired

`BaseAdvisoryAgent` uses a cadence floor mechanism (not a simple `advise_every_n` counter at the registry level). Wiring it requires changing each of the 6 agent constructors and the `AgentRegistry` agent-list construction. Chosen to expose the param for storage now and wire the effect in a follow-up to avoid risk.
