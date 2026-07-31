---
name: gridsignal-sim-v2 overview
description: codebase root, verification commands, completed work through AD2
---

# GridSignal Simulator v2 — Session overview

## Codebase root
`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/`

## Verification commands
```
PYTHONPATH=. python -m pytest tests/ -q          # 417 passed (Step 17 → AD2)
PYTHONPATH=. python scripts/determinism_gate.py  # 9/9 PASS (5 original + 4 AD1+AD2)
PYTHONPATH=. python scripts/load_test.py         # NFR gate (pre-existing 4h-scale violation)
```

## Test count: 417 (unchanged through AD1+AD2)

## Determinism gate: 9 scenarios
`demo-20mw`, `demo-alert`, `demo-5mw`, `demo-prestage`, `demo-pms` (original 5)
`demo-procurement`, `demo-maintenance`, `demo-ramp-relax`, `demo-pms-shortfall` (AD1+AD2)

## Column-3 count (demo-exercised TCs)
- After AC1–AC3: 31 confirmed
- After AD1+AD2: **39 confirmed** (+8: TC-47, TC-52, TC-58, TC-59, TC-60, TC-65, TC-75, TC-76)
- Short list reduced: 20 → **12** remaining

## Completed milestones
Steps 1–17 (417 tests), AC1–AC3 (matrix corrections), AD1 (3 engine scenarios), AD2 (TC-65 live conflict)
