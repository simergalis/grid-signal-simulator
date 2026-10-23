# Phase 6 stop diagnosis and SuperCloud download

Read-only application-code diagnosis. No application, test, scenario, or configuration files were changed. The D4 candidate remains in `stash@{0}` at `52ee2a88971cfd122a654352e20c6442d15e150c`.

## Part A — MIT SuperCloud public data

The download inventory, object metadata, SHA-256 values, byte and line counts, header, UTC date coverage, and ignore/tracking checks are recorded in [`SUPERCLOUD_DOWNLOAD.md`](SUPERCLOUD_DOWNLOAD.md). Only `slurm-log.csv` and `tres-mapping.txt` were downloaded. No generator was brought in and D6 was not started.

## B1 — D4 candidate failure diagnosis

Tests were run individually in the scratch worktrees at candidate `stash@{0}` and base `f6ac658`; the base H1 determinism test took 297.31 seconds. `tc163` and `tc_ssh08_05` fail at both revisions; `tc164` passes at base and fails on the candidate; the H1 named test fails on the candidate before simulation, while its base run passes.

| Test | Base `f6ac658` | D4 candidate | Literal finding and classification |
|---|---|---|---|
| `tests/test_mcp_server.py::test_tc163_base_demo_comparison_includes_claim_note` | FAIL | FAIL | `tests/test_mcp_server.py:461`: expected `result["verdict"] == "PASS"`; actual `"FAIL"`. The fixture at `:424–437` lacks frequency-feedback fields. `study_harness/acceptance.py:29–41` returns `frequency_feedback_unknown`; `:88–96` consequently sets `baseline_valid` and `informed_valid` false. Direct `compare_metrics` output: both validity conditions false; all other eight conditions true; missing frequency fields are `null`; verdict `FAIL`. This is the already-committed IMPL-ISL-22 fail-closed behavior, not a D4 regression; the fixture expectation is stale. |
| `tests/test_mcp_server.py::test_tc164_shared_identity_and_cache_match_for_every_study_scenario` | PASS | FAIL | `tests/test_mcp_server.py:505`: expected digest `73e5d3f1adb1deecf797436599c4caa42e02692fa19f9a554d2ea9e15e0a9f48`; actual `87189befe9debce735877b28860b30e4dfde68743053f1aa63f475938fb9ca01`. An instrumented candidate replay found the first mismatch on `scenario-h1-k8s-ray-24h`, baseline mode. `mcp_server/server.py:405–422, 446–452` computes the request/run/cache identity with the request's `seed=None`; `study_harness/executor.py:541–560` draws/resolves the root seed, and `:350–358` builds the record identity with that resolved seed. Thus the run identifier/cache identity and record identity disagree. This is a D4 integration regression, not merely an outdated expected digest. Fix direction: resolve the root seed once before creating the run/cache identity, then pass that same manifest through execution. |
| `tests/test_mcp_server.py::test_tc_ssh08_05_identical_real_commits_still_compare` | FAIL | FAIL | `tests/test_mcp_server.py:587`: expected comparison verdict `"PASS"`; actual `"FAIL"`. The fixture at `:526–541` omits frequency-feedback fields and gets the same `frequency_feedback_unknown` / false-validity result as `tc163` under `study_harness/acceptance.py:29–41, 88–96`. This is the pre-D4 IMPL-ISL-22 fail-closed behavior; the fixture expectation is stale. |
| `tests/test_study_harness.py::test_h1_informed_is_deterministic_with_bounded_forecast_history` | PASS (1 passed, 297.31 s) | FAIL before a run | Candidate traceback: `TypeError: StudyRunExecutor._probe() missing 1 required keyword-only argument: 'seed_manifest'` at `tests/test_study_harness.py:338–341`; the candidate signature requires it. This is a stale test caller, not evidence of different physical results. Separately, two candidate H1-24h informed runs were executed with the same explicit root seed 42 and seed manifest: both had 17,280 ticks and physical hash `437d480102d11676df747a5ddc742cd29c9785956c1255098dc8d00d9f18a264`; their records and reported metrics matched (fuel `5848.898717938` MMBtu, curtailment `176.779572526` MWh, unserved `0.124133405` MWh, peak unserved `20.746308977` MW, final BESS SoC `0.999999989`). No physical difference was observed. |

