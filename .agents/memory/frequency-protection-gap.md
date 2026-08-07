---
name: Frequency protection gap
description: The swing equation has no bounds; no frequency threshold, UFLS, generator trip, or island-collapse state exists anywhere in the engine. Spec is silent.
---

## Every write to `state._frequency_hz`

| Location | Expression | Bounded? |
|----------|-----------|---------|
| `core/simulation_core.py:170` (`__post_init__`) | `= site.frequency_nominal_hz` | Yes (exact assignment) |
| `core/simulation_core.py:1300` (islanded) | `+= _df_dt * dt_seconds` | **NO — unbounded** |
| `core/simulation_core.py:1303` (grid-connected) | `= site.frequency_nominal_hz` | Yes (exact assignment) |

Only the islanded integration (line 1300) can diverge. It has no floor and no ceiling.

## No thresholds anywhere

No UFLS, under-frequency, over-frequency, generator trip, alarm, or island-collapse condition exists in `core/`, `api/`, or `runtime/`. Curtailment ladder takes `gap_mw` (reserve gap), not frequency.

## Spec is silent

Build plan search found no frequency protection thresholds. §7.1.2 covers BESS anchor reserve only. Closest match: "GridSignal advises and stages; it does not command protection." (build plan line 809).

## Proposed minimal protection layer (not yet implemented)

| Stage | Threshold | Action |
|-------|-----------|--------|
| UF-W | 49.0 Hz | `insufficient_reserve_alert = True` |
| UF-1 | 48.5 Hz | UFLS Stage 1 — load shed via curtailment |
| UF-2 / collapse | 47.5 Hz | Enter `IslandMode.COLLAPSED`, freeze integration, end run |
| OF-1 | 51.5 Hz | Advisory only |
| OF-2 | 52.0 Hz | Trip solar/renewables |

All five → new `SiteConfig` fields, tagged PROTO-N, provenance IEEE 1547-2018.

Collapsed state: `_frequency_hz` frozen at trip threshold; TickResult carries `island_collapsed=True`; run manager terminates tick loop.

## Bearing on I3

I3 fixture runs at f=52 Hz (OF-2 threshold). With protection, the island would trip on over-frequency before the assertion fires. The MSL-floor sign-inversion issue and the missing OF protection are separable but the protection layer is the correct response to f=52 Hz.

**Why:** Frequency unboundedness is the mirror-image of the droop runaway defect — one produces negative infinity, one produces positive infinity. The correction (droop clamp) treats the symptom; the protection layer treats the cause.
