# GridSignal Simulator v2 — Acceptance Matrix (Step 17, rev AC1–AC3)

Generated: 2026-07-31  
Revised: AC1 col-3 restatement; AC2 PMS wire confirmation; AC3 unlabelled TC recovery.

---

## Column key

| Column | Meaning |
|--------|---------|
| **Test exists** | A named pytest class or function carries the TC label (or an equivalent unlabelled test — see AC3) |
| **Test passes** | `pytest tests/ -q` exits green |
| **Code path exercised by demo** | The code implementing the TC's invariant **executes** during at least one of the five seeded scenario runs (determinism gate / test 14-16) — not just "a test uses `build_seeded_store`". Hot path = every `evaluate_tick()` call. `_drive` path = per-tick agent/telemetry/SCADA logic in `RunManager._drive()`. |

> **Why column 3 was restated (AC1):** The original Step 17 counted only 7 TCs whose
> *test code* calls `build_seeded_store`. That is too narrow. The correct question is
> whether the *implementation code* the TC validates runs during any demo scenario.
> The corrected count is **28 labelled TCs** (plus 3 newly-recovered unlabelled ones).
>
> The 20-TC short list at the end of this file is the real finding: these are passing TCs
> whose specific invariant is **not exercised at all by any demo scenario run**.

---

## Code paths that run during every demo scenario tick

| Layer | What runs | Source |
|-------|-----------|--------|
| `evaluate_tick()` hot path | GPU.advance(), CoolingModule.advance(), SolarModule.advance() | every tick |
| `evaluate_tick()` hot path | PreStagingEngine.compute_shift() | demo-prestage only |
| `evaluate_tick()` hot path | PmsModule.tick(), is_fast_shed_active | demo-pms only (but no injection in gate) |
| `evaluate_tick()` hot path | DispatchArbitrator.tick() → select_candidates() | every tick |
| `evaluate_tick()` hot path | bess_bridging_seconds with anchor-reserve deduction | every tick, every demo with BESS |
| `evaluate_tick()` hot path | CurtailmentLadder.generate_candidates() | every tick |
| `evaluate_tick()` hot path | CheckpointClassifier.classify() | every tick |
| `evaluate_tick()` hot path | ConfidenceEngine.band_for() | every tick |
| `evaluate_tick()` hot path | SCADA issue_command (TURBINE + BESS) + deliver_pending() | every tick (turbine/BESS always > 0) |
| `_drive()` per-tick | AgentRegistry.run_all() → DeterministicRouter proposals | every tick |
| `_drive()` per-tick | NetworkTelemetryIngestor.ingest() × 2 records (PTP spine + NTP leaf) | every tick |
| `_drive()` per-tick | FabricCorroborator.ingest_telemetry() | every tick |
| `_drive()` per-tick | corroborator.apply_checkpoint_start() | when job → "running" |

**Not in any demo scenario:** `MaintenanceEngine`, `RampRelaxationEngine`, `ProcurementLayer`
(none of the five seeded scenarios has maintenance_config, ramp_relaxation_config, or
procurement_config).

`check_order_conflict()` is called in evaluate_tick only when `state.pms is not None AND
_curtailment_proposals` is non-empty. demo-pms turbine+BESS covers demand, so no curtailment
proposals are generated and the call never fires.

---

## TC-01 – TC-11: Core formulas and checkpoint classifier

