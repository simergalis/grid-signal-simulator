# DR-2026-10-20-ISLAND-COLLAPSE — Phase 4 reserve report

Status: COMPLETE; STOP at end of Phase 4. No Phase 5 work.
Base application: ae49aaab89564ccf2ef42d505e021641484d0d3a.
P = attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/.
All numerical results below are copied from the named durable evidence files.

## P1 / design and approved clarifications
```json
{
  "approval": "user answer to scope form",
  "release_readiness": "unit_interlocks before an event",
  "tc18_scope": "allow max(depth,diesel,D2-r); keep other assertions",
  "comments": null,
  "head": "5c8dbf2e899a9be6e9cb31c5ef0eaa9f28e1f027",
  "candidate_restored_from": "69350a319e71e97f136b875b00c4660624aee59a",
  "automatic_checkpoint": "5c8dbf2: documentation/evidence only; not application validation",
  "P1_callback": "shared pure release unit helper, receives the queried arbitrator turbine list (also valid for deepcopies)"
}
```

The existing release function and shared unit-interlock helper are unchanged.
The reserve queries the unit helper before an event; it does not require an active contingency.
The shared eligibility predicate and thermal start timing remain authoritative.
The TC-ISL-18 edit changes only the expected maximum of the three floor terms.
```json
{
  "_release_hot_standby_for_contingency": {
    "ast_identical": true,
    "base_lines": [
      757,
      826
    ],
    "candidate_lines": [
      769,
      838
    ]
  },
  "_releasable_hot_standby_turbines": {
    "ast_identical": true,
    "base_lines": [
      664,
      678
    ],
    "candidate_lines": [
      676,
      690
    ]
  },
  "start_eligibility": {
    "ast_identical": true,
    "base_lines": [
      1057,
      1067
    ],
    "candidate_lines": [
      1057,
      1067
    ]
  }
}
```

```json
{
  "passed": 51,
  "failed": 0,
  "failures": [],
  "tc_isl_01_to_03_cases": 12,
  "warning": "existing synthetic BESS C-rate fixture",
  "application_change": "C2(c) plus approved TC18 floor expectation; release event gates unchanged"
}
```

Focused output and JUnit: phase4/P1_FOCUSED.txt and phase4/P1_FOCUSED.xml.

## P2 / GPU boundary test diagnosis, no GPU code or test changes
```json
{
  "base_context_results": {
    "isolation1": "passed",
    "isolation2": "passed",
    "isolation3": "passed",
    "file": "failed",
    "prefix": "failed"
  },
  "candidate_context_results": {
    "isolation1": "passed",
    "isolation2": "passed",
    "isolation3": "passed",
    "file": "passed",
    "prefix": "passed"
  },
  "common_preceding_order_identical": true,
  "base_cases": 774,
  "candidate_cases": 786,
  "extra_candidate_cases": [
    "tests/test_dr_isl_phase4_reserve.py::test_tc_isl_01_above_capacity_warning_attribution_only",
    "tests/test_dr_isl_phase4_reserve.py::test_tc_isl_01_diesel_wins_unchanged",
    "tests/test_dr_isl_phase4_reserve.py::test_tc_isl_01_hot_standby_release_basis_and_unchanged_interlocks",
    "tests/test_dr_isl_phase4_reserve.py::test_tc_isl_01_min_down_and_inflight_countdown",
    "tests/test_dr_isl_phase4_reserve.py::test_tc_isl_01_no_diesel_positive_floor_and_recorded_basis",
    "tests/test_dr_isl_phase4_reserve.py::test_tc_isl_01_no_restartable_unit_records_zero",
    "tests/test_dr_isl_phase4_reserve.py::test_tc_isl_02_grid_tied_or_nonforming_not_applied[overrides0]",
    "tests/test_dr_isl_phase4_reserve.py::test_tc_isl_02_grid_tied_or_nonforming_not_applied[overrides1]",
    "tests/test_dr_isl_phase4_reserve.py::test_tc_isl_02_live_grid_forming_block_fc_not_applied",
    "tests/test_dr_isl_phase4_reserve.py::test_tc_isl_03_conditional_release_and_unserved[None]",
    "tests/test_dr_isl_phase4_reserve.py::test_tc_isl_03_conditional_release_and_unserved[diesel]",
    "tests/test_dr_isl_phase4_reserve.py::test_tc_isl_03_conditional_release_and_unserved[turbine]"
  ],
  "classification": "pre-existing boundary-sampling/timing failure; reproduced at base in file and preceding order; no candidate regression",
  "mechanism": "profile looked up at interval start; result stamped at interval end; latest-tick polling sometimes observes boundary tick. This is not evidence of a polluted pytest singleton.",
  "shared_runtime_state": "WebSocketHub._latest_ticks snapshot, asynchronously written/read; HTTP poll scheduling determines observed samples",
  "source": {
    "profile_lookup": "core/simulation_core.py:842-859,1233-1235",
    "end_timestamp": "core/simulation_core.py:3822",
    "test_expectation": "tests/test_gpu_load_profile.py:82-89,146-169",
    "shared_snapshot": "runtime/run_manager.py:231-237,263"
  },
  "test_and_application_changes_for_gpu": "NONE",
  "candidate_prefix_added_failures": []
}
```

Detailed source evidence and individual outcomes: phase4/P2_REPORT.md,
phase4/P2_SOURCE_PROOF.json and phase4/P2_{base,candidate}_*.results.json.

## P3 R1 / R2
```json
{
  "demo-islanded-ramp": {
    "base": {
      "repeat_physical_hash_identical": true,
      "ticks": 2160,
      "complete": true,
      "collapse": null,
      "min_soc": 0.0,
      "floor_min_mwh": 0.0,
      "floor_max_mwh": 0.0,
      "first_floor_tick": 771,
      "first_floor_basis": {
        "bess-0": {}
      },
      "first_floor_next120s_min_hz": 56.30124604916138,
      "first_discharge_floor_next120s_min_hz": 56.30124604916138,
      "frequency_min": -127.48961154607643,
      "frequency_max": 60.0,
      "unserved_mwh": 0.7984763561509628,
      "balance_failures": 0,
      "illegal_d2r_discharge_count": 0,
      "first_advisory": {
        "tick": 6,
        "sim_time": 30.0,
        "reason": "turbine_catchup"
      },
      "advisory_before_floor": true,
      "at_60s_after_floor": {
        "frequency_hz": 58.283385777786414,
        "gt_plus_solar_minus_demand_mw": 0.0,
        "bess_output_mw": 0.0
      }
    },
    "candidate": {
      "repeat_physical_hash_identical": true,
      "ticks": 2160,
      "complete": true,
      "collapse": null,
      "min_soc": 0.45166506501035325,
      "floor_min_mwh": 0.0625,
      "floor_max_mwh": 7.5,
      "first_floor_tick": 312,
      "first_floor_basis": {
        "bess-0": {
          "bess_id": "bess-0",
          "floor_mwh": 7.5,
          "depth_reserve_mwh": 0.0,
          "diesel_floor_mwh": 0.0,
          "d2r_term_mwh": 7.5,
          "winning_term": "d2r_bridge",
          "basis": "offline_restart",
          "unit_id": "turbine-4",
          "eligibility_wait_s": 0.0,
          "start_duration_s": 600.0,
          "thermal_state": "cold",
          "eligibility_reason": "eligible"
        }
      },
      "first_floor_next120s_min_hz": 59.98901877366516,
      "first_discharge_floor_next120s_min_hz": 59.98901877366516,
      "frequency_min": -127.48961154607643,
      "frequency_max": 60.0,
      "unserved_mwh": 0.785895723386723,
      "balance_failures": 0,
      "illegal_d2r_discharge_count": 0,
      "first_advisory": {
        "tick": 6,
        "sim_time": 30.0,
        "reason": "turbine_catchup"
      },
      "advisory_before_floor": true,
      "at_60s_after_floor": {
        "frequency_hz": 59.9963608710769,
        "gt_plus_solar_minus_demand_mw": 0.0,
        "bess_output_mw": 0.0
      }
    }
  },
  "S10_mit_supercloud_2021-08-11": {
    "base": {
      "repeat_physical_hash_identical": true,
      "ticks": 17280,
      "complete": true,
      "collapse": null,
      "min_soc": 0.0,
      "floor_min_mwh": 0.0,
      "floor_max_mwh": 0.0,
      "first_floor_tick": 2372,
      "first_floor_basis": {
        "bess-0": {}
      },
      "first_floor_next120s_min_hz": 54.48350997809083,
      "first_discharge_floor_next120s_min_hz": 54.48350997809083,
      "frequency_min": -729.1075118080669,
      "frequency_max": 998.9330534505464,
      "unserved_mwh": 10.600341682490331,
      "balance_failures": 0,
      "illegal_d2r_discharge_count": 0,
      "first_advisory": {
        "tick": 118,
        "sim_time": 590.0,
        "reason": "turbine_catchup"
      },
      "advisory_before_floor": true,
      "at_60s_after_floor": {
        "frequency_hz": 57.26928943627905,
        "gt_plus_solar_minus_demand_mw": 0.0,
        "bess_output_mw": 0.0
      }
    },
    "candidate": {
      "repeat_physical_hash_identical": true,
      "ticks": 17280,
      "complete": true,
      "collapse": null,
      "min_soc": 0.0,
      "floor_min_mwh": 0.0,
      "floor_max_mwh": 14.9375,
      "first_floor_tick": 1012,
      "first_floor_basis": {
        "bess-0": {
          "bess_id": "bess-0",
          "floor_mwh": 14.9375,
          "depth_reserve_mwh": 0.0,
          "diesel_floor_mwh": 0.0,
          "d2r_term_mwh": 14.9375,
          "winning_term": "d2r_bridge",
          "basis": "offline_restart",
          "unit_id": "turbine-4",
          "eligibility_wait_s": 895.0,
          "start_duration_s": 300,
          "thermal_state": "hot",
          "eligibility_reason": "min_down"
        }
      },
      "first_floor_next120s_min_hz": 79.88266332350686,
      "first_discharge_floor_next120s_min_hz": 62.11366885785707,
      "frequency_min": -729.1075118080669,
      "frequency_max": 998.9330534505464,
      "unserved_mwh": 8.4639919161834,
      "balance_failures": 0,
      "illegal_d2r_discharge_count": 0,
      "first_advisory": {
        "tick": 118,
        "sim_time": 590.0,
        "reason": "turbine_catchup"
      },
      "advisory_before_floor": true,
      "at_60s_after_floor": {
        "frequency_hz": 85.67952166997779,
        "gt_plus_solar_minus_demand_mw": 20.7100344,
        "bess_output_mw": -18.0
      }
    }
  },
  "TC_ISL_04": {
    "passed": true,
    "nominal_reporting_band_hz": 0.1,
    "band_basis": "PROPOSED_HERE audit proxy only, not a model/protection setting; exact Hz supplied",
    "no_zero_soc_tick": "candidate SoC never0; first floor onset used as reserve-equivalent recovery anchor"
  },
  "TC_ISL_05": {
    "passed": true
  },
  "gate_passed": true
}
```

Tick numbering in these new evidence files is one-based; timestamps are interval ends.
The first floor-onset window and first discharge-floor window are reported separately:
S10 first crosses the moving floor while charging, not while discharging.
TC-ISL-04 uses first reserve-floor onset because template candidate SoC never reaches zero;
its 0.1 Hz nominal reporting band is PROPOSED_HERE, an audit proxy only.
No frequency/protection constant was changed.

### Important limitations (not concealed by completion checks)
The unprotected full-run frequency extremes persist in both versions.
Completion and a passing power ledger do not certify frequency fidelity.
S10's runtime floor can exceed its 14 MWh usable capacity (14.9375 MWh peak).
There is no cap or rejection. D9b remains a build-time warning, as approved;
it does not detect a floor increase occurring later in a run.
A below-floor held SoC is not itself an illegal release: the floor is time-varying.
The discharge audit separately checks the presence of an on-bus synchronous machine.

