---
name: Additive load validation
description: How to add deterministic site-level demand to a scenario that uses Kubernetes demand agents.
---

Use tenant workload bursts when a Kubernetes-backed scenario needs a
deterministic additive site-load injection. Scripted workload events are not a
reliable additive mechanism alongside the Kubernetes controller because its
managed workload state can supersede the scripted job.

**Why:** A validation surge must remain present in the actual power trace; a
declared event that is silently displaced cannot demonstrate a source-handoff
or PCC-cap behavior.

**How to apply:** Size the overlapping tenant bursts against the expected base
load, keep each burst within the per-tenant validation limit, and replay the
target simulation window before relying on it as a dispatch test.