# NAR-001 Variable Inventory

**Task:** GS-DES-NAR-001  
**Phase:** 1 — Signal inventory  
**Date:** 2026-08-08  
**Authorised by:** Phase 1 authorization prompt  
**Baseline codebase:** `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/`  
**Frontend baseline:** `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/`

Abbreviated below as `SIM/` and `FE/` respectively.

---

## How to Read

- **FOUND** — signal exists; `file:line` and verbatim excerpt provided.
- **NOT_FOUND** — signal does not exist in the codebase in any form; absence confirmed.
- **AMBIGUOUS** — signal exists under a different name or structure; nearest match described.
- `on_tick_result: true` — field is declared on the `TickResult` frozen dataclass (`SIM/core/models.py:870`).
- `on_wire: true` — key is emitted by `_tick_result_to_dict()` (`SIM/runtime/run_manager.py:201`).
- `wall_stamp_utc` is the only `TickResult` field intentionally excluded from the wire (see §9).
- TC numbers: none assigned in this file per Amendment A4. Allocate from TC-110 onward after inventory is complete.

---

## Section A — SCHED (Scheduler / Workload Events)

### A.1 — Jobs running in checkpoint_states

```yaml
signal: SCHED.jobs_running
status: FOUND
on_tick_result: true
tick_result_field: checkpoint_states
defined_at: "SIM/core/models.py:882"
assigned_at: "SIM/core/simulation_core.py:509"
excerpt: "checkpoint_states: dict[str, str]"
on_wire: true
wire_field: checkpoint_states
wire_at: "SIM/runtime/run_manager.py:244"
frontend_field: checkpoint_states
rendered_at: "FE/subsystem/useSubsystemData.ts:97"
frontend_literal: false
units_declared: false
units_assumed_by_you: count
duplicates: []
notes: >
  checkpoint_states is a dict[job_id → phase_string]. Callers derive jobs_running
  by filtering values == 'running'. No scalar jobs_running field exists on TickResult
  or wire. The derivation in useSubsystemData.ts:97 is:
  Object.values(tick.checkpoint_states).filter(s => s === 'running').length
```

### A.2 — Total jobs in checkpoint_states

```yaml
signal: SCHED.jobs_total
status: AMBIGUOUS
on_tick_result: true
tick_result_field: checkpoint_states
defined_at: "SIM/core/models.py:882"
assigned_at: "SIM/core/simulation_core.py (within evaluate_tick)"
excerpt: "checkpoint_states: dict[str, str]"
on_wire: true
wire_field: checkpoint_states
wire_at: "SIM/runtime/run_manager.py:244"
frontend_field: checkpoint_states
rendered_at: "FE/subsystem/useSubsystemData.ts:99"
frontend_literal: false
units_declared: false
units_assumed_by_you: count
duplicates: []
notes: >
  No scalar jobs_total field. Derived as Object.keys(tick.checkpoint_states).length.
  jobs_starting: NOT_FOUND — checkpoint_states has no 'starting' phase string.
  The kube path exposes active_jobs (see A.3) for active job count.
```

### A.3 — Kube active jobs

```yaml
signal: SCHED.active_jobs
status: FOUND
on_tick_result: true
tick_result_field: kube_metrics.active_jobs
defined_at: "SIM/core/models.py:843"
assigned_at: "SIM/core/kube_demand.py:399"
excerpt: "active_jobs = len(self._active_jobs)"
on_wire: true
wire_field: kube_metrics.active_jobs
wire_at: "SIM/runtime/run_manager.py:337"
frontend_field: kube_metrics.active_jobs
rendered_at: "FE/subsystem/panels/compute.ts (kube conditional section)"
frontend_literal: false
units_declared: false
units_assumed_by_you: count
duplicates: []
notes: >
  active_jobs = count of _ActiveJob instances currently in self._active_jobs list.
  Jobs are admitted based on headroom and retired when ends_at <= sim_time.
  kube_metrics is null when kube_config is absent from the ScenarioSpec.
```

### A.4 — Kube admitted nodes

```yaml
signal: SCHED.admitted_nodes
status: FOUND
on_tick_result: true
tick_result_field: kube_metrics.admitted_nodes
defined_at: "SIM/core/models.py:844"
assigned_at: "SIM/core/kube_demand.py:396"
excerpt: "admitted_nodes = sum(j.node_count for j in self._active_jobs)"
on_wire: true
wire_field: kube_metrics.admitted_nodes
wire_at: "SIM/runtime/run_manager.py:338"
frontend_field: kube_metrics.admitted_nodes
rendered_at: "FE/subsystem/panels/compute.ts"
frontend_literal: false
units_declared: false
units_assumed_by_you: count
duplicates: []
notes: "Sum of node_count across all active jobs. Distinct from node_count (total_nodes includes min_nodes baseline)."
```

### A.5 — Kube node count

```yaml
signal: SCHED.node_count
status: FOUND
on_tick_result: true
tick_result_field: kube_metrics.node_count
defined_at: "SIM/core/models.py:841"
assigned_at: "SIM/core/kube_demand.py:398"
excerpt: "total_nodes = max(self.config.min_nodes, admitted_nodes)"
on_wire: true
wire_field: kube_metrics.node_count
wire_at: "SIM/runtime/run_manager.py:334"
frontend_field: kube_metrics.node_count
rendered_at: "FE/subsystem/panels/compute.ts"
frontend_literal: false
units_declared: false
units_assumed_by_you: count
duplicates: []
notes: "total_nodes = max(min_nodes, admitted_nodes). Never below the idle baseline."
```

### A.6 — Kube arrivals this tick

```yaml
signal: SCHED.arrivals_this_tick
status: FOUND
on_tick_result: true
tick_result_field: kube_metrics.arrivals_this_tick
defined_at: "SIM/core/models.py:845"
assigned_at: "SIM/core/kube_demand.py:297"
excerpt: "arrivals_this_tick += 1"
on_wire: true
wire_field: kube_metrics.arrivals_this_tick
wire_at: "SIM/runtime/run_manager.py:339"
frontend_field: kube_metrics.arrivals_this_tick
rendered_at: "FE/subsystem/panels/compute.ts"
frontend_literal: false
units_declared: false
units_assumed_by_you: count
duplicates: []
notes: "Incremented each time a job enters the admission queue in this tick."
```

### A.7 — Kube requeued this tick

```yaml
signal: SCHED.requeued_this_tick
status: FOUND
on_tick_result: true
tick_result_field: kube_metrics.requeued_this_tick
defined_at: "SIM/core/models.py:846"
assigned_at: "SIM/core/kube_demand.py:363"
excerpt: "requeued_this_tick += 1"
on_wire: true
wire_field: kube_metrics.requeued_this_tick
wire_at: "SIM/runtime/run_manager.py:340"
frontend_field: kube_metrics.requeued_this_tick
rendered_at: "FE/subsystem/panels/compute.ts"
frontend_literal: false
units_declared: false
units_assumed_by_you: count
duplicates: []
notes: "Incremented when a job is re-queued after eviction."
```

### A.8 — Step phase

```yaml
signal: SCHED.step_phase
status: FOUND
on_tick_result: true
tick_result_field: step_phase
defined_at: "SIM/core/models.py (TickResult)"
assigned_at: "SIM/core/simulation_core.py (within evaluate_tick)"
excerpt: "step_phase: float"
on_wire: true
wire_field: step_phase
wire_at: "SIM/runtime/run_manager.py:440"
frontend_field: step_phase
rendered_at: "gridsignal_logger.py:209"
frontend_literal: false
units_declared: false
units_assumed_by_you: fraction 0.0-1.0
duplicates: []
notes: "Fractional position within current ML training step. 0.0 when no step in progress."
```

### A.9 — Step kind

```yaml
signal: SCHED.step_kind
status: FOUND
on_tick_result: true
tick_result_field: step_kind
defined_at: "SIM/core/models.py (TickResult)"
assigned_at: "SIM/core/simulation_core.py (within evaluate_tick)"
excerpt: "step_kind: str"
on_wire: true
wire_field: step_kind
wire_at: "SIM/runtime/run_manager.py:441"
frontend_field: step_kind
rendered_at: "gridsignal_logger.py:210"
frontend_literal: false
units_declared: false
units_assumed_by_you: string 'training'|'checkpoint'
duplicates: []
notes: "'training' or 'checkpoint'. Empty string when no step in progress."
```

### A.10 — Lead time to next GPU full-TDP

```yaml
signal: SCHED.dt_lead_next_s
status: FOUND
on_tick_result: true
tick_result_field: dt_lead_next_s
defined_at: "SIM/core/models.py (TickResult)"
assigned_at: "SIM/core/simulation_core.py:995"
excerpt: "dt_lead_next_s: float"
on_wire: true
wire_field: dt_lead_next_s
wire_at: "SIM/runtime/run_manager.py:264"
frontend_field: dt_lead_next_s
rendered_at: "FE/subsystem/useSubsystemData.ts:102"
frontend_literal: false
units_declared: false
units_assumed_by_you: seconds
duplicates: []
notes: "0.0 when no GPU job is currently ramping. Minimum over all in-flight jobs."
```

### A.11 — Last event age / Feed health

```yaml
signal: SCHED.last_event_age_s
status: NOT_FOUND
notes: >
  No elapsed-time-since-last-event scalar is exported on TickResult or wire.
  The elapsed time (sim_time - state._last_workload_signal_sim_time) is computed
  internally at SIM/core/simulation_core.py:1081 but only as an anonymous
  comparison operand, not stored. WORKLOAD_SIGNAL_STALE tag (see D section) is
  the closest proxy — it fires when elapsed >= workload_signal_stale_s.

signal: SCHED.feed_health
status: NOT_FOUND
notes: >
  No structured feed-health scalar or enum exists on TickResult or wire.
  data_quality_tags carries WORKLOAD_SIGNAL_STALE and WORKLOAD_SIGNAL_ABSENT
  as tag strings (see D.3), which together carry feed health information,
  but no single 'feed_health' field exists.
```

---

## Section B — LOAD

### B.1 — IT compute draw

```yaml
signal: LOAD.p_compute_mw
status: FOUND
on_tick_result: true
tick_result_field: p_compute_demand_mw
defined_at: "SIM/core/models.py (TickResult)"
assigned_at: "SIM/core/simulation_core.py:509"
excerpt: "p_compute_demand_mw = sum(_per_job_draws.values())"
on_wire: true
wire_field: p_compute_mw
wire_at: "SIM/runtime/run_manager.py:209"
frontend_field: p_compute_mw
rendered_at: "FE/subsystem/panels/compute.ts"
frontend_literal: false
units_declared: false
units_assumed_by_you: MW
duplicates: ["p_compute_demand_mw (also emitted separately at run_manager.py:218)"]
notes: "p_compute_mw is an alias; p_compute_demand_mw is the canonical field name."
```

