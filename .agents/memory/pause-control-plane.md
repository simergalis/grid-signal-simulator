---
name: PAUSE control-plane
description: How the PAUSE/RESUME state machine is implemented; what is and isn't deferred to §22.3.
---

## Rule
`_drive()` awaits `ctx._pause_event` at the top of each tick iteration. `pause_run()` clears it; `resume_run()` and `cancel_run()` set it. `cancel_run()` must ALWAYS set the event before flagging `ctx.cancelled` or a paused loop blocks forever.

**Why:** Any future change to `cancel_run()` that skips `ctx._pause_event.set()` will cause a deadlock — cancel_run() awaits the task, the task blocks at wait(), neither proceeds. TC-PAUSE-6 catches this.

**How to apply:** When modifying `cancel_run()`, `pause_run()`, or `resume_run()`, keep the event and `ctx.paused` flag in sync. Never touch the event without also updating `ctx.paused`.

## What is deferred
§22.3 Tier-0 timer persistence (dedupe keys, checkpoint-valley timers, staging holds in SQLite) is NOT implemented. PAUSE is correct within a process lifetime but a server restart while paused discards in-flight timer state — same gap that already exists for in-progress runs. This is documented as `§22.3-partial` in code comments.

## File locations
- `RunContext.paused` + `RunContext._pause_event`: `runtime/run_manager.py` (fields after `cancelled`)
- `pause_run()` / `resume_run()`: `RunManager` methods, same file
- API routes: `POST /runs/{id}/pause` and `POST /runs/{id}/resume` in `api/routes/runs.py`
- `RunStatusResponse.paused: bool`: `api/schemas.py`
- Frontend: `tickStore.runPaused` suppresses interpolation; `RunControlBar` + `DemoBar` + `SimClockHeader` all carry `isPaused` prop; `App.tsx` owns the state.

## TC-PAUSE test pattern
Tests yield with `for _ in range(5): await asyncio.sleep(0)` after pause_run() to let _drive() reach the wait() before asserting tick counts. One yield is insufficient at max speed.
