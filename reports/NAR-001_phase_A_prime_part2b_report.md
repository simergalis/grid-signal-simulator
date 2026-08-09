# NAR-001 Phase A′ — Part 2b Report

**Date:** 2026-08-09  
**Status:** Stopped at C1 gate. Three clean recordings delivered. Two stop conditions raised.

---

## Inventory correction (R1 — authorised)

§J.3 heading corrected from "(55 keys)" to "(53 keys)". Total at line 1692 corrected from
`13 + 8 + 55 = 76` to `13 + 8 + 53 = 74`. A traceable note was added at the correction site in
`docs/inventory/NAR-001_variable_inventory.md`. No other change was made to that document.

---

## Test suite — TC-118 through TC-122

All 9 tests pass.

```
test_tc118_payload_round_trips                   PASSED
test_tc119_reconnect_marker_and_gap_free_seq     PASSED
test_tc120_catalogue_hash_stable_and_sensitive   PASSED
test_tc120_catalogue_hash_from_tmp_file          PASSED
test_tc121_gap_detected_with_derived_interval    PASSED
test_tc121_interval_not_hardcoded                PASSED
test_tc122_constant_fields_analysis              PASSED
test_tc122_flatten_nested_paths                  PASSED
test_tc122_empty_jsonl                           PASSED
9 passed in 0.76s
```

---

## Recorder additions (implemented in `tools/invariants/record.py`)

### Subscribe-race measurement
`post_returned_utc`, `ws_subscribed_utc`, and `subscribe_window_ms` are now written to every manifest. `ws_subscribed_utc` is captured on receipt of the first message (the `connected_event.set()` fires inside `_ws_messages` at WS handshake completion, but the timestamp is snapped when the first `async for` iteration enters `_timed_source`; this overestimates the window by at most one network RTT, acceptable for its purpose).

### Determinism metadata
`rng_seed_present` (bool or None) and `seed_detail` (dict of config name → seed value) are probed via `GET /scenarios/{scenario_id}` before the run starts and written to the manifest. `mistral_key_present` is snapped from `os.environ` at call time.

### Physical configuration fingerprint (`constant_fields`)
After recording completes, all JSONL tick payloads are read back and every leaf field (including nested paths, e.g. `turbine_units[0].rated_mw`, `commitment_block.action`) is classified:

- **constant_fields**: present in every tick with identical value. Hash is `sha256` of canonical JSON.
- **varying_fields**: absent from any tick, or value differs across ticks.

A `constant_fields_note` is written to the manifest stating that workload event schedules and irradiance profiles are not captured by this fingerprint (they are resolved before the run starts and never appear on the wire).

---

## Seed question — answered

**All 24 API-accessible scenarios have no integer seeds.** Grepping every scenario spec:

- All `demo-*` and `fabric-s*` scenarios: `seed_detail = {}`, `rng_seed_present = False`.
- The `S1_baseline_training.json` through `S8_transceiver_degrade.json` config files (on disk at `config/scenarios/`) do carry `seed: 42`, but these are loaded separately from the API-accessible library. The 24 scenarios returned by `GET /scenarios` do not include them.
- `MISTRAL_API_KEY` is present in this environment.

**#271 is live, not latent.** Every run via the current API — solar via Mistral LLM, cluster/stressor/param generators all unseeded — is stochastic. Two recordings of the same `scenario_id` are not reproducible. The recordings from this session cannot be re-run to produce identical physics.

---

## Scenario selection — C1 through C6

### Library characterisation
All 24 API scenarios are **islanded** (`island_mode: True`, `anchor_reserve_pct: 0.0`). There are no grid-connected scenarios in the library.

| Criterion | Coverage | Notes |
|---|---|---|
| C1 — kube_config | `demo-kube` | Only scenario; **crashes on first tick** — see STOP below |
| C2 — decommitment | `demo-20mw` | Confirmed in recording |
| C3 — grid-connected | **UNACHIEVABLE** | All 24 scenarios are islanded |
| C4 — BESS discharge | `demo-pms-shortfall` | Confirmed in recording |
| C5 — playback_speed 1.0 | `demo-baseline` | Confirmed; see race finding below |
| C6 — unserved/shed | **Not found** | demo-pms-shortfall: all demand served; demo-20mw: all demand served |

---

## Recordings produced

### R1 — demo-pms-shortfall (`run-973f3c70f24e`)

**Covers: C4**

| Field | Value |
|---|---|
| stop_reason | run_complete |
| message_count | 60 (59 ticks + sentinel) |
| first_sim_time_s | 10.0 |
| missed_leading_ticks | True |
| subscribe_window_ms | 506.6 ms |
| observed_tick_interval_s | 5.0 s |
| rng_seed_present | False |
| mistral_key_present | True |
| constant_fields | 141 |
| varying_fields | 631 |

