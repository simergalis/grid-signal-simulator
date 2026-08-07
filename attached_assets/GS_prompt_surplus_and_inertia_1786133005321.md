# Surplus disposal, inertia basis, then rerun S9

**Follows:** S9 rerun at catalogued values. Collapsed at tick 1 on over-frequency from solar surplus.
**Baseline:** 14 failed / 988 passed / 16 xfailed.
**Scope:** Items 1–3 are engine work. Item 4 reruns S9. Items 5–6 are corrections.

The rerun did its job — it collapsed, and it collapsed for a reason worth having. The report is accurate about the mechanism and honest about what the invariants did and did not prove.

Two things it did not conclude, and one correction I owe.

**My scenario JSON is partly at fault.** `solar_rated_mw: 15.0` with `irradiance_steps: [[0.0, 1.0]]` puts full solar at t=0 against an 800-node base job ramping from zero over 120 s. Fifteen megawatts of generation against 0.087 MW of load. That opening condition is unrealistic and it is mine, not the engine's.

**But fixing it only postpones the collapse.** The report's own table shows net demand back at 0.00 MW from t ≈ 2340 s with 15 MW of solar still generating. Protection thresholds plus no surplus disposal means an OF trip at the first surplus tick, whenever it arrives. **The protection layer is currently unusable in islanded mode with solar**, so F-1 is a prerequisite rather than a deferred finding.

---

## Item 1 — Surplus disposal (F-1)

Implement **Option 2 from your own analysis**: inverter frequency-response curtailment.

When `island_mode == ISLANDED` and frequency rises above `of_warning_hz`, curtail renewable output toward load rather than letting the surplus drive the swing equation. This is what a real grid-forming inverter does, it is consistent with IEEE 1547-2018 §6.5.2, and it is the lighter of the two changes.

Requirements:

- Curtailment is **proportional and frequency-driven**, not a hard clamp to load. A step from full output to exactly load is itself a disturbance. Curtail as a function of frequency deviation above `of_warning_hz`, saturating at full curtailment by `of_trip_hz`.
- The curtailed quantity is **reported**, not silently discarded — `p_renewable_curtailed_mw` on `TickResult` and in the payload, `types.ts` entry first.
- Any constant introduced goes in the catalogue with honest provenance. If the curtailment gain has no measured basis, it is `CHOSEN`.

**Do not implement BESS charging in this session.** Option 1 is the larger change and needs its own decision; report what it would require and leave it.

## Item 2 — Inertia is computed against machines that are not connected

From the collapse trace:

> `S_base = max(1.0, 5 × 15.0) / 0.85 = 88.24 MVA` — *uses all turbines in state, not just on-bus*

At tick 1 every turbine is OFFLINE or STARTING. **There is no rotating inertia at all**, yet the swing equation runs as though 75 MW of machines were spinning. That credits inertia which does not exist — structurally the same error as crediting STARTING units toward reserve, which §7.1.3.7 exists to prevent.

Report first, then fix:

1. Every computation of `S_base`, with `file:line`, and which turbine set each uses.
2. What governs island frequency when **no** synchronous machine is on the bus. The grid-forming BESS anchors the island; its frequency is set by an inverter control law, not by a swing equation over absent machines. State what the engine currently does in that case.
3. Whether the BESS contributes synthetic inertia, and whether that is represented anywhere.

Then base `S_base` on **on-bus synchronous capacity**. For the zero-machine case, state what you propose — inverter-anchored frequency is a different model, and it may be that the swing equation should not run at all. **Report the proposal before implementing that branch.**

## Item 3 — Two arithmetic corrections in the report

**F-2's maximum absorbable step is wrong by 5×.** The report gives:

```
Max step = 2.0 × (2 × H × S_base) / f₀ = 23.53 MW
```

That solves for `df/dt = 2.0 Hz/s`, which over a 5 s tick is 10 Hz — not the 2.0 Hz margin to `of_trip_hz`.

Using the report's own per-tick method — 2.101 MW gives 0.893 Hz per tick — the step producing 2.0 Hz in one tick is **≈ 4.7 MW**. The dn1 events at 2.101 MW are therefore **45% of the limit, not 9%**.

