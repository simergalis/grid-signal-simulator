# GridSignal
## Remediation Pack — Agentic AI Prototype Design v0.1 → v0.2

**Resolutions for the 8 blocking, 10 phase-gating, 5 deliverable, and 4 defect findings in Review v0.2**

| Field | Value |
|---|---|
| Date | July 29, 2026 |
| Applies to | GridSignal Agentic AI Prototype — Implementation Design, Draft v0.1 |
| Source | Design Review v0.2 |
| Structure | Four change sets, sequenced. CS-1 and CS-2 are corrections with verified artifacts; CS-3 is new specification; CS-4 is deliverable completion |

---

## 0. How the issues divide

The 27 findings are not one problem. They fall into three classes with very different costs, and conflating them is what makes a remediation list look intimidating when it mostly is not.

| Class | Findings | Nature | Cost |
|---|---|---|---|
| **Corrections** | A-3, A-6, A-7, A-8, B-7, B-8, B-9, B-10, B-11, C-5, D-4 | The design already decided; the artifact is wrong. Arithmetic, schema, code | Hours. Verifiable |
| **Small additions** | A-4, A-5, B-2, B-3 | The design decided nothing; a small, bounded decision is needed | 1 session each |
| **New specification** | A-1, A-2, B-1, B-4, B-5, B-6 | Whole v2.5 sections with no design counterpart | 1 session each, 6 sessions total |
| **Deliverables** | C-1, C-2, C-3, C-4 | Promised, not produced | Mechanical |

**Only six findings require genuine design work.** Everything else is correction or completion. The sequence below is ordered so the cheapest, highest-leverage items land first — in particular A-6, which produces a number worth having before any design-partner conversation.

---

## Change Set 1 — Corrections (verified)

Every item here has been implemented and tested. Artifacts are ready to thread into the design document.

### CS1-1 · A-6 · Derive the token budget instead of choosing it

**The defect.** §4.4 fixes cadences summing to 7 873 calls/day. §4.5 fixes 400 000 input tokens/day. That is 50.8 tokens per call. The two numbers were written independently.

**The wrong fix** is raising the budget to 8–40 M tokens/day. That accepts the cost driver instead of removing it, and it makes LP-3 a commercial problem rather than solving it.

**The right fix has two parts**, because there are two independent multipliers:

**(a) Aggregate the evidence window before it leaves the site.** §4.7's de-identification layer already sits on every egress path. Make it a *compression* layer as well as an identity-stripping layer — which is also more faithful to §21.4, since less leaves the site.

| | Raw (v0.1 as written) | Aggregated (fix) |
|---|---|---|
| Storage agent, 4 h window | 240 samples × 6 fields | 60 bins × (min, mean, max) + summary stats |
| Payload | ~22 000 chars | ~3 800 chars |
| Tokens per call incl. system prompt | **≈ 6 630** | **≈ 1 540** |
| | | **4.3× reduction** |

Agents do not need 240 raw samples to find a correlation; they need shape, extremes, and flagged anomalies. Raw series should reach a model only when an agent explicitly requests a drill-down on a bounded window.

**(b) Replace fixed polling with event-triggered cadence, bounded by a floor and a ceiling.** A fixed 30-second poll spends the same tokens on a quiet site as on a site in a developing shortfall. Each agent gets:

- **floor** — the minimum gap between calls (a rate limit, protects cost)
- **ceiling** — the maximum gap (a liveness floor, protects freshness)
- **triggers** — material state changes that fire a call between floor and ceiling

| Agent | Floor | Ceiling | Typical calls/day | Worst case/day |
|---|---|---|---|---|
| Compute & Workload | 30 s | 10 min | 344 | 2 880 |
| Storage | 60 s | 15 min | 136 | 1 440 |
| Renewable Supply | 60 s | 15 min | 126 | 1 440 |
| Network Telemetry | 60 s | 15 min | 126 | 1 440 |
| Generation | 5 min | 30 min | 63 | 288 |
| Thermal | 5 min | 30 min | 63 | 288 |
| Procurement | 15 min | 60 min | 32 | 96 |
| Calibration | 60 min | 24 h | 2 | 24 |
| **Total** | | | **892** | **7 896** |

