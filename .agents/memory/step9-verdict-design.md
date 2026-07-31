---
name: Step 9 verdict design
description: AssertionSpec location, demo-20mw bess_rated_mw trap, H1 gap rules, CompletedRun in-memory store.
---

## AssertionSpec lives in runtime/verdict.py

Defined in `runtime/` (not `api/schemas.py`) to avoid the circular import:
`runtime/scenario_factory.py → api/routes/scenarios.py → api/schemas.py → runtime/...`.
`api/schemas.py` imports `AssertionSpec` from `runtime.verdict` (api→runtime is allowed).

## Demo-20mw: bess_rated_mw=18.0, NOT 5.0

**Why:** `bess_grid_forming=True` withholds 1 MW anchor reserve.
- 18 MW rated → 17 MW bridging available; peak_shortfall ≈ 13.97 MW → no alert ✓
- 5 MW rated → 4 MW bridging available; 13.97 MW > 4 MW → alert fires ✗

Any test asserting the "passing" no-alert scenario must use `bess_rated_mw=18.0`.

## H1 gap rules (evaluate_verdict)

- Universal assertions (`no_insufficient_reserve_alert`, `max_p_total_mw`): FAIL if retained row violates; INCONCLUSIVE if no violation but gaps exist (has_gaps = gap_count > 0 OR dropped_ticks > 0); PASS only when all retained ticks pass AND no gaps.
- Existential assertion (`alert_fires`): PASS if any retained tick fired (regardless of gaps); INCONCLUSIVE if no retained tick fired but gaps exist; FAIL only when no tick fired AND no gaps.
- Final-point assertion (`min_final_bess_soc`): PASS/FAIL when final tick present; INCONCLUSIVE when final tick missing.

## CompletedRun in-memory store

`RunManager._completed: dict[str, CompletedRun]` stores finished runs until process restart.
- `tick_dicts`: list[dict] in `_tick_result_to_dict` format; `gap_before` flag added by the endpoint.
- `verdict`: `VerdictResult` dataclass with `to_json()` for persistence.
- The two new GET endpoints (`/runs/{id}/result`, `/runs/{id}/timeseries`) check active first (409), then `_completed` (404 if absent).

## Route ordering in runs.py

`/{run_id}/result` and `/{run_id}/timeseries` are registered BEFORE `/{run_id}` (status) so FastAPI matches the more specific paths first. Do not reorder.

## TypeAdapter for assertion parsing in scenario_factory.py

```python
_assertion_adapter: TypeAdapter = TypeAdapter(AssertionSpec)
assertions = [_assertion_adapter.validate_python(a) for a in raw_assertions]
```
Created once at module level (not per-call) to avoid repeated Pydantic schema compilation.

## Gate baseline after Step 9

148 pytest (140 original + 8 from test_verdicts.py), plane separation clean (8 core/ + 7 api/), tsc 0 errors, vitest 19/19.
