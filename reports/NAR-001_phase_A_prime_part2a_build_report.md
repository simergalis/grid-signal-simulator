# NAR-001 Phase A′ — Part 2a Build Report

**Date:** 2026-08-08  
**Status:** Recorder built, tests pass, smoke run complete. Stopped at leading-ticks gate. Awaiting signal before Part 2b.

---

## Files produced

| Path | Purpose |
|---|---|
| `tools/invariants/record.py` | Standalone WebSocket tick recorder |
| `tools/invariants/test_record.py` | TC-118 through TC-121 unit tests |
| `tools/invariants/recordings/run-c3ba3cab67b6.jsonl` | Smoke run JSONL (11 ticks + sentinel) |
| `tools/invariants/recordings/run-c3ba3cab67b6.manifest.json` | Smoke run manifest |

---

## POST /runs authentication (build-report question)

**`POST /runs` is also unauthenticated.**

No auth dependency (`Depends(require_auth)`, cookie check, or bearer token) exists on the `start_run` handler at `api/routes/runs.py:84–450`. A raw POST with no credentials returns `{run_id, soc_floor_pct, soc_ceil_pct}` immediately.

**Implication for #268:** The defect widens from disclosure to unauthenticated resource consumption. Any client can:
1. Start a run (`POST /runs`) — consuming compute budget — without credentials.
2. Subscribe to the run's telemetry (`GET /ws/{run_id}`) — receiving full site telemetry — without credentials.

Both endpoints are open. Neither fix is in scope for this task.

---

## Recorder design notes

### Architecture

- **Transport-agnostic core:** `process_stream(source, *, out_queue, seq_start, is_reconnect, wall_fn)` accepts any `AsyncIterator[str]`. The live recorder and all unit tests pass synthetic or real sources to the same function.
- **Queue-isolated disk writer:** `_disk_writer(path, q)` runs as a separate asyncio task. The WS receiver enqueues messages into an unbounded `asyncio.Queue`; a slow filesystem never stalls the socket read.
- **Reconnect loop:** Up to `_MAX_RECONNECT_ATTEMPTS = 3` reconnects. Each reconnect emits a `{"seq": N, "event": "reconnect"}` marker before resuming. State (seq counter, sim_time history, gap list) is accumulated across attempts.
- **Gap detection:** `sim_time_seconds` is tracked tick-by-tick. Expected interval is derived from the median of the first ≥3 observed deltas — not assumed from any constant. A gap marker `{"seq": N, "event": "sim_time_gap", "from_s": …, "to_s": …}` is emitted when an interval exceeds 1.5× the derived expectation.
- **Verbatim payload:** `json.loads(raw)` is written as-is. No key renaming, no flattening, no null filtering, no type coercion.
- **`received_wall_utc`:** Recorder's own receipt clock (`datetime.datetime.now(utc).isoformat()`). Not `wall_stamp_utc` (excluded from wire by design).

### Stop-reason taxonomy

| Value | Meaning |
|---|---|
| `run_complete` | `{"type": "run_complete"}` sentinel received. Clean. |
| `timeout` | Wall-clock limit reached with run still live. |
| `dropped` | Socket closed without sentinel — likely hub eviction. Recording is suspect. |
| `error:<msg>` | Exception; message included. |

### Catalogue snapshot

`load_catalogue(path)` reads `gridsignal_parameters.json` directly (no server-side accessor). It extracts key→value from `adjustable` (default), `enumerated` (default/options_source), and `locked` (value). The hash is `sha256` of the canonical JSON of the resolved values dict (keys sorted, no whitespace). Stable across reads of an unchanged file; changes when any value changes.

**Catalogue key count: 74** (the spec anticipated 76; 74 keys are present across adjustable/enumerated/locked).

### Manifest fields (beyond original spec)

Added per Refinement 1–3:

```jsonc
{
  "playback_speed": 10.0,             // from POST body, not inferred
  "end_sim_time_requested": 60.0,     // from POST body
  "soc_floor_pct": 10.0,              // from StartRunResponse
  "soc_ceil_pct": 95.0,               // from StartRunResponse
  "missed_leading_ticks": true,
  "first_sim_time_s": 10.0,
  "observed_tick_interval_s": 5.0,    // derived from stream, not assumed
  "sim_time_gaps": [],                // [{from_s, to_s}]
  "run_start_request": { /* POST body verbatim */ }
}
```

---

## Test results — TC-118 through TC-121

```
collected 6 items

test_tc118_payload_round_trips                        PASSED
test_tc119_reconnect_marker_and_gap_free_seq          PASSED
test_tc120_catalogue_hash_stable_and_sensitive        PASSED
test_tc120_catalogue_hash_from_tmp_file               PASSED
test_tc121_gap_detected_with_derived_interval         PASSED
test_tc121_interval_not_hardcoded                     PASSED

6 passed in 0.43s
```

TC-121 includes two variants: one verifies gap detection with a 5 s stream, the other verifies that a 2 s stream derives a 2 s interval (proving the interval is not hardcoded to 5.0).

