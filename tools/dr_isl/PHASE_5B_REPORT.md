# DR-2026-10-20-ISLAND-COLLAPSE — Phase 5b

Status: **PASS**. Phase 5b only; no Phase 6, governor work, or scenario-protection variant started.

## V0 — prior IMPL-ISL-17 work (context)

- The defect was missing transition-event records for successful `stage_for_predicted_step` turbine starts; the native start counter/fuel was already correct (`PHASE_4_DESIGN.md:27–47`).
- The approved design used the existing transition adapter, resolved its sink at event time, and emitted only after an OFFLINE→STARTING command incremented the native counter (`PHASE_4_DESIGN.md:163–171`; `PHASE_4B_REPORT.md:11–28`).
- Commit `146b89f` added an optional observation callback in `core/dispatch.py:379–382,622–641`, wired through `core/simulation_core.py:352–353,389–412`; it is observation-only and does not alter start selection, dispatch, or physics (`PHASE_4B_REPORT.md:23–28`).
- Phase 4b ran TC-ISL-07a–g and the directly affected focused tests: 36 passed, 0 failed (`PHASE_4B_REPORT.md:30–70`).

## 5b.1 — IMPL-ISL-21

Commit `0e7c3d3` — `IMPL-ISL-21: label governor cascade as diagnostic-only (PX-2)`.

Comment/docstring-only changes:
- `P/core/simulation_core.py:1463–1466,1522–1525,3536–3541`
- `P/core/asset_modules.py:938–944`

The comments now state that the governor cascade advances diagnostic state not consumed by executable code, its terminal state is rate-limited but not capped to unit headroom, and primary frequency response is the PX-2 Forecast Engine FS v2.5 scope gap requiring a design addendum. AST hashes before/after are identical:
- `simulation_core.py`: `11202105ccabdacee8ba3de169a6470635b8916b98f9bfc8345a98903ed00675`
- `asset_modules.py`: `e0db09fbd104d06e9b05152b1b3a754ed640e4a9ce05d7c62975c7d3c39d8837`

## 5b.2 — OPEN-ISL-3

### Frequency-feedback predicate and physical paths

One predicate, `frequency_feedback_configured(site, fuel_cell_module)`, is defined at `P/core/frequency_reporting.py:29–64`. It returns false for non-islanded/grid-tied operation (`:37–40`) and true for any configured islanded frequency-sensitive result path:

| Trigger path | Predicate / implementation locations |
|---|---|
| First-stage UF/OF dispatch droop | predicate `frequency_reporting.py:41–46`; actual bounded dispatch correction `simulation_core.py:1543–1597` |
| UFLS stages | predicate `frequency_reporting.py:51–52`; substep protection `simulation_core.py:3555–3650` |
| 81U under-frequency relay | predicate `frequency_reporting.py:47–50`; substep protection `simulation_core.py:3555–3650` |
| Island collapse threshold | predicate `frequency_reporting.py:41–46`; substep collapse check `simulation_core.py:3555–3650` |
| Renewable over-frequency curtailment | predicate `frequency_reporting.py:53–57`; `simulation_core.py:1356–1388` |
| FC IEEE 1547 ride-through/trip | predicate `frequency_reporting.py:58–63`; call/evaluation in `simulation_core.py:3515–3524` and `fuel_cell_module.py:678–741` |

Grid-tied frequency is assigned nominal and not integrated (`simulation_core.py:3664–3667`), so the predicate is false there. Existing `protection_is_configured` remains a separate reporting flag: it returns true for grid-tied operation and checks islanded protection thresholds/stages at `frequency_reporting.py:13–26`. The catalogue's resolved protection default is null frequency thresholds, no 81U threshold, and empty UFLS stages (`P/core/models.py:591,595,626–630`).

The frequency reporting band is `FREQUENCY_VALIDITY_BAND_FRACTION = 0.10`, marked `PROPOSED_HERE` with rationale at `frequency_reporting.py:4–10`. This is a 54–66 Hz band at 60 Hz (45–55 Hz at 50 Hz), used only to label/report ticks; it does not clamp frequency.

The predicate is computed once from the resolved run state in `P/runtime/scenario_factory.py:1949–1962`, stored in run metadata, and passed to the study collector by `P/study_harness/executor.py:360–387`. The collector's additive invalid-tick count/fraction and feedback flag are at `P/study_harness/metrics.py:174–215,496–504,669–688`.

