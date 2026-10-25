# IMPL-ISL-25 STOP diagnosis

## X1 — identity payloads

Constructed `make_study_run_identity(...).payload()` for seed 42, baseline and informed, from the expanded specs at b9c268f and current HEAD 600ffb4. No simulation ran. For the comparison, both `engine_commit` and `harness_commit` were set to `IMPL_ISL_25_NORMALIZED_COMMIT`. All six canonical payloads and SHA-256 digests are byte-identical after normalization; field-level diff count is zero in every case, including all `parameter_set` fields. Digests are recorded in `tools/dr_isl/isl25/IDENTITY_DIAGNOSIS.json`.

Raw commit strings at clean capture: b9c268f worktree — engine/harness `b9c268f1cc895686e912e3132b154e3b24731e35`; current tree — engine/harness `600ffb4e38a091f2829c1243ea334372553f1351`. The stopped gate captured `b9c268f…-dirty` for both. `_live_git_commit()` adds `-dirty` when `git status --porcelain --untracked-files=all` is non-empty. The gate ran before the uncommitted IMPL-ISL-25 source/test changes and `tools/dr_isl/isl25/` evidence were committed as 600ffb4.

## X2 — commit 600ffb4

`git show --stat 600ffb4` identifies it as a Replit Agent commit (`Replit-Commit-Author: Agent`) with the generic message “Expand mcp server functionality and update study harness tests.” It contains the IMPL-ISL-25 implementation in `mcp_server/server.py` and `study_harness/executor.py`, tests in `test_mcp_server.py` and `test_study_harness.py`, plus five evidence/tool files under `tools/dr_isl/isl25/`. Full file list is in the JSON evidence.

No application, test, or scenario changes were made for this diagnosis. The temporary b9c268f worktree was removed.

## Resume attempt — D6c replay and H1 gate stop

### Base-demo scratch comparison

Re-ran `scenario-uneven-multisched-01`, seed 42, in a temporary worktree at D6c HEAD `d12ed881e6c0c0f553132aa3282f3e92baf5b18b` using the study executor. Compared the resulting baseline record with the already-recorded current baseline record. After excluding commit/identity fields, run ID, artifact paths, and `seed_manifest.resolved_at_utc`, there were no differing record paths. The baseline and informed physical hashes remain `f1ebd90e…` and `72cc2876…`; `compare_runs` is PASS with 10 conditions.

Both baseline commitment logs contain 8 entries and hash to `f208644ee01902db2161a740ddb771ce8376a287aa1bc71d280bd20754df45fd` (3,553 canonical JSON bytes). The current informed log and the fresh D6c informed log both contain 11 entries and hash to `35166e43c54cffe3d4c81ac60faef2684d94ce26e7662eb611b246e800002c0d` (5,627 bytes). The saved D6c baseline metric summary instead records `8f6b038c4b7feaa0830e28105708aa20852e0c4cfa4c767a5adb255168a6e2e3` (8 entries, 3,541 bytes), which the direct D6c replay did not reproduce. Thus the base-demo log discrepancy is present in the saved reference itself, not a difference between the D6c replay and the current run.

The base-demo normalized identity digests are `7ac34caca5ba76c53fea696f076249e1c56c9110f4f14aded1b9f77d9adafc42` (baseline) and `dd3f44a2f730c5f347113a3c01bcdb9ce6935db66f360b0c55d6eb2e1e4ac782` (informed), matching the b9c268f payloads. Raw current identity digests and commit strings, plus the comparison evidence, are in `tools/dr_isl/isl25/PROTECTED_STUDY_GATES_RESUMED.json`.

### H1 protected gate — STOP

Ran the H1 pair at seed 42. Both normalized identity payloads match the b9c268f payloads; physical hashes match D6c exactly (`c4fa3b355b2eebf949f1f0ad9f43b1b76770cf05bb380d224a3282699985fc20` baseline; `437d480102d11676df747a5ddc742cd29c9785956c1255098dc8d00d9f18a264` informed). The comparison verdict is PASS, with the same 10/10 conditions and values as D6c. All compared metrics match except `commitment_log` in both arms:

