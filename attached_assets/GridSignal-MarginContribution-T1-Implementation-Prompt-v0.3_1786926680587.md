# GridSignal — T1 Implementation Prompt (v0.3 — grounded in T0 discovery)

**Read this whole prompt, and open `margin-contribution-mockup.html` in a browser, before writing anything.**

This version replaces every `[ASSUME]` marker from v0.2 with confirmed file paths and line numbers from the T0 discovery report. Three architecture decisions were made explicitly by the product owner (not inferred) and are locked below — do not revisit them without stopping and reporting why.

**Locked decisions:**
1. **Dispatch data durability: in-memory MVP.** Margin Contribution reports can only be generated while the originating server session/process is alive. No new durable timeseries persistence is being built in this phase. A restart means the operator must re-run the scenario before generating a report — this is a known, accepted limitation, not a bug to work around.
2. **EconomicProfile scoping: `site_id` FK, no RLS** — matching the live pattern used by `Scenario` and `AssetConfig` (`runtime/persistence.py:163–165, 196–198`), not the `tenant_id` + RLS pattern that exists only in the unapplied reference schema doc.
3. **Per-tenant MWh: quick approximate sum**, computed at the service layer from existing per-job `est_draw_mw` fields. This is explicitly an approximation, not a metered reading, and must be disclosed as such in the report (see MC-10 below).

Attached: `margin-contribution-mockup.html` — a static visual mockup. It is the visual target for Phase 4's **content**, not its chrome — see the Phase 4 caveat below before building navigation. No number in it is real data.

---

## Governing spec

Forecast Engine Functional Spec Addendum, Section 30, v0.4. Formulas, field definitions, FR/NFR list, and acceptance test matrix (TC-MC-1 through TC-MC-13) are binding.

## Design tokens (from the mockup — use exactly)

```css
--bg:#0A1120;        --panel:#111B2E;      --panel-2:#0D1626;
--border:#213049;    --border-soft:#1A2740;
--text:#E7EDF5;      --text-dim:#8CA0BF;   --text-faint:#5C7191;
--teal:#2DD4BF;      --teal-dim:#175C54;
--amber:#F5A524;     --amber-dim:#4A360E;  /* PROPOSED_HERE + overage flags only */
--green:#34D399;
--red:#F87171;        --red-dim:#3A1E1E;
```
Fonts: Space Grotesk (display), Inter (UI body), IBM Plex Mono (every dollar/percentage/MW/MWh figure — labels never mono, numbers always mono). Allocation bar: filled teal for within-allocation usage; hatched amber (`repeating-linear-gradient(135deg, var(--amber) 0 4px, #B8791A 4px 8px)`) for overage, present only when `over_alloc_tenant > 0` — no amber sliver when a tenant hasn't gone over.

## Standing rules

- **Single source of truth for dispatch.** All per-tick dispatch fields (`turbine_output_mw`, `bess_output_mw`, `grid_exchange_mw`, `p_renewable_mw`, `p_renewable_curtailed_mw`, `p_total_mw`, etc. — full list at `runtime/run_manager.py:275–603`) come from `GET /runs/{run_id}/timeseries` (`api/routes/runs.py:644–716`) only. Never recompute site power draw independently.
- **`is not None` discipline.** Follow `api/routes/runs.py:194–200` and `api/schemas.py:1267–1287` exactly — each override field tested independently, `None` means unchanged. Reference the documented rationale at `runtime/solar_sim.py:116–124` (0.0 is a valid physical value, not falsy) if anyone questions why.
- **No invented constants.** Conservative rate card figures ($150/kW-mo, $70/MWh, 1.3× overage) are UI defaults an operator can overwrite, never hardcoded fallback values in calculation code.
- **No PDF work.** No PDF library exists in the codebase (confirmed absent). Export is CSV-only for this phase, via the existing Blob/download pattern. Do not add a PDF dependency without stopping and reporting first.
- **Mockup copy is real UI copy.** Reuse its exact strings, not lorem ipsum.

## Report format — after every phase

1. Files changed, line counts.
2. Each acceptance criterion, quoted verbatim, PASS/FAIL, with evidence.
3. Any spec section (30.1–30.10) found contradictory or underspecified. State "none" if none.
4. Out-of-scope temptations encountered and not acted on. State "none" if none.
5. Full test suite result, pre-existing failing/excluded tests stated explicitly by ID.
6. Any open item (MC-1 through MC-11, list at bottom) implementation had to assume a resolution for — flag it, don't silently resolve it.

---

## Phase 1 — Data model: EconomicProfile persistence

