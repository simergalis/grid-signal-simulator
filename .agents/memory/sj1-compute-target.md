---
name: SJ-1 compute target
description: The requested IT-power target and hardware sizing convention for the Equinix SJ-1 mixed scheduler fleet.
---

# SJ-1 Compute Target

The SJ-1 fleet is defined as 708 H100 nodes in Kubernetes, 708 H100 nodes in Slurm, and 21 GB200 NVL72 racks in Ray. The GB200 rack profile is 120 kW. Its raw IT capacity is 16.9632 MW and is intentionally displayed as the §2 **17.0 MW IT compute target** after normal one-decimal rounding.

**Why:** The scenario must retain the requested heterogeneous fleet and use the existing §2 17.0 MW target, rather than inventing an additional capacity figure. The PUE multiplier represents site demand above the IT figure and must not redefine that target.

**How to apply:** When changing SJ-1 cluster counts or hardware profiles, recalculate the raw IT sum, preserve its 17.0 MW one-decimal target where appropriate, and keep the backend profile catalogue, workload estimation mirror, UI profile label, and regression coverage aligned.