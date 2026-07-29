# GridSignal Simulator — Replit Build Plan v2.2: Phased Prompt Sequence

**Purpose.** A sequence of scoped prompts to hand Replit's agent one at a time, each building on
the working skeleton (`gridsignal_sim/`) rather than asking for "the whole simulator" in one pass.
Each phase has its own acceptance criteria pulled from the specs, so you have a concrete pass/fail
check before moving to the next prompt — instead of discovering gaps only after everything's been
generated.

**This supersedes `GridSignal_Replit_Build_Plan.md`.** It keeps all nine original phases, adds
seven for the advisory agent layer, and reorders them. Original phase numbers are preserved in the
headings so references from the review and remediation documents still resolve.

**How to use this.**
1. Upload `gridsignal_sim/` (the skeleton, tests included) to the Repl first, and confirm
   `PYTHONPATH=. python -m pytest tests/ -v` passes before Step 2. If it doesn't, something broke
   in transfer — fix that before asking for new work.
2. Paste one step's prompt. Let it finish. Run that step's verification yourself before pasting
   the next one — don't queue multiple steps at once.
3. If a step's output doesn't meet its acceptance criteria, say so specifically ("the WebSocket
   endpoint isn't in the route list" / "this test still fails") rather than re-pasting the same
   prompt — vague retries tend to get vague fixes.
4. Each prompt names the spec sections that govern its work. Keep the **Forecast Engine Functional
   Spec v2.5**, the Simulator Functional Spec, and the Simulator Design Spec attached for the whole
   sequence so those references resolve.

---

## 0. What changed from v1, and why

### 0.1 A correction to the agentic design, not to this plan

The Agentic Prototype Design v0.1 resolved the "Replit-independent databases" requirement by
putting Tier 1 in an external PostgreSQL and Tier 2 in external object storage. **That was wrong
for the simulator, and the original build plan was right.**

v2.5 §22.7 is explicit, and it is the section that governs here rather than §22.2:

> For the demonstration simulator the three tiers collapse to two […] Tiers 0 and 1 share one
> embedded write-ahead-logged store file in separate table namespaces, accessed through an ORM so
> that promoting Tier 1 to PostgreSQL is a connection-string change. […] The simulator's
> control-plane store must be a local file, not a networked database, even where a hosted one is
> available in the environment. A demonstration whose persistence layer contradicts the
> architecture it demonstrates is worse than one with less persistence.

The agentic design applied the production architecture (§22.2) where the simulator mapping (§22.7)
applies. Consequences:

- **Original Phase 1 stands unchanged in approach** — one SQLite file, `TimeseriesSink` Protocol
  untouched. It gains tables, not a different store.
- **Original Phase 8's "no external database or cloud service" criterion stands verbatim.** My
  earlier proposal to amend it is withdrawn.
- **Review finding A-8 (partitioned-table primary keys) is deferred, not dropped.** SQLite has no
  declarative partitioning, so the defect cannot bite here. The corrected DDL in `schema_fix.sql`
  remains the production target for the promotion path.
- No external Postgres to provision, no region matching, no Tier 1 latency injection.

The "Replit-independent" requirement is still met, and met better: the store is a **portable file
behind a swappable ORM interface**, so nothing is trapped in Replit's runtime and promotion is a
connection-string change. That is §22.1 principle 4 working as intended.

### 0.2 The spec chain is two versions stale

```
Forecast Engine Functional Spec  v1.6  ──►  v2.5   (+8 sections, +49 test cases)
          │                                   │
          ▼                                   ▼
Simulator Functional Spec  ────────────►   NOT UPDATED
Simulator Design Spec      ────────────►   NOT UPDATED
Build Plan v1              ────────────►   NOT UPDATED
```

| | Simulator specs (v1.6-era) | v2.5 |
|---|---|---|
| Acceptance tests | **27** (TC-01…TC-27) | **76** (TC-01…TC-76) |
| Console | 4 screens | **9 pages** |
| Non-dispatchable supply | Solar as a spec extension | §7.1.1 `P_renewable(t)`, `P_dispatch_required(t)` |
| BESS | Rated capacity and SoC | §7.1.2 anchor-adjusted bridging |
| Absent entirely | — | §21 learning plane, §22 storage tiers, §23 curtailment, §24 procurement, §25 network telemetry, §26 agents, §27 maintenance, §28 execution layer |

**Original Phase 9's "TC-01 through TC-27" is now 36% of the matrix.**

Rather than stall on updating two documents first, **this plan carries the reconciliation**: each
amended or new step names its governing **v2.5** section directly instead of routing through the
stale middle specs. Update those specs afterwards, from what was actually built. Note it on their
cover pages in the meantime so nobody treats them as authoritative.

### 0.3 Three places the skeleton already has what the agent layer needs

**1. The plane separation already exists.** `core/` = "deterministic, synchronous, no asyncio";
`runtime/` = "the only place asyncio appears" (Design Spec §2 principle 2, §4.3). That boundary
**is** v2.5 §21.1's control/advisory split, and it predates the agentic design. So the
`@control_plane` decorator specified in Agentic Design §1.2 is unnecessary — the package boundary
is the decorator — and Step 4's purity gate extends an invariant the project already has rather
than inventing one.

**2. `WebSocketHub.broadcast()` already handles slow clients correctly** — `asyncio.gather` with
per-socket exception isolation (Design Spec §4.4). The broadcaster in Agentic Design §2.2 was a
**regression against working code**. Discard it; extend the hub.

**3. `TimeseriesSink` is already the promotion seam** (Design Spec §6). Nothing about Tier
promotion requires touching `RunManager`.

### 0.4 Execution order

| Step | Phase | Status |
|---|---|---|
| 1 | **0** Baseline transfer check | **Audit half already executed — see `GridSignal_Skeleton_Audit.md`** |
| 1b | **—** Classifier repair + layering fix | **New. Three reproduced bugs; must be first** |
| 2 | **1** Persistence layer | Amended — same store, more tables, per-segment tags |
| 3 | **7** Skeleton gaps + Δt_lead ramp + superposed α(t) | **Moved earlier and rescoped** |
| 4 | **10** Control-plane purity gate | New |
| 5 | **11** Simulated clock and clock domains | New |
| 6 | **2** FastAPI wiring | Unchanged |
| 7 | **3** Live Dashboard | Amended |
| 8 | **4** Scenario Builder + Asset Config | Amended |
| 9 | **5** Results/playback + verdicts | Amended |
| 10 | **13** Deterministic arbitration + pre-staging | New |
| 11 | **6** SCADA layer + §28 execution layer | Amended — absorbs §28 |
| 12 | **12** Advisory scaffolding | New |
| 13 | **14** The six buildable agents | New |
| 14 | **15** Network telemetry + procurement | New |
| 15 | **16** Maintenance, ramp relaxation, Planner | New |
| 16 | **8** Replit deployment | Unchanged |
| 17 | **9** Full acceptance matrix + CI | Amended — 27 → 76 |

**Demo-able checkpoints.** After Step 11 the deterministic simulator is complete against v2.5 with
no agents — that alone shows lead time, two-clock staging, the renewable equivalence, and
anchor-adjusted bridging. After Step 13 the agent layer and the TC-48 kill-switch demonstration are
live. Both are worth showing before the rest finishes.

---

## Step 1 · Phase 0 — Baseline transfer check *(audit half already executed)*

**Governs:** Forecast Engine Functional Spec v2.5 §5.2, §5.3, §7.1.1, §7.1.2, §12; Design Spec §5.

**Goal:** Confirm the skeleton landed intact in the Repl.

> **The audit half of this step is already done** — see `GridSignal_Skeleton_Audit.md`, which was
> executed against the skeleton directly on July 29, 2026 and whose findings are folded into Steps
> 1b, 2, and 3 below. Run only the baseline commands here; the environment is what still needs
> verifying, not the code. If you want the agent to re-derive the audit as a cross-check, the
> original prompt is retained in the audit document's §1.

**Prompt:**
> The `gridsignal_sim/` directory is a working skeleton for the GridSignal Simulator. **Don't
> modify anything in this phase** — this is diagnosis only.
>
> First, run `PYTHONPATH=. python -m pytest tests/ -v` and `PYTHONPATH=. python
> runtime/example_usage.py` from inside `gridsignal_sim/`, and report both outputs. Also run
> `PYTHONPATH=. python scripts/load_test.py --matrix` and report whether the 1x case passes.
>
> Then audit the skeleton against the attached **Forecast Engine Functional Specification v2.5**
> and report findings as a table. Check specifically:
>
> 1. **`evaluate_tick()` call order.** Report the current fixed order verbatim from
>    `core/simulation_core.py`. v2.5 §7.1.1 defines `P_dispatch_required(t) = P_total(t) −
>    P_renewable(t)`, and §7.2 requires the Dispatch Arbitrator to size ΔP against
>    `P_dispatch_required`, not `P_total`. Report whether `P_dispatch_required` exists as a named
>    term at all, and if Solar is evaluated *after* Turbine/BESS in the current order — because if
>    it is, arbitration is sizing against the wrong quantity.
> 2. **BESS bridging.** Report whether `core/dispatch.py` reduces bridging capability by a
>    `P_anchor_reserve` term (v2.5 §7.1.2). If the reserve check uses rated capacity and state of
>    charge alone, say so plainly — that is the pre-v2.0 arithmetic.
> 3. **Hardware profiles.** Report whether profiles in `core/models.py` carry a counting unit
>    (§5.2: chassis / cabinet / package / die / accelerator) and a vintage (§5.3).
> 4. **Data-quality tags.** Report which of `unmapped_hardware`, `invalid_payload`,
>    `uncalibrated_site`, `stale_profile` the confidence engine currently composes, and whether
>    they compose independently or overwrite each other.
> 5. **`core/` purity.** List every import in every module under `core/`. Confirm zero `asyncio`,
>    and flag anything reaching a network client, a database driver, or a wall clock
>    (`time.time`, `datetime.now`).
> 6. **`TimeseriesSink`.** Report the Protocol's exact signature and the current
>    `InMemoryTimeseriesSink` implementation.
> 7. **Test coverage.** Which of v2.5's TC-01 … TC-76 have a corresponding test today? Report as a
>    list of covered IDs, not a count.
>
> Do not fix anything. Report only.

**Acceptance criteria:**
- All 10 existing tests pass; `example_usage.py` prints three runs' results without error;
  `load_test.py --matrix` 1x passes. **If any fails, stop and fix transfer/environment before
  Step 2.**
- The audit distinguishes *absent* from *present but pre-v2.5*. "Solar is modelled" and "solar is
  modelled as `P_renewable(t)` feeding `P_dispatch_required(t)`" are different answers and the
  report must not conflate them.
- Item 5 returns a clean `core/` or names every violation. This is the baseline everything after
  Step 4 depends on.
- **No code changed.** If the agent modified anything, revert and re-run.

---

## Step 1b — Classifier repair + layering fix *(COMPLETE — July 29, 2026)*

> **Executed and closed.** 19 tests passing; `test_step1b_findings.py` 6/6; 1x load gate holding
> (p99 tick 3.6 ms against a 1000 ms budget). Four defects fixed, two of them found during the
> step rather than by the audit:
>
> | ID | Defect | Fix |
> |---|---|---|
> | B-1 | `apply_explicit_event()` crashed the next tick | `explicit_active` single-tick bypass; `assert` → `raise ValueError` |
> | B-2 | `UNCERTAIN` unreachable | 45 s expiry routes to `UNCERTAIN`; separate handler fires `JOB_END` after the 30 s grace |
> | B-3 | `JOB_END` not terminal | Terminal check at the top of `record_and_classify` |
> | B-5 | `core/` imported `runtime/` | `scenario_factory` moved to `runtime/`; three import paths updated, no assertions changed |
> | **D1** | `explicit_hold` absent — a >45 s checkpoint self-classified as `UNCERTAIN`, overriding an authoritative scheduler event | `explicit_hold` flag, set on `checkpoint_start`, cleared on `checkpoint_end`; skips the timeout entirely while held |
> | **D2** | `apply_explicit_event` bypassed the terminal guard — a late `checkpoint_end` resurrected a `JOB_END` job | Terminal check added; discarded events logged, not dropped silently |
> | **D4** | `explicit_hold` unbounded — a missing `checkpoint_end` held staging forever | `MAX_EXPLICIT_HOLD_S`; on expiry the hold releases and the **heuristic resumes** rather than jumping to a classification |
>
> D1, D2, and D4 are the same failure class as v2.5 §23.6's dead-man rule: *"a partitioned
> controller must not be able to hold a customer's fleet down indefinitely."* Worth carrying
> forward — every hold introduced in later steps needs the same question asked of it.

**Original prompt retained below for reference.**


**Governs:** v2.5 §6.2, §2 item 4; Design Spec §2 principle 2.

**Why first.** The Step 1 audit reproduced three defects in `core/dispatch.py`'s
`CheckpointClassifier` — the component v2.5 §2 lists as an IP pillar and the only thing gating
turbine ramp-down — plus one layering violation that would fail Step 4's purity gate on day one.
These are bugs, not documented gaps, and everything after this step builds on the classifier's
output.

**Prompt:**
> Four defects. **Write a failing test for each before fixing it**, so the current behaviour is
> demonstrably wrong rather than assumed wrong.
>
> **1. `apply_explicit_event()` crashes the next tick.** It sets `IN_VALLEY` without setting
> `drop_onset_time` or `pre_drop_draw_mw`, so the next `record_and_classify()` hits the assertion at
> the top of the `IN_VALLEY` branch — reproduced as an uncaught `AssertionError`. Per v2.5 §6.2 an
> explicit scheduler `checkpoint_start`/`checkpoint_end` pair is the **authoritative** signal and
> should short-circuit the shape heuristic entirely, not enter its state machine half-initialised.
> Also replace that `assert` with a real guard: asserts are stripped under `python -O`, which would
> turn a visible crash into silent `None` arithmetic on a control path.
>
> **2. `UNCERTAIN` is unreachable dead code.** When a drop fails to recover inside the 45 s window
> the code assigns `JOB_END`, then tests `elif recovered_fraction < 0.90` — a branch only reachable
> when `recovered >= 0.90`. Contradiction, so `UNCERTAIN` is never assigned and the grace-period
> block below it is dead. Per §6.2, 45 s expiry without recovery and without a scheduler `job_end`
> event routes to **`uncertain`**: hold staging for a further 30 s grace period and flag the job.
> `job_end` follows only from an explicit scheduler event, or from that grace period expiring.
>
> **3. `JOB_END` is not terminal.** It sits in the re-entry branch alongside `NORMAL` and
> `CHECKPOINT`, so a classified job flips back to `in_valley` on the next tick — reproduced with a
> held 16% drop oscillating `job_end` → `in_valley` with no input change. Make `JOB_END` terminal
> for that `job_id`.
>
> **4. `core/scenario_factory.py:30` imports `from runtime.run_manager import …`.** `core/` must not
> import from `runtime/`. Either move `scenario_factory` into `runtime/`, or invert the dependency
> behind a Protocol defined in `core/`. **State which you chose and why** — this is a design
> decision, not a mechanical fix.
>
> Then add these tests:
> - **TC-05 … TC-09** from v2.5 Addendum A, including TC-09's exact-boundary case: drop exactly
>   15.0%, duration exactly 30 s, recovery exactly 90.0% at exactly 45 s → classified **checkpoint**,
>   thresholds inclusive.
> - **The §12 effective-PUE identity as a regression test.** At steady state with cooling settled,
>   `P_total / raw_IT_load` must equal `PUE_base × (1 + α_max)`. It currently holds to 2.2e-12 and
>   nothing asserts it. This is the cheapest available guard against the α/PUE double-count that
>   v1.6 was written to fix reappearing.

**Acceptance criteria:**
- Each of the four fixes has a test that **fails against the current code** and passes after.
  "Tests still pass" does not demonstrate a fixed bug.
- TC-05 … TC-09 pass; the §12 identity test passes.
- No `assert` statements remain on any control path in `core/`.
- The layering choice for item 4 is stated, not silently made.

---

## Step 2 · Phase 1 — Persistence layer

**Governs:** Design Spec §6 (Data Model and Persistence); Simulator Functional Spec §8.1 (`Site`,
`AssetConfig`, `Scenario`, `RunTimeseries`, `ControlEvent`); **v2.5 §22.7** (simulator storage
mapping), §17.1, §17.2, §21.6, §5.2, §5.3.

**Goal:** Replace `InMemoryTimeseriesSink` with a real SQLAlchemy-async + SQLite implementation,
and add the v2.5-era tables the later phases need — **in the same single file**, in separate table
namespaces, per §22.7.

**Prompt:**
> Implement the persistence layer described in design spec §6. Add `runtime/persistence.py` with
> SQLAlchemy async models (`aiosqlite` driver) for the entities `Site`, `AssetConfig`, `Scenario`,
> `RunTimeseries`, `ControlEvent` as named in simulator functional spec §8.1. Implement a
> `SqlitePersistedTimeseriesSink` satisfying the existing `TimeseriesSink` Protocol in
> `runtime/run_manager.py` (`append(tick)` and `finalize(run_id, verdict)`) — **do not change that
> Protocol's signature, and do not change `RunManager` or `RunContext`.**
>
> **One SQLite file on disk, WAL mode.** v2.5 §22.7 requires the simulator's control-plane store be
> a local file, not a networked database, even if a hosted one is available in this environment.
> Do not add PostgreSQL, MongoDB, Firebase, or any hosted service. Access everything through the
> ORM so that promoting to PostgreSQL later is a connection-string change (§22.1 principle 4).
>
> **Writes must not block the event loop** (§22.7). Route sink writes through a bounded queue
> drained by its own task rather than awaiting a synchronous write inside the tick path — a
> synchronous embedded-store write in a single-process async app surfaces as latency during
> NFR-2 load testing and gets misattributed to the forecast path.
>
> In the same file, add these additional table namespaces for later phases. They are unused now;
> create the schema and the models only:
>
> - `dedupe_key` — the §17.1 tuple `(site_id, job_id, event_type, event_id)` with a first-seen
>   timestamp, for the 15-minute rolling window.
> - `quarantine` — §17.2. `raw_payload` must be **TEXT, not JSON**, with an optional parsed JSON
>   sidecar: a malformed event may not be valid JSON at all, and §17.2 requires it be logged in
>   full. Include `failure_kind` in (`schema`, `domain`, `unparseable`), `field_name`,
>   `rule_violated`, plus `corrected_by_event` and `cleared_at` for the recovery path.
> - `recommendation` — §21.6 / §26.3. States (`proposed`, `under_review`, `applied`, `rejected`);
>   `originating_agent`; current/proposed value; `observation_count`; window start/end;
>   `evidence_digest`; `estimated_impact`; `reversibility`; `expires_at`; `model_vendor`;
>   `prompt_digest`; `generated_by` in (`model`, `fallback`); `reviewer_id`. Add a CHECK that a row
>   cannot reach `applied` or `rejected` with a NULL `reviewer_id`.
> - `parameter_change_audit` — §21.6, with `reviewer_id` NOT NULL and `effective_from`.
> - `principal` — `principal_id`, `display_name`, `role` in (`viewer`, `operator`, `approver`).
> - `control_event_ack` — acknowledgments live here, **not as a mutable column on
>   `ControlEvent`**, so that `ControlEvent` stays append-only per FR-2.5 / NFR-5.
>
> Also extend the hardware profile model in `core/models.py` with `counting_unit` in (chassis,
> cabinet, package, die, accelerator) per v2.5 §5.2, and `vintage_generation` +
> `vintage_established` per §5.3. Do not add validation logic yet — Step 10 does that. Add
> `STALE_PROFILE` to `DataQualityTag` and a widening factor for it in `ConfidenceEngine`.
>
> **Fix per-segment tagging.** `simulation_core.py` uses a sticky run-global flag
> (`_unmapped_hardware_ever_seen`), so once any unmapped profile appears anywhere, **every**
> subsequent forecast carries the tag forever — including segments no unmapped job contributed to.
> §5.1 and §12 require tagging the affected *segment*. Tags belong to a forecast segment, not to a
> run. Note that `ConfidenceEngine`'s widening factors already exist and compose additively (base
> 0.05, unmapped +0.10, uncalibrated +0.08, invalid_payload +0.15) — keep them, label them in code
> as **chosen values, not derived**, and add the `stale_profile` row.
>
> Write at least three new tests in `tests/test_persistence.py`: a run's ticks all recoverable
> after `finalize()`; two concurrent runs' rows don't interleave incorrectly; persistence survives
> re-opening (new engine instance, same file) with prior data intact. **Do not modify any existing
> test file.** Run the full suite and report.

