---
name: Addendum H Phase 2a physics ordering
description: Ordering contract for islanded surplus, frequency forcing, and explicit dispatch curtailment.
---

Islanded `frequency_forcing_mw` and `p_imbalance_mw` must use measured generation minus served load before the explicit dispatch-curtailment sink. The sink remains an explicit physical-ledger term and ramps over the configured `PROPOSED_HERE` response delay; the default delay is below the five-second Phase 2a smoke interval.

**Why:** Subtracting the curtailment sink before frequency evaluation hides same-tick surplus from the swing equation, while removing the sink from the ledger breaks physical balance evidence.

**How to apply:** Keep commitment policy, baseline/informed authority, acceptance comparisons, and alert lifecycle logic separate from this ordering. Any future delay or dump-load change must rerun the I1/I2, TC-SURP-4/5, B1b/B5, smoke, and full-suite checks.