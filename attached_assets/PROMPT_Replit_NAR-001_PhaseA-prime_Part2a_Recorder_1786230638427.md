# Replit Agent Prompt — NAR-001 Phase A′ Part 2a: Tick Recorder

Paste everything below the line.

---

## PART 0 AND PART 3 RESPONSE

Both accepted. The Part 0 investigation found a better cause than the hypothesis it was given, and Part 3 is properly evidenced throughout.

Two defects to log with their own task numbers. **Do not fix either one in this task:**

- **#266 — Timeseries sink never wired.** `RunContext.sink` defaults to `InMemoryTimeseriesSink` and nothing replaces it. Every run through the API retains its telemetry in a process-memory list and loses it on completion. `SqlitePersistedTimeseriesSink` is instantiated only in `test_persistence.py`.
- **#267 — Silent insert failure and schema divergence.** The live `run_timeseries` columns are the old wire-alias names; the current ORM attributes differ. Any INSERT would raise, be caught at `persistence.py:650`, logged at ERROR, and swallowed without incrementing `_dropped_ticks`. Fixing #266 without #267 would produce a system that appears to persist and does not.

Three items from Part 3 are going to decision records separately and are not your concern in this task: the endurance arm's use of raw rather than band-widened shortfall, the N-1 floor point-estimate ruling, and TC-58 having no implementation to test.

**None of this blocks the recorder.** It subscribes to the WebSocket as an ordinary client and never touches the sink, the DB, or the ORM.

---

## PRE-CHECK — report in chat, then stop

1. **Run start.** Is there an HTTP endpoint that starts a run and returns a `run_id`? Give the method, path, request body shape, and response shape, with `file:line`. If runs can only be started from the UI, say so plainly.
2. **Auth on the WebSocket.** Does `GET /ws/{run_id}` require authentication? If so, what does a client need to present — a session cookie, a bearer token, something else — and is there a way to obtain one programmatically? `auth_user` and `principal` tables exist, so assume nothing.
3. **Durable output location.** Where can the recorder write JSONL that survives a container reset? Name the path and say why it persists. If no such location exists, say so — that changes the plan.
4. **Concurrency.** Does the WS hub support more than one subscriber per `run_id`? The recorder should be able to attach while the UI is also watching.

Then **stop**.

---

## PART 2a — The recorder

**File:** `tools/invariants/record.py`. Standalone. Imports nothing from `core/`, `runtime/`, or `renewable/`.

### Behaviour

Connects as an ordinary WebSocket client to `GET /ws/{run_id}`. It requires no server-side change. It writes one JSONL line per received message:

```jsonc
{"seq": 0, "received_wall_utc": "2026-08-08T20:15:39.512Z", "payload": { /* the message, verbatim */ }}
```

- **`payload` is the received message unmodified.** No key renaming, no flattening, no filtering, no type coercion, no dropping of nulls, no reordering. If a message arrives whose shape the recorder does not recognise, it records it anyway.
- `seq` is assigned by arrival order and is gap-free. On any reconnect or detected gap, write an explicit `{"seq": N, "event": "reconnect"}` marker rather than silently resuming.
- `received_wall_utc` is the recorder's own receipt clock. It is **not** `wall_stamp_utc`, which is excluded from the wire entirely — do not conflate them, and do not synthesise a `wall_stamp_utc` field.
- Stops on the `{"type": "run_complete"}` sentinel or on a wall-clock timeout, recording which fired.

### Manifest

Alongside each recording, write `<run>.manifest.json`:

```jsonc
{
  "run_id": "...",
  "scenario_id": "...",
  "scenario_version": "...",          // null if none exists
  "speed_multiplier": 1.0,
  "first_sim_time_s": 0.0,
  "last_sim_time_s": 10800.0,
  "message_count": 2161,
  "recorder_start_utc": "...", "recorder_stop_utc": "...",
  "stop_reason": "run_complete",      // run_complete | timeout | error
  "code_rev": "...",                  // null if not obtainable
  "catalogue_hash": "sha256:...",     // of gridsignal_parameters.json, canonicalised
  "catalogue_values": { /* the resolved 76 keys */ }
}
```

The catalogue snapshot is the point of the manifest. Without it, a behaviour difference between two recordings cannot be attributed to code versus configuration, and that distinction is the reason this file exists. Read `gridsignal_parameters.json` directly; do not import the accessor.

---

## PART 2a.5 — Smoke validation before generating the full set

Record **one short run** — a few minutes of sim time is enough — then verify against the recorded JSONL, and report:

1. Which of these are present in every payload, present sometimes, or never present:
   `p_generation_mw`, `p_demand_mw`, `d4_balance_defect_mw`, `grid_exchange_mw`, `frequency_forcing_mw`, `asset_delivery_error_mw`, `turbine_output_mw`, `bess_output_mw`, `p_renewable_mw`, `p_served_mw`, `p_unserved_mw`, `p_compute_mw`, `p_compute_served_mw`, `p_compute_unserved_mw`, `p_cooling_mw`, `p_cooling_served_mw`, `p_cooling_unserved_mw`, `turbine_units`, `bess_soc_fraction`, `bess_usable_mwh`, `commitment_block`, `rated_cooling_mw`, `kube_metrics`, `contingency_coverage`, `sim_time_seconds`, `confidence_lower_mw`, `confidence_upper_mw`, `forecast_mw`, `data_quality_tags`.
2. For every field that is *sometimes* present or sometimes null, the fraction of ticks affected and any pattern you can see in when.
3. `bess_usable_mwh` — confirm it is constant across all ticks in the run, as §C.7 states.
4. Any field whose wire name differs from the NAR-001 inventory.

Then **stop**. This gate exists so a missing field is found after one short run rather than after three long ones.

---

## TESTS

| TC | Assertion |
|---|---|
| TC-118 | A synthetic message round-trips byte-identically: `json.loads(line)["payload"] == original_message`, including nulls, nested objects, empty collections, and floats. No network. |
| TC-119 | A simulated disconnect and reconnect produces an explicit `reconnect` marker, and `seq` remains gap-free across the boundary. |
| TC-120 | `catalogue_hash` is stable across two reads of an unchanged `gridsignal_parameters.json`, and changes when any value changes. |

Tests use synthetic messages and a fake transport. No test opens a real socket or starts a run.

---

## DO NOT

1. Do not modify anything in `core/`, `runtime/`, `renewable/`, `api/`, or `frontend/`. The recorder is an ordinary client.
2. Do not fix #266 or #267. Specifically: **do not wire `SqlitePersistedTimeseriesSink` into the run path as a shortcut to obtaining data.** The recorder exists precisely so that no production change is needed to get telemetry.
3. Do not read telemetry out of `InMemoryTimeseriesSink`, `RunContext`, or any in-process object. Subscribe to the wire like any other client.
4. Do not touch `gridsignal.db`, the ORM, or the schema.
5. Do not transform the payload. Verbatim means verbatim — including nulls, which are load-bearing information for the checkers that come next.
6. Do not filter messages by type. Record everything that arrives.
7. Do not compute, derive, or add any field to the payload. The recorder observes; it does not interpret.
8. Do not proceed past a stop point without my reply.

## STOP AND REPORT IF

- The recorder cannot subscribe without a server-side change.
- Runs cannot be started programmatically.
- The WS hub permits only one subscriber per run, so recording would displace the UI.
- No output location survives a container reset.
- Any field in the 2a.5 list is absent from the wire.