| TC | Description | Test | Passes | Demo path |
|----|-------------|:----:|:------:|:---------:|
| TC-01 | Instantaneous compute term (single profile) | ✅ | ✅ | ✅ |
| TC-02 | Cooling zero before thermal delay | ✅ | ✅ | ✅ |
| TC-03 | Cooling converges to α·max at steady state | ✅ | ✅ | ✅ |
| TC-04 | Mixed-fleet sigma case — equal-share allocation (unlabelled: `test_item4_fleet_covers_shortfall`) | ✅ | ✅ | ✅ |
| TC-05 | Explicit checkpoint event | ✅ | ✅ | ✅ |
| TC-06 | Heuristic positive match | ✅ | ✅ | ✅ |
| TC-07 | Heuristic negative match (job-end) | ✅ | ✅ | ✅ |
| TC-08 | Ambiguous → UNCERTAIN | ✅ | ✅ | ✅ |
| TC-09 | Boundary thresholds inclusive | ✅ | ✅ | ✅ |
| TC-10 | Insufficient reserve — worked example | ✅ | ✅ | ✅ |
| TC-11 | Sufficient reserve — no false alert | ✅ | ✅ | ✅ |

> TC-04 note: `test_item4_fleet_covers_shortfall_above_single_unit_rating` (test_formulas.py)
> tests heterogeneous 3 MW + 7 MW fleet. Demo path: `_capped_equal_share_allocations()`
> runs every tick inside `bess_bridging_seconds` computation.

---

## TC-12 – TC-27: _(deferred)_

| TC | Status |
|----|--------|
| TC-12 – TC-27 | **DEFERRED** — specification section not implemented; no test exists |

---

## TC-28 – TC-35: Agents, advisory gate, clock restart

| TC | Description | Test | Passes | Demo path |
|----|-------------|:----:|:------:|:---------:|
| TC-28 | Endpoint unreachable → no delay | ✅ | ✅ | — |
| TC-29 | No PII (site_id, job_id, SKU) in wire payload | ✅ | ✅ | — |
| TC-30 | Out-of-bounds proposal auto-rejected at gate | ✅ | ✅ | — |
| TC-31 | Unactioned proposals have no dispatch impact | ✅ | ✅ | ✅ |
| TC-32 | Compute-authority ceiling enforced | ✅ | ✅ | ✅ |
| TC-33 | Staging-alert symmetry | ✅ | ✅ | ✅ |
| TC-34 | _(deferred — §17.1 dedupe window not implemented)_ | — | — | — |
| TC-35 | Restart resumes sim clock from persisted tick_seq | ✅ | ✅ | — |

> TC-28: DeterministicRouter bypasses LLM network calls entirely; the endpoint-unreachable
> error path never executes in demo runs.
> TC-29: `deidentify()` is only called at the advisory REST endpoint, not inside
> `evaluate_tick()` or `_drive()`.
> TC-30: gate's `validate()` runs for every DeterministicRouter proposal but all are
> in-bounds; the rejection branch never fires.
> TC-35: no restart happens in any demo scenario run.

---

## TC-36 – TC-40: _(deferred)_

| TC | Status |
|----|--------|
| TC-36 | Restart yields to measured state (deferred Step 10) |
| TC-37 – TC-40 | **DEFERRED** — reserved in `test_api.py` header |

---

## TC-41 – TC-52: Curtailment, arbitration, procurement

| TC | Description | Test | Passes | Demo path |
|----|-------------|:----:|:------:|:---------:|
| TC-41 | Curtailment mandatory ordering | ✅ | ✅ | ✅ |
| TC-42 | Curtailment confirmation required | ✅ | ✅ | ✅ |
| TC-43 | Low-confidence curtailment blocked | ✅ | ✅ | ✅ |
| TC-44 | Curtailment hysteresis / dwell timer | ✅ | ✅ | ✅ |
| TC-45 | _(deferred — no test found)_ | — | — | — |
| TC-46 | Curtailment dead-man check | ✅ | ✅ | ✅ |
| TC-47 | Non-firm spot import does not close reserve gap | ✅ | ✅ | — |
| TC-48 | Bit-identical dispatch trace (agents-enabled) | ✅ | ✅ | ✅ |
| TC-49 | select_candidates deterministic (120 permutations) | ✅ | ✅ | ✅ |
| TC-50 | Fabric rise without WorkloadSignal → FabricFinding only | ✅ | ✅ | — |
| TC-51 | checkpoint_start authoritative; fabric cannot override | ✅ | ✅ | ✅ |
| TC-52 | ReservationProposal.requires_confirmation always True | ✅ | ✅ | — |

