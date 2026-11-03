---
name: Physical hash comparisons
description: Rules for interpreting deterministic before/after simulation hash gates.
---

Compare physical hashes only when both runs use the same input normalization, seed pinning, clock pinning, execution path, and hasher. A match in peak demand or unserved energy does not establish tick-level hash equivalence; if hashes differ, stop at the gate and report the mismatch without guessing at its cause.

**Why:** a recent Proxim8 queue-stress verification produced identical headline demand metrics but different full-run physical hashes against the recorded pre-change values, and the reason was not established.

**How to apply:** reproduce the saved baseline procedure exactly before interpreting any physical-hash delta; do not continue past a required equality gate until the discrepancy is resolved.
