# GridSignal Simulator — Skeleton Audit against Forecast Engine Functional Spec v2.5

**This is the Step 1 / Phase 0 audit, executed directly. It replaces asking Replit's agent to do it.**

| Field | Value |
|---|---|
| Date | July 29, 2026 |
| Audited | `gridsignal_sim/` skeleton — 7 core files, 1,907 lines |
| Against | Forecast Engine Functional Specification v2.5 |
| Baseline | **10/10 tests pass**; `example_usage.py` runs three concurrent runs cleanly |
| Method | Direct source reading plus executable probes; every defect below was reproduced, not inferred |
| Headline | **3 defects in the checkpoint-valley classifier — the one component that gates turbine ramp-down. Two block acceptance tests; one causes an uncaught crash on the authoritative signal path** |

---

## 1. Baseline

```
PYTHONPATH=. python -m pytest tests/ -v     ->  10 passed in 0.05s
PYTHONPATH=. python runtime/example_usage.py
    [demo-20mw]     ticks=60  P_total=2.521 MW  turbine=2.101  bess=0.420  alerts_seen=False
    [demo-5mw]      ticks=60  P_total=0.630 MW  turbine=0.525  bess=0.105  alerts_seen=False
    [demo-baseline] ticks=60  P_total=0.013 MW  turbine=0.011  bess=0.002  alerts_seen=False
```

The skeleton transferred intact. Note for later: the scenario named `demo-20mw` settles at 2.5 MW and fires no insufficient-reserve alert. That is consistent with finding **B-4** below rather than with a broken scenario.

**10 tests, but only 5 acceptance cases are referenced by ID** — TC-01, TC-02, TC-03, TC-10, TC-11. Not TC-01 through TC-11. Against v2.5's 76 cases that is **6.6% coverage**.

---

## 2. What is better than expected

Recorded first because it changes what the build plan needs to build rather than fix.

| # | Finding | Consequence |
|---|---|---|
| **G-1** | **`core/` is genuinely pure.** Zero `asyncio`, zero network clients, zero database drivers, zero `time.time`/`datetime.now` across all five modules | Step 4's purity gate is codifying an invariant that already holds — with one exception, **B-5** |
| **G-2** | **The job→module routing fix is present and correct.** `_owning_gpu_module()` assigns a job to exactly one module on its first STARTING event and reuses it for every later event on that `job_id` | The O(n²) broadcast bug found during load testing is genuinely fixed, not papered over |
| **G-3** | **`ConfidenceEngine` already has real widening factors and composes them additively** — base 0.05, `unmapped_hardware` +0.10, `uncalibrated_site` +0.08, `invalid_payload` +0.15 | **This partially closes review finding B-7.** Numbers exist; they need a `stale_profile` row and a "chosen, not derived" label, not invention from scratch |
| **G-4** | **Checkpoint thresholds are all correct constants** — 15% drop, 5–30 s duration, 45 s recovery window, 90% recovery, 30 s uncertain grace | The §6.2 arithmetic is right. The **state machine around it** is not — see §3 |
| **G-5** | `evaluate_tick()` is genuinely synchronous, side-effect-free, and fixed-order, exactly as Design Spec §5 claims | The plane separation the agentic layer needs is real |

---

## 3. Defects — bugs, not documented gaps

These were not in the README's "deliberately stubbed" list. All three are in `core/dispatch.py`'s `CheckpointClassifier`, which v2.5 §2 lists as one of the four IP pillars and which gates the decision not to ramp turbines down mid-job.

### B-1 · `apply_explicit_event()` crashes the next tick *(uncaught `AssertionError`)*

§6.2 makes an explicit `checkpoint_start`/`checkpoint_end` pair the **primary, authoritative** signal. The skeleton implements it as:

```python
def apply_explicit_event(self, job_id, is_checkpoint_start, sim_time):
    hist = self._history_for(job_id)
    hist.state = CheckpointState.IN_VALLEY if is_checkpoint_start else CheckpointState.CHECKPOINT
```

It sets `IN_VALLEY` but leaves `drop_onset_time` and `pre_drop_draw_mw` as `None`. The very next tick enters the `IN_VALLEY` branch, which opens with:

```python
assert hist.drop_onset_time is not None and hist.pre_drop_draw_mw is not None
```

**Reproduced:** explicit `checkpoint_start` at t=100, next `record_and_classify` → `AssertionError`.