> TC-41..TC-44, TC-46: `CurtailmentLadder.generate_candidates()` + dwell/interlock/dead-man
> checks run every tick even when no gap exists — the path executes, producing an empty list.
> TC-47: `ProcurementLayer` is endpoint-only (not in `evaluate_tick` or `_drive`). No demo
> scenario has `procurement_config`. Non-firm import logic never runs.
> TC-48: the dispatch trace IS the output of every demo run; the determinism gate
> explicitly validates it.
> TC-49: `select_candidates()` is called on the K3 live path inside `evaluate_tick` every tick.
> TC-50: `FabricFinding` is emitted only for **unmatched** fabric rises (no registered job).
> Demo runs pre-register jobs from STARTING events; fabric rises are therefore
> corroborated (matched), never unmatched. The FabricFinding path doesn't execute.
> TC-51: `apply_checkpoint_start()` is called in `_drive` when `checkpoint_states[job_id]
> == "running"`. Demo jobs transition through this state.
> TC-52: `ReservationProposal` is procurement-layer only; not reached in any demo tick.

---

## TC-53 – TC-54: _(deferred)_

| TC | Status |
|----|--------|
| TC-53 – TC-54 | **DEFERRED** — no test exists |

---

## TC-55 – TC-68: Pre-staging, calibration, maintenance, PMS/SCADA

| TC | Description | Test | Passes | Demo path |
|----|-------------|:----:|:------:|:---------:|
| TC-55 | Temperature-bound limits pre-staging shift | ✅ | ✅ | ✅ |
| TC-56 | bms_override=False → engine engages | ✅ | ✅ | ✅ |
| TC-57 | Calibration proposal requires confirmation | ✅ | ✅ | ✅ |
| TC-58 | Reserve uses re-rated ramp | ✅ | ✅ | — |
| TC-59 | Maintenance window requires full-duration validation | ✅ | ✅ | — |
| TC-60 | Rating raise always requires confirmation | ✅ | ✅ | — |
| TC-61 | BESS bridging excludes anchor reserve (unlabelled: `test_item4_anchor_unit_contributes_less`) | ✅ | ✅ | ✅ |
| TC-62 | Anchor reserve defaults conservatively non-zero (unlabelled: `test_item4_demo_scenarios_alert`) | ✅ | ✅ | ✅ |
| TC-63 | Checkpoint classifier boundary (explicit path) | ✅ | ✅ | ✅ |
| TC-64 | PMS fast shed blocks curtailment proposals | ✅ | ✅ | — |
| TC-65 | PMS order-conflict detection (no false positives) | ✅ | ✅ | — |
| TC-66 | Fast-shed log records injection for attribution | ✅ | ✅ | — |
| TC-67 | Open-transition raises dispatch requirement | ✅ | ✅ | — |
| TC-68 | Zero protection commands in egress log | ✅ | ✅ | ✅ |

> TC-55, TC-56: `PreStagingEngine.compute_shift()` runs every tick in demo-prestage.
> TC-57: `DeterministicRouter._KIND_MAP['calibration'] = ('calibration', None, True)` — the
> CalibrationAgent fires a proposal with `requires_confirmation=True` every tick. TC-57's
> invariant is exercised on every demo run with agents active.
> TC-58..TC-60: no demo scenario has `maintenance_config`. `MaintenanceEngine` is never
> instantiated.
> TC-61/TC-62 (unlabelled): `bridging_available_mw()` deducts `p_anchor_reserve_mw`
> from the BESS's available ceiling on every `bess_bridging_seconds` computation — every
> tick, every demo with BESS units. TC-61 confirmed by
> `test_item4_anchor_unit_contributes_less_bridging_than_grid_following` (PASSED).
> TC-62 confirmed by `test_item4_demo_scenarios_alert_behavior` (PASSED, `p_anchor_reserve=1 MW`).
> TC-64: `_pms_shed_active` is False without injection; the curtailment-bypass branch at
> line 239 of `evaluate_tick` never fires in a gate run. Covered by test 15 (injection-based).
> TC-65: `check_order_conflict()` is guarded by `state.pms is not None AND
> _curtailment_proposals`; demo-pms turbine+BESS covers demand, so curtailment proposals
> are empty and the call never fires.
> TC-64..TC-67: covered by `test_step16_wiring.py` test 15 (manual injection, col-3).
> TC-68: `TURBINE_SETPOINT` and `BESS_DISPATCH` commands issued every tick;
> `deliver_pending()` runs every tick. Protection commands never appear. Invariant
> trivially holds — but it IS exercised.

