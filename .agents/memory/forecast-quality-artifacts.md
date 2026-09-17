---
name: Forecast quality artifact coverage
description: How to preserve forecast-error percentiles for long-run stage reports.
---

Forecast-error p90/p99 cannot be reconstructed from the compressed stage tick artifacts because they retain demand and dispatch values but not the controller’s forecast history. Stage runners must calculate and persist the forecast distribution while the controller history is available.

**Why:** A stage report needed exact long-run p90/p99 values, and a rerun was required when the existing artifacts only contained mean, median, p95, min, max, miss count, and miss peak.

**How to apply:** Add requested forecast percentiles to the run-time summary before starting long scenarios; prefer a bounded demand replay for diagnostics and avoid reinjecting the full workload-event stream unless the scenario behavior itself is under test.