**Acceptance criteria:**
- All existing tests still pass, unmodified. New tests pass.
- `RunManager`/`RunContext` constructor signatures and the `TimeseriesSink` Protocol are unchanged.
- **One SQLite file. Zero references to any hosted database or cloud service.**
- Sink writes are queued off the tick path — ask the agent to show where, don't assume.
- `scripts/load_test.py --matrix` 1x still passes. This is the first phase that could regress it.

---

## Step 3 · Phase 7 — Skeleton gaps, Δt_lead ramp, superposed α(t) *(moved earlier, rescoped)*

**Governs:** `gridsignal_sim/README.md` stubs; v2.5 §6.1, §7.1.2, §8, §11.1, §4.2.

**Goal:** Four changes that all touch the compute and dispatch terms, done together because doing
them separately means doing several of them twice.

**Prompt:**
> **0. `P_dispatch_required(t)` — do this first; the other three build on it.** v2.5 §7.1.1:
>
> ```
> P_dispatch_required(t) = P_total(t) − P_renewable(t)
> ```
>
> §7.2's ΔP is a change in `P_dispatch_required(t)`, **not** in `P_total(t)`. Today
> `evaluate_tick()` calls `arbitrator.tick(p_total_mw, …)` and computes `net_demand_mw`
> *afterwards*, where it is written into `TickResult` and read by nothing — so solar reduces a
> displayed figure and has zero effect on staging, the reserve check, or the alert.
>
> Move the renewable term ahead of arbitration and pass `P_dispatch_required` to it. Two
> asymmetries must survive implementation:
>
> - **No lead time.** A renewable shortfall carries no advance signal. An inverter trip is a step
>   change with `Δt_lead = 0`. The reserve check treats renewable output as capacity that can
>   vanish without notice.
> - **Availability, not dispatchability.** `P_renewable(t)` is subtracted from the load the fleet
>   must serve. It may **never** be counted toward ramp capability in the §7.2 step-4 shortfall
>   calculation. Turbine ramp rate and BESS discharge are the only terms that close a gap. Write
>   `ramp_capability()` so renewables are structurally absent — no branch to forget.
>
> A compute step-load and a collapse in renewable output are the same event class to the
> Arbitrator (TC-33).
>
> **1. Per-job draw attribution.** `core/simulation_core.py` line 125 sets
> `job_draw_mw = p_compute_mw`, which is the **site-wide** sum across all GPU modules — not the
> module's aggregate, as the inline comment claims. Attribute draw per job so the checkpoint
> classifier sees one job's trace, not the site's.
>
> **2. Δt_lead as an actual ramp.** `GPUModule.apply_signal()` applies the full node count on
> `STARTING` and `advance()` is a no-op, so compute draw steps from zero to full TDP in a single
> tick. The 30–60 s of lead time the product exists to exploit is therefore not simulated at all.
>
> A job entering `STARTING` begins a ramp over its Δt_lead, reaching full TDP at the end, driven by
> `advance()`. Use a piecewise shape matching §6.1's stated physical causes — container init near
> idle, a steep rise through weight load, a plateau at collective warmup — and **tag it in code and
> on the console as a chosen simulator shape with no measured basis**, since §6.1 specifies the
> interval but not the curve inside it.
>
> Also fix the staging call: `simulation_core.py:78` computes `delta_p_mw` as the sum of *all* GPU
> module output *after* the node count has been applied, so ΔP is total site compute rather than the
> predicted step. It must be the increment this job will add.
>
> **You may modify `tests/test_formulas.py` for this item only** — a ramp changes what draw at a
> given tick means, so timing assertions shift. Report every assertion you changed and why.
>
> **3. α(t) per step-load, by superposition.** §8's α(t) has a single onset t₀, and the skeleton sets
> it once on the first non-zero compute sample and never resets it — so the two-stage rise is
> correct for the first step-load of a run and flat for every one after.
>
> **Do not fix this by resetting t₀.** A single α with a reset t₀ multiplies the *whole* lagged
> compute term, so P_cooling collapses to zero for Δt_thermal seconds whenever a new job starts —
> the chillers serving an already-running job would switch off because a different job began.
> Verified: with job A at 5 MW settled and job B adding 10 MW at t=400, naive reset drives
> P_cooling from 1.000 MW to 0.000 MW for 90 s.
>
> Implement superposition instead, consistent with §11.1's rule that concurrent jobs sum
> per-job-instance:
>
> ```
> P_cooling(t) = Σ_k  α_k(t) × ΔP_compute_k(t − Δt_thermal)
> α_k(t) = α_max × (1 − e^−(t − t₀_k − Δt_thermal)/τ)   for t ≥ t₀_k + Δt_thermal, else 0
> ```
>
> where k indexes step-loads and t₀_k is that step-load's own onset. With a ramp (item 2), define
> onset as the job's `STARTING` event — the engine reads that signal directly and should not have to
> infer onset from the draw shape.
>
> This preserves the §12 identity exactly: at steady state `Σ α_k × ΔP_k = α_max × P_compute`,
> verified to 1e-6. **The Step 1b §12 regression test must still pass after this change** — that is
> the check that superposition was done right.
>
> **4. BESS fleet coordination, anchor constraint, and the reserve aggregation — one change.**
> `DispatchArbitrator.tick()` currently has every BESS unit see the same aggregate shortfall.
> Implement a fleet-coordinated split proportional to each unit's available power and state of
> charge.
>
> In the same change, implement v2.5 §7.1.2:
>
> ```
> BESS_bridging_available(t) = min(rated capacity, usable SoC) − P_anchor_reserve
> ```
>
> `P_anchor_reserve` is zero when a unit is grid-following and non-zero when it is the island's
> grid-forming anchor. The anchor role is **dynamic** — read it from operating mode each tick, not
> from static config. Default it to a conservative non-zero fraction of rated capacity, **never to
> zero**, because zero silently reproduces the unadjusted arithmetic this constraint exists to
> correct. The §7.2 step-4 reserve check and the insufficient-reserve alert both use the
> anchor-adjusted figure.
>
> And fix the reserve aggregation: `dispatch.py:172` computes
> `total_sustainable_s = min(b.max_sustainable_seconds(peak/n) for b in units)` — named "total" but
> operating `min`, so with heterogeneous units the check is bounded by the weakest unit rather than
> the fleet. **Sum each unit's sustainable duration at that unit's allocated share, computed from
> the fleet split above** — which is why this belongs in the same change rather than beside it.
>
> Add tests proving each fix against a scenario that would have been silently wrong before: multiple
> concurrent jobs on one module; two step-loads 400 s apart, asserting the second produces its own
> cooling rise and that the first job's cooling never drops; a shortfall exceeding any single BESS
> unit's rated power but not the fleet's combined capacity; and TC-61, TC-62, TC-63.

