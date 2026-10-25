# IMPL-ISL-25 STOP diagnosis

## X1 — identity payloads

Constructed `make_study_run_identity(...).payload()` for seed 42, baseline and informed, from the expanded specs at b9c268f and current HEAD 600ffb4. No simulation ran. For the comparison, both `engine_commit` and `harness_commit` were set to `IMPL_ISL_25_NORMALIZED_COMMIT`. All six canonical payloads and SHA-256 digests are byte-identical after normalization; field-level diff count is zero in every case, including all `parameter_set` fields. Digests are recorded in `tools/dr_isl/isl25/IDENTITY_DIAGNOSIS.json`.

Raw commit strings at clean capture: b9c268f worktree — engine/harness `b9c268f1cc895686e912e3132b154e3b24731e35`; current tree — engine/harness `600ffb4e38a091f2829c1243ea334372553f1351`. The stopped gate captured `b9c268f…-dirty` for both. `_live_git_commit()` adds `-dirty` when `git status --porcelain --untracked-files=all` is non-empty. The gate ran before the uncommitted IMPL-ISL-25 source/test changes and `tools/dr_isl/isl25/` evidence were committed as 600ffb4.

## X2 — commit 600ffb4

`git show --stat 600ffb4` identifies it as a Replit Agent commit (`Replit-Commit-Author: Agent`) with the generic message “Expand mcp server functionality and update study harness tests.” It contains the IMPL-ISL-25 implementation in `mcp_server/server.py` and `study_harness/executor.py`, tests in `test_mcp_server.py` and `test_study_harness.py`, plus five evidence/tool files under `tools/dr_isl/isl25/`. Full file list is in the JSON evidence.

No application, test, or scenario changes were made for this diagnosis. The temporary b9c268f worktree was removed.
