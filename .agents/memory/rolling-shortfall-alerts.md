---
name: Rolling shortfall alerts
description: Simulator-backed 15-minute to 4-hour planning projection and its authority boundary.
---

Rolling planning alerts are advisory projections derived from the live tick: queue-derived full-TDP compute forecast, measured cooling, authoritative dispatchable capacity, current renewable output, and active ramp lead time. They must remain visually distinct from current balance/reserve alerts and must not be presented as a second physics simulation.

**Why:** The simulator has authoritative present-state and near-term workload data, but no validated external intraday forecast or future asset-availability schedule.

**How to apply:** Preserve the “simulator forecast” label and urgency windows (immediate, prepare, plan) until a validated 15-minute forecast feed and future availability model are added.