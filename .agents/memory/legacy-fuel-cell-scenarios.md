---
name: Legacy fuel-cell scenario representation
description: Governing decision for the eleven aggregate fuel-cell scenarios and future migration attempts.
---

Keep all eleven existing legacy aggregate fuel-cell scenarios on the aggregate path. Do not add inferred block assignments or an aggregate-compatibility mode unless the user explicitly revisits this decision.

**Why:** Exhaustive before/after replay found no block-addressable translation that preserved output, commitment, reserve, contingency, BESS behavior, and alerts. The aggregate source also does not determine running/hot/cold standby splits for multi-stack scenarios.

**How to apply:** Treat representation migration as behavior-preserving data work. Never update expected values to bless block-model differences. Leave the aggregate runtime path operational and use block-addressable configuration only for scenarios authored with explicit block semantics.

For a running 2 MW single-block array, both models recognize the 0.5 minimum-stable fraction as a 1 MW floor. The material first-tick difference is output ramping: the aggregate model advances from 1.0 to 1.1 MW at its 0.02 MW/s ramp, while the block model can move directly to its 2 MW command.

**Why:** The resulting 0.9 MW residual-demand difference changes BESS endurance disproportionately when the remaining gap is only about 2–3 MW. Removing the stable floor would address the wrong mechanism.

**How to apply:** When reviewing genuinely small block arrays, decide and test the intended initial operating point and MW output-ramp behavior separately from minimum stable output and block commitment rate.