# GridSignal Customer Scenarios

**Document status:** Customer-scenario reference document  
**Date:** August 20, 2026  
**Audience:** Customer stakeholders, solutions engineers, operators, product, and engineering  
**Scenario snapshots:** `deliverables/customer-scenarios/`

## Executive summary

GridSignal currently exposes two customer-facing scenarios. They model the same illustrative San Jose, California neutral-colocation GPU data center in two power-system configurations:

1. **Customer Scenario - scenario-equinox-sj-1** — grid-tied operation with a hard 5 MW point-of-common-coupling import ceiling.
2. **Customer Scenario - scenario-turbine-01** — islanded operation with no utility connection and three staged 25 MW gas turbines.

Both scenarios share a mixed GPU estate of Kubernetes/H100, Slurm/H100, and Ray/GB200 scheduler domains. The declared estate represents 16,712 GPUs and 21.9 MW of IT compute demand, or approximately 30.0 MW of facility demand after the configured effective PUE model. Both contain a 30 MW / 60 MWh grid-forming BESS and four 6 MW fuel-cell stacks. The workload profile deliberately starts at 120% demand for ten simulated minutes, then steps down through 100%, 50%, and 10%.

These are **synthetic customer archetypes and advisory simulations**. They are not validated digital twins of a particular Equinix facility or any other live customer site. The San Jose location, Equinix PUE reference, hardware values, workload events, and generation assets are scenario assumptions unless separately validated with customer data.

## Product boundary

The scenarios demonstrate GridSignal’s workload-aware power-operations loop: scheduler-shaped workload intent is translated into compute demand, cooling response, generation/storage behavior, reserve, capacity pressure, and operator-facing explanations.

The current simulator does not connect to live Kubernetes, Slurm, Ray, PMS, BMS, SCADA, relay, utility, or market systems. It does not send production commands, perform certified protection, guarantee uptime, or replace an EMS/PMS, BMS, scheduler, protection relay, or operator. A production customer deployment would require read-only integrations, site-specific calibration, measured telemetry, security controls, tenant isolation, and a separate safety case before any southbound control path.

## Shared data-center model

### Site and operating envelope

| Attribute | Value | Interpretation |
|---|---|---|
| Site | San Jose, CA, USA | Scenario location/archetype; not validated telemetry |
| Coordinates | 37.3382, -121.8863 | Geographic metadata |
| UTC offset | -8 hours | Local-time metadata |
| Colocation model | Neutral colocation | Independent scheduler domains share the facility |
| Simulation horizon | 3,600 seconds | One simulated hour |
| Physics cadence | 5 simulated seconds | Playback affects wall-clock pacing only |
| Solar | 0 MW | No solar contribution in either scenario |
| Calibration flag | false | Neither scenario is customer-calibrated |

The facility is modeled as a neutral-colocation GPU campus rather than one undifferentiated compute load. Work is split between three scheduler domains, each with its own workload share, hardware type, capacity unit, admission bounds, job timing, and deterministic random seed.

### Compute fleet

| Cluster | Scheduler | Hardware | Fleet limit | Capacity unit | GPUs | IT power basis |
|---|---|---|---:|---|---:|---:|
| sj1-k8s-h100 | Kubernetes | H100-class 8-GPU air-cooled node | 950 | node | 7,600 | 9.69 MW at 10.2 kW/node |
| sj1-slurm-h100 | Slurm | H100-class 8-GPU air-cooled node | 950 | node | 7,600 | 9.69 MW at 10.2 kW/node |
| sj1-ray-gb200 | Ray | GB200 NVL72-class liquid-cooled rack | 21 | rack | 1,512 | 2.52 MW at 120 kW/rack |
| **Total** |  |  | **1,921 units** | mixed | **16,712** | **21.90 MW IT** |

The two H100 partitions contain 1,900 nodes × 8 GPUs = 15,200 GPUs and 19.38 MW of IT demand. The Ray partition contains 21 racks × 72 GPUs = 1,512 GPUs and 2.52 MW. Together they produce the declared 21.90 MW IT target.

The facility target is approximately 30.0 MW at the modeled effective PUE of approximately 1.37:

- 21.90 MW IT × 1.37 ≈ 30.00 MW facility demand.
- The JSON expresses the calibration with `pue_base` 1.074 and `alpha_max` 0.276.
- The scenario description says the 1.37 target references Equinix’s disclosed 2025 global portfolio average and assumes an 80% cooling / 20% non-cooling split. That split is an industry-average estimate, not a San Jose-specific measurement.

The simulator separates IT demand from facility demand and applies a delayed cooling response using a 20-second thermal time constant and 90-second thermal update interval. This is important during GPU ramps, but it remains synthetic until compared with measured facility telemetry.

### Scheduler behavior and constraints

Kubernetes and Slurm each use a 42.5% workload share, 950-node maximum, 200-node minimum, 45-second mean interarrival, 200-node mean job size, 80-node standard deviation, 50–300 node job bounds, 30–300 second job duration, 10-second reorder window, 2-second NTP jitter, and independent deterministic seeds 42 and 1042.

