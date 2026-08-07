# Item 6 — UI conformance, with two carried-over verifications

**Follows:** Items 1–5 gate passed. 15 failed / 975 passed / 16 xfailed backend; 29 frontend; zero regressions.
**Reference:** `gridsignal_fleet_modal_proposed.html` — supplied alongside this prompt. Open it before starting.
**Scope:** two verifications, then the conformance pass. No new features, no class C defect work.

The Items 1–5 corrections landed properly. Two things from that report need confirming, and both are exercised by the same fleet state the conformance pass needs anyway — do them together.

---

## Item A — Verify the floor comparison (blocking)

The Items 1–5 report gives this worked example:

> 3 × 7 MW on bus, demand 12 MW · `reserve_floor_mw` = `12 + 7 = 19 MW`
> `reserve_satisfied` = **False** (21 MW < 19 MW — floor NOT met, correctly violated)

**21 is not less than 19.** Committed capacity is 21 MW against a 19 MW floor, so the floor *is* met and `reserve_satisfied` should be `True`.

Either the report is mis-transcribed, or `floor_violated` has the comparison inverted inside `evaluate_commitment()` — which would reproduce the exact sign error Item 1 set out to fix, relocated from the summary block into the evaluator. The field is what an operator reads as an N−1 verdict, so it cannot be left on an assumption.

Verify on live ticks, and report the raw values for both:

1. **Reserve satisfied:** committed capacity comfortably above `demand + largest unit`. Expect `floor_violated = False`, `reserve_satisfied = True`.
2. **Reserve violated:** committed capacity below the floor. Expect the inverse.

Report `committed_rated_mw`, `floor_mw`, `floor_violated` and `reserve_satisfied` for each. If the comparison is inverted, fix it and say so; if the report was simply mis-transcribed, say that instead.

## Item B — Confirm the `levelled_off` window ordering

```python
_ut._levelled_off_sustained = _dwell_elapsed >= _loff_window_s
if _dwell_elapsed >= _ut.config.unload_tail_s:
    _ut._levelled_off_sustained = False   # reset before state change
```

The flag is therefore `True` only between `levelled_off_window_s` and `unload_tail_s`, and `False` at the instant the breaker opens.

**If `levelled_off_window_s ≥ unload_tail_s` in any configuration, the flag is never `True` at all** and the panel's indicator silently never fires — a display that is simply absent rather than wrong, which is harder to notice.

Report both values from the catalogue, whether the ordering is enforced anywhere, and the observed duration for which `levelled_off` is `True` during one real unload. If nothing enforces the ordering, say so — that is a finding, not something to fix here.

## Item C — Confirm the two-set field comments

`committed_rated_mw` excludes UNLOADING; `on_bus_output_mw` includes it. Both are correct, and they answer different questions — reserve capacity versus produced output.

That distinction will read as an inconsistency to the next person who sees it, and the obvious "fix" is to unify them. Confirm the field comments in `core/models.py`, `runtime/run_manager.py` and `types.ts` each state which set they use and why. Quote them.

**Gate for A–C: report before starting the conformance pass.**

---

## Item 6 — Conformance against the mockup

Open `gridsignal_fleet_modal_proposed.html`. The annotation toggle explains what each element fixes.

**It is an information-design reference, not a pixel target.** The mockup is standalone HTML; the panel is `React.createElement` inside the existing `PanelConfig` contract. Layout will and should differ. What must match is **what is shown, how it is scoped, and what an operator can conclude.**

Report each element as **matches / differs / not implemented**, with the reason for any difference. A deliberate deviation is a good answer; an accidental one is not.

| Element | What the mockup specifies |
|---|---|
| Per-unit bar | Output fill, dashed rule at MSL fraction, marker at setpoint. **The gap between fill and marker is the ramp** — it must be legible, not incidental. |
| Ramp gap | Visible on a unit tracking toward a higher setpoint (mockup: turbine-1, 11.20 → 13.50). |
| STARTING row | Countdown draining in place of an output figure; thermal state, start phase, remaining time all shown; SYNC column reads `starting`, not a breaker boolean. |
| UNLOADING | Visually distinct from SYNCHRONISED — a unit leaving must not read as a unit merely running low. |
| Verdict band | N−1 firm from **committed** units. Mockup: 30.0 MW firm against a 38.5 MW design peak = shortfall. From installed it would read 60 MW and appear covered. |
| Committed capacity row | Excludes STARTING; the sub-label says so explicitly. |
| Reserve floor row | Demand + largest committed unit, with the arithmetic shown in the sub-label. |
| Utilisation scale | Position against **both** thresholds (decommit 50%, commit 80%) legible at a glance. |
| Blocked panel | `blocked_by` and `last_decision_reason` shown together, so "satisfied" and "constrained" are distinguishable. |
| Marginal-unit ramp | Clamped to headroom, with the headroom stated in the sub-label. |
| Preserved | Verdict band, fleet table, operator Trip/Start, paralleling strip, dark/monospace/amber language. |

### The state to construct

Build the mockup's fleet: **3 SYNCHRONISED, 1 STARTING, 1 OFFLINE, utilisation 76.7%, reserve floor violated.**

That state is the point of the commitment rows: utilisation sits *below* the 80% commit threshold while a commitment is nonetheless in progress, because the floor governs the trigger. Confirm the panel renders it coherently. **If the panel cannot express that, the commitment rows are not doing their job** and that is the finding.

It also exercises the Item A comparison directly — same arithmetic, real tick.

Capture what the panel actually renders for that state: every stat row value and sub-label, per-unit row contents, and the verdict string. Paste them.

### Report mockup errors

The mockup was drawn from the reference implementation's rules, not from the live engine. If any figure in it is wrong, unbuildable, or inconsistent with what the engine produces, report it. That is useful output, not a failure.

---

## Prohibited

- Treating the mockup as a pixel target, or restyling the panel to match its layout.
- Changing any Items 1–5 correction to make conformance easier.
- Recomputing the reserve floor outside `CommitmentDecision`.
- Including UNLOADING in `committed_rated_mw`, or excluding it from `on_bus_output_mw`.
- Editing `test_I3_droop_*`.
- Editing any test assertion.
- Enforcing the `levelled_off_window_s` / `unload_tail_s` ordering in this session — report it.
- Adding a module-scope numeric constant to `panels/`.
- Emitting any payload key before its `types.ts` entry.
- Modifying `gridsignal_logger.py`.
- Proceeding past the A–C gate without reporting.

## Acceptance criteria

- [ ] Floor comparison verified on a satisfied and a violated tick; raw `committed_rated_mw`, `floor_mw`, `floor_violated`, `reserve_satisfied` reported for both.
- [ ] Inversion fixed and stated, or the report confirmed mis-transcribed.
- [ ] `levelled_off_window_s` and `unload_tail_s` values reported; ordering enforcement stated; observed True-duration measured on a real unload.
- [ ] Field comments for `committed_rated_mw` and `on_bus_output_mw` quoted from all three files.
- [ ] Every mockup element reported matches / differs / not implemented, with reasons.
- [ ] The 76.7% floor-violated state constructed; rendered stat rows, sub-labels, per-unit rows and verdict string pasted.
- [ ] Any mockup error reported.
- [ ] Guards D1, D2, D3, E Tier 1 green; `tsc --noEmit` clean.
- [ ] Suite reported against 15 / 975 / 16 xfailed and 29 frontend, every delta attributed.
