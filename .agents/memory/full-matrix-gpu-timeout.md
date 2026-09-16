---
name: Full-matrix GPU timeout
description: Runtime limit needed when executing the per-file regression matrix.
---

The GPU load-profile test can pass while taking slightly more than the historical 300-second per-batch harness timeout. Keep the exact pytest flags and seed, but allow a longer timeout for that split node so it is not reported as an abandoned test.

**Why:** The test polls a live max-speed simulator run through three simulated load-profile phases; observed runtime was about 301 seconds even though all assertions passed.

**How to apply:** If the per-file runner times out on `test_gpu_load_profile`, split it to the individual node and rerun with a longer harness timeout. Treat the result as a test-runner timeout unless the node reports an assertion failure.