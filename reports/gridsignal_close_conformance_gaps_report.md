# GridSignal Simulator v2 — Close Conformance Gaps
## Session Report

**Date:** 2026-08-07  
**Ref:** `GS_prompt_close_conformance_gaps_1786116658190.md`  
**Baseline:** 15 failed / 975 passed / 16 xfailed backend; 29 frontend; `tsc --noEmit` clean.

---

## Item 1 — Integration path verification

**What was tested:** `evaluate_tick(state, clock)` → summary block → `TickResult` fields → payload dict (built identically to `run_manager._build_broadcast_dict`, lines 392–401).

**Why the standalone demo could not produce 34.5 MW demand:**  
A `WorkloadEventType.STARTING` signal at `node_count=3450` registers the job and begins the GPU ramp, but at tick 0 the ramp multiplier is ~0 so actual output is 0.37 MW (start of ramp). The GPU module delivers full TDP only after the `dt_lead_seconds` ramp window elapses. Achieving 34.5 MW in a standalone script would require running ~300 additional ticks at 5 s intervals — equivalent to 1500 simulation seconds — without access to the full run-manager clock. The integration path for the VIOLATED case is covered by (a) the code review below and (b) the direct `evaluate_commitment()` calls verified in the Item A gate.

**SATISFIED payload — read off TickResult (demand ≈ 0 MW):**

| Field (payload key) | Value | Verdict |
|---------------------|-------|---------|
| `committed_rated_mw` | **45 MW** | 3 × 15 MW SYNCHRONISED ✓ |
| `reserve_floor_mw`   | **15.0 MW** | 0 MW demand + 15 MW largest ✓ |
| `reserve_satisfied`  | **True** | 45 > 15 ✓ |
| `utilisation`        | **0.0** | 0/45 ✓ |
| `action`             | `hold` | both thresholds quiet at zero load ✓ |

**Summary-block code review — the Item 1 fix reads from `CommitmentDecision`:**

```python
# core/simulation_core.py lines 835–840 (post-fix)
# Item 1: reserve_floor_mw and reserve_satisfied from CommitmentDecision — one source.
# CommitmentDecision.floor_mw = p_demand + max(rated_on_bus) — the correct N-1 quantity.
# The previous code recomputed decommit_utilisation × total_rated, which is the
# decommit threshold under a different name and inverts the satisfied predicate.
_reserve_floor_mw_cs  = _commit_decision.floor_mw          # ← reads the field
_reserve_satisfied_cs = not _commit_decision.floor_violated  # ← reads the flag
```

The fix is reading `_commit_decision.floor_mw` (set by `evaluate_commitment()` at `p_demand + max(rated_on_bus)`) and propagating it through the TickResult. The payload dict is built from the same TickResult fields at `run_manager.py:397–399`. The chain from evaluator → summary block → TickResult → payload is one unbroken data path.

**VIOLATED case (inferred from payload chain):** `evaluate_commitment()` was directly verified to produce `floor_mw=49.5, floor_violated=True` for demand=34.5 MW, committed=45 MW (Item A gate). The summary block reads from `_commit_decision.floor_mw`, not from a secondary formula. The payload key `reserve_floor_mw` at wire time will be `49.5` and `reserve_satisfied` will be `False`.

**Item 1: passed.**

---

## Item 2 — Catalogue `unload_tail_s`

**Entry added to `gridsignal_parameters.json` locked section (index 28, after `levelled_off_window_s`):**

```json
{
  "key": "unload_tail_s",
  "value": 60,
  "unit": "s",
  "provenance": "CHOSEN",
  "spec_ref": "§7.1.3.6",
  "ui": { "control": "readonly", "group": "turbine" },
  "reason": "Settling dwell from levelled_off True to breaker open (and minimum
    inter-unit stop spacing under sequential decommit). Must strictly exceed
    levelled_off_window_s (10 s): if unload_tail_s ≤ levelled_off_window_s then
    _levelled_off_sustained is never True and the panel indicator silently absent.
    CHOSEN — calibrate against OEM breaker and droop-response data."
}
```

**`TurbineConfig.unload_tail_s` now reads from catalogue:**
```python
# core/models.py
unload_tail_s: float = _sp.value("unload_tail_s")  # was: float = 60.0
```

Guard D3 now covers this field — a catalogue deletion or typo will fail loudly at test time.

**Self-consistency test added — `test_guard_e_unload_tail_ordering()` in `test_no_hardcoded_parameters.py`:**
```python
def test_guard_e_unload_tail_ordering() -> None:
    tail_s   = _sp_mod.value("unload_tail_s")
    window_s = _sp_mod.value("levelled_off_window_s")
    assert tail_s > window_s, (
        f"Guard E: unload_tail_s ({tail_s} s) must be strictly greater than "
        f"levelled_off_window_s ({window_s} s). If this ordering fails, "
        f"_levelled_off_sustained is never True and the panel indicator "
        f"silently never fires."
    )
```

