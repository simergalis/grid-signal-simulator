# Replit Agent Prompt — NAR-001 Phase A′: Invariant Residual Harness

**Scope:** an offline, read-only analysis harness over persisted run data. It does not touch the tick loop, the API, the frontend, or any model. It produces a report.

Paste everything below the line.

---

## TASK

Build a standalone harness that recomputes six identities against persisted run telemetry and reports the **residual magnitudes**, then produce a report from it.

This is not a fix task and not a test-suite task. Nothing in `core/`, `runtime/`, `renewable/`, or `frontend/` is modified.

**New files, all under a new directory:**
- `tools/invariants/harness.py` — the checkers
- `tools/invariants/load.py` — reads persisted runs
- `tools/invariants/report.py` — emits the report
- `tests/test_invariant_harness.py` — TC-110…TC-117
- `reports/NAR-001_invariant_residuals.md` — the output report
- `reports/NAR-001_residuals.jsonl` — per-tick residuals

Four parts, with a hard stop after Part 1.

---

## PART 1 — Schema and run inventory, then stop

Report in chat. Write no code yet.

1. **`run_timeseries` schema.** Full column list with types, from `SIM/runtime/persistence.py`. State plainly whether each tick is stored as typed columns, as a JSON blob, or a mix. If it is a blob, give the exact serialisation used and whether it matches `_tick_result_to_dict()` output key-for-key.

2. **Available runs.** For each persisted run: `run_id`, scenario identifier, tick count, first and last `sim_time_seconds`, and island mode. Flag any run with fewer than 100 ticks.

3. **Field availability.** For the field list in Part 2 below, confirm each name **against the NAR-001 inventory sections cited**, not against my transcription — I may have copied a name wrong. Report any field where my name and the inventory disagree, and any field that is not persisted even though it is on the wire.

4. **BESS energy fields.** Inventory §C.7 lists BESS rated MW, usable MWh, unit count, and anchor reserve under a heading rather than as separate blocks. Give the exact field names and say whether usable energy is persisted per tick or is configuration only. I5 depends on this.

Then **stop and wait**.

---

## PART 2 — The six checkers

Each checker takes one persisted tick (and, for I5, the previous tick) and returns a residual, not a verdict.

### Field names — confirm before use

| Purpose | Wire/persisted field | Optional? | Inventory ref |
|---|---|---|---|
| Total generation | `p_generation_mw` | no | C.9 |
| Total demand | `p_demand_mw` (wire alias `p_total_mw`) | no | B.3 |
| System's own balance defect | `d4_balance_defect_mw` | no | I table |
| PCC flow | `grid_exchange_mw` | no | C.13 |
| Frequency forcing | `frequency_forcing_mw` | no | C.13 |
| Asset delivery error | `asset_delivery_error_mw` | no | C.13 |
| Turbine fleet output | `turbine_output_mw` | no | C.1 |
| BESS output | `bess_output_mw` | no | C.4 |
| Renewable output | `p_renewable_mw` | no | E.1 |
| Served / unserved | `p_served_mw`, `p_unserved_mw` | **yes — null outside UFLS path** | B.5 |
| Compute block | `p_compute_demand_mw`, `p_compute_served_mw`, `p_compute_unserved_mw` | **served/unserved yes** | B.1, B.5 |
| Cooling block | `p_cooling_demand_mw`, `p_cooling_served_mw`, `p_cooling_unserved_mw` | **served/unserved yes** | B.2, B.5 |
| Per-unit turbines | `turbine_units[].output_mw`, `.rated_mw`, `.state` | no | C.1 |
| BESS SoC | `bess_soc_fraction` | no | C.5 |
| Commitment | `commitment_block.committed_rated_mw`, `.reserve_floor_mw`, `.reserve_satisfied`, `.action`, `.utilisation` | no | C.10 |
| Cooling rating | `rated_cooling_mw` | no | F.1 |
| Kube | `kube_metrics.active_jobs`, `.admitted_nodes`, `.node_count` | **yes — null when kube_config absent** | A.3–A.5 |
| Time | `sim_time_seconds` | no | G.1 |

### I1 — Power balance, and does the system's own defect figure agree?

```
residual_i1 = p_generation_mw + grid_exchange_mw - p_demand_mw
delta_vs_declared = residual_i1 - d4_balance_defect_mw
```

Report both. `delta_vs_declared` is the more interesting number: it says whether an independent recomputation agrees with the system's own declared balance defect. Do not assume `d4_balance_defect_mw` is defined with the same sign convention — determine the sign empirically from the data and state which convention you found.