Ray uses a 15% share, a 21-rack physical fleet, a 3-rack minimum, a 5-rack mean job size, 2-rack standard deviation, 1–42 rack policy range, the `nextgen_rack_liquid` profile, and seed 2042. The 42-rack policy ceiling intentionally exceeds the physical 21-rack fleet, so the runtime fleet remains the binding limit.

### Workload timeline

| Simulated time | GPU load multiplier | Purpose |
|---:|---:|---|
| 0 s | 120% | Stress ramp; first ten minutes |
| 600 s | 100% | Nominal target |
| 720 s | 50% | Load reduction |
| 2,400 s | 10% | Low-load phase |

Both JSON files also configure 13 deterministic 60-second Kubernetes validation bursts at 900 seconds, each marked with a scenario-specific label and 2,142 GPUs. These are simulator stimuli, not live scheduler traces or a claim of 13 simultaneous customer jobs. Runtime admission, fleet, and power constraints govern active load.

The generator defaults are 3 jobs/minute, non-burst mode, tenant weights 42.5% / 42.5% / 15%, job-size weights 30% / 50% / 20%, a maximum of 12 jobs per tenant, and 60–240 second generated job durations. The generator tenant contracts of 1.4, 1.0, and 0.6 MW are illustrative ceilings, not customer contracts.

## Shared power-system model

### BESS

Each scenario has one autonomous, grid-forming BESS rated at 30 MW with 60 MWh usable energy, 95% initial SoC, and a 1 MW anchor reserve. Normal dispatch is limited to a 3-percentage-point SoC drop, nominally 95% to 92%, preserving the remainder for an emergency that normal generation and grid resources cannot cover. This is a simulator operating policy, not a battery warranty or customer operating procedure.

When demand falls, GridSignal follows the implemented BESS-first surplus policy: it accepts charge when physical charge acceptance is available before running down surplus thermal generation. Turbine rundown additionally respects reserve, minimum-run, sequential-stop, and breaker-settling safeguards.

### Fuel cells

Both scenarios enable four fuel-cell stacks rated at 6 MW each, for 24 MW total. In the islanded scenario, 80% of the fleet is the turbine-commit threshold:

**0.80 × 24 MW = 19.2 MW actual fuel-cell output.**

At that rising-edge threshold, exactly one standby turbine is committed from the hottest available tier. This threshold is a modeled control rule, not a claim about a real fuel-cell fleet’s fuel, degradation, maintenance, emissions, or start behavior.

## Customer Scenario 1: grid-tied San Jose site

`scenario-equinox-sj-1` demonstrates a grid-connected neutral-colocation facility with constrained utility import. It tests whether workload-aware forecasting can explain the consequences of a GPU ramp when only a small amount of utility power is available.

| Resource | Configuration |
|---|---|
| Grid | Connected; island mode false |
| PCC import limit | 5.0 MW |
| Procurement | 5.0 MW firm available; no reserved or non-firm availability |
| Fuel cells | 4 × 6 MW = 24 MW |
| Gas turbines | None |
| Solar | 0 MW |
| BESS | 30 MW / 60 MWh, 95% initial SoC |
| Price curve | Deterministic seed 42 |

The 5 MW PCC limit is intentionally much smaller than the approximately 30 MW facility demand at the peak target. The scenario therefore exercises local generation, BESS policy, visible headroom, and unserved-demand behavior instead of allowing unlimited grid import to hide the shortfall. At the 120% opening phase, fuel cells and grid import contribute only within their limits. The BESS can bridge normal demand only within its 3-point SoC budget. As demand falls through the later phases, BESS-first charging and surplus handling become observable.

## Customer Scenario 2: islanded San Jose microgrid

`scenario-turbine-01` uses the same compute estate, workload, BESS, fuel cells, PUE, and one-hour horizon but removes the utility connection. It tests reserve commitment and safe rundown in an islanded high-density GPU microgrid.

| Asset | Thermal state | Rated power | Ramp rate | Minimum stable output | Minimum run | Minimum down |
|---|---|---:|---:|---:|---:|---:|
| gt-hot-01 | hot | 25 MW | 0.2 MW/s | 10 MW (40%) | 1,800 s | 900 s |
| gt-warm-01 | warm | 25 MW | 0.2 MW/s | 10 MW (40%) | 1,800 s | 900 s |
| gt-cold-01 | cold | 25 MW | 0.2 MW/s | 10 MW (40%) | 1,800 s | 900 s |

All three turbines start off-bus. Their hot, warm, and cold labels are meaningful reserve state. Commitment selects hot, then warm, then cold. Ordinary commitment must not consume protected hot standby. At 19.2 MW actual fuel-cell output, exactly one turbine is committed and the remaining labels are advanced to preserve one hot and one warm standby whenever enough units remain.

The JSON leaves explicit start-delay fields null; modeled behavior is driven by thermal state, ramp, minimum stable load, minimum-run, minimum-down, and commitment logic. These fields are not validated manufacturer start curves. When demand falls, the system first tests physical BESS charge acceptance. Only when the BESS cannot absorb the surplus, and when reserve and minimum-run/sequential-stop/settling rules permit, does controlled unload and stop proceed.

