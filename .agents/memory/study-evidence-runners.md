---
name: In-process study evidence
description: Avoid false differences in local MCP and study-harness acceptance runs.
---

When invoking the MCP service in-process, set the working directory to the simulator package root before starting the app. Some catalogue and fabric fixture paths are resolved relative to the process working directory.

For study identity comparisons, construct identities through the same `StudyRunExecutor.run_pair` path and typed expanded specs used by the real run. Hand-reconstructing payloads can change JSON numeric types (for example, an integer in place of a float) and create a false digest mismatch.

**Why:** Acceptance tooling produced a fixture-loading failure from the workspace root and a false identity difference from manually reconstructed payload types.

**How to apply:** Before concluding MCP parity or identity drift, match the app's package working directory and reuse its real identity-construction path.
