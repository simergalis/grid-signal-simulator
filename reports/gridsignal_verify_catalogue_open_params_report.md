# Verify Integration Path, Restore MSL, Catalogue Open Parameters
## Session Report

**Date:** 2026-08-07  
**Ref:** `GS_prompt_verify_and_catalogue_open_params_1786118485083.md`  
**Baseline:** 15 failed / 976 passed / 16 xfailed backend; 29 frontend; `tsc --noEmit` clean.

---

## Item 1 — Integration path: actual run, non-zero demand both cases

**Method:** `SimulationState` built with three turbines forced to `SYNCHRONISED` via direct state assignment (`t.state = TurbineState.SYNCHRONISED`; `t._current_output_mw = rated`). GPU demand injected by calling `gpu.apply_signal(WorkloadSignal(STARTING, node_count=N))` and then setting `gpu._ramp_progress['j1'] = 1.0`, which delivers full TDP on the next tick without the 300-tick ramp-up. `evaluate_tick()` called once per case. Payload dict constructed identically to `run_manager` lines 392–401.

**Why `ramp_progress = 1.0` is a valid direct injection:**  
The GPU module's `output_mw()` computes `node_count × rated_kw × _ramp_multiplier(progress)`. Setting `progress = 1.0` is equivalent to a fully warmed-up cohort — what the engine sees after the ramp window elapses in a live run. It is not a mock; it is the live path reached via direct state manipulation rather than clock time.

**Why the previous satisfied-at-zero case could not discriminate:**  
At demand = 0 MW: `floor_mw = 0 + largest_rated = 15` MW, `committed = 45` MW, `utilisation = 0/45 = 0.000`. The old broken code computed `decommit_utilisation × committed_rated` for floor — which at U=0 also produces values that do not distinguish the implementations. The satisfied-at-zero tick passes both the correct and the hypothetically broken code identically.

**SATISFIED payload — 1 000 nodes × 10 kW = 10.0 MW demand:**

| Field | Value | Arithmetic |
|-------|-------|-----------|
| `net_demand_mw` (TickResult) | **10.300 MW** | GPU output at full TDP + PUE |
| `committed_rated_mw` | **45 MW** | 3 × 15 MW SYNCHRONISED |
| `reserve_floor_mw` | **25.30 MW** | 10.30 + 15.00 (demand + largest) |
| `reserve_satisfied` | **True** | 45 > 25.30 ✓ |
| `utilisation` | **0.229** (23%) | 10.30 / 45 — **non-zero** ✓ |
| `action` | `hold` | below commit threshold |
| `pending_start_unit_id` | `None` | — |

**VIOLATED payload — 3 450 nodes × 10 kW = 34.5 MW demand:**

| Field | Value | Arithmetic |
|-------|-------|-----------|
| `net_demand_mw` (TickResult) | **35.535 MW** | GPU output at full TDP + PUE |
| `committed_rated_mw` | **45 MW** | 3 × 15 MW SYNCHRONISED |
| `reserve_floor_mw` | **50.53 MW** | 35.535 + 15.00 (demand + largest) |
| `reserve_satisfied` | **False** | 45 < 50.53 — floor violated ✓ |
| `utilisation` | **0.790** (79%) | 35.535 / 45 — **non-zero** ✓ |
| `action` | `hold` | commit timer at 5/30 s (not yet sustained) |
| `pending_start_unit_id` | `None` | — |

**Summary:** Both ticks carry non-zero utilisation. The satisfied and violated states are unambiguously distinct on every commitment-block field. The values flow from `evaluate_commitment() → _commit_decision.floor_mw → summary block (line 839) → TickResult → payload dict`. Item 1 acceptance criterion met.

---

## Item 2 — MSL MW restored in the bar sub-annotation

**Approach taken: sub-annotation embedding** (not column restoration).

**Reason for sub-annotation over column restoration:**  
Restoring the `NO-LOAD / MSL MW` column requires dropping another column. The spec offers dropping `RAMP meas/cfg`, but that column still provides non-duplicate information: the *measured* ramp rate alongside the *configured* ceiling — when they diverge the unit is degraded. That divergence is surfaced in no other cell. Dropping it to reclaim the MSL column trades one loss for another. The sub-annotation approach retains all columns and adds the megawatt figure in every unit state.

**Implementation:** `mslSuffix = u.msl_mw > 0 ? ' · MSL X.XX MW' : ''` appended to all dynamic annotation branches. When no other annotation fires, the fallback renders `"MSL X.XX MW"` alone. The "at minimum stable load" branch uses the spec example form exactly: `"at minimum stable load · X.XX MW"`.

**Per-state rendering (msl_mw = 6.00 MW example):**