Recompute, and restate the F-2 conclusion. "Not a risk" and "roughly half the margin" are different findings, and the second one belongs in the spec.

**Tick resolution is too coarse for frequency.** Δf of 6.33 Hz in a single tick, against IEEE 1547 trip times of 0.16 s, means protection is being evaluated at a resolution far coarser than the phenomenon it models. Record this as a known limitation with its consequence: the engine can only detect a threshold crossing to within one tick, and a transient shorter than 5 s is invisible. **Do not change the tick interval** — report the limitation.

---

## Item 4 — Rerun S9

After Items 1–2 land.

**Correct the irradiance profile.** Solar must not exceed load at t=0. Either start irradiance low and rise (a dawn ramp over the first few minutes), or reduce `solar_rated_mw`, or establish the base load before solar arrives. State which you chose and why.

Everything else stays at catalogued values. No overrides.

**Report, whatever happens:**

- Whether the island survived, and if not, the tick, stage, frequency, demand, generation and mechanism.
- Peak renewable curtailment and total curtailed energy.
- Peak over-frequency during the down-ramp phases, against the corrected F-2 limit.
- Time from reserve-floor breach to first unit on-bus, against `cold_start_s` — the F-3 gap, now measured rather than analytical.
- All nine invariants, with which were substantive and which vacuous.
- Full per-tick CSV; path and row count.

**A collapse is still a result.** But if the run survives to the down-ramp, F-2 and F-3 finally get real data instead of analysis.

---

## Item 5 — Protection thresholds are unreachable from a scenario

The report found that the five threshold fields have no `ScenarioSpec` fields and no `scenario_factory` pass-through, so they can only be set from the Python test API.

That makes the black-box scenario not black-box: it cannot be run with protection enabled through `/scenarios`, which is the contract surface a third party uses.

Add the five threshold fields to `ScenarioSpec` as `Optional[float] = None`, pass them through `from_spec_data()`, and document them in the reference. `None` continues to mean disabled, so every existing scenario is unaffected.

## Item 6 — Attribute the +1 suite failure

`test_step16_wiring.py::test_network_telemetry_returns_required_fields_for_active_run` appeared this session and was recorded as *"pre-existing or flaky."* That is unattributed.

Run it ten times. If it is flaky, say so and report the failure rate. If it is deterministic, find what changed. The baseline is what every subsequent gate is measured against and it cannot carry an unexplained entry.

---

## Prohibited

- Overriding `r_asset_mw_per_s`, `inertia_constant_s`, `p_min_stable_frac`, `ramp_seconds`, `t_min_run_s`, `t_min_down_s`, or any start time.
- Implementing BESS charging — report what Option 1 would require.
- Implementing the zero-machine frequency branch before reporting the proposal.
- Changing the tick interval.
- Curtailing renewables with a hard clamp to load rather than a frequency-proportional response.
- Discarding curtailed energy without reporting it.
- Writing any new constant as a code literal.
- Treating a collapse as a test failure.
- Emitting `p_renewable_curtailed_mw` before its `types.ts` entry.
- Modifying `gridsignal_logger.py`.

## Acceptance criteria

- [ ] Frequency-proportional renewable curtailment implemented; gain catalogued with honest provenance.
- [ ] `p_renewable_curtailed_mw` on `TickResult` and payload; `types.ts` entry precedes emission.
- [ ] Option 1 (BESS charging) requirements reported, not implemented.
- [ ] Every `S_base` computation reported with `file:line` and turbine set.
- [ ] `S_base` based on on-bus synchronous capacity; zero-machine proposal reported before implementation.
- [ ] Whether the BESS contributes synthetic inertia stated.
- [ ] F-2 recomputed; conclusion restated against the ≈4.7 MW per-tick limit.
- [ ] Tick-resolution limitation recorded with its consequence.
- [ ] S9 rerun with a corrected irradiance profile; choice stated.
- [ ] Survival, curtailment, peak OF, F-3 gap, all nine invariants, and the CSV reported.
- [ ] Five threshold fields on `ScenarioSpec` with factory pass-through; `None` = disabled preserved.
- [ ] `test_network_telemetry_...` attributed — flaky with a rate, or deterministic with a cause.
- [ ] Suite reported against 14 / 988 / 16 xfailed, every delta attributed.