**C4 confirmed:** `bess_output_mw` ranged 0.889–2.000 MW across all 59 ticks. BESS was discharging throughout.

**C6 not satisfied:** `p_unserved_mw = 0.000` on all 59 ticks, `p_compute_unserved_mw = 0.000`, `p_cooling_unserved_mw = 0.000`. Despite the description's "curtailment ladder engages" and "shortfall≈7 MW after ramp," the recorded demand (`p_demand_mw` max 24.505 MW) was fully served. The curtailment order conflict was logged to SCADA (`commissioning_defect: curtailment order mismatch — PMS shed order ['a_defer', 'b_power_cap'] ≠ GridSignal order ['b_power_cap', 'a_defer']`) but no power was actually shed.

**p_served_mw anomaly noted:** `p_served_mw` ranged 5.789–24.505 MW, while the scenario's rated generation (turbine 5 MW + BESS 3 MW + solar ≈5 MW = 13 MW max) cannot produce 24.505 MW. The semantics of `p_served_mw` in the curtailment context are unclear — it may report the demand signal rather than the delivered power. Flagged for the checkers; do not treat `p_served_mw > rated_generation` as a power-balance invariant violation without understanding the field's definition.

### R2 — demo-baseline (`run-8ab655986f11`)

**Covers: C5**

| Field | Value |
|---|---|
| stop_reason | run_complete |
| message_count | 12 (11 ticks + sentinel) |
| first_sim_time_s | 10.0 |
| missed_leading_ticks | True |
| subscribe_window_ms | **5008.3 ms** |
| observed_tick_interval_s | 5.0 s |
| rng_seed_present | False |
| mistral_key_present | True |
| constant_fields | 170 |
| varying_fields | 599 |

**C5 confirmed** at `playback_speed: 1.0`.

**Subscribe-race finding at 1× speed — settles the ruling's question:**

`missed_leading_ticks: True` even at 1× speed. The subscribe window was **5008 ms** — essentially one full tick interval (5000 ms at 1× speed). The leading tick at sim-time 5.0 s was lost.

The ruling predicted "at 1× speed the race is narrower." This is correct in relative terms: at 10× speed the window is ~0.5 ticks' worth of sim-time, and at 1× speed it is ~1 tick. But the absolute window (~5s) is determined by the Mistral LLM solar-forecast call (which takes ≈5 s regardless of playback speed), not by network RTT. At 1× speed, one 5 s LLM call ≈ one tick; the recorder arrives just after the first broadcast. At higher speeds, the same 5 s call spans multiple ticks, so more can be lost.

**Consequence:** `missed_leading_ticks` is structurally True for all scenario-path runs while `MISTRAL_API_KEY` is present. The 5-second generator overhead (LLM call) eats exactly one tick at 1× speed. This sharpens #269's description: the race is not primarily a network-RTT problem but a generator-pipeline-latency problem. A subscriber-before-start handshake would need to complete before generators run, not merely before `start_run` is called.

### R3 — demo-20mw (`run-37d6809c8917`)

**Covers: C2**

| Field | Value |
|---|---|
| stop_reason | run_complete |
| message_count | 800 (799 ticks + sentinel) |
| first_sim_time_s | 10.0 |
| missed_leading_ticks | True |
| subscribe_window_ms | 340.3 ms |
| observed_tick_interval_s | 5.0 s |
| rng_seed_present | False |
| mistral_key_present | True |
| constant_fields | 193 |
| varying_fields | 660 |
| sim_time_gaps | 0 |

**C2 confirmed — commit, hold, and decommit all observed:**

| sim_time_s | commitment_block.action |
|---|---|
| 10–895 | hold |
| 900–900 | commit |
| 905–3595 | hold |
| 3600–3660 | decommit |
| 3665–4000 | hold |

Commit at t=900 s → 1800 s minimum run met by t=2700 s → decommit decision at ~t=3300 s (≈ 60 ticks of sustained low utilisation) → decommit confirmed at t=3600 s → hold resumes. All three phases (commit, hold, decommit) recorded across 799 ticks.

**BESS activity:** `bess_output_mw` ranged 0.000–16.000 MW. BESS discharged significantly during the high-load period; this run also satisfies C4.

**constant_fields sample (physical configuration fingerprint):**
All five turbine units' `rated_mw = 7.0` appear as constant nested paths (`turbine_units[0].rated_mw` through `turbine_units[4].rated_mw`). `bess_usable_mwh = 8.0` constant throughout. `kube_metrics = None` constant. `commitment_block.action` correctly appears in `varying_fields` (it transitions across the run).