**Acceptance criteria:**
- Each fix has a test demonstrating the **old** behaviour was wrong, not merely that new tests pass.
- TC-61, TC-62, TC-63 pass. The §12 identity test from Step 1b still passes.
- The second-step-load cooling test shows job A's P_cooling never dips when job B starts.
- Every changed assertion in `test_formulas.py` is reported with its reason.
- `load_test.py --matrix` 1x still passes — this touches the hot path.

---

## Step 4 · Phase 10 — Control-plane purity gate *(new)*

**Governs:** v2.5 §21.1, §22.6; Design Spec §2 principle 2, §4.3.

**Goal:** Make the plane boundary mechanically enforced **before there is anything to enforce it
against.** Retrofitting this after agents exist means retrofitting it around violations.

**Prompt:**
> The design spec already requires `core/` to be synchronous with zero `asyncio`, with all
> concurrency confined to `runtime/`. v2.5 §21.1 requires the same boundary for a stronger reason:
> no model inference, and no network or wall-clock dependency, may sit inside the real-time control
> path. Make that mechanically enforced.
>
> Add `tests/test_plane_separation.py` with two layers:
>
> **Static.** Walk the import graph of every module under `core/`. Assert zero imports of:
> `asyncio`, `httpx`, `aiohttp`, `requests`, `urllib`, `asyncpg`, `psycopg`, `sqlalchemy`, `boto3`,
> `mistralai`, `anthropic`, and anything under `advisory/` or `runtime/`. Assert zero references to
> `time.time`, `time.monotonic`, `datetime.now`, `datetime.utcnow` — `core/` reads an injected
> clock only (Step 5 provides it).
>
> **Runtime.** Add a `contextvars` sentinel set while `evaluate_tick()` executes, and a thin shim
> around the forbidden modules raising `ControlPlaneViolation` if entered while the sentinel is
> set. This catches dynamic dispatch and late imports that static analysis cannot.
>
> Wire the static layer into CI as build-breaking. Then **demonstrate both layers failing**: add
> `import httpx` to `core/dispatch.py` and show the static check fail; add a late import inside
> `evaluate_tick()` and show the runtime check fail. Revert both and show them passing again.