| Arm | D6c saved log summary | Current H1 log |
|---|---|---|
| Baseline | 48 entries; 21,318 bytes; `939ef35455be9d4aaf8df5e1c05dc32944eb675277f41c4d4e2c411c42afe8dd` | 48 entries; 21,390 bytes; `72a8e76fb85b9751d6455404e28a987dd17356f03c170197d045d6acb3bc1c34` |
| Informed | 59 entries; 27,608 bytes; `936b820fb671d0d805ff9700fc4ce4c9f71a53f2190b6d9f86da0580fabe6995` | 59 entries; 27,614 bytes; `7d0dafc1bb03c88f9c70f54223de7b22e339d9770567f0640ab50ba22f1b6451` |

The saved D6c evidence contains only the commitment-log digests, not the event rows, so the underlying event-level difference cannot be located from that evidence. No D6c H1 replay was run. Per the acceptance stop rule, work stopped at H1; H2, S10 MCP runs, TC-ISL-65–73, existing-scenario hash reruns, and both full-suite runs were not started. No application, test, or scenario files were changed. The progress evidence is `tools/dr_isl/isl25/PROTECTED_STUDY_GATES_RESUMED.json`.

## IMPL-ISL-25 STOP follow-up — H1 commitment-log diagnosis (Y1–Y3)

Ran `StudyRunExecutor.run_pair` in a temporary, clean worktree at D6c HEAD `d12ed881e6c0c0f553132aa3282f3e92baf5b18b`, seed 42. The pair completed in 266.496 s; `compare_runs` was PASS with 10 conditions. The fresh D6c physical hashes match the current H1 hashes exactly.

Entry-by-entry, the fresh D6c and current H1 `commitment_log` lists are equal in both arms: baseline 48/48 entries, informed 59/59. There are zero differing entries or fields. Action, target unit, simulation time, reason, acceptance, state transition, and source fields therefore also have zero decision differences.

`tools/dr_isl/d6c/ACCEPTANCE_STUDY_GATES.json` stores only summary objects for these H1 logs (baseline at lines 736–742; informed at lines 1113–1119), not the event rows, so those saved rows cannot be diffed entry by entry. However, serializing the current logs with `ensure_ascii=False`, sorted keys, and compact separators reproduces the saved D6c hashes and byte counts exactly:

| Arm | Entries | `ensure_ascii=False` — saved D6c hash / bytes | Default `ensure_ascii=True` — earlier resumed-summary hash / bytes |
|---|---:|---|---|
| Baseline | 48 | `939ef35455be9d4aaf8df5e1c05dc32944eb675277f41c4d4e2c411c42afe8dd` / 21,318 | `72a8e76fb85b9751d6455404e28a987dd17356f03c170197d045d6acb3bc1c34` / 21,390 |
| Informed | 59 | `936b820fb671d0d805ff9700fc4ce4c9f71a53f2190b6d9f86da0580fabe6995` / 27,608 | `7d0dafc1bb03c88f9c70f54223de7b22e339d9770567f0640ab50ba22f1b6451` / 27,614 |

The discrepancy is JSON escaping in the earlier evidence summarizer, not run metadata or event values: `/tmp/isl25_protected_resume.py:13–15` calls `json.dumps` without specifying `ensure_ascii`, so Python defaults to `True`; the saved digests reproduce with `False`. The reason strings contain the Unicode `≤` character, constructed in `core/commitment.py:408–409`. The baseline log contains 24 such characters (72 extra bytes when escaped); the informed log contains 2 (6 extra bytes). No `run_id`, commit string, timestamp, wall-clock, float-formatting, or dict-order variation was found in the event lists.

The apparent H1 commitment-log metric failure recorded in the preceding section is resolved as a serializer mismatch. This diagnostic ends here as requested: no H2 run, S10 MCP run, test, suite, or application change was made. The full entry-level comparison and both serialization measurements are in `tools/dr_isl/isl25/COMMITMENT_LOG_DIAGNOSIS.json`.

## IMPL-ISL-25 resumed acceptance

### Canonical commitment-log evidence

Updated the evidence summarizer in `tools/dr_isl/isl25/run_protected_study_gates.py` to hash large metric values as sorted-key compact JSON with `ensure_ascii=False` (`canonical_json_bytes`, lines 31–37). The earlier default-`ensure_ascii=True` base-demo baseline result (`f208644e…`, 3,553 bytes) was a serializer artifact. With the corrected encoding, the base-demo baseline log matches the saved D6c reference exactly: 8 entries, 3,541 bytes, SHA-256 `8f6b038c4b7feaa0830e28105708aa20852e0c4cfa4c767a5adb255168a6e2e3`. The informed log also matches: 11 entries, 5,627 bytes, SHA-256 `35166e43c54cffe3d4c81ac60faef2684d94ce26e7662eb611b246e800002c0d`.

