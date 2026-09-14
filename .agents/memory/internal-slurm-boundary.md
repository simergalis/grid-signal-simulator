---
name: Internal Slurm scheduler boundary
description: Durable separation between simulated Slurm control and external Slurm state ingestion.
---

The internal Slurm scheduler is opt-in through `slurm_config` and remains separate from the live Slurm snapshot adapter. Both paths bridge into the scheduler-agnostic `WorkloadSignal` contract, while the internal path owns deterministic queue ordering, dependencies, reservations, resource allocation, completion, and cancellation.

**Why:** Existing Slurm ingestion represents an external scheduler's authoritative state. Replacing it with internal decisions would change legacy replay semantics and could let external snapshots fight the simulated queue.

**How to apply:** Keep new internal scheduling features behind `slurm_config`; preserve the snapshot endpoint for external-state ingestion. Treat job commands and environments as metadata only unless a separate sandboxed execution design is explicitly approved.

The internal path uses an explicit typed compatibility contract for the modeled
Slurm policy surface. Unknown fields in node, job, partition, QOS, account,
license, burst-buffer, federation, and cluster-policy blocks must fail
validation rather than being silently ignored.

**Why:** A permissive config boundary would make an apparently accepted Slurm
option look implemented when the deterministic simulator had not modeled it.

**How to apply:** Add new Slurm options as a deliberate scheduler slice with
schema validation, engine behavior, and focused tests; do not widen the
execution boundary as part of a schema-only change.