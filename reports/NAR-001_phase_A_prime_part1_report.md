# NAR-001 Phase A′ — Part 1 Report: Schema and Run Inventory

**Date:** 2026-08-08  
**Status:** ⛔ TWO STOP CONDITIONS MET — awaiting direction before proceeding to Part 2

---

## 1. `run_timeseries` Schema

Storage model: **typed columns, not a JSON blob**, with three exceptions.

The `RunTimeseries` ORM class (`SIM/runtime/persistence.py:175–212`) defines the following columns. DB column name is given first; ORM attribute name follows where they differ (the two are out of sync — explained below).

| # | DB column name | ORM attribute | SQLite type | Nullable | Notes |
|---|---|---|---|---|---|
| 0 | `id` | `id` | INTEGER | NOT NULL | PK, autoincrement |
| 1 | `run_id` | `run_id` | VARCHAR | NOT NULL | indexed |
| 2 | `tick_index` | `tick_index` | INTEGER | NOT NULL | |
| 3 | `sim_time_seconds` | `sim_time_seconds` | FLOAT | NOT NULL | |
| 4 | **`p_compute_mw`** | `p_compute_demand_mw` | FLOAT | NOT NULL | ⚠ column name is wire-alias, not TickResult field name |
| 5 | **`p_cooling_mw`** | `p_cooling_demand_mw` | FLOAT | NOT NULL | ⚠ same mismatch |
| 6 | **`p_total_mw`** | `p_demand_mw` | FLOAT | NOT NULL | ⚠ same mismatch |
| 7 | `net_demand_mw` | `net_demand_mw` | FLOAT | NOT NULL | |
| 8 | `turbine_output_mw` | `turbine_output_mw` | FLOAT | NOT NULL | |
| 9 | `bess_output_mw` | `bess_output_mw` | FLOAT | NOT NULL | |
| 10 | `bess_soc_fraction` | `bess_soc_fraction` | FLOAT | NOT NULL | |
| 11 | `confidence_lower_mw` | `confidence_lower_mw` | FLOAT | NOT NULL | |
| 12 | `confidence_upper_mw` | `confidence_upper_mw` | FLOAT | NOT NULL | |
| 13 | `data_quality_tags` | `data_quality_tags` | TEXT | NOT NULL | **JSON string** — sorted array of tag value strings |
| 14 | `insufficient_reserve_alert` | `insufficient_reserve_alert` | BOOLEAN | NOT NULL | |
| 15 | `unrecognised_profile_alerts` | `unrecognised_profile_alerts` | TEXT | NOT NULL | **JSON string** — sorted array of hardware_profile_id strings |
| 16 | `checkpoint_states` | `checkpoint_states` | TEXT | NOT NULL | **JSON string** — `{job_id: phase_string}` dict |
| 17 | `wall_stamp_utc` | `wall_stamp_utc` | FLOAT | NOT NULL | excluded from WebSocket wire; IS persisted here |

**Three columns are JSON strings in TEXT columns:** `data_quality_tags`, `unrecognised_profile_alerts`, `checkpoint_states`. All others are typed scalars. The class docstring (`persistence.py:177`) notes: "TEXT is portable to PostgreSQL's JSONB on promotion."

### Column name mismatch — ORM source vs live DB

The ORM attribute names in the current source are `p_compute_demand_mw`, `p_cooling_demand_mw`, `p_demand_mw`. SQLAlchemy without an explicit `name=` argument maps these directly as column names. The live DB instead has `p_compute_mw`, `p_cooling_mw`, `p_total_mw` — the **wire-alias** names used in `_tick_result_to_dict()`. This means the DB was created by a prior schema version before the columns were renamed. The readback path confirms intent: `persistence.py:853–855` re-emits them under wire-alias names (`"p_compute_mw": r.p_compute_demand_mw` etc.). Any harness that queries the DB using ORM attribute names from current source will fail; it must use the actual DB column names `p_compute_mw`, `p_cooling_mw`, `p_total_mw`.

### Serialisation vs `_tick_result_to_dict()` output

The persisted column set is a strict subset of the wire dict. The insert path (`persistence.py:626–648`) writes directly from a `TickResult` object, not by re-parsing the wire dict. Values match `_tick_result_to_dict()` output for the fields that are persisted, with one exception: `wall_stamp_utc` is present in the DB but explicitly excluded from the wire dict (`run_manager.py:278–280`).

---

## 2. Available Runs

**⛔ STOP CONDITION MET — fewer than two runs with more than 100 ticks exist.**

The database at `SIM/gridsignal.db` (the only `.db` file in the repository) is completely empty:

| Table | Row count |
|---|---|
| `scenario` | **0** |
| `run_timeseries` | **0** |
| `site` | **0** |

No runs have ever been committed to this database. There is no persisted telemetry to analyse.

---

## 3. Field Availability — Part 2 Field Table vs NAR-001 Inventory

Each Part 2 wire/persisted field name was checked against the NAR-001 inventory (not against the prompt transcription). Two name discrepancies found; all other names match.