### Run validity and persistence/API fields

- In `P/study_harness/acceptance.py:66–85`, a run is frequency-valid iff feedback is not configured or invalid-tick count is zero. That result is folded into existing `baseline_valid` / `informed_valid`; the comparison remains ten conditions (`:113–138,207–214`), not eleven.
- All four fields—`frequency_feedback_configured`, `protection_configured`, `invalid_frequency_tick_count`, `invalid_frequency_fraction`—are added to each condition's inputs and to the comparison frequency payload (`acceptance.py:87–112,139–214`). The MCP response includes those inputs in every condition and top-level `frequency_inputs` (`P/mcp_server/server.py:756–845`).
- R5.2 plane-separation comparison: base violation list = `P/api/routes/ingest.py:17` (`core.models`) and `:18` (`core.slurm_scheduler`); candidate before the layering fix added `P/api/schemas.py:2430` (`core.frequency_reporting.unprotected_island_warning`); after the fix the list is exactly the two base entries. The warning now lives in `P/runtime/build_warnings.py:9–20`, and the seeded spec remains valid.
- Run-level fields are accumulated from existing tick values, persisted in `verdict_json`, restored after restart, and kept on `CompletedRun` (`P/runtime/run_manager.py:1914–1924,3573–3606,3644–3662`; `P/api/routes/runs.py:135–144`).
- Persistence boundary: the per-tick `frequency_valid` value is available in live tick payloads, but the DB restore path intentionally returns `tick_dicts=[]`; tick history itself is not persisted by this route (`P/api/routes/runs.py:91,135–144`). The run-level flags and invalid-frequency count/fraction are persisted and restored.
- REST energy summary exposes all four fields at `P/api/routes/runs.py:1126–1170`; MCP energy section exposes them at `P/mcp_server/server.py:587–612`.
- Existing tick fields are set at `P/core/simulation_core.py:4188–4189` and included in the tick payload at `P/runtime/run_manager.py:798–799`. The unprotected-island build warning remains runtime-layer logic at `P/runtime/build_warnings.py:9–20`, included in run-start response at `P/api/routes/runs.py:690–694`.
- The study identity version advanced from 1 to 2 for the additive frequency-reporting identity (`P/study_harness/metrics.py:22–24`). This changes study identity digests only; physical tick hashes and the original 27 metrics remain identical.

### Seeded catalogue and scenario directory inventory

The complete per-entry inventory (scenario ID/name or file, `frequency_feedback_configured`, and triggering path) is saved in `tools/dr_isl/phase5b/CATALOGUE_INVENTORY.json`.

- Seeded catalogue: 58 entries; 3 are true, all via `fuel_cell_ride_through`: `scenario-fc100-islanded-v2`, `scenario-fc100-islanded-zero-hot-v2`, and `islanded-fc-bess-diesel-slurm-gpu-peaks`. The other 55 are false.
- Scenario directory: 45 JSON files; 35 build as `ScenarioSpec` (33 false, 2 true); 10 legacy/test fixtures do not build as `ScenarioSpec` and are recorded as unavailable rather than classified false. The two valid true files are the two `scenario-fc100-*` entries, both via FC ride-through.
- Actual tested values for the fc100 pair: regular v2 has feedback true, invalid count 0 (run-valid); zero-hot v2 has feedback true, invalid count 214/264 = 0.810606 (run-invalid). These are app-path runs; no study-class verdict is defined for them.

## 5b.3 — acceptance

### V1: physical identity and study metrics

All 14 D11 cases have identical physical hashes to 5fbf357. The physical hash contract is recorded in `tools/dr_isl/phase5b/V1_V3_RESULTS.json`: ticks in order, compact sorted-key JSON plus LF, excluding only `advisory_telemetry`, `fabric_modal`, `wall_stamp_utc`, and `insufficient_reserve_proposal_id`; frequency fields are included. All repetitions matched. For each of the three study pairs, the original 27 study metrics are identical; no physical field changed.

