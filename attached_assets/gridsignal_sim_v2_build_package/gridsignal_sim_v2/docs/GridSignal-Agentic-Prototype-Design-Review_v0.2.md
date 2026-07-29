# GridSignal
## Design Review — Agentic AI Prototype Implementation Design v0.1

**Reviewed against:** GridSignal Forecast Engine Functional Specification v2.5

| Field | Value |
|---|---|
| Document under review | GridSignal Agentic AI Prototype — Implementation Design Document, Draft v0.1 |
| Review date | July 29, 2026 |
| Review status | **v0.2 — supersedes v0.1.** Two independent passes; Pass 2 findings in Section 8A |
| Reviewer | Forecast Engine workstream |
| Verdict | **Not ready for implementation as written.** 8 blocking items, 10 phase-gating items, 4 deliverable gaps |
| Headline finding (Pass 1) | **19 of 76 inherited acceptance tests (25%) are claimed as executable against components the design never specifies** |
| Headline finding (Pass 2) | **The §4.5 token budget permits 51 input tokens per agent call against its own §4.4 cadence table — short by a factor of 20–100. The prototype would run in fallback mode within roughly 40 minutes of every session** |

---

## 0. Verdict Summary

The design is architecturally sound and internally consistent on the axis that matters most — plane separation, authority gating, and determinism are correctly specified, correctly enforced, and correctly tested. Sections 1, 2, 4, 9, and 10 of the design are implementable as written.

The failure is one of **coverage, not correctness**. The design covers v2.5 Sections 4–12, 17, 21, 22, and 26 thoroughly, and covers Sections 23 (partially), 24, 25, 27, and 28 barely or not at all. Because the design's acceptance matrix asserts "all 76 cases (TC-01 … TC-76) are implemented", and its phase gates list those tests as passing criteria, the omission is not a soft one: **Phase 2 and Phase 5 gates as written cannot be reached**, because they require tests against simulated components that no section of the design specifies.

Three defects were also found **in v2.5 itself** during this review (Section 9 below). One of them — a misreference propagated into the design document — is substantive rather than cosmetic.

### Severity distribution

| Class | Count | Meaning |
|---|---|---|
| **A — Blocking** | 8 | A decision or specification is missing that implementation cannot proceed without. A-1…A-5 from Pass 1, A-6…A-8 from Pass 2 |
| **B — Phase-gating** | 10 | Must be closed before the phase that consumes it. B-1…B-8 from Pass 1, B-9…B-11 from Pass 2 |
| **C — Deliverable** | 5 | Promised in the design's own deliverables list but not produced, or produced non-executably |
| **D — Defect** | 4 | Three in the parent specification (Sec 9), one over-claimed enforcement mechanism (D-4) |
| **E — Accepted** | 11 | Correctly carried as open items with rationale; no action required |

**Pass 1 vs Pass 2.** Pass 1 read the design against v2.5 and found *coverage* failures — whole sections of the parent specification with no corresponding design. Pass 2 read the design against itself and found *internal consistency* failures — numbers that contradict other numbers in the same document, code that does not do what its own prose says, and DDL that does not execute. The two passes found disjoint sets. Neither alone would have been sufficient, which is worth noting for how the next revision is reviewed.

---

## 1. Coverage of Requirements

### 1.1 What is fully covered

| v2.5 Section | Coverage | Evidence |
|---|---|---|
| §3 System model, §3.1 cadence | **Complete** | Design §1.2, §3.1. Simulated-clock resolution additionally closes ST-4 |
| §4 Workload-to-MW formula | **Complete** | Design §3.2, §4.1. Both terms, correct decomposition, no double-count |
| §5.1 Unmapped hardware fallback | **Complete** | Design §3.2, §6.6. Tagging, widening, onboarding alert, and the vector-search rejection all present |
| §6.1–6.2 Job start, checkpoint valley | **Complete** | Design §3.2. Both signal paths; TC-09 inclusive-boundary case explicitly constructible |
| §7.1.1 Non-dispatchable supply | **Complete and well-handled** | Design §3.5. The `ramp_capability_mw_s` guard — renewables structurally absent, "no branch to forget" — is the correct implementation posture |
| §7.1.2 Anchor constraint | **Complete** | Design §3.3. Anchor-adjusted bridging, dynamic role, conservative non-zero default |
| §7.2–7.3 Dispatch arbitration | **Complete** | Design §1.6, §4.1 |
| §8 Thermal lag | **Complete** | Design §3.6, incl. §8.2 liquid parameter set correctly declined as default |
| §10 WorkloadSignal contract | **Complete** | Design §6.2 schema, all fields incl. conditional `queue_depth` |
| §11.3 Out-of-order events | **Complete** | Reordering buffer, retroactive-to-history-only rule |
| §12 Confidence | **Partial** — see B-7 | Mechanism specified, magnitudes not |
| §17.1–17.3 Idempotency, malformed input, cold start | **Partial** — see A-3 | Dedupe key diverges from the specified tuple |
| §21 Learning plane | **Complete** | Design §1.1, §4. LP-1 correctly treated as an executable assertion rather than an aspiration |
| §22 Persistence | **Complete** | Design §6. Tier mapping, restart behaviour, batching economics, rejected patterns |
| §26 Agentic control | **Complete** | Design §1.3–1.6. Ranking is deterministic; agents cannot dispatch |

### 1.2 Gaps and omissions

**A-1 — v2.5 §28 Physical Execution Layer and PMS integration is entirely unmodelled.** *(Blocking)*

The design's Phase 2 gate lists TC-64 … TC-68 as passing criteria. None is executable:

- TC-64 (no double-shed after a protective event) requires a simulated protective fast-load-shed layer. None exists.
- TC-65 (priority divergence surfaced at commissioning) requires a power management system with its own shed priority order. None exists.
- TC-66 (shed events feed error attribution) depends on TC-64's component.
- TC-67 (open-transition discontinuity) is asserted in design §3.7 as a one-line behaviour with no transition-mode model behind it.
- TC-68 (GridSignal issues no protection-layer commands) requires an egress boundary over a command surface — Modbus/DNP3/IEC 61850/REST per §28.3 — that the design never defines. TC-68 currently has nothing to capture.