## Direct comparison

| Dimension | Grid-tied scenario | Islanded scenario |
|---|---|---|
| Public label | Customer Scenario - scenario-equinox-sj-1 | Customer Scenario - scenario-turbine-01 |
| Compute estate | 16,712 GPUs / 21.9 MW IT | Same |
| Facility target | Approximately 30 MW at modeled PUE | Same |
| Utility | Connected | None |
| Import limit | 5 MW PCC ceiling | Not applicable |
| BESS | 30 MW / 60 MWh | Same |
| Fuel cells | 24 MW | 24 MW |
| Turbines | None | 3 × 25 MW, hot/warm/cold |
| Primary question | Can constrained grid import and local resources cover the forecast? | When and how should reserve turbines be committed and later released? |
| Calibration | false | false |

The paired design isolates the topology and dispatch question while keeping the compute workload model comparable.

## Customer validation requirements

Before using these as a site-specific operational basis, validate or replace:

1. GPU, node, rack, networking, and liquid-cooling power profiles.
2. Real Kubernetes, Slurm, and Ray event semantics, queue latency, admission, and preemption.
3. IT-to-facility PUE by load level, ambient condition, cooling mode, and season.
4. Service, PCC, transformer, switchgear, protection, islanding, and black-start topology.
5. BESS usable energy, SoC limits, reserve policy, acceptance, degradation, and grid-forming responsibilities.
6. Fuel-cell and turbine ramp, start, minimum-load, fuel, maintenance, emissions, and N−1 data.
7. Meter placement, telemetry quality, scheduler timestamps, synchronization, and missing-data handling.
8. The precise meaning of contracted MW: IT, facility, tenant, or PCC capacity.
9. The authoritative system for protection, switching, load shedding, generator commands, and scheduler actions.
10. Historical replay evidence: forecast error, lead time, reserve-alert precision, and operator usefulness.

Until those steps are complete, describe these as synthetic customer scenarios that demonstrate GridSignal behavior—not as validated representations of a live data center.

## Source-file identity

The exact scenario snapshots are included at:

- `deliverables/customer-scenarios/scenario-equinix-sj-1.json`
- `deliverables/customer-scenarios/scenario-turbine-01.json`

The runtime catalogue adds the public prefix Customer Scenario - while preserving the JSON filenames as compatibility/source paths. The complete JSON contents are reproduced below.

# Appendix A — scenario-equinix-sj-1.json

