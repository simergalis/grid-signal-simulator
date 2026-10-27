# DR-2026-10-27-GRID-MODE-BESS — Phase 0 baseline report
Evidence-only capture; no application, test, or scenario files were changed. The only files in this commit are under `tools/dr_gmb/phase0/`. Per-tick rows were not exported.

## Step 0 — repository state and pinning
```text
$ git rev-parse HEAD
1f0cb9ef082079b3127bc0d6ae2b511606e9ca3f
$ git status --porcelain (before Phase 0 evidence creation)
(empty)
$ git ls-files P/config/scenarios | grep -c '\.json$'
46
$ git ls-files P/config/scenarios | grep S1
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/S10_mit_supercloud_2021-08-11.json
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/S11_mit_supercloud_2021-08-11_bchydro.json
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/S11b_mit_supercloud_2021-08-11_bchydro_60mw.json
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/S1_baseline_training.json
```
Pinning: seed `1729`, patched wall clock `1792454400.0`; same `pin_spec` convention as `tools/dr_isl/d6f/run_existing_gates.py`.

## 0.1 — Scenario inventory
`ScenarioSpec` validation: 36 valid of 46 JSON files; 10 failed. Classification: 12 GRID-TIED+BESS, 0 GRID-TIED no BESS, 24 ISLANDED.
| Scenario ID | island_mode | PCC cap MW | BESS units (id: rated/usable/initial SoC) | dispatch depth raw/effective | turbines | fuel cell | diesel enabled | end_sim_time s | class |
|---|---:|---:|---|---:|---:|---|---|---:|---|
| S10_mit_supercloud_2021-08-11 | True | — | bess-0 18.000/14.000/0.928452 | absent/0.000000 | 5 | False | False | 86400.0 | ISLANDED (protected) |
| S11_mit_supercloud_2021-08-11_bchydro | False | 80.000 | bess-0 18.000/14.000/0.950000 | 0.25/0.250000 | 0 | False | False | 86400.0 | GRID-TIED+BESS (in scope) |
| S11b_mit_supercloud_2021-08-11_bchydro_60mw | False | 60.000 | bess-0 18.000/14.000/0.950000 | 0.25/0.250000 | 0 | False | False | 86400.0 | GRID-TIED+BESS (in scope) |
| addendum-h-lead-time-profile-validation | True | — | bess-0 5.000/2.000/0.950000 | absent/0.000000 | 1 | False | False | 90.0 | ISLANDED (protected) |
| demo-10-tenant-full-ceiling | False | — | bess-1 6.000/8.000/0.850000 | absent/0.000000 | 3 | False | False | 10800.0 | GRID-TIED+BESS (in scope) |
| demo-10-tenant-overload-120pct | False | — | bess-1 6.000/8.000/0.850000 | absent/0.000000 | 3 | False | False | 5400.0 | GRID-TIED+BESS (in scope) |
| demo-10-tenant-random-gpu | False | — | bess-1 10.000/40.000/0.800000 | absent/0.000000 | 1 | False | False | 10800.0 | GRID-TIED+BESS (in scope) |
| demo-20-tenant-contract-breach | False | — | bess-1 5.000/6.000/0.850000 | absent/0.000000 | 5 | True | False | 3600.0 | GRID-TIED+BESS (in scope) |
| demo-fc-bess-grid-peak | False | — | bess-0 18.000/8.000/0.850000 | absent/0.000000 | 0 | True | False | 3600.0 | GRID-TIED+BESS (in scope) |
| demo-grid-fc-bess-shaped-load | False | — | bess-1 6.000/8.000/0.850000 | absent/0.000000 | 0 | True | False | 5400.0 | GRID-TIED+BESS (in scope) |
| demo-islanded-ramp | True | — | bess-0 18.000/14.000/1.000000 | absent/0.000000 | 5 | False | False | 10800.0 | ISLANDED (protected) |
| demo-operator-trip | True | — | bess-0 18.000/14.000/0.950000 | absent/0.000000 | 5 | False | False | 10800.0 | ISLANDED (protected) |
| demo-rolling-planning-peaks | False | — | bess-0 18.000/8.000/0.850000 | absent/0.000000 | 2 | False | False | 14400.0 | GRID-TIED+BESS (in scope) |
| demo-turbine-fc-bess-20-tenants-overage | False | — | bess-1 5.000/6.000/0.850000 | absent/0.000000 | 5 | True | False | 3600.0 | GRID-TIED+BESS (in scope) |
| islanded-8-60-10-ramp | True | — | bess-0 18.000/8.000/1.000000 | absent/0.000000 | 5 | False | False | 5400.0 | ISLANDED (protected) |
| islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs | True | — | bess-0 18.000/14.000/0.950000 | absent/0.000000 | 5 | False | False | 10800.0 | ISLANDED (protected) |
| lead-time-enterprise-8gpu-air-inference | True | — | bess-0 5.000/2.000/0.950000 | absent/0.000000 | 1 | False | False | 60.0 | ISLANDED (protected) |
| lead-time-enterprise-8gpu-air-training | True | — | bess-0 5.000/2.000/0.950000 | absent/0.000000 | 1 | False | False | 60.0 | ISLANDED (protected) |
| lead-time-h100-sxm5-8way-nvl4-inference | True | — | bess-0 5.000/2.000/0.950000 | absent/0.000000 | 1 | False | False | 60.0 | ISLANDED (protected) |
| lead-time-h100-sxm5-8way-nvl4-training | True | — | bess-0 5.000/2.000/0.950000 | absent/0.000000 | 1 | False | False | 60.0 | ISLANDED (protected) |
| lead-time-nextgen-rack-liquid-inference | True | — | bess-0 5.000/2.000/0.950000 | absent/0.000000 | 1 | False | False | 60.0 | ISLANDED (protected) |
| lead-time-nextgen-rack-liquid-training | True | — | bess-0 5.000/2.000/0.950000 | absent/0.000000 | 1 | False | False | 60.0 | ISLANDED (protected) |
| scenario-100mw-fuel-cell-bess-diesel | True | — | bess-100mw-bridge 25.000/25.000/1.000000 | 0.0/0.000000 | 0 | True | True | 1260.0 | ISLANDED (protected) |
| scenario-equinix-sj-1 | False | 5.000 | bess-0 30.000/60.000/0.950000 | 0.03/0.030000 | 0 | True | False | 3600.0 | GRID-TIED+BESS (in scope) |
| scenario-equinox-sj-1 | False | 5.000 | bess-0 30.000/60.000/0.950000 | 0.03/0.030000 | 0 | True | False | 3600.0 | GRID-TIED+BESS (in scope) |
| scenario-fc100-islanded-v2 | True | — | bess-fc100 60.000/40.000/0.950000 | 1/1.000000 | 0 | True | True | 1320.0 | ISLANDED (protected) |
| scenario-fc100-islanded-zero-hot-v2 | True | — | bess-fc100 60.000/40.000/0.950000 | 1/1.000000 | 0 | True | True | 1320.0 | ISLANDED (protected) |
| scenario-h1-k8s-ray-24h | True | — | none | absent/0.000000 | 0 | False | False | 300.0 | ISLANDED (protected) |
| scenario-h1-k8s-ray-7d | True | — | none | absent/0.000000 | 0 | False | False | 300.0 | ISLANDED (protected) |
| scenario-h2-slurm-24h | True | — | none | absent/0.000000 | 0 | False | False | 300.0 | ISLANDED (protected) |
| scenario-h2-slurm-7d | True | — | none | absent/0.000000 | 0 | False | False | 300.0 | ISLANDED (protected) |
| scenario-hybrid-ai-100mw-addendum-i | True | — | bess-hybrid-edge 15.000/6.000/0.950000 | 0.03/0.030000 | 0 | True | True | 600.0 | ISLANDED (protected) |
| scenario-kube-peak-overage | True | — | bess-0 18.000/8.000/0.950000 | absent/0.000000 | 4 | True | False | 3600.0 | ISLANDED (protected) |
| scenario-kubernetes-scheduler-demo | True | — | bess-0 12.000/24.000/0.950000 | absent/0.000000 | 2 | False | False | 1200.0 | ISLANDED (protected) |
| scenario-turbine-01 | True | — | bess-0 30.000/60.000/0.950000 | 0.03/0.030000 | 3 | True | False | 3600.0 | ISLANDED (protected) |
| scenario-uneven-multisched-01 | True | — | bess-0 30.000/60.000/0.950000 | absent/0.000000 | 4 | False | True | 7200.0 | ISLANDED (protected) |