§28 is not a peripheral section. It defines where GridSignal sits relative to the equipment that actually actuates, what a dispatch command actually commands, and the interlock that keeps the system from fighting a protective relay. A prototype that omits it demonstrates a forecast engine, not a control system.

**A-2 — v2.5 §25 NetworkTelemetry is absent from the schema and the simulator.** *(Blocking)*

Agent #7 (Network Telemetry) is in the inventory with an authority ceiling. Behind it there is nothing:

- No `network_telemetry` table in the design's §6.2 DDL.
- No §25.2 contract implementation (`switch_id`, `interface_id`, `throughput_rx/tx`, `error_counters`, `optical_power_tx/rx`, `sample_interval_ms`).
- No §25.3 platform capability tier model (baseline vs enhanced), which TC-71 requires.
- No emission-mode reporting, which TC-72 requires.
- No clock-class model (§11.4 PTP vs NTP), which TC-69 and TC-70 require.

Six acceptance tests (TC-69 … TC-74) plus TC-50 and TC-51 depend on this. Note that TC-74 — *"an adapter routing NetworkTelemetry into the forecast path is non-conforming, not misconfigured"* — is one of the sharper architectural assertions in v2.5, and the prototype currently cannot demonstrate it because there is no second ingest class to mis-route.

**A-3 — Dedupe key diverges from the specified contract.** *(Blocking)*

v2.5 §17.1 and the §29 glossary both specify the dedupe key as the tuple `(site_id, job_id, event_type, event_id)`. The design's §6.2 DDL makes `event_id` the sole `PRIMARY KEY`.

This is arguably stricter — a globally unique `event_id` subsumes the tuple. But it is a silent contract change, and it has a testing consequence: **TC-22 (same `event_id` redelivered with a mutated timestamp) would pass for the wrong reason**, because uniqueness is being enforced by a database constraint rather than by the specified dedupe logic. Either reconcile the schema to the tuple, or record an explicit deviation with the argument for subsumption. Do not leave it implicit.

**A-4 — Hardware profile library omits counting-unit declaration (§5.2) and vintage/staleness (§5.3).** *(Blocking)*

The design's §3.2 profile table has neither field. TC-53 and TC-54 are claimed and unexecutable.

This omission is quantitatively serious rather than tidy-up work, and v2.5 makes the case explicitly:

- **Counting units:** the Vera Rubin rack is marketed as NVL144 (144 dies) and is physically 72 dual-die packages. A site reporting one against a profile assuming the other produces a forecast off **by exactly 2×**, with no symptom other than persistent forecast error. §5.2 requires this to be a domain validation failure and quarantined, specifically not silently converted.
- **Vintage:** forecasting a Rubin cabinet against a GB200-era profile under-predicts by **60–90 kW per cabinet**, so ten racks exceed the 0.5 MW threshold at which §4.4 emits a prediction signal at all. The site is systematically under-staged with no invalid input anywhere to flag.

Both are cheap to add — two columns, one validation rule, one staleness check — and both are the kind of silent-error class the prototype exists to demonstrate the system catching.

**A-5 — No authentication or authorization design exists.** *(Blocking)*

The design's §6.3 API table has an "Auth class" column. Nothing implements it. There is no identity model, no role definition, no session handling, and no mapping from operating tier or recommendation class to an authorized principal. `reviewer_id` is an unvalidated string in the schema.

The consequence is that the §7.3 "gate bypass attempt" stress test is not testing authorization — it is testing a `NOT NULL` constraint. On a design whose entire safety argument rests on a human gate, the gate currently has no door.

v2.5's LP-2 (approval authority, unresolved) is a legitimate reason not to specify the *production* authority model. It is not a reason to ship a prototype with no principal at all. A minimal role stub — `viewer` / `operator` / `approver`, with the §1.4 authority matrix keyed to it — is sufficient for the prototype and forces the LP-2 question into a shape someone can answer.

### 1.3 Simulated resources — coverage assessment

| Resource | Detail level | Assessment |
|---|---|---|
| **GPU / compute** | Profiles, TDP, Δt_lead curve, checkpoints, synchronization, power-cap floor | **Adequate for training.** Inference micro-ramp entirely absent — see B-6. Counting unit and vintage missing — see A-4 |
| **Battery** | Power/energy kept distinct, SoC window, C-rate, round-trip efficiency, degradation, anchor duty | **Strong.** The `bridging_available_mw` implementation is correct and is the subtlest thing in the design |
| **Turbines** | Ramp rate, start latency, minimum stable load, start reliability, re-rating | **Adequate for dispatch.** No degradation or availability-state model — see B-5 |
| **Solar** | Irradiance curve, cloud transient, soiling, per-string availability | **Adequate** |
| **Wind** | Power curve over autocorrelated Weibull series | **Adequate**, correctly flagged as unvalidated (PROTO-2) |
| **Cooling** | α(t), Δt_thermal, τ, air and liquid parameter sets, thermal storage, BMS override | **Strong.** Shiftable-load ordering wrong — see B-2 |
| **Grid tie** | Firm / reserved / non-firm distinction, open transition | **Thin.** No reservation model, no T_reserve, no price curve — see B-4 |
| **Power management system** | — | **Absent** — see A-1 |
| **Network fabric** | — | **Absent** — see A-2 |

---

## 2. Agent Autonomy and Logic

### 2.1 Autonomy levels — assessed as correct

The design's §1.4 rejects the requested "fully autonomous / semi-autonomous / rule-based" taxonomy and replaces it with an authority matrix. **This is the right call and the justification is sound:** no agent is autonomous at any level, because autonomy is a property of the operating tier applied to the deterministic control plane. Every ceiling in the design's §1.3 traces correctly to §26.2, §23.4, or §24.3.

