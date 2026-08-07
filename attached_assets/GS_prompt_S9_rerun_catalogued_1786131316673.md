# S9 — rerun at catalogued values and let it collapse

**Follows:** Protection layer implemented; S9 built and passing 10/10.
**Baseline:** 13 failed / 988 passed / 16 xfailed; `tsc --noEmit` clean.
**Scope:** the protection layer stays. The scenario is rebuilt. No new features.

The protection layer is good work — IEEE 1547-2018 Cat I values at 60 Hz, `Optional[float] = None` so disabled scenarios are untouched, collapse metadata on `TickResult`, plane separation clean. Keep all of it.

The scenario built to exercise it is the problem, and the debugging chronicle says why in its own words.

---

## What went wrong

Four parameters were overridden to reach ten green assertions:

| Override | S9 value | Catalogued | Factor |
|---|---|---|---|
| `r_asset_mw_per_s` | **100.0** | 0.2 | **500×** |
| `inertia_constant_s` | **100.0** | 4.0 (report says real GTs ≈5 s) | 20–25× |
| `p_min_stable_frac` | **0.0** | 0.40 (Phase E, all 23 scenarios) | disabled |
| `GPUModule.ramp_seconds` | **1.0** | 120.0 | disabled |

`r_asset = 100 MW/s` takes a 15 MW machine from zero to rated in **0.15 seconds**. The report describes it plainly: *"effectively instant dispatch"*, *"eliminate ramp-induced OF during phase transitions entirely"*.

Every one of these appears on the prompt's prohibited list. The result is ten assertions passing against a plant with no ramp constraint, no minimum stable load and twenty times physical inertia — so §7.1.3, nine sessions of work, is switched off inside the scenario written to exercise it.

**Three real defects were found and then suppressed.** The chronicle is honest and the diagnostics are sound; each entry is a genuine result treated as an obstacle. They are the substance of this session.

---

## Item 1 — Rerun S9 at catalogued values

Restore, from `site_parameters`, with no scenario override:

- `r_asset_mw_per_s` = 0.2
- `inertia_constant_s` = 4.0
- `p_min_stable_frac` = 0.40
- `GPUModule.ramp_seconds` = 120.0
- `t_min_run_s` = 1800, `t_min_down_s` = 900, start times per thermal state

**Expect it to collapse. That is the deliverable.** Report the tick index, the stage crossed, the frequency at collapse, the demand and generation at that moment, and which of the three mechanisms below caused it.

Do not tune anything to prevent it. If a value must be changed, stop and report the reason instead.

## Item 2 — Fix the demand profile

The current events are four steps at t = 0 / 1800 / 3600 / 4800 with 8 / 52 / 22 / 2 nodes. That is not the specified profile.

Required: 8 MW → 60 MW over 15 min · hold 5 min · 60 → 30 MW over 10 min · 30 → 10 MW over 10 min · hold 50 min · end at 5400 s.

A schema-valid decomposition is supplied as `gridsignal_scenario_islanded_8_60_10.json`: an 800-node base job plus 26 staged 200-node jobs, ended last-on-first-off. Use it, or produce an equivalent and show the resulting draw at t = 0 / 900 / 1200 / 1800 / 2400 / 5395 s.

The 90-minute duration exists so `t_min_run_s` elapses on the last-committed unit and the release sequence falls inside the run. With the current four-step profile that reasoning no longer holds.

## Item 3 — Record the three suppressed findings

Each is a real result. Write each up with its trace, and state the disposition.

**F-1 — The BESS cannot charge, so islanded surplus has nowhere to go.**

> *"2 GTs at MSL (6 MW each) + solar (15 MW) = 27 MW > 23.7 MW demand → BESS can't absorb (`bess_output ≥ 0`) → OF collapse on tick 1."*

On an islanded site with a minimum stable load and solar, surplus is **structural** — it is UC-7, the plant output floor, arriving in practice. The correct responses are BESS charging or curtailment, and neither exists in the model.

Report: whether `bess_output_mw` can go negative anywhere; whether the curtailment ladder can act on surplus as opposed to shortfall; and what §7.1.3.6's "the surplus shall be reported, not silently discarded" currently resolves to at runtime. Propose the fix; **do not implement it.**

**F-2 — A large step-down causes over-frequency, because generation cannot back down.**

> *"phase-2c → phase-3 step-down (−31 MW) exceeded GT ramp limit; GT output stayed high for 3–4 ticks → massive OF spike → 62 Hz trip."*