The retained H1 logs match the D6c reference with the same serializer: baseline 48 entries / 21,318 bytes / `939ef35455be9d4aaf8df5e1c05dc32944eb675277f41c4d4e2c411c42afe8dd`; informed 59 / 27,608 / `936b820fb671d0d805ff9700fc4ce4c9f71a53f2190b6d9f86da0580fabe6995`. No H1 full simulation was rerun in this continuation: retained current H1 records were compared with the fresh D6c run from Y1, and their event lists are equal. Base-demo and H1 gate records were retained; H2 was freshly run as a pair. The commitment-log evidence is in `PROTECTED_STUDY_GATES_FINAL.json` and `CANONICAL_COMMITMENT_LOG_RECHECK.json`.

### Protected study gates

For all six seed-42 baseline/informed payloads, the exact `StudyRunExecutor.run_pair` identity payloads match the b9c268f payload after normalizing only `engine_commit` and `harness_commit`. Physical hashes, reported metrics and `compare_runs` also match D6c; each pair is PASS 10/10. Normalized identity SHA-256 values and physical SHA-256 values:

| Study / arm | Normalized identity SHA-256 | Physical SHA-256 | D6c metrics/hash | `compare_runs` |
|---|---|---|---|---|
| Base demo / baseline | `233d16a239b2020d9e71edf1a20a6897eb5fef8579bc7b0db0a554d823193eca` | `f1ebd90e589a217bbaf85264a2153a268a493a8b644c75ebbe74fd89c7f5def6` | match | PASS 10/10 |
| Base demo / informed | `6767facb028330378dcea19332c49189e7afc815da286adeb97ebf228d6b6e81` | `72cc28766574a78c44913d389207bc6cca268ac1bf29b15abd148c63af334754` | match | PASS 10/10 |
| H1-24h / baseline | `d669c1378eeb338ab2a24f28dfbb495f1d775680fc6a1d684e704d6f82d718fd` | `c4fa3b355b2eebf949f1f0ad9f43b1b76770cf05bb380d224a3282699985fc20` | match | PASS 10/10 |
| H1-24h / informed | `e774b002389627eeb1ff953418f364d9b77f30353409d227e04f2f8737c48b3d` | `437d480102d11676df747a5ddc742cd29c9785956c1255098dc8d00d9f18a264` | match | PASS 10/10 |
| H2-24h / baseline | `b4a20e4f40db4b94eabbb6baa347c7fb4f45c78711b0296aaa1d5bcc35438707` | `603441374503951709dc77d5ae11234e966d5b479e50edca5dd608c7782f217f` | match | PASS 10/10 |
| H2-24h / informed | `7c2fd7bde9ed927c0b44740cb46a3ad4c510f88483a95906a0b8a8bc8800a44b` | `17954e9420ad8d0c9493a690c03cd670ae0a5f57df60f801b7c292aeea3a9fba` | match | PASS 10/10 |

H2 completed at 17,280 ticks per arm; its normalized identities, physical hashes, all recorded metrics, and all ten comparison conditions match the D6c evidence. The exact H2 payload is in `H2_PROTECTED_GATE_VERIFIED.json`. Full gate evidence is in `PROTECTED_STUDY_GATES_FINAL.json`.

### Existing scenarios and pinned S10 reference

All eight existing `ctx.step` hashes match `tools/dr_isl/d6c/ACCEPTANCE_EXISTING_SCENARIO_HASHES.json`; no physical hash changed:

| Scenario | Physical SHA-256 | Ticks |
|---|---|---:|
| `scenario-equinix-sj-1` | `616a769cd5b79c243eb7d4d91ff062651e8c2c6e5351f468f0bc4e3a29eab6a7` | 720 |
| `demo-islanded-ramp` | `f293c4ad161357df6fef9a5e01dbb78098bfcd331c2e7e8ca286c56c9a8ef13e` | 2,160 |
| `S10_mit_supercloud_2021-08-11` | `f230ae8f141183e1e6bcdb8dda0eb8f4920bf5674167bba972e4a72f37c64353` | 17,280 |
| `scenario-turbine-01` | `b0196383e7b4ef1110f700c762a827ce45460acdfa6792484d0d0074e61d344e` | 720 |
| `scenario-hybrid-ai-100mw-addendum-i` | `2400c1a448bd74fc37248e610c13b026f77e5634672f35142041719ded7ae0c4` | 120 |
| `scenario-100mw-fuel-cell-bess-diesel` | `59f042706562f949250e5eb721bdd817a30e9fd1953f16db52ef003ef3488b98` | 252 |
| `scenario-fc100-islanded-v2` | `d381f9837605c79f8d773c98044856877d42d0cd7b7d51b99cd6db8a98610314` | 264 |
| `scenario-fc100-islanded-zero-hot-v2` | `952856bb0068913efe767d80ec200f4ca5c0dc8807f5555664e79c4b18965559` | 264 |

The authoritative D6c comparison is `EXISTING_SCENARIO_D6C_COMPARISON.json`. The accepted pinned-runner S10 reference remains physical SHA-256 `ad91ced6445f21aa4a9a9b4ccb2fb4dd5114d42f2eae3ab5e0be5769fceaf508`, non-fuel SHA-256 `e0ccf0e15265d70738e53c74d273e8ab223d9b30b4439797b8188cb76be7aaba` (`S10_PINNED_CURRENT.json`).

### S10 MCP operation

The in-process MCP service lists S10 as `supercloud_replay`, returns its own tracked scenario JSON, and completed both arms at seeds 42 and 1729. Each run emitted 17,280 ticks; the study input contains 239 workload events and a 320-point non-GPU profile. `get_run_metrics` returned the `operating_cost` energy section. The baseline and informed physical identity hashes and results were identical across the two seeds; the separate seed manifests differ only in `resolved_at_utc`. Wall times vary by run:

| Seed | Arm | Wall seconds | Unserved MWh | Peak unserved MW | Turbine fuel MMBtu | Starts | Invalid-frequency ticks / fraction | Operating-cost total | $/MWh served | $/MWh IT |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 42 | Baseline | 112.124 | 5.535769413 | 16.8004944 | 7,785.288838529 | 37 | 519 / 0.0300347222 | $50,128.167955 | $81.334381725 | $97.305371991 |
| 42 | Informed | 147.154 | 13.940406890 | 31.8004944 | 7,428.015428680 | 47 | 628 / 0.0363425926 | $47,890.547243 | $78.778056313 | $92.961855668 |
| 1729 | Baseline | 111.517 | 5.535769413 | 16.8004944 | 7,785.288838529 | 37 | 519 / 0.0300347222 | $50,128.167955 | $81.334381725 | $97.305371991 |
| 1729 | Informed | 139.599 | 13.940406890 | 31.8004944 | 7,428.015428680 | 47 | 628 / 0.0363425926 | $47,890.547243 | $78.778056313 | $92.961855668 |

Baseline physical identity SHA-256 is `22a109ae31e928518db467fbe3ff90675604ce2e38c0f6ed5551c21aa10d9a3f`; informed is `31500784c695aec403662bb71ccccb0dff6e74d1cb5440197b43251330d380b0`. For both seeds, the ten `compare_runs` conditions are:

| Condition | Result |
|---|---|
| `build_parity` | PASS |
| `baseline_valid` | PASS |
| `informed_valid` | PASS |
| `baseline_energy_balance` | PASS |
| `informed_energy_balance` | PASS |
| `baseline_fuel_reconciled` | PASS |
| `informed_fuel_reconciled` | PASS |
| `identical_compute_trace` | PASS |
| `informed_unserved_energy_no_worse` | FAIL |
| `informed_peak_unserved_no_worse` | FAIL |

Both S10 comparisons therefore report FAIL 8/10, solely because informed unserved energy and peak unserved energy exceed baseline; S10 remains operational, not certified. Both arms report `frequency_feedback_configured=false` and `protection_configured=false`, so the invalid-frequency counts are informational.