### Floor-onset details and below-floor accounting
### demo-islanded-ramp
```json
{
  "base": {
    "first_floor": {
      "tick": 771,
      "sim_time": 3855.0,
      "frequency_hz": 59.99999999998074,
      "gt_mw": 21.921622104217033,
      "bess_mw": 7.572643803374252,
      "soc": 0.0,
      "demand_mw": 44.494265907591284,
      "solar_mw": 15.0,
      "observation": {
        "before": {
          "bess-0": 0.010983237251604131
        },
        "after": {
          "bess-0": 0.0
        },
        "floors": {
          "bess-0": 0.0
        },
        "bases": {
          "bess-0": {}
        },
        "covers": [
          {
            "unit": "bess-0",
            "requested_mw": 7.572643803374252,
            "output_mw": 7.572643803374252,
            "physical_floor_mwh": 0.0,
            "before_mwh": 0.010983237251604131,
            "after_mwh": 0.0,
            "on_bus": [
              "turbine-0",
              "turbine-1",
              "turbine-2",
              "turbine-3"
            ]
          }
        ],
        "balance_passed": true,
        "balance_defect_mw": 0.0,
        "on_bus": [
          "turbine-0",
          "turbine-1",
          "turbine-2",
          "turbine-3"
        ]
      }
    },
    "first_discharge_floor": {
      "tick": 771,
      "sim_time": 3855.0,
      "frequency_hz": 59.99999999998074,
      "gt_mw": 21.921622104217033,
      "bess_mw": 7.572643803374252,
      "soc": 0.0,
      "demand_mw": 44.494265907591284,
      "solar_mw": 15.0,
      "observation": {
        "before": {
          "bess-0": 0.010983237251604131
        },
        "after": {
          "bess-0": 0.0
        },
        "floors": {
          "bess-0": 0.0
        },
        "bases": {
          "bess-0": {}
        },
        "covers": [
          {
            "unit": "bess-0",
            "requested_mw": 7.572643803374252,
            "output_mw": 7.572643803374252,
            "physical_floor_mwh": 0.0,
            "before_mwh": 0.010983237251604131,
            "after_mwh": 0.0,
            "on_bus": [
              "turbine-0",
              "turbine-1",
              "turbine-2",
              "turbine-3"
            ]
          }
        ],
        "balance_passed": true,
        "balance_defect_mw": 0.0,
        "on_bus": [
          "turbine-0",
          "turbine-1",
          "turbine-2",
          "turbine-3"
        ]
      }
    },
    "below_floor_hold_ticks": 1385,
    "below_floor_discharge_ticks": 3,
    "illegal_d2r_discharge_count": 0,
    "first_illegal_d2r_discharge": null,
    "frequency_min_time": 960.0,
    "physical_sha256": "fe798e4292b478ef3f6e25d67e4e22123867f51e49b991ac13981ecaa8114b2a",
    "build_warnings": []
  },
  "candidate": {
    "first_floor": {
      "tick": 312,
      "sim_time": 1560.0,
      "frequency_hz": 59.98901877366516,
      "gt_mw": 32.88335525893466,
      "bess_mw": 11.730991828045049,
      "soc": 0.4522898379269519,
      "demand_mw": 59.614347086979706,
      "solar_mw": 15.0,
      "observation": {
        "before": {
          "bess-0": 6.349072167386793
        },
        "after": {
          "bess-0": 6.3320577309773265
        },
        "floors": {
          "bess-0": 7.5
        },
        "bases": {
          "bess-0": {
            "bess_id": "bess-0",
            "floor_mwh": 7.5,
            "depth_reserve_mwh": 0.0,
            "diesel_floor_mwh": 0.0,
            "d2r_term_mwh": 7.5,
            "winning_term": "d2r_bridge",
            "basis": "offline_restart",
            "unit_id": "turbine-4",
            "eligibility_wait_s": 0.0,
            "start_duration_s": 600.0,
            "thermal_state": "cold",
            "eligibility_reason": "eligible"
          }
        },
        "covers": [
          {
            "unit": "bess-0",
            "requested_mw": 11.730991828045049,
            "output_mw": 11.730991828045049,
            "physical_floor_mwh": 0.0,
            "before_mwh": 6.349072167386793,
            "after_mwh": 6.3320577309773265,
            "on_bus": [
              "turbine-0",
              "turbine-1",
              "turbine-2",
              "turbine-3"
            ]
          }
        ],
        "balance_passed": true,
        "balance_defect_mw": 0.0,
        "on_bus": [
          "turbine-0",
          "turbine-1",
          "turbine-2",
          "turbine-3"
        ]
      }
    },
    "first_discharge_floor": {
      "tick": 312,
      "sim_time": 1560.0,
      "frequency_hz": 59.98901877366516,
      "gt_mw": 32.88335525893466,
      "bess_mw": 11.730991828045049,
      "soc": 0.4522898379269519,
      "demand_mw": 59.614347086979706,
      "solar_mw": 15.0,
      "observation": {
        "before": {
          "bess-0": 6.349072167386793
        },
        "after": {
          "bess-0": 6.3320577309773265
        },
        "floors": {
          "bess-0": 7.5
        },
        "bases": {
          "bess-0": {
            "bess_id": "bess-0",
            "floor_mwh": 7.5,
            "depth_reserve_mwh": 0.0,
            "diesel_floor_mwh": 0.0,
            "d2r_term_mwh": 7.5,
            "winning_term": "d2r_bridge",
            "basis": "offline_restart",
            "unit_id": "turbine-4",
            "eligibility_wait_s": 0.0,
            "start_duration_s": 600.0,
            "thermal_state": "cold",
            "eligibility_reason": "eligible"
          }
        },
        "covers": [
          {
            "unit": "bess-0",
            "requested_mw": 11.730991828045049,
            "output_mw": 11.730991828045049,
            "physical_floor_mwh": 0.0,
            "before_mwh": 6.349072167386793,
            "after_mwh": 6.3320577309773265,
            "on_bus": [
              "turbine-0",
              "turbine-1",
              "turbine-2",
              "turbine-3"
            ]
          }
        ],
        "balance_passed": true,
        "balance_defect_mw": 0.0,
        "on_bus": [
          "turbine-0",
          "turbine-1",
          "turbine-2",
          "turbine-3"
        ]
      }
    },
    "below_floor_hold_ticks": 1845,
    "below_floor_discharge_ticks": 4,
    "illegal_d2r_discharge_count": 0,
    "first_illegal_d2r_discharge": null,
    "frequency_min_time": 960.0,
    "physical_sha256": "f49f71f1573f1f9a22fff6d560eb5a25a380e4088ecccbe12cf6a560964f822a",
    "build_warnings": []
  }
}
```

### S10_mit_supercloud_2021-08-11
```json
{
  "base": {
    "first_floor": {
      "tick": 2372,
      "sim_time": 11860.0,
      "frequency_hz": 59.93638066696738,
      "gt_mw": 42.635830399999996,
      "bess_mw": 14.344395645732686,
      "soc": 0.0,
      "demand_mw": 57.135830399999996,
      "solar_mw": 0,
      "observation": {
        "before": {
          "bess-0": 0.02080487405703124
        },
        "after": {
          "bess-0": 0.0
        },
        "floors": {
          "bess-0": 0.0
        },
        "bases": {
          "bess-0": {}
        },
        "covers": [
          {
            "unit": "bess-0",
            "requested_mw": 14.344395645732686,
            "output_mw": 14.344395645732686,
            "physical_floor_mwh": 0.0,
            "before_mwh": 0.02080487405703124,
            "after_mwh": 0.0,
            "on_bus": [
              "turbine-0",
              "turbine-1",
              "turbine-2",
              "turbine-3",
              "turbine-4"
            ]
          }
        ],
        "balance_passed": true,
        "balance_defect_mw": 0.0,
        "on_bus": [
          "turbine-0",
          "turbine-1",
          "turbine-2",
          "turbine-3",
          "turbine-4"
        ]
      }
    },
    "first_discharge_floor": {
      "tick": 2372,
      "sim_time": 11860.0,
      "frequency_hz": 59.93638066696738,
      "gt_mw": 42.635830399999996,
      "bess_mw": 14.344395645732686,
      "soc": 0.0,
      "demand_mw": 57.135830399999996,
      "solar_mw": 0,
      "observation": {
        "before": {
          "bess-0": 0.02080487405703124
        },
        "after": {
          "bess-0": 0.0
        },
        "floors": {
          "bess-0": 0.0
        },
        "bases": {
          "bess-0": {}
        },
        "covers": [
          {
            "unit": "bess-0",
            "requested_mw": 14.344395645732686,
            "output_mw": 14.344395645732686,
            "physical_floor_mwh": 0.0,
            "before_mwh": 0.02080487405703124,
            "after_mwh": 0.0,
            "on_bus": [
              "turbine-0",
              "turbine-1",
              "turbine-2",
              "turbine-3",
              "turbine-4"
            ]
          }
        ],
        "balance_passed": true,
        "balance_defect_mw": 0.0,
        "on_bus": [
          "turbine-0",
          "turbine-1",
          "turbine-2",
          "turbine-3",
          "turbine-4"
        ]
      }
    },
    "below_floor_hold_ticks": 3203,
    "below_floor_discharge_ticks": 14,
    "illegal_d2r_discharge_count": 0,
    "first_illegal_d2r_discharge": null,
    "frequency_min_time": 33665.0,
    "physical_sha256": "4370c9ebfbfc90d2812cad93285c9749645974502508e8188c3567eb3e60d34d",
    "build_warnings": []
  },
  "candidate": {
    "first_floor": {
      "tick": 1012,
      "sim_time": 5060.0,
      "frequency_hz": 96.94640227850402,
      "gt_mw": 21.0,
      "bess_mw": -18.0,
      "soc": 0.691961070979376,
      "demand_mw": 0.2899656,
      "solar_mw": 0,
      "observation": {
        "before": {
          "bess-0": 9.663514964471515
        },
        "after": {
          "bess-0": 9.687454993711263
        },
        "floors": {
          "bess-0": 14.9375
        },
        "bases": {
          "bess-0": {
            "bess_id": "bess-0",
            "floor_mwh": 14.9375,
            "depth_reserve_mwh": 0.0,
            "diesel_floor_mwh": 0.0,
            "d2r_term_mwh": 14.9375,
            "winning_term": "d2r_bridge",
            "basis": "offline_restart",
            "unit_id": "turbine-4",
            "eligibility_wait_s": 895.0,
            "start_duration_s": 300,
            "thermal_state": "hot",
            "eligibility_reason": "min_down"
          }
        },
        "covers": [],
        "balance_passed": true,
        "balance_defect_mw": 0.0,
        "on_bus": [
          "turbine-0",
          "turbine-1",
          "turbine-2",
          "turbine-3"
        ]
      }
    },
    "first_discharge_floor": {
      "tick": 1063,
      "sim_time": 5315.0,
      "frequency_hz": 63.452370096919104,
      "gt_mw": 18.25,
      "bess_mw": 3.497419999999998,
      "soc": 0.7679315304712216,
      "demand_mw": 21.747419999999998,
      "solar_mw": 0,
      "observation": {
        "before": {
          "bess-0": 10.756114026685779
        },
        "after": {
          "bess-0": 10.751041426597103
        },
        "floors": {
          "bess-0": 11.75
        },
        "bases": {
          "bess-0": {
            "bess_id": "bess-0",
            "floor_mwh": 11.75,
            "depth_reserve_mwh": 0.0,
            "diesel_floor_mwh": 0.0,
            "d2r_term_mwh": 11.75,
            "winning_term": "d2r_bridge",
            "basis": "offline_restart",
            "unit_id": "turbine-4",
            "eligibility_wait_s": 640.0,
            "start_duration_s": 300,
            "thermal_state": "hot",
            "eligibility_reason": "min_down"
          }
        },
        "covers": [
          {
            "unit": "bess-0",
            "requested_mw": 3.497419999999998,
            "output_mw": 3.497419999999998,
            "physical_floor_mwh": 0.0,
            "before_mwh": 10.756114026685779,
            "after_mwh": 10.751041426597103,
            "on_bus": [
              "turbine-0",
              "turbine-1",
              "turbine-2"
            ]
          }
        ],
        "balance_passed": true,
        "balance_defect_mw": 0.0,
        "on_bus": [
          "turbine-0",
          "turbine-1",
          "turbine-2"
        ]
      }
    },
    "below_floor_hold_ticks": 3756,
    "below_floor_discharge_ticks": 702,
    "illegal_d2r_discharge_count": 0,
    "first_illegal_d2r_discharge": null,
    "frequency_min_time": 33665.0,
    "physical_sha256": "8ba0dec0459ca09b9df4ea6fa17bd72fa16038220f425b0a8dd499bfa87557ab",
    "build_warnings": []
  }
}
```

## P3 R3 / unchanged historical physical hashes
```json
{
  "reference": "328309c3a181aefdb702a0577f41acfe673a945450ce61f9ad560696cf0aaa84",
  "actual": {
    "base": "328309c3a181aefdb702a0577f41acfe673a945450ce61f9ad560696cf0aaa84",
    "candidate": "328309c3a181aefdb702a0577f41acfe673a945450ce61f9ad560696cf0aaa84"
  },
  "identical": true
}
```

```json
{
  "reference": "006006e6c9eac82460ee4a343a4d1691f2a34f231ca7fb038c7ae583ab63471a",
  "actual": {
    "base": "006006e6c9eac82460ee4a343a4d1691f2a34f231ca7fb038c7ae583ab63471a",
    "candidate": "006006e6c9eac82460ee4a343a4d1691f2a34f231ca7fb038c7ae583ab63471a"
  },
  "identical": true
}
```

```json
{
  "reference": "9377f009785094697116d356ef554985107ce1ee4c92f01c672f4b30b5f7577a",
  "actual": {
    "base": "9377f009785094697116d356ef554985107ce1ee4c92f01c672f4b30b5f7577a",
    "candidate": "9377f009785094697116d356ef554985107ce1ee4c92f01c672f4b30b5f7577a"
  },
  "identical": true
}
```

```json
{
  "reference": "565edaad7557ed06b545d92fe6c10105ef1a709e1aeb2e224d041e1e475e581b",
  "actual": {
    "base": "565edaad7557ed06b545d92fe6c10105ef1a709e1aeb2e224d041e1e475e581b",
    "candidate": "565edaad7557ed06b545d92fe6c10105ef1a709e1aeb2e224d041e1e475e581b"
  },
  "identical": true
}
```

```json
{
  "reference": "d8146d3e37d9d7e1b306bbf2dc7dea7b2675be9c2bdabca0a209a028772c73d3",
  "actual": {
    "base": "d8146d3e37d9d7e1b306bbf2dc7dea7b2675be9c2bdabca0a209a028772c73d3",
    "candidate": "d8146d3e37d9d7e1b306bbf2dc7dea7b2675be9c2bdabca0a209a028772c73d3"
  },
  "identical": true
}
```

```json
{
  "reference": "d89d3132a5f87e94de6869a1246f5d3f434e03ecab72d744f90329ac8608d8f2",
  "actual": {
    "base": "d89d3132a5f87e94de6869a1246f5d3f434e03ecab72d744f90329ac8608d8f2",
    "candidate": "d89d3132a5f87e94de6869a1246f5d3f434e03ecab72d744f90329ac8608d8f2"
  },
  "identical": true
}
```

