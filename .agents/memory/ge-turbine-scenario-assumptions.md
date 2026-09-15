---
name: GE turbine scenario assumptions
description: Shared GE simple-cycle assumptions and initial spinning-state semantics for seeded turbine scenarios.
---

All seeded turbine scenarios use a 35% minimum stable load, a 0.5 MW/s ramp rate (30 MW/min), and startup times of 300 s hot, 360 s warm, and 600 s cold. A unit marked `initial_state: "spinning"` starts synchronized at its minimum stable load; it cannot also be hot standby.

**Why:** The simulator's earlier frame-class defaults and scenario-specific startup overrides conflicted with the GE guidance, and the uneven multi-scheduler burst test needs synchronized generation at t=0 plus battery bridging while standby units start.

**How to apply:** Keep the shared parameter catalog and seeded scenario JSON aligned. Use explicit spinning units for t=0 generation; use hot-standby units for forecast/startup tests rather than treating standby as synchronized capacity.