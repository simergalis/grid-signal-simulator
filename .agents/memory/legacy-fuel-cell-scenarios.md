---
name: Legacy fuel-cell scenario representation
description: Governing decision for the eleven aggregate fuel-cell scenarios and future migration attempts.
---

Keep all eleven existing legacy aggregate fuel-cell scenarios on the aggregate path. Do not add inferred block assignments or an aggregate-compatibility mode unless the user explicitly revisits this decision.

**Why:** Exhaustive before/after replay found no block-addressable translation that preserved output, commitment, reserve, contingency, BESS behavior, and alerts. The aggregate source also does not determine running/hot/cold standby splits for multi-stack scenarios.

**How to apply:** Treat representation migration as behavior-preserving data work. Never update expected values to bless block-model differences. Leave the aggregate runtime path operational and use block-addressable configuration only for scenarios authored with explicit block semantics.