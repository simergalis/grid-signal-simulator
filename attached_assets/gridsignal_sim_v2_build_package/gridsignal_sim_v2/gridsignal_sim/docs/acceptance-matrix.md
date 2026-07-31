# GridSignal Simulator v2 — Acceptance Matrix (Step 17)

Generated: 2026-07-31

## Column key

| Column | Meaning |
|--------|---------|
| **Test exists** | A named pytest class or function carries the TC label |
| **Test passes** | `pytest tests/ -q` exits green (414+ passing, < 6 s) |
| **Shipped-scenario col-3** | The test reaches the code via `build_seeded_store → build_run_context_from_spec` — not only by direct object construction |

> **Why almost no TC reaches column 3 via direct invocation:** most TCs verify
> correctness of a single class (CurtailmentLadder, SimulatedPMS, …) by
> constructing it in isolation.  Column 3 is satisfied only by tests in
> `test_step16_wiring.py` (tests 14–16) and `test_f2_bridging_basis.py` that
> go through the seeded store path.  This is honest engineering: "covered in
> principle, unexercised end-to-end" is a real risk category.

---

## TC-01 – TC-11: Core formulas and checkpoint classifier

| TC | Description | Test exists | Test passes | Col-3 |
|----|-------------|:-----------:|:-----------:|:-----:|
| TC-01 | Instantaneous compute term (single profile) | ✅ | ✅ | — |
| TC-02 | Cooling zero before thermal delay | ✅ | ✅ | — |
| TC-03 | Cooling converges to α·max at steady state | ✅ | ✅ | — |
| TC-04 | _(reserved — deferred)_ | — | — | — |
| TC-05 | Explicit checkpoint event | ✅ | ✅ | — |
| TC-06 | Heuristic positive match | ✅ | ✅ | — |
| TC-07 | Heuristic negative match (job-end) | ✅ | ✅ | — |
| TC-08 | Ambiguous → UNCERTAIN | ✅ | ✅ | — |
| TC-09 | Boundary thresholds inclusive | ✅ | ✅ | — |
| TC-10 | Insufficient reserve — worked example | ✅ | ✅ | — |
| TC-11 | Sufficient reserve — no false alert | ✅ | ✅ | — |

---

## TC-12 – TC-27: _(deferred — §16.X items without test coverage)_

| TC | Status |
|----|--------|
| TC-12 – TC-27 | **DEFERRED** — specification section not implemented; no test exists |

---

## TC-28 – TC-35: Agents, advisory gate, clock restart

| TC | Description | Test exists | Test passes | Col-3 |
|----|-------------|:-----------:|:-----------:|:-----:|
| TC-28 | Endpoint unreachable → no delay | ✅ | ✅ | — |
| TC-29 | No PII (site_id, job_id, SKU) in wire payload | ✅ | ✅ | — |
| TC-30 | Out-of-bounds proposal auto-rejected at gate | ✅ | ✅ | — |
| TC-31 | Unactioned proposals have no dispatch impact | ✅ | ✅ | — |
| TC-32 | Compute-authority ceiling enforced | ✅ | ✅ | — |
| TC-33 | Staging-alert symmetry | ✅ | ✅ | — |
| TC-34 | _(deferred — §17.1 dedupe window not implemented)_ | — | — | — |
| TC-35 | Restart resumes sim clock from persisted tick_seq | ✅ | ✅ | — |

---

## TC-36 – TC-40: _(deferred — §16.8/§16.9 reserved items)_

| TC | Status |
|----|--------|
| TC-36 | Restart yields to measured state (deferred Step 10) |
| TC-37 – TC-40 | **DEFERRED** — reserved in `test_api.py` header |

---

## TC-41 – TC-52: Curtailment, arbitration, procurement

