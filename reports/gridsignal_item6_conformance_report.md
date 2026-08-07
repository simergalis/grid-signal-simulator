# GridSignal Simulator v2 — Item 6 Conformance Report
## Items A–C Gate + Conformance Pass

**Date:** 2026-08-07  
**Ref:** `GS_prompt_item6_conformance_1786115492683.md`  
**Mockup:** `gridsignal_fleet_modal_proposed_1786115492687.html`  
**Gate prerequisite:** Items 1–5 passed at 15 / 975 / 16 xfailed backend, 29 frontend.

---

## Items A–C Gate

### Item A — Floor comparison verification

**Verdict: report was mis-transcribed. The comparison is correct.**

The comparison in `core/commitment.py` line 264:
```python
floor_violated = total_rated_mw < floor_mw
```

The Items 1–5 report stated: *"21 MW < 19 MW — correctly violated — `reserve_satisfied = False`"*  
This is a transcription error. `21 < 19` is `False`; the floor is met; `reserve_satisfied = True`.

#### Live `evaluate_commitment()` verification (explicit `p_demand_mw`):

| Case | `committed_rated_mw` | `floor_mw` | `floor_violated` | `reserve_satisfied` | `action` |
|------|---------------------|------------|-----------------|--------------------|----|
| SATISFIED: 3×7 MW bus, demand=12 MW, floor=12+7=19 MW | 21.0 | 19.0 | **False** | **True** | hold |
| VIOLATED: 2×7 MW bus, demand=10 MW, floor=10+7=17 MW | 14.0 | 17.0 | **True** | **False** | commit |
| ITEM-6: 3×15 MW bus, demand=34.5 MW, floor=34.5+15=49.5 MW | 45.0 | 49.5 | **True** | **False** | commit |

The comparison is not inverted. Satisfied state correctly returns `reserve_satisfied=True`; violated state correctly returns `reserve_satisfied=False`.

**Note on the live-tick script:** `evaluate_tick()` tests showed `fleet_utilisation=0` and `reserve_floor_mw=largest_mw` because the GPU module carries no jobs, making `p_dispatch_droop_mw=0`. The `evaluate_commitment()` direct calls above bypass this by injecting explicit `p_demand_mw`. The physics is correct; the test scaffold had no workload.

---

### Item B — `levelled_off_window_s` / `unload_tail_s` ordering

**Catalogue values (locked section of `gridsignal_parameters.json`):**

| Parameter | Value | Source |
|-----------|-------|--------|
| `levelled_off_window_s` | **10 s** | catalogue, locked |
| `levelled_off_epsilon_mw` | 0.05 MW | catalogue, locked |
| `unload_tail_s` | **60 s** | `TurbineConfig` dataclass default — **NOT in the locked catalogue** |

**Is the ordering enforced anywhere?**  
**No.** Nothing in the codebase validates that `unload_tail_s > levelled_off_window_s`. `unload_tail_s` is a per-unit `TurbineConfig` field; a spec or test fixture could set it to any positive value, including ≤ 10 s. If that happens, `_levelled_off_sustained` is never `True` and the panel indicator silently never fires.

**Observed True-duration on a real unload (`unload_tail_s = 30 s`):**

```
tick   sim_t  state          output_mw  dwell_s  sustained
   0     0.0  unloading         6.0000      0.0      False
   1     5.0  unloading         6.0000      5.0      False
   2    10.0  unloading         6.0000     10.0       True   ← dwell ≥ window_s (10)
   3    15.0  unloading         6.0000     15.0       True
   4    20.0  unloading         6.0000     20.0       True
   5    25.0  unloading         6.0000     25.0       True
   6    30.0  offline           0.0000      nan      False   ← breaker opens; reset

_levelled_off_sustained = True for 20 s  (= unload_tail_s − levelled_off_window_s = 30 − 10)
```

For the catalogue default (`unload_tail_s = 60 s`): sustained duration would be `60 − 10 = 50 s`.  
**Finding (not to fix here):** the ordering is a convention, not a code invariant. A non-default `unload_tail_s ≤ 10 s` would break the indicator silently.

---

### Item C — `committed_rated_mw` / `on_bus_output_mw` field comments

All three files now state which set each field uses and why. Comments as they stand post–Item 2 fixes:

#### `core/models.py` (TickResult dataclass):
```python
# committed_rated_mw: Σ rated_mw for SYNCHRONISED units this tick — SYNCHRONISED only.
#   UNLOADING units are excluded: they are pinned at MSL with no upward headroom, so
#   counting their nameplate overstates reserve precisely when the fleet is shrinking.
#   Distinct from on_bus_output_mw (run_manager) which INCLUDES UNLOADING because
#   UNLOADING units are breaker-closed and producing; the two fields answer different
#   questions — reserve capacity vs produced output.
# reserve_floor_mw:   p_demand + largest committed unit (N-1 floor from CommitmentDecision).
#   NOT the decommit threshold; reads directly from CommitmentDecision.floor_mw.
# fleet_utilisation:  p_demand / committed_rated_mw (0.0 when no committed units).
```
*(Was stale before this session: said "SYNCHRONISED/UNLOADING" — updated in Item 2 and again in this session.)*

#### `runtime/run_manager.py` (commitment_block emission):
```python
# committed_rated_mw: Σ rated_mw for SYNCHRONISED units only (see models.py).
#   UNLOADING excluded — pinned at MSL, no upward headroom.  Distinct from
#   on_bus_output_mw above which INCLUDES UNLOADING (they produce at MSL).
```
*(Added this session — was absent before.)*

#### `frontend/src/types.ts` (TickPayload.commitment_block):
```typescript
// committed_rated_mw: Σ rated_mw for SYNCHRONISED units — SYNCHRONISED only.
// UNLOADING excluded (pinned at MSL, no headroom). Distinct from on_bus_output_mw
// which includes UNLOADING; the two fields answer different questions.
committed_rated_mw:    number
// reserve_floor_mw: p_demand + largest committed unit (N-1 floor, from CommitmentDecision).
reserve_floor_mw:      number
```
*(Added this session — fields existed but were uncommented.)*

The `on_bus_output_mw` comments in `run_manager.py` (lines 242–244) and `types.ts` (lines 130–131) were already correct and unchanged:
```python
# on_bus_output_mw: algebraic fleet production from the on-bus set A (D-05 rename).
#   Formula: P_fleet = Σ_{i ∈ A} p_i  where A = {state ∈ {synchronised, unloading}}
# UNLOADING units included so per-unit rows always sum to the fleet hero value.
```

**Gate A–C: passed.** Proceeding to conformance.

---

## Item 6 — Conformance Pass

**Reference fleet:** 5 × 15 MW, MSL 40% (6.0 MW/unit), `r_asset` 0.3 MW/s, 45 s lead window.  
**State:** 3 SYNCHRONISED, 1 STARTING, 1 OFFLINE. Demand 34.5 MW. Utilisation 76.7%. Floor violated.

### `evaluate_commitment()` on the Item 6 state (direct call):

```
committed_rated_mw  =  45.0 MW  (3 × 15 MW SYNCHRONISED)
floor_mw            =  49.5 MW  (34.5 demand + 15.0 largest)
floor_violated      =  True     (45.0 < 49.5)
reserve_satisfied   =  False
fleet_utilisation   =  0.767    (34.5 / 45.0 = 76.7%)
action              = 'commit'  (floor governs, not the 80% trigger)
reason              = 'reserve floor violated: 45.0 MW committed < 49.5 MW required'
blocked_by          = '' (no start in progress in this test call; pending starts would populate)
```

The panel CAN express this state. Utilisation (76.7%) sits below the commit threshold (80%), yet `action=commit` fires because `floor_violated=True`. The commitment rows communicate this: Committed MW shows RED with the floor value in the sub-label, and Last decision shows `COMMIT` (not `HOLD`). An operator can see that commitment is active below the utilisation trigger.

### What the panel renders for the 76.7% floor-violated state:

**Stat rows (from panel logic applied to the state above):**

| Row label | Value | Sub-label |
|-----------|-------|-----------|
| Units installed | 5 | 15 MW each · 75 MW total |
| Units on bus | 3 | contributing 32.20 MW |
| N−1 firm capacity | **30.0 MW** | with any one committed unit unavailable |
| Design peak load | (from tick) | declared at scenario design point |
| N−1 margin | −12% | 45 MW committed − 15 MW contingency = 30 MW firm · peak 38.5 MW |
| Aggregate ramp | backend MW | MW/s over 45 s horizon (SYNCHRONISED only — starts excluded) |
| Ramp with 1 unit | clamped to headroom | MW/s · clamped to N MW headroom — BESS covers the remainder |
| Cold-start sync | 900 s (15 min) | STARTING units contribute 0 to ramp reserve |
| **Committed MW** | **45.0 MW** (RED) | reserve floor 49.5 MW (77% utilisation) |
| **Last decision** | **COMMIT** (teal) | reserve floor violated: 45.0 MW committed < 49.5 MW required |
| Starting | turbine-3 (when pending) | in start sequence — not counted toward committed capacity or ramp |