**Blocks TC-05.** The authoritative path is unusable; only the fallback heuristic works. Worse, an `assert` is stripped under `python -O`, so in an optimised deployment this becomes a silent `None` arithmetic error instead of a visible crash.

### B-2 · `UNCERTAIN` is unreachable dead code

§6.2's ambiguous case — a drop with no recovery and no `job_end` inside 45 s — must yield `uncertain`, hold staging for a further 30 s grace period, and flag the job on the console. The branch exists but cannot be entered:

```python
hist.state = JOB_END if recovered_fraction < 0.90 else NORMAL
if hist.state == JOB_END and self.MIN_DROP_DURATION_S <= elapsed:
    pass                                    # always taken when recovery failed
elif recovered_fraction < 0.90:             # only reachable when state == NORMAL,
    hist.state = UNCERTAIN                  # which requires recovered >= 0.90 —
    hist.uncertain_since = sim_time         # a contradiction
```

If recovery failed, the first branch is always taken. If recovery succeeded, the `elif` condition is false. `UNCERTAIN` is therefore never assigned, and the `if hist.state == UNCERTAIN` block that implements the grace period is unreachable.

**Reproduced:** 16% drop held with no recovery for 75 s → never reaches `uncertain`.

**Blocks TC-08.** Also blocks TC-35 (restart mid-grace-period), which cannot be tested against a state that cannot be entered.

### B-3 · `JOB_END` is not terminal — classification oscillates

`JOB_END` is included in the re-entry branch alongside `NORMAL` and `CHECKPOINT`, so a job classified as ended re-enters drop detection on the next tick. Because the trailing 5-minute median now includes the post-drop low samples, the median falls, and the classifier re-detects — or fails to detect — a drop against its own depressed baseline.

**Reproduced:** `in_valley` → `job_end` at t=350 → **back to `in_valley` at t=360**, with no change in input.

This is precisely the failure §6.2 exists to prevent. A dispatch controller consuming this would start and abort turbine ramp-down on alternating ticks.

### B-4 · Δt_lead is not simulated at all

`GPUModule.apply_signal()` sets `_node_counts[job_id] = signal.node_count` immediately on `STARTING`, and `GPUModule.advance()` is an explicit no-op. **Compute draw goes from zero to full TDP within a single tick.**

Δt_lead appears only as a scalar inside `stage_for_predicted_step()`'s reserve arithmetic. It is never a ramp.

Two consequences:

- **The product's central premise is not in the simulation.** §2 item 1 is 30–60 seconds of lead time before GPUs draw power. Here the draw is instantaneous, so there is no interval during which staging happens ahead of load.
- **The staging call reads the wrong quantity.** `simulation_core.py:78` computes `delta_p_mw = sum(g.output_mw() for g in gpu_modules)` *after* the node count has already been applied — so ΔP is current total site compute, not the predicted step. With one job this coincides; with a job starting alongside existing load it over-stages by the amount of the existing load.

This also explains `demo-20mw` settling at 2.5 MW with no alert: the reserve check compares an already-realised total against a ramp requirement, in a configuration where the numbers happen not to trip it.

### B-5 · `core/` already violates its own layering

```
core/scenario_factory.py:30:  from runtime.run_manager import InMemoryTimeseriesSink, RunContext
```

`core/` imports from `runtime/`. Everything else in `core/` is clean, so this is a single edge — but **Step 4's purity gate would fail on day one**, and the fix is a design decision (move `scenario_factory` to `runtime/`, or invert the dependency behind a Protocol) rather than a mechanical one.

### B-6 · Data-quality tagging is sticky and global, not per-segment

```python
if state._unmapped_hardware_ever_seen:
    tags.add(DataQualityTag.UNMAPPED_HARDWARE)
```

Once any unmapped profile is seen anywhere in the run, **every subsequent forecast carries the tag forever**, including segments no unmapped job contributed to. §5.1 and §12 require tagging the affected *segment*. `invalid_payload` is defined in the widening table but is unreachable — no validation or quarantine path exists to set it.

---

## 4. Confirmed gaps — predicted, and in the plan already

