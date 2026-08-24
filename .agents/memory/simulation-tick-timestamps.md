---
name: Simulation tick timestamps
description: Interval-end convention for interpreting profile transitions in run time series and regression checks.
---

Tick payload timestamps label the end of the simulated interval. A demand-profile step that resets at time `T` can still appear in the tick stamped `T`, because that tick was evaluated over the preceding interval; the new value is visible from the next tick.

**Why:** Treating timestamps as interval starts makes a correct short-lived deficit look as though it extended into its recovery window.

**How to apply:** When testing or charting transition recovery, begin the post-transition assertion one simulation tick after the authored step time.

Rolling planning projections are sampled at 15-minute intervals. To target a specific later alert horizon in a synthetic forecast, keep every preceding sample below firm capacity; the alert magnitude at the target may differ.

**Why:** A ramp that crosses capacity between samples is reported at the first sampled point after the crossing, not at the authored continuous-time horizon.

**How to apply:** For 1-hour and 3-hour forecast fixtures, set injected firm capacity from the preceding 15-minute sample rather than assuming the final peak alone determines the reported horizon.