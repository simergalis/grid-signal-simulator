# Replit Agent Prompt — Variable Inventory for GS-DES-NAR-001

**Purpose:** produce the identifier inventory needed before an implementation prompt can be written. This is a **read-only discovery task**. No implementation, no refactor, no fixes.

Copy everything below the line into the Replit agent.

---

## TASK

You are producing a **read-only inventory** of existing identifiers in this repository. You will write exactly one new file and change nothing else.

Do not implement anything. Do not fix anything you find. Do not refactor. A later prompt will do that work; it cannot be written until this inventory exists.

**Output file:** `docs/inventory/NAR-001_variable_inventory.md`

Run in two phases with a hard stop between them.

---

## PHASE 0 — Orient, then stop

Report the following in chat. Do not create the output file yet. Do not proceed to Phase 1 until I reply.

1. **Module map.** For each of these, give the file path and the primary entry symbol:
   - The simulation tick loop (the thing that advances time and produces the per-tick state object).
   - The per-tick state object / dataclass / dict that holds site state at one instant. Give its exact type name and the file it is defined in. If there is no single such object, say so explicitly — that is a significant finding.
   - Every module that computes physics. Name each one. Report whether more than one exists.
   - The API layer that serves state to the frontend, and the WebSocket publisher (topic names and message schema type).
   - The runtime configuration catalogue: the accessor function, the file the values live in, and how a caller reads a key.
   - The frontend components that render the landing-page tiles and the detail panels, by file path.
   - The persistence layer: which tables/models exist for run output, and where the schema is defined.
   - Any existing LLM client module, the model identifier string it uses, and where that string is set.

2. **Enumerations.** List the exact enum/constant names and their full member sets for: turbine unit state, job/workload state, BESS mode, run state, alert or verdict severity.

3. **Test and record IDs in use.** The highest `TC-` number currently present anywhere in the repo, and the list of `DR-` and `GS-DES-` document IDs referenced in code or docs.

4. **Counts.** Approximate number of signals you expect to be able to locate from the Phase 1 list, and which sections of the list you expect to come back mostly `NOT_FOUND`.

Then **stop and wait**.

---

## PHASE 1 — Inventory

For every signal listed in the SIGNAL LIST below, emit one YAML block in the output file, in the order given.

### Required block format

```yaml
- canonical: LOAD.it_draw_mw            # from the list below, verbatim
  status: FOUND                          # FOUND | NOT_FOUND | AMBIGUOUS | MULTIPLE
  backend:
    identifier: it_draw_mw               # exact identifier as written in code
    defined_at: "core/simulation_core.py:412"
    excerpt: "self.it_draw_mw = compute_mw + 0.0"   # verbatim single line, no edits
    type: float
    units_declared: false                # true only if units appear in code/docstring/schema
    units_declared_where: null           # file:line, or null
    units_assumed_by_you: MW             # what you believe; kept separate from the above on purpose
  transport:
    field: itDrawMw
    schema_at: "api/schemas.py:88"
  frontend:
    identifier: itDraw
    rendered_at: "client/src/components/ComputePanel.tsx:143"
    literal: false                       # true if the displayed value is a hardcoded literal
  duplicates:                            # every other place this quantity is computed
    - "gridsignal_logger.py:207"
  notes: ""                              # facts only; see DO NOT #3
```

### Rules for filling it in