| # | v2.5 requirement | Skeleton state | Blocked |
|---|---|---|---|
| **C-1** | §7.1.1 `P_dispatch_required(t) = P_total(t) − P_renewable(t)`; arbitration sizes ΔP against it | **Absent.** `net_demand_mw` is computed *after* `arbitrator.tick(p_total_mw, …)` and is **report-only** — it is written into `TickResult` and read by nothing. `DispatchArbitrator.tick()` takes `p_total_mw`. Zero symbols matching `dispatch_req` or `renewable` in `core/` | **TC-33** |
| **C-2** | §7.1.2 `BESS_bridging_available = min(rated, usable SoC) − P_anchor_reserve`; anchor role dynamic | **Absent.** Zero references to `anchor` or `grid_form` anywhere. `BessConfig` has no anchor field | **TC-61, TC-62, TC-63** |
| **C-3** | §5.2 counting-unit declaration; §5.3 profile vintage and staleness | **Absent.** `HardwareProfile` is `(profile_id, rated_kw, description)` | **TC-53, TC-54** |
| **C-4** | Per-job draw attribution | Worse than documented. The comment says "the module's aggregate draw"; the code uses `job_draw_mw = p_compute_mw`, which is the **site-wide** sum across all modules | Checkpoint accuracy with >1 module |
| **C-5** | §17.1 dedupe, §17.2 validation/quarantine | **Absent entirely.** No dedupe key, no schema/domain validation, no quarantine | **TC-21 … TC-27** |
| **C-6** | §§23–28 (curtailment, procurement, network telemetry, agents, maintenance, execution layer) | **Absent entirely**, as expected — these postdate the skeleton | ~30 cases |

`SolarConfig` is explicitly commented *"Extension E-1 — not in the source spec; simulator-only"*, which confirms solar predates §7.1.1's promotion of renewable output to a first-class supply term. The skeleton is not wrong for its era; it is pre-v1.7.

---

## 5. What this changes in Build Plan v2

### 5.1 Step 1 is complete

This document is its output. Skip it and proceed — but re-run the two baseline commands after upload to confirm the transfer, since that half of Step 1 is about the Repl environment rather than the code.

### 5.2 A new step is needed before everything else

**New Step 1b — Repair the checkpoint-valley classifier and the layering violation.**

B-1, B-2, and B-3 are all in one ~90-line class, and all three are in the component §2 names as an IP pillar. They should be fixed as one change with tests that fail against the current code:

> **Prompt:**
> Three defects in `core/dispatch.py`'s `CheckpointClassifier`, plus one layering violation. Write a
> failing test for each **before** fixing it, so we can see the current behaviour is wrong.
>
> 1. `apply_explicit_event()` sets `IN_VALLEY` without setting `drop_onset_time` or
>    `pre_drop_draw_mw`, so the next `record_and_classify()` hits the assertion at the top of the
>    `IN_VALLEY` branch. The explicit scheduler event is the **authoritative** path per v2.5 §6.2 —
>    it should short-circuit the shape heuristic entirely, not enter its state machine half-
>    initialised. Also replace that `assert` with a real guard: asserts are stripped under `-O`,
>    which would convert a visible crash into silent `None` arithmetic.
> 2. `UNCERTAIN` is unreachable. When a drop fails to recover within the 45 s window, §6.2 requires
>    `uncertain` — hold staging for a further 30 s grace period, flag the job — and `job_end` **only**
>    on an explicit scheduler `job_end` event or after that grace period expires. Restructure so the
>    45 s expiry routes to `UNCERTAIN`, not straight to `JOB_END`.
> 3. `JOB_END` is not terminal: it is in the re-entry branch alongside `NORMAL` and `CHECKPOINT`, so
>    a classified job flips back to `in_valley` on the next tick. Reproduce with a held 16% drop —
>    the state oscillates. `JOB_END` must be terminal for that `job_id`.
> 4. `core/scenario_factory.py` imports `from runtime.run_manager import …`. `core/` must not import
>    from `runtime/`. Either move `scenario_factory` into `runtime/`, or invert the dependency behind
>    a Protocol defined in `core/`. **Say which you chose and why** — this is a design decision.
>
> Then add TC-05, TC-06, TC-07, TC-08, TC-09 from v2.5 Addendum A as explicit tests, including
> TC-09's exact-boundary case: drop exactly 15.0%, duration exactly 30 s, recovery exactly 90.0% at
> exactly 45 s → classified **checkpoint**, thresholds inclusive.

**Acceptance criteria:**
- Each of the four fixes has a test that **fails against the current code** and passes after. "Tests still pass" does not demonstrate a fixed bug.
- TC-05 … TC-09 pass.
- No `assert` statements remain on a control path.

### 5.3 Step 3 grows — Δt_lead joins it