**Resulting budget, derived rather than asserted:**

| | Calls/day | × 1 544 tok | Budget |
|---|---|---|---|
| Typical | 892 | 1.38 M | **Soft budget 2.2 M input tok/site/day**, alert at 70% |
| Worst case | 7 896 | 12.2 M | **Hard ceiling 15 M input tok/site/day**, then fallback |

Indicative cost at soft budget: roughly **$0.44–1.32/site/day** for the Mistral-routed agents, plus a few dollars for the two Claude-routed agents. That is a commercially sane number, and it is the real answer to **LP-3** — which should be updated in v2.5 from "undefined" to "defined with a mechanism and a measured basis pending design-partner entity counts."

**Also fixes:** SIM-06 becomes non-trivial. Under v0.1's budget it passed continuously while testing nothing.

### CS1-2 · A-7 · Split the cadence clock from the evidence clock

**The defect.** §3.1 puts all specification intervals on simulated time and never says which clock agent cadence uses. If cadence follows simulated time, a 60× accelerated demo issues 472 380 calls per wall-day.

**The fix is one paragraph in §4.4**, and the distinction is real rather than a workaround:

> **Agent cadence is measured in wall-clock time. Agent evidence windows are measured in simulated time.**
>
> These are different clocks because they answer different questions. Cadence governs how often a real API is called against a real quota and a real bill, which are wall-clock quantities and do not accelerate. An evidence window governs what span of modelled history the agent reasons over, which is a simulated quantity and must accelerate with the simulation or the agent would see a shrinking fraction of the run.
>
> A consequence worth stating: at high acceleration an agent sees *more* simulated history per call, not more calls. This is the correct behaviour — the agent's job does not get more urgent because the simulation got faster.

**Test to add.** Extend SIM-02: at `GS_SIM_RATE = 60`, assert agent call count over a wall-minute is unchanged from `rate = 1`, and assert every evidence window boundary is expressed in `sim_ts_s`.

### CS1-3 · A-8 + A-3 + C-5 · Corrected Tier 1 schema

These close together because the A-3 dedupe decision determines the A-8 composite key.

**A-3 resolution: adopt the specified tuple.** v2.5 §17.1 and the §29 glossary both define the dedupe key as `(site_id, job_id, event_type, event_id)`. The design's `event_id`-only primary key was a silent divergence. Adopting the tuple is the correct call — not because it is stricter, but because it makes the *schema* the enforcement mechanism for the *specified* rule, so TC-22 passes for the right reason.

**A-8 resolution:** PostgreSQL requires a partitioned table's primary key to include every partition-key column. Corrected keys, all validated:

| Table | Partition key | Primary key | Status |
|---|---|---|---|
| `workload_signal` | `source_ts` | `(site_id, job_id, event_type, event_id, source_ts)` | **valid** |
| `forecast` | `issued_at` | `(id, issued_at)` | **valid** |
| `control_event` | `issued_at` | `(id, issued_at)` | **valid** |
| `network_telemetry` | `observed_at` | `(id, observed_at)` | **valid** |

**C-5 resolutions, all in the same DDL:**

- `control_event` loses `acknowledged_at`; acknowledgments move to an append-only `control_event_ack` table. The table is now genuinely immutable, matching its own comment and NFR-5.
- `quarantine.raw_payload` becomes `TEXT` with an optional `parsed_payload JSONB` sidecar, plus a third `failure_kind` value `unparseable`. A `JSONB` column could not store the exact class of input §17.2 requires be logged in full.
- `recommendation` moves to one clock basis: `suppressed_until_sim_s` replaces the `TIMESTAMPTZ`, with `created_at_wall` retained separately and explicitly named.

The corrected DDL additionally carries forward **A-4** (`counting_unit`), **A-5** (`principal` table and a `CHECK` that no recommendation reaches `applied` or `rejected` without a `reviewer_id`), **B-7** (`band_lower_mw` / `band_upper_mw` as stored columns, since TC-17 sizes off the lower bound), **B-8** (`corrected_by_event`, `cleared_at`), **A-2** (`network_telemetry` with capability tier, sample interval, and clock class), **B-4** (`reservation`), and **B-5** (`asset_health`).

