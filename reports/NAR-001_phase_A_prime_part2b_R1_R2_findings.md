# NAR-001 Phase A′ — Part 2b Pre-flight: R1 & R2 Findings

**Date:** 2026-08-08  
**Status:** Stopped at ScenarioSpec gate (R2). Awaiting ruling before any server-side change or Part 2b run generation.

---

## R1 — The two missing catalogue keys

**Verdict: The inventory's "76" was wrong. The extractor is correct.**

The §J.3 locked table in `docs/inventory/NAR-001_variable_inventory.md` contains exactly **53 rows** — identical to the 53 locked entries in `gridsignal_parameters.json`. The sets are equal: zero keys in the file but not the table; zero keys in the table but not the file.

The section heading `(55 keys)` and the summary line `13 + 8 + 55 = 76` at inventory line 1692 are **internal arithmetic errors in the inventory document**. The table was miscounted by 2. There are no missing keys. The catalogue has 74 entries; `load_catalogue` captures all 74.

**Correction to apply to the inventory:**

| Location | Current (wrong) | Correct |
|---|---|---|
| §J.3 heading | `Locked section (55 keys)` | `Locked section (53 keys)` |
| §J total | `13 + 8 + 55 = 76` | `13 + 8 + 53 = 74` |

No code change required. `load_catalogue` in `tools/invariants/record.py` is correct.

---

## R2 — Generator pipeline: stochasticity and ScenarioSpec

### 2.1 — Each generator classified

The pre-run pipeline is `asyncio.gather` of four coroutines at `api/routes/runs.py:334–340`, plus `generate_corruption_schedule` called synchronously after gather at `:378–390`.

| Generator | Source file | Classification |
|---|---|---|
| `generate_solar_forecast` | `runtime/solar_sim.py:505` | **LLM-backed** when `MISTRAL_API_KEY` active; **physics-deterministic** (config + wall-clock time) in fallback. Not seeded-RNG. |
| `generate_cluster_forecast` | `runtime/cluster_gen.py:305` | **LLM-backed** when `use_llm=True`; **seeded-deterministic** on RNG fallback when `rng_seed` supplied; **stochastic** when `rng_seed` omitted. |
| `generate_stressor_forecast` | `runtime/stressor_gen.py:229` | **LLM-backed** when enabled; **seeded-deterministic** with `rng_seed`; **stochastic** without seed. |
| `sample_run_parameters` | `runtime/param_sampler.py:105` | **Seeded-deterministic** when config `seed` is an integer; **stochastic / time-seeded** when `seed` is `None`. |
| `generate_corruption_schedule` | `runtime/telemetry_corruption.py:144` | **Seeded-deterministic** when seed supplied; **stochastic** when `seed=None`. |

**Implication for run comparability:** Two runs of the same `scenario_id` are not reproducible unless every generator is either in its LLM-cached/deterministic path or has an explicit integer seed in the scenario config. Two recordings cannot be compared as "same scenario" without capturing the full resolved output of the generator pipeline. Whether deployed scenarios fix their seeds requires inspecting each scenario's JSON record — out of scope here.

### 2.2 — The materialised `spec_data`

There is a fully-resolved plain dict `spec_data` in `api/routes/runs.py`. Its lifecycle:

1. **`:106–116`** — `json.loads(record.spec_json)`: base scenario values loaded from DB.
2. **`:334–340`** — `await asyncio.gather(...)`: generator outputs written into `spec_data` in-place (irradiance, ambient, workload events, sampled fields).
3. **`:342–420`** — further mutation: `GenerationBlock` appended via `.model_dump()`, resolved duration set.
4. **`:422–426`** — passed to `build_run_context_from_spec(spec_data)`.
5. **`:449`** — `await manager.start_run(ctx)`: run begins ticking.

`spec_data` is fully resolved and JSON-serialisable (`json.dumps(spec_data)`) in the window between steps 3 and 5 — after all generators have run, before the first tick. A spec hash would be `sha256` of its canonical JSON. No fingerprint is currently computed anywhere in this pipeline.

`RunContext` (`runtime/run_manager.py:610`) does **not** retain a `spec` or `scenario_spec` field. Only selected derived structures are kept (events, sim state, assertions, site/turbine metadata, telemetry schedule). The original `spec_data` is inaccessible after `start_run` returns.

### 2.3 — Can spec_data be captured without a server-side change?

**No.**

`spec_data` is a local variable in the server handler coroutine (`api/routes/runs.py`). The recorder is a separate process that communicates only via HTTP and WebSocket. There is no `GET /runs/{run_id}/spec` endpoint, no run-spec field on the `GET /runs/{run_id}` response, and the DB column `spec_json` holds the pre-generation base spec — not the post-generation resolved spec.

Capturing the materialised spec in the manifest requires one of:

- **Option A:** A new `GET /runs/{run_id}/spec` route that returns the resolved spec JSON, stored in memory or DB at run-start.
- **Option B:** The resolved `spec_data` serialised and written to the run record (a new DB column, e.g. `resolved_spec_json`) at run-start, then readable via an existing or new endpoint.

Both require a server-side change to `api/routes/runs.py` (and likely `SIM/runtime/persistence.py` or the run DB schema). This belongs in its own task. The recorder cannot work around it unilaterally.

---

## ⛔ STOP — ScenarioSpec cannot be captured without a server-side change

Per the Part 2b spec:
> *If it cannot be captured without a server-side change, say so and stop.*

The materialised `spec_data` exists, is fully resolved, and is serialisable — but it is not exposed through any API surface the recorder can reach. **Stopped. Awaiting ruling before any further Part 2b work.**

---

## Defect log additions from this investigation

| ID | Finding |
|---|---|
| #269 | No replay buffer and no subscribe-before-start handshake. Subscriber attaching after `POST /runs` returns cannot receive already-broadcast ticks. Do not fix — belongs in a separate server-side task. |
| (new) | `spec_data` (fully resolved post-generator ScenarioSpec) is not persisted or exposed via any API endpoint. Two runs of the same `scenario_id` with stochastic generators are not guaranteed to be comparable. A `GET /runs/{run_id}/spec` endpoint or `resolved_spec_json` DB column is needed before the recorder's manifest can include `scenario_spec` + `scenario_spec_hash`. |
| (observation) | Inventory §J.3 miscounts its own locked table as 55 (actual: 53). Total catalogue keys is 74, not 76. Inventory correction only — no code change. |
