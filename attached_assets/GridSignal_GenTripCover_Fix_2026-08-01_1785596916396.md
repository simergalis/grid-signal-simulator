# GridSignal — Gen-Trip Cover Defect: Spec Addendum and Replit Change Set

**Scope:** one bounded change set. Corrects the permanently-pinned `GEN-TRIP COVER` readout on the Live Dashboard header strip.

**Why this is not only a code fix.** The tile displays a metric that has no definition anywhere in Forecast Engine Spec v2.5 — it is not in Section 7, not in Section 19, not in the Section 29 glossary. There is therefore nothing for the implementation to be correct *against*. Part 1 below supplies the definition; Parts 2–4 are the Replit prompts that implement it. Handing Replit only Parts 2–4 will produce a tile that changes state but still computes the wrong number.

---

## Part 0 — The three defects, separated

| # | Defect | Layer | Symptom |
|---|---|---|---|
| D-1 | `GEN-TRIP COVER` is binary, generation-only, and undefined | Spec + logic | Reads `cannot carry alone` on every tick of every scenario |
| D-2 | `DISPATCHABLE 24.0 MW` credits solar and ignores anchor reserve | Logic | Contradicts §7.1.1 and §7.1.2; overstates coverage by ~2.7 MW |
| D-3 | Demo plant is a single 20 MW turbine serving a 24 MW critical load | Config | No N−1 firm capacity exists, so D-1 can never read green regardless of D-1's fix |

D-1 and D-2 share the same root cause: the header strip computes coverage by summing nameplate figures rather than by evaluating the contingency. Fix them together. D-3 is independent and can land in either order.

---

## Part 1 — Spec addendum (author this into v2.6 before implementing)

### Proposed § 7.4 — Contingency coverage and the gen-trip readout

Sections 7.2 and 7.3 size the fleet against a *predicted* step-load, where Δt_lead gives the turbine a head start and the BESS bridges a declining wedge. That is a demand-side event with warning. This subsection covers the supply-side event without warning: the loss of the largest online dispatchable unit, at Δt_lead = 0.

The two cases are not interchangeable and a fleet sized for one is not thereby sized for the other. The Section 7.2 check asks whether the BESS can bridge a gap that closes on its own as the turbine ramps. The contingency check asks whether the gap closes at all.

**Contingency selection.** The contingency is the loss of the single online dispatchable unit with the greatest current output. Non-dispatchable supply is excluded from selection and handled as its own event class under 7.1.1, which is a distinct contingency with the same Δt_lead = 0 property.

**The instantaneous deficit.** At the moment of trip, load is unchanged and the tripped unit's output vanishes:

```
P_deficit_0 = P_output(tripped_unit)
```

**Surviving ramp capability.** Remaining online units close the deficit at their configured, re-rated ramp rates (§27.2), bounded by their remaining headroom:

```
P_headroom_surviving = Σ (P_rated_i − P_output_i)   over surviving online units
r_surviving          = Σ r_asset_i                  over surviving online units
```

Hot-standby units that are not synchronized do not count toward `r_surviving`. Their start time is a separate quantity and must not be folded into a ramp rate, for the same reason §7.2 step 4 forbids comparing an energy-like product to a duration.

**The two tests, kept separate.**

*Power test.* Can the BESS carry the deficit at the instant of trip, at its anchor-adjusted capability (§7.1.2)?

```
power_test_passes := BESS_bridging_available ≥ P_deficit_0
```

*Energy test.* Does the BESS have the stored energy to sustain the declining deficit until surviving units close it? The deficit declines linearly at `r_surviving`, so time-to-close is `t_close = P_deficit_0 / r_surviving` and the energy required is the area under that wedge:

```
E_required = 0.5 × P_deficit_0 × t_close
energy_test_passes := E_usable_BESS ≥ E_required
```

`E_usable_BESS` is usable state of charge less the energy reserved for anchor duty, not nameplate capacity.

**Closability.** If surviving headroom cannot reach the deficit, no amount of BESS energy closes it — the wedge never returns to zero and the site is on a countdown to shed:

```
closable := P_headroom_surviving ≥ P_deficit_0
```

**Shed requirement.** Where the deficit is not closable, curtailment (§23) is the remaining term, and the readout states it rather than reporting bare failure:

```
P_shed_required = max(0, P_deficit_0 − P_headroom_surviving)
```

**Ride-through duration.** Where coverage fails, the operator-relevant quantity is how long they have:

```
t_ride_through = E_usable_BESS / P_deficit_0        (approximate; exact where non-closable)
```

**Readout states.** Three, and each carries figures:

| State | Condition | Example readout |
|---|---|---|
| `COVERED` | power ∧ energy ∧ closable | `covered · 6.9 MW deficit · closes in 35 s` |
| `COVERED WITH SHED` | ¬closable, and `P_shed_required` is within curtailable capacity | `needs 3.1 MW shed · 41 s ride-through` |
| `CANNOT CARRY` | ¬closable, and `P_shed_required` exceeds curtailable capacity | `22.6 MW uncovered · 9 s ride-through` |

