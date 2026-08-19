# GridSignal — Updated Functional Specification

**Status:** Current-state functional specification  
**Date:** August 19, 2026  
**Audience:** Senior engineering, product, design partners, and commercial validation teams  
**Purpose:** Describe the implemented GridSignal simulator and its intended product boundary, while identifying the evidence still required to establish customer demand and production readiness.

---

## 1. Executive summary

GridSignal is a workload-aware power operations product for high-density GPU data centers and microgrids. Its active simulator uses synthetic scheduler-shaped workload intent—before a job's modeled electrical load arrives—to predict near-term facility demand, model the response of generation, storage, cooling, grid import, and controllable compute, and present a safe, explainable operating recommendation.

The product thesis is a **seconds-ahead workload-to-megawatt prediction loop**. Instead of responding only to SCADA or meter readings after a power step occurs, the simulator models Kubernetes-, Slurm-, and Ray-shaped workload timelines and uses that modeled lead time to assess reserve, pre-stage resources, and alert an operator to an expected shortfall. Live scheduler connectors remain future work.

The active Python simulator package is a **functional simulator and operator console**, not a production power controller. It runs deterministic physics and scenario workflows, supports configured-user sign-in and administration, persists selected records, streams live ticks to a browser console, and produces gated results and telemetry exports. The nominal workspace API and web artifacts are not release-equivalent to this package. Neither implementation must be represented as a system that autonomously switches real equipment, performs protection actions, or writes commands to production schedulers or power-management systems.

### Product boundary

GridSignal:

- forecasts demand, assesses operational readiness, and models dispatch/advisory outcomes;
- provides what-if scenarios, live simulation telemetry, evidence, and operator-facing explanations;
- may propose actions and simulated setpoints under an authority tier;
- keeps protective action, physical switching, islanding, and real load shedding with the site PMS, protection relays, BMS, and operators.

GridSignal does **not** currently:

- connect to a customer's live Kubernetes, Slurm, Ray, PMS, BMS, SCADA, relay, utility, or market system;
- send a southbound production command;
- provide a certified safety, availability, billing, settlement, or compliance control system;
- establish commercial willingness to pay from simulator usage alone.

---

## 2. Product goals and non-goals

### 2.1 Goals

1. Give an operator early warning of GPU-driven demand steps and their power-system consequence.
2. Translate workload and asset configuration into a consistent site demand forecast, including cooling lag.
3. Model feasible use of BESS, fuel cells, turbines, renewables, grid import, and curtailed or deferred compute.
4. Preserve physical and operating safeguards: ramp limits, minimum stable load, reserve, state of charge, generator state, import limits, and data-quality limits.
5. Make a simulated decision auditable through live telemetry, reasons, run results, scenario configuration, and CSV export.
6. Let prospective customers exercise realistic site archetypes without connecting operational technology.

### 2.2 Non-goals

1. Replace an EMS/PMS, protection relay, BMS, generator controller, utility interconnection controller, or scheduler.
2. Guarantee customer uptime, interconnection approval, tariff savings, or capacity deferral.
3. Make autonomous real-world switching decisions.
4. Treat illustrative cost cards, hardware profiles, synthetic weather, or seeded workloads as customer-site measurements.
5. Infer missing physical telemetry without exposing uncertainty.

---

## 3. Users, roles, and primary jobs

| Actor | Current permissions and purpose | Primary job to be done |
|---|---|---|
| Viewer | Can sign in and observe the console. | Understand current/last simulated readiness and risk. |
| Operator | Uses the run console and scenario workflow. | Test a workload or asset event before it becomes a site incident. |
| Approver | Role and simulator recommendation accept/reject bookkeeping are supported; this is not a physical approval/control workflow. | Review a recommendation and its evidence before an out-of-band operational change. |
| Administrator | Manages user accounts, roles, account activation, password reset, and email diagnostics. | Maintain access and validate sign-in delivery. |
| Scenario author / solutions engineer | Creates, edits, executes, and exports scenarios. | Build a customer-specific digital-twin demonstration or validation case. |
| External integrator (future) | No production connector is currently shipped. | Supply scheduler, asset, PMS, weather, tariff, and telemetry data through governed interfaces. |

Role enforcement is implemented for administration. Approval and physical execution remain a product boundary: the simulator can model authority tiers and record recommendations, but it does not command a real plant.

