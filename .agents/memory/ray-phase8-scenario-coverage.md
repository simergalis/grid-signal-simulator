---
name: Ray Phase 8 scenario coverage
description: Durable end-to-end scenarios covering the Ray control and physical planes.
---

Scenario coverage should exercise the complete Ray path without introducing a
second runtime implementation: KubeRay burst demand scales through admission,
measured power is enforced and observed, stale external data is visible, and
Slurm-backed clusters remain fixed.

**Why:** Unit tests can validate each boundary while still missing regressions
in the handoffs between lifecycle, scheduling, autoscaling, ingestion,
enforcement, and observability.

**How to apply:** Keep scenarios deterministic, assert cross-layer outcomes,
and use the scenario matrix as regression coverage whenever a Ray phase changes.