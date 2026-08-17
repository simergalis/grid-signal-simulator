# GridSignal — Margin Contribution Tool: Black-Box Test Suite (BB-MC-1 through BB-MC-20)

**To Replit: execute these against the running application via its actual HTTP API and/or UI — not by calling internal functions directly.** Each test specifies intent and expected observable behavior; adapt exact endpoint paths, query parameter names, and request schemas to what `api/routes/economic_profiles.py` actually exposes. If a described interaction has no corresponding API surface, stop and report that gap rather than approximating it with an internal call.

These are black-box tests: they verify behavior against the Section 30 spec as a contract, treating implementation as opaque. They are deliberately independent of, and do not replace, the existing white-box suite (TC-MC-1 through TC-MC-13, which assert on internal computation and file:line-specific logic). Some cover the same requirements from the outside; that overlap is intentional — a black-box pass where the corresponding white-box test also passes is a stronger signal than either alone.

## Report format

For each test: PASS/FAIL, the actual request/response (or UI steps taken) as evidence, and — for any FAIL — whether the defect is in the calculation, the API contract, or the input validation layer. After all 20: a summary table (ID, PASS/FAIL, one-line note) and, per the standing project convention, explicit statement of any spec ambiguity encountered while writing the actual requests (state "none" if none).

---

### CRUD and persistence

**BB-MC-1 — Create, list, and fetch reflect the same data.**
Create an Economic Profile via `POST` with a full Cost Configuration and one tenant's Revenue Configuration. Then `GET` the list endpoint and confirm the new profile appears; `GET` it by id and confirm every submitted field matches exactly (including the nested tenant rate).
*Expected:* all three calls return consistent, matching data. No field silently dropped or defaulted.

**BB-MC-2 — Partial update changes only what was submitted.**
Create a profile with fields A, B, C set. `PUT` an update containing only field B. `GET` the profile afterward.
*Expected:* B reflects the new value; A and C are unchanged from their original values — not reset to null, not reset to a default. This is the `is not None` override contract, observed from outside.

