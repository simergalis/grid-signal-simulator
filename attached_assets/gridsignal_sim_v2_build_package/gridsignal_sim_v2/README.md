# GridSignal Simulator — Build Package v2.1

Everything needed to start Build Plan v2.1 on Replit, in one archive.

```
gridsignal_sim_v2/
├── README.md                      <- this file
├── gridsignal_sim/                <- the skeleton, UNMODIFIED. Upload this to the Repl.
│   ├── core/                        deterministic, synchronous, no asyncio
│   ├── runtime/                     the asyncio concurrency layer
│   ├── scripts/load_test.py         NFR harness — keep it as a gate, don't discard it
│   └── tests/                       10 existing tests, all passing
├── audit_tests/                   <- every audit finding as an executable test
│   ├── test_step1b_findings.py      5 fail + 1 pass on the unmodified skeleton
│   └── test_step3_findings.py       7 fail on the unmodified skeleton
├── reference/                     <- verified implementations to draw on, not drop in
│   ├── arbitration_fix.py           deterministic §26.4 selection (Step 10)
│   ├── broadcaster_fix.py           slow-client handling reference (Step 7)
│   └── schema_fix.sql               PostgreSQL promotion target (NOT for Step 2)
└── docs/                          <- attach these to the Repl for the whole sequence
    ├── GridSignal_Replit_Build_Plan_v2.1.md
    ├── GridSignal_Skeleton_Audit.md
    ├── GridSignal-Agentic-Prototype-Design_v0.1.md
    ├── GridSignal-Agentic-Prototype-Design-Review_v0.2.md
    └── GridSignal-Agentic-Prototype-Remediation-Pack.md
```

## Quick start

```bash
cd gridsignal_sim
PYTHONPATH=. python -m pytest tests/ -v          # expect 10 passed
PYTHONPATH=. python runtime/example_usage.py     # expect 3 runs printed
PYTHONPATH=. python scripts/load_test.py --matrix # expect 1x passing
```

That is Build Plan v2.1 **Step 1**. If any of the three fails, the transfer or the
environment broke — fix that before anything else. The audit half of Step 1 is already
done; see `docs/GridSignal_Skeleton_Audit.md`.

Then run the audit tests:

```bash
cd gridsignal_sim
PYTHONPATH=. python -m pytest ../audit_tests/ -v
```

**Expected on the unmodified skeleton: 12 failed, 1 passed.** That is correct and is the
point of the file. Build Plan v2.1 Steps 1b and 3 require each fix to demonstrate the *old*
behaviour was wrong, not merely that new tests pass — these tests are that demonstration,
written before the fixes rather than after.

## What each failure means

### Step 1b — bugs, not gaps (`test_step1b_findings.py`)

| Test | Finding |
|---|---|
| `test_explicit_checkpoint_event_does_not_crash` | **B-1.** `apply_explicit_event()` sets `IN_VALLEY` without `drop_onset_time`/`pre_drop_draw_mw`; next tick raises `AssertionError`. This is §6.2's *authoritative* signal path. The `assert` is also stripped under `python -O`, turning a visible crash into silent `None` arithmetic |
| `test_uncertain_state_is_reachable` | **B-2.** `UNCERTAIN` is unreachable dead code — the `elif` requires `recovered < 0.90` on a branch reached only when `recovered >= 0.90` |
| `test_uncertain_grace_period_then_job_end` | **B-2.** The 30 s grace period below it is dead too |
| `test_job_end_is_terminal` | **B-3.** `JOB_END` sits in the re-entry branch, so classification oscillates `job_end → in_valley` with no input change. A controller reading this starts and aborts ramp-down on alternating ticks |
| `test_core_does_not_import_runtime` | **B-5.** `core/scenario_factory.py:30` imports from `runtime/`. Fails Step 4's purity gate on day one |
| `test_effective_pue_identity` | **PASSES — keep it that way.** §12's `PUE_base × (1+α)` holds to 2.2e-12 and nothing else asserts it. Cheapest guard against the α/PUE double-count v1.6 was written to eliminate, and the thing that catches Step 3's superposition change going wrong |

### Step 3 — v2.5-era gaps (`test_step3_findings.py`)

| Test | Finding |
|---|---|
| `test_arbitration_sizes_against_dispatch_required_not_p_total` | **C-1.** `net_demand_mw` is computed *after* arbitration and read by nothing. Solar reduces a displayed figure and has zero effect on dispatch (§7.1.1, TC-33) |
| `test_bess_bridging_excludes_anchor_reserve` | **C-2.** Zero references to anchor or grid-forming anywhere in `core/` (§7.1.2, TC-61) |
| `test_anchor_reserve_defaults_conservatively_nonzero` | **C-2.** TC-63: defaulting to zero silently reproduces the unadjusted arithmetic the constraint exists to correct |
| `test_dt_lead_is_modelled_as_a_ramp` | **B-4.** Draw steps 0 → full TDP in one tick. The 30–60 s of lead time the product exists to exploit is not simulated |
| `test_second_step_load_produces_its_own_cooling_rise` | **PA-5.** With α pinned at α_max, the second step-load arrives as a **+2.000 MW discontinuity** against a superposed 0.442 MW — the aliasing §8's τ exists to prevent |
| `test_hardware_profile_carries_counting_unit_and_vintage` | **C-3.** §5.2 counting units (a dies-vs-packages mismatch is a **2× forecast error**) and §5.3 vintage (60–90 kW/cabinet under-prediction) |
| `test_checkpoint_classifier_sees_per_job_draw` | **C-4.** `job_draw_mw = p_compute_mw` — the **site-wide** sum, not the module's aggregate as the comment claims |

## Two cautions on `reference/`

**`schema_fix.sql` is not for Step 2.** It is PostgreSQL and it is the *promotion target*.
v2.5 §22.7 requires the simulator's control-plane store to be **one local SQLite file**, "even
where a hosted one is available in the environment." Step 2 builds SQLite through an ORM so
that promoting later is a connection-string change. Use the schema for its table *shapes* and
its constraint reasoning, not its dialect.

**`broadcaster_fix.py` is a reference, not a replacement.** The skeleton's existing
`WebSocketHub.broadcast()` already fans out with `asyncio.gather` and per-socket exception
isolation, which is the behaviour we want. Step 7 **extends** it. The reference exists to show
the slow-client failure mode explicitly.

## Order

1. **Step 1** — the three baseline commands above
2. **Step 1b** — classifier repair + layering fix. Make `test_step1b_findings.py` go 5-fail → 5-pass
3. **Step 2** — persistence
4. **Step 3** — skeleton gaps, Δt_lead ramp, superposed α(t), fleet split + anchor. Make
   `test_step3_findings.py` go 7-fail → 7-pass
5. **Steps 4–17** — per `docs/GridSignal_Replit_Build_Plan_v2.1.md`

`test_effective_pue_identity` must stay green throughout. If it breaks during Step 3, the
superposition was done wrong.
