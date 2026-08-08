# Replit Agent Prompt — NAR-001 Phase A′ Part 2a: Build Go-Ahead

Paste everything below the line.

---

## PRE-CHECK RESPONSE

All four gates clear. **Proceed to build.** Three refinements below arise from what the pre-check found, plus one new defect to log and one question to answer along the way.

**#268 — `GET /ws/{run_id}` is unauthenticated.** `websocket.accept()` is called before any auth check: no dependency, no cookie check, no token validation. Full site telemetry goes to any client holding a `run_id`, on a system that has `auth_user` and `principal` tables and is heading for multi-tenant row-level security. Database-level tenant isolation is defeated by an open socket that bypasses it. Log it; **do not fix it in this task** — an auth change here would be a production change, and the recorder is deliberately not the vehicle for one.

**Question, answer in your build report:** is `POST /runs` authenticated? The pre-check covered the WebSocket but not the run-start endpoint. If that is also open, #268 widens from disclosure to unauthenticated resource consumption.

---

## REFINEMENT 1 — The subscribe race, and why it matters

`POST /runs` returns and the run "advances autonomously in an asyncio task immediately after the response is returned." `broadcast()` fans out only to currently-subscribed sockets and there is no replay buffer. So every tick emitted between the response returning and the recorder's `subscribe()` completing is **gone**.

This is not cosmetic. I5 differences consecutive ticks, and every trend baseline starts from the run's opening state. A recording that silently begins at `sim_time_seconds = 35.0` will produce residuals that look like physics and are actually a missing prologue.

Required handling:

- Subscribe as early as possible: issue `POST /runs`, then open the socket immediately, with no intervening work.
- Record `first_sim_time_s` in the manifest and set `missed_leading_ticks: true` whenever it is greater than one tick interval above zero. Do not guess at what was missed and do not backfill.
- Report the observed value in the 2a.5 findings. If leading ticks are routinely lost, say so — the fix would be a server-side change and therefore a separate task, not something to work around here.

## REFINEMENT 2 — `seq` cannot detect a server-side drop

`seq` is assigned on arrival, so it is gap-free by construction and proves nothing about what the hub failed to send. The hub drops a slow or stalled subscriber individually (`run_manager.py:193–196`), and a recorder that falls behind on disk writes is exactly such a subscriber.

The real continuity check is `sim_time_seconds`:

- After each message, compare `sim_time_seconds` against the previous one. Flag any interval that is not the expected spacing.
- Derive the expected spacing from the data — the first several observed intervals — not from an assumed 5.0 s. `playback_speed` affects wall-clock cadence, and the tick interval is a literal at `run_manager.py:606` rather than a catalogue key, so neither should be assumed.
- Write an explicit `{"seq": N, "event": "sim_time_gap", "from_s": ..., "to_s": ...}` marker into the JSONL at the point of discontinuity, and carry a gap list in the manifest.

To reduce the chance of being dropped in the first place: receive into an in-memory queue and write to disk from a separate task, so a slow filesystem never stalls the socket read.

## REFINEMENT 3 — Stop reason taxonomy

`stop_reason` needs four values, not three, because the failure modes are different findings:

| Value | Meaning |
|---|---|
| `run_complete` | The `{"type": "run_complete"}` sentinel arrived. Clean. |
| `timeout` | Wall-clock limit hit with the run still live. |
| `dropped` | The socket closed without a sentinel — likely hub-side eviction. **A recording ending this way is suspect and must be labelled as such.** |
| `error` | Anything else; include the exception. |

A truncated recording that reports `run_complete` would send the checkers looking for physics defects at the end of a run that simply stopped being observed.

---

## MANIFEST — additions

Add to the manifest specified previously:

```jsonc
{
  "playback_speed": 1.0,            // from the POST /runs request, not inferred
  "end_sim_time_requested": 300.0,  // from the request
  "soc_floor_pct": 10.0,            // from the StartRunResponse
  "soc_ceil_pct": 95.0,             // from the StartRunResponse
  "missed_leading_ticks": false,
  "first_sim_time_s": 0.0,
  "observed_tick_interval_s": 5.0,  // derived from data, not assumed
  "sim_time_gaps": [],              // [{from_s, to_s}]
  "run_start_request": { /* the POST body verbatim */ }
}
```

`soc_floor_pct` and `soc_ceil_pct` come back in `StartRunResponse` and are run-scoped configuration that is not in the catalogue — they belong in the manifest for the same reason the catalogue snapshot does.

Write recordings to `/home/runner/workspace/tools/invariants/recordings/`.

---

## EVERYTHING ELSE UNCHANGED

The recorder spec, the verbatim-payload rule, the null rule, the catalogue snapshot, Part 2a.5, and the do-not list all stand as written. In particular: `payload` is the received message unmodified, nulls included; the recorder imports nothing from `core/`, `runtime/`, or `renewable/`; and it neither fixes #266, #267, nor #268.

For the 2a.5 smoke run, use the `scenario_id` path with a short `end_sim_time` and a raised `playback_speed` so the run completes quickly — and note in the findings whether the raised speed appeared to affect delivery or drops.

---

## TESTS — one added

| TC | Assertion |
|---|---|
| TC-118 | Synthetic message round-trips byte-identically, including nulls, nested objects, empty collections, and floats. No network. |
| TC-119 | Simulated disconnect and reconnect produces a `reconnect` marker; `seq` remains gap-free across the boundary. |
| TC-120 | `catalogue_hash` is stable across two reads of an unchanged file and changes when any value changes. |
| TC-121 | A synthetic stream with a missing tick produces a `sim_time_gap` marker with correct `from_s`/`to_s`, and the gap appears in the manifest. A stream with no gaps produces neither. Expected interval is derived from the stream, not hardcoded. |

## STOP AND REPORT IF

- The recorder is dropped by the hub during the smoke run.
- `first_sim_time_s` is materially above zero, i.e. leading ticks are being lost.
- Any field in the 2a.5 list is absent from the wire.
- `POST /runs` requires credentials the recorder cannot obtain.
