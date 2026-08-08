# Replit Agent Prompt — NAR-001 Phase A′ Part 1 Response and Revised Plan

Paste everything below the line.

---

## PART 1 RESPONSE

Report accepted. Both stop conditions were correctly raised and the premise of my Part 2 design was wrong: I assumed `run_timeseries` was a telemetry archive. It is not — it is a 17-column conformance record, and its field set looks deliberately chosen for TC evidence (confidence bounds, DQ tags, `insufficient_reserve_alert`, `unrecognised_profile_alerts`, `checkpoint_states`) rather than for analysis.

Answers to your three questions:

**A1 — Alternate data source: yes, record from the WebSocket.** `_tick_result_to_dict()` emits every `TickResult` field except `wall_stamp_utc` (inventory §9). The wire is therefore a complete record where the DB is a subset. A standalone recorder that subscribes to `/ws/{run_id}` and writes each message verbatim to JSONL gives the harness everything, changes nothing in `core/`, `runtime/`, `renewable/`, or `frontend/`, and stays entirely out of the control path. Spec below.

**A2 — Do not expand `run_timeseries`.** Its column set is a conformance artefact. Widening it to serve an analysis harness conflates two purposes and turns a read-only investigation into a schema migration on a persistence table. If that table should carry more, that is a separate decision with its own DR. Not here, not as a side effect of this task.

**A3 — Do not write a migration.** The table has zero rows. But before doing anything to it, see Part 0 — the divergence you found may be the reason it is empty.

---

## PART 0 — Test one hypothesis first, then stop

You reported that the live DB columns are `p_compute_mw` / `p_cooling_mw` / `p_total_mw` while the current ORM attributes are `p_compute_demand_mw` / `p_cooling_demand_mw` / `p_demand_mw`, and separately that the table has zero rows.

**Hypothesis: those two facts are the same fact.** If SQLAlchemy is binding ORM attribute names that do not exist as columns in the live DB, every insert into `run_timeseries` would raise — and if that exception is caught and logged rather than propagated, runs would appear to complete normally while persisting nothing.

This is a hypothesis, not a diagnosis. Confirm or refute it by reading, and do not fix anything either way:

1. Give the insert path verbatim (`persistence.py:626–648` and its caller), with `file:line`.
2. Is the insert wrapped in a `try`/`except`? If so, quote the handler and state exactly what it does with the exception — re-raise, log, or swallow.
3. Is persistence invoked unconditionally per tick, per run, or gated behind a flag or config value? Name the gate if one exists.
4. Is there any log output, in any log file or console history available to you, showing a persistence write failure?
5. Confirm how the live `gridsignal.db` was created — by `create_all()` from an earlier ORM revision, by a migration, or by hand.

Report in chat and **stop**. If persistence has been silently failing, that is a defect worth its own task number and it changes what "no persisted runs" means.

---

## REVISED ORDER OF WORK

Part 3 needs no data and is unblocked today. It is also the highest-value section in the original prompt. It moves first.

1. **Part 0** — the hypothesis above. Stop.
2. **Part 3** — static conformance probe. Unblocked, no data required. Stop.
3. **Part 2a** — build the recorder.
4. **Part 2b** — generate runs with the recorder attached.
5. **Part 2c** — build the six checkers against recorded JSONL.

---

## PART 3 — Static conformance probe (unchanged, now runs first)

No data, no execution. Read the code and answer with `file:line` and verbatim excerpts.

**P3.1 — Does the §7.2 step-4 insufficient-reserve arithmetic read the confidence band or the point estimate?**
Give the expression computing `peak_shortfall_mw` verbatim and name every input. State whether it reads `forecast_mw`, `confidence_upper_mw`, `confidence_lower_mw`, or `p_demand_mw`. Do the same for whatever computes `bess_bridging_seconds`, and for the comparison between the two that sets `insufficient_reserve_alert`.

**P3.2 — Is the bridging capability anchor-adjusted?**
Give the expression verbatim. State whether `bess_anchor_reserve_mw` is subtracted before the comparison in P3.1.

**P3.3 — `_p_dispatch_droop_mw`.**
Give its assignment verbatim and name every input, each with `file:line`. State whether it derives from measured demand or from a forecast field.

**P3.4 — Re-rated capability.**
Does `turbine_units[].rated_mw` carry an applied re-rating, or is it always nameplate? Where would a re-rating be applied, if anywhere?

