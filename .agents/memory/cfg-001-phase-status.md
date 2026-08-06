---
name: GS-DES-CFG-001 phase status
description: Phase tracker for the hardcoded-constant elimination refactor; traps, rulings, and guard status after each phase.
---

## Phase tracker

| Phase | Status | Notes |
|-------|--------|-------|
| 0 — Guards installed | ✅ DONE | Guard D1/D2 (Python) + Guard E Tier-1/Tier-2 (TS) |
| 1 — Drift fixes | ✅ DONE | pue_base corrected (1.11→1.03); band_enabled bool added; bess_rated_mw exempted Reason B |
| 2 — site_parameters.py | ✅ DONE | core/site_parameters.py created; 7 backend literals migrated to _sp.value() |
| 3 — panels/ ALL_CAPS removal | ✅ DONE (closed) | All panels/ constants removed; Class B revert + fleet fix applied; closeout items resolved |
| 4 — TickResult/serialiser extension | NOT STARTED | Add bess_rated_mw, bess_usable_mwh, dt_thermal_seconds, alpha_max to TickResult + _tick_result_to_dict |
| 5–7 | NOT STARTED | |

## Phase 3 closeout — key rulings

**Wire-format audit (Item 2 resolution):**
- `bess_units`, `dt_thermal_seconds`, `alpha_max` are on `ScenarioSpec` NOT `TickPayload`.
- `_tick_result_to_dict` (run_manager.py:156–367) does NOT emit any of them.
- `storage.ts`: BulletBar removed entirely (bar whose max = its own value is permanently full).
  - "Rated power" → "not instrumented"; "Usable energy" → "not instrumented".
  - "Current output" stat row uses `tick.bess_output_mw` directly (accurate label).
  - `BulletBar` import removed from storage.ts.
- `thermal.ts`: α_max BulletBar kept but `value: 0, note: 'not instrumented'` (not value=actual).
  - "Δt_thermal" stat row → "not instrumented".
- Phase 4's job: add these four fields to TickResult + serialiser.

**Fleet vs per-unit classification in generation.ts:**
- `tick.ramp_capability_mw` (loading-layer, on TickPayload at types.ts:175) = **FLEET-LEVEL**:
  - Used for: `fleetRampCap`, hero value, verdict, `canClose`, BulletBar "Fleet ramp capability".
- `u0.r_asset_mw_per_s` = **PER-UNIT**:
  - Used for: `rampMWs`, stat "Ramp rate configured", stat "Time to full output", `unitRampCap` in why[1] prose ("this unit delivers").
- `installedFleetMW(units)` = **FLEET-LEVEL**: chart ceiling, BulletBar "Output as share of fleet rated".
- `unitMW = u0.rated_mw` = **PER-UNIT**: "Rated output" stat row only.
- `largestUnitMW()` added to siteParameters.ts (one definition only, line 108).

**Collection delta attribution (Item 4):**
- Canonical CWD: `gridsignal_sim/` (fabric tests pass; `config/` resolves correctly).
- Current canonical count: **974 collected, 12 failed (all pre-existing), 965 passed**.
- Stated baseline of 975 was a working-tree measurement that included pre-triage lifecycle
  variants not preserved in commit `55c5072` ("Update corruption schedule lifecycle tests").
- Git diff `72a194e → HEAD` on test files: only 2 files changed.
  - `test_no_hardcoded_parameters.py`: +2 (new — Phase 0 guard tests).
  - `test_corruption_schedule_lifecycle.py`: +1 (`test_for_tick_one_tick_overshoot_is_tolerated`).
- Net committed delta: +3.  72a194e committed state had 971 tests; 971+3=974. ✓
- The stated −1 gap (975→974 before guard tests, or 975+2−3=974 after) is a pre-Phase-0
  artefact: the baseline was measured from a working tree with 4 triage-session variants
  in lifecycle.py that were not committed to 72a194e; the triage commit kept only 7.
- No Phase 0–3 regression. The 12 failures are unchanged Class A+C+D pre-existing.

**docstring prose (Item 3):**
- Original `generation.ts` line ~49: `RAMP_MW_S * 45` and "in the 45 s of warning".
- Phase 3 already replaced both: `rampCap.toFixed(1)` (derived) and `tick.dt_lead_next_s.toFixed(0)` (runtime).
- After fleet fix: `unitRampCap.toFixed(1)` (per-unit, derived from dt_lead_next_s) and `tick.dt_lead_next_s.toFixed(0)`. No literal 45 anywhere in generation.ts.
- Docstring line 8 "45 s" → "configured lead window". ✓

## THE TRAP — fabric CWD false positive
Running pytest from `gridsignal_sim_v2/` instead of `gridsignal_sim/` makes all fabric
tests fail with FileNotFoundError (fabric_engine.py line 41: `_CFG_DIR = Path(os.environ.get("GS_FABRIC_CONFIG_DIR", "config"))` is relative to CWD).
Always run from `gridsignal_sim/`.

## Guard status (Phase 3 closeout)
| Guard | Result |
|-------|--------|
| D1 (no parameter drift) | ✅ PASS |
| D2 (backlog) | ✅ PASS (informational) |
| E Tier-1 (no module-scope ALL_CAPS in panels/) | ✅ PASS |
| TypeScript --noEmit | ✅ clean |
| Full suite from canonical CWD | 12 failed (pre-existing), 965 passed, 974 collected |
