# DR-2026-10-20-ISLAND-COLLAPSE — Phase 1e / IMPL-ISL-13
Status: FINISHED — read-only provenance, semantics and build-only scope audit.
Base: e36667c4c6907a8f14904818c0ccefa7145c5322.
P = `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/`; F = `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/`; T = `/tmp/DR-ISL-phase1e/`.
All P/F references below expand to those literal workspace-relative paths.
No production code, config, scenario, test, runner or parameter file was changed.
No simulation was stepped, no RunManager run was started, and no live API,
production database, deployment or publish operation was used.
Only the final report is copied to tools/dr_isl/PHASE_1E_REPORT.md and committed alone.

## 1e.1 — Provenance of 3600 seconds

The commit adding BOTH diesel_power_block and delta_t_start_s=3600.0 is:
- hash: `244faac23696b475153247ffb5249fdaf6c3d654`
- author date and commit date: `2026-09-15T17:22:03Z`
- author: `Replit Agent <agent@replit.com>`
- message: `Update uneven multisched scenario configuration and clean up fuel cell test`
- body: `Replit-Commit-Author: Agent`
- files: P/config/scenarios/scenario-uneven-multisched-01.json and
  P/tests/test_fuel_cell_phase2.py.

The literal git log -S and introducing patch are in Appendix A. It inserts
`"delta_t_start_s": 3600.0`, `"residual_ramp_s": 60.0`, `"f_block": 1.0` and
`"authority_tier": "advisory_only"` together. It changes the description from a
fuel-cell stack to “4 gas turbines (hot/warm/cold standby), grid-forming BESS,
and advisory diesel backup.” That description does NOT explain a one-hour diesel start.
The current value remains at P/config/scenarios/scenario-uneven-multisched-01.json:191;
the block is at :184–196. No comment or timing-source field accompanies 3600.

The same 3600/60 pair appears at:
- P/config/scenarios/scenario-fc100-islanded-v2.json:14;
- P/config/scenarios/scenario-fc100-islanded-zero-hot-v2.json:14;
- P/api/routes/scenarios.py:1157–1158,1177–1179
  (islanded-fc-bess-diesel-slurm-gpu-peaks).
The FC100 description says “advisory-only diesel final reserve”
(P/config/scenarios/scenario-fc100-islanded-v2.json:3), not why one hour is required.
Equality of values elsewhere is evidence of reuse, NOT proof of copy-paste
or of the original author's physical intent.

