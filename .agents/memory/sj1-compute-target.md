---
name: SJ-1 compute target
description: The requested IT-power target and hardware sizing convention for the Equinix SJ-1 mixed scheduler fleet.
---

# SJ-1 Compute Target

The SJ-1 fleet is defined as 708 H100 nodes in Kubernetes, 708 H100 nodes in Slurm, and 21 GB200 NVL72 racks in Ray. The GB200 rack profile is 120 kW. Its raw IT capacity is 16.9632 MW and is intentionally displayed as the §2 **17.0 MW IT compute target** after normal one-decimal rounding.

**Why:** The scenario must retain the requested heterogeneous fleet and use the existing §2 17.0 MW target, rather than inventing an additional capacity figure. The PUE multiplier represents site demand above the IT figure and must not redefine that target.

**How to apply:** When changing SJ-1 cluster counts or hardware profiles, recalculate the raw IT sum, preserve its 17.0 MW one-decimal target where appropriate, and keep the backend profile catalogue, workload estimation mirror, UI profile label, and regression coverage aligned.

## Job-cap convention

SJ-1 uses per-cluster generator caps rather than the legacy `max_nodes / 2` rule: 300 units for each H100 cluster and a 42-rack policy ceiling for the GB200 cluster. A policy cap never overrides actual cluster capacity, so Ray remains hard-bounded by its 21 installed racks.

**Why:** A single global unit cap has no stable physical meaning across H100 nodes and GB200 racks, and would permit unrealistic allocations in the smaller Ray fleet.

**How to apply:** Keep job-cap configuration local to each scheduler cluster; preserve the legacy half-fleet fallback when no explicit cap is declared. Validate the policy cap is not below the minimum job size, and enforce the lesser of policy and fleet capacity when generating a job.