---
name: Forecast scale-event protection
description: Commitment and preload behavior for forecasted workload scale-ups.
---

Treat a future workload SCALE event as a forecast burst start for informed turbine commitment. A scale-up can arrive while a stopped turbine is still unloading, within minimum-down time, or restarting, so it must participate in preload and stop-protection decisions even when the workload's original STARTING event is historical.

**Why:** The Addendum H smoke's remaining informed deficit was caused by a future Ray scale event being present in the forecast profile but absent from the controller's announced-start set. The controller stopped hot units before the scale, then could not restart them before the burst.

**How to apply:** When deriving forecast announcement times, future preload candidates, or restart-window stop vetoes, include `SCALE` alongside `STARTING` and `RUNNING`. Preserve job-level deduplication so a scale event replaces a job's target rather than adding a duplicate workload.