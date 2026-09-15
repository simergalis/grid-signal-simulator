---
name: Ray Phase 6 power enforcement
description: Durable boundary for applying measured physical power limits to Ray workloads.
---

Power enforcement is a separate physical layer: it consumes measured workload
usage and produces effective usage plus deterministic events. It must not derive
power from logical CPU/GPU requests, resize clusters, admit infrastructure, or
mutate logical placement. Capacity-only mode reports violations without changing
the measured snapshot.

**Why:** Autoscaling and logical scheduling answer different questions from
physical enforcement; combining them makes measured overload look like an
admission or placement decision and hides the actual control boundary.

**How to apply:** Keep measured usage observations explicit, apply per-policy
limits before cluster budgets, order event output deterministically, and keep
all enforcement state local to the physical layer.