This is the mirror of the §7.2 breaker-open finding and it is exactly what the down-ramp half of the scenario existed to reveal. At `r_asset = 0.2` the effect is far larger than at 0.5.

Report the peak over-frequency, its duration, and the maximum step-down the fleet can absorb without crossing `of_trip_hz`. That figure is a real operating limit and belongs in the spec.

**F-3 — Under-capacity collapses the island, and cold start decides whether it recovers.**

> *"3-GT capacity (45 MW) < phase-2b net demand (51 MW)… persistent 0.018 Hz/s UF drift → 57 Hz collapse."*

Report the time from the reserve floor being breached to collapse, and compare it against the start time of the unit that would have covered it. If the start time exceeds the time-to-collapse, the site cannot self-rescue from that state — which is the strongest argument the product has for acting on the scheduler signal.

## Item 4 — Two corrections

**The 60 Hz path is untested, not unaffected.** Item 4's earlier finding — *"zero existing tests are affected"* — is true because I3, I3b and B1a all pass `frequency_nominal_hz=50.0` explicitly. So the production default, the SDG&E frequency, has no coverage at all. From the suite, "unaffected" and "untested" are indistinguishable. Report which tests exercise 60 Hz; if none, say so.

**`S9_islanded_ramp_protection.json` is not schema-valid.** It uses `scenario_id`, `dt_s`, `duration_s`, `nodes`, `kw_per_node`, `ramp_s`, `breaker_closed`, `gt_mode`, and `start_time_s` as a dict — none of which exist in `ScenarioSpec`. It will not POST to `/scenarios`. Validate it against `scenario_spec_schema.json` and report the errors.

Note also: `scenario_spec_reference.md` documents `min_final_bess_soc` as taking `threshold_fraction`; the schema requires `threshold`. The documented example would be rejected.

---

## Assertions

Replace the current ten. **Assert invariants, not survival** — whether the island survives is the finding, not the pass condition.

1. No on-bus unit's output moves by more than `r_asset × dt` in one tick, except the breaker-open step from MSL to zero.
2. No SYNCHRONISED unit's **setpoint** is below its MSL.
3. At most one unit in STARTING; at most one in UNLOADING.
4. No loaded unit transitions directly to OFFLINE.
5. Per-unit `output_mw` sums to `on_bus_output_mw` every tick.
6. No unit released before `t_min_run_s` has elapsed since synchronisation.
7. Consecutive breaker-opens separated by at least the settle interval.
8. If frequency crosses a threshold, the corresponding stage fires and `collapse_reason` is set.
9. The run terminates either at 5400 s or on collapse — never silently.

A collapse satisfies these. A plant that cannot ramp does not.

## Trace

Emit the full per-tick CSV specified previously — demand, per-unit state and output and setpoint and MSL, fleet totals, commitment block, BESS, frequency and df/dt and collapse fields, accounting, contingency. Report the path and row count.

---

## Prohibited

- Overriding `r_asset_mw_per_s`, `inertia_constant_s`, `p_min_stable_frac`, `ramp_seconds`, `t_min_run_s`, `t_min_down_s`, or any start time.
- Pre-synchronising additional units to avoid a collapse.
- Adding, weakening or removing an assertion to make the run pass.
- Implementing BESS charging or curtailment. Report F-1; do not fix it.
- Editing the spec. Report F-2's operating limit.
- Treating a collapse as a failure.
- Modifying `gridsignal_logger.py`.

## Acceptance criteria

- [ ] S9 rerun at catalogued values with zero physics overrides; every parameter's source stated.
- [ ] Demand profile matches the specification; draw reported at the six checkpoints.
- [ ] Collapse — if it occurs — reported with tick, stage, frequency, demand, generation and mechanism.
- [ ] F-1 reported: whether `bess_output_mw` can go negative, whether curtailment acts on surplus, what the §7.1.3.6 surplus rule resolves to. Fix proposed, not implemented.
- [ ] F-2 reported: peak over-frequency, duration, and maximum absorbable step-down.
- [ ] F-3 reported: time-to-collapse against the covering unit's start time.
- [ ] 60 Hz test coverage reported; absence stated plainly if that is the answer.
- [ ] `S9_islanded_ramp_protection.json` validated against the schema; errors listed.
- [ ] Nine invariant assertions replace the previous ten; all evaluated.
- [ ] Full per-tick CSV emitted; path and row count reported.
- [ ] Suite reported against 13 / 988 / 16 xfailed, every delta attributed.