---

## 4. End-to-end operator workflows

### 4.1 Authenticate and enter the console

1. A configured user enters an email address.
2. The service issues a time-limited, rate-limited one-time code through configured email delivery.
3. The user submits the code; the service creates an authenticated session cookie.
4. The application calls `/api/auth/me` to obtain identity and role.
5. The user may sign out; authenticated users can set or change a password where their account permits it.

Administrators can create, activate, deactivate, delete, and reset users. They can also check and send a diagnostic test email. A break-glass bootstrap path requires an administrator secret and is an operational recovery mechanism, not a normal user flow.

### 4.2 Select, configure, and run a scenario

1. The user selects a seeded scenario or a scenario created during the current service lifetime.
2. The user chooses a playback speed (1×, 5×, 10×, 30×, or maximum) and a duration.
3. Optional run-time overrides may configure BESS behavior or a GPU demand generator.
4. GridSignal validates and materializes the run configuration, including seeded workload, solar, stressor, and telemetry-corruption inputs where configured.
5. The service starts a single managed run and returns a run identifier and applicable BESS operating bounds.
6. The user can pause, resume, or stop an active run. A completed run retains verdict information; detailed replay availability is limited by the persistence model described below.

### 4.3 Monitor a live run

During a run, the browser subscribes to `WS /ws/{run_id}` and receives a tick at a five-simulated-second cadence. The console drains incoming tick data independently of the simulator cadence to keep the UI responsive.

The opening screen and detail pages surface:

- demand, generation, renewable output, grid exchange, served and unserved power;
- BESS output, setpoint, state of charge, bridging availability, and reserve constraints;
- turbine state, output, setpoint, ramp, commitment reason, and controlled unload/settling state;
- fuel-cell contribution, thermal/cooling load, PUE-related values, and pre-staging;
- forecast, confidence, model error, reserve/contingency coverage, and balance defect;
- GPU/cluster state, job queue indicators, capacity and utilization;
- fabric/network state, telemetry quality, and scenario-specific stressors;
- economic dispatch and procurement values when those features are configured;
- warnings, explanations, data-quality tags, and authority/protection status.

### 4.4 Review results and export evidence

After completion, the user can review:

- scenario verdict and assertion outcomes;
- ordered time series with gap markers;
- a scrubbed playback view and tick-level detail;
- energy/cost summaries where enabled;
- data-gap warnings and run outcome context.

The console can generate and download a CSV telemetry log through an asynchronous export job only when its export safety gates pass. In particular, provisional frequency-protection runs are not exportable. Verdict/results may remain available from persisted records; detailed replay and tick-based export require accessible retained tick rows. Export jobs and generated files are process-local and can disappear on restart.

### 4.5 Create and manage scenarios

The scenario manager supports list, detail, create, update, and delete workflows during the current service lifetime. It executes a selected scenario by calling `POST /runs` with `scenario_id`; there is no separate scenario-execute endpoint. The active scenario store is in memory: authored changes are lost on restart and built-in scenarios are re-seeded. The scenario builder exposes validated configuration for assets, synthetic workload behavior, grid connection, GPU load profiles, BESS settings, and related scenario fields.

Scenario schema supports, as applicable:

- BESS, fuel-cell, turbine, and renewable assets;
- site and location information;
- islanded or grid-connected operation and import cap;
- thermal/PUE configuration;
- scripted workload, solar, trip, and job-end events;
- multi-cluster Kubernetes/Slurm/Ray-style workload generation;
- weather, ambient, stressor, maintenance, procurement, and telemetry-corruption inputs;
- assertions used to determine a run verdict.

### 4.6 Configure and inspect supporting domains

The authenticated console provides dedicated views for:

- **Readiness / overview:** current operational posture, forecast, supply, and reserve.
- **Proposals & learning:** recommendation history and enable/disable state for advisory agents.
- **Grid & procurement:** grid capacity, import/export concepts, economic profiles, tariffs, and run cost.
- **Network telemetry:** fabric state, queue/load indicators, gaps, and quality context.
- **Thermal & cooling:** cooling demand, thermal storage/pre-staging, and relevant asset conditions.
- **Scenario planner:** what-if analysis and scenario-oriented run history.
- **Renewable supply console:** a separate solar-oriented view.

No-data and idle states are expected before a run has produced the corresponding telemetry; the UI must show absence of data rather than invent values.

