# D6b status — stopped at D6b.2

Base HEAD at inspection: `03476900f0bf1813f6e459c54e75c21946e019bc`.

## D6b.1 decision

**LEGITIMATE THRESHOLD EFFECT**, accepted per Lloyd's ruling dated 2026-10-24. In
`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/commitment.py:360–369`,
the reserve-floor decommit check compares `remaining_total >= floor_without`.
With one unit remaining, this permits decommit only when turbine-side demand is
exactly zero. At tick 6580, the CPU load makes demand approximately
`9.5e-5 MW`, so the comparison blocks decommit. Commitment logic is unchanged;
changing it is deferred.

## D6b.2 stop

S10 is not yet added to the MCP allowlist. The current allowlist is
`mcp_server/server.py:60–69`; scenario listing resolves a study class at
`:330–343`, and `start_run` first expands the spec at `:457–459` and creates
the run identity at `:465–473`.

The available study classes are limited by
`study_harness/executor.py:72–80` to the four reference scenarios and
`scenario-uneven-multisched-01`. For all other IDs, the function raises
`UnsupportedScenarioError`. The existing expansion path at
`executor.py:282–305` treats every non-Addendum-H ID as the base-demo class and
loads the base-demo JSON, so it cannot safely run S10 by merely adding an
allowlist entry.

No existing study class fits S10. Per the instruction not to invent a
classification, work stopped before editing code or running D6b.3–D6b.5.
