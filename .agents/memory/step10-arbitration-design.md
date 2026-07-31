---
name: Step 10 arbitration design
description: Phase 0 insertion point in evaluate_tick, CurtailmentLadder hold analysis, TC-49 permutation trap, OperatingTier and PreStagingConfig patterns.
---

## Phase 0 insertion point in evaluate_tick()

Pre-staging (§8.1) inserts AFTER `p_dispatch_required_mw = max(0, p_total - p_renewable)` (step 3) and BEFORE `state.arbitrator.tick()` (step 4). It reduces the SIZE of the gap before the §26.4 ladder closes it — it is not a rung in the ladder.

The curtailment ladder observation inserts AFTER step 4 (turbine/BESS) using the remaining gap.

## TC-49: test over ALL PERMUTATIONS, not one ordering

`select_candidates()` sorts by (ladder_position ASC, estimated_impact_mw DESC, candidate_id ASC) — a strict total order. Two candidates with the same `response_kind` must have different `candidate_id`s. A dict keyed by `response_kind` silently drops one when two agents publish the same kind. Test with `itertools.permutations` over a 5-candidate set (120 orderings).

## CurtailmentLadder hold analysis (D1/D2/D4 pattern)

- **Bound**: 120 s dwell (`DWELL_BEFORE_ESCALATION_S`) + 300 s dead-man (`MAX_HOLD_S`) + 20% restoration margin
- **Terminal**: gap drops to ≤80% of trigger gap → reset; OR dead-man fires
- **No-release**: dead-man auto-releases after `MAX_HOLD_S`, logs control anomaly

## PreStagingEngine hold analysis

- **Bound**: `inlet_temp_low_c` — physics caps shift to 0.0 as temp approaches lower bound
- **Terminal**: temperature reaches lower bound; BMS override; gap closes
- **No-release**: temperature bound IS the hard cap; no separate dead-man needed

## TC-42: C/D requires_confirmation is set at tier construction

`_REQUIRES_CONFIRMATION[C_SUSPEND] = True`, `_REQUIRES_CONFIRMATION[D_PREEMPT] = True`. This is independent of `OperatingTier`. There is no tier setting that makes C/D autonomous.

## TC-43: low_confidence resets the dwell timer

When `is_low_confidence=True`, `CurtailmentLadder.tick()` calls `_reset()` AND returns `[]`. This means a low_confidence tick during mid-dwell resets the 120 s timer; after confidence restores, a full fresh dwell is required.

## OperatingTier and PreStagingConfig follow IslandMode pattern

Both are fields on `SiteConfig` (like `island_mode`), read each tick by the ladder/engine. `OperatingTier` defaults to `SUPERVISED` (conservative). `PreStagingConfig` is `Optional[PreStagingConfig]` defaulting to `None` (no pre-staging unless explicitly configured). Full machinery deferred to later steps.

## Gate baseline after Step 10

180 pytest (148 prior + 32 new from test_step10_arbitration.py), plane separation clean (8 core/ + 7 api/), tsc 0 errors, vitest 19/19, example_usage 4/4, load_test 1x PASS (16.6s / 30s budget).
