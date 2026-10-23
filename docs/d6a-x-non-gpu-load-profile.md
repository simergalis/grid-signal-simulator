# D6a-X: additive measured non-GPU IT load

This document records the approved, narrowly scoped D6a-X extension from
DR-2026-10-20-ISLAND-COLLAPSE. The field is additive and defaults to absent;
an absent or empty profile preserves existing scenario behavior. The profile
is a sequence of `[sim_time_seconds, MW]` points with strictly increasing
times and finite, non-negative values. Load is zero before the first point and
is held constant until the next point and after the final point.

At each tick the simulator adds the profile value once to existing GPU compute
demand, then adds the existing cooling demand. The profile represents measured
non-GPU IT load, so the existing cooling model receives it as IT load; it does
not alter GPU job events, GPU workload multipliers, or the queue-derived
forecast (`core/simulation_core.py:3142–3163`). When workload signals are absent,
the existing confidence fallback uses measured total demand, so it sees only
the current CPU load, not the profile's future points. Existing served/unserved
and physical-balance accounting therefore treat it as ordinary demand.

The tick telemetry field is `p_non_gpu_demand_mw`. API/WebSocket and persisted
tick telemetry omit it when the profile is absent. Internally the absent
profile remains `None`; the physical identity serializer omits that sentinel,
so legacy physical hashes remain unchanged. Configured profiles contribute
their numeric value, including explicit zeroes, to the physical identity.

Scenario configuration is readable through the existing scenario JSON/API
representation. The frontend currently receives the telemetry type but has no
dedicated scenario-detail display for this new series; a UI editor or chart is
out of scope.

Approval: Lloyd authorized the additive field and its single demand-entry
point under the D6a-X instruction. The CPU-profile candidate that follows is
still generated only under `tools/dr_isl/d6/`; this change does not edit the
seeded S10 scenario.