## P3 R4 / protected records
```json
{
  "checks": [
    {
      "scenario": "scenario-uneven-multisched-01",
      "arm": "baseline",
      "version": "base",
      "physical_sha256": [
        "90f4b8a55acceb521f972d9596c5137f104dbc34e158ac3bc58cadf73e5164f1",
        "90f4b8a55acceb521f972d9596c5137f104dbc34e158ac3bc58cadf73e5164f1"
      ],
      "compact_sha256": [
        "a2370e5fd24c65cbfd2e70b41f154eeee8857060a689f05a7c7d6ef93c49fd48",
        "a2370e5fd24c65cbfd2e70b41f154eeee8857060a689f05a7c7d6ef93c49fd48"
      ],
      "repetitions_physical_identical": true,
      "repetitions_compact_identical": true,
      "repetitions_metrics_identical": true,
      "metric_count": 27,
      "base_candidate_identical": true,
      "native_status": [
        "PASS",
        "PASS"
      ],
      "production_reference": {
        "dispatch_curtailment_mwh": 8.136511735,
        "turbine_fuel_mmbtu": 714.363019086,
        "unserved_mwh": 0.351692658,
        "peak_unserved_mw": 22.309362466
      },
      "production_actual": {
        "dispatch_curtailment_mwh": 8.136511735,
        "turbine_fuel_mmbtu": 714.363019086,
        "unserved_mwh": 0.351692658,
        "peak_unserved_mw": 22.309362466
      },
      "production_identical_at_9dp": true
    },
    {
      "scenario": "scenario-uneven-multisched-01",
      "arm": "baseline",
      "version": "candidate",
      "physical_sha256": [
        "90f4b8a55acceb521f972d9596c5137f104dbc34e158ac3bc58cadf73e5164f1",
        "90f4b8a55acceb521f972d9596c5137f104dbc34e158ac3bc58cadf73e5164f1"
      ],
      "compact_sha256": [
        "a2370e5fd24c65cbfd2e70b41f154eeee8857060a689f05a7c7d6ef93c49fd48",
        "a2370e5fd24c65cbfd2e70b41f154eeee8857060a689f05a7c7d6ef93c49fd48"
      ],
      "repetitions_physical_identical": true,
      "repetitions_compact_identical": true,
      "repetitions_metrics_identical": true,
      "metric_count": 27,
      "base_candidate_identical": true,
      "native_status": [
        "PASS",
        "PASS"
      ],
      "production_reference": {
        "dispatch_curtailment_mwh": 8.136511735,
        "turbine_fuel_mmbtu": 714.363019086,
        "unserved_mwh": 0.351692658,
        "peak_unserved_mw": 22.309362466
      },
      "production_actual": {
        "dispatch_curtailment_mwh": 8.136511735,
        "turbine_fuel_mmbtu": 714.363019086,
        "unserved_mwh": 0.351692658,
        "peak_unserved_mw": 22.309362466
      },
      "production_identical_at_9dp": true
    },
    {
      "scenario": "scenario-uneven-multisched-01",
      "arm": "informed",
      "version": "base",
      "physical_sha256": [
        "ea12dabd9944d98aad3f8fc966122f2432e33fb7bd150c8dc313ca9a88dd27a6",
        "ea12dabd9944d98aad3f8fc966122f2432e33fb7bd150c8dc313ca9a88dd27a6"
      ],
      "compact_sha256": [
        "0197b5b22abae47ed48635835a25f0bdfb6580a0df61291c82fbfc246fcacc65",
        "0197b5b22abae47ed48635835a25f0bdfb6580a0df61291c82fbfc246fcacc65"
      ],
      "repetitions_physical_identical": true,
      "repetitions_compact_identical": true,
      "repetitions_metrics_identical": true,
      "metric_count": 27,
      "base_candidate_identical": true,
      "native_status": [
        "PASS",
        "PASS"
      ],
      "production_reference": {
        "dispatch_curtailment_mwh": 5.278943188,
        "turbine_fuel_mmbtu": 665.398247704,
        "unserved_mwh": 0.020719074,
        "peak_unserved_mw": 7.52325057
      },
      "production_actual": {
        "dispatch_curtailment_mwh": 5.278943188,
        "turbine_fuel_mmbtu": 665.398247704,
        "unserved_mwh": 0.020719074,
        "peak_unserved_mw": 7.52325057
      },
      "production_identical_at_9dp": true
    },
    {
      "scenario": "scenario-uneven-multisched-01",
      "arm": "informed",
      "version": "candidate",
      "physical_sha256": [
        "ea12dabd9944d98aad3f8fc966122f2432e33fb7bd150c8dc313ca9a88dd27a6",
        "ea12dabd9944d98aad3f8fc966122f2432e33fb7bd150c8dc313ca9a88dd27a6"
      ],
      "compact_sha256": [
        "0197b5b22abae47ed48635835a25f0bdfb6580a0df61291c82fbfc246fcacc65",
        "0197b5b22abae47ed48635835a25f0bdfb6580a0df61291c82fbfc246fcacc65"
      ],
      "repetitions_physical_identical": true,
      "repetitions_compact_identical": true,
      "repetitions_metrics_identical": true,
      "metric_count": 27,
      "base_candidate_identical": true,
      "native_status": [
        "PASS",
        "PASS"
      ],
      "production_reference": {
        "dispatch_curtailment_mwh": 5.278943188,
        "turbine_fuel_mmbtu": 665.398247704,
        "unserved_mwh": 0.020719074,
        "peak_unserved_mw": 7.52325057
      },
      "production_actual": {
        "dispatch_curtailment_mwh": 5.278943188,
        "turbine_fuel_mmbtu": 665.398247704,
        "unserved_mwh": 0.020719074,
        "peak_unserved_mw": 7.52325057
      },
      "production_identical_at_9dp": true
    },
    {
      "scenario": "scenario-h1-k8s-ray-24h",
      "arm": "baseline",
      "version": "base",
      "physical_sha256": [
        "57a1370fd9d26d4bea4d2361f3ae2086aede264badba0c314095219d9741727b",
        "57a1370fd9d26d4bea4d2361f3ae2086aede264badba0c314095219d9741727b"
      ],
      "compact_sha256": [
        "e0d9b888edb338c3796d64a26bd99ac6afb751b4c93bcf0e54b0a73165705755",
        "e0d9b888edb338c3796d64a26bd99ac6afb751b4c93bcf0e54b0a73165705755"
      ],
      "repetitions_physical_identical": true,
      "repetitions_compact_identical": true,
      "repetitions_metrics_identical": true,
      "metric_count": 27,
      "base_candidate_identical": true,
      "native_status": [
        "PASS",
        "PASS"
      ]
    },
    {
      "scenario": "scenario-h1-k8s-ray-24h",
      "arm": "baseline",
      "version": "candidate",
      "physical_sha256": [
        "57a1370fd9d26d4bea4d2361f3ae2086aede264badba0c314095219d9741727b",
        "57a1370fd9d26d4bea4d2361f3ae2086aede264badba0c314095219d9741727b"
      ],
      "compact_sha256": [
        "e0d9b888edb338c3796d64a26bd99ac6afb751b4c93bcf0e54b0a73165705755",
        "e0d9b888edb338c3796d64a26bd99ac6afb751b4c93bcf0e54b0a73165705755"
      ],
      "repetitions_physical_identical": true,
      "repetitions_compact_identical": true,
      "repetitions_metrics_identical": true,
      "metric_count": 27,
      "base_candidate_identical": true,
      "native_status": [
        "PASS",
        "PASS"
      ]
    },
    {
      "scenario": "scenario-h1-k8s-ray-24h",
      "arm": "informed",
      "version": "base",
      "physical_sha256": [
        "60430dc7631204990acc39213cbcbeba8636b71a05d23c1a101c6c5faee71ef9",
        "60430dc7631204990acc39213cbcbeba8636b71a05d23c1a101c6c5faee71ef9"
      ],
      "compact_sha256": [
        "19c2420ea61da37cb73fd2187495dad781f1e4de10766f988347894fe671c4e2",
        "19c2420ea61da37cb73fd2187495dad781f1e4de10766f988347894fe671c4e2"
      ],
      "repetitions_physical_identical": true,
      "repetitions_compact_identical": true,
      "repetitions_metrics_identical": true,
      "metric_count": 27,
      "base_candidate_identical": true,
      "native_status": [
        "PASS",
        "PASS"
      ]
    },
    {
      "scenario": "scenario-h1-k8s-ray-24h",
      "arm": "informed",
      "version": "candidate",
      "physical_sha256": [
        "60430dc7631204990acc39213cbcbeba8636b71a05d23c1a101c6c5faee71ef9",
        "60430dc7631204990acc39213cbcbeba8636b71a05d23c1a101c6c5faee71ef9"
      ],
      "compact_sha256": [
        "19c2420ea61da37cb73fd2187495dad781f1e4de10766f988347894fe671c4e2",
        "19c2420ea61da37cb73fd2187495dad781f1e4de10766f988347894fe671c4e2"
      ],
      "repetitions_physical_identical": true,
      "repetitions_compact_identical": true,
      "repetitions_metrics_identical": true,
      "metric_count": 27,
      "base_candidate_identical": true,
      "native_status": [
        "PASS",
        "PASS"
      ]
    },
    {
      "scenario": "scenario-h2-slurm-24h",
      "arm": "baseline",
      "version": "base",
      "physical_sha256": [
        "f7c8de426e7b1b08650e0980e6ea26d38ce8bf03db2734cd21a18368f413b4a1",
        "f7c8de426e7b1b08650e0980e6ea26d38ce8bf03db2734cd21a18368f413b4a1"
      ],
      "compact_sha256": [
        "8d0d3037dcaa712ccc34a5f744654af15b8654363911e63566f78467443e8b66",
        "8d0d3037dcaa712ccc34a5f744654af15b8654363911e63566f78467443e8b66"
      ],
      "repetitions_physical_identical": true,
      "repetitions_compact_identical": true,
      "repetitions_metrics_identical": true,
      "metric_count": 27,
      "base_candidate_identical": true,
      "native_status": [
        "PASS",
        "PASS"
      ]
    },
    {
      "scenario": "scenario-h2-slurm-24h",
      "arm": "baseline",
      "version": "candidate",
      "physical_sha256": [
        "f7c8de426e7b1b08650e0980e6ea26d38ce8bf03db2734cd21a18368f413b4a1",
        "f7c8de426e7b1b08650e0980e6ea26d38ce8bf03db2734cd21a18368f413b4a1"
      ],
      "compact_sha256": [
        "8d0d3037dcaa712ccc34a5f744654af15b8654363911e63566f78467443e8b66",
        "8d0d3037dcaa712ccc34a5f744654af15b8654363911e63566f78467443e8b66"
      ],
      "repetitions_physical_identical": true,
      "repetitions_compact_identical": true,
      "repetitions_metrics_identical": true,
      "metric_count": 27,
      "base_candidate_identical": true,
      "native_status": [
        "PASS",
        "PASS"
      ]
    },
    {
      "scenario": "scenario-h2-slurm-24h",
      "arm": "informed",
      "version": "base",
      "physical_sha256": [
        "b7383d283f09d625f531ecc216b447b868792f50069bbc662b1636d2b988bbfb",
        "b7383d283f09d625f531ecc216b447b868792f50069bbc662b1636d2b988bbfb"
      ],
      "compact_sha256": [
        "0def2a33daa2770e5095d8cb63b2c5e7d01ab65c85aaf4db3bd732a89623a3c7",
        "0def2a33daa2770e5095d8cb63b2c5e7d01ab65c85aaf4db3bd732a89623a3c7"
      ],
      "repetitions_physical_identical": true,
      "repetitions_compact_identical": true,
      "repetitions_metrics_identical": true,
      "metric_count": 27,
      "base_candidate_identical": true,
      "native_status": [
        "PASS",
        "PASS"
      ]
    },
    {
      "scenario": "scenario-h2-slurm-24h",
      "arm": "informed",
      "version": "candidate",
      "physical_sha256": [
        "b7383d283f09d625f531ecc216b447b868792f50069bbc662b1636d2b988bbfb",
        "b7383d283f09d625f531ecc216b447b868792f50069bbc662b1636d2b988bbfb"
      ],
      "compact_sha256": [
        "0def2a33daa2770e5095d8cb63b2c5e7d01ab65c85aaf4db3bd732a89623a3c7",
        "0def2a33daa2770e5095d8cb63b2c5e7d01ab65c85aaf4db3bd732a89623a3c7"
      ],
      "repetitions_physical_identical": true,
      "repetitions_compact_identical": true,
      "repetitions_metrics_identical": true,
      "metric_count": 27,
      "base_candidate_identical": true,
      "native_status": [
        "PASS",
        "PASS"
      ]
    }
  ],
  "compare_runs": {
    "scenario-uneven-multisched-01/base": {
      "conditions": {
        "build_parity": true,
        "baseline_valid": true,
        "informed_valid": true,
        "baseline_energy_balance": true,
        "informed_energy_balance": true,
        "baseline_fuel_reconciled": true,
        "informed_fuel_reconciled": true,
        "identical_compute_trace": true,
        "informed_unserved_energy_no_worse": true,
        "informed_peak_unserved_no_worse": true
      },
      "condition_order": [
        "build_parity",
        "baseline_valid",
        "informed_valid",
        "baseline_energy_balance",
        "informed_energy_balance",
        "baseline_fuel_reconciled",
        "informed_fuel_reconciled",
        "identical_compute_trace",
        "informed_unserved_energy_no_worse",
        "informed_peak_unserved_no_worse"
      ],
      "verdict": "PASS",
      "informed_vs_baseline": {
        "baseline_unserved_mwh": 0.351692658,
        "informed_unserved_mwh": 0.020719074,
        "baseline_peak_unserved_mw": 22.309362466,
        "informed_peak_unserved_mw": 7.52325057
      }
    },
    "scenario-uneven-multisched-01/candidate": {
      "conditions": {
        "build_parity": true,
        "baseline_valid": true,
        "informed_valid": true,
        "baseline_energy_balance": true,
        "informed_energy_balance": true,
        "baseline_fuel_reconciled": true,
        "informed_fuel_reconciled": true,
        "identical_compute_trace": true,
        "informed_unserved_energy_no_worse": true,
        "informed_peak_unserved_no_worse": true
      },
      "condition_order": [
        "build_parity",
        "baseline_valid",
        "informed_valid",
        "baseline_energy_balance",
        "informed_energy_balance",
        "baseline_fuel_reconciled",
        "informed_fuel_reconciled",
        "identical_compute_trace",
        "informed_unserved_energy_no_worse",
        "informed_peak_unserved_no_worse"
      ],
      "verdict": "PASS",
      "informed_vs_baseline": {
        "baseline_unserved_mwh": 0.351692658,
        "informed_unserved_mwh": 0.020719074,
        "baseline_peak_unserved_mw": 22.309362466,
        "informed_peak_unserved_mw": 7.52325057
      }
    },
    "scenario-h1-k8s-ray-24h/base": {
      "conditions": {
        "build_parity": true,
        "baseline_valid": true,
        "informed_valid": true,
        "baseline_energy_balance": true,
        "informed_energy_balance": true,
        "baseline_fuel_reconciled": true,
        "informed_fuel_reconciled": true,
        "identical_compute_trace": true,
        "informed_unserved_energy_no_worse": true,
        "informed_peak_unserved_no_worse": true
      },
      "condition_order": [
        "build_parity",
        "baseline_valid",
        "informed_valid",
        "baseline_energy_balance",
        "informed_energy_balance",
        "baseline_fuel_reconciled",
        "informed_fuel_reconciled",
        "identical_compute_trace",
        "informed_unserved_energy_no_worse",
        "informed_peak_unserved_no_worse"
      ],
      "verdict": "PASS",
      "informed_vs_baseline": {
        "baseline_unserved_mwh": 0.894372986,
        "informed_unserved_mwh": 0.124133405,
        "baseline_peak_unserved_mw": 35.021533247,
        "informed_peak_unserved_mw": 20.746308977
      }
    },
    "scenario-h1-k8s-ray-24h/candidate": {
      "conditions": {
        "build_parity": true,
        "baseline_valid": true,
        "informed_valid": true,
        "baseline_energy_balance": true,
        "informed_energy_balance": true,
        "baseline_fuel_reconciled": true,
        "informed_fuel_reconciled": true,
        "identical_compute_trace": true,
        "informed_unserved_energy_no_worse": true,
        "informed_peak_unserved_no_worse": true
      },
      "condition_order": [
        "build_parity",
        "baseline_valid",
        "informed_valid",
        "baseline_energy_balance",
        "informed_energy_balance",
        "baseline_fuel_reconciled",
        "informed_fuel_reconciled",
        "identical_compute_trace",
        "informed_unserved_energy_no_worse",
        "informed_peak_unserved_no_worse"
      ],
      "verdict": "PASS",
      "informed_vs_baseline": {
        "baseline_unserved_mwh": 0.894372986,
        "informed_unserved_mwh": 0.124133405,
        "baseline_peak_unserved_mw": 35.021533247,
        "informed_peak_unserved_mw": 20.746308977
      }
    },
    "scenario-h2-slurm-24h/base": {
      "conditions": {
        "build_parity": true,
        "baseline_valid": true,
        "informed_valid": true,
        "baseline_energy_balance": true,
        "informed_energy_balance": true,
        "baseline_fuel_reconciled": true,
        "informed_fuel_reconciled": true,
        "identical_compute_trace": true,
        "informed_unserved_energy_no_worse": true,
        "informed_peak_unserved_no_worse": true
      },
      "condition_order": [
        "build_parity",
        "baseline_valid",
        "informed_valid",
        "baseline_energy_balance",
        "informed_energy_balance",
        "baseline_fuel_reconciled",
        "informed_fuel_reconciled",
        "identical_compute_trace",
        "informed_unserved_energy_no_worse",
        "informed_peak_unserved_no_worse"
      ],
      "verdict": "PASS",
      "informed_vs_baseline": {
        "baseline_unserved_mwh": 5.011418076,
        "informed_unserved_mwh": 0.859772492,
        "baseline_peak_unserved_mw": 44.86838787,
        "informed_peak_unserved_mw": 42.36838787
      }
    },
    "scenario-h2-slurm-24h/candidate": {
      "conditions": {
        "build_parity": true,
        "baseline_valid": true,
        "informed_valid": true,
        "baseline_energy_balance": true,
        "informed_energy_balance": true,
        "baseline_fuel_reconciled": true,
        "informed_fuel_reconciled": true,
        "identical_compute_trace": true,
        "informed_unserved_energy_no_worse": true,
        "informed_peak_unserved_no_worse": true
      },
      "condition_order": [
        "build_parity",
        "baseline_valid",
        "informed_valid",
        "baseline_energy_balance",
        "informed_energy_balance",
        "baseline_fuel_reconciled",
        "informed_fuel_reconciled",
        "identical_compute_trace",
        "informed_unserved_energy_no_worse",
        "informed_peak_unserved_no_worse"
      ],
      "verdict": "PASS",
      "informed_vs_baseline": {
        "baseline_unserved_mwh": 5.011418076,
        "informed_unserved_mwh": 0.859772492,
        "baseline_peak_unserved_mw": 44.86838787,
        "informed_peak_unserved_mw": 42.36838787
      }
    }
  },
  "h2_baseline_reconciliation": {
    "base": {
      "payload": {
        "release_charged": true,
        "recorded_event_count": 11,
        "measured_event_count": 11,
        "measured_start_fuel_mmbtu": 124.0,
        "tier_sum_mmbtu": null,
        "passed": true
      },
      "measured_start_event_count": 11,
      "constraints_valid": true,
      "hard_violations": []
    },
    "candidate": {
      "payload": {
        "release_charged": true,
        "recorded_event_count": 11,
        "measured_event_count": 11,
        "measured_start_fuel_mmbtu": 124.0,
        "tier_sum_mmbtu": null,
        "passed": true
      },
      "measured_start_event_count": 11,
      "constraints_valid": true,
      "hard_violations": []
    }
  },
  "passed": true
}
```