### I2 — Attribution (corrected)

Two distinct checks; do both, report separately.

```
residual_i2a = (turbine_output_mw + bess_output_mw + p_renewable_mw) - p_generation_mw
residual_i2b = p_compute_demand_mw - (admitted_nodes * kw_per_node / 1000.0)
```

I2a is supply summation. I2b is the job-attribution identity — compute demand against the node power that is supposed to produce it. `kw_per_node` comes from the hardware profile; report where you read it from and whether it is per-run constant. **If `kube_metrics` is null, I2b is not evaluable — skip, do not substitute zero.**

### I3 — Tri-field, per block

```
residual_i3_site    = (p_served_mw + p_unserved_mw) - p_demand_mw
residual_i3_compute = (p_compute_served_mw + p_compute_unserved_mw) - p_compute_demand_mw
residual_i3_cooling = (p_cooling_served_mw + p_cooling_unserved_mw) - p_cooling_demand_mw
```

All three depend on Optional fields. See the null rule below.

### I4 — Asset rating

Per turbine unit: `output_mw - rated_mw`, reported only where positive. Plus `p_cooling_demand_mw - rated_cooling_mw`, reported only where positive. Report the maximum exceedance per run and the tick at which it occurred.

### I5 — Storage energy

Between consecutive ticks:

```
energy_from_soc_mwh   = (soc[t-1] - soc[t]) * bess_usable_mwh
energy_from_power_mwh = bess_output_mw[t] * dt_s / 3600.0
residual_i5           = energy_from_soc_mwh - energy_from_power_mwh
```

`dt_s` from consecutive `sim_time_seconds`, not from an assumed tick rate. If `bess_usable_mwh` is configuration rather than per-tick, read it once per run and say so. If it is absent entirely, report `ΔSoC` and `∫P dt` as two separate series and mark I5 partially evaluable.

### I6 — Fleet capacity and reserve floor reconstruction

```
on_bus         = [u for u in turbine_units if u.state == 'synchronised' and not u.hot_standby]
recomputed_floor_mw     = p_demand_mw + max(u.rated_mw for u in on_bus)
recomputed_committed_mw = sum(u.rated_mw for u in on_bus)
residual_floor          = recomputed_floor_mw - commitment_block.reserve_floor_mw
residual_committed      = recomputed_committed_mw - commitment_block.committed_rated_mw
reconstructed_floor_violated = recomputed_committed_mw < recomputed_floor_mw
agreement = (not reconstructed_floor_violated) == commitment_block.reserve_satisfied
```

`floor_violated` is not persisted (inventory Q3), so this reconstructs it. Report every tick where `agreement` is false — those are ticks where the wire and an independent recomputation disagree about reserve. Also report every tick where `reserve_satisfied` is false alongside `action == 'hold'`.

Confirm the `hot_standby` field name and the exact `state` string for on-bus units before relying on either. Report what you find.

### The null rule — this is the one that will produce a false defect report if you get it wrong

Several fields are `Optional` and are null on entire code paths: `p_served_mw`, `p_unserved_mw`, the four per-block served/unserved fields, `kube_metrics`, `contingency_coverage`, `p_expected_mw`.

**Null means NOT EVALUABLE.** Record the tick as skipped with the reason and the field name. Never coerce null to `0.0`, never treat a null block as a zero residual, never let a null propagate into arithmetic. A harness that coerces nulls will report the entire non-UFLS portion of every run as a massive tri-field violation, and that report will be wrong.

Every invariant reports three counts per run: evaluated, skipped, and — separately — the reason breakdown for skips.

### No tolerances, no verdicts

Do not define a pass threshold. Do not emit PASS/FAIL. Do not introduce any tolerance constant. The output is a distribution of residuals; the tolerances will be set from that distribution afterward, which cannot happen if you have already thresholded the data.

### Units

Zero fields in this codebase declare their units (inventory §10 and the `units_declared` tally). The harness therefore states its assumptions explicitly: emit a table at the top of the report listing every field it consumed and the unit it assumed. If any assumption turns out wrong, that table is where it will be caught.

---

## PART 3 — Static conformance probe

No data, no execution. Read the code and answer in the report:

**P3.1 — Does the §7.2 step-4 insufficient-reserve arithmetic read the confidence band or the point estimate?**
Give the expression that computes `peak_shortfall_mw` verbatim, with file:line, and name every input. State whether it reads `forecast_mw`, `confidence_upper_mw`, `confidence_lower_mw`, or `p_demand_mw`. Do the same for whatever computes `bess_bridging_seconds` and for the comparison between them.

**P3.2 — Is the bridging capability anchor-adjusted?**
Give the expression, verbatim, and state whether `bess_anchor_reserve_mw` is subtracted before the comparison in P3.1.

**P3.3 — `_p_dispatch_droop_mw`.**
Give its assignment verbatim and name every input. State whether it is derived from measured demand or from a forecast field.

**P3.4 — Re-rated capability.**
Does `turbine_units[].rated_mw` carry an applied re-rating, or is it always nameplate? Where would a re-rating be applied, if anywhere?

Report what the code does. Do not judge conformance, do not change anything.

---

## PART 4 — Report

`reports/NAR-001_invariant_residuals.md`, in this order:

```
## 1. Units assumed             (the table from Part 2)
## 2. Runs analysed             (run_id, scenario, ticks, mode, evaluated/skipped per invariant)
## 3. Residual distributions    (per invariant per run: min, p50, p95, p99, max, and count beyond 1%/5%/10% of the relevant scale)
## 4. Time-series characterisation  (for any invariant whose p95 is non-trivial: is the residual constant, drifting, step-shaped, or spiking? At what sim_time?)
## 5. I6 disagreements          (every tick where recomputation and reserve_satisfied disagree)
## 6. Skipped-tick breakdown    (by invariant, by reason, by run)
## 7. Part 3 static findings
## 8. What I could not determine
```

Sections 3 and 4 in that order deliberately: distribution scan first, then time-series characterisation only of what the scan flags.

Also emit `reports/NAR-001_residuals.jsonl`, one record per tick per invariant, so the distributions can be re-derived without re-running.

---

## TESTS — TC-110…TC-117

Allocated from TC-110; TC-61…TC-98 and TC-203 are occupied, TC-99…TC-202 otherwise free.

| TC | Assertion |
|---|---|
| TC-110 | I1 returns a known residual on a hand-built tick with a deliberate 9.46 MW imbalance, and ~0 on a balanced one. |
| TC-111 | I2a and I2b each fire on a purpose-built failing fixture and are silent on a passing one. I2b returns NOT_EVALUABLE when `kube_metrics` is null. |
| TC-112 | I3 returns NOT_EVALUABLE — **not zero** — for every tick where any served/unserved field is null. |
| TC-113 | I4 reports positive exceedance only; a unit at exactly rated output produces no exceedance record. |
| TC-114 | I5 residual is ~0 for a synthetic discharge where ΔSoC and ∫P agree, and non-zero where they do not. |
| TC-115 | I6 reconstructs `floor_violated` correctly for a fixture where `reserve_satisfied` is true and one where it is false; the disagreement case is detected. |
| TC-116 | The harness is deterministic: same persisted input → byte-identical JSONL. No RNG, no wall-clock reads, no dict-ordering dependence. |
| TC-117 | No checker emits a pass/fail verdict or references a tolerance constant. Assert by inspection of the returned record schema. |

---

## DO NOT

1. Do not modify anything in `core/`, `runtime/`, `renewable/`, or `frontend/`. This harness reads persisted data and reads source; it changes neither.
2. Do not fix any defect the harness finds. Report it.
3. Do not coerce a null to zero, ever. Skip and record the reason.
4. Do not define, introduce, or import a tolerance, threshold, or epsilon. No pass/fail.
5. Do not write a summed value back into any payload. Spec §16.14/TC-92 prohibits computing `p_generation_mw` by summing in the transport layer — the harness computes a *comparison* for reporting and writes nothing into any tick. Do not "fix" `p_generation_mw` and do not refuse the I2a comparison on that basis.
6. Do not assume the tick interval. Derive `dt_s` from consecutive `sim_time_seconds`.
7. Do not infer units from field names. Use the assumptions table and state them.
8. Do not add catalogue keys.
9. Do not edit any spec, decision record, or the NAR-001 inventory.
10. Do not proceed past Part 1 without my reply.

## STOP AND REPORT IF

- `run_timeseries` does not persist enough fields to evaluate at least four of the six invariants.
- Any field name in the Part 2 table disagrees with the NAR-001 inventory.
- Fewer than two runs with more than 100 ticks exist.
- Any invariant's skip rate exceeds 80% of ticks — that means the data path, not the physics, is what you are measuring.