### B.2 — Cooling draw

```yaml
signal: LOAD.p_cooling_mw
status: FOUND
on_tick_result: true
tick_result_field: p_cooling_demand_mw
defined_at: "SIM/core/models.py (TickResult)"
assigned_at: "SIM/core/simulation_core.py:514"
excerpt: "p_cooling_demand_mw = state.cooling.output_mw()"
on_wire: true
wire_field: p_cooling_mw
wire_at: "SIM/runtime/run_manager.py:210"
frontend_field: p_cooling_mw
rendered_at: "FE/subsystem/panels/compute.ts"
frontend_literal: false
units_declared: false
units_assumed_by_you: MW
duplicates: ["p_cooling_demand_mw (also emitted separately at run_manager.py:222)"]
notes: "90-second lagged response from CoolingModule."
```

### B.3 — Total site demand

```yaml
signal: LOAD.p_total_mw
status: FOUND
on_tick_result: true
tick_result_field: p_demand_mw
defined_at: "SIM/core/models.py (TickResult)"
assigned_at: "SIM/core/simulation_core.py:516"
excerpt: "p_demand_mw = p_compute_demand_mw + p_cooling_demand_mw"
on_wire: true
wire_field: p_total_mw
wire_at: "SIM/runtime/run_manager.py:211"
frontend_field: p_total_mw
rendered_at: "FE/subsystem/panels/compute.ts"
frontend_literal: false
units_declared: false
units_assumed_by_you: MW
duplicates: ["p_demand_mw (also emitted separately at run_manager.py:226)"]
notes: "p_total_mw = p_compute_mw + p_cooling_mw. Does not include PUE overhead separately."
```

### B.4 — Net demand (dispatch-side)

```yaml
signal: LOAD.net_demand_mw
status: FOUND
on_tick_result: true
tick_result_field: net_demand_mw
defined_at: "SIM/core/models.py (TickResult)"
assigned_at: "SIM/core/simulation_core.py:586"
excerpt: "net_demand_mw = p_dispatch_required_mw"
on_wire: true
wire_field: net_demand_mw
wire_at: "SIM/runtime/run_manager.py:236"
frontend_field: net_demand_mw
rendered_at: "FE/subsystem/panels/generation.ts"
frontend_literal: false
units_declared: false
units_assumed_by_you: MW
duplicates: []
notes: "net_demand_mw = max(0, p_total_mw - p_renewable_mw). What dispatch must cover."
```

### B.5-B.10 — Served/unserved load breakdown

```yaml
signal: LOAD.p_served_mw
status: FOUND
on_tick_result: true
tick_result_field: p_served_mw
defined_at: "SIM/core/models.py (TickResult)"
assigned_at: "SIM/core/simulation_core.py:1675"
excerpt: "_p_served_mw = p_demand_mw - _cumulative_shed_mw"
on_wire: true
wire_field: p_served_mw
wire_at: "SIM/runtime/run_manager.py:228"
frontend_field: p_served_mw
rendered_at: "FE/opening/VerdictBand.tsx"
frontend_literal: false
units_declared: false
units_assumed_by_you: MW
duplicates: []
notes: "Optional[float] — null when UFLS path not active (grid-connected normal operation)."

signal: LOAD.p_unserved_mw
status: FOUND
on_tick_result: true
tick_result_field: p_unserved_mw
defined_at: "SIM/core/models.py (TickResult)"
assigned_at: "SIM/core/simulation_core.py:1675"
excerpt: "_p_served_mw = p_demand_mw - _cumulative_shed_mw"
on_wire: true
wire_field: p_unserved_mw
wire_at: "SIM/runtime/run_manager.py:229"
frontend_field: p_unserved_mw
rendered_at: "FE/opening/VerdictBand.tsx"
frontend_literal: false
units_declared: false
units_assumed_by_you: MW
duplicates: []
notes: "Optional[float] — null when UFLS path not active. Equals cumulative shed MW."

signal: LOAD.p_compute_served_mw
status: FOUND
on_tick_result: true
tick_result_field: p_compute_served_mw
defined_at: "SIM/core/models.py (TickResult)"
assigned_at: "SIM/core/simulation_core.py:1685"
excerpt: "_p_compute_served_mw   = p_compute_demand_mw - _p_unserved_mw * _compute_demand_frac"
on_wire: true
wire_field: p_compute_served_mw
wire_at: "SIM/runtime/run_manager.py:220"
frontend_field: null
rendered_at: null
frontend_literal: false
units_declared: false
units_assumed_by_you: MW
duplicates: []
notes: "Optional[float] — null outside UFLS path. Proportional split by compute/total fraction."

signal: LOAD.p_compute_unserved_mw
status: FOUND
on_tick_result: true
tick_result_field: p_compute_unserved_mw
defined_at: "SIM/core/models.py (TickResult)"
assigned_at: "SIM/core/simulation_core.py:1685"
excerpt: "see p_compute_served_mw assignment"
on_wire: true
wire_field: p_compute_unserved_mw
wire_at: "SIM/runtime/run_manager.py:221"
frontend_field: null
rendered_at: null
units_declared: false
units_assumed_by_you: MW
duplicates: []
notes: "Optional[float]."

signal: LOAD.p_cooling_served_mw
status: FOUND
on_tick_result: true
tick_result_field: p_cooling_served_mw
on_wire: true
wire_field: p_cooling_served_mw
wire_at: "SIM/runtime/run_manager.py:224"
units_assumed_by_you: MW
notes: "Optional[float]."

signal: LOAD.p_cooling_unserved_mw
status: FOUND
on_tick_result: true
tick_result_field: p_cooling_unserved_mw
on_wire: true
wire_field: p_cooling_unserved_mw
wire_at: "SIM/runtime/run_manager.py:225"
units_assumed_by_you: MW
notes: "Optional[float]."
```

### B.11 — PUE effective

```yaml
signal: LOAD.pue_effective
status: NOT_FOUND
notes: >
  No pue_effective field on TickResult or wire. pue_base (catalogue key PARAM-06,
  value 1.03) is a static config constant read at scenario build time and never
  stamped on TickResult. The effective PUE (which varies with cooling) is not
  computed or exported as a named scalar. alpha_max (on wire) and
  ambient_alpha_scale (on wire) capture the cooling fraction, but their product
  is not labelled as PUE anywhere in the codebase.
```

---

## Section C — GEN (Generation)

### C.1 — Turbine fleet output

```yaml
signal: GEN.turbine_output_mw
status: FOUND
on_tick_result: true
tick_result_field: turbine_output_mw
defined_at: "SIM/core/models.py (TickResult)"
assigned_at: "SIM/core/simulation_core.py:824"
excerpt: "turbine_output_mw: float"
on_wire: true
wire_field: turbine_output_mw
wire_at: "SIM/runtime/run_manager.py:237"
frontend_field: turbine_output_mw
rendered_at: "FE/subsystem/useSubsystemData.ts:133"
frontend_literal: false
units_declared: false
units_assumed_by_you: MW
duplicates: []
notes: "All SYNCHRONISED + RAMPING/AT_TARGET units included."
```

### C.2 — On-bus fleet output (A-set)

```yaml
signal: GEN.on_bus_output_mw
status: FOUND
on_tick_result: false
tick_result_field: null
defined_at: null
assigned_at: null
excerpt: null
on_wire: true
wire_field: on_bus_output_mw
wire_at: "SIM/runtime/run_manager.py:319"
frontend_field: on_bus_output_mw
rendered_at: "FE/subsystem/panels/turbineFleet.ts"
frontend_literal: false
units_declared: false
units_assumed_by_you: MW
duplicates: []
notes: >
  Wire-derived field, not a TickResult field. Computed in _tick_result_to_dict()
  as sum(output_mw for units with state in {synchronised, unloading}).
  UNLOADING units included (they produce at MSL). Formula:
  round(sum(u.get('output_mw',0.0) for u in tick.turbine_units
  if u.get('state') in {'synchronised','unloading'}), 4)
```

### C.3 — Units on bus count

```yaml
signal: GEN.units_on_bus_count
status: FOUND
on_tick_result: false
on_wire: true
wire_field: units_on_bus_count
wire_at: "SIM/runtime/run_manager.py:309"
frontend_field: null
rendered_at: "FE/subsystem/panels/turbineFleet.ts"
frontend_literal: false
units_declared: false
units_assumed_by_you: count
duplicates: []
notes: "Wire-derived. Count of turbine_units with state in {synchronised, unloading}."
```

### C.4 — BESS output

```yaml
signal: GEN.bess_output_mw
status: FOUND
on_tick_result: true
tick_result_field: bess_output_mw
assigned_at: "SIM/core/simulation_core.py:824"
on_wire: true
wire_field: bess_output_mw
wire_at: "SIM/runtime/run_manager.py:238"
frontend_field: bess_output_mw
rendered_at: "FE/subsystem/useSubsystemData.ts:199"
units_declared: false
units_assumed_by_you: MW
notes: "Positive = discharge. After SOC/power clipping."
```

### C.5 — BESS state of charge

```yaml
signal: GEN.bess_soc_fraction
status: FOUND
on_tick_result: true
tick_result_field: bess_soc_fraction
on_wire: true
wire_field: bess_soc_fraction
wire_at: "SIM/runtime/run_manager.py:239"
frontend_field: bess_soc_fraction
rendered_at: "FE/subsystem/useSubsystemData.ts:118"
units_declared: false
units_assumed_by_you: fraction 0.0-1.0
notes: ""
```

### C.6 — BESS bridging seconds

```yaml
signal: GEN.bess_bridging_seconds
status: FOUND
on_tick_result: true
tick_result_field: bess_bridging_seconds
on_wire: true
wire_field: bess_bridging_seconds
wire_at: "SIM/runtime/run_manager.py:256"
frontend_field: bess_bridging_seconds
rendered_at: "FE/subsystem/useSubsystemData.ts:119"
units_declared: false
units_assumed_by_you: seconds
notes: "Capped at 86400 s (24 h) for JSON safety when net_demand_mw == 0."
```

### C.7 — BESS rated MW / usable MWh / unit count / anchor reserve

