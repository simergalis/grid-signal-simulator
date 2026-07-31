---
name: Step 11 SCADA + PMS design
description: K1/K2/K3 unified pool wiring, generate_candidates() authoritative path, TC-64–TC-68 patterns, and design constraints.
---

**K1 — DispatchArbitrator.tick() returns 3-tuple**
`(turbine_mw, bess_mw, list[CandidateResponse])`. BESS at
`LadderPosition.STORAGE_DISCHARGE` (0), turbine at `TURBINE_RAMP` (1). Both
`requires_confirmation=False`. Returns empty list if output ≈ 0.

**K2 — generate_candidates() is the authoritative curtailment live path**
- `CurtailmentLadder.generate_candidates()` returns `list[CandidateResponse]`.
- A/B: `requires_confirmation = (operating_tier != OperatingTier.AUTONOMOUS)`.
- C/D: `requires_confirmation = True` always (TC-42).
- `tick()` is now a thin wrapper: calls `generate_candidates()` and converts.
- **Why:** evaluate_tick calls `generate_candidates()` so the unified pool is
  assembled before `select_candidates()`. Tests that call `tick()` directly still
  work — tick() delegates to generate_candidates() and converts back.
- **THE TRAP:** do NOT call both `generate_candidates()` and `tick()` on the
  same SimulationState in the same tick — both advance dwell timer state once.

**K3 — unified pool in evaluate_tick**
Pool = `_arb_candidates + _curtailment_candidates`; passed to `select_candidates()`.
Pool ordering: STORAGE_DISCHARGE(0) → TURBINE_RAMP(1) → CURTAILMENT_A_B(4) → CURTAILMENT_C_D(5).
`select_candidates()` re-sorts, so insertion order doesn't matter — TC-49 permutation invariance holds.

**TC-64 — PMS fast shed gates curtailment**
`_pms_shed_active = state.pms.is_fast_shed_active` → set before curtailment ladder call.
If True: `_curtailment_candidates = []` (bypass ladder entirely).
Fast shed event already in `pms.fast_shed_log` for TC-66 attribution.

**TC-65 — PMS order conflict detection**
After curtailment proposals built: `state.pms.check_order_conflict(_gs_shed_order)`.
Overlap between GS curtailment response_kind list and PMS shed_priority_order list.
Reversed common prefix → commissioning_defect string. No overlap → None.

**TC-67 — open-transition coverage gap**
`inject_transition()` → `pms.tick()` returns `(0.0, gap_mw)`.
evaluate_tick: `p_dispatch_required_mw += _transition_gap_mw` and `net_demand_mw = p_dispatch_required_mw`.
Gap appears at full magnitude immediately (discontinuity, not ramp).
CLOSED_TRANSITION → zero gap regardless.

**TC-68 — protection commands blocked**
`PROTECTION_COMMANDS` frozenset in scada_layer.py. `issue_command()` raises ValueError for any member.
SimulatedScadaLayer only accepts TURBINE_SETPOINT, BESS_DISPATCH, LOAD_CURTAILMENT, PRE_STAGING.

**SCADA layer design constraints**
- Advisory/attribution only. Asset physics advance synchronously each tick.
- Simulated latency is simulated time (target_sim_time), not wall clock — no threading needed.
- `deliver_pending()` is O(assets) synchronous; called once per tick after all commands issued.
- `seed=42` in SimulationState.__post_init__ for deterministic tests.

**_PROTOCOL_DEFAULTS (§4.6.2)**
MODBUS: latency=1, loss=0.001, max_bytes=256.
DNP3: latency=2, loss=0.005, max_bytes=512.
IEC61850_GOOSE: latency=0, loss=0.0001, max_bytes=1024.
IEC61850_MMS: latency=1, loss=0.002, max_bytes=2048.
GOOSE is zero-latency (relay multicast). MMS has largest messages.
Degraded: effective_loss = min(1.0, base_loss * DEGRADED_FACTOR=10).
