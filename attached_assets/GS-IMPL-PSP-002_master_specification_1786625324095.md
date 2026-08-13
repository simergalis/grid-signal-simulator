# GS-IMPL-PSP-002 — Master Implementation Specification
## Power Source Priority, Economic Dispatch, and Multi-Tenant Admission

**Status:** DRAFT, consolidated, for direct Replit implementation.

**Supersedes, for build purposes only:** GS-IMPL-PSP-001. This document is now
the single source of truth for what to build and how the pieces connect.
Functional Spec §29 (Power Source Economic Priority Advisory) and §30
(Multi-Tenant Power Budget Enforcement) remain the authoritative *product*
definitions — this document does not change what either section decided,
it resolves two gaps that existed only because those sections and the
code built after them were written in separate conversations without a
final reconciliation pass:

1. **`EconomicDispatchLoop` was implemented in code but never formally
   specified.** §29 defines only the ranking advisory
   (`PowerSourceRanker`). The continuous autonomous-tier dispatch
   capability was built afterward, directly in code, with no
   corresponding spec section. §2 below is that missing specification.
2. **Nothing previously stated, in one place, that `PMSTestDouble` is
   simulator-only and must never be the escalation target in a real
   deployment.** §4 below states this explicitly and gives the production
   substitute.

If anything in this document conflicts with §29 or §30's *product intent*
(not their implementation gaps), the functional spec wins and this
document has a defect — flag it rather than silently building to this
document's version.

---

## 0. Reading order for implementation

Read in this order. Do not start coding from the middle.

1. §1 — file layout and module boundaries (what goes where)
2. §2 — every data contract, complete field tables (what gets passed around)
3. §3 — every module's public API (what gets called)
4. §4 — the system tick/event sequence (what calls what, in what order — the section most likely to prevent a wrong implementation)
5. §5 — production vs. simulator substitution (what changes between a demo and a real deployment)
6. §6 — non-goals (what must never be built, even if it seems convenient)
7. §7 — parameter catalogue requirements
8. §8 — build phases, in order, each with a stop-and-report
9. §9 — test requirements
10. §10 — open items
11. §11 — acceptance criteria

---

## 1. File layout

```
gridsignal_sim/
  core/
    power_source_priority.py     — PowerSourceRanker (§3.1)
    economic_dispatch_loop.py    — EconomicDispatchLoop (§3.2, newly specified here)
    tenant_budget_gate.py        — BudgetGate (§3.3, from §30, not yet in a code file — build fresh per this spec)
  runtime/
    pms_test_double.py           — PMSTestDouble (§3.4) — SIMULATOR ONLY, see §5
  scripts/
    scenario_author.py           — offline Mistral scenario authoring (§3.5) — OFFLINE ONLY, see §5
  tests/
    test_power_source_priority.py
    test_economic_dispatch_loop.py   (new)
    test_tenant_budget_gate.py       (new)
    test_pms_test_double.py          (new)
    test_no_forbidden_imports.py     (new, structural — §6.4)
```

**Reference implementations already written and passing tests**, to be
relocated into this tree, not rewritten from scratch:
`power_source_priority.py`, `pms_test_double.py`, `economic_dispatch_loop.py`,
`scenario_author.py`, `test_power_source_priority.py`. Treat these as
canonical starting points. `tenant_budget_gate.py` does not yet exist as
code — §3.3 below is its complete specification, written fresh for this
document.

**Import boundary, absolute:**

| Directory | May import from | May be imported by |
|---|---|---|
| `core/` | Parameter catalogue, standard library | `runtime/`, the real dispatch/advisory pipeline, tests |
| `runtime/` | `core/`, standard library | The simulator harness, tests. **Never** the production pipeline |
| `scripts/` | `core/` (for type definitions only), `mistralai`, standard library | Nothing. Never imported by `core/` or `runtime/`, ever |

---

## 2. Data contracts

### 2.1 `PowerSource` (input to `PowerRanker`)

