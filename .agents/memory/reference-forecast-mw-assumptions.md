---
name: Reference forecast MW assumptions
description: Assumptions attached to raw reference forecast counts when exposing derived MW values.
---

The reference forecast's derived MW values use the existing catalog profiles `enterprise_8gpu_air` for Kubernetes and Slurm and `nextgen_rack_liquid` for Ray, with the generic PARAM-06 PUE default rather than an SJ-2 calibration.

The same resolved profiles provide GPU counts: 8 GPUs per Kubernetes/Slurm chassis and 72 GPUs per Ray rack; GPU totals do not use PUE.

**Why:** The source labels are workload-unit descriptions, not exact profile IDs, and no SJ-2-specific PUE calibration exists.

**How to apply:** Preserve raw counts alongside derived values and expose the profile mapping and generic-PUE assumption in any consuming API response; do not silently present the result as site-calibrated.