Two properties are correctly identified and worth preserving in any revision:

- The most consequential actions become *less* automatable as tier rises (ladder C/D and procurement have a hard human gate at every tier).
- The parameter gate is tier-invariant, because a parameter change has a larger blast radius than any single dispatch action.

**No finding.** This section is complete.

### 2.2 Agent logic — one substantive gap

Decision-making workflows (§4.2), the Recommendation contract (§4.3), the evidence floor, bounds rejection, and expiry are all specified to implementation precision.

Conflict resolution (§1.6) is correct but **incomplete in one respect — B-2 below**: v2.5 §8.1 establishes a third load class (shiftable, alongside firm and curtailable) and states that pre-staging happens **ahead of** the §26.4 arbitration ladder rather than inside it, *"because it reduces the size of the gap rather than closing a gap that already exists."* The design's `SELECTION_ORDER` has no pre-stage phase. Pre-cooling is mentioned as an agent capability and a console control but never appears in the response ordering.

This is a correctness gap, not an omission: as written, the arbitration would size a gap without accounting for the pre-staging that should already have reduced it.

### 2.3 LLM usage examples — adequate, with one omission

Present and sufficient: the five-phase loop sequence diagram (§4.2), the `Recommendation` Pydantic contract (§4.3), the per-agent Mistral/Claude routing table with justification (§4.4), the `ModelRouter` fallback ladder in code (§4.6), the `Deidentifier` in code (§4.7), and three worked workflows (§4.8) — of which Workflow C is the most valuable, because it honestly shows the agent arriving 18 seconds *after* the control plane has already responded.

Missing: **the agent base class itself (C-3)**. Deliverable #3 promises it; the document describes the loop in prose and a diagram but never shows the class that implements it. Given that every agent inherits its evidence floor, expiry, and provenance stamping from that class, its absence is the difference between eight consistent agents and eight variations.

Also absent: **the actual prompt templates**. §4.9 states three prompt disciplines but shows no rendered system prompt for any agent. `prompt_digest` is specified as a schema field, which implies a canonical rendering exists; it is never shown.

---

## 3. Dashboard Interactivity

### 3.1 Real-time support — adequate

The snapshot-plus-delta protocol at 4 Hz with `seq` gap detection and slow-client drop-to-resync is correctly specified, and the design is right that the failure mode of a cleverer protocol is a console silently displaying stale power figures. The `QueueFull` branch — dropping a slow client rather than back-pressuring the tick — is the correct priority and is tested (SIM-12).

The interpolation rule (client-side interpolation rendered in a distinct visual weight) is a good detail that most designs omit.

### 3.2 User controls — aligned, with one conflation

The three affordances (Propose / Acknowledge / Confirm-consequence) map correctly to authority classes, and §19.11's requirement that a control declares its authority *before* it is pressed is satisfied. The type-to-confirm modal naming affected `job_id`s and lost job-hours correctly implements §19.3's restoration-asymmetry requirement.

**B-3 — Scenario Planner and Scenario Builder are conflated.** *(Phase-gating)*

v2.5 §18.5 specifies the Scenario Planner as an analytical consumer of persisted history that answers *"what if we added more BESS instead of a second turbine"* (FR-4.4) and reports to the operator dashboard as VP-of-Infrastructure-facing output. The design's §2.4 Scenario Builder is a stressor-injection test harness with pass/fail assertions.

These are different products serving different personas. Both are needed. Page 9 in the design's inventory claims to be the former and specifies only the latter. The TCO/what-if cost model — marginal cost per MWh across import, generation, and storage round-trip, with turbine cost as amortized capital rather than fuel alone (§21.2 workstream 3) — is entirely absent.

### 3.3 Tech stack — appropriate

React + TypeScript + Vite + FastAPI + WebSockets is the right choice for nine routed pages with modal confirmation flows and 4 Hz deltas. The rejection of Streamlit is correctly argued. TypeScript is correctly identified as load-bearing rather than preference, because the delta protocol is easy to get subtly wrong untyped.

**No finding on stack selection.** See C-1 for the missing frontend code.

---

## 4. Replit-Independent Databases

### 4.1 Decoupling — correct, and correctly bounded

The Tier 0 local / Tier 1–2 external split is the right resolution of the original requirement, and the argument is sound: the intent behind "Replit-independent databases" is that no state of lasting value is trapped in Replit, which is fully satisfied. Putting a WAN hop behind a dispatch decision would satisfy the letter of the request and contradict §22.1 principle 1 and §22.6.

The Postgres and S3-compatible choices scale independently of Replit. The MongoDB and Firebase rejections (§6.6) are argued on architecture rather than capability, which is the right basis — the Firebase argument in particular (its real-time model would invert the §19 authority model, rendering whatever is in the datastore rather than what the control plane decided and audited) is correct and non-obvious.

### 4.2 Schema, APIs, data flows — mostly clear, two gaps

The DDL is implementation-ready for ingest, forecast, audit, recommendations, quarantine, and scenarios. Two decisions are well-justified: `forecast.applied_params` denormalized so a band is reproducible from the row alone, and `scenario_run.dispatch_trace_hash` so TC-48 is an equality comparison rather than a diff.

Missing tables:

- `network_telemetry` (A-2)
- `reservation` / `reservation_proposal` and price-curve history (B-4)
- `asset_health` / maintenance window records (B-5)
- Learning-store entities. §22.2 places the learning store in Tier 1 and §21.5 specifies it as a structured store over typed entities; the design references it and never schematizes it

### 4.3 Fallback for persistence — strong

Tier 1 unavailable → buffer to Tier 0 and drain (TC-37, SIM-08). Tier 2 unavailable → local backlog with a 70% pressure alert and a documented preference ordering that never sacrifices control or audit data (TC-38). Every secret absent → fully functional deterministic simulator with no agents.

The last of these is the best fallback property in the document: it makes the prototype demonstrable on a laptop with no credentials, and it exercises LP-1 through configuration rather than through failure.

**No finding.**

