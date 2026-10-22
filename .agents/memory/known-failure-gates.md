---
name: Known-failure gates
description: Baseline failing node IDs do not excuse new violations inside the same test.
---

A known failing test is not a blanket waiver. Compare assertion/error signatures
and complete violation lists as well as added/removed failing node IDs.

**Why:** a candidate added an API-to-core import inside an architecture test that
already failed for unrelated imports. The failing node set did not reveal the
additional violation.

**How to apply:** for regression gates with accepted baseline failures, retain
the baseline diagnostics and inspect changed diagnostics on those nodes. A
specific waived intermittent test does not waive other added failures or new
failure modes in already-failing tests.