Full DDL: `schema_fix.sql`, 10 statements, parsed clean.

### CS1-4 · B-9 · Deterministic arbitration selection

**The defect, demonstrated.** `{r.kind: r for r in recs}` silently overwrites same-kind recommendations and depends on input ordering that no query defines. Across all 24 permutations of a 4-recommendation set, v0.1's selector produced **two distinct outcomes**. TC-49 requires selection be reproducible from the recommendation set alone.

**The fix.** Sort by a total order before selecting, and *rank* same-kind collisions rather than dropping one:

```python
def _total_order(r):
    """Ladder position, then impact descending, then id. No ties possible,
    because recommendation_id is unique. Reproducible from the set alone."""
    return (_RANK.get(r.kind, len(SELECTION_ORDER)),
            -r.estimated_impact_mw, r.recommendation_id)

def select_fixed(shortfall_mw, recs, capability):
    remaining, selected, used_by_kind = shortfall_mw, [], {}
    for rec in sorted(recs, key=_total_order):          # <-- the fix
        if remaining <= CLOSURE_EPSILON_MW: break
        if rec.kind not in _RANK: continue
        head = capability.headroom_for(rec.kind) - used_by_kind.get(rec.kind, 0.0)
        if head <= 0: continue
        c = min(head, remaining)
        selected.append(replace(rec, contribution_mw=c))
        used_by_kind[rec.kind] = used_by_kind.get(rec.kind, 0.0) + c
        remaining -= c
    return selected
```

**Verified:** 24/24 permutations → one outcome. 200 random shuffles → one outcome.

**Why ranking rather than dropping matters.** Two agents proposing the same response class is not an error — Storage and Thermal can both legitimately propose discharge. Dropping one loses evidence a reviewer may need and makes the queue misrepresent what the agents actually concluded. Ranking preserves both and shares the headroom deterministically.

**Also required:** add `ORDER BY recommendation_id` to the Tier 1 read, so the input set is stable before it is sorted. Belt and braces, and it makes the invariant visible at the query.

### CS1-5 · B-10 · Broadcaster, backoff, and naming

**The defect, demonstrated.** `except asyncio.QueueFull: q.put_nowait(RESYNC_SENTINEL)` raises `QueueFull` again on the queue that just raised it. In test, the broadcaster died on frame 0 — **starving all three clients because one was suspended.** That is the exact inversion of the intended behaviour, on the code path whose comment says it protects the tick loop.

**The fix.** Resync becomes a flag on the client, not a message in the full queue:

```python
async def broadcast_fixed(clients, frame):
    for c in clients:
        if c.needs_resync:
            continue                     # nothing sent until the client re-requests
        try:
            c.q.put_nowait(frame)
        except asyncio.QueueFull:
            c.needs_resync = True        # mark, drain, never raise
            c.dropped += 1
            while not c.q.empty():
                c.q.get_nowait()
```

**Verified:** 5/5 frames broadcast, no exception, healthy clients `[0, 2]` still served, slow client marked and drained.

Also in this change set: add the jittered backoff to `ModelRouter.reason()` that the §4.6 fallback table specifies and the code omits; and rename `usable_energy_mwh` to `available_energy_mwh` in `bridging_available_mw`, since ambiguity between nameplate and currently-available energy is expensive in exactly that function.

### CS1-6 · D-4 · Restate SIM-11 as something implementable

**The defect.** §1.2 and §7.2 describe SIM-11 as "static analysis over the control-plane call graph", build-breaking. Sound call-graph analysis of Python is not decidable under dynamic dispatch, and SIM-11 is the mechanism the entire plane separation rests on. An enforcement mechanism described more confidently than it can be implemented is worse than a weaker one described accurately.

**The fix — two layers, both implementable:**

1. **Static: import-and-attribute reachability.** Walk the module import graph from every `@control_plane`-decorated coroutine's defining module; assert no path reaches `httpx`, `aiohttp`, `asyncpg`, `boto3`, the model router package, `time.time`, or `datetime.now`. Runs in CI and as a pre-commit hook. Catches the overwhelming majority of real violations because they arrive as an import.
2. **Runtime: a context guard.** Control-plane tasks run inside a `contextvar` sentinel; the forbidden modules are wrapped with a shim that raises `ControlPlaneViolation` if entered while the sentinel is set. Catches what static analysis cannot — dynamic dispatch, `getattr`, late imports.