---

## 5. Testing and Validation

### 5.1 Test case comprehensiveness — the headline problem

The design asserts: *"All 76 cases (TC-01 … TC-76) are implemented as scenario-driven blackbox tests against a running instance."* This assertion is false as written.

**19 of 76 tests (25%) have no component to test against:**

| Tests | Count | Blocked by |
|---|---|---|
| TC-50, TC-51 | 2 | A-2 (no NetworkTelemetry) |
| TC-53 | 1 | A-4 (no counting unit) |
| TC-54 | 1 | A-4 (no vintage) |
| TC-59, TC-60 | 2 | B-5 (no maintenance model) |
| TC-64 … TC-68 | 5 | A-1 (no PMS / protective layer) |
| TC-69 … TC-74 | 6 | A-2 (no clock classes, no capability tiers) |
| TC-75, TC-76 | 2 | B-1 (no adaptive ramp relaxation) |

Two further tests — TC-47 and TC-52 — are weakly supported: the firm/reserved/non-firm distinction exists as a table row but no reservation entity does, so TC-52 ("proposal remains in `under_review` indefinitely or until it expires") has no proposal type to exercise.

This directly invalidates the Phase 2 and Phase 5 gates in the design's §9.1, both of which list blocked tests as passing criteria.

The 15 prototype-specific tests (SIM-01 … SIM-15) are well-constructed. SIM-11 (build-breaking static check that no control-plane coroutine reaches the HTTP client, Postgres driver, model router, or wall clock) is the single most valuable test in the document, because it converts the architecture's central rule from a convention into a mechanism.

### 5.2 Validation metrics — correct, with one gap

The correction of "100% LLM uptime" to "0% control-plane dependence on model availability" is right, and the reclassification of vendor availability as a cost-and-usefulness signal rather than a reliability one is correctly argued.

The three-tier metric structure (safety-and-correctness / performance / service-quality) with only the first blocking release is appropriate.

**C-4 — No load-test design exists** for the NFR-2 p99 targets asserted in §7.4. The design states `p99 ≤ 2.0 s` decision-to-command and `p99 ≤ 250 ms` tick compute with no harness, no load profile, and no measurement methodology. SIM-13 specifies 50 concurrent clients during a 20 MW step-load, which is a UI load test, not an NFR-2 validation.

**B-7 — Confidence band widening factors are unspecified.** §12 and §17.3 require independent, composable widening for four tags. The design says bands widen and never states by how much, or whether composition is additive or multiplicative. TC-16 ("strictly wider") passes under any rule; **TC-17 (conservative dispatch sizing off the lower bound) is sensitive to magnitude** — a widening factor chosen carelessly either never fires the alert or fires it constantly. v2.5 does not specify these either, so this is an inherited gap, but a simulator must pick numbers and must tag them as chosen rather than derived.

### 5.3 Edge cases — well covered, one recovery path missing

Agent conflicts (§7.3 stress tests), LLM failures (§4.6 ladder), rogue agents, gate-bypass attempts, and autonomy-escalation attempts are all specified with assertions. The agent-starvation test honestly reports that the prototype **cannot** distinguish "offline" from "no option available" (AG-3) rather than papering over it.

**B-8 — §17.2 recovery path unspecified.** v2.5 requires an affected job's contribution be treated as 0 MW and tagged `low_confidence: invalid_payload` *"until a corrected event for that job_id is received."* The design never specifies how a corrected event clears the tag, what constitutes "corrected", or what happens to forecast segments already issued under the tag.

---

## 6. Alignment with Constraints

| Constraint | Adherence | Note |
|---|---|---|
| Exclusively Mistral and Claude | **Yes** | Router has exactly two vendor clients. Exclusions documented with reasons so the decision is revisitable rather than re-litigated |
| Modularity | **Yes** | §22.1 principle 4 honoured — tier substitution is a connection-string change |
| Scalability | **Yes, correctly framed** | The design correctly identifies that the scaling property that matters is that agents, sites, and analytics add nothing to the control path |
| Real-time performance | **Partial** | Targets stated; no load-test design to validate them (C-4) |
| No conflicting dependencies | **One** | See below |

**Conflicting assumption identified.** The design's §5.4 states that Tier 0 loss on Replit redeploy is *"a feature of the demo rather than a defect"* because it exercises the §22.3 restart path. This is half right and half wrong. §22.3 explicitly distinguishes a **restart** (Tier 0 present, state reconstructed, never a cold start) from a **cold start** (no Tier 0 record at all, which is the §17.3 `uncalibrated_site` path), and states the two *"must not share an implementation branch."*

A redeploy that destroys the Tier 0 file is a cold start, not a restart. It therefore exercises the wrong path, and framing it as a demonstration of restart behaviour would demonstrate the opposite of what §22.3 requires. Either persist Tier 0 across redeploys, or state plainly that redeploy is a cold start and that restart behaviour is demonstrated by in-process restart only.

---

## 7. Deliverables and Documentation

### 7.1 Deliverables produced vs. promised

| # | Deliverable | Status |
|---|---|---|
| 1 | Design document | **Delivered** |
| 2 | Diagrams (architecture, autonomy, agent loop, navigation, data flow) | **Delivered** — five Mermaid diagrams, all verified to render |
| 3 | Agent logic reference implementation | **Partial** — router, de-identifier, and Recommendation contract shown; **base class and prompt templates missing (C-3)** |
| 4 | Control-plane reference implementation | **Partial** — arbitration ranking and bridging capability shown; formula and classifier not |
| 5 | Dashboard API surface | **Partial** — endpoint table and WS broadcaster shown; **no OpenAPI, no WS protocol schema** |
| 6 | Frontend components | **Not delivered (C-1)** — no React code anywhere in the document |
| 7 | Database schema | **Partial** — DDL delivered; **no SQLAlchemy models, no buffered-writer implementation (C-2)** |
| 8 | Scenario definitions | **Partial** — one full YAML example, six presets described in a table only |
| 9 | Test matrix | **Partial** — see §5.1; 19 tests unsupported |
| 10 | Implementation checklist | **Delivered** — phase-gated, though two gates are unreachable |
| 11 | User guide | **Delivered** (abridged, correctly marked) |
| 12 | Deployment runbook | **Not delivered** — listed only |