**BB-MC-3 — Delete removes the profile.**
Create a profile, confirm it's fetchable, `DELETE` it, then `GET` it by id again.
*Expected:* the second `GET` returns 404 (or the API's equivalent not-found response) — not a 200 with stale or empty data.

### Validation and tagging

**BB-MC-4 — Omitted fields surface as `PROPOSED_HERE` in the API response.**
Create a profile leaving the BESS marginal cost field unset. `GET` the profile.
*Expected:* the response marks that field as unset/`PROPOSED_HERE` (whatever the API's actual representation is) rather than silently substituting a value with no indication it wasn't operator-entered.

**BB-MC-5 — Invalid input is rejected, not silently accepted or crashed on.**
Attempt to create a profile with (a) a negative overage rate, and separately (b) a tenant rate entry missing `tenant_id`.
*Expected:* both attempts return a 4xx validation error with a message identifying the problem field. Neither should return 500, and neither should succeed and silently store bad data.

### Per-tenant billing logic

**BB-MC-6 — Three tenants, three independent billing bases, in one profile.**
Configure Tenant A per-MW-committed, Tenant B per-MW-consumed, Tenant C per-GPU-hour, all in the same profile.
*Expected:* fetching the profile shows each tenant's basis and rate independently — changing one doesn't affect another's stored configuration.

**BB-MC-7 — Usage exactly at the Contracted Allocation produces zero overage.**
Configure a tenant with Contracted Allocation = 4,500 MWh. Generate a proforma against a run where that tenant's metered usage is exactly 4,500 MWh (boundary value).
*Expected:* overage revenue for that tenant is exactly $0; all revenue is at the base rate. This is the boundary case between "within" and "over" — verify it doesn't fall on the wrong side by an off-by-one or floating-point margin.

**BB-MC-8 — Usage above allocation splits correctly.**
Same setup as BB-MC-7, but with usage at 5,110 MWh (610 MWh over).
*Expected:* revenue = (4,500 × base_rate) + (610 × overage_rate), and the report shows within-allocation and overage as separate line items, not a single blended figure.

**BB-MC-9 — No overage rate configured bills flat, without error.**
Configure a tenant with a Contracted Allocation but no Overage rate. Generate a proforma where usage exceeds the allocation.
*Expected:* all usage bills at the base rate. No error, no crash, no implicit zero-revenue treatment of the excess usage.

**BB-MC-10 — Zero-usage tenant produces zero revenue and zero allocated cost, not a crash.**
Include a tenant in the profile that has zero metered usage in the underlying run (e.g., an idle tenant).
*Expected:* that tenant's row shows $0 revenue and $0 allocated COGS/FixedCost — not a divide-by-zero error in the usage-weighting allocation (MC-7), and not an omitted row.

### Dispatch-derived cost logic

**BB-MC-11 — Grid export periods don't reduce cost.**
Generate a proforma against a run that includes at least one tick where the site is net-exporting to the grid.
*Expected:* the export ticks contribute $0 to grid COGS — not a negative cost. Total grid COGS should be observably consistent with import-only accounting (spot-check: it shouldn't be lower than what import-only ticks alone would produce).

**BB-MC-12 — Configured curtailment cost appears in the report.**
Configure a curtailment $/job-hour rate, generate a proforma against a run containing a curtailment event.
*Expected:* the affected period's Margin Contribution reflects the curtailment deduction as a distinct line item, and the underlying scenario's dispatch behavior is unaffected (cross-check against the scenario's own results — curtailment cost modeling must not have altered dispatch).

### Aggregation and rollup

**BB-MC-13 — Per-tenant rows sum exactly to the aggregate.**
Generate a proforma for a multi-tenant profile. Sum each tenant's Margin Contribution from the response and compare to the reported aggregate total.
*Expected:* exact match (within floating-point rounding tolerance, not a material discrepancy). This is an arithmetic identity, not a modeling assumption — any mismatch is a defect.

**BB-MC-14 — Monthly/Quarterly/Annual scale proportionally.**
Generate a proforma for the same run and profile at Monthly, Quarterly, and Annual period settings.
*Expected:* Quarterly ≈ 3× Monthly and Annual ≈ 12× Monthly (within the tolerance implied by the 730/2190/8760-hour scale factors) — confirming the scaling multiplier is actually applied consistently across the three period options, not hardcoded to one.

**BB-MC-15 — Period scaling requires explicit confirmation.**
Attempt to generate a Quarterly or Annual proforma without providing whatever confirmation flag/step the implementation requires for the scaling assumption (per MC-1's resolution).
*Expected:* the system either rejects the request or clearly surfaces the scaling assumption for confirmation before proceeding — it must not silently scale and return a result with no indication the assumption was applied.

### Cross-scenario and export

**BB-MC-16 — Comparison mode ranks two scenarios correctly.**
Run two scenarios against the same Economic Profile, request a comparison.
*Expected:* the response includes both scenarios' Margin Contribution figures, correctly ordered/ranked relative to each other (higher margin scenario identifiable as such).

**BB-MC-17 — CSV export is structurally complete.**
Export a generated proforma as CSV.
*Expected:* the file parses as valid CSV, contains one row per tenant plus an aggregate row, and includes the operational-margin scope disclaimer text (MC-4) somewhere in the file — not just in the on-screen UI.

### Determinism and session-scope error handling

**BB-MC-18 — Repeat generation is identical.**
Generate a proforma for a given run + profile. Generate it again immediately after, same inputs.
*Expected:* the two responses are identical field-for-field (or byte-identical if the API returns a hashable/exportable format) — no re-computation artifact, no timestamp or ordering difference in the data itself.

**BB-MC-19 — Unknown/expired run_id returns 410, not a crash.**
Request a proforma using a fabricated or no-longer-resident `run_id` (simulating the post-restart session-scope case, MC-11).
*Expected:* HTTP 410 with an operator-readable message indicating the scenario data is no longer available and the scenario should be re-run — not a 500 error, not a silently empty report.

**BB-MC-20 — Still-active run_id returns 409, not a crash or partial result.**
Start a scenario run, and before it completes, request a proforma against its `run_id`.
*Expected:* HTTP 409 with a message indicating the run hasn't finished yet — not a partial/incomplete proforma presented as final, and not a 500 error.

---

## Coverage note

This suite deliberately applies boundary-value analysis (BB-MC-7 vs. BB-MC-8), equivalence partitioning across billing bases (BB-MC-6), error guessing on malformed input (BB-MC-5), and state-transition coverage on the run lifecycle (BB-MC-19, BB-MC-20 — not-found / in-progress / complete are three distinct states, only the last of which should ever produce a report). It does not re-test the internal sign-convention or dt-integration logic already covered white-box by TC-MC-1 and TC-MC-11 — BB-MC-11 checks the *observable effect* of that logic (export doesn't reduce cost) without asserting on how it's computed internally.
