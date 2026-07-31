---
name: gridsignal-sim-v2 overview
description: Codebase root, verification commands, and completed step status through Step 17 (final).
---

## Codebase root

`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/`

All relative paths below are from that root.

## Four verification commands

```bash
cd .../gridsignal_sim
PYTHONPATH=. python -m pytest tests/ -q          # 417 passed, ~6 s
PYTHONPATH=. python scripts/load_test.py         # NFR gate (≥5 concurrent, <1 s latency, 4 h < 30 s)
PYTHONPATH=. python scripts/determinism_gate.py  # 5/5 seeded scenarios hash-identical
PYTHONPATH=. python scripts/load_test.py --matrix  # 1x/2x/4x headroom sweep
```

## Step status (all complete through Step 17)

- Steps 1–9: formulas, clock, scenarios, verdicts, persistence, arbitration
- Step 10: pre-staging Phase 0 insertion, CurtailmentLadder, OperatingTier
- Step 11: SCADA layer, PMS, K1/K2/K3 unified pool
- Step 12: advisory gate, deidentify(), proposal lifecycle
- Step 13: six buildable agents, DeterministicRouter, TC-48 trace
- Step 14: network telemetry, procurement, TC-69..TC-74 / TC-47 / TC-50..TC-52
- Step 15: maintenance (TC-58..TC-60), ramp relaxation (TC-75..TC-76)
- Step 16: W1/W2/W3 endpoint wiring, 13 tests + 3 new column-3 tests (tests 14–16)
- Step 17 (COMPLETE): 3-column acceptance matrix, 3 new shipped-scenario tests,
  determinism gate script, 8-gate CI workflow, AB2 frontend constants synced

## Suite count history

Steps 1–16: 414 passing → Step 17 adds 3 tests → **417 passing**

## Key invariants to maintain

- `api/ → core/` imports are FORBIDDEN (test_api_gate_clean_api_passes enforces this)
- `wall_stamp_utc` on TickResult is `float` (Unix epoch), NOT datetime — never call .isoformat()
- CostModelEngine bridge lives in `runtime/run_manager.py`, not api/ (plane rule)
- `evaluate_tick()` requires `_EVALUATE_TICK_PERMITTED` ContextVar to be True — use `_guard()` helper or RunManager
- `DeterministicRouter` is selected when `PYTEST_CURRENT_TEST` env var is set