**Two constraints on the readout, both of which the current implementation violates.**

First, the readout is quantitative on every tick. Section 7.2 step 4 already requires the insufficient-reserve alert to identify the shortfall "in MW and seconds," and there is no principled reason the contingency readout should meet a lower bar than the forecast one.

Second, a state that cannot change is not a readout. Where the plant configuration makes one state permanent — a single-unit fleet, in which N−1 firm generation is zero by construction — that fact belongs to the plant configuration view, not to a live header strip. An operator learns within one shift to stop reading a tile that never moves, which is the precise failure mode a contingency indicator must not have.

### Proposed § 7.5 — Dispatchable capacity, stated correctly

The header `DISPATCHABLE` figure shall be the sum of online turbine capacity and anchor-adjusted BESS bridging capability. It shall not include non-dispatchable renewable output, per 7.1.1: solar reduces the load the fleet must serve but may never be credited toward closing a gap. Nor shall it include the portion of BESS capability committed to anchor duty, per 7.1.2.

Renewable output is displayed as a separate, separately-labelled term. Summing it into a figure captioned "dispatchable" is the specific arithmetic error 7.1.1 exists to prevent, and a dashboard that commits it teaches operators the wrong model of their own plant.

### Proposed § 16.14 — Acceptance: contingency coverage (§7.4, §7.5)

| **ID** | **Scenario** | **Input** | **Expected result** |
|---|---|---|---|
| TC-77 | Deficit is output, not nameplate | Largest online unit rated 7 MW, currently producing 4.2 MW; unit trips | `P_deficit_0` = 4.2 MW. The 7 MW rating does not appear in the deficit arithmetic |
| TC-78 | Power and energy tests are independent | BESS with ample power rating and depleted state of charge; deficit within its power capability | Power test passes, energy test fails. State is not `COVERED`. The two results are reported separately, not collapsed into one verdict |
| TC-79 | Anchor duty reduces both tests | Same contingency run twice, once grid-following and once with the BESS as islanded anchor | Anchor run reports strictly lower bridging capability and strictly shorter ride-through. Neither test uses rated capacity |
| TC-80 | Non-closable deficit states the shed | Surviving headroom 2.0 MW against a 6.0 MW deficit | State `COVERED WITH SHED` or `CANNOT CARRY` per curtailable capacity, reporting `P_shed_required` = 4.0 MW. Not a bare failure string |
| TC-81 | Solar is excluded from the contingency arithmetic | Contingency evaluated with 1.69 MW of solar producing | Solar reduces served load but contributes zero to coverage, ride-through, or the closability test |
| TC-82 | `DISPATCHABLE` excludes solar and anchor reserve | Header figure computed with solar producing and BESS holding anchor duty | Figure equals online turbine capacity plus anchor-adjusted BESS bridging only. Solar is displayed as a separate labelled term |
| TC-83 | Hot standby is not a ramp rate | Fleet with one synchronized unit and one hot-standby unit; contingency evaluated | Standby unit contributes zero to `r_surviving`. Its start time is reported separately and is not folded into the ramp arithmetic |
| TC-84 | State transitions during a run | Scenario in which a second unit is taken offline mid-run | Readout transitions `COVERED` → `COVERED WITH SHED` on the tick the fleet state changes, with updated figures. Transition is logged |
| TC-85 | Re-rated assets counted at re-rated capability | Surviving unit carries an applied re-rating per §27.2 | Closability and `t_close` use the re-rated ramp rate, consistent with TC-58 |

---

## Part 2 — Replit prompt: coverage engine (D-1, D-2)

