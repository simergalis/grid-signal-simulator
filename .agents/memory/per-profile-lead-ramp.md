---
name: Per-profile lead ramp overrides
description: Compatibility rule for hardware-specific GPU ramp timing in lead-time telemetry.
---

Hardware-specific GPU ramp timing is an optional profile override. A non-null
HardwareProfile ramp value is used for jobs mapped to that profile; profiles
without the override continue using the scenario/module-level timing.

**Why:** Existing catalogue profiles and authored scenarios must retain their
previous ramp behavior while validation scenarios need deliberately different
timings to prove that profile identity is connected to observed lead time.

**How to apply:** Add explicit overrides only to validation or measured
profiles. Do not change the module-level fallback or the 0.95 observation
threshold when adding new profile timing coverage.