# NAR-001 Phase A′ — Part 0 and Part 3 Report

**Date:** 2026-08-08  
**Status:** Both parts complete. Stopped per revised order of work. Ready to proceed to Part 2a (recorder) on signal.

---

## Part 0 — Hypothesis: ORM/DB Column Mismatch → Silent Insert Failures → Empty DB

**Verdict: Confirmed, but a more fundamental cause supersedes it.**

---

### 1. Insert path verbatim

**Caller — `runtime/run_manager.py:1512`:**
```python
await ctx.sink.append(tick_result)   # I/O -- yields to sibling runs
```
Called unconditionally every tick, after `evaluate_tick()` and the solar re-stamp, before the WebSocket broadcast.

**`SqlitePersistedTimeseriesSink.append()` — `persistence.py:692–722`:**
```python
async def append(self, tick: TickResult) -> None:
    if self._write_queue is None:
        raise RuntimeError(...)
    try:
        self._write_queue.put_nowait(tick)
    except asyncio.QueueFull:
        self._dropped_ticks += 1
        ...
```
Returns immediately. Does NOT wait for the INSERT to complete.

**Drain loop INSERT — `persistence.py:623–648`:**
```python
async with AsyncSession(self._engine) as session:
    async with session.begin():
        session.add(
            RunTimeseries(
                run_id=tick.run_id,
                tick_index=tick.tick_index,
                sim_time_seconds=tick.sim_time_seconds,
                p_compute_demand_mw=tick.p_compute_demand_mw,   # ← ORM attribute name
                p_cooling_demand_mw=tick.p_cooling_demand_mw,   # ← ORM attribute name
                p_demand_mw=tick.p_demand_mw,                   # ← ORM attribute name
                net_demand_mw=tick.net_demand_mw,
                turbine_output_mw=tick.turbine_output_mw,
                bess_output_mw=tick.bess_output_mw,
                bess_soc_fraction=tick.bess_soc_fraction,
                confidence_lower_mw=tick.confidence.lower_bound_mw,
                confidence_upper_mw=tick.confidence.upper_bound_mw,
                data_quality_tags=json.dumps(...),
                insufficient_reserve_alert=tick.insufficient_reserve_alert,
                unrecognised_profile_alerts=json.dumps(...),
                checkpoint_states=json.dumps(tick.checkpoint_states),
                wall_stamp_utc=tick.wall_stamp_utc,
            )
        )
```

---

### 2. Exception handler

```python
except Exception:
    _log.exception(
        "persistence drain: failed to write tick %d for run %s",
        tick.tick_index,
        tick.run_id,
    )
finally:
    self._write_queue.task_done()
```

**What the handler does:** logs at ERROR level (full traceback via `_log.exception`), then continues. Does NOT re-raise. The drain loop proceeds to the next item. `_dropped_ticks` is NOT incremented on insert failure — only on `asyncio.QueueFull`. An operator watching the UI sees no indication of the failure.

---

### 3. Is persistence invoked unconditionally?

**Gate: `ctx.sink` is always `InMemoryTimeseriesSink`.**

`RunContext.sink` is declared at `run_manager.py:628`:
```python
sink: TimeseriesSink = field(default_factory=InMemoryTimeseriesSink)
```

`InMemoryTimeseriesSink` docstring (`run_manager.py:566–569`):
```python
class InMemoryTimeseriesSink:
    """Stub used for tests and local dev; swap for the real
    SQLAlchemy-async-backed sink (runtime/persistence.py, not included
    in this skeleton) in production."""
```

Neither `build_run_context_from_spec` nor `build_run_context` replaces this default. `runs.py` does not import `SqlitePersistedTimeseriesSink`. Every run executed through the API uses `InMemoryTimeseriesSink`, which stores ticks in a Python list in process memory only.

`SqlitePersistedTimeseriesSink` is instantiated only in persistence tests (`test_persistence.py:230`) — never in the production API path.

---

### 4. Log output

No `.log` files found in the repository. Because the primary cause means no inserts are ever attempted, there would be no persistence-related ERROR log lines in normal operation.

---

### 5. How `gridsignal.db` was created

**Path A — app lifespan (`api/db.py:158`):**
```python
await conn.run_sync(Base.metadata.create_all, checkfirst=True)
```
Called from `create_auth_tables()` in the FastAPI lifespan. Creates ALL tables in `Base.metadata` (including `run_timeseries`) with `checkfirst=True`. If `run_timeseries` already existed from a prior schema version, `checkfirst=True` leaves it untouched.

**Path B — `SqlitePersistedTimeseriesSink.start()` (`persistence.py:575`):**
```python
await conn.run_sync(Base.metadata.create_all)
```
No `checkfirst`. Never called — the sink is never instantiated in the API path.

**Conclusion:** `gridsignal.db` was created by Path A using an **older ORM revision** that used wire-alias column names (`p_compute_mw`, `p_cooling_mw`, `p_total_mw`). The current ORM's `create_all(checkfirst=True)` finds the table already existing and leaves the old schema intact. The live DB and the current ORM source are structurally out of sync.