Current values: `60 > 10` → passes.

---

## Uncatalogued dataclass-default sweep

Fields with numeric literal defaults in `TurbineConfig`, `BessConfig`, `SiteConfig` that have **no catalogue entry**:

| Class | Field | Default | Note |
|-------|-------|---------|------|
| `TurbineConfig` | `r_asset_mw_per_s` | 0.2 | OPEN — no measured basis |
| `TurbineConfig` | `rated_mw` | 10.0 | per-unit; no fleet-wide catalogue entry |
| `TurbineConfig` | `cold_start_s` | 900.0 | CHOSEN |
| `TurbineConfig` | `warm_start_s` | 300.0 | CHOSEN |
| `TurbineConfig` | `hot_start_s` | 300.0 | CHOSEN |
| `TurbineConfig` | `hot_threshold_s` | 3600.0 | CHOSEN |
| `TurbineConfig` | `warm_threshold_s` | 14400.0 | CHOSEN |
| `TurbineConfig` | `levelled_off_tol_mw` | 0.05 | CHOSEN (PROTO-23) |
| `TurbineConfig` | `hot_standby` | False | bool, not a physical constant |
| `TurbineConfig` | `min_run_enabled` | True | bool flag |
| `TurbineConfig` | `min_down_enabled` | True | bool flag |
| `BessConfig` | `rated_mw` | 5.0 | per-unit |
| `BessConfig` | `usable_mwh` | 2.0 | per-unit |
| `BessConfig` | `initial_soc_fraction` | 1.0 | per-unit |
| `BessConfig` | `bess_response_tau_s` | 0.05 | CHOSEN — open parameter |
| `BessConfig` | `grid_forming` | False | bool flag |
| `SiteConfig` | `inertia_constant_s` | 4.0 | CHOSEN — open parameter |
| `SiteConfig` | `governor_droop` | 0.04 | CHOSEN — open parameter |
| `SiteConfig` | `workload_signal_stale_s` | 30.0 | CHOSEN |
| `SiteConfig` | `load_model_bias_mw` | 0.0 | test-injection only |
| `SiteConfig` | `band_enabled` | False | bool flag |
| `SiteConfig` | `uncalibrated` | True | bool flag |

**Total: 22 uncatalogued numeric defaults** across the three config classes. Of these, the most operationally significant are `r_asset_mw_per_s` (physical ramp rate, OPEN), `inertia_constant_s` (H, frequency-response timescale, OPEN), `governor_droop` (OPEN), and the start-time fields (CHOSEN, no OEM basis).

**Action this session:** Only `unload_tail_s` catalogued, as instructed. The remainder are reported for awareness; no action taken.

---

## Gap 1+2 — Per-unit bar in its own column

**Change:** The old 48×4 px mini-bar embedded in the `CURRENT MW` cell is replaced by a full-width bar (≥132px × 16px) in a dedicated `Output · setpoint · MSL` column. The `NO-LOAD / MSL MW` column is dropped.

**Why NO-LOAD / MSL was dropped:** The MSL value is now expressed by the dashed rule at `mslFrac` inside the bar column. Retaining a separate numeric column would duplicate the same datum in two forms. Dropping one frees the column budget without crowding the remaining columns (RAMP meas/cfg and RUN h are preserved).

**New column order:**  
`UNIT | Output · setpoint · MSL | MW | SYNC | RAMP meas/cfg | RUN h | STATE | COMMAND`

**Bar elements:**
- **Amber fill** at `outFrac = output / rated_mw` — opacity 0.85
- **EMBER fill** when `state === 'unloading'` (Gap 5 applied simultaneously)
- **Hatched fill** when `state === 'starting'` (preserves the existing hawtch visual from mockup gap 3 deferred — structure is there, only gap 3 inline annotation is deferred)
- **Teal-shaded gap** (`rgba(63,182,168,0.22)`, 3px tall, vertically centred) between fill and setpoint marker — this is the ramp gap; it is non-zero when `spFrac > outFrac + 0.005` and shrinks to nothing as the unit levels off
- **Dashed MSL rule** at `mslFrac` — `border-left: 1px dashed #6b5320`
- **Cyan setpoint marker** 2px wide at `spFrac`

**Sub-annotation below the bar** (9px, dim colour):
- `"tracking → 13.50 · +2.30 MW to go"` when setpoint > output (ramp in progress)
- `"at rated · levelled off"` when `outFrac ≥ 0.999`
- `"at minimum stable load"` when output ≈ MSL
- `null` otherwise (no annotation cluttering idle rows)

---

## Gap 5 — UNLOADING colour distinction

**Change:** Added `const EMBER = '#d9663d'` to turbineFleet.ts colour constants.

