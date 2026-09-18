---
name: Curtailment fuel attribution
description: The two curtailment-fuel metrics and the attribution rule used by Phase 2b reports.
---

Report two distinct curtailment-fuel quantities. Interval-exposure fuel sums all turbine fuel telemetry on ticks where dispatch curtailment is active. Attributable fuel allocates each tick's curtailed MWh across on-bus turbines in proportion to delivered output and prices each allocation at that unit's operating-point heat rate; it excludes no-load, standby, and start fuel.

**Why:** Treating interval-exposure fuel as attributable fuel overstated the fuel directly associated with curtailed generation and produced misleading avoided-curtailment shares.

**How to apply:** Use attributable fuel for avoided-curtailment deltas and shares. Preserve interval-exposure fuel as a separate diagnostic, and keep both values in run and aggregate artifacts.