**Acceptance criteria:**
- Both layers pass against the current skeleton.
- **The agent has shown both guards actually failing, then reverted.** A guard nobody has seen fail
  is a guard nobody knows works. Do not accept "the test passes" as evidence here.

---

## Step 5 · Phase 11 — Simulated clock and the two clock domains *(new)*

**Governs:** v2.5 §22.8 (ST-4), §17.1, §6.2, §23.3; Agentic Design §3.1.

**Goal:** Resolve which clock every interval is measured against, before anything measures one.
v2.5 §22.8 flags this as open and states the likely answer; this step decides it.

**Prompt:**
> Every interval in v2.5 is expressed in real time — the 15-minute dedupe window, the 45-second and
> 30-second checkpoint classification intervals, the 120-second curtailment dwell, the 10-second
> BESS taper hold, the 90-day retention boundary. A simulator running faster than real time must
> decide which clock these are measured against. §22.8 (ST-4) records this as unresolved. Resolve
> it as follows.
>
> Implement a `SimClock` in `core/`: monotonic simulated seconds since scenario t0, a wall-clock
> stamp, a rate multiplier, and a persisted `tick_seq` that is the restart anchor. Persist it to
> the Step 2 store every tick. Inject it into `evaluate_tick()` — `core/` must not read a wall
> clock, and Step 4's gate enforces that.
>
> Apply these two rules and state them in the module docstring, because they are easy to get
> backwards:
>
> - **All specification intervals are measured in simulated time.** A 15-minute dedupe window at
>   60× expires after 15 simulated minutes, not 15 wall seconds.
> - **A restart resumes the simulated clock rather than jumping forward.** Otherwise a grace period
>   would appear to have expired during the restart.
>
> Record wall-clock alongside simulated time on every persisted record, since forecast-error
> attribution against real latency needs both.
>
> Add tests: at `rate=60`, a 15-minute dedupe window expires after 15 simulated minutes; a job in
> the §6.2 `uncertain` state with 20 s elapsed against the 30 s grace period, restarted, resumes
> with elapsed time preserved and expires 10 s later — not 30 (v2.5 TC-35).

**Acceptance criteria:**
- TC-34 and TC-35 pass **at `rate=60` as well as `rate=1`.** Both pass trivially at 1×; running
  them accelerated is the check that catches a clock-domain error.
- No wall-clock reference anywhere in `core/` — Step 4's static gate confirms this.

---

## Step 6 · Phase 2 — FastAPI application wiring

**Governs:** Simulator Design Spec §7 (API Design); Simulator Functional Spec §10.1, §10.2.

**Goal:** Stand up the real REST + WebSocket surface against the existing `RunManager` and the
Step 2 persistence layer — no UI yet.

**Prompt:**
> Implement the FastAPI application described in the attached design spec §7's endpoint table:
> `POST /runs` (starts a run via the existing `RunManager.start_run`), `WS /runs/{run_id}/live`
> (subscribes to `WebSocketHub`, using a thin adapter from FastAPI's `WebSocket` to the existing
> `WebSocketLike` Protocol in `runtime/run_manager.py`), `GET /runs/{run_id}/results` (reads
> `RunTimeseries` from the Phase 1 sink), and REST CRUD for `/sites`, `/asset-configs`,
> `/scenarios` per functional spec §7.2–§7.3's screens. One `RunManager` and one `WebSocketHub`
> instance, held as FastAPI app state, shared across requests — do not create a new one per
> request. Add integration tests in `tests/test_api.py` using FastAPI's `TestClient`/
> `AsyncClient`: starting a run via REST and receiving ticks over the WebSocket in order, and a
> concurrent-users test that starts 5 runs via 5 simultaneous REST calls and confirms all 5
> progress independently (this should reuse the isolation-proving pattern from
> `tests/test_concurrency.py`, against the real HTTP/WebSocket surface this time, not the bare
> `RunManager`). Do not implement the frontend yet.

