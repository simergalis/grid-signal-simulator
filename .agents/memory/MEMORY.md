---
name: gridsignal-sim-memory
description: Key decisions and traps across GS simulator implementation sessions.
---

- [Spec-2 surplus and inertia](spec2-surplus-inertia.md) — §INV-CURT, §INV-INERTIA, S9 rerun, ScenarioSpec thresholds, F-4 dispatch gap.
- [Phase 2A-7 frequency dynamics](phase2a7-freq-dynamics.md) — UFLS/81U opt-in, governor decoupling, sub-step swing equation, protection_provisional, export gate.
- [Phase 0/1 balance + droop wiring](phase0-phase1-balance-droop.md) — D4 routing-identity finding, attribute name diffs, catalogue keys, site_parameters import needed, gate surface, test delta.
- [Cost-based local dispatch](fuel-cell-dispatch-wiring.md) — rank discretionary BESS, turbine, then fuel cell by catalogue cost; turbine minimum output remains must-run.
- [Solar sim capacity mismatch](solar-sim-capacity-mismatch.md) — SolarSim total rated MW ≠ scenario solar_rated_mw; A0 override and C backstop must normalize by ratio or dispatch starves.
- [Payload guard contract](payload-guard-contract.md) — every key added to _tick_result_to_dict() must also be typed in frontend/src/types.ts TickPayload or test_payload_guard fails.
- [Operator profile replay](operator-profile-replay.md) — §4.3 PMSTestDouble has a 3-part gate (grid_authority_tier, non-null profile, pms_shortfall_log stamp); all three must be open or it silently does nothing.
- [SoC corruption dashboard wiring](soc-corruption-dashboard.md) — bess_soc_corrupted_fraction must follow confidence: ConfidenceBand in TickResult (field ordering constraint); corruption stamps both contingency_coverage and the fraction together.
- [PAUSE control-plane](pause-control-plane.md) — asyncio.Event gate in _drive(); §22.3 timer persistence deferred; STOP vs PAUSE semantics.
- [Frontend build + modal naming traps](gridsignal-frontend-build.md) — prod serves pre-built bundle; must run build_prod.sh + restart after any src/ edit. Two overlapping constant sets in GpuNodeGeneratorModal; Queue tab needs component-level TENANT_COLOUR_BY_ID / SCHEDULER_BADGE_BY_TYPE.
- [Hot-standby release policy](hot-standby-cascade.md) — explicit FC/cascade policies release reserved units; normal commitment must not preempt them.
- [Grid import cap routing](grid-import-cap-routing.md) — PCC import caps clamp only negative exchange; excess deficit stays on frequency_forcing and appears as unserved load.
- [SJ-1 compute target](sj1-compute-target.md) — the mixed fleet’s 16.9632 MW IT sum is deliberately presented as the §2 17.0 MW target; keep IT and PUE-inclusive site demand separate.
- [PUE calibration contract](pue-calibration-contract.md) — pue_base excludes cooling; derive total PUE and validate the runtime base value against the declared catalogue range.
- [BESS escalation semantics](bess-escalation-semantics.md) — bridge-floor and turbine-catch-up are independent; do not redefine legacy reserve-alert verdicts.
- [Additive load validation](additive-load-validation.md) — Kube scenarios need tenant bursts for reliable site-level load injections; scripted job events are not additive there.
- [GPU load multipliers](gpu-load-multipliers.md) — profiles are non-negative demand multipliers; values above 1.0 model planned GPU over-peak demand.
- [BESS-first turbine rundown](bess-first-turbine-rundown.md) — only decommit after physical BESS charge capacity saturates; reserve excludes unloading units.
- [Gridley query catalogue](gridley-query-catalogue.md) — read-only answers use a versioned snapshot-backed catalogue; unknown metrics never default to Energy Flow.
