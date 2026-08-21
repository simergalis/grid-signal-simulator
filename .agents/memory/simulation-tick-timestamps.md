---
name: Simulation tick timestamps
description: Interval-end convention for interpreting profile transitions in run time series and regression checks.
---

Tick payload timestamps label the end of the simulated interval. A demand-profile step that resets at time `T` can still appear in the tick stamped `T`, because that tick was evaluated over the preceding interval; the new value is visible from the next tick.

**Why:** Treating timestamps as interval starts makes a correct short-lived deficit look as though it extended into its recovery window.

**How to apply:** When testing or charting transition recovery, begin the post-transition assertion one simulation tick after the authored step time.