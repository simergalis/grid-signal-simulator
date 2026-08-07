# 60 Hz default, then the frequency protection layer

**Follows:** Setpoint contradiction resolved, §7.2 claim withdrawn, droop clamp applied, protection layer diagnosed.
**Baseline:** 13 failed / 978 passed / 16 xfailed backend; 29 frontend; `tsc --noEmit` clean.
**Decision taken:** nominal frequency is **60 Hz**.
**Scope:** Item 1 is the frequency base change and it must land alone. Items 2–4 follow from it.

The protection diagnosis was thorough — three write sites found, zero thresholds anywhere in the engine, spec confirmed silent. One thing it surfaced without naming: the engine defaults to 50 Hz while the primary demo site is in SDG&E territory, which is 60 Hz. That has to be settled before any threshold is chosen, because every one of them scales with it.

---

## Item 1 — Change `frequency_nominal_hz` to 60.0 (blocking, lands alone)

`SiteConfig.frequency_nominal_hz` currently defaults to **50.0**. The droop trace confirms it: the divisor `0.04 × 50.0 = 2.0 Hz`.

The primary demo environment is an SDG&E territory San Diego site. North America is 60 Hz.

**This is not a cosmetic change.** `df/dt = f_nom × ΔP / (2H·S_base)` scales linearly with `f_nom`, so every frequency excursion in the model becomes 20% faster. RoCoF, droop response magnitude, and every derived frequency criterion move together.

Before changing anything, report:

1. `frequency_nominal_hz` with `file:line`, its default, and whether it is catalogued.
2. Every scenario fixture that sets it explicitly. If any already override to 60, the default was masking a split.
3. Every computation that reads it — the droop block, the swing equation, anything else — with `file:line`.

Then change the default to **60.0**, catalogue it if it is not already, and land it **in its own commit** with nothing else. It moves numbers across every islanded scenario, and mixing it with the protection layer would make the delta unattributable.

Report the suite delta and classify every moved test correct-or-incorrect. Expect movement in the frequency and balance-decomposition tests. **Edit none of them.**

## Item 2 — Re-derive the protection thresholds at 60 Hz

The proposed thresholds — 49.0 / 48.5 / 47.5 / 51.5 / 52.0 Hz — are **50 Hz-system values**, consistent with European grid codes. They were cited to IEEE 1547, which is a North American 60 Hz standard whose Category I trip settings sit near 56.5 / 58.5 / 61.2 / 62.0 Hz.

Citation and values described different systems. That is precisely the failure the provenance discipline exists to prevent: a `CHOSEN` figure wearing a standards reference that does not support it.

Re-derive at 60 Hz. For each threshold report the **actual clause** — standard, edition, table or section number — and the value it gives. Where IEEE 1547-2018 specifies a trip time alongside the frequency, report that too; a threshold without a time is not a protection setting.

Where the standard offers a range or leaves it to the interconnection agreement, say so and mark the value `CHOSEN` with the range noted. **Do not attach a citation that does not support the number.**

SDG&E will have its own interconnection requirements that may differ from the IEEE baseline. Note where that is likely and flag it for operator confirmation rather than guessing.

**Gate for Items 1–2: report before implementing anything in Item 3.**

---

## Item 3 — Implement the protection layer

Only after Items 1 and 2 are reported and the thresholds agreed.

**Bound the integration.** `simulation_core.py:1300` — `state._frequency_hz += _df_dt * dt_seconds` — is the only unbounded write of the three. It is what allows −24 Hz.

**Stages, at the Item 2 values:** under-frequency warning, UFLS load shed, island collapse; over-frequency warning, generation trip. Every threshold catalogued with its real provenance, read through `site_parameters`, never a literal.

**Collapse behaviour — a design decision, not an engine one.** The diagnosis proposed terminating the tick loop. That is what a real island does, but this is a simulator whose job is to show an operator what happened, and a run that simply stops tells them less than one that holds a visible terminal state.

**Implement the visible terminal state:** frequency frozen at the trip threshold, `island_collapsed: bool` on `TickResult` with the trip reason and the tick index at which it occurred, broadcast, and the loop halted after that final tick is delivered. The operator sees a plant that collapsed and why — not a feed that goes quiet.

Add a `types.ts` entry before the backend emits the field, per task #191.