> **Phase GT-1 — Contingency coverage computation**
>
> Implement contingency coverage per Forecast Engine Spec §7.4 and §7.5. This replaces the current header-strip logic that produces the `GEN-TRIP COVER` and `DISPATCHABLE` values.
>
> Add a pure function — no I/O, no clock access, no simulation state mutation — with this shape:
>
> ```python
> def evaluate_contingency(plant_state: PlantState) -> ContingencyCoverage:
>     ...
> ```
>
> `ContingencyCoverage` is a frozen dataclass carrying, at minimum: `tripped_unit_id`, `deficit_mw`, `headroom_surviving_mw`, `r_surviving_mw_per_s`, `bess_bridging_available_mw`, `bess_usable_energy_mwh`, `power_test_passes`, `energy_test_passes`, `closable`, `time_to_close_s`, `shed_required_mw`, `ride_through_s`, and `state` as an enum of `COVERED | COVERED_WITH_SHED | CANNOT_CARRY`.
>
> Required behaviors:
>
> 1. Contingency selection is the online dispatchable unit with the greatest **current output**, not the greatest rating. Solar and other non-dispatchable sources are never selection candidates.
> 2. `deficit_mw` is the tripped unit's current output.
> 3. `bess_bridging_available_mw` is `min(rated, usable_soc_power) − P_anchor_reserve`, per §7.1.2. When the site is grid-following, `P_anchor_reserve` is zero; when islanded with the BESS as anchor, it is the configured value. Read the anchor role from power-management state, not from static config.
> 4. Power test and energy test are computed and reported independently. Do not collapse them into a single boolean before they reach the return value.
> 5. Surviving ramp rate sums only **synchronized online** units. Hot-standby units contribute zero.
> 6. Where `closable` is false, compute `shed_required_mw` and compare it against currently curtailable capacity per §23.2 to choose between `COVERED_WITH_SHED` and `CANNOT_CARRY`.
> 7. Surviving units are counted at their **re-rated** ramp rates where a re-rating is applied, consistent with TC-58.
>
> Separately, correct the `DISPATCHABLE` header figure: it is online turbine capacity plus anchor-adjusted BESS bridging capability. It excludes solar entirely and excludes the anchor-reserved portion of the BESS. Return renewable output as a distinct field so the UI can label it separately.
>
> **Acceptance:** pytest cases implementing TC-77 through TC-83 and TC-85 pass. Each test asserts on named fields of `ContingencyCoverage`, not on rendered strings. `evaluate_contingency` is deterministic: called twice with an identical `PlantState`, it returns equal values.

---

## Part 3 — Replit prompt: header strip render (D-1 display half)

> **Phase GT-2 — Quantitative gen-trip readout**
>
> Replace the binary `cannot carry alone / if gen trips` header tile with a quantitative readout driven by `ContingencyCoverage` from Phase GT-1.
>
> - Recompute and re-render on every tick, not on state change only. The figures move continuously with state of charge, load, and fleet state even when the enum does not.
> - Each state renders with numbers. `COVERED` shows deficit and time-to-close. `COVERED_WITH_SHED` shows shed-required and ride-through. `CANNOT_CARRY` shows uncovered MW and ride-through. No state renders as a bare adjective.
> - Colour follows state; the numeric line is present in all three.
> - Log every state transition with a timestamp and the triggering plant-state change, so the transition is available to the run record and to Section 21.2 error attribution.
> - Add the separated `RENEWABLE` term to the strip alongside `DISPATCHABLE`, labelled as non-firm.
>
> **Acceptance:** TC-84 passes. In a scenario where a unit is taken offline mid-run, the tile transitions within one tick and the numeric fields update on ticks where no transition occurs. A run against an unchanged plant state produces an unchanged enum with continuously varying figures.

---

## Part 4 — Replit prompt: demo plant configuration (D-3)

> **Phase GT-3 — Realistic demo fleet**
>
> The `demo-20mw` plant configures a single gas turbine against a ~24 MW critical load. No islanded AI site of this class is built that way, and it makes N−1 firm capacity zero by construction — so the Phase GT-1 arithmetic, however correct, can only ever report failure.
>
> Reconfigure the demo plant to a fleet: **5 units × 7 MW rated, 4 synchronized online at baseline, 1 hot standby.** This gives 28 MW online against a 23.95 MW load, N−1 firm of 21 MW, and a baseline state of `COVERED_WITH_SHED` or `COVERED` depending on the BESS figures below — which is a demo that has somewhere to go.
>
> Also revisit the BESS sizing. The current configuration shows 2.30 MW output with 1.0 MW of anchor reserve, which is sized for the §7.2 ramp-bridging case and is roughly an order of magnitude short of the contingency case at this site. Add BESS rated power and rated energy as explicit, separately-configurable scenario parameters rather than deriving them, so the two sizing cases can be demonstrated against each other.
>
> Add two scenario stressors:
> - `unit_maintenance` — takes one online unit offline, dropping N−1 firm and flipping the readout one state.
> - `unit_trip` — trips the largest online unit, exercising the coverage path live rather than hypothetically.
>
> **Acceptance:** `demo-20mw` opens in a non-failing contingency state. `unit_maintenance` produces a visible state transition mid-run. `unit_trip` produces an actual dispatch response whose observed behavior matches the `ContingencyCoverage` figures reported immediately before the trip, within the tick resolution.

---

## Part 5 — What to check after the change lands

The tension between `READY — all systems armed and dispatchable` and the contingency readout is real and should survive the fix rather than be smoothed away. Readiness answers *can I stage the forecast load*; contingency coverage answers *can I survive losing my largest source*. Both can be true at once and an operator needs both. If the fix makes the two tiles agree in all cases, something has been over-collapsed.

One property of the current demo config is worth preserving deliberately: the BESS holds the anchor, not the turbine. A turbine trip is therefore a power event, not a loss of the island's voltage and frequency reference. Had the turbine been the anchor, the same trip would take the reference with it — a categorically worse failure that §7.1.2 already distinguishes and that the console does not currently make legible. Consider whether the anchor assignment belongs on the header strip too; a microgrid engineer in an investor meeting will look for it.
