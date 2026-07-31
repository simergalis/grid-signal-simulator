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
3. `PYTHONPATH=. python runtime/example_usage.py`   ← must run from codebase root with PYTHONPATH set
4. `PYTHONPATH=. python scripts/load_test.py`

**Frontend typecheck (from frontend/):**
`node_modules/.bin/tsc -p tsconfig.json --noEmit`

**Items completed through Step 11:**
- D11 — BessModule.max_sustainable_seconds() power ceiling (returns 0.0 when discharge > rated)
- PROTO-8 — example_usage.py config corrections (demo-20mw bess 18MW/8MWh after P5; demo-alert 2.5MWh)
- Step 3 Items 1-4 — GPUModule, ramp, CoolingModule, BESS fleet split/anchor/reserve aggregation
- P1-P5 — deque cursor, test coverage, bridging ceilings hoisted, demo-20mw BESS resize
- Step 4 — control-plane purity gate
- Step 5 — SimClock + two clock domains
- Step 6 — FastAPI wiring; Q5 static gate extended to api/
- C1/C2 — bess_bridging_seconds (fleet=min()), dt_lead_next_s (min() across in-flight ramps)
- Step 7 — p_renewable_mw, bess_bridging_seconds, dt_lead_next_s in TickResult + WS payload
- Step 8 — SimClock snapshots, WS resync, alert acknowledge
- Step 9 — AssertionSpec verdicts, demo-20mw gates, H1 gap rules
- Step 10 — §26.4 dispatch arbitration: CandidateResponse, LadderPosition, OperatingTier,
             select_candidates() TC-49 total order, CurtailmentLadder with dead-man/dwell/
             restoration, PreStagingEngine, InsufficientReserveAlert
- Step 11 — K1/K2/K3 unified §26.4 pool live path; SCADA + PMS (§28):
             DispatchArbitrator.tick() → 3-tuple + CandidateResponse;
             CurtailmentLadder.generate_candidates() (K2 operating_tier branching);
             tick() thin wrapper; SimulatedScadaLayer + SimulatedPMS in core/scada_layer.py;
             TransitionMode + PmsConfig in models.py; evaluate_tick unified pool path;
             TC-49 live path, TC-64/65/66/67/68 all tested.

**Audit gate status:** 13/13 passing (all closed)

**Test counts:** 217 pytest (tests/ + audit_tests/), 19 vitest

**Demo scenario alerts_seen (stable):**
- demo-20mw: False, demo-alert: True, demo-5mw: False, demo-baseline: False

**Step 12 added:**
- core/deident.py (EvidenceWindow, deidentify(), assert_no_pii() — TC-29 egress filter)
- runtime/advisory_gate.py (AdvisoryGate, Proposal, ProposalState, make_proposal — TC-30 + lifecycle)
- runtime/advisory_router.py (AdvisoryRouter, LP-1 short-circuit, Mistral/Anthropic HTTP calls)
- runtime/advisory_principal.py (AdvisoryPrincipal, orchestration, tick() expiry loop)
- tests/test_step12_advisory.py (43 new tests: TC-29, TC-30, LP-1, hold questions, structure)

**Gate baseline at Step 12 completion:**
- pytest: 217 passed
- plane separation: CLEAN (9 core/ + 7 api/)
- tsc: 0 errors
- vitest: 19/19
- example_usage: 4/4 demos
- load-test 1×: PASS (17.6 s / 30 s budget, p50 compute 1081 µs)