**Do not wire frequency into the curtailment ladder in this session.** The diagnosis confirmed the ladder responds to a reserve-capacity gap and takes no frequency input. Making UFLS a ladder stage is a larger design question — report whether it should be, do not do it.

## Item 4 — Report the bearing on I3 and B1a

The diagnosis noted that at `of_trip_hz`, I3's 52 Hz scenario would itself be a trip condition — the island would not survive to the tick where the assertion fires. At 60 Hz nominal, 52 Hz is a 13% under-frequency excursion instead of an over-frequency one, so **the I3 scenario changes character entirely** under Item 1.

Report what I3 and I3b now exercise at 60 Hz nominal, whether the §7.1.3.6 MSL-floor finding still holds, and whether the fixtures were written against a 50 Hz assumption. The same question applies to B1a.

**Report only.** These are spec findings; the amendments are made elsewhere.

---

## Item 5 — Black-box scenario test with full trace

A new end-to-end acceptance test, run **after** Items 1–3 land, exercising the whole stack against a realistic islanded ramp.

### Scenario

| Element | Value |
|---|---|
| Generators | **5 × 15 MW**, hot standby (`hot_start_s` = 300 s), **1 SYNCHRONISED at t=0** at 8 MW |
| Solar | functional — **rated 15 MW** (PROTO-7: 0.25 × peak compute), clear-sky midday profile |
| BESS | demo unit — 18 MW / 8 MWh, grid-forming, SOC 1.0 at t=0 |
| Grid connection | **none — islanded throughout** (`IslandMode.ISLANDED`) |
| Frequency | 60 Hz nominal (Item 1) |
| `design_peak_load_mw` | set from the 60 MW compute peak plus cooling at that point |
| dt | 5 s |

**Build it as a new scenario spec** in `config/scenarios/`, driven by scripted `WorkloadSignal` events rather than the Kubernetes agent, so the demand profile is exact and the run is deterministic. Register it alongside the existing seeded scenarios. Name it for what it tests, not for this session.

**Fleet rating and thermal state are specified, not open.** 5 × 15 MW hot standby is the only combination in the table below that both exercises all five units and keeps BESS bridging inside the demo unit's 18 MW rating. Do not substitute another without reporting why.

Demand profile — GPU compute power:

| Window | Duration | Demand |
|---|---|---|
| t = 0 | — | 8 MW |
| 0 → 900 s | 15 min | 8 → 60 MW (ramp) |
| 900 → 1200 s | 5 min | 60 MW (hold) |
| 1200 → 1800 s | 10 min | 60 → 30 MW (ramp down) |
| 1800 → 2400 s | 10 min | 30 → 10 MW (ramp down) |
| 2400 → **5400 s** | **50 min** | 10 MW (hold) |
| t = 5400 s | — | end |

**90 minutes total; 1080 ticks at dt = 5 s.**

### Why the run is 90 minutes, not 45

The demand shape above is exactly as specified. Only the final hold is extended, and the reason is `t_min_run_s`.

**These reference figures assume no solar.** With 15 MW of solar the net dispatch requirement at the 60 MW peak drops to roughly 45 MW plus cooling, so the live commitment sequence will differ — likely one fewer unit, and later commits. Treat the timings below as the shape to expect, not values to match. The `t_min_run_s` arithmetic that drives the run length is unaffected, because it depends on the *last* sync time rather than on how many units committed.

Run against the reference §7.1.3 rules, hot standby, **no solar**, the commitment sequence is:

```
   0s  gt-1  offline      -> starting
 300s  gt-1  starting     -> synchronised
 360s  gt-2  offline      -> starting          (60 s settle interval)
 660s  gt-2  starting     -> synchronised
 720s  gt-3  offline      -> starting
1020s  gt-3  starting     -> synchronised
1080s  gt-4  offline      -> starting
1380s  gt-4  starting     -> synchronised      ← last commitment
3180s  gt-4  synchronised -> unloading         ← 1380 + t_min_run 1800
3185s  gt-3  synchronised -> unloading
3190s  gt-2  synchronised -> unloading
```

**At 45 minutes the run ends at 2700 s — 480 seconds before the first unit can be released.** Demand falls from 60 MW to 10 MW across the second half of the scenario and *nothing happens*: no decommitment, no unload, no breaker opening. The entire ramp-down portion tests nothing it was written to test.

Extending the final hold to 50 minutes puts the release sequence inside the run.

