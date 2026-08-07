# Close the priority conformance gaps

**Follows:** Item 6 conformance pass. Items A–C gated; nine gaps reported honestly.
**Baseline:** 15 failed / 975 passed / 16 xfailed backend; 29 frontend; `tsc --noEmit` clean.
**Reference:** `gridsignal_fleet_modal_proposed.html`.
**Scope:** two verifications, four gaps to close, two optional. Five gaps are explicitly deferred.

The conformance report was accurate and self-critical — the ramp-gap and UNLOADING findings were reported against your own work, which is what made them useful. The nine gaps are not equal, and this session closes four.

---

## Item 1 — Verify the integration path, not the evaluator (blocking)

Item A confirmed `evaluate_commitment()` computes the floor correctly. **That function was never the defect.** The Item 1 bug was in the summary block in `simulation_core.py`, which recomputed the floor instead of reading it — so verifying the source says nothing about whether the consumer now reads it correctly.

The report is clear that the live path could not be exercised:

> `evaluate_tick()` tests showed `fleet_utilisation=0` and `reserve_floor_mw=largest_mw` because the GPU module carries no jobs

Build a tick **with actual workload** and verify end to end: `evaluate_tick` → summary block → `TickResult` → `commitment_block` in the broadcast dict → the values the panel receives.

Read the figures off the **payload**, not off the evaluator. Report `committed_rated_mw`, `reserve_floor_mw`, `reserve_satisfied`, `fleet_utilisation` and `pending_start_unit_id` as they appear in the emitted dict, for one satisfied and one violated tick.

This is the only remaining unverified link in the chain the Items 1–5 corrections touched.

## Item 2 — Catalogue `unload_tail_s`

> `unload_tail_s` | 60 s | `TurbineConfig` dataclass default — **NOT in the locked catalogue**

A control-relevant physical constant with no catalogue entry, no provenance and no `spec_ref` — and it gates breaker-open, so it determines when a unit leaves the bus. Guard D cannot see it, for the same reason it could not see `_COOLING_MARGIN`: the guard enforces agreement between code and catalogue and is silent about constants absent from the catalogue.

Add it with `CHOSEN` provenance and `spec_ref` §7.1.3.6, read through `site_parameters`.

Then express the Item B ordering finding as a catalogue-level check: `unload_tail_s > levelled_off_window_s`. A violation means `levelled_off` is never `True` and the panel indicator silently never fires — an absent display rather than a wrong one, which is the harder kind to notice. Assert it in the catalogue self-consistency test alongside the existing min/max checks.

Sweep for siblings while you are there: any other physical constant living as a `TurbineConfig`, `BessConfig` or `SiteConfig` dataclass default with no catalogue entry. Report the list; catalogue only `unload_tail_s` in this session.

---

## Gaps to close

### Gap 1 + 2 — The per-unit bar needs its own column, with the ramp gap

> The mini-bar has fill and setpoint marker but no shaded gap element between them. The ramp is visible only as a statistical value in the "Ramp with 1 unit" row.

**This is the design, not a refinement.** The whole workstream exists to make ramping a modelled, visible quantity, and at 48 × 4 px inside the CURRENT MW cell it cannot be legible even with the shading added.

Give the bar its own table column — the mockup uses "Output · setpoint · MSL" at roughly 132 × 16 px. Add the shaded region between fill and setpoint marker. On a unit tracking toward a higher setpoint the gap must be visible at a glance, and it must visibly close as the unit levels off.

Keep the numeric MW value in its own cell; the bar supplements it rather than replacing it.

If the table cannot accommodate another column without crowding, say which existing column you would drop and why — do not shrink the bar back to fit.

### Gap 5 — UNLOADING needs a colour distinction

> Unit ID colour is GOLD for all states; fill colour does not change for UNLOADING. A unit leaving cannot be visually distinguished from a unit at MSL by colour alone.

Under sequential stops, units pass through UNLOADING routinely. A unit at 6.0 MW that is leaving looks identical to one that is simply lightly loaded — an operational misread, not a styling preference.

Use the ember treatment from the mockup for both the unit ID and the bar fill when `state === 'unloading'`. Small change; it is on this list because of what it prevents, not because of its size.

### Gap 9 — Show `blocked_by` and `reason` together

> The "Last decision" stat row shows `blocked_by` OR `reason` — whichever is non-empty — not both.

The blocked panel exists to let an operator distinguish "satisfied" from "constrained". Hiding the decision reason when a block is present removes exactly the context that distinction needs. Render both.

---

## Optional if cheap

**Gap 8 — utilisation scale.** A visual bar with markers at the decommit and commit thresholds. The text conveys the number; the scale conveys the position relative to both thresholds, which is what makes the 76.7%-floor-violated state legible at a glance.

**Gap 7 — dedicated reserve-floor row.** Currently absorbed into the Committed MW sub-label. Its own row with the arithmetic — `34.50 MW demand + 15.0 MW largest committed unit` — makes the N−1 question explicit.

Take these only if they do not compete with Gaps 1+2. Report if you skip them.

---

## Explicitly deferred — do not implement

Gaps 3 (hatched STARTING fill), 4 (inline thermal annotation), 6 (naming the excluded starting unit in the sub-label), and any remaining visual-fidelity difference. The information is already present in each case. Leave them.

---

## Prohibited

- Shrinking the per-unit bar to fit the existing column layout.
- Verifying the floor through `evaluate_commitment()` rather than the emitted payload.
- Implementing the deferred gaps.
- Enforcing the `unload_tail_s` ordering anywhere but the catalogue self-consistency test.
- Cataloguing constants other than `unload_tail_s` in this session — report the sweep, do not act on it.
- Treating the mockup as a pixel target. It is an information-design reference; layout may differ where you state why.
- Editing any test assertion.
- Adding a module-scope numeric constant to `panels/`.
- Emitting any payload key before its `types.ts` entry.
- Modifying `gridsignal_logger.py`.

## Acceptance criteria

- [ ] `commitment_block` values read off the emitted payload on a workload-carrying tick, satisfied and violated cases both reported.
- [ ] `unload_tail_s` catalogued with `CHOSEN` provenance and §7.1.3.6; read through `site_parameters`.
- [ ] `unload_tail_s > levelled_off_window_s` asserted in the catalogue self-consistency test.
- [ ] Uncatalogued dataclass-default sweep reported; nothing else catalogued.
- [ ] Per-unit bar in its own column at legible scale, with the ramp gap shaded and visibly closing as a unit levels off.
- [ ] UNLOADING distinguished by colour on both unit ID and bar fill.
- [ ] `blocked_by` and `reason` rendered together.
- [ ] Gaps 7 and 8 taken or explicitly skipped with a reason.
- [ ] Gaps 3, 4, 6 untouched.
- [ ] Guards D1, D2, D3, E Tier 1 green; `tsc --noEmit` clean.
- [ ] Suite reported against 15 / 975 / 16 xfailed and 29 frontend, every delta attributed.
