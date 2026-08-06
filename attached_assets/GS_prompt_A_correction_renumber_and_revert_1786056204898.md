# Correction — renumber, revert, and restart at Phase A as specified

**Supersedes:** the session reported as "Phase A / Phase B" and follow-up tasks #222, #223, #224.
**Baseline to return to:** 12 failed, 965 passed, 974 collected, 0 errors from canonical CWD `gridsignal_sim/`.
**Target model:** `backend/core/` — the live engine. **Not** `gridsignal_logger.py`.

The two tests written in that session were useful and the sequential-start finding is real. Three things went wrong around them, and all three compound if the next session builds on this state.

---

## What went wrong

**The phase labels do not match the prompt.** The prompt's Phase A is *"structures, zero behaviour change"* — `CommitmentConfig`, `SustainedCondition`, `PendingStartRegister`, `core/commitment.py`, every threshold catalogued, nothing wired, **suite delta exactly zero**. Phase B is *"interval ordering and a real write guard"*. The session instead wrote two tests and changed `_stage_for_predicted_step` — a targeted fix to defect **1** in the "What is wrong now" list, which is Phase D work.

Everything downstream shifted by one. #222 labelled Phase C is P0 fixes plus `is_synchronised` reclassification; #223 labelled Phase D is the D-05 rename; #224 is Phase E. The write guard and the commitment engine dropped out of the sequence entirely.

**TC-87 and TC-88 are assigned.** TC-87 is *"output at interval n equals the accumulated integral, independent of the setpoint trajectory"*; TC-88 is *"a unit promoted during `advance()` is not loaded in the interval of its promotion."* Both are Phase B. The sequential-start tests need different numbers.

**The change discards the commitment count.** `_offline[0].stage_target(_eff_delta, sim_time)` stages **one unit against the entire delta**. For an 80 MW step against 25 MW units, that unit is commanded to a target it cannot reach and nothing commands the second, third or fourth. The headroom check may eventually stage more — reactively, at 80% measured utilisation, which is the trigger §7.1.3.3 exists to replace.

DR-2026-08-06 sets the count from forecast ΔP plus the largest-unit reserve; sequencing governs *when each command issues*, never *how many are needed*. This fixed simultaneity by deleting the count. It is also the same shape as the very first change in this project, reverted in Phase 0 for exactly this reason.

---

## Item 1 — Revert the dispatch change

Restore `_stage_for_predicted_step` in `core/dispatch.py` to the `_n_start = min(max(1, ceil(delta / rated) + 1), len(_offline))` form. It is wrong — it is the defect that opened this work — but it is wrong in a way Phase D replaces wholesale, and leaving a half-fix in place contaminates the Phase A zero-delta gate.

Restore `test_tc84f`'s original assertion. See Item 3.

**Gate: suite back to 12 / 965 / 974 / 0 exactly.**

## Item 2 — Renumber and keep the two tests

The tests are good. Move them to **TC-89** and **TC-90**, which the prompt reserves for Phase D sequencing, and leave TC-87 and TC-88 free for Phase B.

They will fail after the Item 1 revert. That is correct — they encode Phase D behaviour that does not exist yet. Mark them `xfail` with a reason naming Phase D, or hold them uncommitted until Phase D. State which you chose.

**Add a third case, and expect it to fail even after the eventual fix.**

The session concluded:

> No same-tick double-start possible: the headroom check guards on `_sync_rated_mw > 0` counting only SYNCHRONISED units — a freshly-RAMPING unit is excluded, so the guard fails and the check cannot fire in the same tick. No additional guard needed.

That holds only when the fleet is **entirely offline**. With one unit already SYNCHRONISED — the normal case, and the case in the 5→80 MW scenario — `_sync_rated_mw > 0` is satisfied, `_stage_for_predicted_step` stages a unit, and the headroom check can stage a **second on the same tick**, because nothing records that a start command was already issued.

Both existing tests start from an all-offline fleet, so neither would catch it. Add **TC-91**: one unit already SYNCHRONISED, demand rising, assert at most one OFFLINE → non-OFFLINE transition per tick. Report whether it fails today.

That is what `PendingStartRegister` exists for, and it is in Phase A precisely so this cannot happen. Do not conclude a guard is unnecessary from the case where it happens to be unreachable.

## Item 3 — `test_tc84f` is a finding, not a stale assertion

