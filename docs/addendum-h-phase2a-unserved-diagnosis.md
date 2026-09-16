# Addendum H Phase 2a — Unserved-energy diagnosis

## Scope and reproduction

This is a read-only diagnosis of the existing Phase 2a smoke fixture before
the controller changes. The fixture is the temporary derivative of
`config/scenarios/scenario-uneven-multisched-01.json` used by TC-102:

- 7,200 simulated seconds.
- Four `gt_mode="aero"` turbines.
- Three initially synchronized turbines and one hot standby.
- Minimum run/down timers disabled, as in the existing fixture.
- `kube_clusters` and `slurm_config` removed so the run is headless and
  deterministic.
- The workload remains the scripted scheduler-shaped GPU workload demand.

The existing 5-second physics tick was used. The two modes were run
independently from the same fixture. Unserved energy was integrated as
`max(p_unserved_mw, 0) × 5 / 3600`.

The complete machine-readable per-tick capture from this reproduction is
preserved in
`docs/addendum-h-phase2a-unserved-timeline.json`. It contains both the
baseline and informed arrays, including every per-tick row. Each row contains:

```text
sim_time_s,
compute_demand_mw,
cooling_demand_mw,
total_site_demand_mw,
turbines[{id,state,output_mw,rated_mw}],
synchronized_capacity_mw,
bess_output_mw,
bess_soc_fraction,
bess_power_limit_mw,
bess_available_bridging_mw,
bess_anchor_reserve_mw,
unserved_mw
```

The rows below summarize every contiguous interval containing an unserved
tick. The companion JSON is the per-tick source for all values; no ticks with
positive `p_unserved_mw` were omitted.

## Results

| Mode | Positive-unserved ticks | Unserved energy |
|---|---:|---:|
| Baseline | 52 | 0.475991 MWh |
| Informed | 128 | 0.998980 MWh |

### Baseline intervals

| Interval (s) | Peak site demand (MW) | Peak unserved (MW) | Cause summary |
|---:|---:|---:|---|
| 335–365 | 98.993780 | 25.000000 | Burst onset while three turbines ramp; fourth unit is offline/starting |
| 420–610 | 116.096603 | 12.096603 | Sustained 90 MW compute burst plus cooling exceeds 3-unit capacity plus BESS above anchor |
| 1855–1880 | 83.995470 | 14.995470 | Later burst onset while the fourth unit is not yet synchronized |

### Informed intervals

| Interval (s) | Peak site demand (MW) | Peak unserved (MW) | Cause summary |
|---:|---:|---:|---|
| 335–365 | 98.993780 | 19.160560 | Burst onset during controller start/ramp |
| 380–395 | 98.993823 | 8.750000 | Fourth unit is still starting |
| 420–610 | 116.096603 | 12.096603 | Same sustained capacity limit as baseline |
| 990 | 35.993556 | 8.750000 | Controller has reduced synchronized output while a unit is starting |
| 1855–1880 | 83.995470 | 14.995470 | Fourth unit is not yet synchronized at burst onset |
| 1920–2235 | 83.995470 | 15.000000 | Stop/start sequencing leaves insufficient synchronized output |
| 2770–2775 | 59.999766 | 8.750000 | A unit is starting while the demand is above remaining ramped output |
| 3075–3085 | 59.999766 | 4.000234 | Start/ramp transition |
| 3150–3155 | 59.999766 | 8.750000 | Start/ramp transition |

## Burst-capacity diagnosis

The largest scripted burst has approximately:

```text
compute:  89.994396 MW
cooling:  26.102207 MW
total:   116.096603 MW
```

With three synchronized 25 MW turbines and the 30 MW BESS:

```text
synced turbine nameplate: 75 MW
BESS power limit:         30 MW
anchor reserve:            1 MW
BESS allowance:           29 MW
available total:         104 MW
shortfall at peak:        12.096603 MW
```

Therefore, yes: the cooling demand added on top of the approximately 90 MW
compute burst pushes the site above `75 MW + 29 MW`. The observed peak
shortfall is approximately 12.10 MW even after the three turbines are at
nameplate and the BESS is at its 29 MW allowance.

The same fixture also reaches:

| Scripted demand phase | Compute peak (MW) | Cooling peak (MW) | Total peak (MW) |
|---|---:|---:|---:|
| Initial H100 burst | 89.994396 | 26.102207 | 116.096603 |
| Tail of initial burst | 89.994396 | 17.998243 | 107.992639 |
| Later burst | 83.995470 | 0.000000 | 83.995470 |
| Post-release demand | 59.999766 | 0.000000 | 59.999766 |

## Transient versus sustained behavior

The unserved energy has both causes:

1. **Transient ramp limitation.** At burst onset, synchronized turbines are
   at minimum stable output or are still ramping, and a starting unit has
   zero synchronized output. This produces the early spikes, including the
   25 MW baseline peak at 340 seconds.
2. **Sustained capacity limitation.** During the main burst, the demand
   remains above the 104 MW capacity of three synchronized turbines plus the
   BESS allowance. The deficit persists while the fourth turbine is not yet
   synchronized. At the 116.096603 MW peak, the structural gap is
   12.096603 MW.

This is not only a short-lived controller or forecast artifact. The main
burst contains a capacity-limited component.

## Could the current fleet serve the burst without look-ahead?

### Three synchronized turbines plus the 30 MW BESS

No. Even at full turbine output, the maximum is 104 MW after preserving the
1 MW anchor reserve. The minimum change for the steady-state peak is either:

- synchronize a fourth 25 MW turbine; or
- increase BESS rated power from 30 MW to at least
  `42.096603 MW` while retaining the 1 MW reserve.

The latter is a minimum increase of approximately 12.096603 MW of BESS
inverter power, ignoring any additional ramp-onset margin.

### Four synchronized turbines plus the 30 MW BESS

Four fully producing turbines plus the BESS allowance provide:

```text
100 MW + 29 MW = 129 MW
```

which covers the 116.096603 MW steady-state peak. However, four units
initially held at their 35% minimum stable output provide only 35 MW before
their governors ramp. With the current BESS, that configuration can still
have onset shortfall. The cleanest minimum change for zero unserved energy
in this fixture is to pre-load the synchronized units before the burst,
rather than relying on no-forecast startup/ramp response.

If no pre-loading is allowed and the turbines contribute only their minimum
stable output at the burst instant, the BESS would need approximately:

```text
116.096603 - 35.0 + 1.0 = 82.096603 MW rated power
```

to cover the instantaneous peak while preserving the 1 MW anchor reserve.
That is a power-sizing bound, not a recommendation to change the
zero-unserved acceptance rule.

## Conclusion

The existing smoke failures are explained by a combination of turbine ramp
transients and a real three-unit steady-state capacity deficit caused by
cooling. This diagnosis does not change the zero-unserved acceptance rule.
The controller and fixture changes are evaluated separately after this
report.