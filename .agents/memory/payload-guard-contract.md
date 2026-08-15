---
name: Payload guard contract
description: Any new key in _tick_result_to_dict() must also appear in TickPayload in frontend/src/types.ts or the payload guard test fails.
---

`tests/test_payload_guard.py::test_tc_guard_1_all_python_keys_have_ts_field` extracts every string key from `_tick_result_to_dict()` in `runtime/run_manager.py` and checks each one exists as a field name in `frontend/src/types.ts` (the `TickPayload` interface).

**Why:** Enforces frontend/backend wire-format parity. A backend field invisible to TypeScript causes silent data loss in the dashboard.

**How to apply:** After adding any key to `_tick_result_to_dict()`, immediately add the corresponding field to the `TickPayload` interface in `frontend/src/types.ts`. Use `number | null` for Optional[float], `number` for float, `string | null` for Optional[str], `boolean` for bool. The guard runs with the rest of the test suite — no separate step needed.

Note: `frontend/src/types.ts` lives at `gridsignal_sim_v2/frontend/src/types.ts` (one level above `gridsignal_sim/`), so git add paths must be specified from the workspace root, not from inside `gridsignal_sim/`.
