---
name: Alert clustering and dispositions
description: Alert clustering must remain proposal-only; durable per-instance dispositions carry reviewer, freshness, batch, and proposal-reason fields.
---

Cluster proposals never replace or mutate alert instances. Bulk disposition is a separate explicit path gated by catalogue policy and fresh telemetry for every member; each member receives its own durable audit row sharing one batch reference.

**Why:** Operators need to preserve hard-alert accountability while still reviewing repeated low-impact conditions efficiently.

**How to apply:** Extend the existing alert-review path for proposals, keep individual controls visible, and treat catalogue policy as the only source for bulk eligibility and clustering thresholds.