The itemized cost lines are the same at both seeds. Baseline: gas 8,626.100033 MMBtu (HHV), $44,344.975194; diesel 0.0 gal, $0; turbine VOM $3,818.809199; turbine FOM $1,964.383562; total $50,128.167955. Informed: gas 8,230.241095 MMBtu (HHV), $42,309.947230; diesel 0.0 gal, $0; turbine VOM $3,616.216451; turbine FOM $1,964.383562; total $47,890.547243. Start, BESS degradation, and unserved-energy lines have null prices and are excluded. The MCP payload currently reports a zero diesel quantity and includes a zero-dollar diesel line although S10 has no diesel fleet; this does not change either total, but differs from the D6c no-fleet-null semantics. No application change was made for it. Full line details are in `S10_MCP_ACCEPTANCE.json`.

Seed-42 MCP/REST parity passed across all 17,280 ticks at the 0.00005 tolerance. Maximum absolute difference was 0.0 for every compared float field, including each of five turbine outputs; `frequency_valid` and `turbine_start_count` had zero mismatches, as did turbine unit state and unit counts. REST wall time was 250.066 seconds. See `S10_MCP_ACCEPTANCE.json`.

### TC-ISL tests and full suite

TC-ISL-65 through TC-ISL-73 are present and PASS in both complete suite runs:

| ID | Test | Source |
|---|---|---|
| 65 | `test_tc_isl_65_s10_list_and_get_scenario_use_tracked_source` | `tests/test_mcp_server.py:471` |
| 66 | `test_tc_isl_66_s10_start_run_metrics_and_compare_are_reachable` | `tests/test_mcp_server.py:503` |
| 67 | `test_tc_isl_67_s10_expansion_uses_canonical_json_without_fuel_overlay` | `tests/test_study_harness.py:672` |
| 68 | `test_tc_isl_68_s10_pair_shares_probe_and_non_gpu_profile` | `tests/test_study_harness.py:709` |
| 69 | `test_tc_isl_69_s10_source_events_are_part_of_run_identity` | `tests/test_study_harness.py:753` |
| 70 | `test_tc_isl_70_unprotected_s10_invalid_ticks_are_informational` | `tests/test_mcp_server.py:570` |
| 71 | `test_tc_isl_71_rest_physics_parity_enforces_rounding_and_discrete_fields` | `tests/test_study_harness.py:860` |
| 72 | `test_tc_isl_72_cache_identity_isolates_s10_source_event_edits` | `tests/test_study_harness.py:789` |
| 73 | `test_tc_isl_73_existing_base_and_h_identities_match_prechange_evidence` | `tests/test_study_harness.py:830` |

The real-package full suite completed under both `PYTHONHASHSEED=1` and `987654321`. Each run: 2,255 passed, 15 failed, 3 skipped, 23 xfailed, 54 warnings, and 3 passing subtests (2,296 test cases; 14:07.20 and 14:09.07). Both failing-ID sets are identical. Against `tools/dr_isl/PHASE_6C_FAILING_TESTS.txt`, there were zero added failures; the only removal in both runs was the waived `tests/test_gpu_load_profile.py::test_gpu_load_profile`, which passed in each run. The 15 remaining IDs are saved separately in `PHASE6C_HASH1.FAILING_TESTS.txt` and `PHASE6C_HASH2.FAILING_TESTS.txt`; summaries and JUnit XML are in `tools/dr_isl/isl25/`.

### Logged item and provenance

Logged IMPL-ISL-28, report-only: `study_harness/executor.py:123–138` removes raw `workload_events` from the identity parameter set for all classes, but adds `workload_events_sha256` only for `supercloud_replay` (`:127–132`). Thus a base-demo or H-class source-event timeline edit is not independently represented in that class's identity/cache key.

The IMPL-ISL-25 implementation remains commit `600ffb4e38a091f2829c1243ea334372553f1351`; its files are `mcp_server/server.py`, `study_harness/executor.py`, `tests/test_mcp_server.py`, `tests/test_study_harness.py`, and five `tools/dr_isl/isl25/` evidence/runner files. This completion changed no application, test, or scenario files. The pinned S10 acceptance script changes its working directory to the package root (`run_s10_mcp_acceptance.py:28–30`) because the in-process app resolves catalogue/fabric paths relative to that directory.

`git ls-files | grep -i -E 'slurm-log\\.csv|tres-mapping\\.txt|channels\\.csv|gridsignal\\.db'` returned no paths. No CSV or SuperCloud raw data was added.