### 7.2 Audience adequacy

**For developers:** adequate for Phases 0–1 and Phase 5, thin for Phases 2–4. An engineer could build the control plane and the advisory plane from this document. They could not build the simulated PMS, the fabric telemetry layer, or the console frontend without further specification.

**For stakeholders:** strong. §10.3 (what the prototype demonstrates well) and §10.4 (the claim not made) are the right shape for an investor conversation, and the refusal to assert the 80% intervention-reduction figure is correct — the audience most likely to be shown this demo is the audience most likely to ask how the figure was derived.

---

## 8. Risk Assessment

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R-1 | **Plane separation erodes during implementation** — a developer adds an `await` on a model call inside a control coroutine to "make the demo smarter" | Medium | Critical — destroys the product's central claim | SIM-11 already mitigates this and is the correct mechanism. **Strengthen:** make it a pre-commit hook as well as a CI gate, and add the wall-clock check explicitly to the same rule |
| R-2 | **Unreviewed recommendation queue** — eight agents outproduce one operator; the gate becomes ceremonial | **High** | High — "an unread queue is autonomous operation with a compliance artifact attached" (AG-4) | Impact ranking, grouping, and expiry are specified. **Add:** a hard per-day recommendation budget per agent, and a queue-depth metric with an alert. Instrument acceptance rate per agent from day one so a systematically ignored agent can be disabled |
| R-3 | **LLM latency masks as system latency** in a demo | Medium | Medium — reputational in the room, not technical | Already mitigated architecturally. **Add:** render agent-derived panels with an explicit "as of" timestamp so an operator never mistakes stale advisory output for live telemetry |
| R-4 | **Token spend unbounded at scale** (LP-3) | Medium | Medium — commercial | §4.5 budget mechanism is correct. **Add:** a hard monthly ceiling in addition to the daily one, and alert at 70% consistent with the §22.4 backlog convention |
| R-5 | **Tier 0 single-store loss** (ST-2) | Low in demo, **High in production** | Critical — loss of Tier 0 is loss of dispatch | Correctly carried as an open item. **Do not solve it in the prototype**; solve it with the §18.7 edge-appliance redundancy question, as v2.5 instructs |
| R-6 | **External Postgres latency spikes** under Replit's variable egress | Medium | Low — buffered, off the control path | Already mitigated. **Add:** SIM-08 should inject latency, not just unreachability — a slow store is a more common failure than an absent one and exercises the buffer differently |
| R-7 | **Simulated-clock drift between the two planes** — advisory plane reasons over Tier 1 rows stamped in simulated time while running in wall time | Medium | Medium — silent evidence-window errors | Both clocks are persisted per §3.1. **Add:** an assertion that every agent's evidence window is expressed in simulated time, and a test that an agent's window is correct at 60× acceleration |
| R-8 | **19 unexecutable tests are quietly dropped** rather than closed, and the design's "all 76" claim persists into a stakeholder conversation | **High** | High — credibility | This review. Correct the claim in §7.1 of the design to state coverage explicitly, and gate each phase only on tests its components support |
| R-9 | **Scenario Planner never gets built** because Page 9 appears to exist | Medium | Medium — FR-4.4 unaddressed | B-3. Separate the two products in the page inventory before Phase 4 |
| R-10 | **`reviewer_id` remains an unvalidated string** through to a customer demo | **High** | High — the gate is the safety argument | A-5. A three-role stub is a day of work and forces LP-2 into an answerable shape |

---

## 8A. Pass 2 — Findings Missed by the First Review

Pass 1 reviewed the design against v2.5 and found coverage gaps. Pass 2 reviewed the design **against itself** — internal arithmetic, code correctness, and schema executability — which is a different failure surface. Seven findings, three of them demonstrable rather than arguable.

### A-6 — The token budget is short by 20–100× against the design's own cadence table *(Blocking)*

Design §4.4 fixes a per-agent cadence. Design §4.5 fixes a daily budget of 400 000 input tokens. These two numbers were written independently and are not compatible.

| Agent | Cadence (§4.4) | Calls/day |
|---|---|---|
| Compute & Workload | 30 s | 2 880 |
| Storage | 60 s | 1 440 |
| Renewable Supply | 60 s | 1 440 |
| Network Telemetry | 60 s | 1 440 |
| Generation | 5 min | 288 |
| Thermal | 5 min | 288 |
| Procurement | 15 min | 96 |
| Calibration | daily | 1 |
| **Total** | | **7 873** |

400 000 ÷ 7 873 = **50.8 input tokens per call.** An evidence window carrying a numeric time series, per §4.7's `DeidentifiedEvidence` structure, will not fit in 51 tokens; a realistic window is 1 000–5 000.

| Evidence size | Daily need | Multiple of budget | Budget exhausted after |
|---|---|---|---|
| 1 000 tok/call | 7.9 M | 20× | 400 calls (~73 min) |
| 2 000 tok/call | 15.7 M | 39× | 200 calls (~37 min) |
| 5 000 tok/call | 39.4 M | 98× | 80 calls (~15 min) |

**Consequence.** §4.5 specifies that budget exhaustion drops all agents to deterministic fallback. As written, the prototype enters fallback mode within the first hour of every session and stays there. Every agent-driven demonstration would run on threshold heuristics while reporting `generated_by: "fallback"` — which is honest, and useless.

This also means SIM-06 ("token budget exhausted mid-run → zero change to dispatch trace") would pass trivially and continuously, testing nothing.

**Fix:** either raise the budget to a defensible figure derived from measured evidence size, or lengthen cadences, or both. The budget must be **derived from** the cadence table rather than chosen beside it. Note that this makes LP-3 sharper rather than softer: the real exposure is 8–40 M tokens per site per day, which is a commercial number worth knowing before a design-partner conversation.

