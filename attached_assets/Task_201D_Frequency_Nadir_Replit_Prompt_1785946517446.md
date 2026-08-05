# Task #201-D — Frequency Nadir Prediction and the SC-20 Demonstration Pair

**Scoped subset of #201.** This task delivers `predicted_frequency_nadir_hz` and the SC-20 scenario pair that exercises it. It is cut deliberately narrow because it gates a design-partner meeting with an islanded-site operator, and nadir in Hz against their protection settings is the only number in the product that speaks their operating reality.

**Target model:** `core/simulation_core.py`, `core/models.py`, `scenario_factory.py`, and the frequency test corpus.
**Out of scope:** `gridsignal_logger.py`. Separate physics implementation, reached only by `/api/export/telemetry-log`. Do not read it, do not change it, do not use it to cross-check.

**Prerequisite:** #200 (Balance Channel Scope) must be merged. `asset_delivery_error_mw` must already be out of the energy identity, with surplus in `frequency_forcing_mw` alone. If it is not, stop and report before beginning Phase 0.

---

## Do not

1. Do not implement a closed-form or approximate nadir formula. See Phase 3 — this is the single most important constraint in the task.
2. Do not implement Phase 3 transitional sequences, TRANSITIONAL decommit, or sub-MSL fleet behaviour.
3. Do not implement unit commitment, `CommitmentProposal`, or any queue-depth forecast.
4. Do not change protective relay settings (ROCOF threshold, underfrequency threshold) without an explicit approval stop.
5. Do not tune `H`, droop, `r_asset`, or any physical parameter to make an assertion pass. If TC-89 fails, report the failure and the arithmetic; do not close the gap by moving a constant.
6. Do not add a second computation path for frequency, inertia, or nadir.
7. Do not edit the Forecast Engine specification. Produce a written summary of implemented behaviour for the spec author instead.
8. Do not change any MW value, asset rating, or plant configuration outside the explicit SC-20 re-size in Phase 4.

---

## Phase 0 — Discovery. Stop and report.

Produce findings only. **No code changes in this phase.**

**0.1 — Nominal frequency.** Enumerate every location where a nominal frequency value appears: `SiteConfig.frequency_nominal_hz` and its default, every literal `50.0` or `60.0` in a frequency context, every fixture, every test assertion whose expected value was derived from a nominal. Report file, line, current value, and whether it is a definition or a derived assertion.

**0.2 — Inertia.** Report how system inertia is currently represented. Specifically: is there an inertia constant `H` per unit? Is it on machine MVA base or system base? What converts MW rating to MVA — a power factor constant, and where is it defined? If inertia is not currently modelled at all, say so plainly; that changes the shape of Phase 3.

**0.3 — Swing equation.** Report the current integration: its inputs after the #200 channel-scope change, its timestep, its integration method, and whether governor droop is read (task history shows `governor_droop` was defined in fixtures but never read in `simulation_core.py`, leaving a pure integrator; confirm the 13.3 work closed this).

**0.4 — Block-load pickup.** Confirm the emergent load-sharing behaviour is in place: that `P_elec` is set by load sharing on the bus and the machine's electrical output rises to its share instantly, bounded by `rated_i`. Report whether any residual "block pickup allowance" parameter exists anywhere; if one does, it is wrong and must be reported, not removed in this phase.

**0.5 — Corpus inventory.** List every test in I1–I5, the 13.2 decomposition suite, and the 13.3 droop suite whose expected value depends on nominal frequency. Count them.

**0.6 — Numbering.** Report which `TC-` identifiers are currently allocated in the simulator corpus. Task history indicates TC-82b and TC-89 are in use. **Flag any collision** with TC-77–TC-82 (SA-01) or TC-83–TC-89 (SA-02) and propose a non-conflicting range. Do not renumber anything yet.

**STOP. Report 0.1–0.6 and wait for approval before Phase 1.**

---

## Phase 1 — Site nominal frequency

**1.1** `SiteConfig.frequency_nominal_hz` becomes a required field with no default. Fail fast at startup if absent. Same treatment `SiteLocation` received, and for the same reason: a silently defaulted site parameter that is wrong produces plausible-looking output.

**1.2** Set the demo site (San Diego) to `60.0`.

**1.3** No literal nominal frequency anywhere outside the `SiteConfig` definition. Every consumer reads it from the site object. Droop response, nadir, ROCOF, and every threshold derive from it per tick.

**1.4** Versioned persisted state: if any stored artifact carries a frequency-derived value, add migration logic. Do not silently reinterpret old records at a new nominal.

---

## Phase 2 — Frequency corpus re-baseline. Stop and report.

Re-derive every expected value identified in 0.5. Droop response scales with nominal, so these are wrong for a 60 Hz site.

**Required output: an enumeration of every changed value, with its mechanism.** For each: test ID, old expected, new expected, and the one-line derivation. A table of before/after numbers without mechanisms is not acceptable — it makes an arithmetic error indistinguishable from a physics change.

**STOP. Report the enumeration and wait for approval before Phase 3.**

---

## Phase 3 — `predicted_frequency_nadir_hz`

### 3.1 The constraint that governs this phase

**The predictor must call the same swing-equation integration the live engine uses.** It forward-integrates the existing physics against the forecast step. It does not use a closed-form nadir approximation, a lookup table, or a separate simplified model.