Report what the code does. Do not judge conformance. Do not change anything. Then **stop**.

---

## PART 2a — The recorder

**File:** `tools/invariants/record.py`. Standalone. Imports nothing from `core/`.

Behaviour:

- Connects as a WebSocket client to the existing `GET /ws/{run_id}` endpoint. It is an ordinary subscriber; it gets no special treatment and requires no server-side change.
- Writes one JSONL line per received message:

```jsonc
{"seq": 0, "received_wall_utc": "2026-08-08T20:15:39.512Z", "payload": { /* the message, verbatim */ }}
```

- **`payload` is the received message byte-for-byte.** No key renaming, no flattening, no filtering, no type coercion, no dropping of nulls. If a message arrives that the recorder does not understand, it records it anyway.
- `seq` is assigned by arrival order and is gap-free. If the recorder detects a gap or a reconnect, it writes an explicit `{"seq": N, "event": "reconnect"}` marker rather than silently resuming.
- Stops on the `{"type": "run_complete"}` sentinel, and also on a wall-clock timeout, recording which one fired.
- Writes a sidecar `<run>.manifest.json`: `run_id`, scenario identifier, first and last `sim_time_seconds`, message count, recorder start and stop wall times, stop reason, and the code revision if one is obtainable.

Report the run-start mechanism before writing this: is there an HTTP endpoint that starts a run and returns a `run_id`, or is a run only startable from the UI? Give the endpoint and its parameters if one exists.

**Note on durability:** the container filesystem resets. Recorded JSONL and manifests must be written somewhere that survives, or exported, or the runs have to be repeated. Say where you are writing them and whether that location persists.

---

## PART 2b — Generate runs

With the recorder attached, run at least three scenarios covering: one islanded ramp with commitment and release, one grid-connected run, and one run long enough that decommitment occurs. Report the scenario identifiers you used and why.

Run at 1× unless a run would take impractically long, and record the speed multiplier in the manifest either way.

---

## PART 2c — The checkers

Unchanged from the original Phase A′ prompt (I1, I2a, I2b, I3, I4, I5, I6), with three amendments:

- **Source is the recorded JSONL**, read through `tools/invariants/load.py`, not the DB.
- **Field names are wire names**, since that is what the recorder captures. Where the wire nests (`commitment_block.*`, `kube_metrics.*`, `contingency_coverage.*`, `turbine_units[]`), address them by their wire path. Confirm each against the NAR-001 inventory before use and report any disagreement.
- **`bess_usable_mwh` is on the wire**, so I5 is fully evaluable from recorded data. It is a per-run constant stamped on every tick; read it once and assert it does not vary within a run.

The null rule, the no-tolerances rule, and the units-assumptions table all stand unchanged. Nulls are `NOT_EVALUABLE`, never `0.0`.

---

## TESTS

TC-110…TC-117 unchanged. Two added for the recorder:

| TC | Assertion |
|---|---|
| TC-118 | A synthetic message round-trips byte-identically: `json.loads(line)["payload"] == original_message`, including nulls, key order-independence, and nested objects. |
| TC-119 | A simulated disconnect and reconnect produces an explicit `reconnect` marker and a `seq` that remains gap-free across the boundary. |

---

## DO NOT

1. Do not modify anything in `core/`, `runtime/`, `renewable/`, or `frontend/`. The recorder is an ordinary WebSocket client and requires no server-side change. If it appears to require one, stop and report rather than making it.
2. Do not expand, migrate, alter, or drop `run_timeseries`. Do not delete or recreate `gridsignal.db`.
3. Do not fix the ORM/DB column divergence. Part 0 investigates it; a fix is a separate task.
4. Do not fix anything Part 3 finds. Report it.
5. Do not transform the payload in the recorder. Verbatim means verbatim.
6. Do not coerce a null to zero anywhere, in the recorder or the checkers.
7. Do not define a tolerance, threshold, or epsilon, and do not emit pass/fail.
8. Do not infer units from field names.
9. Do not proceed past a stop point without my reply.

## STOP AND REPORT IF

- The recorder cannot subscribe without a server-side change.
- Runs cannot be started programmatically and must be driven through the UI.
- Any wire field name disagrees with the NAR-001 inventory.
- Recorded output cannot be written anywhere that survives a container reset.
