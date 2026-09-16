# Follow-up #655 — FC100 achieved-output diagnosis

Date: 2026-09-16

## Conclusion

The FC100 expectation is stale. The observed `25.927777... MW` at the
`t=60 s` tick is produced by the current Addendum G-1/G-2 block model's
intrinsic output-ramp behavior. It is not evidence that the fuel-cell
production path is incorrectly applying a fuel-system limit, an apparent-power
limit, or an efficiency multiplier.

The fix belongs in the acceptance test expectation and its explanatory
comments, not in unrelated production code. The strict xfail should be
removed only when that test is deliberately updated to assert the current
specification.

## Exact output path at t=60 s

The FC100 acceptance test runs five-second intervals and reads
`tick.fuel_cell_achieved_output_mw` at `sim_time_seconds == 60` in:

- `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_scenario_fc100_islanded_v2.py:81-86`

The production path is:

1. `core/simulation_core.py:1433-1437` sets the block array's
   load-following target and calls `fuel_cell_module.advance(...)`.
2. `core/simulation_core.py:1438-1441` reads the achieved array output through
   `fuel_cell_module.output_mw()`.
3. `core/fuel_cell_module.py:652-653` returns the sum of each block's
   `output_mw`.
4. `core/fuel_cell_module.py:1022-1043` computes each running block's desired
   output and applies its intrinsic MW/s ramp. The step is limited by:

   ```text
   intrinsic_output_ramp_rate_mw_per_s × productive_seconds_in_interval
   ```

5. `core/simulation_core.py:2690-2697` places that measured fuel-cell output
   into the tick result as `fuel_cell_achieved_output_mw`.

For the seeded FC100 fixture, the relevant inputs are visible in the scenario
record loaded by `build_seeded_store()`:

- `block_rated_mw = 0.325`
- `block_count = 246`
- `initial_running_blocks = 62`
- `initial_hot_standby_blocks = 184`
- `power_factor = 1.0`
- `apparent_power_rating_mva_per_block` omitted, so it defaults to
  `block_rated_mw`
- `fuel_system = None`
- `min_stable_frac = 0.0`

Therefore:

- `core/fuel_cell_module.py:490-494` gives an effective block rating of
  exactly `0.325 MW`; PF handling does not reduce it.
- `core/fuel_cell_module.py:420-427` derives the default intrinsic ramp as
  `0.325 / (3 × 3) = 0.036111111... MW/s`.
- The newly committed blocks do not become full-output blocks immediately.
  They synchronize in successive five-second intervals and earn only the
  productive ramp time available in their interval.

The observed sequence confirms this mechanism:

| Sim time | Running blocks | Achieved output |
|---:|---:|---:|
| 40 s | 67 | 20.150000 MW |
| 45 s | 72 | 21.052778 MW |
| 50 s | 77 | 22.677778 MW |
| 55 s | 82 | 24.302778 MW |
| 60 s | 87 | 25.927778 MW |

At `t=60 s`, 87 blocks are in the `RUNNING` state, but some of the recently
synchronized blocks are still below their `0.325 MW` output ceiling. The
state count is therefore not equivalent to 87 blocks already producing at
nameplate.

## What does not cause the reduction

### Fuel-system physics

The FC100 unit has no authored `fuel_system`. The Addendum G-2 hydraulic path
in `core/fuel_cell_module.py:1065-1070` is therefore not entered. The
pressure, delivered-fuel lag, utilisation clamp, and fuel-supply cap in
`core/fuel_cell_module.py:1072-1211` do not reduce this fixture's output.

### Apparent rating and power factor

`power_factor` is `1.0`, and the omitted apparent rating defaults to
`0.325 MVA` per block. The calculation at
`core/fuel_cell_module.py:490-494` consequently leaves the real block rating
at `0.325 MW`. The observed `0.298 MW` average across the 87 running blocks
is an average over mixed ramp states, not a PF-derived 91.7% rating.

### Heat-rate or efficiency derating

The G-2 heat-rate values affect fuel consumption, not the direct real-power
output calculation in this no-fuel-system fixture. No efficiency multiplier is
applied to the output at the point where `output_mw()` is read.

## Commit and intent

The behavior was introduced in two related Addendum G commits:

- **`f8e0741` — `Implement fuel cell ramp constraints and update associated test suites and schemas`**
  - Added `intrinsic_output_ramp_rate_mw_per_s`.
  - Applied the intrinsic ramp before optional fuel-system constraints.
  - Documented the behavior as a proposed physical block-ramp constraint.
- **`39ade71` — `Update fuel cell ramp logic and simulation schemas`**
  - Changed the default from the three-second first-order initial-slope
    approximation to the approximate three-time-constant settling point:
    `effective_block_rating / (3 × 3 seconds)`.
  - Updated the associated Addendum G-1 test from `2 / 3` to `2 / 9`.

The current implementation comments explicitly state that the intrinsic stack
capability is an engineering placeholder and that optional fuel-system
physics is a separate additional constraint. This is an intentional,
documented model change after the FC100 acceptance expectation was written.

## Specification assessment

Under the current Addendum G-1/G-2 specification, `25.9278 MW` is physically
consistent at `t=60 s`:

- the 87-block count represents committed/running state;
- recently synchronized blocks are still ramping;
- only the achieved block outputs are counted as delivered real power;
- no fuel-system or PF derating is required to explain the result.

The old expectation, `87 × 0.325 = 28.275 MW`, assumes every block reaches
nameplate output at the instant it becomes `RUNNING`. That assumption conflicts
with the current intrinsic-ramp contract.

## Recommendation

Update the FC100 acceptance test to assert the current ramp-limited value,
or—preferably—assert the physical invariant that:

1. running-block count reaches 87 at `t=60 s`;
2. achieved output equals the sum of the individual block outputs;
3. no block exceeds `0.325 MW`;
4. the newly synchronized blocks continue increasing toward nameplate under
   the configured intrinsic ramp;
5. the shortfall is derived from achieved output rather than state count.

The corresponding shortfall expectation should be updated from
`38.3922 MW` to the observed `40.739422... MW` for this tick. Do not change
the production ramp or remove the fuel-cell physics to satisfy the stale
nameplate assertion.