### The finding this exposes — expect it and report it

Demand reaches its floor of 10 MW at t = 2400 s. The first release is at t = 3180 s. **For 780 seconds the fleet holds four units on bus against a load that needs one, because `t_min_run_s` blocks release — not because dispatch wants them.**

That is correct behaviour under §7.1.3.3, and it is the kind of thing an operator will ask about. Report the over-commitment window explicitly: its duration, the surplus MW, and where that surplus goes.

Note also that in the reference the three releases fall 5 seconds apart, because sequential stops (D-09) postdate the reference implementation. **The live engine must space them by the settle interval.** If the trace shows three breakers opening within one or two ticks, the D-09 rule is not working — that is a discriminating check, not a cosmetic one.

### Why 5 × 15 MW hot standby

Run against the reference §7.1.3 rules, the profile gives:

| Fleet | Peak units on bus | Syncs in run | Peak BESS bridging |
|---|---|---|---|
| 5 × 15 MW, cold | 3 | 2 (t = 900 s, 1860 s) | **45.0 MW** |
| 5 × 15 MW, hot | 5 | 4 (300 / 660 / 1020 / 1380 s) | 16.1 MW |
| 5 × 25 MW, cold | 3 | 2 (t = 900 s, 1860 s) | **35.0 MW** |
| 5 × 25 MW, hot | 4 | 3 | 2.4 MW |

**Cold start makes the scenario infeasible.** At 900 s per start plus settle, only two units reach the bus in 45 minutes, and the second arrives at t = 1860 s — after demand has already been falling for eleven minutes. The BESS would have to carry 35–45 MW, which no BESS on a site this size can do. The reference figures assume an uncapped BESS; with a real 18 MW unit the load is simply unserved.

**Run hot-standby.** If you run cold as a second case, expect and report the unserved-load result rather than treating it as a failure — it is the correct answer, and the strongest available evidence for why start time dominates BESS sizing.

**Energy check before running:** peak bridging of ~16 MW against an 18 MW / 8 MWh unit is within power rating, but sustained discharge must stay within energy. Report BESS MWh delivered and minimum SOC. If SOC floors, the scenario has found a real sizing constraint — report it rather than resizing the BESS to make the run succeed.

### Trace — every variable, per tick, downloadable

Emit a CSV to `/mnt/user-data/outputs/` (or the equivalent retrievable path in this environment) and report the absolute path. One row per tick, with at minimum:

**Time** — `tick_index`, `sim_time_s`

**Demand** — `p_compute_mw`, `p_cooling_mw`, `p_total_mw`, `p_renewable_mw`, `net_demand_mw`, `p_dispatch_required_mw`, `p_dispatch_droop_mw`

**Per unit, all five** — `state`, `output_mw`, `setpoint_mw`, `msl_mw`, `time_to_online_s`, `thermal_state`, `levelled_off`

**Fleet** — `on_bus_output_mw`, `units_on_bus_count`, `committed_rated_mw`, `sub_msl_surplus_mw`, `ramp_capability_mw`

**Commitment** — `commitment_action`, `commitment_target_unit_id`, `reserve_floor_mw`, `reserve_satisfied`, `fleet_utilisation`, `pending_start_unit_id`, `commitment_blocked_by`, `commitment_reason`

**Storage** — `bess_setpoint_mw`, `bess_output_mw`, `bess_soc_fraction`, `bess_bridging_seconds`

**Frequency** — `frequency_hz`, `df_dt_hz_per_s`, `frequency_forcing_mw`, `droop_correction_mw`, `island_collapsed`, trip reason if any

**Accounting** — `asset_delivery_error_mw`, `balance_residual_mw`, `unserved_load_mw`

**Contingency** — `n1_state`, `n1_firm_mw`, `n1_deficit_mw`, `insufficient_reserve_alert`

Report the file path and row count. State plainly if any listed field does not exist rather than substituting a proxy.

### Assertions

Keep them behavioural, not numeric — the numbers are what the trace is for.