Each pair below used fresh base/candidate runs; no result-cache reuse.
The physical fields, native compact ticks and all 27 metrics are compared exactly.
Complete 27-metric before/after tables follow (one of two identical repetitions per arm).
### scenario-uneven-multisched-01 / baseline
```json
{
  "base_physical_sha256": "90f4b8a55acceb521f972d9596c5137f104dbc34e158ac3bc58cadf73e5164f1",
  "candidate_physical_sha256": "90f4b8a55acceb521f972d9596c5137f104dbc34e158ac3bc58cadf73e5164f1",
  "base_compact_sha256": "a2370e5fd24c65cbfd2e70b41f154eeee8857060a689f05a7c7d6ef93c49fd48",
  "candidate_compact_sha256": "a2370e5fd24c65cbfd2e70b41f154eeee8857060a689f05a7c7d6ef93c49fd48",
  "before_metrics": {
    "tick_count": 1440,
    "interval_seconds": 5.0,
    "fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 690.133782974,
      "no_load_fuel_mmbtu": 8.19,
      "hot_standby_fuel_mmbtu": 0.039236111,
      "start_fuel_mmbtu": 16.0
    },
    "turbine_fuel_mmbtu": 714.363019086,
    "fuel_reconciled": true,
    "start_fuel_reconciliation": {
      "release_charged": true,
      "recorded_event_count": 2,
      "measured_event_count": 2,
      "measured_start_fuel_mmbtu": 16.0,
      "tier_sum_mmbtu": null,
      "passed": true
    },
    "dispatch_curtailment_mwh": 8.136511735,
    "dispatch_curtailment_interval_exposure_fuel_mmbtu": 291.229346912,
    "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 287.502680246,
      "no_load_fuel_mmbtu": 3.726666667,
      "hot_standby_fuel_mmbtu": 0.0,
      "start_fuel_mmbtu": 0.0
    },
    "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
      "gt-spin-01": 93.186666667,
      "gt-spin-02": 92.778235801,
      "gt-hot-01": 54.624513889,
      "gt-hot-02": 50.639930556
    },
    "dispatch_curtailment_attributable_fuel_mmbtu": 85.443185219,
    "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
      "gt-spin-01": 29.816221037,
      "gt-spin-02": 29.711129581,
      "gt-hot-01": 14.277890997,
      "gt-hot-02": 11.637943604
    },
    "unserved_mwh": 0.351692658,
    "peak_unserved_mw": 22.309362466,
    "served_mwh": 64.203838044,
    "unserved_intervals": [
      {
        "start_sim_time_s": 325.0,
        "end_sim_time_s": 465.0,
        "peak_unserved_mw": 22.30936246553462
      },
      {
        "start_sim_time_s": 1850.0,
        "end_sim_time_s": 1855.0,
        "peak_unserved_mw": 4.628919357798523
      }
    ],
    "energy_balance": {
      "closure_status": true,
      "max_abs_physical_ledger_defect_mw": 0.0,
      "served_demand_mwh": 64.203838044,
      "unserved_demand_mwh": 0.351692658
    },
    "bess_soc_min": 0.746789342,
    "bess_soc_max": 0.999999999,
    "bess_soc_final": 0.999999999,
    "commitment": {
      "distinct_event_count": 8,
      "visible_distinct_event_count": 8,
      "suppressed_repeat_count": 0,
      "log_complete": true,
      "omitted_record_count": 0,
      "reserve_floor_refusal_count": 0,
      "reserve_floor_distinct_event_count": 0,
      "reserve_floor_visible_distinct_event_count": 0,
      "reserve_floor_suppressed_repeat_count": 0,
      "reserve_floor_log_complete": true,
      "reserve_floor_omitted_record_count": 0,
      "same_unit_restart_within_min_down_window_count": 0
    },
    "forecast": {
      "miss_count": 0,
      "miss_peak_mw": 0.0
    },
    "compute_trace_sha256": "fb3a32d783d0a61ddd2cb8ec7bfbe0204712a2c6f6f9398ef60932160dafa54b",
    "compute_trace_count": 1440,
    "daily_breakdown": [
      {
        "day": 1,
        "kind": "weekday",
        "fuel_by_component_mmbtu": {
          "load_fuel_mmbtu": 690.133782974,
          "no_load_fuel_mmbtu": 8.19,
          "hot_standby_fuel_mmbtu": 0.039236111,
          "start_fuel_mmbtu": 16.0
        },
        "fuel_mmbtu": 714.363019086,
        "unserved_mwh": 0.351692658,
        "curtailed_mwh": 8.136511735,
        "bess_soc_end": 0.999999999
      }
    ],
    "constraints_valid": true,
    "hard_violations": []
  },
  "after_metrics": {
    "tick_count": 1440,
    "interval_seconds": 5.0,
    "fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 690.133782974,
      "no_load_fuel_mmbtu": 8.19,
      "hot_standby_fuel_mmbtu": 0.039236111,
      "start_fuel_mmbtu": 16.0
    },
    "turbine_fuel_mmbtu": 714.363019086,
    "fuel_reconciled": true,
    "start_fuel_reconciliation": {
      "release_charged": true,
      "recorded_event_count": 2,
      "measured_event_count": 2,
      "measured_start_fuel_mmbtu": 16.0,
      "tier_sum_mmbtu": null,
      "passed": true
    },
    "dispatch_curtailment_mwh": 8.136511735,
    "dispatch_curtailment_interval_exposure_fuel_mmbtu": 291.229346912,
    "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 287.502680246,
      "no_load_fuel_mmbtu": 3.726666667,
      "hot_standby_fuel_mmbtu": 0.0,
      "start_fuel_mmbtu": 0.0
    },
    "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
      "gt-spin-01": 93.186666667,
      "gt-spin-02": 92.778235801,
      "gt-hot-01": 54.624513889,
      "gt-hot-02": 50.639930556
    },
    "dispatch_curtailment_attributable_fuel_mmbtu": 85.443185219,
    "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
      "gt-spin-01": 29.816221037,
      "gt-spin-02": 29.711129581,
      "gt-hot-01": 14.277890997,
      "gt-hot-02": 11.637943604
    },
    "unserved_mwh": 0.351692658,
    "peak_unserved_mw": 22.309362466,
    "served_mwh": 64.203838044,
    "unserved_intervals": [
      {
        "start_sim_time_s": 325.0,
        "end_sim_time_s": 465.0,
        "peak_unserved_mw": 22.30936246553462
      },
      {
        "start_sim_time_s": 1850.0,
        "end_sim_time_s": 1855.0,
        "peak_unserved_mw": 4.628919357798523
      }
    ],
    "energy_balance": {
      "closure_status": true,
      "max_abs_physical_ledger_defect_mw": 0.0,
      "served_demand_mwh": 64.203838044,
      "unserved_demand_mwh": 0.351692658
    },
    "bess_soc_min": 0.746789342,
    "bess_soc_max": 0.999999999,
    "bess_soc_final": 0.999999999,
    "commitment": {
      "distinct_event_count": 8,
      "visible_distinct_event_count": 8,
      "suppressed_repeat_count": 0,
      "log_complete": true,
      "omitted_record_count": 0,
      "reserve_floor_refusal_count": 0,
      "reserve_floor_distinct_event_count": 0,
      "reserve_floor_visible_distinct_event_count": 0,
      "reserve_floor_suppressed_repeat_count": 0,
      "reserve_floor_log_complete": true,
      "reserve_floor_omitted_record_count": 0,
      "same_unit_restart_within_min_down_window_count": 0
    },
    "forecast": {
      "miss_count": 0,
      "miss_peak_mw": 0.0
    },
    "compute_trace_sha256": "fb3a32d783d0a61ddd2cb8ec7bfbe0204712a2c6f6f9398ef60932160dafa54b",
    "compute_trace_count": 1440,
    "daily_breakdown": [
      {
        "day": 1,
        "kind": "weekday",
        "fuel_by_component_mmbtu": {
          "load_fuel_mmbtu": 690.133782974,
          "no_load_fuel_mmbtu": 8.19,
          "hot_standby_fuel_mmbtu": 0.039236111,
          "start_fuel_mmbtu": 16.0
        },
        "fuel_mmbtu": 714.363019086,
        "unserved_mwh": 0.351692658,
        "curtailed_mwh": 8.136511735,
        "bess_soc_end": 0.999999999
      }
    ],
    "constraints_valid": true,
    "hard_violations": []
  },
  "base_final_floor_basis": null,
  "candidate_final_floor_basis": {
    "bess-0": {
      "bess_id": "bess-0",
      "floor_mwh": 6.25,
      "depth_reserve_mwh": 0.0,
      "diesel_floor_mwh": 1.4583333333333333,
      "d2r_term_mwh": 6.25,
      "winning_term": "d2r_bridge",
      "basis": "offline_restart",
      "unit_id": "gt-hot-01",
      "eligibility_wait_s": 0.0,
      "start_duration_s": 300.0,
      "thermal_state": "hot",
      "eligibility_reason": "eligible"
    }
  },
  "physical_identical": true,
  "compact_identical": true,
  "metrics_identical": true
}
```