```yaml
signal: GEN.bess_rated_mw
status: FOUND
on_tick_result: true
tick_result_field: bess_rated_mw
on_wire: true
wire_field: bess_rated_mw
wire_at: "SIM/runtime/run_manager.py:447"
frontend_field: bess_rated_mw
rendered_at: "FE/subsystem/panels/storage.ts"
units_declared: false
units_assumed_by_you: MW
notes: "Config nameplate aggregate, not contingency_coverage.bess_usable_energy_mwh."

signal: GEN.bess_usable_mwh
status: FOUND
on_tick_result: true
tick_result_field: bess_usable_mwh
on_wire: true
wire_field: bess_usable_mwh
wire_at: "SIM/runtime/run_manager.py:448"
units_assumed_by_you: MWh
notes: ""

signal: GEN.bess_unit_count
status: FOUND
on_tick_result: true
tick_result_field: bess_unit_count
on_wire: true
wire_field: bess_unit_count
wire_at: "SIM/runtime/run_manager.py:449"
units_assumed_by_you: count
notes: ""

signal: GEN.bess_anchor_reserve_mw
status: FOUND
on_tick_result: true
tick_result_field: bess_anchor_reserve_mw
on_wire: true
wire_field: bess_anchor_reserve_mw
wire_at: "SIM/runtime/run_manager.py:457"
units_assumed_by_you: MW
notes: "Headroom withheld from bridging for grid-forming frequency regulation."
```

### C.8 — Dispatch setpoints

```yaml
signal: GEN.bess_setpoint_mw
status: FOUND
on_tick_result: true
tick_result_field: bess_setpoint_mw
on_wire: true
wire_field: bess_setpoint_mw
wire_at: "SIM/runtime/run_manager.py:406"
units_assumed_by_you: MW
notes: "Commanded output before SOC/power clipping."

signal: GEN.gt_setpoint_mw
status: FOUND
on_tick_result: true
tick_result_field: gt_setpoint_mw
on_wire: true
wire_field: gt_setpoint_mw
wire_at: "SIM/runtime/run_manager.py:407"
units_assumed_by_you: MW
notes: "Total dispatch requirement handed to turbine fleet."
```

### C.9 — Generation total / ramp / balance

```yaml
signal: GEN.p_generation_mw
status: FOUND
on_tick_result: true
tick_result_field: p_generation_mw
on_wire: true
wire_field: p_generation_mw
wire_at: "SIM/runtime/run_manager.py:230"
units_assumed_by_you: MW
notes: >
  Phase 1 field. Summing turbine + solar + BESS to produce p_generation_mw in
  the transport layer is prohibited (spec §16.14 TC-92). Value comes from evaluate_tick.

signal: GEN.ramp_capability_mw
status: FOUND
on_tick_result: true
tick_result_field: ramp_capability_mw
on_wire: true
wire_field: ramp_capability_mw
wire_at: "SIM/runtime/run_manager.py:435"
frontend_field: ramp_capability_mw
rendered_at: "FE/subsystem/panels/generation.ts"
units_assumed_by_you: MW
notes: "Fleet ramp over the runtime lead horizon (dt_lead_next_s)."

signal: GEN.turbine_ramp_credit_mw
status: FOUND
on_tick_result: true
tick_result_field: turbine_ramp_credit_mw
on_wire: true
wire_field: turbine_ramp_credit_mw
wire_at: "SIM/runtime/run_manager.py:260"
units_assumed_by_you: MW
notes: "MW turbines can cover before demand step lands."

signal: GEN.peak_shortfall_mw
status: FOUND
on_tick_result: true
tick_result_field: peak_shortfall_mw
on_wire: true
wire_field: peak_shortfall_mw
wire_at: "SIM/runtime/run_manager.py:261"
units_assumed_by_you: MW
notes: "MW BESS must bridge (delta - credit)."

signal: GEN.bridging_basis
status: FOUND
on_tick_result: true
tick_result_field: bridging_basis
on_wire: true
wire_field: bridging_basis
wire_at: "SIM/runtime/run_manager.py:269"
units_assumed_by_you: string
notes: "'predicted_peak' | 'current_demand' | 'no_load'"
```

### C.10 — Commitment / reserve

```yaml
signal: GEN.committed_rated_mw
status: FOUND
on_tick_result: true
tick_result_field: committed_rated_mw
on_wire: true
wire_field: commitment_block.committed_rated_mw
wire_at: "SIM/runtime/run_manager.py:470"
units_assumed_by_you: MW
notes: "Σ rated_mw for SYNCHRONISED units only. UNLOADING excluded."

signal: GEN.reserve_floor_mw
status: FOUND
on_tick_result: true
tick_result_field: reserve_floor_mw
on_wire: true
wire_field: commitment_block.reserve_floor_mw
wire_at: "SIM/runtime/run_manager.py:471"
units_assumed_by_you: MW
notes: "p_demand_mw + max(rated_mw of on-bus units). N-1 requirement."

signal: GEN.reserve_satisfied
status: FOUND
on_tick_result: true
tick_result_field: reserve_satisfied
assigned_at: "SIM/core/simulation_core.py:980"
excerpt: "_reserve_satisfied_cs  = not _commit_decision.floor_violated"
on_wire: true
wire_field: commitment_block.reserve_satisfied
wire_at: "SIM/runtime/run_manager.py:472"
units_assumed_by_you: boolean
notes: >
  Point estimate — compares committed_rated_mw against p_demand_mw + largest unit.
  Does NOT evaluate the confidence band upper bound.
  INV-2 (band check, never point estimate) applies to the BESS bridging check,
  not to this N-1 floor check.

signal: GEN.floor_violated
status: NOT_FOUND
notes: >
  floor_violated: bool exists on CommitmentDecision (SIM/core/commitment.py:214).
  It is NOT a TickResult field and NOT emitted on the wire.
  Only its negation (reserve_satisfied = not floor_violated) reaches the wire
  via commitment_block.reserve_satisfied.
  floor_violated is computed at SIM/core/commitment.py:269:
  "floor_violated = total_rated_mw < floor_mw"

signal: GEN.commitment_action
status: FOUND
on_tick_result: true
tick_result_field: commitment_action
on_wire: true
wire_field: commitment_block.action
wire_at: "SIM/runtime/run_manager.py:466"
units_assumed_by_you: string 'commit'|'decommit'|'hold'
notes: ""

signal: GEN.fleet_utilisation
status: FOUND
on_tick_result: true
tick_result_field: fleet_utilisation
on_wire: true
wire_field: commitment_block.utilisation
wire_at: "SIM/runtime/run_manager.py:473"
units_assumed_by_you: fraction
notes: "U = p_demand_mw / committed_rated_mw."
```

### C.11 — Frequency / protection

```yaml
signal: GEN.frequency_hz
status: FOUND
on_tick_result: true
tick_result_field: frequency_hz
on_wire: true
wire_field: frequency_hz
wire_at: "SIM/runtime/run_manager.py:408"
frontend_field: frequency_hz
rendered_at: "gridsignal_logger.py:188"
units_declared: false
units_assumed_by_you: Hz
notes: "Swing-equation output (islanded mode). Nominal = 50 or 60 Hz per site config."

signal: GEN.protection_provisional
status: FOUND
on_tick_result: true
tick_result_field: protection_provisional
on_wire: true
wire_field: protection_provisional
wire_at: "SIM/runtime/run_manager.py:234"
units_assumed_by_you: boolean
notes: "True for all islanded ticks. Gates export HTTP 403."
```

### C.12 — BESS mode

```yaml
signal: GEN.BESS.mode
status: NOT_FOUND
notes: >
  No BESS mode enum exists. BessConfig.grid_forming: bool is the only mode
  distinction (grid-forming vs grid-following). There is no CHARGING/DISCHARGING/
  IDLE/ANCHOR enum or field on TickResult or the wire. bess_anchor_reserve_mw
  is the closest structural proxy for anchor-mode headroom, but it is a scalar,
  not a mode label.
```

### C.13 — Balance decomposition

```yaml
signal: GEN.grid_exchange_mw
status: FOUND
on_tick_result: true
tick_result_field: grid_exchange_mw
on_wire: true
wire_field: grid_exchange_mw
wire_at: "SIM/runtime/run_manager.py:415"
units_assumed_by_you: MW
notes: "PCC flow — exactly 0.0 in islanded mode."

signal: GEN.frequency_forcing_mw
status: FOUND
on_tick_result: true
tick_result_field: frequency_forcing_mw
on_wire: true
wire_field: frequency_forcing_mw
wire_at: "SIM/runtime/run_manager.py:416"
units_assumed_by_you: MW
notes: "Dispatch-plan inertial pressure. 0 in grid-connected mode."

signal: GEN.asset_delivery_error_mw
status: FOUND
on_tick_result: true
tick_result_field: asset_delivery_error_mw
on_wire: true
wire_field: asset_delivery_error_mw
wire_at: "SIM/runtime/run_manager.py:417"
units_assumed_by_you: MW
notes: "Physical shortfall (asset setpoint tracking shortfall). ~0 steady-state."
```

---

## Section D — DEMAND

### D.1 — Forecast MW

```yaml
signal: DEMAND.forecast_mw
status: FOUND
on_tick_result: true
tick_result_field: forecast_mw
on_wire: true
wire_field: forecast_mw
wire_at: "SIM/runtime/run_manager.py:399"
frontend_field: forecast_mw
rendered_at: "FE/subsystem/panels/forecastQuality.ts"
units_declared: false
units_assumed_by_you: MW
notes: "Queue-derived compute forecast (Section 4 formula). Single source of truth (F4 criterion)."
```

### D.2 — Confidence band

```yaml
signal: DEMAND.confidence_lower_mw
status: FOUND
on_tick_result: true
tick_result_field: confidence.lower_bound_mw
on_wire: true
wire_field: confidence_lower_mw
wire_at: "SIM/runtime/run_manager.py:240"
frontend_field: confidence_lower_mw
rendered_at: "FE/subsystem/useSubsystemData.ts:152"
units_declared: false
units_assumed_by_you: MW
notes: "Flattened from ConfidenceBand.lower_bound_mw."

signal: DEMAND.confidence_upper_mw
status: FOUND
on_tick_result: true
tick_result_field: confidence.upper_bound_mw
on_wire: true
wire_field: confidence_upper_mw
wire_at: "SIM/runtime/run_manager.py:241"
frontend_field: confidence_upper_mw
rendered_at: "FE/subsystem/useSubsystemData.ts:152"
units_assumed_by_you: MW
notes: ""
```

### D.3 — Data quality tags

```yaml
signal: DEMAND.data_quality_tags
status: FOUND
on_tick_result: true
tick_result_field: confidence.tags
on_wire: true
wire_field: data_quality_tags
wire_at: "SIM/runtime/run_manager.py:242"
excerpt: '"data_quality_tags": sorted(t.value for t in tick.confidence.tags)'
frontend_field: data_quality_tags
rendered_at: "FE/subsystem/useSubsystemData.ts:151"
units_declared: false
units_assumed_by_you: list[string]
duplicates: []
notes: >
  Sorted list of DataQualityTag enum string values. Members:
  unmapped_hardware | uncalibrated_site | invalid_payload | stale_profile |
  workload_signal_stale | workload_signal_absent
```

### D.4 — Insufficient reserve alert

