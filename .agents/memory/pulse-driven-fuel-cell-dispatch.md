---
name: Pulse-driven fuel-cell dispatch
description: Dispatch rule for islanded fuel-cell sites whose workload is intermittent rather than a continuous baseload.
---

Pulse-only islanded scenarios must explicitly use load-following fuel-cell output; fixed full-nameplate baseload is valid only when a matching continuous load or export/dump path exists. Keep fixed baseload as the default for existing scenarios.

**Why:** A full BESS cannot absorb sustained surplus. A 100 MW fixed fuel-cell target against near-zero idle demand drove the surplus into frequency forcing. Ramp-up also must be fast enough to keep the bridge gap within BESS discharge capacity, while ramp-down must keep shutdown surplus within BESS charge capacity.

**How to apply:** Size scenario-specific fuel-cell rise and fall rates against the largest per-tick workload change and BESS power limit. Validate the complete workload cycle, including pulse shutdown, and require negligible imbalance, nominal frequency, and backup generation remaining off during normal operation.