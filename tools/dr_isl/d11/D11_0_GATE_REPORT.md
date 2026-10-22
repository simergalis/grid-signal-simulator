# D11.0 — STOP: evidence hygiene scope requires clarification

## Literal commit findings

- Original IMPL-ISL-19 report-only commit: `1209c8dd0e418f978a8d001f74687f8dc7ce1a83`.
- `git log -1 --stat` reported 39 files changed, 93,081 insertions.
- It included eight `tools/dr_isl/isl19/*.channels.csv` files, two named for S10.
- Amended local commit: `c8a1e41995d0f8d39c95c97af793d0726f6170b8`.
- All eight channel CSVs removed from the index, retained byte-identically on disk (SHA-256 before/after checked).
- Added `tools/dr_isl/**/*.channels.csv` to `.gitignore`.
- `git ls-files` after amendment contained zero paths ending `.channels.csv`.
- `git status --short` immediately after amendment: empty.
- No application, test or scenario content changed. No simulation or suite started. No push, publish or deployment.

## Remaining tracked paths

Literal results of `git ls-files` filtered case-insensitively for `s10` or `supercloud`:

```text
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/S10_mit_supercloud_2021-08-11.json
tools/dr_isl/isl19/S10_mit_supercloud_2021-08-11_app.baseline.stderr.txt
tools/dr_isl/isl19/S10_mit_supercloud_2021-08-11_app.baseline.summary.json
tools/dr_isl/isl19/S10_mit_supercloud_2021-08-11_app.comparison.json
tools/dr_isl/isl19/S10_mit_supercloud_2021-08-11_app.ledger_cf.stderr.txt
tools/dr_isl/isl19/S10_mit_supercloud_2021-08-11_app.ledger_cf.summary.json
tools/dr_isl/phase4/P3_R1_S10_mit_supercloud_2021-08-11_app_1.base.stderr.txt
tools/dr_isl/phase4/P3_R1_S10_mit_supercloud_2021-08-11_app_1.candidate.stderr.txt
tools/dr_isl/phase4/P3_R1_S10_mit_supercloud_2021-08-11_app_1.json
tools/dr_isl/phase4/P3_R1_S10_mit_supercloud_2021-08-11_app_2.base.stderr.txt
tools/dr_isl/phase4/P3_R1_S10_mit_supercloud_2021-08-11_app_2.candidate.stderr.txt
tools/dr_isl/phase4/P3_R1_S10_mit_supercloud_2021-08-11_app_2.json
tools/dr_isl/phase5/S10_mit_supercloud_2021-08-11_app.base.stderr.txt
tools/dr_isl/phase5/S10_mit_supercloud_2021-08-11_app.candidate.stderr.txt
tools/dr_isl/phase5/S10_mit_supercloud_2021-08-11_app.json
```

This filename filter is not a content scan: mixed-scenario reports and JSON evidence also contain S10 results. `ISL19_REPORT.md`, `RESULTS.json`, `REPRESENTATIVE_TICKS.json` and `FINAL_INTEGRITY.json` were retained as requested. The integrity manifest describes the original measurement files, including CSVs now retained locally but no longer indexed.

## Gate disposition

Cannot confirm “no S10-derived file is tracked anywhere”: 15 matching paths remain, including the previously tracked scenario and retained JSON summaries. D11.0 also explicitly says to keep JSON summaries tracked.

STOP before D11.1/D11.2. Clarify whether the prohibition means raw/per-tick trace material only, with the scenario and aggregate summaries retained, or all S10-derived content including the existing scenario and aggregate/mixed evidence.

No candidate application changes exist; application code remains at `5225a05`. Nothing needs to be stashed.
