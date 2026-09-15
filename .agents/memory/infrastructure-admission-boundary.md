---
name: infrastructure-admission-boundary
description: Durable boundary between Phase 2 infrastructure admission and later Kubernetes/Ray runtime behavior.
---

Infrastructure admission must grant or reject a complete Ray-sized allocation before any Pod placement or Ray process work. Kubernetes admission owns provider queueing, quotas, budgets, priority, gang atomicity, delay, and optional preemption; the ordinary Kubernetes scheduler remains a separate placement engine. Slurm admission should expose the existing partition/QOS/reservation/GRES queue through the same allocation-result contract rather than replacing it.

**Why:** Treating Pod placement or Ray task scheduling as admission would conflate independent control planes and make capacity budgets impossible to audit.

**How to apply:** Later Ray lifecycle work consumes an admitted `InfrastructureAllocation`; it must not silently bypass the admission engine or reinterpret raw Pod placement as batch admission.