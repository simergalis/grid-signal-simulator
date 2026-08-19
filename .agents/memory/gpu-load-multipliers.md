---
name: gpu-load-multipliers
description: How scenario GPU load profiles represent planned demand peaks above nominal full load.
---

## Rule
Treat a scenario GPU load profile as a non-negative demand multiplier, not a
utilisation percentage capped at 100%. A value of 1.0 is nominal full load;
values above 1.0 represent an intentional GPU over-peak.

**Why:** capping the profile at 1.0 silently converts an authored peak demand
into normal load, so dispatch, reserve behavior, and operator telemetry no
longer represent the scenario the operator selected.

**How to apply:** use a zero-order-hold breakpoint to begin the over-peak
window and a second breakpoint at its intended end to restore the next demand
stage. Keep negative authored values safe by treating them as zero demand.