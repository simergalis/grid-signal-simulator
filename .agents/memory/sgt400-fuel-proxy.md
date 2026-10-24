---
name: SGT-400 fuel proxy
description: Approved S10 turbine heat-rate proxy and its remaining equipment uncertainty.
---

For the S10 candidate, use the Siemens SGT-400 brochure row: 10,103 kJ/kWh at 14.3 MW(e), not the SGT-600 row's 10,720 kJ/kWh. Label the heat-rate basis `ASSUMED LHV, PROPOSED_HERE`; the brochure does not state the basis, and S10's installed turbine model is unknown.

**Why:** the user selected the SGT-400 value after identifying that 10,720 kJ/kWh belongs to the SGT-600 row. The proxy must not imply that S10's actual equipment has been identified.

**How to apply:** keep the proxy and its uncertainty explicit in generator-produced S10-derived candidates and accounting. Do not edit the tracked S10 scenario or template to apply it.