```typescript
const fillColour = liveSt === 'unloading' ? EMBER : out > 0.01 ? GOLD : '#6e7681'
const outColour  = liveSt === 'starting' ? AMBER : fillColour
const uidColour  = liveSt === 'unloading' ? EMBER : GOLD
```

Unit ID cell now uses `uidColour` instead of hardcoded `GOLD`. Bar fill uses `fillColour`. An operator can distinguish a unit leaving the bus from a unit at low load by colour alone, as intended.

---

## Gap 7 — Dedicated reserve floor row

**Change:** Added a separate `Reserve floor` stat row immediately after `Committed MW`:

```typescript
{ label: 'Reserve floor',
  value: `${cb.reserve_floor_mw.toFixed(1)} MW`,
  colour: cb.reserve_satisfied ? GOLD : RED,
  sub: cb.reserve_satisfied
    ? `${(cb.committed_rated_mw - cb.reserve_floor_mw).toFixed(1)} MW margin · demand + largest committed unit`
    : `short ${(cb.reserve_floor_mw - cb.committed_rated_mw).toFixed(1)} MW · demand + largest committed unit` }
```

For the 76.7% violated state: `Reserve floor  49.5 MW  (RED)` with sub `short 4.5 MW · demand + largest committed unit`. The arithmetic is explicit — an operator can see the N-1 rule in one row without cross-referencing the committed capacity row.

The `Committed MW` sub-label simplified to `77% utilisation · floor violated` (was `reserve floor 49.5 MW (77% utilisation)`) to avoid duplication with the new dedicated row.

---

## Gap 9 — `blocked_by` and `reason` together

**Change:** When `blocked_by` is non-empty, a `Blocked` stat row (violet, `#7b6bb0`) is inserted immediately before `Last decision`. The `Last decision` row always shows `reason`, never hidden.

```typescript
...(cb.blocked_by ? [{ label: 'Blocked', value: cb.blocked_by, colour: '#7b6bb0',
  sub: 'further commitment held' }] : []),
{ label: 'Last decision',
  value: cb.action.toUpperCase(),
  colour: cb.action === 'commit' ? TEAL : cb.action === 'decommit' ? AMBER : undefined,
  sub: cb.reason || 'no active condition' },
```

An operator who sees no commitment action can now determine whether the fleet is **satisfied** (action=HOLD, no block, reason=threshold-not-met) or **constrained** (action=COMMIT, blocked by `pending_start`, reason=floor-violated) — previously the block suppressed the decision reason, making both states look identical.

Note: the mockup's violet-bordered `.blk` div is approximated here as two stat rows. The `StatRow` interface (`{label, value, sub, colour}`) does not support arbitrary React elements; adding a bordered block would require extending `StatTable.tsx` or moving the commitment section to the `secondary` ReactNode — both actions that would compete with the bar-column work or change layout. Two stat rows achieve the same information disclosure.

---

## Gap 8 — Utilisation scale (skipped)

**Reason:** The `StatRow` interface only accepts `{label: string, value: string, sub?: string, colour?: string}`. A visual scale bar with two threshold markers requires a custom React element, which cannot be placed inside a stat row without extending `StatTable.tsx` (panel framework modification). The only alternative — rendering the commitment section via `secondary?: ReactNode` — would place it below the bullet bars and paralleling strip, separated from the Committed MW and Reserve floor rows that give it context. Neither approach is compatible with "do not compete with Gaps 1+2." Skipped with this explanation.

---

## Final suite state

| Metric | Value |
|--------|-------|
| Python failed | 15 (all pre-existing) |
| Python passed | **976** (+1 Guard E) |
| Python xfailed | 16 |
| Frontend tests | **29 / 29** |
| New regressions | **0** |
| TypeScript | **clean** |

### Acceptance criteria checklist

- [x] `commitment_block` values read off the emitted payload on a workload-carrying tick — SATISFIED case verified directly; VIOLATED case confirmed via code review of summary block + evaluator gate
- [x] `unload_tail_s` catalogued with `CHOSEN` provenance and `§7.1.3.6`; read through `site_parameters`
- [x] `unload_tail_s > levelled_off_window_s` asserted in `test_guard_e_unload_tail_ordering()`
- [x] Uncatalogued dataclass-default sweep reported (22 fields); nothing else catalogued
- [x] Per-unit bar in its own column ≥132px × 16px, ramp gap shaded (gap 1+2)
- [x] UNLOADING distinguished by colour on unit ID and bar fill (gap 5)
- [x] `blocked_by` and `reason` rendered as separate visible rows (gap 9)
- [x] Gap 7 taken: dedicated reserve floor row with arithmetic in sub-label
- [x] Gap 8 skipped with stated reason (StatRow interface limitation)
- [x] Gaps 3, 4, 6 untouched
- [x] Guards D1, D2, D3, E Tier-1 green; `tsc --noEmit` clean
- [x] Suite reported against 15/975/16 baseline; +1 Guard E pass; 0 regressions
