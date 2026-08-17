---
name: margin-contribution-tool
description: §30 Margin Contribution Tool implementation decisions, wiring notes, and constraints.
---

## Key decisions

**grid_exchange_mw sign convention (confirmed):**
`grid_exchange_mw` in tick_dicts is **positive on import** — `simulation_core.py:2089`
negates the internal balance-residual convention before writing to TickResult.
COGS formula uses `max(0, grid_exchange_mw)`.  Negative values = export → $0 cost.

**MC-1 period scaling (locked decision):**
Repeat-and-scale: `scale_factor = target_hours / run_duration_hours`.
Monthly = 730 h, Quarterly = 2190 h, Annual = 8760 h.
Operator must click "Confirm" in the report UI before the scale note shows as acknowledged.
This is a functional gate, not decoration — matches mockup spec.

**MC-10 per-tenant MWh (locked approximation):**
Summed from `active_jobs_detail[].est_draw_mw × dt_h` per tick, grouped by `tenant_id`.
Not metered.  Disclosure is mandatory in every ProformaResponse and CSV export.
Keys confirmed from run_manager.py:292/298: `tenant_id`, `est_draw_mw`.

**MC-11 session-scope (locked):**
tick_dicts are in-memory only; lost on server restart.
`get_proforma` returns 410 with a clear operator-facing message if `manager.get_completed(run_id)` is None.
Returns 409 if run is still active.

**DB-backed profiles (AC-2.6):**
`EconomicProfile` and `EconomicProfileTenantRate` ORM classes in `runtime/persistence.py`.
Created via `Base.metadata.create_all(checkfirst=True)` called in `create_auth_tables()`
(same lifespan mechanism as auth tables — no Alembic needed).
`EconomicProfileStore.ts` is a frontend cache layer only; DB is source of truth.

**dt_s is variable (AC-3.2):**
Per-tick duration computed as `sim_time_seconds[i] - sim_time_seconds[i-1]`.
Tick 0 uses `sim_time_seconds[0]` (run starts at t=0).  Never assumed constant.

**COGS separation:**
- COGS energy (variable): grid import + turbine fuel + BESS marginal dispatch
- Fixed cost (capex): turbine amortised capital + BESS capex + solar capex
Both allocated to tenants by usage weight (`tenant_mwh / total_mwh`).

**overage_rate absent (TC-MC-9 / AC-2.5):**
`overage_rate is None` → bills at `base_rate` for overage.  No error state, no crash.
Effective overage rate: `rate.overage_rate if rate.overage_rate is not None else rate.base_rate`.

**Rate card UI defaults (placeholder only):**
Conservative defaults shown as input placeholder text:
grid_peak=$70, grid_offpeak=$45, turb_fuel=$35, turb_capex=$15,
bess_marginal=$5, bess_capex=$25, solar_capex=$12, curtail=$40.
These are NEVER used as fallback values in calculation code.
Empty field → 0.0 contribution (None → 0.0 via `_coalesce()`).

**PROPOSED_HERE fields:**
Operator can tag any cost field as a third-party estimate.
Stored as JSON list in `economic_profile.proposed_here_fields` column.
Shown as amber badge in modal; amber count disclosed in report and CSV.

## Files created/modified (for orientation only — not as changelog)

Backend:
- `runtime/persistence.py` — added EconomicProfile + EconomicProfileTenantRate after RunTimeseries
- `api/routes/economic_profiles.py` — NEW: full CRUD + proforma calculation + CSV export
- `api/app.py` — added economic_profiles_routes.router registration

Frontend:
- `frontend/src/types.ts` — added EconomicProfile/ProformaResponse types at end
- `frontend/src/store/economicProfileStore.ts` — NEW: DB-backed Zustand store
- `frontend/src/components/EconomicProfileModal.tsx` — NEW: tabbed Configure Economics modal
- `frontend/src/components/MarginContributionReport.tsx` — NEW: proforma report component
- `frontend/src/components/ScenarioPlannerPage.tsx` — added modal/report wiring

Tests:
- `tests/test_margin_contribution.py` — 17 tests, TC-MC-1 through TC-MC-13, all pass

## Test results (confirmed)
All 17 unit tests pass.  TypeScript compiles cleanly.  Vite build succeeds (1148 kB bundle).
