---
name: gridsignal-sim v2 overview
description: Location, four verification commands, and status of all completed items in the gridsignal_sim_v2 build.
---

**Codebase root:**
`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/`

**Four verification commands (run from codebase root with PYTHONPATH=.):**
1. `python -m pytest tests/ -v`
2. `python -m pytest ../audit_tests/ -v`
3. `python runtime/example_usage.py`
4. `python scripts/load_test.py --matrix`

**Items completed:**
- D11 — BessModule.max_sustainable_seconds() power ceiling (returns 0.0 when discharge > rated)
- PROTO-8 — example_usage.py config corrections (demo-20mw bess 18MW/8MWh after P5; demo-alert 2.5MWh)
- Step 3 Item 1 — GPUModule.per_job_compute_mw() substrate; evaluate_tick step 5 uses per-job draw
- Step 3 Item 2 — GPUModule ramp (ramp_seconds=45s, piecewise PROTO-1 curve, advance() updates progress)
- Step 3 Item 3 — CoolingModule per-job superposition (_LoadEnvelope, simulation/scalar paths, retention rule)
- P1 — deque + absolute cursor for O(1) lagged-sample lookup in CoolingModule
- P2 — three new Item 3 tests (concurrent rise, job-end persistence, cursor corruption)
- P3 — retention rule explicit: envelope retained dt_thermal + 5τ after end_t; load_mw never zeroed on close
- Step 3 Item 4 — BESS fleet split, anchor constraint, reserve aggregation (see bess-anchor-reserve.md)
- D13 — reserve aggregation: min() not sum(); see bess-anchor-reserve.md for counter-example and why
- P4 — hoist island_mode + bridging ceilings once per tick; cover_shortfall takes power_ceiling_mw
- P5 — demo-20mw BESS resized 15→18 MW; bridging 17 MW; 21.7% margin over ~13.97 MW shortfall
- Step 4 — control-plane purity gate (see plane-separation-guard.md)

**Audit gate status:** 13/13 passing (all closed)

**Test counts:** 50 unit tests (tests/), 13 audit tests (audit_tests/)

**Demo scenario alerts_seen (stable):**
- demo-20mw: False, demo-alert: True, demo-5mw: False, demo-baseline: False

**Performance (post-D13/P4):**
- 1x: 13.7 s wall, p50 842 µs — PASS (was 948 µs; −106 µs)
- 2x: 27.5 s wall, p50 1740 µs — PASS (was 1893 µs; 2.5 s headroom to 30 s)
- 4x: FAIL (pre-existing, out of scope)