| Field | Type | Notes |
|---|---|---|
| `source_id` | str | Unique per instance |
| `source_type` | enum: `solar, grid_firm, grid_reserved, grid_spot, bess, turbine, fuel_cell` | |
| `dispatchable` | bool | Solar is always `False` |
| `counts_toward_reserve` | bool | Per §7.1/§24.1; fuel cell and firmed-solar default `False` pending PSP-3 |
| `marginal_cost_mwh` | float, USD/MWh | Current-period cost; TOU-varying for grid, flat for PPA sources |
| `response_latency_class` | enum: `instant, ramp_limited, thermal_lag, not_commanded` | Metadata only — not read by ranking logic, see PSP-7 |
| `authority_tier` | enum: `autonomous, confirm, human_only` | Per §23.4/§24.3 |
| `available_mw` | float | Live telemetry |
| `cost_basis_note` | str, optional | Provenance string, e.g. `"PG&E B-20, off_peak_summer"` |

### 2.2 `RankedSource` / `AdvisoryOutput` (output of `PowerRanker`)

`RankedSource`: `rank, source_id, source_type, marginal_cost_mwh, available_mw, reserve_eligible, authority_tier, cost_basis_note` — direct annotation of `PowerSource`, no new information.

`AdvisoryOutput`: `ranked_sources: list[RankedSource]`, `excluded_non_dispatchable: list[str]` (solar source_ids), `note: str` (fixed advisory-only disclaimer, see reference implementation).

### 2.3 `DispatchAllocation` / `ShortfallEvent` / `DispatchResult` (output of `EconomicDispatchLoop`)

