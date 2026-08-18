---
name: gridsignal-sim-memory
description: Key decisions and traps across GS simulator implementation sessions.
---

- [Spec-2 surplus and inertia](spec2-surplus-inertia.md) — §INV-CURT, §INV-INERTIA, S9 rerun, ScenarioSpec thresholds, F-4 dispatch gap.
- [Phase 2A-7 frequency dynamics](phase2a7-freq-dynamics.md) — UFLS/81U opt-in, governor decoupling, sub-step swing equation, protection_provisional, export gate.
- [Phase 0/1 balance + droop wiring](phase0-phase1-balance-droop.md) — D4 routing-identity finding, attribute name diffs, catalogue keys, site_parameters import needed, gate surface, test delta.
- [Fuel cell dispatch wiring](fuel-cell-dispatch-wiring.md) — _sync_ceiling_mw must include FC rated MW or FC never dispatches; full wiring checklist + pre-existing test failures.
- [Solar sim capacity mismatch](solar-sim-capacity-mismatch.md) — SolarSim total rated MW ≠ scenario solar_rated_mw; A0 override and C backstop must normalize by ratio or dispatch starves.
- [Payload guard contract](payload-guard-contract.md) — every key added to _tick_result_to_dict() must also be typed in frontend/src/types.ts TickPayload or test_payload_guard fails.
- [Operator profile replay](operator-profile-replay.md) — §4.3 PMSTestDouble has a 3-part gate (grid_authority_tier, non-null profile, pms_shortfall_log stamp); all three must be open or it silently does nothing.
- [SoC corruption dashboard wiring](soc-corruption-dashboard.md) — bess_soc_corrupted_fraction must follow confidence: ConfidenceBand in TickResult (field ordering constraint); corruption stamps both contingency_coverage and the fraction together.
- [PAUSE control-plane](pause-control-plane.md) — asyncio.Event gate in _drive(); §22.3 timer persistence deferred; STOP vs PAUSE semantics.
- [Frontend build + modal naming traps](gridsignal-frontend-build.md) — prod serves pre-built bundle; must run build_prod.sh + restart after any src/ edit. Two overlapping constant sets in GpuNodeGeneratorModal; Queue tab needs component-level TENANT_COLOUR_BY_ID / SCHEDULER_BADGE_BY_TYPE.
- [Hot-standby cascade](hot-standby-cascade.md) — hot-standby turbines are OFFLINE (not SYNCHRONISED); clear config.hot_standby then call command_start(); never look for SYNCHRONISED state.
