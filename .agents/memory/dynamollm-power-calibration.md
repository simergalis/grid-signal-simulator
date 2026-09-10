---
name: DynamoLLM power calibration
description: Durable calibration boundary for H100 chassis power and inference model sensitivity.
---

The simulator treats 10.2 kW for an 8-GPU H100/Hopper chassis as a conservative
full-node envelope, equal to 1.275 kW/GPU and inclusive of non-GPU overhead.
The existing enterprise_8gpu_air identifier remains a compatibility alias for
the canonical hopper_8gpu_air profile. Table III energy values are not power
multipliers.

**Why:** DynamoLLM HPCA 2025 Figure 8 shows approximately 250–800 W/GPU and
approximately 18–56 kW cluster power across P50/P90/P99 evaluated operating
points. Table III is Wh/request, so multiplying it into instantaneous kW would
violate hardware power caps. SinglePool TP8 at 1980 MHz is the appropriate
unoptimized baseline; its Llama2-70B value is the reference model.

**How to apply:** Apply the SinglePool model ratio to generated inference job
duration, with Llama2-70B as the 1.0 default reference. Keep GPUModule current
and target power at the hardware profile's rated draw; never multiply node
power by model energy. Scripted events with explicit JOB_END timestamps remain
authoritative.