**Acceptance criteria:**
- `uvicorn` (or Replit's run command) serves the API; `POST /runs` returns a `run_id`.
- WebSocket delivers ticks in order for a subscribed run.
- The 5-concurrent-runs-via-HTTP test passes — this is the first real proof the ≥5-concurrent-
  users NFR (functional spec §11) holds through the actual API, not just the internal
  `RunManager`.
- No per-request `RunManager`/`WebSocketHub` instantiation (check the app-state wiring
  specifically — this is an easy way to silently break run isolation).

The "one `RunManager` and one `WebSocketHub` instance, held as FastAPI app state" criterion now
does double duty — it is also what stops agents instantiating their own runs in Step 12.

---

## Step 7 · Phase 3 — Frontend scaffold + Live Dashboard

**Governs:** Simulator Functional Spec §7.1, §11; **v2.5 §19.2** (Page 1 — Site Overview);
Design Spec §3, §4.4.

**Goal:** As original, plus the v2.5 landing-page panels and correct behaviour under acceleration.

**Prompt:**
> Scaffold a React (Vite) frontend under `frontend/` and implement the Live Dashboard screen per
> functional spec §7.1: current GPU/turbine/BESS/solar output, a live-updating power-forecast
> chart (P_compute, P_cooling, P_total against time), and an alert banner for
> `insufficient_reserve_alert`. Connect to the Phase 2 WebSocket endpoint. Use a lightweight
> charting library (Chart.js or Recharts, per design spec §3's stack table). Before writing
> component code, show me a short written description of the planned layout and component
> breakdown so I can confirm it matches functional spec §7.1 before you build it. After building,
> start a run via the Phase 2 API and confirm the dashboard updates within the 1-second latency
> target (functional spec §11) — describe how you verified this, not just that you believe it.

**Additionally**, three items from Forecast Engine Functional Spec v2.5:
>
> 1. **Panels per v2.5 §19.2.** The hero countdown to GPU full-TDP (Δt_lead); the forecast panel
>    plotting `P_compute`, `P_cooling`, `P_total` **and `P_renewable`** with the confidence band;
>    an asset reserve panel showing BESS **bridging capability in seconds**, not just state of
>    charge — §19.4's point is that the organizing question is how much time the battery buys, not
>    how full it is; and the insufficient-reserve alert dock with an acknowledge control.
> 2. **Extend the existing `WebSocketHub`** (`runtime/run_manager.py`) rather than writing a new
>    broadcaster. It already fans out with `asyncio.gather` and per-socket exception isolation per
>    design spec §4.4, which is the behaviour we want — a slow or dead client must never
>    back-pressure the run loop.
> 3. **Behaviour under acceleration.** The console renders at `min(4 Hz, tick_rate)`. Where the
>    simulated tick rate exceeds the frame rate — at `rate=60` a 5-second tick completes every
>    83 ms of wall time, three ticks per frame — frames carry a decimation factor and affected
>    panels show a "showing 1 of N ticks" indicator. **Disable interpolation entirely when
>    decimating**: interpolating between dropped ticks fabricates a curve the simulation did not
>    produce.
>
> Render data-quality tags (`unmapped_hardware`, `invalid_payload`, `uncalibrated_site`,
> `stale_profile`) as inline flags wherever affected values appear, not as hidden metadata (§19.11).
>
> Before writing component code, show me a short written description of the planned layout and
> component breakdown so I can confirm it against §7.1 and §19.2 before you build.

**Acceptance criteria:**
- Layout matches functional spec §7.1's described panels — check this yourself against the spec
  text, don't just accept "looks reasonable."
- Dashboard visibly updates live while a run is in progress, not just on page load.
- No Section 7.2/7.3/7.4 functionality bleeding in yet — keep this phase scoped to §7.1 only.
- Dashboard remains correct and visibly labelled at `rate=60`.
- The bridging-capability readout is in **seconds**, and matches the arithmetic that fires the
  insufficient-reserve alert.
- No new broadcaster — `WebSocketHub` extended, not replaced.

---

## Step 8 · Phase 4 — Scenario Builder + Asset Configuration

**Governs:** Simulator Functional Spec §7.2, §7.3, §6.2; v2.5 §7.1.1.

**Prompt:**
> Implement the Scenario Builder (functional spec §7.2) and Asset Configuration (§7.3) screens
> against the Phase 2 REST endpoints for `/scenarios` and `/asset-configs`. The Scenario Builder
> must let a user script a sequence of `WorkloadSignal` events (job launch, turbine failure,
> cloudy period — per §7.2) and define pass/fail assertions. The stressor list should match
> functional spec §6.2's stressor table exactly — list what stressors you implemented against
> that table and flag any you couldn't map cleanly. The Asset Configuration screen exposes the
> per-site parameters listed in functional spec §7.3 (battery size, turbine ramp rate, cooling
> lag, etc.) without requiring a code change. Persist scenarios/configs through the Phase 1
> persistence layer, not in frontend state only.

**Additionally**, three items:
>
> 1. **Every assertion needs a machine-evaluable `check:` expression**, not just a prose `expect:`.
>    An assertion that cannot be evaluated is documentation, not a test.
> 2. **Add v2.5-era stressors** to the §6.2 stressor list: renewable step loss (inverter trip,
>    feeder loss — `Δt_lead = 0`, no advance warning, per §7.1.1); grid loss and island transition;
>    clock skew injection; malformed and out-of-order WorkloadSignal events; unmapped hardware
>    profile. Report which map cleanly onto §6.2's existing table and which are new rows.
> 3. **Asset Configuration exposes** `P_anchor_reserve`, `counting_unit`, and profile vintage
>    alongside the existing per-site parameters.
>
> Add these preset scenarios, each mapping to named v2.5 acceptance cases: *Peak Demand* (four
> concurrent training starts exceeding turbine ramp — TC-10, TC-41); *Renewable Collapse* (inverter
> trip under flat compute — TC-33); *Blackout Mode* (grid loss, island transition, BESS becomes
> anchor mid-forecast — TC-62, TC-67); *Checkpoint Ambiguity* (drop with no recovery and no
> `job_end` inside 45 s — TC-08, TC-35); *Bad Integration* (malformed payloads, out-of-order events,
> clock skew, unmapped SKUs — TC-15, TC-18, TC-20, TC-23).

**Acceptance criteria:**
- Every stressor in functional spec §6.2's table has a UI affordance, or there's an explicit,
  reported gap.
- A scenario built in the UI, saved, reloaded, and run produces the same result as one built via
  `core/scenario_factory.py` with equivalent parameters — this is a good sanity check that the
  UI-to-domain-model translation is faithful, not lossy.
- Every preset runs and its assertions evaluate to a verdict.
- **TC-33 specifically**: a +6 MW compute step and a −6 MW renewable step produce the same ΔP in
  `P_dispatch_required(t)` and the same staging response, with Run B evaluated at `Δt_lead = 0`.
  `P_dispatch_required` is implemented in **Step 3 item 0**, not here — this step exercises it
  through a scenario rather than introducing it.

---

## Step 9 · Phase 5 — Results/playback screen + pass/fail verdicts

**Governs:** Simulator Functional Spec §7.4; the `TODO` in `runtime/run_manager.py`'s `_drive()`.

**Scoping note.** The **Scenario Planner** (v2.5 §18.5, FR-4.4 — "more BESS or a second turbine?")
is a *different product* from the Scenario Builder and is **not** built here. It moves to Step 15.

**Prompt:**
> Two things. First, implement scenario assertion evaluation: replace the `TODO` in
> `runtime/run_manager.py`'s `_drive()` (`verdict = None`) with real evaluation of a scenario's
> pass/fail assertions (functional spec §7.2) against the completed `RunTimeseries`, and persist
> the verdict via `sink.finalize()`. Second, implement the Results screen (functional spec §7.4):
> scrubbable tick-by-tick playback of a completed run, with the verdict and which specific
> assertions passed/failed shown clearly. Add tests in `tests/test_verdicts.py` covering at least
> one scenario that should pass and one that should deliberately fail, using the TC-10-style
> insufficient-reserve worked example from the source spec (source spec §7.3) as the failing
> case.

**Acceptance criteria:**
- `verdict` is no longer hardcoded `None` anywhere in the run lifecycle.
- The failing-case test actually fails the assertion it's supposed to (i.e., you've checked it
  isn't vacuously passing).
- Playback is scrubbable (can jump to an arbitrary tick), not just a linear replay.

---

## Step 10 · Phase 13 — Deterministic arbitration + pre-staging *(new)*

**Governs:** v2.5 §26.4, §8.1, §23.2, §23.3; Design Spec §5.

**Goal:** Extend `core/dispatch.py` with the selection ordering agents will later publish into.
**This is control-plane work, stays in `core/`, and contains no model call.**

**Prompt:**
> Two additions to `core/dispatch.py`. Both are pure, synchronous, and deterministic — Step 4's
> gate applies.
>
> **1. The §26.4 selection ordering.** Given a shortfall and a set of candidate responses, select
> deterministically in this fixed order: storage discharge → turbine ramp → firm grid import →
> reserved grid purchase → curtailment ladder A/B → curtailment ladder C/D. The ordering is by
> reliability sufficiency first, then reversibility, then cost. **Cost ranks last deliberately**: a
> system that optimizes cost ahead of reversibility will eventually choose an irreversible cheap
> option over a reversible expensive one, at the exact moment its forecast is wrong.
>
> Two requirements that are easy to get wrong:
>
> - **Sort by a total order before selecting** — ladder position, then estimated impact descending,
>   then a unique identifier. Do **not** build a dict keyed by response kind: two agents may later
>   publish the same kind, a dict silently drops one, and selection then depends on input ordering.
>   v2.5 TC-49 requires selection be reproducible from the recommendation set *alone*.
> - **Same-kind candidates are ranked and share that kind's headroom**, not dropped.
>
> **2. Two-phase arbitration (§8.1).** Pre-staging reduces the size of the gap rather than closing
> an existing one, so it sits *ahead of* the ladder, not inside it:
>
> ```
> Phase 0 — GAP REDUCTION (shiftable load): pre-cool within band; charge thermal storage
>           -> recompute ΔP against the reduced requirement
> Phase 1 — GAP CLOSURE (§26.4 ladder, above)
> ```
>
> Pre-staging is bounded by a configured inlet-temperature band, is never autonomous, and the
> simulated BMS retains unconditional override (§8.1, TC-56).
>
> Also implement the §23.2 curtailment ladder itself — A defer / B power-cap / C suspend /
> D preempt — with **mandatory ordering** (never invoke a tier while headroom remains at a lower
> one, TC-41), the §23.3 hysteresis (120 s dwell, 20% restoration margin), and the §23.6 interlocks:
> site floor never curtailed; **degraded forecasts never curtail autonomously** (a segment tagged
> `low_confidence` — TC-43); dead-man expiry; and curtailment bounded by the predicted gap, not by
> present state.
>
> Preserve `evaluate_tick()`'s fixed evaluation order (Design Spec §5) — this **inserts a stage at a
> defined point, it does not reorder existing stages.** Say explicitly where you inserted it.

**Acceptance criteria:**
- **TC-49 asserted over all permutations** of a candidate set, not one ordering. A test that runs
  the selector once proves nothing.
- TC-41, TC-42, TC-43, TC-44, TC-46, TC-55, TC-56 pass.
- `load_test.py --matrix` 1x still passes.
- The agent has stated where in `evaluate_tick()` the pre-staging phase was inserted.

---

## Step 11 · Phase 6 — Simulated SCADA layer + §28 execution layer

**Governs:** Simulator Functional Spec §4.6, §4.6.1, §4.6.2; **v2.5 §28**; Design Spec §2
principle 3, §4.3, §5.

**Goal:** As original — protocol-tagged command latency and message loss — **plus** v2.5 §28's
physical execution layer, which describes the same boundary from the other side. This is the
natural home for §28: §28.3's integration surface is exactly §4.6.1's protocol table.

**Prompt:**
> Implement `core/scada_layer.py` per simulator functional spec §4.6 exactly as originally
> specified: a `SimulatedScadaLayer` where each asset's control channel is protocol-tagged (Modbus,
> DNP3, IEC 61850 GOOSE/MMS per §4.6.1) with configurable command latency, message-loss
> probability, and max-message-size tolerance, defaults per protocol per §4.6.2. It sits between
> `DispatchArbitrator`'s output and the asset modules' `advance()` calls. Wire it into
> `evaluate_tick()` keeping the fixed evaluation order intact. **Use a seeded RNG, not real
> randomness**, or the determinism NFR breaks (functional spec §11; design spec §2 principle 3).
>
> Before writing it, answer: does adding this layer change `evaluate_tick()`'s timing
> characteristics enough to matter for design spec §4.3's "no threading needed" analysis? If a
> command's simulated latency means an asset's state now depends on a queue of pending commands
> rather than a single synchronous call, **say so explicitly** rather than quietly changing the
> architecture — that's a real design decision, not an implementation detail.
>
> Then add the physical execution layer per Forecast Engine Functional Spec v2.5 §28:
>
> - A simulated **power management system** holding its own shed priority order, independent of
>   GridSignal's curtailment priority. Where the two disagree, report it as a commissioning defect —
>   **the PMS order is authoritative and GridSignal does not override it** (§28.4, TC-65).
> - **Protective fast load shed** as an injectable event. When it fires, GridSignal observes a
>   discontinuous load drop and must enter reconciliation and re-plan against measured state — it
>   must **not** compose a curtailment command in response (TC-64). Record the event for
>   forecast-error attribution as a predictive-staging failure (TC-66).
> - **Transition modes**, open-transition by default: loss of utility supply is a coverage
>   discontinuity to be ridden through, not a smooth capacity reduction (TC-67).
> - A **command egress boundary** every outbound command passes through and a test can capture.
>   Model it as an abstract command bus over the §4.6.1 protocol channels — TC-68 needs a boundary
>   to capture, not additional wire fidelity beyond what §4.6 already gives you.
>
> Write whitebox tests mirroring `tests/test_formulas.py` for: a command delayed past its target
> tick; a dropped command; a degraded-link fault per §4.6.1's DNP3 row; and v2.5 TC-64 … TC-68.

**Acceptance criteria:**
- As original: deterministic under fixed seed, verified with a byte-identical-output test; each
  protocol has visibly distinct latency/loss characteristics; the timing-impact question is
  answered specifically, not skipped.
- **TC-68**: a full scenario run with every integration active issues **zero** islanding,
  synchro-check, anti-islanding, droop, or protective-shed commands at the egress boundary.
  GridSignal advises and stages; it does not command protection.
- TC-64, TC-65, TC-66, TC-67 pass.

> **This is the first demo-able checkpoint.** After this step the deterministic simulator is
> complete against v2.5 with no agents at all — enough to show lead time, two-clock staging, the
> renewable equivalence, and anchor-adjusted bridging.

---

## Step 12 · Phase 12 — Advisory scaffolding *(new)*

**Governs:** v2.5 §21.3, §21.4, §21.6, §26.3; Agentic Design §4.3–4.7; Remediation Pack CS1-1.

**Goal:** Build the machinery every agent depends on, before any agent exists. **The order within
this phase matters**: the de-identifier is built first so no model client can predate the egress
filter.

**Prompt:**
> Create an `advisory/` package alongside `runtime/`. **Nothing in `core/` may import from it** —
> Step 4's gate enforces this. Build in this order:
>
> **1. `advisory/deident.py` — the mandatory egress transform (§21.4).** Per-session opaque handles
> for `site_id` and `job_id`. Hardware profiles referenced by anonymized class index with rated
> wattage retained (`"profile_A at 10.2 kW/unit"`), **never by SKU name**. Never let raw
> WorkloadSignal payloads, job names, customer identity, the calibrated parameter set, or the
> contents of the hardware profile library leave the process.
>
> **It is also the aggregation layer.** Raw series are downsampled to at most 60 bins carrying
> min/mean/max plus summary statistics and flagged anomalies — not raw samples. Target roughly
> 1,500 input tokens per evidence window. An agent does not need 240 raw samples to find a
> correlation; it needs shape, extremes, and anomalies. Raw series reach a model only on an explicit
> bounded drill-down request.
>
> **2. `advisory/router.py` — Mistral and Claude behind one interface.** Role assignment per §21.3:
> Mistral for high-volume correlation over structured numeric series; Claude for analysis and
> operator-facing reporting, where output structuring is the product. **No other vendor.**
>
> Fallback ladder: timeout (20 s) → one retry with **jittered backoff** → alternate vendor where
> the role permits → deterministic heuristic. Malformed JSON: one reprompt naming the schema
> violation, then heuristic. Out-of-bounds value: auto-reject at generation, **no retry** — an
> out-of-bounds derivation indicates a measurement or ingestion problem, not a model problem.
>
> Token budget: **soft 2.2 M input tokens per site per day**, alert at 70%; **hard ceiling 15 M**,
> then all agents to heuristic mode with a console banner. Enforced at the router, not at the agent,
> so an agent cannot exceed its budget by being written badly.
>
> **Refuse any payload lacking a de-identifier provenance stamp.**
>
> **3. `advisory/gate.py` — the §21.6 four-state lifecycle.** proposed → under_review →
> applied/rejected. **Automatic bounds rejection at generation time**: α_max outside 0.10–0.30,
> Δt_thermal outside 60–120 s, PUE_base outside 1.02–1.05, r_asset ≤ 0 — rejected before reaching a
> reviewer, logged as a learning-plane data-quality event (TC-30). Expiry enforced by the gate, not
> the agent. Reviewer identity required to leave `under_review`. Rejected proposals suppressed from
> re-proposal for 30 days unless supporting evidence materially changes.
>
> **The gate is tier-invariant**: a site in Autonomous tier still queues every parameter change for
> human approval, because changing a parameter changes all future dispatch decisions.
>
> **4. `advisory/principal.py`** — three roles: `viewer` (read only), `operator` (acknowledge
> alerts; ladder A/B at Supervised; turbine staging; pre-cool within band), `approver` (everything
> an operator may, plus §21.6 promotion, ladder C/D confirmation, reservation authorization).
>
> Add tests capturing all outbound HTTP at the boundary and asserting no `site_id`, `job_id`,
> customer identifier, or hardware SKU name appears in any request body.

**Acceptance criteria:**
- TC-29, TC-30 pass; the egress capture test passes.
- **With both `MISTRAL_API_KEY` and `ANTHROPIC_API_KEY` absent, the whole application still runs as
  a deterministic simulator with no agents and no errors.** This is the fastest smoke test in the
  project and exercises LP-1 through configuration rather than failure.
- `advisory/` appears in no import under `core/`.

---

## Step 13 · Phase 14 — The six buildable agents *(new)*

**Governs:** v2.5 §26.2, §26.5; Agentic Design §1.3, §4.2, §4.8.

**Goal:** Compute & Workload, Storage, Generation, Renewable Supply, Thermal, Calibration.
Procurement and Network Telemetry wait for Step 14.

**Prompt:**
> Implement an agent base class in `advisory/agents/base.py` executing a five-phase loop:
>
> 1. **Observe** — query the evidence window from the Step 2 store.
> 2. **Qualify** — significance floor. **An agent that cannot state the evidence for a
>    recommendation shall not emit it** (§26.5).
> 3. **Transform** — de-identify and aggregate via Step 12's module.
> 4. **Reason** — router call, strict JSON schema, validated on receipt.
> 5. **Propose** — through the gate.
>
> Provenance (`originating_agent`, `prompt_digest`, `evidence_digest`, `generated_by`) is stamped by
> the base class, not each agent, so it cannot be forgotten.
>
> **Cadence is wall-clock**, event-triggered with a floor (rate limit) and ceiling (liveness floor)
> per agent — **not fixed polling**, which spends identically on a quiet site and a site in
> shortfall. **Evidence windows are simulated time.** These are different clocks answering different
> questions: cadence governs a real API quota and a real bill, and neither accelerates.
>
> | Agent | Floor | Ceiling |
> |---|---|---|
> | Compute & Workload | 30 s | 10 min |
> | Storage | 60 s | 15 min |
> | Renewable Supply | 60 s | 15 min |
> | Generation | 5 min | 30 min |
> | Thermal | 5 min | 30 min |
> | Calibration | 60 min | 24 h |
>
> Authority ceilings per §26.2 — **no agent dispatches**. Compute proposes curtailment (ladder A/B
> executable at Autonomous, **C/D never autonomous at any tier**). Storage proposes charge
> scheduling and re-rating. Generation is **advisory only** — a turbine start is supervisory control
> under NFR-3/NFR-4. Renewable Supply is **advisory only by construction**; solar and wind are
> passive collectors and no control surface exists (§7.1.1). Thermal is advisory for anything the
> BMS owns. Calibration proposes parameter changes through the §21.6 gate.
>
> Each agent gets a deterministic heuristic fallback — a threshold on a trailing mean, no more. It
> exists to keep the recommendation surface populated and honest, not to replicate model output.
> Heuristic output carries `generated_by: "fallback"` and renders with a distinct badge, because a
> reviewer weighing evidence needs to know whether it was assembled by a model or a threshold.
>
> Put the rendered system prompts for Compute and Calibration in the repo **as files, not inline
> strings** — `prompt_digest` implies a canonical rendering exists.
>
> Build the §19.10 Proposals & Learning page: every recommendation with originating agent, asserted
> change, current and proposed values, evidence and observation window, estimated impact,
> reversibility, expiry. Approve and reject record reviewer identity and timestamp. Sort by impact.
> Add the **Agents: ON/OFF** header toggle.

**Acceptance criteria:**
- **TC-48 is the gate for this phase.** With every agent stopped, the dispatch trace over a full
  scenario run is **bit-identical** to a run with agents present but recommendations un-actioned.
  Compare hashes, not eyeballs.
- TC-28: all model endpoints unreachable for 30 simulated minutes under load → no forecast delayed
  past the 5-second tick, only proposal generation stops.
- TC-31, TC-32, TC-57 pass.
- Flipping **Agents: OFF** mid-run changes nothing about dispatch and leaves the console fully
  functional as a monitoring surface.

> **Second demo-able checkpoint.** The kill-switch demonstration takes about fifteen seconds and is
> the fastest available answer to "what happens when your model vendor has an incident?"

---

## Step 14 · Phase 15 — Network telemetry + procurement *(new)*

**Governs:** v2.5 §24, §25, §11.4.

**Prompt:**
> **NetworkTelemetry (§25).** Implement the §25.2 contract as a **second ingest class** sharing the
> validation, quarantine, and idempotency machinery of §17.1–17.2 — a second ingestion path with
> different rules would be a second set of bugs. Fields: `switch_id`, `site_id`, `interface_id`,
> `throughput_rx/tx` (sampled rates, not counter deltas), `error_counters`, `optical_power_tx/rx`,
> `sample_interval_ms`.
>
> It is **dispatch-path ineligible by contract**: an adapter routing NetworkTelemetry into the
> forecast path is rejected as **non-conforming, not misconfigured** (TC-74). Add §25.3 capability
> tiers (baseline / enhanced) — a baseline platform degrades roles, not ingestion (TC-71). Add the
> §11.4 clock-class model: PTP vs NTP, with **demotion when observed skew contradicts a declared
> discipline** (TC-70), and cross-source correlation reported at the **looser** clock bound (TC-69).
>
> Add the corroboration record: for each predicted job start, whether a corresponding traffic rise
> was observed within the expected window. A scheduler `checkpoint_start` event is authoritative and
> fabric evidence **cannot override it** (TC-51). Fabric corroboration alone does not count toward
> the §17.3 reconciliation threshold — throughput is not a magnitude proxy (TC-73).
>
> Build the §19.9 Network Telemetry console page. **Read-only, no controls** — by design, not
> omission.
>
> **Procurement (§24).** Firm / reserved / non-firm capacity with `T_reserve` lead time and a
> **seeded synthetic price curve** — no live external feeds; a demo depending on a third-party API's
> availability will eventually fail in front of an audience for a reason unrelated to the product.
> Non-firm spot import reduces served load but does **not** close the reserve gap (TC-47).
> `ReservationProposal` is **never autonomous at any tier** (§24.3, TC-52). Build the §19.8 Grid &
> Procurement page — the authorization control is the only place in the console where an action
> commits money, and it is styled and confirmed differently for that reason.

**Acceptance criteria:**
- TC-47, TC-50, TC-51, TC-52, TC-69 … TC-74 pass.
- Fabric traffic rising sharply with no preceding WorkloadSignal produces **no forecast change and
  no staging action** — only a missed-job corroboration finding (TC-50).

---

## Step 15 · Phase 16 — Maintenance, ramp relaxation, Scenario Planner *(new)*

**Governs:** v2.5 §27, §23.7, §18.5; parent FR-4.3/4.4.

**Prompt:**
> Three items.
>
> **1. Prescriptive maintenance (§27).** Asset degradation and health tracking; availability state;
> the §27.3 prescriptive ladder; **forecast-aware window validation across the full duration** — a
> proposed window beginning in a demand trough and ending during a forecast step-load is rejected,
> because validation covers the whole duration, not the start instant (TC-59). Scheduling is
> **proposal-only at every tier**: taking an asset out of service dispatches a technician, not a
> setpoint. **Ratings move down more easily than up** — a proposal raising a rating asserts an asset
> can do more than believed, which if wrong is discovered during a shortfall, so it requires a
> longer observation window and explicit confirmation (§27.5, TC-60). Build the §19.6 Thermal &
> Cooling page, whose primary readout is **thermal headroom** — how much additional compute load the
> cooling plant can absorb before approach-to-limit, and how long it takes to get there.
>
> **2. Adaptive ramp relaxation (§23.7.2).** A static scheduler ramp policy — bring accelerators up
> under a power cap and release it over 60–90 seconds — prevents an unmanageable step-load with no
> forecasting at all, and §23.7 is explicit that this should be recommended as the baseline. What
> prediction adds is making it *adaptive*: relax the ramp when the reserve position confirms
> headroom. **Relaxation requires a reserve check passing against the confidence band's lower
> bound**, not merely the absence of a warning (TC-75). On loss of GridSignal the relaxation lapses
> and the site baseline policy resumes — the failure direction is toward conservative
> pre-installation behaviour, **never toward an unramped start** (TC-76).
>
> **3. Scenario Planner (§18.5, FR-4.4).** Distinct from the Scenario Builder built in Steps 8–9.
> This answers "what if we added more BESS instead of a second turbine" over **persisted run
> history**, not assumptions. It needs the §21.2 workstream-3 cost model: marginal cost per MWh for
> grid import, on-site generation, and storage round-trip, with **turbine cost modelled as amortized
> capital against duty cycle rather than fuel alone** — generation capacity is typically
> debt-financed, so the economically relevant question is how often the asset runs against what it
> costs to own, not the marginal cost of the hour it runs. Build it as the §19.1 Page 9 surface.

**Acceptance criteria:**
- TC-58, TC-59, TC-60, TC-75, TC-76 pass.
- The Scenario Planner produces a cost comparison over an asset-mix change from actual run history.
- Thermal headroom is expressed in **both** MW absorbable and time-to-limit.

---

## Step 16 · Phase 8 — Replit deployment

**Prompt:**
> Configure this Repl per functional spec §10.2–§10.3: a single run command that builds the React
> frontend and then starts the FastAPI server serving the built frontend as static files on one
> port (§10.2's "single Repl process, single port" model). Confirm no external database or cloud
> service is referenced anywhere in the config. Enable Always-On per §10.2's rationale (avoiding
> cold-start delay before investor demos, not because correctness requires it). Publish a Replit
> Deployment separate from the development Repl per §10.3, and report both URLs.

**Acceptance criteria:**
- One `.replit`/build command; "Run" produces a working demo with no manual build step.
- Dev and deployed instances are separate, per §10.3's explicit guidance.

The **"no external database or cloud service"** criterion above is correct per v2.5 §22.7 and
stands unchanged — see §0.1.

Two additions:
- Use a **Reserved VM** rather than Always-On alone; a non-Reserved Repl sleeps on inactivity, which
  kills long scenario runs mid-demonstration.
- `MISTRAL_API_KEY` and `ANTHROPIC_API_KEY` go in Replit Secrets. Confirm the deployment still runs
  correctly with **both absent** — that is the Step 12 acceptance criterion re-verified against the
  real deployment.

---

## Step 17 · Phase 9 — Full acceptance matrix + CI

**Governs:** **v2.5 §16 (Addendum A — all 76 test cases)**; Simulator Functional Spec §12.1; Design
Spec §12.5; `scripts/load_test.py`.

**Goal:** Close the traceability loop against v2.5, not the v1.6-era 27.

**Prompt:**
> Go through Forecast Engine Functional Specification **v2.5** Addendum A (§16, **TC-01 through
> TC-76**) and the simulator functional spec's §12.1 SIM-TC references one by one. For each, confirm
> a corresponding test exists in this repo and passes, or write it. Report as a table: TC ID,
> description, test file and name, pass/fail. Add SIM-01 … SIM-15 from the Agentic Prototype Design
> §7.2.
>
> Then wire `scripts/load_test.py` into CI per its docstring — on every merge to files under
> `core/`, `runtime/`, or `advisory/`, not on every commit.
>
> Add a **determinism gate**: every preset scenario runs twice, once agents-enabled and once
> agents-disabled, and the dispatch trace hash must match. Wire it into CI alongside the load test.

**Acceptance criteria:**
- The reported table has no "missing, not written" rows left unaddressed without explicit discussion
  of why.
- `scripts/load_test.py --matrix` still shows 1x passing after everything in Steps 1–16 — this is
  the point of keeping it rather than discarding it after the concurrency work.
- The agents-enabled vs agents-disabled determinism gate passes on every preset.

---

## Notes on using this sequence

- **Don't skip Step 1.** It is now doing two jobs: transfer verification and a v2.5 gap audit. If
  the audit reports that `P_dispatch_required` doesn't exist or that BESS bridging is unadjusted,
  several later steps change scope — better to know before Step 2 than during Step 10.
- **Design spec §4 (concurrency model) and §2 (design principles) are worth re-attaching or
  re-quoting at every step**, even ones that look UI-only. It is easy for an agent building the
  frontend or the API layer to reach into `core/` and add `asyncio` or shared mutable state where
  the design deliberately avoided it. Step 4's purity gate now catches this mechanically, but the
  gate is easier to satisfy than to repair after the fact.
- **Steps 7–9 (UI) are the ones most likely to silently drift from the mockups.** The functional
  spec's Figure 2 and v2.5 §19.2's panel-by-panel correspondence are worth comparing screenshots
  against directly, not just trusting a written description.
- **The single hardest thing to get right in this whole sequence is TC-48** — dispatch behaviour
  bit-identical with agents on and off. Everything about the plane separation exists to make that
  true, and it is the one result that is impossible to fake in a demo. If it fails after Step 13,
  the fault is architectural and worth stopping for, not patching around.
- **Every constant introduced across these steps** — confidence widening factors, degradation rates,
  cadence floors, the Δt_lead ramp shape, the wind power curve — is a **chosen** value, not a
  derived one, and must be labelled as such in code and on the console. v2.5's discipline throughout
  is that placeholder numbers are labelled as placeholders.
- If Replit's agent proposes deviating from a spec section in any step (a different library, a
  simplified data model, skipping a stressor), that's fine to accept — but make it say so
  explicitly rather than silently substituting, so you're deciding rather than discovering later.