| Part 2 name | Inventory ref | DB column | Persisted? | Discrepancy |
|---|---|---|---|---|
| `p_generation_mw` | §C.9 | — | **NO** | — |
| `p_demand_mw` (wire alias `p_total_mw`) | §B.3 | `p_total_mw` | yes | Inventory correctly names both; DB uses alias |
| `d4_balance_defect_mw` | §I table | — | **NO** | — |
| `grid_exchange_mw` | §C.13 | — | **NO** | — |
| `frequency_forcing_mw` | §C.13 | — | **NO** | — |
| `asset_delivery_error_mw` | §C.13 | — | **NO** | — |
| `turbine_output_mw` | §C.1 | `turbine_output_mw` | yes | — |
| `bess_output_mw` | §C.4 | `bess_output_mw` | yes | — |
| `p_renewable_mw` | §E.1 | — | **NO** | — |
| `p_served_mw`, `p_unserved_mw` | §B.5 | — | **NO** | — |
| `p_compute_demand_mw` | §B.1 | `p_compute_mw` | yes (alias mismatch) | Part 2 uses TickResult name; DB has wire-alias `p_compute_mw` |
| `p_compute_served_mw`, `p_compute_unserved_mw` | §B.5 | — | **NO** | — |
| `p_cooling_demand_mw` | §B.2 | `p_cooling_mw` | yes (alias mismatch) | Same wire-alias issue |
| `p_cooling_served_mw`, `p_cooling_unserved_mw` | §B.5 | — | **NO** | — |
| `turbine_units[].output_mw`, `.rated_mw`, `.state` | §C.1 | — | **NO** | — |
| `bess_soc_fraction` | §C.5 | `bess_soc_fraction` | yes | — |
| `commitment_block.*` (all sub-fields) | §C.10 | — | **NO** | — |
| `rated_cooling_mw` | §F.1 | — | **NO** | — |
| `kube_metrics.*` | §A.3–A.5 | — | **NO** | — |
| `sim_time_seconds` | §G.1 | `sim_time_seconds` | yes | — |

**⛔ STOP CONDITION MET — fewer than four of six invariants evaluable from persisted data.**

| Invariant | Fields required, not in DB | Evaluable? |
|---|---|---|
| I1 — Power balance | `p_generation_mw`, `d4_balance_defect_mw`, `grid_exchange_mw` | **No** |
| I2a — Supply summation | `p_renewable_mw`, `p_generation_mw` | **No** |
| I2b — Job attribution | `kube_metrics.*` | **No** |
| I3 — Tri-field | `p_served_mw`, `p_unserved_mw`, per-block served/unserved | **No** |
| I4 — Asset rating | `turbine_units[]`, `rated_cooling_mw` | **No** |
| I5 — Storage energy | `bess_soc_fraction` ✓, `bess_output_mw` ✓, `bess_usable_mwh` ✗ | **Partial only** |
| I6 — Fleet capacity | `turbine_units[]`, `commitment_block.*` | **No** |

Only I5 is partially evaluable: ΔSoC and ∫P dt can each be computed from persisted fields, but cannot be combined into a single residual without `bess_usable_mwh` (which is on the wire but not persisted in `run_timeseries`).

---

## 4. BESS Energy Fields — §C.7

The NAR-001 inventory §C.7 covers four BESS fields under one heading:

| Field | Wire key | In DB? | Nature |
|---|---|---|---|
| `bess_rated_mw` | `bess_rated_mw` | **NO** | Config nameplate — Σ `config.rated_mw` across fleet. **Constant per run.** |
| `bess_usable_mwh` | `bess_usable_mwh` | **NO** | Config nameplate — Σ `config.usable_mwh` across fleet. `models.py:1272`: "FLEET: Σ config.usable_mwh — config nameplate". **Constant per run**, stamped on every tick for panel convenience only. |
| `bess_unit_count` | `bess_unit_count` | **NO** | Count of BESS fleet units. Constant per run. |
| `bess_anchor_reserve_mw` | `bess_anchor_reserve_mw` | **NO** | Headroom reserved for grid-forming. Constant per run. |

`bess_usable_mwh` is **configuration-only** (per-run constant, not a per-tick physics output). It is on the wire but not persisted in `run_timeseries`. For I5, its value would need to be recovered from `spec_json` in the `scenario` table or from `gridsignal_parameters.json` directly.

---

## Summary and Blockers

Two independent STOP conditions are both met:

**Blocker 1 — No persisted runs.** The database is completely empty (0 scenario rows, 0 timeseries rows). There is no data to analyse.

**Blocker 2 — Insufficient persisted fields.** `run_timeseries` stores 17 columns total. The fields required by I1, I2, I3, I4, and I6 are never written to the DB. Only I5 is even partially evaluable.

### Questions for direction

1. Is there an alternate data source — a different DB file, an exported JSONL, or a procedure that generates synthetic runs the harness can consume?

2. Should the field set written to `run_timeseries` be expanded before the harness is built? Fields that would unblock the most invariants (in priority order): `p_generation_mw`, `d4_balance_defect_mw`, `grid_exchange_mw` (unblocks I1); `p_renewable_mw` (unblocks I2a); `turbine_units` as JSON (unblocks I4 and I6); per-block served/unserved and `p_served_mw`/`p_unserved_mw` (unblocks I3); `kube_metrics` as JSON (unblocks I2b); `bess_usable_mwh` (completes I5).

3. The DB column names (`p_compute_mw`, `p_cooling_mw`, `p_total_mw`) differ from the current ORM attribute names (`p_compute_demand_mw`, `p_cooling_demand_mw`, `p_demand_mw`). Should a migration be applied to the DB, or should the harness query by actual DB column names?