The first and third failures predate D4: `f6ac658` (`2026-10-23 04:25:57 +0000`, `IMPL-ISL-22: frequency validity fails closed on missing fields`) contains the behavior. That commit changed `runtime/run_manager.py`, `study_harness/acceptance.py`, `tests/test_dr_isl_frequency_feedback.py`, and two Phase 6 evidence files.

## B2 — hash-contract gate; STOP

The recorded contract in `tools/dr_isl/phase5b/V1_V3_RESULTS.json:929` is SHA-256 over ordered ticks, compact sorted-key JSON plus LF, excluding exactly `advisory_telemetry`, `fabric_modal`, `wall_stamp_utc`, and `insufficient_reserve_proposal_id`, with NaN allowed. Base `tools/dr_isl/baseline_runner.py:33–50` and candidate `core/physical_identity.py:34–61` implement the same field exclusions and serialization for these TickResult values (including `ensure_ascii=True`, which is the JSON default in the candidate helper).

On base `f6ac658`, a fresh seed-42 `scenario-uneven-multisched-01` study-harness capture produced 1,440 ticks per arm. Both hash methods returned the same hashes:

| Arm | Phase 5b contract | D4 candidate helper | Saved Phase 5b hash (`V1_V3_RESULTS.json:1211, 1244`) |
|---|---|---|---|
| Baseline | `f1ebd90e589a217bbaf85264a2153a268a493a8b644c75ebbe74fd89c7f5def6` | `f1ebd90e589a217bbaf85264a2153a268a493a8b644c75ebbe74fd89c7f5def6` | `e9a25202a069acdb648779981f07bc27e1cbe53a5a2b44e1571bd8724912a5f9` |
| Informed | `72cc28766574a78c44913d389207bc6cca268ac1bf29b15abd148c63af334754` | `72cc28766574a78c44913d389207bc6cca268ac1bf29b15abd148c63af334754` | `34bc07cdebda13c4e07bc990408745fbeeb5f916248cd7159d9f8fd656ee2702` |

The fresh run's reported metrics matched the saved values: baseline curtailment `8.136511735` MWh, turbine fuel `714.363019086` MMBtu, unserved `0.351692658` MWh, peak unserved `22.309362466` MW; informed curtailment `5.278943188` MWh, turbine fuel `665.398247704` MMBtu, unserved `0.020719074` MWh, peak unserved `7.52325057` MW.

**Gate failed:** the Phase 5b contract does not reproduce either saved hash, and the two serializers agree exactly on the fresh tick stream. This is not a helper-serialization difference. No Phase 5b per-tick rows were retained; `tools/dr_isl/phase6/6_3A_BASE_DEMO_GATE.json:11` records that their rows/hash context were not retained. Therefore the first historical differing tick/field cannot be identified from the available evidence. The base harness also does not pass its `seed=42` argument to the context build in `_probe` (`study_harness/executor.py:302–328`) or `_run_mode` (`:350–366`); the seed is used in identity construction (`:350–358`). This is relevant evidence, but does not establish the missing first field. Per the gate instruction, diagnosis stopped here; no D4 code or tests were changed.

## B3–B4 — cleanup and base confirmation

- Removed the scratch worktrees `/tmp/isl-p6diag` and `/tmp/isl-p6base`; neither remains in `git worktree list`.
- `f6ac658` is `f6ac65849906df7ab33654a0b126a79c9af23d04`, authored `2026-10-23 04:25:57 +0000`. Its stat is the five files listed above and its `study_harness/acceptance.py:29–41, 88–96` contains the unknown-frequency handling.
- The D4 candidate stash is `52ee2a88971cfd122a654352e20c6442d15e150c`, dated `2026-10-23 11:06:06 +0000`; it remains `stash@{0}` and was not applied to the main tree.
- Main was `cd4e3958d87af8a57a6b3e5506d0a1d5bea07c9b` before this report. The application subtree diff from `f6ac658` was empty. The SuperCloud data remains ignored and untracked; no data file or CSV is part of this report commit.
