---
name: Alibaba trace replay runtime
description: Durable input and runtime constraints for replaying Alibaba-style Kubernetes CSV traces.
---

Relative numeric timestamps in the Alibaba pod exports are seconds from the trace start. The replay defaults to seconds for numeric relative timestamps; relative millisecond traces must opt into the explicit milliseconds override, while absolute Unix millisecond timestamps remain auto-detectable.

**Why:** Dividing the Alibaba seconds values by 1000 shrinks queue waits by exactly 1000 and hides contention. The same archive uses lifecycle-complete traces alongside resource-only multigpu CSVs, so missing lifecycle columns must still be surfaced as an intentional skip.

**How to apply:** Keep `creation_time` as arrival, `deletion_time` as simulated release, and `scheduled_time` as comparison-only data. Deduplicate scheduler-owned wakeups in the replay event heap; otherwise each future trace timestamp can reinsert the same wakeup and make a full trace unnecessarily superlinear.