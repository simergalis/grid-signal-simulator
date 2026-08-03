---
name: Solar tile stale-tick pattern
description: Why the Solar PV tile was mismatched with the Renewable Supply modal, and how it was fixed.
---

## The rule
The Solar PV tile in `PlantNode.tsx` must source its MW value from the live
`/api/solar/state` poll (same as the modal), NOT from `tick.p_renewable_mw`
alone.

## Why
After a run ends, `RunManager.clear_run_sync()` resets
`SolarSim._mistral_fraction_received_at = None`.  This switches
`live_aggregate_mw()` from the Mistral-injected fraction back to POA physics
(real-world sun position, typically lower than the simulation's solar-noon
scenario assumption).

The WebSocket tick is stale at this point — the last broadcast happened before
the run ended and it is never re-broadcast.  The tile showed the run's peak
value (~4.25 MW) while the modal, which polls `/api/solar/state` at 1.5 Hz,
showed the new standalone POA value (~1.06 MW).

## How to apply
`OpeningScreen.tsx` runs a 1.5 Hz `setInterval` polling `/api/solar/state`
and stores `liveSolarMW` in state.  It is threaded through `PlantDiagram` →
`PlantNode` as a new prop.  `PlantNode` prefers `liveSolarMW` over
`tick.p_renewable_mw` for the `solar-pv` node only:
```typescript
const mwValue = (def.id === 'solar-pv' && liveSolarMW != null)
  ? liveSolarMW
  : getMwValue(def, tick)
```
The same logic governs the amber "sun up · zero output" alert — it continues
to use `tick.p_renewable_mw` / `tick.p_expected_mw` so it only fires during
active runs.
