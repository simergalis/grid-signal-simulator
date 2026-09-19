---
name: Phase 2b baseline reconciliation
description: Long-horizon baseline Slurm replays can expose production/cascade turbine starts outside the commitment controller log.
---

The unchanged Phase 2b acceptance rule treats a baseline run as invalid when
actual turbine start counters exceed controller-log start counters. In the
seven-day Slurm reference, this surfaced as production/cascade starts marked
as an untracked path; informed mode reconciled cleanly.

**Why:** The baseline is intentionally measured-core-only, so forcing these
records into the informed controller log would change the policy boundary and
could hide a real auditability defect.

**How to apply:** Preserve the hard failure and report the reconciliation
evidence unless the acceptance/policy owner explicitly authorizes a separate
logging-path change.