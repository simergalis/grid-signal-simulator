---
name: Cooling envelope isolation
description: Prevent scalar cooling samples for an independent IT load from mutating per-job GPU cooling envelopes.
---

The scalar `CoolingModule.record_compute_sample()` path and per-job GPU path share the same envelope map. On a scalar load decrease, the scalar path closes the newest live envelope without distinguishing synthetic scalar envelopes from GPU-job envelopes.

**Why:** In the SuperCloud CPU-load candidate, the non-GPU profile stepped down to zero while GPU workload events were active. The scalar step-down ended a GPU cooling envelope, so GPU cooling and total demand fell substantially despite adding CPU demand.

**How to apply:** Keep independent measured IT loads in isolated cooling state or add source-aware envelope ownership before routing them through the scalar cooling API. Verify that a step-down in one load source cannot close another source's envelope.
