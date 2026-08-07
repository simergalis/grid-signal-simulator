# Resolve the setpoint contradiction, then bound frequency

**Follows:** Droop diagnosis, offline-setpoint gate, warmup sweep, d10 re-trace.
**Baseline:** 13 failed / 978 passed / 16 xfailed backend; 29 frontend; `tsc --noEmit` clean.
**Scope:** Items 1–3 are corrections and clarifications. Item 4 is the protection layer, and it is the substantive piece.

The droop trace was properly done and the surplus hypothesis was refuted honestly rather than salvaged. Four things follow, and the deepest one is not the droop bound.

---

## Item 1 — The report contradicts itself on `gt_setpoint_mw` (blocking)

Item 2 of the last report states:

> `TickResult.gt_setpoint_mw` is intentionally kept as `_p_dispatch_droop_mw` (line 1362) so B5b and informational consumers are unchanged. **B5b stays green.**

The suite result states:

> `test_B5b_gt_setpoint_mw_equals_dispatch_required` — PASS → **FAIL** — gate correctly zeroes the field

Both cannot be true. Either the implementation went further than the design section describes, or B5b broke for an unrelated reason.

Report the **current** state of `simulation_core.py` around line 1362 verbatim, and say plainly whether `TickResult.gt_setpoint_mw` is gated. Then state which of these holds:

- Only `_asset_delivery_error_mw` is gated → B5b must have broken for another reason; find it.
- `TickResult.gt_setpoint_mw` is also gated → the design section is wrong and needs correcting, and the modal's per-unit setpoint marker is now gated too, which was one of the reasons for the change.

This determines what the fleet modal renders on an OFFLINE unit, so it cannot be left ambiguous.

## Item 2 — B5b needs a spec citation, not a verdict

> B5b was testing the pre-gate wrong behavior. Fixing it requires a test edit (prohibited).

Possibly correct, but asserted rather than established. B5b is a B-series acceptance test, so it traces to a spec clause. The question is what `gt_setpoint_mw` is **defined** to mean:

- *"What the turbine fleet is commanded to produce"* → gating on SYNCHRONISED is right and B5b encoded the old behaviour.
- *"The share of dispatch requirement allocated to turbines"* → zero is wrong whenever demand exists, and the gate has changed a specified field.

Find the spec clause B5b traces to and quote it. Decide from the spec, not from the implementation. If the spec is silent, say so — that is a gap to record, and the gate then needs a decision rather than an inference.

## Item 3 — Check the §7.2 attribution before reopening it

> The §7.2 amendment measurement assumed the turbine ramps up past the demand curve, takes over from the BESS … the taper is the handoff event.

The §7.2 amendment (D-10) measured the **breaker-open bridging duty at decommitment** — MSL shed against surviving-unit ramp recovery, tabulated across survivor counts 3/2/1/0 on two fleets. Those were constructed states, not full runs, and none depended on a turbine catching up to demand or on the taper firing.

Re-read that measurement and confirm whether `hot_start_s` bears on it. If it does not, withdraw the claim and record that the §7.2 evidence stands. If it does, show which figures move.

**Also, for the record on d10:** it has been in the failing set since the original triage, but the symptom has changed — the earlier diagnosis described a BESS re-firing at t=140 s with a 5 s toggle; it now sits flat at rated for the entire run. State it as pre-existing-by-name and a different defect by behaviour, so "pre-existing" stops doing two jobs in the failure table.

**Gate for Items 1–3: report before starting Item 4.**

---

## Item 4 — Frequency has no floor, and that is the real defect

The trace shows `f_exit` running **33.156 → 18.084 → 4.782 → −6.749 → −16.510 → −24.499 Hz.**

Negative frequency is not a physical state. The droop correction is not the runaway — it is *proportional* to a Δf that has no floor, so bounding the correction treats the symptom.

The arithmetic is right: `df/dt = f_nom × ΔP / (2H·S_base) ≈ 3.4 Hz/s`, and over a 5 s tick that is −16.8 Hz. What is missing is that **no real island reaches −24 Hz.** It sheds load, generators trip on under-frequency protection, and the island collapses. The engine has a swing equation with no protection layer, so it integrates straight through collapse and keeps reporting numbers.

This matters beyond the tests. An islanded microgrid simulator whose frequency model has no collapse condition will be asked about by the first power engineer who sees it, and the current answer is that it does not represent the failure mode it exists to help avoid.

### 4a — Apply the droop clamp

Take the proposed bound: clamp `_p_dispatch_droop_mw` to `_s_base_mw × power_factor` (= Σ rated_MW). Both terms are already computed at the droop block, and no new constant is introduced.

Report the resulting values for the same six ticks, and the suite delta.

### 4b — Diagnose the protection layer (report only, no implementation)

Report:

1. Every place `state._frequency_hz` is written, with `file:line`, and whether any bound exists.
2. Whether any under-frequency or over-frequency threshold appears anywhere in the engine — load shedding, generator trip, alarm.
3. What the curtailment ladder currently responds to, and whether frequency is among its inputs.
4. Whether the spec defines any frequency protection. §7.1.2 covers the grid-forming anchor; check whether it or any other section specifies UFLS thresholds, generator trip settings, or an island-collapse state.

Then propose, without implementing: what a minimal protection layer would need — thresholds, what trips at each, and what state the plant enters when the island collapses. Note which values would be catalogued and their provenance.

**Do not implement.** This is a physics-model addition with spec implications, and it needs a decision before code.

Note explicitly whether the missing protection layer also bears on the I3 findings, where frequency reaches 62.35 Hz — over-frequency with no ceiling is the mirror of the same gap.

---

## Prohibited

- Leaving the `gt_setpoint_mw` contradiction unresolved.
- Deciding B5b from the implementation rather than the spec.
- Implementing any protection layer, threshold, or trip logic.
- Editing any test assertion or fixture.
- Writing any new constant as a code literal.
- Adding a module-scope numeric constant to `panels/`.
- Modifying `gridsignal_logger.py`.
- Proceeding past the Item 1–3 gate without reporting.

## Acceptance criteria

- [ ] `simulation_core.py` line 1362 region quoted verbatim; gating state of `TickResult.gt_setpoint_mw` stated plainly.
- [ ] B5b's break attributed to the gate or to another cause, with evidence.
- [ ] Spec clause for `gt_setpoint_mw` quoted, or the gap recorded.
- [ ] §7.2 attribution confirmed or withdrawn, with the measurement re-read.
- [ ] d10 restated as pre-existing-by-name with a changed symptom.
- [ ] Droop clamp applied; same six ticks re-reported; suite delta attributed.
- [ ] Every write to `state._frequency_hz` reported with `file:line`.
- [ ] Existence or absence of any frequency threshold in the engine reported.
- [ ] Spec searched for frequency protection; findings quoted or absence recorded.
- [ ] Minimal protection layer proposed, not implemented, with catalogue candidates named.
- [ ] Bearing on the I3 over-frequency case stated.
- [ ] Guards D1, D2, D3, E green; `tsc --noEmit` clean.
- [ ] Suite reported against 13 / 978 / 16 xfailed, every delta attributed.
