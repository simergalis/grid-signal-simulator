---
name: Lead-time collection scope
description: Durable boundary for GPU lead-time measurement coverage.
---

The GPU lead-time collection uses only hardware profiles already present in the runtime catalogue and only the workload classes already represented by the scenario wire contract: `training` and `inference`.

**Why:** The current catalogue has no distinct Blackwell Ultra NVL72 or Rubin VR200 NVL72 definitions, and the current workload contract has no `checkpointing` value. Inventing either would make the measurements look more precise than the simulator's supported model.

**How to apply:** Add collection fixtures only for supported profile/class pairs. Report missing hardware profiles and checkpointing as skipped coverage until their definitions are approved and implemented.