~~~json
{
  "name": "scenario-equinix-sj-1",
  "description": "This grid-tied neutral-colocation scenario preserves the deterministic aggregate arrival timing and job-duration behavior of scenario-kube-peak-overage while splitting the compute estate across independent Kubernetes, Slurm, and Ray clusters. The Kubernetes and Slurm partitions each contain 950 H100-class 8-GPU nodes; the Ray partition contains 21 GB200 NVL72-class 120 kW racks. Together they represent 16,712 GPUs and a 21.9 MW IT compute target (rounded from the declared hardware mix), which becomes approximately 30.0 MW of facility demand at the calibrated effective PUE. Per-cluster job caps are 300 H100 nodes and a 42-rack GB200 policy ceiling, with the Ray fleet's 21-rack capacity remaining the hard runtime limit. The site has a 30 MW / 60 MWh BESS, a 24 MW fuel-cell fleet, and a 5 MW point-of-common-coupling import ceiling. The BESS supplies normal demand only through a 3 percentage-point drop from its configured 95% initial SoC, then retains the remaining charge for an emergency that the fuel-cell fleet and available grid import cannot cover. The pue_base 1.074 and alpha_max 0.276 calibration targets Equinix's disclosed 2025 global portfolio average total PUE of 1.37 using an assumed 80% cooling / 20% non-cooling overhead split; that split is an industry-average estimate, not an Equinix- or SJ-1-specific measurement.",
  "site_name": "San Jose, CA, USA",
  "site_latitude": 37.3382,
  "site_longitude": -121.8863,
  "site_utc_offset_h": -8.0,
  "workload_events": [],
  "hardware_profile_id": "enterprise_8gpu_air",
  "dt_lead_seconds": 0.0,
  "bess_units": [
    {
      "asset_id": "bess-0",
      "rated_mw": 30.0,
      "usable_mwh": 60.0,
      "initial_soc_fraction": 0.95,
      "grid_forming": true,
      "p_anchor_reserve_mw": 1.0,
      "authority_tier": "autonomous"
    }
  ],
  "turbine_units": [],
  "solar_rated_mw": 0.0,
  "fuel_cell_enabled": true,
  "fuel_cell_rated_mw": 6.0,
  "fuel_cell_stack_count": 4,
  "operating_tier": null,
  "edl_calendar_month": null,
  "tenant_budgets": null,
  "operator_response_profile": null,
  "grid_authority_tier": "autonomous",
  "design_peak_load_mw": null,
  "irradiance_steps": [
    [
      0.0,
      1.0
    ]
  ],
  "gpu_load_profile": [
    [
      0.0,
      1.2
    ],
    [
      600.0,
      1.0
    ],
    [
      720.0,
      0.5
    ],
    [
      2400.0,
      0.1
    ]
  ],
  "workload_floor_fraction": null,
  "island_mode": false,
  "grid_import_limit_mw": 5.0,
  "bess_normal_dispatch_depth_fraction": 0.03,
  "frequency_nominal_hz": 60.0,
  "uf_warning_hz": null,
  "ufls_stage1_hz": null,
  "island_collapse_hz": null,
  "of_warning_hz": null,
  "of_trip_hz": null,
  "ufls_stages": null,
  "relay_81u_threshold_hz": null,
  "relay_81u_delay_s": null,
  "power_factor": 0.85,
  "pue_base": 1.074,
  "end_sim_time": 3600.0,
  "demo_description": "## What this scenario simulates\n\nA grid-tied neutral-colocation GPU site with independent Kubernetes/H100, Slurm/H100, and Ray/GB200 NVL72 scheduler clusters, a 21.9 MW IT compute target, approximately 30.0 MW of calibrated facility demand, a 30 MW / 60 MWh battery, a 24 MW fuel-cell array, and a hard 5 MW grid-import ceiling.\n\nThe PUE calibration targets Equinix's disclosed 2025 global portfolio average total PUE of 1.37 using pue_base 1.074 and alpha_max 0.276. Its assumed 80% cooling / 20% non-cooling overhead split is an industry-average estimate, not an Equinix- or SJ-1-specific measurement.\n\n## What to watch\n\n1. Each scheduler cluster enforces its own capacity ceiling.\n2. H100 nodes and GB200 racks retain distinct capacity and GPU-count metadata.\n3. Per-job caps are cluster-specific: 300 H100 nodes or up to 42 GB200 racks by policy, with the Ray fleet capacity remaining the hard runtime bound.\n4. The aggregate fleet contains 16,712 GPUs and rounds to 21.9 MW IT power, while individual generated jobs remain below 7 MW.\n5. The BESS serves normal demand through a three-percentage-point SoC drop (95% to 92%), then fuel cell and capped grid supply normal demand. The preserved BESS charge is released only when those sources cannot cover the load.",
  "default_playback_speed": 1.0,
  "dt_thermal_seconds": 90.0,
  "plant_dt_thermal_seconds": null,
  "alpha_max": 0.276,
  "plant_alpha_max": null,
  "tau_seconds": 20.0,
  "plant_tau_seconds": null,
  "anchor_reserve_pct": 0.0,
  "band_enabled": false,
  "band_pct_calibrated": 0.0,
  "band_mult_uncalibrated": 2.0,
  "band_mult_unmapped_hw": 1.5,
  "pre_staging_config": null,
  "pms_config": null,
  "procurement_config": {
    "firm_available_mw": 5.0,
    "reserved_available_mw": 0.0,
    "non_firm_available_mw": 0.0,
    "price_curve_seed": 42
  },
  "maintenance_config": null,
  "ramp_relaxation_config": null,
  "kube_config": null,
  "kube_clusters": [
    {
      "cluster_id": "sj1-k8s-h100",
      "tenant_id": "K8S-H100",
      "scheduler_type": "K8S",
      "capacity_unit": "node",
      "workload_share": 0.425,
      "hardware_profile_id": "enterprise_8gpu_air",
      "max_nodes": 950,
      "min_nodes": 200,
      "mean_interarrival_s": 45.0,
      "mean_job_nodes": 200,
      "job_node_std": 80.0,
      "min_job_nodes": 50,
      "max_job_nodes": 300,
      "mean_job_duration_s": 300.0,
      "min_job_duration_s": 30.0,
      "reorder_window_s": 10.0,
      "ntp_jitter_s": 2.0,
      "headroom_threshold_mw": 37.0,
      "rng_seed": 42,
      "step_config": null,
      "load_config": null
    },
    {
      "cluster_id": "sj1-slurm-h100",
      "tenant_id": "SLURM-H100",
      "scheduler_type": "SLURM",
      "capacity_unit": "node",
      "workload_share": 0.425,
      "hardware_profile_id": "enterprise_8gpu_air",
      "max_nodes": 950,
      "min_nodes": 200,
      "mean_interarrival_s": 45.0,
      "mean_job_nodes": 200,
      "job_node_std": 80.0,
      "min_job_nodes": 50,
      "max_job_nodes": 300,
      "mean_job_duration_s": 300.0,
      "min_job_duration_s": 30.0,
      "reorder_window_s": 10.0,
      "ntp_jitter_s": 2.0,
      "headroom_threshold_mw": 37.0,
      "rng_seed": 1042,
      "step_config": null,
      "load_config": null
    },
    {
      "cluster_id": "sj1-ray-gb200",
      "tenant_id": "RAY-GB200",
      "scheduler_type": "RAY",
      "capacity_unit": "rack",
      "workload_share": 0.15,
      "hardware_profile_id": "nextgen_rack_liquid",
      "max_nodes": 21,
      "min_nodes": 3,
      "mean_interarrival_s": 45.0,
      "mean_job_nodes": 5,
      "job_node_std": 2.0,
      "min_job_nodes": 1,
      "max_job_nodes": 42,
      "mean_job_duration_s": 300.0,
      "min_job_duration_s": 30.0,
      "reorder_window_s": 10.0,
      "ntp_jitter_s": 2.0,
      "headroom_threshold_mw": 37.0,
      "rng_seed": 2042,
      "step_config": null,
      "load_config": null
    }
  ],
  "load_config": null,
  "ambient_steps": [],
  "cluster_gen_config": null,
  "stressor_gen_config": null,
  "param_sampling_config": null,
  "telemetry_corruption_config": null,
  "generation_block": null,
  "calibrated": false,
  "dq_inject_events": [],
  "solar_origin_utc_hour": null,
  "tenant_events": [
    {
      "tenant_id": "t01",
      "scheduler": "Kubernetes",
      "label": "PCC import validation burst 1/13",
      "gpus": 2142,
      "t_start": 900.0,
      "duration_s": 60.0
    },
    {
      "tenant_id": "t02",
      "scheduler": "Kubernetes",
      "label": "PCC import validation burst 2/13",
      "gpus": 2142,
      "t_start": 900.0,
      "duration_s": 60.0
    },
    {
      "tenant_id": "t03",
      "scheduler": "Kubernetes",
      "label": "PCC import validation burst 3/13",
      "gpus": 2142,
      "t_start": 900.0,
      "duration_s": 60.0
    },
    {
      "tenant_id": "t04",
      "scheduler": "Kubernetes",
      "label": "PCC import validation burst 4/13",
      "gpus": 2142,
      "t_start": 900.0,
      "duration_s": 60.0
    },
    {
      "tenant_id": "t05",
      "scheduler": "Kubernetes",
      "label": "PCC import validation burst 5/13",
      "gpus": 2142,
      "t_start": 900.0,
      "duration_s": 60.0
    },
    {
      "tenant_id": "t06",
      "scheduler": "Kubernetes",
      "label": "PCC import validation burst 6/13",
      "gpus": 2142,
      "t_start": 900.0,
      "duration_s": 60.0
    },
    {
      "tenant_id": "t07",
      "scheduler": "Kubernetes",
      "label": "PCC import validation burst 7/13",
      "gpus": 2142,
      "t_start": 900.0,
      "duration_s": 60.0
    },
    {
      "tenant_id": "t08",
      "scheduler": "Kubernetes",
      "label": "PCC import validation burst 8/13",
      "gpus": 2142,
      "t_start": 900.0,
      "duration_s": 60.0
    },
    {
      "tenant_id": "t09",
      "scheduler": "Kubernetes",
      "label": "PCC import validation burst 9/13",
      "gpus": 2142,
      "t_start": 900.0,
      "duration_s": 60.0
    },
    {
      "tenant_id": "t10",
      "scheduler": "Kubernetes",
      "label": "PCC import validation burst 10/13",
      "gpus": 2142,
      "t_start": 900.0,
      "duration_s": 60.0
    },
    {
      "tenant_id": "t11",
      "scheduler": "Kubernetes",
      "label": "PCC import validation burst 11/13",
      "gpus": 2142,
      "t_start": 900.0,
      "duration_s": 60.0
    },
    {
      "tenant_id": "t12",
      "scheduler": "Kubernetes",
      "label": "PCC import validation burst 12/13",
      "gpus": 2142,
      "t_start": 900.0,
      "duration_s": 60.0
    },
    {
      "tenant_id": "t13",
      "scheduler": "Kubernetes",
      "label": "PCC import validation burst 13/13",
      "gpus": 2142,
      "t_start": 900.0,
      "duration_s": 60.0
    }
  ],
  "generator_config": {
    "ratePerMinute": 3,
    "burstMode": false,
    "burstSize": [
      3,
      8
    ],
    "burstIntervalSeconds": [
      30,
      90
    ],
    "tenantWeights": {
      "a": 0.425,
      "b": 0.425,
      "c": 0.15
    },
    "jobSizes": {
      "small": 0.3,
      "medium": 0.5,
      "large": 0.2
    },
    "maxJobsPerTenant": 12,
    "jobDurationRange": [
      60,
      240
    ],
    "tenantContracts": {
      "a": 1.4,
      "b": 1.0,
      "c": 0.6
    }
  },
  "assertions": [
    {
      "check": "pue_base_in_declared_range"
    }
  ],
  "fabric_scenario_id": null,
  "cascade_commit_fraction": 0.5,
  "ui_bess_rated_mw": 30.0,
  "ui_bess_usable_mwh": 60.0,
  "grid_import_price_per_mwh": null,
  "bess_charge_price_override_per_mwh": null
}~~~