**Scope.** New tables, modeled directly on the `Scenario` / `AssetConfig` pattern in `runtime/persistence.py:163–211`:

- `economic_profile`: `id` PK, `site_id` FK (matching `AssetConfig.site_id`, `persistence.py:163–165`), `name`, Cost Configuration fields (grid TOU rates by period, turbine fuel + amortized capital, BESS marginal + amortized capital, solar amortized capital, curtailment $/job-hour or SLA credit rate) — all `Optional[float]`, all individually taggable `PROPOSED_HERE`.
- `economic_profile_tenant_rate`: `id` PK, `economic_profile_id` FK, `tenant_id` (matching the values in `_TENANT_DEFS` — `A`, `B`, `C`, per `runtime/scenario_factory.py:852–865`), `billing_basis`, `base_rate`, `contracted_allocation`, `overage_rate`, optional `sla_credit`. One row per tenant per profile.

**Required first step — do not skip:** locate the exact mechanism that currently creates the `scenario` and `asset_config` tables (likely `Base.metadata.create_all` or a startup script near `persistence.py`) and use that identical mechanism for these two new tables. T0 found no migration runner (Alembic or otherwise) anywhere in the tree — **do not introduce one** without stopping and reporting first.

**Acceptance criteria:**
- AC-1.1: Every Cost/Revenue numeric field `Optional`, `is not None` semantics, individually `PROPOSED_HERE`-taggable.
- AC-1.2: An `economic_profile` can be created, named, saved, and re-fetched by id, independent of any Scenario.
- AC-1.3: `economic_profile_tenant_rate` supports independent billing basis, base rate, Contracted Allocation, Overage rate per tenant.
- AC-1.4: No dispatch-plane file (`runtime/run_manager.py`, `core/simulation_core.py`) imports from, or is imported by, the new persistence code.
- AC-1.5: Tables use `site_id`, not `tenant_id` + RLS (per locked decision 2).

---

## Phase 2 — Pre-scenario UI: "Configure Economics"

**Scope.** New control in `ScenarioPlannerPage.tsx`'s Scenario Parameters panel (lines 228–301), adjacent to the existing "Run Scenario →" button (lines 289–298) — wrap both in a flex row, or place the new control immediately before/after it.

**Important distinction — two different precedents apply to two different things:**
- **Visual/interaction style** may borrow from `GpuNodeGeneratorModal.tsx`'s tabbed modal structure (lines 145–147 onward) and the design tokens above.
- **Data persistence must NOT follow `gpuGeneratorStore.ts`** — that store is Zustand-only, ephemeral, doesn't survive reload. An Economic Profile must persist durably (FR-30.1 requires reuse across scenarios). Follow the **Scenario CRUD pattern instead**: backend `api/routes/scenarios.py:1079–1216` (POST/GET-list/GET-by-id/PUT/DELETE), frontend `frontend/src/store/scenarioStore.ts:18–38, 91–121` (`createScenario`/`updateScenario` pattern) — build a new `economicProfileStore.ts` on the same shape, hitting new `/economic-profiles` routes backed by Phase 1's tables.

**Acceptance criteria:**
- AC-2.1: "Configure Economics" reachable before "Run Scenario" is clicked.
- AC-2.2: Saving an Economic Profile doesn't trigger or require a scenario run.
- AC-2.3: A saved profile can be selected and applied to a new scenario before run.
- AC-2.4: `PROPOSED_HERE`-tagged fields are visually distinguishable (amber tag styling).
- AC-2.5 (FR-30.6): Contracted Allocation and Overage rate present per tenant; a tenant with no Overage rate bills flat, no error state (TC-MC-9).
- AC-2.6: Reload the page after saving a profile — it's still there. (This is the specific behavior that distinguishes this from the GPU Node Generator pattern; test it explicitly.)

---

## Phase 3 — Post-scenario calculation: Margin Contribution engine

**Scope.** Given a `run_id` (session-scoped, per locked decision 1) and an attached `economic_profile_id`, compute per-tenant and aggregate Margin Contribution.

**Data retrieval:** `GET /runs/{run_id}/timeseries` (`api/routes/runs.py:644–716`). **Handle the session-scope limitation explicitly** — if the endpoint returns HTTP 410 or 409 (server restarted since the run completed, per `api/routes/runs.py:665–680, 774–787`), the UI must show a clear message ("This scenario's data is no longer available — re-run it to generate a Margin Contribution report") rather than a crash or a silently empty report. This is a required acceptance criterion, not an edge case to skip.