| Unit state | Annotation |
|------------|-----------|
| `starting` | `"MSL 6.00 MW"` |
| Tracking to setpoint | `"tracking → 13.50 · +2.30 MW to go · MSL 6.00 MW"` |
| At rated, levelled off | `"at rated · levelled off · MSL 6.00 MW"` |
| At MSL | `"at minimum stable load · 6.00 MW"` *(spec example form)* |
| All other states | `"MSL 6.00 MW"` |
| `msl_mw == 0` | `null` (no annotation, unchanged) |

MSL MW is now visible in every state. An operator asking "how low can this unit go" has the answer in the same sub-annotation row they already scan for ramp status.

---

## Item 3 — Open parameters catalogued

### Guard D3 / D2 state

| Metric | Before | After |
|--------|--------|-------|
| `_sp.value()` call sites in `core/` (D3) | **15** | **26** |
| Locked catalogue entries | **29** | **40** |
| Guard D2 backlog | *not empty* | **empty** |

Guard D2 backlog is now empty — `test_guard_d2_backlog_reported` printed `"Guard D2 backlog: empty (all matching literals migrated)."` Guard D3 (`test_guard_d3_sp_value_keys_in_catalogue`) passes — all 26 `_sp.value(key)` keys are in the catalogue. Guard D1 (`test_guard_d1_no_drift`) passes. Guard E passes.

---

### Priority 1 — catalogued

**`r_asset_mw_per_s = 0.2 MW/s`** — `TurbineConfig`  
Provenance: `CHOSEN`. Spec ref: `§7.1 MVP default`. Group: `turbine`.  
The ramp rate is the single most consequential constant in the generation-dispatch model. Every ramp-credit figure in the Generation panel is `r_asset × dt_lead`. Until replaced with OEM measured data, all derived ramp-capability figures are unvalidated. Entry states this explicitly. Claim discipline: do not quote ramp figures externally before replacing with OEM data.

**`cold_start_s = 900 s`** — `TurbineConfig`  
Provenance: `CHOSEN`. Spec ref: `§TC-80`. Group: `turbine`.  
Implied by TC-80 scenario structure; no OEM basis. Frame-class gas turbines: 10–30 min typical. Must be replaced with manufacturer commissioning data.

**`warm_start_s = 300 s`** — `TurbineConfig`  
Provenance: `CHOSEN`. Spec ref: `§7.1 Phase 2`. Group: `turbine`.  
Engineering placeholder; no OEM basis.

**`hot_start_s = 300 s`** — `TurbineConfig`  
Provenance: `CHOSEN`. Spec ref: `§D-08 / Phase D`. Group: `turbine`.  
Corrected from 60 → 300 s during Phase D (D-08): a frame machine cannot synchronise in one minute. The previous 60 s was an unrealistic bypass. Correction history is in the entry's `provenance_detail` so future auditors can find it.

**`inertia_constant_s = 4.0 s`** — `SiteConfig`  
Provenance: `CHOSEN`. Spec ref: `§Phase 13.2`. Group: `site`. **OPEN PARAMETER.**  
H sets the entire frequency-response timescale. The electromechanical time constant is ≈2H/droop, so every derived frequency criterion scales directly with H. Entry states: do not quote absolute frequency figures externally until H is measured and validated against the design partner's generator data.

**`governor_droop = 0.04 pu`** — `SiteConfig`  
Provenance: `CHOSEN`. Spec ref: `§Phase 13.3`. Group: `site`. **OPEN PARAMETER.**  
Typical gas turbine governor setting; no measured basis. Governs frequency response alongside `inertia_constant_s`. Both must be measured together.

---

### Priority 2 — catalogued

**`hot_threshold_s = 3 600 s`** — `TurbineConfig`  
Provenance: `CHOSEN`. 1 h; no OEM calibration. Group: `turbine`.

**`warm_threshold_s = 14 400 s`** — `TurbineConfig`  
Provenance: `CHOSEN`. 4 h; no OEM calibration. Group: `turbine`.

**`levelled_off_tol_mw = 0.05 MW`** — `TurbineConfig`  
Provenance: `CHOSEN`. Spec ref: `PROTO-23`. Group: `turbine`.  
Must be < `r_asset_mw_per_s × dt_seconds` (1.0 MW at r=0.2, dt=5). Entry cites this cross-parameter dependency.

**`workload_signal_stale_s = 30 s`** — `SiteConfig`  
Provenance: `CHOSEN`. Spec ref: `§Phase 11.2`. Group: `site`.  
30 s allows up to 15 s orchestrator heartbeat intervals with a 2× margin. No measured basis.

**`bess_response_tau_s = 0.05 s`** — `BessConfig`  
Provenance: `CHOSEN`. Spec ref: `§Phase 13 inverter model`. Group: `bess`. **OPEN PARAMETER.**  
Grid-forming inverter class (VSM); no measured basis. Entry notes the representative range (20–500 ms depending on inverter class) and states: BESS coverage figures are unvalidated until tau is measured.

---

### Excluded fields — decisions on the record

**Booleans — not physical constants; excluded from catalogue:**

