---
name: Rolling planning forecast timeline
description: Future scripted workload peaks must be projected from the event schedule without running a second physics simulation.
---

The rolling-planning UI consumes a deterministic backend timeline of full-TDP compute forecasts sampled every 15 minutes. Future STARTING events add their rated contribution and JOB_END/CANCELLED events remove it; the frontend preserves its existing cooling and firm-capacity calculations.

**Why:** The live TickResult forecast is intentionally current-state-only, so using it alone makes future scheduled peaks appear as “No projected shortfall.” A second simulation would risk diverging from authoritative physics.

**How to apply:** When adding scripted planning scenarios, give each peak a matching end event if distinct overload windows are intended, keep the wire field optional for direct/headless runs, and let scripted points override the reference-day shape numerically as well as by label.