### scenario-uneven-multisched-01 / informed
```json
{
  "base_physical_sha256": "ea12dabd9944d98aad3f8fc966122f2432e33fb7bd150c8dc313ca9a88dd27a6",
  "candidate_physical_sha256": "ea12dabd9944d98aad3f8fc966122f2432e33fb7bd150c8dc313ca9a88dd27a6",
  "base_compact_sha256": "0197b5b22abae47ed48635835a25f0bdfb6580a0df61291c82fbfc246fcacc65",
  "candidate_compact_sha256": "0197b5b22abae47ed48635835a25f0bdfb6580a0df61291c82fbfc246fcacc65",
  "before_metrics": {
    "tick_count": 1440,
    "interval_seconds": 5.0,
    "fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 642.554567148,
      "no_load_fuel_mmbtu": 6.843333333,
      "hot_standby_fuel_mmbtu": 0.000347222,
      "start_fuel_mmbtu": 16.0
    },
    "turbine_fuel_mmbtu": 665.398247704,
    "fuel_reconciled": true,
    "start_fuel_reconciliation": {
      "release_charged": true,
      "recorded_event_count": 2,
      "measured_event_count": 2,
      "measured_start_fuel_mmbtu": 16.0,
      "tier_sum_mmbtu": null,
      "passed": true
    },
    "dispatch_curtailment_mwh": 5.278943188,
    "dispatch_curtailment_interval_exposure_fuel_mmbtu": 141.143846919,
    "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 139.390513585,
      "no_load_fuel_mmbtu": 1.753333333,
      "hot_standby_fuel_mmbtu": 0.0,
      "start_fuel_mmbtu": 0.0
    },
    "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
      "gt-spin-01": 61.708845913,
      "gt-spin-02": 61.092791773,
      "gt-hot-01": 9.303598121,
      "gt-hot-02": 9.038611111
    },
    "dispatch_curtailment_attributable_fuel_mmbtu": 55.021850379,
    "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
      "gt-spin-01": 26.368861337,
      "gt-spin-02": 26.22775275,
      "gt-hot-01": 1.242273356,
      "gt-hot-02": 1.182962935
    },
    "unserved_mwh": 0.020719074,
    "peak_unserved_mw": 7.52325057,
    "served_mwh": 64.534811628,
    "unserved_intervals": [
      {
        "start_sim_time_s": 335.0,
        "end_sim_time_s": 345.0,
        "peak_unserved_mw": 7.5232505700275
      }
    ],
    "energy_balance": {
      "closure_status": true,
      "max_abs_physical_ledger_defect_mw": 0.0,
      "served_demand_mwh": 64.534811628,
      "unserved_demand_mwh": 0.020719074
    },
    "bess_soc_min": 0.859751061,
    "bess_soc_max": 0.999999999,
    "bess_soc_final": 0.999999999,
    "commitment": {
      "distinct_event_count": 11,
      "visible_distinct_event_count": 11,
      "suppressed_repeat_count": 1374,
      "log_complete": true,
      "omitted_record_count": 0,
      "reserve_floor_refusal_count": 1377,
      "reserve_floor_distinct_event_count": 1377,
      "reserve_floor_visible_distinct_event_count": 1377,
      "reserve_floor_suppressed_repeat_count": 0,
      "reserve_floor_log_complete": true,
      "reserve_floor_omitted_record_count": 0,
      "same_unit_restart_within_min_down_window_count": 0
    },
    "forecast": {
      "miss_count": 4,
      "miss_peak_mw": 3.208264895
    },
    "compute_trace_sha256": "fb3a32d783d0a61ddd2cb8ec7bfbe0204712a2c6f6f9398ef60932160dafa54b",
    "compute_trace_count": 1440,
    "daily_breakdown": [
      {
        "day": 1,
        "kind": "weekday",
        "fuel_by_component_mmbtu": {
          "load_fuel_mmbtu": 642.554567148,
          "no_load_fuel_mmbtu": 6.843333333,
          "hot_standby_fuel_mmbtu": 0.000347222,
          "start_fuel_mmbtu": 16.0
        },
        "fuel_mmbtu": 665.398247704,
        "unserved_mwh": 0.020719074,
        "curtailed_mwh": 5.278943188,
        "bess_soc_end": 0.999999999
      }
    ],
    "constraints_valid": true,
    "hard_violations": []
  },
  "after_metrics": {
    "tick_count": 1440,
    "interval_seconds": 5.0,
    "fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 642.554567148,
      "no_load_fuel_mmbtu": 6.843333333,
      "hot_standby_fuel_mmbtu": 0.000347222,
      "start_fuel_mmbtu": 16.0
    },
    "turbine_fuel_mmbtu": 665.398247704,
    "fuel_reconciled": true,
    "start_fuel_reconciliation": {
      "release_charged": true,
      "recorded_event_count": 2,
      "measured_event_count": 2,
      "measured_start_fuel_mmbtu": 16.0,
      "tier_sum_mmbtu": null,
      "passed": true
    },
    "dispatch_curtailment_mwh": 5.278943188,
    "dispatch_curtailment_interval_exposure_fuel_mmbtu": 141.143846919,
    "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 139.390513585,
      "no_load_fuel_mmbtu": 1.753333333,
      "hot_standby_fuel_mmbtu": 0.0,
      "start_fuel_mmbtu": 0.0
    },
    "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
      "gt-spin-01": 61.708845913,
      "gt-spin-02": 61.092791773,
      "gt-hot-01": 9.303598121,
      "gt-hot-02": 9.038611111
    },
    "dispatch_curtailment_attributable_fuel_mmbtu": 55.021850379,
    "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
      "gt-spin-01": 26.368861337,
      "gt-spin-02": 26.22775275,
      "gt-hot-01": 1.242273356,
      "gt-hot-02": 1.182962935
    },
    "unserved_mwh": 0.020719074,
    "peak_unserved_mw": 7.52325057,
    "served_mwh": 64.534811628,
    "unserved_intervals": [
      {
        "start_sim_time_s": 335.0,
        "end_sim_time_s": 345.0,
        "peak_unserved_mw": 7.5232505700275
      }
    ],
    "energy_balance": {
      "closure_status": true,
      "max_abs_physical_ledger_defect_mw": 0.0,
      "served_demand_mwh": 64.534811628,
      "unserved_demand_mwh": 0.020719074
    },
    "bess_soc_min": 0.859751061,
    "bess_soc_max": 0.999999999,
    "bess_soc_final": 0.999999999,
    "commitment": {
      "distinct_event_count": 11,
      "visible_distinct_event_count": 11,
      "suppressed_repeat_count": 1374,
      "log_complete": true,
      "omitted_record_count": 0,
      "reserve_floor_refusal_count": 1377,
      "reserve_floor_distinct_event_count": 1377,
      "reserve_floor_visible_distinct_event_count": 1377,
      "reserve_floor_suppressed_repeat_count": 0,
      "reserve_floor_log_complete": true,
      "reserve_floor_omitted_record_count": 0,
      "same_unit_restart_within_min_down_window_count": 0
    },
    "forecast": {
      "miss_count": 4,
      "miss_peak_mw": 3.208264895
    },
    "compute_trace_sha256": "fb3a32d783d0a61ddd2cb8ec7bfbe0204712a2c6f6f9398ef60932160dafa54b",
    "compute_trace_count": 1440,
    "daily_breakdown": [
      {
        "day": 1,
        "kind": "weekday",
        "fuel_by_component_mmbtu": {
          "load_fuel_mmbtu": 642.554567148,
          "no_load_fuel_mmbtu": 6.843333333,
          "hot_standby_fuel_mmbtu": 0.000347222,
          "start_fuel_mmbtu": 16.0
        },
        "fuel_mmbtu": 665.398247704,
        "unserved_mwh": 0.020719074,
        "curtailed_mwh": 5.278943188,
        "bess_soc_end": 0.999999999
      }
    ],
    "constraints_valid": true,
    "hard_violations": []
  },
  "base_final_floor_basis": null,
  "candidate_final_floor_basis": {
    "bess-0": {
      "bess_id": "bess-0",
      "floor_mwh": 7.5,
      "depth_reserve_mwh": 0.0,
      "diesel_floor_mwh": 1.4583333333333333,
      "d2r_term_mwh": 7.5,
      "winning_term": "d2r_bridge",
      "basis": "offline_restart",
      "unit_id": "gt-hot-01",
      "eligibility_wait_s": 0.0,
      "start_duration_s": 360.0,
      "thermal_state": "warm",
      "eligibility_reason": "eligible"
    }
  },
  "physical_identical": true,
  "compact_identical": true,
  "metrics_identical": true
}
```

### scenario-h1-k8s-ray-24h / baseline
```json
{
  "base_physical_sha256": "57a1370fd9d26d4bea4d2361f3ae2086aede264badba0c314095219d9741727b",
  "candidate_physical_sha256": "57a1370fd9d26d4bea4d2361f3ae2086aede264badba0c314095219d9741727b",
  "base_compact_sha256": "e0d9b888edb338c3796d64a26bd99ac6afb751b4c93bcf0e54b0a73165705755",
  "candidate_compact_sha256": "e0d9b888edb338c3796d64a26bd99ac6afb751b4c93bcf0e54b0a73165705755",
  "before_metrics": {
    "tick_count": 17280,
    "interval_seconds": 5.0,
    "fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 5847.168216351,
      "no_load_fuel_mmbtu": 72.43,
      "hot_standby_fuel_mmbtu": 4.142013889,
      "start_fuel_mmbtu": 116.0
    },
    "turbine_fuel_mmbtu": 6039.74023024,
    "fuel_reconciled": true,
    "start_fuel_reconciliation": {
      "release_charged": true,
      "recorded_event_count": 12,
      "measured_event_count": 12,
      "measured_start_fuel_mmbtu": 116.0,
      "tier_sum_mmbtu": null,
      "passed": true
    },
    "dispatch_curtailment_mwh": 187.690139189,
    "dispatch_curtailment_interval_exposure_fuel_mmbtu": 3394.620064264,
    "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 3347.181453153,
      "no_load_fuel_mmbtu": 43.573333333,
      "hot_standby_fuel_mmbtu": 3.865277778,
      "start_fuel_mmbtu": 0.0
    },
    "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
      "gt-spin-01": 1572.100972222,
      "gt-spin-02": 1571.541314265,
      "gt-hot-01": 154.755902778,
      "gt-hot-02": 96.221875
    },
    "dispatch_curtailment_attributable_fuel_mmbtu": 1974.088304814,
    "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
      "gt-spin-01": 929.988576652,
      "gt-spin-02": 929.873705803,
      "gt-hot-01": 79.517141839,
      "gt-hot-02": 34.708880519
    },
    "unserved_mwh": 0.894372986,
    "peak_unserved_mw": 35.021533247,
    "served_mwh": 367.781736493,
    "unserved_intervals": [
      {
        "start_sim_time_s": 28860.0,
        "end_sim_time_s": 28865.0,
        "peak_unserved_mw": 0.8040054789154141
      },
      {
        "start_sim_time_s": 30650.0,
        "end_sim_time_s": 30680.0,
        "peak_unserved_mw": 26.618853625395175
      },
      {
        "start_sim_time_s": 30995.0,
        "end_sim_time_s": 31000.0,
        "peak_unserved_mw": 0.0014763720534602953
      },
      {
        "start_sim_time_s": 31500.0,
        "end_sim_time_s": 31515.0,
        "peak_unserved_mw": 5.514271219813324
      },
      {
        "start_sim_time_s": 36030.0,
        "end_sim_time_s": 36045.0,
        "peak_unserved_mw": 5.033568781899795
      },
      {
        "start_sim_time_s": 37850.0,
        "end_sim_time_s": 37880.0,
        "peak_unserved_mw": 29.417818249240682
      },
      {
        "start_sim_time_s": 38240.0,
        "end_sim_time_s": 38255.0,
        "peak_unserved_mw": 1.9529208953445476
      },
      {
        "start_sim_time_s": 38700.0,
        "end_sim_time_s": 38715.0,
        "peak_unserved_mw": 5.25701274369851
      },
      {
        "start_sim_time_s": 45050.0,
        "end_sim_time_s": 45080.0,
        "peak_unserved_mw": 32.46833679356759
      },
      {
        "start_sim_time_s": 45440.0,
        "end_sim_time_s": 45455.0,
        "peak_unserved_mw": 0.5423003956669561
      },
      {
        "start_sim_time_s": 45900.0,
        "end_sim_time_s": 45915.0,
        "peak_unserved_mw": 6.887755602473391
      },
      {
        "start_sim_time_s": 52250.0,
        "end_sim_time_s": 52280.0,
        "peak_unserved_mw": 35.021533246572275
      },
      {
        "start_sim_time_s": 52640.0,
        "end_sim_time_s": 52655.0,
        "peak_unserved_mw": 2.804922000000005
      },
      {
        "start_sim_time_s": 57630.0,
        "end_sim_time_s": 57635.0,
        "peak_unserved_mw": 0.7155264052397072
      },
      {
        "start_sim_time_s": 59450.0,
        "end_sim_time_s": 59480.0,
        "peak_unserved_mw": 27.5
      },
      {
        "start_sim_time_s": 59840.0,
        "end_sim_time_s": 59855.0,
        "peak_unserved_mw": 0.741633537511504
      },
      {
        "start_sim_time_s": 60300.0,
        "end_sim_time_s": 60315.0,
        "peak_unserved_mw": 5.328277620981893
      },
      {
        "start_sim_time_s": 66650.0,
        "end_sim_time_s": 66680.0,
        "peak_unserved_mw": 33.2463089774655
      },
      {
        "start_sim_time_s": 67040.0,
        "end_sim_time_s": 67055.0,
        "peak_unserved_mw": 3.1841012001148385
      },
      {
        "start_sim_time_s": 67500.0,
        "end_sim_time_s": 67515.0,
        "peak_unserved_mw": 5.294020684052754
      }
    ],
    "energy_balance": {
      "closure_status": true,
      "max_abs_physical_ledger_defect_mw": 0.0,
      "served_demand_mwh": 367.781736493,
      "unserved_demand_mwh": 0.894372986
    },
    "bess_soc_min": 0.828342155,
    "bess_soc_max": 0.999999999,
    "bess_soc_final": 0.999999998,
    "commitment": {
      "distinct_event_count": 48,
      "visible_distinct_event_count": 48,
      "suppressed_repeat_count": 0,
      "log_complete": true,
      "omitted_record_count": 0,
      "reserve_floor_refusal_count": 0,
      "reserve_floor_distinct_event_count": 0,
      "reserve_floor_visible_distinct_event_count": 0,
      "reserve_floor_suppressed_repeat_count": 0,
      "reserve_floor_log_complete": true,
      "reserve_floor_omitted_record_count": 0,
      "same_unit_restart_within_min_down_window_count": 0
    },
    "forecast": {
      "miss_count": 0,
      "miss_peak_mw": 0.0
    },
    "compute_trace_sha256": "916eb28339ae921141941a8c90069e573e80ef4bf65f2be39cc3e45b8747ccff",
    "compute_trace_count": 17280,
    "daily_breakdown": [
      {
        "day": 1,
        "kind": "weekday",
        "fuel_by_component_mmbtu": {
          "load_fuel_mmbtu": 5847.168216351,
          "no_load_fuel_mmbtu": 72.43,
          "hot_standby_fuel_mmbtu": 4.142013889,
          "start_fuel_mmbtu": 116.0
        },
        "fuel_mmbtu": 6039.74023024,
        "unserved_mwh": 0.894372986,
        "curtailed_mwh": 187.690139189,
        "bess_soc_end": 0.999999998
      }
    ],
    "constraints_valid": true,
    "hard_violations": []
  },
  "after_metrics": {
    "tick_count": 17280,
    "interval_seconds": 5.0,
    "fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 5847.168216351,
      "no_load_fuel_mmbtu": 72.43,
      "hot_standby_fuel_mmbtu": 4.142013889,
      "start_fuel_mmbtu": 116.0
    },
    "turbine_fuel_mmbtu": 6039.74023024,
    "fuel_reconciled": true,
    "start_fuel_reconciliation": {
      "release_charged": true,
      "recorded_event_count": 12,
      "measured_event_count": 12,
      "measured_start_fuel_mmbtu": 116.0,
      "tier_sum_mmbtu": null,
      "passed": true
    },
    "dispatch_curtailment_mwh": 187.690139189,
    "dispatch_curtailment_interval_exposure_fuel_mmbtu": 3394.620064264,
    "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 3347.181453153,
      "no_load_fuel_mmbtu": 43.573333333,
      "hot_standby_fuel_mmbtu": 3.865277778,
      "start_fuel_mmbtu": 0.0
    },
    "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
      "gt-spin-01": 1572.100972222,
      "gt-spin-02": 1571.541314265,
      "gt-hot-01": 154.755902778,
      "gt-hot-02": 96.221875
    },
    "dispatch_curtailment_attributable_fuel_mmbtu": 1974.088304814,
    "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
      "gt-spin-01": 929.988576652,
      "gt-spin-02": 929.873705803,
      "gt-hot-01": 79.517141839,
      "gt-hot-02": 34.708880519
    },
    "unserved_mwh": 0.894372986,
    "peak_unserved_mw": 35.021533247,
    "served_mwh": 367.781736493,
    "unserved_intervals": [
      {
        "start_sim_time_s": 28860.0,
        "end_sim_time_s": 28865.0,
        "peak_unserved_mw": 0.8040054789154141
      },
      {
        "start_sim_time_s": 30650.0,
        "end_sim_time_s": 30680.0,
        "peak_unserved_mw": 26.618853625395175
      },
      {
        "start_sim_time_s": 30995.0,
        "end_sim_time_s": 31000.0,
        "peak_unserved_mw": 0.0014763720534602953
      },
      {
        "start_sim_time_s": 31500.0,
        "end_sim_time_s": 31515.0,
        "peak_unserved_mw": 5.514271219813324
      },
      {
        "start_sim_time_s": 36030.0,
        "end_sim_time_s": 36045.0,
        "peak_unserved_mw": 5.033568781899795
      },
      {
        "start_sim_time_s": 37850.0,
        "end_sim_time_s": 37880.0,
        "peak_unserved_mw": 29.417818249240682
      },
      {
        "start_sim_time_s": 38240.0,
        "end_sim_time_s": 38255.0,
        "peak_unserved_mw": 1.9529208953445476
      },
      {
        "start_sim_time_s": 38700.0,
        "end_sim_time_s": 38715.0,
        "peak_unserved_mw": 5.25701274369851
      },
      {
        "start_sim_time_s": 45050.0,
        "end_sim_time_s": 45080.0,
        "peak_unserved_mw": 32.46833679356759
      },
      {
        "start_sim_time_s": 45440.0,
        "end_sim_time_s": 45455.0,
        "peak_unserved_mw": 0.5423003956669561
      },
      {
        "start_sim_time_s": 45900.0,
        "end_sim_time_s": 45915.0,
        "peak_unserved_mw": 6.887755602473391
      },
      {
        "start_sim_time_s": 52250.0,
        "end_sim_time_s": 52280.0,
        "peak_unserved_mw": 35.021533246572275
      },
      {
        "start_sim_time_s": 52640.0,
        "end_sim_time_s": 52655.0,
        "peak_unserved_mw": 2.804922000000005
      },
      {
        "start_sim_time_s": 57630.0,
        "end_sim_time_s": 57635.0,
        "peak_unserved_mw": 0.7155264052397072
      },
      {
        "start_sim_time_s": 59450.0,
        "end_sim_time_s": 59480.0,
        "peak_unserved_mw": 27.5
      },
      {
        "start_sim_time_s": 59840.0,
        "end_sim_time_s": 59855.0,
        "peak_unserved_mw": 0.741633537511504
      },
      {
        "start_sim_time_s": 60300.0,
        "end_sim_time_s": 60315.0,
        "peak_unserved_mw": 5.328277620981893
      },
      {
        "start_sim_time_s": 66650.0,
        "end_sim_time_s": 66680.0,
        "peak_unserved_mw": 33.2463089774655
      },
      {
        "start_sim_time_s": 67040.0,
        "end_sim_time_s": 67055.0,
        "peak_unserved_mw": 3.1841012001148385
      },
      {
        "start_sim_time_s": 67500.0,
        "end_sim_time_s": 67515.0,
        "peak_unserved_mw": 5.294020684052754
      }
    ],
    "energy_balance": {
      "closure_status": true,
      "max_abs_physical_ledger_defect_mw": 0.0,
      "served_demand_mwh": 367.781736493,
      "unserved_demand_mwh": 0.894372986
    },
    "bess_soc_min": 0.828342155,
    "bess_soc_max": 0.999999999,
    "bess_soc_final": 0.999999998,
    "commitment": {
      "distinct_event_count": 48,
      "visible_distinct_event_count": 48,
      "suppressed_repeat_count": 0,
      "log_complete": true,
      "omitted_record_count": 0,
      "reserve_floor_refusal_count": 0,
      "reserve_floor_distinct_event_count": 0,
      "reserve_floor_visible_distinct_event_count": 0,
      "reserve_floor_suppressed_repeat_count": 0,
      "reserve_floor_log_complete": true,
      "reserve_floor_omitted_record_count": 0,
      "same_unit_restart_within_min_down_window_count": 0
    },
    "forecast": {
      "miss_count": 0,
      "miss_peak_mw": 0.0
    },
    "compute_trace_sha256": "916eb28339ae921141941a8c90069e573e80ef4bf65f2be39cc3e45b8747ccff",
    "compute_trace_count": 17280,
    "daily_breakdown": [
      {
        "day": 1,
        "kind": "weekday",
        "fuel_by_component_mmbtu": {
          "load_fuel_mmbtu": 5847.168216351,
          "no_load_fuel_mmbtu": 72.43,
          "hot_standby_fuel_mmbtu": 4.142013889,
          "start_fuel_mmbtu": 116.0
        },
        "fuel_mmbtu": 6039.74023024,
        "unserved_mwh": 0.894372986,
        "curtailed_mwh": 187.690139189,
        "bess_soc_end": 0.999999998
      }
    ],
    "constraints_valid": true,
    "hard_violations": []
  },
  "base_final_floor_basis": null,
  "candidate_final_floor_basis": {
    "bess-0": {
      "bess_id": "bess-0",
      "floor_mwh": 12.5,
      "depth_reserve_mwh": 0.0,
      "diesel_floor_mwh": 0.0,
      "d2r_term_mwh": 12.5,
      "winning_term": "d2r_bridge",
      "basis": "offline_restart",
      "unit_id": "gt-hot-01",
      "eligibility_wait_s": 0.0,
      "start_duration_s": 600.0,
      "thermal_state": "cold",
      "eligibility_reason": "eligible"
    }
  },
  "physical_identical": true,
  "compact_identical": true,
  "metrics_identical": true
}
```

