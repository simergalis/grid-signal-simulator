# Phase E — Corrections, test repair, then stop sequencing and the physical constraints

**Follows:** Phase D complete. Commitment engine wired, sequential starts confirmed, zero regressions.
**Current suite:** 38 failed, 946 passed, 982 collected.
**Target model:** `backend/core/` — the live engine. **Not** `gridsignal_logger.py`.
**Scope:** Items 1–4 correct and repair. Items 5–9 are Phase E proper. This is the last phase of §7.1.3.

Phase E flips `p_min_stable_frac` from 0.0 to 0.40 across **23 scenarios** that have never had a minimum stable load floor. Only `demo-20mw` already runs at 0.40. That is the largest numeric change in the whole sequence, and roughly a third of the turbine test surface is currently dark. Repair it before flipping anything.

---

## Item 1 — Re-measure the N−1 window over a real horizon

Item 8 of Phase D reported 100% COVERED and drew the wrong conclusion from it.

> Turbine-0 enters `STARTING` at t = 0 and **remains in `STARTING` throughout the 300 s window** … synchronisation occurs at approximately t = 300 s, the edge of the measurement window.

No unit ever reached the bus. The 100% figure is the BESS carrying a 6.3 MW load with 16 MW of bridging; turbines were irrelevant to it. `tripped_unit_id = None` on every tick confirms the contingency path was never exercised. Raising `hot_start_s` to 300 made the window exactly one start time long.

The contrast drawn against Phase B is also inverted: Phase B looked worse because units were actually on the bus and a trip mattered. Here there was nothing to trip.

**Re-measure over 1800 s** — the §7.1.3.9 reference configuration — long enough to see at least two sequential commitments. Report: time to first COVERED, time to first unit reaching SYNCHRONISED, the degraded-window duration, and the COVERED / COVERED_WITH_SHED split. Run it once with a unit trip injected so the contingency path is actually exercised.

This is the number §7.1.3.8 needs. Report it; do not edit the spec.

## Item 2 — The renamed discriminator no longer discriminates

`test_ramping_turbine_ignores_loading_setpoint_drop` was rewritten as `test_starting_turbine_output_frozen_by_loading_exclusion`, with `EXPECTED_STEP` changed from 1.0 to 0.0.

That test existed to prove one thing: **a unit under ramp does not get pulled toward a dropped setpoint.** It was the behavioural discriminator that settled the dual-writer question, and it worked because a RAMPING unit was on the bus with real output that two control paths could disagree about.

Rewritten against STARTING with an expected step of 0.0, it asserts that a unit producing zero MW continues to produce zero MW. True, and it tests nothing — that state has no output to protect. Changing `EXPECTED_STEP` was an assertion change, which the Phase D prompt asked you to stop and report rather than make.

**Write the correct successor.** A SYNCHRONISED unit tracking upward; drop the setpoint abruptly well below its current output; assert output falls at no more than `r_asset × dt` per interval and never snaps to the setpoint. That is the property that catches a second writer reappearing. Keep the frozen-STARTING test if it is useful, but it does not replace this one.

## Item 3 — TC-91 does not exercise the real hazard

TC-91 now calls `command_start()` and `pending.record_start()` itself, then checks the headroom path is blocked. That proves the register works once something has registered.

The hazard is two **production** call sites both issuing a command in one tick — `_stage_for_predicted_step` and the commitment check — with the register mediating. Hand-rolling the first command means they are never both live.

Add a variant that drives a real tick with both paths eligible. If the register is unreachable that way, say so and explain why, because that would mean it has no job.

## Item 4 — Repair the 26 stale-assertion failures

Phase C deferred these on the grounds that Phase D would restore an equivalent commitment path. It now has, so they are repairable and no longer blocked.

| File | Tests | Blocked on |
|---|---|---|
| `test_unit_trip.py` | TC-84a–e | `AT_TARGET` deleted |
| `test_13_4_criteria.py` | B4a, B4b | `AT_TARGET` deleted |
| `test_13_5_criteria.py` | R4×4, R5×3, R6×3 | `stage_target()` deleted |
| `test_formulas.py` | ramp-rate, d8 staging | `stage_target()` / `_target_mw` deleted |
| `test_operator_unit_commands.py` | TC-203-1/3/4 | `is_synchronised` renamed |
| `test_p1b_p2.py` | TC-81 ×4 | `AT_TARGET`, `_check_loading_exclusion` deleted |

**These are scaffolding repairs.** Setups reference deleted states and methods; the assertions are mostly still correct. Repair the setup against `command_start()`, `is_on_bus` / `contributes_to_reserve`, and the new state set.

**Where an assertion genuinely encoded the old behaviour, do not change it — report it** with old value, new value, and why the new one is right. `test_formulas.py`'s ramp-rate test and `test_13_5_criteria.py`'s R4 group are the likeliest to fall in that category, since both are about staging targets that no longer exist as a concept.

Leaving a third of the turbine surface dark through a 23-scenario MSL change is the risk this item removes.

**Gate for Items 1–4: report the corrected failure count and the re-measured N−1 figures before starting Item 5.**

---

## Item 5 — Stop sequencing