No linked task number or DR is present in the introducing commit message/body.
Searches of .local/tasks/*.md, docs, the scenario's source/history and diesel/
scenario tests located no stated reason for the choice of 3600.
No external manufacturer/start-performance source is cited for that value.
The search scope is recorded in the evidence appendix; it is not a claim about
private or external task systems to which this audit has no evidence.

**Verdict: UNDETERMINED.** It is an explicit authored override, not an implicit
default; that does not establish “deliberate with a stated reason.”
It is not proven to be a placeholder or a copy-paste mistake.
Correction to a new sourced value is NOT established by the available provenance.
The schema defaults are themselves described as placeholders, so reverting to a
default would not satisfy the “sourced correction” ruling.

## 1e.2 — Implemented semantics and authority

| Field | Implemented meaning | Source |
|---|---|---|
| delta_t_start_s | Command-accepted STARTING countdown to SYNCHRONISED on a successful start; current output remains zero while starting. | P/core/asset_modules.py:1421–1469 |
| residual_ramp_s | After synchronization, time to interpolate from rated×f_block to full rating; also used when resuming from unloading. | P/core/asset_modules.py:1472–1498 |
| p_start | Per-attempt success probability: one RNG draw at accepted command_start, unless the deterministic success_override seam is used; also the binomial probability for sizing the reliability fleet. | P/core/asset_modules.py:1436–1443; P/api/schemas.py:759–773,846–853 |
| f_block | Fraction of rated MW present immediately on successful synchronization. With f_block=1, the output is already full rating; the reserve duration still includes residual_ramp_s. | P/core/asset_modules.py:1464–1466,1488–1497; P/core/dispatch.py:499–503 |
| start_stagger_interval_s | Primary unit i is assigned start_offset_s=i×interval; added reliability units have start_offset_s=None. The fleet coordinator schedules primary starts against episode time and these offsets. | P/api/schemas.py:846–876; P/core/diesel_fleet.py:267–306 |
| authority_tier | Diesel schema literal advisory_only; retained as authored schema metadata, not a runtime physical exemption. It is not the autonomous/confirm/human_only AuthorityTier enum. | P/api/schemas.py:728–732,753–756 |

Exact comments (not paraphrased):
P/api/schemas.py:705–707:
“The default values are intentionally marked PROPOSED_HERE. They are
placeholders from Addendum H and are not catalogue-backed validations.
target_capacity_mw is the one required author input.”
P/api/schemas.py:728–731:
“Deliberately distinct from core.power_source_priority.AuthorityTier
(autonomous/confirm/human_only), which gates real EDL allocation
eligibility. Diesel has no GridSignal execution path by construction
(TC-68); this is advisory metadata only.”

Diesel authority field read/write inventory, with every literal occurrence in Appendix D:
1. P/api/schemas.py:732,756 validate the only permitted value;
   :876 reads block.authority_tier and writes it to each DieselUnitSpec.
2. ScenarioSpec serialization and ScenarioStore serialization preserve the schema
   field (P/api/routes/scenarios.py:130–137). Seed authoring at :1169,1184 writes it.
3. P/runtime/scenario_factory.py:1022–1045 reads the diesel block and per-unit
   timing, probability, role and loading fields but DOES NOT read authority_tier.
   P/core/models.py:974–990 DieselConfig has no authority_tier member.
4. P/core/asset_modules.py:1330–1499 and P/core/diesel_fleet.py:185–306 act on local
   unit state, gap, offsets, timing and successful starts, not authority_tier.
   “Advisory only” does NOT mean these simulated physical units never run.
5. P/core/dispatch.py:479–528 uses the FULL configured fleet, including standby
   entries for its last-start-offset selection; it does not inspect authority_tier,
   active output, p_start, f_block or start success to exempt it from the floor.
6. Diesel is not created as an EDL source by the source-registration block
   P/runtime/scenario_factory.py:1800–1865. Other sources' generic authority reads
   (including core/economic_dispatch_loop.py:291 and runtime/pms_test_double.py)
   apply to their own RankedPowerSources, not to DieselUnitSpec.authority_tier.
7. Frontend type F/types.ts:979 declares the advisory_only literal;
   F/components/ScenarioBuilder.tsx:256,852 and
   F/opening/PowerSupplySourcesModal.tsx:253 AUTHOR that literal.
   They do not provide an alternate diesel authority tier or waive a reserve.
8. P/tests/test_diesel_schema.py:87 asserts that the generated field is advisory_only.
   Tests were READ, not executed in this phase. All backend/frontend occurrences,
   including unrelated generic BESS/turbine authority fields, are enumerated.

Effect on dispatch / commitment / advisory / reserve:
- No diesel runtime dispatch/commitment branch consumes this metadata.
- The local physical diesel coordinator can still command_start; source/timing
  references above are the evidence, rather than inferring behavior from the label.
- It restricts schema choice to advisory_only, and marks authored advisory status.
- It does not change or bypass soc_floor_mwh. Lloyd's authority ruling agrees
  with this implemented reserve calculation.

The DieselUnitSpec docstring at P/api/schemas.py:738–739 still says it is a
“schema-only representation” and “not consumed by dispatch.” That historical
comment does not describe the current construction/physical reserve path:
factory:1023–1045 creates runtime modules and dispatch:479–528 consumes them.
It is not evidence for excluding advisory units from the physical floor.

### Defaults and existing values
DieselPowerBlockSpec defaults: delta_t_start_s=10.0, residual_ramp_s=8.0,
p_start=0.985, f_block=0.80, start_stagger_interval_s=2.0
(P/api/schemas.py:712–718). DieselConfig defaults are the same 10.0/8.0
for its timing fields (P/core/models.py:980–984). Factory fallbacks match
(P/runtime/scenario_factory.py:1029,1035–1037).
DieselUnitSpec timing fields are REQUIRED (:746,748), not separately defaulted;
materialization copies block timing (:869–871).
These are observed defaults, NOT recommended replacements.

The seeded scenario runtime values are printed below. Each diesel entry contains
asset_id, delta_t_start_s, residual_ramp_s and start_offset_s; full DieselConfig
fields and all unseeded-file variants are in Appendix B.

```json
{
  "scenario_id": "scenario-uneven-multisched-01",
  "diesel_units": [
    {
      "asset_id": "diesel-000",
      "delta_t_start_s": 3600.0,
      "residual_ramp_s": 60.0,
      "start_offset_s": 0.0,
      "f_block": 1.0,
      "p_start": 1.0
    }
  ]
}
```

```json
{
  "scenario_id": "scenario-100mw-fuel-cell-bess-diesel",
  "diesel_units": [
    {
      "asset_id": "diesel-000",
      "delta_t_start_s": 10.0,
      "residual_ramp_s": 8.0,
      "start_offset_s": 0.0,
      "f_block": 0.8,
      "p_start": 1.0
    },
    {
      "asset_id": "diesel-001",
      "delta_t_start_s": 10.0,
      "residual_ramp_s": 8.0,
      "start_offset_s": 2.0,
      "f_block": 0.8,
      "p_start": 1.0
    },
    {
      "asset_id": "diesel-002",
      "delta_t_start_s": 10.0,
      "residual_ramp_s": 8.0,
      "start_offset_s": 4.0,
      "f_block": 0.8,
      "p_start": 1.0
    },
    {
      "asset_id": "diesel-003",
      "delta_t_start_s": 10.0,
      "residual_ramp_s": 8.0,
      "start_offset_s": 6.0,
      "f_block": 0.8,
      "p_start": 1.0
    },
    {
      "asset_id": "diesel-004",
      "delta_t_start_s": 10.0,
      "residual_ramp_s": 8.0,
      "start_offset_s": 8.0,
      "f_block": 0.8,
      "p_start": 1.0
    },
    {
      "asset_id": "diesel-005",
      "delta_t_start_s": 10.0,
      "residual_ramp_s": 8.0,
      "start_offset_s": 10.0,
      "f_block": 0.8,
      "p_start": 1.0
    },
    {
      "asset_id": "diesel-006",
      "delta_t_start_s": 10.0,
      "residual_ramp_s": 8.0,
      "start_offset_s": 12.0,
      "f_block": 0.8,
      "p_start": 1.0
    },
    {
      "asset_id": "diesel-007",
      "delta_t_start_s": 10.0,
      "residual_ramp_s": 8.0,
      "start_offset_s": 14.0,
      "f_block": 0.8,
      "p_start": 1.0
    },
    {
      "asset_id": "diesel-008",
      "delta_t_start_s": 10.0,
      "residual_ramp_s": 8.0,
      "start_offset_s": 16.0,
      "f_block": 0.8,
      "p_start": 1.0
    },
    {
      "asset_id": "diesel-009",
      "delta_t_start_s": 10.0,
      "residual_ramp_s": 8.0,
      "start_offset_s": 18.0,
      "f_block": 0.8,
      "p_start": 1.0
    },
    {
      "asset_id": "diesel-010",
      "delta_t_start_s": 10.0,
      "residual_ramp_s": 8.0,
      "start_offset_s": 20.0,
      "f_block": 0.8,
      "p_start": 1.0
    }
  ]
}
```

```json
{
  "scenario_id": "scenario-fc100-islanded-v2",
  "diesel_units": [
    {
      "asset_id": "diesel-000",
      "delta_t_start_s": 3600.0,
      "residual_ramp_s": 60.0,
      "start_offset_s": 0.0,
      "f_block": 1.0,
      "p_start": 1.0
    }
  ]
}
```

```json
{
  "scenario_id": "scenario-fc100-islanded-zero-hot-v2",
  "diesel_units": [
    {
      "asset_id": "diesel-000",
      "delta_t_start_s": 3600.0,
      "residual_ramp_s": 60.0,
      "start_offset_s": 0.0,
      "f_block": 1.0,
      "p_start": 1.0
    }
  ]
}
```

```json
{
  "scenario_id": "islanded-fc-bess-diesel-slurm-gpu-peaks",
  "diesel_units": [
    {
      "asset_id": "diesel-000",
      "delta_t_start_s": 3600.0,
      "residual_ramp_s": 60.0,
      "start_offset_s": 0.0,
      "f_block": 1.0,
      "p_start": 1.0
    }
  ]
}
```

Test values (read-only source inventory; full call expressions in Appendix E):
- tests/test_diesel_phase2.py:20–22 helper defaults 1.0/4.0;
  :89–91 uses 2.0/5.0; :226–227 uses 1.0/10.0.
- tests/test_diesel_phase3.py:20–22 uses 1.0/1.0.
- tests/test_reserve_reconciliation.py:40–41 defaults 10.0/8.0;
  :75–76 uses 20.0/8.0; :88–89 10.0/8.0;
  :104–105 2000.0/1600.0; :129–130 1000.0/440.0.
- tests/test_addendum_i_phase1.py:122–132 passes parameterized timing through
  its helper to DieselConfig; source expressions are retained in the appendix.
- tests/test_isl_grid_forming_viability.py:43 omits the timing, so the runtime
  defaults apply. No test-derived value is treated as a real-machine source.

## 1e.3 — Complete build-only scope

Method: T/audit.py loads every .json/.json.gz.b64 asset in config/scenarios,
ScenarioSpec.model_validate_json, model_dump(mode="json"), then the real
build_run_context_from_spec at playback_speed=0.0. It independently calls
build_seeded_store (the app path, P/api/app.py:189) and performs the same
validation/build for EVERY seeded record. No ctx.step or RunManager invocation.
Random/clock/fabric pins are diagnostic-only patches in scratch, not config edits.
The builder's automatic kube debug CSVs are redirected into T.
All successful builds have ticks_executed=0. No external generator runs were used.

```json
{
  "file_assets": 45,
  "seeded_catalogue_records": 58,
  "build_attempts": 103,
  "successful_builds": 93,
  "errors": 10,
  "max_ticks_executed": 0
}
```

The 10 failed assets are NOT silently skipped or translated. Full literal
validation errors appear in Appendix B. S1–S9 have legacy black-box structures
that do not satisfy ScenarioSpec; addendum-h-cav-1-workload-class-validation
also fails validation. Every SEEDED record builds successfully.

```json
[
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/S1_baseline_training.json",
    "id": "S1_baseline_training",
    "error": "4 validation errors for ScenarioSpec\nname\n  Field required [type=missing, input_value={'scenario_id': 'regressi...subsequent comparison.'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\nassertions.0\n  Input tag 'phase_exists' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S1-A1', 'check': ...resent in the timeline'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.1\n  Input tag 'verdict_never' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S1-A2', 'check': ...corroboration (TC-82b)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.2\n  Input tag 'metric_always' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S1-A3', 'check': ...ncy < 1000 ms (TC-84b)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/S2_checkpoint_hotspot.json",
    "id": "S2_checkpoint_hotspot",
    "error": "6 validation errors for ScenarioSpec\nname\n  Field required [type=missing, input_value={'scenario_id': 'regressi...torage hardware fault.\"}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\nassertions.0\n  Input tag 'phase_exists' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S2-A1', 'check': ...eckpoint phase present'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.1\n  Input tag 'metric_in_phase' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S2-A2', 'check': ...ing checkpoint (TC-81)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.2\n  Input tag 'metric_in_phase' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S2-A3', 'check': ...ing checkpoint (TC-81)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.3\n  Input tag 'verdict_exists' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S2-A4', 'check': ...t_corroborated (TC-81)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.4\n  Input tag 'telemetry_field_in_phase' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S2-A5', 'check': ...apability tier (TC-81)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/S3_job_end_withholds.json",
    "id": "S3_job_end_withholds",
    "error": "4 validation errors for ScenarioSpec\nname\n  Field required [type=missing, input_value={'scenario_id': 'regressi...ant operational check.\"}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\nassertions.0\n  Input tag 'phase_exists' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S3-A1', 'check': ...'job_end phase present'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.1\n  Input tag 'metric_in_phase' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S3-A2', 'check': ...during job_end (TC-82)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.2\n  Input tag 'verdict_never' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S3-A3', 'check': ... no checkpoint (TC-82)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/S4_control_path_nfr2_breach.json",
    "id": "S4_control_path_nfr2_breach",
    "error": "6 validation errors for ScenarioSpec\nname\n  Field required [type=missing, input_value={'scenario_id': 'regressi...response matters most.\"}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\nassertions.0\n  Input tag 'control_breach_exists' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S4-A1', 'check': ...stion stressor (TC-84)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.1\n  Input tag 'metric_always' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S4-A2', 'check': ...tend stressor) (TC-84)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.2\n  Input tag 'gateway_in_breach' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S4-A3', 'check': ...g NFR-2 breach (TC-84)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.3\n  Input tag 'dominant_in_breach_not' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S4-A4', 'check': ... during breach (TC-84)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.4\n  Input tag 'control_budget' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S4-A5', 'check': ... on every tick (TC-84)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/S5_gray_failure.json",
    "id": "S5_gray_failure",
    "error": "2 validation errors for ScenarioSpec\nname\n  Field required [type=missing, input_value={'scenario_id': 'regressi...operational safeguard.\"}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\nassertions.0\n  Input tag 'gray_loss_elevated' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S5-A1', 'check': ...ove the injected floor'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/S6_baseline_tier_degradation.json",
    "id": "S6_baseline_tier_degradation",
    "error": "4 validation errors for ScenarioSpec\nname\n  Field required [type=missing, input_value={'scenario_id': 'regressi...ch require an upgrade.'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\nassertions.0\n  Input tag 'capability_tier_assertion' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S6-A1', 'check': ...graded capability tier'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.1\n  Input tag 'phase_discrimination_false' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S6-A2', 'check': ...lable at degraded tier'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.2\n  Input tag 'verdict_never' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S6-A3', 'check': ...itted at degraded tier'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/S7_slow_checkpoint.json",
    "id": "S7_slow_checkpoint",
    "error": "4 validation errors for ScenarioSpec\nname\n  Field required [type=missing, input_value={'scenario_id': 'regressi...ontier model training.'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\nassertions.0\n  Input tag 'phase_exists' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S7-A1', 'check': ...eckpoint phase present'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.1\n  Input tag 'metric_in_phase' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S7-A2', 'check': ...during slow checkpoint'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.2\n  Input tag 'verdict_exists' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S7-A3', 'check': ...er ELEPHANT_SUSTAIN_S)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/S8_transceiver_degrade.json",
    "id": "S8_transceiver_degrade",
    "error": "2 validation errors for ScenarioSpec\nname\n  Field required [type=missing, input_value={'scenario_id': 'regressi...ed unexpected results.'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\nassertions.0\n  Input tag 'crc_errors_present' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S8-A1', 'check': ...ero CRC error counters'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/S9_islanded_ramp_protection.json",
    "id": "S9_islanded_ramp_protection",
    "error": "10 validation errors for ScenarioSpec\nname\n  Field required [type=missing, input_value={'_comment': 'Regression ...000.0, 'ramp_s': 60.0}]}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\nworkload_events.0.event_type\n  Field required [type=missing, input_value={'timestamp': 0, 'job_id'... 1000.0, 'ramp_s': 60.0}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\nworkload_events.1.event_type\n  Field required [type=missing, input_value={'timestamp': 1800, 'job_...1000.0, 'ramp_s': 120.0}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\nworkload_events.2.event_type\n  Field required [type=missing, input_value={'timestamp': 3600, 'job_...1000.0, 'ramp_s': 120.0}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\nworkload_events.3.event_type\n  Field required [type=missing, input_value={'timestamp': 4800, 'job_... 1000.0, 'ramp_s': 60.0}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\nturbine_units.0.gt_mode\n  Input should be 'frame' or 'aero' [type=literal_error, input_value='open_cycle', input_type=str]\n    For further information visit https://errors.pydantic.dev/2.13/v/literal_error\nturbine_units.1.gt_mode\n  Input should be 'frame' or 'aero' [type=literal_error, input_value='open_cycle', input_type=str]\n    For further information visit https://errors.pydantic.dev/2.13/v/literal_error\nturbine_units.2.gt_mode\n  Input should be 'frame' or 'aero' [type=literal_error, input_value='open_cycle', input_type=str]\n    For further information visit https://errors.pydantic.dev/2.13/v/literal_error\nturbine_units.3.gt_mode\n  Input should be 'frame' or 'aero' [type=literal_error, input_value='open_cycle', input_type=str]\n    For further information visit https://errors.pydantic.dev/2.13/v/literal_error\nturbine_units.4.gt_mode\n  Input should be 'frame' or 'aero' [type=literal_error, input_value='open_cycle', input_type=str]\n    For further information visit https://errors.pydantic.dev/2.13/v/literal_error"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/addendum-h-cav-1-workload-class-validation.json",
    "id": "addendum-h-cav-1-workload-class-validation",
    "error": "1 validation error for ScenarioSpec\nworkload_events.2.workload_class\n  Input should be 'training', 'inference' or 'other' [type=literal_error, input_value='checkpointing', input_type=str]\n    For further information visit https://errors.pydantic.dev/2.13/v/literal_error"
  }
]
```

### Every per-BESS result
Columns floor/depth/diesel are in MWh; initial is configured initial SoC energy.
Winning term is the unmodified runtime max(depth,diesel) calculation.
An empty BESS list is explicitly reported. Diesel timings for each row are in
its complete row in Appendix B, not guessed from its display name.

| Origin / scenario | BESS | Usable | Initial energy | Floor | Depth | Diesel | Winner | >usable | >initial |
|---|---|---:|---:|---:|---:|---:|---|---|---|

| file: S10_mit_supercloud_2021-08-11 | bess-0 | 14.0 | 14.0 | 0.0 | 0 | 0.0 | tie | False | False |

| file: addendum-h-lead-time-profile-validation | bess-0 | 2.0 | 1.9 | 0.0 | 0 | 0.0 | tie | False | False |

| file: demo-10-tenant-full-ceiling | bess-1 | 8.0 | 6.8 | 0.0 | 0 | 0.0 | tie | False | False |

| file: demo-10-tenant-overload-120pct | bess-1 | 8.0 | 6.8 | 0.0 | 0 | 0.0 | tie | False | False |

| file: demo-10-tenant-random-gpu | bess-1 | 40.0 | 32.0 | 0.0 | 0 | 0.0 | tie | False | False |

| file: demo-20-tenant-contract-breach | bess-1 | 6.0 | 5.1 | 0.0 | 0 | 0.0 | tie | False | False |

| file: demo-fc-bess-grid-peak | bess-0 | 8.0 | 6.8 | 0.0 | 0 | 0.0 | tie | False | False |

| file: demo-grid-fc-bess-shaped-load | bess-1 | 8.0 | 6.8 | 0.0 | 0 | 0.0 | tie | False | False |

| file: demo-islanded-ramp | bess-0 | 14.0 | 14.0 | 0.0 | 0 | 0.0 | tie | False | False |

| file: demo-operator-trip | bess-0 | 14.0 | 13.299999999999999 | 0.0 | 0 | 0.0 | tie | False | False |

| file: demo-rolling-planning-peaks | bess-0 | 8.0 | 6.8 | 0.0 | 0 | 0.0 | tie | False | False |

| file: demo-turbine-fc-bess-20-tenants-overage | bess-1 | 6.0 | 5.1 | 0.0 | 0 | 0.0 | tie | False | False |

| file: islanded-8-60-10-ramp | bess-0 | 8.0 | 8.0 | 0.0 | 0 | 0.0 | tie | False | False |

| file: islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs | bess-0 | 14.0 | 13.299999999999999 | 0.0 | 0 | 0.0 | tie | False | False |

| file: lead-time-enterprise-8gpu-air-inference | bess-0 | 2.0 | 1.9 | 0.0 | 0 | 0.0 | tie | False | False |

| file: lead-time-enterprise-8gpu-air-training | bess-0 | 2.0 | 1.9 | 0.0 | 0 | 0.0 | tie | False | False |

| file: lead-time-h100-sxm5-8way-nvl4-inference | bess-0 | 2.0 | 1.9 | 0.0 | 0 | 0.0 | tie | False | False |

| file: lead-time-h100-sxm5-8way-nvl4-training | bess-0 | 2.0 | 1.9 | 0.0 | 0 | 0.0 | tie | False | False |

| file: lead-time-nextgen-rack-liquid-inference | bess-0 | 2.0 | 1.9 | 0.0 | 0 | 0.0 | tie | False | False |

| file: lead-time-nextgen-rack-liquid-training | bess-0 | 2.0 | 1.9 | 0.0 | 0 | 0.0 | tie | False | False |

| file: scenario-100mw-fuel-cell-bess-diesel | bess-100mw-bridge | 25.0 | 25.0 | 0.6597222222222222 | 0 | 0.6597222222222222 | diesel_floor | False | False |

| file: scenario-equinix-sj-1 | bess-0 | 60.0 | 57.0 | 55.199999999999996 | 55.199999999999996 | 0.0 | depth_reserve | False | False |

| file: scenario-equinix-sj-2-24h | bess-0 | 60.0 | 57.0 | 55.199999999999996 | 55.199999999999996 | 0.0 | depth_reserve | False | False |

| file: scenario-equinox-sj-1 | bess-0 | 60.0 | 57.0 | 55.199999999999996 | 55.199999999999996 | 0.0 | depth_reserve | False | False |

| file: scenario-fc100-islanded-v2 | bess-fc100 | 40.0 | 38.0 | 152.5 | 0.0 | 152.5 | diesel_floor | True | True |

| file: scenario-fc100-islanded-zero-hot-v2 | bess-fc100 | 40.0 | 38.0 | 152.5 | 0.0 | 152.5 | diesel_floor | True | True |

| file: scenario-h1-k8s-ray-24h | bess-0 | 60.0 | 57.0 | 0.0 | 0 | 0.0 | tie | False | False |

| file: scenario-h1-k8s-ray-7d | bess-0 | 60.0 | 57.0 | 0.0 | 0 | 0.0 | tie | False | False |

| file: scenario-h2-slurm-24h | bess-0 | 60.0 | 57.0 | 0.0 | 0 | 0.0 | tie | False | False |

| file: scenario-h2-slurm-7d | bess-0 | 60.0 | 57.0 | 0.0 | 0 | 0.0 | tie | False | False |

| file: scenario-hybrid-ai-100mw-addendum-i | bess-hybrid-edge | 6.0 | 5.699999999999999 | 5.52 | 5.52 | 0.5833333333333334 | depth_reserve | False | False |

| file: scenario-kube-peak-overage | bess-0 | 8.0 | 7.6 | 0.0 | 0 | 0.0 | tie | False | False |

| file: scenario-kubernetes-scheduler-demo | bess-0 | 24.0 | 22.799999999999997 | 0.0 | 0 | 0.0 | tie | False | False |

| file: scenario-turbine-01 | bess-0 | 60.0 | 57.0 | 55.199999999999996 | 55.199999999999996 | 0.0 | depth_reserve | False | False |

| file: scenario-uneven-multisched-01 | bess-0 | 60.0 | 57.0 | 76.25 | 0 | 76.25 | diesel_floor | True | True |

| catalogue: demo-pms-shortfall | bess-0 | 2.0 | 1.9 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: demo-pms | bess-0 | 8.0 | 7.6 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: demo-prestage | bess-0 | 8.0 | 7.6 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: demo-20mw | bess-0 | 8.0 | 7.6 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: demo-forecast-quality | bess-0 | 8.0 | 7.6 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: demo-advisory-agents | bess-0 | 0.5 | 0.475 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: demo-alert | bess-0 | 0.5 | 0.475 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: demo-5mw | bess-0 | 2.0 | 1.9 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: demo-baseline | bess-0 | 2.0 | 1.9 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: demo-3turbine | bess-0 | 8.0 | 7.6 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: demo-fleet | bess-0 | 8.0 | 7.6 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: demo-fleet | bess-1 | 2.5 | 2.375 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: demo-tc33-compute | bess-0 | 2.5 | 2.375 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: demo-tc33-renewable | bess-0 | 2.5 | 2.375 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: demo-solar-peak | bess-0 | 8.0 | 7.6 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: scenario-kube-peak-overage | bess-0 | 8.0 | 7.6 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: demo-operator-trip | bess-0 | 14.0 | 13.299999999999999 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs | bess-0 | 14.0 | 13.299999999999999 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: test-fc-dispatch | bess-0 | 0.5 | 0.475 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: grid-resonance-stress | bess-0 | 8.0 | 7.6 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: regression-test-healthy-training-baseline | bess-0 | 2.5 | 2.375 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: regression-test-checkpoint-storage-hotspot | bess-0 | 2.5 | 2.375 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: regression-test-clean-job-termination | bess-0 | 2.5 | 2.375 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: regression-test-control-path-latency-isolation | bess-0 | 2.5 | 2.375 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: regression-test-gray-link-failure | bess-0 | 2.5 | 2.375 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: regression-test-degraded-fabric-observability | bess-0 | 2.5 | 2.375 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: regression-test-slow-checkpoint | bess-0 | 2.5 | 2.375 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: regression-test-transceiver-degradation | bess-0 | 2.5 | 2.375 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: demo-islanded-ramp | bess-0 | 14.0 | 14.0 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: demo-10-tenant-random-gpu | bess-1 | 40.0 | 32.0 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: demo-10-tenant-full-ceiling | bess-1 | 8.0 | 6.8 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: demo-10-tenant-overload-120pct | bess-1 | 8.0 | 6.8 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: demo-grid-fc-bess-shaped-load | bess-1 | 8.0 | 6.8 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: demo-20-tenant-contract-breach | bess-1 | 6.0 | 5.1 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: demo-turbine-fc-bess-20-tenants-overage | bess-1 | 6.0 | 5.1 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: islanded-8-60-10-ramp | bess-0 | 8.0 | 8.0 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: demo-fc-bess-grid-peak | bess-0 | 8.0 | 6.8 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: demo-rolling-planning-peaks | bess-0 | 8.0 | 6.8 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: scenario-equinix-sj-1 | bess-0 | 60.0 | 57.0 | 55.199999999999996 | 55.199999999999996 | 0.0 | depth_reserve | False | False |

| catalogue: scenario-kubernetes-scheduler-demo | bess-0 | 24.0 | 22.799999999999997 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: scenario-equinix-sj-2-24h | bess-0 | 60.0 | 57.0 | 55.199999999999996 | 55.199999999999996 | 0.0 | depth_reserve | False | False |

| catalogue: scenario-turbine-01 | bess-0 | 60.0 | 57.0 | 55.199999999999996 | 55.199999999999996 | 0.0 | depth_reserve | False | False |

| catalogue: scenario-uneven-multisched-01 | bess-0 | 60.0 | 57.0 | 76.25 | 0 | 76.25 | diesel_floor | True | True |

| catalogue: scenario-h1-k8s-ray-24h | bess-0 | 60.0 | 57.0 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: scenario-h1-k8s-ray-7d | bess-0 | 60.0 | 57.0 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: scenario-h2-slurm-24h | bess-0 | 60.0 | 57.0 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: scenario-h2-slurm-7d | bess-0 | 60.0 | 57.0 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: scenario-100mw-fuel-cell-bess-diesel | bess-100mw-bridge | 25.0 | 25.0 | 0.6597222222222222 | 0 | 0.6597222222222222 | diesel_floor | False | False |

| catalogue: scenario-fc100-islanded-v2 | bess-fc100 | 40.0 | 38.0 | 152.5 | 0.0 | 152.5 | diesel_floor | True | True |

| catalogue: scenario-fc100-islanded-zero-hot-v2 | bess-fc100 | 40.0 | 38.0 | 152.5 | 0.0 | 152.5 | diesel_floor | True | True |

| catalogue: lead-time-enterprise-8gpu-air-training | bess-0 | 2.0 | 1.9 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: lead-time-enterprise-8gpu-air-inference | bess-0 | 2.0 | 1.9 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: lead-time-h100-sxm5-8way-nvl4-training | bess-0 | 2.0 | 1.9 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: lead-time-h100-sxm5-8way-nvl4-inference | bess-0 | 2.0 | 1.9 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: lead-time-nextgen-rack-liquid-training | bess-0 | 2.0 | 1.9 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: lead-time-nextgen-rack-liquid-inference | bess-0 | 2.0 | 1.9 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: addendum-h-lead-time-profile-validation | bess-0 | 2.0 | 1.9 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: S10_mit_supercloud_2021-08-11 | bess-0 | 14.0 | 14.0 | 0.0 | 0 | 0.0 | tie | False | False |

| catalogue: islanded-fc-bess-diesel-slurm-gpu-peaks | bess-fc100 | 40.0 | 38.0 | 152.5 | 0.0 | 152.5 | diesel_floor | True | True |

### Every catalogue scenario with floor ≥ usable
There are FOUR distinct seeded catalogue IDs; file/catalogue duplicates are
retained in the complete matrix above. There are no additional equal-only cases.

```json
[
  {
    "id": "scenario-uneven-multisched-01",
    "bess": {
      "asset_id": "bess-0",
      "rated_mw": 30.0,
      "usable_mwh": 60.0,
      "initial_soc_fraction": 0.95,
      "initial_soc_mwh": 57.0,
      "depth_fraction": 0.0,
      "depth_reserve_mwh": 0,
      "diesel_floor_mwh": 76.25,
      "resolved_soc_floor_mwh": 76.25,
      "winning_term": "diesel_floor",
      "floor_gt_usable": true,
      "floor_ge_usable": true,
      "floor_gt_initial_energy": true,
      "runtime_soc_mwh": 57.0
    },
    "diesel_units": [
      {
        "asset_id": "diesel-000",
        "rated_mw": 20.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 0.0,
        "delta_t_start_s": 3600.0,
        "f_block": 1.0,
        "residual_ramp_s": 60.0,
        "min_stable_load_mw": 6.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      }
    ]
  },
  {
    "id": "scenario-fc100-islanded-v2",
    "bess": {
      "asset_id": "bess-fc100",
      "rated_mw": 60.0,
      "usable_mwh": 40.0,
      "initial_soc_fraction": 0.95,
      "initial_soc_mwh": 38.0,
      "depth_fraction": 1.0,
      "depth_reserve_mwh": 0.0,
      "diesel_floor_mwh": 152.5,
      "resolved_soc_floor_mwh": 152.5,
      "winning_term": "diesel_floor",
      "floor_gt_usable": true,
      "floor_ge_usable": true,
      "floor_gt_initial_energy": true,
      "runtime_soc_mwh": 38.0
    },
    "diesel_units": [
      {
        "asset_id": "diesel-000",
        "rated_mw": 20.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 0.0,
        "delta_t_start_s": 3600.0,
        "f_block": 1.0,
        "residual_ramp_s": 60.0,
        "min_stable_load_mw": 6.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      }
    ]
  },
  {
    "id": "scenario-fc100-islanded-zero-hot-v2",
    "bess": {
      "asset_id": "bess-fc100",
      "rated_mw": 60.0,
      "usable_mwh": 40.0,
      "initial_soc_fraction": 0.95,
      "initial_soc_mwh": 38.0,
      "depth_fraction": 1.0,
      "depth_reserve_mwh": 0.0,
      "diesel_floor_mwh": 152.5,
      "resolved_soc_floor_mwh": 152.5,
      "winning_term": "diesel_floor",
      "floor_gt_usable": true,
      "floor_ge_usable": true,
      "floor_gt_initial_energy": true,
      "runtime_soc_mwh": 38.0
    },
    "diesel_units": [
      {
        "asset_id": "diesel-000",
        "rated_mw": 20.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 0.0,
        "delta_t_start_s": 3600.0,
        "f_block": 1.0,
        "residual_ramp_s": 60.0,
        "min_stable_load_mw": 6.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      }
    ]
  },
  {
    "id": "islanded-fc-bess-diesel-slurm-gpu-peaks",
    "bess": {
      "asset_id": "bess-fc100",
      "rated_mw": 60.0,
      "usable_mwh": 40.0,
      "initial_soc_fraction": 0.95,
      "initial_soc_mwh": 38.0,
      "depth_fraction": 1.0,
      "depth_reserve_mwh": 0.0,
      "diesel_floor_mwh": 152.5,
      "resolved_soc_floor_mwh": 152.5,
      "winning_term": "diesel_floor",
      "floor_gt_usable": true,
      "floor_ge_usable": true,
      "floor_gt_initial_energy": true,
      "runtime_soc_mwh": 38.0
    },
    "diesel_units": [
      {
        "asset_id": "diesel-000",
        "rated_mw": 20.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 0.0,
        "delta_t_start_s": 3600.0,
        "f_block": 1.0,
        "residual_ramp_s": 60.0,
        "min_stable_load_mw": 6.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      }
    ]
  }
]
```

Runtime formula, P/core/dispatch.py:479–528:
duration=max(start offsets)+delta_t_start_s+residual_ramp_s of the last-offset
driver; diesel_floor=2.5×BESS_RATED_MW×duration/3600; depth term is
usable×max(0, initial_soc_fraction−normal_dispatch_depth_fraction) when the
configured depth fraction is positive, otherwise zero; floor=max(the two).
It uses the BESS's rated MW, NOT the diesel's rated MW.
For uneven-multisched: 2.5×30×(3600+60)/3600=76.25, initial energy=57,
usable=60. For the FC100 variants: 2.5×60×3660/3600=152.5,
initial=38, usable=40. In all four builds the returned floor remains uncapped,
and initial stored energy remains as authored. They build, rather than reject.
No warning mentioning floor/76.25/152.5/reserve was captured in T/build.log.
This is not a claim that every possible UI warning path was exercised.

Important compact-H exception: the four H catalogue FILES validate as compact
metadata, then factory:633 expands from raw base JSON without post-expansion
ScenarioSpec validation. Their BUILT runtime diesel_units=[] and floor=0.
They are not evidence that a normalized enabled diesel fleet has zero reserve.
The expansion order, not an authority exemption, explains this scope boundary.

## 1e.4 — Study-harness exposure (no simulations)

The actual StudyRunExecutor._expanded_spec was called for all four reference IDs
and the base demo, without probe/run_pair. Raw and validated builds (where valid)
are compared; no fields were manually repaired to make validation pass.
P/study_harness/executor.py:249–279 reads raw base or calls the expander;
P/runtime/phase2b_reference.py:100–120 copies the base including the diesel block,
and :160–163 removes only the compact metadata keys.

| Scenario | Raw runtime diesels / floor | Full expanded ScenarioSpec result | Materialization evidence |
|---|---|---|---|

| scenario-h1-k8s-ray-24h | 0 / 0.0 MWh | REJECTS: workload_share sum 0.600000 | isolated diesel schema produces 1 unit; NOT full ScenarioSpec validation |

| scenario-h1-k8s-ray-7d | 0 / 0.0 MWh | REJECTS: end_sim_time 604800 > 86400 | isolated diesel schema produces 1 unit; NOT full ScenarioSpec validation |

| scenario-h2-slurm-24h | 0 / 0.0 MWh | REJECTS: workload_share sum 0.400000 | isolated diesel schema produces 1 unit; NOT full ScenarioSpec validation |

| scenario-h2-slurm-7d | 0 / 0.0 MWh | REJECTS: end_sim_time 604800 > 86400 | isolated diesel schema produces 1 unit; NOT full ScenarioSpec validation |

| scenario-uneven-multisched-01 | 0 / 0.0 MWh | VALID | 1 unit; floor 76.25 MWh |

The workload-share validator is P/api/schemas.py:2432–2449: nonempty cluster
shares must sum to 1.0; the expanded H1 subset sums to 0.6 and H2 to 0.4.
The horizon limit is P/api/schemas.py:2074, le=86400; expanded seven-day values
are 604800. The compact seed path intentionally permits the metadata representation
before expansion, but validating the fully expanded spec hits those limits.
No cluster shares or horizon were changed in this diagnosis.

For H cases that reject, a full validated-spec diff does not exist. The ISOLATED
DieselPowerBlockSpec → generate_diesel_fleet result is printed below to show
what the diesel schema itself materializes; it is NOT substituted for successful
ScenarioSpec validation. The base demo's full member-level diff is in Appendix C.
Most inserted fields are schema defaults; the consequential materialized member
is diesel_units: MISSING → one 20 MW primary, start_offset_s=0,
delta_t_start_s=3600, residual_ramp_s=60, f_block=1, advisory_only.
Its raw runtime has no diesel; its fully validated runtime has one and floor 76.25.

```json
[
  {
    "scenario_id": "scenario-h1-k8s-ray-24h",
    "raw_context": {
      "diesel_worst_case_sync_s": 0.0,
      "diesel_units": [],
      "bess": [
        {
          "asset_id": "bess-0",
          "rated_mw": 30.0,
          "usable_mwh": 60.0,
          "initial_soc_fraction": 0.95,
          "initial_soc_mwh": 57.0,
          "depth_fraction": 0.0,
          "depth_reserve_mwh": 0,
          "diesel_floor_mwh": 0.0,
          "resolved_soc_floor_mwh": 0.0,
          "winning_term": "tie",
          "floor_gt_usable": false,
          "floor_ge_usable": false,
          "floor_gt_initial_energy": false,
          "runtime_soc_mwh": 57.0
        }
      ],
      "island_mode": "islanded",
      "ticks_executed": 0,
      "end_sim_time": 86400.0
    },
    "raw_diesel_units": "<MISSING>",
    "diesel_power_block": {
      "enabled": true,
      "target_capacity_mw": 20.0,
      "unit_rating_mw": 20.0,
      "p_start": 1.0,
      "target_reliability": 1.0,
      "f_block": 1.0,
      "delta_t_start_s": 3600.0,
      "residual_ramp_s": 60.0,
      "start_stagger_interval_s": 1.0,
      "authority_tier": "advisory_only"
    },
    "validation_status": "ERROR",
    "error_type": "ValidationError",
    "error": "1 validation error for ScenarioSpec\n  Value error, kube_clusters workload_share values must sum to 1.0 (got 0.600000) [type=value_error, input_value={'name': 'Addendum H-1 Ku...tier': 'advisory_only'}}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/value_error",
    "isolated_diesel_schema_result_NOT_full_scenario_validation": [
      {
        "asset_id": "diesel-000",
        "rated_mw": 20.0,
        "role": "primary",
        "start_offset_s": 0.0,
        "delta_t_start_s": 3600.0,
        "f_block": 1.0,
        "residual_ramp_s": 60.0,
        "min_stable_load_mw": 6.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0,
        "authority_tier": "advisory_only"
      }
    ]
  },
  {
    "scenario_id": "scenario-h1-k8s-ray-7d",
    "raw_context": {
      "diesel_worst_case_sync_s": 0.0,
      "diesel_units": [],
      "bess": [
        {
          "asset_id": "bess-0",
          "rated_mw": 30.0,
          "usable_mwh": 60.0,
          "initial_soc_fraction": 0.95,
          "initial_soc_mwh": 57.0,
          "depth_fraction": 0.0,
          "depth_reserve_mwh": 0,
          "diesel_floor_mwh": 0.0,
          "resolved_soc_floor_mwh": 0.0,
          "winning_term": "tie",
          "floor_gt_usable": false,
          "floor_ge_usable": false,
          "floor_gt_initial_energy": false,
          "runtime_soc_mwh": 57.0
        }
      ],
      "island_mode": "islanded",
      "ticks_executed": 0,
      "end_sim_time": 604800.0
    },
    "raw_diesel_units": "<MISSING>",
    "diesel_power_block": {
      "enabled": true,
      "target_capacity_mw": 20.0,
      "unit_rating_mw": 20.0,
      "p_start": 1.0,
      "target_reliability": 1.0,
      "f_block": 1.0,
      "delta_t_start_s": 3600.0,
      "residual_ramp_s": 60.0,
      "start_stagger_interval_s": 1.0,
      "authority_tier": "advisory_only"
    },
    "validation_status": "ERROR",
    "error_type": "ValidationError",
    "error": "1 validation error for ScenarioSpec\nend_sim_time\n  Input should be less than or equal to 86400 [type=less_than_equal, input_value=604800.0, input_type=float]\n    For further information visit https://errors.pydantic.dev/2.13/v/less_than_equal",
    "isolated_diesel_schema_result_NOT_full_scenario_validation": [
      {
        "asset_id": "diesel-000",
        "rated_mw": 20.0,
        "role": "primary",
        "start_offset_s": 0.0,
        "delta_t_start_s": 3600.0,
        "f_block": 1.0,
        "residual_ramp_s": 60.0,
        "min_stable_load_mw": 6.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0,
        "authority_tier": "advisory_only"
      }
    ]
  },
  {
    "scenario_id": "scenario-h2-slurm-24h",
    "raw_context": {
      "diesel_worst_case_sync_s": 0.0,
      "diesel_units": [],
      "bess": [
        {
          "asset_id": "bess-0",
          "rated_mw": 30.0,
          "usable_mwh": 60.0,
          "initial_soc_fraction": 0.95,
          "initial_soc_mwh": 57.0,
          "depth_fraction": 0.0,
          "depth_reserve_mwh": 0,
          "diesel_floor_mwh": 0.0,
          "resolved_soc_floor_mwh": 0.0,
          "winning_term": "tie",
          "floor_gt_usable": false,
          "floor_ge_usable": false,
          "floor_gt_initial_energy": false,
          "runtime_soc_mwh": 57.0
        }
      ],
      "island_mode": "islanded",
      "ticks_executed": 0,
      "end_sim_time": 86400.0
    },
    "raw_diesel_units": "<MISSING>",
    "diesel_power_block": {
      "enabled": true,
      "target_capacity_mw": 20.0,
      "unit_rating_mw": 20.0,
      "p_start": 1.0,
      "target_reliability": 1.0,
      "f_block": 1.0,
      "delta_t_start_s": 3600.0,
      "residual_ramp_s": 60.0,
      "start_stagger_interval_s": 1.0,
      "authority_tier": "advisory_only"
    },
    "validation_status": "ERROR",
    "error_type": "ValidationError",
    "error": "1 validation error for ScenarioSpec\n  Value error, kube_clusters workload_share values must sum to 1.0 (got 0.400000) [type=value_error, input_value={'name': 'Addendum H-2 Sl...tier': 'advisory_only'}}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/value_error",
    "isolated_diesel_schema_result_NOT_full_scenario_validation": [
      {
        "asset_id": "diesel-000",
        "rated_mw": 20.0,
        "role": "primary",
        "start_offset_s": 0.0,
        "delta_t_start_s": 3600.0,
        "f_block": 1.0,
        "residual_ramp_s": 60.0,
        "min_stable_load_mw": 6.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0,
        "authority_tier": "advisory_only"
      }
    ]
  },
  {
    "scenario_id": "scenario-h2-slurm-7d",
    "raw_context": {
      "diesel_worst_case_sync_s": 0.0,
      "diesel_units": [],
      "bess": [
        {
          "asset_id": "bess-0",
          "rated_mw": 30.0,
          "usable_mwh": 60.0,
          "initial_soc_fraction": 0.95,
          "initial_soc_mwh": 57.0,
          "depth_fraction": 0.0,
          "depth_reserve_mwh": 0,
          "diesel_floor_mwh": 0.0,
          "resolved_soc_floor_mwh": 0.0,
          "winning_term": "tie",
          "floor_gt_usable": false,
          "floor_ge_usable": false,
          "floor_gt_initial_energy": false,
          "runtime_soc_mwh": 57.0
        }
      ],
      "island_mode": "islanded",
      "ticks_executed": 0,
      "end_sim_time": 604800.0
    },
    "raw_diesel_units": "<MISSING>",
    "diesel_power_block": {
      "enabled": true,
      "target_capacity_mw": 20.0,
      "unit_rating_mw": 20.0,
      "p_start": 1.0,
      "target_reliability": 1.0,
      "f_block": 1.0,
      "delta_t_start_s": 3600.0,
      "residual_ramp_s": 60.0,
      "start_stagger_interval_s": 1.0,
      "authority_tier": "advisory_only"
    },
    "validation_status": "ERROR",
    "error_type": "ValidationError",
    "error": "1 validation error for ScenarioSpec\nend_sim_time\n  Input should be less than or equal to 86400 [type=less_than_equal, input_value=604800.0, input_type=float]\n    For further information visit https://errors.pydantic.dev/2.13/v/less_than_equal",
    "isolated_diesel_schema_result_NOT_full_scenario_validation": [
      {
        "asset_id": "diesel-000",
        "rated_mw": 20.0,
        "role": "primary",
        "start_offset_s": 0.0,
        "delta_t_start_s": 3600.0,
        "f_block": 1.0,
        "residual_ramp_s": 60.0,
        "min_stable_load_mw": 6.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0,
        "authority_tier": "advisory_only"
      }
    ]
  },
  {
    "scenario_id": "scenario-uneven-multisched-01",
    "raw_context": {
      "diesel_worst_case_sync_s": 0.0,
      "diesel_units": [],
      "bess": [
        {
          "asset_id": "bess-0",
          "rated_mw": 30.0,
          "usable_mwh": 60.0,
          "initial_soc_fraction": 0.95,
          "initial_soc_mwh": 57.0,
          "depth_fraction": 0.0,
          "depth_reserve_mwh": 0,
          "diesel_floor_mwh": 0.0,
          "resolved_soc_floor_mwh": 0.0,
          "winning_term": "tie",
          "floor_gt_usable": false,
          "floor_ge_usable": false,
          "floor_gt_initial_energy": false,
          "runtime_soc_mwh": 57.0
        }
      ],
      "island_mode": "islanded",
      "ticks_executed": 0,
      "end_sim_time": 7200.0
    },
    "raw_diesel_units": "<MISSING>",
    "diesel_power_block": {
      "enabled": true,
      "target_capacity_mw": 20.0,
      "unit_rating_mw": 20.0,
      "p_start": 1.0,
      "target_reliability": 1.0,
      "f_block": 1.0,
      "delta_t_start_s": 3600.0,
      "residual_ramp_s": 60.0,
      "start_stagger_interval_s": 1.0,
      "debounce_s": 1.0,
      "restore_hold_s": 300.0,
      "min_run_s": 900.0,
      "min_down_s": 300.0,
      "min_stable_load_mw_fraction": 0.3,
      "cooldown_s": 300.0,
      "fuel_burn_gal_per_hr_per_unit_at_full_load": 230.0,
      "fuel_type": "diesel",
      "min_fuel_runtime_hours": 48.0,
      "authority_tier": "advisory_only"
    },
    "validation_status": "VALID",
    "validated_context": {
      "diesel_worst_case_sync_s": 3660.0,
      "diesel_units": [
        {
          "asset_id": "diesel-000",
          "rated_mw": 20.0,
          "role": "primary",
          "p_start": 1.0,
          "start_offset_s": 0.0,
          "delta_t_start_s": 3600.0,
          "f_block": 1.0,
          "residual_ramp_s": 60.0,
          "min_stable_load_mw": 6.0,
          "min_run_s": 900.0,
          "min_down_s": 300.0,
          "cooldown_s": 300.0
        }
      ],
      "bess": [
        {
          "asset_id": "bess-0",
          "rated_mw": 30.0,
          "usable_mwh": 60.0,
          "initial_soc_fraction": 0.95,
          "initial_soc_mwh": 57.0,
          "depth_fraction": 0.0,
          "depth_reserve_mwh": 0,
          "diesel_floor_mwh": 76.25,
          "resolved_soc_floor_mwh": 76.25,
          "winning_term": "diesel_floor",
          "floor_gt_usable": true,
          "floor_ge_usable": true,
          "floor_gt_initial_energy": true,
          "runtime_soc_mwh": 57.0
        }
      ],
      "island_mode": "islanded",
      "ticks_executed": 0,
      "end_sim_time": 7200.0
    },
    "changed_members": 121,
    "diff_file": "scenario-uneven-multisched-01.materialization-diff.json",
    "validated_diesel_units": [
      {
        "asset_id": "diesel-000",
        "rated_mw": 20.0,
        "role": "primary",
        "start_offset_s": 0.0,
        "delta_t_start_s": 3600.0,
        "f_block": 1.0,
        "residual_ramp_s": 60.0,
        "min_stable_load_mw": 6.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0,
        "authority_tier": "advisory_only"
      }
    ]
  }
]
```

### Retained A/B evidence and the named certifications
The literal labels “2026-09-19b” and “2026-09-29” were NOT found in searched
docs, tools, .study-mcp-data JSON/Markdown or .local/tasks. The audit cannot
independently bind those DATE-LABELLED certifications to a unique stored record.
They must not be silently identified by approximate dates or numerical similarity.

Located base-demo cached baseline/informed records have engine_commit and
harness_commit 1c93333c45132779a6815b5e12bf641cc920d846, duration 7200,
parameter_set.diesel_power_block.enabled=true, timing=3600/60,
and parameter_set.diesel_units MISSING. Their recorded curtailment is
4.794773294 / 0.370052665 MWh (rounded serialized figures).
Located H1/H2 24h summary/arm artifacts contain the scenario/mode and historical
metrics; their JSON has no engine_commit or harness_commit member, so this audit
does not invent those metadata values. Full metadata and source lines follow.

```json
[
  {
    "scenario_id": "scenario-uneven-multisched-01",
    "mode": "baseline",
    "tick_count": 1440,
    "dispatch_curtailment_mwh": 4.794773294,
    "engine_commit": "1c93333c45132779a6815b5e12bf641cc920d846",
    "harness_commit": "1c93333c45132779a6815b5e12bf641cc920d846",
    "acceptance_verdict": null,
    "path": ".study-mcp-data/cache/records/2371244b01b6bb564b5b3a3c434899374d89bfdc7afe79479fa5f8ed0fe8e7ea.json",
    "identity": {
      "duration_seconds": 7200.0,
      "engine_commit": "1c93333c45132779a6815b5e12bf641cc920d846",
      "harness_commit": "1c93333c45132779a6815b5e12bf641cc920d846",
      "mode": "baseline",
      "scenario_id": "scenario-uneven-multisched-01",
      "seed": null,
      "tick_seconds": 5.0
    },
    "parameter_set_diesel_power_block": {
      "authority_tier": "advisory_only",
      "delta_t_start_s": 3600.0,
      "enabled": true,
      "f_block": 1.0,
      "p_start": 1.0,
      "residual_ramp_s": 60.0,
      "start_stagger_interval_s": 1.0,
      "target_capacity_mw": 20.0,
      "target_reliability": 1.0,
      "unit_rating_mw": 20.0
    },
    "parameter_set_diesel_units": "<MISSING>",
    "field_lines": {
      "scenario_id": [
        345,
        369
      ],
      "mode": [
        254,
        366
      ],
      "dispatch_curtailment_mwh": [
        225
      ],
      "engine_commit": [
        232,
        252
      ],
      "harness_commit": [
        249,
        253
      ],
      "diesel_power_block": [
        269
      ],
      "diesel_units": []
    }
  },
  {
    "scenario_id": "scenario-uneven-multisched-01",
    "mode": "informed",
    "tick_count": 1440,
    "dispatch_curtailment_mwh": 0.370052665,
    "engine_commit": "1c93333c45132779a6815b5e12bf641cc920d846",
    "harness_commit": "1c93333c45132779a6815b5e12bf641cc920d846",
    "acceptance_verdict": null,
    "path": ".study-mcp-data/cache/records/8b6a71123e6c7ea24452f96e63da5bade985a26e05a6b013f4cd03f0feec9097.json",
    "identity": {
      "duration_seconds": 7200.0,
      "engine_commit": "1c93333c45132779a6815b5e12bf641cc920d846",
      "harness_commit": "1c93333c45132779a6815b5e12bf641cc920d846",
      "mode": "informed",
      "scenario_id": "scenario-uneven-multisched-01",
      "seed": null,
      "tick_seconds": 5.0
    },
    "parameter_set_diesel_power_block": {
      "authority_tier": "advisory_only",
      "delta_t_start_s": 3600.0,
      "enabled": true,
      "f_block": 1.0,
      "p_start": 1.0,
      "residual_ramp_s": 60.0,
      "start_stagger_interval_s": 1.0,
      "target_capacity_mw": 20.0,
      "target_reliability": 1.0,
      "unit_rating_mw": 20.0
    },
    "parameter_set_diesel_units": "<MISSING>",
    "field_lines": {
      "scenario_id": [
        402,
        426
      ],
      "mode": [
        311,
        423
      ],
      "dispatch_curtailment_mwh": [
        282
      ],
      "engine_commit": [
        289,
        309
      ],
      "harness_commit": [
        306,
        310
      ],
      "diesel_power_block": [
        326
      ],
      "diesel_units": []
    }
  },
  {
    "scenario_id": "scenario-uneven-multisched-01",
    "mode": "baseline",
    "tick_count": 1440,
    "dispatch_curtailment_mwh": 4.794773294,
    "engine_commit": "c25cab6385a2ca2c8ef3b4e3f297710c46ff52f9",
    "harness_commit": "c25cab6385a2ca2c8ef3b4e3f297710c46ff52f9",
    "acceptance_verdict": null,
    "path": "docs/dr-2026-09-24-base-study/artifacts/run-e2e89fcf1b16b7df1fcd50fcda485369e6e490928a58029971186f4cfb3b2189.json",
    "identity": {
      "duration_seconds": 7200.0,
      "engine_commit": "c25cab6385a2ca2c8ef3b4e3f297710c46ff52f9",
      "harness_commit": "c25cab6385a2ca2c8ef3b4e3f297710c46ff52f9",
      "mode": "baseline",
      "scenario_id": "scenario-uneven-multisched-01",
      "seed": null,
      "tick_seconds": 5.0
    },
    "parameter_set_diesel_power_block": {
      "authority_tier": "advisory_only",
      "delta_t_start_s": 3600.0,
      "enabled": true,
      "f_block": 1.0,
      "p_start": 1.0,
      "residual_ramp_s": 60.0,
      "start_stagger_interval_s": 1.0,
      "target_capacity_mw": 20.0,
      "target_reliability": 1.0,
      "unit_rating_mw": 20.0
    },
    "parameter_set_diesel_units": "<MISSING>",
    "field_lines": {
      "scenario_id": [
        333,
        357
      ],
      "mode": [
        242,
        354
      ],
      "dispatch_curtailment_mwh": [
        213
      ],
      "engine_commit": [
        220,
        240
      ],
      "harness_commit": [
        237,
        241
      ],
      "diesel_power_block": [
        257
      ],
      "diesel_units": []
    }
  },
  {
    "scenario_id": "scenario-h1-k8s-ray-24h",
    "mode": "informed",
    "tick_count": 17280,
    "dispatch_curtailment_mwh": 162.509583594,
    "engine_commit": null,
    "harness_commit": null,
    "acceptance_verdict": "PASS",
    "path": "docs/addendum-h-phase2b-results/scenario-h1-k8s-ray-24h-informed.json",
    "identity": {},
    "parameter_set_diesel_power_block": "<MISSING>",
    "parameter_set_diesel_units": "<MISSING>",
    "field_lines": {
      "scenario_id": [
        786
      ],
      "mode": [
        780
      ],
      "dispatch_curtailment_mwh": [
        661,
        685
      ],
      "engine_commit": [],
      "harness_commit": [],
      "diesel_power_block": [],
      "diesel_units": []
    }
  },
  {
    "scenario_id": "scenario-h2-slurm-24h",
    "mode": "baseline",
    "tick_count": 17280,
    "dispatch_curtailment_mwh": 324.144769567,
    "engine_commit": null,
    "harness_commit": null,
    "acceptance_verdict": "PASS",
    "path": "docs/addendum-h-phase2b-results/scenario-h2-slurm-24h-baseline.json",
    "identity": {},
    "parameter_set_diesel_power_block": "<MISSING>",
    "parameter_set_diesel_units": "<MISSING>",
    "field_lines": {
      "scenario_id": [
        426
      ],
      "mode": [
        420
      ],
      "dispatch_curtailment_mwh": [
        301,
        325
      ],
      "engine_commit": [],
      "harness_commit": [],
      "diesel_power_block": [],
      "diesel_units": []
    }
  },
  {
    "scenario_id": "scenario-h2-slurm-24h",
    "mode": "informed",
    "tick_count": 17280,
    "dispatch_curtailment_mwh": 299.465950765,
    "engine_commit": null,
    "harness_commit": null,
    "acceptance_verdict": "PASS",
    "path": "docs/addendum-h-phase2b-results/scenario-h2-slurm-24h-informed.json",
    "identity": {},
    "parameter_set_diesel_power_block": "<MISSING>",
    "parameter_set_diesel_units": "<MISSING>",
    "field_lines": {
      "scenario_id": [
        1216
      ],
      "mode": [
        1210
      ],
      "dispatch_curtailment_mwh": [
        1091,
        1115
      ],
      "engine_commit": [],
      "harness_commit": [],
      "diesel_power_block": [],
      "diesel_units": []
    }
  },
  {
    "scenario_id": "scenario-h1-k8s-ray-24h",
    "mode": "baseline",
    "tick_count": 17280,
    "dispatch_curtailment_mwh": 187.690139189,
    "engine_commit": null,
    "harness_commit": null,
    "acceptance_verdict": "PASS",
    "path": "docs/addendum-h-phase2b-results/scenario-h1-k8s-ray-24h-baseline.json",
    "identity": {},
    "parameter_set_diesel_power_block": "<MISSING>",
    "parameter_set_diesel_units": "<MISSING>",
    "field_lines": {
      "scenario_id": [
        666
      ],
      "mode": [
        660
      ],
      "dispatch_curtailment_mwh": [
        541,
        565
      ],
      "engine_commit": [],
      "harness_commit": [],
      "diesel_power_block": [],
      "diesel_units": []
    }
  }
]
```

Would records change?
- Archived records are NOT rewritten by this audit. No A/B runs were launched.
- A NEW normalized base-demo execution would not be the same input/identity as
  the located raw-input study record: it gains diesel_units and a physical floor.
  This is already demonstrated in committed Phase 1d evidence
  tools/dr_isl/PHASE_1D_REPORT.md:290–334: normalized conventional
  curtailment=15.267058272851246, informed=14.705963574916513, rather than the
  raw 4.79477329394151/0.3700526648755099. Those are PRIOR diagnostic results,
  not new Phase 1e runs or certified replacement values.
- A fully normalized H1-24h record CANNOT currently be regenerated by simply
  wrapping the expanded spec in ScenarioSpec: validation rejects first.
  The same applies to H2 and seven-day horizons as printed above.
  The isolated materialization proves exposure to an added diesel/floor,
  but exact A/B fuel, curtailment and other metric deltas are NOT DETERMINABLE
  from build-only work. No claim of unchanged certification is supported.
- Source identity hashing retains the expanded parameter_set, including
  diesel_units: P/study_harness/executor.py:66–81;
  P/study_harness/manifest.py:23–33. It removes workload_events/kube/slurm for
  replay identity, NOT diesel_units. A materialization-changing input therefore
  needs a new identity/record; copying an old certification is not input parity.

## 1e.5 — Summary and dispositions under Lloyd's stated rulings

No replacement timing is selected. “Flag; retain pending provenance” below is
deliberately NOT “keep as deliberate”: deliberate physical intent is unproven.
The three suggested disposition labels cannot honestly distinguish deliberate
from mistaken timing when the reason is absent. Pending source/author evidence,
correction is NOT yet indicated; the over-capacity build condition IS indicated
for flagging without silently capping the floor or rejecting the scenario.

The table covers each distinct input ID; file/catalogue origins are both listed
in the complete audit matrix. For legacy validation errors no reserve conclusion
is fabricated. “No action” is specific to this reserve/timing ruling, not a
claim that the scenario has no other defects.

| Scenario | Floor / usable, MWh | Cause | Recommended disposition |
|---|---|---|---|

| S10_mit_supercloud_2021-08-11 | bess-0: 0.0 / 14.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| S1_baseline_training | not determined | ScenarioSpec validation error | No timing correction indicated; retain literal validation failure, no floor ruling possible |

| S2_checkpoint_hotspot | not determined | ScenarioSpec validation error | No timing correction indicated; retain literal validation failure, no floor ruling possible |

| S3_job_end_withholds | not determined | ScenarioSpec validation error | No timing correction indicated; retain literal validation failure, no floor ruling possible |

| S4_control_path_nfr2_breach | not determined | ScenarioSpec validation error | No timing correction indicated; retain literal validation failure, no floor ruling possible |

| S5_gray_failure | not determined | ScenarioSpec validation error | No timing correction indicated; retain literal validation failure, no floor ruling possible |

| S6_baseline_tier_degradation | not determined | ScenarioSpec validation error | No timing correction indicated; retain literal validation failure, no floor ruling possible |

| S7_slow_checkpoint | not determined | ScenarioSpec validation error | No timing correction indicated; retain literal validation failure, no floor ruling possible |

| S8_transceiver_degrade | not determined | ScenarioSpec validation error | No timing correction indicated; retain literal validation failure, no floor ruling possible |

| S9_islanded_ramp_protection | not determined | ScenarioSpec validation error | No timing correction indicated; retain literal validation failure, no floor ruling possible |

| addendum-h-cav-1-workload-class-validation | not determined | ScenarioSpec validation error | No timing correction indicated; retain literal validation failure, no floor ruling possible |

| addendum-h-lead-time-profile-validation | bess-0: 0.0 / 2.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| demo-10-tenant-full-ceiling | bess-1: 0.0 / 8.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| demo-10-tenant-overload-120pct | bess-1: 0.0 / 8.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| demo-10-tenant-random-gpu | bess-1: 0.0 / 40.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| demo-20-tenant-contract-breach | bess-1: 0.0 / 6.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| demo-20mw | bess-0: 0.0 / 8.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| demo-3turbine | bess-0: 0.0 / 8.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| demo-5mw | bess-0: 0.0 / 2.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| demo-advisory-agents | bess-0: 0.0 / 0.5 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| demo-alert | bess-0: 0.0 / 0.5 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| demo-baseline | bess-0: 0.0 / 2.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| demo-fc-bess-grid-peak | bess-0: 0.0 / 8.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| demo-fleet | bess-0: 0.0 / 8.0 MWh; bess-1: 0.0 / 2.5 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| demo-forecast-quality | bess-0: 0.0 / 8.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| demo-grid-fc-bess-shaped-load | bess-1: 0.0 / 8.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| demo-islanded-ramp | bess-0: 0.0 / 14.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| demo-operator-trip | bess-0: 0.0 / 14.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| demo-pms | bess-0: 0.0 / 8.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| demo-pms-shortfall | bess-0: 0.0 / 2.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| demo-prestage | bess-0: 0.0 / 8.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| demo-rolling-planning-peaks | bess-0: 0.0 / 8.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| demo-solar-peak | bess-0: 0.0 / 8.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| demo-tc33-compute | bess-0: 0.0 / 2.5 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| demo-tc33-renewable | bess-0: 0.0 / 2.5 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| demo-turbine-fc-bess-20-tenants-overage | bess-1: 0.0 / 6.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| grid-resonance-stress | bess-0: 0.0 / 8.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| islanded-8-60-10-ramp | bess-0: 0.0 / 8.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| islanded-fc-bess-diesel-slurm-gpu-peaks | bess-fc100: 152.5 / 40.0 MWh | 3600+60 s diesel reserve exceeds usable energy; timing rationale undetermined | Flag at build; retain timing pending provenance. Neither sourced correction nor deliberate timing is established; do not cap/reject. |

| islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs | bess-0: 0.0 / 14.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| lead-time-enterprise-8gpu-air-inference | bess-0: 0.0 / 2.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| lead-time-enterprise-8gpu-air-training | bess-0: 0.0 / 2.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| lead-time-h100-sxm5-8way-nvl4-inference | bess-0: 0.0 / 2.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| lead-time-h100-sxm5-8way-nvl4-training | bess-0: 0.0 / 2.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| lead-time-nextgen-rack-liquid-inference | bess-0: 0.0 / 2.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| lead-time-nextgen-rack-liquid-training | bess-0: 0.0 / 2.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| regression-test-checkpoint-storage-hotspot | bess-0: 0.0 / 2.5 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| regression-test-clean-job-termination | bess-0: 0.0 / 2.5 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| regression-test-control-path-latency-isolation | bess-0: 0.0 / 2.5 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| regression-test-degraded-fabric-observability | bess-0: 0.0 / 2.5 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| regression-test-gray-link-failure | bess-0: 0.0 / 2.5 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| regression-test-healthy-training-baseline | bess-0: 0.0 / 2.5 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| regression-test-slow-checkpoint | bess-0: 0.0 / 2.5 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| regression-test-transceiver-degradation | bess-0: 0.0 / 2.5 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| scenario-100mw-fuel-cell-bess-diesel | bess-100mw-bridge: 0.6597222222222222 / 25.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| scenario-equinix-sj-1 | bess-0: 55.199999999999996 / 60.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| scenario-equinix-sj-2-24h | bess-0: 55.199999999999996 / 60.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| scenario-equinox-sj-1 | bess-0: 55.199999999999996 / 60.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| scenario-fc100-islanded-v2 | bess-fc100: 152.5 / 40.0 MWh | 3600+60 s diesel reserve exceeds usable energy; timing rationale undetermined | Flag at build; retain timing pending provenance. Neither sourced correction nor deliberate timing is established; do not cap/reject. |

| scenario-fc100-islanded-zero-hot-v2 | bess-fc100: 152.5 / 40.0 MWh | 3600+60 s diesel reserve exceeds usable energy; timing rationale undetermined | Flag at build; retain timing pending provenance. Neither sourced correction nor deliberate timing is established; do not cap/reject. |

| scenario-h1-k8s-ray-24h | bess-0: 0.0 / 60.0 MWh | raw-base expansion after compact validation leaves diesel unmaterialized | No sourced timing correction indicated; flag materialization/expanded-schema exposure before relying on certification. |

| scenario-h1-k8s-ray-7d | bess-0: 0.0 / 60.0 MWh | raw-base expansion after compact validation leaves diesel unmaterialized | No sourced timing correction indicated; flag materialization/expanded-schema exposure before relying on certification. |

| scenario-h2-slurm-24h | bess-0: 0.0 / 60.0 MWh | raw-base expansion after compact validation leaves diesel unmaterialized | No sourced timing correction indicated; flag materialization/expanded-schema exposure before relying on certification. |

| scenario-h2-slurm-7d | bess-0: 0.0 / 60.0 MWh | raw-base expansion after compact validation leaves diesel unmaterialized | No sourced timing correction indicated; flag materialization/expanded-schema exposure before relying on certification. |

| scenario-hybrid-ai-100mw-addendum-i | bess-hybrid-edge: 5.52 / 6.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| scenario-kube-peak-overage | bess-0: 0.0 / 8.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| scenario-kubernetes-scheduler-demo | bess-0: 0.0 / 24.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| scenario-turbine-01 | bess-0: 55.199999999999996 / 60.0 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

| scenario-uneven-multisched-01 | bess-0: 76.25 / 60.0 MWh | 3600+60 s diesel reserve exceeds usable energy; timing rationale undetermined | Flag at build; retain timing pending provenance. Neither sourced correction nor deliberate timing is established; do not cap/reject. |

| test-fc-dispatch | bess-0: 0.0 / 0.5 MWh | resolved max(depth,diesel) is below usable capacity | No action under this reserve-capacity ruling. |

### Scope conclusions
1. Authority exemption is NOT implemented and is NOT needed to explain the result.
2. The four excessive catalogue floors are returned uncapped by successful builds.
   A build flag is indicated under the stated ruling; this phase does not add one.
3. A sourced correction of 3600 s is not justified by this provenance evidence.
   The existing 10/8 defaults are explicitly placeholders, not substitute sources.
4. All five study expanded inputs inherit the enabled 3600/60 block. Only the base
   demo can currently complete full expanded ScenarioSpec validation; H cases
   expose additional schema-boundary constraints. No parameter was changed.
5. Do not reuse an old certified A/B label for a newly materialized topology.
   The two requested date-label mappings remain unverified from retained files.

## Appendix A — Literal history commands, hashes, author, date and introducing patch

### timing_history
```text
git log --format=%H %aI %an%n%B -p -S delta_t_start_s -- attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-uneven-multisched-01.json
244faac23696b475153247ffb5249fdaf6c3d654 2026-09-15T17:22:03Z Replit Agent
Update uneven multisched scenario configuration and clean up fuel cell test

Replit-Commit-Author: Agent


diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-uneven-multisched-01.json b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-uneven-multisched-01.json
index e4b151d..38e5067 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-uneven-multisched-01.json
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-uneven-multisched-01.json
@@ -1,6 +1,6 @@
 {
   "name": "Uneven Multi-Scheduler Turbine Demo",
-  "description": "Kubernetes, Slurm, and Ray jobs admitted on staggered, uneven intervals to create demand peaks, layered with scripted GPU bursts that guarantee a 45s Job Signal (Δt_lead) lead-time window. Full generation stack: 3 gas turbines (hot/warm/cold standby), fuel cell array, and grid-forming BESS. Turbine commitment triggers at 80% fuel-cell utilization; hot/warm/cold startup durations are 5/10/20 minutes respectively, so any committed unit produces a Turbine Online countdown of 5+ minutes.",
+  "description": "Kubernetes, Slurm, and Ray jobs admitted on staggered, uneven intervals to create demand peaks, layered with scripted GPU bursts that guarantee a 45s Job Signal (Δt_lead) lead-time window. Full generation stack: 4 gas turbines (hot/warm/cold standby), grid-forming BESS, and advisory diesel backup. Hot/warm/cold startup durations are 5/10/20 minutes respectively, so any committed unit produces a Turbine Online countdown of 5+ minutes.",
 
   "hardware_profile_id": "enterprise_8gpu_air",
   "dt_lead_seconds": 45.0,
@@ -85,15 +85,24 @@
   "turbine_units": [
     { "asset_id": "gt-hot-01", "rated_mw": 25.0, "r_asset_mw_per_s": 0.2, "hot_standby": true, "thermal_state": "hot", "hot_start_s": 300.0, "warm_start_s": 600.0, "cold_start_s": 1200.0 },
     { "asset_id": "gt-warm-01", "rated_mw": 25.0, "r_asset_mw_per_s": 0.2, "hot_standby": true, "thermal_state": "warm", "hot_start_s": 300.0, "warm_start_s": 600.0, "cold_start_s": 1200.0 },
-    { "asset_id": "gt-cold-01", "rated_mw": 25.0, "r_asset_mw_per_s": 0.2, "hot_standby": true, "thermal_state": "cold", "hot_start_s": 300.0, "warm_start_s": 600.0, "cold_start_s": 1200.0 }
+    { "asset_id": "gt-cold-01", "rated_mw": 25.0, "r_asset_mw_per_s": 0.2, "hot_standby": true, "thermal_state": "cold", "hot_start_s": 300.0, "warm_start_s": 600.0, "cold_start_s": 1200.0 },
+    { "asset_id": "gt-cold-02", "rated_mw": 25.0, "r_asset_mw_per_s": 0.2, "hot_standby": true, "thermal_state": "cold", "hot_start_s": 300.0, "warm_start_s": 600.0, "cold_start_s": 1200.0 }
   ],
 
   "bess_units": [
     { "asset_id": "bess-0", "rated_mw": 30.0, "usable_mwh": 60.0, "initial_soc_fraction": 0.95, "grid_forming": true, "p_anchor_reserve_mw": 1.0, "authority_tier": "autonomous" }
   ],
 
-  "fuel_cell_enabled": true,
-  "fuel_cell_rated_mw": 6.0,
-  "fuel_cell_stack_count": 4,
-  "fuel_cell_turbine_commit_fraction": 0.8
+  "diesel_power_block": {
+    "enabled": true,
+    "target_capacity_mw": 20.0,
+    "unit_rating_mw": 20.0,
+    "p_start": 1.0,
+    "target_reliability": 1.0,
+    "f_block": 1.0,
+    "delta_t_start_s": 3600.0,
+    "residual_ramp_s": 60.0,
+    "start_stagger_interval_s": 1.0,
+    "authority_tier": "advisory_only"
+  }
 }
\ No newline at end of file

```

### block_history
```text
git log --format=%H %aI %an%n%B -p -S diesel_power_block -- attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-uneven-multisched-01.json
244faac23696b475153247ffb5249fdaf6c3d654 2026-09-15T17:22:03Z Replit Agent
Update uneven multisched scenario configuration and clean up fuel cell test

Replit-Commit-Author: Agent


diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-uneven-multisched-01.json b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-uneven-multisched-01.json
index e4b151d..38e5067 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-uneven-multisched-01.json
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-uneven-multisched-01.json
@@ -1,6 +1,6 @@
 {
   "name": "Uneven Multi-Scheduler Turbine Demo",
-  "description": "Kubernetes, Slurm, and Ray jobs admitted on staggered, uneven intervals to create demand peaks, layered with scripted GPU bursts that guarantee a 45s Job Signal (Δt_lead) lead-time window. Full generation stack: 3 gas turbines (hot/warm/cold standby), fuel cell array, and grid-forming BESS. Turbine commitment triggers at 80% fuel-cell utilization; hot/warm/cold startup durations are 5/10/20 minutes respectively, so any committed unit produces a Turbine Online countdown of 5+ minutes.",
+  "description": "Kubernetes, Slurm, and Ray jobs admitted on staggered, uneven intervals to create demand peaks, layered with scripted GPU bursts that guarantee a 45s Job Signal (Δt_lead) lead-time window. Full generation stack: 4 gas turbines (hot/warm/cold standby), grid-forming BESS, and advisory diesel backup. Hot/warm/cold startup durations are 5/10/20 minutes respectively, so any committed unit produces a Turbine Online countdown of 5+ minutes.",
 
   "hardware_profile_id": "enterprise_8gpu_air",
   "dt_lead_seconds": 45.0,
@@ -85,15 +85,24 @@
   "turbine_units": [
     { "asset_id": "gt-hot-01", "rated_mw": 25.0, "r_asset_mw_per_s": 0.2, "hot_standby": true, "thermal_state": "hot", "hot_start_s": 300.0, "warm_start_s": 600.0, "cold_start_s": 1200.0 },
     { "asset_id": "gt-warm-01", "rated_mw": 25.0, "r_asset_mw_per_s": 0.2, "hot_standby": true, "thermal_state": "warm", "hot_start_s": 300.0, "warm_start_s": 600.0, "cold_start_s": 1200.0 },
-    { "asset_id": "gt-cold-01", "rated_mw": 25.0, "r_asset_mw_per_s": 0.2, "hot_standby": true, "thermal_state": "cold", "hot_start_s": 300.0, "warm_start_s": 600.0, "cold_start_s": 1200.0 }
+    { "asset_id": "gt-cold-01", "rated_mw": 25.0, "r_asset_mw_per_s": 0.2, "hot_standby": true, "thermal_state": "cold", "hot_start_s": 300.0, "warm_start_s": 600.0, "cold_start_s": 1200.0 },
+    { "asset_id": "gt-cold-02", "rated_mw": 25.0, "r_asset_mw_per_s": 0.2, "hot_standby": true, "thermal_state": "cold", "hot_start_s": 300.0, "warm_start_s": 600.0, "cold_start_s": 1200.0 }
   ],
 
   "bess_units": [
     { "asset_id": "bess-0", "rated_mw": 30.0, "usable_mwh": 60.0, "initial_soc_fraction": 0.95, "grid_forming": true, "p_anchor_reserve_mw": 1.0, "authority_tier": "autonomous" }
   ],
 
-  "fuel_cell_enabled": true,
-  "fuel_cell_rated_mw": 6.0,
-  "fuel_cell_stack_count": 4,
-  "fuel_cell_turbine_commit_fraction": 0.8
+  "diesel_power_block": {
+    "enabled": true,
+    "target_capacity_mw": 20.0,
+    "unit_rating_mw": 20.0,
+    "p_start": 1.0,
+    "target_reliability": 1.0,
+    "f_block": 1.0,
+    "delta_t_start_s": 3600.0,
+    "residual_ramp_s": 60.0,
+    "start_stagger_interval_s": 1.0,
+    "authority_tier": "advisory_only"
+  }
 }
\ No newline at end of file

```

### introduced_commit
```text
git show --format=fuller --stat 244faac23696b475153247ffb5249fdaf6c3d654
commit 244faac23696b475153247ffb5249fdaf6c3d654
Author:     Replit Agent <agent@replit.com>
AuthorDate: Tue Sep 15 17:22:03 2026 +0000
Commit:     Replit Agent <agent@replit.com>
CommitDate: Tue Sep 15 17:22:03 2026 +0000

    Update uneven multisched scenario configuration and clean up fuel cell test
    
    Replit-Commit-Author: Agent

 .../scenarios/scenario-uneven-multisched-01.json    | 21 +++++++++++++++------
 .../gridsignal_sim/tests/test_fuel_cell_phase2.py   |  1 -
 2 files changed, 15 insertions(+), 7 deletions(-)

```

### same_values_fc100_history
```text
git log -1 --format=%H %aI %an%n%B -S 3600 -- attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-fc100-islanded-v2.json
f10e4c4a005b1899490ccd003b902e634eac4e1e 2026-09-03T22:30:16Z Replit Agent
Implement fuel cell module updates and add islanded scenario configuration

Replit-Commit-Author: Agent


```

### summary_history
```text
git log -1 --format=%H %aI %s -- docs/addendum-h-phase2b-results/scenario-h1-k8s-ray-24h-summary.json
591a66678001ce54723357c53524c20d0740423e 2026-09-18T14:30:50Z Close Phase 2b-1 curtailment attribution check

```

## Appendix B — Complete per-asset and per-catalogue build results (all diesel configs)

```json
[
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/S10_mit_supercloud_2021-08-11.json",
    "scenario_id": "S10_mit_supercloud_2021-08-11",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 18.0,
        "usable_mwh": 14.0,
        "initial_soc_fraction": 1.0,
        "initial_soc_mwh": 14.0,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 14.0
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 86400.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/S1_baseline_training.json",
    "scenario_id": "S1_baseline_training",
    "status": "ERROR",
    "error_type": "ValidationError",
    "error": "4 validation errors for ScenarioSpec\nname\n  Field required [type=missing, input_value={'scenario_id': 'regressi...subsequent comparison.'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\nassertions.0\n  Input tag 'phase_exists' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S1-A1', 'check': ...resent in the timeline'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.1\n  Input tag 'verdict_never' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S1-A2', 'check': ...corroboration (TC-82b)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.2\n  Input tag 'metric_always' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S1-A3', 'check': ...ncy < 1000 ms (TC-84b)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/S2_checkpoint_hotspot.json",
    "scenario_id": "S2_checkpoint_hotspot",
    "status": "ERROR",
    "error_type": "ValidationError",
    "error": "6 validation errors for ScenarioSpec\nname\n  Field required [type=missing, input_value={'scenario_id': 'regressi...torage hardware fault.\"}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\nassertions.0\n  Input tag 'phase_exists' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S2-A1', 'check': ...eckpoint phase present'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.1\n  Input tag 'metric_in_phase' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S2-A2', 'check': ...ing checkpoint (TC-81)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.2\n  Input tag 'metric_in_phase' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S2-A3', 'check': ...ing checkpoint (TC-81)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.3\n  Input tag 'verdict_exists' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S2-A4', 'check': ...t_corroborated (TC-81)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.4\n  Input tag 'telemetry_field_in_phase' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S2-A5', 'check': ...apability tier (TC-81)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/S3_job_end_withholds.json",
    "scenario_id": "S3_job_end_withholds",
    "status": "ERROR",
    "error_type": "ValidationError",
    "error": "4 validation errors for ScenarioSpec\nname\n  Field required [type=missing, input_value={'scenario_id': 'regressi...ant operational check.\"}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\nassertions.0\n  Input tag 'phase_exists' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S3-A1', 'check': ...'job_end phase present'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.1\n  Input tag 'metric_in_phase' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S3-A2', 'check': ...during job_end (TC-82)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.2\n  Input tag 'verdict_never' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S3-A3', 'check': ... no checkpoint (TC-82)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/S4_control_path_nfr2_breach.json",
    "scenario_id": "S4_control_path_nfr2_breach",
    "status": "ERROR",
    "error_type": "ValidationError",
    "error": "6 validation errors for ScenarioSpec\nname\n  Field required [type=missing, input_value={'scenario_id': 'regressi...response matters most.\"}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\nassertions.0\n  Input tag 'control_breach_exists' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S4-A1', 'check': ...stion stressor (TC-84)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.1\n  Input tag 'metric_always' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S4-A2', 'check': ...tend stressor) (TC-84)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.2\n  Input tag 'gateway_in_breach' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S4-A3', 'check': ...g NFR-2 breach (TC-84)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.3\n  Input tag 'dominant_in_breach_not' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S4-A4', 'check': ... during breach (TC-84)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.4\n  Input tag 'control_budget' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S4-A5', 'check': ... on every tick (TC-84)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/S5_gray_failure.json",
    "scenario_id": "S5_gray_failure",
    "status": "ERROR",
    "error_type": "ValidationError",
    "error": "2 validation errors for ScenarioSpec\nname\n  Field required [type=missing, input_value={'scenario_id': 'regressi...operational safeguard.\"}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\nassertions.0\n  Input tag 'gray_loss_elevated' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S5-A1', 'check': ...ove the injected floor'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/S6_baseline_tier_degradation.json",
    "scenario_id": "S6_baseline_tier_degradation",
    "status": "ERROR",
    "error_type": "ValidationError",
    "error": "4 validation errors for ScenarioSpec\nname\n  Field required [type=missing, input_value={'scenario_id': 'regressi...ch require an upgrade.'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\nassertions.0\n  Input tag 'capability_tier_assertion' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S6-A1', 'check': ...graded capability tier'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.1\n  Input tag 'phase_discrimination_false' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S6-A2', 'check': ...lable at degraded tier'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.2\n  Input tag 'verdict_never' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S6-A3', 'check': ...itted at degraded tier'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/S7_slow_checkpoint.json",
    "scenario_id": "S7_slow_checkpoint",
    "status": "ERROR",
    "error_type": "ValidationError",
    "error": "4 validation errors for ScenarioSpec\nname\n  Field required [type=missing, input_value={'scenario_id': 'regressi...ontier model training.'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\nassertions.0\n  Input tag 'phase_exists' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S7-A1', 'check': ...eckpoint phase present'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.1\n  Input tag 'metric_in_phase' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S7-A2', 'check': ...during slow checkpoint'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid\nassertions.2\n  Input tag 'verdict_exists' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S7-A3', 'check': ...er ELEPHANT_SUSTAIN_S)'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/S8_transceiver_degrade.json",
    "scenario_id": "S8_transceiver_degrade",
    "status": "ERROR",
    "error_type": "ValidationError",
    "error": "2 validation errors for ScenarioSpec\nname\n  Field required [type=missing, input_value={'scenario_id': 'regressi...ed unexpected results.'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\nassertions.0\n  Input tag 'crc_errors_present' found using 'check' does not match any of the expected tags: 'no_insufficient_reserve_alert', 'alert_fires', 'declining_fuel_cell_reserve_alert_fires', 'max_p_total_mw', 'min_final_bess_soc', 'pue_base_in_declared_range', 'persistent_fuel_cell_deficit', 'peak_fuel_cell_array_output', 'no_cold_warming_contingency_capacity', 'fuel_cell_commanded_and_achieved_reported', 'fuel_cell_output_nonzero' [type=union_tag_invalid, input_value={'id': 'S8-A1', 'check': ...ero CRC error counters'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/union_tag_invalid"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/S9_islanded_ramp_protection.json",
    "scenario_id": "S9_islanded_ramp_protection",
    "status": "ERROR",
    "error_type": "ValidationError",
    "error": "10 validation errors for ScenarioSpec\nname\n  Field required [type=missing, input_value={'_comment': 'Regression ...000.0, 'ramp_s': 60.0}]}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\nworkload_events.0.event_type\n  Field required [type=missing, input_value={'timestamp': 0, 'job_id'... 1000.0, 'ramp_s': 60.0}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\nworkload_events.1.event_type\n  Field required [type=missing, input_value={'timestamp': 1800, 'job_...1000.0, 'ramp_s': 120.0}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\nworkload_events.2.event_type\n  Field required [type=missing, input_value={'timestamp': 3600, 'job_...1000.0, 'ramp_s': 120.0}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\nworkload_events.3.event_type\n  Field required [type=missing, input_value={'timestamp': 4800, 'job_... 1000.0, 'ramp_s': 60.0}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\nturbine_units.0.gt_mode\n  Input should be 'frame' or 'aero' [type=literal_error, input_value='open_cycle', input_type=str]\n    For further information visit https://errors.pydantic.dev/2.13/v/literal_error\nturbine_units.1.gt_mode\n  Input should be 'frame' or 'aero' [type=literal_error, input_value='open_cycle', input_type=str]\n    For further information visit https://errors.pydantic.dev/2.13/v/literal_error\nturbine_units.2.gt_mode\n  Input should be 'frame' or 'aero' [type=literal_error, input_value='open_cycle', input_type=str]\n    For further information visit https://errors.pydantic.dev/2.13/v/literal_error\nturbine_units.3.gt_mode\n  Input should be 'frame' or 'aero' [type=literal_error, input_value='open_cycle', input_type=str]\n    For further information visit https://errors.pydantic.dev/2.13/v/literal_error\nturbine_units.4.gt_mode\n  Input should be 'frame' or 'aero' [type=literal_error, input_value='open_cycle', input_type=str]\n    For further information visit https://errors.pydantic.dev/2.13/v/literal_error"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/addendum-h-cav-1-workload-class-validation.json",
    "scenario_id": "addendum-h-cav-1-workload-class-validation",
    "status": "ERROR",
    "error_type": "ValidationError",
    "error": "1 validation error for ScenarioSpec\nworkload_events.2.workload_class\n  Input should be 'training', 'inference' or 'other' [type=literal_error, input_value='checkpointing', input_type=str]\n    For further information visit https://errors.pydantic.dev/2.13/v/literal_error"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/addendum-h-lead-time-profile-validation.json",
    "scenario_id": "addendum-h-lead-time-profile-validation",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 2.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 1.9,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 1.9
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 90.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/demo-10-tenant-full-ceiling.json",
    "scenario_id": "demo-10-tenant-full-ceiling",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-1",
        "rated_mw": 6.0,
        "usable_mwh": 8.0,
        "initial_soc_fraction": 0.85,
        "initial_soc_mwh": 6.8,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 6.8
      }
    ],
    "island_mode": "grid_tie",
    "ticks_executed": 0,
    "end_sim_time": 10800.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/demo-10-tenant-overload-120pct.json",
    "scenario_id": "demo-10-tenant-overload-120pct",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-1",
        "rated_mw": 6.0,
        "usable_mwh": 8.0,
        "initial_soc_fraction": 0.85,
        "initial_soc_mwh": 6.8,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 6.8
      }
    ],
    "island_mode": "grid_tie",
    "ticks_executed": 0,
    "end_sim_time": 5400.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/demo-10-tenant-random-gpu.json",
    "scenario_id": "demo-10-tenant-random-gpu",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-1",
        "rated_mw": 10.0,
        "usable_mwh": 40.0,
        "initial_soc_fraction": 0.8,
        "initial_soc_mwh": 32.0,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 32.0
      }
    ],
    "island_mode": "grid_tie",
    "ticks_executed": 0,
    "end_sim_time": 10800.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/demo-20-tenant-contract-breach.json",
    "scenario_id": "demo-20-tenant-contract-breach",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-1",
        "rated_mw": 5.0,
        "usable_mwh": 6.0,
        "initial_soc_fraction": 0.85,
        "initial_soc_mwh": 5.1,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 5.1
      }
    ],
    "island_mode": "grid_tie",
    "ticks_executed": 0,
    "end_sim_time": 3600.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/demo-fc-bess-grid-peak.json",
    "scenario_id": "demo-fc-bess-grid-peak",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 18.0,
        "usable_mwh": 8.0,
        "initial_soc_fraction": 0.85,
        "initial_soc_mwh": 6.8,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 6.8
      }
    ],
    "island_mode": "grid_tie",
    "ticks_executed": 0,
    "end_sim_time": 3600.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/demo-grid-fc-bess-shaped-load.json",
    "scenario_id": "demo-grid-fc-bess-shaped-load",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-1",
        "rated_mw": 6.0,
        "usable_mwh": 8.0,
        "initial_soc_fraction": 0.85,
        "initial_soc_mwh": 6.8,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 6.8
      }
    ],
    "island_mode": "grid_tie",
    "ticks_executed": 0,
    "end_sim_time": 5400.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/demo-islanded-ramp.json",
    "scenario_id": "demo-islanded-ramp",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 18.0,
        "usable_mwh": 14.0,
        "initial_soc_fraction": 1.0,
        "initial_soc_mwh": 14.0,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 14.0
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 10800.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/demo-operator-trip.json",
    "scenario_id": "demo-operator-trip",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 18.0,
        "usable_mwh": 14.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 13.299999999999999,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 13.299999999999999
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 10800.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/demo-rolling-planning-peaks.json",
    "scenario_id": "demo-rolling-planning-peaks",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 18.0,
        "usable_mwh": 8.0,
        "initial_soc_fraction": 0.85,
        "initial_soc_mwh": 6.8,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 6.8
      }
    ],
    "island_mode": "grid_tie",
    "ticks_executed": 0,
    "end_sim_time": 14400.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/demo-turbine-fc-bess-20-tenants-overage.json",
    "scenario_id": "demo-turbine-fc-bess-20-tenants-overage",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-1",
        "rated_mw": 5.0,
        "usable_mwh": 6.0,
        "initial_soc_fraction": 0.85,
        "initial_soc_mwh": 5.1,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 5.1
      }
    ],
    "island_mode": "grid_tie",
    "ticks_executed": 0,
    "end_sim_time": 3600.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/islanded-8-60-10-ramp.json",
    "scenario_id": "islanded-8-60-10-ramp",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 18.0,
        "usable_mwh": 8.0,
        "initial_soc_fraction": 1.0,
        "initial_soc_mwh": 8.0,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 8.0
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 5400.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs.json",
    "scenario_id": "islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 18.0,
        "usable_mwh": 14.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 13.299999999999999,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 13.299999999999999
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 10800.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/lead-time-enterprise-8gpu-air-inference.json",
    "scenario_id": "lead-time-enterprise-8gpu-air-inference",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 2.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 1.9,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 1.9
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 60.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/lead-time-enterprise-8gpu-air-training.json",
    "scenario_id": "lead-time-enterprise-8gpu-air-training",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 2.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 1.9,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 1.9
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 60.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/lead-time-h100-sxm5-8way-nvl4-inference.json",
    "scenario_id": "lead-time-h100-sxm5-8way-nvl4-inference",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 2.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 1.9,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 1.9
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 60.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/lead-time-h100-sxm5-8way-nvl4-training.json",
    "scenario_id": "lead-time-h100-sxm5-8way-nvl4-training",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 2.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 1.9,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 1.9
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 60.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/lead-time-nextgen-rack-liquid-inference.json",
    "scenario_id": "lead-time-nextgen-rack-liquid-inference",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 2.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 1.9,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 1.9
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 60.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/lead-time-nextgen-rack-liquid-training.json",
    "scenario_id": "lead-time-nextgen-rack-liquid-training",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 2.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 1.9,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 1.9
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 60.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-100mw-fuel-cell-bess-diesel.json",
    "scenario_id": "scenario-100mw-fuel-cell-bess-diesel",
    "diesel_worst_case_sync_s": 38.0,
    "diesel_units": [
      {
        "asset_id": "diesel-000",
        "rated_mw": 10.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 0.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 3.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-001",
        "rated_mw": 10.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 2.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 3.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-002",
        "rated_mw": 10.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 4.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 3.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-003",
        "rated_mw": 10.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 6.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 3.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-004",
        "rated_mw": 10.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 8.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 3.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-005",
        "rated_mw": 10.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 10.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 3.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-006",
        "rated_mw": 10.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 12.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 3.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-007",
        "rated_mw": 10.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 14.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 3.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-008",
        "rated_mw": 10.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 16.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 3.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-009",
        "rated_mw": 10.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 18.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 3.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-010",
        "rated_mw": 10.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 20.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 3.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      }
    ],
    "bess": [
      {
        "asset_id": "bess-100mw-bridge",
        "rated_mw": 25.0,
        "usable_mwh": 25.0,
        "initial_soc_fraction": 1.0,
        "initial_soc_mwh": 25.0,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.6597222222222222,
        "resolved_soc_floor_mwh": 0.6597222222222222,
        "winning_term": "diesel_floor",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 25.0
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 1260.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-equinix-sj-1.json",
    "scenario_id": "scenario-equinix-sj-1",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 30.0,
        "usable_mwh": 60.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 57.0,
        "depth_fraction": 0.03,
        "depth_reserve_mwh": 55.199999999999996,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 55.199999999999996,
        "winning_term": "depth_reserve",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 57.0
      }
    ],
    "island_mode": "grid_tie",
    "ticks_executed": 0,
    "end_sim_time": 3600.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-equinix-sj-2-24h.json.gz.b64",
    "scenario_id": "scenario-equinix-sj-2-24h",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 30.0,
        "usable_mwh": 60.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 57.0,
        "depth_fraction": 0.03,
        "depth_reserve_mwh": 55.199999999999996,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 55.199999999999996,
        "winning_term": "depth_reserve",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 57.0
      }
    ],
    "island_mode": "grid_tie",
    "ticks_executed": 0,
    "end_sim_time": 86400.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-equinox-sj-1.json",
    "scenario_id": "scenario-equinox-sj-1",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 30.0,
        "usable_mwh": 60.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 57.0,
        "depth_fraction": 0.03,
        "depth_reserve_mwh": 55.199999999999996,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 55.199999999999996,
        "winning_term": "depth_reserve",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 57.0
      }
    ],
    "island_mode": "grid_tie",
    "ticks_executed": 0,
    "end_sim_time": 3600.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-fc100-islanded-v2.json",
    "scenario_id": "scenario-fc100-islanded-v2",
    "diesel_worst_case_sync_s": 3660.0,
    "diesel_units": [
      {
        "asset_id": "diesel-000",
        "rated_mw": 20.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 0.0,
        "delta_t_start_s": 3600.0,
        "f_block": 1.0,
        "residual_ramp_s": 60.0,
        "min_stable_load_mw": 6.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      }
    ],
    "bess": [
      {
        "asset_id": "bess-fc100",
        "rated_mw": 60.0,
        "usable_mwh": 40.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 38.0,
        "depth_fraction": 1.0,
        "depth_reserve_mwh": 0.0,
        "diesel_floor_mwh": 152.5,
        "resolved_soc_floor_mwh": 152.5,
        "winning_term": "diesel_floor",
        "floor_gt_usable": true,
        "floor_ge_usable": true,
        "floor_gt_initial_energy": true,
        "runtime_soc_mwh": 38.0
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 1320.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-fc100-islanded-zero-hot-v2.json",
    "scenario_id": "scenario-fc100-islanded-zero-hot-v2",
    "diesel_worst_case_sync_s": 3660.0,
    "diesel_units": [
      {
        "asset_id": "diesel-000",
        "rated_mw": 20.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 0.0,
        "delta_t_start_s": 3600.0,
        "f_block": 1.0,
        "residual_ramp_s": 60.0,
        "min_stable_load_mw": 6.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      }
    ],
    "bess": [
      {
        "asset_id": "bess-fc100",
        "rated_mw": 60.0,
        "usable_mwh": 40.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 38.0,
        "depth_fraction": 1.0,
        "depth_reserve_mwh": 0.0,
        "diesel_floor_mwh": 152.5,
        "resolved_soc_floor_mwh": 152.5,
        "winning_term": "diesel_floor",
        "floor_gt_usable": true,
        "floor_ge_usable": true,
        "floor_gt_initial_energy": true,
        "runtime_soc_mwh": 38.0
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 1320.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-h1-k8s-ray-24h.json",
    "scenario_id": "scenario-h1-k8s-ray-24h",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 30.0,
        "usable_mwh": 60.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 57.0,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 57.0
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 86400.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-h1-k8s-ray-7d.json",
    "scenario_id": "scenario-h1-k8s-ray-7d",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 30.0,
        "usable_mwh": 60.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 57.0,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 57.0
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 604800.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-h2-slurm-24h.json",
    "scenario_id": "scenario-h2-slurm-24h",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 30.0,
        "usable_mwh": 60.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 57.0,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 57.0
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 86400.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-h2-slurm-7d.json",
    "scenario_id": "scenario-h2-slurm-7d",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 30.0,
        "usable_mwh": 60.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 57.0,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 57.0
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 604800.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-hybrid-ai-100mw-addendum-i.json",
    "scenario_id": "scenario-hybrid-ai-100mw-addendum-i",
    "diesel_worst_case_sync_s": 56.0,
    "diesel_units": [
      {
        "asset_id": "diesel-000",
        "rated_mw": 3.25,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 0.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 0.975,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-001",
        "rated_mw": 3.25,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 2.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 0.975,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-002",
        "rated_mw": 3.25,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 4.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 0.975,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-003",
        "rated_mw": 3.25,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 6.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 0.975,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-004",
        "rated_mw": 3.25,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 8.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 0.975,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-005",
        "rated_mw": 3.25,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 10.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 0.975,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-006",
        "rated_mw": 3.25,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 12.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 0.975,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-007",
        "rated_mw": 3.25,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 14.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 0.975,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-008",
        "rated_mw": 3.25,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 16.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 0.975,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-009",
        "rated_mw": 3.25,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 18.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 0.975,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-010",
        "rated_mw": 3.25,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 20.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 0.975,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-011",
        "rated_mw": 3.25,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 22.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 0.975,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-012",
        "rated_mw": 3.25,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 24.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 0.975,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-013",
        "rated_mw": 3.25,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 26.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 0.975,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-014",
        "rated_mw": 3.25,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 28.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 0.975,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-015",
        "rated_mw": 3.25,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 30.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 0.975,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-016",
        "rated_mw": 3.25,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 32.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 0.975,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-017",
        "rated_mw": 3.25,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 34.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 0.975,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-018",
        "rated_mw": 3.25,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 36.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 0.975,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-019",
        "rated_mw": 3.25,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 38.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 0.975,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      }
    ],
    "bess": [
      {
        "asset_id": "bess-hybrid-edge",
        "rated_mw": 15.0,
        "usable_mwh": 6.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 5.699999999999999,
        "depth_fraction": 0.03,
        "depth_reserve_mwh": 5.52,
        "diesel_floor_mwh": 0.5833333333333334,
        "resolved_soc_floor_mwh": 5.52,
        "winning_term": "depth_reserve",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 5.699999999999999
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 600.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-kube-peak-overage.json",
    "scenario_id": "scenario-kube-peak-overage",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 18.0,
        "usable_mwh": 8.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 7.6,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 7.6
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 3600.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-kubernetes-scheduler-demo.json",
    "scenario_id": "scenario-kubernetes-scheduler-demo",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 12.0,
        "usable_mwh": 24.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 22.799999999999997,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 22.799999999999997
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 1200.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-turbine-01.json",
    "scenario_id": "scenario-turbine-01",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 30.0,
        "usable_mwh": 60.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 57.0,
        "depth_fraction": 0.03,
        "depth_reserve_mwh": 55.199999999999996,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 55.199999999999996,
        "winning_term": "depth_reserve",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 57.0
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 3600.0,
    "status": "BUILT"
  },
  {
    "origin": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-uneven-multisched-01.json",
    "scenario_id": "scenario-uneven-multisched-01",
    "diesel_worst_case_sync_s": 3660.0,
    "diesel_units": [
      {
        "asset_id": "diesel-000",
        "rated_mw": 20.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 0.0,
        "delta_t_start_s": 3600.0,
        "f_block": 1.0,
        "residual_ramp_s": 60.0,
        "min_stable_load_mw": 6.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      }
    ],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 30.0,
        "usable_mwh": 60.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 57.0,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 76.25,
        "resolved_soc_floor_mwh": 76.25,
        "winning_term": "diesel_floor",
        "floor_gt_usable": true,
        "floor_ge_usable": true,
        "floor_gt_initial_energy": true,
        "runtime_soc_mwh": 57.0
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 7200.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "demo-pms-shortfall",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 3.0,
        "usable_mwh": 2.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 1.9,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 1.9
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 300.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "demo-pms",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 18.0,
        "usable_mwh": 8.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 7.6,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 7.6
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 300.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "demo-prestage",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 18.0,
        "usable_mwh": 8.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 7.6,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 7.6
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 300.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "demo-20mw",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 18.0,
        "usable_mwh": 8.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 7.6,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 7.6
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 300.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "demo-forecast-quality",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 18.0,
        "usable_mwh": 8.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 7.6,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 7.6
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 300.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "demo-advisory-agents",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 1.0,
        "usable_mwh": 0.5,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 0.475,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 0.475
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 600.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "demo-alert",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 1.0,
        "usable_mwh": 0.5,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 0.475,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 0.475
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 300.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "demo-5mw",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 2.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 1.9,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 1.9
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 300.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "demo-baseline",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 2.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 1.9,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 1.9
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 300.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "demo-3turbine",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 18.0,
        "usable_mwh": 8.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 7.6,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 7.6
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 300.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "demo-fleet",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 18.0,
        "usable_mwh": 8.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 7.6,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 7.6
      },
      {
        "asset_id": "bess-1",
        "rated_mw": 5.0,
        "usable_mwh": 2.5,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 2.375,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 2.375
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 300.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "demo-tc33-compute",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 2.5,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 2.375,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 2.375
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 120.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "demo-tc33-renewable",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 2.5,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 2.375,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 2.375
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 120.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "demo-solar-peak",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 18.0,
        "usable_mwh": 8.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 7.6,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 7.6
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 300.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "scenario-kube-peak-overage",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 18.0,
        "usable_mwh": 8.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 7.6,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 7.6
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 3600.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "demo-operator-trip",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 18.0,
        "usable_mwh": 14.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 13.299999999999999,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 13.299999999999999
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 10800.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 18.0,
        "usable_mwh": 14.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 13.299999999999999,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 13.299999999999999
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 10800.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "test-fc-dispatch",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 1.0,
        "usable_mwh": 0.5,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 0.475,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 0.475
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 600.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "grid-resonance-stress",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 18.0,
        "usable_mwh": 8.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 7.6,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 7.6
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 300.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "regression-test-healthy-training-baseline",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 2.5,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 2.375,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 2.375
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 60.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "regression-test-checkpoint-storage-hotspot",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 2.5,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 2.375,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 2.375
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 80.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "regression-test-clean-job-termination",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 2.5,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 2.375,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 2.375
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 60.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "regression-test-control-path-latency-isolation",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 2.5,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 2.375,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 2.375
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 60.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "regression-test-gray-link-failure",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 2.5,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 2.375,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 2.375
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 60.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "regression-test-degraded-fabric-observability",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 2.5,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 2.375,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 2.375
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 60.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "regression-test-slow-checkpoint",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 2.5,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 2.375,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 2.375
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 100.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "regression-test-transceiver-degradation",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 2.5,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 2.375,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 2.375
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 60.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "demo-islanded-ramp",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 18.0,
        "usable_mwh": 14.0,
        "initial_soc_fraction": 1.0,
        "initial_soc_mwh": 14.0,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 14.0
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 10800.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "demo-10-tenant-random-gpu",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-1",
        "rated_mw": 10.0,
        "usable_mwh": 40.0,
        "initial_soc_fraction": 0.8,
        "initial_soc_mwh": 32.0,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 32.0
      }
    ],
    "island_mode": "grid_tie",
    "ticks_executed": 0,
    "end_sim_time": 10800.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "demo-10-tenant-full-ceiling",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-1",
        "rated_mw": 6.0,
        "usable_mwh": 8.0,
        "initial_soc_fraction": 0.85,
        "initial_soc_mwh": 6.8,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 6.8
      }
    ],
    "island_mode": "grid_tie",
    "ticks_executed": 0,
    "end_sim_time": 10800.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "demo-10-tenant-overload-120pct",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-1",
        "rated_mw": 6.0,
        "usable_mwh": 8.0,
        "initial_soc_fraction": 0.85,
        "initial_soc_mwh": 6.8,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 6.8
      }
    ],
    "island_mode": "grid_tie",
    "ticks_executed": 0,
    "end_sim_time": 5400.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "demo-grid-fc-bess-shaped-load",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-1",
        "rated_mw": 6.0,
        "usable_mwh": 8.0,
        "initial_soc_fraction": 0.85,
        "initial_soc_mwh": 6.8,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 6.8
      }
    ],
    "island_mode": "grid_tie",
    "ticks_executed": 0,
    "end_sim_time": 5400.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "demo-20-tenant-contract-breach",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-1",
        "rated_mw": 5.0,
        "usable_mwh": 6.0,
        "initial_soc_fraction": 0.85,
        "initial_soc_mwh": 5.1,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 5.1
      }
    ],
    "island_mode": "grid_tie",
    "ticks_executed": 0,
    "end_sim_time": 3600.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "demo-turbine-fc-bess-20-tenants-overage",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-1",
        "rated_mw": 5.0,
        "usable_mwh": 6.0,
        "initial_soc_fraction": 0.85,
        "initial_soc_mwh": 5.1,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 5.1
      }
    ],
    "island_mode": "grid_tie",
    "ticks_executed": 0,
    "end_sim_time": 3600.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "islanded-8-60-10-ramp",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 18.0,
        "usable_mwh": 8.0,
        "initial_soc_fraction": 1.0,
        "initial_soc_mwh": 8.0,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 8.0
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 5400.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "demo-fc-bess-grid-peak",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 18.0,
        "usable_mwh": 8.0,
        "initial_soc_fraction": 0.85,
        "initial_soc_mwh": 6.8,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 6.8
      }
    ],
    "island_mode": "grid_tie",
    "ticks_executed": 0,
    "end_sim_time": 3600.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "demo-rolling-planning-peaks",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 18.0,
        "usable_mwh": 8.0,
        "initial_soc_fraction": 0.85,
        "initial_soc_mwh": 6.8,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 6.8
      }
    ],
    "island_mode": "grid_tie",
    "ticks_executed": 0,
    "end_sim_time": 14400.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "scenario-equinix-sj-1",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 30.0,
        "usable_mwh": 60.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 57.0,
        "depth_fraction": 0.03,
        "depth_reserve_mwh": 55.199999999999996,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 55.199999999999996,
        "winning_term": "depth_reserve",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 57.0
      }
    ],
    "island_mode": "grid_tie",
    "ticks_executed": 0,
    "end_sim_time": 3600.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "scenario-kubernetes-scheduler-demo",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 12.0,
        "usable_mwh": 24.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 22.799999999999997,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 22.799999999999997
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 1200.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "scenario-equinix-sj-2-24h",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 30.0,
        "usable_mwh": 60.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 57.0,
        "depth_fraction": 0.03,
        "depth_reserve_mwh": 55.199999999999996,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 55.199999999999996,
        "winning_term": "depth_reserve",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 57.0
      }
    ],
    "island_mode": "grid_tie",
    "ticks_executed": 0,
    "end_sim_time": 86400.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "scenario-turbine-01",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 30.0,
        "usable_mwh": 60.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 57.0,
        "depth_fraction": 0.03,
        "depth_reserve_mwh": 55.199999999999996,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 55.199999999999996,
        "winning_term": "depth_reserve",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 57.0
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 3600.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "scenario-uneven-multisched-01",
    "diesel_worst_case_sync_s": 3660.0,
    "diesel_units": [
      {
        "asset_id": "diesel-000",
        "rated_mw": 20.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 0.0,
        "delta_t_start_s": 3600.0,
        "f_block": 1.0,
        "residual_ramp_s": 60.0,
        "min_stable_load_mw": 6.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      }
    ],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 30.0,
        "usable_mwh": 60.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 57.0,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 76.25,
        "resolved_soc_floor_mwh": 76.25,
        "winning_term": "diesel_floor",
        "floor_gt_usable": true,
        "floor_ge_usable": true,
        "floor_gt_initial_energy": true,
        "runtime_soc_mwh": 57.0
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 7200.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "scenario-h1-k8s-ray-24h",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 30.0,
        "usable_mwh": 60.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 57.0,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 57.0
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 86400.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "scenario-h1-k8s-ray-7d",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 30.0,
        "usable_mwh": 60.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 57.0,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 57.0
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 604800.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "scenario-h2-slurm-24h",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 30.0,
        "usable_mwh": 60.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 57.0,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 57.0
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 86400.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "scenario-h2-slurm-7d",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 30.0,
        "usable_mwh": 60.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 57.0,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 57.0
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 604800.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "scenario-100mw-fuel-cell-bess-diesel",
    "diesel_worst_case_sync_s": 38.0,
    "diesel_units": [
      {
        "asset_id": "diesel-000",
        "rated_mw": 10.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 0.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 3.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-001",
        "rated_mw": 10.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 2.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 3.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-002",
        "rated_mw": 10.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 4.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 3.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-003",
        "rated_mw": 10.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 6.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 3.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-004",
        "rated_mw": 10.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 8.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 3.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-005",
        "rated_mw": 10.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 10.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 3.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-006",
        "rated_mw": 10.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 12.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 3.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-007",
        "rated_mw": 10.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 14.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 3.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-008",
        "rated_mw": 10.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 16.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 3.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-009",
        "rated_mw": 10.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 18.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 3.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      },
      {
        "asset_id": "diesel-010",
        "rated_mw": 10.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 20.0,
        "delta_t_start_s": 10.0,
        "f_block": 0.8,
        "residual_ramp_s": 8.0,
        "min_stable_load_mw": 3.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      }
    ],
    "bess": [
      {
        "asset_id": "bess-100mw-bridge",
        "rated_mw": 25.0,
        "usable_mwh": 25.0,
        "initial_soc_fraction": 1.0,
        "initial_soc_mwh": 25.0,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.6597222222222222,
        "resolved_soc_floor_mwh": 0.6597222222222222,
        "winning_term": "diesel_floor",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 25.0
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 1260.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "scenario-fc100-islanded-v2",
    "diesel_worst_case_sync_s": 3660.0,
    "diesel_units": [
      {
        "asset_id": "diesel-000",
        "rated_mw": 20.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 0.0,
        "delta_t_start_s": 3600.0,
        "f_block": 1.0,
        "residual_ramp_s": 60.0,
        "min_stable_load_mw": 6.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      }
    ],
    "bess": [
      {
        "asset_id": "bess-fc100",
        "rated_mw": 60.0,
        "usable_mwh": 40.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 38.0,
        "depth_fraction": 1.0,
        "depth_reserve_mwh": 0.0,
        "diesel_floor_mwh": 152.5,
        "resolved_soc_floor_mwh": 152.5,
        "winning_term": "diesel_floor",
        "floor_gt_usable": true,
        "floor_ge_usable": true,
        "floor_gt_initial_energy": true,
        "runtime_soc_mwh": 38.0
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 1320.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "scenario-fc100-islanded-zero-hot-v2",
    "diesel_worst_case_sync_s": 3660.0,
    "diesel_units": [
      {
        "asset_id": "diesel-000",
        "rated_mw": 20.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 0.0,
        "delta_t_start_s": 3600.0,
        "f_block": 1.0,
        "residual_ramp_s": 60.0,
        "min_stable_load_mw": 6.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      }
    ],
    "bess": [
      {
        "asset_id": "bess-fc100",
        "rated_mw": 60.0,
        "usable_mwh": 40.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 38.0,
        "depth_fraction": 1.0,
        "depth_reserve_mwh": 0.0,
        "diesel_floor_mwh": 152.5,
        "resolved_soc_floor_mwh": 152.5,
        "winning_term": "diesel_floor",
        "floor_gt_usable": true,
        "floor_ge_usable": true,
        "floor_gt_initial_energy": true,
        "runtime_soc_mwh": 38.0
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 1320.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "lead-time-enterprise-8gpu-air-training",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 2.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 1.9,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 1.9
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 60.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "lead-time-enterprise-8gpu-air-inference",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 2.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 1.9,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 1.9
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 60.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "lead-time-h100-sxm5-8way-nvl4-training",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 2.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 1.9,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 1.9
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 60.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "lead-time-h100-sxm5-8way-nvl4-inference",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 2.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 1.9,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 1.9
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 60.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "lead-time-nextgen-rack-liquid-training",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 2.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 1.9,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 1.9
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 60.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "lead-time-nextgen-rack-liquid-inference",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 2.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 1.9,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 1.9
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 60.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "addendum-h-lead-time-profile-validation",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 2.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 1.9,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 1.9
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 90.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "S10_mit_supercloud_2021-08-11",
    "diesel_worst_case_sync_s": 0.0,
    "diesel_units": [],
    "bess": [
      {
        "asset_id": "bess-0",
        "rated_mw": 18.0,
        "usable_mwh": 14.0,
        "initial_soc_fraction": 1.0,
        "initial_soc_mwh": 14.0,
        "depth_fraction": 0.0,
        "depth_reserve_mwh": 0,
        "diesel_floor_mwh": 0.0,
        "resolved_soc_floor_mwh": 0.0,
        "winning_term": "tie",
        "floor_gt_usable": false,
        "floor_ge_usable": false,
        "floor_gt_initial_energy": false,
        "runtime_soc_mwh": 14.0
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 86400.0,
    "status": "BUILT"
  },
  {
    "origin": "seeded catalogue",
    "scenario_id": "islanded-fc-bess-diesel-slurm-gpu-peaks",
    "diesel_worst_case_sync_s": 3660.0,
    "diesel_units": [
      {
        "asset_id": "diesel-000",
        "rated_mw": 20.0,
        "role": "primary",
        "p_start": 1.0,
        "start_offset_s": 0.0,
        "delta_t_start_s": 3600.0,
        "f_block": 1.0,
        "residual_ramp_s": 60.0,
        "min_stable_load_mw": 6.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0
      }
    ],
    "bess": [
      {
        "asset_id": "bess-fc100",
        "rated_mw": 60.0,
        "usable_mwh": 40.0,
        "initial_soc_fraction": 0.95,
        "initial_soc_mwh": 38.0,
        "depth_fraction": 1.0,
        "depth_reserve_mwh": 0.0,
        "diesel_floor_mwh": 152.5,
        "resolved_soc_floor_mwh": 152.5,
        "winning_term": "diesel_floor",
        "floor_gt_usable": true,
        "floor_ge_usable": true,
        "floor_gt_initial_energy": true,
        "runtime_soc_mwh": 38.0
      }
    ],
    "island_mode": "islanded",
    "ticks_executed": 0,
    "end_sim_time": 5400.0,
    "status": "BUILT"
  }
]
```

## Appendix C — Base expanded-spec → fully validated-spec diff

```json
[
  {
    "path": "$.alpha_max",
    "raw": "<MISSING>",
    "validated": 0.2
  },
  {
    "path": "$.ambient_steps",
    "raw": "<MISSING>",
    "validated": []
  },
  {
    "path": "$.anchor_reserve_pct",
    "raw": "<MISSING>",
    "validated": 0.0
  },
  {
    "path": "$.assertions",
    "raw": "<MISSING>",
    "validated": []
  },
  {
    "path": "$.band_enabled",
    "raw": "<MISSING>",
    "validated": false
  },
  {
    "path": "$.band_mult_uncalibrated",
    "raw": "<MISSING>",
    "validated": 2.0
  },
  {
    "path": "$.band_mult_unmapped_hw",
    "raw": "<MISSING>",
    "validated": 1.5
  },
  {
    "path": "$.band_pct_calibrated",
    "raw": "<MISSING>",
    "validated": 0.0
  },
  {
    "path": "$.bess_bridging_floor_anchor_multiple",
    "raw": "<MISSING>",
    "validated": 2.0
  },
  {
    "path": "$.bess_bridging_floor_fraction",
    "raw": "<MISSING>",
    "validated": 0.15
  },
  {
    "path": "$.bess_catchup_bridge_margin",
    "raw": "<MISSING>",
    "validated": 0.8
  },
  {
    "path": "$.bess_catchup_slope_window_s",
    "raw": "<MISSING>",
    "validated": 15.0
  },
  {
    "path": "$.bess_catchup_sustain_s",
    "raw": "<MISSING>",
    "validated": 30.0
  },
  {
    "path": "$.bess_charge_price_override_per_mwh",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.bess_material_discharge_fraction",
    "raw": "<MISSING>",
    "validated": 0.05
  },
  {
    "path": "$.bess_material_discharge_min_mw",
    "raw": "<MISSING>",
    "validated": 1.0
  },
  {
    "path": "$.bess_normal_dispatch_depth_fraction",
    "raw": "<MISSING>",
    "validated": 0.0
  },
  {
    "path": "$.calibrated",
    "raw": "<MISSING>",
    "validated": false
  },
  {
    "path": "$.cascade_commit_fraction",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.cluster_gen_config",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.default_playback_speed",
    "raw": "<MISSING>",
    "validated": 1.0
  },
  {
    "path": "$.demo_description",
    "raw": "<MISSING>",
    "validated": ""
  },
  {
    "path": "$.design_peak_load_mw",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.diesel_power_block.cooldown_s",
    "raw": "<MISSING>",
    "validated": 300.0
  },
  {
    "path": "$.diesel_power_block.debounce_s",
    "raw": "<MISSING>",
    "validated": 1.0
  },
  {
    "path": "$.diesel_power_block.fuel_burn_gal_per_hr_per_unit_at_full_load",
    "raw": "<MISSING>",
    "validated": 230.0
  },
  {
    "path": "$.diesel_power_block.fuel_type",
    "raw": "<MISSING>",
    "validated": "diesel"
  },
  {
    "path": "$.diesel_power_block.min_down_s",
    "raw": "<MISSING>",
    "validated": 300.0
  },
  {
    "path": "$.diesel_power_block.min_fuel_runtime_hours",
    "raw": "<MISSING>",
    "validated": 48.0
  },
  {
    "path": "$.diesel_power_block.min_run_s",
    "raw": "<MISSING>",
    "validated": 900.0
  },
  {
    "path": "$.diesel_power_block.min_stable_load_mw_fraction",
    "raw": "<MISSING>",
    "validated": 0.3
  },
  {
    "path": "$.diesel_power_block.restore_hold_s",
    "raw": "<MISSING>",
    "validated": 300.0
  },
  {
    "path": "$.diesel_units",
    "raw": "<MISSING>",
    "validated": [
      {
        "asset_id": "diesel-000",
        "rated_mw": 20.0,
        "role": "primary",
        "start_offset_s": 0.0,
        "delta_t_start_s": 3600.0,
        "f_block": 1.0,
        "residual_ramp_s": 60.0,
        "min_stable_load_mw": 6.0,
        "min_run_s": 900.0,
        "min_down_s": 300.0,
        "cooldown_s": 300.0,
        "authority_tier": "advisory_only"
      }
    ]
  },
  {
    "path": "$.dispatch_curtailment_response_delay_s",
    "raw": "<MISSING>",
    "validated": 0.5
  },
  {
    "path": "$.dq_inject_events",
    "raw": "<MISSING>",
    "validated": []
  },
  {
    "path": "$.dt_thermal_seconds",
    "raw": "<MISSING>",
    "validated": 90.0
  },
  {
    "path": "$.edl_calendar_month",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.fabric_scenario_id",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.fuel_cell_baseload_target_mw",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.fuel_cell_enabled",
    "raw": "<MISSING>",
    "validated": false
  },
  {
    "path": "$.fuel_cell_initial_state",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.fuel_cell_load_following",
    "raw": "<MISSING>",
    "validated": false
  },
  {
    "path": "$.fuel_cell_min_stable_fraction",
    "raw": "<MISSING>",
    "validated": 0.5
  },
  {
    "path": "$.fuel_cell_ramp_down_rate_mw_per_s",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.fuel_cell_ramp_rate_mw_per_s",
    "raw": "<MISSING>",
    "validated": 0.02
  },
  {
    "path": "$.fuel_cell_rated_mw",
    "raw": "<MISSING>",
    "validated": 0.0
  },
  {
    "path": "$.fuel_cell_stack_count",
    "raw": "<MISSING>",
    "validated": 1
  },
  {
    "path": "$.fuel_cell_state",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.fuel_cell_turbine_commit_fraction",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.fuel_cell_units",
    "raw": "<MISSING>",
    "validated": []
  },
  {
    "path": "$.generation_baseload_mw",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.generation_block",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.generation_peak_following",
    "raw": "<MISSING>",
    "validated": true
  },
  {
    "path": "$.generator_config",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.gpu_load_profile",
    "raw": "<MISSING>",
    "validated": []
  },
  {
    "path": "$.grid_authority_tier",
    "raw": "<MISSING>",
    "validated": "autonomous"
  },
  {
    "path": "$.grid_import_limit_mw",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.grid_import_price_per_mwh",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.irradiance_steps",
    "raw": "<MISSING>",
    "validated": [
      [
        0.0,
        1.0
      ]
    ]
  },
  {
    "path": "$.island_collapse_hz",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.kube_clusters",
    "raw": [
      {
        "cluster_id": "um-k8s-h100",
        "tenant_id": "K8S-H100",
        "scheduler_type": "K8S",
        "capacity_unit": "node",
        "workload_share": 0.4,
        "hardware_profile_id": "enterprise_8gpu_air",
        "max_nodes": 900,
        "min_nodes": 150,
        "mean_interarrival_s": 40.0,
        "mean_job_nodes": 180,
        "job_node_std": 90.0,
        "min_job_nodes": 50,
        "max_job_nodes": 320,
        "mean_job_duration_s": 280.0,
        "min_job_duration_s": 40.0,
        "reorder_window_s": 8.0,
        "ntp_jitter_s": 2.0,
        "headroom_threshold_mw": 37.0,
        "rng_seed": 51
      },
      {
        "cluster_id": "um-slurm-h100",
        "tenant_id": "SLURM-H100",
        "scheduler_type": "SLURM",
        "capacity_unit": "node",
        "workload_share": 0.4,
        "hardware_profile_id": "enterprise_8gpu_air",
        "max_nodes": 900,
        "min_nodes": 150,
        "mean_interarrival_s": 95.0,
        "mean_job_nodes": 220,
        "job_node_std": 100.0,
        "min_job_nodes": 60,
        "max_job_nodes": 340,
        "mean_job_duration_s": 340.0,
        "min_job_duration_s": 45.0,
        "rng_seed": 1051
      },
      {
        "cluster_id": "um-ray-gb200",
        "tenant_id": "RAY-GB200",
        "scheduler_type": "RAY",
        "capacity_unit": "rack",
        "workload_share": 0.2,
        "hardware_profile_id": "nextgen_rack_liquid",
        "max_nodes": 40,
        "min_nodes": 3,
        "mean_interarrival_s": 65.0,
        "mean_job_nodes": 6,
        "job_node_std": 3.0,
        "min_job_nodes": 1,
        "max_job_nodes": 40,
        "mean_job_duration_s": 260.0,
        "min_job_duration_s": 30.0,
        "rng_seed": 2051
      }
    ],
    "validated": [
      {
        "hardware_profile_id": "enterprise_8gpu_air",
        "max_nodes": 900,
        "min_nodes": 150,
        "mean_interarrival_s": 40.0,
        "mean_job_nodes": 180,
        "job_node_std": 90.0,
        "min_job_nodes": 50,
        "max_job_nodes": 320,
        "mean_job_duration_s": 280.0,
        "min_job_duration_s": 40.0,
        "reorder_window_s": 8.0,
        "ntp_jitter_s": 2.0,
        "headroom_threshold_mw": 37.0,
        "rng_seed": 51,
        "node_cpu_milli": 96000,
        "node_memory_mib": 1500000,
        "node_gpu_count": null,
        "node_gpu_type": null,
        "pod_cpu_milli": null,
        "pod_memory_mib": null,
        "pod_gpu_count": null,
        "pod_gpu_types": [],
        "pod_priority": 0,
        "backoff_duration_s": 10.0,
        "max_backoff_retries": 1,
        "container_start_delay_s": 0.0,
        "step_config": null,
        "load_config": null,
        "cluster_id": "um-k8s-h100",
        "tenant_id": "K8S-H100",
        "scheduler_type": "K8S",
        "capacity_unit": "node",
        "workload_share": 0.4
      },
      {
        "hardware_profile_id": "enterprise_8gpu_air",
        "max_nodes": 900,
        "min_nodes": 150,
        "mean_interarrival_s": 95.0,
        "mean_job_nodes": 220,
        "job_node_std": 100.0,
        "min_job_nodes": 60,
        "max_job_nodes": 340,
        "mean_job_duration_s": 340.0,
        "min_job_duration_s": 45.0,
        "reorder_window_s": 10.0,
        "ntp_jitter_s": 2.0,
        "headroom_threshold_mw": 2.5,
        "rng_seed": 1051,
        "node_cpu_milli": 96000,
        "node_memory_mib": 1500000,
        "node_gpu_count": null,
        "node_gpu_type": null,
        "pod_cpu_milli": null,
        "pod_memory_mib": null,
        "pod_gpu_count": null,
        "pod_gpu_types": [],
        "pod_priority": 0,
        "backoff_duration_s": 10.0,
        "max_backoff_retries": 1,
        "container_start_delay_s": 0.0,
        "step_config": null,
        "load_config": null,
        "cluster_id": "um-slurm-h100",
        "tenant_id": "SLURM-H100",
        "scheduler_type": "SLURM",
        "capacity_unit": "node",
        "workload_share": 0.4
      },
      {
        "hardware_profile_id": "nextgen_rack_liquid",
        "max_nodes": 40,
        "min_nodes": 3,
        "mean_interarrival_s": 65.0,
        "mean_job_nodes": 6,
        "job_node_std": 3.0,
        "min_job_nodes": 1,
        "max_job_nodes": 40,
        "mean_job_duration_s": 260.0,
        "min_job_duration_s": 30.0,
        "reorder_window_s": 10.0,
        "ntp_jitter_s": 2.0,
        "headroom_threshold_mw": 2.5,
        "rng_seed": 2051,
        "node_cpu_milli": 96000,
        "node_memory_mib": 1500000,
        "node_gpu_count": null,
        "node_gpu_type": null,
        "pod_cpu_milli": null,
        "pod_memory_mib": null,
        "pod_gpu_count": null,
        "pod_gpu_types": [],
        "pod_priority": 0,
        "backoff_duration_s": 10.0,
        "max_backoff_retries": 1,
        "container_start_delay_s": 0.0,
        "step_config": null,
        "load_config": null,
        "cluster_id": "um-ray-gb200",
        "tenant_id": "RAY-GB200",
        "scheduler_type": "RAY",
        "capacity_unit": "rack",
        "workload_share": 0.2
      }
    ]
  },
  {
    "path": "$.kube_config",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.load_config",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.maintenance_config",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.of_trip_hz",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.of_warning_hz",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.operating_tier",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.operator_response_profile",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.param_sampling_config",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.phase2b_reference_base_scenario",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.phase2b_reference_days",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.phase2b_reference_family",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.plant_alpha_max",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.plant_dt_thermal_seconds",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.plant_tau_seconds",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.pms_config",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.pre_staging_config",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.procurement_config",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.pue_base",
    "raw": "<MISSING>",
    "validated": 1.03
  },
  {
    "path": "$.ramp_relaxation_config",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.relay_81u_delay_s",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.relay_81u_threshold_hz",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.site_latitude",
    "raw": "<MISSING>",
    "validated": 37.3541
  },
  {
    "path": "$.site_longitude",
    "raw": "<MISSING>",
    "validated": -121.9552
  },
  {
    "path": "$.site_name",
    "raw": "<MISSING>",
    "validated": "Santa Clara, CA, USA"
  },
  {
    "path": "$.site_utc_offset_h",
    "raw": "<MISSING>",
    "validated": -8.130346666666666
  },
  {
    "path": "$.slurm_config.accounting_enforce",
    "raw": "<MISSING>",
    "validated": []
  },
  {
    "path": "$.slurm_config.accounts",
    "raw": "<MISSING>",
    "validated": []
  },
  {
    "path": "$.slurm_config.backfill",
    "raw": "<MISSING>",
    "validated": true
  },
  {
    "path": "$.slurm_config.burst_buffers",
    "raw": "<MISSING>",
    "validated": []
  },
  {
    "path": "$.slurm_config.cgroup_enforce",
    "raw": "<MISSING>",
    "validated": true
  },
  {
    "path": "$.slurm_config.federation",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.slurm_config.jobs",
    "raw": [
      {
        "job_id": "um-slurm-training-01",
        "job_name": "slurm-training-01",
        "user": "slurm-demo",
        "account": "research",
        "arrival_time": 30.0,
        "duration": 240.0,
        "node_count": 2,
        "gpus_per_node": 8,
        "cpus_per_node": 96,
        "memory_mb_per_node": 100000,
        "gpu_model": "h100",
        "partition": "gpu",
        "priority": 100.0,
        "qos": "normal",
        "hardware_profile_id": "enterprise_8gpu_air",
        "tenant_id": "SLURM-H100",
        "workload_class": "training",
        "command": "python train.py"
      },
      {
        "job_id": "um-slurm-training-02",
        "job_name": "slurm-training-02",
        "user": "slurm-demo",
        "account": "research",
        "arrival_time": 310.0,
        "duration": 300.0,
        "node_count": 4,
        "gpus_per_node": 8,
        "cpus_per_node": 96,
        "memory_mb_per_node": 100000,
        "gpu_model": "h100",
        "partition": "gpu",
        "priority": 110.0,
        "qos": "normal",
        "hardware_profile_id": "enterprise_8gpu_air",
        "tenant_id": "SLURM-H100",
        "workload_class": "training",
        "command": "python train.py --resume"
      },
      {
        "job_id": "um-slurm-inference-03",
        "job_name": "slurm-inference-03",
        "user": "slurm-demo",
        "account": "research",
        "arrival_time": 920.0,
        "duration": 600.0,
        "node_count": 2,
        "gpus_per_node": 8,
        "cpus_per_node": 96,
        "memory_mb_per_node": 100000,
        "gpu_model": "h100",
        "partition": "gpu",
        "priority": 90.0,
        "qos": "normal",
        "hardware_profile_id": "enterprise_8gpu_air",
        "tenant_id": "SLURM-H100",
        "workload_class": "inference",
        "command": "python serve.py"
      }
    ],
    "validated": [
      {
        "job_id": "um-slurm-training-01",
        "job_name": "slurm-training-01",
        "user": "slurm-demo",
        "account": "research",
        "arrival_time": 30.0,
        "duration": 240.0,
        "time_limit_s": null,
        "deadline": null,
        "node_count": 2,
        "ntasks": 1,
        "cpus_per_task": 1,
        "gpus_per_node": 8,
        "cpus_per_node": 96,
        "memory_mb_per_node": 100000,
        "memory_mb_per_cpu": null,
        "tmp_disk_mb": 0,
        "gpu_model": "h100",
        "gres": {},
        "partition": "gpu",
        "features": [],
        "topology": null,
        "exclusive": false,
        "oversubscribe": false,
        "licenses": {},
        "burst_buffer": null,
        "burst_buffer_mb": 0,
        "tres_per_job": {},
        "priority": 100.0,
        "qos": "normal",
        "qos_weight": 1.0,
        "fair_share_usage": 0.0,
        "dependencies": [],
        "reservation": null,
        "requeue": false,
        "preemptible": true,
        "checkpoint_interval_s": null,
        "checkpoint_signal_s": null,
        "array_start": null,
        "array_end": null,
        "array_step": 1,
        "array_max_concurrent": null,
        "hetero_group_id": null,
        "hetero_component": null,
        "federation": null,
        "cluster": null,
        "hardware_profile_id": "enterprise_8gpu_air",
        "workload_class": "training",
        "tenant_id": "SLURM-H100",
        "command": "python train.py",
        "environment": {},
        "phases": [],
        "gpu_power_kw": 10.2
      },
      {
        "job_id": "um-slurm-training-02",
        "job_name": "slurm-training-02",
        "user": "slurm-demo",
        "account": "research",
        "arrival_time": 310.0,
        "duration": 300.0,
        "time_limit_s": null,
        "deadline": null,
        "node_count": 4,
        "ntasks": 1,
        "cpus_per_task": 1,
        "gpus_per_node": 8,
        "cpus_per_node": 96,
        "memory_mb_per_node": 100000,
        "memory_mb_per_cpu": null,
        "tmp_disk_mb": 0,
        "gpu_model": "h100",
        "gres": {},
        "partition": "gpu",
        "features": [],
        "topology": null,
        "exclusive": false,
        "oversubscribe": false,
        "licenses": {},
        "burst_buffer": null,
        "burst_buffer_mb": 0,
        "tres_per_job": {},
        "priority": 110.0,
        "qos": "normal",
        "qos_weight": 1.0,
        "fair_share_usage": 0.0,
        "dependencies": [],
        "reservation": null,
        "requeue": false,
        "preemptible": true,
        "checkpoint_interval_s": null,
        "checkpoint_signal_s": null,
        "array_start": null,
        "array_end": null,
        "array_step": 1,
        "array_max_concurrent": null,
        "hetero_group_id": null,
        "hetero_component": null,
        "federation": null,
        "cluster": null,
        "hardware_profile_id": "enterprise_8gpu_air",
        "workload_class": "training",
        "tenant_id": "SLURM-H100",
        "command": "python train.py --resume",
        "environment": {},
        "phases": [],
        "gpu_power_kw": 10.2
      },
      {
        "job_id": "um-slurm-inference-03",
        "job_name": "slurm-inference-03",
        "user": "slurm-demo",
        "account": "research",
        "arrival_time": 920.0,
        "duration": 600.0,
        "time_limit_s": null,
        "deadline": null,
        "node_count": 2,
        "ntasks": 1,
        "cpus_per_task": 1,
        "gpus_per_node": 8,
        "cpus_per_node": 96,
        "memory_mb_per_node": 100000,
        "memory_mb_per_cpu": null,
        "tmp_disk_mb": 0,
        "gpu_model": "h100",
        "gres": {},
        "partition": "gpu",
        "features": [],
        "topology": null,
        "exclusive": false,
        "oversubscribe": false,
        "licenses": {},
        "burst_buffer": null,
        "burst_buffer_mb": 0,
        "tres_per_job": {},
        "priority": 90.0,
        "qos": "normal",
        "qos_weight": 1.0,
        "fair_share_usage": 0.0,
        "dependencies": [],
        "reservation": null,
        "requeue": false,
        "preemptible": true,
        "checkpoint_interval_s": null,
        "checkpoint_signal_s": null,
        "array_start": null,
        "array_end": null,
        "array_step": 1,
        "array_max_concurrent": null,
        "hetero_group_id": null,
        "hetero_component": null,
        "federation": null,
        "cluster": null,
        "hardware_profile_id": "enterprise_8gpu_air",
        "workload_class": "inference",
        "tenant_id": "SLURM-H100",
        "command": "python serve.py",
        "environment": {},
        "phases": [],
        "gpu_power_kw": 10.2
      }
    ]
  },
  {
    "path": "$.slurm_config.licenses",
    "raw": "<MISSING>",
    "validated": []
  },
  {
    "path": "$.slurm_config.max_array_size",
    "raw": "<MISSING>",
    "validated": 10000
  },
  {
    "path": "$.slurm_config.max_job_count",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.slurm_config.nodes",
    "raw": [
      {
        "node_id": "um-slurm-01",
        "partition": "gpu",
        "gpus": 8,
        "gpu_model": "h100",
        "cpus": 96,
        "memory_mb": 100000,
        "features": [
          "h100",
          "nvlink"
        ]
      },
      {
        "node_id": "um-slurm-02",
        "partition": "gpu",
        "gpus": 8,
        "gpu_model": "h100",
        "cpus": 96,
        "memory_mb": 100000,
        "features": [
          "h100",
          "nvlink"
        ]
      },
      {
        "node_id": "um-slurm-03",
        "partition": "gpu",
        "gpus": 8,
        "gpu_model": "h100",
        "cpus": 96,
        "memory_mb": 100000,
        "features": [
          "h100",
          "nvlink"
        ]
      },
      {
        "node_id": "um-slurm-04",
        "partition": "gpu",
        "gpus": 8,
        "gpu_model": "h100",
        "cpus": 96,
        "memory_mb": 100000,
        "features": [
          "h100",
          "nvlink"
        ]
      },
      {
        "node_id": "um-slurm-05",
        "partition": "gpu",
        "gpus": 8,
        "gpu_model": "h100",
        "cpus": 96,
        "memory_mb": 100000,
        "features": [
          "h100",
          "nvlink"
        ]
      },
      {
        "node_id": "um-slurm-06",
        "partition": "gpu",
        "gpus": 8,
        "gpu_model": "h100",
        "cpus": 96,
        "memory_mb": 100000,
        "features": [
          "h100",
          "nvlink"
        ]
      },
      {
        "node_id": "um-slurm-07",
        "partition": "gpu",
        "gpus": 8,
        "gpu_model": "h100",
        "cpus": 96,
        "memory_mb": 100000,
        "features": [
          "h100",
          "nvlink"
        ]
      },
      {
        "node_id": "um-slurm-08",
        "partition": "gpu",
        "gpus": 8,
        "gpu_model": "h100",
        "cpus": 96,
        "memory_mb": 100000,
        "features": [
          "h100",
          "nvlink"
        ]
      }
    ],
    "validated": [
      {
        "node_id": "um-slurm-01",
        "partition": "gpu",
        "gpus": 8,
        "gpu_model": "h100",
        "cpus": 96,
        "memory_mb": 100000,
        "features": [
          "h100",
          "nvlink"
        ],
        "state": "IDLE",
        "sockets": 1,
        "cores_per_socket": 1,
        "threads_per_core": 1,
        "topology": {},
        "gres": {}
      },
      {
        "node_id": "um-slurm-02",
        "partition": "gpu",
        "gpus": 8,
        "gpu_model": "h100",
        "cpus": 96,
        "memory_mb": 100000,
        "features": [
          "h100",
          "nvlink"
        ],
        "state": "IDLE",
        "sockets": 1,
        "cores_per_socket": 1,
        "threads_per_core": 1,
        "topology": {},
        "gres": {}
      },
      {
        "node_id": "um-slurm-03",
        "partition": "gpu",
        "gpus": 8,
        "gpu_model": "h100",
        "cpus": 96,
        "memory_mb": 100000,
        "features": [
          "h100",
          "nvlink"
        ],
        "state": "IDLE",
        "sockets": 1,
        "cores_per_socket": 1,
        "threads_per_core": 1,
        "topology": {},
        "gres": {}
      },
      {
        "node_id": "um-slurm-04",
        "partition": "gpu",
        "gpus": 8,
        "gpu_model": "h100",
        "cpus": 96,
        "memory_mb": 100000,
        "features": [
          "h100",
          "nvlink"
        ],
        "state": "IDLE",
        "sockets": 1,
        "cores_per_socket": 1,
        "threads_per_core": 1,
        "topology": {},
        "gres": {}
      },
      {
        "node_id": "um-slurm-05",
        "partition": "gpu",
        "gpus": 8,
        "gpu_model": "h100",
        "cpus": 96,
        "memory_mb": 100000,
        "features": [
          "h100",
          "nvlink"
        ],
        "state": "IDLE",
        "sockets": 1,
        "cores_per_socket": 1,
        "threads_per_core": 1,
        "topology": {},
        "gres": {}
      },
      {
        "node_id": "um-slurm-06",
        "partition": "gpu",
        "gpus": 8,
        "gpu_model": "h100",
        "cpus": 96,
        "memory_mb": 100000,
        "features": [
          "h100",
          "nvlink"
        ],
        "state": "IDLE",
        "sockets": 1,
        "cores_per_socket": 1,
        "threads_per_core": 1,
        "topology": {},
        "gres": {}
      },
      {
        "node_id": "um-slurm-07",
        "partition": "gpu",
        "gpus": 8,
        "gpu_model": "h100",
        "cpus": 96,
        "memory_mb": 100000,
        "features": [
          "h100",
          "nvlink"
        ],
        "state": "IDLE",
        "sockets": 1,
        "cores_per_socket": 1,
        "threads_per_core": 1,
        "topology": {},
        "gres": {}
      },
      {
        "node_id": "um-slurm-08",
        "partition": "gpu",
        "gpus": 8,
        "gpu_model": "h100",
        "cpus": 96,
        "memory_mb": 100000,
        "features": [
          "h100",
          "nvlink"
        ],
        "state": "IDLE",
        "sockets": 1,
        "cores_per_socket": 1,
        "threads_per_core": 1,
        "topology": {},
        "gres": {}
      }
    ]
  },
  {
    "path": "$.slurm_config.partitions",
    "raw": [
      {
        "name": "gpu",
        "nodes": [
          "um-slurm-01",
          "um-slurm-02",
          "um-slurm-03",
          "um-slurm-04",
          "um-slurm-05",
          "um-slurm-06",
          "um-slurm-07",
          "um-slurm-08"
        ],
        "default": true
      }
    ],
    "validated": [
      {
        "name": "gpu",
        "nodes": [
          "um-slurm-01",
          "um-slurm-02",
          "um-slurm-03",
          "um-slurm-04",
          "um-slurm-05",
          "um-slurm-06",
          "um-slurm-07",
          "um-slurm-08"
        ],
        "state": "UP",
        "default": true,
        "max_time_s": null,
        "allow_accounts": [],
        "allow_qos": [],
        "oversubscribe": false
      }
    ]
  },
  {
    "path": "$.slurm_config.qos",
    "raw": [
      {
        "name": "normal",
        "priority_factor": 1.0
      }
    ],
    "validated": [
      {
        "name": "normal",
        "priority_factor": 1.0,
        "max_jobs": null,
        "max_tres": {},
        "max_wall_time_s": null,
        "allowed_accounts": [],
        "preempt_mode": "off",
        "preempt_exempt_time_s": 0.0
      }
    ]
  },
  {
    "path": "$.slurm_config.qos_weights",
    "raw": "<MISSING>",
    "validated": {}
  },
  {
    "path": "$.slurm_config.reservations",
    "raw": "<MISSING>",
    "validated": []
  },
  {
    "path": "$.slurm_config.topology_plugin",
    "raw": "<MISSING>",
    "validated": "flat"
  },
  {
    "path": "$.solar_origin_utc_hour",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.solar_rated_mw",
    "raw": "<MISSING>",
    "validated": 0.0
  },
  {
    "path": "$.stressor_gen_config",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.tau_seconds",
    "raw": "<MISSING>",
    "validated": 20.0
  },
  {
    "path": "$.telemetry_corruption_config",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.tenant_budgets",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.tenant_events",
    "raw": "<MISSING>",
    "validated": []
  },
  {
    "path": "$.turbine_commitment_floor",
    "raw": "<MISSING>",
    "validated": 1
  },
  {
    "path": "$.turbine_commitment_mode",
    "raw": "<MISSING>",
    "validated": "disabled"
  },
  {
    "path": "$.turbine_commitment_sensitivity_mw",
    "raw": "<MISSING>",
    "validated": 2.0
  },
  {
    "path": "$.turbine_forecast_lead_seconds",
    "raw": "<MISSING>",
    "validated": 600.0
  },
  {
    "path": "$.turbine_units",
    "raw": [
      {
        "asset_id": "gt-spin-01",
        "rated_mw": 25.0,
        "r_asset_mw_per_s": 0.5,
        "hot_standby": false,
        "initial_state": "spinning",
        "p_min_stable_frac": 0.35,
        "thermal_state": "hot",
        "hot_start_s": 300.0,
        "warm_start_s": 360.0,
        "cold_start_s": 600.0,
        "gt_mode": "aero"
      },
      {
        "asset_id": "gt-spin-02",
        "rated_mw": 25.0,
        "r_asset_mw_per_s": 0.5,
        "hot_standby": false,
        "initial_state": "spinning",
        "p_min_stable_frac": 0.35,
        "thermal_state": "hot",
        "hot_start_s": 300.0,
        "warm_start_s": 360.0,
        "cold_start_s": 600.0,
        "gt_mode": "aero"
      },
      {
        "asset_id": "gt-hot-01",
        "rated_mw": 25.0,
        "r_asset_mw_per_s": 0.5,
        "hot_standby": true,
        "p_min_stable_frac": 0.35,
        "thermal_state": "hot",
        "hot_start_s": 300.0,
        "warm_start_s": 360.0,
        "cold_start_s": 600.0,
        "gt_mode": "aero"
      },
      {
        "asset_id": "gt-hot-02",
        "rated_mw": 25.0,
        "r_asset_mw_per_s": 0.5,
        "hot_standby": true,
        "p_min_stable_frac": 0.35,
        "thermal_state": "hot",
        "hot_start_s": 300.0,
        "warm_start_s": 360.0,
        "cold_start_s": 600.0,
        "gt_mode": "aero"
      }
    ],
    "validated": [
      {
        "asset_id": "gt-spin-01",
        "rated_mw": 25.0,
        "r_asset_mw_per_s": 0.5,
        "run_hours_h": null,
        "hot_standby": false,
        "gt_mode": "aero",
        "initial_state": "spinning",
        "p_min_stable_frac": 0.35,
        "t_min_run_s": 1800.0,
        "min_run_enabled": true,
        "t_min_down_s": 900.0,
        "min_down_enabled": true,
        "cold_start_s": 600.0,
        "warm_start_s": 360.0,
        "hot_start_s": 300.0,
        "thermal_state": "hot",
        "fuel": null,
        "power_factor": null,
        "inertia_constant_s": null,
        "droop_r": null,
        "valve_actuation_tc_s": null,
        "fuel_to_power_tc_s": null,
        "max_instantaneous_load_step_mw": null,
        "authority_tier": "autonomous"
      },
      {
        "asset_id": "gt-spin-02",
        "rated_mw": 25.0,
        "r_asset_mw_per_s": 0.5,
        "run_hours_h": null,
        "hot_standby": false,
        "gt_mode": "aero",
        "initial_state": "spinning",
        "p_min_stable_frac": 0.35,
        "t_min_run_s": 1800.0,
        "min_run_enabled": true,
        "t_min_down_s": 900.0,
        "min_down_enabled": true,
        "cold_start_s": 600.0,
        "warm_start_s": 360.0,
        "hot_start_s": 300.0,
        "thermal_state": "hot",
        "fuel": null,
        "power_factor": null,
        "inertia_constant_s": null,
        "droop_r": null,
        "valve_actuation_tc_s": null,
        "fuel_to_power_tc_s": null,
        "max_instantaneous_load_step_mw": null,
        "authority_tier": "autonomous"
      },
      {
        "asset_id": "gt-hot-01",
        "rated_mw": 25.0,
        "r_asset_mw_per_s": 0.5,
        "run_hours_h": null,
        "hot_standby": true,
        "gt_mode": "aero",
        "initial_state": "offline",
        "p_min_stable_frac": 0.35,
        "t_min_run_s": 1800.0,
        "min_run_enabled": true,
        "t_min_down_s": 900.0,
        "min_down_enabled": true,
        "cold_start_s": 600.0,
        "warm_start_s": 360.0,
        "hot_start_s": 300.0,
        "thermal_state": "hot",
        "fuel": null,
        "power_factor": null,
        "inertia_constant_s": null,
        "droop_r": null,
        "valve_actuation_tc_s": null,
        "fuel_to_power_tc_s": null,
        "max_instantaneous_load_step_mw": null,
        "authority_tier": "autonomous"
      },
      {
        "asset_id": "gt-hot-02",
        "rated_mw": 25.0,
        "r_asset_mw_per_s": 0.5,
        "run_hours_h": null,
        "hot_standby": true,
        "gt_mode": "aero",
        "initial_state": "offline",
        "p_min_stable_frac": 0.35,
        "t_min_run_s": 1800.0,
        "min_run_enabled": true,
        "t_min_down_s": 900.0,
        "min_down_enabled": true,
        "cold_start_s": 600.0,
        "warm_start_s": 360.0,
        "hot_start_s": 300.0,
        "thermal_state": "hot",
        "fuel": null,
        "power_factor": null,
        "inertia_constant_s": null,
        "droop_r": null,
        "valve_actuation_tc_s": null,
        "fuel_to_power_tc_s": null,
        "max_instantaneous_load_step_mw": null,
        "authority_tier": "autonomous"
      }
    ]
  },
  {
    "path": "$.uf_warning_hz",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.ufls_stage1_hz",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.ufls_stages",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.ui_bess_rated_mw",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.ui_bess_usable_mwh",
    "raw": "<MISSING>",
    "validated": null
  },
  {
    "path": "$.workload_events",
    "raw": [
      {
        "event_id": "evt-signal-burst-01-start",
        "job_id": "signal-burst-01",
        "event_type": "starting",
        "timestamp": 30.0,
        "node_count": 4283,
        "hardware_profile_id": "enterprise_8gpu_air",
        "scheduler_type": "K8S",
        "cluster_id": "um-k8s-h100",
        "tenant_id": "K8S-H100"
      },
      {
        "event_id": "evt-signal-burst-01-end",
        "job_id": "signal-burst-01",
        "event_type": "job_end",
        "timestamp": 270.0,
        "node_count": 0,
        "hardware_profile_id": "enterprise_8gpu_air",
        "scheduler_type": "K8S",
        "cluster_id": "um-k8s-h100",
        "tenant_id": "K8S-H100"
      },
      {
        "event_id": "evt-signal-burst-02-start",
        "job_id": "signal-burst-02",
        "event_type": "starting",
        "timestamp": 310.0,
        "node_count": 8566,
        "hardware_profile_id": "enterprise_8gpu_air",
        "scheduler_type": "SLURM",
        "cluster_id": "um-slurm-cluster",
        "tenant_id": "SLURM-H100"
      },
      {
        "event_id": "evt-signal-burst-02-end",
        "job_id": "signal-burst-02",
        "event_type": "job_end",
        "timestamp": 610.0,
        "node_count": 0,
        "hardware_profile_id": "enterprise_8gpu_air",
        "scheduler_type": "SLURM",
        "cluster_id": "um-slurm-cluster",
        "tenant_id": "SLURM-H100"
      },
      {
        "event_id": "evt-signal-burst-03-start",
        "job_id": "signal-burst-03",
        "event_type": "starting",
        "timestamp": 920.0,
        "node_count": 3426,
        "hardware_profile_id": "enterprise_8gpu_air",
        "scheduler_type": "RAY",
        "cluster_id": "um-ray-gb200",
        "tenant_id": "RAY-GB200",
        "ray_cluster_id": "um-ray-gb200",
        "infrastructure_allocation_id": "um-ray-allocation-03",
        "ray_workload_id": "signal-burst-03"
      },
      {
        "event_id": "evt-signal-burst-03-end",
        "job_id": "signal-burst-03",
        "event_type": "job_end",
        "timestamp": 1520.0,
        "node_count": 0,
        "hardware_profile_id": "enterprise_8gpu_air",
        "scheduler_type": "RAY",
        "cluster_id": "um-ray-gb200",
        "tenant_id": "RAY-GB200",
        "ray_cluster_id": "um-ray-gb200",
        "infrastructure_allocation_id": "um-ray-allocation-03",
        "ray_workload_id": "signal-burst-03"
      },
      {
        "event_id": "evt-signal-burst-04-start",
        "job_id": "signal-burst-04",
        "event_type": "starting",
        "timestamp": 1850.0,
        "node_count": 7995,
        "hardware_profile_id": "enterprise_8gpu_air",
        "scheduler_type": "K8S",
        "cluster_id": "um-k8s-h100",
        "tenant_id": "K8S-H100"
      },
      {
        "event_id": "evt-signal-burst-04-end",
        "job_id": "signal-burst-04",
        "event_type": "job_end",
        "timestamp": 2450.0,
        "node_count": 0,
        "hardware_profile_id": "enterprise_8gpu_air",
        "scheduler_type": "K8S",
        "cluster_id": "um-k8s-h100",
        "tenant_id": "K8S-H100"
      },
      {
        "event_id": "evt-signal-burst-05-start",
        "job_id": "signal-burst-05",
        "event_type": "starting",
        "timestamp": 2700.0,
        "node_count": 5711,
        "hardware_profile_id": "enterprise_8gpu_air",
        "scheduler_type": "RAY",
        "cluster_id": "um-ray-gb200",
        "tenant_id": "RAY-GB200",
        "ray_cluster_id": "um-ray-gb200",
        "infrastructure_allocation_id": "um-ray-allocation-05",
        "ray_workload_id": "signal-burst-05"
      },
      {
        "event_id": "evt-signal-burst-05-end",
        "job_id": "signal-burst-05",
        "event_type": "job_end",
        "timestamp": 3300.0,
        "node_count": 0,
        "hardware_profile_id": "enterprise_8gpu_air",
        "scheduler_type": "RAY",
        "cluster_id": "um-ray-gb200",
        "tenant_id": "RAY-GB200",
        "ray_cluster_id": "um-ray-gb200",
        "infrastructure_allocation_id": "um-ray-allocation-05",
        "ray_workload_id": "signal-burst-05"
      }
    ],
    "validated": [
      {
        "event_id": "evt-signal-burst-01-start",
        "job_id": "signal-burst-01",
        "event_type": "starting",
        "timestamp": 30.0,
        "node_count": 4283,
        "hardware_profile_id": "enterprise_8gpu_air",
        "workload_class": "training",
        "scheduler_domain": null,
        "tenant_id": "K8S-H100",
        "cluster_id": "um-k8s-h100",
        "scheduler_type": "K8S",
        "capacity_unit": null,
        "gpus_per_unit": 1,
        "infrastructure_allocation_id": null,
        "ray_cluster_id": null,
        "ray_workload_id": null,
        "admission_domain_id": null,
        "admission_queue_id": null,
        "capacity_budget_id": null,
        "admission_provider": null,
        "power_enforcement_policy": null,
        "request_rate": null,
        "renewable_shortfall_mw": 0.0,
        "electrical_group_id": null
      },
      {
        "event_id": "evt-signal-burst-01-end",
        "job_id": "signal-burst-01",
        "event_type": "job_end",
        "timestamp": 270.0,
        "node_count": 0,
        "hardware_profile_id": "enterprise_8gpu_air",
        "workload_class": "training",
        "scheduler_domain": null,
        "tenant_id": "K8S-H100",
        "cluster_id": "um-k8s-h100",
        "scheduler_type": "K8S",
        "capacity_unit": null,
        "gpus_per_unit": 1,
        "infrastructure_allocation_id": null,
        "ray_cluster_id": null,
        "ray_workload_id": null,
        "admission_domain_id": null,
        "admission_queue_id": null,
        "capacity_budget_id": null,
        "admission_provider": null,
        "power_enforcement_policy": null,
        "request_rate": null,
        "renewable_shortfall_mw": 0.0,
        "electrical_group_id": null
      },
      {
        "event_id": "evt-signal-burst-02-start",
        "job_id": "signal-burst-02",
        "event_type": "starting",
        "timestamp": 310.0,
        "node_count": 8566,
        "hardware_profile_id": "enterprise_8gpu_air",
        "workload_class": "training",
        "scheduler_domain": null,
        "tenant_id": "SLURM-H100",
        "cluster_id": "um-slurm-cluster",
        "scheduler_type": "SLURM",
        "capacity_unit": null,
        "gpus_per_unit": 1,
        "infrastructure_allocation_id": null,
        "ray_cluster_id": null,
        "ray_workload_id": null,
        "admission_domain_id": null,
        "admission_queue_id": null,
        "capacity_budget_id": null,
        "admission_provider": null,
        "power_enforcement_policy": null,
        "request_rate": null,
        "renewable_shortfall_mw": 0.0,
        "electrical_group_id": null
      },
      {
        "event_id": "evt-signal-burst-02-end",
        "job_id": "signal-burst-02",
        "event_type": "job_end",
        "timestamp": 610.0,
        "node_count": 0,
        "hardware_profile_id": "enterprise_8gpu_air",
        "workload_class": "training",
        "scheduler_domain": null,
        "tenant_id": "SLURM-H100",
        "cluster_id": "um-slurm-cluster",
        "scheduler_type": "SLURM",
        "capacity_unit": null,
        "gpus_per_unit": 1,
        "infrastructure_allocation_id": null,
        "ray_cluster_id": null,
        "ray_workload_id": null,
        "admission_domain_id": null,
        "admission_queue_id": null,
        "capacity_budget_id": null,
        "admission_provider": null,
        "power_enforcement_policy": null,
        "request_rate": null,
        "renewable_shortfall_mw": 0.0,
        "electrical_group_id": null
      },
      {
        "event_id": "evt-signal-burst-03-start",
        "job_id": "signal-burst-03",
        "event_type": "starting",
        "timestamp": 920.0,
        "node_count": 3426,
        "hardware_profile_id": "enterprise_8gpu_air",
        "workload_class": "training",
        "scheduler_domain": null,
        "tenant_id": "RAY-GB200",
        "cluster_id": "um-ray-gb200",
        "scheduler_type": "RAY",
        "capacity_unit": null,
        "gpus_per_unit": 1,
        "infrastructure_allocation_id": "um-ray-allocation-03",
        "ray_cluster_id": "um-ray-gb200",
        "ray_workload_id": "signal-burst-03",
        "admission_domain_id": null,
        "admission_queue_id": null,
        "capacity_budget_id": null,
        "admission_provider": null,
        "power_enforcement_policy": null,
        "request_rate": null,
        "renewable_shortfall_mw": 0.0,
        "electrical_group_id": null
      },
      {
        "event_id": "evt-signal-burst-03-end",
        "job_id": "signal-burst-03",
        "event_type": "job_end",
        "timestamp": 1520.0,
        "node_count": 0,
        "hardware_profile_id": "enterprise_8gpu_air",
        "workload_class": "training",
        "scheduler_domain": null,
        "tenant_id": "RAY-GB200",
        "cluster_id": "um-ray-gb200",
        "scheduler_type": "RAY",
        "capacity_unit": null,
        "gpus_per_unit": 1,
        "infrastructure_allocation_id": "um-ray-allocation-03",
        "ray_cluster_id": "um-ray-gb200",
        "ray_workload_id": "signal-burst-03",
        "admission_domain_id": null,
        "admission_queue_id": null,
        "capacity_budget_id": null,
        "admission_provider": null,
        "power_enforcement_policy": null,
        "request_rate": null,
        "renewable_shortfall_mw": 0.0,
        "electrical_group_id": null
      },
      {
        "event_id": "evt-signal-burst-04-start",
        "job_id": "signal-burst-04",
        "event_type": "starting",
        "timestamp": 1850.0,
        "node_count": 7995,
        "hardware_profile_id": "enterprise_8gpu_air",
        "workload_class": "training",
        "scheduler_domain": null,
        "tenant_id": "K8S-H100",
        "cluster_id": "um-k8s-h100",
        "scheduler_type": "K8S",
        "capacity_unit": null,
        "gpus_per_unit": 1,
        "infrastructure_allocation_id": null,
        "ray_cluster_id": null,
        "ray_workload_id": null,
        "admission_domain_id": null,
        "admission_queue_id": null,
        "capacity_budget_id": null,
        "admission_provider": null,
        "power_enforcement_policy": null,
        "request_rate": null,
        "renewable_shortfall_mw": 0.0,
        "electrical_group_id": null
      },
      {
        "event_id": "evt-signal-burst-04-end",
        "job_id": "signal-burst-04",
        "event_type": "job_end",
        "timestamp": 2450.0,
        "node_count": 0,
        "hardware_profile_id": "enterprise_8gpu_air",
        "workload_class": "training",
        "scheduler_domain": null,
        "tenant_id": "K8S-H100",
        "cluster_id": "um-k8s-h100",
        "scheduler_type": "K8S",
        "capacity_unit": null,
        "gpus_per_unit": 1,
        "infrastructure_allocation_id": null,
        "ray_cluster_id": null,
        "ray_workload_id": null,
        "admission_domain_id": null,
        "admission_queue_id": null,
        "capacity_budget_id": null,
        "admission_provider": null,
        "power_enforcement_policy": null,
        "request_rate": null,
        "renewable_shortfall_mw": 0.0,
        "electrical_group_id": null
      },
      {
        "event_id": "evt-signal-burst-05-start",
        "job_id": "signal-burst-05",
        "event_type": "starting",
        "timestamp": 2700.0,
        "node_count": 5711,
        "hardware_profile_id": "enterprise_8gpu_air",
        "workload_class": "training",
        "scheduler_domain": null,
        "tenant_id": "RAY-GB200",
        "cluster_id": "um-ray-gb200",
        "scheduler_type": "RAY",
        "capacity_unit": null,
        "gpus_per_unit": 1,
        "infrastructure_allocation_id": "um-ray-allocation-05",
        "ray_cluster_id": "um-ray-gb200",
        "ray_workload_id": "signal-burst-05",
        "admission_domain_id": null,
        "admission_queue_id": null,
        "capacity_budget_id": null,
        "admission_provider": null,
        "power_enforcement_policy": null,
        "request_rate": null,
        "renewable_shortfall_mw": 0.0,
        "electrical_group_id": null
      },
      {
        "event_id": "evt-signal-burst-05-end",
        "job_id": "signal-burst-05",
        "event_type": "job_end",
        "timestamp": 3300.0,
        "node_count": 0,
        "hardware_profile_id": "enterprise_8gpu_air",
        "workload_class": "training",
        "scheduler_domain": null,
        "tenant_id": "RAY-GB200",
        "cluster_id": "um-ray-gb200",
        "scheduler_type": "RAY",
        "capacity_unit": null,
        "gpus_per_unit": 1,
        "infrastructure_allocation_id": "um-ray-allocation-05",
        "ray_cluster_id": "um-ray-gb200",
        "ray_workload_id": "signal-burst-05",
        "admission_domain_id": null,
        "admission_queue_id": null,
        "capacity_budget_id": null,
        "admission_provider": null,
        "power_enforcement_policy": null,
        "request_rate": null,
        "renewable_shortfall_mw": 0.0,
        "electrical_group_id": null
      }
    ]
  },
  {
    "path": "$.workload_floor_fraction",
    "raw": "<MISSING>",
    "validated": null
  }
]
```

## Appendix D — All authority_tier / advisory_only source occurrences

```json
[
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/routes/scenarios.py",
    "line": 413,
    "text": "            grid_authority_tier=\"confirm\","
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/routes/scenarios.py",
    "line": 1169,
    "text": "                \"authority_tier\": \"advisory_only\","
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/routes/scenarios.py",
    "line": 1184,
    "text": "                    \"authority_tier\": \"advisory_only\","
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py",
    "line": 487,
    "text": "    authority_tier: Optional[str] = Field("
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py",
    "line": 732,
    "text": "    authority_tier: Literal[\"advisory_only\"] = \"advisory_only\""
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py",
    "line": 756,
    "text": "    authority_tier: Literal[\"advisory_only\"] = \"advisory_only\""
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py",
    "line": 876,
    "text": "                authority_tier=block.authority_tier,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py",
    "line": 1002,
    "text": "    authority_tier: Optional[str] = Field("
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py",
    "line": 1885,
    "text": "    grid_authority_tier: Optional[str] = Field("
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/economic_dispatch_loop.py",
    "line": 278,
    "text": "                    authority_tier=src.authority_tier,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/economic_dispatch_loop.py",
    "line": 291,
    "text": "            if rs.authority_tier == AuthorityTier.AUTONOMOUS"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py",
    "line": 1894,
    "text": "    # a serialised PMSLogEntry: {t_s, source_id, action, authority_tier, detail}."
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_source_priority.py",
    "line": 93,
    "text": "    authority_tier"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_source_priority.py",
    "line": 108,
    "text": "    authority_tier: AuthorityTier"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_source_priority.py",
    "line": 126,
    "text": "    authority_tier: AuthorityTier"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_source_priority.py",
    "line": 228,
    "text": "                        authority_tier=src.authority_tier,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_source_priority.py",
    "line": 244,
    "text": "                authority_tier=src.authority_tier,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py",
    "line": 799,
    "text": "            authority_tier=_AuthorityTier.AUTONOMOUS,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py",
    "line": 810,
    "text": "            authority_tier=_AuthorityTier.AUTONOMOUS,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py",
    "line": 821,
    "text": "            authority_tier=_AuthorityTier.AUTONOMOUS,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/pms_test_double.py",
    "line": 74,
    "text": "    authority_tier: str   # AuthorityTier.value"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/pms_test_double.py",
    "line": 134,
    "text": "                f\"Source rank={rank}, authority={ranked_src.authority_tier.value}.\""
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/pms_test_double.py",
    "line": 138,
    "text": "                t_s, action, ranked_src.source_id, ranked_src.authority_tier.value,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/pms_test_double.py",
    "line": 144,
    "text": "                authority_tier=ranked_src.authority_tier.value,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py",
    "line": 869,
    "text": "        # Each entry: {t_s, source_id, action, authority_tier, detail}."
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py",
    "line": 2827,
    "text": "                            if getattr(_src, \"authority_tier\", None) not in ("
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py",
    "line": 2845,
    "text": "                                    authority_tier=_src.authority_tier,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py",
    "line": 2886,
    "text": "                                        \"authority_tier\": _e.authority_tier,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py",
    "line": 348,
    "text": "            authority_tier=_AuthorityTier.AUTONOMOUS,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py",
    "line": 359,
    "text": "            authority_tier=_AuthorityTier.AUTONOMOUS,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py",
    "line": 511,
    "text": "            authority_tier=_AuthorityTier.AUTONOMOUS,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py",
    "line": 524,
    "text": "            authority_tier=_AuthorityTier.AUTONOMOUS,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py",
    "line": 1812,
    "text": "        _tier_raw = _b.get(\"authority_tier\", \"autonomous\")"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py",
    "line": 1824,
    "text": "            authority_tier=_bess_tier,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py",
    "line": 1846,
    "text": "                authority_tier=_AuthorityTier.AUTONOMOUS,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py",
    "line": 1859,
    "text": "            authority_tier=_AuthorityTier.AUTONOMOUS,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py",
    "line": 1868,
    "text": "    # shortfall events, enabling PMSTestDouble replay (grid_authority_tier field)."
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py",
    "line": 1870,
    "text": "    _grid_tier_raw = spec_data.get(\"grid_authority_tier\", \"autonomous\")"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py",
    "line": 1882,
    "text": "        authority_tier=_grid_tier,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_schema.py",
    "line": 87,
    "text": "    assert all(unit.authority_tier == \"advisory_only\" for unit in fleet)"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_economic_dispatch_loop.py",
    "line": 61,
    "text": "    authority_tier: AuthorityTier = AuthorityTier.AUTONOMOUS,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_economic_dispatch_loop.py",
    "line": 73,
    "text": "        authority_tier=authority_tier,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_economic_dispatch_loop.py",
    "line": 110,
    "text": "        confirm_grid = _src(\"grid-confirm\", authority_tier=AuthorityTier.CONFIRM,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_economic_dispatch_loop.py",
    "line": 125,
    "text": "        human_src = _src(\"emergency-gen\", authority_tier=AuthorityTier.HUMAN_ONLY,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_economic_dispatch_loop.py",
    "line": 136,
    "text": "                          authority_tier=AuthorityTier.AUTONOMOUS, available_mw=8.0)"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_economic_dispatch_loop.py",
    "line": 138,
    "text": "                       authority_tier=AuthorityTier.CONFIRM, available_mw=100.0)"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_economic_dispatch_loop.py",
    "line": 153,
    "text": "                       authority_tier=AuthorityTier.CONFIRM, available_mw=100.0)"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_economic_dispatch_loop.py",
    "line": 552,
    "text": "            authority_tier=AuthorityTier.AUTONOMOUS,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_economic_dispatch_loop.py",
    "line": 594,
    "text": "            authority_tier=AuthorityTier.AUTONOMOUS,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_power_source_priority.py",
    "line": 51,
    "text": "    authority_tier: AuthorityTier = AuthorityTier.AUTONOMOUS,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_power_source_priority.py",
    "line": 62,
    "text": "        authority_tier=authority_tier,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_power_source_priority.py",
    "line": 190,
    "text": "            authority_tier=AuthorityTier.CONFIRM,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_power_source_priority.py",
    "line": 195,
    "text": "        assert result.ranked_sources[0].authority_tier == AuthorityTier.CONFIRM"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_power_source_priority.py",
    "line": 201,
    "text": "            authority_tier=AuthorityTier.HUMAN_ONLY,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_power_source_priority.py",
    "line": 206,
    "text": "        assert result.ranked_sources[0].authority_tier == AuthorityTier.HUMAN_ONLY"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_power_source_priority.py",
    "line": 270,
    "text": "    def test_note_is_advisory_only_disclaimer(self) -> None:"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_power_source_priority.py",
    "line": 324,
    "text": "                  authority_tier: AuthorityTier = AuthorityTier.AUTONOMOUS) -> PowerSource:"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_power_source_priority.py",
    "line": 330,
    "text": "            authority_tier=authority_tier,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_power_source_priority.py",
    "line": 375,
    "text": "            authority_tier=AuthorityTier.CONFIRM,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase4.py",
    "line": 44,
    "text": "    authority_tier: AuthorityTier = AuthorityTier.AUTONOMOUS,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase4.py",
    "line": 55,
    "text": "        authority_tier=authority_tier,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase5.py",
    "line": 69,
    "text": "        authority_tier=AuthorityTier.AUTONOMOUS,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase5.py",
    "line": 83,
    "text": "        authority_tier=AuthorityTier.AUTONOMOUS,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase5.py",
    "line": 101,
    "text": "        authority_tier=AuthorityTier.CONFIRM,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase5.py",
    "line": 239,
    "text": "                         authority_tier=\"confirm\", detail=\"d1\")"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase5.py",
    "line": 241,
    "text": "                         authority_tier=\"confirm\", detail=\"d1\")"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase5.py",
    "line": 245,
    "text": "                         authority_tier=\"confirm\", detail=\"d1\")"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 6,
    "text": "  \"When a scenario has an operator_response_profile set and grid_authority_tier"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 28,
    "text": "A. Added grid_authority_tier field to ScenarioSpec (schemas.py) and to"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 34,
    "text": "B. Updated demo-pms-shortfall seeded scenario to set grid_authority_tier="
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 50,
    "text": "  C16-2  build_run_context_from_spec with grid_authority_tier=\"confirm\" \u2192"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 52,
    "text": "  C16-3  Default (no grid_authority_tier key) \u2192 grid-firm is AUTONOMOUS."
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 58,
    "text": "  C16-7  demo-pms-shortfall seeded scenario has grid_authority_tier=\"confirm\"."
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 103,
    "text": "    \"\"\"Same spec but with grid_authority_tier='confirm' so shortfall can fire.\"\"\""
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 105,
    "text": "    spec[\"grid_authority_tier\"] = \"confirm\""
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 137,
    "text": "            authority_tier=AuthorityTier.AUTONOMOUS,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 148,
    "text": "            authority_tier=AuthorityTier.AUTONOMOUS,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 159,
    "text": "            authority_tier=AuthorityTier.CONFIRM,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 199,
    "text": "    # \u2500\u2500 C16-2: grid_authority_tier=\"confirm\" respected by factory \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 202,
    "text": "        \"\"\"build_run_context_from_spec with grid_authority_tier='confirm' \u2192"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 214,
    "text": "        assert grid.authority_tier == AuthorityTier.CONFIRM, ("
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 215,
    "text": "            f\"grid-firm must be CONFIRM when spec sets grid_authority_tier='confirm'; \""
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 216,
    "text": "            f\"got {grid.authority_tier!r}\""
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 222,
    "text": "        \"\"\"Spec without grid_authority_tier \u2192 grid-firm remains AUTONOMOUS.\"\"\""
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 231,
    "text": "        assert grid.authority_tier == AuthorityTier.AUTONOMOUS, ("
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 232,
    "text": "            f\"grid-firm must default to AUTONOMOUS; got {grid.authority_tier!r}\""
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 262,
    "text": "            \"authority_tier\": \"confirm\","
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 276,
    "text": "        autonomous = [s for s in sources if s.authority_tier == AuthorityTier.AUTONOMOUS]"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 299,
    "text": "            if s.authority_tier in (AuthorityTier.CONFIRM, AuthorityTier.HUMAN_ONLY)"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 326,
    "text": "            if s.authority_tier in (AuthorityTier.CONFIRM, AuthorityTier.HUMAN_ONLY)"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 340,
    "text": "                    \"authority_tier\": e.authority_tier,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 375,
    "text": "    # \u2500\u2500 C16-7: seeded scenario has grid_authority_tier=\"confirm\" \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 377,
    "text": "    def test_demo_pms_shortfall_has_grid_authority_tier_confirm(self) -> None:"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 378,
    "text": "        \"\"\"demo-pms-shortfall seeded scenario must have grid_authority_tier='confirm'.\"\"\""
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 384,
    "text": "        tier = spec_data.get(\"grid_authority_tier\")"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 386,
    "text": "            f\"demo-pms-shortfall must have grid_authority_tier='confirm' \""
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 394,
    "text": "        _REQUIRED_KEYS = {\"t_s\", \"source_id\", \"action\", \"authority_tier\", \"detail\"}"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 399,
    "text": "            if s.authority_tier in (AuthorityTier.CONFIRM, AuthorityTier.HUMAN_ONLY)"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_psp002_phase7.py",
    "line": 409,
    "text": "                \"authority_tier\": e.authority_tier,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/components/ScenarioBuilder.tsx",
    "line": 256,
    "text": "    authority_tier: 'advisory_only',"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/components/ScenarioBuilder.tsx",
    "line": 852,
    "text": "                      authority_tier: 'advisory_only',"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/components/ScenarioBuilder.tsx",
    "line": 1126,
    "text": "                          const active = (b.authority_tier ?? 'autonomous') === tier"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/components/ScenarioBuilder.tsx",
    "line": 1130,
    "text": "                            <button key={tier} onClick={() => patchBess(i, { authority_tier: tier })}"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/components/ScenarioBuilder.tsx",
    "line": 1209,
    "text": "                          const active = (t.authority_tier ?? 'autonomous') === tier"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/components/ScenarioBuilder.tsx",
    "line": 1213,
    "text": "                            <button key={tier} onClick={() => patchTurbine(i, { authority_tier: tier })}"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/opening/PowerManagementModal.tsx",
    "line": 113,
    "text": "    tier: (b.authority_tier as AuthorityTier | undefined) ?? 'autonomous',"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/opening/PowerManagementModal.tsx",
    "line": 121,
    "text": "    tier: (t.authority_tier as AuthorityTier | undefined) ?? 'autonomous',"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/opening/PowerManagementModal.tsx",
    "line": 193,
    "text": "      map[`bess-${b.asset_id}`] = (b.authority_tier as AuthorityTier | undefined) ?? 'autonomous'"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/opening/PowerManagementModal.tsx",
    "line": 196,
    "text": "      map[`turb-${t.asset_id}`] = (t.authority_tier as AuthorityTier | undefined) ?? 'autonomous'"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/opening/PowerManagementModal.tsx",
    "line": 211,
    "text": "      map[`bess-${b.asset_id}`] = (b.authority_tier as AuthorityTier | undefined) ?? 'autonomous'"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/opening/PowerManagementModal.tsx",
    "line": 214,
    "text": "      map[`turb-${t.asset_id}`] = (t.authority_tier as AuthorityTier | undefined) ?? 'autonomous'"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/opening/PowerManagementModal.tsx",
    "line": 237,
    "text": "        authority_tier: sourceTiers[`bess-${b.asset_id}`] ?? b.authority_tier ?? 'autonomous',"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/opening/PowerManagementModal.tsx",
    "line": 241,
    "text": "        authority_tier: sourceTiers[`turb-${t.asset_id}`] ?? t.authority_tier ?? 'autonomous',"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/opening/PowerSupplySourcesModal.tsx",
    "line": 253,
    "text": "            authority_tier: 'advisory_only',"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/types.ts",
    "line": 185,
    "text": "    authority_tier: string"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/types.ts",
    "line": 815,
    "text": "  authority_tier?: AuthorityTier"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/types.ts",
    "line": 867,
    "text": "  authority_tier?: AuthorityTier"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/types.ts",
    "line": 979,
    "text": "  authority_tier: 'advisory_only'"
  }
]
```

## Appendix E — Every test timing occurrence and DieselConfig call

```json
[
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_addendum_i_phase1.py",
    "line": 122,
    "text": "    delta_t_start_s: float,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_addendum_i_phase1.py",
    "line": 123,
    "text": "    residual_ramp_s: float,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_addendum_i_phase1.py",
    "line": 131,
    "text": "            delta_t_start_s=delta_t_start_s,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_addendum_i_phase1.py",
    "line": 132,
    "text": "            residual_ramp_s=residual_ramp_s,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_addendum_i_phase1.py",
    "line": 126,
    "DieselConfig_call": "DieselConfig(\n            asset_id=asset_id,\n            rated_mw=5.0,\n            role=\"primary\",\n            start_offset_s=start_offset_s,\n            delta_t_start_s=delta_t_start_s,\n            residual_ramp_s=residual_ramp_s,\n        )"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase2.py",
    "line": 20,
    "text": "    delta_t_start_s: float = 1.0,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase2.py",
    "line": 22,
    "text": "    residual_ramp_s: float = 4.0,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase2.py",
    "line": 33,
    "text": "        delta_t_start_s=delta_t_start_s,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase2.py",
    "line": 35,
    "text": "        residual_ramp_s=residual_ramp_s,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase2.py",
    "line": 51,
    "text": "                delta_t_start_s=spec.delta_t_start_s,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase2.py",
    "line": 53,
    "text": "                residual_ramp_s=spec.residual_ramp_s,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase2.py",
    "line": 89,
    "text": "            delta_t_start_s=2.0,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase2.py",
    "line": 91,
    "text": "            residual_ramp_s=5.0,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase2.py",
    "line": 226,
    "text": "        delta_t_start_s=1.0,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase2.py",
    "line": 227,
    "text": "        residual_ramp_s=10.0,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase2.py",
    "line": 85,
    "DieselConfig_call": "DieselConfig(\n            asset_id=\"diesel-000\",\n            rated_mw=10.0,\n            role=\"primary\",\n            delta_t_start_s=2.0,\n            f_block=0.8,\n            residual_ramp_s=5.0,\n        )"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase2.py",
    "line": 45,
    "DieselConfig_call": "DieselConfig(\n                asset_id=spec.asset_id,\n                rated_mw=spec.rated_mw,\n                role=spec.role,\n                p_start=block.p_start,\n                start_offset_s=spec.start_offset_s,\n                delta_t_start_s=spec.delta_t_start_s,\n                f_block=spec.f_block,\n                residual_ramp_s=spec.residual_ramp_s,\n                min_stable_load_mw=spec.min_stable_load_mw,\n                min_run_s=spec.min_run_s,\n                min_down_s=spec.min_down_s,\n                cooldown_s=spec.cooldown_s,\n            )"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase3.py",
    "line": 20,
    "text": "    \"delta_t_start_s\": 1.0,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase3.py",
    "line": 22,
    "text": "    \"residual_ramp_s\": 1.0,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_isl_grid_forming_viability.py",
    "line": 43,
    "DieselConfig_call": "DieselConfig(\n            asset_id=\"diesel-former\", rated_mw=1.0, role=\"primary\",\n        )"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_reserve_reconciliation.py",
    "line": 40,
    "text": "    delta_t_start_s: float = 10.0,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_reserve_reconciliation.py",
    "line": 41,
    "text": "    residual_ramp_s: float = 8.0,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_reserve_reconciliation.py",
    "line": 48,
    "text": "            delta_t_start_s=delta_t_start_s,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_reserve_reconciliation.py",
    "line": 49,
    "text": "            residual_ramp_s=residual_ramp_s,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_reserve_reconciliation.py",
    "line": 75,
    "text": "            delta_t_start_s=20.0,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_reserve_reconciliation.py",
    "line": 76,
    "text": "            residual_ramp_s=8.0,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_reserve_reconciliation.py",
    "line": 88,
    "text": "            delta_t_start_s=10.0,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_reserve_reconciliation.py",
    "line": 89,
    "text": "            residual_ramp_s=8.0,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_reserve_reconciliation.py",
    "line": 104,
    "text": "            delta_t_start_s=2000.0,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_reserve_reconciliation.py",
    "line": 105,
    "text": "            residual_ramp_s=1600.0,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_reserve_reconciliation.py",
    "line": 129,
    "text": "            delta_t_start_s=1000.0,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_reserve_reconciliation.py",
    "line": 130,
    "text": "            residual_ramp_s=440.0,"
  },
  {
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_reserve_reconciliation.py",
    "line": 44,
    "DieselConfig_call": "DieselConfig(\n            asset_id=\"diesel-reserve\",\n            rated_mw=rated_mw,\n            role=\"primary\",\n            delta_t_start_s=delta_t_start_s,\n            residual_ramp_s=residual_ramp_s,\n        )"
  }
]
```

## Appendix F — Literal source excerpts with file:line

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py:702–756
```text
702: class DieselPowerBlockSpec(BaseModel):
703:     """Scenario-author-facing configuration for a diesel power block.
704: 
705:     The default values are intentionally marked PROPOSED_HERE.  They are
706:     placeholders from Addendum H and are not catalogue-backed validations.
707:     ``target_capacity_mw`` is the one required author input.
708:     """
709: 
710:     enabled: bool = False
711:     target_capacity_mw: float
712:     unit_rating_mw: float = 3.0
713:     p_start: float = 0.985
714:     target_reliability: float = 0.999
715:     f_block: float = 0.80
716:     delta_t_start_s: float = 10.0
717:     residual_ramp_s: float = 8.0
718:     start_stagger_interval_s: float = 2.0
719:     debounce_s: float = 1.0
720:     restore_hold_s: float = 300.0
721:     min_run_s: float = 900.0
722:     min_down_s: float = 300.0
723:     min_stable_load_mw_fraction: float = 0.30
724:     cooldown_s: float = 300.0
725:     fuel_burn_gal_per_hr_per_unit_at_full_load: float = 230.0
726:     fuel_type: Literal["diesel", "hvo"] = "diesel"
727:     min_fuel_runtime_hours: float = 48.0
728:     # Deliberately distinct from core.power_source_priority.AuthorityTier
729:     # (autonomous/confirm/human_only), which gates real EDL allocation
730:     # eligibility. Diesel has no GridSignal execution path by construction
731:     # (TC-68); this is advisory metadata only.
732:     authority_tier: Literal["advisory_only"] = "advisory_only"
733: 
734: 
735: class DieselUnitSpec(BaseModel):
736:     """Materialized per-unit diesel fleet shape.
737: 
738:     This is deliberately a schema-only representation in this phase.  It is
739:     not a runtime asset configuration and is not consumed by dispatch.
740:     """
741: 
742:     asset_id: str
743:     rated_mw: float
744:     role: Literal["primary", "standby"]
745:     start_offset_s: Optional[float]
746:     delta_t_start_s: float
747:     f_block: float
748:     residual_ramp_s: float
749:     min_stable_load_mw: float
750:     min_run_s: float
751:     min_down_s: float
752:     cooldown_s: float
753:     # Deliberately distinct from core.power_source_priority.AuthorityTier:
754:     # this is advisory metadata only because diesel has no GridSignal
755:     # execution path by construction (TC-68).
756:     authority_tier: Literal["advisory_only"] = "advisory_only"
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py:824–879
```text
824: def generate_diesel_fleet(
825:     block: DieselPowerBlockSpec,
826: ) -> list[DieselUnitSpec]:
827:     """Materialize the block-level diesel configuration into per-unit specs.
828: 
829:     Primary units receive staggered trigger offsets.  Reliability reserve
830:     units are cold standby: their offset remains ``None`` until a later phase
831:     activates a specific 1:1 replacement.
832:     """
833:     if not block.enabled:
834:         return []
835:     if block.target_capacity_mw <= 0.0:
836:         raise ValueError(
837:             "diesel_power_block.target_capacity_mw must be greater than 0 "
838:             f"when enabled (got {block.target_capacity_mw})"
839:         )
840:     if block.unit_rating_mw <= 0.0:
841:         raise ValueError(
842:             "diesel_power_block.unit_rating_mw must be greater than 0 "
843:             f"(got {block.unit_rating_mw})"
844:         )
845: 
846:     n_active = _math.ceil(block.target_capacity_mw / block.unit_rating_mw)
847:     n_total = solve_min_fleet_size(
848:         n_active=n_active,
849:         p_start=block.p_start,
850:         target_reliability=block.target_reliability,
851:     )
852:     min_stable_load_mw = (
853:         block.unit_rating_mw * block.min_stable_load_mw_fraction
854:     )
855: 
856:     fleet: list[DieselUnitSpec] = []
857:     for index in range(n_total):
858:         is_primary = index < n_active
859:         fleet.append(
860:             DieselUnitSpec(
861:                 asset_id=f"diesel-{index:03d}",
862:                 rated_mw=block.unit_rating_mw,
863:                 role="primary" if is_primary else "standby",
864:                 start_offset_s=(
865:                     index * block.start_stagger_interval_s
866:                     if is_primary
867:                     else None
868:                 ),
869:                 delta_t_start_s=block.delta_t_start_s,
870:                 f_block=block.f_block,
871:                 residual_ramp_s=block.residual_ramp_s,
872:                 min_stable_load_mw=min_stable_load_mw,
873:                 min_run_s=block.min_run_s,
874:                 min_down_s=block.min_down_s,
875:                 cooldown_s=block.cooldown_s,
876:                 authority_tier=block.authority_tier,
877:             )
878:         )
879:     return fleet
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py:1690–1697
```text
1690:         default="disabled",
1691:         description=(
1692:             "Forecast-driven turbine commitment mode. baseline keeps at least "
1693:             "three synchronized units without using forecast; informed uses "
1694:             "announced workload forecast. disabled preserves legacy behavior."
1695:         ),
1696:     )
1697:     turbine_forecast_lead_seconds: float = Field(
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py:2070–2076
```text
2070:             "Raising pf toward 1.0 lowers S_base and increases df/dt; lowering it slows frequency response."
2071:         ),
2072:     )
2073:     pue_base: float = Field(default=1.03, ge=1.0, le=2.0)
2074:     end_sim_time: float = Field(default=300.0, ge=60.0, le=86400.0)
2075:     # Operator-facing "What this demonstrates" copy shown in the DemoBar.
2076:     # Plain prose, 1-3 sentences.  Empty string = fall back to the hardcoded default.
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py:2432–2449
```text
2432:             )
2433:         if not self.kube_clusters:
2434:             return self
2435: 
2436:         cluster_ids = [cluster.cluster_id for cluster in self.kube_clusters]
2437:         if len(cluster_ids) != len(set(cluster_ids)):
2438:             raise ValueError("kube_clusters cluster_id values must be unique")
2439: 
2440:         workload_share = sum(
2441:             cluster.workload_share for cluster in self.kube_clusters
2442:         )
2443:         if abs(workload_share - 1.0) > 1e-6:
2444:             raise ValueError(
2445:                 "kube_clusters workload_share values must sum to 1.0 "
2446:                 f"(got {workload_share:.6f})"
2447:             )
2448:         return self
2449: 
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py:2484–2492
```text
2484:     @model_validator(mode="after")
2485:     def _materialize_diesel_fleet(self) -> "ScenarioSpec":
2486:         """Expand an enabled diesel block into its deterministic unit list."""
2487:         self.diesel_units = (
2488:             generate_diesel_fleet(self.diesel_power_block)
2489:             if self.diesel_power_block is not None
2490:             else []
2491:         )
2492:         return self
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py:973–991
```text
973: @dataclass
974: class DieselConfig:
975:     """Runtime configuration for one materialized diesel unit."""
976: 
977:     asset_id: str
978:     rated_mw: float
979:     role: str
980:     p_start: float = 0.985
981:     start_offset_s: Optional[float] = None
982:     delta_t_start_s: float = 10.0
983:     f_block: float = 0.80
984:     residual_ramp_s: float = 8.0
985:     min_stable_load_mw: float = 0.0
986:     min_run_s: float = 900.0
987:     min_down_s: float = 300.0
988:     cooldown_s: float = 300.0
989: 
990: 
991: @dataclass
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py:27–40
```text
27: from .fuel_cell_module import FuelCellModule, FuelCellState
28: from .models import (
29:     ConfidenceBand, DataQualityTag, IslandMode, OperatingTier,
30:     PreStagingConfig, SiteConfig, UnitAvailability,
31: )
32: 
33: _log = logging.getLogger(__name__)
34: 
35: # Addendum I §I.4 / I.9: PROPOSED_HERE, unvalidated default pending
36: # commissioning evidence.
37: MARGIN_MULTIPLIER = 2.5
38: 
39: 
40: # ---------------------------------------------------------------------------
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py:479–528
```text
479:     def diesel_worst_case_sync_s(self) -> float:
480:         """Return the configured fleet's worst-case synchronization duration.
481: 
482:         The full fleet is used for the Phase I floor.  The unit with the
483:         greatest start offset supplies the per-unit startup and residual-ramp
484:         values, because it is the last unit in the configured stagger sequence.
485:         """
486:         if not self.diesel_units:
487:             return 0.0
488: 
489:         driver = max(
490:             self.diesel_units,
491:             key=lambda unit: (
492:                 unit.config.start_offset_s or 0.0,
493:                 unit.config.asset_id,
494:             ),
495:         )
496:         return (
497:             max(
498:                 (unit.config.start_offset_s or 0.0 for unit in self.diesel_units),
499:                 default=0.0,
500:             )
501:             + driver.config.delta_t_start_s
502:             + driver.config.residual_ramp_s
503:         )
504: 
505:     def soc_floor_mwh(self, bess: BessModule) -> float:
506:         """Return the reconciled reserve threshold for this BESS unit.
507: 
508:         The configured normal-dispatch reserve and the diesel-derived Addendum I
509:         floor are two views of the same retained energy.  Keep their final
510:         reconciliation here so live callers and direct arbitrator callers use
511:         one formula.
512:         """
513:         diesel_floor_mwh = (
514:             MARGIN_MULTIPLIER
515:             * bess.config.rated_mw
516:             * (self.diesel_worst_case_sync_s() / 3600.0)
517:         )
518:         normal_depth_fraction = self.site.bess_normal_dispatch_depth_fraction
519:         depth_reserve_mwh = (
520:             bess.config.usable_mwh
521:             * max(
522:                 0.0,
523:                 bess.config.initial_soc_fraction - normal_depth_fraction,
524:             )
525:             if normal_depth_fraction > 0.0
526:             else 0.0
527:         )
528:         return max(depth_reserve_mwh, diesel_floor_mwh)
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py:1330–1376
```text
1330: @dataclass
1331: class DieselModule(AssetModule):
1332:     """One diesel unit with an explicit start outcome and local output curve.
1333: 
1334:     Fleet policy intentionally does not live here.  The module owns only its
1335:     own start, synchronization, unloading, and restart-lockout state;
1336:     DieselFleetCoordinator owns cross-unit activation and failover.
1337:     """
1338: 
1339:     config: DieselConfig
1340:     state: DieselState = DieselState.OFFLINE
1341:     _current_output_mw: float = 0.0
1342:     _time_to_online_s: float = 0.0
1343:     _start_success: Optional[bool] = None
1344:     _start_attempted: bool = False
1345:     _run_start_s: float = math.nan
1346:     _last_stop_s: float = math.nan
1347:     _time_since_sync_s: float = 0.0
1348:     _unload_elapsed_s: float = 0.0
1349:     _unload_start_output_mw: float = 0.0
1350:     _cooldown_until_s: float = math.nan
1351:     _last_known_sim_time: float = 0.0
1352:     _rng: random.Random = field(
1353:         default_factory=random.Random,
1354:         repr=False,
1355:         compare=False,
1356:     )
1357:     _resuming_from_unloading: bool = False
1358:     _resume_start_output_mw: float = 0.0
1359:     _resume_elapsed_s: float = 0.0
1360: 
1361:     def __post_init__(self) -> None:
1362:         if self.config.rated_mw <= 0.0:
1363:             raise ValueError("diesel rated_mw must be greater than zero")
1364:         if not 0.0 <= self.config.p_start <= 1.0:
1365:             raise ValueError("diesel p_start must be between zero and one")
1366:         for name in (
1367:             "delta_t_start_s",
1368:             "residual_ramp_s",
1369:             "min_run_s",
1370:             "min_down_s",
1371:             "cooldown_s",
1372:         ):
1373:             if getattr(self.config, name) < 0.0:
1374:                 raise ValueError(f"diesel {name} must not be negative")
1375:         if not 0.0 <= self.config.f_block <= 1.0:
1376:             raise ValueError("diesel f_block must be between zero and one")
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py:1404–1499
```text
1404:     @property
1405:     def is_on_bus(self) -> bool:
1406:         return self.state in (DieselState.SYNCHRONISED, DieselState.UNLOADING)
1407: 
1408:     def can_start(self, sim_time: float) -> bool:
1409:         """Return whether this unit can accept a new start command."""
1410:         if self.state != DieselState.OFFLINE or self._start_attempted:
1411:             return False
1412:         if not math.isnan(self._cooldown_until_s) and sim_time < self._cooldown_until_s:
1413:             return False
1414:         if (
1415:             not math.isnan(self._last_stop_s)
1416:             and sim_time - self._last_stop_s < self.config.min_down_s
1417:         ):
1418:             return False
1419:         return True
1420: 
1421:     def command_start(
1422:         self,
1423:         sim_time: float,
1424:         *,
1425:         success_override: Optional[bool] = None,
1426:     ) -> None:
1427:         """Accept an OFFLINE start and immediately store its success outcome.
1428: 
1429:         ``success_override`` is an explicit deterministic test seam.  When it
1430:         is absent, the unit draws once from its configured ``p_start``.
1431:         """
1432:         self._last_known_sim_time = sim_time
1433:         if not self.can_start(sim_time):
1434:             return
1435: 
1436:         self._start_success = (
1437:             bool(success_override)
1438:             if success_override is not None
1439:             else self._rng.random() < self.config.p_start
1440:         )
1441:         self._start_attempted = True
1442:         self.state = DieselState.STARTING
1443:         self._time_to_online_s = self.config.delta_t_start_s
1444:         self._current_output_mw = 0.0
1445:         self._resuming_from_unloading = False
1446: 
1447:     def advance(self, sim_time: float, dt_seconds: float) -> None:
1448:         """Advance startup, synchronization output, or controlled unloading."""
1449:         if dt_seconds < 0.0:
1450:             raise ValueError("diesel dt_seconds must not be negative")
1451:         self._last_known_sim_time = sim_time
1452: 
1453:         if self.state == DieselState.STARTING:
1454:             self._time_to_online_s = max(
1455:                 0.0,
1456:                 self._time_to_online_s - dt_seconds,
1457:             )
1458:             if self._time_to_online_s <= 0.0:
1459:                 self._time_to_online_s = 0.0
1460:                 if self._start_success:
1461:                     self.state = DieselState.SYNCHRONISED
1462:                     self._run_start_s = sim_time
1463:                     self._time_since_sync_s = 0.0
1464:                     self._current_output_mw = (
1465:                         self.config.rated_mw * self.config.f_block
1466:                     )
1467:                 else:
1468:                     self.state = DieselState.FAILED_START
1469:                     self._current_output_mw = 0.0
1470:             return
1471: 
1472:         if self.state == DieselState.SYNCHRONISED:
1473:             if self._resuming_from_unloading:
1474:                 self._resume_elapsed_s += dt_seconds
1475:                 duration = self.config.residual_ramp_s
1476:                 fraction = (
1477:                     1.0
1478:                     if duration <= 0.0
1479:                     else min(1.0, self._resume_elapsed_s / duration)
1480:                 )
1481:                 self._current_output_mw = (
1482:                     self._resume_start_output_mw
1483:                     + (self.config.rated_mw - self._resume_start_output_mw)
1484:                     * fraction
1485:                 )
1486:             else:
1487:                 self._time_since_sync_s += dt_seconds
1488:                 base_mw = self.config.rated_mw * self.config.f_block
1489:                 duration = self.config.residual_ramp_s
1490:                 fraction = (
1491:                     1.0
1492:                     if duration <= 0.0
1493:                     else min(1.0, self._time_since_sync_s / duration)
1494:                 )
1495:                 self._current_output_mw = (
1496:                     base_mw
1497:                     + (self.config.rated_mw - base_mw) * fraction
1498:                 )
1499:             return
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/diesel_fleet.py:185–222
```text
185:         *,
186:         success_overrides: Optional[Mapping[str, bool]] = None,
187:     ) -> DieselFleetSnapshot:
188:         """Advance units and coordinate one synthetic-gap fleet tick.
189: 
190:         ``gap_mw`` is intentionally caller-supplied.  The live simulation
191:         provides the pre-diesel remaining gap without making this coordinator
192:         read dispatch arithmetic.
193:         """
194:         if dt_seconds < 0.0:
195:             raise ValueError("diesel fleet dt_seconds must not be negative")
196:         self._last_sim_time = sim_time
197: 
198:         for unit in self.diesel_units:
199:             unit.advance(sim_time, dt_seconds)
200:         self._consume_fuel(dt_seconds)
201:         self._complete_cooldown_if_ready(sim_time)
202: 
203:         if gap_mw > 0.0:
204:             self._positive_gap_s += dt_seconds
205:         else:
206:             self._positive_gap_s = 0.0
207: 
208:         if self.episode_id is None:
209:             if (
210:                 gap_mw > 0.0
211:                 and self._positive_gap_s >= self.debounce_s
212:                 and math.isnan(self._cooldown_until_s)
213:             ):
214:                 self._begin_episode(sim_time)
215:             else:
216:                 self._update_rollup()
217:                 return self.snapshot()
218: 
219:         if gap_mw > 0.0:
220:             self._restore_elapsed_s = 0.0
221:             if any(unit.state == DieselState.UNLOADING for unit in self.diesel_units):
222:                 for unit in self.diesel_units:
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/diesel_fleet.py:254–312
```text
254:         self.insufficient_start_alerts.clear()
255:         self.fleet_state = "starting"
256:         self._state_since_sim_time = sim_time
257: 
258:     def _start_due_primary_units(
259:         self,
260:         sim_time: float,
261:         success_overrides: Mapping[str, bool],
262:     ) -> None:
263:         for unit in self.diesel_units:
264:             if unit.role != "primary" or unit.start_attempted:
265:                 continue
266:             offset = max(0.0, unit.start_offset_s or 0.0)
267:             if sim_time - self._activation_sim_time < offset:
268:                 continue
269:             unit.command_start(
270:                 sim_time,
271:                 success_override=success_overrides.get(unit.asset_id),
272:             )
273: 
274:     def _handle_failed_starts(
275:         self,
276:         sim_time: float,
277:         success_overrides: Mapping[str, bool],
278:     ) -> None:
279:         for failed in self.diesel_units:
280:             if (
281:                 failed.state != DieselState.FAILED_START
282:                 or failed.asset_id in self._handled_failed_starts
283:             ):
284:                 continue
285:             self._handled_failed_starts.add(failed.asset_id)
286: 
287:             if self.synchronised_count >= (self.n_active or 0):
288:                 continue
289: 
290:             replacement = next(
291:                 (
292:                     unit
293:                     for unit in self.diesel_units
294:                     if unit.role == "standby"
295:                     and unit.can_start(sim_time)
296:                 ),
297:                 None,
298:             )
299:             if replacement is not None:
300:                 replacement.command_start(
301:                     sim_time,
302:                     success_override=success_overrides.get(replacement.asset_id),
303:                 )
304: 
305:     def _update_insufficient_start(self, sim_time: float) -> None:
306:         if self.episode_id is None or self.synchronised_count >= (self.n_active or 0):
307:             return
308:         if any(unit.state == DieselState.UNLOADING for unit in self.diesel_units):
309:             return
310:         if any(unit.state == DieselState.STARTING for unit in self.diesel_units):
311:             return
312:         standby_available = any(
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py:607–638
```text
607: def build_run_context_from_spec(
608:     run_id: str,
609:     spec_data: dict,
610:     playback_speed: float = 0.0,
611: ) -> RunContext:
612:     """Build a RunContext from a scenario spec dictionary (JSON-round-trip safe).
613: 
614:     ``spec_data`` is the plain-Python form of a serialised ScenarioSpec —
615:     i.e. ``json.loads(record.spec_json)`` or ``spec.model_dump()``.
616:     All dicts, lists, and scalars; no Pydantic models.
617: 
618:     Design constraints:
619:     - This function must NOT import from api/ (runtime/ → api/ is forbidden
620:       by §21.1 plane-separation).  The caller (api/routes/runs.py) is
621:       responsible for validating the spec via Pydantic and serialising it;
622:       this function only reads a plain dict.
623:     - WorkloadClass is read from each scripted event, defaulting to TRAINING
624:       for backward compatibility with existing scenario specs.
625:     - An empty workload_events list is valid (idle run or TC-33 compute
626:       where the job starts at t>0).
627:     - SOLAR_STEP events are forwarded with event_type=WorkloadEventType.SOLAR_STEP;
628:       SimulationState.apply_workload_signal's early-return handles them.
629: 
630:     Step 9 will swap ScenarioRecord.spec_json reads from in-memory to
631:     SQLAlchemy while calling this function identically.
632:     """
633:     spec_data = expand_phase2b_reference_spec(spec_data)
634:     validate_fuel_cell_source_consistency(spec_data)
635: 
636:     # ── Site configuration ────────────────────────────────────────────────
637:     island = (
638:         IslandMode.ISLANDED
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py:1018–1045
```text
1018: 
1019:     # ── Diesel runtime modules ───────────────────────────────────────────
1020:     # The modules are coordinated by SimulationState's fleet coordinator;
1021:     # dispatch arbitration remains responsible for turbines and BESS.
1022:     _diesel_block = spec_data.get("diesel_power_block") or {}
1023:     diesel_units = [
1024:         DieselModule(
1025:             DieselConfig(
1026:                 asset_id=d.get("asset_id") or f"diesel-{i:03d}",
1027:                 rated_mw=float(d.get("rated_mw", _diesel_block.get("unit_rating_mw", 3.0))),
1028:                 role=str(d.get("role", "primary")),
1029:                 p_start=float(_diesel_block.get("p_start", 0.985)),
1030:                 start_offset_s=(
1031:                     None
1032:                     if d.get("start_offset_s") is None
1033:                     else float(d["start_offset_s"])
1034:                 ),
1035:                 delta_t_start_s=float(d.get("delta_t_start_s", _diesel_block.get("delta_t_start_s", 10.0))),
1036:                 f_block=float(d.get("f_block", _diesel_block.get("f_block", 0.80))),
1037:                 residual_ramp_s=float(d.get("residual_ramp_s", _diesel_block.get("residual_ramp_s", 8.0))),
1038:                 min_stable_load_mw=float(d.get("min_stable_load_mw", 0.0)),
1039:                 min_run_s=float(d.get("min_run_s", _diesel_block.get("min_run_s", 900.0))),
1040:                 min_down_s=float(d.get("min_down_s", _diesel_block.get("min_down_s", 300.0))),
1041:                 cooldown_s=float(d.get("cooldown_s", _diesel_block.get("cooldown_s", 300.0))),
1042:             )
1043:         )
1044:         for i, d in enumerate(spec_data.get("diesel_units", []))
1045:     ]
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py:1800–1865
```text
1800:     # economic dispatch.
1801:     #
1802:     # Authority tier: honour per-unit spec field written by the Scenario
1803:     # Builder UI (autonomous / confirm / human_only).  Defaults to AUTONOMOUS
1804:     # so the EDL can dispatch without operator confirmation in headless runs.
1805:     #
1806:     # Grid source: uncapped (available_mw=999.0 — no hard physics limit).
1807:     # EDL.step() reprices grid sources per TOU each tick, so the initial
1808:     # marginal_cost_mwh here is a catalogue-read placeholder only.
1809:     _edl_sources: list[_PowerSource] = []
1810: 
1811:     for _i, _b in enumerate(spec_data.get("bess_units", [])):
1812:         _tier_raw = _b.get("authority_tier", "autonomous")
1813:         try:
1814:             _bess_tier = _AuthorityTier(_tier_raw)
1815:         except ValueError:
1816:             _bess_tier = _AuthorityTier.AUTONOMOUS
1817:         _edl_sources.append(_PowerSource(
1818:             source_id=_b.get("asset_id") or f"bess-{_i}",
1819:             source_type=_PowerSourceType.BESS,
1820:             dispatchable=True,
1821:             counts_toward_reserve=True,
1822:             marginal_cost_mwh=float(_sp.value("bess_marginal_cost_mwh")),
1823:             response_latency_class=_ResponseLatencyClass.INSTANT,
1824:             authority_tier=_bess_tier,
1825:             available_mw=float(_b.get("rated_mw", 5.0)),
1826:             cost_basis_note="cycle amortisation (PSP-6)",
1827:         ))
1828: 
1829:     # Turbine fleet: add to EDL for merit-order advisory and cost accounting.
1830:     # available_mw is initialised to the rated fleet total here; run_manager._drive()
1831:     # updates it each tick to tick_result.turbine_output_mw so cost attribution
1832:     # reflects actual physics dispatch rather than nameplate capacity.
1833:     _spec_turbine_units = spec_data.get("turbine_units", [])
1834:     if _spec_turbine_units:
1835:         _turbine_fleet_rated_mw = sum(
1836:             float(t.get("rated_mw", 10.0)) for t in _spec_turbine_units
1837:         )
1838:         if _turbine_fleet_rated_mw > 0.0:
1839:             _edl_sources.append(_PowerSource(
1840:                 source_id="turbine-fleet",
1841:                 source_type=_PowerSourceType.TURBINE,
1842:                 dispatchable=True,
1843:                 counts_toward_reserve=True,
1844:                 marginal_cost_mwh=float(_sp.value("turbine_variable_per_mwh")),
1845:                 response_latency_class=_ResponseLatencyClass.THERMAL_LAG,
1846:                 authority_tier=_AuthorityTier.AUTONOMOUS,
1847:                 available_mw=_turbine_fleet_rated_mw,
1848:                 cost_basis_note="fuel + variable O&M (turbine_variable_per_mwh catalogue)",
1849:             ))
1850: 
1851:     if spec_data.get("fuel_cell_enabled", False):
1852:         _edl_sources.append(_PowerSource(
1853:             source_id="fuel-cell-0",
1854:             source_type=_PowerSourceType.FUEL_CELL,
1855:             dispatchable=True,
1856:             counts_toward_reserve=False,
1857:             marginal_cost_mwh=float(_sp.value("fuel_cell_ppa_rate_mwh")),
1858:             response_latency_class=_ResponseLatencyClass.RAMP_LIMITED,
1859:             authority_tier=_AuthorityTier.AUTONOMOUS,
1860:             # fleet-total MW: per-stack rated_mw × stack_count (same as sim_state)
1861:             available_mw=_fc_rated_mw_fleet,
1862:             cost_basis_note="fuel cell PPA rate (PSP-002 §7)",
1863:         ))
1864: 
1865:     # Grid is always present as the last-resort source.
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/phase2b_reference.py:87–120
```text
87: def expand_phase2b_reference_spec(spec_data: dict[str, Any]) -> dict[str, Any]:
88:     """Expand a compact H-1/H-2 catalogue entry into a normal run spec."""
89:     family = spec_data.get("phase2b_reference_family")
90:     if family is None:
91:         return spec_data
92:     if family not in {"h1", "h2"}:
93:         raise ValueError(f"unsupported Phase 2b reference family: {family!r}")
94: 
95:     base_name = str(
96:         spec_data.get("phase2b_reference_base_scenario", _DEFAULT_BASE)
97:     )
98:     base_path = _SCENARIO_DIR / base_name
99:     if not base_path.is_file():
100:         raise FileNotFoundError(f"Phase 2b base scenario not found: {base_path}")
101:     base = json.loads(base_path.read_text())
102:     days = int(spec_data.get("phase2b_reference_days", 1))
103:     if days not in {1, 7}:
104:         raise ValueError("Phase 2b reference horizon must be 1 or 7 days")
105: 
106:     expanded = copy.deepcopy(base)
107:     # These records are intentionally metadata-only.  Do not overlay the
108:     # Pydantic model's defaulted empty arrays or policy defaults when callers
109:     # pass model_dump() rather than the original compact JSON.
110:     expanded["name"] = str(spec_data.get("name", expanded["name"]))
111:     # Keep this override in the expansion layer so the unchanged Phase 2a base
112:     # scenario remains unchanged on disk.
113:     expanded["turbine_units"] = apply_study_fuel_model(
114:         base.get("turbine_units", [])
115:     )
116: 
117:     expanded["end_sim_time"] = days * _DAY_SECONDS
118:     expanded["description"] = (
119:         f"Addendum H {family.upper()} reference scenario with "
120:         f"scheduler-shaped GPU workload demand over {days} day(s), "
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/phase2b_reference.py:133–164
```text
133:             event,
134:             family=family,
135:             cluster_number=cluster_number,
136:             offset_s=offset_s,
137:         )
138:         for cluster_number, offset_s in offsets
139:         for event in base.get("workload_events", [])
140:         if str(event.get("scheduler_type", "")).upper() in allowed_scheduler
141:     ]
142: 
143:     if family == "h1":
144:         expanded.pop("slurm_config", None)
145:     else:
146:         slurm = copy.deepcopy(base.get("slurm_config"))
147:         if slurm is None:
148:             raise ValueError("H-2 reference requires the base slurm_config")
149:         slurm["jobs"] = [
150:             _copy_slurm_job(
151:                 job,
152:                 family=family,
153:                 cluster_number=cluster_number,
154:                 offset_s=offset_s,
155:             )
156:             for cluster_number, offset_s in offsets
157:             for job in base.get("slurm_config", {}).get("jobs", [])
158:         ]
159:         expanded["slurm_config"] = slurm
160: 
161:     expanded.pop("phase2b_reference_base_scenario", None)
162:     expanded.pop("phase2b_reference_family", None)
163:     expanded.pop("phase2b_reference_days", None)
164:     return expanded
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/routes/scenarios.py:1139–1185
```text
1139:             "fuel_cell_stack_count": 1,
1140:             "fuel_cell_load_following": True,
1141:             "fuel_cell_min_stable_fraction": 0.5,
1142:             "island_mode": True,
1143:             "pue_base": 1.0,
1144:             "power_factor": 0.85,
1145:             "alpha_max": 0.2,
1146:             "bess_normal_dispatch_depth_fraction": 1.0,
1147:             "bess_bridging_floor_fraction": 0.15,
1148:             "bess_material_discharge_fraction": 0.05,
1149:             "end_sim_time": 5400.0,
1150:             "diesel_power_block": {
1151:                 "enabled": True,
1152:                 "target_capacity_mw": 20.0,
1153:                 "unit_rating_mw": 20.0,
1154:                 "p_start": 1.0,
1155:                 "target_reliability": 1.0,
1156:                 "f_block": 1.0,
1157:                 "delta_t_start_s": 3600.0,
1158:                 "residual_ramp_s": 60.0,
1159:                 "start_stagger_interval_s": 1.0,
1160:                 "debounce_s": 1.0,
1161:                 "restore_hold_s": 300.0,
1162:                 "min_run_s": 900.0,
1163:                 "min_down_s": 300.0,
1164:                 "min_stable_load_mw_fraction": 0.3,
1165:                 "cooldown_s": 300.0,
1166:                 "fuel_burn_gal_per_hr_per_unit_at_full_load": 230.0,
1167:                 "fuel_type": "diesel",
1168:                 "min_fuel_runtime_hours": 48.0,
1169:                 "authority_tier": "advisory_only",
1170:             },
1171:             "diesel_units": [
1172:                 {
1173:                     "asset_id": "diesel-000",
1174:                     "rated_mw": 20.0,
1175:                     "role": "primary",
1176:                     "start_offset_s": 0.0,
1177:                     "delta_t_start_s": 3600.0,
1178:                     "f_block": 1.0,
1179:                     "residual_ramp_s": 60.0,
1180:                     "min_stable_load_mw": 6.0,
1181:                     "min_run_s": 900.0,
1182:                     "min_down_s": 300.0,
1183:                     "cooldown_s": 300.0,
1184:                     "authority_tier": "advisory_only",
1185:                 }
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/routes/scenarios.py:1351–1369
```text
1351: def _seed_json_scenarios(store: ScenarioStore) -> None:
1352:     """Seed scenarios stored as full ScenarioSpec JSON files in config/scenarios/.
1353: 
1354:     Each entry maps a stable store key to a filename under config/scenarios/.
1355:     The JSON must be a valid ScenarioSpec (model_dump_json output).
1356:     """
1357:     import base64 as _base64
1358:     import gzip as _gzip
1359:     import json as _json
1360:     from pathlib import Path as _Path
1361: 
1362:     _JSON_ENTRIES: list[tuple[str, str]] = [
1363:         # (store_id, filename)
1364:         ("demo-islanded-ramp",  "demo-islanded-ramp.json"),
1365:         ("demo-operator-trip",  "demo-operator-trip.json"),
1366:         ("islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs",
1367:          "islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs.json"),
1368:         # 10-tenant stochastic GPU load — 3-hour simulation across A–J tenants
1369:         ("demo-10-tenant-random-gpu", "demo-10-tenant-random-gpu.json"),
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/routes/scenarios.py:1441–1487
```text
1441:         "scenario-turbine-01": "26 Customer Scenario - scenario-turbine-01",
1442:     }
1443: 
1444:     _cfg_dir = _Path(__file__).resolve().parents[2] / "config" / "scenarios"
1445:     for store_id, filename in _JSON_ENTRIES:
1446:         _jpath = _cfg_dir / filename
1447:         try:
1448:             if filename.endswith(".json.gz.b64"):
1449:                 _raw = _gzip.decompress(
1450:                     _base64.b64decode(_jpath.read_text())
1451:                 ).decode("utf-8")
1452:             else:
1453:                 _raw = _jpath.read_text()
1454:             _spec = ScenarioSpec.model_validate_json(_raw)
1455:             if display_name := _DISPLAY_NAME_OVERRIDES.get(store_id):
1456:                 _spec = _spec.model_copy(update={"name": display_name})
1457:             _warnings = _spec.collect_initial_spinning_warnings()
1458:             if _warnings:
1459:                 import logging as _logging
1460:                 for _warning in _warnings:
1461:                     _logging.getLogger(__name__).warning(
1462:                         "Scenario %s turbine starting-count violation: %s",
1463:                         store_id,
1464:                         _warning,
1465:                     )
1466:             store._seed(store_id, _spec)
1467:         except Exception as exc:
1468:             import logging as _logging
1469:             _logging.getLogger(__name__).warning(
1470:                 "Failed to seed %s from %s: %s", store_id, filename, exc
1471:             )
1472: 
1473: 
1474: def build_seeded_store() -> ScenarioStore:
1475:     """Return a ScenarioStore pre-loaded with all built-in demo scenarios."""
1476:     store = ScenarioStore()
1477:     for sid, spec in _SEEDED:
1478:         store._seed(sid, spec)
1479:     _seed_fabric_scenarios(store)
1480:     _seed_json_scenarios(store)
1481:     store._seed(
1482:         "islanded-fc-bess-diesel-slurm-gpu-peaks",
1483:         _build_persistent_slurm_gpu_peak_scenario(),
1484:     )
1485:     return store
1486: 
1487: 
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/executor.py:249–279
```text
249:     def _expanded_spec(
250:         self,
251:         scenario_id: str,
252:         parameter_overrides: Mapping[str, Any] | None,
253:         duration_seconds: float | None,
254:     ) -> dict[str, Any]:
255:         study_class = self._study_class_for_scenario(scenario_id)
256:         if study_class == STUDY_CLASS_ADDENDUM_H:
257:             # Keep the existing compact H catalogue loading and expansion path.
258:             spec = expand_phase2b_reference_spec(
259:                 _load_compact_spec(scenario_id)
260:             )
261:         else:
262:             base_path = (
263:                 Path(__file__).resolve().parents[1]
264:                 / "config"
265:                 / "scenarios"
266:                 / f"{BASE_DEMO_SCENARIO_ID}.json"
267:             )
268:             on_disk_spec = json.loads(base_path.read_text())
269:             spec = copy.deepcopy(on_disk_spec)
270:             spec["turbine_units"] = apply_study_fuel_model(
271:                 spec.get("turbine_units", [])
272:             )
273:         if duration_seconds is not None:
274:             spec["end_sim_time"] = float(duration_seconds)
275:         if parameter_overrides:
276:             _deep_merge(spec, parameter_overrides)
277:         return spec
278: 
279:     def _probe(
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/executor.py:281–306
```text
281:         spec: dict[str, Any],
282:         *,
283:         run_id: str,
284:     ) -> tuple[list[dict[str, Any]], list[tuple[float, float]]]:
285:         probe_spec = copy.deepcopy(spec)
286:         probe_spec["turbine_commitment_mode"] = "baseline"
287:         ctx = build_run_context_from_spec(run_id, probe_spec, playback_speed=0.0)
288:         ctx.sim_state.capture_workload_signal_trace = True
289:         tick_count = int(round(float(ctx.end_sim_time) / self.tick_seconds))
290:         demand_replay: list[tuple[float, float]] = []
291:         for _ in range(tick_count):
292:             tick = ctx.step()
293:             demand_replay.append(
294:                 (
295:                     float(tick.p_compute_demand_mw),
296:                     float(tick.p_cooling_demand_mw),
297:                 )
298:             )
299:         replay_events = [
300:             _signal_dict(signal)
301:             for signal in ctx.sim_state.workload_signal_trace
302:         ]
303:         if not replay_events:
304:             raise AssertionError(f"{run_id}: empty baseline workload trace")
305:         return replay_events, demand_replay
306: 
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/executor.py:321–354
```text
321:         run_spec = copy.deepcopy(spec)
322:         run_spec["turbine_commitment_mode"] = mode
323:         run_spec.pop("kube_clusters", None)
324:         run_spec.pop("slurm_config", None)
325:         run_spec["workload_events"] = replay_events
326:         duration_seconds = float(run_spec["end_sim_time"])
327:         identity = make_study_run_identity(
328:             scenario_id=scenario_id,
329:             mode=mode,
330:             spec=run_spec,
331:             seed=seed,
332:             tick_seconds=self.tick_seconds,
333:             engine_commit=self.engine_commit,
334:             harness_commit=self.harness_commit,
335:         )
336: 
337:         def execute() -> dict[str, Any]:
338:             ctx = build_run_context_from_spec(
339:                 f"{scenario_id}-{mode}-study-s1",
340:                 run_spec,
341:                 playback_speed=0.0,
342:             )
343:             ctx.sim_state.demand_replay_trace = demand_replay
344:             collector = MetricsCollector(self.tick_seconds)
345:             tick_rows: list[dict[str, Any]] = []
346:             tick_count = int(round(duration_seconds / self.tick_seconds))
347:             for _ in range(tick_count):
348:                 tick = ctx.step()
349:                 collector.add(tick)
350:                 tick_rows.append(_compact_tick(tick))
351:                 if progress_callback is not None and (
352:                     len(tick_rows) == tick_count
353:                     or len(tick_rows) % 100 == 0
354:                 ):
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-uneven-multisched-01.json:1–5
```text
1: {
2:   "name": "01 Turbine Scenario with Kubernetes Slurm Ray",
3:   "description": "Two-hour Kubernetes, Slurm, and Ray demonstration with 45 MW and 90 MW bursts starting at t=30 s and t=310 s, followed by bursts at t=920 s, t=1850 s, and t=2700 s. Burst durations are 240 s, 300 s, and 600 s for the final three bursts, so workloads do not overlap. Two gas turbines are spinning at 35% minimum stable load from t=0; two more start from hot standby at Burst-02 and the grid-forming BESS bridges their startup gap. GE assumptions: 300-second hot start, 360-second warm start, 600-second cold start, and 30 MW/min ramp.",
4: 
5:   "hardware_profile_id": "enterprise_8gpu_air",
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-uneven-multisched-01.json:178–196
```text
178:   ],
179: 
180:   "bess_units": [
181:     { "asset_id": "bess-0", "rated_mw": 30.0, "usable_mwh": 60.0, "initial_soc_fraction": 0.95, "grid_forming": true, "p_anchor_reserve_mw": 1.0, "authority_tier": "autonomous" }
182:   ],
183: 
184:   "diesel_power_block": {
185:     "enabled": true,
186:     "target_capacity_mw": 20.0,
187:     "unit_rating_mw": 20.0,
188:     "p_start": 1.0,
189:     "target_reliability": 1.0,
190:     "f_block": 1.0,
191:     "delta_t_start_s": 3600.0,
192:     "residual_ramp_s": 60.0,
193:     "start_stagger_interval_s": 1.0,
194:     "authority_tier": "advisory_only"
195:   }
196: }
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-fc100-islanded-v2.json:1–18
```text
1: {
2:   "name": "28 FC100 Islanded Readiness Reference",
3:   "description": "Addendum G-1 reference: islanded block fuel-cell array, deterministic 20 MW to 80 MW settled total-site demand step, grid-forming BESS bridge, and advisory-only diesel final reserve. GPU compute rises from approximately 16.67 MW to 66.67 MW while the cooling plant rises from approximately 3.33 MW to 13.33 MW after its thermal delay.",
4:   "site_name": "FC100 Islanded Reference Plant",
5:   "workload_events": [
6:     {"event_id": "fc-base-start", "job_id": "fc-base", "event_type": "running", "timestamp": 0, "node_count": 1634, "hardware_profile_id": "enterprise_8gpu_air"},
7:     {"event_id": "fc-peak-start", "job_id": "fc-peak", "event_type": "starting", "timestamp": 30, "node_count": 4902, "hardware_profile_id": "enterprise_8gpu_air"},
8:     {"event_id": "fc-peak-end", "job_id": "fc-peak", "event_type": "job_end", "timestamp": 1260, "node_count": 0, "hardware_profile_id": "enterprise_8gpu_air"},
9:     {"event_id": "fc-base-end", "job_id": "fc-base", "event_type": "job_end", "timestamp": 1320, "node_count": 0, "hardware_profile_id": "enterprise_8gpu_air"}
10:   ],
11:   "dt_lead_seconds": 30,
12:   "bess_units": [{"asset_id": "bess-fc100", "rated_mw": 60, "usable_mwh": 40, "initial_soc_fraction": 0.95, "grid_forming": true, "p_anchor_reserve_mw": 1}],
13:   "turbine_units": [],
14:   "diesel_power_block": {"enabled": true, "target_capacity_mw": 20, "unit_rating_mw": 20, "p_start": 1, "target_reliability": 1, "f_block": 1, "delta_t_start_s": 3600, "residual_ramp_s": 60, "start_stagger_interval_s": 1, "authority_tier": "advisory_only"},
15:   "solar_rated_mw": 0,
16:   "fuel_cell_enabled": true,
17:   "fuel_cell_units": [{
18:     "asset_id": "fc100-array", "block_rated_mw": 0.325, "block_count": 246,
```

## Method limitations and repository boundary
The first exposure audit attempted full H1 validation without catching the
known-to-this-audit workload-share ValidationError; it stopped after saving
the complete 103-item scope. The scratch script was amended to RETAIN the error
and continue to the other exposure inputs. Application code was never edited;
no validation failure was “fixed” by changing a share/horizon/timing.
The successful second build-only pass retained all errors and produced the
exposure matrix. No simulation ticks were executed in either pass.

Exact certification-date searches used docs, tools, .study-mcp-data,
.local/tasks with hidden/no-ignore inclusion; no external task system or
private document service was queried. No claim about absent external evidence.
Scenario JSON or archived records were read, never rewritten.
No fresh behavior/fuel claim is inferred from an unexecuted context.

Report is copied byte-identically to tools/dr_isl/PHASE_1E_REPORT.md and committed
alone as “DR-ISL report: Phase 1e (no app code)”. Its resulting commit hash and
post-commit git status are given in the final response, not self-embedded.

### Scratch inventory

- `/tmp/DR-ISL-phase1e/3600-provenance.txt` (3603 bytes)

- `/tmp/DR-ISL-phase1e/audit.log` (12492 bytes)

- `/tmp/DR-ISL-phase1e/audit.py` (7231 bytes)

- `/tmp/DR-ISL-phase1e/authority-occurrences.json` (27172 bytes)

- `/tmp/DR-ISL-phase1e/block_history.txt` (3603 bytes)

- `/tmp/DR-ISL-phase1e/build.log` (5778 bytes)

- `/tmp/DR-ISL-phase1e/collect.py` (5143 bytes)

- `/tmp/DR-ISL-phase1e/exposure.json` (11077 bytes)

- `/tmp/DR-ISL-phase1e/history.json` (9966 bytes)

- `/tmp/DR-ISL-phase1e/initial-search.txt` (173766 bytes)

- `/tmp/DR-ISL-phase1e/introduced_commit.txt` (532 bytes)

- `/tmp/DR-ISL-phase1e/report.py` (25299 bytes)

- `/tmp/DR-ISL-phase1e/retained-record-metadata.json` (7575 bytes)

- `/tmp/DR-ISL-phase1e/same_values_fc100_history.txt` (180 bytes)

- `/tmp/DR-ISL-phase1e/scenario-h1-k8s-ray-24h.expanded.json` (25228 bytes)

- `/tmp/DR-ISL-phase1e/scenario-h1-k8s-ray-7d.expanded.json` (134068 bytes)

- `/tmp/DR-ISL-phase1e/scenario-h2-slurm-24h.expanded.json` (21534 bytes)

- `/tmp/DR-ISL-phase1e/scenario-h2-slurm-7d.expanded.json` (101874 bytes)

- `/tmp/DR-ISL-phase1e/scenario-uneven-multisched-01.expanded.json` (12691 bytes)

- `/tmp/DR-ISL-phase1e/scenario-uneven-multisched-01.materialization-diff.json` (47343 bytes)

- `/tmp/DR-ISL-phase1e/scenario-uneven-multisched-01.validated.json` (28910 bytes)

- `/tmp/DR-ISL-phase1e/scope.json` (116465 bytes)

- `/tmp/DR-ISL-phase1e/seeded_ids.json` (1899 bytes)

- `/tmp/DR-ISL-phase1e/source-evidence.md` (46244 bytes)

- `/tmp/DR-ISL-phase1e/summary_history.txt` (109 bytes)

- `/tmp/DR-ISL-phase1e/test-timing-occurrences.txt` (4291 bytes)

- `/tmp/DR-ISL-phase1e/test-timings.json` (7999 bytes)

- `/tmp/DR-ISL-phase1e/timing_history.txt` (3603 bytes)

STOP — END OF PHASE 1e. No implementation, publish/deploy/push, or later phase started.
