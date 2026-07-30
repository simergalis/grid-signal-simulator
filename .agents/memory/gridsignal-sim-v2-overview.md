---
name: gridsignal-sim v2 overview
description: Location, four verification commands, and status of all completed items in the gridsignal_sim_v2 build.
---

**Codebase root:**
`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/`

**Frontend root:**
`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/`
(standalone Vite/React app; proxies /runs and /ws/* to uvicorn on port 8000)

**Four verification commands (run from codebase root with PYTHONPATH=.):**
1. `python -m pytest tests/ -v`
2. `python -m pytest ../audit_tests/ -v`
3. `python runtime/example_usage.py`
4. `python scripts/load_test.py --matrix`

**Frontend typecheck (from frontend/):**
`node_modules/.bin/tsc -p tsconfig.json --noEmit`

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
- Step 5 — SimClock + two clock domains (see clock-domains.md)
- Step 6 — FastAPI wiring (see fastapi-wiring.md)
- Q5 — Static gate extended to api/ (see fastapi-wiring.md)
- C1 — bess_bridging_seconds in TickResult (from max_sustainable_seconds, not MW/MW ratio); fleet = min()
- C2 — dt_lead_next_s = min() across in-flight ramp remaining times (not sum()); field named _next_s
- Step 7 — p_renewable_mw, bess_bridging_seconds, dt_lead_next_s in TickResult + WS payload;
           back-pressure _SEND_TIMEOUT_S=0.25 in _safe_send; frontend at ../frontend/

**Audit gate status:** 13/13 passing (all closed)

**Test counts:** 78 unit tests (tests/), 13 audit tests (audit_tests/)

**Demo scenario alerts_seen (stable):**
- demo-20mw: False, demo-alert: True, demo-5mw: False, demo-baseline: False

**Performance (1x load test — 100 GPU / 16 turbine / 8 BESS / 8 solar):**
- compute p50: 1886.6 µs  ← evaluate_tick() hot path only
- delivery p50: 4.010 ms  ← compute + sink.append + broadcast
- NOTE: the Step 6 "844 µs" was compute p50 from the demo-20mw micro-scenario (1 turbine, 1 BESS);
  the Q5 "2.1 ms" was compute p50 from the full 1x load test (100 GPU). Different scenario sizes,
  not a regression. Static gate runs at test-collection time, does not touch the hot path.
- 2x: compute p50 ~3700 µs, wall clock 58 s — FAIL (pre-existing 4h-wall-clock NFR)
- 4x: FAIL (pre-existing, out of scope)

**Step 7 known boundaries (document in code):**
- Back-pressure drop: subscriber removed after _SEND_TIMEOUT_S; no auto-recovery until Step 8 resync
- Alert acknowledge: local (Zustand) only; POST /api/alerts/{id}/acknowledge deferred to Step 8
- Turbine rated capacity not in tick payload; AssetReservePanel shows current output only (Step 8)
- No snapshot-on-connect / WS resync protocol (Step 8)