The reasoning was right: sequential starts genuinely produce `COVERED_WITH_SHED` during the ramp-in window. That is a real operational property — with sequential commitment the fleet is below N−1 coverage for the duration of a start.

Relaxing the assertion to "must not be `CANNOT_CARRY`" records that as acceptable without anyone deciding it, and discards the information. §7.1.3.8 already states that degradation during commitment is expected and **shall be surfaced rather than suppressed**.

Restore the original assertion for now. When Phase D lands, the assertion should encode the **bounded window** — that coverage degrades, for no longer than one start sequence, and recovers — not merely that the worst case was avoided.

Report the measured duration of the degraded window so §7.1.3.8 can state a bound.

## Item 4 — Then do Phase A as specified

`CommitmentConfig`, `SustainedCondition`, `PendingStartRegister`, `CommitmentDecision`, and `core/commitment.py` with `evaluate_commitment()`. **Nothing wired. No call sites.**

Every threshold goes in `gridsignal_parameters.json` with `CHOSEN` provenance and `spec_ref` to §7.1.3.3, read through `core.site_parameters` — not as dataclass literals, which would trip Guard D1 the moment anyone catalogues them: `commit_utilisation` 0.80, `decommit_utilisation` 0.50, `decommit_post_removal_max` 0.70, `commit_confirm_s` 30, `decommit_confirm_s` 300, `inter_start_settle_s` 60, `levelled_off_epsilon_mw` 0.05, `levelled_off_window_s` 10.

`evaluate_commitment()` takes `UnitAvailability` snapshots, never live `TurbineModule` objects. No I/O, no wall clock, no RNG, mutating nothing but the two `SustainedCondition` arguments.

**Gate: suite delta exactly zero against 12 / 965 / 974 / 0, excluding the deliberately-failing or xfailed TC-89/90/91. Guard D1 green with the eight new entries.**

## Item 5 — Restate the task sequence

Recreate the follow-up tasks against the prompt's phase letters, not the shifted ones:

- **Phase B** — interval-entry snapshot, `begin_interval()`, write counter raising `RuntimeError`; TC-87, TC-88.
- **Phase C** — delete the legacy RAMPING path, `stage_target()`, `_target_mw`; add `UNLOADING`; rename `is_synchronised` → `is_on_bus` plus `contributes_to_reserve`; persisted-state migration; fix `test_tc_p0_1/2/3/5`.
- **Phase D** — `evaluate_commitment()` wired, reserve floor, sequential starts, cold-start bypass removed, `hot_start_s` 60 → 300; TC-89 … TC-93.
- **Phase E** — stop sequencing, sequential stops, sequential base-loading, MSL and dwell defaults enabled; TC-94 … TC-97.

The D-05 payload rename belongs in **Phase C**, with the state changes that make it necessary — not as a phase of its own.

---

## Prohibited

- Leaving the `_stage_for_predicted_step` change in place through Phase A.
- Using TC-87 or TC-88 for anything other than the Phase B tests.
- Wiring `evaluate_commitment()` in Phase A.
- Writing any commitment threshold as a code literal.
- Editing any test assertion or fixture, except `test_tc_p0_1/2/3/5` in Phase C.
- Concluding a guard is unnecessary from a case where it is unreachable.
- Staging one unit against a whole delta. The count comes from forecast ΔP plus largest-unit reserve.
- Modifying `gridsignal_logger.py`.
- Proceeding past a phase gate without reporting.

## Acceptance criteria

- [ ] `_stage_for_predicted_step` reverted; `test_tc84f` assertion restored; suite exactly 12 / 965 / 974 / 0.
- [ ] Sequential-start tests renumbered TC-89 and TC-90; disposition (xfail or held) stated.
- [ ] TC-91 added with one unit already SYNCHRONISED; result today reported.
- [ ] Degraded-N−1 window duration measured and reported for §7.1.3.8.
- [ ] Phase A structures added; **nothing wired**; no call site to `evaluate_commitment()`.
- [ ] Eight commitment thresholds catalogued with `CHOSEN` provenance and `spec_ref`; read through `site_parameters`.
- [ ] Phase A suite delta exactly zero, excluding TC-89/90/91.
- [ ] Guards D1, D2, E Tier 1 green; TypeScript `--noEmit` clean.
- [ ] Follow-up tasks recreated against the prompt's phase letters, with the D-05 rename in Phase C.
