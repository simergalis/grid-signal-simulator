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
| 3 — panels/ ALL_CAPS removal | ✅ DONE | All panels/ constants removed; Class B revert + fleet fix applied; closeout items resolved |
| 4 — TickResult/serialiser extension | ✅ DONE | 5 fields on wire; panels restored; bess_output_mw confirmed fleet; labelling fixed |
| 5–7 | NOT STARTED | |

## Phase 4 — key implementation details

**Ordering rule (per spec):** types.ts entries must land BEFORE backend emission.
- Edit 1: `types.ts` (TickPayload) — 5 new fields added.
- Edit 2: `core/models.py` (TickResult) — 5 new fields added.
- Edit 3: `runtime/run_manager.py` — enriched in dataclasses.replace() + emitted in _tick_result_to_dict.

**Five fields added:**
| Field | Python source | TickPayload type |
|-------|---------------|-----------------|
| `bess_rated_mw` | `sum(b.config.rated_mw for b in ctx.sim_state.bess_units)` | `number` |
| `bess_usable_mwh` | `sum(b.config.usable_mwh for b in ctx.sim_state.bess_units)` | `number` |
| `bess_unit_count` | `len(ctx.sim_state.bess_units)` | `number` |
| `dt_thermal_seconds` | `ctx.sim_state.site.dt_thermal_seconds` | `number` |
| `alpha_max` | `ctx.sim_state.site.alpha_max` | `number` |

**THE TRAP — TickResult default values for physics constants:**
Guard D1 scans for numeric literals that disagree with gridsignal_parameters.json.
`dt_thermal_seconds: float = 0.0` and `alpha_max: float = 0.0` on TickResult FAILED D1
because `0.0 ≠ 90.0` and `0.0 ≠ 0.2` in the catalogue.
Fix: use `_sp.value("dt_thermal")` and `_sp.value("alpha_max")` as defaults on TickResult,
matching the SiteConfig pattern. The per-tick value is overwritten by the dataclasses.replace()
enrichment from `ctx.sim_state.site`.

**bess_output_mw scope — Item 2 confirmed:**
FLEET-LEVEL sum. Confirmed from `dispatch.py:681–683`:
`bess_output_mw = 0.0; for bess in bess_units: bess_output_mw += bess.cover_shortfall(...)`.
Candidate ID is `"bess-fleet"`. Sub-label updated in storage.ts: "fleet discharge — sum across all units".

**bess_usable_mwh — NOT from contingency_coverage:**
`contingency_coverage.bess_usable_energy_mwh` is rewritten by SOC-corruption injection
(run_manager.py:787–788 staleness substitution). Source must be `b.config.usable_mwh`.
Both models.py field comment and _tick_result_to_dict comment state this explicitly.

**alpha_max vs ambient_alpha_scale:**
Both now on wire. `alpha_max` = base from SiteConfig. `ambient_alpha_scale` = factor applied to it
(already on wire since Phase W3). Panel must show both as separate quantities.
Thermal panel: BulletBar shows `alphaEff = alphaMax × ambient_alpha_scale` (effective %)
as bar value, `alphaMax × 100` as the target marker, note states "base × scale → effective".

**thermal.ts:105 "15% margin · PROTO-10" — removed and derived:**
Was a hardcoded literal in a string (outside Guard E reach). Replaced with:
`marginPct = (ratedMW / (alphaMax × max(p_compute_mw, 1e-6)) - 1) × 100`
Displayed as "{N}% headroom over α_max × compute ceiling". Falls back to
"rated ceiling from thermal model" when alphaMax = 0.

**generation.ts Item 4 labelling changes:**
1. BulletBar note for fleet ramp: added "Measures on-bus units only — STARTING units
   contribute zero (not yet committed to bus)."
2. why[1]: "this unit delivers" → "one machine delivers" (explicit per-unit framing).
3. "Ramp rate configured" sub: "site parameter" → "first-unit nameplate (homogeneous fleet)"
   (both the no-tick and live-tick versions).

## THE TRAP — fabric CWD false positive
Running pytest from `gridsignal_sim_v2/` instead of `gridsignal_sim/` makes all fabric
tests fail with FileNotFoundError. Always run from `gridsignal_sim/`.

## Guard status (Phase 4 close)
| Guard | Result |
|-------|--------|
| D1 (no parameter drift) | ✅ PASS |
| D2 (backlog) | ✅ PASS (informational) |
| E Tier-1 (no module-scope ALL_CAPS in panels/) | ✅ PASS |
| TypeScript --noEmit | ✅ clean |
| Full suite from canonical CWD | 12 failed (pre-existing), 965 passed, 977 collected |

## Baseline (canonical CWD gridsignal_sim/)
**12 failed, 965 passed, 977 collected, 0 errors.**
Pre-existing failures — Class A+C+D (prohibited from fixing):
- test_f5_sim_time_interval_end::test_internal_elapsed_unaffected_by_f5
- test_formulas::test_d10_demo_20mw_bess_fires_and_tapers
- test_kube_no_oscillation::TestKubePowerCapNoOscillation::test_oscillation_is_reproducible_across_seeds (3 SUBFAILED seeds)
- test_kube_no_oscillation::TestKubePowerCapNoOscillation::test_power_cap_toggle_count_within_300s
- test_step16_wiring::test_demo_pms_column3_tc64_to_tc68
- test_telemetry_corruption_wiring::test_tc_gt2_f_state_flips_when_soc_crosses_threshold
- test_turbine_payload_p0::test_tc_p0_1/2/3/5 (4 tests)
