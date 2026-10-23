# DR-2026-10-20-ISLAND-COLLAPSE — Phase 6 report (stopped at 6.5)

**Result: STOP.** The first full-suite run added four failures against `tools/dr_isl/PHASE_5B_FAILING_TESTS.txt` (19 current vs 15 baseline). Per the Phase 6 gate, the second `PYTHONHASHSEED` suite was not started, no fixes or Phase 6 commits were made, and the D4 candidate is being returned to a stash with the main application tree at base `f6ac65849906df7ab33654a0b126a79c9af23d04`.

## 6.0 — IMPL-ISL-22
- Base application commit: `f6ac65849906df7ab33654a0b126a79c9af23d04`.
- The candidate changes `study_harness/acceptance.py` and restored-run handling to preserve unknown frequency fields as `null`; unknown feedback/count fails frequency validity with a reason instead of defaulting to `False`/`0`.
- Focused 6.0 tests: 16 passed (the recorded Phase 6.0 result).

## 6.1 — D4 inventory
- Full RNG/clock inventory: `tools/dr_isl/phase6/6_1_D4_INVENTORY.md` (source locations and old pinning details). It covers Kube/Slurm/Ray RNGs (`core/kube_demand.py`), per-diesel `random.Random` (`core/asset_modules.py`), cluster/stressor/parameter generators, telemetry corruption, SolarSim, fabric's old `hash(run_id)`, de-identification, random IDs, run wall stamps, API solar forecast time, advisory cadence and wall-clock pacing.
- The inventory states that API solar forecast samples/ambient steps are materialized in the run spec, wall stamps are non-physical, and automatic advisory proposals do not feed back into physics. Existing interactive SolarSim/live behavior was not evaluated by the headless direct-`ctx.step()` comparisons below.

## 6.2 — D4 candidate (not committed/validated)
- One seed resolver: `P/runtime/seed_resolution.py:18–81`; root `None` draws and records one seed; named consumers use SHA-256 derivation version `d4-sha256-v1` (`:12–15,51–80`). `seed_consumers_for_spec` lists consumers/configured seeds (`:84–139`); factory wiring and run metadata are in `P/runtime/scenario_factory.py` and `P/runtime/run_manager.py`.
- Physical identity has one helper and the exact four exclusions (`P/core/physical_identity.py:15–22,47–61`): `advisory_telemetry`, `fabric_modal`, `wall_stamp_utc`, `insufficient_reserve_proposal_id`; each tick is compact, sorted-key JSON plus LF, with NaN allowed.
- Study cache identity is version 3 (`P/study_harness/executor.py:52,85–86`) and includes the seed derivation version to prevent reuse of old cache identities.
- The candidate uses simulation time for advisory cadence in `study`/`headless` and wall time for `interactive` (`P/runtime/run_manager.py:82–87`). It records/replays SolarSim input traces (`P/runtime/run_manager.py:2651–2702`).
- `PHYSICAL_TICK_HASH_EXCLUSIONS` and `SEED_DERIVATION_VERSION` carry `PROPOSED_HERE` rationale/source comments (`P/core/physical_identity.py:12–15`; `P/runtime/seed_resolution.py:12–15`).

## 6.3 — acceptance evidence
### (a) Explicit seed 42, pre-D4 base `f6ac658` versus candidate
All six runs (base demo, H1-24h, H2-24h; both arms) had **zero differing physical tick fields**, equal tick counts and equal physical hashes on both sides. All 31 compared metric fields were equal (the original 27 plus four frequency-reporting fields); `compare_runs` remained PASS with all 10 conditions true for each pair. Evidence: `6_3A_TICK_FIELD_COMPARISON.json`, `6_3A_METRIC_COMPARISON.json`.

| Case/arm | ticks | common base/candidate physical SHA-256 |
|---|---:|---|
| base demo baseline | 1,440 | `f1ebd90e589a217bbaf85264a2153a268a493a8b644c75ebbe74fd89c7f5def6` |
| base demo informed | 1,440 | `72cc28766574a78c44913d389207bc6cca268ac1bf29b15abd148c63af334754` |
| H1-24h baseline | 17,280 | `c4fa3b355b2eebf949f1f0ad9f43b1b76770cf05bb380d224a3282699985fc20` |
| H1-24h informed | 17,280 | `437d480102d11676df747a5ddc742cd29c9785956c1255098dc8d00d9f18a264` |
| H2-24h baseline | 17,280 | `603441374503951709dc77d5ae11234e966d5b479e50edca5dd608c7782f217f` |
| H2-24h informed | 17,280 | `17954e9420ad8d0c9493a690c03cd670ae0a5f57df60f801b7c292aeea3a9fba` |

The old 6.0 saved hash values differ from these fresh hashes, but the retained old per-tick rows are unavailable for field-level comparison. The fresh base-versus-candidate comparison is zero-field-difference; this discrepancy is documented in `6_3A_BASE_DEMO_GATE.json`.

