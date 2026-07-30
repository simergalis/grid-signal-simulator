---
name: sim_time labeling convention
description: sim_time is interval-START; TickResult quantities describe state at sim_time+dt. Step 8 plot/attribution code must use one convention consistently.
---

## Rule

`sim_time` on every `TickResult` and in every `SimClock` is the **START** of the
5-second interval: `[sim_time, sim_time + dt_seconds)`.

RunContext.step() sets `clock.sim_time = self.sim_time` BEFORE calling
`evaluate_tick()`, then does `self.sim_time += dt` AFTER.  Inside `evaluate_tick()`,
asset `advance()` calls run BEFORE any reading is taken.  So every quantity in
TickResult (power MW, SoC, dt_lead_next_s, bess_bridging_seconds, …) reflects the
physical state at `sim_time + dt_seconds` — the END of the interval.

Concretely: tick_index=1, sim_time=0.0 describes state after the first 5 simulated
seconds.  `dt_lead_next_s = 40.0` means 40 s of ramp remain **at t=5 s**, not t=0 s.

## Chosen convention: (A) interval-start labeling

Plot and store at x = sim_time (not sim_time + dt).  This is what the current code
does.  The first point appears at x=0 but physically represents t=5 s state.

**Why:** Simple; matches the persisted field value with no transformation needed.

**How to apply:** Attribution code in Step 8 and later steps must use the same
convention for both storage and queries.  Never mix (A) for storage with (B)
`sim_time + dt` for attribution — the result is a 5-second misalignment on every
forecast comparison.

The only semantic trap: `sim_time=0.0` does NOT mean "no time has elapsed yet."

## Documentation location

Full explanation added to `SimClock` class docstring in `core/sim_clock.py`
("sim_time labeling convention — INTERVAL-START" section).
