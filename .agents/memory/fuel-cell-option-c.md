---
name: Fuel-cell Stage 3 Option C boundary
description: Durable scope and safety rules for grid forming, reactive loading, ride-through, and deliberately absent fault-duty modelling.
---

Fuel-cell Stage 3 is intentionally limited to grid-forming viability, power-factor/reactive loading, and IEEE 1547 frequency/ROCOF ride-through. Do not add fault-current contribution, fault-purpose inverter current limits, transformer impedance, or electrical properties on block-addressing groups.

**Why:** A board-only fault calculation omits collection-system backfeed and can understate duty by roughly a factor of seventeen while still looking precise. No fault-duty figure is safer than a partial one; the stamped engineer-of-record study remains authoritative.

**How to apply:** Keep fault-duty keys entirely absent from schemas and payloads—not zero or null. Electrical groups remain only a human-meaningful name and block count.

A fuel-cell former counts only while a running block produces real power. A BESS former can establish voltage at zero net MW exchange while energized and holding usable charge; an exhausted BESS does not count. Multiple formers are allowed.

**Why:** Grid-forming voltage synthesis does not require positive BESS real-power flow, but it does require a live inverter and energy source. Requiring positive BESS MW incorrectly collapses balanced islands.

**How to apply:** Collapse with the distinct reason `island_collapse_no_grid_forming_source` when neither condition remains.

Ride-through timers are contiguous-excursion timers and must run at frequency-physics substep resolution. Stop/non-producing intervals reset timers; protection trips remain persistent.

**Why:** Banking partial timer duration across separated excursions or restarts causes premature trips and violates the specified IEEE delay behavior.

**How to apply:** Track the fast and 300-second bands independently, reset each inactive threshold every substep, and reconcile P/Q/S, generation, forcing, and served/unserved telemetry to post-trip state on the trip tick.