| Scenario / arm | Physical SHA-256 (baseline = candidate) |
|---|---|
| Base demo / baseline | `e9a25202a069acdb648779981f07bc27e1cbe53a5a2b44e1571bd8724912a5f9` |
| Base demo / informed | `34bc07cdebda13c4e07bc990408745fbeeb5f916248cd7159d9f8fd656ee2702` |
| H1-24h / baseline | `249a9925b8f97e20db79cf6f02bf0c282f2f57ec825026af0ec183a0d4dad7f1` |
| H1-24h / informed | `0c929bba5ae33582779fc3790b9e66b4d48ed17820a70bdb9885c12db40cc6f7` |
| H2-24h / baseline | `3f39c1e60e3b1b30eb51455b50c2c429947f24955a9744e2d22680a86c5b524e` |
| H2-24h / informed | `85aff01fe0a381f3438c6e9cdf53c942501ea1585d72d3dbf6c1f9992ea62ee4` |
| S10 | `3e24904fd7e8f71afa1f5b30ec2f2958a6b43e7670ab9fefae04f3440aa57bff` |
| SJ-1 | `84a8294e726190fa58a869f9e64b455bfb3ef7675bad448ae39f643f269db510` |
| scenario-turbine-01 | `23fffd3cf5f1281cb72742254e05d393c705e5cdacf2fe5036541e8deedb59b4` |
| hybrid-ai-100mw-addendum-i | `5b71aa3959769d9b579e7781b120bf1fcabecdaed1476481f2e6e5bf56f1ddfb` |
| 100mw-fuel-cell-bess-diesel | `dad91d98830c78f678ed4c490729d1a6772046251a979e6c50af3a5f9f6300cb` |
| fc100-islanded-v2 | `44b5f15a0cee3477fd14f3d22255c17ef42abd6a3765d8adc3443abbf9b88565` |
| fc100-islanded-zero-hot-v2 | `0bc7e7a2a5af0798a4b4a3cdc69687e6084ff57bde0c2b34500545f84115b8ce` |
| demo-islanded-ramp | `e3b8cc8dfcc4fc4847f653b260e0e9a7c6ee88e1722930ca59567875df2219d6` |

### V2: frequency validity table

Values below are the measured current values; first-invalid is tick / interval-end seconds / Hz. Full per-case details and repeat checks are in `V1_V3_RESULTS.json` and `D11_3_RESULTS.json`.

| Scenario / arm | Feedback | Protection | Invalid ticks / fraction | First invalid | Hz min–max |
|---|---:|---:|---:|---|---:|
| Base demo / baseline | false | false | 53 / 0.036806 | 67 / 335 s / 40.909530 | -5.000867–60.043916 |
| Base demo / informed | false | false | 0 / 0 | — | 55.495062–60.298693 |
| H1-24h / baseline | false | false | 811 / 0.046933 | 6131 / 30655 s / 48.715169 | 17.097717–60.271877 |
| H1-24h / informed | false | false | 76 / 0.004398 | 13331 / 66655 s / 53.419875 | 48.591568–60.458334 |
| H2-24h / baseline | false | false | 549 / 0.031771 | 5827 / 29135 s / 46.454310 | -239.886266–60.223706 |
| H2-24h / informed | false | false | 412 / 0.023843 | 5828 / 29140 s / 52.894218 | 11.925776–60.149177 |
| S10 | false | false | 594 / 0.034375 | 1921 / 9605 s / 51.132179 | -749.690548–60.545957 |
| SJ-1 | false | true | 0 / 0 | — | 60.000000–60.000000 |
| scenario-turbine-01 | false | false | 0 / 0 | — | 60.000000–60.586407 |
| hybrid-ai-100mw-addendum-i | false | false | 54 / 0.450000 | 1 / 5 s / -20.297650 | -218.796065–60.979553 |
| 100mw-fuel-cell-bess-diesel | false | false | 0 / 0 | — | 60.000000–60.000000 |
| fc100-islanded-v2 | true | false | 0 / 0 | — | 60.000000–60.000000 |
| fc100-islanded-zero-hot-v2 | true | false | 214 / 0.810606 | 46 / 230 s / 39.396750 | -82.804352–60.000000 |
| demo-islanded-ramp | false | false | 103 / 0.047685 | 136 / 680 s / 53.373055 | -127.489612–60.000000 |

Base demo and H1/H2 contain invalid ticks, but their feedback predicate is false; their invalid fractions are informational and do not invalidate the pair. Grid-tied SJ-1 has `protection_configured=true` and `frequency_feedback_configured=false`.

### V3: compare_runs

