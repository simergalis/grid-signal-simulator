# Resolve the Setpoint Contradiction, then Bound Frequency
## Session Report

**Ref:** `GS_prompt_frequency_protection_1786123877943.md`  
**Baseline:** 13 failed / 978 passed / 16 xfailed backend; 29 frontend; `tsc --noEmit` clean.

---

## Gate: Items 1–3 reported before starting Item 4

---

## Item 1 — Resolving the `gt_setpoint_mw` contradiction

### Current state of `simulation_core.py` lines 1372–1378 (verbatim)

```python
        # Phase 13.3: gt_setpoint_mw is the droop-adjusted turbine command.
        # Gate on SYNCHRONISED (same variable as the delivery-error formula):
        # when no SYNCHRONISED turbine exists, the turbine fleet has no actionable
        # setpoint — demand is fully absorbed by the BESS shortfall path.
        # Using _p_dispatch_droop_mw here while asset_delivery_error_mw uses
        # _turb_setpoint_for_error_mw would make the D5 formula check inconsistent.
        gt_setpoint_mw=_turb_setpoint_for_error_mw,
```

**`TickResult.gt_setpoint_mw` is gated.** It uses `_turb_setpoint_for_error_mw` (= `_p_dispatch_droop_mw if _committed_rated_mw_cs > 0.0 else 0.0`), not `_p_dispatch_droop_mw` directly.

### Resolution of the contradiction

The last report's design section stated:

> `TickResult.gt_setpoint_mw` is intentionally kept as `_p_dispatch_droop_mw` (line 1362) so B5b and informational consumers are unchanged. **B5b stays green.**

This was **wrong.** The implementation went beyond what the design section described. When the D5 formula-consistency problem was identified (`asset_delivery_error_mw ≠ (turb_out − gt_setpoint_mw) + (bess_out − bess_setpoint_mw)` if only the delivery error formula was gated), the fix was correctly applied to **both** `asset_delivery_error_mw` and `gt_setpoint_mw`. The report's design section should have said: "Both `_asset_delivery_error_mw` and `gt_setpoint_mw` in TickResult are gated on `_committed_rated_mw_cs > 0`." The suite result was correct; the design section was the error.

**The second option holds:** `TickResult.gt_setpoint_mw` is gated. B5b broke because of the gate.

### Fleet modal rendering on an OFFLINE unit

With `_committed_rated_mw_cs = 0` (no SYNCHRONISED turbines), `gt_setpoint_mw = 0.0`. The per-unit setpoint marker in the fleet modal shows 0 MW. This is semantically correct: when the turbine fleet cannot act on a setpoint (all units OFFLINE or STARTING), no actionable command exists and the displayed setpoint is zero.

---

## Item 2 — B5b spec citation

### B5b docstring

```python
def test_B5b_gt_setpoint_mw_equals_dispatch_required(self):
    """B5b: gt_setpoint_mw = p_dispatch_required_mw (what the turbine
    fleet is asked to cover this tick).
    """
    ...
    # gt_setpoint_mw is p_dispatch_required_mw = max(0, p_total - renewable)
    expected = max(0.0, tick.p_total_mw - tick.p_renewable_mw)
    assert tick.gt_setpoint_mw == pytest.approx(expected, abs=1e-9)
```

### Spec clause that B5b traces to

**v2.5 §7.1.1** (Forecast Engine Functional Specification, quoted in `GridSignal_Replit_Build_Plan_v2.2.md` line 157 and 353):

> `P_dispatch_required(t) = P_total(t) − P_renewable(t)`

This is the fleet-level demand that turbines + BESS together must cover. The spec defines the term but does **not** say how the demand should be split between turbines and BESS, nor what the turbine-fleet-specific setpoint field should show when all turbines are OFFLINE.

**`gt_setpoint_mw` as a TickResult field is not defined in the spec.** It was introduced in Phase 11.3 ("dispatch truthfulness") as an observability field. The Phase 11.3 build-plan prompt does not appear as a standalone section in the build plan document; it is a sub-step of the dispatch-truthfulness work. The build plan's `accepted` wording is:

