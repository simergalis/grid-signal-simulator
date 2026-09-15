---
name: Ray Phase 4 execution scheduling
description: Durable boundaries for logical Ray workload scheduling after cluster readiness.
---

Ray execution scheduling begins only after the Phase 3 lifecycle reports READY. It
accounts for logical head/worker slots and placement-group bundle reservations,
while physical allocation, hard enforcement, power, autoscaling, and host
execution remain outside this phase. A workload keeps its requested cluster
identity during opt-in spillback; placement_cluster_id records where it actually
runs.

**Why:** Treating a Ray placement-group reservation as additional workload
capacity would double-count resources, and bypassing READY would let execution
race infrastructure startup.

**How to apply:** New scheduler behavior should use logical resources only,
release assignments before retrying, require bounded retries, and preserve the
requested-versus-actual cluster distinction in events and status.