---

## 5. Functional requirements

### FR-1 — Identity, access, and administration

1. The system shall support email one-time-code sign-in, logout, session inspection, rate limiting, and expiration.
2. The system shall maintain active/inactive account state and at least viewer, operator, approver, and administrator roles for configured accounts.
3. The system shall restrict administrative user-management functions to an authenticated administrator or the configured break-glass secret.
4. The system shall log only safe operational details and avoid emitting credentials or session material.
5. The production implementation must add a documented tenant-isolation and authorization model before handling customer data.

### FR-2 — Scenario definition and validation

1. The system shall hold seeded and user-managed scenarios as validated JSON specifications in the active process.
2. The system shall reject invalid asset topology, invalid duration, invalid load profile, impossible BESS/turbine fields, and unsupported combinations.
3. The system shall preserve scenario identity, configuration, selected location, and run association for the active process; durable scenario CRUD is a production requirement, not a current capability.
4. The system shall treat engine-generated fields as runtime output rather than user-authoritative input.
5. The system shall make synthetic/demo scenarios visibly distinct from customer-calibrated scenarios.

### FR-3 — Run lifecycle and replay

1. The system shall start only through the managed run orchestrator; API handlers must not run physics directly.
2. The system shall expose active run discovery, status, pause, resume, cancellation, latest tick, result, and time-series retrieval.
3. Pause shall freeze simulation time and timers between ticks; cancel shall discard the active execution state.
4. Runs shall use a deterministic five-simulated-second physics cadence; playback speed changes wall-clock pacing, not the underlying equations.
5. A completed verdict shall be persisted where storage is configured. Full tick replay must be labeled unavailable after restart when only a verdict remains.

### FR-4 — Workload-to-megawatt forecast

1. The system shall model workload events and synthetic multi-tenant, scheduler-shaped cluster timelines into compute load.
2. The system shall support hardware-profile-based demand mapping and explicitly surface unknown/unmapped hardware conditions.
3. The system shall model cooling as a delayed demand response rather than assuming all facility overhead arrives simultaneously.
4. The system shall represent checkpointing, job timing, arrival variability, capacity limits, modeled scheduler labels, and clock uncertainty where a scenario configures them. It shall not claim a live Kubernetes, Slurm, or Ray connector until one is delivered and validated.
5. The system shall produce forecast, confidence, error, and provenance/quality fields needed to explain the output.

### FR-5 — Physical asset, dispatch, and reserve model

1. The system shall model BESS power/energy limits, SoC, normal versus emergency dispatch depth, grid-forming anchor reserve, charge/discharge acceptance, and bridging time.
2. The system shall model fuel-cell enablement, stack count, rated capacity, and dispatch contribution. It shall model turbine availability, output, ramp rate, thermal state, start delay, minimum stable load, minimum run/down time, controlled unload, and breaker settling.
3. The system shall model renewable supply as non-dispatchable and exclude it from dispatchable ramp capability.
4. The system shall model grid import caps and preserve any remaining deficit as visible unserved demand or frequency/balance forcing, rather than silently filling it.
5. The system shall evaluate dispatch/commitment using residual site demand and only count assets with upward reserve capability toward contingency reserve.
6. When demand falls, the system shall charge BESS before running down surplus thermal generation. It shall initiate rundown only when physical BESS charge acceptance cannot absorb the surplus and all reserve, minimum-run, sequential-stop, and settling safeguards permit it.

### FR-6 — Forecast-based readiness and safety behavior

1. The system shall calculate expected demand, renewable contribution, dispatch requirement, ramp capability, reserve condition, and shortfall.
2. The system shall expose an insufficient-reserve alert rather than conceal a forecast or physical shortfall.
3. The system shall preserve a separation between deterministic control-plane calculations and advisory/learning behavior.
4. The system shall mark islanded protection behavior as provisional where it is a simulator model rather than certified protective equipment.
5. The system shall not issue a production protection, scheduler, BESS, turbine, or grid command.

### FR-7 — Data quality and telemetry integrity

1. The system shall include tick timestamps, sequence/order information, data-quality tags, confidence/error context, and dropped/gap indicators.
2. The system shall support scenario-driven telemetry corruption and apply it to emitted observations, not the underlying physics.
3. The UI shall show quality limitations and avoid presenting degraded telemetry as a precise operational measurement.
4. WebSocket consumers shall treat the feed as push-only; a late subscriber is not guaranteed prior ticks.