---

## Part 2a.5 — Smoke validation

**Run:** `demo-baseline` scenario · `end_sim_time=60 s` · `playback_speed=10×`  
**Result:** `stop_reason=run_complete` · 12 lines (11 tick payloads + 1 sentinel) · no hub drop · no sim_time_gaps

### 1. Field presence

| Field | Status |
|---|---|
| `sim_time_seconds` | always present, non-null |
| `p_generation_mw` | always present, non-null |
| `p_demand_mw` | always present, non-null |
| `d4_balance_defect_mw` | always present, non-null |
| `grid_exchange_mw` | always present, non-null |
| `frequency_forcing_mw` | always present, non-null |
| `asset_delivery_error_mw` | always present, non-null |
| `turbine_output_mw` | always present, non-null |
| `bess_output_mw` | always present, non-null |
| `p_renewable_mw` | always present, non-null |
| `p_served_mw` | always present, non-null |
| `p_unserved_mw` | always present, non-null |
| `p_compute_mw` | always present, non-null |
| `p_compute_served_mw` | always present, non-null |
| `p_compute_unserved_mw` | always present, non-null |
| `p_cooling_mw` | always present, non-null |
| `p_cooling_served_mw` | always present, non-null |
| `p_cooling_unserved_mw` | always present, non-null |
| `turbine_units` | always present, non-null |
| `bess_soc_fraction` | always present, non-null |
| `bess_usable_mwh` | always present, non-null |
| `commitment_block` | always present, non-null |
| `rated_cooling_mw` | always present, non-null |
| `contingency_coverage` | always present, non-null |
| `confidence_lower_mw` | always present, non-null |
| `confidence_upper_mw` | always present, non-null |
| `forecast_mw` | always present, non-null |
| `data_quality_tags` | always present, non-null |
| **`kube_metrics`** | **always present, always null** |

No field from the checklist is absent from the wire. No field is "sometimes present." All 29 are key-present on every tick.

### 2. `kube_metrics` nullability pattern

`kube_metrics` is `null` on all 11 ticks. This is structural: the field is only non-null on runs with `kube_config` set in the `ScenarioSpec` (`run_manager.py:331–344`). The `demo-baseline` scenario does not set `kube_config`. The key is always emitted; the value is always `null`. **Checkers must treat `null` as a first-class value, not as an error or absence.**

### 3. `bess_usable_mwh` constancy

`bess_usable_mwh = 2.0` on all 11 ticks. Constant as §C.7 states — config nameplate, not a running integral.

### 4. Wire field names vs. NAR-001 inventory

Three fields exist under **both** their old wire-alias names and their new ORM attribute names simultaneously:

| Old wire-alias name | New ORM attribute name | Both on wire? |
|---|---|---|
| `p_compute_mw` | `p_compute_demand_mw` | ✓ |
| `p_cooling_mw` | `p_cooling_demand_mw` | ✓ |
| `p_total_mw` | `p_demand_mw` | ✓ |

Both names carry identical values. This dual-wiring is intentional (`_tick_result_to_dict` lines 209–226). Checkers should read the new names (`p_compute_demand_mw` etc.) as canonical; old names are present for UI backwards-compatibility.

### 5. Playback speed and delivery

The 60-sim-second run at 10× speed completed in ~17.7 real-world seconds (theoretical minimum: 6 s). The gap is explained by the pre-run LLM generator pipeline (`asyncio.gather` of solar, cluster, stressor, param-sampler generators), which runs fully before `manager.start_run()` and before `POST /runs` returns. No hub drops occurred.

---

## ⛔ STOP — leading ticks are being lost

**`first_sim_time_s = 10.0`** · `missed_leading_ticks = true`

The recorder's first received tick was at sim-time 10 s. The tick at sim-time 5 s (the first emitted tick of the run) was not received.

**Observed tick sequence:** 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60 (11 of 12 expected ticks)

**Cause (subscribe race):** `POST /runs` returns only after the generator pipeline completes. At that moment `manager.start_run(ctx)` has already scheduled the asyncio drive-coroutine. By the time the recorder receives the HTTP response, opens a TCP connection, and completes the WebSocket handshake (~0.5–1 wall-clock seconds), the first tick has already been broadcast. At 10× playback speed, one tick = 0.5 real seconds — within the subscribe race window.

**Nature of the finding:**
- This is structural for the `scenario_id` path at raised playback speeds.
- At 1× speed (one tick = 5 real seconds), the subscribe race is narrower and leading-tick loss may not occur.
- A fix requires a server-side change (replay buffer, or a subscribe-before-start handshake) — a separate task, not a workaround in the recorder.
- `missed_leading_ticks: true` is recorded in the manifest and will be visible to checkers. Recordings where this flag is set should not be used as the sole evidence for first-tick invariants (I5 trend baselines, initial state checks).

**Stopped per DO NOT rule #8. Awaiting reply before Part 2b.**