Layer 1 is build-breaking; layer 2 is test-breaking and would be a hard failure in a scenario run. Together they are stronger than the claim v0.1 made and, unlike it, can actually be written.

### CS1-7 · B-11 · Console sampling above acceleration

**The fix.** Couple frame rate to tick rate above a threshold, and label decimation rather than hiding it:

> The console renders at `min(4 Hz, tick_rate)`. Where the simulated tick rate exceeds the frame rate, frames carry a `decimation` factor and the affected panels render a "showing 1 of N ticks" indicator. Interpolation is disabled entirely when decimating, because interpolating *between* dropped ticks fabricates a curve the simulation did not produce.

### CS1-8 · Small corrections

| Finding | Fix |
|---|---|
| **B-7** | Confidence widening: specify multiplicative composition with per-tag factors — `unmapped_hardware` ×1.6, `invalid_payload` ×2.0, `uncalibrated_site` ×1.4, `stale_profile` ×1.3, applied to the half-band. Tag these as **chosen, not derived**, following the PROTO-1 precedent. TC-16 passes under any rule; TC-17 is magnitude-sensitive, so the numbers must exist and must be labelled as provisional |
| **B-8** | `invalid_payload` recovery: a corrected event is a new `event_id` for the same `job_id` that passes both validation layers. On receipt, `quarantine.corrected_by_event` and `cleared_at` are set and the tag stops applying to *newly issued* segments. Segments already issued are never retroactively re-tagged, consistent with §11.3's rule that history is corrected for accuracy reporting but dispatch commands already issued are not altered |
| **C-5** | Give every scenario assertion a machine-evaluable `check:` expression. The §2.4 TC-33 assertion currently has only `expect:` prose |
| **§5.4** | Redeploy is a **cold start**, not a restart — §22.3 requires the two never share an implementation branch. Either persist Tier 0 across redeploys via a mounted volume, or restate the demo claim: restart behaviour is demonstrated by in-process restart only |
| **§11.2** | Add job-cancellation-mid-ramp to the design body; it currently exists only as a checklist line |

---

## Change Set 2 — Small additions

Four bounded decisions, one session each.

### CS2-1 · A-4 · Counting unit and profile vintage

Two columns and two rules, closing the largest silent-error class in the specification.

```python
class HardwareProfile(BaseModel):
    profile_id: str
    rated_kw: float
    counting_unit: Literal["chassis","cabinet","package","die","accelerator"]  # §5.2
    vintage_generation: str          # e.g. "GB200", "VR200"
    vintage_established: date        # when the rated draw was recorded
```

- **Mismatch is a domain validation failure and is quarantined** (TC-53). Never silently converted — an automatic conversion encodes an assumption about which side is correct, and the whole point is that this is the assumption nobody should be making. The NVL144-vs-72-packages case is exactly a 2× forecast error.
- **Staleness:** vintage older than 18 months renders `stale` on the console and widens the band (TC-54). A generation-gap prompt fires where the site's densest profile is more than one generation behind the library's newest entry.

### CS2-2 · A-5 · Minimal authorization

Three roles, one table, one `CHECK` constraint — enough to make the gate a door without pre-empting **LP-2**:

| Role | May |
|---|---|
| `viewer` | Read every page. No control surface |
| `operator` | Acknowledge alerts; ladder A/B at Supervised; turbine staging; pre-cool within band |
| `approver` | Everything an operator may, plus §21.6 promotion, ladder C/D confirmation, reservation authorization |

The §1.4 authority matrix keys to role rather than to nothing. The schema `CHECK` makes a recommendation reaching `applied` or `rejected` without a `reviewer_id` structurally impossible, so the §7.3 gate-bypass test finally tests authorization rather than `NOT NULL`.

**This does not answer LP-2** — who *should* hold `approver`, and whether it differs by operating tier, remains v2.5's open question. It makes the question answerable by giving it a shape.

