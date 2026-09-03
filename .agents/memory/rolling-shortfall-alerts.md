---
name: Rolling shortfall alerts
description: Simulator-backed 15-minute to 4-hour planning projection and its authority boundary.
---

Rolling planning alerts are advisory projections derived from the live tick: queue-derived full-TDP compute forecast, measured cooling, firm generation capacity, current renewable output, and active ramp lead time. Contingency dispatchable capacity includes BESS bridge power, which must be subtracted for this 15-minute–4-hour planning horizon. They must remain visually distinct from current balance/reserve alerts and must not be presented as a second physics simulation.

**Why:** The simulator has authoritative present-state and near-term workload data, but no validated external intraday forecast or future asset-availability schedule. Short-duration battery bridge power is not sustained generation and can otherwise hide a real projected workload gap.

**How to apply:** Preserve the “simulator forecast” label and urgency windows (immediate, prepare, plan); compare projected demand against dispatchable capacity minus BESS bridging MW until a validated future availability and storage-duration model is added.