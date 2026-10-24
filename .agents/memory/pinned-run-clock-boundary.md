---
name: Pinned run clock boundary
description: Why deterministic headless simulation runs must pin the wall clock before building context, not only during execution.
---

For a pinned simulator replay, freeze wall time before seed resolution and run-context construction, and keep it fixed through `RunManager` execution and result serialization. Pinning only the drive loop leaves build-time timestamps and any time-derived initialization dependent on the real clock.

**Why:** an early replay attempt pinned the run but let the factory read the live clock; its results therefore did not satisfy the same reproducibility contract as the baseline runner.

**How to apply:** place the clock patch around the complete build → run → serialize boundary, alongside the recorded root seed and deterministic consumer seeds.