### FR-8 — Advisory, economic, and demand-side features

1. The system shall model advisory agents as recommendation sources with visible enable/disable state and evidence.
2. The deterministic runtime shall continue if optional LLM-backed advisory services are unavailable.
3. Where configured, the system shall model economic dispatch, tenant budget gates, procurement, duration-scaled cost, and scenario cost outcomes.
4. The system shall expose planned compute curtailment/defer behavior as advisory/simulation behavior; live scheduler write-back is not shipped.
5. Cost outputs shall identify whether their underlying rate card or marginal-cost assumptions are illustrative.

---

## 6. Architecture and interfaces

### 6.1 Runtime architecture

The deployed simulator consists of:

1. **React/TypeScript SPA** — operator console, scenario builder, administrator UI, run controls, results, and charts.
2. **FastAPI application** — serves REST endpoints, WebSocket stream, and the built frontend from one process/port.
3. **RunManager and WebSocketHub** — process-lifetime orchestration for active runs, stream fan-out, latest tick cache, and completion handling.
4. **Deterministic simulation core** — synchronous tick evaluation, workload, assets, dispatch, balance, swing/frequency, protection approximation, thermal, and result generation.
5. **Async pre-run generators** — scenario materialization for weather/solar, cluster workload, stressors, parameter sampling, and corruption schedules.
6. **Persistence layer** — SQLAlchemy-backed PostgreSQL when configured, otherwise SQLite development storage.
7. **Optional advisory layer** — deterministic fallback is required when external AI services are absent.

### 6.2 Primary API surface

| Interface | Purpose |
|---|---|
| `POST /runs` | Start a scenario or supported direct run with playback and optional overrides. |
| `GET /runs` and `GET /runs/{id}` | Discover active runs and retrieve current status. |
| `POST /runs/{id}/pause`, `POST /runs/{id}/resume`, `DELETE /runs/{id}` | Run control. |
| `GET /runs/{id}/latest-tick` | REST polling fallback for the current or final tick. |
| `GET /runs/{id}/result`, `GET /runs/{id}/timeseries` | Completed run verdict and replay data. |
| `WS /ws/{run_id}` | Live tick stream. |
| `/scenarios` and `/scenarios/{id}` | Process-local scenario CRUD and detail; execute a scenario through `POST /runs` with `scenario_id`. |
| `/api/auth/*`, `/api/admin/*` | Sign-in/session and administrator functions. |
| `/api/agents/*`, `/api/export/*`, `/api/solar/*`, `/api/location/*`, `/api/ai/*` | Supporting advisory, export, renewable, site, and explanation functions. |

The emitted tick is the principal integration contract. Adding a tick field requires coordinated backend serialization and frontend type updates. The specification should be tested as a contract, not inferred from individual widgets.

### 6.3 Important deployment discrepancy

The working product implementation currently resides in the Python simulator package under `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim` and its paired React frontend. The nominal workspace Express API, generated OpenAPI contract, Drizzle schema, and simple web artifact are substantially behind that implementation and expose only a health-check-level surface.

**Release requirement:** before a production release, establish one source of truth for code, API contract, schema/migrations, build pipeline, tests, and deployment artifact. Senior engineering should treat this as a release-blocking packaging/governance issue.

---

## 7. Data, persistence, and audit behavior

The product data model includes site configuration, asset configuration, scenarios, run results, timeseries records, economic profiles/rates, control events, recommendations, user/OTP records, parameter audit data, command acknowledgements, and runtime error records.

Current persistence expectations:

- completed run verdicts can be retained across a process restart;
- scenario CRUD uses a process-local in-memory store; user-created or edited scenarios are lost on restart and seeded scenarios are restored;
- active runs, WebSocket subscribers, latest ticks, and detailed tick replay are process-local;
- export job state and generated files are process-local;
- a restart may therefore retain a verdict but make the detailed historical time series unavailable;
- scenario results and control/audit records require production retention, backup, encryption, ownership, and deletion policies before use with customer data;
- simulation replay is deterministic only when the relevant seeds, site/catalogue/configuration, and materialized event schedule are held constant.

---

## 8. Safety, security, and operational constraints

