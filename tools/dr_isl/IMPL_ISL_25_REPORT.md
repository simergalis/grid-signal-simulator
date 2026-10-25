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