B-4 belongs with the per-job attribution work, because both live in `GPUModule` and `evaluate_tick()`'s compute term. Add to Step 3's prompt:

> Model Δt_lead as an actual ramp. `GPUModule.apply_signal()` currently applies the full node count
> on `STARTING` and `advance()` is a no-op, so compute draw steps from zero to full TDP in one tick —
> which means the 30–60 s lead time the product exists to exploit is not simulated at all.
>
> A job entering `STARTING` should begin a ramp over its Δt_lead reaching full TDP at the end, with
> `advance()` driving it. Use a piecewise shape matching §6.1's stated physical causes — container
> init near idle, a steep rise through weight load, a plateau at collective warmup — and **tag it as
> a chosen simulator shape with no measured basis**, since §6.1 specifies the interval but not the
> curve inside it.
>
> Then fix the staging call: `simulation_core.py:78` computes `delta_p_mw` as the sum of *all* GPU
> module output after the node count has been applied, so ΔP is total site compute rather than the
> predicted step. It must be the increment this job will add.

This also makes the Step 7 hero countdown meaningful — currently it would count down to a step that has already happened.

### 5.4 Step 4 needs B-5 fixed first

The purity gate fails immediately on `scenario_factory`. Folded into Step 1b above.

### 5.5 Step 2 shrinks slightly

**G-3 is good news for the persistence step**: `ConfidenceEngine`'s widening factors already exist and compose additively. Step 2 adds a `stale_profile` row and the "chosen, not derived" label rather than inventing a scheme. Also add the per-segment tagging fix (B-6) here, since it is a data-model concern — tags belong to a forecast segment, not to a run.

### 5.6 Revised order

| Step | Content | Change |
|---|---|---|
| 1 | Baseline transfer check only | **Audit half complete — this document** |
| **1b** | **Classifier repair + layering fix** | **New, and first** |
| 2 | Persistence + v2.5 tables + per-segment tags | Slightly reduced (G-3) |
| 3 | Skeleton gaps + anchor constraint **+ Δt_lead ramp** | **Grown (B-4)** |
| 4 | Purity gate | Unblocked by 1b |
| 5–17 | Unchanged from Build Plan v2 | |

---

## 6. Revised coverage estimate

| | Before audit | After audit |
|---|---|---|
| Claimed covered | "TC-01 through TC-11" | **5 cases** (TC-01, 02, 03, 10, 11) |
| Blocked by bugs | 0 known | **5** (TC-05 … TC-09) |
| Blocked by gaps | ~19 estimated | **~40** — adds TC-21…TC-27 (no ingest layer), TC-53, TC-54, TC-61…TC-63 |
| Buildable in Steps 1b–11 | — | ~45 of 76 |
| Requires Steps 12–16 | — | ~31 of 76 |

The gap is larger than the review estimated, but the shape is unchanged: **it is concentrated in sections that postdate the skeleton**, plus one component that is broken rather than missing.

---

## 7. The one thing worth deciding before Step 1b

B-4 raises a scoping question the build plan cannot answer for you.

Adding a Δt_lead ramp changes what the existing 10 tests measure. TC-01's instantaneous-compute assertion, and any test asserting a draw figure at a given tick, will shift — because draw at a tick after `STARTING` is no longer full TDP.

Two options:

- **Ramp inside the simulator** (recommended). The simulator then models what the real system sees, and the hero countdown, the staging window, and TC-33's equivalence all become demonstrable. Cost: the existing formula tests need their timing updated, and Step 1b's "do not modify existing test files" rule has to be relaxed for `test_formulas.py`.
- **Keep instantaneous draw and treat Δt_lead purely as reserve-check arithmetic.** Cheaper and preserves every existing test, but the demo cannot show staging happening *before* load, which is the single most persuasive thing it has.

I would take the first. It is more work, and it is the difference between demonstrating the product and demonstrating the formulas.

---

*End of audit.*

---

## 8. Equation verification (added after §7)

Every equation v2.5 specifies was differential-tested against an independent implementation.