### CS2-3 · B-2 · Pre-staging ahead of the arbitration ladder

§8.1 establishes a third load class — shiftable, alongside firm and curtailable — and states that pre-staging sits *ahead of* the §26.4 ladder "because it reduces the size of the gap rather than closing a gap that already exists." The v0.1 `SELECTION_ORDER` has no pre-stage phase, so it would size a gap that pre-cooling should already have shrunk.

**The fix restructures arbitration into two phases:**

```
Phase 0 — GAP REDUCTION (shiftable load, §8.1)
    pre-cool within band; charge thermal storage
    -> recompute ΔP against the reduced requirement
Phase 1 — GAP CLOSURE (§26.4 ladder, unchanged)
    storage -> turbine -> firm import -> reserved purchase -> ladder A/B -> ladder C/D
```

Phase 0 is bounded, never autonomous, and the BMS retains unconditional override. It emits no ladder action and cannot close a gap on its own — which is precisely why it must not sit inside a ladder whose ordering is by reliability sufficiency.

### CS2-4 · B-3 · Separate Scenario Planner from Scenario Builder

They serve different personas and only one exists in v0.1.

| | Scenario **Builder** (v0.1 §2.4) | Scenario **Planner** (v2.5 §18.5, FR-4.4) |
|---|---|---|
| Purpose | Inject stressors, assert pass/fail | Answer "more BESS or a second turbine?" |
| Persona | Engineering, QA | VP Infrastructure |
| Input | Stressor schedule + seed | Persisted operational history |
| Output | Test verdict | Cost comparison over an asset-mix change |
| Needs | Already specified | **Cost model — absent** |

The missing piece is the §21.2 workstream-3 cost model: marginal cost per MWh for grid import, on-site generation, and storage round-trip, with **turbine cost modelled as amortized capital against duty cycle rather than fuel alone** — because generation capacity is typically debt-financed, so the economically relevant question is how often the asset runs against what it costs to own.

Note this is downstream of **v2.5 defect D-3**: §19.1 lists a Page 9 that has no §19.x subsection, which is very likely why v0.1 substituted the test harness. Resolve D-3 first.

---

## Change Set 3 — New specification

Six sessions. These are the only findings that require design work rather than correction.

| # | Item | Scope | Decisions needed | Unlocks |
|---|---|---|---|---|
| **CS3-1** | **A-2 · NetworkTelemetry** | §25.2 contract (schema already drafted in CS1-3), §25.3 capability tiers, §11.4 clock classes with false-precision demotion, corroboration record | Which fabric platform to model; how demotion is detected from observed skew | TC-50, TC-51, TC-69 … TC-74 (**8 tests**) |
| **CS3-2** | **A-1 · PMS and execution layer** | §28 — simulated power management system, shed priority order, protective fast-load-shed, transition modes, §28.3 command egress surface | Whether to model the protocol surface (Modbus/DNP3/IEC 61850) or an abstract command bus. **Recommend abstract** — TC-68 needs an egress boundary to capture, not wire fidelity | TC-64 … TC-68 (**5 tests**) |
| **CS3-3** | **B-1 · Adaptive ramp relaxation** | §23.7.2 — relaxation gated on a reserve check passing against the band *lower bound*; §23.7.1 static-baseline comparison | None substantive; §23.7 already specifies the behaviour | TC-75, TC-76 (**2 tests**) |
| **CS3-4** | **B-5 · Prescriptive maintenance** | §27 — degradation model, availability state, §27.3 ladder, window validation across full duration, §27.5 evidence asymmetry | Degradation rates (simulator parameters, tag as unmeasured) | TC-59, TC-60 (**2 tests**) |
| **CS3-5** | **B-4 · Procurement model** | §24 — `T_reserve` lead time, price curve, demand-charge exposure (schema drafted in CS1-3) | Price-curve process: synthetic and seeded, per §6.4's no-live-feeds rule | TC-47, TC-52 strengthened |
| **CS3-6** | **B-6 · Inference micro-ramp** | §6 row 2 — ±500 kW over ~10 s from `queue_depth`/`request_rate` | v2.5 §15 leaves the mapping function open. **Recommend a placeholder tagged as unmeasured**, following PROTO-1, rather than inventing a function | Inference workload class |