```yaml
signal: DEMAND.insufficient_reserve_alert
status: FOUND
on_tick_result: true
tick_result_field: insufficient_reserve_alert
on_wire: true
wire_field: insufficient_reserve_alert
wire_at: "SIM/runtime/run_manager.py:243"
frontend_field: insufficient_reserve_alert
rendered_at: "FE/subsystem/useSubsystemData.ts:120"
units_declared: false
units_assumed_by_you: boolean
notes: "True when BESS cannot cover peak_shortfall_mw."
```

### D.5 — Band widening percentage

```yaml
signal: DEMAND.band_widening_pct
status: NOT_FOUND
notes: >
  No band_widening_pct scalar on TickResult or wire. The catalogue holds
  band_mult_uncalibrated (×2.0) and band_mult_unmapped_hw (×1.5) as multipliers,
  and band_pct_calibrated (±4%) as the base band, but their product is not
  exported as a named percentage. The actual band width can be inferred from
  (confidence_upper_mw - confidence_lower_mw) / 2 / forecast_mw, but this
  arithmetic is not labelled or exported.
```

### D.6 — Calibration state

```yaml
signal: DEMAND.calibration_state
status: NOT_FOUND
notes: >
  No calibration_state enum or string field exists. Whether the site is
  uncalibrated is tracked as a bool (SiteConfig.uncalibrated) and surfaced
  only as the 'uncalibrated_site' tag in data_quality_tags. There is no
  structured calibration_state field on TickResult or wire.
```

---

## Section E — RENEW (Renewable Supply)

### E.1 — Renewable output

```yaml
signal: RENEW.p_renewable_mw
status: FOUND
on_tick_result: true
tick_result_field: p_renewable_mw
assigned_at: "SIM/core/simulation_core.py:509"
on_wire: true
wire_field: p_renewable_mw
wire_at: "SIM/runtime/run_manager.py:248"
frontend_field: p_renewable_mw
rendered_at: "FE/subsystem/useSubsystemData.ts:140"
units_declared: false
units_assumed_by_you: MW
notes: "Post-curtailment solar output injected into energy balance."
```

### E.2 — Curtailed MW

```yaml
signal: RENEW.p_renewable_curtailed_mw
status: FOUND
on_tick_result: true
tick_result_field: p_renewable_curtailed_mw
on_wire: true
wire_field: p_renewable_curtailed_mw
wire_at: "SIM/runtime/run_manager.py:252"
units_declared: false
units_assumed_by_you: MW
notes: >
  §INV-CURT: MW curtailed from solar this tick by frequency-response inverter.
  0.0 in grid-connected mode, when thresholds are unset, or when f <= of_warning.
  p_renewable_mw is post-curtailment; this field carries the delta.
```

### E.3 — Expected MW (POA-derived)

```yaml
signal: RENEW.p_expected_mw
status: FOUND
on_tick_result: true
tick_result_field: p_expected_mw
defined_at: "SIM/core/models.py (TickResult)"
assigned_at: "SIM/renewable/solar.py:1121"
excerpt: "p_expected = sum(bank_expected_mw(cfg, st, b) for b in st.blocks)"
on_wire: true
wire_field: p_expected_mw
wire_at: "SIM/runtime/run_manager.py:363"
frontend_field: p_expected_mw
rendered_at: "FE/subsystem/panels/renewable.ts"
frontend_literal: false
units_declared: false
units_assumed_by_you: MW
duplicates: []
notes: >
  Optional[float] — null on run paths that do not go through SolarSim.
  bank_expected_mw formula at SIM/renewable/solar.py:182:
  "measured_poa = st.poa * st.cloud_factor"
  "return max(0.0, min(b.rated_mw * (measured_poa / 1000.0) * temp_derate(cfg, st.module_temp_c), b.rated_mw))"
  Inputs: BankState.rated_mw, PlantState.poa (W/m²), PlantState.cloud_factor, PlantState.module_temp_c, SiteConfig.
```

### E.4 — Banks reporting

```yaml
signal: RENEW.banks_reporting
status: FOUND
on_tick_result: true
tick_result_field: banks_reporting
assigned_at: "SIM/renewable/solar.py:1123"
excerpt: "banks_reporting = sum(1 for b in st.blocks if b.state != 'no_comms')"
on_wire: true
wire_field: banks_reporting
wire_at: "SIM/runtime/run_manager.py:364"
units_declared: false
units_assumed_by_you: count
notes: "Optional[int] — null on non-SolarSim paths. Comment: 20 = all, old model default."
```

### E.5 — Solar weather / conditions

```yaml
signal: RENEW.solar_weather
status: FOUND
on_tick_result: true
tick_result_field: solar_weather
on_wire: true
wire_field: solar_weather
wire_at: "SIM/runtime/run_manager.py:347"
frontend_field: solar_weather
rendered_at: "FE/subsystem/panels/renewable.ts"
units_declared: false
units_assumed_by_you: string e.g. 'clear' | 'overcast'
notes: "Constant per run. Empty string on non-solar paths."

signal: RENEW.solar_conditions
status: FOUND
on_tick_result: true
tick_result_field: solar_conditions
on_wire: true
wire_field: solar_conditions
wire_at: "SIM/runtime/run_manager.py:348"
frontend_field: solar_conditions
rendered_at: "FE/subsystem/panels/renewable.ts"
units_assumed_by_you: string
notes: "Human-readable Mistral conditions label. Constant per run."
```

### E.6 — Sun elevation

```yaml
signal: RENEW.sun_elevation_deg
status: NOT_FOUND
notes: >
  SIM/renewable/solar.py computes no solar elevation, altitude, or zenith angle.
  The module uses POA (plane of array irradiance, W/m²) as a direct state variable
  (PlantState.poa, PlantState.clear_sky_poa) seeded from cfg.poa_seed and evolved
  stochastically. No trigonometric sun-position calculation exists anywhere in the file.
  site_lat and site_lon are on the wire (see G section) but are not consumed by solar.py.
```

### E.7 — Offset applied MW

```yaml
signal: RENEW.offset_applied_mw
status: NOT_FOUND
notes: >
  No offset_applied_mw concept in the codebase. p_renewable_curtailed_mw carries
  the inverter curtailment delta. There is no separate "offset" mechanism.
```

---

## Section F — THERM (Thermal / Cooling)

### F.1-F.4 — Cooling headroom suite

```yaml
signal: THERM.rated_cooling_mw
status: FOUND
on_tick_result: true
tick_result_field: rated_cooling_mw
on_wire: true
wire_field: rated_cooling_mw
wire_at: "SIM/runtime/run_manager.py:293"
frontend_field: rated_cooling_mw
rendered_at: "FE/subsystem/useSubsystemData.ts:109"
units_declared: false
units_assumed_by_you: MW
notes: "Cooling plant nameplate."

signal: THERM.absorbable_mw
status: FOUND
on_tick_result: true
tick_result_field: absorbable_mw
on_wire: true
wire_field: absorbable_mw
wire_at: "SIM/runtime/run_manager.py:294"
frontend_field: absorbable_mw
rendered_at: "FE/subsystem/useSubsystemData.ts:110"
units_assumed_by_you: MW
notes: "rated - current cooling draw. Headroom before approach."

signal: THERM.time_to_limit_s
status: FOUND
on_tick_result: true
tick_result_field: time_to_limit_s
on_wire: true
wire_field: time_to_limit_s
wire_at: "SIM/runtime/run_manager.py:295"
frontend_field: time_to_limit_s
rendered_at: "FE/subsystem/useSubsystemData.ts:188"
units_assumed_by_you: seconds
notes: "Seconds until cooling headroom = 0. 86400 = effectively infinite."

signal: THERM.approach_rate_mw_s
status: FOUND
on_tick_result: true
tick_result_field: approach_rate_mw_s
on_wire: true
wire_field: approach_rate_mw_s
wire_at: "SIM/runtime/run_manager.py:296"
frontend_field: approach_rate_mw_s
rendered_at: "FE/subsystem/useSubsystemData.ts:189"
units_assumed_by_you: MW/s
notes: "Rate of cooling load rise (MW/s)."
```

### F.5 — Compute inlet temperature

```yaml
signal: THERM.compute_inlet_temp_c
status: FOUND
on_tick_result: true
tick_result_field: compute_inlet_temp_c
on_wire: true
wire_field: compute_inlet_temp_c
wire_at: "SIM/runtime/run_manager.py:426"
units_declared: false
units_assumed_by_you: degC
notes: "Inlet air temperature derived from lagged cooling output. Inherits dt_thermal lag."
```

### F.6 — Ambient temperature

```yaml
signal: THERM.ambient_avg_c
status: FOUND
on_tick_result: true
tick_result_field: ambient_avg_c
on_wire: true
wire_field: ambient_avg_c
wire_at: "SIM/runtime/run_manager.py:351"
units_declared: false
units_assumed_by_you: degC
notes: "Constant per run (from forecast ambient steps). 0.0 when solar forecast absent."
```

### F.7 — Ambient alpha scale / alpha max / dt_thermal

```yaml
signal: THERM.ambient_alpha_scale
status: FOUND
on_tick_result: true
tick_result_field: ambient_alpha_scale
on_wire: true
wire_field: ambient_alpha_scale
wire_at: "SIM/runtime/run_manager.py:352"
units_assumed_by_you: dimensionless
notes: "1.0 + 0.015 × (T_amb − 21). Clamped to [0.80, 1.20]."

signal: THERM.alpha_max
status: FOUND
on_tick_result: true
tick_result_field: alpha_max
on_wire: true
wire_field: alpha_max
wire_at: "SIM/runtime/run_manager.py:456"
units_assumed_by_you: dimensionless
notes: >
  BASE value from SiteConfig — NOT pre-multiplied by ambient_alpha_scale.
  A panel must display both to avoid labelling the scaled product as α_max.

signal: THERM.dt_thermal_seconds
status: FOUND
on_tick_result: true
tick_result_field: dt_thermal_seconds
on_wire: true
wire_field: dt_thermal_seconds
wire_at: "SIM/runtime/run_manager.py:455"
units_assumed_by_you: seconds
notes: "Cooling lag time constant (90 s default)."
```

### F.8-F.12 — Absent thermal signals

