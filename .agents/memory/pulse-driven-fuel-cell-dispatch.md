---
name: Pulse-driven fuel-cell dispatch
description: Dispatch rule for islanded fuel-cell sites whose workload is intermittent rather than a continuous baseload.
---

Pulse-only islanded scenarios must explicitly use load-following fuel-cell output; fixed full-nameplate baseload is valid only when a matching continuous load or export/dump path exists. Keep fixed baseload as the default for existing scenarios.

**Why:** A full BESS cannot absorb sustained surplus. A 100 MW fixed fuel-cell target against near-zero idle demand drove the surplus into frequency forcing. Ramp-up also must be fast enough to keep the bridge gap within BESS discharge capacity, while ramp-down must keep shutdown surplus within BESS charge capacity.

**How to apply:** Size scenario-specific fuel-cell rise and fall rates against the largest per-tick workload change and BESS power limit. Validate the complete workload cycle, including pulse shutdown, and require negligible imbalance, nominal frequency, and backup generation remaining off during normal operation.

## Deterministic multi-scheduler staircases

Scripted jobs carrying cluster and scheduler provenance must be aggregated into one persistent allocation per cluster, using STARTING once and SCALE for later level changes.

**Why:** Ending one cohort and starting a replacement at the same timestamp resets GPU startup ramp state. That turns a requested stair-step handoff into a temporary demand collapse and can spuriously start backup generation.

**How to apply:** Author K8S, SLURM, and RAY job cohorts with stable cluster IDs. Apply each timestamp atomically, preserve scheduler metadata, and validate the full staircase for intended compute peaks, negligible imbalance, and backup generation remaining off.