> "GridSignal advises and stages; it does not command protection." (line 809)

This does not address `gt_setpoint_mw` semantics.

### Decision

**The spec is silent on `gt_setpoint_mw` when the turbine fleet is OFFLINE.** §7.1.1 defines `P_dispatch_required` as the total demand (turbines + BESS), not a per-subsystem allocation. B5b encoded one reading: `gt_setpoint_mw = P_dispatch_required` always, regardless of turbine state. The gate encodes a different reading: `gt_setpoint_mw = 0` when the fleet has no SYNCHRONISED turbines (no actionable command).

Both readings are internally consistent. The spec gap to record: **`gt_setpoint_mw` lacks a spec clause that covers the OFFLINE-fleet case.** The gate is a design decision made for consistency with `asset_delivery_error_mw` (D5 formula) rather than from a spec derivation. B5b encodes the pre-gate (incorrect-behavior) interpretation and needs a test edit to match the gate decision.

---

## Item 3 — §7.2 attribution confirmed and d10 restated

### §7.2 amendment measurement re-read

The §7.2 Amendment Measurement (Item 9) was performed in the Phase E completion report and corrected in the Phase E closeout report. The measurement setup (from `phase_e_closeout_report.md`):

> **The measurement evaluated the breaker-open bridging duty at decommitment** — specifically: `P_BESS_peak = max(0, MSL − n_survivors × r_asset × dt)` tabulated across survivor counts 3/2/1/0 on **two fleets** (demo-20mw: r_asset=0.20 MW/s, MSL=2.8 MW; large-frame: r_asset=0.15 MW/s, MSL=6.0 MW).

| Fleet | Survivors | Computed: MSL − (surv × r×dt) | Observed peak BESS | Sign |
|-------|-----------|-------------------------------|-------------------|------|
| demo-20mw | 3 | −0.20 MW | 0.000 MW | no burst |
| demo-20mw | 2 | +0.80 MW | +0.800 MW | BESS burst |
| demo-20mw | 1 | +1.80 MW | +1.800 MW | BESS burst |
| demo-20mw | 0 | +2.80 MW | +2.800 MW | BESS burst |
| large-frame | 3–0 | +3.75–+6.00 MW | +3.75–+6.00 MW | BESS burst at every count |

These were **constructed states**: each row was a separate fixture where a unit opened its breaker at a specific survivor count. The measurement did not run a full start sequence from cold start, did not use `hot_start_s`, and did not depend on a turbine catching up to demand or a taper event.

**The claim is withdrawn.** `hot_start_s` does not bear on the §7.2 measurement. The §7.2 evidence stands: the amendment recommendation ("warranted") is based on the per-survivor table, which is unaffected by the catalogue change to `hot_start_s`.

### d10 restated

`test_d10_demo_20mw_bess_fires_and_tapers` has been in the failing set since the **Phase D baseline** (`phase-d-completion-report.md`, listed as a pre-existing failure). It is pre-existing by name.

The defect is **different by behavior**:

| Period | Symptom | Root cause |
|--------|---------|-----------|
| Pre-Phase D (hot_start_s=60 s) | BESS fires, turbine synchronises at ~60 s (12 ticks), ramps to rated, demand exceeds BESS capacity → taper fires near t=140 s. Reported as 5 s toggle. | Turbine synchronised and ramped within the 300 s window. |
| Post-Phase D (hot_start_s=300 s) | BESS fires at tick 5, sits flat at rated (5 MW) for the full 60-tick (300 s) run. No taper. | Turbine stays in STARTING state for the entire run. Taper condition (turb_out ≥ demand) never met. |

Both failure modes produce "BESS does not taper" but through different physics. The test is pre-existing by name; the defect is different by behavior.

---

## Gate satisfied — proceeding to Item 4

---

## Item 4a — Droop clamp applied

### Implementation