```yaml
signal: THERM.alpha_measured
status: NOT_FOUND
notes: "No measured α_max exists. Only the CHOSEN value (catalogue key alpha_max = 0.2) is available."

signal: THERM.cooling_lag_observed_s
status: NOT_FOUND
notes: >
  No observed/measured lag is exported. dt_thermal_seconds (on wire) is the configured
  lag constant. There is no field tracking the empirically observed lag.

signal: THERM.cdu_state
status: NOT_FOUND
notes: >
  No CDU (coolant distribution unit) state field exists on TickResult, wire,
  or in any module. CoolingModule at SIM/core/asset_modules.py models cooling
  as a first-order lag without per-unit CDU state.

signal: THERM.loop_state
status: NOT_FOUND
notes: "No loop_state or cooling loop state field exists anywhere in the codebase."

signal: THERM.approach_temp_c
status: NOT_FOUND
notes: >
  No approach_temp_c field exists. compute_inlet_temp_c (on wire) is the inlet
  air temperature. There is no separate 'approach temperature' concept exported.
  The closest proxy is: approach_temp = cooling approach as sensed by the
  absorbable_mw / time_to_limit_s pair, neither of which is a temperature.
```

---

## Section G — RUN (Run / Clock)

### G.1 — Run identity

```yaml
signal: RUN.run_id
status: FOUND
on_tick_result: true
tick_result_field: run_id
on_wire: true
wire_field: run_id
wire_at: "SIM/runtime/run_manager.py:206"
units_assumed_by_you: string UUID
notes: ""

signal: RUN.tick_index
status: FOUND
on_tick_result: true
tick_result_field: tick_index
on_wire: true
wire_field: tick_index
wire_at: "SIM/runtime/run_manager.py:207"
units_assumed_by_you: integer
notes: "0-based. Increments each 5-second tick."

signal: RUN.sim_time_seconds
status: FOUND
on_tick_result: true
tick_result_field: sim_time_seconds
on_wire: true
wire_field: sim_time_seconds
wire_at: "SIM/runtime/run_manager.py:208"
units_assumed_by_you: seconds
notes: "Interval-end timestamp per spec Section 3.1."
```

### G.2 — Site identity / location

```yaml
signal: RUN.site_name
status: FOUND
on_tick_result: true
tick_result_field: site_name
on_wire: true
wire_field: site_name
wire_at: "SIM/runtime/run_manager.py:370"
units_assumed_by_you: string
notes: "Constant per run."

signal: RUN.site_lat
status: FOUND
on_tick_result: true
tick_result_field: site_lat
on_wire: true
wire_field: site_lat
wire_at: "SIM/runtime/run_manager.py:367"
units_assumed_by_you: decimal degrees
notes: ""

signal: RUN.site_lon
status: FOUND
on_tick_result: true
tick_result_field: site_lon
on_wire: true
wire_field: site_lon
wire_at: "SIM/runtime/run_manager.py:368"
units_assumed_by_you: decimal degrees
notes: ""

signal: RUN.site_utc_offset_h
status: FOUND
on_tick_result: true
tick_result_field: site_utc_offset_h
defined_at: "SIM/core/models.py:1092 (SiteConfig); TickResult carries its own float copy"
assigned_at: "SIM/runtime/scenario_factory.py:898"
excerpt: "site_utc_offset_h=float(spec_data.get('site_utc_offset_h',"
on_wire: true
wire_field: site_utc_offset_h
wire_at: "SIM/runtime/run_manager.py:369"
units_declared: false
units_assumed_by_you: hours (UTC offset, e.g. +10.0 for AEST)
duplicates: []
notes: >
  Set from ScenarioSpec.site_utc_offset_h in scenario_factory.py:898 into SiteConfig.
  SiteConfig default at models.py:1092: site_utc_offset_h: float = 0.0.
  SIM/renewable/solar.py does NOT read this field (solar.py uses POA physics, no sun-position geometry).
  No module converts it to a local datetime or timezone string.
```

### G.3 — Island collapse

```yaml
signal: RUN.island_collapsed
status: FOUND
on_tick_result: true
tick_result_field: island_collapsed
on_wire: true
wire_field: island_collapsed
wire_at: "SIM/runtime/run_manager.py:480"
units_assumed_by_you: boolean
notes: "True only on terminal collapse tick."

signal: RUN.collapse_reason
status: FOUND
on_tick_result: true
tick_result_field: collapse_reason
on_wire: true
wire_field: collapse_reason
wire_at: "SIM/runtime/run_manager.py:481"
units_assumed_by_you: Optional[string]
notes: "null unless island_collapsed is True."
```

### G.4 — Absent run signals

```yaml
signal: CLOCK.site_local
status: NOT_FOUND
notes: >
  No local-time datetime or string is computed or exported. site_utc_offset_h
  is on the wire but no module converts it to a local datetime object or string.

signal: CLOCK.site_tz
status: NOT_FOUND
notes: >
  No timezone identifier string (e.g. 'Australia/Sydney') exists. Only the
  numeric UTC offset (site_utc_offset_h, float) is available.

signal: RUN.code_rev
status: NOT_FOUND
notes: "No code revision or git SHA is stamped on TickResult or the wire."

signal: RUN.physics_path
status: NOT_FOUND
notes: "No physics_path or engine variant label is exported."

signal: RUN.scenario_version
status: NOT_FOUND
notes: "No scenario_version field on TickResult or wire."
```

---

## Section H — VERDICT / NET

### H.1 — Per-subsystem TileState

```yaml
signal: VERDICT.compute.state
status: FOUND
on_tick_result: false
on_wire: false
frontend_field: null
rendered_at: "FE/subsystem/useSubsystemData.ts:100"
excerpt: "const computeState: TileState = runningJobs > 0 ? 'ACTIVE' : totalJobs > 0 ? 'ACTIVE' : 'READY'"
frontend_literal: false
notes: "Reads tick.checkpoint_states. Values: 'ACTIVE' | 'READY'."

signal: VERDICT.thermal.state
status: FOUND
rendered_at: "FE/subsystem/useSubsystemData.ts:112"
excerpt: "const thermalState: TileState = fraction < 0.05 ? 'ATTENTION' : 'READY'"
notes: "fraction = absorbable_mw / rated_cooling_mw. Values: 'ATTENTION' | 'READY'."

signal: VERDICT.storage.state
status: FOUND
rendered_at: "FE/subsystem/useSubsystemData.ts:120"
excerpt: "const storageState: TileState = alert ? 'ATTENTION' : bridge_s >= 86400 ? 'READY' : bridge_s > 0 ? 'READY' : 'ATTENTION'"
notes: "Reads insufficient_reserve_alert (alert) and bess_bridging_seconds."

signal: VERDICT.generation.state
status: FOUND
rendered_at: "FE/subsystem/useSubsystemData.ts:134"
excerpt: "const genState: TileState = turbineMW > 0 ? 'ACTIVE' : 'READY'"
notes: "Reads turbine_output_mw."

signal: VERDICT.renewable.state
status: FOUND
rendered_at: "FE/subsystem/useSubsystemData.ts:141"
excerpt: "const renewState: TileState = 'ADVISORY'  // by design — non-dispatchable"
frontend_literal: true
notes: "Always 'ADVISORY'. Hardcoded by design."

signal: VERDICT.grid.state
status: FOUND
rendered_at: "FE/subsystem/useSubsystemData.ts:224"
excerpt: "state:   'ISLANDED',"
frontend_literal: true
notes: "Always 'ISLANDED'. Hardcoded — this plant is islanded by design."

signal: VERDICT.forecast-quality.state
status: FOUND
rendered_at: "FE/subsystem/useSubsystemData.ts:153"
excerpt: "const fqState: TileState = dqTags.length > 0 ? 'ATTENTION' : 'READY'"
notes: "Reads data_quality_tags."

signal: VERDICT.network.state
status: FOUND
rendered_at: "FE/subsystem/useSubsystemData.ts:244"
excerpt: "state:   'READY',"
frontend_literal: true
notes: "Always 'READY'. Hardcoded — static configured network state, no live fabric on tick."

signal: VERDICT.agents.state
status: FOUND
rendered_at: "FE/subsystem/useSubsystemData.ts:254"
excerpt: "state:   'ARMED',"
frontend_literal: true
notes: "Always 'ARMED'. Hardcoded."
```

### H.2 — Per-subsystem verdict strings

All nine verdict strings are built in `FE/subsystem/useSubsystemData.ts`. None has structured backing — all are string literals or template literals computed inline.

| Panel | Reads from tick | Is dynamic? |
|---|---|---|
| Compute | `dt_lead_next_s`, `checkpoint_states` | yes |
| Thermal | `absorbable_mw`, `rated_cooling_mw` | yes |
| Storage | `bess_bridging_seconds`, `insufficient_reserve_alert` | yes |
| Generation | `turbine_output_mw` | yes |
| Renewable | `p_renewable_mw` | yes |
| Grid | — | no (literal) |
| Forecast Quality | `data_quality_tags`, `confidence_upper_mw`, `confidence_lower_mw` | yes |
| Network | — | no (literal) |
| Agents | — | no (literal) |

### H.3 — Alert fields

```yaml
signal: ALERT.insufficient_reserve_alert
status: FOUND
on_tick_result: true
tick_result_field: insufficient_reserve_alert
on_wire: true
wire_field: insufficient_reserve_alert
wire_at: "SIM/runtime/run_manager.py:243"
notes: "Single bool. No structured alert list."

signal: ALERT.active_list
status: NOT_FOUND
notes: >
  No structured list of active alerts exists. insufficient_reserve_alert is the only
  alert scalar on the wire. data_quality_tags provides a list of DQ conditions, but
  these are not the same concept as a general alert list.

signal: ALERT.attention_subsystem_count
status: NOT_FOUND
notes: >
  No scalar count of ATTENTION-state subsystems is computed or exported.
  The count can only be derived client-side from the nine TileState values in
  useSubsystemData.ts.
```

### H.4 — Network fabric signals

```yaml
signal: NET.switches_reporting
status: NOT_FOUND
notes: >
  The network tile verdict '2 switches reporting — one at NTP only' is a hardcoded
  string literal at FE/subsystem/useSubsystemData.ts:167. No switches_reporting
  scalar exists on TickResult or wire. The network tile state is also hardcoded
  as 'READY'. Live fabric metrics are served via GET /network-telemetry (polled
  2 Hz in the detail modal) — not on the tick WebSocket stream.

signal: NET.clock_class
status: NOT_FOUND
notes: "No clock_class field exists on TickResult or wire."

signal: NET.clock_class_degraded_n
status: NOT_FOUND
notes: "Does not exist."
```

### H.5 — Overall readiness verdict

```yaml
signal: VERDICT.overall
status: FOUND
on_tick_result: false
on_wire: false
rendered_at: "FE/readiness/ReadinessBanner.tsx"
excerpt: >
  !tick ? {label:'NO RUN',...} : alert ? {label:'ATTENTION',...} :
  tick.bess_bridging_seconds > 0 ? {label:'ARMED',...} : {label:'READY',...}
frontend_literal: false
notes: >
  Derived inline in ReadinessBanner.tsx from bess_bridging_seconds and
  insufficient_reserve_alert. No stable component ID — addressed by component name only.
  Values: 'NO RUN' | 'ATTENTION' | 'ARMED' | 'READY'.
```