### Validation failures (not modified)
| Scenario ID | Validation failure summary |
|---|---|
| S1_baseline_training | Field required [type=missing, input_value={'scenario_id': 'regressi...subsequent comparison.'}, input_type=dict]; Input tag 'phase_exists' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S1-A1', 'check': ...resent in the timeline'}, input_type=dict]; Input tag 'verdict_never' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S1-A2', 'check': ...corroboration (TC-82b)'}, input_type=dict]; Input tag 'metric_always' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S1-A3', 'check': ...ncy < 1000 ms (TC-84b)'}, input_type=dict] |
| S2_checkpoint_hotspot | Field required [type=missing, input_value={'scenario_id': 'regressi...torage hardware fault."}, input_type=dict]; Input tag 'phase_exists' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S2-A1', 'check': ...eckpoint phase present'}, input_type=dict]; Input tag 'metric_in_phase' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S2-A2', 'check': ...ing checkpoint (TC-81)'}, input_type=dict]; Input tag 'metric_in_phase' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S2-A3', 'check': ...ing checkpoint (TC-81)'}, input_type=dict] |
| S3_job_end_withholds | Field required [type=missing, input_value={'scenario_id': 'regressi...ant operational check."}, input_type=dict]; Input tag 'phase_exists' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S3-A1', 'check': ...'job_end phase present'}, input_type=dict]; Input tag 'metric_in_phase' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S3-A2', 'check': ...during job_end (TC-82)'}, input_type=dict]; Input tag 'verdict_never' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S3-A3', 'check': ... no checkpoint (TC-82)'}, input_type=dict] |
| S4_control_path_nfr2_breach | Field required [type=missing, input_value={'scenario_id': 'regressi...response matters most."}, input_type=dict]; Input tag 'control_breach_exists' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S4-A1', 'check': ...stion stressor (TC-84)'}, input_type=dict]; Input tag 'metric_always' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S4-A2', 'check': ...tend stressor) (TC-84)'}, input_type=dict]; Input tag 'gateway_in_breach' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S4-A3', 'check': ...g NFR-2 breach (TC-84)'}, input_type=dict] |
| S5_gray_failure | Field required [type=missing, input_value={'scenario_id': 'regressi...operational safeguard."}, input_type=dict]; Input tag 'gray_loss_elevated' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S5-A1', 'check': ...ove the injected floor'}, input_type=dict] |
| S6_baseline_tier_degradation | Field required [type=missing, input_value={'scenario_id': 'regressi...ch require an upgrade.'}, input_type=dict]; Input tag 'capability_tier_assertion' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S6-A1', 'check': ...graded capability tier'}, input_type=dict]; Input tag 'phase_discrimination_false' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S6-A2', 'check': ...lable at degraded tier'}, input_type=dict]; Input tag 'verdict_never' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S6-A3', 'check': ...itted at degraded tier'}, input_type=dict] |
| S7_slow_checkpoint | Field required [type=missing, input_value={'scenario_id': 'regressi...ontier model training.'}, input_type=dict]; Input tag 'phase_exists' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S7-A1', 'check': ...eckpoint phase present'}, input_type=dict]; Input tag 'metric_in_phase' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S7-A2', 'check': ...during slow checkpoint'}, input_type=dict]; Input tag 'verdict_exists' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S7-A3', 'check': ...er ELEPHANT_SUSTAIN_S)'}, input_type=dict] |
| S8_transceiver_degrade | Field required [type=missing, input_value={'scenario_id': 'regressi...ed unexpected results.'}, input_type=dict]; Input tag 'crc_errors_present' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S8-A1', 'check': ...ero CRC error counters'}, input_type=dict] |
| S9_islanded_ramp_protection | Field required [type=missing, input_value={'_comment': 'Regression ...000.0, 'ramp_s': 60.0}]}, input_type=dict]; Field required [type=missing, input_value={'timestamp': 0, 'job_id'... 1000.0, 'ramp_s': 60.0}, input_type=dict]; Field required [type=missing, input_value={'timestamp': 1800, 'job_...1000.0, 'ramp_s': 120.0}, input_type=dict]; Field required [type=missing, input_value={'timestamp': 3600, 'job_...1000.0, 'ramp_s': 120.0}, input_type=dict] |
| addendum-h-cav-1-workload-class-validation | Input should be 'training', 'inference' or 'other' [type=literal_error, input_value='checkpointing', input_type=str] |
Full Pydantic validation text is retained in `INVENTORY.json`.

## 0.2 — Grid-tied+BESS baselines
Runner: `ScenarioSpec.model_validate -> build_run_context_from_spec -> ctx.step -> PhysicalIdentityHasher.update`; seed `1729`, wall clock `1792454400.0`, repetitions `2`. Path: `ScenarioSpec.model_validate -> build_run_context_from_spec -> ctx.step -> PhysicalIdentityHasher.update` (validated spec → `build_run_context_from_spec` → `ctx.step` → `PhysicalIdentityHasher.update`). All two-repetition physical hashes and metric dictionaries match: `True`.
The exact full-precision values and both repetitions are in `GRID_TIED_BASELINES.json`; the tables below round energy/power/SoC to 6 decimals.
| Scenario | Rep1 = Rep2 physical SHA-256 | Demand MWh | Served MWh | Unserved MWh | Peak unserved MW | Peak / max import MW | Cap ticks |
|---|---|---:|---:|---:|---:|---:|---:|
| S11_mit_supercloud_2021-08-11_bchydro | `1b07273588accdc1ad2fe6167854aa68ea6c08271f3e81d0aa4564b1dace7f44` (True/True) | 621.857848 | 621.857848 | 0.000000 | 0.000000 | 61.800494 / 61.800494 | 0 |
| S11b_mit_supercloud_2021-08-11_bchydro_60mw | `3398c9984f05558691e472e07c12ddd65a323a70c2588657dbb55cfce4d6b5bf` (True/True) | 621.857848 | 621.857848 | 0.000000 | 0.000000 | 60.000000 / 60.000000 | 2086 |
| demo-10-tenant-full-ceiling | `9a16b201ebc6f56b2d3d83b37590e787d3615697a79233918651120310cdcfb7` (True/True) | 8.942432 | 8.942432 | 0.000000 | 0.000000 | 0.000000 / 0.000000 | 0 |
| demo-10-tenant-overload-120pct | `82d9d3c45f012abc83568269c832e5d6f60c94d58c1c2242897b2991767c1148` (True/True) | 53.428877 | 53.428877 | 0.000000 | 0.000000 | 22.481612 / 22.481612 | 0 |
| demo-10-tenant-random-gpu | `9d3d182d8bf76b585c7cf95092ff264c86fac204b9b78aff43d1eb700f4587a5` (True/True) | 5.980713 | 5.980713 | 0.000000 | 0.000000 | 0.000000 / 0.000000 | 0 |
| demo-20-tenant-contract-breach | `6892279e688331685808e1beacc19b7c08a22cd5eb4ff00902d3b12fbe393033` (True/True) | 5.888400 | 5.888400 | 0.000000 | 0.000000 | 0.000000 / 0.000000 | 0 |
| demo-fc-bess-grid-peak | `06f0d7a6f3c957f0e6f822c53d9186213f4547c4cb82c08294f6edfc16b5840c` (True/True) | 33.878034 | 33.878034 | 0.000000 | 0.000000 | 26.339948 / 26.339948 | 0 |
| demo-grid-fc-bess-shaped-load | `6c0e72877fd38c90c7c532c8567b18c386f282d0024f8438561e68e92575878f` (True/True) | 53.428877 | 53.428877 | 0.000000 | 0.000000 | 36.731612 / 36.731612 | 0 |
| demo-rolling-planning-peaks | `175974fdd4d44ee1940573008095e700942a7805b3a58cab1603ecc1686797fe` (True/True) | 89.883866 | 89.883866 | 0.000000 | 0.000000 | 17.821600 / 17.821600 | 0 |
| demo-turbine-fc-bess-20-tenants-overage | `ecb5c03d82a2653115975cf6bf25005284dc3fd8e58ae90b5131723a2c793c4a` (True/True) | 5.888400 | 5.888400 | 0.000000 | 0.000000 | 0.000000 / 0.000000 | 0 |
| scenario-equinix-sj-1 | `616a769cd5b79c243eb7d4d91ff062651e8c2c6e5351f468f0bc4e3a29eab6a7` (True/True) | 7.645088 | 7.392817 | 0.252272 | 10.133034 | 5.000000 / 5.000000 | 24 |
| scenario-equinox-sj-1 | `2f0a446724cb0a8a8a153eb038bc592a620d2a14eb313ba4a404b07b101597d9` (True/True) | 6.619276 | 6.619276 | 0.000000 | 0.000000 | 0.000000 / 0.000000 | 0 |

| Scenario | BESS discharge MWh | BESS charge MWh | AC throughput MWh | SoC start / min @ time s / end | Balance closing ticks / total | Max abs defect MW | Invalid-frequency ticks |
|---|---:|---:|---:|---|---:|---:|---:|
| S11_mit_supercloud_2021-08-11_bchydro | 3.351604 | 0.000000 | 3.351604 | 0.950000 / 0.700000 @ 1205.0 / 0.700000 | 17280 / 17280 | 0 | 0 |
| S11b_mit_supercloud_2021-08-11_bchydro_60mw | 8.499342 | 0.000000 | 8.499342 | 0.950000 / 0.316024 @ 65075.0 / 0.316024 | 17280 / 17280 | 0 | 0 |
| demo-10-tenant-full-ceiling | 0.000000 | 1.253131 | 1.253131 | 0.850000 / 0.850582 @ 5.0 / 1.000000 | 2160 / 2160 | 8.881784197e-16 | 0 |
| demo-10-tenant-overload-120pct | 6.511688 | 0.000000 | 6.511688 | 0.850000 / 0.000000 @ 3920.0 / 0.000000 | 1080 / 1080 | 0 | 0 |
| demo-10-tenant-random-gpu | 0.000000 | 8.354208 | 8.354208 | 0.800000 / 0.800175 @ 5.0 / 1.000000 | 2160 / 2160 | 4.4408920985e-16 | 0 |
| demo-20-tenant-contract-breach | 0.071578 | 0.866512 | 0.938090 | 0.850000 / 0.837542 @ 330.0 / 0.975838 | 720 / 720 | 0 | 0 |
| demo-fc-bess-grid-peak | 6.511688 | 0.000000 | 6.511688 | 0.850000 / 0.000000 @ 1340.0 / 0.000000 | 720 / 720 | 0 | 0 |
| demo-grid-fc-bess-shaped-load | 6.511688 | 0.000000 | 6.511688 | 0.850000 / 0.000000 @ 3910.0 / 0.000000 | 1080 / 1080 | 0 | 0 |
| demo-rolling-planning-peaks | 6.511688 | 0.000000 | 6.511688 | 0.850000 / 0.000000 @ 1515.0 / 0.000000 | 2880 / 2880 | 0 | 0 |
| demo-turbine-fc-bess-20-tenants-overage | 0.071578 | 0.866512 | 0.938090 | 0.850000 / 0.837542 @ 330.0 / 0.975838 | 720 / 720 | 0 | 0 |
| scenario-equinix-sj-1 | 1.312746 | 4.564393 | 5.877139 | 0.950000 / 0.950221 @ 5.0 / 1.000000 | 720 / 720 | 1.7763568394e-15 | 0 |
| scenario-equinox-sj-1 | 0.135087 | 3.280142 | 3.415229 | 0.950000 / 0.950141 @ 5.0 / 1.000000 | 720 / 720 | 1.7763568394e-15 | 0 |

### scenario-equinix-sj-1 BESS discharge by pre-BESS local residual
Local residual = demand − turbine − diesel − fuel-cell − renewable output before BESS and grid; split at the scenario import cap. `discharge_mw_tick_sum` is the sum of positive BESS MW across ticks; MWh is interval-weighted.
| Local residual bucket | Ticks | Sum discharge MW across ticks | Discharge MWh |
|---|---:|---:|---:|
| local_residual_gt_cap | 36 | 891.642890303 | 1.238392903 |
| local_residual_le_cap | 684 | 53.534101314 | 0.074352918 |
Open GMB-2 baseline: `0.074352918 MWh` of positive discharge occurred while pre-BESS local residual was at/below cap; `1.238392903 MWh` when above cap.

### scenario-equinox-sj-1 BESS discharge by pre-BESS local residual
Local residual = demand − turbine − diesel − fuel-cell − renewable output before BESS and grid; split at the scenario import cap. `discharge_mw_tick_sum` is the sum of positive BESS MW across ticks; MWh is interval-weighted.
| Local residual bucket | Ticks | Sum discharge MW across ticks | Discharge MWh |
|---|---:|---:|---:|
| local_residual_gt_cap | 0 | 0.000000000 | 0.000000000 |
| local_residual_le_cap | 720 | 97.262945034 | 0.135087424 |
Open GMB-2 baseline: `0.135087424 MWh` of positive discharge occurred while pre-BESS local residual was at/below cap; `0.000000000 MWh` when above cap.

## 0.3 — Islanded protected hashes and protected study gates
Direct `ctx.step` hashes use seed `1729`, wall clock `1792454400.0`, and `ScenarioSpec.model_validate -> build_run_context_from_spec -> ctx.step -> PhysicalIdentityHasher.update`. Current-context hashes for the islanded inventory are recorded below. Existing saved hash comparison uses `tools/dr_isl/d6c/ACCEPTANCE_EXISTING_SCENARIO_HASHES.json`; its overlapping reference cases match: `True`.
| Islanded scenario | Ticks | Current ctx.step physical SHA-256 | D6c reference | Result |
|---|---:|---|---|---|
| S10_mit_supercloud_2021-08-11 | 17280 | `f230ae8f141183e1e6bcdb8dda0eb8f4920bf5674167bba972e4a72f37c64353` | f230ae8f141183e1e6bcdb8dda0eb8f4920bf5674167bba972e4a72f37c64353 | PASS |
| addendum-h-lead-time-profile-validation | 18 | `ef5f298ca7d2afcc0626713bd91e77b76217af255eebacf060e30b09ebf3215e` | — | not in saved D6c set |
| demo-islanded-ramp | 2160 | `f293c4ad161357df6fef9a5e01dbb78098bfcd331c2e7e8ca286c56c9a8ef13e` | f293c4ad161357df6fef9a5e01dbb78098bfcd331c2e7e8ca286c56c9a8ef13e | PASS |
| demo-operator-trip | 2160 | `7f82b1bfb67eeacd427dbac67d03e0680d960c0dfcdc122bd2e3ef6d42e36162` | — | not in saved D6c set |
| islanded-8-60-10-ramp | 1080 | `216cc0c3e2cddc16186364c161a3c1a34d1cbbed8dfc2e3f42688d4b515dcc3b` | — | not in saved D6c set |
| islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs | 2160 | `aa16e2038f36087f4ab0ef04001dab33a1220dfdbaae88d11d4d4f04b515df6b` | — | not in saved D6c set |
| lead-time-enterprise-8gpu-air-inference | 12 | `60963bc81119afb292c68632d36ea53964306bba0b2862d1dae2457c5b1f3036` | — | not in saved D6c set |
| lead-time-enterprise-8gpu-air-training | 12 | `ad5140d862142ca5a4f710a5ac253484663fc3e9716761d97421bc92b5f53a16` | — | not in saved D6c set |
| lead-time-h100-sxm5-8way-nvl4-inference | 12 | `3b2310d354cf8a5782e25e4fd5fd13e11560ce4c026be8b4f59369238a7e74e9` | — | not in saved D6c set |
| lead-time-h100-sxm5-8way-nvl4-training | 12 | `d9c1ef84b029d61ca4fe6c02859b172aff81e2089fd01f34132ac5198e942e22` | — | not in saved D6c set |
| lead-time-nextgen-rack-liquid-inference | 12 | `a8c79ddca9d8a657aacf89c7e777d00bc1775d0ec194d69a6b4291df982a37f2` | — | not in saved D6c set |
| lead-time-nextgen-rack-liquid-training | 12 | `46a3d0e5ec55bf596659ec518cb7f8a9d21851cd6193291164327ea7c4df7cce` | — | not in saved D6c set |
| scenario-100mw-fuel-cell-bess-diesel | 252 | `59f042706562f949250e5eb721bdd817a30e9fd1953f16db52ef003ef3488b98` | 59f042706562f949250e5eb721bdd817a30e9fd1953f16db52ef003ef3488b98 | PASS |
| scenario-fc100-islanded-v2 | 264 | `d381f9837605c79f8d773c98044856877d42d0cd7b7d51b99cd6db8a98610314` | d381f9837605c79f8d773c98044856877d42d0cd7b7d51b99cd6db8a98610314 | PASS |
| scenario-fc100-islanded-zero-hot-v2 | 264 | `952856bb0068913efe767d80ec200f4ca5c0dc8807f5555664e79c4b18965559` | 952856bb0068913efe767d80ec200f4ca5c0dc8807f5555664e79c4b18965559 | PASS |
| scenario-h1-k8s-ray-24h | 17280 | `df8aee70fa7fb0ed50656e73163e7d28105323d57c74e1bd05b9ec6be1f47bbe` | — | not in saved D6c set |
| scenario-h1-k8s-ray-7d | 120960 | `51cb3d0007bca34296850117e758481c4da697a7b6b980a17f0118a8f0bd8f8a` | — | not in saved D6c set |
| scenario-h2-slurm-24h | 17280 | `89efc983744c8195b83f74b24b85b8d5385407fe7959e1d533aa68f5cd9accb0` | — | not in saved D6c set |
| scenario-h2-slurm-7d | 120960 | `2ead6babc70ecd26c85308282bf1eba1136cf1678135a12000028d1be5e97098` | — | not in saved D6c set |
| scenario-hybrid-ai-100mw-addendum-i | 120 | `2400c1a448bd74fc37248e610c13b026f77e5634672f35142041719ded7ae0c4` | 2400c1a448bd74fc37248e610c13b026f77e5634672f35142041719ded7ae0c4 | PASS |
| scenario-kube-peak-overage | 720 | `239763f27e883a4e7e143b9cb42d300ed8ba6bc57f2d3c1c861e0732afe28569` | — | not in saved D6c set |
| scenario-kubernetes-scheduler-demo | 240 | `859147b55d99fa1f85a898bc2c8797ad1aa258ec5715adfd7e590abe5b034d5e` | — | not in saved D6c set |
| scenario-turbine-01 | 720 | `b0196383e7b4ef1110f700c762a827ce45460acdfa6792484d0d0074e61d344e` | b0196383e7b4ef1110f700c762a827ce45460acdfa6792484d0d0074e61d344e | PASS |
| scenario-uneven-multisched-01 | 1440 | `79dda8d3ac1da4b30e1d086ace71af2639f0c3c10008e6525f48b7a7b1646bc7` | — | not in saved D6c set |

Pinned S10 runner reference from `tools/dr_isl/isl25/S10_PINNED_CURRENT.json`; fresh pinned runner output is `S10_PINNED_RUN.json`. Current run: `ad91ced6445f21aa4a9a9b4ccb2fb4dd5114d42f2eae3ab5e0be5769fceaf508` physical, `e0ccf0e15265d70738e53c74d273e8ab223d9b30b4439797b8188cb76be7aaba` non-fuel, `17280` ticks. Matches the accepted pinned reference: True.

Protected seed-42 study gate command: `python tools/dr_isl/isl25/run_protected_study_gates.py --output tools/dr_gmb/phase0/PROTECTED_STUDY_GATES.json`; reference `tools/dr_isl/isl30/PROTECTED_STUDY_GATES_ISL30.json`; result `PASS`. Each scenario below passed all 10 compare conditions; no metric differences were recorded.
| Study scenario | Verdict / conditions | Baseline physical SHA-256 | Baseline raw / normalized identity | Informed physical SHA-256 | Informed raw / normalized identity | Metric differences |
|---|---|---|---|---|---|---|
| scenario-uneven-multisched-01 | PASS 10/10 | `f1ebd90e589a217bbaf85264a2153a268a493a8b644c75ebbe74fd89c7f5def6` | `e25100f64f572efad4062f96df197f70a919ab15a0c8d125a60344ab9039b25b` / `3b75a2ac5bb2272da1f80ba7094d22cc5eb1b9f428e937965322bcc4967c90d5` | `23c4c5b7d7f0eb98a9e9071a1a64ab8ea2d7c843d1e7f1af072f9daf99a84ef1` | `d2b281e8602f6f1ba39e8d32f2f63e669203748dc497881e6d72673dbea45421` / `146a97a2cd2c3245af6eb930b26572f8b0ac1c561cb8275a71d7f93f8b88e8cb` | `{}` |
| scenario-h1-k8s-ray-24h | PASS 10/10 | `c4fa3b355b2eebf949f1f0ad9f43b1b76770cf05bb380d224a3282699985fc20` | `e1677d584145a25a52adf8c91c849c9b545d9ebbcd4ec9c99dd821d81311e16e` / `5fd65e2c703534d508241f55891d560c1a50bb40dc0a03888f12848c49ffe4d2` | `49fe8905d6e97f8654a0bc3febab07198f6f89cac66e7b0993bbeb62e7cb4de2` | `1d99fb904281cd92c8e1963cc3a0b602434db5e89e0bc6ab31e44e379e1431e3` / `007d261ed79e949cf53b8e7261c50a4834ee15777e3d64708c3e5578f86df40e` | `{}` |
| scenario-h2-slurm-24h | PASS 10/10 | `603441374503951709dc77d5ae11234e966d5b479e50edca5dd608c7782f217f` | `8e17f3cd578da91b94793d106151597277f8bc6afcae5af498ecd0cb3d72bded` / `e2a840930e370cb4042b4ad93e40bd0435cdd0853f272dde3e27c60ef0ca26e7` | `0562d2e0df0fc06547a3fa301cd4c237ae8857f60c40ae2331241db2b5b1dbec` | `408d94a4bba836bdc58a1dc696ecc7c1659ecaf92e56afe91b4eec308e06fba8` / `ec2be03deb35de444b593f338e35cd09ce071c9b1b9fe03cd6f1d60b34617312` | `{}` |

## 0.4 — Code map (read-only)
- **Arbitrator inputs:** `core/simulation_core.py:2196–2206`; `DispatchArbitrator.tick` receives net dispatch requirement, interval, BESS target, per-unit ceilings and SoC floors.
- **Grid exchange:** `core/simulation_core.py:3371–3395`; islanded mode sets exchange to zero. Grid mode uses the balance residual; `grid_import_limit_mw=None` means unbounded import balancing, otherwise only negative exchange/import is capped and excess deficit remains in frequency forcing.
- **SoC floor:** `core/dispatch.py:518–596`; normal-depth reserve is `usable_mwh × max(0, initial_soc_fraction − depth)` when depth is positive; diesel floor is also computed; the D2-R bridge applies only when islanded, grid-forming and no live grid-forming fuel cell; final floor is the maximum of these terms.
- **Surplus charge path:** `core/dispatch.py:963–978` calls `BessModule.absorb_surplus` only when local fleet output exceeds dispatch requirement. `core/asset_modules.py:1780–1834` bounds charge by `rated_mw` and remaining energy; this is not a grid-import charging path.
- **Efficiency/rate:** `core/models.py:1002–1009, 1059–1066` derives one-way charge/discharge efficiency as `sqrt(round_trip_efficiency)`; catalogue `gridsignal_parameters.json:1363–1374` sets round trip to `0.917` (`sqrt = 0.957601169590`). `core/simulation_core.py:2252–2258` limits charge acceptance by `min(rated_mw, remaining usable_mwh / dt_hours)`; no separate scenario charge-rate field was found. `bess_response_tau_s=0.05` is at `gridsignal_parameters.json:997–1008`. The scenario field `bess_charge_price_override_per_mwh` at `api/schemas.py:2494–2507` is an accounting input, not a physical rate.
- **Single grid-mode insertion site for D1/D2:** `core/dispatch.py:920–995` inside `DispatchArbitrator.tick`, adjacent to the centralized island-mode selection and BESS discharge/surplus path; an explicit grid branch there can preserve the existing islanded branch unchanged.

## Evidence files
- `BASELINE_METADATA.json`
- `INVENTORY.json`
- `GRID_TIED_BASELINES.json`
- `ISLANDED_CTX_HASHES.json`
- `S10_PINNED_RUN.json`
- `PROTECTED_STUDY_GATES.json`
- `CODE_MAP.json`