**CS3-3 is the one to do first of these six**, despite unlocking the fewest tests. §23.7 contains the specification's own strongest self-criticism — that a static scheduler ramp policy is the honest baseline competitor and should be recommended even though it costs GridSignal nothing to say so. A prototype that omits it omits the argument an engineering-literate investor will arrive with.

---

## Change Set 4 — Deliverables

| Finding | Item |
|---|---|
| **C-1** | React components: console shell, WS delta reducer, one component per authority affordance (Propose / Acknowledge / Confirm-consequence) |
| **C-2** | SQLAlchemy models against the corrected DDL; buffered off-loop writer |
| **C-3** | Agent base class implementing the five-phase loop; two rendered system prompts, since `prompt_digest` implies a canonical rendering exists |
| **C-4** | NFR-2 load-test design: load profile, harness, methodology — distinct from SIM-13, which is a UI load test |
| — | Deployment runbook; OpenAPI output; formal WS protocol schema |

---

## Sequence

Ordered by leverage, not by finding number.

| Session | Contents | Why here |
|---|---|---|
| **1** | CS1-1 (budget), CS1-2 (cadence clock), CS1-3 (schema) | Highest leverage. Produces the real LP-3 number and makes the schema executable. Everything downstream persists into this schema |
| **2** | CS1-4, CS1-5, CS1-6, CS1-7, CS1-8 | All remaining corrections. Artifacts already written and tested |
| **3** | CS2-1 (counting unit/vintage), CS2-2 (authorization) | Unblocks the Phase 1 gate |
| **4** | CS2-3 (pre-staging), CS2-4 (Planner split) | Requires v2.5 D-3 resolved first |
| **5–10** | CS3-1 … CS3-6, one per session | The genuine design work |
| **11+** | CS4 | Mechanical once the specification is stable |

**Sessions 1–4 restore the design to a state where Phases 0–1 are buildable.** Sessions 5–10 restore the "all 76 tests" claim to truth — 17 of the 19 unexecutable tests unlock in CS3-1 through CS3-4 alone.

---

## Parallel: v2.5 amendments

These are cheap and should not wait for the design work, since several findings above depend on them.

| ID | Amendment |
|---|---|
| **D-1** | §26.2 lists seven agents; §19.10, AG-1, AG-4 say six. Correct the prose; AG-1's "six times larger" becomes seven, or eight if PA-2 is adopted |
| **D-2** | §19.7 does not exist. Renumber §19.8 → §19.7 and cascade, **and** correct the two citations in §26.3 and AG-4 that point at §19.8 (Grid & Procurement) when they mean §19.10 (Proposals & Learning) |
| **D-3** | §19.1 lists nine pages; Page 9 has no subsection. Add §19.x for Scenario Planner — CS2-4 depends on it |
| **LP-3** | Update from "no per-site call budget defined" to the derived figures in CS1-1, marked provisional pending design-partner entity counts |
| **PA-1 … PA-4** | The four amendments already proposed in design §9.3 |

---

## What this does not fix

Recorded so the remediation is not mistaken for completeness. These remain open after every change set above, correctly:

**AG-2** (agent placement — the prototype runs in-process and sidesteps it), **AG-3** (arbitration under partial information — CS1-4 makes selection deterministic but still cannot distinguish "Procurement offline" from "Procurement has no option"; a capability-declaration heartbeat is the likely answer and is not designed here), **AG-4** (review capacity — mitigations exist, sustainable volume unmeasured), **LP-2** (approval authority — CS2-2 gives it a shape, not an answer), **LP-5** (significance floor), **ST-2** (Tier 0 redundancy — correctly deferred to the §18.7 edge-appliance decision), **PX-2**, **CL-1**, **PROTO-1**, **PROTO-2**.

Every confidence-widening factor, degradation rate, and curve shape introduced in these change sets is a chosen value, not a derived one, and must carry that label into the design document. The specification's discipline throughout is that placeholder numbers are labelled as placeholders, and a remediation that quietly introduces twelve new unlabelled constants would have traded one defect class for a worse one.

---

*End of remediation pack.*
