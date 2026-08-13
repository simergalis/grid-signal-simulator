---
name: PSP-002 phases 0–2 decisions
description: Key decisions, corrections, and structural outcomes from GS-IMPL-PSP-002 phases 0 through 2.
---

## Spec file
`attached_assets/GS-IMPL-PSP-002_master_specification_1786625324095.md`

## Phase gate status (as of 2026-08-13)
- Phase 0: DONE (catalogue scaffolding + corrections)
- Phase 1: DONE (module relocation + import boundary)
- Phase 2: DONE (three named defects corrected)
- Phase 3–5: NOT STARTED

## Catalogue corrections (Phase 0 revisions)

**Why:** Phase 0 used an old PG&E tariff. All rates corrected to Cal. P.U.C. Sheet No. 61081-E, effective March 1, 2026.

Summer rates (old → new):
- `pge_tou_summer_peak_mwh`: $117.58 → $177.02 (period: 4–9pm = hours 16–20)
- `pge_tou_summer_partial_peak_mwh` RETIRED → `pge_tou_summer_part_peak_mwh`: $74.90 → $142.27 (period: 2–4pm + 9–11pm = hours 14–15, 21–22)
- `pge_tou_summer_off_peak_mwh`: $41.08 → $114.82

Winter rates (stubs resolved):
- `pge_tou_winter_peak_mwh`: null/RAISES → $156.32 (hours 16–20)
- `pge_tou_winter_partial_peak_mwh` RENAMED → `pge_tou_winter_super_off_peak_mwh`: null/RAISES → $58.72 (months 3–5, hours 9–13 ONLY — needs month, not just season)
- `pge_tou_winter_off_peak_mwh`: null/RAISES → $114.60

New keys added:
- `battery_capex_per_mwh`: $125,000/MWh (Ember Oct 2025)
- `cycle_life_cycles`: 5000 (LFP conservative)
- `pge_voltage_class`: "secondary" (per-deployment tag)

**PSP-6 resolved:** `bess_marginal_cost_mwh` = $38.00/MWh. Method A: ($125,000 / 5,000 cycles) + ~$13/MWh round-trip loss. Both source params tagged PROPOSED_HERE.

**Critical:** Zero `UNAVAILABLE_RAISES` stubs remain. PSP-5 and PSP-6 both resolved.

## Phase 1 — files created

| File | Location | Notes |
|---|---|---|
| `power_source_priority.py` | `core/` | PowerRanker, PowerSource, AdvisoryOutput |
| `economic_dispatch_loop.py` | `core/` | Phase 1 (defective), corrected in Phase 2 |
| `pms_test_double.py` | `runtime/` | PMSTestDouble — simulator ONLY |
| `scenario_author.py` | `scripts/` | Offline Mistral; never imported by core/runtime |
| `test_power_source_priority.py` | `tests/` | TC-C1, TC-C2, TC-C3 (advisory half) |
| `test_no_forbidden_imports.py` | `tests/` | TC-C11, TC-C12, TC-C13 structural |

`WorkloadSignal.tenant_id: Optional[str] = None` added to `core/models.py`.

**Import boundary confirmed clean:** core/ has zero runtime/ imports; runtime/ has zero LLM/southbound/PSP-002-RNG imports.

**RNG exemptions in runtime/ (5 files, seeded Random instances, not global state):**
cluster_gen.py, param_sampler.py, run_manager.py, stressor_gen.py, telemetry_corruption.py.
All use `random.Random(seed)` — isolated, seeded, predating PSP-002.

## Phase 2 — three defects corrected

**DEFECT-1 (§2.3.1):** `total_cost_per_hour` → `cost_this_tick`. Formula: Σ(allocated_mw × price × tick_duration_hours). `tick_duration_hours` is now an explicit keyword-only parameter.

**DEFECT-2 (PSP-5 / §3.2.1):** step() now takes `season` AND `month` (both keyword-only). `_pge_price_for_period()` reads all rates from catalogue. Super Off-Peak (months 3–5, hours 9–13) correctly distinguished from winter off-peak — season alone is insufficient.

**DEFECT-3 (PSP-6 / §7):** BESS sources are repriced in step() using `_sp.value("bess_marginal_cost_mwh")`, overriding any caller-supplied value.

**Keyword-only enforcement:** bare `*` after `t_s` in step() signature. Any positional caller gets TypeError immediately.

**Confirmed: zero existing callers** of EconomicDispatchLoop.step() anywhere in the repo before Phase 2. The grep for `EconomicDispatchLoop(` returned nothing outside the new PSP-002 files.

