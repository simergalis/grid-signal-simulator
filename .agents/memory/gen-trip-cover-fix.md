---
name: Gen-trip cover fix (GT-1 / GT-2 / GT-3)
description: D-1 quantitative readout, D-2 dispatchable fix, D-3 demo fleet reconfiguration — §7.4/§7.5.
---

# Gen-trip cover fix

## Key design decisions

**D-1: ContingencyCoverage split across two files to avoid circular import**
- `core/models.py`: `ContingencyState` enum + `ContingencyCoverage` frozen dataclass (needed by TickResult)
- `core/contingency.py`: `TurbineSnapshot`, `BessSnapshot`, `PlantState` input structs + `evaluate_contingency()` pure function
- `simulation_core.py` imports from both; `models.py` does NOT import from `contingency.py`

**D-2: dispatchable_mw = online turbine RATED (not output) + anchor-adj BESS bridging**
- Solar is excluded entirely — never credited toward coverage or dispatchable
- Anchor deduction applies only when `grid_forming=True AND island_mode=ISLANDED`
- In GRID_TIE mode, anchor deduction is zero regardless of grid_forming

**D-3: demo-20mw reconfigured to 5×7 MW fleet**
- turbine-0..3: synchronized online; turbine-4: `hot_standby=True`
- BESS unchanged: 18 MW / 8 MWh, grid-forming, p_anchor_reserve=1 MW
- Steady-state each turbine @6 MW → COVERED_WITH_SHED (shed 3 MW ≤ 37 MW curtailable)
- Early ramp each @1 MW → COVERED; natural transition visible on screen

**D-4: hot_standby in TurbineConfig**
- `hot_standby: bool = False` on `TurbineConfig` (models.py)
- `TurbineModule.stage_target()` returns early if `self.config.hot_standby`
- `is_synchronized = (state != TurbineState.OFFLINE)` — hot standby units stay OFFLINE, contribute zero to r_surviving and dispatchable_mw

**D-5: Insertion point in simulation_core.py**
- contingency computed AFTER dispatch arbitration + SCADA, BEFORE checkpoint classification (step 5)
- Keyword used in search: `# 5. Checkpoint classification`

**D-6: CurtailmentLadder.total_capacity_mw()**
- New method returns `sum(_TIER_CAPACITY_MW.values())` = 37 MW (A=2,B=5,C=10,D=20)
- Called in simulation_core.py to build PlantState.curtailable_capacity_mw

**D-7: VerdictBand gen-trip tile**
- COVERED:           teal  "covered · X.X MW · closes in Ys"
- COVERED_WITH_SHED: amber "X.X MW shed · Ys ride-through"
- CANNOT_CARRY:      red   "X.X MW uncov · Ys ride-through"
- TC-84 transition logging via useRef + useEffect on `contingency_coverage.state`
- Renewable (non-firm) tile replaces Δt_lead in hasRun branch

## Why
- D-1 circular import: TickResult is in models.py; if PlantState were also there, models.py would need TurbineState from asset_modules creating a cycle.
- D-3 N-1 was zero by construction with single 20 MW turbine — not a useful demo.

## How to apply
- Any future TickResult field additions: add to `core/models.py` TickResult dataclass + `_tick_result_to_dict()` in `run_manager.py`
- Any future contingency changes: touch `core/contingency.py` only; models.py shape is stable
