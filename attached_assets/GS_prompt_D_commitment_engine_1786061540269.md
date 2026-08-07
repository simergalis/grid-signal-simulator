# Phase D — Corrections, then wire the commitment engine

**Follows:** Phase C complete. Legacy path deleted, `UNLOADING` added, predicate renamed, D-05 payload rename landed.
**Current suite:** 42 failed, 937 passed, 3 xfailed, 982 collected.
**Target model:** `backend/core/` — the live engine. **Not** `gridsignal_logger.py`.
**Scope:** Items 1–4 correct Phase C. Items 5–8 are Phase D proper. No Phase E work.

Phase C landed with zero genuine regressions across a 30-test delta, which is the right outcome. Four things need correcting before the commitment engine is wired, because two of them mean an invariant Phase D depends on is currently unverified.

---

## Item 1 — `is_synchronized=(t.state != TurbineState.OFFLINE)` is now wrong

`runtime/run_manager.py`, around line 887. Reported as *"semantics are still correct for its purpose"* and left unchanged. They are not correct after Phase C.

`!= OFFLINE` now includes **STARTING** — a unit up to fifteen minutes from synchronisation, producing nothing, flagged as synchronised. If that snapshot feeds contingency evaluation, committed capacity is credited as available capacity, which is precisely the invariant §7.1.3.7 exists to prevent. It also includes `OUT_OF_SERVICE`, a faulted unit.

It was missed because it is a raw state comparison, not a call to the renamed property — so the name-driven reclassification could not see it. That is worth noting as a limit of the method, not just a one-off miss.

**Before changing it:** report where that snapshot is consumed, in case a downstream consumer depends on the wider set. Then change it to `t.is_on_bus` unless the consumer analysis says otherwise, and say which.

**Also sweep for siblings:** any other raw `t.state ==` / `t.state !=` comparison standing in for an on-bus or reserve predicate. Report every hit with its `file:line` and whether it is still correct under the new state set.

## Item 2 — Guard D1 was not deleted; its status is unreported

The report says *"Guard D1 (`_check_loading_exclusion`) — DELETED per Phase C Item 3."* These are two different things.

`_check_loading_exclusion` is the loading-layer membership check, correctly deleted. **Guard D1** is `test_guard_d1_no_literal_disagrees_with_the_catalogue` in `tests/test_no_hardcoded_parameters.py` — the configuration guard blocking code literals that disagree with `gridsignal_parameters.json`.

Because the two were conflated, nothing in the Phase C report confirms the catalogue guard still passes. Re-run it and report the result explicitly. It should be green; that needs stating rather than inferring.

## Item 3 — Three tests have stale scaffolding, not stale assertions

TC-87, TC-88 and `test_ramping_turbine_ignores_loading_setpoint_drop` are classified as *"correct failures — encoded deleted behaviour."* They did not.

TC-87 and TC-88 were written in Phase B to prove the interval-ordering invariant, and **that invariant did not change in Phase C.** What broke is their setup: they drive units through `stage_target()` and `TurbineState.RAMPING` to reach the state under test. The assertions are still right; the scaffolding no longer compiles.

Leaving them red means Phase C silently discarded the guarantee Phase B established, and Phase D would build on an unverified ordering invariant.

Rewrite all three against `command_start()` and the new state set. **This is fixture repair, not assertion editing** — if you find yourself changing what a test asserts, stop and report instead.

`test_ramping_turbine_ignores_loading_setpoint_drop` is the behavioural discriminator from the earlier dual-writer investigation. Keep it and rename it if the name no longer fits.

This is a distinct class from "assertion encoded old behaviour", and worth carrying in future reports: **stale scaffolding gets repaired; stale assertions get left alone until the phase that makes them right.**

## Item 4 — `TC-P0-4`

It fails on a renamed field — the same fixture repair as `TC-P0-1/2/3/5`, which were fixed under Phase C Item 6. The prompt named four tests and there are five; that was an omission on my part, not a boundary. Fix it.

**Gate for Items 1–4: report the corrected failure count. Expect roughly 36–38, with the remainder legitimately blocked on Items 5–8.**

---

## Item 5 — Wire `evaluate_commitment()`

Replace the headroom block in `core/simulation_core.py` entirely. The commitment decision is computed by the pure evaluator added in Phase A and applied by the caller; decide and apply stay separate, because that separation is what makes the decision unit-testable against constructed fleet states rather than full scenario runs.

**Reserve floor — primary, always binding:**

```
Σ rated over SYNCHRONISED ≥ P_dispatch_required + max(rated over SYNCHRONISED)
```

Demand plus the largest single committed unit. Sizing to demand alone leaves zero spinning reserve and pins the N−1 assessment at CANNOT_CARRY permanently.

**Commit** when the floor is violated, is forecast to be violated within Δt_lead, or `U ≥ commit_utilisation` sustained 30 s.

**Decommit** the last-committed unit only when all hold, sustained 300 s: floor satisfied without it; `U ≤ decommit_utilisation` with it; `U ≤ decommit_post_removal_max` without it; `t_min_run_s` satisfied.

