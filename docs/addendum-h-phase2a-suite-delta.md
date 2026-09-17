# Addendum H Phase 2a suite delta

Date: 2026-09-17

This is a read-only comparison of the prior full-suite totals
(`2,068 collected / 1,977 passed / 65 failed / 3 skipped / 23 xfailed`)
with the committed cleanup run and the IMPL-H56/H57 repair. The final clean
rerun totals are `2,079 collected / 1,988 passed / 65 failed / 3 skipped /
23 xfailed`.

The apparent pass-count contradiction in the pre-repair comparison resolves as
follows:

- Eleven new test nodes were added, TC-126 through TC-136, and all eleven
  passed.
- Ten previously passing nodes became failures before this repair.
- One previously passing node became skipped before this repair.
- The remaining historical outcomes did not change.

The four added nodes before TC-130 are:

| Test | Result |
| --- | --- |
| `test_tc126_low_forecast_allows_stop_when_remaining_msl_exceeds_demand` | passed |
| `test_tc127_informed_decommit_veto_repeats_are_counted_not_relogged` | passed |
| `test_tc128_dispatch_curtailment_closes_islanded_physical_balance` | passed |
| `test_tc129_direct_tick_wire_contains_on_bus_count_and_dispatch_curtailment` | passed |

TC-130 through TC-136 also passed. The current per-test manifest is
`docs/addendum-h-phase2a-full-suite-outcomes.md`.

## Pre-repair outcome changes

The first failure line below is copied from the current outcome record. The
historical outcome for each row was `passed`.

| Test node | Old | New | First line of current failure | Addendum H path touch since `1c333d3` |
| --- | --- | --- | --- | --- |
| `tests/test_13_3_frequency.py::TestI1FrequencyDeviationVisible::test_I1_islanded_surplus_raises_frequency` | passed | failed | `AssertionError: I1: frequency_forcing_mw must be ≈ 1.0 MW with 1 MW solar surplus; got 0.000000 MW` | **Yes.** `72aa49a` changed the positive-residual path in `core/simulation_core.py:2898-2911,3360-3369` and the balance ledger in `core/power_balance.py:35-52,145-165`. |
| `tests/test_13_3_frequency.py::TestI2SwingEquationAccuracy::test_I2_explicit_formula_fixture` | passed | failed | `AssertionError: I2 precondition: frequency_forcing_mw should be ~1 MW; got 0.000000` | **Yes.** Same explicit dispatch-curtailment change: `core/simulation_core.py:2898-2911,3360-3369`; `core/power_balance.py:35-52,145-165`. |
| `tests/test_bess_surplus_absorption.py::TestSurplusAbsorption::test_TC_SURP_4_partial_absorption_when_rated_mw_limits` | passed | failed | `AssertionError: TC-SURP-4: un-absorbed surplus must appear in frequency_forcing_mw; got 0.0000` | **Yes.** Same positive-residual/frequency path in `core/simulation_core.py:2898-2911,3360-3369`. |
| `tests/test_bess_surplus_absorption.py::TestSurplusAbsorption::test_TC_SURP_5_absorption_reduces_frequency_forcing` | passed | failed | `AssertionError: TC-SURP-5: BESS absorption must reduce frequency_forcing_mw; absorb=0.0000, full=0.0000` | **Yes.** Same positive-residual/frequency path in `core/simulation_core.py:2898-2911,3360-3369`. |
| `tests/test_cascade_commit.py::test_cascade_commit_sequence` | passed | failed | `httpx.ConnectError: [Errno 111] Connection refused` | **No direct H path.** This is an HTTP/API-server connection failure before the simulator assertion; no Addendum H production line is implicated. |
| `tests/test_diesel_phase3.py::test_live_diesel_output_increases_generation_and_balance_residual` | passed | failed | `assert 0.0 == 3.0 ± 3.0e-06` | **No direct diesel-path touch.** Diesel snapshot/output is read from `core/simulation_core.py:1902-1903`; the H balance change is later at `2898-2911` and does not change diesel dispatch. |
| `tests/test_forecast_path.py::TestDispatchTruthfulness::test_B1b_islanded_load_model_error_not_visible_in_delivery_channel` | passed | failed | `AssertionError: B1b: 1 MW solar surplus should appear in frequency_forcing_mw; got 0.000000000` | **Yes.** The test reaches the changed positive-residual path in `core/simulation_core.py:2898-2911,3360-3369`. |
| `tests/test_forecast_path.py::TestDispatchTruthfulness::test_B5_frequency_tracks_frequency_forcing_mw` | passed | failed | `AssertionError: B5 precondition: frequency_forcing_mw must be ≈ 1.0 MW with 1 MW solar surplus; got 0.000000` | **Yes.** The test reaches the changed positive-residual path in `core/simulation_core.py:2898-2911,3360-3369`. |
| `tests/test_fuel_cell_dispatch.py::test_fuel_cell_dispatch` | passed | failed | `httpx.ConnectError: [Errno 111] Connection refused` | **No direct H path.** This is an HTTP/API-server connection failure before the simulator assertion. |
| `tests/test_gpu_load_profile.py::test_gpu_load_profile` | passed | failed | `httpx.ConnectError: [Errno 111] Connection refused` | **No direct H path.** This is an HTTP/API-server connection failure before the simulator assertion. |