| Field | Reason |
|-------|--------|
| `TurbineConfig.hot_standby` | Operational flag: commissioned-but-offline. No physical quantity to calibrate. |
| `TurbineConfig.min_run_enabled` | Guard flag: enables/disables R5 (min-run) constraint. Not a measured quantity; presence or absence is a design decision. |
| `TurbineConfig.min_down_enabled` | Guard flag: enables/disables R6 (min-down) constraint. Same reasoning as `min_run_enabled`. |
| `BessConfig.grid_forming` | Topology flag: true = VSM/virtual-inertia mode. Inverter capability decision, not a calibration constant. |
| `SiteConfig.band_enabled` | Feature flag: enables confidence band. Not a physical constant. |
| `SiteConfig.uncalibrated` | Calibration-state marker for the band multiplier selection. Not a constant; changes when site is commissioned. |

**Per-unit nameplates — scenario configuration, not site parameters:**

| Field | Reason for exclusion |
|-------|---------------------|
| `TurbineConfig.rated_mw = 10.0` | Per-unit nameplate: each turbine may have a different rated capacity. A single catalogue entry would imply all units share one rating, which is false for a mixed fleet. Scenario factory sets this per asset. |
| `BessConfig.rated_mw = 5.0` | Same reasoning: per-unit nameplate, scenario-specific. |
| `BessConfig.usable_mwh = 2.0` | Per-unit energy nameplate. Varies by battery chemistry and age; a catalogue default would misrepresent physical systems. |
| `BessConfig.initial_soc_fraction = 1.0` | Initial condition, not a physical constant. Set per run by scenario factory; changes between simulation runs. |

**`load_model_bias_mw = 0.0` — confirmed test-only:**

The field is declared at `SiteConfig` line 377 with the comment: *"Default 0.0 — the dispatch engine's load estimate matches the metered load. When non-zero, the difference is reported as `model_error_mw` in TickResult WITHOUT flowing into `p_dispatch_required`, `bess_setpoint`, or `frequency_forcing`. Represents injected PUE miscalibration or load-accounting drift; test-only."*

`simulation_core.py` line 515 reads: `# Does NOT flow into p_dispatch_required, BESS setpoint, or frequency_forcing.` — it is captured as `_model_error_mw` and surfaced in `TickResult.model_error_mw` for display only. No production dispatch path reads it. **Confirmed test-injection only; not catalogued.**

---

### Cross-parameter invariant candidates (reported, none enforced)

The spec prohibits enforcing new cross-parameter invariants beyond `unload_tail_s > levelled_off_window_s`. The following candidates are documented here for future commissioning:

| Candidate | Form | Risk if violated |
|-----------|------|-----------------|
| **H–droop timescale** | `2 × inertia_constant_s / governor_droop` gives the electromechanical time constant. H and droop must be calibrated together — changing one without the other invalidates all derived frequency criteria. | Silent: the frequency model still runs; it produces physically incorrect df/dt. |
| **Start-time ordering** | `hot_start_s ≤ warm_start_s ≤ cold_start_s` | Violation means the engine predicts a hotter unit takes longer to synchronise than a colder one — incorrect commitment timing. |
| **Thermal threshold ordering** | `hot_threshold_s < warm_threshold_s` | Violation means units are never classified WARM — all transitions skip from HOT to COLD. |
| **`levelled_off_tol_mw` < `r_asset_mw_per_s × dt_seconds`** | At r=0.2, dt=5: tol must be < 1.0 MW | Violation: levelled_off fires prematurely mid-descent; units stop before reaching MSL. |
| **`unload_tail_s > levelled_off_window_s`** | Already enforced (Guard E). | — |

None of the above are enforced as new tests in this session.

---

## Acceptance criteria

- [x] Satisfied and violated `commitment_block` values read from emitted payload dict, both with non-zero `utilisation` (0.229 and 0.790 respectively)
- [x] MSL restored in megawatts via sub-annotation; approach stated with rationale
- [x] Priority 1 fields catalogued: `r_asset_mw_per_s`, `cold_start_s`, `warm_start_s`, `hot_start_s`, `inertia_constant_s`, `governor_droop` — all `CHOSEN` with honest provenance, all reading through `_sp.value()`
- [x] Priority 2 fields catalogued: `hot_threshold_s`, `warm_threshold_s`, `levelled_off_tol_mw`, `workload_signal_stale_s`, `bess_response_tau_s`
- [x] Every excluded field reported with reason on the record
- [x] `load_model_bias_mw` confirmed test-only — no production reader
- [x] Guard D3 call-site count: 15 → 26; Guard D2 backlog: non-empty → **empty**
- [x] Cross-parameter invariant candidates reported; none enforced
- [x] Guards D1, D2, D3, E all green; `tsc --noEmit` clean
- [x] Suite: 15 / 976 / 16 xfailed; 29 frontend — **0 regressions**
