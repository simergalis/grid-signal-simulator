# DR-GMB Phase 1 — grid-first dispatch and visible grid meter

## User-visible issue

The screenshot showed `Grid Connection 0.00 MW` while the BESS tile showed discharge. The frontend modal reads `tick.grid_import_mw` and falls back to zero when that field is absent (`frontend/src/opening/GridConnectionModal.tsx:253`). The runtime tick payload previously exposed signed `grid_exchange_mw`, but not the positive import/export meter values expected by this UI.

## Implemented behavior

- Grid-connected dispatch is grid-first. The BESS discharge limit is zero when there is no configured import cap; with a cap, it can cover only demand above that cap (`core/simulation_core.py:2183–2194`, `2210–2218`).
- Grid headroom can recharge the BESS up to its configured `initial_soc_fraction`, using the existing charge efficiency and rated-power limit. It does not use the tariff price (`core/simulation_core.py:2195–2208`; `core/dispatch.py:492–529`).
- The existing SoC reserve-floor calculation is still passed to the arbitrator (`core/simulation_core.py:2219–2239`). The islanded dispatch branch was not changed.
- The live tick serializer now emits `grid_import_mw = round(max(0, -grid_exchange_mw), 5)` and the corresponding positive export value (`runtime/run_manager.py:877–878`). The tick type includes the import field (`frontend/src/types.ts:227–229`), and the grid tile uses `grid_import_mw` (`frontend/src/opening/plantLayout.ts:120`). The grid connection modal already reads this field (`frontend/src/opening/GridConnectionModal.tsx:253`).

## S11/S11b smoke check

Using the pinned `ctx.step` path (seed 1729, wall clock 1792454400), the first four ticks for both S11 and S11b report grid import equal to demand and BESS output of zero. For example, at 20 seconds, demand and grid import are both 0.1184821034 MW (meter rounded to 0.11848 MW); BESS output is 0 MW. See `GRID_MODE_SMOKE.json` for all eight rows.

This is an early, low-load sample only, not a full-day S11/S11b acceptance run.

## Verification

- Focused grid, serializer, payload, and aggregate tests: **35 passed, 0 failed** (1 warning; 18.77 s).
- Related dispatch/BESS suite: **133 passed, 0 failed** (7 warnings; 35.32 s).
- Frontend `npm run build`: **passed**.
- Protected base-demo, H1, H2 seed-42 gates: **PASS 10/10** for each. Normalized identities match their references and metric differences are empty; physical hashes are in `GRID_MODE_SMOKE.json`.
- An extra pinned islanded `ctx.step` comparison completed **16 of 24** scenario hashes; all 16 matched both repetitions and the Phase 0 reference. The remaining eight were not run to completion, so this is not reported as a full 24-scenario pass.
- The `artifacts/gridsignal: web` workflow was restarted and its log records `GET /` as **200 OK**. The screenshot check shows only the unauthenticated sign-in page; the signed-in S11 UI could not be visually verified.

## Commits and scope

- `588cfa6` — grid-first dispatch and grid-headroom recharge.
- `00bad18` — positive grid meter in the live payload and UI.
- No scenario JSON was changed. No full regression suite, publish, deployment, or push was performed.
