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
| 5 — Prose sweep + Phase 4 corrections | ✅ DONE | 3 corrections; stale prose fixed; undeclared count = 11 (reported) |
| 6–7 | NOT STARTED | |

## Phase 5 — key rulings and findings

**Item 1 — 15% margin is circular (NOT a derivation):**
`_COOLING_MARGIN = 1.15` in `scenario_factory.py:182` (tagged PROTO-10-MARGIN at lines 316, 645).
`ratedMW / (alphaMax × p_compute)` recovers the constant algebraically — circular round-trip.
Also varies with p_compute_mw: a design-time constant would move tick by tick.
Resolution: sub-label removed entirely. Stat row is complete without it.
Do not present this ratio as a "derivation" in any future phase.

**Item 2 — α_max bar ceiling = 30% (catalogue maximum):**
Old: max=100 — the operating range (10–30%) was a thin sliver, ambient-stress invisible.
New: max=30 — catalogue max for alpha_max (gridsignal_parameters.json adjustable, max=0.3, spec_ref v2.5 §8).
Justification: base α_max (20%) sits at 2/3 of full scale; at peak ambient stress (effective=30%) the bar is full — a defined physical event. Stated in the BulletBar comment.

**Item 3 — SiteConfig/catalogue/TickResult defaults all agree:**
| Source | dt_thermal_seconds | alpha_max |
|--------|-------------------|-----------|
| Catalogue (gridsignal_parameters.json adjustable) | default=90, min=60, max=120 | default=0.2, min=0.1, max=0.3 |
| SiteConfig default | `_sp.value("dt_thermal")` = 90 (models.py:279) | `_sp.value("alpha_max")` = 0.2 (models.py:277) |
| TickResult default | `_sp.value("dt_thermal")` = 90 | `_sp.value("alpha_max")` = 0.2 |
All three agree. No Guard D1 miss.

**Enrichment skip — production path:**
Enrichment (`_dc_replace` at run_manager.py:1270) happens BEFORE both `ctx.sink.append()` and
`self._ws_hub.broadcast()`. All production ticks are enriched; enrichment cannot be skipped.
Test paths: `test_f2_bridging_basis.py:239` and `test_f5_sim_time_interval_end.py:132` call
`_tick_result_to_dict` directly with synthetic TickResults. They bypass enrichment but use
`_sp.value()` defaults — same as catalogue → no observable discrepancy.

**Item 4 — Prose sweep classification:**
Stale items fixed (live-tick paths where wire data now available):
1. compute.ts:94 — `'~90 s'` → `\`~${tick.dt_thermal_seconds.toFixed(0)} s\``
2. thermal.ts:127 — chartTitle `'THE 90-SECOND LAG'` → uses `tick.dt_thermal_seconds`
3. thermal.ts:141 — why[0] `'roughly 90 seconds'` → uses `tick.dt_thermal_seconds`
4. generation.ts:128 — `'1 of 1'` → derived from `tick.turbine_units` filter by state
5. thermal.ts:131 — "Rated capacity" sub (circular derivation) removed

Undeclared count = 11 (design figures with no wire source):
- agents.ts:39: heroValue `'6/6'` — agent count not on wire
- agents.ts:47: `'30–60 s'` fast cadence — not on wire
- agents.ts:48: `'5–60 min'` slow cadence — not on wire
- agents.ts:50: `'2.2 M / 15 M'` token budget — not on wire
- thermal.ts:136: τ = `'20 s'` — tau in catalogue (default=20, min=10, max=40) but NOT broadcast on tick; sub-label updated to state this
- storage.ts:109,117: anchor reserve `'1.0 MW'` / `'One megawatt'` — design constant §7.1.2, not on wire
- turbineFleet.ts:593: cold start `'5–10 min'` — not on wire; sub `'45 s'` also undeclared
- thermal.ts:41: no-tick chartTitle `'THE 90-SECOND LAG'` — no tick in scope, stays undeclared
- compute.ts:43,44,148,152,153: `'30–60 s'`, `'90 s'` in no-tick why[] / live why[] — no-tick stays undeclared; PROTO-10 live-tick ones (149,153) were stale and now use `tick.dt_thermal_seconds`
- forecastQuality.ts:21-24: CI widening % (+10%,+8%,+15%,+5%) — not on wire; line 89 already labelled "chosen value, not derived"
Count is large enough that future tooling may be warranted (Guard E string extension was explicitly prohibited this phase).

**Item 5 — "977 collected" reporting error corrected:**
Phase 4 report said "977 collected" — this was 12+965=977 test OUTCOMES, not node IDs.
Actual `pytest --collect-only` count is 974, unchanged from Phase 3.
No new tests were added in Phase 4. The three net new tests in the codebase relative to
commit 72a194e (Phase 0 baseline) are:
1. `test_guard_d1_no_drift` (test_no_hardcoded_parameters.py) — Phase 0
2. `test_guard_d2_backlog_reported` (test_no_hardcoded_parameters.py) — Phase 0
3. `test_for_tick_one_tick_overshoot_is_tolerated` (test_corruption_schedule_lifecycle.py) — triage pre-Phase-0

## Guard status (Phase 5 close)
| Guard | Result |
|-------|--------|
| D1 (no parameter drift) | ✅ PASS |
| D2 (backlog) | ✅ PASS (informational) |
| E Tier-1 (no module-scope ALL_CAPS in panels/) | ✅ PASS |
| TypeScript --noEmit | ✅ clean |
| Full suite from canonical CWD | 12 failed (pre-existing), 965 passed, 974 collected, 0 errors |