This project has been bitten three times by dual computation paths — solar plant-level versus per-bank, balance residual, aggregate power — and the resolution each time was deletion of the redundant path, not reconciliation. A nadir predictor built on its own approximation will disagree with the measured nadir, and the disagreement will surface in front of an operator as two numbers on one screen that do not match.

If forward-integrating the live physics is not structurally possible from where the predictor must run, **stop and report that** rather than substituting an approximation.

### 3.2 Two fields, not one

| Field | Meaning |
|---|---|
| `predicted_frequency_nadir_hz` | Computed at staging time, before the step lands. What GridSignal says will happen |
| `measured_frequency_nadir_hz` | Running minimum of actual frequency over the event window. What did happen |

Both are required. The product claim is not "we predict a nadir" — it is "we predicted it, we were right, and staging changed it." One field cannot carry that.

### 3.3 Computation

Predicted nadir is computed when the §7.2 reserve check runs, using the forecast step and the staged asset position at that moment. Re-computed on each re-plan.

Measured nadir is a running minimum over a window opening at the staging event and closing on a configurable settle criterion. Report the window definition chosen; do not invent a settle rule silently.

### 3.4 Type-boundary guard

Both fields require matching typed fields in `TickPayload` per the task #191 guard. The guard must pass. If it does not, the guard is correct and the broadcast dict is wrong.

**STOP. Report the predictor's integration path, the settle criterion, and a single worked tick showing predicted versus measured, before Phase 4.**

---

## Phase 4 — SC-20 re-size and TC-89

### 4.1 The problem

SC-20A was calibrated against a model without correct load-sharing behaviour. Its `alert_fires` assertion no longer holds. The scenario must be re-sized so the control arm produces a frequency excursion that breaches protection, while the treatment arm does not.

### 4.2 Re-size

Using the inertia values reported in 0.2 and the relay thresholds confirmed in 4.3, compute the compute-step magnitude at which SC-20A breaches ROCOF. Adjust `job-c` node count and, if required, `max_p_total_mw`. **Report the arithmetic before applying it.**

Constraints: SC-20B must continue to pass `no_insufficient_reserve_alert` with margin; the two files must continue to differ in exactly `name`, `description`, `dt_lead_seconds`, and the one assertion object; `rng_seed` identical.

### 4.3 Relay thresholds — approval stop

Confirm the ROCOF and underfrequency thresholds currently in the model and their provenance. If they are placeholders rather than site-derived, say so. **Do not change them without explicit approval** — they are protection settings, not tuning parameters.

### 4.4 TC-89

Assert the product claim directly:

- Run SC-20A (`dt_lead_seconds = 0`) and SC-20B (`dt_lead_seconds = 45`), identical in all else.
- `predicted_frequency_nadir_hz` in Arm B is measurably higher (closer to nominal) than in Arm A.
- Assert a **minimum separation in Hz**, not merely an inequality. A demonstration that turns on 0.01 Hz is not a demonstration.
- `|predicted − measured|` within tolerance in **both** arms. Report the tolerance and its basis.
- Arm A breaches at least one protection threshold; Arm B breaches none.

### 4.5 `start_sync_s`

SC-20 currently sets `start_sync_s: 90` for GEN-3. Published cold-start durations are 5–10 minutes for aeroderivative and 10–30 for frame machines. Ninety seconds is below the fastest class by a factor of three.

**Do not change the value in this task.** Report it, and report whether any SC-20 assertion depends on GEN-3 arriving in time. If one does, that assertion is unsound and must be flagged for the next task.

---

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | Phase 0 findings reported before any code change | Report, six sections |
| 2 | `frequency_nominal_hz` required, no default, fail-fast | Startup test with the field absent |
| 3 | No literal nominal frequency outside `SiteConfig` | Grep output, empty |
| 4 | Corpus re-baselined with per-value mechanisms | Enumeration table |
| 5 | Full frequency suite green at 60 Hz | Test run |
| 6 | Nadir predictor forward-integrates the live physics | Code path trace, single call site |
| 7 | No second physics implementation introduced | Diff review |
| 8 | Both nadir fields present and typed | #191 guard passes |
| 9 | SC-20A breaches ROCOF; SC-20B does not | TC-89 |
| 10 | Nadir separation between arms exceeds the stated minimum | TC-89, value reported |
| 11 | Predicted within tolerance of measured, both arms | TC-89 |
| 12 | SC-20A/B differ in exactly the four permitted fields | Diff |
| 13 | Determinism: two runs per arm, bit-identical | Test run |
| 14 | `start_sync_s` reported, not changed | Report |
| 15 | No parameter tuned to close an assertion gap | Diff review |
| 16 | Written behaviour summary produced for the spec author | Document |

---

## Route back to the requester, do not decide

1. **Inertia constant `H` and the MVA base.** If 0.2 finds no inertia model, this task cannot compute a nadir and the scope changes — report immediately rather than proceeding.
2. **Relay thresholds** if they prove to be placeholders.
3. **Minimum nadir separation for TC-89** — the value that makes the demonstration meaningful is a product judgement, not an engineering one.
4. **TC numbering collision** if 0.6 finds one.
