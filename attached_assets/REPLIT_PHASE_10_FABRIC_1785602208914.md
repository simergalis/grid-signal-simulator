# Replit Build Plan — Phase 10: Fabric Model

Continues the nine-phase sequence. Prerequisites: Phase 1 (persistence), Phase 2 (FastAPI wiring), Phase 3 (Live Dashboard), Phase 5 (results/playback).

This phase ships with its implementation already written and tested. The agent's job is integration, not invention — do not regenerate `fabric/`.

---

## 10.0 — Drop in and verify

```
pip install pytest pillow
python -m pytest tests/test_fabric_model.py -q      # expect 22 passed
python mockups/render_mockups.py                    # expect 4 PNGs
```

**Acceptance:** 22 tests pass with no edits to `fabric/`. If any fail on arrival, stop and report which — do not adjust thresholds to make them pass. Every constant in `config/` is deliberate and several are load-bearing for a specific acceptance row.

---

## 10.1 — Wire the fabric tick into the simulation loop

The fabric model runs at its own cadence (`fabric_emission_interval_ms`, default 250 ms), **not** on the 5-second forecast tick. Coupling them rebuilds the averaging problem Engine §25.4 rejects polling to avoid.

```python
fabric = FabricModel.from_files(
    "config/fabric_fixture_default.json",
    "config/fabric_constants.json",
    "config/workload_traffic_profiles.json",
    seed=scenario.seed,
)
# in the async fabric task, every 250 ms of simulated time:
result = fabric.tick(tick_index, sim_time_s, active_jobs, stressors,
                     dt_s=0.25, asset_class=asset_class)
```

`active_jobs` are the same `Job` records the forecast engine consumes. Do not build a second job list for the fabric — the whole point is that both read the same state.

**Acceptance:**
- Fabric ticks are emitted at 250 ms of simulated time regardless of the forecast tick.
- `fabric.reset()` is called on scenario load and on replay-from-zero.
- The fabric task does not block the event loop (Engine §22.7).

---

## 10.2 — Persist to the Tier 0/1 store

Three tables in the control-plane namespace: `fabric_link_state`, `control_path_sample`, `network_telemetry_event`. `session_transport_sample` goes in a **separate namespace**.

**Acceptance:**
- `session_transport_sample` is not co-located with simulated telemetry. Co-locating them is how the two planes get confused six months from now.
- `NetworkTelemetry` events pass through the existing `WorkloadSignal` validation, quarantine, and idempotency path. No second ingestion path (Engine §17.1–17.2).
- `event_id` is stable across a replay at the same seed, so redelivery dedupes.

---

## 10.3 — REST endpoints

```
GET  /api/fabric/fixture                 -> topology fixture as loaded
GET  /api/fabric/state?tick=N            -> per-link state for one tick
GET  /api/fabric/modal                   -> the six plant-plane modal fields
GET  /api/fabric/control-path?window=60  -> decomposed latency series
GET  /api/session/transport              -> instrument plane, p50/p95/p99
POST /api/fabric/stressor                -> inject at runtime
```

**Acceptance:** `/api/session/transport` returns live values when the simulation is stopped. This is TC-85 and it is not optional.

---

## 10.4 — WebSocket tick payload

Add a `fabric` block carrying only the modal-view fields plus the per-link utilisation vector. Do not push full `LinkState` records for 608 links at 4 Hz.

Server side, stamp every outgoing tick:

```python
payload = instrument.stamp_tick(payload)   # adds t_emit_ns
```

Client side, on receipt: `instrument.observe_tick(payload.t_emit_ns)`, plus a ping/pong every 5 s for clock offset.

**Acceptance:**
- `t_emit_ns` comes from wall clock, never simulated time.
- WS latency percentiles populate within 60 ticks and keep updating while paused.

---

## 10.5 — Network Fabric modal

Rebuild per `mockups/mockup_01..03`. Two labelled groups:

- **SIMULATED FABRIC** — control latency, congested links, bandwidth headroom, packet loss, retransmit rate, topology links
- **SESSION TRANSPORT · measured** — WS tick latency, API round-trip

Plus the control-latency decomposition bar against the 2000 ms budget, and the phase-discrimination block.

**Acceptance:**
- Any field the build has not wired still renders `not instrumented`. The existing behaviour is correct; preserve it. A zero that reads as a measurement is worse than an honest gap.
- The decomposition bar shows four terms, not a single total.
- Corroboration is labelled *advisory* and displays the precedence rule.

---

## 10.6 — §19.9 Network Telemetry page

Per `mockups/mockup_04`. Three elements:

1. **Per-link utilisation heat strip**, one row per fabric. The hotspot is the point — an aggregate hides it.
2. **Phase-annotated compute/storage throughput**, with checkpoint and weight-load bands shaded.
3. **Control-latency decomposition** against budget, with the dominant term named.

**Acceptance:** running S2 shows a single saturated storage link while its siblings sit near idle, and the checkpoint band aligns with the compute trace going flat.

---

## 10.7 — Scenario library

Register S1–S8 in the Scenario Builder. Each carries assertions; the results view must show per-assertion pass/fail with the observed value, not just an aggregate verdict.

**Acceptance:**
```
python -c "from fabric.scenario import *; ..."   # all 8 report passed=True
```

The two rows to demo, in order: **S2** (a hotspot appearing during checkpoint and not during training) and **S4** (a correct forecast, a correct dispatch decision, and a command that arrives after the ramp window).

---

## 10.8 — CI wiring

Add `tests/test_fabric_model.py` to the existing pytest job. Add a nightly job that runs all eight scenarios and fails on any assertion regression.

**Acceptance:** TC-77 (reproducibility) and TC-78 (substream isolation) run on every commit. They are the tests that catch a whole class of silent regressions, and they are cheap.

---

## What not to do

- **Do not call a language model anywhere in this path.** Not for telemetry values, not for topology, not for stressor timing. Engine §21.1 excludes inference from the control plane; a non-reproducible input makes every assertion above untestable. Model assistance for *authoring* a new fixture offline is fine — the output is frozen into a file.
- **Do not replace the counter-based PRNG with `random.seed()`.** It will appear to work and will silently stop reproducing under asyncio. TC-77 catches it; do not disable TC-77.
- **Do not synthesise WS tick latency or API round-trip.** TC-85 exists for this.
- **Do not spread elephant flows evenly to "fix" the hotspot.** The hotspot is the finding.