---

## Chosen constants register

Every value below is **chosen, not derived**. v2.5's discipline throughout is that placeholder
numbers are labelled as placeholders, and a build that quietly accumulates unlabelled constants
trades one defect class for a worse one. Each must carry the label in code and, where it reaches
an operator, on the console.

| ID | Constant | Value | Introduced | Basis |
|---|---|---|---|---|
| **PROTO-1** | Δt_lead internal ramp shape | piecewise | Step 3 | §6.1 gives the interval, not the curve |
| **PROTO-2** | Wind power curve | Weibull | Step 15 | Unvalidated against any site |
| **PROTO-3** | `MAX_EXPLICIT_HOLD_S` | 900 s | **Step 1b (done)** | Plausible upper bound on a large checkpoint write. Unmeasured |
| **PROTO-4** | Confidence widening factors | base 0.05; unmapped +0.10; uncalibrated +0.08; invalid_payload +0.15; stale_profile TBD | pre-existing, extended Step 2 | Additive composition. No measured basis |
| **PROTO-5** | Agent cadence floors and ceilings | 30 s – 24 h | Step 13 | Derived from cost, not from observed agent value |
| **PROTO-6** | Token budget | soft 2.2 M / hard 15 M per site-day | Step 12 | Derived from PROTO-5 and a 1 544-token evidence window |

