# Phase 5b durable evidence

## Baseline and IMPL-ISL-21

- Initial HEAD was `e72f0ec`; compared with `5fbf357`, the only package paths differing were four tests (`test_13_3_frequency.py`, `test_bess_surplus_absorption.py`, `test_dr_isl_dump_response.py`, `test_forecast_path.py`). Production source matches.
- IMPL-ISL-21 comment-only commit: `0e7c3d3`, message `IMPL-ISL-21: label governor cascade as diagnostic-only (PX-2)`.
- AST SHA-256 (`ast.dump(ast.parse(source), include_attributes=False)`) before and after the comment edits:
  - `P/core/simulation_core.py`: `11202105ccabdacee8ba3de169a6470635b8916b98f9bfc8345a98903ed00675` both; identical.
  - `P/core/asset_modules.py`: `e0db09fbd104d06e9b05152b1b3a754ed640e4a9ce05d7c62975c7d3c39d8837` both; identical.
- TC-ISL-26–30 had no ID collisions in `P/tests/`.
- Focused run: 42 passed, 1 Starlette/httpx deprecation warning.

## Phase 5b design boundaries

- Existing `TickResult.frequency_valid` and `TickResult.protection_configured` remain untouched; no swing-equation, dispatch, protection, relay, trip, or scenario JSON code is changed.
- `frequency_feedback_configured` is resolved once in the scenario factory and carried through run metadata, study metrics, comparison inputs, MCP energy metrics, and the REST energy summary.
- The study comparison retains the existing ten conditions; the frequency rule is folded into `baseline_valid` and `informed_valid`.
- No `*.channels.csv` is intentionally included; the tracked-file check is recorded in the final report.

## Final verification

- Full suite completed: 2212 passed, 15 failed, 3 skipped, 23 xfailed, 3 subtests passed; 54 warnings. The 15 failure IDs exactly match `tools/dr_isl/D11T_FAILING_TESTS.txt` (0 added, 0 removed); `test_gpu_load_profile` passed.
- Evidence files: `FULL_SUITE_SUMMARY.json`, `FULL_SUITE.xml`, `PHYSICAL_BASE_5FB.jsonl`, `PHYSICAL_CURRENT_5B.jsonl`, `V1_V3_RESULTS.json`, and `CATALOGUE_INVENTORY.json`.