### A-7 — Agent cadence clock is unspecified, creating a 60× cost exposure *(Blocking)*

Design §3.1 resolves ST-4 by measuring **all specification intervals against simulated time**, and states that no control-plane code reads a wall clock. It never says which clock agent cadence uses.

If agent cadence follows simulated time — the natural reading of §3.1 — then at the `GS_SIM_RATE = 60` acceleration the design itself proposes for the 24-hour-cycle scenario:

| Sim rate | Calls per wall-day |
|---|---|
| 1× | 7 873 |
| 10× | 78 730 |
| 60× | **472 380** |

A 15-minute accelerated demo would issue roughly 5 000 model calls. Combined with A-6 this is not merely expensive; it is a plausible way to exhaust a vendor quota during a live demonstration.

**Fix:** state explicitly that **agent cadence is wall-clock**, while agent *evidence windows* are expressed in simulated time. These are genuinely different clocks serving different purposes, and the design currently conflates them by omission. This is R-7 manifesting concretely rather than hypothetically.

### A-8 — The Tier 1 DDL will not execute *(Blocking)*

Both partitioned tables in design §6.2 are invalid PostgreSQL:

```sql
CREATE TABLE workload_signal (
    event_id TEXT PRIMARY KEY,     -- partition key not included
    ...
) PARTITION BY RANGE (source_ts);  -- ERROR

CREATE TABLE forecast (
    id BIGSERIAL PRIMARY KEY,      -- partition key not included
    ...
) PARTITION BY RANGE (issued_at);  -- ERROR
```

PostgreSQL requires that any unique or primary-key constraint on a partitioned table include every partition-key column. Both statements fail at `CREATE TABLE`, not at runtime.

**Fix:** `PRIMARY KEY (event_id, source_ts)` and `PRIMARY KEY (id, issued_at)`. Note the interaction with **A-3** (dedupe key divergence): if A-3 is resolved by adopting the specified `(site_id, job_id, event_type, event_id)` tuple, the partitioned primary key becomes that tuple plus `source_ts`, and the two findings close together rather than separately.

### B-9 — Arbitration selection is not deterministic as coded *(Phase-gating)*

Design §1.6's `select_responses` builds `by_kind = {r.kind: r for r in recs}`. Two problems:

- If two agents publish the same `kind` against one shortfall, the later one **silently overwrites** the earlier. No rule specifies which wins, and none is logged.
- Determinism depends on the ordering of `recs`, which arrives from a Tier 1 query. Design §6.2 defines no `ORDER BY` for that read, so ordering is whatever the planner returns.

TC-49 requires that *"selection is reproducible from the recommendation set alone."* As coded, it is reproducible from the recommendation set **and** an unspecified sort order. This is the one place the design lets non-determinism back into a control-adjacent decision — precisely the property §26.4 exists to protect.

**Fix:** sort `recs` by a total order (`kind`, then `estimated_impact` descending, then `recommendation_id`) before selection, and specify explicitly what happens when two agents publish the same kind — rank them rather than dropping one.

### B-10 — Three code defects in the reference implementations *(Phase-gating)*

- **`Broadcaster.run()` (§2.2):** the `except asyncio.QueueFull` handler calls `q.put_nowait(RESYNC_SENTINEL)` on the queue that just raised `QueueFull`. It will raise again, uncaught, inside the broadcast loop — killing the broadcaster for **all** clients because one was slow. This inverts the intended behaviour exactly. Fix: drain-one-then-put, or set a per-client `needs_resync` flag outside the queue.
- **`ModelRouter.reason()` (§4.6):** the fallback table specifies "one retry with jittered backoff." The code has no sleep and no jitter. Table and code disagree.
- **`bridging_available_mw()` (§3.3):** `min(bess.rated_mw, usable_soc_mw)` is redundant — `usable_soc_mw` already takes a `min` against `rated_mw`. Harmless, but `usable_energy_mwh` is ambiguous between nameplate and currently-available energy, and the anchor arithmetic is the one place in the design where an ambiguous variable name is expensive.

### B-11 — Console sampling is undefined above ~50× acceleration *(Phase-gating)*

Design §2.2 fixes the console at 4 Hz (250 ms) "regardless." Design §3.1 permits `GS_SIM_RATE` acceleration. At 60×, a 5-second simulated tick completes every 83 ms of wall time — **three ticks per rendered frame.** The console silently undersamples, and the design's interpolation rule makes the dropped ticks invisible rather than visible.

This matters because §2.4's 24-hour-cycle preset is specified to run accelerated, and §10.3 lists console panels as the primary demonstration surface.

**Fix:** either couple frame rate to tick rate above a threshold, or decimate deliberately and label the panel as decimated. The current design does the latter without saying so.

### C-5 — Two schema and scenario details that block their own tests *(Deliverable)*

- **`control_event` is self-contradictory.** The DDL comments it as *"Immutable by policy: no UPDATE or DELETE grant on this table for the app role"* and then defines `acknowledged_at TIMESTAMPTZ`, which can only be populated by an `UPDATE`. Fix: move acknowledgment to a separate append-only `control_event_ack` table, preserving immutability.
- **`quarantine.raw_payload` is typed `JSONB NOT NULL`.** §17.2 requires malformed events be *"logged in full."* A payload that is truncated or not valid JSON cannot be stored in a `JSONB` column — meaning the store cannot hold the exact class of input it exists to capture. Fix: `TEXT`, with an optional parsed `JSONB` sidecar.
- **`recommendation` mixes clock domains:** `expires_at_sim_s` is simulated time; `suppressed_until` is `TIMESTAMPTZ`. Pick one basis per table, or name both explicitly.
- **The §2.4 scenario YAML's TC-33 assertion has `expect:` but no `check:`**, so it is prose, not an executable assertion. Every assertion needs a machine-evaluable `check:`.

### D-4 — SIM-11 is asserted but not specifiable as written *(Recorded)*

