---
name: Live Slurm ingestion
description: Compatibility and safety contract for external slurmrestd snapshots entering a live GridSignal run.
---

External Slurm snapshots are state-aware: `PENDING` uses requested TRES (and may report zero allocated nodes, so chassis count is derived from requested GPUs), `RUNNING` uses allocated TRES, and terminal states should try allocation then request metadata. A state-specific stable event identity is retry-safe, but per-job lifecycle ordering must reject late state regressions so a delayed running snapshot cannot revive a terminal job.

**Why:** slurmrestd drops or zeroes allocation information before placement and after deallocation. Treating one TRES field as universally authoritative silently rejects real queue/terminal notifications. Poll responses may also arrive out of order.

**How to apply:** retain the required H100 chassis topology check whenever an allocation or request creates load, keep injection authenticated, and test both a live next-tick load increase and terminal load removal when changing this adapter or supporting another Slurm GPU profile.