### (b) Separate-process unpinned pairs
Two fresh processes per scenario used run seed `1729`, `PYTHONHASHSEED=1` and `987654321`, without `baseline_runner` pinning, using ScenarioSpec + `build_run_context_from_spec` and direct `ctx.step()` headless ticks. A preliminary RunManager trial exceeded its 300-second command timeout; the recorded comparisons therefore use this direct engine path. Each pair had identical seed manifests, hashes and tick counts; every run had zero physical-balance failures. Every current hash differs from the Phase 5b pinned hash because each scenario contains derived null-config consumers (at least `advisory_deidentification`, `fabric`, and `solar_sim`); diesel/Kube derived consumers are shown where present. Old fabric used `hash(run_id)`, while the old runner also pinned null streams to 1729. Full per-scenario seed sources and values: `6_3B_SEED_SOURCES.json`, `6_3B_UNPINNED_RESULTS.json`.

| Scenario | ticks | D4 hash (both processes) | Phase 5b pinned hash | equal? |
|---|---:|---|---|---|
| scenario-turbine-01 | 720 | `b0196383e7b4ef1110f700c762a827ce45460acdfa6792484d0d0074e61d344e` | `23fffd3cf5f1281cb72742254e05d393c705e5cdacf2fe5036541e8deedb59b4` | no |
| S10_mit_supercloud_2021-08-11 | 17,280 | `107c7a5766f99f79d750b50401c8e3341d2b350e18156a312db13ab82679876a` | `3e24904fd7e8f71afa1f5b30ec2f2958a6b43e7670ab9fefae04f3440aa57bff` | no |
| scenario-equinix-sj-1 | 720 | `616a769cd5b79c243eb7d4d91ff062651e8c2c6e5351f468f0bc4e3a29eab6a7` | `84a8294e726190fa58a869f9e64b455bfb3ef7675bad448ae39f643f269db510` | no |
| scenario-hybrid-ai-100mw-addendum-i | 120 | `2400c1a448bd74fc37248e610c13b026f77e5634672f35142041719ded7ae0c4` | `5b71aa3959769d9b579e7781b120bf1fcabecdaed1476481f2e6e5bf56f1ddfb` | no |
| scenario-100mw-fuel-cell-bess-diesel | 252 | `59f042706562f949250e5eb721bdd817a30e9fd1953f16db52ef003ef3488b98` | `dad91d98830c78f678ed4c490729d1a6772046251a979e6c50af3a5f9f6300cb` | no |
| scenario-fc100-islanded-v2 | 264 | `d381f9837605c79f8d773c98044856877d42d0cd7b7d51b99cd6db8a98610314` | `44b5f15a0cee3477fd14f3d22255c17ef42abd6a3765d8adc3443abbf9b88565` | no |
| scenario-fc100-islanded-zero-hot-v2 | 264 | `952856bb0068913efe767d80ec200f4ca5c0dc8807f5555664e79c4b18965559` | `0bc7e7a2a5af0798a4b4a3cdc69687e6084ff57bde0c2b34500545f84115b8ce` | no |
| demo-islanded-ramp | 2,160 | `8d6ab42d8e2cda3f7be1eb2082307a0e2b0940f6cd9697fb2d97a2314c52b944` | `e3b8cc8dfcc4fc4847f653b260e0e9a7c6ee88e1722930ca59567875df2219d6` | no |

### (c) Recorded-seed replay
Three runs were replayed in separate processes with `PYTHONHASHSEED=314159`; all hashes were identical to their recorded D4 run (`6_3C_REPLAY_RESULTS.json`): scenario-turbine-01, 720 ticks, 9 consumers, `b0196383…d344e`; scenario-100mw-fuel-cell-bess-diesel, 252 ticks, 17 consumers, `59f04270…8b98`; scenario-equinix-sj-1, 720 ticks, 9 consumers, `616a769c…b6a7`.

### (d) Randomness findings
The old fabric path depended on Python `hash(run_id)` (`6_1_D4_INVENTORY.md`, original location `P/runtime/scenario_factory.py:2129`); D4 replaces it with a named stable digest. The old null-seed consumers listed in `6_3B_SEED_SOURCES.json` were pinned or entropy-based and are now keyed to the recorded run seed. Across all eight separate-process cases, changing `PYTHONHASHSEED` did not change the D4 physical hash. Their differences from Phase 5b are expected because the D4 derived streams differ from the old pins; no case in the 8-case set had every RNG consumer explicitly configured.

## 6.4 — tests
TC-ISL-34 through TC-ISL-40 were used for seed resolution/recording, stable cross-process consumer derivation, per-diesel seeds, fabric independence from `hash()`, the physical-hash exclusion contract, sim-time advisory cadence, and recorded-seed replay. Focused command: `pytest -q tests/test_dr_isl_phase6_reproducibility.py tests/test_dr_isl_frequency_feedback.py` — **22 passed**.

