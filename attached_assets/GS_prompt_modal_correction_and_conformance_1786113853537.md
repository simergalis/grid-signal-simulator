# Correction — reserve floor, clamp, and UI conformance

**Follows:** Items 4–9 (fleet modal backend wiring and UI defect fixes).
**Baseline:** 15 failed / 974 passed / 16 xfailed backend; 29 passed frontend; `tsc --noEmit` clean.
**Reference:** `gridsignal_fleet_modal_proposed.html` — attached alongside this prompt.
**Scope:** five corrections, then a conformance pass. No new features. No class C defect work.

The UI structure landed well — per-unit bars, STARTING countdown, UNLOADING distinct, commitment rows. Three of the computed values behind them are wrong, and one clamp fixes the absurd case while leaving the real one.

---

## Item 1 — `reserve_floor_mw` is not the reserve floor (blocking)

```python
_reserve_floor_mw_cs = _commit_cfg_cs.decommit_utilisation * _committed_rated_mw_cs
_reserve_satisfied_cs = _fleet_utilisation_cs >= _commit_cfg_cs.decommit_utilisation
```

That computes **50% of committed capacity** and reports satisfied when utilisation is *above* 50%. §7.1.3.3 defines the floor as:

```
Σ rated over SYNCHRONISED  ≥  P_dispatch_required + max(rated over SYNCHRONISED)
```

Demand **plus the largest committed unit**. The implemented version has no largest-unit term, so it is not an N−1 quantity at all — it is the decommit threshold under a different name.

The consequence inverts: a lightly-loaded fleet with ample spinning reserve now reports `reserve_satisfied = False`, while a fleet at 90% utilisation with no backup reports `True`. This field feeds the modal's verdict band and the "Committed MW" row colour, so the inversion reaches the operator directly.

**`evaluate_commitment()` already computes the correct floor.** Read it from the decision rather than recomputing a different quantity in the summary block. If `CommitmentDecision` does not currently carry it, add it there — one source, not two.

Report the values before and after on a live tick.

## Item 2 — `committed_rated_mw` must exclude UNLOADING

> `committed_rated_mw: Σ rated_mw for SYNCHRONISED/UNLOADING units`

An unloading unit is leaving the bus, pinned at MSL, with no upward headroom. Counting its full nameplate overstates reserve precisely when the fleet is shrinking — the moment the figure matters most.

`contributes_to_reserve` is `{SYNCHRONISED}` only, and that distinction was the entire point of the Phase C predicate split. Use it.

Note this differs from `on_bus_output_mw`, which correctly **includes** UNLOADING because those units are genuinely producing. Two different questions, two different sets. State both in the field comments so the next reader does not "harmonise" them.

## Item 3 — U-3's clamp guards nameplate, not headroom

```typescript
const rampWith1MW = Math.min(rampEnergyMW / units.length, maxUnitMW)
```

Two defects.

**`units.length` counts OFFLINE and STARTING units.** Dividing fleet ramp energy by five when three are on bus understates each contributing unit.

**The clamp is against nameplate, not headroom.** A unit at 12 MW output on a 15 MW machine can contribute at most **3 MW** more, whatever the horizon. Clamping to 15 fixes the absurd case — 33 MW from a 15 MW machine — and leaves the real one intact.

The correct per-unit quantity is `min(rated_mw − output_mw, r_asset × horizon_s)`, which is exactly what the backend `ramp_capability()` computes. Derive from that.

**TC-99b currently locks in the wrong bound** — its *"100 MW clamped to 15 MW"* assertion encodes nameplate clamping. Update it to assert headroom clamping, and add a case with a unit near rated where the two answers differ: nameplate clamping says 15, headroom clamping says 3. That case is the test.

## Item 4 — `levelled_off` reports the wrong predicate

```python
"levelled_off": not math.isnan(t._levelled_off_since_s)
```

That reports the condition has **started** holding. §7.1.3.1 defines levelled-off as holding for `levelled_off_window_s`, and the breaker-open gate uses the sustained form.

So the payload and the control logic currently disagree by up to one window — the panel can show a unit levelled off while the breaker gate still considers it settling. Compute the sustained predicate and broadcast that.

## Item 5 — TC-98 asserts a fixture against itself

`output_mw: [12.5, 11.8]` with `on_bus_output_mw: 24.3` — the fixture supplies both sides of the equation, so the test proves the panel can add rather than that the backend keeps the two consistent.

The case that matters is the backend one, and it is exactly what the D-05 rename could break. Add a **backend** assertion over a real tick: per-unit `output_mw` summed over `is_on_bus` equals `on_bus_output_mw`, including a UNLOADING unit at MSL. Keep the frontend test as a rendering check.