**The panel renders the floor-violated state coherently.** The commitment rows correctly show the situation: capacity is below the floor, a commit is in progress, and the starting unit is identified separately as not counting toward reserve. An operator can distinguish "satisfied and constrained" from "violated and committing."

---

### Conformance element-by-element

| Element | Mockup specifies | Panel status | Notes |
|---------|-----------------|--------------|-------|
| **Per-unit bar** | Full-width bar (132px+, 16px tall) in its own "Output · setpoint · MSL" column; fill (amber/ember), dashed MSL rule, cyan setpoint marker | **DIFFERS** | Panel has a 48px × 4px mini-bar embedded in the CURRENT MW cell. Same three elements present (fill, dashed MSL rule, cyan marker) but at small scale inside a data cell, not a dedicated column. |
| **Ramp gap** | Teal-shaded region between fill and setpoint marker; legible gap shows unit tracking toward higher setpoint (mockup: turbine-1, 11.20 → 13.50 MW) | **NOT IMPLEMENTED** | The mini-bar has fill and setpoint marker but no shaded gap element between them. The ramp is visible only as a statistical value in the "Ramp with 1 unit" row. |
| **STARTING row** | Hatched countdown fill draining over `hot_start_s`; inline annotation "hot · sync in 3:05 · purge complete"; SYNC column reads "starting" | **PARTLY IMPLEMENTED** | Countdown is shown as seconds in the output cell (e.g. "185s"). SYNC column reads "syncing". But: (1) bar shows empty/black fill, not the hatched countdown animation; (2) thermal state + start phase annotation is not inline — it appears only in the separate clickable ThermalStateWidget below the table. |
| **UNLOADING** | Ember (orange-red) unit ID colour; visually distinct from SYNCHRONISED; fill uses ember colour | **PARTLY IMPLEMENTED** | STATE column text is "unloading" (distinct). But: unit ID colour is GOLD for all states (not ember for UNLOADING); fill colour in mini-bar does not change for UNLOADING state (always uses `outColour` which is GOLD when output > 0). A unit leaving cannot be visually distinguished from a unit at MSL by colour alone. |
| **Verdict band N−1 firm** | Computed from committed (on-bus) units; 30.0 MW = 3×15 − 15; installed would give 60 MW and mask the shortfall | **MATCHES** | U-4 fix is in place. `n1FirmMW = onBusMW − maxOnBusMW` uses the same on-bus filter as `isOnBus()`. A 5-unit fleet with 3 on bus correctly reports 30.0 MW firm, not 60 MW. |
| **Committed capacity row** | Value = sum of SYNCHRONISED units; sub-label explicitly says "turbine-3 starting contributes 0" | **DIFFERS** | Value is correct (SYNCHRONISED only). Sub-label reads `reserve floor 49.5 MW (77% utilisation)` — informative but does not call out the excluded starting unit by name or category. |
| **Reserve floor row** | Dedicated row with value "49.5 MW · short 4.5" and sub "34.50 MW demand + 15.0 MW largest committed unit" showing arithmetic | **NOT IMPLEMENTED as dedicated row** | The floor value appears as part of the "Committed MW" row sub-label. There is no separate row for the reserve floor with its own label, value, shortfall notation, and arithmetic sub-label. |
| **Utilisation scale** | Visual scale bar with two threshold markers (decommit 50%, commit 80%), fill at current utilisation, text "76.7% — below the commit threshold" | **NOT IMPLEMENTED** | No visual scale bar exists. Utilisation is expressed as a percentage in the "Committed MW" sub-label only (no markers, no visual position). |
| **Blocked panel** | `blocked_by` shown in a distinct violet-bordered panel AND `last_decision_reason` on a separate line below it | **DIFFERS** | The "Last decision" stat row shows `blocked_by` OR `reason` — whichever is non-empty — not both simultaneously. When `blocked_by` is populated, `reason` is hidden. An operator cannot see both why the fleet is constrained and what the engine last decided at the same time. |
| **Marginal-unit ramp** | "turbine-2: 9.00 MW headroom · 13.50 MW at rate — clamped to headroom → 9.0 MW" | **MATCHES** | U-3 fix is in place. `rampWith1MW = min(perUnit, maxHeadroom)`. Sub-label reads "clamped to N MW headroom — BESS covers the remainder". The headroom value is stated. |
| **Preserved: verdict band, fleet table, Trip/Start, paralleling strip, dark/mono/amber** | All retained | **MATCHES** | All five preserved elements are present and unchanged. Fleet table has UNIT, CURRENT MW, NO-LOAD/MSL MW, SYNC, RAMP, RUN h, STATE, COMMAND columns. ParallelingInset present. |