`SYNCHRONISED → UNLOADING` (setpoint forced to MSL, tracking down at `r_asset` through the loading layer) → levelled-off predicate satisfied → breaker opens → `OFFLINE`, `t_min_down_s` begins.

`levelled_off` is `|setpoint − output| < ε` sustained for a window — **a derived predicate computed where needed, never a `TurbineState`.** A state requires an owner, and a second owner of unit output reproduces the defect this whole sequence removed.

The step at breaker open is real: output falls continuously to MSL then discontinuously to zero. Do not smooth it.

## Item 6 — Sequential stops (D-09)

At most one unit in UNLOADING at a time, with a settling interval after each breaker opens. Symmetric to Item 6 of Phase D.

Without this the decommitment path exhibits the mirror image of the defect that opened this work — a reference run released three units in ten seconds, shedding 30 MW of minimum stable load across three breakers.

Add **TC-94** (unload precedes breaker open; no loaded unit goes directly to OFFLINE) and **TC-97** (at most one unit in UNLOADING at any time).

## Item 7 — Sequential base-loading (D-14)

Replace proportional sharing in `core/loading.py` — currently `shares = rated_i / Σ rated` across all on-bus units — with sequential base-loading: units loaded toward rated in commitment order, every unit at or above MSL, residual to the marginal unit. Keep the existing clamp and redistribution loop and the sub-MSL surplus return; only the initial allocation changes.

Proportional sharing makes per-unit utilisation identical to fleet utilisation regardless of unit count, so the Phase D commit trigger becomes a fleet-level signal presented as a per-unit one. The two are mutually defeating.

Add **TC-96**: assert per-unit utilisation diverges from fleet utilisation — that is the property, not the allocation arithmetic.

## Item 8 — Enable the physical constraints, last and alone

`p_min_stable_frac` 0.0 → 0.40, `t_min_run_s` 0.0 → 1800, `t_min_down_s` 0.0 → 900. All three are already enforced; only the defaults change. Catalogue each with `CHOSEN` provenance and `spec_ref` to §7.1.3.6, read through `site_parameters`.

**Do this in its own commit, after Items 5–7 are green.** It moves numbers across 23 scenarios, and mixing it with a behavioural change makes attribution impossible.

Add **TC-95** (MSL floors the allocation; the sub-MSL surplus is reported, not discarded).

Report the per-scenario delta: equilibrium demand, fleet utilisation, and any assertion that moves. Expect a large list. Classify each correct-or-incorrect; **edit none of them.**

## Item 9 — The §7.2 amendment measurement (D-10)

When a breaker opens, the unit sheds `p_min_stable_mw` in one interval while survivors recover at only `r_asset × dt` each. That gap is a bridging duty on the way **down**, and §7.2 step 4 sizes the BESS against the start-up gap only.

Measure it: peak BESS discharge at a breaker-open event, and the worst case against `p_min_stable_mw − (surviving units × r_asset × dt)`. Report both. The spec amendment is made elsewhere.

---

## Prohibited

- Changing what any test asserts. Items 2, 3 and 4 are scaffolding repair; a needed assertion change is reported, not made.
- Enabling the Item 8 defaults before Items 5–7 are green, or in the same commit as any of them.
- Making `levelled_off` a `TurbineState`.
- Transitioning a loaded unit directly to OFFLINE, in any code path.
- Smoothing the MSL step at breaker open.
- Writing any threshold, MSL fraction or dwell time as a code literal.
- Adding a start-time literal to a test fixture without a stated reason — `cold_start_s=60.0` was added to a fixture during Phase D at a value D-08 rejected as implausible. Justify it or use the default.
- Editing the spec. Report the Item 1 and Item 9 measurements.
- Adding a module-scope numeric constant to `panels/`.
- Modifying `gridsignal_logger.py`.
- Proceeding past a phase gate without reporting.

## Acceptance criteria

- [ ] N−1 window re-measured over 1800 s with a trip injected; time to first SYNCHRONISED, degraded-window duration, and COVERED / COVERED_WITH_SHED split all reported.
- [ ] Setpoint-drop discriminator rewritten against a SYNCHRONISED unit; rate-limited fall asserted; confirmed it fails if a second writer is reintroduced.
- [ ] TC-91 variant driving both production call sites in one tick, or a stated reason the register is unreachable that way.
- [ ] All 26 stale-assertion failures repaired or individually reported with old value, new value and rationale.
- [ ] Corrected failure count reported before Item 5 begins.
- [ ] Unload sequence implemented; `levelled_off` is a predicate, not a state.
- [ ] At most one unit in UNLOADING at any time in any scenario.
- [ ] Sequential base-loading replaces proportional sharing; TC-96 asserts per-unit utilisation diverges from fleet utilisation.
- [ ] Item 8 defaults enabled in their own commit, after Items 5–7 green; all three catalogued.
- [ ] Per-scenario delta reported for all 23 affected scenarios.
- [ ] TC-94, TC-95, TC-96, TC-97 added and passing.
- [ ] Breaker-open bridging duty measured; peak discharge and worst case reported.
- [ ] Guards D1, D2, E Tier 1 green; TypeScript `--noEmit` clean.
- [ ] Suite delta reported per item; every newly failing test classified correct-or-incorrect.