**Gate for Items 1–5: report the corrected values from a live tick, and the backend suite delta.**

---

## Item 6 — UI conformance against the proposed mockup

`gridsignal_fleet_modal_proposed.html` is a rendered mockup of the agreed design, with annotations explaining what each element fixes. Open it, then compare the implemented panel against it element by element.

**It is a design reference, not a pixel target.** The mockup is standalone HTML; the panel is `React.createElement` inside the existing `PanelConfig` contract. Layout will differ. What must match is the **information design** — what is shown, how it is scoped, and what an operator can conclude.

Report conformance per element as **matches / differs / not implemented**, with the reason for any difference. A deliberate deviation is a fine answer; an accidental one is not.

| Element | What the mockup specifies |
|---|---|
| Per-unit bar | Output fill, dashed rule at MSL fraction, marker at setpoint. **The gap between fill and marker is the ramp** — it must be legible, not incidental. |
| Ramp gap | Visible on a unit tracking toward a higher setpoint (mockup: turbine-1 at 11.20 → 13.50). |
| STARTING row | Countdown draining in place of an output figure; thermal state, start phase and remaining time all shown; SYNC column reads `starting`, not a breaker boolean. |
| UNLOADING | Visually distinct from SYNCHRONISED — a unit leaving must not read as a unit merely running low. |
| Verdict band | N−1 firm from **committed** units. Mockup: 30.0 MW firm vs 38.5 MW design peak = shortfall. From installed it would read 60 MW and appear covered. |
| Committed capacity row | Excludes STARTING; sub-label says so explicitly. |
| Reserve floor row | Demand + largest committed unit, with the arithmetic shown in the sub-label. |
| Utilisation scale | Position against **both** thresholds (decommit 50%, commit 80%) visible at a glance. |
| Blocked panel | `blocked_by` and `last_decision_reason` shown together, so "satisfied" and "constrained" are distinguishable. |
| Marginal-unit ramp | Clamped to headroom, with the headroom stated in the sub-label. |
| Preserved | Verdict band, fleet table, operator Trip/Start, paralleling strip, dark/monospace/amber language. |

**One conformance case worth constructing deliberately.** The mockup's fleet state — 3 synchronised, 1 starting, 1 offline, utilisation 76.7%, reserve floor violated — demonstrates that the floor governs over the utilisation trigger. Build that state and confirm the panel renders it coherently: utilisation *below* the commit threshold while a commitment is nonetheless in progress. If the panel cannot express that, the commitment rows are not doing their job.

Report anything in the mockup that turns out to be wrong or unbuildable. It was drawn from the reference implementation's rules, not from the live engine, and it may be mistaken.

---

## Prohibited

- Recomputing the reserve floor in the summary block. Read it from `CommitmentDecision`.
- Including UNLOADING in `committed_rated_mw`, or excluding it from `on_bus_output_mw`.
- Clamping per-unit ramp to nameplate rather than headroom.
- Editing `test_I3_droop_*` — the §7.1.3.6 finding stands.
- Editing any other test assertion except TC-99b.
- Treating the mockup as a pixel target, or restyling the panel to match its layout.
- Adding a module-scope numeric constant to `panels/`.
- Emitting any payload key before its `types.ts` entry.
- Modifying `gridsignal_logger.py`.
- Proceeding past the Item 1–5 gate without reporting.

## Acceptance criteria

- [ ] `reserve_floor_mw` = demand + largest committed unit, read from `CommitmentDecision`; before/after values on a live tick reported.
- [ ] `reserve_satisfied` correct in sign — verified on both a lightly-loaded fleet with reserve and a heavily-loaded fleet without.
- [ ] `committed_rated_mw` uses `contributes_to_reserve`; field comments distinguish it from `on_bus_output_mw`.
- [ ] Per-unit ramp clamped to headroom; divisor counts on-bus units only.
- [ ] TC-99b updated to headroom clamping, with a near-rated case where the two bounds differ.
- [ ] `levelled_off` broadcasts the sustained predicate, matching the breaker-open gate.
- [ ] Backend assertion added: per-unit `output_mw` over `is_on_bus` sums to `on_bus_output_mw`, including a UNLOADING unit.
- [ ] Conformance reported per element as matches / differs / not implemented, with reasons.
- [ ] The 76.7%-utilisation floor-violated state built and rendered; result reported.
- [ ] Any mockup error reported.
- [ ] Guards D1, D2, D3, E Tier 1 green; `tsc --noEmit` clean.
- [ ] Suite reported against 15 / 974 / 16 xfailed and 29 frontend, every delta attributed.