- **`defined_at` and `excerpt` are mandatory for any `FOUND`.** A block with `status: FOUND` and no file:line and no verbatim excerpt is invalid. If you cannot supply both, the status is `NOT_FOUND`.
- **`NOT_FOUND` is a correct and useful answer.** Do not stretch a partial match to fill a row. If the closest thing you found is not the same quantity, use `NOT_FOUND` and name the near-miss in `notes`.
- **`AMBIGUOUS`** when two or more identifiers could plausibly be the signal and you cannot tell which without running the code. List all candidates in `notes`. Do not pick one.
- **`MULTIPLE`** when the same quantity is genuinely computed in more than one place. List every site in `duplicates`. Do not reconcile them, do not judge which is correct, do not delete either.
- **`units_declared` is `true` only if the units are written down somewhere** — a type annotation, docstring, schema description, column comment, or config catalogue entry. A variable named `_mw` does **not** declare its units. This distinction is the point of the field.
- **`frontend.literal: true`** when the tile renders a constant rather than a value fed from the backend. Flag every one of these; they are findings, not noise.
- Where a signal exists only on the frontend with no backend producer, fill `backend.status` context in `notes` and set the top-level status to `NOT_FOUND` with an explanation.

---

## SIGNAL LIST

### A. Scheduler / workload (`SCHED`)
`SCHED.job_admit_event`, `SCHED.job_complete_event`, `SCHED.job_checkpoint_event`, `SCHED.node_count`, `SCHED.queue_depth`, `SCHED.dt_lead_s`, `SCHED.jobs_total`, `SCHED.jobs_running`, `SCHED.jobs_starting`, `SCHED.job_class` (per job), `SCHED.per_job_draw_mw`, `SCHED.last_event_age_s`, `SCHED.feed_health`

### B. Load / consumption (`LOAD`)
`LOAD.it_draw_mw`, `LOAD.cooling_draw_mw`, `LOAD.site_total_mw`, `LOAD.pue_base`, `LOAD.pue_effective`, and for each load block (compute, cooling, and any others that exist): `LOAD.{block}.served_mw`, `LOAD.{block}.demand_mw`, `LOAD.{block}.unserved_mw`

### C. Generation and storage (`GEN`)
`GEN.unit_state` (per unit), `GEN.unit_setpoint_mw`, `GEN.unit_output_mw`, `GEN.unit_rated_mw`, `GEN.unit_msl_mw`, `GEN.breaker_state`, `GEN.units_installed`, `GEN.units_online`, `GEN.fleet_output_mw`, `GEN.n1_firm_mw`, `GEN.aggregate_ramp_mw_per_s`, `GEN.gen_trip_cover_shed_mw`, `GEN.committed_mw`, `GEN.reserve_floor_mw`, `GEN.reserve_margin_mw`, `GEN.floor_violated`, `GEN.last_decision`, `SUPPLY.dispatchable_mw`, `BESS.output_mw`, `BESS.soc_pct`, `BESS.rated_mw`, `BESS.rated_mwh`, `BESS.mode`, `BESS.anchor_mw`

### D. Demand / forecast (`DEMAND`)
`DEMAND.predicted_step_mw`, `DEMAND.band_low_mw`, `DEMAND.band_high_mw`, `DEMAND.forecast_mw`, `DQ.flag_count`, `DQ.band_widening_pct`, `DEMAND.calibration_state`

### E. Renewable (`RENEW`)
`RENEW.solar_output_mw`, `RENEW.expected_mw`, `RENEW.offset_applied_mw`, `RENEW.rated_mw`, `RENEW.sun_elevation_deg`, `RENEW.conditions`, `RENEW.banks_reporting`, `RENEW.banks_total`

### F. Thermal (`THERM`)
`THERM.cooling_mw`, `THERM.cooling_rated_mw`, `THERM.alpha_measured`, `THERM.alpha_modelled`, `THERM.dt_thermal_configured_s`, `THERM.cooling_lag_observed_s`, `THERM.cdu_state`, `THERM.loop_state`, `THERM.approach_temp_c`, `THERM.ambient_temp_c`

### G. Run, clock, and mode (`RUN`)
`RUN.run_id`, `RUN.t_sim_s`, `RUN.wall_clock_utc`, `RUN.speed_multiplier`, `RUN.state`, `RUN.tick_rate_s`, `RUN.scenario_id`, `RUN.scenario_version`, `RUN.mode` (grid/islanded), `RUN.physics_path`, `RUN.code_rev`, `CLOCK.site_tz`, `CLOCK.site_local`, `CLOCK.utc`