Design §1.2 and §7.2 specify SIM-11 as *"static analysis over the control-plane call graph"*, build-breaking. Full call-graph analysis of Python is not decidable in the presence of dynamic dispatch, and SIM-11 is the mechanism the entire plane separation rests on.

What is feasible is an **import-and-attribute-reachability check** over modules reachable from `@control_plane`-decorated coroutines, combined with a runtime guard that raises if a control-plane task touches a forbidden module. That is weaker than claimed and strong enough in practice, but the design should say which one it means. An enforcement mechanism described more confidently than it can be implemented is worse than a weaker one described accurately.

---

## 9. Defects Found in v2.5 Itself

These are in the parent specification, not the design. Reported because cross-reference integrity matters and one of them has propagated.

**D-1 — Agent count disagrees with the agent table.** §26.2 lists **seven** agents (Compute & Workload, Storage, Generation, Thermal, Procurement, Network Telemetry, Calibration). Three passages say **six**:

- §19.10: *"Six agents (26.2) each generating recommendations…"*
- §26.6 AG-1: *"Six agents with different cadences… the interaction with LP-3's undefined cost ceiling is now six times larger."*
- §26.6 AG-4: *"Six agents generating recommendations against a single operator's attention…"*

Likely cause: the Calibration agent was added to the table when the learning plane was named, without updating the prose. AG-1's "six times larger" should read "seven times larger" — and eight, if PA-2's Renewable Supply agent is adopted.

**D-2 — §19.7 does not exist, and two references land on the wrong page.** Section 19 numbering runs 19.1 … 19.6, then jumps to 19.8. Consequently "Page 6 — Grid & Procurement" sits at §19.8, and:

- §26.3 states *"Recommendations are ranked and triaged on this (19.8)"* — but ranking and triage are specified at §19.10, Page 8 Proposals & Learning. §19.8 is Grid & Procurement.
- §26.6 AG-4 states *"Grouping, impact ranking, and bulk disposition are stated as requirements in 19.8"* — same error. The requirement text is in §19.10.

This is substantive, not cosmetic: both references point a reader at the procurement page when they mean the review queue. **The design document inherited and repeated the AG-4 text verbatim in its §9.2**, propagating the error.

Recommended fix: renumber §19.8 → §19.7 and cascade, or insert a §19.7 if one was intended and lost. Either way, correct the two citations to §19.10.

**D-3 — §19.1 lists nine console pages; only eight have subsections.** Page 9 (Scenario Planner) appears in the inventory with a specified control surface and has no corresponding §19.x subsection. This is the likely root of design finding B-3 — with no page specification to implement against, the design substituted the test-harness Scenario Builder.

---

## 10. Remediation Checklist

Ordered by when it blocks. Check items only when the specification text exists, not when it is agreed.

### Before implementation begins

- [ ] **A-3** Reconcile the dedupe key: adopt the `(site_id, job_id, event_type, event_id)` tuple, or record an explicit deviation arguing subsumption by globally unique `event_id`
- [ ] **A-5** Specify a minimal authorization model: `viewer` / `operator` / `approver`, keyed to the §1.4 authority matrix; `reviewer_id` becomes a validated principal
- [ ] **R-8** Correct the design's §7.1 coverage claim; re-gate each phase only on tests its components support
- [ ] **D-1, D-2, D-3** Raise the three v2.5 defects; remove the inherited §19.8 misreference from design §9.2
- [ ] **A-6** Re-derive the §4.5 token budget **from** the §4.4 cadence table and a measured evidence-window size. Record the resulting per-site daily figure as the real LP-3 exposure
- [ ] **A-7** State explicitly that agent **cadence is wall-clock** while agent **evidence windows are simulated time**; add the accelerated-rate cost bound
- [ ] **A-8** Fix both partitioned-table primary keys (`event_id, source_ts` and `id, issued_at`). Close jointly with A-3, since the dedupe-tuple decision changes the composite key
- [ ] **D-4** Restate SIM-11 as an import-and-attribute reachability check plus a runtime guard, or specify how call-graph analysis is made sound

### Before Phase 1 gate (control plane)

- [ ] **A-4** Add `counting_unit` (chassis / cabinet / package / die / accelerator) and `vintage` to the hardware profile library; add the §5.2 mismatch quarantine rule and the §5.3 18-month staleness flag and generation-gap prompt
- [ ] **B-7** Specify confidence-band widening factors per tag and the composition rule; tag them as chosen values, not derived
- [ ] **B-8** Specify the `invalid_payload` recovery path: what constitutes a corrected event, how the tag clears, and what happens to segments already issued
- [ ] **§11.2** Add explicit job-cancellation-mid-ramp handling to the design body (currently only implied by the checklist)
- [ ] **B-9** Sort recommendations by a total order before selection; specify the same-`kind` collision rule. TC-49 is unassertable until this exists
- [ ] **B-10** Fix `Broadcaster.run()` — the `QueueFull` handler raises `QueueFull`, killing the broadcaster for every client because one was slow
- [ ] **B-10** Add the jittered backoff the §4.6 fallback table specifies but the code omits
- [ ] **B-10** Disambiguate `usable_energy_mwh` (nameplate vs currently available) in `bridging_available_mw`

### Before Phase 2 gate (simulated plant)

- [ ] **A-1** Specify a simulated power management system: shed priority order, protective fast-load-shed trigger, transition modes, and the §28.3 command egress surface that TC-68 captures against
- [ ] **A-2** Specify the NetworkTelemetry contract (§25.2), platform capability tiers (§25.3), emission-mode reporting, and the §11.4 clock-class model (PTP / NTP, with false-precision demotion)
- [ ] **B-1** Specify adaptive ramp relaxation (§23.7.2), including the §23.7.1 static-baseline comparison the specification insists on stating plainly
- [ ] **B-2** Insert a pre-staging phase **ahead of** the §26.4 arbitration ladder; correct `SELECTION_ORDER` to size the gap after pre-staging has reduced it
- [ ] **B-5** Specify asset health, degradation, availability state, the §27.3 prescriptive ladder, and window validation across full duration (TC-59)
- [ ] **B-6** Specify inference micro-ramp behaviour, or state explicitly that the simulator emits a placeholder and tags it — following the PROTO-1 precedent
- [ ] **§6** Confirm which of TC-47 / TC-52 the reservation model must support