---

### Part 0 — Summary: Two distinct defects

**Primary defect — sink never wired in (explains zero rows):**
`SqlitePersistedTimeseriesSink` is never instantiated in the API run path. Every run uses `InMemoryTimeseriesSink`. Zero ticks ever enter the DB write queue during normal operation. The empty `run_timeseries` table is a direct consequence.

**Secondary defect — silent insert failure if wired (would produce zero rows even if fixed):**
The DB schema has the old column names (`p_compute_mw`, `p_cooling_mw`, `p_total_mw`); the current ORM uses `p_compute_demand_mw`, `p_cooling_demand_mw`, `p_demand_mw`. Any INSERT using the current ORM would raise an `OperationalError` caught by `persistence.py:650`, logged at ERROR, and swallowed. `_dropped_ticks` would not increment; the operator would see runs completing normally with no data persisted.

**Both are defects worth separate task numbers. Neither surfaces to the operator.**

---

## Part 3 — Static Conformance Probe

### P3.1 — Does §7.2 step-4 insufficient-reserve arithmetic read the confidence band or the point estimate?

**Short answer:** The power-ceiling arm uses a band-widened shortfall (site-configured multiplier, not the per-tick wire band). The endurance arm uses the raw point shortfall. Neither arm reads `forecast_mw`, `confidence_upper_mw`, or `confidence_lower_mw`.

**Full trace:**

**Stage 1 — `delta_p_mw` (`simulation_core.py:318–320`, called at STARTING event):**
```python
delta_p_mw = (
    max(0.0, _p_target_after - _p_renewable_mw)
    - max(0.0, _p_target_before - _p_renewable_mw)
)
```
`_p_target_after/before` = sum of full-TDP draws for all active jobs (measured IT state).  
`_p_renewable_mw` = live solar output at staging time.  
**`forecast_mw` and confidence fields: not read.**

**Stage 2 — `peak_shortfall_mw` and ramp credit (`dispatch.py:566–569`):**
```python
_raw_credit       = sum(t.config.r_asset_mw_per_s for t in _active_turbines) * dt_lead_seconds
already_ramped_mw = min(_raw_credit, delta_p_mw)
peak_shortfall_mw = max(0.0, delta_p_mw - already_ramped_mw)
```
Pure arithmetic on `delta_p_mw` and turbine ramp rates. No forecast or confidence field.

**Stage 3 — Band-widened shortfall, power-ceiling arm (`dispatch.py:591–594`):**
```python
_band_upper      = self.site.reserve_band_upper(is_unmapped_hw=False)
_check_shortfall = peak_shortfall_mw * (1.0 + _band_upper)

if _check_shortfall > fleet_power_ceiling:
    return InsufficientReserveAlert(shortfall_mw=peak_shortfall_mw, ...)
```
Comment at `dispatch.py:584`: *"INV-2 (§2.5, TC-17): reserve check evaluates the confidence band, not the point estimate."*  
`_band_upper` is derived from catalogue keys `band_pct_calibrated`, `band_mult_uncalibrated`, `band_mult_unmapped_hw` via `SiteConfig.reserve_band_upper()` — **not** from the per-tick `confidence_upper_mw`/`confidence_lower_mw` wire fields. The "confidence band" referenced in the INV-2 comment is the site-configured headroom multiplier.

**Stage 4 — Endurance arm (`dispatch.py:605–613`):**
```python
allocations = self._capped_equal_share_allocations(peak_shortfall_mw, ceilings)
fleet_min_s = min(b.max_sustainable_seconds(alloc, island_mode) ...)
if fleet_min_s >= gap_s:
    return None, already_ramped_mw, peak_shortfall_mw
```
Uses **raw** `peak_shortfall_mw` (not `_check_shortfall`). No confidence field.

**`insufficient_reserve_alert` firing (`simulation_core.py:1264`):**
```python
alert_fired = state._pending_alert is not None and state._pending_alert.fires_at_sim_time <= sim_time
```
`fires_at_sim_time` is set to the `sim_time` of the STARTING event (`dispatch.py:599,620`). Alert fires on the same tick the STARTING signal lands. The tick-level `bess_bridging_seconds` is computed separately and is **not** the comparand for `insufficient_reserve_alert`.

**`bess_bridging_seconds` (tick path, `simulation_core.py:1023–1056`):**
```python
_pending_peak_mw   = state._pending_alert.shortfall_mw if state._pending_alert is not None else 0.0
_binding_demand_mw = max(net_demand_mw, _pending_peak_mw)
```
`net_demand_mw = max(0.0, p_demand_mw - p_renewable_mw)` — **measured demand**.  
`_pending_alert.shortfall_mw` — raw (not band-widened) physical shortfall.  
Neither `forecast_mw` nor `confidence_upper_mw`/`confidence_lower_mw` is read.

---

### P3.2 — Is the bridging capability anchor-adjusted?

**Yes — in both the staging path and the tick-level panel path.**

