# Two corrections, then diagnose the remaining 15

**Follows:** Open-parameter catalogue complete. Guard D2 backlog empty, D3 at 26 call sites, Item 1 verified end to end.
**Baseline:** 15 failed / 976 passed / 16 xfailed backend; 29 frontend; `tsc --noEmit` clean.
**Scope:** Items 1–2 are corrections. Item 3 is **diagnosis only — no fixes.**

The catalogue work closed properly and the exclusion decisions are on the record. Two small things from that report need settling, and then the remaining 15 failures are the last substantive work in this sequence.

---

## Item 1 — `warm_start_s` and `hot_start_s` are both 300 s

Both were catalogued at 300 s, with different provenance and different spec refs. That makes the thermal-state distinction inoperative: a warm unit and a hot unit synchronise at the same moment, so `warm_threshold_s` at 4 hours sorts units into a state that behaves identically to HOT.

Physically they should differ. A machine on turning gear starts appreciably faster than one down for two hours. The D-08 correction moved `hot_start_s` 60 → 300 for sound reasons, but it landed *on top of* `warm_start_s` rather than beside it.

Your own reported invariant — `hot_start_s ≤ warm_start_s ≤ cold_start_s` — holds only weakly here.

Decide and report: lower `hot_start_s` (180 s is a defensible frame-class figure), or raise `warm_start_s` (600 s sits sensibly between 300 and 900). Either is fine; both being 300 is not. Update the catalogue entries and their `provenance_detail`, keeping the D-08 correction history.

Then check what depends on the distinction. If `warm_threshold_s` sorts units into a state with no distinct behaviour, the threshold is currently decorative — say so if that is what you find.

## Item 2 — Second-tick verification of the floor driving a commit

The violated payload showed `action = hold` with the commit timer at 5/30 s. That is consistent — the floor governs commitment, but the commit path is separately gated on the pending-start register and the settle interval, and a single tick from a standing start cannot show one.

It does mean the harness has not yet demonstrated the floor **actually driving a start**. Run the violated case forward past the 30 s confirmation window and report the tick at which `action` becomes `commit`, together with `pending_start_unit_id` and `blocked_by`.

Small addition to the existing harness. It closes the one thing the single-tick test could not show.

**Gate for Items 1–2: report before starting Item 3.**

---

## Item 3 — Diagnose the remaining 15 (report only)

**No fixes in this session.** Several of these have been carried since the original triage, and two were diagnosed against a loading layer that Phase E has since replaced wholesale — so the prior diagnoses describe code that no longer exists. Re-diagnose from the current tree.

Classify each of the 15 and report with evidence. Group them:

### Group A — intentional red (expect 4)

`test_power_cap_toggle_count_within_300s`, `test_oscillation_is_reproducible_across_seeds` (×3 seeds). Confirm from each docstring that the failure is still deliberate and still describes current behaviour. A test written to fail against a hardcode that has since been catalogued may no longer be red for its stated reason.

### Group B — known, with an agreed disposition (expect 3)

- `test_I3_droop_creates_restoring_force_when_f_above_nominal` and `test_I3_droop_direction_vs_no_droop` — the §7.1.3.6 MSL-floor finding. Confirm the diagnosis still holds and report the spec text that should be written. **Do not edit the tests.**
- `test_tc_203_3_immediate_start_after_trip_accepted_when_cooldown_zero` — asserts `t_min_down_s == 0.0`, which was the old default. Now that `min_down_enabled` exists, the test's intent is expressible as `min_down_enabled=False`. Report the one-line fixture change; do not apply it.

### Group C — stale assertion, one line (expect 1)

`test_internal_elapsed_unaffected_by_f5` — asserts 40.0 against an actual 115.0, traced to `ramp_seconds` moving 45 → 120. Confirm the trace still holds and report the exact change.

### Group D — genuine defects, re-diagnose from scratch (expect the rest)

**`test_d10_demo_20mw_bess_fires_and_tapers`.** Previously diagnosed as cooling-load growth creating a real shortfall. I argued at the time it was the §7.2 step-3 taper failing its sustained-10-second rule, given a BESS toggling 0→5→0 at the 5 s tick period. **Both diagnoses predate the loading-layer replacement.** Produce a fresh tick-by-tick trace and determine which — or neither — holds now.

**`test_tc_gt2_f_state_flips_when_soc_crosses_threshold`.** Previously traced to the loading layer driving turbine output to zero, giving `e_required = 0`. Under MSL that path should no longer exist — a committed unit cannot be driven below `p_min_stable_mw`. Re-trace; if the symptom persists it has a different cause.

**`test_demo_pms_column3_tc64_to_tc68`.** SCADA commands stay 0 across an 8-tick window. Never examined in any prior session. Diagnose from scratch.

**`test_D3_grid_connected_settled`, `test_D3_islanded_settled`, `test_I4a_healthy_islanded_delivery_error_near_zero`, `test_B1a_islanded_delivery_fault_visible_in_delivery_channel`.** An earlier report attributed the D3 pair to *"commitment engine issues start during test → delivery error"*. If that is right, these are not pre-existing at all — they are consequences of Phase D, and the classification has been carried wrongly. Establish for each: was it failing before the commitment engine was wired, and if not, is the new behaviour correct?

That last group is the one I would look at first. Four tests about delivery error and balance decomposition failing together, attributed in passing to the commitment engine, is either a real interaction worth understanding or a misattribution that has been repeated for several sessions.

### For each of the 15, report

Test name · current failure mode · root cause with `file:line` · whether the prior diagnosis still holds · classification · proposed disposition. **No fixes.**

---

## Prohibited

- Fixing anything in Item 3, including the one-line changes.
- Editing any test assertion or fixture.
- Carrying forward a prior diagnosis without re-establishing it against the current tree.
- Leaving `warm_start_s` and `hot_start_s` equal.
- Enforcing any cross-parameter invariant beyond the existing Guard E check.
- Adding a module-scope numeric constant to `panels/`.
- Modifying `gridsignal_logger.py`.
- Proceeding past the Item 1–2 gate without reporting.

## Acceptance criteria

- [ ] `warm_start_s` and `hot_start_s` distinct; decision and rationale reported; catalogue entries and `provenance_detail` updated.
- [ ] Whether `warm_threshold_s` sorts units into a behaviourally distinct state reported.
- [ ] Violated case run past the confirmation window; commit tick, `pending_start_unit_id` and `blocked_by` reported.
- [ ] All 15 failures classified into groups A–D with evidence.
- [ ] For each, prior diagnosis confirmed or refuted against the current tree.
- [ ] `test_d10` and `test_tc_gt2` re-traced from scratch; both prior diagnoses explicitly addressed.
- [ ] D3 pair, I4a and B1a established as pre-existing or Phase-D-caused, with evidence either way.
- [ ] `test_demo_pms_column3` diagnosed for the first time.
- [ ] Zero fixes applied; suite unchanged at 15 / 976 / 16 xfailed.
- [ ] Guards D1, D2, D3, E green; `tsc --noEmit` clean.
