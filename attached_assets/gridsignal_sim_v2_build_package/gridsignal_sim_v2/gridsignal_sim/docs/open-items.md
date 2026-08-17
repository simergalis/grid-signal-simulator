# Implementation-Level Open Items

This file tracks implementation-level gaps and deferred invariants that are
distinct from the spec-level open-items registry (PSP-/PX-/CL-/A- prefixes)
maintained in the formal spec documents.  Entries here describe constraints
that are correct but unenforced, or coverage gaps that are intentionally
deferred.  They are not bugs — the simulator produces correct output — but
they represent places where a future change could silently break an invariant
that currently holds by convention only.

---

## IMPL-1 — Fleet `max_nodes` agreement across KubeDemandAgent instances

**Status:** Convention only. Runtime assertion added at construction time
(scenario_factory.py) catches *mismatched* `max_nodes` values the moment three
agents are built, so a misconfigured spec fails loudly at run start rather than
silently under-enforcing the shared ceiling.

**What is enforced:** The assertion checks that all three agents share an
identical `max_nodes` value after construction.  If they don't, it raises with
a message naming the offending tenant and both values.

**What is NOT enforced / future risk:** The assertion only fires at
construction.  A future change that mutates `agent.config.max_nodes` after
construction, or that introduces a fourth agent with a different ceiling, would
not be caught by the current check.  Additionally, the ramp patch in
`simulation_core.py` uses `state.kube_agents[0].config.max_nodes` as the fleet
denominator; if the invariant ever breaks in a way the construction assertion
misses, this silently uses the wrong denominator.

**Review trigger:** Revisit if the number of agents changes from three, if
`max_nodes` becomes per-tenant rather than fleet-wide, or if any post-
construction mutation of `KubeConfig` is introduced.

---

## IMPL-2 — `payload_guard` verifies top-level broadcast keys only; sub-field shape is not checked

**Status:** Intentional deferred scope.

`test_payload_guard.py` confirms that every top-level key in the broadcast dict
(built by `_tick_result_to_dict` in `runtime/run_manager.py`) has a
corresponding typed field in `frontend/src/types.ts`.  This is enforced via
source-level parsing.

**What is NOT verified:** Sub-field shape correspondence between Python
dataclasses and TypeScript interfaces is not checked.  For example, if a field
is added to `QueuedJobSummary` (Python) but omitted from `QueuedJobSummary`
(TypeScript), or vice versa, the guard does not catch it.  The correspondence
is maintained by convention — the two definitions must be updated in lockstep.

**Review trigger:** Any change to `QueuedJobSummary`, `ActiveJobSummary`, or
any other sub-object carried inside `kube_metrics` (or any other nested dict in
the broadcast) should include a manual check that the TypeScript interface
mirrors the Python fields.  A sub-field schema test could be added in the
future to automate this.

---

## IMPL-3 — EconomicProfile DB persistence across server restart (AC-2.6)

**Status:** Unit-tested via ORM; live round-trip not yet verified in production.

`EconomicProfile` and `EconomicProfileTenantRate` rows are created via
`runtime/persistence.py` ORM classes and picked up by the existing
`Base.metadata.create_all(checkfirst=True)` call in `create_auth_tables()`
(lifespan startup).  The persistence path is correct, but a live end-to-end
verification — create a profile, restart the server process, confirm the
profile is still present via `GET /api/economic-profiles/` — has not been
performed.

**What is NOT enforced / future risk:** If the database URL changes between
restarts, or if `create_auth_tables()` is not called before the first API
request, profiles created in one session will not be visible after restart.
The ORM table creation is idempotent (`checkfirst=True`), so adding the
tables again is always safe.

**Review trigger:** Revisit if the database backend is swapped, if
`create_auth_tables()` is removed or made conditional, or if any migration
script drops and recreates the `economic_profiles` or
`economic_profile_tenant_rates` tables.

---

## IMPL-4 — Margin Report 410 path shows operator-facing message, not blank panel

**Status:** HTTP 410 path is unit-tested (TC-MC-12); frontend rendering of the
error message has not been visually verified.

`MarginContributionReport.tsx` receives the 410 detail string from the backend
and must render "This scenario's data is no longer available — re-run it to
generate a Margin Contribution report" rather than a blank or crashed panel.
The component has error-state handling wired, but the exact rendering has not
been confirmed against a live 410 response.

**What is NOT enforced / future risk:** If the error boundary in
`MarginContributionReport.tsx` catches the 410 but renders a generic error
rather than the operator-facing string, the UX requirement (AC-3.1) is
violated silently.

**Review trigger:** Revisit if the error display path in
`MarginContributionReport.tsx` is refactored, or if the 410 detail string
format returned by `api/routes/economic_profiles.py` changes.

---

## IMPL-5 — Over-allocation amber bar renders only when `over_alloc_flag = true`

**Status:** Flag is correctly computed and returned in the proforma response;
conditional rendering in `MarginContributionReport.tsx` (AllocBar component)
has not been visually verified against a run where a tenant exceeds their
contracted allocation.

The `over_alloc_flag` field in `TenantProformaRow` drives the hatched amber
fill on the allocation bar.  The component renders the amber portion as
`over_alloc_flag ? <AmberSegment> : null`.  This path is exercised by the
TC-MC-6 unit test but has not been confirmed against a rendered report in a
live session.

**What is NOT enforced / future risk:** If the amber segment's CSS class is
accidentally applied unconditionally, or if the `over_alloc_flag` value is
coerced to a truthy string rather than a boolean in the JSON response,
the bar will render amber for all tenants regardless of allocation status.

**Review trigger:** Revisit if `TenantProformaRow` or the AllocBar rendering
logic in `MarginContributionReport.tsx` is changed.

---

## IMPL-FC-HEADROOM-001 — Fuel cell capacity excluded from kube admission headroom *(resolved)*

**Status:** Fixed. Acceptance test `TC-FC1a/TC-FC1b` in `tests/test_kube_powercap.py`.

**What was wrong:** `kube_demand.py` line 358 computed
`headroom_mw = turbine_headroom_mw + bess_headroom_mw`, omitting fuel cell idle
capacity. The kube admission gate (`power_cap_active` fires when
`headroom_mw < 2.5 MW`) was therefore blind to up to `fc_rated_mw` of available
headroom whenever a fuel cell asset was present but not yet dispatched, causing
the scheduler to hold jobs earlier than the true power balance required.

**Fix (three files):**

1. `core/kube_demand.py` — added `fuel_cell_headroom_mw: float = 0.0` to
   `KubeGridState` dataclass. Field defaults to `0.0` so non-FC scenarios are
   unaffected. Updated line 358 to include the new term in the headroom sum.
2. `core/simulation_core.py` — computed `fuel_cell_headroom_mw` alongside the
   existing turbine/BESS headroom at `KubeGridState` construction time, using
   `max(0.0, state.fuel_cell_rated_mw - fuel_cell_output_mw)` — same treatment
   as BESS (flat rated minus current output, floored at zero).
3. `tests/test_kube_powercap.py` — added `TestKubePowercapFuelCellHeadroom`
   (TC-FC1a: cap clears when FC brings total above threshold; TC-FC1b: non-FC
   scenarios unaffected).

**Scope:** The fix propagates to all three consumers of `headroom_mw` — the
admission gate (line 359), the eviction gate (line 529), and
`KubeMetrics.headroom_mw` (line 585 → WS payload → operator display). All three
are intended to include FC headroom.

**Review trigger:** Revisit if a new dispatchable source (hydrogen storage,
backup diesel) is added to the merit order — it must also be added to
`KubeGridState` and the headroom sum, per the same pattern.
