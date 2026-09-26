---
name: Full-matrix GPU timeout
description: Runtime limit needed when executing the per-file regression matrix.
---

The GPU load-profile node can take slightly more than the historical 300-second per-batch harness timeout, and a full-suite phase-3 mismatch may not reproduce when run alone. Preserve the exact pytest flags and seed; rerun the isolated node before classifying a suite-only failure.

**Why:** The test polls a live max-speed simulator run through three simulated load-profile phases. A full-suite phase-3 fraction mismatch passed on an isolated rerun on 2026-09-26, so elapsed time and suite context can affect the observed result.

**How to apply:** If the per-file or full-suite run times out or reports a phase mismatch for `test_gpu_load_profile`, rerun that exact node with a longer timeout before attributing it to a code change.