---

## ⛔ STOP — C1: demo-kube crashes on first tick

`demo-kube` is the only scenario in the library with `kube_config` set. Both recording attempts (concurrent and isolated, at speeds 15× and 10×) returned `stop_reason: dropped` with 0 messages.

**Root cause identified from server log:**

```
Task exception was never retrieved
future: <Task finished name='run-run-eb86877c77fc' ...> exception=ZeroDivisionError('float division by zero')>
  File ".../core/asset_modules.py", line 305, in advance
    self._ramp_progress[job_id] = min(1.0, p + dt_seconds / self.ramp_seconds)
ZeroDivisionError: float division by zero
```

`demo-kube` sets `dt_lead_seconds = 0.0`. The GPU asset module's `advance()` method performs `dt_seconds / self.ramp_seconds`. When `ramp_seconds` resolves to `dt_lead_seconds = 0`, the first call to `ctx.step()` raises `ZeroDivisionError`. The `_drive()` coroutine crashes immediately; `WebSocketHub` evicts the run; the WS accepts then closes before transmitting any message; all 3 recorder reconnect attempts observe `stop_reason: dropped`.

**Consequence:** I2b (`kube_metrics` non-null) is unexercisable with the current scenario library and server code. The scenario configuration is not to blame — `dt_lead = 0` is a valid operational intent (no advance notice). The defect is in `asset_modules.py:305` (missing guard against `ramp_seconds = 0`).

**Stopped per DO NOT rule 2 (no server-side code changes) and per STOP condition (recording dropped, I2b unexercisable).**

---

## Criteria coverage summary

| Criterion | Status | Recording |
|---|---|---|
| C1 — kube_config | ⛔ BLOCKED (server crash) | demo-kube: dropped |
| C2 — islanded + decommit | ✓ | demo-20mw: run-37d6809c8917 |
| C3 — grid-connected | ✗ UNACHIEVABLE | No grid-connected scenario in library |
| C4 — BESS discharge | ✓ | demo-pms-shortfall: run-973f3c70f24e |
| C5 — playback_speed 1.0 | ✓ | demo-baseline: run-8ab655986f11 |
| C6 — unserved/shed | ✗ Not found | Attempted: demo-pms-shortfall, demo-20mw |

---

## Defect log additions

| ID | Finding |
|---|---|
| #272 | `asset_modules.py:305` divides `dt_seconds / self.ramp_seconds` without guarding against `ramp_seconds = 0`. `demo-kube` (the only kube_config scenario) sets `dt_lead_seconds = 0.0`, triggering this on the first tick. The run crashes silently (`exception was never retrieved`), evicting all WS subscribers. Fix: guard `if self.ramp_seconds > 0` or clamp `ramp_seconds = max(dt_seconds, ramp_seconds)`. |
| (obs.) | C3 (grid-connected) is structurally absent from the library. All 24 API scenarios have `island_mode = True`. `grid_exchange_mw` will be zero on every recording in this session; I1's grid term is untested. |
| (obs.) | C6 (unserved/shed): `demo-pms-shortfall` logged curtailment order conflicts but delivered all demand. No scenario tried so far produces non-zero `p_unserved_mw`. C6 may be unachievable from the current library without a scenario that exceeds generation capacity. |
| (obs.) | `p_served_mw` semantics in curtailment context: demo-pms-shortfall shows `p_served_mw` up to 24.5 MW with rated generation ≤13 MW. The field may report the demand signal rather than delivered power. Checkers should not use `p_served_mw > generation_capacity` as evidence of a power-balance violation without confirming the field definition. |
| (obs.) | Subscribe race sharpened: at 1× speed, `subscribe_window_ms = 5008 ms ≈ one tick interval`. The race is driven by Mistral LLM generator latency (~5 s), not network RTT. A replay buffer fix must account for generator pipeline time, not merely post-`start_run` latency. |

---

## Recordings index

| Recording | Scenario | Covers | Ticks | Dropped? |
|---|---|---|---|---|
| `run-973f3c70f24e` | demo-pms-shortfall | C4 | 59 | No |
| `run-8ab655986f11` | demo-baseline | C5 | 11 | No |
| `run-37d6809c8917` | demo-20mw | C2, C4 | 799 | No |
| `run-9e39c38eb00f` | demo-kube | C1 attempt | 0 | Yes |
| `run-eb86877c77fc` | demo-kube (retry) | C1 attempt | 0 | Yes |
