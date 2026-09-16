---
name: Phase 2a test harness
description: Correct working directory and known unrelated suite blockers for simulator validation.
---

Run simulator tests from the gridsignal package directory so `core` and `runtime` resolve. Running pytest from the outer build-package directory also collects audit_tests, which require a different import path.

**Why:** The outer invocation failed during audit-test collection, while the package-root invocation reached the simulator suite and exposed unrelated pre-existing failures before completing.

**How to apply:** Use targeted Phase 2a/operator tests from the build-package root or run the broader suite from `.../gridsignal_sim_v2/gridsignal_sim`; classify D4/TC-89/FC100 failures against baseline before changing Phase 2a code.