`BessModule.bridging_available_mw` (`asset_modules.py:1087–1092`):
```python
anchor_deduction = (
    self.config.p_anchor_reserve_mw
    if self.config.grid_forming and island_mode == IslandMode.ISLANDED
    else 0.0
)
return max(0.0, self.config.rated_mw - anchor_deduction)
```

`bess_anchor_reserve_mw` is subtracted only when **both** `grid_forming=True` AND `island_mode=ISLANDED`. Grid-following units and grid-connected mode take `anchor_deduction = 0.0`.

Both call sites apply this function before any comparison:

- **Staging path** (`dispatch.py:574`):  
  `ceilings = [b.bridging_available_mw(island_mode) for b in self.bess_units]`

- **Tick-level panel** (`simulation_core.py:1039`):  
  `_bbs_ceilings = [b.bridging_available_mw(_bbs_island_mode) for b in state.bess_units]`

`bess_anchor_reserve_mw` is therefore subtracted before both the insufficient-reserve comparison (staging) and the `bess_bridging_seconds` figure (panel).

---

### P3.3 — `_p_dispatch_droop_mw`

**Verbatim assignment (`simulation_core.py:719–725`):**
```python
_p_dispatch_droop_mw = max(
    0.0,
    min(
        p_dispatch_required_mw + _droop_correction_mw,
        _sync_ceiling_mw,
    ),
)
```

**Every input:**

| Input | File:line | Verbatim | Measured or forecast? |
|---|---|---|---|
| `p_dispatch_required_mw` | `simulation_core.py:585` | `max(0.0, p_demand_mw - p_renewable_mw)` | **Measured** — `p_demand_mw = p_compute_demand_mw + p_cooling_demand_mw` (live draw) |
| `_droop_correction_mw` | `simulation_core.py:707–712` | `Σ_i (−Δf / (droop_r × f₀)) × (rated_mw / pf)` for on-bus turbines | **Measured** — from `state._frequency_hz` (current tick frequency) |
| `_sync_ceiling_mw` | `simulation_core.py:718` | `sum(t.config.rated_mw for t in state.turbines)` | Config nameplate (not measured, not forecast) |

`_p_dispatch_droop_mw` is derived entirely from **measured demand and current frequency**. It reads neither `forecast_mw` nor any confidence field.

**`_droop_correction_mw` verbatim (`simulation_core.py:707–712`):**
```python
_droop_correction_mw = sum(
    (-_f_error_hz / (t.config.droop_r * state.site.frequency_nominal_hz))
    * (t.config.rated_mw / t.config.power_factor)
    for t in _on_bus_turbines
    if t.config.droop_r > 0.0
)
```
where `_f_error_hz = state._frequency_hz - state.site.frequency_nominal_hz` (`simulation_core.py:701`).

Applied only in islanded mode with on-bus turbines and `|Δf| > 0.02 Hz` governor deadband; otherwise `_droop_correction_mw = 0.0`.

---

### P3.4 — Re-rated capability

**`turbine_units[].rated_mw` always carries nameplate. No re-rating exists anywhere in the codebase.**

Evidence:

- `models.py:555`: `TurbineConfig.rated_mw: float = 10.0` — set at construction; `TurbineConfig` is a dataclass with no setter or mutation method on this field.
- `asset_modules.py:892`: `self._current_output_mw = max(0.0, min(new_output_mw, self.config.rated_mw))` — physical output is clipped to nameplate; the nameplate value is not modified.
- `asset_modules.py:965`: `rated_mw=self.config.rated_mw` — the per-unit field stamped on every TickResult is the unchanged config value.
- No function named `rerate`, `derate`, `apply_capacity_factor`, or equivalent appears in `core/`, `runtime/`, or `renewable/`.

If a re-rating were to be applied, the only sound locations would be at `TurbineConfig` construction time in `scenario_factory.py`, or by overriding the field in the unit state snapshot at `asset_modules.py:965`. Neither is currently used.

---

## Summary of findings by question

| Question | Finding |
|---|---|
| P0 primary cause | `SqlitePersistedTimeseriesSink` never instantiated in API path; every run uses `InMemoryTimeseriesSink` |
| P0 secondary cause | DB column names are old wire-alias names; current ORM attribute names differ; every INSERT would fail and be silently swallowed |
| P0 DB origin | Created by older ORM revision; `create_all(checkfirst=True)` leaves old schema intact |
| P3.1 — band or point? | Power-ceiling arm uses band-widened shortfall (catalogue multiplier, not wire band). Endurance arm uses raw point shortfall. Neither reads `forecast_mw` or `confidence_*_mw`. |
| P3.2 — anchor-adjusted? | Yes. `bridging_available_mw` subtracts `bess_anchor_reserve_mw` in both staging and tick paths, when `grid_forming=True AND island_mode=ISLANDED`. |
| P3.3 — `_p_dispatch_droop_mw` source | Measured demand (`p_demand_mw - p_renewable_mw`) plus droop correction from live frequency. No forecast field. |
| P3.4 — `rated_mw` nameplate or re-rated? | Always nameplate (`TurbineConfig.rated_mw`). No re-rating mechanism exists. |