**Per-tenant MWh (approximate, per locked decision 3):** for each tick in the returned `tick_dicts`, sum `active_jobs_detail[].est_draw_mw` grouped by `tenant_id`, multiply by that tick's duration in hours, accumulate across the run. Before implementing: confirm from `runtime/run_manager.py:275–603` whether tick duration (`dt_s`) is fixed or variable across a run — if variable, the per-tick duration must be used, not an assumed constant. **Stop and report if tick spacing is irregular in a way that complicates this.**

**COGS_energy:** per tick, `turbine_output_mw × turbine_$/MWh + bess_output_mw × bess_$/MWh + grid_exchange_mw × grid_$/MWh` (fields per `run_manager.py:275–603`), integrated over the run using the same per-tick duration as above. **Stop and report if `grid_exchange_mw`'s sign convention (import-positive vs. export-positive) isn't already documented somewhere in the codebase** — do not guess a sign and silently get import/export backwards.

**Formulas (Section 30.5, unchanged):**
```
within_alloc_tenant  = min( usage_tenant(period), ContractedAllocation_tenant )
over_alloc_tenant     = max( 0, usage_tenant(period) − ContractedAllocation_tenant )
Revenue_tenant(period) = within_alloc_tenant × BaseRate_tenant + over_alloc_tenant × OverageRate_tenant
MarginContribution(period) = Σ Revenue_tenant − Σ COGS_energy − FixedCost − Σ CurtailmentCost
```
Pooled COGS_energy and FixedCost allocated to tenants by metered-usage weighting (MC-7) — flag explicitly as assumption, never present as measured.

**`grid_exchange_mw` sign convention (confirmed, Section 30.5):** positive = grid import (site drawing power from the grid); negative = grid export (site pushing power to the grid). Confirmed at `runtime/simulation_core.py:2089`, where the internal convention is negated before writing the tick dict. COGS_energy must use `max(0, grid_exchange_mw)` — only import ticks contribute to grid purchase cost. Do not treat export ticks as negative cost.

**Acceptance criteria:** TC-MC-1 through TC-MC-13 verbatim from spec Section 30.9, plus:
- AC-3.1: 410/409 from the timeseries endpoint produces the operator-facing message above, not an error page.
- AC-3.2: Per-tick duration is read from actual tick data, not assumed constant, unless T0's finding on fixed dt is confirmed correct during implementation.

**Explicit stop-and-report gate before this phase begins:** confirm how period-scaling (MC-1) is handled — repeat-and-scale a single trace, or multiple stitched runs — before writing monthly/quarterly/annual rollup code. The mockup's "Scaled from a 1-month trace, repeated flat across the quarter — confirmed by operator" note is required, functional UI, not decoration.

---

## Phase 4 — Report output and comparison mode

**Scope.** Build the Margin Contribution report using `margin-contribution-mockup.html` as the visual target for its **content** — the tenant cards, allocation bars, aggregate summary bar, meta strip, period toggle, and disclaimer.

**Caveat on the mockup's chrome — read before building:** the mockup's left sidebar (Live Dashboard / Asset Configuration / Scenario Planner / Grid Connection / Reports nav items) was illustrative, not confirmed against the real app shell. T0 found `ScenarioPlannerPage.tsx` renders inside a tab in `App.tsx` (lines 331–332, 422–425), which suggests a tab-based shell, not necessarily a left-nav-with-sub-items shell. **Do not build new sidebar navigation to match the mockup.** Instead: `ScenarioPlannerPage.tsx:303–378` already renders a cost-stream results table (baseline/alternative/delta) — the closest existing "proforma" surface in the app. Add the Margin Contribution report as a new section on that same page, adapting the mockup's content design into whatever container that page already provides. **If it's unclear where this content should physically live within the existing tab structure, stop and report rather than guessing** — this is a real UX call, not a styling detail.

**Export:** CSV only, via the existing Blob/download pattern at `RunControlBar.tsx:27–74` (or the duplicate in `DemoBar.tsx:69–137`). No PDF.

**Acceptance criteria:**
- AC-4.1: Report traces back to its exact `run_id` and `economic_profile_id` (FR-30.4) — displayed, not just stored.
- AC-4.2: Comparison mode shows ≥2 scenarios' Margin Contribution side-by-side, correctly ranked (TC-MC-6).
- AC-4.3: Regenerating the same report from the same still-live `run_id` produces identical output, no new dispatch computation triggered (NFR-30.2 / TC-MC-7).
- AC-4.4: Every export carries the operational-margin scope disclaimer (MC-4) **and** the per-tenant-MWh-is-approximate disclosure (MC-10, below).
- AC-4.5: Allocation bar renders zero amber when `over_alloc_tenant = 0`, proportional hatched amber when positive.
- AC-4.6: All monetary and MW/MWh figures render in mono; labels and chrome do not.
- AC-4.7: CSV export includes both the per-tenant table and the aggregate row.

