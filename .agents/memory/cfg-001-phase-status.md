---
name: GS-DES-CFG-001 phase status
description: Phase tracker for the dynamic-config / hardcoded-constant elimination spec; includes the fabric CWD baseline trap.
---

## Phase completion

| Phase | Status | Guard result |
|---|---|---|
| 0 — Guards installed | ✅ Complete | Guard D1 runs, Guard E Tier-1 runs |
| 1 — Three drift fixes | ✅ Complete | Guard D1 passes (0 drifts) |
| 2 — Wire site_parameters into backend; D2 backlog empty | ✅ Complete | Guard D2 backlog empty |
| 3 — Remove Tier-1 constants from `panels/` | ✅ Complete | Guard E Tier-1 passes (2/2) |
| 4–7 — Frontend class B/C, payload extension, settings modal | 🔲 Not started | — |

## Guard summary after Phase 3
- **Guard D1** (`test_guard_d1_no_drift`): PASS — 0 catalogue drifts
- **Guard D2** (`test_guard_d2_backlog_reported`): PASS — backlog empty
- **Guard E Tier-1** (`no_hardcoded_constants.test.ts`): PASS — 0 violations in `panels/`
- **Guard E Tier-2** (informational): reports ~10 constants in broader `src/` (Phase 4–6 scope)

## Fabric CWD baseline trap
`test_fabric_scenarios_e2e.py` and `test_fabric_tick_payload.py` fail with
`FileNotFoundError: config/fabric_fixture_default.json` when pytest runs from the
project root (`gridsignal_sim_v2/`). The file lives at `gridsignal_sim/config/…`.
`fabric_engine.py:41` uses `GS_FABRIC_CONFIG_DIR` env-var, defaulting to `"config"` (relative).

**These 18 failures are pre-existing** — not caused by Phase 0–3 changes.
The "true" baseline excluding fabric CWD failures: **12 failed** (Class A × 4, Class C × 3, Class D × 5).

When reporting clean runs, use:
```
python -m pytest --ignore=audit_tests \
  --ignore=gridsignal_sim/tests/test_fabric_scenarios_e2e.py \
  --ignore=gridsignal_sim/tests/test_fabric_tick_payload.py
```
Expected result: **12 failed, ~944 passed** (all pre-existing, none from this spec).

## Remaining Tier-1 backlog (Phase 3 cleared all 7)
All 7 Tier-1 violations are gone:
- `turbineFleet.ts: PEAK_LOAD_MW` → `peakSiteLoadMW(history)` (observed peak)
- `generation.ts: RATED_MW` → `tick.turbine_units[0]?.rated_mw`
- `generation.ts: RAMP_MW_S` → `tick.turbine_units[0]?.r_asset_mw_per_s`
- `storage.ts: RATED_MW` → `tick.bess_units?.[0]?.rated_mw`
- `storage.ts: USABLE_MWH` → `tick.bess_units?.[0]?.usable_mwh`
- `thermal.ts: DT_THERMAL_S` → `tick.dt_thermal_seconds`
- `thermal.ts: ALPHA_MAX` → `tick.alpha_max`

## Phase 4–7 Tier-2 backlog (informational, not blocking)
Constants still in broader `src/` (not panels/): `FRAME_INTERVAL_MS`, `SOC_FLOOR_DEFAULT`,
`SOC_CEIL_DEFAULT`, `BRIDGING_FULL_RESERVE`, `MAX_HISTORY`, `BRIDGING_FULL`, constants in
`plantLayout.ts`, `HISTORY_MAX`. Payload extension (`design_peak_load_mw` on ScenarioSpec)
and settings modal also remain.

**Why:** Phase 3 scope was `panels/` only (Tier-1 blocking violations). Tier-2 is informational.
**How to apply:** Check Guard E Tier-2 output before starting Phase 4 to get current list.