### scenario-h1-k8s-ray-24h / informed
```json
{
  "base_physical_sha256": "60430dc7631204990acc39213cbcbeba8636b71a05d23c1a101c6c5faee71ef9",
  "candidate_physical_sha256": "60430dc7631204990acc39213cbcbeba8636b71a05d23c1a101c6c5faee71ef9",
  "base_compact_sha256": "19c2420ea61da37cb73fd2187495dad781f1e4de10766f988347894fe671c4e2",
  "candidate_compact_sha256": "19c2420ea61da37cb73fd2187495dad781f1e4de10766f988347894fe671c4e2",
  "before_metrics": {
    "tick_count": 17280,
    "interval_seconds": 5.0,
    "fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 5660.766981827,
      "no_load_fuel_mmbtu": 68.021666667,
      "hot_standby_fuel_mmbtu": 4.110069444,
      "start_fuel_mmbtu": 116.0
    },
    "turbine_fuel_mmbtu": 5848.898717938,
    "fuel_reconciled": true,
    "start_fuel_reconciliation": {
      "release_charged": true,
      "recorded_event_count": 12,
      "measured_event_count": 12,
      "measured_start_fuel_mmbtu": 116.0,
      "tier_sum_mmbtu": null,
      "passed": true
    },
    "dispatch_curtailment_mwh": 176.779572526,
    "dispatch_curtailment_interval_exposure_fuel_mmbtu": 3120.455542377,
    "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 3076.704847933,
      "no_load_fuel_mmbtu": 39.875,
      "hot_standby_fuel_mmbtu": 3.875694444,
      "start_fuel_mmbtu": 0.0
    },
    "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
      "gt-spin-01": 1517.310386732,
      "gt-spin-02": 1515.555086201,
      "gt-hot-01": 64.949375,
      "gt-hot-02": 22.640694444
    },
    "dispatch_curtailment_attributable_fuel_mmbtu": 1858.026440381,
    "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
      "gt-spin-01": 911.921257907,
      "gt-spin-02": 911.395881109,
      "gt-hot-01": 32.505522721,
      "gt-hot-02": 2.203778644
    },
    "unserved_mwh": 0.124133405,
    "peak_unserved_mw": 20.746308977,
    "served_mwh": 368.551976074,
    "unserved_intervals": [
      {
        "start_sim_time_s": 30650.0,
        "end_sim_time_s": 30660.0,
        "peak_unserved_mw": 3.783533866069419
      },
      {
        "start_sim_time_s": 36030.0,
        "end_sim_time_s": 36040.0,
        "peak_unserved_mw": 4.552312656116847
      },
      {
        "start_sim_time_s": 37850.0,
        "end_sim_time_s": 37865.0,
        "peak_unserved_mw": 6.706977469665091
      },
      {
        "start_sim_time_s": 45050.0,
        "end_sim_time_s": 45060.0,
        "peak_unserved_mw": 14.968336793567588
      },
      {
        "start_sim_time_s": 52250.0,
        "end_sim_time_s": 52260.0,
        "peak_unserved_mw": 6.873673087220638
      },
      {
        "start_sim_time_s": 57630.0,
        "end_sim_time_s": 57635.0,
        "peak_unserved_mw": 0.7155264052397072
      },
      {
        "start_sim_time_s": 66650.0,
        "end_sim_time_s": 66670.0,
        "peak_unserved_mw": 20.746308977465503
      }
    ],
    "energy_balance": {
      "closure_status": true,
      "max_abs_physical_ledger_defect_mw": 0.0,
      "served_demand_mwh": 368.551976074,
      "unserved_demand_mwh": 0.124133405
    },
    "bess_soc_min": 0.877673489,
    "bess_soc_max": 0.999999999,
    "bess_soc_final": 0.999999989,
    "commitment": {
      "distinct_event_count": 59,
      "visible_distinct_event_count": 59,
      "suppressed_repeat_count": 14027,
      "log_complete": true,
      "omitted_record_count": 0,
      "reserve_floor_refusal_count": 16340,
      "reserve_floor_distinct_event_count": 16338,
      "reserve_floor_visible_distinct_event_count": 16338,
      "reserve_floor_suppressed_repeat_count": 2,
      "reserve_floor_log_complete": true,
      "reserve_floor_omitted_record_count": 0,
      "same_unit_restart_within_min_down_window_count": 0
    },
    "forecast": {
      "miss_count": 0,
      "miss_peak_mw": 0.0
    },
    "compute_trace_sha256": "916eb28339ae921141941a8c90069e573e80ef4bf65f2be39cc3e45b8747ccff",
    "compute_trace_count": 17280,
    "daily_breakdown": [
      {
        "day": 1,
        "kind": "weekday",
        "fuel_by_component_mmbtu": {
          "load_fuel_mmbtu": 5660.766981827,
          "no_load_fuel_mmbtu": 68.021666667,
          "hot_standby_fuel_mmbtu": 4.110069444,
          "start_fuel_mmbtu": 116.0
        },
        "fuel_mmbtu": 5848.898717938,
        "unserved_mwh": 0.124133405,
        "curtailed_mwh": 176.779572526,
        "bess_soc_end": 0.999999989
      }
    ],
    "constraints_valid": true,
    "hard_violations": []
  },
  "after_metrics": {
    "tick_count": 17280,
    "interval_seconds": 5.0,
    "fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 5660.766981827,
      "no_load_fuel_mmbtu": 68.021666667,
      "hot_standby_fuel_mmbtu": 4.110069444,
      "start_fuel_mmbtu": 116.0
    },
    "turbine_fuel_mmbtu": 5848.898717938,
    "fuel_reconciled": true,
    "start_fuel_reconciliation": {
      "release_charged": true,
      "recorded_event_count": 12,
      "measured_event_count": 12,
      "measured_start_fuel_mmbtu": 116.0,
      "tier_sum_mmbtu": null,
      "passed": true
    },
    "dispatch_curtailment_mwh": 176.779572526,
    "dispatch_curtailment_interval_exposure_fuel_mmbtu": 3120.455542377,
    "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 3076.704847933,
      "no_load_fuel_mmbtu": 39.875,
      "hot_standby_fuel_mmbtu": 3.875694444,
      "start_fuel_mmbtu": 0.0
    },
    "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
      "gt-spin-01": 1517.310386732,
      "gt-spin-02": 1515.555086201,
      "gt-hot-01": 64.949375,
      "gt-hot-02": 22.640694444
    },
    "dispatch_curtailment_attributable_fuel_mmbtu": 1858.026440381,
    "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
      "gt-spin-01": 911.921257907,
      "gt-spin-02": 911.395881109,
      "gt-hot-01": 32.505522721,
      "gt-hot-02": 2.203778644
    },
    "unserved_mwh": 0.124133405,
    "peak_unserved_mw": 20.746308977,
    "served_mwh": 368.551976074,
    "unserved_intervals": [
      {
        "start_sim_time_s": 30650.0,
        "end_sim_time_s": 30660.0,
        "peak_unserved_mw": 3.783533866069419
      },
      {
        "start_sim_time_s": 36030.0,
        "end_sim_time_s": 36040.0,
        "peak_unserved_mw": 4.552312656116847
      },
      {
        "start_sim_time_s": 37850.0,
        "end_sim_time_s": 37865.0,
        "peak_unserved_mw": 6.706977469665091
      },
      {
        "start_sim_time_s": 45050.0,
        "end_sim_time_s": 45060.0,
        "peak_unserved_mw": 14.968336793567588
      },
      {
        "start_sim_time_s": 52250.0,
        "end_sim_time_s": 52260.0,
        "peak_unserved_mw": 6.873673087220638
      },
      {
        "start_sim_time_s": 57630.0,
        "end_sim_time_s": 57635.0,
        "peak_unserved_mw": 0.7155264052397072
      },
      {
        "start_sim_time_s": 66650.0,
        "end_sim_time_s": 66670.0,
        "peak_unserved_mw": 20.746308977465503
      }
    ],
    "energy_balance": {
      "closure_status": true,
      "max_abs_physical_ledger_defect_mw": 0.0,
      "served_demand_mwh": 368.551976074,
      "unserved_demand_mwh": 0.124133405
    },
    "bess_soc_min": 0.877673489,
    "bess_soc_max": 0.999999999,
    "bess_soc_final": 0.999999989,
    "commitment": {
      "distinct_event_count": 59,
      "visible_distinct_event_count": 59,
      "suppressed_repeat_count": 14027,
      "log_complete": true,
      "omitted_record_count": 0,
      "reserve_floor_refusal_count": 16340,
      "reserve_floor_distinct_event_count": 16338,
      "reserve_floor_visible_distinct_event_count": 16338,
      "reserve_floor_suppressed_repeat_count": 2,
      "reserve_floor_log_complete": true,
      "reserve_floor_omitted_record_count": 0,
      "same_unit_restart_within_min_down_window_count": 0
    },
    "forecast": {
      "miss_count": 0,
      "miss_peak_mw": 0.0
    },
    "compute_trace_sha256": "916eb28339ae921141941a8c90069e573e80ef4bf65f2be39cc3e45b8747ccff",
    "compute_trace_count": 17280,
    "daily_breakdown": [
      {
        "day": 1,
        "kind": "weekday",
        "fuel_by_component_mmbtu": {
          "load_fuel_mmbtu": 5660.766981827,
          "no_load_fuel_mmbtu": 68.021666667,
          "hot_standby_fuel_mmbtu": 4.110069444,
          "start_fuel_mmbtu": 116.0
        },
        "fuel_mmbtu": 5848.898717938,
        "unserved_mwh": 0.124133405,
        "curtailed_mwh": 176.779572526,
        "bess_soc_end": 0.999999989
      }
    ],
    "constraints_valid": true,
    "hard_violations": []
  },
  "base_final_floor_basis": null,
  "candidate_final_floor_basis": {
    "bess-0": {
      "bess_id": "bess-0",
      "floor_mwh": 12.5,
      "depth_reserve_mwh": 0.0,
      "diesel_floor_mwh": 0.0,
      "d2r_term_mwh": 12.5,
      "winning_term": "d2r_bridge",
      "basis": "offline_restart",
      "unit_id": "gt-hot-01",
      "eligibility_wait_s": 0.0,
      "start_duration_s": 600.0,
      "thermal_state": "cold",
      "eligibility_reason": "eligible"
    }
  },
  "physical_identical": true,
  "compact_identical": true,
  "metrics_identical": true
}
```