---

## Phase 5 — Determinism and full test suite

**Scope.** Follow the exact pattern in `tests/test_step13_agents.py:151–180` (TC-48): run the same completed scenario twice, serialize the Margin Contribution output, SHA-256 hash both, assert equal. This should hold naturally given `tick_dicts` are themselves deterministic (confirmed by `tests/test_fabric_model.py:39–55`) — the one new risk is the per-tenant MWh summation introducing order-of-operations non-determinism (e.g., dict iteration order). Check for that specifically.

**Acceptance criteria:**
- AC-5.1: TC-MC-10 (determinism) passes using the `test_step13_agents.py` hash-comparison structure.
- AC-5.2: Full suite run, TC-MC-1 through TC-MC-13 passing, reported per the standard format above.

**Section 30.9 — Acceptance test matrix (TC-MC-1 through TC-MC-13):**

| ID | What it verifies | Notes |
|---|---|---|
| TC-MC-1 | `grid_exchange_mw < 0` (export) contributes zero to COGS; `> 0` (import) contributes correctly | Two test functions in file |
| TC-MC-2 | Turbine fuel cost proportional to `turbine_output_mw` | — |
| TC-MC-3 | BESS marginal cost on dispatch only; `bess_output_mw < 0` (charging) excluded | — |
| TC-MC-4 | Per-tenant MWh: `est_draw_mw × dt_h` summed per tick, grouped by `tenant_id` | — |
| TC-MC-5 | `scale_factor = target_hours / run_duration_hours` for Monthly (730 h), Quarterly (2190 h), Annual (8760 h) | Parametrized × 3 periods |
| TC-MC-6 | Revenue split: `within_alloc × base_rate + over_alloc × overage_rate`; zero overage when under contract | Two test functions in file |
| TC-MC-7 | Pooled COGS allocated by `usage_weight = tenant_mwh / total_mwh` | — |
| TC-MC-8 | Aggregate margin identity: `total_revenue − total_energy_cogs − total_capex_cost − total_curtailment_cost` | — |
| TC-MC-9 | Tenant with `overage_rate = None` bills all usage at `base_rate`; no error, no crash (AC-2.5) | — |
| TC-MC-10 | Determinism: identical inputs → identical SHA-256 hash across two calls | Added beyond original spec |
| TC-MC-11 | Variable `dt_s`: COGS computed using per-tick duration from `sim_time_seconds` delta, not assumed constant | Added beyond original spec |
| TC-MC-12 | HTTP 410 raised when `run_id` not found in `RunManager` (server-restart path) | Added beyond original spec |
| TC-MC-13 | HTTP 409 raised when run is still active (tick data not yet complete) | Added beyond original spec |

**Test count note (`pytest --collect-only -q` verified):** 13 spec IDs → 15 source functions → 17 collected instances. TC-MC-1: 2 functions (import-guard + positive-import assertion). TC-MC-5: 1 function parametrized × 3 periods (monthly, quarterly, annual) → 3 instances at runtime. TC-MC-6: 2 functions (within+over split and no-overage fallback). TC-MC-2/3/4/7/8/9/10/11/12/13: 1 function each (10 IDs). Source function sum: 2 + 1 + 2 + 10 = 15. Collected instance sum: 2 + 3 + 2 + 10 = 17.

**Spec contradictions encountered during implementation:** none.

**Out-of-scope temptations declined during implementation:** none.

---

## Open items carried into implementation

MC-1 (period-scaling), MC-2 (rate realism), MC-3 (curtailment/SLA authority), MC-7 (COGS allocation by weighting proxy), MC-8 (allocation semantics for capacity-billed tenants), MC-9 (allocation period reconciliation), plus two new items from T0:

- **MC-10 — Per-tenant MWh is an approximation, not a metered value.** It's derived by summing instantaneous per-job draw (`est_draw_mw`) across ticks, not from a dedicated energy meter or validated accumulator. Every report must disclose this. Revisit if/when real per-tenant metering (TPCM) is wired in.
- **MC-11 — Session-scope limitation.** Margin Contribution reports are only generable while the originating server process is alive (locked decision 1). A server restart between running a scenario and generating its report requires re-running the scenario. Revisit if durable timeseries persistence (the already-built-but-unwired `SqlitePersistedTimeseriesSink`) is connected in a later phase.

If any phase requires taking a further position on any of these, stop and report the decision point rather than picking a resolution.