| # | Equation | v2.5 | Result |
|---|---|---|---|
| EQ-1 | `P_compute = Σ[Nodes_i × kW_i] × PUE_base / 1000` | §4.1 | **Exact** (delta 0.00e+00). Mixed-fleet Σ is per-job, not single-scalar — TC-04 satisfied |
| EQ-2 | `α(t) = α_max(1 − e^−(t−t₀−Δt_thermal)/τ)`, else 0 | §8 | **Exact at all 9 probe points**, including the `t₀+Δt_thermal` boundary |
| EQ-3 | `P_cooling = α(t) × P_compute(t − Δt_thermal)` | §4.2 | **Present**, nearest-sample lookup (documented; adequate at the 5 s tick) |
| EQ-4 | `P_total = P_compute + P_cooling` | §4.3 | **Exact** |
| EQ-5 | turbine ramp at `r_asset` | §7.1 | **Exact.** §7.3's worked example reproduces: 6 MW at t=30 s, 0 divergences over 24 ticks |
| EQ-6 | `BESS_output = max(0, P_total − turbine_output)` | §7.2.2 | **Exact**, including rated-power and SoC clamps |
| EQ-7 | `gap = ΔP/r_asset − Δt_lead` | §7.2.4, §9 | **Exact.** 20 MW / 30 s lead → 70 s gap, 14 MW peak *declining*, not flat. TC-11 no false alert |
| EQ-8 | effective PUE = `PUE_base × (1 + α)` | §12 | **Exact** — 1.236000 vs 1.236000, delta 2.2e-12. **Untested in the suite** |

**Conclusion: the originally specified equations are implemented and correct.** No equation work is
required and the Forecast Engine spec does not need to gain them.

### 8.1 Absent rather than wrong

Both postdate the skeleton and are present in v2.5. What needs updating is the **Simulator Design
Specification**, which was written against v1.6 and never carried them down.

- `P_dispatch_required(t) = P_total(t) − P_renewable(t)` (§7.1.1)
- `BESS_bridging_available(t) = min(rated, usable SoC) − P_anchor_reserve` (§7.1.2)

### 8.2 A v2.5 defect: cooling does not superpose, but compute does

§11.1 states that concurrent jobs are summed by superposition in `P_compute(t)`, "the Σᵢ term is
per-job-instance." §4.2 and §8 then apply a **single scalar α(t) with a single t₀** to the whole
lagged compute term. Those two are incompatible once jobs overlap, and the incompatibility is not
cosmetic.

Verified numerically. Job A at 5 MW settled; job B adds 10 MW at t=400:

| t | P_compute | Single α, t₀ reset to 400 | Superposed |
|---|---|---|---|
| 395 | 5.0 | 0.000 | 1.000 |
| 400 | 15.0 | **0.000** | 1.000 |
| 490 | 15.0 | **0.000** | 1.000 |
| 500 | 15.0 | 1.180 | 1.787 |
| 700 | 15.0 | 3.000 | 3.000 |

A single α with a reset t₀ drives `P_cooling` to **zero for 90 seconds** when a second job starts,
because α multiplies the whole lagged term including job A's already-settled load. Physically: the
chillers serving a running job switch off because a different job began. Leaving t₀ unreset — what
the skeleton does — instead means no second cooling rise ever occurs.

**Proposed amendment to v2.5 §4.2 / §8** (call it PA-5):

```
P_cooling(t) = Σ_k  α_k(t) × ΔP_compute_k(t − Δt_thermal)
α_k(t) = α_max × (1 − e^−(t − t₀_k − Δt_thermal)/τ)   for t ≥ t₀_k + Δt_thermal, else 0
```

where k indexes step-loads and t₀_k is that step-load's own onset. This preserves the §12 identity
exactly — at steady state `Σ α_k × ΔP_k = α_max × P_compute`, verified to 1e-6 — and makes the
cooling term consistent with §11.1's superposition rule for compute.

### 8.3 Two fidelity decisions, both now taken

- **α(t) onset** — resolved as per-step superposition above (PA-5), *not* a t₀ reset. Folded into
  Build Plan v2.1 Step 3 item 3.
- **BESS fleet aggregation** — `dispatch.py:172` computes
  `total_sustainable_s = min(b.max_sustainable_seconds(peak/n) for b in units)`: named "total",
  operating `min`. With identical units the arithmetic is right; with heterogeneous units the check
  is bounded by the weakest unit rather than the fleet. Resolved as **sum each unit's sustainable
  duration at its allocated share, computed from the fleet split** — folded into Step 3 item 4,
  since it depends on the split existing.

### 8.4 One test to add regardless

The §12 identity holds to 2.2e-12 and **nothing asserts it**. It is the cheapest available guard
against the α/PUE double-count that v1.6 was written to eliminate reappearing under later edits —
particularly the superposition change in Step 3. Added to Build Plan v2.1 Step 1b.
