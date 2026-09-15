---
name: Scenario seed round-trip buffer
description: The frontend seed round-trip test can exceed Node's synchronous child-process output buffer when seeded Slurm topology is large.
---

The scenario seed round-trip test must account for large serialized seed specs, especially when a Slurm scenario includes many explicit nodes. A default `execFileSync` output buffer can fail with `ENOBUFS` before the UI assertions run.

**Why:** Large persisted topology data is valid simulator input, but it makes the test's Python-to-Node JSON handoff much larger than ordinary scenario fixtures.

**How to apply:** Treat this as a test-harness buffer issue, not a Scheduler Telemetry rendering failure; raise the child-process buffer or reduce the handoff payload when repairing that test.