---

## Section I — Invariants

Input availability for each invariant:

| Invariant | Description | Input fields available on wire | Gap |
|---|---|---|---|
| I1 — Power balance | generation - demand ~ 0 | p_generation_mw, p_demand_mw, d4_balance_defect_mw | None |
| I2 — Attribution | turbine + bess + solar = generation | turbine_output_mw, bess_output_mw, p_renewable_mw, p_generation_mw | None |
| I3 — Tri-field | grid_exchange + frequency_forcing + asset_delivery_error = balance | grid_exchange_mw, frequency_forcing_mw, asset_delivery_error_mw, d4_balance_defect_mw | None |
| I4 — Asset rating | unit output ≤ rated_mw | per-unit turbine_units[].output_mw, .rated_mw | None |
| I5 — Storage energy | SoC decreases when discharging | bess_soc_fraction, bess_output_mw | None |
| I6 — N−1 firm capacity | committed_rated_mw ≥ p_demand + largest unit | committed_rated_mw, reserve_floor_mw, reserve_satisfied | None — all three on wire |
| I7 — Solar vs elevation | p_expected_mw ∝ irradiance; elevation not exported | p_expected_mw (on wire), sun_elevation_deg (NOT_FOUND) | sun_elevation_deg absent |
| I8 — Feed health vs last-event age | STALE fires when elapsed ≥ threshold | data_quality_tags (FOUND), elapsed time (NOT_FOUND) | last_event_age_s absent |
| I9 — Clock coherence | site_utc_offset_h consistent | site_utc_offset_h (on wire), site_tz string (NOT_FOUND), site_local datetime (NOT_FOUND) | full coherence check blocked |

---

## Section J — Catalogue Keys (gridsignal_parameters.json)

All keys listable: **yes** (76 keys confirmed across three sections).  
`tick_rate_s`: **NOT_FOUND** as a catalogue key. The actual tick rate is `TICK_INTERVAL_SIM_SECONDS = 5.0` (a Python constant at `SIM/runtime/run_manager.py:606`). The closest catalogue key is `forecast_tick_s = 5` (locked section), which matches it.

### J.1 — Adjustable section (13 keys)

| Key | PARAM-id | Default | Unit | split | Notes |
|---|---|---|---|---|---|
| dt_lead | PARAM-01 | 45 | s | true | Δt_lead — allocation to full TDP |
| dt_thermal | PARAM-02 | 90 | s | true | Δt_thermal — cooling response delay |
| alpha_max | PARAM-03 | 0.2 | dimensionless | true | α_max — steady-state cooling fraction |
| tau | PARAM-04 | 20 | s | true | τ — cooling rise time constant |
| r_asset | PARAM-05 | 0.2 | MW/s | true | Turbine ramp rate per unit |
| pue_base | PARAM-06 | 1.03 | dimensionless | true | PUE_base — non-cooling overhead |
| bess_rated_mw | PARAM-07 | 15.0 | MW | false | BESS rated power |
| soc_pct | PARAM-08 | 100 | % | true | BESS state of charge |
| anchor_reserve_pct | PARAM-09 | 8 | % of rated | false | Grid-forming headroom |
| p_renewable_mw | PARAM-10 | 3.0 | MW | plant_only | Non-dispatchable supply |
| band_pct_calibrated | PARAM-13 | 4 | ±% | false | Confidence band, calibrated site |
| band_mult_uncalibrated | PARAM-14 | 2.0 | × | false | Widening multiplier, uncalibrated |
| band_mult_unmapped_hw | PARAM-15 | 1.5 | × | false | Widening multiplier, unmapped hardware |

### J.2 — Enumerated section (8 keys)

| Key | PARAM-id | Options | Notes |
|---|---|---|---|
| hardware_profile_id | PARAM-20 | options_source: hardware_profile_library | Controls kW-per-node |
| workload_class | PARAM-21 | training \| inference \| other | |
| turbine_count | PARAM-22 | 1 \| 2 \| 3 \| 4 | Integer select |
| grid_mode | PARAM-23 | grid_connected \| islanded | Gates anchor_reserve_pct |
| operating_tier | PARAM-24 | advisory \| supervised \| autonomous | |
| clock_discipline | PARAM-25 | ntp \| ptp \| declared_ptp_actual_ntp | |
| fabric_signal_tier | PARAM-26 | legacy \| current \| emerging | |
| scenario_preset | PARAM-27 | options_source: scenario_library | |

### J.3 — Locked section (55 keys)

| Key | Value | Unit | Notes |
|---|---|---|---|
| checkpoint_drop_pct | 15 | % | CONFORMANCE; TC-06…TC-09 |
| checkpoint_duration_min_s | 5 | s | CONFORMANCE |
| checkpoint_duration_max_s | 30 | s | CONFORMANCE |
| checkpoint_recovery_pct | 90 | % | CONFORMANCE |
| checkpoint_recovery_window_s | 45 | s | CONFORMANCE |
| forecast_tick_s | 5 | s | CONFORMANCE; tick rate |
| reorder_buffer_s | 10 | s | CONFORMANCE |
| bess_taper_window_s | 10 | s | CONFORMANCE |
| nfr2_decision_to_command_s | 2 | s | CONFORMANCE; NFR-2 |
| bess_response_latency_ms | 100 | ms | CONFORMANCE |
| clock_skew_bound_s | 2 | s | CONFORMANCE |
| ambient_cooling_nominal_c | 21.0 | °C | PROPOSED_HERE; ASHRAE 90.4 ref |
| ambient_cooling_scale_per_c | 0.015 | fraction/°C | PROPOSED_HERE; 1.5%/°C |
| p_min_stable_frac | 0.4 | fraction | CHOSEN; MSL = 40% rated |
| t_min_run_s | 1800 | s | CHOSEN; 30 min min run |
| t_min_down_s | 900 | s | CHOSEN; 15 min cooldown |
| p_anchor_reserve_mw_san_diego | 2.0 | MW | CHOSEN; site override |
| cooling_margin | 1.15 | dimensionless | CHOSEN; 15% sizing margin |
| solar_fraction_of_peak | 0.25 | dimensionless | PROPOSED_HERE; 25% of peak IT |
| bess_anchor_reserve_mw | 1.0 | MW | CHOSEN; class default |
| commit_utilisation | 0.8 | dimensionless | CHOSEN; 80% commit trigger |
| decommit_utilisation | 0.5 | dimensionless | CHOSEN; 50% decommit trigger |
| decommit_post_removal_max | 0.7 | dimensionless | CHOSEN |
| commit_confirm_s | 30 | s | CHOSEN; 6 ticks |
| decommit_confirm_s | 300 | s | CHOSEN; 60 ticks |
| inter_start_settle_s | 60 | s | CHOSEN |
| levelled_off_epsilon_mw | 0.05 | MW | CHOSEN; deadband |
| levelled_off_window_s | 10 | s | CHOSEN; confirmation window |
| unload_tail_s | 60 | s | CHOSEN; dwell after levelled_off |
| r_asset_mw_per_s | 0.2 | MW/s | CHOSEN; default ramp rate |
| cold_start_s | 900 | s | CHOSEN; 15 min |
| warm_start_s | 600 | s | CHOSEN; 10 min |
| hot_start_s | 300 | s | CHOSEN; 5 min |
| inertia_constant_s | 4.0 | s | CHOSEN; H constant |
| governor_droop | 0.04 | pu | CHOSEN; 4% droop |
| hot_threshold_s | 3600 | s | CHOSEN; 1 h |
| warm_threshold_s | 14400 | s | CHOSEN; 4 h |
| levelled_off_tol_mw | 0.05 | MW | CHOSEN; PROTO-23 |
| workload_signal_stale_s | 30 | s | CHOSEN; staleness threshold |
| bess_response_tau_s | 0.05 | s | CHOSEN; 50 ms VSM |
| anchor_mode | "vsm" | string | DR-2026-08-08-FREQ |
| vsm_inertia_constant_s | 2.0 | s | PROVISIONAL-UNMEASURED |
| dynamic_step_s | 0.01 | s | DR-2026-08-08-FREQ; 10 ms sub-step |
| fixed_speed_cooling_fraction | 0.30 | dimensionless | PROVISIONAL-UNMEASURED |
| d_motor | 2.5 | pu/pu | PROVISIONAL-UNMEASURED |
| valve_actuation_tc_s | 0.2 | s | PROVISIONAL-UNMEASURED |
| fuel_to_power_tc_s | 1.0 | s | PROVISIONAL-UNMEASURED |
| max_instantaneous_load_step_mw | 2.25 | MW | PROVISIONAL-UNMEASURED |
| ufls_stages | [59.3Hz/15%, 58.9Hz/15%, 58.5Hz/20%] | list | PROVISIONAL-UNMEASURED |
| relay_81u_threshold_hz | 57.5 | Hz | PROVISIONAL-UNMEASURED |
| relay_81u_delay_s | 0.10 | s | PROVISIONAL-UNMEASURED |
| droop_r | 0.04 | pu/pu | CHOSEN; per-unit alias of governor_droop |
| power_factor_turbine | 0.85 | dimensionless | CHOSEN |

**Total counted: 13 adjustable + 8 enumerated + 55 locked = 76 keys.**

---

## Section K — Tile Content

### K.1 — Explainer tile

Content source: `FE/opening/TopologyExplainer.tsx`  
Three plane descriptions (Computation plane, Energy plane, Control plane) and a signal-flow description are **TSX string literals** in the component file. No backing data model. Addressed only by component name — no stable IDs.

### K.2 — ReadinessBanner overall verdict

```
Source: FE/readiness/ReadinessBanner.tsx
Inputs read from tick: bess_bridging_seconds, turbine_output_mw, dt_lead_next_s,
                       data_quality_tags, bridging_basis
Derivation (verbatim):
  !tick ? {label:'NO RUN',...} : alert ? {label:'ATTENTION',...} :
  tick.bess_bridging_seconds > 0 ? {label:'ARMED',...} : {label:'READY',...}
No stable component ID — addressed by component name only.
```

### K.3 — VerdictBand claim

```
Source: FE/opening/VerdictBand.tsx
Tick fields read: dt_lead_next_s, contingency_coverage (state, ride_through_s,
  time_to_close_s, deficit_mw, shed_required_mw, headroom_surviving_mw,
  dispatchable_mw, renewable_mw), sim_time_seconds, data_quality_tags,
  p_demand_mw, p_served_mw, p_unserved_mw, forecast_mw,
  turbine_output_mw, bess_output_mw, p_renewable_mw
Claim string: built inline from contingency_coverage.state — no stable ID.
Running predicate: tick !== null && tick.dt_lead_next_s > 0
```

### K.4 — Nine readiness tiles

