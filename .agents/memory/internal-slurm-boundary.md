---
name: Internal Slurm scheduler boundary
description: Durable separation between simulated Slurm control and external Slurm state ingestion.
---

The internal Slurm scheduler is opt-in through `slurm_config` and remains separate from the live Slurm snapshot adapter. Both paths bridge into the scheduler-agnostic `WorkloadSignal` contract, while the internal path owns deterministic queue ordering, dependencies, reservations, resource allocation, completion, and cancellation.

**Why:** Existing Slurm ingestion represents an external scheduler's authoritative state. Replacing it with internal decisions would change legacy replay semantics and could let external snapshots fight the simulated queue.

**How to apply:** Keep new internal scheduling features behind `slurm_config`; preserve the snapshot endpoint for external-state ingestion. Treat job commands and environments as metadata only unless a separate sandboxed execution design is explicitly approved.