## 6.5 — full suite gate (STOP)
Real package command: `PYTHONHASHSEED=1 pytest -q --junitxml=tools/dr_isl/phase6/6_5_suite_hashseed1.xml`; completed in 361.91 s. Result: **2,218 passed, 19 failed, 3 skipped, 23 xfailed, 54 warnings, 3 subtests passed**. Baseline: 15 failed. Added: 4. Removed: 0. The added IDs are:
- `tests/test_mcp_server.py::test_tc163_base_demo_comparison_includes_claim_note`
- `tests/test_mcp_server.py::test_tc164_shared_identity_and_cache_match_for_every_study_scenario`
- `tests/test_mcp_server.py::test_tc_ssh08_05_identical_real_commits_still_compare`
- `tests/test_study_harness.py::test_h1_informed_is_deterministic_with_bounded_forecast_history`

All 19 IDs are in `tools/dr_isl/PHASE_6_FAILING_TESTS.txt`; the full JUnit is `tools/dr_isl/phase6/6_5_suite_hashseed1.xml` and the parsed counts/delta are `tools/dr_isl/phase6/6_5_SUITE_HASHSEED1_SUMMARY.json`. Per the stop rule, no `PYTHONHASHSEED=987654321` suite was run, no fixes were attempted, and no D4 implementation/test/report commits were made. The Phase 0 failing-ID list was not found in the workspace or `/tmp`, so that delta cannot be computed.

## 6.6 — stopped state
- Base application: `f6ac65849906df7ab33654a0b126a79c9af23d04`; D4 candidate checkpoint before restoration: `97cdc18ff61f11246bbed290fbc4f9464b055372` (automatic checkpoint, not validated).
- Candidate stash: `stash@{0}`, commit `52ee2a88971cfd122a654352e20c6442d15e150c`, message `DR-ISL Phase 6 D4 candidate; stopped at 6.5 added suite failures`. The stash contains the 15 D4 application/tool files, including the three new package files. Current `main` is at `f6ac658`; `git diff f6ac658 -- P` is empty.
- Evidence files remain in the working tree under `tools/dr_isl/phase6/`; largest is the 6.5 JUnit at 353,936 bytes. No `*.channels.csv` is tracked.
- The D4 candidate was not served. After restoring base, `artifacts/gridsignal: web` was restarted; workflow startup logged `GET /` 200, direct `curl http://127.0.0.1:22126/` returned HTTP 200, and the actual entry module `api.app` imported as `FastAPI`.

### Candidate files and changed line ranges (preserved in `stash@{0}`)
- `P/advisory/agent_registry.py`: 71, 76, 80–83, 160.
- `P/advisory/agents/base.py`: 123, 164.
- `P/api/routes/runs.py`: 76–79, 359–382, 435, 474, 521, 676, 695–697, 719–720, 723–727, 813–814.
- `P/api/schemas.py`: 2837–2842, 2946–2947.
- `P/core/deident.py`: 134–139, 149, 271, 394, 462–465, 482.
- `P/core/physical_identity.py`: new file, 1–83.
- `P/renewable/solar.py`: 643–646.
- `P/runtime/cluster_gen.py`: 230–233, 246, 254, 272, 279.
- `P/runtime/run_manager.py`: 49, 82–88, 1933–1934, 2594, 2652–2669, 2697–2703, 3199, 3283–3285, 3692–3698, 3703–3705, 3723–3726.
- `P/runtime/scenario_factory.py`: 20, 78–81, 234–235, 237–244, 304–306, 386–395, 406–408, 412–414, 441, 454–461, 510–512, 578–589, 611–613, 628–630, 673–676, 701–708, 1120–1127, 1165–1167, 1365–1368, 1377–1379, 1383, 1389–1397, 1672, 1682–1699, 1876–1878, 2033–2035, 2076–2078, 2095–2097, 2188, 2233–2238.
- `P/runtime/seed_resolution.py`: new file, 1–139.
- `P/runtime/stressor_gen.py`: 198–201, 203.
- `P/study_harness/executor.py`: 20–25, 50–52, 85–86, 318, 322–329, 358, 374, 385–387, 398, 402, 413–416, 541–546, 550, 558–559, 579–584, 588, 596–597, 606–607.
- `P/tests/test_dr_isl_phase6_reproducibility.py`: new file, 1–192.
- `tools/dr_isl/baseline_runner.py`: 3–6, 88–91, 117–123, 139, 142–145, 157.

Final source state: `git status` contains only the Phase 6 report/evidence files (plus the progress note); no application source or scenario change remains outside the stash. `main` is `f6ac658`. Replit's automatic `gitsafe-backup/main` still points to unvalidated checkpoint `97cdc18`; it was not modified.