# Appendix B — scenario-turbine-01.json

~~~json
{
  "name": "scenario-turbine-01",
  "description": "This islanded neutral-colocation scenario preserves the deterministic aggregate arrival timing and job-duration behavior of scenario-kube-peak-overage while splitting the compute estate across independent Kubernetes, Slurm, and Ray clusters. The Kubernetes and Slurm partitions each contain 950 H100-class 8-GPU nodes; the Ray partition contains 21 GB200 NVL72-class 120 kW racks. Together they represent 16,712 GPUs and a 21.9 MW IT compute target (rounded from the declared hardware mix), which becomes approximately 30.0 MW of facility demand at the calibrated effective PUE. Per-cluster job caps are 300 H100 nodes and a 42-rack GB200 policy ceiling, with the Ray fleet's 21-rack capacity remaining the hard runtime limit. The site has a 30 MW / 60 MWh BESS, a 24 MW fuel-cell fleet, and three 25 MW gas turbines held off-bus in hot, warm, and cold standby. There is no PCC grid connection or grid-procurement capability. The BESS supplies normal demand only through a 3 percentage-point drop from its configured 95% initial SoC, then retains the remaining charge for an emergency that the on-site fuel-cell and turbine fleet cannot cover. When actual fuel-cell output rises to 80% of its available fleet capacity, the simulator commits exactly one turbine from the hottest available standby tier and promotes the remaining reserve labels to preserve one hot and one warm standby whenever enough units remain. The pue_base 1.074 and alpha_max 0.276 calibration targets Equinix's disclosed 2025 global portfolio average total PUE of 1.37 using an assumed 80% cooling / 20% non-cooling overhead split; that split is an industry-average estimate, not an Equinix- or SJ-1-specific measurement.",
  "site_name": "San Jose, CA, USA",
  "site_latitude": 37.3382,
  "site_longitude": -121.8863,
  "site_utc_offset_h": -8.0,
  "workload_events": [],
  "hardware_profile_id": "enterprise_8gpu_air",
  "dt_lead_seconds": 0.0,
  "bess_units": [
    {
      "asset_id": "bess-0",
      "rated_mw": 30.0,
      "usable_mwh": 60.0,
      "initial_soc_fraction": 0.95,
      "grid_forming": true,
      "p_anchor_reserve_mw": 1.0,
      "authority_tier": "autonomous"
    }
  ],
  "turbine_units": [
    {
      "asset_id": "gt-hot-01",
      "rated_mw": 25.0,
      "r_asset_mw_per_s": 0.2,
      "run_hours_h": null,
      "hot_standby": true,
      "p_min_stable_frac": 0.4,
      "t_min_run_s": 1800.0,
      "min_run_enabled": true,
      "t_min_down_s": 900.0,
      "min_down_enabled": true,
      "cold_start_s": null,
      "warm_start_s": null,
      "hot_start_s": null,
      "thermal_state": "hot",
      "power_factor": null,
      "inertia_constant_s": null,
      "droop_r": null,
      "valve_actuation_tc_s": null,
      "fuel_to_power_tc_s": null,
      "max_instantaneous_load_step_mw": null,
      "authority_tier": "autonomous"
    },
    {
      "asset_id": "gt-warm-01",
      "rated_mw": 25.0,
      "r_asset_mw_per_s": 0.2,
      "run_hours_h": null,
      "hot_standby": true,
      "p_min_stable_frac": 0.4,
      "t_min_run_s": 1800.0,
      "min_run_enabled": true,
      "t_min_down_s": 900.0,
      "min_down_enabled": true,
      "cold_start_s": null,
      "warm_start_s": null,
      "hot_start_s": null,
      "thermal_state": "warm",
      "power_factor": null,
      "inertia_constant_s": null,
      "droop_r": null,
      "valve_actuation_tc_s": null,
      "fuel_to_power_tc_s": null,
      "max_instantaneous_load_step_mw": null,
      "authority_tier": "autonomous"
    },
    {
      "asset_id": "gt-cold-01",
      "rated_mw": 25.0,
      "r_asset_mw_per_s": 0.2,
      "run_hours_h": null,
      "hot_standby": true,
      "p_min_stable_frac": 0.4,
      "t_min_run_s": 1800.0,
      "min_run_enabled": true,
      "t_min_down_s": 900.0,
      "min_down_enabled": true,
      "cold_start_s": null,
      "warm_start_s": null,
      "hot_start_s": null,
      "thermal_state": "cold",
      "power_factor": null,
      "inertia_constant_s": null,
      "droop_r": null,
      "valve_actuation_tc_s": null,
      "fuel_to_power_tc_s": null,
      "max_instantaneous_load_step_mw": null,
      "authority_tier": "autonomous"
    }
  ],
  "solar_rated_mw": 0.0,
  "fuel_cell_enabled": true,
  "fuel_cell_rated_mw": 6.0,
  "fuel_cell_stack_count": 4,
  "fuel_cell_turbine_commit_fraction": 0.8,
  "operating_tier": null,
  "edl_calendar_month": null,
  "tenant_budgets": null,
  "operator_response_profile": null,
  "grid_authority_tier": "autonomous",
  "design_peak_load_mw": null,
  "irradiance_steps": [
    [
      0.0,
      1.0
    ]
  ],
  "gpu_load_profile": [
    [
      0.0,
      1.2
    ],
    [
      600.0,
      1.0
    ],
    [
      720.0,
      0.5
    ],
    [
      2400.0,
      0.1
    ]
  ],
  "workload_floor_fraction": null,
  "island_mode": true,
  "grid_import_limit_mw": null,
  "bess_normal_dispatch_depth_fraction": 0.03,
  "frequency_nominal_hz": 60.0,
  "uf_warning_hz": null,
  "ufls_stage1_hz": null,
  "island_collapse_hz": null,
  "of_warning_hz": null,
  "of_trip_hz": null,
  "ufls_stages": null,
  "relay_81u_threshold_hz": null,
  "relay_81u_delay_s": null,
  "power_factor": 0.85,
  "pue_base": 1.074,
  "end_sim_time": 3600.0,
  "demo_description": "## What this scenario simulates\n\nAn islanded neutral-colocation GPU site with independent Kubernetes/H100, Slurm/H100, and Ray/GB200 NVL72 scheduler clusters, a 21.9 MW IT compute target, approximately 30.0 MW of calibrated facility demand, a 30 MW / 60 MWh battery, a 24 MW fuel-cell array, and three 25 MW off-bus gas turbines in hot, warm, and cold standby. There is no grid connection.\n\nThe PUE calibration targets Equinix's disclosed 2025 global portfolio average total PUE of 1.37 using pue_base 1.074 and alpha_max 0.276. Its assumed 80% cooling / 20% non-cooling overhead split is an industry-average estimate, not an Equinix- or SJ-1-specific measurement.\n\n## What to watch\n\n1. Each scheduler cluster enforces its own capacity ceiling.\n2. H100 nodes and GB200 racks retain distinct capacity and GPU-count metadata.\n3. Per-job caps are cluster-specific: 300 H100 nodes or up to 42 GB200 racks by policy, with the Ray fleet capacity remaining the hard runtime bound.\n4. The aggregate fleet contains 16,712 GPUs and rounds to 21.9 MW IT power, while individual generated jobs remain below 7 MW.\n5. The BESS serves normal demand through a three-percentage-point SoC drop (95% to 92%), then retains its remaining charge for an emergency the on-site fuel-cell and turbine fleet cannot cover.\n6. The gas-turbine fleet begins off-bus with one hot, one warm, and one cold standby unit, illustrating staged on-site reserve availability.\n7. At 19.2 MW of actual fuel-cell output (80% of the 24 MW fleet), exactly one turbine starts from the hottest available standby tier; the remaining reserve labels then advance to retain one hot and one warm standby when two units remain.",
  "default_playback_speed": 1.0,
  "dt_thermal_seconds": 90.0,
  "plant_dt_thermal_seconds": null,
  "alpha_max": 0.276,
  "plant_alpha_max": null,
  "tau_seconds": 20.0,
  "plant_tau_seconds": null,
  "anchor_reserve_pct": 0.0,
  "band_enabled": false,
  "band_pct_calibrated": 0.0,
  "band_mult_uncalibrated": 2.0,
  "band_mult_unmapped_hw": 1.5,
  "pre_staging_config": null,
  "pms_config": null,
  "procurement_config": null,
  "maintenance_config": null,
  "ramp_relaxation_config": null,
  "kube_config": null,
  "kube_clusters": [
    {
      "cluster_id": "sj1-k8s-h100",
      "tenant_id": "K8S-H100",
      "scheduler_type": "K8S",
      "capacity_unit": "node",
      "workload_share": 0.425,
      "hardware_profile_id": "enterprise_8gpu_air",
      "max_nodes": 950,
      "min_nodes": 200,
      "mean_interarrival_s": 45.0,
      "mean_job_nodes": 200,
      "job_node_std": 80.0,
      "min_job_nodes": 50,
      "max_job_nodes": 300,
      "mean_job_duration_s": 300.0,
      "min_job_duration_s": 30.0,
      "reorder_window_s": 10.0,
      "ntp_jitter_s": 2.0,
      "headroom_threshold_mw": 37.0,
      "rng_seed": 42,
      "step_config": null,
      "load_config": null
    },
    {
      "cluster_id": "sj1-slurm-h100",
      "tenant_id": "SLURM-H100",
      "scheduler_type": "SLURM",
      "capacity_unit": "node",
      "workload_share": 0.425,
      "hardware_profile_id": "enterprise_8gpu_air",
      "max_nodes": 950,
      "min_nodes": 200,
      "mean_interarrival_s": 45.0,
      "mean_job_nodes": 200,
      "job_node_std": 80.0,
      "min_job_nodes": 50,
      "max_job_nodes": 300,
      "mean_job_duration_s": 300.0,
      "min_job_duration_s": 30.0,
      "reorder_window_s": 10.0,
      "ntp_jitter_s": 2.0,
      "headroom_threshold_mw": 37.0,
      "rng_seed": 1042,
      "step_config": null,
      "load_config": null
    },
    {
      "cluster_id": "sj1-ray-gb200",
      "tenant_id": "RAY-GB200",
      "scheduler_type": "RAY",
      "capacity_unit": "rack",
      "workload_share": 0.15,
      "hardware_profile_id": "nextgen_rack_liquid",
      "max_nodes": 21,
      "min_nodes": 3,
      "mean_interarrival_s": 45.0,
      "mean_job_nodes": 5,
      "job_node_std": 2.0,
      "min_job_nodes": 1,
      "max_job_nodes": 42,
      "mean_job_duration_s": 300.0,
      "min_job_duration_s": 30.0,
      "reorder_window_s": 10.0,
      "ntp_jitter_s": 2.0,
      "headroom_threshold_mw": 37.0,
      "rng_seed": 2042,
      "step_config": null,
      "load_config": null
    }
  ],
  "load_config": null,
  "ambient_steps": [],
  "cluster_gen_config": null,
  "stressor_gen_config": null,
  "param_sampling_config": null,
  "telemetry_corruption_config": null,
  "generation_block": null,
  "calibrated": false,
  "dq_inject_events": [],
  "solar_origin_utc_hour": null,
  "tenant_events": [
    {
      "tenant_id": "t01",
      "scheduler": "Kubernetes",
      "label": "Turbine reserve validation burst 1/13",
      "gpus": 2142,
      "t_start": 900.0,
      "duration_s": 60.0
    },
    {
      "tenant_id": "t02",
      "scheduler": "Kubernetes",
      "label": "Turbine reserve validation burst 2/13",
      "gpus": 2142,
      "t_start": 900.0,
      "duration_s": 60.0
    },
    {
      "tenant_id": "t03",
      "scheduler": "Kubernetes",
      "label": "Turbine reserve validation burst 3/13",
      "gpus": 2142,
      "t_start": 900.0,
      "duration_s": 60.0
    },
    {
      "tenant_id": "t04",
      "scheduler": "Kubernetes",
      "label": "Turbine reserve validation burst 4/13",
      "gpus": 2142,
      "t_start": 900.0,
      "duration_s": 60.0
    },
    {
      "tenant_id": "t05",
      "scheduler": "Kubernetes",
      "label": "Turbine reserve validation burst 5/13",
      "gpus": 2142,
      "t_start": 900.0,
      "duration_s": 60.0
    },
    {
      "tenant_id": "t06",
      "scheduler": "Kubernetes",
      "label": "Turbine reserve validation burst 6/13",
      "gpus": 2142,
      "t_start": 900.0,
      "duration_s": 60.0
    },
    {
      "tenant_id": "t07",
      "scheduler": "Kubernetes",
      "label": "Turbine reserve validation burst 7/13",
      "gpus": 2142,
      "t_start": 900.0,
      "duration_s": 60.0
    },
    {
      "tenant_id": "t08",
      "scheduler": "Kubernetes",
      "label": "Turbine reserve validation burst 8/13",
      "gpus": 2142,
      "t_start": 900.0,
      "duration_s": 60.0
    },
    {
      "tenant_id": "t09",
      "scheduler": "Kubernetes",
      "label": "Turbine reserve validation burst 9/13",
      "gpus": 2142,
      "t_start": 900.0,
      "duration_s": 60.0
    },
    {
      "tenant_id": "t10",
      "scheduler": "Kubernetes",
      "label": "Turbine reserve validation burst 10/13",
      "gpus": 2142,
      "t_start": 900.0,
      "duration_s": 60.0
    },
    {
      "tenant_id": "t11",
      "scheduler": "Kubernetes",
      "label": "Turbine reserve validation burst 11/13",
      "gpus": 2142,
      "t_start": 900.0,
      "duration_s": 60.0
    },
    {
      "tenant_id": "t12",
      "scheduler": "Kubernetes",
      "label": "Turbine reserve validation burst 12/13",
      "gpus": 2142,
      "t_start": 900.0,
      "duration_s": 60.0
    },
    {
      "tenant_id": "t13",
      "scheduler": "Kubernetes",
      "label": "Turbine reserve validation burst 13/13",
      "gpus": 2142,
      "t_start": 900.0,
      "duration_s": 60.0
    }
  ],
  "generator_config": {
    "ratePerMinute": 3,
    "burstMode": false,
    "burstSize": [
      3,
      8
    ],
    "burstIntervalSeconds": [
      30,
      90
    ],
    "tenantWeights": {
      "a": 0.425,
      "b": 0.425,
      "c": 0.15
    },
    "jobSizes": {
      "small": 0.3,
      "medium": 0.5,
      "large": 0.2
    },
    "maxJobsPerTenant": 12,
    "jobDurationRange": [
      60,
      240
    ],
    "tenantContracts": {
      "a": 1.4,
      "b": 1.0,
      "c": 0.6
    }
  },
  "assertions": [
    {
      "check": "pue_base_in_declared_range"
    }
  ],
  "fabric_scenario_id": null,
  "cascade_commit_fraction": 0.5,
  "ui_bess_rated_mw": 30.0,
  "ui_bess_usable_mwh": 60.0,
  "grid_import_price_per_mwh": null,
  "bess_charge_price_override_per_mwh": null
}~~~

---

## Document limitations

This document summarizes the current simulator configuration and preserves the distinction between implemented behavior, illustrative assumptions, and customer-validated facts. If either JSON source changes, regenerate this document so the narrative and appendices remain synchronized.