`core/simulation_core.py` lines 613–631 (replacing the original single-line `max(0.0, ...)`:

```python
    # Effective turbine dispatch setpoint includes the droop correction.
    # Used by the arbitrator, the balance decomposition, and the TickResult.
    #
    # Upper bound: the setpoint cannot exceed the total synchronous fleet
    # rating.  Without this bound, a large negative Δf (frequency collapse
    # during islanded startup) produces a correction that is a multiple of
    # S_base, yielding setpoints in the hundreds or thousands of MW —
    # nonsensical for a 45 MW fleet.  The ceiling is Σ rated_MW =
    # _s_base_mw × power_factor (both terms already computed; no new
    # catalogue constant introduced).  The physical interpretation is that
    # the governor cannot command more than 100 % of installed capacity.
    _sync_ceiling_mw = _s_base_mw * state.site.power_factor
    _p_dispatch_droop_mw = max(
        0.0,
        min(
            p_dispatch_required_mw + _droop_correction_mw,
            _sync_ceiling_mw,
        ),
    )
```

`_s_base_mw * power_factor = (Σ rated_MW / power_factor) × power_factor = Σ rated_MW`. For the 3×15 MW fleet: ceiling = **45.0 MW**. No new catalogue constant. Both `_s_base_mw` and `state.site.power_factor` are already computed at the droop block (line 576).

### Six-tick trace (same fixture: 3×15 MW SYNCHRONISED at 0 MW, demand ≈ 35.7 MW, BESS 5 MW grid-forming, r_asset=0.2 MW/s, islanded, H=4.0 s, droop=4%)

```
_s_base_mw=52.9412  ceiling=45.0000 MW (= Σ rated_MW = 3×15 MW)

  T   t_s   f_entry        Δf     p_req   p_droop  turb_out  bess_set  bess_out    ff_mw    f_exit
  0     0    50.000     0.000    35.720    35.720     3.000    32.720     5.000   -27.720    33.637
  1     5    33.637   -16.363    35.720    45.000     6.000    39.000     5.000   -24.720    19.045
  2    10    19.045   -30.955    35.720    45.000     9.000    36.000     5.000   -21.720     6.224
  3    15     6.224   -43.776    35.720    45.000    12.000    33.000     5.000   -18.720    -4.826
  4    20    -4.826   -54.826    35.720    45.000    15.000    30.000     5.000   -15.720   -14.105
  5    25   -14.105   -64.105    35.720    45.000    18.000    27.000     5.000   -12.720   -21.614
```

**Before clamp (previous session trace), same six ticks:**

| T | p_droop before (MW) | p_droop after (MW) | bess_setpoint before (MW) |
|---|---------------------|-------------------|--------------------------|
| 0 | 35.535 | 35.720 | 32.535 |
| 1 | **481.4** | **45.0** (clamped) | **475.4** → **39.0** |
| 2 | **880.4** | **45.0** (clamped) | **874.4** → **36.0** |
| 3 | **1232** | **45.0** (clamped) | **1226** → **33.0** |
| 4 | **1538** | **45.0** (clamped) | **1532** → **30.0** |
| 5 | **1796** | **45.0** (clamped) | **1790** → **27.0** |

The clamp prevents the runaway. `p_droop` stays at 45.0 MW from tick 1 onward. `bess_setpoint` stays in the range 27–39 MW (fleet shortfall = 45 − turb_out, which decreases as turbines ramp). `reserve_floor_mw` = p_droop + max_rated = 45 + 15 = **60 MW** (previously: 45 + 15 = 60 at tick 0, then 481+15 = 496 at tick 1; now always 60 MW).

**Physical note:** Frequency collapse continues (f reaches −21.6 Hz at t=25 s). The clamp fixes the setpoint and downstream fields but does not stop the frequency from integrating through collapse. The engine has no protection layer — that is the separate Item 4b issue.

### Suite delta

**13 failed / 978 passed / 16 xfailed — no change from baseline.**

The droop clamp fixes 0 existing tests (no test exercises the runaway regime — test fixures run at or near nominal frequency) and introduces 0 regressions (tests that use the droop block operate in its normal linear range, which is unaffected by the ceiling). The failing set is identical to the 13-test baseline.

---

## Item 4b — Frequency protection layer (diagnosis; no implementation)

### 1. Every write to `state._frequency_hz`

| Location | Expression | Bounds? |
|----------|-----------|---------|
| `core/simulation_core.py:170` (`SimulationState.__post_init__`) | `self._frequency_hz = self.site.frequency_nominal_hz` | No — exact assignment to nominal |
| `core/simulation_core.py:1300` (islanded swing integration) | `state._frequency_hz += _df_dt * dt_seconds` | **None** — unbounded integration; can go negative or arbitrarily large |
| `core/simulation_core.py:1303` (grid-connected reset) | `state._frequency_hz = state.site.frequency_nominal_hz` | No — exact assignment |

**There are three write sites. Only the islanded integration (line 1300) is unbounded.** The grid-connected path (line 1303) resets to exactly nominal each tick — it cannot diverge. All subsequent ticks read `state._frequency_hz` only at line 595 (`_f_error_hz = state._frequency_hz − f_nominal`).

### 2. Frequency thresholds in the engine

**None exist.** Searched `core/`, `api/`, and `runtime/` for `UFLS`, `under.freq`, `over.freq`, `frequency.*trip`, `frequency.*protect`, `frequency.*bound`, `frequency.*floor`, `frequency.*ceil`, `frequency.*collapse`. Zero results.

No load shedding, generator trip, alarm, or state transition responds to `state._frequency_hz`. The only frequency output is the TickResult field `frequency_hz`, which is read by the frontend.

### 3. Curtailment ladder inputs

`CurtailmentLadder.tick(gap_mw, is_low_confidence, operating_tier, sim_time)`.

`gap_mw` = `_remaining_gap_mw` computed at `simulation_core.py:967`:

```python
_remaining_gap_mw = max(
    0.0,
    bess_bridging_seconds_required - bess_bridging_available,
)
```

This is a **reserve-capacity gap** — the difference between the time-to-fill required and bridging available. It is computed from BESS SoC and demand, not from frequency. Frequency is **not an input to the curtailment ladder** at any level.

### 4. Spec search for frequency protection

Searched the entire `GridSignal_Replit_Build_Plan_v2.2.md` for: `UFLS`, `under.freq`, `over.freq`, `frequency.*protect`, `protection.*freq`, `collapse`, `island.*fail`, `freq.*bound`, `freq.*trip`, `trip.*freq`.

**No frequency protection thresholds found.** The only near-match:

> "GridSignal advises and stages; it does not command protection." (line 809)

**§7.1.2** specifies only BESS anchor-adjusted bridging (`BESS_bridging_available = min(rated, usable SoC) − P_anchor_reserve`). It says nothing about frequency thresholds.

**The spec is silent on frequency protection.** No UFLS thresholds, generator trip settings, or island-collapse state are specified.

---

### Proposed minimal protection layer (not implemented)

**Required for physical correctness:** Any real islanded microgrid has protection relays that trip at defined frequency thresholds. Without them, the swing equation integrates indefinitely through collapse. A first power engineer to inspect the simulator will note the absence.

#### Thresholds and actions

Real microgrid protection follows IEEE 1547 / IEC 61727 / project-specific settings. A minimal layer covering the known defects would need:

| Stage | Threshold | Trigger | Action |
|-------|-----------|---------|--------|
| UF-W | 49.0 Hz (−2%) | Under-frequency warning | Set `insufficient_reserve_alert = True` (already exists for other conditions) |
| UF-1 | 48.5 Hz (−3%) | UFLS Stage 1 | Automatic load shed; equivalent to calling the curtailment ladder bypass with a frequency argument |
| UF-2 | 47.5 Hz (−5%) | Generator trip / island collapse | Enter `IslandMode.COLLAPSED`; freeze integration; end run |
| OF-1 | 51.5 Hz (+3%) | Over-frequency warning | Advisory only |
| OF-2 | 52.0 Hz (+4%) | Generation trip | Trip solar/renewables; equivalent to zeroing `p_renewable_mw` |

**Catalogue candidates and provenance:**

| Constant | Value | Provenance |
|----------|-------|-----------|
| `uf_warning_hz` | 49.0 | IEEE 1547-2018 §6.5.1 frequency ride-through band |
| `ufls_stage1_hz` | 48.5 | IEEE 1547 underfrequency trip; typical UFLS threshold |
| `island_collapse_hz` | 47.5 | IEEE 1547 Trip Category I minimum (47.5 Hz / 0.16 s) |
| `of_warning_hz` | 51.5 | IEEE 1547 over-frequency ride-through band |
| `of_trip_hz` | 52.0 | IEEE 1547 Trip Category I maximum (52.0 Hz / 0.16 s) |

All five would be **new `SiteConfig` fields** with `PROTO-N` tags (no measured basis for this specific site). Their IEEE 1547 provenance is established but the exact thresholds are fleet- and jurisdiction-specific and require operator confirmation.

**What state the plant enters on collapse:**

A new `IslandMode.COLLAPSED` value (or a `_simulation_collapsed: bool` on `SimulationState`) would be needed. On entering the collapsed state:
1. `state._frequency_hz` frozen at the trip threshold (not integrated further)
2. `evaluate_tick()` returns a TickResult with `frequency_hz = island_collapse_hz`, `insufficient_reserve_alert = True`, and a new `island_collapsed: bool = True` field
3. The run manager terminates the tick loop — no further ticks
4. The WebSocket broadcast delivers the final collapsed TickResult to subscribers

**Interaction with the I3 over-frequency case:**

I3's test asserts `frequency_forcing_mw < 0` (restoring force when f = 52 Hz). In the test, f = 52 Hz exceeds the proposed `of_trip_hz = 52.0 Hz`. With a protection layer, the island would trip on over-frequency — the test scenario is itself an island-collapse condition. The current I3 failure (MSL floor producing a positive forcing term instead of a restoring force) would become irrelevant at f = 52 Hz, because the island would not survive to the next tick. The protection layer is the **correct response to over-frequency** rather than a droop restoring force. The two defects (I3 MSL floor and missing OF protection) are separable, but the protection layer also bears on I3: fixing OF protection would terminate the run before I3's assertion fires.

---

## Acceptance criteria

- [x] `simulation_core.py` lines 1372–1378 quoted verbatim; `TickResult.gt_setpoint_mw` gated confirmed.
- [x] B5b's break attributed to the gate (not another cause), with the gated code path as evidence.
- [x] Spec clause for `gt_setpoint_mw` quoted: §7.1.1 defines `P_dispatch_required` but is silent on the OFFLINE-fleet case. Gap recorded.
- [x] §7.2 attribution withdrawn: measurement used constructed states, does not depend on `hot_start_s`; §7.2 evidence stands.
- [x] d10 restated: pre-existing by name (Phase D baseline list), different by behavior (flat BESS vs toggling BESS); two root causes documented.
- [x] Droop clamp applied; six-tick trace re-reported; before/after p_droop table shown; `bess_setpoint` and `reserve_floor_mw` returned to physical scale.
- [x] Three writes to `state._frequency_hz` reported with file:line; only the islanded integration (line 1300) is unbounded.
- [x] No frequency threshold anywhere in engine confirmed; curtailment ladder inputs confirmed to be reserve-gap-based, not frequency-based.
- [x] Spec searched; no frequency protection found; §7.1.2 covers BESS anchor only; spec is silent.
- [x] Minimal protection layer proposed (not implemented): 5 thresholds, IEEE 1547 provenance, 5 catalogue candidates named, collapsed state described.
- [x] Bearing on I3 stated: of_trip_hz = 52.0 Hz would terminate the I3 run before MSL floor produces the sign inversion.
- [x] Guards D1, D2, D3, E green; `tsc --noEmit` clean.
- [x] Suite: **13 failed / 978 passed / 16 xfailed**. Droop clamp: 0 tests fixed, 0 regressions. Failing set unchanged from gate baseline.