---

## TC-69 – TC-76: Network telemetry and ramp relaxation

| TC | Description | Test | Passes | Demo path |
|----|-------------|:----:|:------:|:---------:|
| TC-69 | Cross-source correlation window = max(bound_a, bound_b) | ✅ | ✅ | ✅ |
| TC-70 | Declared PTP + \|skew\| > 2 ms → effective discipline = NTP | ✅ | ✅ | — |
| TC-71 | BASELINE tier degrades roles but not ingestion | ✅ | ✅ | — |
| TC-72 | Optical power outside [-40, +10] dBm → quarantined | ✅ | ✅ | — |
| TC-73 | Fabric corroboration does NOT increment reconciliation_count | ✅ | ✅ | ✅ |
| TC-74 | NetworkTelemetry in dispatch path → NetworkTelemetryDispatchError | ✅ | ✅ | — |
| TC-75 | Relaxation requires upper-bound reserve check to pass | ✅ | ✅ | — |
| TC-76 | GridSignal loss lapses relaxation to baseline policy | ✅ | ✅ | — |

> Synthetic telemetry (per `_ingest_synthetic_telemetry`): spine = PTP, skew=0.4 ms (< 2 ms
> threshold, **not** demoted); leaf = NTP, skew=320 ms. Optical power: spine tx=−3.2 dBm,
> spine rx=−5.1 dBm, leaf tx=−6.0 dBm, leaf rx=−8.2 dBm (all within [−40, +10] dBm).
> TC-69: spine (PTP, bound=1000 ms) + leaf (NTP, bound=2000 ms) → correlation window =
> max(1000, 2000) = 2000 ms. Computed every tick. ✅
> TC-70: demotion requires |skew| > 2 ms. Synthetic spine skew=0.4 ms — demotion branch
> never fires.
> TC-71: synthetic records use ENHANCED tier (not BASELINE). BASELINE degradation code
> never runs.
> TC-72: all synthetic optical power values are in-range. Quarantine branch never fires.
> TC-73: fabric records ingested every tick; FabricCorroborator never increments
> `reconciliation_count` for fabric traffic. Invariant exercised.
> TC-74: routing NetworkTelemetry to dispatch path raises `NetworkTelemetryDispatchError`
> — this path is never triggered in normal operation.
> TC-75, TC-76: no demo scenario has `ramp_relaxation_config`. `RampRelaxationEngine`
> is never instantiated.

---

## Summary

| Category | Count |
|----------|------:|
| TCs with labelled tests (passing) | **48** |
| TCs covered by unlabelled tests — TC-04, TC-61, TC-62 (passing) | **3** |
| **Total confirmed covered** | **51** |
| Of those 51, code path executed by at least one demo scenario | **31** |
| Of those 51, code path NOT executed by any demo scenario | **20** |
| Deferred / no test at all | **25** |
| **Total in spec (TC-01 – TC-76)** | **76** |

---

## Short list: 20 TCs that pass but no demo scenario reaches

These are the actual risk items. A bug in their implementation would not be caught by
running `scripts/determinism_gate.py` or any demo scenario end-to-end.