### scenario-h2-slurm-24h / baseline
```json
{
  "base_physical_sha256": "f7c8de426e7b1b08650e0980e6ea26d38ce8bf03db2734cd21a18368f413b4a1",
  "candidate_physical_sha256": "f7c8de426e7b1b08650e0980e6ea26d38ce8bf03db2734cd21a18368f413b4a1",
  "base_compact_sha256": "8d0d3037dcaa712ccc34a5f744654af15b8654363911e63566f78467443e8b66",
  "candidate_compact_sha256": "8d0d3037dcaa712ccc34a5f744654af15b8654363911e63566f78467443e8b66",
  "before_metrics": {
    "tick_count": 17280,
    "interval_seconds": 5.0,
    "fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 5136.719001539,
      "no_load_fuel_mmbtu": 65.231666667,
      "hot_standby_fuel_mmbtu": 4.552430556,
      "start_fuel_mmbtu": 124.0
    },
    "turbine_fuel_mmbtu": 5330.503098761,
    "fuel_reconciled": true,
    "start_fuel_reconciliation": {
      "release_charged": true,
      "recorded_event_count": 11,
      "measured_event_count": 11,
      "measured_start_fuel_mmbtu": 124.0,
      "tier_sum_mmbtu": null,
      "passed": true
    },
    "dispatch_curtailment_mwh": 349.917690813,
    "dispatch_curtailment_interval_exposure_fuel_mmbtu": 4838.569627585,
    "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 4712.832474807,
      "no_load_fuel_mmbtu": 61.375,
      "hot_standby_fuel_mmbtu": 4.362152778,
      "start_fuel_mmbtu": 60.0
    },
    "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
      "gt-spin-01": 2130.396041667,
      "gt-spin-02": 2130.396041667,
      "gt-hot-01": 345.279002588,
      "gt-hot-02": 232.498541667
    },
    "dispatch_curtailment_attributable_fuel_mmbtu": 3680.617469434,
    "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
      "gt-spin-01": 1639.723878254,
      "gt-spin-02": 1639.723878254,
      "gt-hot-01": 221.207657519,
      "gt-hot-02": 179.962055406
    },
    "unserved_mwh": 5.011418076,
    "peak_unserved_mw": 44.86838787,
    "served_mwh": 138.948956374,
    "unserved_intervals": [
      {
        "start_sim_time_s": 29125.0,
        "end_sim_time_s": 29410.0,
        "peak_unserved_mw": 38.098732218014646
      },
      {
        "start_sim_time_s": 29450.0,
        "end_sim_time_s": 29460.0,
        "peak_unserved_mw": 4.37595409165764
      },
      {
        "start_sim_time_s": 36310.0,
        "end_sim_time_s": 36415.0,
        "peak_unserved_mw": 40.894865912415625
      },
      {
        "start_sim_time_s": 43510.0,
        "end_sim_time_s": 43620.0,
        "peak_unserved_mw": 41.9036584956214
      },
      {
        "start_sim_time_s": 50710.0,
        "end_sim_time_s": 50815.0,
        "peak_unserved_mw": 40.390845418775996
      },
      {
        "start_sim_time_s": 57910.0,
        "end_sim_time_s": 58025.0,
        "peak_unserved_mw": 44.86838786968556
      },
      {
        "start_sim_time_s": 65110.0,
        "end_sim_time_s": 65215.0,
        "peak_unserved_mw": 40.390845418775996
      }
    ],
    "energy_balance": {
      "closure_status": true,
      "max_abs_physical_ledger_defect_mw": 0.0,
      "served_demand_mwh": 138.948956374,
      "unserved_demand_mwh": 5.011418076
    },
    "bess_soc_min": 0.950386947,
    "bess_soc_max": 0.999999999,
    "bess_soc_final": 0.999999998,
    "commitment": {
      "distinct_event_count": 44,
      "visible_distinct_event_count": 44,
      "suppressed_repeat_count": 0,
      "log_complete": true,
      "omitted_record_count": 0,
      "reserve_floor_refusal_count": 0,
      "reserve_floor_distinct_event_count": 0,
      "reserve_floor_visible_distinct_event_count": 0,
      "reserve_floor_suppressed_repeat_count": 0,
      "reserve_floor_log_complete": true,
      "reserve_floor_omitted_record_count": 0,
      "same_unit_restart_within_min_down_window_count": 0
    },
    "forecast": {
      "miss_count": 0,
      "miss_peak_mw": 0.0
    },
    "compute_trace_sha256": "ea1916a426e67dde51a9a926dc4b64b0c2eb2470ee2e0076fe7f17b8d55f420b",
    "compute_trace_count": 17280,
    "daily_breakdown": [
      {
        "day": 1,
        "kind": "weekday",
        "fuel_by_component_mmbtu": {
          "load_fuel_mmbtu": 5136.719001539,
          "no_load_fuel_mmbtu": 65.231666667,
          "hot_standby_fuel_mmbtu": 4.552430556,
          "start_fuel_mmbtu": 124.0
        },
        "fuel_mmbtu": 5330.503098761,
        "unserved_mwh": 5.011418076,
        "curtailed_mwh": 349.917690813,
        "bess_soc_end": 0.999999998
      }
    ],
    "constraints_valid": true,
    "hard_violations": []
  },
  "after_metrics": {
    "tick_count": 17280,
    "interval_seconds": 5.0,
    "fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 5136.719001539,
      "no_load_fuel_mmbtu": 65.231666667,
      "hot_standby_fuel_mmbtu": 4.552430556,
      "start_fuel_mmbtu": 124.0
    },
    "turbine_fuel_mmbtu": 5330.503098761,
    "fuel_reconciled": true,
    "start_fuel_reconciliation": {
      "release_charged": true,
      "recorded_event_count": 11,
      "measured_event_count": 11,
      "measured_start_fuel_mmbtu": 124.0,
      "tier_sum_mmbtu": null,
      "passed": true
    },
    "dispatch_curtailment_mwh": 349.917690813,
    "dispatch_curtailment_interval_exposure_fuel_mmbtu": 4838.569627585,
    "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 4712.832474807,
      "no_load_fuel_mmbtu": 61.375,
      "hot_standby_fuel_mmbtu": 4.362152778,
      "start_fuel_mmbtu": 60.0
    },
    "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
      "gt-spin-01": 2130.396041667,
      "gt-spin-02": 2130.396041667,
      "gt-hot-01": 345.279002588,
      "gt-hot-02": 232.498541667
    },
    "dispatch_curtailment_attributable_fuel_mmbtu": 3680.617469434,
    "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
      "gt-spin-01": 1639.723878254,
      "gt-spin-02": 1639.723878254,
      "gt-hot-01": 221.207657519,
      "gt-hot-02": 179.962055406
    },
    "unserved_mwh": 5.011418076,
    "peak_unserved_mw": 44.86838787,
    "served_mwh": 138.948956374,
    "unserved_intervals": [
      {
        "start_sim_time_s": 29125.0,
        "end_sim_time_s": 29410.0,
        "peak_unserved_mw": 38.098732218014646
      },
      {
        "start_sim_time_s": 29450.0,
        "end_sim_time_s": 29460.0,
        "peak_unserved_mw": 4.37595409165764
      },
      {
        "start_sim_time_s": 36310.0,
        "end_sim_time_s": 36415.0,
        "peak_unserved_mw": 40.894865912415625
      },
      {
        "start_sim_time_s": 43510.0,
        "end_sim_time_s": 43620.0,
        "peak_unserved_mw": 41.9036584956214
      },
      {
        "start_sim_time_s": 50710.0,
        "end_sim_time_s": 50815.0,
        "peak_unserved_mw": 40.390845418775996
      },
      {
        "start_sim_time_s": 57910.0,
        "end_sim_time_s": 58025.0,
        "peak_unserved_mw": 44.86838786968556
      },
      {
        "start_sim_time_s": 65110.0,
        "end_sim_time_s": 65215.0,
        "peak_unserved_mw": 40.390845418775996
      }
    ],
    "energy_balance": {
      "closure_status": true,
      "max_abs_physical_ledger_defect_mw": 0.0,
      "served_demand_mwh": 138.948956374,
      "unserved_demand_mwh": 5.011418076
    },
    "bess_soc_min": 0.950386947,
    "bess_soc_max": 0.999999999,
    "bess_soc_final": 0.999999998,
    "commitment": {
      "distinct_event_count": 44,
      "visible_distinct_event_count": 44,
      "suppressed_repeat_count": 0,
      "log_complete": true,
      "omitted_record_count": 0,
      "reserve_floor_refusal_count": 0,
      "reserve_floor_distinct_event_count": 0,
      "reserve_floor_visible_distinct_event_count": 0,
      "reserve_floor_suppressed_repeat_count": 0,
      "reserve_floor_log_complete": true,
      "reserve_floor_omitted_record_count": 0,
      "same_unit_restart_within_min_down_window_count": 0
    },
    "forecast": {
      "miss_count": 0,
      "miss_peak_mw": 0.0
    },
    "compute_trace_sha256": "ea1916a426e67dde51a9a926dc4b64b0c2eb2470ee2e0076fe7f17b8d55f420b",
    "compute_trace_count": 17280,
    "daily_breakdown": [
      {
        "day": 1,
        "kind": "weekday",
        "fuel_by_component_mmbtu": {
          "load_fuel_mmbtu": 5136.719001539,
          "no_load_fuel_mmbtu": 65.231666667,
          "hot_standby_fuel_mmbtu": 4.552430556,
          "start_fuel_mmbtu": 124.0
        },
        "fuel_mmbtu": 5330.503098761,
        "unserved_mwh": 5.011418076,
        "curtailed_mwh": 349.917690813,
        "bess_soc_end": 0.999999998
      }
    ],
    "constraints_valid": true,
    "hard_violations": []
  },
  "base_final_floor_basis": null,
  "candidate_final_floor_basis": {
    "bess-0": {
      "bess_id": "bess-0",
      "floor_mwh": 12.5,
      "depth_reserve_mwh": 0.0,
      "diesel_floor_mwh": 0.0,
      "d2r_term_mwh": 12.5,
      "winning_term": "d2r_bridge",
      "basis": "offline_restart",
      "unit_id": "gt-hot-01",
      "eligibility_wait_s": 0.0,
      "start_duration_s": 600.0,
      "thermal_state": "cold",
      "eligibility_reason": "eligible"
    }
  },
  "physical_identical": true,
  "compact_identical": true,
  "metrics_identical": true
}
```