Base demo, H1-24h, and H2-24h each remain **PASS 10/10**. All ten condition names/order and booleans match 5fbf357. All four frequency fields appear in both arms' inputs and the payload. For base demo, H1, and H2, both arms have `frequency_feedback_configured=false`; protection flags are false; invalid counts are respectively 53/0, 811/76, and 549/412. Because feedback is not configured, these invalid ticks are informational. The condition list remains: `build_parity`, `baseline_valid`, `informed_valid`, `baseline_energy_balance`, `informed_energy_balance`, `baseline_fuel_reconciled`, `informed_fuel_reconciled`, `identical_compute_trace`, `informed_unserved_energy_no_worse`, `informed_peak_unserved_no_worse`.

## 5b.4 — tests

No TC-ISL-26–30 collision was found. `tests/test_dr_isl_frequency_feedback.py` covers:
- TC-ISL-26: unprotected islanded run has feedback false; a >66 Hz tick remains unchanged and is marked invalid; comparison is PASS and the invalid fraction is reported.
- TC-ISL-27: configured feedback plus invalid ticks makes baseline/informed validity false and comparison FAIL while retaining 10 conditions; all four frequency fields are present in each condition and the MCP comparison payload.
- TC-ISL-28: configured feedback with zero invalid ticks remains valid/PASS.
- TC-ISL-29: grid-tied feedback false while reporting protection true; REST/MCP fields and DB-restored fields agree.
- TC-ISL-30: each trigger—UF droop, OF droop, UFLS, 81U, island-collapse threshold, renewable OF curtailment, and FC ride-through—sets the predicate true; an 81U threshold above nominal does not.

Focused frequency and directly affected tests: **42 passed**, 1 existing Starlette/httpx deprecation warning. The plane-separation gate has only its two existing imports at `P/api/routes/ingest.py:17–18`; its full-suite failure remains in the baseline list and no new API→core violation was added.

## 5b.5 — full suite

Command: `PYTHONHASHSEED=1729 python -m pytest -q --junitxml=tools/dr_isl/phase5b/FULL_SUITE.xml`, run from `P`.

- Pytest: 2212 passed, 15 failed, 3 skipped, 23 xfailed, 3 subtests passed; 54 warnings; 682.87 s.
- JUnit: 2256 tests, 15 failures, 0 errors, 26 skipped including xfails.
- Against `tools/dr_isl/D11T_FAILING_TESTS.txt`: **added 0, removed 0, remaining 15**. The exact list is `tools/dr_isl/PHASE_5B_FAILING_TESTS.txt`.
- `tests/test_gpu_load_profile.py::test_gpu_load_profile` passed in this full-suite run.
- The suite process exited 1 because the 15 pre-existing failures remain; the Phase 5b suite gate passes because there were no added failures.

## 5b.6 — commits, workflow, and boundaries

- `0e7c3d3` — `IMPL-ISL-21: label governor cascade as diagnostic-only (PX-2)`; comment/docstring-only files listed in §5b.1.
- `46cd09c` — `OPEN-ISL-3: gate study validity on configured frequency feedback` — `P/core/frequency_reporting.py:4–64`; `P/runtime/scenario_factory.py:1946–1962`; `P/study_harness/metrics.py:22–24,174–215,669–688`; `P/study_harness/executor.py:360–387`; `P/study_harness/acceptance.py:66–214`; `P/runtime/run_manager.py:1914–1924,3573–3606,3644–3662`; `P/api/routes/runs.py:135–144,1126–1170`; `P/mcp_server/server.py:589–611,779–845`.
- `8f73e38` — `OPEN-ISL-3: test frequency-feedback validity and payload` — `P/tests/test_dr_isl_frequency_feedback.py:1–298` (force-added because `attached_assets/` is ignored).
- Report-only commit — this report, `PHASE_5B_FAILING_TESTS.txt`, and compact JSON/JUnit evidence in `tools/dr_isl/phase5b/`.
- No scenario JSON was edited; no frequency/physics or dispatch behavior was changed. No `*.channels.csv` is tracked.
- The development workflow was restarted after the commits; GET `/` returned HTTP 200.

**Final verdict: PASS.** Frequency feedback now affects run certification only when a configured path can affect physical results. No physical ticks changed, the 27 prior study metrics remain identical, all three certified comparisons retain PASS 10/10, and the full suite has no added failure. STOP — end of Phase 5b.