1. GridSignal is advisory/simulation software. It must never be marketed or deployed as a substitute for protection or real-time PMS control without a separately engineered, certified integration program.
2. Protective load shedding, breaker action, islanding/reconnection, and device interlocks remain external system responsibilities.
3. Any future southbound integration requires explicit command authority, acknowledgement, timeout, idempotency, audit, rollback/fallback, operator approval, and protective interlock requirements.
4. Any customer deployment requires tenant-scoped authorization, least-privilege service identities, secure secrets management, rate limiting, audit retention, and a documented incident/recovery model.
5. The application should withstand absent optional AI services and continue deterministic simulation/advisory fallback behavior.
6. The service must declare when telemetry, hardware profile, calibration, configuration, or time synchronization quality limits a result.

---

## 9. Acceptance evidence and quality bar

The simulator has a broad automated test base spanning API/auth/bootstrap, scenario lifecycle, persistence, formulas, power balance, frequency/protection approximation, commitment and turbine sequencing, BESS behavior, solar/weather, workload generation, Kubernetes capacity, fabric modeling, corruption, payload guards, and UI panel smoke tests.

The release quality bar for a customer pilot should additionally require:

1. Contract tests for every externally supported REST and WebSocket payload.
2. Scenario validation tests for every customer demo profile and configuration override.
3. Deterministic replay evidence for each supplied seed/configuration.
4. Failure-injection tests for missing/stale telemetry, WebSocket loss, API restart, email failure, optional advisory outage, and invalid scenario input.
5. Security assessment for authentication, administration, scenario ownership, export authorization, audit trails, and secrets.
6. Controlled site-data comparison showing forecast error, lead time, and operating outcome against actual measurements.

---

## 10. Current product gaps and explicit open decisions

| Area | Current status | Required decision or work |
|---|---|---|
| Live customer integrations | Not shipped. Workload, asset, PMS, and grid data are simulated/materialized. | Define connector priorities, read-only first pilot scope, protocol/security model, and data ownership. |
| Physical control | Out of scope for the current app. | Retain advisory boundary; require a distinct safety case before any command path. |
| Customer-specific calibration | Scenario calibration and hardware profiles are illustrative unless validated. | Establish a site-onboarding/calibration process with measurement provenance. |
| Commercial economics | Cost cards and some marginal-cost inputs are modeled, not billing-grade. | Decide whether economic dispatch is a core product capability or an integration to a customer optimizer/PMS. |
| Tenant governance | Multi-tenant scenarios exist; complete production tenant isolation and unconfigured-tenant handling are not established. | Define contractual capacity, fairness, ownership, and enforcement policy. |
| Durable scenario and replay history | Verdict persistence exists, but scenario CRUD, export jobs, and full tick history are process-local and can be lost on restart. | Define durable scenario ownership, time-series storage, retention, replay, and export policy. |
| Workspace/release packaging | Active simulator and nominal artifacts are not aligned. | Consolidate source, API specification, migration ownership, build/release, and deployment verification. |
| Demand evidence | Product problem and simulator demos are credible hypotheses, not commercial validation. | Run structured discovery and paid/committed design-partner pilots. |

---

## 11. Customer-demand assessment plan

### 11.1 Core hypotheses

| Hypothesis | Why it may matter | Evidence today | Evidence required |
|---|---|---|---|
| GPU workload intent provides economically useful lead time over reactive telemetry. | It may reduce reserve, BESS sizing, curtailment, or outage risk. | Strong technical rationale and simulator demonstrations. | Compare scheduler-event lead time, forecast error, and avoided shortfall against meter-only baseline at a real site. |
| Operators will pay for a workload-aware readiness layer. | It creates value only if it changes decisions or reduces risk/cost. | Problem narrative and scenario specificity; no willingness-to-pay proof. | Interviews, budget-owner validation, pilot LOIs, paid proof-of-value, and renewal/expansion signals. |
| Scheduler/PMS integration is feasible without unacceptable operational risk. | The product depends on high-quality intent data and trusted operating boundaries. | Simulated Kubernetes, Slurm, and Ray models; advisory boundary is clear. | Read-only connector pilot, security review, timestamp/coverage analysis, and operations-team acceptance. |
| Adaptive forecasting is better than a static scheduler ramp limit. | Static ramp policy is a cheaper alternative. | Product specification identifies the comparison; throughput tax is not measured. | Quantify utilization/throughput impact, reserve reduction, false positive/negative rates, and operator action quality. |
| A scenario/digital-twin workflow accelerates customer adoption. | It provides a low-risk first engagement before OT integration. | Rich scenario builder, results, replay, and export exist. | Measure demo-to-pilot conversion, time to model a site, scenario reuse, and stakeholder signoff. |

