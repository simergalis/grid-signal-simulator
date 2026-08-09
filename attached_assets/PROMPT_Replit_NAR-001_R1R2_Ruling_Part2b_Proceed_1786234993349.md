# Replit Agent Prompt — NAR-001 Phase A′: R1/R2 Ruling and Part 2b Proceed

Paste everything below the line.

---

## R1 — Accepted

The inventory miscounted its own table. 74 is correct, `load_catalogue` is correct, and no code change is needed.

**Authorised, as an exception to the standing rule against editing the inventory:** correct §J.3's heading to `Locked section (53 keys)` and the total at line 1692 to `13 + 8 + 53 = 74`. Add a one-line note at the correction site recording that the original figures were arithmetic errors found during Phase A′, so the change is traceable. Correct nothing else in that document.

---

## R2 — RULING: do not build the endpoint. Proceed to Part 2b.

Correct stop, and the finding is more important than the blocker it created. But the blocker doesn't actually block this phase.

**Why 2b proceeds anyway:** every invariant I1–I6 is evaluated *within* a single tick, or between two consecutive ticks in I5's case. None of them compares run A against run B. A power-balance residual of 9 MW in a recording is a defect in that recording regardless of whether a second run of the same `scenario_id` would reproduce it. Cross-run comparability is needed to *re-investigate* a finding and to attribute a behaviour change to code versus configuration — both of which come later. It is not needed to find the defects, which is what Phase A′ is for.

So: no server-side change, no new endpoint, no new DB column, no waiting.

---

## SUBSTITUTE — derive a run fingerprint from the wire

The resolved `spec_data` is unreachable, but a large part of the resolved *configuration* is already stamped on every tick: `turbine_units[].rated_mw`, `bess_usable_mwh`, `rated_cooling_mw`, `alpha_max`, `site_utc_offset_h`, site identity fields, and others.

Add to the recorder, after a recording completes:

1. Compute the set of payload fields whose value is **identical across every tick** in the run. Walk nested paths too (`turbine_units[i].rated_mw`, `commitment_block.*`).
2. Write that set, with values, into the manifest as `constant_fields`, and its canonical-JSON sha256 as `constant_fields_hash`.
3. Write the fields that varied into `varying_fields` as a name list only, no values.

This is empirical rather than asserted, which makes it better than reading a spec would be in one respect: if something believed constant turns out to vary mid-run, this finds it. `bess_usable_mwh` is the obvious first test — §C.7 says config nameplate, and the smoke run agreed, but that should be a measurement rather than a citation.

It does not capture the workload event schedule or the irradiance profile. That limitation is real and goes in the manifest as a comment. It is a fingerprint of the physical configuration, not of the scenario.

---

## DEFECTS — split into two, because they are different problems

**#270 — The resolved `ScenarioSpec` is discarded.** `spec_data` is fully resolved and JSON-serialisable between generator completion and `start_run`, and nothing captures it. `RunContext` retains no `spec` field, the DB holds only the pre-generation base, and no endpoint exposes it. A run cannot be reconstructed after the fact.

**#271 — The generator pipeline is stochastic by default.** Three of five generators fall back to unseeded RNG when `rng_seed` is omitted, and two are LLM-backed when a key is present. Same `scenario_id`, different scenario.

These need separating because the fixes are independent: #270 is "we throw the record away," #271 is "the thing we would record varies." Fixing #270 alone gives reproducible *forensics* without reproducible *runs* — which is most of the value, and is the cheaper fix.

**One question that decides how live #271 is, answer in your 2b report:** do the scenarios actually in the library set integer seeds, or do they omit them? Grep the scenario records. If the deployed scenarios all fix their seeds, #271 is latent and #270 is the only real problem. If they don't, every run to date has been unreproducible.

**Related, worth noting in the log:** the LLM branch means run *start* depends on `MISTRAL_API_KEY` being present, so a run started with the key set is a materially different scenario class from one started without it. That is the same env-var-driven divergence already logged for `advisory_router.py`, and both belong to one pattern: behaviour that changes with deployment environment rather than with configuration.

---

## PART 2b — proceed as specified

The scenario selection criteria C1–C6 stand unchanged. Additionally, for every run, record in the manifest whether the scenario record carried an integer `rng_seed` / `seed`, and whether `MISTRAL_API_KEY` was present in the environment at run start. Those two facts are what a later reader will need to know whether a recording could be reproduced.

C1 remains the one that matters most — `kube_metrics` was null on all 11 smoke ticks, so I2b is still entirely unexercised.

---

## TESTS — one added

| TC | Assertion |
|---|---|
| TC-122 | `constant_fields` on a synthetic stream contains exactly the fields that do not vary, excludes one that changes on the final tick only, walks nested paths, and produces a hash that is stable across two computations and differs when any constant value differs. |

---

## DO NOT

1. Do not add `GET /runs/{run_id}/spec`, a `resolved_spec_json` column, or any other server-side capture. That is #270's fix and belongs in its own task.
2. Do not modify `api/routes/runs.py`, `run_manager.py`, `persistence.py`, or any generator module.
3. Do not set, inject, or alter a seed to make runs reproducible. Record what the scenario already specifies; changing it would mean the recordings are not of the system as it stands.
4. Do not correct anything in the inventory beyond the two figures authorised in R1.
5. Do not fix #266–#271.
6. Do not proceed to the checkers. That is Part 2c.

## STOP AND REPORT IF

- No scenario in the library sets `kube_config`, leaving I2b permanently unexercised.
- A recording ends with `stop_reason: dropped`.
- `constant_fields` turns out to include a field that §C.7 or the inventory describes as varying, or excludes one described as constant.
