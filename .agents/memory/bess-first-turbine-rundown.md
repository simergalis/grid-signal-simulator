---
name: BESS-first turbine rundown
description: Rules for safely reducing turbine commitment after a demand drop and BESS charging.
---

Turbine decommit hysteresis may begin only when the remaining physical BESS charge acceptance cannot absorb the turbine surplus. An inverter's transient response lag is not charge saturation and must not initiate a shutdown.

**Why:** A lagged inverter can briefly report less charging than commanded while still having sufficient SoC and power headroom. Treating that moment as saturation causes premature turbine rundown and avoidable oscillation.

**How to apply:** Base the gate on charge power and energy headroom, then preserve the existing confirmation, minimum-run/down, hot-standby, sequential breaker-settling, and N-1 reserve guards. Use raw residual site demand for commitment capacity calculations, and count only units with upward reserve capability—never an unloading unit held at its stable floor.