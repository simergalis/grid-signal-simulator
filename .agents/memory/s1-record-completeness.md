---
name: S1 record completeness
description: How bounded seven-day study records must be interpreted during replay.
---

Bounded operational lists are evidence-bearing only when they carry an explicit truncation marker and omission count. A list shorter than its writer cap without a marker is a recording defect, not safe clipping.

**Why:** The H-2 baseline start list had 30 entries with no marker while telemetry measured 71 start/release events; treating the visible list as complete caused a false reconciliation failure and hid the source defect.

**How to apply:** Metrics should use tick telemetry for complete re-emitted calculations, mark bounded commitment/refusal counts as incomplete, and preserve any original guard failure rather than synthesizing controller events as a pass.