| Tile ID | State source | Verdict source |
|---|---|---|
| compute | useSubsystemData.ts computeState | computeVerdict |
| thermal | useSubsystemData.ts thermalState | thermalVerdict |
| storage | useSubsystemData.ts storageState | storageVerdict |
| generation | useSubsystemData.ts genState | genVerdict |
| renewable | useSubsystemData.ts renewState (always 'ADVISORY') | renewVerdict |
| grid | hardcoded 'ISLANDED' | literal string |
| forecast-quality | useSubsystemData.ts fqState | fqVerdict |
| network | hardcoded 'READY' | literal string |
| agents | hardcoded 'ARMED' | literal string |

---

## 9. TickResult Fields Not Emitted by `_tick_result_to_dict()`

Only **one** `TickResult` field is intentionally excluded from the wire:

| Field | Type | Reason for exclusion |
|---|---|---|
| `wall_stamp_utc` | `float` | Explicitly excluded per `SIM/runtime/run_manager.py:278–280`: "wall_stamp_utc is intentionally excluded: the existing test test_websocket_subscriber_receives_tick_payload asserts it must NOT appear in WebSocket payloads (runtime-internal; not part of the wire format)." |

All other `TickResult` fields are emitted (some under alias keys: `p_compute_mw` = `p_compute_demand_mw`; `p_cooling_mw` = `p_cooling_demand_mw`; `p_total_mw` = `p_demand_mw`; `confidence.lower_bound_mw` → `confidence_lower_mw`; `confidence.upper_bound_mw` → `confidence_upper_mw`; `confidence.tags` → `data_quality_tags`; `fabric_modal` → `fabric`; commitment fields → nested in `commitment_block`).

---

## 10. Existing Tolerance / Hysteresis / Confirmation-Window Keys

All keys in `gridsignal_parameters.json` whose meaning is an epsilon, tolerance, deadband, hysteresis band, confirmation window, hold time, debounce, or staleness threshold:

| Key | Section | Value | Unit | Read by | Notes |
|---|---|---|---|---|---|
| levelled_off_epsilon_mw | locked | 0.05 | MW | `SIM/core/commitment.py:88` via `_sp_value("levelled_off_epsilon_mw")` | Deadband: unit is "levelled off" when |output − setpoint| < this value |
| levelled_off_tol_mw | locked | 0.05 | MW | `SIM/core/commitment.py` (stop sequencer) | Absolute output tolerance for UNLOADING MSL detection. Same value as levelled_off_epsilon_mw — different use. |
| levelled_off_window_s | locked | 10 | s | `SIM/core/commitment.py:89` via `_sp_value("levelled_off_window_s")` | Confirmation window: levelled_off condition must be sustained this many seconds |
| commit_confirm_s | locked | 30 | s | `SIM/core/commitment.py:85` via `_sp_value("commit_confirm_s")`; used at `SIM/core/simulation_core.py:171` | Commitment confirmation window (hold time) |
| decommit_confirm_s | locked | 300 | s | `SIM/core/commitment.py:86` via `_sp_value("decommit_confirm_s")`; used at `SIM/core/simulation_core.py:172` | Decommit confirmation window |
| inter_start_settle_s | locked | 60 | s | `SIM/core/commitment.py:87` via `_sp_value("inter_start_settle_s")`; used at `SIM/core/commitment.py:183`: `(sim_time - self.start_commanded_at_s) >= inter_start_settle_s` | Hold time between consecutive unit starts |
| unload_tail_s | locked | 60 | s | `SIM/core/asset_modules.py` (TurbineModule stop sequencer) | Dwell from levelled_off True to breaker open; must exceed levelled_off_window_s |
| workload_signal_stale_s | locked | 30 | s | `SIM/core/models.py:357`: `workload_signal_stale_s: float = _sp.value("workload_signal_stale_s")`; evaluated at `SIM/core/simulation_core.py:1081` | Staleness threshold: WORKLOAD_SIGNAL_STALE fires when elapsed ≥ this |
| bess_taper_window_s | locked | 10 | s | `SIM/core/asset_modules.py` (BessModule) | BESS taper window (debounce-like SOC taper) |
| reorder_buffer_s | locked | 10 | s | `SIM/core/kube_demand.py:84` | Reorder buffer: drain events only after this window has elapsed |
| clock_skew_bound_s | locked | 2 | s | `SIM/runtime/` (clock integrity checks) | Tolerance bound for NTP clock skew |
| bess_response_latency_ms | locked | 100 | ms | `SIM/core/asset_modules.py` (BessModule) | Response latency bound (CONFORMANCE) |
| bess_response_tau_s | locked | 0.05 | s | `SIM/core/asset_modules.py` (BessModule) | First-order response time constant: alpha = 1 − exp(−dt/tau) |
| band_pct_calibrated | adjustable | 4 | ±% | `SIM/core/simulation_core.py` (ConfidenceEngine) | Confidence band half-width for calibrated site (epsilon-like bound) |
| band_mult_uncalibrated | adjustable | 2.0 | × | `SIM/core/simulation_core.py` (ConfidenceEngine) | Band widening multiplier — scales band_pct_calibrated |
| band_mult_unmapped_hw | adjustable | 1.5 | × | `SIM/core/simulation_core.py` (ConfidenceEngine) | Band widening multiplier for unmapped hardware |

---

## 11. Targeted Questions

### Q2 — Turbine display states: mapping from TurbineState to UI strings

**Source:** `FE/subsystem/panels/turbineFleet.ts:344–373`

The mapping is a switch in TSX (conditional expression), not a lookup function:

```typescript
// turbineFleet.ts:344
const liveSt   = u.state ?? (onBus ? 'synchronised' : 'offline')

// Breaker state string (syncStr) — turbineFleet.ts:346
const syncStr  = liveSt === 'starting' ? 'syncing' : onBus ? 'closed' : 'open'

// State label string (stateStr) — turbineFleet.ts:364–373
const stateStr =
  liveSt === 'synchronised'
    ? (isDeg ? 'degraded' : 'online')
    : liveSt === 'unloading'
    ? 'unloading'
    : liveSt === 'ramping' || liveSt === 'at_target'
    ? 'ramping'
    : liveSt === 'starting'
    ? 'starting'
    : isDeg ? 'degraded' : 'available'
```

Full mapping table:

| TurbineState wire value | stateStr (label) | syncStr (breaker) |
|---|---|---|
| `'synchronised'` (not degraded) | `'online'` | `'closed'` |
| `'synchronised'` (degraded) | `'degraded'` | `'closed'` |
| `'unloading'` | `'unloading'` | `'closed'` |
| `'ramping'` | `'ramping'` | `'closed'` |
| `'at_target'` (legacy alias) | `'ramping'` | `'closed'` |
| `'starting'` | `'starting'` | `'syncing'` |
| `'offline'` (not degraded) | `'available'` | `'open'` |
| `'offline'` (degraded) | `'degraded'` | `'open'` |
| `'out_of_service'` (not degraded) | `'available'` | `'open'` |
| `'out_of_service'` (degraded) | `'degraded'` | `'open'` |
| null (fallback, onBus) | `'online'` or `'degraded'` | `'closed'` |
| null (fallback, off-bus) | `'available'` or `'degraded'` | `'open'` |

`isDeg` is computed from per-unit fields (not shown above) and indicates a degraded condition within a state.

The three strings mentioned in the question — `'available'`, `'syncing'`, and `'open'` — appear in:
- `'available'` → `stateStr` for offline/out_of_service non-degraded units
- `'syncing'` → `syncStr` for STARTING units (breaker state, not label)
- `'open'` → `syncStr` for off-bus units (breaker state, not label)

---

### Q3 — `floor_violated`

`floor_violated` is a field on `CommitmentDecision` (`SIM/core/commitment.py:214`):
```python
floor_violated: bool = False   # total_rated < floor_mw this interval
```

It is computed at `SIM/core/commitment.py:269`:
```python
floor_violated = total_rated_mw < floor_mw
```

where `floor_mw = p_demand_mw + largest_mw` (N-1 requirement).

It is used at `SIM/core/simulation_core.py:918` to construct the commitment log entry, and at `SIM/core/simulation_core.py:980`:
```python
_reserve_satisfied_cs  = not _commit_decision.floor_violated
```

**Does it reach the wire?** No. `floor_violated` is never emitted directly. Only its negation, `reserve_satisfied = not floor_violated`, reaches the wire as `commitment_block.reserve_satisfied`. `floor_violated` exists only inside `SIM/core/commitment.py` and `SIM/core/simulation_core.py`.

---

### Q4 — Solar elevation in `renewable/solar.py`

**Does not exist.** `SIM/renewable/solar.py` computes no solar elevation, altitude, or zenith angle internally. The file contains no trigonometric sun-position calculation. POA (`PlantState.poa`, W/m²) is used as a direct physical state variable — seeded from `cfg.poa_seed` and evolved stochastically. There is no `sin_altitude`, `solar_zenith`, `declination`, `hour_angle`, or equivalent symbol anywhere in the 1,224-line file.

---

### Q5 — `p_expected_mw` assignment expression and inputs

Assignment at `SIM/renewable/solar.py:1121`:
```python
p_expected = sum(bank_expected_mw(cfg, st, b) for b in st.blocks)
```

`bank_expected_mw` at `SIM/renewable/solar.py:182–195`:
```python
def bank_expected_mw(cfg: SiteConfig, st: PlantState, b: BankState) -> float:
    measured_poa = st.poa * st.cloud_factor
    return max(0.0, min(
        b.rated_mw * (measured_poa / 1000.0) * temp_derate(cfg, st.module_temp_c),
        b.rated_mw,
    ))
```

Inputs and their origins:

| Input | Source | File:line |
|---|---|---|
| `b.rated_mw` | `BankState.rated_mw` — per-bank rated AC output | `SIM/renewable/solar.py:43` |
| `st.poa` | `PlantState.poa` — plane-of-array irradiance (W/m²) | `SIM/renewable/solar.py:86` |
| `st.cloud_factor` | `PlantState.cloud_factor` — cloud transmission fraction | `SIM/renewable/solar.py:90` |
| `st.module_temp_c` | `PlantState.module_temp_c` — module temperature (°C) | `SIM/renewable/solar.py:88` |
| `cfg` | `SiteConfig` (from `renewable/config.py`) — for `temp_derate()` | `SIM/renewable/solar.py:26` |

The `temp_derate()` function adjusts output for module temperature deviation from STC. `measured_poa / 1000.0` converts W/m² to the normalised irradiance fraction.

---

### Q6 — Time source for solar sun position

`SIM/renewable/solar.py` **does not use any time value to determine sun position.** There is no sun-position geometry in the file.

