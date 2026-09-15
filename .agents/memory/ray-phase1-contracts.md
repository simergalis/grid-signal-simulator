---
name: Ray Phase 1 contracts
description: Phase 1 establishes nested Ray identity and resource ownership without runtime scheduling.
---

Ray is represented as an application scheduler nested inside exactly one
Kubernetes or Slurm infrastructure allocation. Phase 1 only defines typed
resource and parent-child contracts, compatibility metadata, and
double-counting validation; it must not be treated as Ray lifecycle,
autoscaling, or task scheduling support.

**Why:** Treating Ray as a peer `scheduler_type` loses the infrastructure-versus
application boundary and can count the same capacity twice.

**How to apply:** Later Ray runtime work must bind one cluster to one
infrastructure allocation, validate cluster/workload capacity before scheduling,
and preserve legacy signals that carry no nested IDs.