---
name: Ray Phase 7 external observability
description: Durable rules for external Ray snapshots and read-only reporting.
---

External Ray snapshots are observation-only and use the shared deduplication and
quarantine pipeline. Ordering is scoped by source and cluster: accepted
snapshots must advance both source sequence and observation time. Observability
reports freshness, workload/worker state, power status, and control-plane event
counts without issuing commands.

**Why:** External APIs can retry or deliver stale data, and observability must
not accidentally become a second scheduling or enforcement path.

**How to apply:** Preserve raw invalid payloads in quarantine, make stale/no-data
states explicit, and keep ingestion, admission, placement, autoscaling, and
power enforcement as separate boundaries.