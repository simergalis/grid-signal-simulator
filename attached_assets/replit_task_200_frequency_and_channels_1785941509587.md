# Task #200 — Site Frequency Wiring and Balance Channel Scope

Two corrections, both found during the #199 pre-work gate. Both must land before Phase 3, because Phase 3's acceptance criteria are measured against frequency behaviour and against the balance channels.

**Target model:** `core/simulation_core.py`, `core/models.py`, `scenario_factory.py`, and the frequency test corpus.
**Out of scope:** `gridsignal_logger.py`. Separate physics implementation, reached only by `/api/export/telemetry-log`.

**Do not** implement Phase 3 transitional sequences, Phase 4 operator endpoints, commitment logic, or session recording in this task.

---

## Part A — Site nominal frequency

### Finding

`SiteConfig.frequency_nominal_hz` defaults to `50.0` with the comment "EU/APAC default; override for 60 Hz." `ScenarioSpec` has no `frequency_nominal_hz` field, so the engine cannot receive an override. The demo-20mw scenario therefore runs at 50 Hz.

San Diego is 60 Hz. Every tariff and site assumption in the spec is built on SDG&E territory. The entire frequency test corpus — I1 through I5, the §13.2 decomposition tests, the §13.3 droop response tests — was written and passes against 50 Hz. **Droop response scales with nominal frequency**, so those expected values are wrong for this site.

TC-82c passed only because a literal `f0 = 50.0` in the test happened to match the wrong default. That is the shape of defect this work exists to eliminate.

### Required changes

**A1. Wire the field through.** Add `frequency_nominal_hz` to `ScenarioSpec`, carry it through `scenario_factory.py` into `SiteConfig`. Set the demo-20mw seeded scenario to `60.0`.

**A2. Remove the silent default.** `SiteConfig.frequency_nominal_hz` must not default to any value. An unset nominal fails fast at startup with a named error, the same treatment `SiteLocation` received and for the same reason: a wrong nominal that passes tests is worse than a missing one that stops the run.

**A3. No literal nominal anywhere.** Grep for `50.0`, `60.0`, `f0`, and `f_nominal` across engine and tests. Every one must source from `SiteConfig`. Report any that cannot, with the reason.

**A4. Re-baseline the frequency corpus.** Every test whose expected value changes when nominal moves from 50 to 60 Hz must be updated, and **each one enumerated in the report with the mechanism that changed it** — which term in the swing equation or droop response scales with nominal, and why the new value follows.

This is the most important output of this task. A short enumeration is a signal that values were adjusted rather than derived. If a value changes in a way you cannot explain mechanically, **stop and report rather than updating it.**

**A5. Existing 50 Hz coverage.** Some tests may legitimately want a 50 Hz site — the grid-connected and EU-shaped fixtures. Where that is true, set it explicitly on the fixture rather than relying on a default. Report which fixtures are 50 Hz by intent versus by inheritance.

### Part A acceptance

- `ScenarioSpec` carries `frequency_nominal_hz`; demo-20mw is 60.0.
- `SiteConfig` has no default; an unset nominal fails at startup with a named error. Prove it: construct a config without it, show the failure, revert.
- No literal nominal frequency in engine or test code. Every reference sources from config.
- Every changed frequency assertion enumerated with its mechanism.
- Each fixture's nominal is set by intent, not inherited.

**Stop and report before Part B.**

---

## Part B — `asset_delivery_error_mw` leaves the energy identity

### Finding

The PW-2 reversion restored `−sub_msl` to the islanded delivery-error term, so the surplus cancels within the sum and D4 holds cleanly. The algebra is correct. The semantics are not.

`asset_delivery_error_mw` now reports **zero** in the islanded case while the fleet sits 0.8 MW above its commanded setpoint. That is the exact behaviour PW-2 was written to eliminate: an operator asking "is the fleet doing what it was told" gets "yes" while it is not.

The double-count that forced the reversion existed only because a **reporting** quantity was load-bearing in an **energy** identity. Fix the cause.

### Required changes

**B1. D4 carries three energy channels.** Sub-MSL surplus lives in `frequency_forcing_mw` alone — that is where the energy goes. The identity holds with no conditional and no mode branch.

**B2. `asset_delivery_error_mw` becomes a reporting field outside the identity.** It means **commanded ≠ delivered, whatever the cause** — floor constraint, actuator lag, hardware fault, all of it. It is not a term in D4.

**B3. Establish what §13.2 intended.** Determine whether `asset_delivery_error_mw` was defined as an energy term or a reporting term when the three channels were established. Report the finding. If it was an energy term, this is a deliberate re-scope and must be recorded as a needed §13.2 spec edit — **report it, do not edit the spec document.**

**B4. TC-82b asserts the same value in both modes.** 0.8 MW islanded, 0.8 MW grid-connected. Same physical situation, same reported discrepancy. Mode must not change what the fleet reports about its own command tracking.

### Part B acceptance

- D4 identity: three energy channels, no conditional, no mode branch. Algebra shown in both islanded and grid-connected modes.
- `asset_delivery_error_mw` is not a term in D4.
- A unit held at its MSL floor above setpoint reports the discrepancy in `asset_delivery_error_mw` in both modes.
- TC-82b asserts 0.8 MW in both modes.
- `d4_balance_defect_mw` stays zero across the full suite.

---

## Do not

- Touch `gridsignal_logger.py`.
- Leave any default value on `SiteConfig.frequency_nominal_hz`.
- Leave any literal nominal frequency in engine or test code.
- Adjust a frequency expected value you cannot explain mechanically. Stop and report.
- Add a fourth energy channel to D4, under any name.
- Make `asset_delivery_error_mw` mode-dependent.
- Edit the spec document. Report needed edits.
- Implement Phase 3, Phase 4, commitment logic, or session recording.
- Migrate scenarios off `RAMPING`/`AT_TARGET`, or delete `advance()`. That is task #201.
- Invent a constant. If a value is needed that is not named here or already in the fixtures, **stop and report rather than choosing.**
- Tune a constant or tolerance to make an assertion pass.
- Renumber or edit existing TC IDs.
- Proceed from Part A to Part B without reporting.

---

## Report format — after Part A, and again after Part B

1. Files changed, line counts.
2. Each acceptance criterion quoted, PASS/FAIL, with evidence.
3. **Part A:** every frequency assertion whose expected value changed, with the mechanism — which term scales with nominal and why the new value follows. Enumerate individually; do not summarise.
4. **Part A:** every fixture's nominal frequency, marked as set-by-intent or previously-inherited.
5. **Part B:** what §13.2 intended `asset_delivery_error_mw` to be, and whether this is a re-scope requiring a spec edit.
6. Spec sections found contradictory or underspecified. State "none" explicitly if none.
7. Out-of-scope temptations: list, do not do. State "none" explicitly if none.
8. Full-suite result **with the exclusion set stated explicitly**. Any change to the seven known failures, in either direction, reported with cause.