Where the two conflict, **the floor governs.** The 30 s / 300 s asymmetry is normative — starting is a 900-second action, stopping is fast to command and slow to undo, and under §26.4's reliability → reversibility → cost ordering decommitment is the least reversible routine action the system takes.

All eight thresholds come from `site_parameters`, never as literals.

## Item 6 — Sequential starts, and the count

**This is where the count changes.** Phase C preserved `N_needed+1` deliberately. Phase D replaces it: the number of units to commit comes from `evaluate_commitment()` — forecast ΔP plus largest-unit reserve — and sequencing governs *when each command issues*, never how many are needed.

Do not solve simultaneity by staging one unit against a whole delta. That was tried and reverted; it discards the count instead of sequencing it.

- At most one unit in STARTING at any time.
- Next start command no earlier than `inter_start_settle_s` after the previous unit reaches SYNCHRONISED.
- `PendingStartRegister` suppresses duplicate commands. **It carries no capacity semantics** and must never appear in a reserve, headroom or ramp figure.

**Remove the cold-start bypass.** Scenario duration is adjusted in the scenario, not by shortening the start model. Raise `TurbineConfig.hot_start_s` from 60 to 300 (D-08) — a frame machine cannot synchronise in a minute — and move the UI's hardcoded 60 in the same commit, per §U-5 of the modal work.

## Item 7 — TC-89, TC-90, TC-91

They are `xfail(strict=True)`. If Phase D works they will xpass, which under `strict=True` fails the suite — that is the signal. Remove the marker when they pass legitimately, and report the transition explicitly.

TC-91 is the one to watch: one unit already SYNCHRONISED, demand rising, at most one OFFLINE → non-OFFLINE transition per tick. Phase A found it failing because `N_needed+1` staged two units itself. After Item 6 the primary fix is the count; `PendingStartRegister` is the backstop for the case where `_stage_for_predicted_step` and the commitment check could each issue a command in the same tick. **Confirm both mechanisms, not just the count** — a test passing because the count changed says nothing about whether the register works.

Add **TC-92** (reserve floor commits N+1 for a demand N units can serve) and **TC-93** (STARTING contributes zero to reserve, ramp and headroom).

## Item 8 — Re-measure the degraded N−1 window

Two measurements exist and both describe code no longer in the tree:

- Phase A measured **unbounded** — reactive trigger, one unit starting; the 80% threshold never fired at 40% utilisation.
- Phase B measured **5 seconds** — but only because `N_needed+1` started two units simultaneously. The defect was making N−1 look healthy.

Neither is the figure §7.1.3.8 needs. Measure it against proactive commitment with sequential starts and report: time to first COVERED, the degraded window duration, and the COVERED / COVERED_WITH_SHED split over 300 s. Phase B's split was 24 / 36 — 60% of the run below N−1 coverage.

That number becomes the §7.1.3.8 bound. **Report it; do not edit the spec.**

---

## Prohibited

- Changing what any test asserts. Items 3 and 4 are fixture repair only.
- Editing any test assertion or fixture beyond Items 3 and 4.
- Staging one unit against a whole delta.
- Crediting `PendingStartRegister` contents toward any capacity, reserve, headroom or ramp figure.
- Writing any commitment threshold as a code literal.
- Shortening a start time, or bypassing `command_start()`, to fit a scenario duration.
- Any Phase E work: no unload sequence beyond the existing state transition, no sequential stops, no base-loading change, no MSL or dwell default changes.
- Transitioning a loaded unit directly to OFFLINE.
- Editing the spec. Report the Item 8 measurement.
- Adding a module-scope numeric constant to `panels/`.
- Modifying `gridsignal_logger.py`.
- Proceeding past a phase gate without reporting.

## Acceptance criteria

- [ ] Item 1 snapshot consumers reported; predicate corrected; sibling raw-state comparisons swept and reported with `file:line`.
- [ ] Guard D1 re-run and its result reported explicitly, distinct from `_check_loading_exclusion`.
- [ ] TC-87, TC-88 and the ordering discriminator rewritten against the new state set and passing; assertions unchanged.
- [ ] `TC-P0-4` passing.
- [ ] Corrected failure count reported before Items 5–8 begin.
- [ ] `evaluate_commitment()` wired; headroom block removed; decide and apply separate.
- [ ] Commitment count from forecast ΔP plus largest-unit reserve, not from a fixed formula.
- [ ] At most one unit in STARTING at any time in any scenario; settle interval respected.
- [ ] Cold-start bypass removed; `hot_start_s` 60 → 300 with the UI literal moved in the same commit.
- [ ] TC-89, TC-90, TC-91 passing with the xfail marker removed; TC-91 confirmed to exercise both the count and the register.
- [ ] TC-92, TC-93 added and passing.
- [ ] Degraded N−1 window re-measured; time to first COVERED, window duration, and 300 s split all reported.
- [ ] Guards D1, D2, E Tier 1 green; TypeScript `--noEmit` clean.
- [ ] Suite delta reported with every newly failing test classified correct-or-incorrect.