1. At most one unit in STARTING at any tick; at most one in UNLOADING.
2. No unit transitions from a loaded state directly to OFFLINE.
3. No on-bus unit's output moves by more than `r_asset × dt` in one tick — **except the breaker-open tick**, where output steps from MSL to zero. That discontinuity is real physics (§7.1.3.6) and must not be smoothed. Assert the exception explicitly rather than widening the tolerance.
4. No SYNCHRONISED unit's **setpoint** is below its MSL. Assert on the setpoint, not the output: a freshly-synchronised unit sits below MSL while it tracks up to the floor at `r_asset`, which is correct. If you assert on output you will fail on the ramp-in of every commitment.
5. Per-unit `output_mw` over on-bus units sums to `on_bus_output_mw` every tick.
6. Frequency stays within the Item 2 trip band, **or** `island_collapsed` is set with a reason.
7. Units commit before demand crosses the reserve floor, not after — report the lead time at each commitment.
8. No unit is released before `t_min_run_s` has elapsed since its synchronisation.
9. Consecutive breaker-opens are separated by at least the settle interval — **not** by one or two ticks.
10. At least one full commit-and-release cycle completes within the run. If none does, the run is too short and the timing needs revisiting rather than the assertions relaxing.

### What to report alongside the trace

- Every commitment and decommitment event with its tick, unit, and reason.
- Peak BESS discharge and total energy delivered.
- Minimum frequency reached, and whether any protection stage fired.
- Whether the island survived the run.
- Any tick with unserved load, and how much.
- Whether solar output materially changed the commitment sequence, against the no-solar reference above.
- BESS energy delivered and minimum SOC reached.
- The over-commitment window: from demand reaching its floor to the first release, with the surplus MW and where it went.
- Spacing between consecutive breaker-opens, against the settle interval.

**If the island collapses, that is a result, not a test failure.** Report the tick, the trip stage, and the demand at that moment. An islanded 5–50 MW site taking a 52 MW step in fifteen minutes is a genuinely demanding case, and knowing where it breaks is the point of running it.

---

## Prohibited

- Landing the 60 Hz change in the same commit as anything else.
- Choosing a threshold before Item 2's citations are reported.
- Attaching a standards citation that does not support the value. If it is `CHOSEN`, say so.
- Writing any threshold as a code literal.
- Wiring frequency into the curtailment ladder.
- Terminating the run without a visible collapsed state.
- Editing any test assertion or fixture.
- Emitting `island_collapsed` before its `types.ts` entry exists.
- Adding a module-scope numeric constant to `panels/`.
- Modifying `gridsignal_logger.py`.
- Proceeding past the Item 1–2 gate without reporting.

## Acceptance criteria

- [ ] `frequency_nominal_hz` reported with `file:line`, default, catalogue status, and every reader.
- [ ] Scenario fixtures setting it explicitly reported; any pre-existing 50/60 split named.
- [ ] Default changed to 60.0 in its own commit; suite delta reported and every moved test classified.
- [ ] Each protection threshold re-derived at 60 Hz with standard, edition, and clause cited — or marked `CHOSEN` with the range.
- [ ] Trip times reported alongside frequencies.
- [ ] SDG&E interconnection divergence flagged where likely.
- [ ] Integration at `simulation_core.py:1300` bounded.
- [ ] Thresholds catalogued, read through `site_parameters`.
- [ ] `island_collapsed` implemented as a visible terminal state with trip reason and tick index; `types.ts` entry precedes emission.
- [ ] Curtailment-ladder question reported, not implemented.
- [ ] I3, I3b and B1a re-characterised at 60 Hz; whether their fixtures assumed 50 Hz stated.
- [ ] Scenario registered in `config/scenarios/` with scripted workload events; deterministic across two runs.
- [ ] Fleet 5 × 15 MW hot standby, solar 15 MW, BESS 18 MW / 8 MWh, islanded, 60 Hz, dt 5 s.
- [ ] `design_peak_load_mw` set and reported.
- [ ] BESS MWh delivered and minimum SOC reported; SOC floor reported as a finding if reached.
- [ ] Full per-tick CSV trace emitted; path and row count reported; missing fields named rather than proxied.
- [ ] All eight behavioural assertions evaluated; failures reported, not accommodated.
- [ ] Commitment lead time reported at each commit event.
- [ ] At least one full commit-and-release cycle observed within the run.
- [ ] Over-commitment window reported with duration and surplus.
- [ ] Breaker-open spacing checked against the settle interval.
- [ ] Island survival, minimum frequency, peak BESS, and any unserved load reported.
- [ ] Guards D1, D2, D3, E green; `tsc --noEmit` clean.
- [ ] Suite reported against 13 / 978 / 16 xfailed, every delta attributed.