In standalone (non-run) mode, `PlantState.poa` is seeded from `cfg.poa_seed` and evolved stochastically each tick (`SIM/renewable/solar.py:794`:  
`st.poa = _clamp(st.poa - 0.06 + (rng.random() - 0.5) * 1.6, 300, 1050)`).

In run-sync mode, `receive_mistral_fraction(sim_time, fraction)` is called by the run loop with the current `sim_time` and an irradiance fraction from `ctx.irradiance_profile.fraction_at(sim_time)`. Here `sim_time` is used only to update `self._mistral_fraction_received_at` (for staleness tracking), not for any sun-angle calculation.

**`site_utc_offset_h` is NOT consumed by `solar.py`.** No UTC timestamp, no local timestamp, and no timezone offset is used by the solar physics.

---

### Q7 — `site_utc_offset_h`: source and readers

**Defined on `SiteConfig`:** `SIM/core/models.py:1092`
```python
site_utc_offset_h: float = 0.0
```

**Set from:** `SIM/runtime/scenario_factory.py:898`
```python
site_utc_offset_h=float(spec_data.get("site_utc_offset_h",
```
(remainder of line: falls back to 0.0 when absent from ScenarioSpec JSON.)

**On `TickResult`:** yes — a separate `site_utc_offset_h: float` field is declared on `TickResult` and stamped from `state.site.site_utc_offset_h` in `evaluate_tick()`.

**On wire:** yes — `SIM/runtime/run_manager.py:369`:
```python
"site_utc_offset_h": tick.site_utc_offset_h,
```

**Modules that read it:**
- `SIM/runtime/scenario_factory.py` — reads from ScenarioSpec JSON, writes to SiteConfig
- `SIM/core/simulation_core.py` — stamps on TickResult
- `SIM/runtime/run_manager.py` — emits on wire

**`SIM/renewable/solar.py` does NOT read it** (confirmed by grep returning no hits).

No module converts `site_utc_offset_h` to a local `datetime` object or timezone string.

---

### Q8 — `kube_metrics.active_jobs`: what it counts

**Assignment:** `SIM/core/kube_demand.py:399`
```python
active_jobs = len(self._active_jobs)
```

`self._active_jobs` is a `list[_ActiveJob]` managed by the admission controller (`SIM/core/kube_demand.py:216`). Jobs enter the list when admitted (headroom permits), and are removed at `SIM/core/kube_demand.py:311`:
```python
self._active_jobs = [j for j in self._active_jobs if j.ends_at > sim_time]
```

So `active_jobs` = count of jobs currently admitted and not yet retired (by sim-time expiry).

**Relationship to IT draw:** Each `_ActiveJob` contributes `j.node_count × kw_per_node / 1000` MW to `p_compute_demand_mw`. The IT draw is the sum of all active jobs' node power. `active_jobs` is the count; `admitted_nodes = sum(j.node_count for j in self._active_jobs)` is the power-relevant quantity.

`admitted_nodes` is distinct from `node_count` (= `max(min_nodes, admitted_nodes)`) — the total cluster size including the idle baseline.

---

### Q9 — Workload staleness tags: thresholds and elapsed time

**`WORKLOAD_SIGNAL_STALE` threshold:** catalogue key `workload_signal_stale_s = 30` (locked section).  
Read at `SIM/core/models.py:357`:
```python
workload_signal_stale_s: float = _sp.value("workload_signal_stale_s")
```
Evaluated at `SIM/core/simulation_core.py:1078–1081`:
```python
_workload_signal_stale = (
    bool(state.gpu_modules)
    and state._ever_received_workload_signal
    and (sim_time - state._last_workload_signal_sim_time) >= state.site.workload_signal_stale_s
)
```

**`WORKLOAD_SIGNAL_ABSENT` threshold:** no numeric threshold — fires when no signal has ever been received (`SIM/core/simulation_core.py:1075–1077`):
```python
_workload_signal_absent = (
    bool(state.gpu_modules) and not state._ever_received_workload_signal
)
```

**Elapsed-time value computed?** Yes — `(sim_time - state._last_workload_signal_sim_time)` at `SIM/core/simulation_core.py:1081`. It is computed as an anonymous comparison operand only and is **not stored, not exported, and not on the wire.**

---

### Q10 — `contingency_coverage`: full field list with types

**Source:** `SIM/core/models.py:757–786` (`ContingencyCoverage` dataclass)  
All 15 fields are emitted on the wire (`SIM/runtime/run_manager.py:373–390`):

| Field | Type | Wire key | Notes |
|---|---|---|---|
| `tripped_unit_id` | `Optional[str]` | `tripped_unit_id` | Which unit tripped |
| `deficit_mw` | `float` | `deficit_mw` | Shortfall MW |
| `headroom_surviving_mw` | `float` | `headroom_surviving_mw` | Surviving fleet headroom |
| `r_surviving_mw_per_s` | `float` | `r_surviving_mw_per_s` | Surviving fleet ramp rate |
| `bess_bridging_available_mw` | `float` | `bess_bridging_available_mw` | BESS power available for bridging |
| `bess_usable_energy_mwh` | `float` | `bess_usable_energy_mwh` | BESS energy available |
| `power_test_passes` | `bool` | `power_test_passes` | N−1 power test result |
| `energy_test_passes` | `bool` | `energy_test_passes` | N−1 energy test result |
| `closable` | `bool` | `closable` | Can close within time_to_close_s |
| `time_to_close_s` | `float` | `time_to_close_s` | Capped at 86400 on wire |
| `shed_required_mw` | `float` | `shed_required_mw` | MW of load shed required |
| `ride_through_s` | `float` | `ride_through_s` | Capped at 86400 on wire |
| `state` | `ContingencyState` | `state` | Enum value emitted as `.value` string |
| `dispatchable_mw` | `float` | `dispatchable_mw` | Total dispatchable supply |
| `renewable_mw` | `float` | `renewable_mw` | Renewable contribution |

`contingency_coverage` is `Optional[ContingencyCoverage]` — null on legacy paths.

---

### Q11 — Tick rate

**Literal:** `TICK_INTERVAL_SIM_SECONDS = 5.0`  
**File:line:** `SIM/runtime/run_manager.py:606`  
**Verbatim:** `TICK_INTERVAL_SIM_SECONDS = 5.0  # source spec Section 3.1 evaluation cadence`

**Single value, not per-run.** The same constant is used for all runs.

**Catalogue key:** `forecast_tick_s = 5` (locked section). This matches the literal but uses different naming. `tick_rate_s` as a key: **NOT_FOUND** in the catalogue.

---

### Q12 — Reserve fields: `reserve_satisfied` expression

**Verbatim expression at `SIM/core/simulation_core.py:980`:**
```python
_reserve_satisfied_cs  = not _commit_decision.floor_violated
```

**`floor_violated` verbatim at `SIM/core/commitment.py:269`:**
```python
floor_violated = total_rated_mw < floor_mw
```

where (`SIM/core/commitment.py:265–268`):
```python
on_bus_rated = [u.rated_mw for u in on_bus if not u.hot_standby]
total_rated_mw = sum(on_bus_rated)
largest_mw = max(on_bus_rated, default=0.0)
floor_mw = p_demand_mw + largest_mw
```

`on_bus` = SYNCHRONISED units only. `p_demand_mw` argument to `evaluate_commitment` = `_p_dispatch_droop_mw` (current dispatch requirement, a point estimate).

**Point estimate or confidence band?** Point estimate. `reserve_satisfied` evaluates `total_rated_mw >= p_demand_mw + max_unit`, where `p_demand_mw` is the current tick's demand point, not the confidence band upper bound. `INV-2` ("reserve check evaluates the confidence band, never the point estimate") applies to the BESS bridging check (`bess_bridging_seconds >= peak_shortfall_mw`), not to the N-1 floor check.

The exact field compared: `p_demand_mw` is the turbine-side dispatch requirement (current point estimate of net demand at this tick, `_p_dispatch_droop_mw` in simulation_core.py).

---

### Q13 — `useSubsystemData.ts`: Compute & Workload verdict construction

**Full verbatim code at `FE/subsystem/useSubsystemData.ts:102–106`:**
```typescript
const computeVerdict = tick.dt_lead_next_s > 0
  ? `Ramp in progress — ${tick.dt_lead_next_s.toFixed(0)} s until GPU reaches full TDP.`
  : runningJobs > 0
  ? `${runningJobs} job${runningJobs > 1 ? 's' : ''} at full draw. Cooldown 90 s after finish.`
  : 'No jobs queued. Thermal load at rest.'
```

**What determines the thermal clause:** The literal string `"Cooldown 90 s after finish."` is a hardcoded string. It does **not** read `dt_thermal_seconds` or any thermal field from the tick payload. The "90 s" is a copy of the `dt_thermal` catalogue default embedded as a string literal. If `dt_thermal` changes, this string will not update.

**Does the Compute verdict read any thermal field?** No. The Compute & Workload verdict reads only:
- `tick.dt_lead_next_s`
- `runningJobs` (derived from `tick.checkpoint_states`, line 97-98)

The **Thermal & Cooling** tile is a separate component (verdict at line 113-115) and reads `tick.absorbable_mw` and `tick.rated_cooling_mw`. These are not shared into the Compute verdict.

---

### Q14 — `recommendation` table: writer and lifecycle

**ORM class:** `Recommendation` at `SIM/runtime/persistence.py:366`

**State machine (from `persistence.py:382–420`):**
States: `proposed | under_review | applied | rejected`

DB CHECK constraints:
- `state IN ('proposed', 'under_review', 'applied', 'rejected')` — `ck_recommendation_state`
- `generated_by IN ('model', 'fallback')` — `ck_recommendation_generated_by`
- `NOT (state IN ('applied', 'rejected') AND reviewer_id IS NULL)` — `ck_recommendation_reviewer_required`

The third constraint means: **a recommendation cannot be applied or rejected without a reviewer.** `reviewer_id` must be non-null before a state transition to `applied` or `rejected` is written. This is enforced at the storage layer so it holds even on direct DB writes.

**What writes to the table:** `SIM/runtime/advisory_router.py` is the LLM advisory layer. The explicit INSERT site (`session.add(Recommendation(...))`) was not found by keyword grep in `advisory_router.py` — it may be delegated to a helper or use a write function whose name differs from the patterns searched. The `Recommendation` class at `persistence.py:366` is the only ORM definition. The related `ParameterChangeAudit` table (`persistence.py:436`) records applied changes and requires `reviewer_id IS NOT NULL`.

**Lifecycle summary:**
1. `advisory_router.py` creates a row at `state='proposed'`, `generated_by='model'` or `'fallback'`
2. An operator can move it to `state='under_review'`
3. With `reviewer_id` set, it transitions to `state='applied'` (writes a `ParameterChangeAudit` row) or `state='rejected'`
