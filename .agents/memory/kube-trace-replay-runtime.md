---
name: Alibaba trace replay runtime
description: Durable input and runtime constraints for replaying Alibaba-style Kubernetes CSV traces.
---

Relative numeric timestamps in the Alibaba pod exports are millisecond offsets from the trace start, while absolute Unix timestamps may use seconds or milliseconds. The replay should expose an override and record the selected policy rather than assuming all numeric timestamps share one epoch format.

**Why:** Treating 12-million-scale relative millisecond values as seconds creates multi-month simulations and invalid queue waits. The same archive uses lifecycle-complete traces alongside resource-only multigpu CSVs, so missing lifecycle columns must be surfaced as an intentional skip.

**How to apply:** Keep `creation_time` as arrival, `deletion_time` as simulated release, and `scheduled_time` as comparison-only data. Deduplicate scheduler-owned wakeups in the replay event heap; otherwise each future trace timestamp can reinsert the same wakeup and make a full trace unnecessarily superlinear.