**Naming.** Use the `PROTO-` prefix for simulator-chosen constants. Do **not** use `CL-`, `LP-`,
`AG-`, `ST-`, or `PX-` — those are v2.5's own residual-item namespaces (`CL-1` is Tier B power-cap
yield, `CL-3` is economic curtailment), and reusing them creates a collision that only surfaces
when someone cross-references the parent spec. `MAX_EXPLICIT_HOLD_S` was initially tagged `CL-2`
during Step 1b; retag it **PROTO-3**.

---

## Proposed amendments to v2.5

Raised by implementation, not in force until v2.5 adopts them.

| ID | Amendment |
|---|---|
| **PA-1** | Regenerate Figure 1 with the learning plane (§21.8 already asks for it) |
| **PA-2** | Add wind as a second non-dispatchable source under §7.1.1 treatment |
| **PA-3** | Specify, or explicitly decline to specify, the Δt_lead internal curve |
| **PA-4** | Adopt simulated time as the measurement basis for all specification intervals (closes ST-4) |
| **PA-5** | `P_cooling(t) = Σₖ αₖ(t) × ΔP_compute_k(t − Δt_thermal)` — cooling must superpose per step-load, as §11.1 already requires of compute. A single α with a single t₀ is only correct for one step-load per run |
| **PA-6** | §6.2's job-end bullet and ambiguous-case bullet **describe the same input state and prescribe different outcomes**. Both say "did not return to ≥90% within 45 s"; one says classify `job_end`, the other says hold as `uncertain`. TC-07 and TC-08 differ only in drop depth, which affects nothing in the classification path. The Step 1b implementation reads them as *classification* (45 s → `uncertain`) versus *staging behaviour* (+30 s grace → `job_end`), which is coherent. §6.2 should say so |

---

## Still open after all 17 steps

Carried deliberately, per v2.5's own residual-items discipline: **AG-2** (agent placement — all
in-process here, which sidesteps rather than answers it), **AG-3** (arbitration cannot distinguish
"agent offline" from "agent has no option"; a capability-declaration heartbeat is the likely answer
and is not designed), **AG-4** (review capacity — mitigations exist, sustainable volume unmeasured),
**LP-2** (who should hold `approver` — Step 12 gives the question a shape, not an answer), **LP-3**
(budget now has a mechanism and a derived figure, pending design-partner entity counts), **LP-5**
(significance floor), **ST-2** (Tier 0 redundancy — belongs with the §18.7 edge-appliance decision),
**PX-2** (genset anchor droop), **CL-1** (Tier B power-cap yield), **A-8** (partitioned-table
primary keys — deferred to the PostgreSQL promotion path, not applicable to SQLite).

**And the document chain.** After the build, reconcile the Simulator Functional Spec and Simulator
Design Spec to v2.5 *from what was actually built*. Until then they track v1.6 and are not
authoritative — worth a note on their cover pages so nobody discovers that the hard way.

---

*End of build plan v2.*