| Type | Fields |
|---|---|
| `DispatchAllocation` | `t_s: float`, `source_id: str`, `allocated_mw: float`, `price_mwh: float` |
| `ShortfallEvent` | `t_s: float`, `demand_mw: float`, `covered_mw: float`, `shortfall_mw: float` |
| `DispatchResult` | `t_s: float`, `allocations: list[DispatchAllocation]`, `cost_this_tick: float` (see §2.3.1 — renamed and redefined from the reference implementation's `total_cost_per_hour`), `shortfall: ShortfallEvent \| None` |

**2.3.1 — Correction to the reference implementation.** The reference
`economic_dispatch_loop.py`'s `total_cost_per_hour` field assumed a full
hour of holding at every tick, flagged as a known defect in
GS-IMPL-PSP-001 §3.3. This document renames the field to `cost_this_tick`
and requires it be computed as `Σ(allocated_mw × price_mwh × tick_duration_hours)`,
where `tick_duration_hours` is passed into `step()` explicitly rather than
assumed. This is a required change before Phase 2 (§8) is considered
complete, not an optional cleanup.

### 2.4 `WorkloadSignal` (extends §10, per §30.3)

All fields from Functional Spec §10, plus:

| Field | Type | Required | Notes |
|---|---|---|---|
| `tenant_id` | str | **Yes** | New in this subsystem. Missing `tenant_id` fails schema validation per §17.2 — quarantined, never defaulted |

### 2.5 `TenantPowerBudget` (per §30.4)

| Field | Type | Notes |
|---|---|---|
| `tenant_id` | str | |
| `site_id` | str | |
| `budget_mw` | float | Externally supplied, not GridSignal-derived |
| `source_of_truth` | str | E.g. `"colo contract system"` |
| `effective_from` / `effective_until` | ISO-8601 UTC | No mid-window silent switch, per §17.3's pattern |

No record for a `(tenant_id, site_id)` pair means unbounded — no gate
applied. See MT-1 (§10) for why this is a known soft spot, not an
oversight.

### 2.6 `WorkloadCommand` (existing, §23.5 — reused, not modified)

Unchanged. `BudgetGate` (§3.3) issues `action = defer` on this exact
contract. No new `action` enum value is created by this subsystem.

### 2.7 `OperatorResponseProfile` / `PMSLogEntry` (simulator only, §3.4)

As in the reference `pms_test_double.py`: `OperatorResponseProfile` holds
`response_latency_s: dict[int, float]`, `approve: dict[int, bool]`,
defaults for both. `PMSLogEntry` holds `t_s, source_id, action, authority_tier, detail`.
**Both types live in `runtime/` only** — do not import them from `core/`.

---

## 3. Module APIs

### 3.1 `core/power_source_priority.py` — `PowerRanker`

```
class PowerRanker:
    def rank(self, sources: list[PowerSource]) -> AdvisoryOutput
```

Behavior: exclude solar, exclude `dispatchable=False`, exclude
`available_mw <= 0`, sort ascending by `marginal_cost_mwh`, annotate,
return. No side effects. No hardware access. See reference implementation
— unchanged except costs must be sourced from the parameter catalogue
per §7, not the module-level dict.

### 3.2 `core/economic_dispatch_loop.py` — `EconomicDispatchLoop` (newly specified)

```
class EconomicDispatchLoop:
    def step(
        self,
        t_s: float,
        tick_duration_hours: float,   # NEW — required, see §2.3.1
        hour_of_day: int,
        season: Literal["summer", "winter"],   # NEW — required, see §3.2.1
        demand_mw: float,
        sources: list[PowerSource],
    ) -> DispatchResult
```

Behavior, restated precisely from GS-IMPL-PSP-001 §3.3 with both
corrections folded in:

1. Reprice grid sources for `(hour_of_day, season)`. Non-grid sources
   pass through unchanged.
2. Call `PowerRanker.rank()` on the repriced sources.
3. Filter to `authority_tier == autonomous` only. **This filter is not
   optional and not configurable** — see §6.3.
4. Greedily allocate cheapest-first until `demand_mw` is covered or
   autonomous sources are exhausted.
5. Compute `cost_this_tick` per §2.3.1.
6. If demand remains uncovered, emit a `ShortfallEvent`. Do not raise an
   exception, do not retry, do not reach for a `confirm`/`human_only`
   source — return the event and stop. The caller (§4) is responsible for
   what happens next.

**3.2.1 — Correction to the reference implementation.** The reference
`pge_price_for_hour()` was summer-only, flagged as blocking defect PSP-5.
This corrected signature takes `season` explicitly. The caller (whatever
invokes `EconomicDispatchLoop.step()` from the main simulator/dispatch
loop) is responsible for deriving `season` from the simulated calendar
date — this module does not read a clock itself, simulated or otherwise
(consistent with §6.2's no-runtime-clock-reads rule, which until now
applied only to `runtime/`; it applies here too because `step()` must be
callable identically inside a simulator replay and inside a live system).

### 3.3 `core/tenant_budget_gate.py` — `BudgetGate` (new, per §30.5–30.7)

No reference implementation exists yet. Build fresh, exactly as follows.

```
class BudgetGate:
    def evaluate(
        self,
        signal: WorkloadSignal,          # must have event_type == "queued"
        budget: TenantPowerBudget | None,   # None if unconfigured — see §2.5
        tenant_committed_mw: float,       # sum of tenant's active + provisional draw
        predicted_draw_mw: float,         # this job's predicted draw, §4.1 formula
        rotation_state: RotationState,    # §3.3.1, for §30.7's fairness rule
    ) -> WorkloadCommand | None
```

Returns `None` (no action, job proceeds) when:
- `budget is None` (unconfigured tenant, MT-1), or
- `tenant_committed_mw + predicted_draw_mw <= budget.budget_mw`

Returns a `WorkloadCommand(action="defer", target=signal.job_id, authority=<current operating tier, §23.4 Ladder A>)`
when the budget would be exceeded.

**3.3.1 — `RotationState`** (implements §30.7, previously described only
in prose, now given a concrete shape):

```
@dataclass
class RotationState:
    selection_count: dict[str, int]   # tenant_id -> count, rolling window
    window_days: int = 30

    def least_recently_selected(self, candidate_tenant_ids: list[str]) -> str:
        # lowest count first; ties broken by caller using priority class, then job age
        ...

    def record_selection(self, tenant_id: str) -> None:
        ...
```

`BudgetGate` itself only evaluates one job at a time and does not choose
*among* tenants — `RotationState` is consulted by whatever caller is
handling multiple simultaneously-eligible deferrals across tenants (§4
step 2), consistent with §30.7's description of rotation as a tie-breaker
layered on top of, not inside, the per-job evaluation.

**Durability requirement (MT-4):** `RotationState`'s `selection_count`
is Tier 0 state per §22.3 — it must survive a restart. Not optional for
production; may be in-memory only for early simulator work, but must be
flagged loudly (log warning on startup) if running without persistence.

### 3.4 `runtime/pms_test_double.py` — `PMSTestDouble`

Unchanged from the reference implementation. Restated for completeness:

```
class PMSTestDouble:
    def __init__(self, response_profile: OperatorResponseProfile)
    def process(self, advisory: AdvisoryOutput, t_s: float) -> list[PMSLogEntry]
```

**This class must never be instantiated, imported, or referenced from
`core/`.** See §5.

### 3.5 `scripts/scenario_author.py` — offline only

Unchanged from the reference implementation.
`generate_operator_response_profile(persona, requests, model) -> dict`,
called once per persona, writing a JSON file consumed by `PMSTestDouble`
at simulator startup. Never called during a run. Never imported by
`core/` or `runtime/`.

---

## 4. System tick / event sequence

This is the section most likely to prevent a wrong implementation. Two
independent triggers exist — a job-lifecycle event, and a fixed-interval
tick — and their relative ordering matters.

### 4.1 On `WorkloadSignal(event_type = queued)`

```
1. Compute predicted_draw_mw for the job (§4.1 formula, sized off
   requested allocation).
2. Look up TenantPowerBudget for (signal.tenant_id, signal.site_id).
3. Look up tenant_committed_mw (sum of that tenant's starting/running/
   provisionally-admitted jobs).
4. command = BudgetGate.evaluate(signal, budget, tenant_committed_mw,
                                   predicted_draw_mw, rotation_state)
5. If command is not None:
     - Issue command via the WorkloadCommand write-back path (§23.5).
     - rotation_state.record_selection(signal.tenant_id)
     - STOP. The job does not proceed to admission this cycle.
6. If command is None: no action. The job proceeds through the
   scheduler's own native admission logic, unaffected by this subsystem.
```

This step never touches `EconomicDispatchLoop` or §7 Dispatch
Arbitration. It runs strictly earlier, at `queued`, before a job has any
live draw to arbitrate or dispatch against.

### 4.2 On every real-time control tick (existing §3.1 parent-spec cadence — 5-second tick, or on any WorkloadSignal event)

```
1. §7 Dispatch Arbitration runs FIRST, unchanged, exactly as already
   specified. It handles any transient step-load using latency-based
   asset selection. This subsystem does not participate in this step
   and must not be inserted before or interleaved with it (§6.3 lists the
   double-controller failure mode this ordering prevents).

2. AFTER §7 has resolved for this tick, EconomicDispatchLoop.step() runs,
   operating on the resulting steady-state P_total(t) and the current
   autonomous-tier source states:

     result = EconomicDispatchLoop().step(t_s, tick_duration_hours,
                                            hour_of_day, season,
                                            demand_mw=P_total(t),
                                            sources=autonomous_and_confirm_sources)

3. If result.shortfall is not None:
     → go to §4.3 (escalation). Do not let the tick silently pass with
       unmet demand and no record of it.

4. Record result.allocations and result.cost_this_tick for the economics
   screen / cost tracking. This is read-only downstream consumption —
   nothing in this subsystem writes to hardware at this step either.
```

### 4.3 Escalation (triggered by a `ShortfallEvent` from step 4.2.3)

**This step differs between simulator and production. See §5 for the
full explanation — do not implement only the simulator branch and assume
it generalizes.**

```
Simulator:
  entries = PMSTestDouble(response_profile).process(advisory_output, t_s)
  # advisory_output here is a fresh PowerRanker.rank() call restricted to
  # confirm/human_only sources — NOT the autonomous-only ranking from 4.2.
  Record entries for the test/demo log.

Production:
  Publish the shortfall, plus a PowerRanker.rank() output over
  confirm/human_only sources, via the existing §28.3 northbound
  REST/MQTT advisory channel to the real PMS/operator console.
  GridSignal's involvement ends at publication. Nothing in core/ waits
  for, polls for, or assumes a particular response time.
```

---

## 5. Production vs. simulator substitution — read this before wiring anything to `runtime/`

**The gap this section closes:** GS-IMPL-PSP-001 built `PMSTestDouble` as
a simulator test double without ever stating, in the same document,
what production does instead. A Replit session working from that
document alone could reasonably wire `core/`'s escalation path directly
to `PMSTestDouble`, since it was the only escalation-handling code that
existed. That would be wrong, and would not be caught by any test in
GS-IMPL-PSP-001's suite, because every test in that suite exercises the
simulator path only.

**The rule:** `core/` never imports from `runtime/`. Full stop. The
escalation step in §4.3 is written as two branches specifically because
this is a real fork in behavior, not a refactoring detail:

| | Simulator | Production |
|---|---|---|
| What resolves a `confirm`/`human_only` request | `PMSTestDouble`, driven by a pre-generated `OperatorResponseProfile` | The real PMS and a real human operator, via the console |
| Where the code lives | `runtime/` | Nowhere in this codebase — it's the PMS vendor's system and the operator's judgment |
| What GridSignal does | Calls `PMSTestDouble.process()` directly, in-process | Publishes to REST/MQTT (§28.3) and returns — no further involvement |
| Determinism | Required — same profile, same result, every replay | Not applicable — a real operator's response time and decision are not GridSignal's to predict or control |

**Enforcement:** §6.4's structural import test catches an accidental
`runtime/` import inside `core/`. It does not catch a *correct* import
inside a *simulator harness* file that itself lives outside both
`core/` and `runtime/` (e.g. a top-level `run_simulation.py`) — that file
choosing to call `PMSTestDouble` is correct and expected. The boundary is
about what `core/` and `runtime/` may import from each other, not about
whether `PMSTestDouble` may exist and be called at all.

---

## 6. Non-goals — restated and consolidated from §29.5, §30.8, and GS-IMPL-PSP-001 §5

1. **No southbound writes.** No module anywhere in this subsystem holds
   a Modbus TCP, DNP3, OPC UA, or IEC 61850 client. This includes
   `PMSTestDouble`, which simulates a decision, never a live connection.
2. **No runtime LLM calls.** `scenario_author.py`'s Mistral calls happen
   once, offline, before a run starts. Nothing in `core/` or `runtime/`
   calls any LLM API, ever.
3. **`EconomicDispatchLoop` never allocates to `confirm`/`human_only`
   tier sources.** This is enforced by the hard filter in §3.2 step 3,
   not by convention — if a future change makes this filter configurable
   or bypassable, that change is out of scope for this subsystem and
   needs its own product decision, not a quiet code change.
4. **`EconomicDispatchLoop` does not replace §7 Dispatch Arbitration.**
   Restated because it's the easiest boundary to blur under deadline
   pressure: real-time transient response remains §7's job, selected by
   latency against Δt_lead. This subsystem only reallocates steady-state
   load between transients, strictly after §7 has resolved for the tick
   (§4.2 step 1–2's ordering is not incidental).
5. **`BudgetGate` does not replace scheduler-native resource quotas.**
   Kueue/Volcano/YuniKorn's GPU-count and memory quotas are untouched.
   `BudgetGate` only ever adds a power-budget-motivated `defer`.
6. **This is not a billing mechanism.** `TenantPowerBudget` is consumed
   for admission purposes only.
7. **No new `WorkloadCommand` action type.** `BudgetGate` reuses the
   existing `defer` action under the existing §23.4 authority table.

---

## 7. Parameter catalogue requirements

| Parameter | Status | Required before production use |
|---|---|---|
| PG&E TOU rates, both seasons, all periods | Currently hardcoded, summer-only (PSP-5, blocking) | Full table, catalogued, cited, dated |
| Fuel cell PPA rate | Hardcoded single value | Per-deployment parameter |
| Solar PPA rate | Hardcoded single value | Per-deployment parameter |
| BESS marginal cost basis | **Does not exist** (PSP-6) | New parameter; methodology undecided — see §10 |
| `TenantPowerBudget` records | Does not exist by default | Per-tenant, per-site, sourced from colo contract system |
| Operator response profiles | Illustrative personas only | Real profiles per design partner, or explicit fallback |

No entry above may retain a hardcoded fallback in shipped `core/` code.
A hardcoded fallback that silently activates on a missing catalogue entry
is the same defect class as an unverified diagnostic field — it looks
correct and isn't.

---

## 8. Build phases

Each phase ends with a stop-and-report. Do not start the next phase
until the prior one's report has been reviewed.

### Phase 0 — Parameter catalogue scaffolding
**Do:** Add catalogue entries or explicit "unavailable, raises" stubs for
every row in §7.
**Do not:** Add a hardcoded BESS cost fallback. Do not approximate a
missing winter TOU table from the summer one.
**Report:** Catalogue coverage, stub behavior for each gap.

### Phase 1 — Module relocation and import boundary
**Do:** Move the four existing reference files into the tree per §1.
Write `test_no_forbidden_imports.py` (§9, §6.4).
**Do not:** Change any public interface during the move.
**Report:** Import diff; structural test passing.

### Phase 2 — Correct the three named defects
**Do:** §2.3.1's `cost_this_tick` fix, §3.2.1's season-aware TOU pricing,
BESS cost sourced-or-fails per §7.
**Do not:** Touch `PowerRanker`'s ranking algorithm or `PMSTestDouble`'s
gating logic — scope is these three defects only.
**Report:** Before/after output showing season-correct pricing differs
between a summer and winter scenario hour.

### Phase 3 — Build `BudgetGate` and wire §4.1
**Do:** Implement `core/tenant_budget_gate.py` per §3.3, including
`RotationState`. Wire the `queued`-event handler per §4.1.
**Do not:** Let `BudgetGate` import anything from `runtime/`. Do not
invent a new `WorkloadCommand` action.
**Report:** A short scenario showing a job deferred for tenant-budget
reasons, and the resulting `WorkloadCommand`, end to end.

### Phase 4 — Wire the full tick sequence and the production/simulator fork
**Do:** Implement §4.2 and §4.3 exactly as ordered. Implement both
branches of §4.3's fork — simulator calling `PMSTestDouble`, production
publishing via §28.3. **Both branches must exist even if production
publishing is stubbed to a log line for now** — the fork itself, not just
the simulator branch, is the deliverable of this phase.
**Do not:** Let `core/` import `PMSTestDouble` under any code path,
including a conditional one gated by an environment flag. The
simulator/production selection happens at the harness level, outside
`core/` and `runtime/` both — see §5.
**Report:** A run showing §7 Dispatch Arbitration and
`EconomicDispatchLoop` firing in the correct order on the same tick,
timestamped in logs.

### Phase 5 — Test suite completion and scenario authoring
**Do:** Wire `scenario_author.py` to the real `ScenarioSpec` schema.
Implement all tests in §9.
**Do not:** Add any code path calling `scenario_author.py` or any LLM
client from `core/` or `runtime/`, even behind a flag.
**Report:** Full suite run; `test_no_forbidden_imports.py` still passing.

---

## 9. Test requirements

(Provisional numbering — renumber into the master TC- sequence at
integration time.)

| ID | Scenario | Expected result |
|---|---|---|
| TC-C1 | Solar never ranked | Excluded from `AdvisoryOutput.ranked_sources` under any cost |
| TC-C2 | Non-reserve-eligible flagged, not excluded | `reserve_eligible: false`, still ranked |
| TC-C3 | `EconomicDispatchLoop` never allocates to `confirm`/`human_only` | `ShortfallEvent` produced instead |
| TC-C4 | `cost_this_tick` scales with `tick_duration_hours` | Halving tick duration halves reported cost for identical allocation |
| TC-C5 | TOU pricing is season-correct | Same hour, `season="summer"` vs `"winter"` → different `marginal_cost_mwh` |
| TC-C6 | `BudgetGate` returns `None` for unconfigured tenant | No `WorkloadCommand` issued (MT-1 behavior, confirmed as specified) |
| TC-C7 | `BudgetGate` returns `defer` when budget exceeded | Correct `WorkloadCommand`, `authority` matches current operating tier |
| TC-C8 | Missing `tenant_id` fails schema validation | Quarantined per §17.2 |
| TC-C9 | Rotation prevents repeat selection | Lowest-`selection_count` tenant chosen among equally-eligible candidates |
| TC-C10 | §7 Arbitration always precedes `EconomicDispatchLoop` in tick order | Log timestamps show Arbitration resolution strictly before dispatch-loop allocation on the same tick |
| TC-C11 | `core/` has zero dependency on `runtime/` | Static import check passes |
| TC-C12 | `runtime/` and `scripts/` have zero southbound/LLM/RNG dependency | Static import check passes (§6.4) |
| TC-C13 | Simulator escalation path never fires in a production-configured run | Given a `production` harness flag, `PMSTestDouble` is never instantiated — verify via mock/spy, not just absence of error |
| TC-C14 | Deterministic replay | Same `ScenarioSpec` + `OperatorResponseProfile`, two simulator runs → byte-identical `PMSLogEntry` and `DispatchResult` sequences |

---

## 10. Open items — consolidated, deduplicated

Renumbered here as `PSP-` for anything about the ranking/dispatch
mechanism, `MT-` for anything about tenant budgeting. Cross-references to
the original §29/§30 numbering are given for traceability.

**Blocking for MVP (must resolve before any design-partner-facing use):**

- **PSP-5** (was §29's open item) — TOU pricing was summer-only; §3.2.1
  fixes the interface, Phase 2 must supply the real winter table.
- **PSP-6** — BESS has no defined marginal cost basis anywhere in the
  spec. Arguably the highest-priority gap in this entire subsystem, since
  unlike grid/fuel-cell/solar prices, there's no external market
  reference to validate a wrong number against.
- **MT-1** — Unconfigured-tenant default is silently unbounded. Same
  shape as PSP-6: a soft failure that looks like correct behavior.
  Recommend an `unbudgeted_tenant` tag, mirroring §17.3's
  `uncalibrated_site` pattern, before this reaches a design partner.

**Not blocking, but should not be silently resolved during implementation:**

- **PSP-1** — Whether §29 ships as a GridSignal capability at all, versus
  living entirely in the PMS or a third-party optimizer per §28.7, is
  still a product decision, not an engineering one.
- **PSP-2** — All §29.6 reference cost data is market-sourced, not
  measured at any design-partner site.
- **PSP-3** — Fuel cell / firmed-solar reserve eligibility undetermined;
  currently defaults conservatively to `false`.
- **PSP-4** — Fuel cell is not yet a formal §7.1 asset class.
- **PSP-7** — `response_latency_class` is stored but unvalidated against
  §7's asset table; low urgency.
- **MT-2** — `TenantPowerBudget` is a flat ceiling; no time-varying
  (TOU-style) tenant allocation is expressible.
- **MT-3** — No authorization workflow specified for *changing* a
  `TenantPowerBudget` once set.
- **MT-4** — `RotationState` durability across a restart is a stated
  requirement (§3.3.1) but not yet implemented in any reference code.
- **MT-5** — Admission-time predicted draw uses requested allocation, not
  confirmed allocation; may be conservative relative to actual granted
  resources.

---

## 11. Acceptance criteria

This subsystem is ready for design-partner-facing use only when:

1. All of §9's tests pass, including TC-C10 and TC-C13 — the two tests
   that specifically verify the tick-ordering and simulator/production
   boundary this document exists to nail down.
2. No entry in §7's parameter table has a silent hardcoded fallback in
   shipped `core/` code.
3. PSP-5, PSP-6, and MT-1 are resolved, not merely stubbed.
4. `test_no_forbidden_imports.py` runs in CI and has never been skipped
   or weakened to pass.
5. PSP-1 has an actual product answer. This subsystem should not reach a
   design partner while its own parent capability is still an open
   product question.
6. A reviewer who has read only this document — not the prior three, not
   the conversation that produced them — can correctly answer: "what
   happens on a shortfall in production, and what module handles it?"
   without guessing. If that question requires opening another document
   to answer correctly, this document has not done its job.
