---
name: Gridley query catalogue
description: Durable contract for Ask Gridley read-only query matching.
---

Ask Gridley query matching is closed over a versioned catalogue of snapshot-backed entries. The action class is `query`; matched responses include the entry name, source path, units, confidence, and catalogue version. Unknown metrics return `no_match`, name closest tracked entries, and are logged with question and scenario context. Scenario mutation remains a separate `adjust_parameter` path.

**Why:** A silent Energy Flow fallback can make an unrelated operator question look authoritative and is unsafe for a grounded simulator assistant.

**How to apply:** Add new read-only metrics to the declared catalogue and snapshot contract together; do not add ad hoc fallback branches or place matching/AI work in the physics tick loop.