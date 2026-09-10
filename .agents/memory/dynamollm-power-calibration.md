---
name: DynamoLLM power calibration
description: Durable calibration boundary for H100 chassis power and inference model sensitivity.
---

The simulator treats 10.2 kW for an 8-GPU H100/Hopper chassis as a conservative
full-node envelope, equal to 1.275 kW/GPU and inclusive of non-GPU overhead.
The existing enterprise_8gpu_air identifier remains a compatibility alias for
the canonical hopper_8gpu_air profile.

**Why:** DynamoLLM HPCA 2025 Figure 8 shows approximately 250–800 W/GPU and
approximately 18–56 kW cluster power across P50/P90/P99 evaluated operating
points. Those measurements support dynamic workload sensitivity but do not
replace a chassis/nameplate envelope or justify a flat 300 W/GPU assumption.

**How to apply:** Apply DynamoLLM Table III model factors only once in the
shared GPUModule current/target power path, and only for explicit inference
signals with recognized model ids. Keep training, checkpointing, other, and
unknown models at the hardware-only factor until measured data exists.