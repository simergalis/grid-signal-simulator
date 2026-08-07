# Phase E closeout — four items to close §7.1.3

**Follows:** Phase E complete. 26 stale tests repaired, 18 new tests added, one classified delta, zero regressions.
**Baseline:** 13 failed, 975 passed, 16 xfailed.
**Target model:** `backend/core/` — the live engine. **Not** `gridsignal_logger.py`.
**Scope:** four items. No fleet-modal work, no class C defect work.

§7.1.3 is implemented. Four things need settling before it is signed off — three are corrections and one is a measurement whose conclusion does not follow from its own numbers.

---

## Item 1 — Replace the Guard D1 exemptions with an explicit flag

Item 8 added Guard D1 exemptions for `t_min_run_s` and `t_min_down_s`, on the grounds that `0.0` is a disable-flag sentinel while the catalogue holds a CHOSEN production default.

That is the same conflict DR-2026-08-06 **D-03** resolved for `band_pct_calibrated`, and it was resolved by adding an explicit boolean — not by exempting the guard. This is the first time in this project a guard has been quieted rather than satisfied, and quieting is how the parameter catalogue's own usage note came to be ignored in the first place.

**Fix as per D-03:** add `min_run_enabled: bool` and `min_down_enabled: bool` to `TurbineConfig`. The dwell times then always carry a meaningful duration, and `0.0` stops meaning two things. Remove both Guard D1 exemptions.

Report the exemption list before and after. If any exemption remains, name it and state why it is not the same problem.

## Item 2 — Rename `p_min_stable_frac_all_scenarios`

The other two entries added in Item 8 are `t_min_run_s` and `t_min_down_s` — names of quantities. This one names a migration event, which will read as nonsense once there is no "all scenarios" rollout to remember.

More concretely: `TurbineConfig` reads `p_min_stable_frac`, so there is now a catalogue key that does not match the field it governs, and a second key could plausibly be added under the real name. Two catalogue entries for one quantity is the drift the catalogue exists to prevent.

Rename to `p_min_stable_frac`. If a key by that name already exists, report both and reconcile — that would itself be the defect.

## Item 3 — `command_stop()` must report why it declined

The R5 guard returns silently:

```python
if (... sim_time - self._run_start_s < self.config.t_min_run_s):
    return  # defer; caller retries on next decommit check
```

Deferring is the correct behaviour. Doing it silently is not: the commitment layer cannot distinguish "stop accepted" from "stop refused", so it has no way to tell an operator whether the fleet is satisfied or constrained.

`CommitmentDecision` already carries `blocked_by` for exactly this, and the fleet modal is specified to render it. Return the block reason rather than `None`, and thread it into the decommit path so `blocked_by` reflects a real refusal.

Report every caller of `command_stop()` and what each now does with the reason.

## Item 4 — Re-measure the breaker-open bridging duty

The Item 9 conclusion — *"no §7.2 spec amendment required"* — does not follow from the numbers reported.

**The margin is 0.2 MW on a 2.8 MW step: 7%.** That is not comfortable, and it was evaluated at a single operating point: `demo-20mw`, four units, 7 MW rated, `r_asset = 0.2`.

The arithmetic scales differently on each side. The MSL step is proportional to `rated_mw`; the survivors' recovery is `r_asset × dt × survivor_count`. Larger units, or fewer survivors, and the sign flips. A 15 MW fleet at the same MSL fraction produces a real discharge — the reference implementation measured 1.55 MW.

**The 3-survivor case is also not the interesting one.** Under sequential decommitment units shed one at a time, so the survivor count falls with each stop and the gap opens at the end of the sequence. The report jumps from 3 survivors to 0 without evaluating 2 or 1.

Re-measure and report a table over:

- survivor counts 3, 2, 1, 0
- at least two fleets — `demo-20mw` and one with materially larger units
- both the computed worst case `p_min_stable_mw − (survivors × r_asset × dt)` and the **observed** peak BESS discharge from an actual run

Then state whether a §7.2 amendment is needed, given the range rather than one point. If the answer is still no, it needs to hold across the table.

The spec edit is made elsewhere. Report the numbers.

---

## Prohibited

- Adding a Guard D1 exemption, or leaving one in place, as a substitute for fixing the underlying conflict.
- Editing any test assertion or fixture. `TC-203-3` is correctly classified and stays failing until the enabled-flag change makes it meaningful again — report its status after Item 1.
- Concluding on the §7.2 amendment from a single operating point.
- Editing the spec.
- Any fleet-modal work — U-1 through U-6 are a separate workstream.
- Any class C defect work.
- Writing any threshold, MSL fraction or dwell time as a code literal.
- Modifying `gridsignal_logger.py`.

## Acceptance criteria

- [ ] `min_run_enabled` and `min_down_enabled` added; both Guard D1 exemptions removed; exemption list reported before and after.
- [ ] `p_min_stable_frac_all_scenarios` renamed to `p_min_stable_frac`; any duplicate key reported and reconciled.
- [ ] `command_stop()` returns a block reason; every caller reported with what it does with it; `blocked_by` reflects a real refusal.
- [ ] `TC-203-3` status reported after the enabled-flag change.
- [ ] Bridging duty measured across survivor counts 3 / 2 / 1 / 0 on at least two fleets, computed worst case and observed peak discharge both reported.
- [ ] §7.2 amendment recommendation stated against the full table.
- [ ] Guards D1, D2, E Tier 1 green; TypeScript `--noEmit` clean.
- [ ] Suite reported against 13 / 975 / 16 xfailed, any delta attributed.
