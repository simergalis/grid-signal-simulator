# IMPL-ISL-30/31 seed-42 references

`PROTECTED_STUDY_GATES_ISL30.json` is the current seed-42 reference for the
default 1,800-second announcement cap. It records identity version 4, keeps
base/H1/H2 as protected comparisons, and labels S10 operational rather than
certified. The earlier files below remain unchanged for historical audit;
they are superseded as the current seed-42 result/identity reference.

## Prior accepted and protected references

- `tools/dr_isl/isl25/PROTECTED_STUDY_GATES_FINAL.json:22-79,98-178` — prior
  base/H1/H2 hashes and accepted identities (identity v3).
- `tools/dr_isl/d6c/ACCEPTANCE_STUDY_GATES.json:137-703,897-1482,1670-2297`
  — D6c full metric snapshots for base, H1 and H2.
- `tools/dr_isl/d6b/D6B_3_STUDY_GATES.json:1-2194`,
  `tools/dr_isl/d6f/STUDY_GATES.json:1-1458`, and
  `STUDY_GATE_COMPARISON.json:1-95` — earlier accepted seed-42 study gates.
- `tools/dr_isl/d6/D6AX_STUDY_HASH_GATE.json:1-632` and
  `D6AX_STUDY_METRIC_COMPARE.json:1-54` — earlier D6a-X hash and metric gates.
- `tools/dr_isl/isl25/S10_MCP_ACCEPTANCE_SUMMARY.json:32-270,527-765` —
  pre-ISL30 S10 baseline/informed metrics, identity digests and operating-cost
  sections.
- `tools/dr_isl/isl25/RUN_PATH_IDENTITIES.json:13-1063` — the prior exact
  StudyRunExecutor identity payloads (v3).
- `tools/dr_isl/isl25/PROTECTED_STUDY_GATES_PROGRESS.json:1003-1030,48948-48954`
  and `PROTECTED_STUDY_GATES_RESUMED.json:43-441` — earlier
  in-progress/resumed protected-gate evidence.
- `tools/dr_isl/isl25/H2_PROTECTED_GATE.json:14,217-217,507-507,812-818`
  and `H2_PROTECTED_GATE_VERIFIED.json:178-178,456-456,727-728` —
  historical H2 gate evidence against the D6c reference.
- `tools/dr_isl/isl25/BASE_IDENTITIES_BEFORE.json:12-72` and
  `IDENTITY_DIAGNOSIS.json:1-2100` — earlier identity diagnostics; not current
  acceptance gates.

## ISL30 controller result evidence

- `tools/dr_isl/d6g/BASE_COUNTERFACTUAL.json:1-85`,
  `H1_COUNTERFACTUAL.json:1-85`, `H2_COUNTERFACTUAL.json:1-85`, and
  `S10_COUNTERFACTUAL.json:1-152` — D6g before/after comparisons.
- `tools/dr_isl/isl30/BASE_COUNTERFACTUAL.json:1-123`,
  `H1_COUNTERFACTUAL.json:1-132`, `H2_COUNTERFACTUAL.json:1-201`, and
  `S10_COUNTERFACTUAL.json:1-170` — cap-1,800 ISL30/31 seed-42 counterfactuals;
  these are the source values for the new rollup.
- `tools/dr_isl/isl30/cap1200/BASE_COUNTERFACTUAL.json`,
  `H1_COUNTERFACTUAL.json`, `H2_COUNTERFACTUAL.json`, and
  `S10_mit_supercloud_2021-08-11_COUNTERFACTUAL.json` (respectively lines
  `1-109`, `1-110`, `1-101`, `1-120`) — the separate cap-1,200 comparison;
  their cap-1,800 sides agree with the cap-1,800 rollup.
- `tools/dr_isl/isl30/multiseed/scenario-uneven-multisched-01.jsonl:1-11`,
  `scenario-h2-slurm-24h.jsonl:1-11`, and `SUMMARY.md:1-34` — 11-seed
  robustness evidence, retained as such.

## Test and gate readers

No application test or fixture contains the prior fixed physical hashes or
superseded metric literals. The relevant tests are dynamic identity/cache and
parity checks: `tests/test_mcp_server.py:757` (TC-ISL-164) and
`tests/test_study_harness.py:793` (TC-ISL-72), `:838` (TC-ISL-73), and
`:868` (TC-ISL-71).

`tools/dr_isl/isl25/run_protected_study_gates.py` was the only executable
reader of the old D6c metric reference and v3 identity file. It now reads the
ISL30 reference and checks the complete saved metric set plus the v4 identity
payload/digest. Its progress output is directed to `tools/dr_isl/isl30/` so
the historical ISL25 progress file is not overwritten.
