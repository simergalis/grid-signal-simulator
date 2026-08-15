---
name: operator-profile-replay
description: How the EDL §4.3 PMSTestDouble escalation path works and what was needed to make it observable (Task #372).
---

# Operator Profile Replay (Task #372)

## The rule
Any three-part gate must ALL be open for PMSTestDouble to run and be observable:
1. `grid_authority_tier = "confirm"` in the spec (else autonomous pool = 1031 MW → shortfall impossible)
2. `operator_response_profile` must be non-null in the spec (else `ctx.pms_response_profile is None` → branch skipped)
3. `_pms_entries` must be stamped onto `tick_result.pms_shortfall_log` (else output discarded — same bug class as Task #371 `edl_dispatch_cost_usd`)

**Why:** grid-firm was hardcoded AUTONOMOUS with 999 MW in scenario_factory.py, making §4.3 unreachable regardless of demand. All seeded scenarios also had `operator_response_profile: null`. And even if both conditions were met, entries were logged but not stamped onto TickResult.

**How to apply:** When any feature uses the §4.3 shortfall escalation path, check all three gates above before debugging why PMSTestDouble seems to do nothing.

## Key wiring
- `grid_authority_tier` field: `ScenarioSpec` in `api/schemas.py`, read by `build_run_context_from_spec()` in `runtime/scenario_factory.py`
- Shortfall stamp: `_drive()` A1b block in `runtime/run_manager.py` — after `PMSTestDouble.process()`, `_dc_replace(tick_result, pms_shortfall_log=tuple(...))`
- Serialisation: `_tick_result_to_dict()` → `"pms_shortfall_log": list(tick.pms_shortfall_log)`
- TypeScript: `TickPayload.pms_shortfall_log: Array<{t_s, source_id, action, authority_tier, detail}>`
- Payload guard: every key in `_tick_result_to_dict` must have a matching field in `TickPayload` or `test_payload_guard.py::test_tc_guard_1_all_python_keys_have_ts_field` fails

## Seeded scenario
`demo-pms-shortfall` (in `api/routes/scenarios.py`): now has `grid_authority_tier="confirm"` and `operator_response_profile` set. BESS 3 MW + turbine 5 MW = 8 MW autonomous capacity; demand ~15 MW → shortfall fires every tick of the run.