| TC | Description | Test exists | Test passes | Col-3 |
|----|-------------|:-----------:|:-----------:|:-----:|
| TC-41 | Curtailment mandatory ordering | ✅ | ✅ | — |
| TC-42 | Curtailment confirmation required | ✅ | ✅ | — |
| TC-43 | Low-confidence curtailment blocked | ✅ | ✅ | — |
| TC-44 | Curtailment hysteresis | ✅ | ✅ | — |
| TC-45 | _(deferred — no test found)_ | — | — | — |
| TC-46 | Curtailment dead-man check | ✅ | ✅ | — |
| TC-47 | Non-firm spot import does not close reserve gap | ✅ | ✅ | — |
| TC-48 | Bit-identical dispatch trace (agents-enabled) | ✅ | ✅ | — |
| TC-49 | select_candidates deterministic (120 permutations) | ✅ | ✅ | — |
| TC-50 | Fabric rise without WorkloadSignal → FabricFinding only | ✅ | ✅ | — |
| TC-51 | checkpoint_start authoritative; fabric cannot override | ✅ | ✅ | — |
| TC-52 | ReservationProposal.requires_confirmation always True | ✅ | ✅ | — |

---

## TC-53 – TC-54: _(deferred — no test found)_

| TC | Status |
|----|--------|
| TC-53 – TC-54 | **DEFERRED** — no test exists |

---

## TC-55 – TC-68: Pre-staging, calibration, maintenance, PMS/SCADA

| TC | Description | Test exists | Test passes | Col-3 |
|----|-------------|:-----------:|:-----------:|:-----:|
| TC-55 | Temperature-bound limits pre-staging shift | ✅ | ✅ | ✅ |
| TC-56 | bms_override=False → engine engages | ✅ | ✅ | ✅ |
| TC-57 | Calibration proposal requires confirmation | ✅ | ✅ | — |
| TC-58 | Reserve arithmetic uses re-rated ramp | ✅ | ✅ | — |
| TC-59 | Maintenance window requires full-duration validation | ✅ | ✅ | — |
| TC-60 | Rating raise always requires confirmation | ✅ | ✅ | — |
| TC-61 | _(deferred — no test found)_ | — | — | — |
| TC-62 | _(deferred — no test found)_ | — | — | — |
| TC-63 | Checkpoint classifier boundary (explicit path) | ✅ | ✅ | — |
| TC-64 | PMS fast shed blocks curtailment proposals | ✅ | ✅ | ✅ |
| TC-65 | PMS order-conflict detection (no false positives) | ✅ | ✅ | ✅ |
| TC-66 | Fast-shed log records injection for attribution | ✅ | ✅ | ✅ |
| TC-67 | Open-transition raises dispatch requirement | ✅ | ✅ | ✅ |
| TC-68 | Zero protection commands in egress log | ✅ | ✅ | ✅ |

> **Column-3 source:** `test_step16_wiring.py` tests 14 (demo-prestage) and 15
> (demo-pms) are the first tests to exercise these TCs on the full
> `build_seeded_store → build_run_context_from_spec → evaluate_tick` path.

---

## TC-69 – TC-76: Network telemetry and ramp relaxation

| TC | Description | Test exists | Test passes | Col-3 |
|----|-------------|:-----------:|:-----------:|:-----:|
| TC-69 | Cross-source correlation window = max(bound_a, bound_b) | ✅ | ✅ | — |
| TC-70 | Declared PTP + \|skew\| > 2 ms → effective discipline = NTP | ✅ | ✅ | — |
| TC-71 | BASELINE tier degrades roles but not ingestion | ✅ | ✅ | — |
| TC-72 | Optical power outside [-40, +10] dBm → quarantined | ✅ | ✅ | — |
| TC-73 | Fabric corroboration does NOT increment reconciliation_count | ✅ | ✅ | — |
| TC-74 | NetworkTelemetry in dispatch path → NetworkTelemetryDispatchError | ✅ | ✅ | — |
| TC-75 | Relaxation requires upper-bound reserve check to pass | ✅ | ✅ | — |
| TC-76 | GridSignal loss lapses relaxation to baseline policy | ✅ | ✅ | — |

---

## Summary

| Category | Count |
|----------|------:|
| TCs implemented + passing (cols 1 + 2) | **48** |
| Of those, also shipped-scenario exercised (col 3) | **7** |
| Deferred / no test exists | **28** |
| **Total in spec (TC-01 – TC-76)** | **76** |

### Deferred TC list

TC-04, TC-12–TC-27, TC-34, TC-36–TC-40, TC-45, TC-53–TC-54, TC-61–TC-62

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
