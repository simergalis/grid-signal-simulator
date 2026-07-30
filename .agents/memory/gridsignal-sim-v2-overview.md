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
- PROTO-8 — example_usage.py config corrections (demo-20mw bess 15MW/8MWh, demo-alert 2.5MWh)
- Step 3 Item 1 — GPUModule.per_job_compute_mw() substrate; evaluate_tick step 5 uses per-job draw
- Step 3 Item 2 — GPUModule ramp (ramp_seconds=45s, piecewise PROTO-1 curve, advance() updates progress)
- Step 3 Item 3 — CoolingModule per-job superposition (_LoadEnvelope, simulation/scalar paths, retention rule)
- P1 — deque + absolute cursor for O(1) lagged-sample lookup in CoolingModule
- P2 — three new Item 3 tests (concurrent rise, job-end persistence, cursor corruption)
- P3 — retention rule explicit: envelope retained dt_thermal + 5τ after end_t; load_mw never zeroed on close
- Step 3 Item 4 — BESS fleet split, anchor constraint, reserve aggregation (see bess-anchor-reserve.md)

**Audit gate status after Step 3 Item 4:** 13/13 passing (all closed)

**Test counts:** 39 unit tests (tests/), 13 audit tests (audit_tests/)

**Demo scenario alerts_seen (stable):**
- demo-20mw: False, demo-alert: True, demo-5mw: False, demo-baseline: False

**Performance (post-Item-4):**
- 1x: ~15 s wall, p50 ~950 µs — PASS
- 2x: ~30 s wall, p50 ~1890 µs — PASS (close to 30s budget, watch)
- 4x: FAIL (pre-existing, out of scope)
