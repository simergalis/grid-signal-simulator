---
name: ray-cluster-readiness-boundary
description: Durable Phase 3 boundary for Ray cluster startup timing, readiness, and allocation release.
---

Ray cluster startup begins only after infrastructure admission grants the complete allocation. The lifecycle must keep infrastructure admission delay separate from cluster startup delay, expose only registered logical resources as ready, and release the infrastructure allocation on drain, termination, or startup failure. Ray task scheduling, placement groups, and autoscaling are downstream concerns.

**Why:** Conflating queue delay with startup delay or exposing reserved-but-unregistered workers as ready would overstate usable Ray capacity and distort later workload scheduling.

**How to apply:** Phase 4 consumes `READY` cluster status and its registered logical resources; it must not infer readiness from admission alone.