| TC | Why the demo path doesn't reach it |
|----|-------------------------------------|
| TC-28 | DeterministicRouter bypasses LLM endpoint; unreachable-endpoint error path never fires |
| TC-29 | `deidentify()` only called at REST endpoint, not in tick loop |
| TC-30 | Gate only sees in-bounds proposals from DeterministicRouter; rejection branch never fires |
| TC-35 | Persistence restart: no demo run invokes the restart path |
| TC-47 | `ProcurementLayer` is endpoint-only; no demo has `procurement_config` |
| TC-50 | FabricFinding requires **no registered job**; demo runs pre-register via STARTING events |
| TC-52 | `ReservationProposal` only created at procurement endpoint; not in tick loop |
| TC-58 | No demo has `maintenance_config`; `MaintenanceEngine` never instantiated |
| TC-59 | Same as TC-58 |
| TC-60 | Same as TC-58 |
| TC-64 | PMS fast-shed interlock (`_pms_shed_active` check) requires injection; gate injects nothing |
| TC-65 | `check_order_conflict()` requires `_curtailment_proposals` non-empty; demo-pms covers demand with turbine+BESS |
| TC-66 | Fast-shed log requires injection; gate injects nothing |
| TC-67 | Open-transition gap requires injection; gate injects nothing |
| TC-70 | Synthetic PTP skew = 0.4 ms < 2 ms threshold; demotion branch never fires |
| TC-71 | Synthetic telemetry is ENHANCED tier; BASELINE degradation code never runs |
| TC-72 | Synthetic optical power in [−40, +10] dBm; quarantine branch never fires |
| TC-74 | NetworkTelemetry-to-dispatch routing is a contract error; never triggered in normal operation |
| TC-75 | No demo has `ramp_relaxation_config`; `RampRelaxationEngine` never instantiated |
| TC-76 | Same as TC-75 |

---

## Deferred TC list (25)

TC-12–TC-27, TC-34, TC-36–TC-40, TC-45, TC-53–TC-54

---

## Eight CI gates

| # | Name | File / command | Trigger |
|---|------|----------------|---------|
| 1 | Unit suite | `pytest tests/ -q` | Every push/PR |
| 2 | Plane separation | `tests/test_plane_separation.py` | Every push/PR |
| 3 | TC-29 no-PII | `TestTC29NoPII` | Every push/PR |
| 4 | TC-68 egress | `TestTC68NoProtectionCommands` | Every push/PR |
| 5 | Verdict acceptance | `tests/test_verdicts.py` | Every push/PR |
| 6 | Load / NFR | `scripts/load_test.py` | On changes to `core/`, `runtime/`, `advisory/` |
| 7 | Determinism | `scripts/determinism_gate.py` | Every push/PR |
| 8 | Shipped-scenario smoke | `test_step16_wiring.py` tests 14–16 + `test_f2_bridging_basis.py` | Every push/PR |

---

## AC2 — demo-pms PMS wiring confirmation

`demo-pms state.pms = <core.scada_layer.SimulatedPMS object>` — PMS is correctly wired.
`demo-20mw state.pms = None` — as expected.

**Why demo-pms and demo-20mw hash identically in the determinism gate:**

The gate runs the tick loop without injection. `state.pms.tick(sim_time, dt)` returns
`(0.0, 0.0)` for `(shed_mw, transition_gap_mw)` when no `inject_fast_shed()` or
`inject_transition()` has been called. Therefore `_pms_shed_active = False`,
`_transition_gap_mw = 0.0`, and `p_dispatch_required_mw` is identical to demo-20mw's.
turbine + BESS dispatch is therefore identical → same hash.

**Coverage:** The PMS injection path (TC-64, TC-66, TC-67) is covered by
`test_step16_wiring.py` test 15 (manual tick loop with `inject_fast_shed()` and
`inject_transition()` at specified sim_times), not by the determinism gate.