One additional historical outcome changed from pass to skip:

| Test node | Old | New | Current reason |
| --- | --- | --- | --- |
| `tests/test_13_3_frequency.py::TestI2SwingEquationAccuracy::test_I2_single_tick_matches_formula` | passed | skipped | `No frequency forcing — I2 not exercisable` |

The other current skipped nodes were already skipped in the comparison run.

After the repair, the ten pre-repair failures listed above are reduced to the
same 65-failure unrelated baseline, and the skipped I2 node passes.

## IMPL-H56/H57 rerun

The seven Addendum H physics regressions are repaired without weakening or
skipping their assertions:

| Test group | Result |
| --- | --- |
| I1 islanded surplus visibility | passed |
| I2 swing-equation single-tick and explicit-formula checks | passed |
| TC-SURP-4 partial BESS absorption | passed |
| TC-SURP-5 BESS absorption reduces forcing | passed |
| B1b load-model error stays out of delivery error | passed |
| B5 frequency follows forcing | passed |

The diesel balance-residual check also passes after the corrected residual
ordering. The three HTTP-backed checks were rerun with the simulator workflow
available: cascade commit **passed**, fuel-cell dispatch **passed**, and GPU
load profile remained a connection-refusal failure in the full-suite batch.
The GPU test was then rerun alone after the simulator restart and passed
(`1 passed in 301.23s`). The batch-only connection refusal is unrelated to the
Addendum H physics path.

The repair is limited to the positive islanded residual path in
`core/simulation_core.py`: frequency and measured imbalance read the
pre-curtailment residual, while the explicit sink remains in the physical
ledger. `dispatch_curtailment_response_delay_s` is configurable and marked
`PROPOSED_HERE`; the unchanged 5-second smoke fixture completes past the
default 0.5-second response delay.

## Dispatch-curtailment fuel definition

The existing report field
`dispatch_curtailment_fuel_by_component_mmbtu` is **not** fuel attributable
to the curtailed MWh. It is cumulative fuel burned during every interval whose
`p_dispatch_curtailed_mw` is positive:

1. `run_phase2a_smoke.py:153-158` marks an interval active when
   `tick.p_dispatch_curtailed_mw > 1e-9`.
2. `run_phase2a_smoke.py:161-173` computes positive increments of each
   cumulative per-unit fuel component.
3. `run_phase2a_smoke.py:174-177` adds those increments for active intervals.

That definition produces:

| Mode | Dispatch-curtailed energy | Existing “fuel on active ticks” |
| --- | ---: | ---: |
| Baseline | 8.443844163 MWh | 178.581544619 MMBtu |
| Informed | 0.755511020 MWh | 40.997217920 MMBtu |

### Fuel attributable to curtailed energy itself

Because the tick payload has a fleet-level curtailment value rather than a
unit-level curtailed-MW value, the calculation below allocates each tick's
curtailed MW across on-bus turbines in proportion to their operating output.
For each unit and tick:

```text
allocated_curtailed_mw =
    p_dispatch_curtailed_mw
    × unit_output_mw / total_on_bus_turbine_output_mw

attributable_fuel_mmbtu =
    allocated_curtailed_mw
    × (5 seconds / 3600)
    × heat_rate_btu_per_kwh(load_fraction)
    / 1000
```

The operating-point heat-rate calculation is the same curve used by the
physical fuel accumulator at `core/asset_modules.py:1244-1259`; curve
interpolation is defined at `core/models.py:934-942`.

| Mode | Curtailed energy | Attributable load fuel |
| --- | ---: | ---: |
| Baseline | 8.443844163 MWh | **88.769659888 MMBtu** |
| Informed | 0.755511020 MWh | **7.524710956 MMBtu** |

This attributable value excludes synchronized no-load and hot-standby fuel:
it prices only the curtailed energy at each unit's operating-point load heat
rate. The high 178.58 / 41.00 MMBtu figures therefore represent interval fuel
exposure, while 88.77 / 7.52 MMBtu represent the curtailed-energy
attribution under the stated proportional unit allocation.