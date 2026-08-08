# NAR-001 Phase A′ — Part 2a Pre-Check Report

**Date:** 2026-08-08  
**Status:** All four gates clear. No stop conditions raised. Ready to proceed to Part 2a (recorder) on signal.

---

## 1. Run start — HTTP endpoint

**Yes — `POST /runs` starts a run and returns a `run_id`.**

Source: `api/routes/runs.py:78–450`

### Request body (`StartRunRequest`, `api/schemas.py:942`)

Two mutually exclusive paths, enforced by `model_validator`:

```jsonc
// (a) scenario_id path
{
  "scenario_id": "S2_checkpoint_hotspot",
  "end_sim_time": 300.0,       // optional; overrides the stored spec default
  "playback_speed": 1.0        // optional; float, default 1.0
}

// (b) direct programmatic path
{
  "job_id": "job-abc",
  "node_count": 600,
  "hardware_profile_id": "enterprise_8gpu_air",  // optional
  "end_sim_time": 300.0,                         // optional, default 300.0
  "playback_speed": 1.0
}
```

### Response body (`StartRunResponse`, `runs.py:450`)

```json
{
  "run_id": "run-<12 hex chars>",
  "soc_floor_pct": 10.0,
  "soc_ceil_pct": 95.0
}
```

The run advances autonomously in an asyncio task immediately after the response is returned. Subscribe to `GET /ws/{run_id}` for tick data.

---

## 2. Auth on the WebSocket

**No authentication required. The endpoint is open.**

Source: `api/routes/ws.py:29–49`

```python
@router.websocket("/ws/{run_id}")
async def subscribe_run(websocket: WebSocket, run_id: str) -> None:
    hub: WebSocketHub = websocket.app.state.ws_hub
    await websocket.accept()          # ← no auth check before accept
    hub.subscribe(run_id, websocket)
    ...
```

There is no `Depends(require_auth)`, no cookie check, no bearer token validation. The handler accepts immediately and subscribes. The recorder needs no credentials to connect.

---

## 3. Durable output location

**`/home/runner/workspace/` — the Replit workspace volume — survives container resets.**

The workspace is backed by Replit's persistent volume (the repl's filesystem). Container resets do not wipe it. Every file already in the `workspace/` tree (e.g. `reports/`, `docs/`) persists across restarts, confirmed by the presence of existing report files after prior sessions.

The recorder should write to `tools/invariants/recordings/` under the workspace root. This is the same persistence tier as the `reports/` directory already in use.

PostgreSQL (`DATABASE_URL` present, points at a managed instance) also persists, but writing JSONL flat files to the workspace is simpler and keeps the recorder free of any ORM dependency, as required by the spec.

---

## 4. Concurrency — multiple subscribers per `run_id`

**Yes — the hub supports unlimited subscribers per `run_id` concurrently.**

Source: `runtime/run_manager.py:124–196`

```python
class WebSocketHub:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[WebSocketLike]] = {}

    def subscribe(self, run_id: str, ws: WebSocketLike) -> None:
        self._subscribers.setdefault(run_id, set()).add(ws)
```

`broadcast()` fans out to `list(self._subscribers.get(run_id, ()))` using `asyncio.gather`, so every subscriber in the set receives every tick concurrently. A slow or stalled socket is dropped individually without affecting other subscribers (`run_manager.py:193–196`). The recorder can attach while the UI is also watching with no interference.

---

## Summary

| Gate | Result |
|---|---|
| HTTP endpoint to start a run programmatically | ✓ `POST /runs` — returns `run_id` immediately |
| WebSocket auth | ✓ None required — endpoint is open |
| Durable output location | ✓ `/home/runner/workspace/tools/invariants/recordings/` — Replit persistent volume |
| Multi-subscriber support | ✓ Hub uses a `set` per run; `broadcast()` fans out to all concurrently |