### Before Phase 3 gate (persistence)

- [ ] **B-4** Add `reservation`, `reservation_proposal`, and price-curve tables; specify `T_reserve` and demand-charge exposure
- [ ] **A-2** Add `network_telemetry` table
- [ ] **B-5** Add `asset_health` and maintenance-window tables
- [ ] **§21.5** Schematize the learning-store entities in Tier 1
- [ ] **§5.4** Resolve the redeploy-is-a-cold-start conflict: persist Tier 0 across redeploys, or restate the demo claim honestly
- [ ] **C-5** Move `acknowledged_at` out of `control_event` into an append-only ack table; the current DDL contradicts its own immutability comment
- [ ] **C-5** Retype `quarantine.raw_payload` to `TEXT` — a `JSONB` column cannot store the malformed payloads §17.2 requires be logged in full
- [ ] **C-5** Resolve mixed clock domains in `recommendation` (`expires_at_sim_s` vs `suppressed_until`)

### Before Phase 4 gate (console)

- [ ] **B-3** Separate Scenario Planner (§18.5 TCO what-if, FR-4.4) from Scenario Builder (test harness); specify the cost model, including turbine cost as amortized capital against duty cycle
- [ ] **C-1** Produce React component code: console shell, delta reducer, and one authority-affordance component per class
- [ ] **§19** Specify Page 9 against a v2.5 subsection once D-3 is resolved
- [ ] **B-11** Define console sampling above ~50× acceleration: couple frame rate to tick rate, or decimate deliberately and label it

### Before Phase 5 gate (advisory plane)

- [ ] **C-3** Produce the agent base class implementing the five-phase loop
- [ ] **C-3** Produce at least two rendered system prompts, since `prompt_digest` implies a canonical rendering
- [ ] **R-2** Add a per-agent daily recommendation budget and a queue-depth alert
- [ ] **R-7** Add an assertion that every agent evidence window is expressed in simulated time; test at 60× acceleration

### Before Phase 6 gate (acceptance)

- [ ] **C-4** Design the NFR-2 load test: load profile, harness, measurement methodology, and the distinction from SIM-13's UI load test
- [ ] **R-6** Extend SIM-08 to inject Tier 1 *latency*, not only unreachability
- [ ] **C-5** Give every scenario assertion a machine-evaluable `check:`; the §2.4 TC-33 assertion currently has only prose
- [ ] **A-6** Re-verify SIM-06 is non-trivial — under the current budget it passes continuously and tests nothing
- [ ] Re-verify the full matrix once A-1, A-2, B-1, B-4, B-5 land — target 76 of 76 executable

### Before Phase 7 (deployment)

- [ ] **C-2** Produce SQLAlchemy models and the buffered-writer implementation
- [ ] Produce the deployment runbook (listed as deliverable 12, not produced)
- [ ] Produce OpenAPI output and a formal WS protocol schema

---

## 11. Items Correctly Carried — No Action

These are properly recorded open items with stated rationale. Leaving them open is the right decision and closing them with an assumption would be worse.

AG-1 (per-agent model assignment, provisional), AG-2 (agent placement), AG-3 (arbitration under partial information — correctly reported as unsolved rather than papered over), AG-4 (review capacity), LP-2 (approval authority — though see A-5 for the prototype stub), LP-3 (cost ceiling, mechanism without a validated number), LP-5 (significance floor), ST-2 (Tier 0 redundancy — correctly deferred to the §18.7 decision), PX-2 (genset anchor droop), CL-1 (Tier B yield), PROTO-1 and PROTO-2 (Δt_lead curve and wind power curve, both correctly tagged as unvalidated modelling choices).

The four proposed v2.5 amendments (PA-1 … PA-4) are appropriately framed as proposals not in force.

---

## 12. Final Answer

**The design specification is not complete and is not ready for implementation in full.**

After two passes, it is ready for **Phase 0** — foundation — subject to closing the eight blocking items first. Pass 1's conclusion that Phase 1 was reachable no longer holds: A-8 means the Tier 1 schema does not execute, and B-9 means TC-49 is unassertable, and both sit inside the Phase 1 gate.

The document's architecture remains right, and the parts it specifies, it specifies well. It has two distinct defects, found by two distinct kinds of reading:

- **It asserts coverage it does not have.** 19 of 76 acceptance tests are claimed against components no section describes, concentrated in v2.5 Sections 24, 25, 27, and 28 — the four sections added most recently to the parent specification, which is the expected place for a derived document to lag.
- **Its numbers do not agree with each other.** The token budget contradicts the cadence table by 20–100×; the cadence clock is unspecified against a 60× accelerator the same document introduces; the DDL does not execute; and the one code path guarding arbitration determinism depends on an unspecified sort order.

The second class is the more instructive. Every one of those findings is internal — none required reading v2.5 at all — which means a single pass against the parent specification is not a sufficient review procedure for this document. The next revision should be read twice on purpose: once outward against v2.5, once inward against itself.

**Recommended sequence.** Close A-6, A-7, and A-8 first — they are arithmetic and schema corrections measurable in hours, and A-6 additionally produces the real LP-3 number, which is worth having before any design-partner conversation. Then A-3 and A-4 (which close together with A-8), then A-5, then the phase-gating items in checklist order, which is also the order the build plan consumes them.

**Estimated remediation:** 8 blocking items, of which 5 are small (arithmetic, schema, a role stub) and 3 require new specification (A-1 PMS, A-2 NetworkTelemetry, plus B-1 adaptive ramp relaxation). The three specification items are the real work; everything else is correction.

---

*End of review.*