## D10 failure — confirmed pre-existing, unrelated to PSP-002

Test: `test_formulas.py::test_d10_demo_20mw_bess_fires_and_tapers`
Failure: BESS never tapers; `bess_outputs` stays at [5.0, 5.0, ...] because `gen=9.99 MW` throughout (turbine only outputs ~10 MW despite `rated_mw=25`).
Cause: D4 balance routing issue in `simulation_core.py` — turbine output not correctly attributed in `p_generation_mw`. Zero PSP-002 code is imported or called by this test.

## Post-review corrections (applied before Phase 3)

**Correction A — `season` dropped from step():**
`season` is fully derivable from `month` (6–9 → summer, 10–5 → winter). Removed from step() signature; derived internally by `_season_from_month(month)`. `_pge_price_for_period(hour_of_day, month)` no longer takes season. Passing `season=` as a keyword now raises TypeError.

**Correction B — BESS repricing scope fixed:**
BESS catalogue repricing moved from `step()` into `PowerRanker.rank()`. Both the autonomous dispatch path (through step()) and the §4.3 escalation path (direct rank() call on confirm/human_only sources) now see the same catalogue-sourced BESS cost. `step()` reprices grid sources only (TOU is legitimately tick-context-dependent; BESS cost is not). `_bess_marginal_cost()` helper removed from `economic_dispatch_loop.py`.

## Phase 2 test results (after post-review corrections)
- Total: 64 passed. Pre-existing failure: `test_d10_demo_20mw_bess_fires_and_tapers` (unrelated D4).

## Phase 3 decisions

**Files added:**
- `core/tenant_budget_gate.py` — QuarantinedSignalError, RotationState, BudgetGate, handle_queued_event()
- `tests/test_tenant_budget_gate.py` — TC-C6, TC-C7, TC-C8, TC-C9

**models.py additions:** TenantPowerBudget, WorkloadCommandAction(DEFER), WorkloadCommand(action, target, authority: OperatingTier).

**`operating_tier` extension to evaluate() signature:** spec §3.3 doesn't list it, but WorkloadCommand.authority requires it. Added as keyword-only with default SUPERVISED. Phase 4 caller must source this from `SiteConfig.operating_tier` (§23.4 Ladder A) — not a convenient default or cached value.

**Quarantine priority over MT-1:** QuarantinedSignalError raised before MT-1 (budget=None) check. tenant_id=None always quarantines, regardless of budget presence.

**RotationState.persistence_backed removed:** Was a boolean flag, but no backing store exists so setting True would suppress the warning dishonestly. MT-4 warning fires unconditionally at construction. Tests no longer suppress it.

**least_recently_selected() returns list[str], not str:** Returns ALL candidates tied at the minimum count. Caller applies tiebreak (priority class, then job age) per §3.3.1. Alphabetical tiebreak was spec deviation — permanently disadvantaged tenants whose IDs sort late with no business justification. test_tie_returns_all_tied_candidates is the key spec-compliance pin test.

**Grid-TOU repricing scope gap — RESOLVED in Phase 4.** `pge_price_for_period` and `season_from_month` are now public module-level functions in `economic_dispatch_loop.py`. The §4.3 escalation assembler in `_drive()` calls them directly before `PowerRanker().rank()` to reprice GRID_FIRM/SPOT/RESERVED confirm/human_only sources at the tick's actual TOU rate. Underscore aliases preserved for backward compat.

**Phase 4 — EDL wired in `_drive()` section A1b (after §7, before A2 SOC corruption).** `RunContext` gains three new fields: `edl_sources`, `edl_calendar_month` (int, TOU month), `pms_response_profile`. Both §4.3 branches exist: simulator (`_PMSTestDouble`) and production log-stub. `_is_simulator_harness()` reads `GS_PRODUCTION_HARNESS` env var at call time (not module load) so tests can patch it without reimporting.

**operating_tier sourcing (§23.4 §4.1 / §4.3 callers):** Must be sourced from `ctx.sim_state.site.operating_tier` (Ladder A), not a startup default. EDL's `_drive()` wiring uses `getattr(..., "operating_tier", None)` to log it; downstream callers wiring BudgetGate must do the same.

## Phase 4 test results
- Total: 110 passed (14 new Phase 4 tests in test_psp002_phase4.py, 6 new in test_economic_dispatch_loop.py)
- Pre-existing failure: `test_d10_demo_20mw_bess_fires_and_tapers` (D4 balance routing, unrelated)