### H. Verdicts, alerts, network (`VERDICT` / `NET`)
`VERDICT.{panel}` — the derived verdict/headline string for each detail panel and for the readiness header. For each: is it a formatted string with no structured backing, or does a structured representation exist? Report the format string and its inputs.
`ALERT.active_list`, `ALERT.attention_subsystem_count`, `NET.switches_reporting`, `NET.clock_class`, `NET.clock_class_degraded_n`

### I. Invariant inputs

For each identity below, report whether **every** input term is available in a single state object at one instant, and name the terms. If any term is not available, say which.

- **I1** power balance: Σ supply vs Σ served, islanded
- **I2** attribution: `it_draw_mw` vs Σ per-job draw
- **I3** tri-field: `served + unserved = demand` per block
- **I4** asset rating: served/output vs rated, per asset
- **I5** storage energy: ΔSoC × E_rated vs ∫P_bess dt
- **I6** fleet capacity: output vs units_online × unit_rating; n1_firm vs committed − largest unit
- **I7** solar expectation vs sun elevation
- **I8** feed health vs last-event age
- **I9** clock coherence across displayed timestamps

### J. Configuration catalogue

List every existing catalogue key with its current value and where the value is defined. Separately, list which of these **do not yet exist** (I expect all of them): `tick_rate_s`, and any deadband, hysteresis, trend-window, staleness, or tolerance parameter. Do not create them.

### K. Explainer and readiness tiles

- Where does the text currently shown in the explainer tile come from — a TSX literal, a scenario spec field, a database column, or something else? Give file:line.
- Same for the readiness header string and its countdown field.
- Are these tiles addressed anywhere by a stable component ID, or only by their title string?

---

## OUTPUT FILE STRUCTURE

```
# NAR-001 Variable Inventory
## 1. Summary counts        (FOUND / NOT_FOUND / AMBIGUOUS / MULTIPLE, by section)
## 2. Signals with no backend producer      (frontend literals)
## 3. Quantities computed in more than one place
## 4. Signals whose units are nowhere declared
## 5. Full inventory        (the YAML blocks, in list order)
## 6. Invariant input availability   (section I)
## 7. Configuration catalogue          (section J)
## 8. Questions I could not resolve by reading
```

Sections 2, 3, and 4 are the ones I will read first. Populate them properly.

---

## DO NOT

1. Do not modify any file other than the single output file. No fixes, no renames, no refactors, no new modules, no deletions.
2. Do not implement any part of the narration feature. This prompt produces an inventory only.
3. **Do not infer behaviour, semantics, or units from an identifier name.** `bess_rated_mw` tells you nothing about what the value is or whether it is in megawatts. Report the name, the definition site, and the verbatim line. Leave interpretation to me.
4. Do not guess to fill a row. `NOT_FOUND` and `AMBIGUOUS` are correct answers and are more useful than a confident wrong one.
5. Do not reconcile, consolidate, or choose between duplicate implementations. Report all of them.
6. Do not create any configuration key, constant, or default value. If something is missing, that is the finding.
7. Do not edit any specification, design document, or decision record.
8. Do not run the simulator, generate telemetry, or execute a scenario. This is a static read.
9. Do not write "standard naming conventions apply" or any equivalent generalisation in place of an actual identifier.
10. Do not proceed from Phase 0 to Phase 1 without my reply.
11. If the task grows beyond what you can complete accurately, stop and report what is done and what remains. A partial inventory with correct file:line references is worth more than a complete one with invented ones.

## STOP AND REPORT IF

- You cannot locate a single per-tick state object.
- You find more than two modules computing physics.
- More than a quarter of any section comes back `NOT_FOUND`.
- Any signal in the list turns out to be rendered from a frontend literal with no backend path at all.