### scenario-h2-slurm-24h / informed
```json
{
  "base_physical_sha256": "b7383d283f09d625f531ecc216b447b868792f50069bbc662b1636d2b988bbfb",
  "candidate_physical_sha256": "b7383d283f09d625f531ecc216b447b868792f50069bbc662b1636d2b988bbfb",
  "base_compact_sha256": "0def2a33daa2770e5095d8cb63b2c5e7d01ab65c85aaf4db3bd732a89623a3c7",
  "candidate_compact_sha256": "0def2a33daa2770e5095d8cb63b2c5e7d01ab65c85aaf4db3bd732a89623a3c7",
  "before_metrics": {
    "tick_count": 17280,
    "interval_seconds": 5.0,
    "fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 5106.733034717,
      "no_load_fuel_mmbtu": 64.855,
      "hot_standby_fuel_mmbtu": 3.761458333,
      "start_fuel_mmbtu": 152.0
    },
    "turbine_fuel_mmbtu": 5327.34949305,
    "fuel_reconciled": true,
    "start_fuel_reconciliation": {
      "release_charged": true,
      "recorded_event_count": 14,
      "measured_event_count": 14,
      "measured_start_fuel_mmbtu": 152.0,
      "tier_sum_mmbtu": null,
      "passed": true
    },
    "dispatch_curtailment_mwh": 342.977539092,
    "dispatch_curtailment_interval_exposure_fuel_mmbtu": 4892.43517635,
    "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 4675.898162461,
      "no_load_fuel_mmbtu": 60.895,
      "hot_standby_fuel_mmbtu": 3.642013889,
      "start_fuel_mmbtu": 152.0
    },
    "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
      "gt-spin-01": 2152.666217898,
      "gt-spin-02": 1708.675833457,
      "gt-hot-01": 737.513194445,
      "gt-hot-02": 293.579930556
    },
    "dispatch_curtailment_attributable_fuel_mmbtu": 3607.524008603,
    "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
      "gt-spin-01": 1645.630131731,
      "gt-spin-02": 1260.841712162,
      "gt-hot-01": 536.782073718,
      "gt-hot-02": 164.270090991
    },
    "unserved_mwh": 0.859772492,
    "peak_unserved_mw": 42.36838787,
    "served_mwh": 143.100601957,
    "unserved_intervals": [
      {
        "start_sim_time_s": 29130.0,
        "end_sim_time_s": 29165.0,
        "peak_unserved_mw": 19.287968405751712
      },
      {
        "start_sim_time_s": 29215.0,
        "end_sim_time_s": 29235.0,
        "peak_unserved_mw": 1.8802011558611156
      },
      {
        "start_sim_time_s": 36310.0,
        "end_sim_time_s": 36350.0,
        "peak_unserved_mw": 38.394865912415625
      },
      {
        "start_sim_time_s": 43510.0,
        "end_sim_time_s": 43555.0,
        "peak_unserved_mw": 39.4036584956214
      },
      {
        "start_sim_time_s": 50710.0,
        "end_sim_time_s": 50725.0,
        "peak_unserved_mw": 26.640845418775996
      },
      {
        "start_sim_time_s": 57910.0,
        "end_sim_time_s": 57940.0,
        "peak_unserved_mw": 42.36838786968556
      },
      {
        "start_sim_time_s": 65110.0,
        "end_sim_time_s": 65140.0,
        "peak_unserved_mw": 37.890845418775996
      }
    ],
    "energy_balance": {
      "closure_status": true,
      "max_abs_physical_ledger_defect_mw": 0.0,
      "served_demand_mwh": 143.100601957,
      "unserved_demand_mwh": 0.859772492
    },
    "bess_soc_min": 0.950386947,
    "bess_soc_max": 0.999999998,
    "bess_soc_final": 0.999999987,
    "commitment": {
      "distinct_event_count": 65,
      "visible_distinct_event_count": 65,
      "suppressed_repeat_count": 11198,
      "log_complete": true,
      "omitted_record_count": 0,
      "reserve_floor_refusal_count": 14904,
      "reserve_floor_distinct_event_count": 14904,
      "reserve_floor_visible_distinct_event_count": 14904,
      "reserve_floor_suppressed_repeat_count": 0,
      "reserve_floor_log_complete": true,
      "reserve_floor_omitted_record_count": 0,
      "same_unit_restart_within_min_down_window_count": 0
    },
    "forecast": {
      "miss_count": 39,
      "miss_peak_mw": 13.130749227
    },
    "compute_trace_sha256": "ea1916a426e67dde51a9a926dc4b64b0c2eb2470ee2e0076fe7f17b8d55f420b",
    "compute_trace_count": 17280,
    "daily_breakdown": [
      {
        "day": 1,
        "kind": "weekday",
        "fuel_by_component_mmbtu": {
          "load_fuel_mmbtu": 5106.733034717,
          "no_load_fuel_mmbtu": 64.855,
          "hot_standby_fuel_mmbtu": 3.761458333,
          "start_fuel_mmbtu": 152.0
        },
        "fuel_mmbtu": 5327.34949305,
        "unserved_mwh": 0.859772492,
        "curtailed_mwh": 342.977539092,
        "bess_soc_end": 0.999999987
      }
    ],
    "constraints_valid": true,
    "hard_violations": []
  },
  "after_metrics": {
    "tick_count": 17280,
    "interval_seconds": 5.0,
    "fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 5106.733034717,
      "no_load_fuel_mmbtu": 64.855,
      "hot_standby_fuel_mmbtu": 3.761458333,
      "start_fuel_mmbtu": 152.0
    },
    "turbine_fuel_mmbtu": 5327.34949305,
    "fuel_reconciled": true,
    "start_fuel_reconciliation": {
      "release_charged": true,
      "recorded_event_count": 14,
      "measured_event_count": 14,
      "measured_start_fuel_mmbtu": 152.0,
      "tier_sum_mmbtu": null,
      "passed": true
    },
    "dispatch_curtailment_mwh": 342.977539092,
    "dispatch_curtailment_interval_exposure_fuel_mmbtu": 4892.43517635,
    "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 4675.898162461,
      "no_load_fuel_mmbtu": 60.895,
      "hot_standby_fuel_mmbtu": 3.642013889,
      "start_fuel_mmbtu": 152.0
    },
    "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
      "gt-spin-01": 2152.666217898,
      "gt-spin-02": 1708.675833457,
      "gt-hot-01": 737.513194445,
      "gt-hot-02": 293.579930556
    },
    "dispatch_curtailment_attributable_fuel_mmbtu": 3607.524008603,
    "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
      "gt-spin-01": 1645.630131731,
      "gt-spin-02": 1260.841712162,
      "gt-hot-01": 536.782073718,
      "gt-hot-02": 164.270090991
    },
    "unserved_mwh": 0.859772492,
    "peak_unserved_mw": 42.36838787,
    "served_mwh": 143.100601957,
    "unserved_intervals": [
      {
        "start_sim_time_s": 29130.0,
        "end_sim_time_s": 29165.0,
        "peak_unserved_mw": 19.287968405751712
      },
      {
        "start_sim_time_s": 29215.0,
        "end_sim_time_s": 29235.0,
        "peak_unserved_mw": 1.8802011558611156
      },
      {
        "start_sim_time_s": 36310.0,
        "end_sim_time_s": 36350.0,
        "peak_unserved_mw": 38.394865912415625
      },
      {
        "start_sim_time_s": 43510.0,
        "end_sim_time_s": 43555.0,
        "peak_unserved_mw": 39.4036584956214
      },
      {
        "start_sim_time_s": 50710.0,
        "end_sim_time_s": 50725.0,
        "peak_unserved_mw": 26.640845418775996
      },
      {
        "start_sim_time_s": 57910.0,
        "end_sim_time_s": 57940.0,
        "peak_unserved_mw": 42.36838786968556
      },
      {
        "start_sim_time_s": 65110.0,
        "end_sim_time_s": 65140.0,
        "peak_unserved_mw": 37.890845418775996
      }
    ],
    "energy_balance": {
      "closure_status": true,
      "max_abs_physical_ledger_defect_mw": 0.0,
      "served_demand_mwh": 143.100601957,
      "unserved_demand_mwh": 0.859772492
    },
    "bess_soc_min": 0.950386947,
    "bess_soc_max": 0.999999998,
    "bess_soc_final": 0.999999987,
    "commitment": {
      "distinct_event_count": 65,
      "visible_distinct_event_count": 65,
      "suppressed_repeat_count": 11198,
      "log_complete": true,
      "omitted_record_count": 0,
      "reserve_floor_refusal_count": 14904,
      "reserve_floor_distinct_event_count": 14904,
      "reserve_floor_visible_distinct_event_count": 14904,
      "reserve_floor_suppressed_repeat_count": 0,
      "reserve_floor_log_complete": true,
      "reserve_floor_omitted_record_count": 0,
      "same_unit_restart_within_min_down_window_count": 0
    },
    "forecast": {
      "miss_count": 39,
      "miss_peak_mw": 13.130749227
    },
    "compute_trace_sha256": "ea1916a426e67dde51a9a926dc4b64b0c2eb2470ee2e0076fe7f17b8d55f420b",
    "compute_trace_count": 17280,
    "daily_breakdown": [
      {
        "day": 1,
        "kind": "weekday",
        "fuel_by_component_mmbtu": {
          "load_fuel_mmbtu": 5106.733034717,
          "no_load_fuel_mmbtu": 64.855,
          "hot_standby_fuel_mmbtu": 3.761458333,
          "start_fuel_mmbtu": 152.0
        },
        "fuel_mmbtu": 5327.34949305,
        "unserved_mwh": 0.859772492,
        "curtailed_mwh": 342.977539092,
        "bess_soc_end": 0.999999987
      }
    ],
    "constraints_valid": true,
    "hard_violations": []
  },
  "base_final_floor_basis": null,
  "candidate_final_floor_basis": {
    "bess-0": {
      "bess_id": "bess-0",
      "floor_mwh": 12.5,
      "depth_reserve_mwh": 0.0,
      "diesel_floor_mwh": 0.0,
      "d2r_term_mwh": 12.5,
      "winning_term": "d2r_bridge",
      "basis": "offline_restart",
      "unit_id": "gt-hot-01",
      "eligibility_wait_s": 0.0,
      "start_duration_s": 600.0,
      "thermal_state": "cold",
      "eligibility_reason": "eligible"
    }
  },
  "physical_identical": true,
  "compact_identical": true,
  "metrics_identical": true
}
```

## P4 / full suite, real package
```json
{
  "pytest_exit_code": 1,
  "counts": {
    "tests": 2227,
    "failures": 15,
    "errors": 0,
    "skipped": 26,
    "passed": 2186
  },
  "added": [],
  "removed": [],
  "remaining": [
    "tests/test_13_3_frequency.py::TestI4DeliveryFaultMovesFrequency::test_I4_delivery_fault_causes_frequency_deviation",
    "tests/test_13_5_criteria.py::TestR4PMinStable::test_R4_fields_present_on_turbine_config",
    "tests/test_artifact_truncation.py::test_tc173_executor_run_validates_from_truncated_record_and_sidecar",
    "tests/test_diesel_phase3.py::test_live_diesel_is_less_aggressive_than_disabled_before_curtailment",
    "tests/test_diesel_setpoint_gap.py::test_hybrid_covered_demand_does_not_release_bess_reserve",
    "tests/test_fabric_scenarios_e2e.py::test_fabric_scenario_names",
    "tests/test_forecast_path.py::TestDispatchTruthfulness::test_B1a_islanded_delivery_fault_visible_in_delivery_channel",
    "tests/test_fuel_cell_phase2.py::test_fixed_target_survives_a_step_load_and_output_remains_rate_limited",
    "tests/test_gridley.py::test_gridley_logs_no_match_with_question_and_scenario_context",
    "tests/test_gridley.py::test_gridley_retrieves_operator_knowledge_for_natural_variants",
    "tests/test_gridley.py::test_gridley_uses_grounded_operator_benefits_fallback_without_claude",
    "tests/test_kubernetes_scheduler_demo_scenario.py::test_catalogue_demo_constructs_phase_a_scheduler_and_has_real_queue_wait",
    "tests/test_plane_separation.py::TestApiStaticLayer::test_api_gate_clean_api_passes",
    "tests/test_scenario_fc100_islanded_v2.py::test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load",
    "tests/test_unit_trip.py::test_tc84f_demo_20mw_contingency_state_changes_after_trip"
  ],
  "gpu_waiver_as_IMPL_SSH_07": false,
  "passed": true,
  "pytest_summary": "15 failed, 2183 passed, 3 skipped, 23 xfailed, 54 warnings, 3 subtests passed in 757.79s (0:12:37)",
  "counting_note": "Native pytest passed excludes subtests; JUnit passed includes passing subtests and its skipped count includes xfailed cases."
}
```

JUnit is updated after every test in phase4/P4_FULL_SUITE.incremental.xml.
Final native JUnit: phase4/P4_FULL_SUITE_FINAL.xml.
Full stdout: phase4/P4_FULL_SUITE.txt.
Failing IDs: PHASE_4_FAILING_TESTS.txt and phase4/PHASE_4_FAILING_TESTS.txt.
The comparison reference is HOUSEKEEPING_FAILING_TESTS.txt (15 known failures).

## P5 / tracking only, no content change
```json
{
  "commit": "0d40b39b7c708d94ff18ad87146688cc4b242211",
  "files": [
    {
      "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_task_630_100mw_fuel_cell_scenario.py",
      "sha256_before": "9898e80b75e0c4734ae8143de6728ce46a7e6e65d8ef05a8de068f2b9744ca30",
      "size_bytes": 6305,
      "tracked_before": false,
      "sha256_after": "9898e80b75e0c4734ae8143de6728ce46a7e6e65d8ef05a8de068f2b9744ca30",
      "unchanged": true,
      "tracked_after": true
    },
    {
      "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/knowledge/behind-the-meter-market-context.md",
      "sha256_before": "f3b52a3fdfca0f9c7c49ee3bc41e28dcb4a4c349f9e560f4f4ff2411fbf2aa63",
      "size_bytes": 2255,
      "tracked_before": false,
      "sha256_after": "f3b52a3fdfca0f9c7c49ee3bc41e28dcb4a4c349f9e560f4f4ff2411fbf2aa63",
      "unchanged": true,
      "tracked_after": true
    },
    {
      "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/knowledge/gridsignal-operator-benefits.md",
      "sha256_before": "57a098dfe8bc563eb435e6a637284571cee02a0cf4d8f1763944541817fa43ac",
      "size_bytes": 3155,
      "tracked_before": false,
      "sha256_after": "57a098dfe8bc563eb435e6a637284571cee02a0cf4d8f1763944541817fa43ac",
      "unchanged": true,
      "tracked_after": true
    },
    {
      "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/mcp_server/__init__.py",
      "sha256_before": "688a30c32f0fff1ba2a9bbf22054c658c15c54eb6453e145dff7b5e7f5ce5851",
      "size_bytes": 64,
      "tracked_before": false,
      "sha256_after": "688a30c32f0fff1ba2a9bbf22054c658c15c54eb6453e145dff7b5e7f5ce5851",
      "unchanged": true,
      "tracked_after": true
    },
    {
      "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/mcp_server/__main__.py",
      "sha256_before": "f62076518bb1c16c668be4376b6c379087b2f4dd5dc79ddd6b3aca08bf725fe9",
      "size_bytes": 247,
      "tracked_before": false,
      "sha256_after": "f62076518bb1c16c668be4376b6c379087b2f4dd5dc79ddd6b3aca08bf725fe9",
      "unchanged": true,
      "tracked_after": true
    }
  ],
  "gridsignal_db_added": false
}
```

gridsignal.db was not added.

## Implementation, tests, source ranges, commits and git state
```json
{
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py": [
    {
      "start": 1069,
      "end": 1088,
      "added_line_count": 20
    },
    {
      "start": 1106,
      "end": 1108,
      "added_line_count": 3
    }
  ],
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py": [
    {
      "start": 383,
      "end": 391,
      "added_line_count": 9
    },
    {
      "start": 541,
      "end": 629,
      "added_line_count": 89
    }
  ],
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py": [
    {
      "start": 354,
      "end": 356,
      "added_line_count": 3
    },
    {
      "start": 392,
      "end": 400,
      "added_line_count": 9
    },
    {
      "start": 1000,
      "end": 1000,
      "added_line_count": 1
    },
    {
      "start": 2038,
      "end": 2047,
      "added_line_count": 10
    },
    {
      "start": 2049,
      "end": 2056,
      "added_line_count": 8
    },
    {
      "start": 2130,
      "end": 2130,
      "added_line_count": 1
    }
  ],
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/build_warnings.py": [
    {
      "start": 37,
      "end": 41,
      "added_line_count": 5
    }
  ],
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py": [
    {
      "start": 1952,
      "end": 1958,
      "added_line_count": 7
    }
  ],
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_phase2c.py": [
    {
      "start": 54,
      "end": 56,
      "added_line_count": 3
    }
  ],
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_phase4_reserve.py": [
    {
      "start": 1,
      "end": 235,
      "added_line_count": 235
    }
  ]
}
```

Full literal diff: phase4/CANDIDATE_DIFF.patch.
```json
{
  "head_before": "5c8dbf2e899a9be6e9cb31c5ef0eaa9f28e1f027",
  "automatic_checkpoint_note": "5c8dbf2 preceded this resumption and contains documentation only; no automatic application checkpoint was treated as a validated implementation",
  "implementation_commit": "458fdddf8fc1dfd3672ca45c847f86690df95773",
  "implementation_files": [
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py",
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py",
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py",
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/build_warnings.py",
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py"
  ],
  "test_commit": "d3d0e0aeb36a55c6c78e07cd3465f53ff7018102",
  "test_files": [
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_phase4_reserve.py",
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_phase2c.py"
  ],
  "tracking_commit": "0d40b39b7c708d94ff18ad87146688cc4b242211",
  "tracking_files": [
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_task_630_100mw_fuel_cell_scenario.py",
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/knowledge/behind-the-meter-market-context.md",
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/knowledge/gridsignal-operator-benefits.md",
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/mcp_server/__init__.py",
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/mcp_server/__main__.py"
  ],
  "application_status_after_commits": "",
  "main_source_equals_measured_candidate": true,
  "no_scenario_content_change": true,
  "no_publish_deploy_push": true
}
```

The report-only commit hash is supplied in the delivery message, not embedded here
(embedding its own hash would be self-referential).

## Boundaries and durability
No scenario JSON, costs, commitment, eligibility conditions, diesel dispatch,
frequency, protection, or advisory bridge-escalation logic changed.
S10 was run for evidence but its scenario file was not edited.
No publish, deploy, push, or Phase 5 work.
Ticks were streamed to hashes/accumulators; only summaries and bounded windows were saved.
Every retained evidence file is at most 50 MB.

STOP — end of Phase 4.