### 11.2 Target customer profiles

1. GPU colocation operators operating mixed Kubernetes, Slurm, and Ray estates.
2. AI data-center owners with constrained interconnection, on-site generation, BESS, fuel cells, or a microgrid.
3. Operators planning high-density GPU expansions who need capacity/readiness studies before equipment is installed.
4. Power-management, microgrid, BMS, and scheduler vendors seeking a workload-intent integration layer rather than a competing controller.

### 11.3 Pilot entry point

The recommended first customer deployment is **read-only and advisory**:

1. Ingest one scheduler/event stream and one set of site telemetry feeds.
2. Calibrate a limited hardware profile set against measured demand.
3. Run GridSignal in shadow mode alongside the customer’s existing PMS.
4. Measure forecast lead time, error, predicted versus actual reserve risk, and operator usefulness.
5. Use the scenario planner to compare actual incidents or planned GPU ramp events.
6. Do not send live dispatch, load-shed, or scheduler commands during the first pilot.

### 11.4 Success metrics

For a design partner, measure:

- coverage of scheduler events and asset telemetry;
- median and tail lead time between workload allocation and power change;
- forecast MAE/bias by hardware profile and workload class;
- reserve-alert precision/recall against post-run outcomes;
- avoided or better-timed operator interventions;
- BESS energy/reserve impact relative to reactive or static-ramp baseline;
- change in job delay/throughput under any proposed ramp policy;
- time required to model a new site;
- operator trust: explanation clarity, false-alert tolerance, and adoption in runbooks;
- commercial outcome: signed pilot, paid expansion, deployment commitment, or clearly documented rejection reason.

---

## 12. Senior-engineering review questions

1. Is the workload-to-megawatt forecast sufficiently differentiated from a static scheduler rate limit to justify a standalone product?
2. Which read-only integrations are essential to prove the product within 90 days?
3. What exact reliability, security, retention, and deployment requirements are necessary for a shadow-mode pilot?
4. What is the authoritative production data contract for scheduler intent, SCADA/BMS/PMS state, grid availability, and configuration provenance?
5. Which safety and authorization controls must be proven before recommendation approval is introduced, and which remain permanently external?
6. Should economic dispatch be owned by GridSignal, limited to explanatory modeling, or delegated to the existing PMS/optimizer?
7. What customer outcome is valuable enough to support a paid pilot: avoided capital, lower curtailment, lower BESS cycling, more usable capacity, fewer incidents, or faster interconnection planning?
8. What packaging and contract consolidation plan will make the deployed simulator, source repository, API specification, and test suite release-consistent?

---

## Appendix A — Representative implemented scenario

`scenario-equinix-sj-1` is a grid-tied San Jose GPU-colocation simulation:

- 16,712 modeled GPUs across Kubernetes/H100, Slurm/H100, and Ray/GB200 environments;
- 21.9 MW modeled IT capacity and approximately 30 MW PUE-inclusive facility demand;
- 30 MW / 60 MWh BESS, 24 MW fuel-cell array, and 5 MW grid-import cap;
- no modeled solar or turbine fleet;
- 120% GPU demand for the first ten simulated minutes, followed by defined lower-load phases;
- a controlled validation burst designed to exercise fuel-cell-to-grid handoff.

It is a high-quality demonstration and regression scenario. Its PUE, workload, capacity, and event figures must be labeled as model inputs and validation stimuli—not customer-site measurements—unless a customer verifies them.

---

## Appendix B — Source basis

This specification was assembled from the active simulator implementation, its React console, scenario/configuration files, automated tests, current workflow behavior, and existing GridSignal product/forecast documentation. Key implementation sources include:

- `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/`
- `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/`
- `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/`
- `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/`
- `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/`
- `GridSignal-Forecast-Engine-Functional-Spec_v2.5_1785353484165.md`
- `scenario-equinix-sj-1_customer_summary.md`

Where product documentation, demo narratives, and active code differ, this document treats active simulator behavior as the current implementation and labels unverified commercial/production capabilities explicitly.