---

### Mockup errors found

1. **Fleet hero value**: Mockup shows `32.20 MW on bus` in the hero. The three on-bus units produce 15.00 + 11.20 + 6.00 = 32.20 MW. ✓ Consistent.

2. **Committed capacity vs N-1 firm**: Mockup shows committed = 45.0 MW and N-1 firm = 30.0 MW (45 − 15). But the verdict says "N-1 firm capacity 30.0 MW does not cover the 38.5 MW design peak — shortfall 8.5 MW". `38.5 − 30.0 = 8.5`. ✓ Arithmetic consistent.

3. **Marginal unit annotation**: Mockup shows turbine-2 (at MSL, 6.0 MW / 15.0 rated = 9.0 MW headroom) as the marginal unit. At r_asset = 0.3 MW/s × 45 s = 13.5 MW potential, clamped to 9.0 MW headroom → 9.0 MW. ✓ Consistent with U-3 headroom clamping.

4. **Fleet ramp capability = 12.8 MW**: The mockup claims 12.8 MW aggregate ramp over 45 s. At 0.3 MW/s × 45 s = 13.5 MW per unit potential. turbine-0 is at rated (0 headroom), so it contributes 0. turbine-1 at 11.20 MW has 3.80 MW headroom, turbine-2 at 6.00 MW has 9.00 MW headroom → aggregate = 3.80 + 9.00 = 12.80 MW. ✓ Consistent.

5. **"one unit is starting; coverage is expected to restore at synchronisation"**: The verdict note is plausible but turbine-3 at 15 MW syncing would raise committed from 45 to 60 MW and N-1 firm from 30 to 45 MW, covering the 38.5 MW peak with margin. ✓ Consistent.

**No internal inconsistencies found in the mockup.** All figures are derivable from the stated parameters (5 × 15 MW, MSL 40%, r_asset 0.3 MW/s, 45 s lead window, demand 34.5 MW).

---

## Differences requiring implementation to close

| # | Element | Gap |
|---|---------|-----|
| 1 | Per-unit bar | Mini-bar (48 × 4 px in data cell) vs dedicated column (132+ × 16 px). The ramp gap cannot be legible at mini scale. |
| 2 | Ramp gap shading | No shaded teal region between fill and setpoint marker. |
| 3 | STARTING hatched bar | Empty bar instead of hatched countdown fill draining over `hot_start_s`. |
| 4 | STARTING inline annotation | Thermal state + phase shown only via ThermalStateWidget (below table, click-to-open), not inline in the row. |
| 5 | UNLOADING color distinction | Unit ID and fill are GOLD like SYNCHRONISED; mockup uses ember (orange-red). |
| 6 | Committed row sub-label | Does not name the excluded STARTING unit explicitly. |
| 7 | Reserve floor: dedicated row | No separate row — floor absorbed into Committed MW sub-label. |
| 8 | Utilisation scale bar | No visual bar with threshold markers; utilisation is text-only in a sub-label. |
| 9 | Blocked + reason simultaneous | `blocked_by` hides `reason` in the current stat row; mockup shows both. |

Items 1–5 fixes (U-2, U-3, U-4, U-5, STARTING sync column, commitment rows) are all implemented and matching. The nine gaps above are layout and visual-fidelity differences — the panel communicates the correct information but does not organise it the way the mockup proposes.

---

## Final Suite State

| Metric | Value |
|--------|-------|
| Python failed | 15 (all pre-existing) |
| Python passed | **975** |
| Python xfailed | 16 |
| Frontend tests | **29 / 29** |
| New regressions | **0** |
| TypeScript | **clean** |

### Files changed this session (Items A–C + comment fixes):
| File | Change |
|------|--------|
| `core/models.py` | `committed_rated_mw` comment updated: SYNCHRONISED-only, reason for exclusion, distinction from `on_bus_output_mw`, corrected `reserve_floor_mw` description |
| `runtime/run_manager.py` | Added `committed_rated_mw` set comment at `commitment_block` emission site |
| `frontend/src/types.ts` | Added `committed_rated_mw` and `reserve_floor_mw` comments in `TickPayload.commitment_block` type |
