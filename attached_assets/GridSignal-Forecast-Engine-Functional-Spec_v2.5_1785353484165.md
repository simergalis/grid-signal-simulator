# GridSignal

**Forecast Engine — Functional Specification**

*Workload-to-Megawatt Translation Layer*

| **Field** | **Value** |
|---|---|
| Document status | Draft v2.5 — adds Section 23.7 (scheduler-side ramp limiting as the baseline alternative to prediction, and GridSignal's adaptive relaxation of it), records secular compression of Δt_lead as a residual dependency, and restates the market-gap finding as absence of evidence |
| Date | July 20, 2026 (rev. July 29, 2026) |
| Parent document | Product Specification: GridSignal, Draft v0.1 |
| Traceability | Elaborates FR-1.1 – FR-1.6 (Forecast Engine) and NFR-2 (Latency) of the parent product spec |
| Audience | Engineering (forecast engine, connector fabric, dispatch advisor), QA/Test, Product |
| Owner | Forecast Engine workstream |

## Document Revision History

| **Version** | **Date** | **Change summary** |
|---|---|---|
| v2.5 | July 29, 2026 | Adds Section 23.7, which states the cheapest alternative to this product — a static scheduler-side ramp policy — recommends it as a baseline, and specifies GridSignal's adaptive relaxation of it as the differentiated capability. Adds acceptance tests TC-75 and TC-76 and residual item CL-5 (the throughput tax is unmeasured). Records secular compression of Δt_lead as a Section 15 residual dependency. Restates the Executive Summary market-gap claim in the absence-of-evidence terms already used in Section 28.8 (PX-5). Arising from an adversarial review of the product thesis, July 29, 2026. |
| v2.4 | July 29, 2026 | Adds an Executive Summary for readers who are not power engineers: problem statement, solution, architecture, scope boundaries, and an explicit account of which parts are specified versus which constants remain unvalidated. Editorial only — no change to specified behavior, thresholds, or acceptance criteria. |
| v2.3 | July 29, 2026 | Expands Section 25: hardware-plane signal classes with capability tiers (25.3), export-plane subscription model preferring event notification over polling (25.4), and explicit limits on what fabric telemetry may contribute to calibration (25.6). Replaces the single ±2 s clock requirement in Section 11.4 with per-source clock classes, since a PTP-disciplined source and a job scheduler differ by nine orders of magnitude in timestamp accuracy. Formalizes NetworkTelemetry as a second ingest event class in Section 10, dispatch-path-ineligible by contract rather than by convention. Adds TC-69–TC-74 and residual item NT-4. |
| v2.2 | July 29, 2026 | Adds Section 28 (physical execution layer and PMS integration), placing GridSignal explicitly in the control stack above a real-time power management system and below day-ahead economic optimization. Two corrections to existing behavior: Section 7.1.2 constrains BESS bridging capability when the battery serves as grid-forming anchor, and Section 28.4 establishes an interlock against the sub-100 ms protective load-shedding layer that Section 23 curtailment would otherwise double-count. Adds P_anchor_reserve to Section 3, TC-61–TC-68, and residual items PX-1–PX-5. Renumbers the glossary to Section 29. |
| v2.1 | July 29, 2026 | Regenerates the Section 5 hardware profile library by hardware generation and adds counting-unit declaration (5.2) and profile vintage (5.3), closing a silent 2× forecast error and a 60–90 kW/cabinet staleness error. Revises Tier B curtailment yield for synchronized workloads (23.2). Adds pre-cooling and the shiftable load class (8.1) and liquid-cooling recalibration (8.2). Adds console Page 5 (Thermal & Cooling) and the Thermal agent. Adds Section 27 (prescriptive maintenance and asset availability). Adds TC-53–TC-60 and residual items PM-1–PM-5. Renumbers the glossary to Section 28. |
| v2.0 | July 29, 2026 | Restructures Section 19 into a multi-page operator console. Adds Section 23 (controllable load and compute curtailment), Section 24 (grid procurement and reserved capacity), Section 25 (network telemetry ingestion), and Section 26 (agentic control architecture). Adds P_curtailable(t), P_grid_firm, and P_grid_reserved(t) to Section 3 and two rows to Section 7.1. Adds acceptance tests TC-41–TC-52 and residual items CL-1–CL-4, GP-1–GP-4, NT-1–NT-3, AG-1–AG-4. Renumbers the glossary from Section 23 to Section 27. This is the first version in which GridSignal may act on the demand side, not only the supply side — see Section 23.1. |
| v1.9 | July 29, 2026 | Adds this revision history, a table of contents, and the glossary (then Section 23, now Section 27). Editorial only — no change to specified behavior, thresholds, or acceptance criteria. |
| v1.8 | July 29, 2026 | Adds Section 22 (persistence and storage architecture: storage tiers, restart reconstruction, object-storage batching and residency, rejected patterns) and acceptance tests TC-34–TC-40. Closes the Section 15 in-flight-state-on-restart residual item and updates the stale Section 17.1 cross-reference. Adds residual items ST-1–ST-4. |
| v1.7 | July 29, 2026 | Adds Section 21 (AI/ML model strategy, learning plane separation, model role assignment, data-residency boundary, learning promotion gate) and Section 7.1.1 (non-dispatchable renewable supply, net dispatch requirement). Adds P_renewable(t) to Section 3 and a solar row to Section 7.1. Adds acceptance tests TC-28–TC-33 and residual items LP-1–LP-5. |
| v1.6 | July 20, 2026 | Adds page footer (Confidential / Page x of y / date). |
| v1.0 – v1.5 | July 20, 2026 | Initial specification and review-cycle revisions. Supersedes the informal "Secret Sauce" engineering note of the same date, resolving the 13 items logged in Section 14. Individual entries predate this table; see Section 14 for the resolution history. |

## Table of Contents

- [Document Revision History](#document-revision-history)
- [Executive Summary](#executive-summary)
  - [ES.1 The problem: a load that electrical systems were not built for](#es1-the-problem-a-load-that-electrical-systems-were-not-built-for)
  - [ES.2 The insight: the computer knows before the electricity does](#es2-the-insight-the-computer-knows-before-the-electricity-does)
  - [ES.3 The proposed solution, in plain terms](#es3-the-proposed-solution-in-plain-terms)
  - [ES.4 What GridSignal deliberately does not do](#es4-what-gridsignal-deliberately-does-not-do)
  - [ES.5 The architecture, in ordinary language](#es5-the-architecture-in-ordinary-language)
  - [ES.6 Where GridSignal fits among the systems already there](#es6-where-gridsignal-fits-among-the-systems-already-there)
  - [ES.7 What is specified, and what is not yet known](#es7-what-is-specified-and-what-is-not-yet-known)
- [1. Purpose and Scope](#1-purpose-and-scope)
- [2. Secret Sauce: Intellectual Property Summary](#2-secret-sauce-intellectual-property-summary)
- [3. System Model and Definitions](#3-system-model-and-definitions)
  - [3.1 Evaluation cadence](#31-evaluation-cadence)
- [4. The Workload-to-Megawatt Formula (Resolved)](#4-the-workload-to-megawatt-formula-resolved)
  - [4.1 Instantaneous compute term](#41-instantaneous-compute-term)
  - [4.2 Lagged cooling term](#42-lagged-cooling-term)
  - [4.3 Total site draw](#43-total-site-draw)
  - [4.4 Output signal](#44-output-signal)
- [5. Hardware Power Profile Library](#5-hardware-power-profile-library)
  - [5.1 Unknown-hardware fallback rule (resolves open question)](#51-unknown-hardware-fallback-rule-resolves-open-question)
  - [5.2 Counting-unit declaration](#52-counting-unit-declaration)
  - [5.3 Profile vintage and staleness](#53-profile-vintage-and-staleness)
- [6. Workload Load Signatures](#6-workload-load-signatures)
  - [6.1 Job-start detection and lead time](#61-job-start-detection-and-lead-time)
  - [6.2 Checkpoint-valley detection (resolved — quantitative trigger)](#62-checkpoint-valley-detection-resolved--quantitative-trigger)
- [7. Physical Asset Latency Model and Dispatch Arbitration](#7-physical-asset-latency-model-and-dispatch-arbitration)
  - [7.1 Asset ramp characteristics](#71-asset-ramp-characteristics)
  - [7.1.1 Non-dispatchable supply and the net dispatch requirement](#711-non-dispatchable-supply-and-the-net-dispatch-requirement)
  - [7.1.2 The grid-forming anchor constraint on BESS bridging](#712-the-grid-forming-anchor-constraint-on-bess-bridging)
  - [7.2 Dispatch arbitration rule (resolved — was previously unspecified)](#72-dispatch-arbitration-rule-resolved--was-previously-unspecified)
  - [7.3 Worked example (documents the gap the original note left implicit)](#73-worked-example-documents-the-gap-the-original-note-left-implicit)
- [8. Thermal Lag / Cooling Model](#8-thermal-lag--cooling-model)
  - [8.1 Pre-cooling and the shiftable load class](#81-pre-cooling-and-the-shiftable-load-class)
  - [8.2 Liquid cooling and the changing time constants](#82-liquid-cooling-and-the-changing-time-constants)
- [9. Time Constant Reconciliation](#9-time-constant-reconciliation)
- [10. Input Data Contract: WorkloadSignal Payload](#10-input-data-contract-workloadsignal-payload)
- [11. Edge Cases and Error Handling](#11-edge-cases-and-error-handling)
  - [11.1 Overlapping job launches](#111-overlapping-job-launches)
  - [11.2 Job cancellation mid-ramp](#112-job-cancellation-mid-ramp)
  - [11.3 Out-of-order or delayed events](#113-out-of-order-or-delayed-events)
  - [11.4 Clock skew](#114-clock-skew)
  - [11.5 Unmapped hardware](#115-unmapped-hardware)
- [12. Confidence, Tolerance, and Accuracy Reporting](#12-confidence-tolerance-and-accuracy-reporting)
- [13. Traceability to Parent Product Specification](#13-traceability-to-parent-product-specification)
- [14. Resolution Log: Contradictions and Open Questions Closed](#14-resolution-log-contradictions-and-open-questions-closed)
- [15. Residual Open Items (Cannot Be Resolved on Paper)](#15-residual-open-items-cannot-be-resolved-on-paper)
- [16. Addendum A: Acceptance Test Matrix](#16-addendum-a-acceptance-test-matrix)
  - [16.1 Core formula (Section 4, Section 8)](#161-core-formula-section-4-section-8)
  - [16.2 Checkpoint-valley classification (Section 6.2)](#162-checkpoint-valley-classification-section-62)
  - [16.3 Dispatch arbitration and insufficient-reserve alert (Section 7)](#163-dispatch-arbitration-and-insufficient-reserve-alert-section-7)
  - [16.4 Hardware fallback and confidence (Section 5.1, Section 12)](#164-hardware-fallback-and-confidence-section-51-section-12)
  - [16.5 Event ordering and clock integrity (Section 11.3, 11.4)](#165-event-ordering-and-clock-integrity-section-113-114)
  - [16.6 Idempotency, malformed input, and cold start (Addendum B)](#166-idempotency-malformed-input-and-cold-start-addendum-b)
  - [16.7 Learning plane, plane separation, and non-dispatchable supply (Section 7.1.1, Section 21)](#167-learning-plane-plane-separation-and-non-dispatchable-supply-section-711-section-21)
  - [16.8 Persistence, restart, and storage tiers (Section 22)](#168-persistence-restart-and-storage-tiers-section-22)
  - [16.9 Curtailment, procurement, network telemetry, and agents (Sections 23–26)](#169-curtailment-procurement-network-telemetry-and-agents-sections-2326)
  - [16.10 Profile generations, thermal, and prescriptive maintenance (Sections 5, 8, 27)](#1610-profile-generations-thermal-and-prescriptive-maintenance-sections-5-8-27)
  - [16.11 Execution layer, anchor constraint, and protective interlock (Sections 7.1.2, 28)](#1611-execution-layer-anchor-constraint-and-protective-interlock-sections-712-28)
  - [16.12 Clock classes, fabric signal tiers, and calibration limits (Sections 11.4, 25)](#1612-clock-classes-fabric-signal-tiers-and-calibration-limits-sections-114-25)
  - [16.13 Adaptive ramp relaxation (Section 23.7)](#1613-adaptive-ramp-relaxation-section-237)
- [17. Addendum B: Idempotency, Malformed-Input, and Cold-Start Handling](#17-addendum-b-idempotency-malformed-input-and-cold-start-handling)
  - [17.1 Idempotency](#171-idempotency)
  - [17.2 Malformed and invalid input](#172-malformed-and-invalid-input)
  - [17.3 Cold start (uncalibrated site)](#173-cold-start-uncalibrated-site)
- [18. System Architecture: Component and Data-Flow Description](#18-system-architecture-component-and-data-flow-description)
  - [18.1 External systems → Ingestion](#181-external-systems--ingestion)
  - [18.2 WorkloadSignal → Forecast Engine](#182-workloadsignal--forecast-engine)
  - [18.3 Forecast and data model → Dispatch Advisor](#183-forecast-and-data-model--dispatch-advisor)
  - [18.4 DispatchPlan → Physical layer](#184-dispatchplan--physical-layer)
  - [18.5 Data model → Scenario Planner](#185-data-model--scenario-planner)
  - [18.6 The one structural relationship](#186-the-one-structural-relationship)
- [19. Operator Console: Page Structure and Reference Mockup](#19-operator-console-page-structure-and-reference-mockup)
  - [19.1 Console page inventory](#191-console-page-inventory)
  - [19.2 Page 1 — Site Overview](#192-page-1--site-overview)
  - [19.3 Page 2 — Compute & Workload](#193-page-2--compute--workload)
  - [19.4 Page 3 — Energy Storage](#194-page-3--energy-storage)
  - [19.5 Page 4 — Generation & Supply](#195-page-4--generation--supply)
  - [19.6 Page 5 — Thermal & Cooling](#196-page-5--thermal--cooling)
  - [19.8 Page 6 — Grid & Procurement](#198-page-6--grid--procurement)
  - [19.9 Page 7 — Network Telemetry](#199-page-7--network-telemetry)
  - [19.10 Page 8 — Proposals & Learning](#1910-page-8--proposals--learning)
  - [19.11 Cross-page conventions](#1911-cross-page-conventions)
- [20. IP Strategy](#20-ip-strategy)
  - [20.1 Strong candidates (tied to specific, non-obvious mechanisms)](#201-strong-candidates-tied-to-specific-non-obvious-mechanisms)
  - [20.2 Weaker candidates (more likely to face prior-art or abstractness pushback)](#202-weaker-candidates-more-likely-to-face-prior-art-or-abstractness-pushback)
  - [20.3 Claim strategy note](#203-claim-strategy-note)
- [21. AI/ML Model Strategy and Learning Loop](#21-aiml-model-strategy-and-learning-loop)
  - [21.1 The governing constraint: two planes, one direction of influence](#211-the-governing-constraint-two-planes-one-direction-of-influence)
  - [21.2 What the learning plane is for](#212-what-the-learning-plane-is-for)
  - [21.3 Model role assignment](#213-model-role-assignment)
  - [21.4 Data-residency boundary](#214-data-residency-boundary)
  - [21.5 The learning store](#215-the-learning-store)
  - [21.6 Learning promotion gate](#216-learning-promotion-gate)
  - [21.7 Relationship to the Confidence / Calibration Engine](#217-relationship-to-the-confidence--calibration-engine)
  - [21.8 Architecture placement](#218-architecture-placement)
  - [21.9 Residual open items](#219-residual-open-items)
- [22. Persistence and Storage Architecture](#22-persistence-and-storage-architecture)
  - [22.1 Principles](#221-principles)
  - [22.2 Storage tiers](#222-storage-tiers)
  - [22.3 Restart behavior (closes the Section 15 in-flight-state item)](#223-restart-behavior-closes-the-section-15-in-flight-state-item)
  - [22.4 Object storage: batching, idempotency, and edge-to-cloud sync](#224-object-storage-batching-idempotency-and-edge-to-cloud-sync)
  - [22.5 Data residency and bucket ownership](#225-data-residency-and-bucket-ownership)
  - [22.5.1 Jurisdiction, and what a jurisdiction flag does not buy](#2251-jurisdiction-and-what-a-jurisdiction-flag-does-not-buy)
  - [22.6 Rejected patterns](#226-rejected-patterns)
  - [22.7 Reference implementation and simulator mapping](#227-reference-implementation-and-simulator-mapping)
  - [22.8 Open items](#228-open-items)
- [23. Controllable Load and Compute Curtailment](#23-controllable-load-and-compute-curtailment)
  - [23.1 What this changes](#231-what-this-changes)
  - [23.2 The curtailment ladder](#232-the-curtailment-ladder)
  - [23.3 Placement in dispatch arbitration](#233-placement-in-dispatch-arbitration)
  - [23.4 Authority](#234-authority)
  - [23.5 Scheduler write-back: the WorkloadCommand contract](#235-scheduler-write-back-the-workloadcommand-contract)
  - [23.6 Safety interlocks](#236-safety-interlocks)
  - [23.7 Scheduler-side ramp limiting, and what prediction adds to it](#237-scheduler-side-ramp-limiting-and-what-prediction-adds-to-it)
  - [23.7.1 What a static ramp policy does not solve](#2371-what-a-static-ramp-policy-does-not-solve)
  - [23.7.2 Adaptive ramp relaxation](#2372-adaptive-ramp-relaxation)
  - [23.7.3 The comparison is quantitative, and the quantities are unmeasured](#2373-the-comparison-is-quantitative-and-the-quantities-are-unmeasured)
  - [23.8 Open items](#238-open-items)
- [24. Grid Procurement and Reserved Capacity](#24-grid-procurement-and-reserved-capacity)
  - [24.1 The supply model](#241-the-supply-model)
  - [24.2 The reservation decision](#242-the-reservation-decision)
  - [24.3 Authority: spending money is a different class of action](#243-authority-spending-money-is-a-different-class-of-action)
  - [24.4 Open items](#244-open-items)
- [25. Network Telemetry Ingestion](#25-network-telemetry-ingestion)
  - [25.1 Role, and the causality constraint](#251-role-and-the-causality-constraint)
  - [25.2 Data contract: NetworkTelemetry](#252-data-contract-networktelemetry)
  - [25.3 Hardware-plane signals and platform capability tiers](#253-hardware-plane-signals-and-platform-capability-tiers)
  - [25.4 Export plane and subscription model](#254-export-plane-and-subscription-model)
  - [25.5 Use in checkpoint-valley classification](#255-use-in-checkpoint-valley-classification)
  - [25.6 Contribution to calibration, and its limits](#256-contribution-to-calibration-and-its-limits)
  - [25.7 Open items](#257-open-items)
- [26. Agentic Control Architecture](#26-agentic-control-architecture)
  - [26.1 What "agentic" means here, and what it does not](#261-what-agentic-means-here-and-what-it-does-not)
  - [26.2 Agent inventory](#262-agent-inventory)
  - [26.3 Recommendation lifecycle](#263-recommendation-lifecycle)
  - [26.4 Inter-agent arbitration](#264-inter-agent-arbitration)
  - [26.5 Failure and fallback](#265-failure-and-fallback)
  - [26.6 Open items](#266-open-items)
- [27. Prescriptive Maintenance and Asset Availability](#27-prescriptive-maintenance-and-asset-availability)
  - [27.1 What "prescriptive" adds, and why it belongs here](#271-what-prescriptive-adds-and-why-it-belongs-here)
  - [27.2 Asset health and degradation model](#272-asset-health-and-degradation-model)
  - [27.3 The prescriptive ladder](#273-the-prescriptive-ladder)
  - [27.4 Forecast-aware scheduling and the availability state](#274-forecast-aware-scheduling-and-the-availability-state)
  - [27.5 Authority](#275-authority)
  - [27.6 What this is not](#276-what-this-is-not)
  - [27.7 Open items](#277-open-items)
- [28. Physical Execution Layer and Power Management System Integration](#28-physical-execution-layer-and-power-management-system-integration)
  - [28.1 Where GridSignal sits](#281-where-gridsignal-sits)
  - [28.2 What a dispatch command actually commands](#282-what-a-dispatch-command-actually-commands)
  - [28.3 Integration surface](#283-integration-surface)
  - [28.4 Interlock with protective fast load shedding](#284-interlock-with-protective-fast-load-shedding)
  - [28.5 Transition modes and what grid connection actually costs](#285-transition-modes-and-what-grid-connection-actually-costs)
  - [28.6 Scenario Planner and electrical digital twins](#286-scenario-planner-and-electrical-digital-twins)
  - [28.7 What GridSignal does not do](#287-what-gridsignal-does-not-do)
  - [28.8 Open items](#288-open-items)
- [29. Glossary of Terms](#29-glossary-of-terms)

## Executive Summary

This summary is written for readers who are not power engineers. It states the problem GridSignal addresses, describes the proposed solution without mathematics, and outlines the architecture in ordinary language. Everything asserted here is specified in implementable detail in Sections 1–29. Where a claim rests on an assumption that has not yet been validated against a real operating site, this summary says so, rather than leaving the reader to discover it in a residual-items list forty pages later.

### ES.1 The problem: a load that electrical systems were not built for

Electrical infrastructure rests on an assumption so basic that it is rarely stated aloud — that demand changes gradually. An office building fills up over an hour. A factory line starts in stages. Even a conventional data centre serving millions of web requests draws power smoothly, because the individual demands are uncorrelated and average out. Generators, switchgear, and utility grids are all designed around that smoothness.

Training a large AI model breaks the assumption, and it does so for a specific physical reason worth understanding, because everything else follows from it. A training job is not thousands of independent tasks. It is one enormous calculation split across thousands of processors that must stay in lockstep: each step of the computation requires every processor to exchange results with every other before the next step can begin. They start together, they compute together, and they pause together. From the electrical system's point of view, ten thousand processors behave as a single device.

The result is not a ramp. It is a step. A large training job can add tens of megawatts to a site's demand within seconds of starting, and remove it just as abruptly when it finishes. The equipment is also getting dramatically denser: a rack of AI hardware drew roughly 40 kilowatts three product generations ago, about 130 kilowatts two generations ago, and 190–230 kilowatts in the current generation, with 600-kilowatt designs already specified for the generation after this one. A single cabinet now consumes what a small neighbourhood does, and that figure has risen roughly fifteen-fold in four years.

**Why the operators own this problem rather than the utility.** Connecting a large new load to the public grid has become slow — waits of four years or more are common in the United States, and analysis of North American grid regions suggests that a majority will operate below comfortable reserve margins for much of the remainder of this decade. Many AI data centre operators have therefore stopped waiting and built their own generation on site: gas turbines, batteries, solar, sometimes a grid connection retained only as backup. The industry calls this "bring your own power." It solves the connection problem and inherits a new one. A continental power grid has enormous physical inertia and thousands of generators sharing the burden of any single disturbance. A site microgrid has a handful of machines and no inertia to speak of. A twenty-megawatt step that a utility would not notice is, on a site microgrid, the whole problem.

**Why existing controls cannot solve it.** Every commercially available control system for this equipment is reactive, and reactive is a structural limitation rather than a quality problem. The sequence is always the same: the job starts and the processors draw power; a sensor measures the change; the controller commands a generator to increase output; the generator ramps up at whatever rate its mechanical design permits. By the time the first measurement exists, the load has already arrived. The controller is responding to history.

The arithmetic is unforgiving. A gas turbine typically ramps at roughly one megawatt every five seconds, so a twenty-megawatt step needs about a hundred seconds of ramping. The load arrives in a small fraction of that. The difference has to be covered by batteries, if enough have been purchased, or else by a voltage and frequency excursion — which is the polite term for protective equipment tripping and the site going dark. A substantial share of serious data centre outages are power-related, and the industry's usual answer is to buy more of everything: more battery, more generator, more margin. That is expensive capital sitting idle against an event that a few seconds of warning would have handled comfortably.

### ES.2 The insight: the computer knows before the electricity does

The observation GridSignal is built on can be stated in one sentence. The software that decides which machines will run a job makes that decision before the machines start drawing power.

Large computing clusters are not used directly. Work is submitted to a job scheduler — Slurm, Kubernetes, and Ray are the common ones — which holds a queue of pending work and decides what runs where. When a job reaches the front of the queue, the scheduler allocates it: it records that this specific job will run on these specific machines, of this specific type, in this quantity. That allocation is a discrete, timestamped, machine-readable event.

Then thirty to sixty seconds pass before the processors reach full power. Software containers have to start. Model weights, often hundreds of gigabytes, have to be read from storage into memory. The high-speed network connecting the processors performs its own initialisation. Only after all of that does the electrical load actually materialise.

**That interval is the entire opportunity, and its nature matters more than its length.** It is not a measurement of something that is happening. It is a statement of intent about something that has not happened yet. No sensor, however good, can produce it, because at the moment the scheduler makes its decision there is nothing yet to sense. A reactive system is a person standing at the entrance of a car park counting cars as they arrive. GridSignal reads the reservation list.

**Why this has not already been done.** The signal sits in the gap between two professions that rarely meet. People who build power management systems come from industrial, utility, and building-services backgrounds; job schedulers belong to high-performance computing and platform engineering. The vendors who make excellent microgrid controllers do not read Slurm queues, and the engineers who read Slurm queues do not dispatch turbines. A review of the leading vendors' published product documentation is consistent with this: their forecasting uses historical metering, weather feeds, and utility tariff signals on horizons from fifteen minutes to two days ahead, and their real-time control is reactive in the millisecond range. The seconds-ahead band between the two appears unoccupied. That finding should be read for exactly what it is — an absence of evidence in public material, not a vendor disclaiming the capability — and a single unpublished reference design could revise it. Nor does an empty band by itself prove an attractive one: well-capitalized companies with better access to these customers than we have may have evaluated this space and declined it. The argument for the opportunity has to rest on the causality asymmetry described above, which is structural, rather than on the vacancy, which is circumstantial.

### ES.3 The proposed solution, in plain terms

GridSignal reads the job queue, converts what it finds into a prediction of electrical demand, and stages the site's equipment before that demand arrives. Five things have to work for that to be more than a slogan.
- **1. Read intent, not consequences.** The system connects to the job scheduler and receives its allocation events directly. Every subsequent step depends on this being the input, because it is the only input that exists before the load does.
- **2. Translate machines into megawatts.** This is the least obvious part and, commercially, the most defensible. A queue event says something like "job 88214 has been allocated fourteen nodes of type nextgen_rack_liquid." Converting that into a power figure requires knowing what that specific hardware actually draws — per model, per configuration, per cooling method. That is a body of specialised knowledge that control vendors from heating and ventilation backgrounds simply do not carry, and it changes every year as new hardware ships. GridSignal maintains it as a versioned library with an explicit record of which hardware generation each entry describes, because an out-of-date entry silently under-predicts by ninety kilowatts per cabinet and nothing in the data looks wrong.
- **3. Plan on two clocks at once.** A predicted surge in computing power creates two separate problems on two different timescales. The generators have to spin up, which is a mechanical process measured in seconds. Then, roughly a minute and a half later, the cooling system notices all that heat and increases its own power draw — a second surge, arriving after the first has been dealt with. A system that plans only for the first is ambushed by the second. GridSignal forecasts and stages both against a single predicted event.
- **4. Know when a pause is not an ending.** Training jobs stop periodically to save their progress to disk, a process called checkpointing. During it, power draw falls sharply for five to thirty seconds. From the electrical trace alone this is indistinguishable from the job finishing. A reactive controller sees the drop, concludes the work is over, and begins shutting generation down — just as the job resumes and the load comes back. GridSignal applies an explicit test: a drop of at least fifteen percent lasting between five and thirty seconds and recovering to ninety percent within forty-five seconds is a checkpoint, and generation is held. Anything else is treated as a genuine ending. When the evidence is ambiguous, the system holds its position and says so on the dashboard rather than guessing.
- **5. Say so, in advance, when it will not work.** If the arithmetic shows that the available generation and battery cannot cover a predicted surge, the operator is told at the beginning of the thirty-second window — with the specific shortfall stated in megawatts and seconds — rather than after the lights have flickered. A warning that arrives with time to act on it is a different product from an alarm.

### ES.4 What GridSignal deliberately does not do

Any site of this kind already has a microgrid controller managing its generation, a building management system running its cooling, protection relays guarding its electrical safety, and often a maintenance management system tracking its equipment. These are mature products from established vendors, several of them carrying safety obligations and grid-code compliance requirements.

GridSignal replaces none of them. It does not perform islanding or reconnection, does not command chillers, does not shed load protectively, does not control the connection to the public grid, and does not issue work orders. The specification draws this boundary in three separate places and the principle is identical each time:

**GridSignal forecasts and pre-stages; the domain controllers execute.**

There are two reasons, one technical and one commercial. Technically, those systems act in milliseconds — a static transfer switch operates in about four thousandths of a second — and a prediction made thirty seconds ahead has no business inside a loop that fast. Commercially, crossing any of those lines would mean competing with an entrenched vendor on their own ground while abandoning the one capability nobody else has. Positioned this way, the established vendors are integration partners rather than rivals: their equipment already speaks the industrial protocols GridSignal would use to advise it, and their forecasting gap is precisely the space GridSignal occupies.

### ES.5 The architecture, in ordinary language

The system answers four questions in sequence: what is about to happen, what does that mean in megawatts, what should be done about it, and who does it. The architectural decisions worth understanding are about where each of those happens and how much of it is allowed to be clever.

**It runs at the site, not in the cloud.** The entire value is a thirty-to-sixty-second window, and the round trip to a distant data centre is an unpredictable fraction of it. More importantly, a site that has built its own power precisely because it cannot depend on outside infrastructure should not have its power controller depend on an internet connection. GridSignal's time-critical work runs on a computer physically at the site, and continues working with the network down.

**The part that makes decisions is deliberately unintelligent.** There is no AI model, no machine-learning inference, and no statistical judgement anywhere in the path that leads to a command. Given the same inputs, it produces the same outputs, every time, and any decision it made can be reconstructed afterwards from the record. This is a deliberate choice that runs against current expectations, so it is worth stating the three reasons plainly. Speed: the budget from decision to command is two seconds, and language-model inference cannot be reliably bounded inside it. Accountability: a control decision that cannot be reproduced cannot be audited, defended after an incident, or explained to an insurer. Independence: the loop has to keep working when the network does not. The intelligence in GridSignal is in what it reads and how it translates, not in a model exercising judgement about dispatch.

**The part that learns sits alongside, never inside.** A separate layer, under no deadline, runs six specialised agents — for computing, storage, generation, procurement, network, and thermal systems. Each watches its own domain, finds patterns, measures how wrong yesterday's forecasts turned out to be, and proposes changes to the settings the decision-making layer uses.

They propose. Nothing they conclude takes effect until a person approves it. This distinction carries more weight than it might appear to: a system that learns continuously and applies what it learns immediately is a system whose behaviour changes without anyone having decided that it should. Proposals queue up with their supporting evidence, an operator approves or rejects each one, and every approval is recorded against the person who made it. Proposals whose values fall outside sensible engineering ranges are rejected automatically and never reach a human at all, because in practice they indicate a measurement fault rather than a discovery.

**It fails in the direction of doing less.** If the entire learning layer becomes unavailable — every external model provider unreachable, the network down, the cloud gone — the decision layer continues operating unchanged on its last approved settings. The only thing lost is new proposals. This is written as a testable requirement rather than an aspiration, and there is an acceptance test that asserts the dispatch behaviour is identical either way.

**What an operator sees.** A console of nine pages: a site overview, then one page each for computing workloads, energy storage, generation and supply, thermal and cooling, grid and procurement, network telemetry, the queue of pending proposals, and a scenario planner for asking what-if questions against real history. Every page shows the current operating mode, and every control states the authority it acts under before it is pressed.

**What it remembers.** Three tiers of storage, separated by how badly their loss would hurt. A local file on the site computer holds the state the decision loop needs, so that a restart resumes rather than forgets and no network is required. A database holds site history and the audit trail of every command ever issued. A long-term archive holds everything older, and losing access to it affects nothing but long-range analysis.

### ES.6 Where GridSignal fits among the systems already there

The clearest way to see the opportunity is to arrange the existing control systems by how fast they act.

| **Layer** | **Timescale** | **What occupies it** | **GridSignal** |
|---|---|---|---|
| Economic planning | 15 minutes to 2 days | Energy management software optimising against tariffs, weather, and generation cost | Feeds it |
| Workload prediction | 30 to 60 seconds | Nothing, in any vendor stack reviewed | This is GridSignal |
| Real-time control | Sub-second to seconds | Microgrid controller: islanding, load sharing, generator coordination | Advises it |
| Protection | Milliseconds | Protective relays, fast load shedding, transfer switches | Must not interfere with it |

The table is the investment case in one picture. GridSignal is not a better version of anything in the second, third, or fourth row. It occupies a band that is empty, and it makes the rows below it more effective by giving them warning they have never previously had.

### ES.7 What is specified, and what is not yet known

A specification that presented estimates as validated facts would be harder to correct later and less useful to the engineers building from it, so this document separates the two carefully. The same separation belongs in a summary.

**Specified, and testable today.** The translation formulas, the timing thresholds, the rules for deciding between a checkpoint and a job ending, the arbitration order between battery and generator, the data contracts with the scheduler, the behaviour on malformed input and on restart, and the authority required for every action the system can take. Seventy-four acceptance test cases state the scenario, the input, and the expected result, so that a working implementation can be checked against this document rather than against somebody's recollection of it.

**Estimated, and awaiting a real site.** The constants inside those formulas are engineering judgements. The ninety-second delay before cooling responds is the midpoint of a plausible range, not a measurement. The turbine ramp rate of one megawatt every five seconds is a single figure standing in for every make and model. The hardware power figures are manufacturers' ratings rather than observed draw. Each of these requires telemetry from an operating site before it can be trusted, and the specification treats that dependency as a first-class concern: every new site begins in an explicitly uncalibrated state, every forecast it produces is tagged as such, the confidence ranges are widened accordingly, and dispatch is sized against the pessimistic end of those ranges rather than the optimistic one.

**Not yet built.** There is no production deployment. A browser-based simulator exists to demonstrate the behaviour to engineering and investor audiences without requiring hardware or a design partner's telemetry.

**Unmeasured, and material.** The alternatives to this product are not only competing products. A larger battery, or a scheduler policy that ramps every job up gradually, will each close much of the same gap more cheaply and with less integration risk. Section 23.7 states the second of these in full, recommends it as a baseline, and defines the two quantities that determine whether prediction earns its place alongside it — neither of which has yet been measured at an operating site. A reader evaluating this work should treat the engineering as specified and the commercial magnitude as an open question, because that is what they are.

The honest summary is that the mechanism is designed and specified to the level of detail an engineering team can build from, and the numbers inside it are placeholders awaiting a design partner. Those are different kinds of incompleteness, and conflating them would misrepresent the state of the work in either the flattering or the unflattering direction.

## 1. Purpose and Scope

**Purpose.** This document is the engineering functional specification for the Forecast Engine's core translation layer: the mechanism that converts job-scheduler queue telemetry (Slurm / Kubernetes / Ray) into a real-time physical megawatt (MW) draw prediction, and the downstream lag models that stage microgrid assets ahead of that draw. It supersedes the informal “Secret Sauce” engineering note dated July 20, 2026 by resolving the formula contradiction, the unreconciled time constants, and the further specification gaps identified in review — 13 items in total; see the full resolution log in Section 14.

**Scope.** Covers the Forecast Engine's workload-to-power model (Section 4), the hardware power-profile library (Section 5), workload load signatures including the checkpoint-valley detector (Section 6), the physical asset ramp/dispatch model (Section 7), the thermal lag model (Section 8), the input data contract (Section 10), edge-case handling (Section 11), and the AI/ML model strategy and learning loop that sits alongside — but deliberately outside — the real-time control path (Section 21). It does not cover Connector Fabric protocol adapters, Scenario Planner, or UI/dashboard design, which are addressed in the parent product specification.

**Out of scope for this version.** Per-vendor calibration of hardware power draw against measured telemetry (requires design-partner data per product spec Section 8 / Section 11 item 6); Autonomous dispatch mode logic beyond the staging recommendations described in Section 7 (full safety-interlock design is covered under NFR-3/NFR-4 of the parent spec).

## 2. Secret Sauce: Intellectual Property Summary

GridSignal's defensible technical differentiation is not any single formula but the combination of four elements, none of which incumbent EMS/BMS platforms implement because they are not workload-aware:
- **1. Predictive, not reactive, sensing point.** GridSignal reads the job-scheduler queue (Slurm/K8s/Ray) before the GPUs draw power, giving 30–60 seconds of lead time that a power-sensor-based BMS structurally cannot obtain — by the time a BMS senses the load, it has already happened. This is the foundational asymmetry the rest of the IP is built on.
- **2. The workload-to-megawatt translation layer.** A hardware-profile-indexed conversion (Section 4–5) that turns a queue event's node/GPU allocation into a physical power figure in real time, instead of treating all jobs as an undifferentiated “task.” This requires and encodes non-public operational knowledge of AI hardware power draw (per-SKU, per-rack-density) that most EMS vendors, who come from industrial/HVAC backgrounds, do not carry.
- **3. The dual-lag staging model.** Two independently-modeled delays — mechanical asset ramp time (Section 7) and thermal/cooling lag (Section 8) — are forecast and staged against a single predicted compute event on two different clocks. This is what prevents the “double-whammy” step-load (compute spike + delayed chiller step-load) that causes voltage instability in reactive systems.
- **4. Checkpoint-valley discrimination.** A pattern-matching heuristic (Section 6.2) that distinguishes a training job's brief checkpoint dip from an actual job completion, preventing a reactive controller from prematurely ramping down turbines mid-job — a failure mode that is specific to LLM training workloads and invisible to generic load forecasting.

These four elements compose into the product spec's core differentiation thesis (parent doc, Section 1): workload-aware forecasting out-predicts generic historical/weather-based forecasting used by incumbents. Sections 4–8 below specify each element to implementation precision.

## 3. System Model and Definitions

All quantities below are functions of continuous time t (seconds), evaluated on a discrete tick per Section 3.1. Symbols:

| **Symbol** | **Meaning** | **Units** |
|---|---|---|
| P_compute(t) | Instantaneous IT/compute electrical draw at the rack, summed across all active jobs | MW |
| P_cooling(t) | Incremental cooling-system electrical draw attributable to the thermal lag response | MW |
| P_total(t) | Total site electrical draw = P_compute(t) + P_cooling(t) | MW |
| Nodes_i(t) | Count of active nodes of hardware profile i at time t, from queue telemetry | count |
| kW_i | Rated power draw per node/chassis of hardware profile i (Section 5) | kW |
| PUE_base | Fixed, near-instantaneous overhead multiplier: power distribution/UPS/conversion losses not attributable to active cooling response | unitless, typically 1.02–1.05 |
| α(t) | Cooling-lag incremental fraction applied to lagged compute load (Section 8) | unitless, 0.10–0.30 |
| Δt_thermal | Site-specific thermal lag coefficient (Section 8, Section 9) | seconds, default 90 |
| Δt_lead | Queue-to-power lead time: interval between a job entering “starting” state and GPUs reaching full draw | seconds, 30–60 |
| r_asset | Mechanical ramp rate of a given generation asset (Section 7) | MW / second |
| P_renewable(t) | Aggregate output of non-dispatchable on-site generation (solar PV and any other passive collector). An exogenous measured/forecast input, not a commanded setpoint — Section 7.1.1 | MW |
| P_curtailable(t) | That portion of P_compute(t) which site policy has marked as eligible for curtailment, resolved by priority class — Section 23.2 | MW |
| P_grid_firm | Contracted grid import capacity continuously available without reservation — Section 24.1 | MW |
| P_grid_reserved(t) | Additional grid import capacity reserved in advance for a specific window; firm once purchased, but only obtainable at reservation lead time T_reserve — Section 24.1 | MW |
| P_anchor_reserve | Headroom a grid-forming anchor source must retain for voltage and frequency regulation, and which is therefore unavailable for bridging — Section 7.1.2 | MW |

### 3.1 Evaluation cadence

The translation layer is event-driven, not purely polling: it recomputes P_total(t) whenever a WorkloadSignal event arrives (job start/stop/checkpoint/scale event per the parent spec's data model, Section 7) and additionally on a fixed 5-second tick to advance the lag models between events. This satisfies parent-spec NFR-2's requirement that control command execution latency be under 2 seconds from decision to command issuance — the 5-second tick is the forecast refresh floor; it is independent of, and faster than, the 5-minute short-horizon forecast refresh in FR-1.3, which governs the rolling 15-minute–4-hour forecast surfaced on the dashboard, not the real-time staging loop described here.

## 4. The Workload-to-Megawatt Formula (Resolved)

The original formula applied PUE_site as an instantaneous multiplier over the whole compute term while separately claiming cooling response is delayed by 60–120 seconds — an internal contradiction, since PUE conventionally already includes cooling overhead. This version splits fixed/instant overhead from delayed/cooling-attributable overhead so no term double-counts cooling, and makes both terms explicit functions of time.

### 4.1 Instantaneous compute term

P_compute(t) = Σᵢ [ Nodesᵢ(t) × kWᵢ ] × PUE_base / 1000 (MW; ÷1000 converts kW to MW)

This term is indexed by hardware profile i (Section 5), not a single scalar constant, and updates immediately (same tick) as queue telemetry reports a node-count change for any job. PUE_base captures only the overhead that responds on the same timescale as the compute load itself (power distribution and conversion losses, UPS losses) — not active cooling.

### 4.2 Lagged cooling term

P_cooling(t) = α(t) × P_compute(t − Δt_thermal) (MW; see Section 8 for the full α(t) rise function — this is not a step function)

### 4.3 Total site draw

P_total(t) = P_compute(t) + P_cooling(t)

This decomposition resolves the double-count: PUE_base and α(t) are mutually exclusive overhead buckets, and only the α(t) term is subject to the thermal delay. A site's fully-loaded effective PUE at steady state (no ramp in progress) is therefore PUE_base × (1 + α), which should be validated against a site's nameplate/measured PUE during commissioning (Section 12).

### 4.4 Output signal

The engine emits a discrete prediction event whenever a forecast step-load crosses a configurable threshold (default 0.5 MW), of the form:

PREDICTION SIGNAL: +4.2 MW compute step-load at T+30s; +0.9 MW secondary cooling step-load at T+120s (confidence: ±12%)

The confidence figure is required output, not decorative — see Section 12.

## 5. Hardware Power Profile Library

kW_i is looked up from a versioned, site-configurable table keyed by a hardware profile identifier reported in the WorkloadSignal payload (Section 10). Seed values for MVP:

| **Profile ID** | **Description** | **Counting unit** | **Rated draw** | **Vintage** |
|---|---|---|---|---|
| hopper_8gpu_air | Air-cooled 8-GPU server, H100/H200 class (DGX-class chassis) | chassis | ≈ 10.2 kW / chassis | 2023–24 |
| blackwell_nvl72 | GB200 NVL72 liquid-cooled rack — 72 packages, 36 Grace CPUs, unified NVLink 5 domain | cabinet | 120–132 kW / cabinet | 2024–25 |
| blackwell_ultra_nvl72 | GB300 NVL72 liquid-cooled rack | cabinet | 140–150 kW / cabinet | 2025 |
| rubin_vr200_nvl72 | Vera Rubin VR200 rack. Marketed as NVL144 counting 144 GPU dies; physically 72 dual-die packages — see 5.2 | cabinet | 190–230 kW / cabinet | 2026 |
| generic_fallback | Unrecognized or unconfigured hardware profile | as reported | Site-configured — see 5.1. No global default is safe across this range | n/a |

### 5.1 Unknown-hardware fallback rule (resolves open question)

If a WorkloadSignal reports a hardware profile identifier not present in the site's library, the engine shall:
- Apply the site-configured generic_fallback rated draw rather than rejecting the event or silently omitting the job's contribution. The fallback is a per-site commissioning value, not a global constant: the profiles in the table above span roughly 10 kW to 230 kW per counted unit, so any single global default is badly wrong at one end of that range or the other. A site whose configured fallback is below its own densest known deployment escalates an unmapped profile to an operator alert rather than forecasting from a value it already knows to be too low.
- Tag the resulting forecast segment with a data-quality flag (low_confidence: unmapped_hardware) that widens the reported confidence interval for that segment (Section 12) and surfaces on the operator dashboard.
- Emit a one-time onboarding alert per unrecognized profile ID per site, prompting an operator or integrator to map it in the hardware profile library.

This ensures an unmapped SKU degrades forecast precision rather than forecast availability, consistent with the parent spec's FR-1.6 graceful-degradation principle.

### 5.2 Counting-unit declaration

Every profile declares the unit that node_count is expressed in: chassis, cabinet, package, die, or accelerator. The WorkloadSignal's node_count (Section 10) is interpreted in the declared unit of the profile its hardware_profile_id resolves to, and nowhere else.

**This is not bookkeeping.** Vendors change counting conventions between generations. The Vera Rubin rack is marketed as NVL144, counting 144 GPU dies, and is physically 72 dual-die packages — so "144 GPUs" and "72 GPUs" describe the same cabinet and differ by exactly 2×. A site integration that reports one while the profile assumes the other produces a forecast that is off by a factor of two, in a direction that depends on which side got it wrong, with no symptom other than persistent forecast error.

A reported unit that disagrees with the profile's declared unit is a domain validation failure under Section 17.2 and is quarantined. It is specifically not converted silently: an automatic conversion would encode an assumption about which side is correct, and the whole point is that this is the assumption nobody should be making.

### 5.3 Profile vintage and staleness

Every profile carries a vintage: the hardware generation it describes and the date its rated draw was established. The reason is that rack power is not converging. Roughly 40 kW per rack for Hopper-class deployments, 120–132 kW for GB200 NVL72, 140–150 kW for GB300, and 190–230 kW for Vera Rubin VR200, with the following generation specified at 600 kW-class densities and megawatt-class rack designs already published. That is on the order of a 15× span inside this specification's own service life.

A library without vintage tracking therefore ages silently, and the failure is quantitatively serious rather than cosmetic: forecasting a Rubin cabinet against a GB200-era profile under-predicts by 60–90 kW per cabinet, so ten racks exceed the 0.5 MW threshold at which Section 4.4 emits a prediction signal at all. The site would be systematically under-staged with no invalid input anywhere to flag.
- **Staleness flag.** A profile whose vintage exceeds a configurable age (MVP default: 18 months) renders as stale on the operator console and widens the confidence band on any forecast segment it contributes to, using the same mechanism as Section 5.1.
- **Generation-gap prompt.** Where a site's densest configured profile is more than one generation behind the newest entry in the library, a review prompt is raised. This catches the common case: the library was updated centrally and the site configuration was not.
- **Vintage is not calibration.** A vintage records when a nameplate figure was recorded, not whether it matches measured draw at this site. Calibration remains the Section 12 and Section 21.6 path, and a site may hold a current-vintage profile that is still badly calibrated for its own configuration.

## 6. Workload Load Signatures

| **Workload type** | **Power signature** | **Operational output** |
|---|---|---|
| LLM training run | Sustained draw at 95–100% TDP with periodic checkpoint drops/spikes | Step-load prediction of +5 to +20 MW sustained over hours/days; see 6.1 for job-start detection and 6.2 for checkpoint discrimination |
| Inference serving | Volatile, diurnal/traffic-correlated wave with sudden burstiness | Micro-ramp prediction of ±500 kW over ~10-second intervals, generated from request-queue-depth telemetry rather than node-count changes |
| Model checkpointing | Brief severe compute drop (10–30s) followed by immediate re-ramp | Checkpoint-valley flag (6.2) suppresses turbine ramp-down during the valley |

### 6.1 Job-start detection and lead time

A job transitions from queued to starting when the scheduler allocates nodes; GPUs reach full TDP Δt_lead ≈ 30–60 seconds later (container init, model/weight load, NCCL/collective warmup). The engine begins staging assets at the starting event, not at the full-TDP event, to use the full available lead time — see Section 7 for how this interacts with mechanical ramp rate.

### 6.2 Checkpoint-valley detection (resolved — quantitative trigger)

The original note said only “flag the checkpoint valley” with no measurable trigger. Resolved rule, evaluated per active training job:
- **Primary signal (preferred):** a checkpoint_start / checkpoint_end event pair in the WorkloadSignal stream (Section 10), if the scheduler/framework integration emits one. When present, this is authoritative and no heuristic is needed.
- **Fallback signal (shape heuristic, used when no explicit checkpoint event is available):** a drop of ≥15% from the job's trailing 5-minute median sustained draw, lasting between 5 and 30 seconds, followed by a return to ≥90% of the pre-drop draw within 45 seconds of the drop's onset, is classified as a checkpoint valley.
- **Job-end classification:** a drop meeting the same threshold that does NOT return to ≥90% of pre-drop draw within 45 seconds, OR a job_end event from the scheduler, is classified as job completion and turbine ramp-down proceeds normally.
- **Ambiguous case:** if 45 seconds elapse without either a re-ramp or a scheduler job_end event, the engine holds current staging (does not ramp down) for a configurable grace period (MVP default: additional 30 seconds) and flags the job status as uncertain on the dashboard, rather than guessing.

This makes the checkpoint-valley behavior testable: a blackbox test can construct a synthetic draw trace against the three thresholds above (15% / 30s / 45s / 90%) and assert the expected classification.

## 7. Physical Asset Latency Model and Dispatch Arbitration

### 7.1 Asset ramp characteristics

| **Asset class** | **Response latency** | **Ramp constraint** | **Role** |
|---|---|---|---|
| BESS (battery storage) | < 100 ms | Effectively instantaneous within capacity limit | Bridges the gap between prediction and slower assets reaching target output |
| Gas turbine / reciprocating engine | Seconds to start; then mechanically ramp-limited | MVP default: 1 MW per 5 seconds (r_asset = 0.2 MW/s) — configurable per asset make/model as vendor data is obtained | Sustained capacity for the duration of the job |
| Cooling system (HVAC/chillers) | Thermal, not mechanical, lag | Governed by Δt_thermal and α(t) (Section 8), not r_asset | Secondary, delayed step-load — not a dispatchable asset in the staging sense, but must be provisioned for |
| Non-dispatchable renewable (solar PV) | N/A — never commanded | Output is an exogenous input, not a setpoint; varies with irradiance, weather, soiling, and module/string faults | Reduces the net load the dispatchable fleet must serve; a fall in output is a supply-side shortfall handled by the same Section 7.2 arithmetic as a demand-side spike |
| Curtailable compute load | Seconds to minutes, action-dependent; restoration is far slower than curtailment | Bounded by site curtailment policy and priority class; laddered, not binary — Section 23.2 | Last-resort reliability resource. Reduces demand when supply cannot be made to meet it. Never used for economic optimization in this version |
| Grid import (firm and reserved) | None for firm capacity; T_reserve (hours) for additional reserved blocks | Bounded by contracted capacity; spot availability above it is non-firm — Section 24.1 | Firm and reserved capacity count toward the Section 7.2 reserve check; non-firm spot import does not |

### 7.1.1 Non-dispatchable supply and the net dispatch requirement

**Resolved in product review, July 27, 2026.** Solar PV is a passive collector, not a dispatchable asset. Panel- and module-level telemetry reports operational health — string faults, soiling, inverter status — rather than a controllable output setpoint, so GridSignal can measure and forecast solar output but cannot command it. The controllable fleet is therefore turbines and BESS only, with grid-tie as an import/export boundary. Small modular reactors are excluded from this version as too immature to model with defensible parameters.

This makes solar an input to the arbitration arithmetic rather than a participant in it. Define the net dispatch requirement:

**P_dispatch_required(t) = P_total(t) − P_renewable(t)**

Section 7.2's ΔP is a change in P_dispatch_required(t), not in P_total(t). The consequence is worth stating plainly, because it is the reason this term belongs in the Forecast Engine at all rather than only in the Scenario Planner: a compute step-load and a collapse in renewable output are the same event class to the Dispatch Arbitrator. A 6 MW compute spike arriving while solar holds steady and a 6 MW loss of solar under flat compute both produce a 6 MW increase in P_dispatch_required(t) and both must trigger the same staging and the same insufficient-reserve check. The compound case — a compute spike coinciding with a renewable shortfall — is additive and is the worst case the reserve check must size against.

Two asymmetries relative to the compute term are load-bearing and must not be lost in implementation:
- **No lead time.** The entire premise of Sections 2 and 6.1 is that queue telemetry gives 30–60 seconds of warning before compute draw materializes. A renewable shortfall carries no equivalent advance signal. A cloud transient is forecastable at low confidence from irradiance data; a physical fault — an inverter trip, or a contractor severing a feeder — is a step change with Δt_lead = 0. The reserve check must therefore treat renewable output as capacity that can vanish without notice, not as firm capacity.
- **Availability, not dispatchability.** P_renewable(t) may be subtracted from the load the fleet must serve, but it may never be counted toward the ramp capability in the Section 7.2 step 4 shortfall calculation. Turbine ramp rate and BESS discharge capacity are the only terms that close a gap; solar cannot be ramped to close one.

**Scenario framework interaction.** Because renewable output is an input, it is also an injectable stressor: a reduced-irradiance profile, a step loss of a feeder, and a compute spike coincident with either are scenario inputs rather than special-case logic in the engine. The engine needs no scenario-specific code path — it needs only to read P_renewable(t) as a first-class supply term, which is what this subsection specifies.

**Open.** Default module/array sizing and an irradiance-to-MW conversion for simulator seed configuration are not fixed here; nameplate output varies with array size and whether the mount is fixed or tracking. Recorded as a residual item in Section 15.

### 7.1.2 The grid-forming anchor constraint on BESS bridging

Section 7.2 treats BESS discharge as available up to rated capacity and state of charge. That is correct when the battery is grid-following, operating in P/Q mode and taking its voltage and frequency reference from somewhere else. It is not correct when the battery is the island's grid-forming anchor.

An islanded microgrid requires one source to establish the voltage and frequency reference — the anchor, operating in V/f mode with virtual synchronous machine or droop behavior. That role is commonly filled by either a genset or the BESS, and a battery transitions between current-source and voltage-source behavior when the site islands. A BESS acting as anchor has a first duty that is not energy delivery: it is holding the reference that every grid-following inverter on site depends on.

**The consequence for the reserve arithmetic.** An anchor must retain headroom in both directions to regulate against disturbance. Discharging it to its rated limit to bridge a compute step-load leaves nothing with which to hold frequency when the next disturbance arrives — and a compute step-load is itself a disturbance. Bridging capability is therefore reduced by the anchor duty:

**BESS_bridging_available(t) = min(rated capacity, usable SoC) − P_anchor_reserve**

where P_anchor_reserve is zero when the battery is grid-following and non-zero when it is the anchor. The Section 7.2 step 4 reserve check and the insufficient-reserve alert shall use the anchor-adjusted figure. Using the unadjusted one produces a check that passes shortly before a frequency excursion, which is the specific failure this specification exists to prevent.
- **The anchor role is dynamic, not static.** A site that is grid-connected has no anchor duty on its BESS — the utility is the reference. The same site islanded does. Anchor assignment therefore changes with operating mode and must be read from the power management system rather than assumed from configuration.
- **Where the anchor is a genset, the constraint moves.** A genset anchor is governed by its droop response and inertia rather than by transfer timing, and it is the droop dynamics that bound how fast load can be added. This is outside the ramp-rate model in Section 7 and is recorded as PX-2.
- **P_anchor_reserve is not currently derivable by GridSignal.** It is a property of the island's dynamic stability study, not of the battery nameplate. It shall be a site configuration value supplied at commissioning, treated as a control-relevant parameter under Section 21.6, and defaulted to a conservative fraction of rated capacity rather than to zero — because defaulting to zero silently reproduces the unadjusted arithmetic this subsection exists to correct.

### 7.2 Dispatch arbitration rule (resolved — was previously unspecified)

Given a predicted step-load of magnitude ΔP starting at T+Δt_lead, the controller stages assets as follows:
- **1. Turbine ramp starts immediately** at the earliest moment the prediction is available (i.e., at the job's starting event, using the full Δt_lead window), targeting ΔP at rate r_asset per online turbine.
- **2. BESS covers the shortfall** at every tick: BESS_output(t) = max(0, P_total(t) − turbine_output(t)), up to the anchor-adjusted bridging capability defined in Section 7.1.2, which equals rated capacity and state of charge only when the battery is grid-following.
- **3. BESS discharge tapers** as turbine_output(t) approaches P_total(t); once turbine_output(t) ≥ P_total(t) for a sustained 10-second window, BESS returns to standby/recharge.
- **4. Insufficient-reserve alert (resolves the lead-time-vs-ramp-time gap risk):** at staging time, the controller computes the ramp time required for available turbine capacity to reach ΔP (ΔP / r_asset) and the resulting gap window during which BESS alone must cover the declining shortfall (gap duration = ΔP / r_asset − Δt_lead, when positive; see Section 9). It then checks whether the BESS's max sustainable discharge duration at the required power level (a duration, in seconds — not BESS rated MW multiplied by that duration, which would be an energy-like quantity and cannot be compared to a time) covers that gap. If it does not, the system issues an insufficient-reserve warning to the operator dashboard at staging time — not after the fact — identifying the specific shortfall in MW and seconds. This is an advisory in Forecast/Dispatch-Advisory tier and a hard alert requiring operator acknowledgment in Supervised/Autonomous tiers, consistent with the parent spec's tiering model (Section 6) and NFR-4 safety-interlock requirement.

### 7.3 Worked example (documents the gap the original note left implicit)

A 20 MW LLM training job launches with Δt_lead = 30 seconds. Required turbine ramp time at the MVP default rate = 20 MW / 0.2 MW/s = 100 seconds — 70 seconds longer than the available lead time. Because the turbine begins ramping at job start (Section 7.2 step 1), not at T+30s, it has already reached 0.2 MW/s × 30s = 6 MW by the time the full 20 MW load lands. The shortfall the BESS must cover therefore starts at 20 − 6 = 14 MW at T+30s and declines linearly — not a flat 20 MW — to 0 MW by T+100s, per the arbitration formula in step 2 (BESS_output(t) = max(0, P_total(t) − turbine_output(t))). If the site's BESS cannot sustain a 14 MW discharge for up to 70 seconds (equivalently, roughly 0.14 MWh of usable energy across the declining ramp), the insufficient-reserve alert fires at T+0 (job start), giving the operator the remaining ~30 seconds of lead time to intervene manually (e.g., pre-empt a lower-priority job, accept a brief voltage/frequency excursion, or curtail).

## 8. Thermal Lag / Cooling Model

The original note asked for “a simple decay/delay function” without defining one. Resolved specification:

α(t) = α_max × (1 − e^−(t − t₀ − Δt_thermal) / τ) for t ≥ t₀ + Δt_thermal, else 0

Where t₀ is the compute step-load onset time, Δt_thermal is the delay before cooling begins responding at all (default 90s, configurable 60–120s per site per Section 9), α_max is the steady-state incremental cooling fraction (default 0.20, configurable range 0.10–0.30 per FR site data), and τ is a short rise-time constant (MVP default 20s) representing that chillers ramp up over tens of seconds rather than stepping instantly, since a discontinuous step is itself physically unrealistic and would falsely alias as a second instantaneous event to the dispatch controller. α_max and τ are both per-site configuration values with the defaults above applied until a site's own telemetry allows recalibration (Section 12).

This function is deliberately a first-order exponential rise, not a full thermodynamic model, per the original note's guidance that a simulator-grade approximation is sufficient for MVP.

### 8.1 Pre-cooling and the shiftable load class

Section 7.1 describes cooling as "not a dispatchable asset in the staging sense." That was accurate when cooling meant chillers reacting to heat that had already been produced. It is increasingly not, and the distinction matters because GridSignal is unusually well placed to exploit it: the engine knows a step-load is coming 30–60 seconds before it arrives, which is precisely the input a pre-cooling decision needs.

Three mechanisms make cooling partly dispatchable: lowering setpoints ahead of a predicted step-load, which uses building and coolant thermal mass as short-duration storage; chilled-water or ice thermal storage, which is the direct thermal analogue of BESS and has both a state of charge and a discharge duration; and coolant supply temperature, which trades cooling power against IT inlet temperature within a safe band.

**This introduces a third load class.** The specification now distinguishes firm load, curtailable load (Section 23), and shiftable load. Curtailment removes energy from the forecast; shifting moves it earlier. They are not interchangeable and they sit at different points in the response order — pre-staging happens ahead of the Section 26.4 arbitration ladder rather than inside it, because it reduces the size of the gap rather than closing a gap that already exists.

**Bounds.** Pre-cooling operates inside a configured inlet-temperature band and is never autonomous. The site building management system retains unconditional override, for the reason given in 19.6: GridSignal forecasts and pre-stages, the BMS controls, and a system that starts issuing chiller commands has abandoned the workload-aware position for the incumbent's ground.

### 8.2 Liquid cooling and the changing time constants

The Δt_thermal default of 90 s and the α(t) rise-time constant τ of 20 s were framed around chiller response with air-side thermal mass buffering the step. That regime is disappearing at the densities in Section 5.3. Current-generation liquid-cooled racks ship with fanless compute and switch trays, roughly double the coolant flow of the preceding generation, and rack airflow requirements reduced by approximately 80%.

The likely direction is that Δt_thermal shortens and α(t) rises more steeply, because a direct-to-chip loop couples more tightly and buffers less than an air path. The likely direction is not a substitute for measurement, and this is stated as a calibration priority rather than a new default: changing 90 s to a guess would replace a known-provisional value with a differently-provisional one. The Thermal agent (26.2) and console page (19.6) exist substantially to close this, and Section 15's calibration dependency now has a named instrument rather than only a dependency.

## 9. Time Constant Reconciliation

The original note used three overlapping, unreconciled time constants (Δt_lead, Δt_thermal, and the bare figure ‘90s’ that turned out to be a default, not a separate constant). This table is the single source of truth for those three plus one more — the BESS bridging window — which is not from the original note but is derived later in this document (Section 7.2) from the other three; none of the four should be used interchangeably in implementation.

| **Constant** | **Value** | **What it measures** | **Where used** |
|---|---|---|---|
| Δt_lead | 30–60s (site/job dependent) | Time from scheduler allocating a job to GPUs reaching full TDP | Determines when turbine ramp can begin (Section 6.1, 7.2) |
| Δt_thermal | 60–120s, default 90s | Time from compute spike to cooling system beginning to respond | Delay term in α(t) (Section 8) |
| τ (thermal rise time) | Default 20s | How quickly α(t) approaches α_max once cooling starts responding | Shape of α(t) (Section 8) |
| BESS bridging window | Derived: ΔP / r_asset − Δt_lead (when positive) | How long BESS must cover the gap between prediction lead time and turbine ramp completion | Insufficient-reserve check (Section 7.2) |

Δt_lead differs in kind from the other three constants in this table, and the difference is easy to miss because they are presented together. Δt_thermal, τ, and the bridging window are properties of physical plant. Δt_lead is not: it is the duration of a software process — container start, model weight load, and collective initialization — and it will change as that software changes. It is an engineering artifact, not a physical constant, and Section 15 records the consequence. The 90-second default used for Δt_thermal is the midpoint of the observed 60–120s range and is a starting configuration value, not a physical constant — it must be exposed as a per-site setting and recalibrated once a design-partner site provides measured chiller response data (parent spec Section 11, item 6).

## 10. Input Data Contract: WorkloadSignal Payload

Resolves the previously-unspecified requirement on what the Slurm/K8s/Ray integration must supply. Minimum required fields per WorkloadSignal event (parent spec data model, Section 7):

| **Field** | **Type** | **Required** | **Notes** |
|---|---|---|---|
| job_id | string | Yes | Stable identifier across the job's lifecycle events |
| event_id | string | Yes | Globally unique per event, producer-assigned; required for idempotent dedupe (Section 17.1) |
| event_type | enum | Yes | queued \| starting \| running \| scale \| checkpoint_start \| checkpoint_end \| job_end \| cancelled |
| timestamp | ISO-8601, UTC | Yes | Source-clock timestamp; see Section 11.4 for skew handling |
| hardware_profile_id | string | Yes | Keys into the hardware profile library (Section 5); unmapped values trigger the Section 5.1 fallback |
| node_count | integer | Yes | Active node/chassis count for this job at event time; a scale event carries the new count for an already-running job |
| workload_class | enum | Yes | training \| inference \| other — selects the load-signature model (Section 6) |
| site_id | string | Yes | Routes the event to the correct site's hardware library and lag configuration |
| queue_depth / request_rate | number | Conditional | Required for workload_class = inference to drive micro-ramp modeling (Section 6, row 2) |

**Two ingest event classes exist as of v2.3.** WorkloadSignal, specified below, is the engine's workload input and is dispatch-path eligible: it can change a forecast and therefore a control action. NetworkTelemetry (Section 25.2) is a second class with its own contract, its own clock requirement (11.4), and no path into the forecast. That exclusion is a property of the contract rather than a convention in prose — an adapter that routes NetworkTelemetry into the forecast path is not misconfigured, it is non-conforming. The two classes share the validation, quarantine, and idempotency machinery of Sections 17.1–17.2, because a second ingestion path with different rules would be a second set of bugs.

## 11. Edge Cases and Error Handling

### 11.1 Overlapping job launches

Multiple concurrent starting/running jobs are summed by superposition in P_compute(t) (Section 4.1, the Σᵢ term is per-job-instance, not per-hardware-profile-only). Dispatch arbitration (Section 7.2) operates on the aggregate predicted ΔP, not per-job, since generation assets serve the site load as a whole.

### 11.2 Job cancellation mid-ramp

A cancelled event before a job reaches running state removes that job's reserved node_count from the forecast immediately and, if assets have already begun staging in response to it, triggers a dispatch re-plan (parent spec FR-3.3) rather than allowing turbines to continue ramping toward a load that will not materialize.

### 11.3 Out-of-order or delayed events

Events are ordered by their timestamp field, not arrival order, within a 10-second re-ordering buffer at the ingestion layer. An event arriving with a timestamp older than the current buffer window is applied retroactively to the forecast history (for accuracy reporting, Section 12) but does not retroactively alter dispatch commands already issued.

### 11.4 Clock skew

Timestamp accuracy is not uniform across sources, and treating it as uniform discards precision where it exists while implying precision where it does not. Three source classes, with different requirements and different consequences:

| **Source class** | **Requirement** | **Discipline** | **What the bound limits** |
|---|---|---|---|
| Job scheduler (WorkloadSignal) | ±2 s | NTP | The Δt_lead advantage. Skew here erodes the lead time the entire system depends on, which is why the bound is tight relative to a 30–60 s window |
| Facility and asset telemetry (SCADA/BMS, OEM) | ±2 s | NTP | Correlation of measured power against forecast segments |
| Fabric telemetry (NetworkTelemetry) | Sub-microsecond where the platform supports it | IEEE 1588v2 PTP, SyncE | Phase discrimination within the fabric stream (25.5), which resolves transitions an NTP-bounded timestamp would average away |

**Cross-source correlation inherits the looser clock.** This is the rule most easily got wrong. A PTP-disciplined fabric source does not improve the accuracy of comparing a fabric event against a scheduler event — that comparison is bounded by the scheduler's ±2 s and nothing recovers it. Nanosecond discipline is therefore valuable for reasoning about transitions inside the fabric stream, where both timestamps come from the same clock domain, and provides no benefit to the corroboration role in 25.1, whose window is Δt_lead plus margin anyway. Specifying PTP and then assuming it tightens every comparison would be a quiet way to over-trust a correlation.

The ingestion layer flags and logs — but does not discard — events whose timestamp differs from ingestion-server receipt time by more than the source class bound, recording the skew magnitude for audit. Where a source declares PTP discipline but its observed skew is consistent with NTP, the declaration is treated as unreliable and the source is demoted to the NTP bound, since a false claim of precision is worse than an honest lack of it.

### 11.5 Unmapped hardware

See Section 5.1.

## 12. Confidence, Tolerance, and Accuracy Reporting

Point-estimate predictions (e.g., “+4.2 MW”) are insufficient for a controller making dispatch decisions with real cost/safety consequences. Per parent spec FR-1.3, every forecast segment carries a confidence interval. For the real-time staging loop specifically:
- Each P_total(t) prediction is reported with a ± percentage band, initialized from the hardware profile's data-quality tier (mapped hardware: tighter band; generic_fallback: wider band per Section 5.1) and narrowed over time using rolling forecast-error tracking (parent spec FR-1.5, MAPE per load type).
- A prediction whose confidence band would put the lower bound of required capacity above currently staged/available capacity triggers the same insufficient-reserve alert path as Section 7.2, using the band's lower bound rather than the point estimate — i.e., dispatch sizing is conservative by default, not optimistic.
- Effective PUE at steady state (PUE_base × (1 + α), Section 4.3 — where α has converged to α_max) should be checked against each site's measured/nameplate PUE at commissioning; a persistent divergence is a signal to recalibrate α_max, τ, or PUE_base for that site rather than evidence the model form is wrong.

## 13. Traceability to Parent Product Specification

| **This document** | **Parent spec requirement** |
|---|---|
| Section 4 (formula), Section 5 (hardware library) | FR-1.1 (ingest job-scheduler signals) |
| Section 6 (load signatures) | FR-1.2 (model load signatures per workload type) |
| Section 3.1 (evaluation cadence), Section 12 (confidence) | FR-1.3 (rolling forecasts with confidence intervals) |
| Section 6.2 (checkpoint-valley detection) | FR-1.4 (<30s spike detection lead time) |
| Section 12 (accuracy reporting) | FR-1.5 (per-site retraining, MAPE reporting) |
| Section 5.1 (unmapped hardware fallback) | FR-1.6 (graceful degradation) |
| Section 3.1, Section 7.2 | NFR-2 (latency) |
| Section 7.2 (insufficient-reserve alert) | NFR-4 (safety interlocks); Section 6 tiering (Advisory vs. Supervised/Autonomous) |
| Section 21.2, 21.6 (learning plane, promotion gate) | FR-1.5 (per-site retraining, MAPE reporting) |
| Section 21.1 (control/learning plane separation) | NFR-2 (latency); NFR-3/NFR-4 (safety interlocks) — the real-time path carries no model-inference dependency |
| Section 7.1.1 (non-dispatchable supply) | FR-3.3 (dispatch re-plan); FR-4.4 (asset mix what-if) |
| Section 22.2, 22.3 (storage tiers, restart reconstruction) | FR-1.6 (graceful degradation); FR-3.3 (dispatch re-plan on state disagreement) |
| Section 22.4, 22.5 (batching, residency, bucket ownership) | FR-2.5, NFR-5 (audit trail); parent spec Section 11 (deployment topology) |
| Section 23 (curtailment ladder, authority, interlocks) | NFR-3/NFR-4 (safety interlocks); Section 6 tiering; FR-3.3 (dispatch re-plan) |
| Section 24 (grid procurement) | FR-1.3 (15-minute–4-hour horizon forecast — first capability driven by it); FR-4.4 (asset mix economics) |
| Section 25 (network telemetry) | FR-1.5 (forecast-error attribution); FR-2.1 (Connector Fabric adapters); FR-1.6 (graceful degradation) |
| Section 26 (agentic architecture); Section 19 (console pages) | NFR-2 (latency — agents excluded from the control path); FR-4.3 (operator reporting) |
| Section 5.2, 5.3 (counting unit, vintage) | FR-1.1 (ingest scheduler signals); FR-1.6 (graceful degradation) |
| Section 8.1, 8.2 (pre-cooling, liquid recalibration) | FR-1.2 (load signatures); FR-1.5 (per-site retraining) |
| Section 27 (prescriptive maintenance, availability state) | FR-3.3 (dispatch re-plan); NFR-4 (safety interlocks); parent spec Section 11 (design-partner calibration) |
| Section 28.1–28.3 (control stack placement, execution layer, protocols) | FR-2.1–FR-2.3 (Connector Fabric adapters); NFR-2 (latency) |
| Section 28.4 (protective shed interlock); Section 7.1.2 (anchor reserve) | NFR-3/NFR-4 (safety interlocks); FR-3.3 (dispatch re-plan); FR-1.5 (error attribution) |
| Section 11.4 (clock classes); Section 25.3, 25.4 (signal tiers, export) | FR-2.1 (Connector Fabric adapters); FR-1.4 (spike detection lead time) |
| Section 25.6 (calibration limits) | FR-1.5 (per-site retraining, MAPE); Section 17.3 (calibration threshold) |

## 14. Resolution Log: Contradictions and Open Questions Closed

Each item below was raised against the original “Secret Sauce” note; each is now resolved in this specification.

| **#** | **Issue** | **Resolution** |
|---|---|---|
| 1 | PUE applied instantly while cooling modeled as delayed — double-count / contradiction | Split into PUE_base (instant, non-cooling) and α(t) (delayed, cooling-only) — Section 4 |
| 2 | Formula had no time variable | All terms explicit functions of t; 5-second evaluation tick defined — Section 3.1, 4 |
| 3 | Single scalar kW constant couldn't represent mixed fleet | Indexed hardware profile library, keyed by payload field — Section 5 |
| 4 | Three unreconciled time constants (30–60s / 60–120s / 90s) | Each given a distinct name, meaning, and default; reconciliation table — Section 9 |
| 5 | Lead-time-vs-ramp-time shortfall (e.g., 20 MW job, 30s lead, 100s ramp) not addressed | Insufficient-reserve alert computed at staging time; worked example — Section 7.2, 7.3 |
| 6 | No dispatch arbitration rule between BESS and turbines | Explicit staged rule: turbines ramp immediately, BESS covers shortfall, tapers on turbine catch-up — Section 7.2 |
| 7 | Checkpoint-valley flag had no quantitative trigger | Explicit thresholds (15% / 5–30s / 45s / 90%) plus authoritative scheduler-event path — Section 6.2 |
| 8 | Cooling-lag function f() left undefined (“simple decay/delay”) | First-order exponential rise with delay Δt_thermal and rise time τ — Section 8 |
| 9 | Required Slurm/K8s payload fields undefined | Data contract table with required/conditional fields — Section 10 |
| 10 | Unknown-hardware fallback undefined | Generic fallback profile + confidence-flagging + onboarding alert — Section 5.1 |
| 11 | PUE_site configuration source unspecified | Per-site config value, checked against nameplate/measured PUE at commissioning — Section 4.3, 12 |
| 12 | Edge cases (overlap, cancellation, out-of-order, clock skew) unaddressed | Explicit handling rules — Section 11 |
| 13 | Predictions given as bare point estimates with no tolerance | Confidence-band requirement, conservative-by-default dispatch sizing — Section 12 |

## 15. Residual Open Items (Cannot Be Resolved on Paper)

The following are not specification gaps but genuine dependencies on data not yet available; they are flagged here rather than closed with an assumption:
- **Calibration against measured data.** Δt_thermal, α_max, τ, and r_asset defaults are engineering placeholders. Parent spec Section 11 (item 6) and Section 8 (design-partner requirement) already identify that forecast-accuracy claims require live design-partner telemetry — this document's defaults should be treated as the initial simulator configuration, not validated constants, until at least one site's measured chiller and turbine response data is available.
- **Vendor-specific ramp rates.** r_asset = 1 MW/5s is a single MVP default across all turbine/engine makes; actual mechanical ramp rates vary by OEM and model. This should move into the same per-asset configuration mechanism as the hardware profile library (Section 5) once Connector Fabric OEM integrations (parent spec FR-2.1) are available to report or confirm nameplate ramp specs.
- **Inference micro-ramp model detail.** Section 6's inference row specifies the required output (±500 kW / ~10s) but not the request-queue-depth-to-power mapping function, since inference power draw is workload- and model-size-dependent in a way training draw is not. This requires its own sub-specification once inference telemetry from a design-partner site is available, and is intentionally not force-fit into this document's formula set.
- **In-flight state on engine restart.** Section 17.1's dedupe window and any active checkpoint-valley grace period (Section 6.2) or partially-staged dispatch (Section 7.2) are, as specified, in-memory/session state. Closed in Section 22.3. A restart is not a cold reset: this state is held in the Tier 0 control-plane store and reconstructed on startup, with measured asset state taking precedence over reconstructed intent wherever the two disagree. What remains open is redundancy rather than durability — a single appliance holding a single local store makes appliance loss a dispatch outage (Section 22.8, ST-2), which should be resolved together with the edge-appliance redundancy question rather than after it.
- **Configuration-change governance.** Section 17.3 treats moving a site out of uncalibrated_site — and, by the same logic, any future change to a site's α_max, τ, Δt_thermal, r_asset, or hardware profile library — as an auditable configuration change, but this document does not specify who may authorize such a change, what validation bounds apply (e.g., preventing an operator from setting α_max outside its stated 0.10–0.30 range by mistake), or how the change is surfaced for review. This is a real gap, not a deferred nicety: these parameters directly drive dispatch decisions.
- **GPU allocation granularity.** Section 10 defines node_count as an active node/chassis count, which assumes the scheduler allocates in whole nodes. Whether production AI schedulers allocate in whole nodes, in fixed cluster blocks, or at individual-GPU granularity is unresolved, and it matters: if a job can hold a fraction of a chassis, the Section 4.1 term Nodesᵢ(t) × kWᵢ overstates that job's draw, and the error is largest for exactly the high-density liquid-cooled profiles where a per-cabinet figure is largest. Resolving this may require a second quantity — allocated GPUs per node — in the WorkloadSignal contract, and a per-profile idle/base draw so a partially-allocated chassis is not modelled as drawing zero. Blocked on confirmation from a design-partner scheduler configuration; do not assume whole-node allocation in implementation without a flag that can be flipped.
- **Renewable supply seed parameters.** Section 7.1.1 establishes P_renewable(t) as a first-class supply term but does not fix default array sizing or an irradiance-to-MW conversion. Nameplate output varies with array area and with fixed versus tracking mounts, so a single default is not defensible; this needs either a small profile library on the pattern of Section 5 or a site-configured curve.
- **Learning-plane residuals.** Section 21.8 carries four open items (LP-2 through LP-5): approval authority for a learning promotion, hosted-inference cost ceiling, self-hosted inference licensing and sizing, and a statistical-significance floor before a Proposal may be generated. LP-2 is the sharpest of these — it is the same unresolved question as the configuration-change governance item above, and the two should be closed together rather than separately.
- **Secular compression of Δt_lead.** The 30–60 second lead time on which this entire specification depends is the interval between scheduler allocation and full GPU draw, and every component of it is under active industry optimization: container start-up, model weight loading from storage, and collective-communication warmup. Faster storage tiers, pre-staged and cached weights, checkpoint-restore, warm container pools, and faster collective libraries all push it down. The direction is not entirely one way — growing model sizes push weight-load time up, and it is not obvious which effect dominates — but the specification should not treat Δt_lead as a stable site characteristic when it is the output of a process someone is actively trying to make faster. Three things are needed and none exists: a measured Δt_lead per site rather than a configured range, a tracked trend for it over time, and a stated floor below which the staging premise no longer holds. The last is the important one, because it is the threshold at which this product stops working, and nobody has calculated it.

## 16. Addendum A: Acceptance Test Matrix

This addendum translates the thresholds and worked examples already defined in Sections 4–12 into a concrete set of acceptance test cases. Each test is stated as a scenario, an input, and an assertable expected result, so it can be implemented directly as a unit/integration test (synthetic WorkloadSignal traces) or a blackbox test against a running instance. Test IDs are grouped by the spec section they validate; none introduce new behavior — where a test implies a rule not yet written down, that rule is defined in Addendum B rather than invented here.

### 16.1 Core formula (Section 4, Section 8)

| **ID** | **Scenario** | **Input** | **Expected result** |
|---|---|---|---|
| TC-01 | Instantaneous compute term, single hardware profile | 10 nodes, profile enterprise_8gpu_air (10.2 kW), PUE_base = 1.03 | P_compute(t) = 10 × 10.2 × 1.03 / 1000 ≈ 0.1051 MW, within ±0.1% |
| TC-02 | Cooling term before thermal delay elapses | Job starts at t₀; evaluate at t₀ + 60s (< default Δt_thermal = 90s) | P_cooling(t) = 0 |
| TC-03 | Cooling term at steady state | Same job held constant ≥ Δt_thermal + 5τ (≥ 190s at defaults) | P_cooling(t) converges to α_max × P_compute within 2% of asymptote |
| TC-04 | Mixed fleet, two hardware profiles active simultaneously | 6 × enterprise_8gpu_air + 2 × nextgen_rack_liquid (126 kW) | P_compute(t) = Σ of both terms, not a single-scalar approximation |

### 16.2 Checkpoint-valley classification (Section 6.2)

| **ID** | **Scenario** | **Input** | **Expected result** |
|---|---|---|---|
| TC-05 | Explicit scheduler checkpoint event | checkpoint_start / checkpoint_end pair brackets a compute drop | Classified checkpoint (primary signal); staging held throughout |
| TC-06 | Heuristic positive match | 18% drop, 20s duration, recovers to 92% of pre-drop draw within 40s, no explicit event | Classified checkpoint (fallback signal) |
| TC-07 | Heuristic negative match (job end) | 15% drop, 30s duration, recovers to only 85% by 45s | Classified job_end; turbine ramp-down proceeds normally |
| TC-08 | Ambiguous case | 16% drop, no recovery and no job_end event by 45s | Status = uncertain; staging held for additional 30s grace period; dashboard flag set |
| TC-09 | Boundary condition, exact thresholds | Drop exactly 15.0%, duration exactly 30s, recovery exactly 90.0% at exactly 45s | Classified checkpoint (thresholds are inclusive, ≥/≤ as defined in Sec. 6.2, not strict >/<) |

### 16.3 Dispatch arbitration and insufficient-reserve alert (Section 7)

| **ID** | **Scenario** | **Input** | **Expected result** |
|---|---|---|---|
| TC-10 | Insufficient reserve (Sec. 7.3 worked example) | 20 MW job, Δt_lead = 30s, single turbine r_asset = 0.2 MW/s | Required ramp time = 100s > 30s lead → alert fires at T+0, reporting a 70s gap window with peak shortfall 14 MW at T+30s (20 MW load − 6 MW already-ramped turbine output), declining to 0 by T+100s — not a flat 20 MW |
| TC-11 | Sufficient reserve, no false alert | 5 MW job, Δt_lead = 60s, r_asset = 0.2 MW/s | Required ramp time = 25s < 60s lead → no alert issued |
| TC-12 | BESS shortfall coverage | During the TC-10 gap window | BESS_output(t) = max(0, P_total(t) − turbine_output(t)) at every tick, bounded by rated capacity/SOC |
| TC-13 | BESS taper on turbine catch-up | turbine_output(t) ≥ P_total(t) sustained for 10 consecutive seconds | BESS returns to standby/recharge within one tick of the 10s threshold being met |
| TC-14 | Alert tier behavior | Same TC-10 scenario, once in Forecast/Advisory tier and once in Supervised tier | Advisory tier: dashboard warning only. Supervised tier: hard alert requiring operator acknowledgment before further auto-dispatch per NFR-4. |

### 16.4 Hardware fallback and confidence (Section 5.1, Section 12)

| **ID** | **Scenario** | **Input** | **Expected result** |
|---|---|---|---|
| TC-15 | Unmapped hardware profile | hardware_profile_id not present in site library | generic_fallback rate applied; segment tagged low_confidence: unmapped_hardware; one onboarding alert emitted per unique unmapped ID per site |
| TC-16 | Confidence band widens on fallback | Equal node_count, once with mapped profile and once with generic_fallback | Fallback case reports a strictly wider ± confidence band than the mapped case |
| TC-17 | Conservative dispatch sizing | Confidence interval's lower bound of required capacity exceeds currently staged capacity, even though the point estimate is covered | Insufficient-reserve alert still fires, evaluated against the lower bound, not the point estimate |

### 16.5 Event ordering and clock integrity (Section 11.3, 11.4)

| **ID** | **Scenario** | **Input** | **Expected result** |
|---|---|---|---|
| TC-18 | Out-of-order event within buffer | Event timestamped 6s before the latest applied event, arrives within the 10s reordering buffer | Reordered and applied in timestamp order; forecast state reflects correct sequence |
| TC-19 | Late event outside buffer | Event timestamp is >10s older than current buffer window at arrival | Applied retroactively to forecast history/accuracy tracking only; already-issued dispatch commands unchanged |
| TC-20 | Clock skew flag | Event timestamp differs from ingestion receipt time by >5s | Event flagged and logged, not discarded; skew magnitude recorded for audit |

### 16.6 Idempotency, malformed input, and cold start (Addendum B)

| **ID** | **Scenario** | **Input** | **Expected result** |
|---|---|---|---|
| TC-21 | Exact duplicate event | Identical event_id redelivered | Second occurrence discarded; no double-count of node_count; no duplicate alert |
| TC-22 | Retried event, mutated timestamp | Same event_id redelivered with a different timestamp (e.g., producer-side retry) | Still deduped by event_id; first-seen timestamp is retained as authoritative |
| TC-23 | Missing required field | Event missing hardware_profile_id | Quarantined at ingestion; job's node contribution treated as 0 MW and tagged low_confidence: invalid_payload until a corrected event arrives |
| TC-24 | Out-of-range value | node_count = −3 | Rejected at ingestion; structured error returned to source; job quarantined as in TC-23 |
| TC-25 | Invalid enum value | event_type = “pasued” (typo / unrecognized) | Rejected and quarantined; ingestion pipeline continues processing other events without interruption |
| TC-26 | Cold-start default configuration | New site_id with no prior calibration record | Engine uses MVP global defaults (Δt_thermal=90s, α_max=0.20, τ=20s, r_asset=0.2 MW/s); all forecasts tagged uncalibrated_site |
| TC-27 | Calibration transition | Site accumulates ≥ calibration threshold of reconciled measured events (Addendum B.3) | uncalibrated_site tag removed; site-specific calibrated parameters applied to subsequent forecasts |

### 16.7 Learning plane, plane separation, and non-dispatchable supply (Section 7.1.1, Section 21)

| **ID** | **Scenario** | **Input** | **Expected result** |
|---|---|---|---|
| TC-28 | Learning plane unavailable | All hosted model endpoints unreachable for a sustained 30-minute window while jobs start, run, and complete | Control plane continues without degradation: forecasts, dispatch arbitration, and insufficient-reserve alerts all produced on the last-applied parameter set. Only new Proposal generation stops. No forecast is delayed past the Section 3.1 5-second tick |
| TC-29 | Data-residency boundary | Any outbound hosted-model request, captured at the egress boundary | Payload contains no site_id, job_id, customer identifier, or hardware profile SKU name. A request bypassing the transformation layer fails the test — this is a defect, not a warning |
| TC-30 | Out-of-bounds proposal rejected at generation | Learning plane derives α_max = 0.42 (outside the 0.10–0.30 range) | Proposal auto-rejected at generation time, never enters the review queue, logged as a learning-plane data-quality event |
| TC-31 | Promotion gate holds | A valid in-bounds Proposal is generated and left un-actioned for 24 hours | Dispatch behavior over that window is bit-identical to a control run with the learning plane disabled. Proposal state remains under_review |
| TC-32 | Promotion applied mid-ramp | A Proposal is approved while a job is actively ramping | In-flight prediction is not recomputed under new parameters; new values apply only to forecasts issued after approval, per Section 17.3. Audit record carries reviewer identity and timestamp |
| TC-33 | Renewable shortfall equivalence | Run A: +6 MW compute step, flat renewable output. Run B: flat compute, −6 MW step loss of renewable output | Both produce the same +6 MW ΔP in P_dispatch_required(t) and the same staging response and reserve check. Run B is evaluated at Δt_lead = 0; renewable output is never credited toward ramp capability in the step 4 shortfall calculation |

### 16.8 Persistence, restart, and storage tiers (Section 22)

| **ID** | **Scenario** | **Input** | **Expected result** |
|---|---|---|---|
| TC-34 | Restart inside the dedupe window | Event E processed; engine restarted 3 minutes later; E redelivered with its original event_id | E is rejected as a duplicate. node_count is not double-counted and no duplicate alert is emitted — identical outcome to TC-21 with no restart |
| TC-35 | Restart mid-grace-period | A job is in the Section 6.2 uncertain state with 20 s elapsed against the 30 s grace period; engine restarted; restart completes in 5 s | Grace period resumes with elapsed time preserved and expires 10 s after restart, not 30 s. Staging is held throughout. The dashboard uncertain flag survives the restart |
| TC-36 | Reconstructed intent contradicts measured state | Tier 0 records a turbine ramp in progress; on restart the asset reports idle | Measured state wins. A dispatch re-plan is triggered per FR-3.3; the pre-restart command is not blindly re-issued. Divergence is logged |
| TC-37 | Analytical/archival tier unreachable | Object storage endpoint unreachable for 24 hours under normal job load | Control plane and Tier 1 unaffected: forecasts, dispatch, alerts, and audit writes all continue. Batches accumulate on local disk and drain on reconnect with no duplicates |
| TC-38 | Backlog pressure during extended outage | Unsynced local backlog exceeds the configured fraction of available local storage | Operator alert raised. Oldest analytical batches are dropped in preference to Tier 0 state or blocking ingestion; audit records are never dropped |
| TC-39 | Batched writes, not per-event | 10,000 events ingested within one batch interval | Object-store write operations are bounded by batch count, not event count. One PUT per event is a defect |
| TC-40 | Analytics bucket residency | Contents of the GridSignal-owned analytics bucket after a full day of operation | No site_id, job_id, customer identifier, or hardware SKU name present in any object or key. Same boundary as TC-29, enforced at rest rather than in flight |

### 16.9 Curtailment, procurement, network telemetry, and agents (Sections 23–26)

| **ID** | **Scenario** | **Input** | **Expected result** |
|---|---|---|---|
| TC-41 | Curtailment ladder ordering | Predicted uncoverable gap of 3 MW; Tier A and B together yield 4 MW | Only Tiers A and B are invoked. No suspend or preempt command is composed while lower-tier headroom remains |
| TC-42 | Ladder C/D never autonomous | Site in Autonomous tier; predicted gap resolvable only by preemption | No preempt command issues without explicit human confirmation. An alert is raised naming the affected jobs and the residual shortfall |
| TC-43 | Degraded forecast does not curtail | Predicted gap derived from a segment tagged low_confidence: invalid_payload | No autonomous curtailment at any ladder tier. Operator confirmation is required, and the tag is shown in the confirmation |
| TC-44 | Hysteresis prevents oscillation | Curtailment relieves the shortfall, which removes its own justification, sustained over 10 minutes | Curtailment holds for the minimum dwell time and restores only when forecast headroom exceeds restored load by the configured margin. No more than one reversal per dwell period |
| TC-45 | Dead-man expiry | Curtailment active; GridSignal-to-scheduler connection lost and not restored before expires_at | The scheduler reverts the action unilaterally at expiry. Curtailment does not persist through the partition |
| TC-46 | Restoration is staged, not instantaneous | Curtailed load is authorized for restoration | Restoration is treated as a predicted step-load and staged through the Section 7 path, with Δt_lead applied. Load is not restored faster than generation can follow |
| TC-47 | Non-firm import is not counted as reserve | Reserve check with firm capacity 5 MW, held reservation 3 MW, and 4 MW of spot import presently flowing | Only 8 MW is credited toward coverage. The 4 MW spot import reduces served load but does not close the reserve gap |
| TC-48 | All agents stopped | Every agent in 26.2 halted for a full scenario run | Dispatch behavior is bit-identical to a run with agents present but recommendations un-actioned. Forecasts, staging, and alerts unaffected |
| TC-49 | Inter-agent arbitration is deterministic | One shortfall; Generation, Procurement, Compute, and Storage all publish recommendations. Run twice with identical inputs | Identical selection both times, following the 26.4 order. Selection is reproducible from the recommendation set alone |
| TC-50 | Network telemetry has no dispatch path | Fabric traffic rises sharply with no preceding WorkloadSignal | No forecast change and no staging action. A missed-job corroboration finding is recorded for 21.2 attribution |
| TC-51 | Corroboration cannot override a primary signal | Explicit scheduler checkpoint_start event; fabric signature suggests job end | Classified checkpoint. The scheduler event is authoritative per 25.3; the disagreement is logged |
| TC-52 | Procurement never autonomous | Site in Autonomous tier; a valid in-bounds ReservationProposal is generated | No purchase occurs without explicit authorization. Proposal remains in under_review indefinitely or until it expires |

### 16.10 Profile generations, thermal, and prescriptive maintenance (Sections 5, 8, 27)

| **ID** | **Scenario** | **Input** | **Expected result** |
|---|---|---|---|
| TC-53 | Counting-unit mismatch | WorkloadSignal reports node_count in dies against a profile declaring cabinet | Quarantined as a domain validation failure per 17.2. No silent conversion is performed in either direction |
| TC-54 | Stale profile flagged | Active profile whose vintage exceeds the configured staleness age | Rendered stale on the console; confidence band widened on every segment the profile contributes to |
| TC-55 | Tier B applies per job, not per device | Curtailment targets a synchronized training job; capping a subset would nominally meet the shortfall | The cap is applied to every participant of the job or to none. No partial-job cap is composed |
| TC-56 | Pre-cooling bounds and BMS override | Pre-cooling staged ahead of a predicted step-load; BMS asserts override mid-stage | Setpoint change stays inside the configured inlet-temperature band and yields immediately to the BMS. Override is logged, not contested |
| TC-57 | Thermal divergence proposes, does not act | Measured Δt_thermal diverges persistently from configured | A calibration Proposal is raised through the 21.6 gate. No autonomous change to Δt_thermal, α_max, or τ occurs |
| TC-58 | Degraded asset counted at re-rated capability | Turbine with an applied re-rating from 0.2 to 0.15 MW/s; reserve check run | Reserve arithmetic uses 0.15 MW/s. The asset is neither excluded nor counted at nameplate |
| TC-59 | Maintenance window validated across its full duration | Proposed four-hour window beginning in a demand trough and ending during a forecast 20 MW step-load | Window rejected. Validation covers the whole duration against forecast demand, not the start instant |
| TC-60 | Rating increases require stronger evidence | Two proposals with equal observation counts: one lowering r_asset, one raising it | The lowering proposal follows the ordinary 21.6 path. The raising proposal requires the longer observation window and explicit confirmation per 27.5 |

### 16.11 Execution layer, anchor constraint, and protective interlock (Sections 7.1.2, 28)

| **ID** | **Scenario** | **Input** | **Expected result** |
|---|---|---|---|
| TC-61 | Anchor-adjusted bridging capability | Islanded site, BESS is grid-forming anchor with a configured P_anchor_reserve; reserve check run against a predicted step-load | Bridging capability is reduced by P_anchor_reserve. The insufficient-reserve alert fires at the adjusted figure, not at rated capacity and state of charge |
| TC-62 | Anchor role changes with operating mode | Same site transitions from grid-connected to islanded while a forecast is active | P_anchor_reserve goes from zero to its configured value and subsequent reserve checks reflect it. In-flight predictions are not silently recomputed per Section 17.3 |
| TC-63 | Anchor reserve defaults conservatively | New site with no P_anchor_reserve configured, operating islanded | A conservative non-zero default applies and the forecast is tagged. The value does not default to zero |
| TC-64 | No double-shed after a protective event | Protective fast load shed fires; GridSignal observes the resulting discontinuous load drop | No curtailment command is composed in response. The engine enters reconciliation and re-plans against measured state per FR-3.3 |
| TC-65 | Priority divergence surfaced at commissioning | GridSignal curtailment priority order disagrees with the power management system shed priority | Divergence reported as a commissioning defect. The power management system order is treated as authoritative and GridSignal does not override it |
| TC-66 | Shed events feed error attribution | A protective shed occurs at a site in normal operation | Event recorded and delivered to the Section 21.2 forecast-error attribution workstream as a predictive-staging failure |
| TC-67 | Open-transition discontinuity in the reserve check | Grid-connected site with open-transition grid-tie loses utility supply while a step-load is staged | Reserve check treats the transition as a coverage discontinuity to be ridden through, not as a smooth capacity reduction |
| TC-68 | GridSignal issues no protection-layer commands | Full scenario run with every integration surface active, commands captured at the egress boundary | No islanding, synchro-check, anti-islanding, droop, or protective-shed command is issued. Outputs are advisories and staging setpoints only |

### 16.12 Clock classes, fabric signal tiers, and calibration limits (Sections 11.4, 25)

| **ID** | **Scenario** | **Input** | **Expected result** |
|---|---|---|---|
| TC-69 | Cross-source correlation inherits the looser clock | PTP-disciplined fabric event correlated against an NTP-bounded scheduler event | Correlation uncertainty is reported at the scheduler bound. No result claims accuracy better than the loosest clock in the comparison |
| TC-70 | False precision demoted | Source declares PTP discipline; observed skew is consistent with NTP | Source demoted to the NTP bound. Declaration is logged as unreliable and the tighter bound is not applied to any downstream use |
| TC-71 | Baseline-tier platform degrades roles, not ingestion | Platform providing utilization and error counters only; adapter declares baseline tier | Corroboration and fabric operations remain available. Phase discrimination is reported unavailable. Ingestion continues and no forecast is affected |
| TC-72 | Emission mode reported with the data | Source emitting at a 30-second sample interval | Interval is carried in the payload. A consumer requiring sub-second resolution reports the signal as insufficient rather than treating quiet periods as measured absence |
| TC-73 | Throughput is not a magnitude proxy | Fabric telemetry corroborates a predicted step-load; no measured power is available for the same window | The event may be recorded as corroborated but does not count toward the Section 17.3 reconciliation threshold. The site does not exit uncalibrated_site |
| TC-74 | NetworkTelemetry is dispatch-path ineligible by contract | Adapter attempts to route a NetworkTelemetry event into the forecast path | Rejected as non-conforming, not as misconfigured. No forecast state is modified and the attempt is logged |

### 16.13 Adaptive ramp relaxation (Section 23.7)

| **ID** | **Scenario** | **Input** | **Expected result** |
|---|---|---|---|
| TC-75 | Relaxation requires confirmed headroom | Job start with ample nominal headroom, but the governing forecast segment carries low_confidence: unmapped_hardware | No relaxation issued. The site baseline ramp policy applies unchanged. Relaxation requires a reserve check passing against the band lower bound, not merely the absence of a warning |
| TC-76 | Forecast loss falls back to the static policy | GridSignal becomes unavailable while a relaxation is in force | The relaxation lapses and the site baseline ramp policy resumes. The failure direction is toward the conservative pre-installation behavior, never toward an unramped start |

## 17. Addendum B: Idempotency, Malformed-Input, and Cold-Start Handling

These rules were identified as missing during spec review: the original document assumed well-formed, single-delivery, already-calibrated input. This addendum defines the missing behavior precisely enough to implement and test against (Section 16.6 above).

### 17.1 Idempotency

**Contract change:** this addendum is the reason the Section 10 WorkloadSignal payload includes event_id (string, globally unique per event, producer-assigned) as a required field — timestamp-based deduplication alone is not reliable, since a legitimate retry may carry a corrected or updated timestamp.

**Dedupe key:** (site_id, job_id, event_type, event_id). The ingestion layer maintains a rolling window of recently-seen dedupe keys (MVP default: 15 minutes, sized to comfortably exceed any expected retry interval).
- On a duplicate event_id for an already-processed key: the event is discarded before it reaches the forecast state machine. No node-count double-count, no duplicate dispatch action, no duplicate alert.
- If a duplicate arrives with a different timestamp or payload body than the original (e.g., a producer bug), the original is retained as authoritative and the mismatch is logged as a data-quality warning — it is not silently accepted as a correction, since a corrected value should arrive as a new event_id with an explicit relationship to the original, not an overwrite.
- The dedupe window is a memory/state-store concern, not a business-logic one: it must survive an engine restart. The dedupe window is Tier 0 state (Section 22.2); its durability and its reconstruction on startup are specified in Section 22.3, which requires that a restart occurring inside the 15-minute window still reject a duplicate rather than admit it.

### 17.2 Malformed and invalid input

Validation happens at ingestion, before an event reaches the forecast/dispatch state machine. Two independent checks apply:
- **Schema validation:** all required fields from Section 10 (including event_id, added to the contract per 17.1) must be present and correctly typed. A missing or wrong-typed field fails schema validation.
- **Domain validation:** field values must be within defined bounds — e.g., node_count ≥ 0; event_type must be one of the enumerated values in Section 10; timestamp must parse as valid ISO-8601. A value that is well-typed but out-of-domain (node_count = −3) fails domain validation.

**On validation failure (either kind), the engine shall:**
- Quarantine the event: it is logged in full (for debugging and audit) but not applied to any forecast, dispatch, or confidence calculation.
- Return a structured rejection to the source integration (field name, validation rule violated) rather than a silent drop, so the Connector Fabric adapter (parent spec FR-2.1–FR-2.3) can surface it to an integrator during commissioning rather than it surfacing only as an unexplained forecast gap in production.
- Treat the affected job's contribution as 0 MW and tag any forecast segment touching that job window as low_confidence: invalid_payload, using the same confidence-widening mechanism as the unmapped-hardware case (Section 5.1, Section 12), until a corrected event for that job_id is received.
- Never crash or stall the ingestion pipeline on a single malformed event: validation failures are per-event and must not block processing of subsequent, valid events from the same or other jobs.

### 17.3 Cold start (uncalibrated site)

Sections 4, 7, and 8 define default parameter values (PUE_base, α_max, τ, Δt_thermal, r_asset) as MVP starting points pending per-site calibration (Section 15 already flags this as a residual dependency on design-partner data). This addendum defines the mechanical lifecycle of that state, not the calibration methodology itself, which remains future work.
- **Default state:** every newly onboarded site_id starts in an uncalibrated_site state and uses the MVP global default parameter set for every formula in Sections 4–8. No site-specific override is assumed to exist until explicitly set.
- **Tagging:** every forecast produced for a site in uncalibrated_site state carries an uncalibrated_site data-quality tag, using the same mechanism as low_confidence: unmapped_hardware and low_confidence: invalid_payload — these three tags are independent and can co-occur on the same forecast segment.
- **Confidence impact:** the confidence-band calculation (Section 12) treats uncalibrated_site as its own widening factor, applied in addition to (not instead of) any hardware- or payload-driven widening already in effect.
- **Calibration threshold (placeholder, not final):** a site transitions out of uncalibrated_site once it has accumulated a minimum number of reconciled step-load observations against measured ground truth — MVP placeholder threshold: 20 distinct step-load events ≥ 1 MW with corresponding measured power data. The exact number is a tuning parameter, not a resolved constant, and should be revisited once design-partner data is available (Section 15).
- **Transition is explicit, not silent:** moving a site out of uncalibrated_site (and thereby changing which parameter values drive live dispatch decisions) is treated as a configuration change subject to the same audit trail as any other control-relevant parameter change — full governance of that audit trail is intentionally out of scope here and remains a residual item (Section 15's config-management gap).
- **No mid-window parameter switch:** if a site is recalibrated while a job is actively ramping, the new parameters apply to forecasts issued after the transition; an in-flight prediction is not silently recomputed under new parameters mid-ramp, to avoid a dispatch discontinuity.

## 18. System Architecture: Component and Data-Flow Description

This section is the verbal companion to the architecture diagram (GridSignal-Architecture-Diagram.mermaid, Figure 1 below), walking through every component and relationship shown there. It complements Section 2's IP summary and Section 13's requirement traceability by describing how the pieces fit together mechanically — what calls what, in what order, and why each connection exists.

![figure-1-architecture](media/figure-1-architecture.jpg)

*Figure 1. GridSignal Forecast Engine architecture — component and data-flow diagram. Cylinders denote persisted Data Model entities (parent spec Sec 7); colored clusters denote the compute/control components described in Sections 4–8. Source: GridSignal-Architecture-Diagram.mermaid.*

### 18.1 External systems → Ingestion

Three independent external sources feed the pipeline, and they do not all go through the same door. The Job Scheduler (Slurm/K8s/Ray) and SCADA/BMS Telemetry both flow into Schema + Domain Validation first — every event from either source, whether it is a job-queue signal or a facility telemetry reading, is checked against the WorkloadSignal contract (Section 10, extended by Section 17.1–17.2) before it is trusted. The Generator/BESS OEM APIs, by contrast, do not produce WorkloadSignal events at all — they report asset state and capability (rated output, current state of charge, operating limits), so they write directly into the Asset entity in the data model rather than passing through the workload-validation path. This is a deliberate asymmetry: workload telemetry is high-frequency, job-shaped, and needs validation before it can affect a forecast; asset telemetry is closer to slowly-changing configuration.

Inside ingestion, validation branches two ways. A pass moves the event to the Idempotency Check, which deduplicates by event_id (Section 17.1) so a retried or redelivered event does not get counted twice. A fail routes the event to the Quarantine Store instead (Section 17.2) — it is logged for debugging but never touches a forecast, and a notification carries out to the Operator Dashboard so a bad integration gets surfaced during commissioning rather than silently degrading forecast quality in production. Only events that clear both checks become a persisted WorkloadSignal.

### 18.2 WorkloadSignal → Forecast Engine

The WorkloadSignal entity is the handoff point between ingestion and computation — once an event is validated and deduped, it is durable state, not just a message in flight. From there it flows into the Hardware Profile Library (Section 5), which is the first computational step: every WorkloadSignal carries a hardware_profile_id, and this is where that identifier gets resolved into an actual rated power draw (or, if unmapped, falls back to the generic profile per Section 5.1 and gets flagged).

That resolved power figure feeds the Workload-to-MW Formula (Section 4), which is the core of the Forecast Engine — it is where P_compute(t) and the lagged P_cooling(t) term (Section 8) actually get computed. For training-class jobs specifically, the formula's output also passes through the Checkpoint-Valley Classifier (Section 6.2), and this relationship runs both ways: the classifier watches the formula's draw trace for the shape of a checkpoint dip, but its verdict (checkpoint vs. job-end vs. uncertain) feeds back into the formula's own state, since a misclassified checkpoint would otherwise show up as a false step-down in the power prediction itself.

Everything the formula and classifier produce then passes through the Confidence / Calibration Engine (Section 12, Section 17.3) before it is allowed to become a Forecast. This is the stage that applies the uncalibrated_site widening for new sites, the low_confidence: unmapped_hardware widening from the profile library, and the low_confidence: invalid_payload widening for anything touched by a quarantined event — so a Forecast is never just a point estimate; it always carries whatever confidence penalties its inputs earned along the way.

### 18.3 Forecast and data model → Dispatch Advisor

The Forecast entity is where the engine's output becomes persisted, queryable state — and it is also where the Dispatch Advisor picks up. The Dispatch Arbitrator (Section 7.2) does not act on the Forecast alone: it also pulls directly from Site and Asset, because staging a response requires knowing not just how much power is coming, but what is physically available to meet it (which turbines are online, their ramp rates, current BESS state of charge, site-level reserve-margin constraints). The Forecast tells the Arbitrator what is coming; Site and Asset tell it what it has to work with.

The Arbitrator's decision splits into two outputs. The primary path produces a DispatchPlan — the ranked, staged sequence of actions (turbine ramp starting immediately, BESS covering the shortfall, BESS tapering as turbines catch up, per Section 7.2 steps 1–3). The secondary path is conditional: if the Arbitrator's own shortfall calculation shows the required ramp time exceeds available lead time and bridging capacity (Section 7.2 step 4, worked example in 7.3), it emits an Insufficient-Reserve Alert directly to the Operator Dashboard — this bypasses the DispatchPlan entirely because it is a warning about a gap the plan cannot close on its own, not an executable action.

### 18.4 DispatchPlan → Physical layer

A DispatchPlan does not touch hardware directly. It is translated into individual ControlEvent records first — this is the audit boundary (parent spec FR-2.5, NFR-5): every command that reaches a physical asset exists as an immutable, logged event before it is dispatched, which is what makes the system's actions reconstructable after the fact. From ControlEvent, commands fan out to the physical asset classes — reached in practice through the switching and protection devices catalogued in Section 28.2 rather than commanded directly: BESS, Turbines/Engines, Cooling System, and Grid-tie. Notably, the Cooling System sits in this same physical layer even though nothing in the Forecast Engine treats it as a dispatchable asset the way turbines and BESS are — it receives commands (or at minimum, provisioning signals) as a consequence of the P_cooling(t) term, but the arbitration logic upstream does not ramp it the way it ramps generation assets (Section 7.1).

### 18.5 Data model → Scenario Planner

Separately from the real-time control loop, Forecast and Asset both feed the Scenario Planner, which in turn produces Scenario records and reports back out to the Operator Dashboard (as VP-of-Infrastructure-facing reports rather than operational alerts, per parent spec FR-4.3). This is the one relationship in the architecture that is not part of the real-time control loop — it is what lets the same cost/asset model used for live dispatch also answer “what if we added more BESS instead of a second turbine” (parent spec FR-4.4), using actual operational history rather than assumptions.

### 18.6 The one structural relationship

The Site→Asset ownership link is different in kind from every other relationship described above — it is not a data flow, it is a static ownership relationship (a Site has one or more Assets, per the parent spec's data model, Section 7). It is included so the architecture does not imply Asset records appear from nowhere; an Asset belongs to a Site from the moment it is configured, independent of any runtime event.

## 19. Operator Console: Page Structure and Reference Mockup

The Operator Dashboard is the terminus of the architecture in Section 18 — it is where the Insufficient-Reserve Alert (Section 7.2), the Quarantine notification (Section 17.2), and the Scenario Planner's reports (parent spec FR-4.3) all converge. Figure 2 below is a high-fidelity reference mockup of that surface for the Facility/Energy Operations Manager persona (parent spec Section 2.3), grounded directly in this document's numbered sections rather than placeholder content.

As of v2.0 the console is a set of pages rather than a single screen. The single-screen mockup below remains the landing page; the pages added around it exist because Sections 23–26 introduce asset classes and actions that have no home on a one-screen summary, and because Section 21.6 requires a review queue that did not previously exist anywhere in this document.

**One rule governs every page.** A page may display anything. A page may only offer a control where this specification defines the authority under which that control acts. Every control surface named below traces to a tier rule in Section 7.2, 23.4, 24.4, or 26.3 — a control with no authority definition is not implementable, and should not be drawn.

### 19.1 Console page inventory

| **Page** | **Purpose** | **Specified in** | **Control surface** |
|---|---|---|---|
| 1. Site Overview | Landing page. Predicted step-load, staged response, active alerts, at-a-glance asset reserve | Sec 4, 7, 12 (mockup below) | Alert acknowledgment only |
| 2. Compute & Workload | Job inventory, node and GPU allocation state, per-job draw, curtailment eligibility and ladder position | Sec 6, 10, 23 | Curtailment actions, gated per 23.4 |
| 3. Energy Storage | BESS state of charge, power and energy rating, bridging capability, cycle count and health | Sec 7.1, 7.2, 9 | Charge-mode selection, gated |
| 4. Generation & Supply | Turbine fleet state and runtime, solar output against forecast, cooling pre-staging | Sec 7.1, 7.1.1, 8 | Turbine start/stop, gated. Solar is read-only by construction |
| 5. Thermal & Cooling | Thermal headroom, measured versus modeled α(t) and Δt_thermal, CDU and loop state, pre-staging record | Sec 8, 8.1, 8.2, 19.6 | Bounded pre-cooling staging. BMS retains override |
| 6. Grid & Procurement | Firm capacity, active and pending reservations, price curve, import against contract | Sec 24 | Reservation authorization — never autonomous |
| 7. Network Telemetry | Optical switch throughput, link and optical health, forecast corroboration record | Sec 25 | None. Read-only by design — see 25.1 |
| 8. Proposals & Learning | The Section 21.6 queue: every agent recommendation and calibration proposal, with evidence | Sec 21.6, 26.3, 27.5 | Approve / reject, with reviewer identity recorded |
| 9. Scenario Planner | What-if analysis over persisted history | Sec 18.5, parent FR-4.3/4.4 | Scenario authoring and execution |

### 19.2 Page 1 — Site Overview

![figure-2-operator-dashboard](media/figure-2-operator-dashboard.png)

*Figure 2. Operator Dashboard reference mockup. Source: GridSignal-Operator-Dashboard-Mockup.html (interactive).*

Panel-by-panel correspondence to this specification:
- **Alert dock:** renders the Section 7.2/7.3 insufficient-reserve alert using the same job parameters as the worked example (20 MW step, 30s lead, 100s required ramp) and an acknowledge control, consistent with the Supervised-tier acknowledgment requirement in Section 7.2 step 4. The mockup's specific BESS-bridging and residual-shortfall figures (62s / ~8s / 3.1 MW) illustrate a site with partial BESS coverage and are independent of — not a restatement of — the worked example's own numbers, where the peak shortfall is 14 MW declining over the full 70-second gap (Section 7.3). A real dashboard would show whichever figures the site's actual BESS capacity produces.
- **Hero countdown:** dramatizes the Δt_lead window (Section 6.1, Section 9) as a live countdown to GPU full-TDP, with the predicted magnitude and confidence interval (Section 12) shown alongside it.
- **Site power forecast panel:** plots P_compute(t), P_cooling(t), and P_total(t) (Section 4) with the two-stage rise described in Section 8 — compute settling by T+30s, the cooling term visibly beginning its rise at the T+90s marker — plus the confidence band from Section 12.
- **Asset reserve panel:** shows the asset classes from Section 7.1 in the roles the arbitration rule assigns them: BESS bridging, turbines ramping, cooling pre-staging, grid-tie idle while islanded. The mockup predates the v1.7 addition of non-dispatchable renewable supply (Section 7.1.1) and the v2.0 addition of curtailable load and reserved grid import (Section 7.1), and does not show them; Figure 2 requires regeneration alongside Figure 1.
- **Active workloads table:** surfaces job-level state from Section 6 (running / checkpoint / ramping) and renders the low_confidence data-quality tags from Section 5.1 and Section 17.3 (unmapped_hardware, uncalibrated_site) as inline flags rather than hidden metadata.
- **Dispatch arbitration timeline:** uses the same structure as the Section 7.3 worked example — BESS, turbine, and cooling bars against a T+0 to T+120s axis, with the shortfall segment visually called out — but, per the note above, the mockup's specific shortfall figures are illustrative and do not match Section 7.3's numbers exactly.

This mockup is a design reference, not a build specification — it establishes information hierarchy and terminology consistent with this document, but interaction details, responsive behavior, and exact componentry remain implementation decisions for the team building the dashboard.

### 19.3 Page 2 — Compute & Workload

Extends the landing page's active-workloads table into the inventory and control surface required by Section 23. Panels: node and accelerator allocation by hardware profile, with unmapped profiles flagged per Section 5.1; per-job draw and priority class; curtailment eligibility, showing which jobs site policy has marked curtailable and at which ladder tier (23.2); and a curtailment ladder view showing, for the current predicted shortfall, how much load each tier would shed and at what cost in job hours.

**The restoration asymmetry must be visible on this page, not buried.** Curtailment takes seconds; restoring a preempted job costs a full Δt_lead plus checkpoint reload. An operator shedding load needs to see the cost of putting it back before acting, or the page has encouraged a decision it did not inform.

### 19.4 Page 3 — Energy Storage

The organizing question for this page is not how full the battery is but how much time it buys. Three quantities, kept distinct because conflating them is the specific error Section 7.2 step 4 warns against: power rating in MW, energy capacity in MWh, and state of charge as a percentage.

**Primary readout — bridging capability.** The Section 9 BESS bridging window evaluated against present state of charge and the largest step-load currently forecast: the number of seconds of cover available before generation must have caught up, and whether that exceeds the required ramp time. This is the number that answers "does the battery give generation enough time to react," and it is the same arithmetic that fires the insufficient-reserve alert — surfaced continuously rather than only at alert time.

Secondary panels: charge/discharge history against forecast, cycle count and depth-of-discharge distribution, cell/bank thermal state, and degradation trend against nameplate. Charge-mode selection is a gated control, because deliberately charging during a predicted step-load window reduces bridging capability at the moment it is most needed.

### 19.5 Page 4 — Generation & Supply

Turbine fleet: per-unit online state, output, measured ramp rate against the configured r_asset, runtime hours, and time since last start. Start and stop are gated controls; a start command is a supervisory control action subject to NFR-3/NFR-4 interlocks and is never issued by an agent without authorization (26.3).

Solar: measured output against forecast, per-string or per-inverter fault state from panel telemetry, and the contribution of P_renewable(t) to the net dispatch requirement (7.1.1). This page carries no solar control, and the absence is deliberate rather than incomplete — solar is a passive collector, and a page offering a control that does nothing is worse than a page offering none.

### 19.6 Page 5 — Thermal & Cooling

Cooling was placed alongside generation in v2.0. That grouped by physical plant rather than by role in the arithmetic, and it put cooling on the wrong side: P_cooling(t) is a term in P_total(t). It is load, not supply, and sitting it beside turbines implies it offsets demand when it is demand. It is also, at α_max defaults, the second-largest consumer on site, and the only asset class above ten percent of the picture without a page.

**Primary readout — thermal headroom.** How much additional compute load the cooling plant can absorb before approach-to-limit, and how long it takes to get there. This is the thermal analogue of the bridging-capability readout on Page 3, and it answers the question an operator at 230 kW per cabinet actually has: at these densities the interval between a cooling shortfall and thermal throttling is minutes, and there is presently nowhere in the console that margin is visible.

**Calibration instrument.** Measured α(t) plotted against the modeled curve, and observed Δt_thermal against configured. Section 15 has carried α_max, τ, and Δt_thermal as engineering placeholders pending design-partner data since the first draft of this document. This panel is where that gap stops being a paragraph in a residual-items list and becomes a number an engineer can watch move.

Supporting panels: CDU and loop state — supply and return temperature, flow rate, pump status, and approach temperature, since a rising approach is how fouling and flow restriction first appear; per-row inlet temperatures and hot-spot identification; thermal storage state of charge and discharge duration where present; and a pre-staging record showing what was staged against which predicted step-load and whether the response arrived within Δt_thermal. That last panel is the thermal counterpart of the network corroboration record in 25.1, and it serves the same purpose — establishing whether the prediction produced the response it assumed.

**Controls, and the boundary.** Bounded pre-cooling setpoint staging (8.1), gated per 19.11. Nothing further. Every site already operates a building management system that controls cooling, and Section 2 positions GridSignal explicitly as not an EMS or BMS. The relationship here is the same one the specification already takes with turbines: propose, do not command, and the BMS retains unconditional override.

### 19.8 Page 6 — Grid & Procurement

Contracted firm capacity and present import against it; active reservations with their windows and prices; pending ReservationProposals awaiting authorization (24.4); price curve over the FR-1.3 forecast horizon; and demand-charge exposure for the current billing period. The authorization control is the only place in the console where an action commits money, and it is styled and confirmed differently from every other control for that reason.

### 19.9 Page 7 — Network Telemetry

Per-switch and per-interface throughput, error counters, and optical power levels; fabric-level aggregate against historical baseline; and the corroboration record described in 25.1 — for each predicted job start, whether a corresponding traffic rise was observed within the expected window. This page is read-only. It is a diagnostic and a forecast-quality instrument, not a dispatch input, for the reason given in 25.1.

### 19.10 Page 8 — Proposals & Learning

The Section 21.6 review queue, which until now had no specified home. Every Proposal and every agent Recommendation appears here with its originating agent, asserted change, current and proposed values, supporting evidence and observation window, estimated impact, reversibility, and expiry. Approve and reject are the two controls, and both record reviewer identity and timestamp.

**Volume is a design constraint on this page, not an afterthought.** Six agents (26.2) each generating recommendations will produce more items than an operator can meaningfully review, and a queue that is not read is equivalent to autonomous operation with extra steps. Grouping, ranking by estimated impact, and bulk disposition of low-impact items are requirements of this page rather than refinements — see AG-4.

### 19.11 Cross-page conventions

- **Operating tier is always visible.** The current tier (Forecast/Advisory, Supervised, Autonomous) appears in the persistent header on every page, because the meaning of every control on every page depends on it.
- **Every control declares its authority.** A control shows whether it acts immediately, requires acknowledgment, or only submits a proposal — before it is pressed, not after.
- **Data-quality tags travel with the data.** unmapped_hardware, invalid_payload, and uncalibrated_site render as inline flags wherever affected values appear, on every page, as they already do on the landing page.
- **Irreversible and customer-impacting actions are confirmed separately.** Job preemption (23.2 Tier D) and reservation purchase (24.4) require explicit confirmation naming the consequence, distinct from ordinary acknowledgment.

## 20. IP Strategy

**Disclaimer.** This section is a technical read of where this specification's mechanisms look distinctive enough to warrant a conversation with patent counsel — it is not a legal opinion that any of them are patentable. Patentability turns on things outside this document's scope: a professional prior-art search (particularly in demand-response, DERMS, and generator-control-systems patent classes, not just general ML/forecasting art) and how narrowly or broadly claims are ultimately drafted. Nothing here should be treated as freedom-to-operate analysis.

### 20.1 Strong candidates (tied to specific, non-obvious mechanisms)

- **1. Job-scheduler-derived power forecasting for microgrid dispatch.** The core mechanism in Section 2 / Section 4: deriving a real-time physical power draw prediction from job-scheduler queue state (Slurm/K8s/Ray) before the compute hardware draws power, using a hardware-profile-indexed lookup rather than sensor telemetry. The distinctive element for a claim is not “predict power from software state” in the abstract — likely too broad and vulnerable to an abstract-idea rejection on its own — but the specific pipeline: queue event → hardware-SKU-indexed wattage lookup → real-time MW figure → physical asset dispatch. Tying the claim to the downstream hardware control step (Section 7) is what would most likely help subject-matter eligibility.
- **2. Dual-clock asset staging for compound step-loads.** Section 2 item 3 and Sections 7–8: independently modeling and staging two different physical response delays — mechanical generator ramp on one clock, thermal/cooling response on a second, longer clock — against a single predicted compute event, specifically to prevent the compute-spike-then-delayed-chiller-spike “double-whammy.” This is a fairly specific control-systems mechanism; the novelty is in coordinating two asset classes with different physics against one upstream prediction, not either delay model alone.
- **3. Checkpoint-vs-completion discrimination for generation dispatch.** Section 6.2: the specific heuristic (percentage-drop threshold plus duration window plus recovery-within-window test, with a fallback to an “uncertain, hold state” rather than guessing) used to prevent a dispatch controller from prematurely ramping down generation assets during a training checkpoint. This is narrow and concrete enough to be a reasonable candidate — the claim would be specifically about using workload-shape classification to gate generator ramp-down decisions, a fairly unusual cross-domain combination of ML training internals informing power-plant dispatch logic.
- **4. Pre-emptive insufficient-reserve detection from ramp-time arithmetic.** Section 7.2 rule 4 and Section 7.3: computing, at staging time — before any shortfall materializes — whether available generation ramp rate and BESS bridging capacity will cover a predicted step-load, by comparing required ramp time against available lead time, and firing a warning proactively rather than reactively (before a voltage/frequency event occurs, not after). The potentially distinctive piece is predicting the future capacity shortfall from known ramp-rate physics and acting before it happens, versus conventional reserve-margin monitoring, which is typically threshold-based on present state.
- **5. Confidence-weighted, tag-composable dispatch sizing.** Section 12: sizing dispatch decisions off the lower bound of a forecast confidence interval, where that interval is dynamically widened by independently-tracked, composable data-quality flags (unmapped hardware, uncalibrated site, invalid payload — Sections 5.1, 17.2, 17.3) that can co-occur on a single forecast segment. The novel piece is less “use confidence intervals,” which is common, and more the specific mechanism of stacking independent provenance-based penalty factors that trace back to why a given prediction is less trustworthy, then using that composed uncertainty to conservatively bias a physical control decision.

### 20.2 Weaker candidates (more likely to face prior-art or abstractness pushback)

- **6. Cold-start default-to-calibrated parameter lifecycle.** Section 17.3: automatically operating a new site on global defaults while explicitly tagging output as uncalibrated until a measured-data threshold is met. Useful engineering pattern, but “use defaults until enough data exists, then recalibrate” is common enough in adaptive control systems that novelty would likely hinge entirely on the specific triggering criteria and audit mechanics, not the general idea.
- **7. Idempotent, provenance-tagged ingestion for a real-time control loop.** Sections 10, 17.1–17.2: event-ID deduplication plus schema/domain validation with quarantine-and-degrade-gracefully behavior. This is largely standard distributed-systems practice; on its own it is unlikely to clear a novelty bar even applied to this domain. It is more realistically a limitation within Claim 1 or Claim 5 above than a standalone claim.
- **8. Human-gated promotion of machine-derived control parameters.** Section 21.6: a continuously-learning system that derives candidate changes to physical-dispatch parameters but holds them in a proposed state, bounds-checks them automatically against a declared valid range, and requires explicit authorization before they influence a control decision. The physical-control tie-in is present, which helps, but human-in-the-loop approval of automatically-derived settings is well-established in industrial control; any novelty would rest on the automatic bounds rejection and the audit coupling, not the gate itself.

### 20.3 Claim strategy note

The strongest candidates above are the ones that couple a software prediction mechanism to a specific physical control action — dispatching a turbine, staging a chiller, gating BESS discharge — rather than stopping at “compute a forecast.” That coupling is generally what helps software-adjacent inventions clear patent-eligibility scrutiny. Candidates 1, 2, 3, and 4 all have that physical-control tie-in built into how this specification already structures the mechanism (Section 7 in particular), which is not incidental to how they are described here — it reflects how the underlying system is designed to work.

Practical next step: an attorney-led prior-art search specifically in demand-response, DERMS, and generator-control-systems patent classes, run against Candidates 1–5 individually rather than as a single combined filing, since they rest on different mechanisms and may warrant separate claim sets or a continuation strategy.

## 21. AI/ML Model Strategy and Learning Loop

This section was requested in product review (July 27, 2026) to answer four questions that Sections 4–12 do not: what the training and learning loop actually is, which models are used for what, where the data goes, and when a learned conclusion is allowed to change system behavior. It specifies the analytics and learning plane. It does not modify any formula in Sections 4–8.

### 21.1 The governing constraint: two planes, one direction of influence

The most consequential decision in this section is a negative one. **No model inference sits inside the real-time control path.**

The reasoning is arithmetic rather than stylistic. NFR-2 allows two seconds from decision to command issuance, and Section 3.1 sets a 5-second forecast tick as the refresh floor. Hosted model inference has a p99 latency and a variance profile that cannot be bounded within that budget, is non-deterministic under identical inputs, and — for any hosted endpoint — is reachable only across a WAN, which is precisely the dependency the real-time loop is designed to avoid. A control decision that cannot be reproduced from its inputs also cannot be audited under NFR-5 or defended after an incident.

The two planes are therefore separated as follows, and influence runs in one direction only: the learning plane may propose changes to the parameters the control plane uses, and may never participate in a control decision.

| **Plane** | **Latency budget** | **Components** | **Posture when the other plane fails** |
|---|---|---|---|
| Control plane (Sections 4–8) | ≤ 2 s per NFR-2; 5 s tick per Section 3.1 | Hardware profile lookup, P_compute/P_cooling formulas, checkpoint-valley classifier, dispatch arbitration, insufficient-reserve check. Deterministic and reproducible from inputs | Runs indefinitely on the last-applied parameter set. Loses only new calibration proposals |
| Learning / analytics plane (this section) | Seconds to minutes; no hard bound | Correlation and state tracking, calibration proposals, cost and make-vs-buy analysis, what-if modeling, operator-facing narrative reporting. Model-based and non-deterministic | Backfills from the persisted event history once the control plane is reachable again; no learning is lost, only delayed |

**LP-1 (hard requirement).** Loss of every model vendor — API outage, contract termination, price change, or network partition — shall not degrade the control plane beyond the suspension of new Proposal generation. This is an acceptance criterion with a test attached (TC-28), not a design aspiration. It is also the reason the vendor-selection decisions in 21.3 are reversible: if no control decision depends on a model, no control decision is hostage to a model vendor.

### 21.2 What the learning plane is for

Its job is to track every modeled entity's state through time, persist that history, and surface correlations that a hand-written rule would not encode. Four workstreams, in rough order of near-term value:
- **1. Load-pattern discovery.** Recurring site demand shape by hour and day of week, including recurring exceptions — a site that peaks Wednesday afternoons for a reason nobody wrote down. This feeds the 15-minute-to-4-hour horizon forecast under FR-1.3, and explicitly not the 30–60-second staging loop, which is driven by queue events rather than history.
- **2. Supply-pattern discovery.** Production patterns per non-dispatchable source and their regional dependence — diurnal and seasonal solar, hydro seasonality in the Pacific Northwest, wind profiles in ERCOT-style markets. Consumes the P_renewable(t) term defined in Section 7.1.1.
- **3. Source cost attribution.** Marginal cost per MWh for grid import, on-site turbine generation, and stored energy round-trip. Turbine cost must be modeled as amortized capital rather than fuel alone: generation capacity is typically debt-financed, so the economically relevant question is duty cycle — how often the asset actually runs against what it costs to own — not the marginal cost of the hour it runs. This workstream produces the generate-versus-import conclusion and feeds the Scenario Planner (Section 18.5, parent spec FR-4.4).
- **4. Forecast-error attribution.** Rolling MAPE per load type per FR-1.5, decomposed by hardware profile, workload class, and data-quality tag. The decomposition is the point: an undecomposed error figure tells an operator that the forecast is drifting but not which of the Section 5 profiles or Section 9 time constants is responsible, and therefore does not support a calibration proposal.

### 21.3 Model role assignment

Roles are assigned by task shape and cost profile rather than by a single ranking. The high-frequency task is correlation over structured numeric series, where output prose quality is irrelevant; the low-frequency task is analysis and reporting, where it is the whole product.

| **Role** | **Model (MVP)** | **Rationale** | **What leaves the site** |
|---|---|---|---|
| High-volume correlation and state tracking | Mistral (hosted) | Roughly an order of magnitude cheaper per token at this call volume, and the task needs no output formatting — it ingests structured series and returns correlations. EU jurisdiction is a favorable privacy posture for a product that will be sold to operators with data-residency obligations | Aggregated, de-identified numeric series only (21.4) |
| Analysis, statistical reasoning, operator-facing reporting | Claude (hosted) | Materially better structuring of analytical output and statistical narrative. Runs at daily or on-demand frequency, so per-call cost is not the binding constraint it is for role 1 | Same de-identified aggregates, plus operator-authored question text (21.4) |
| Proprietary and on-premises inference | Cohere, self-hosted (roadmap, not MVP) | The intended home for any function whose exposure would leak GridSignal IP as characterized in Section 20 — in particular anything that would reveal the hardware profile library or the calibration mechanism to a third-party inference provider | Nothing |

**Excluded vendors.** Recorded here so the decision is revisitable rather than re-litigated. OpenAI is excluded on commercial-terms and strategic-consistency risk — the concern is not capability but exposure to unilateral changes in retention terms or pricing on a dependency embedded in a customer-facing product. xAI/Grok is excluded on governance predictability. Both are business-continuity judgments rather than benchmark results, and both should be revisited if a zero-retention or self-hosted deployment path removes the underlying dependency risk. LP-1 is what makes revisiting them cheap.

### 21.4 Data-residency boundary

Two of the three MVP roles call a third-party hosted API, which stands in direct tension with the requirement that a customer's operational knowledge stay under their control — and with the Section 20 position that the hardware profile library is itself non-public know-how. The boundary is therefore specified, not assumed:
- **Never leaves the site:** raw WorkloadSignal payloads; job_id and job names; site_id; customer identity; the site's calibrated parameter set; the contents of the hardware profile library.
- **May be sent to a hosted model, after transformation:** numeric time series with entity identifiers replaced by per-session opaque handles, and hardware profiles referenced by anonymized class index (e.g. "profile_A at 10.2 kW/chassis") rather than by vendor SKU.

The consequence is that the transformation layer is a required component rather than a hardening measure applied later. A hosted-model call that bypasses it is a defect, and it is tested as one (TC-29). Stating this now is cheaper than retrofitting it: the transformation constrains what the learning plane can be asked to do, so it needs to exist before the analytics workstreams are built against it, not after.

### 21.5 The learning store

- **Form.** An in-process state store over typed entities, explicitly not a vector/RAG retrieval index. The queries this plane runs are time-series correlations across a bounded, known entity set — sites, assets, jobs, forecasts, control events — which a semantic retrieval index serves poorly and a structured store serves well. This is a deliberate exclusion, recorded because the default assumption for an LLM-adjacent component is otherwise.
- **Ownership.** GridSignal-operated and per-site. No shared multi-tenant learning corpus in MVP; cross-site learning is out of scope until an explicit customer-consent model exists, since aggregating one operator's load patterns into a model that serves a competitor is a commercial problem before it is a technical one.
- **Durability.** "In-memory" describes the read path, not the durability guarantee. The learning store shall be write-ahead-logged to local persistent storage and fully reconstructable after a restart. This is the same durability requirement already stated for the Section 17.1 dedupe store, and Section 15's in-flight-state-on-restart item covers both — they are one decision, not two.
- **Update cadence.** Continuous. Observations are written as they arrive rather than batched into a periodic upload; a daily batch would mean an operator investigating an incident is querying stale state. What is deliberately not continuous is the application of what the store concludes, which is the subject of 21.6.

### 21.6 Learning promotion gate

A system that learns continuously and applies what it learns immediately is a system whose dispatch behavior changes without anyone deciding that it should. This subsection specifies the gate that prevents that. Nothing the learning plane concludes takes effect on its own; a conclusion enters the pipeline as a Proposal record and moves through four states.

| **State** | **Meaning** | **Effect on dispatch** |
|---|---|---|
| proposed | Learning plane has derived a candidate parameter change or correlation, with the supporting evidence and observation window attached | None |
| under_review | Surfaced in the pending-learnings queue on the operator dashboard (Section 19) | None |
| applied | Explicitly approved by an authorized reviewer | Takes effect on forecasts issued after approval. Section 17.3's no-mid-window-parameter-switch rule applies |
| rejected | Reviewer classified it as an anomaly, a one-off, or immaterial | None. Retained for audit and suppressed from re-proposal for a configurable interval (MVP default: 30 days) unless the supporting evidence materially changes |

**Required Proposal contents.** The parameter or correlation asserted; the current and proposed values; the observation count and time window it was drawn from; the measured forecast-error improvement that motivates it; and, on every state transition, the reviewer identity and timestamp. A Proposal that cannot state its evidence is not reviewable and shall not be generated.

**Automatic bounds rejection** (partially closes the Section 15 configuration-governance gap). A Proposal whose value falls outside the declared valid range for that parameter — α_max outside 0.10–0.30, Δt_thermal outside 60–120 s, PUE_base outside 1.02–1.05, r_asset ≤ 0 — is rejected at generation time and never reaches a reviewer. Out-of-bounds derivation is logged as a learning-plane data-quality event, because in practice it indicates a measurement or ingestion problem rather than a genuine site characteristic. This is the validation-bounds half of the Section 15 gap; the authorization half remains open below.

**Relationship to Section 17.3.** An applied promotion is a control-relevant configuration change and carries the same audit trail as the uncalibrated_site transition. These are one mechanism, not two: a site leaving uncalibrated_site is a promotion, and should be implemented through this pipeline rather than as a parallel path.

### 21.7 Relationship to the Confidence / Calibration Engine

Section 12 and this section are the same feedback loop observed at two timescales. Section 12 operates within a forecast: it widens a band because of what is known about that segment's inputs — unmapped hardware, an uncalibrated site, a quarantined payload. Section 21 operates across forecasts: it observes accumulated error and proposes that a parameter should change.

The interface between them is narrow by design. The Confidence / Calibration Engine (Section 18.2) consumes applied parameters only. A Proposal in proposed or under_review state never widens or narrows a live confidence band, and never reaches the control plane. This preserves the property that a forecast's confidence band is reproducible from the parameter set in effect when it was issued.

### 21.8 Architecture placement

Figure 1 (Section 18) does not yet show the learning plane and should be regenerated to include it. Its attachment points, in the vocabulary of Sections 18.1–18.6:
- Reads from the persisted Forecast and ControlEvent entities, plus measured outcomes from SCADA/BMS telemetry — all of which are already durable state, so the learning plane needs no new tap into the real-time path.
- Writes Proposal records to the Operator Dashboard, alongside the insufficient-reserve alerts and quarantine notifications already described in Section 18.3 and 18.1.
- On approval only, writes to the site parameter set consumed by the Confidence / Calibration Engine.
- Has no edge into the Workload-to-MW Formula, the Checkpoint-Valley Classifier, or the Dispatch Arbitrator. If a future diagram shows one, either the diagram or the implementation is wrong.

The learning plane sits on the same side of the boundary as the Scenario Planner (Section 18.5): both are analytical consumers of persisted state rather than participants in the real-time control loop, and both may run off-site where the control loop may not.

### 21.9 Residual open items

- **LP-2 — approval authority.** Who may move a Proposal to applied, and whether that authority differs by operating tier (Advisory, Supervised, Autonomous), is unresolved. This is the same question as the Section 15 configuration-governance item and should be closed once, not twice. It is the sharpest of these four: the gate in 21.6 is only as strong as the answer.
- **LP-3 — inference cost ceiling.** No per-site call budget or token ceiling is defined for hosted inference. Correlation workloads scale with entity count and event rate, so an unbounded budget is a real commercial exposure at a large site.
- **LP-4 — self-hosted path.** Cohere licensing terms have not been reviewed, and the hardware footprint for on-premises inference has not been sized. This interacts with edge appliance sizing and needs resolving before the roadmap row in 21.3 is treated as committed.
- **LP-5 — significance floor.** No minimum observation count or statistical-significance test is defined before a Proposal may be generated, which leaves the gate in 21.6 defending against a volume of weakly-evidenced proposals it was not designed to filter. A placeholder consistent with the Section 17.3 calibration threshold (20 distinct step-load events ≥ 1 MW) is the starting point, but the correct floor is a function of observed variance and needs design-partner data.

## 22. Persistence and Storage Architecture

This section specifies where every piece of system state lives, which store owns it, and — equally load-bearing — which storage technologies may not be used for which purpose. It was written following an architecture review (July 29, 2026) of a proposal that would have placed vector, graph, and distributed in-memory stores inside the real-time control path. The rejections in 22.6 are recorded with their reasons because several of those patterns would have silently invalidated acceptance tests already defined in Addendum A, which is a failure mode worth naming rather than a matter of taste.

### 22.1 Principles

Four rules generate every decision below.
- **1. Every dependency in the control path is a failure mode.** Section 21.1 establishes that no model inference sits in the real-time loop; the same reasoning governs storage. A store the control plane cannot reach is a store that can stop dispatch. Ten dependencies at 99.9% availability each compose to roughly 99% — on the order of seven hours a month degraded — which would make GridSignal a less available control system than the reactive ones it replaces, on a product whose entire proposition is preventing power-related outages. The control plane shall therefore depend on exactly one store, and that store shall be local to the edge appliance.
- **2. Determinism in, determinism out.** Anything that gates a control decision — a threshold, a timer, a classification — must be reproducible from persisted inputs. A store that returns approximate, ranked, or eviction-timed results may not sit behind a control decision, because a decision that cannot be reconstructed cannot be audited under NFR-5 or defended after an incident.
- **3. Locality follows the loop.** The Section 18 ingestion → forecast → dispatch chain runs on a site-local edge appliance; its state store runs there too. Analytical and archival tiers may be remote precisely because nothing in the real-time path waits on them.
- **4. Interface, not vendor.** Each tier is specified as an interface — embedded transactional store, relational store, S3-compatible object store — with a default implementation named. Substituting an implementation shall be a configuration change, not a code change. This is what keeps the air-gapped deployment case (22.5) from requiring a separate product.

### 22.2 Storage tiers

| **Tier** | **What it holds** | **Default implementation** | **Posture when unavailable** |
|---|---|---|---|
| Tier 0 — control-plane state | Section 17.1 dedupe keys (15-minute rolling window); active checkpoint-valley evaluation and grace timers (6.2); partially-staged DispatchPlan state (7.2); the site's currently applied parameter set | Embedded transactional store with write-ahead logging, single file, local to the edge appliance. No network path | Loss of Tier 0 is loss of dispatch. Treated as an appliance fault, not a degraded mode (ST-2) |
| Tier 1 — site history and audit | WorkloadSignal history; Forecast records; the ControlEvent audit trail (FR-2.5, NFR-5); quarantine store (17.2); learning store (21.5); Proposal records and parameter-change audit (21.6) | PostgreSQL, time-partitioned. A time-series extension only if a measured query is slow — not preemptively | Control plane continues. Writes buffer to Tier 0 and drain on recovery. No forecast or dispatch is delayed |
| Tier 2 — analytical and archival | Parquet exports of Forecast and ControlEvent history beyond the Tier 1 hot window; Scenario Planner working set (18.5); the de-identified learning corpus permitted by 21.4 | S3-compatible object storage, queried by an embedded analytical engine. Cloudflare R2 as hosted default; MinIO for on-premises and air-gapped sites | Scenario Planner and long-range analytics degrade. No effect on the control plane, Tier 1, or the audit trail |

**Hot-window boundary.** Tier 1 retains a configurable hot window of Forecast and ControlEvent records (MVP default: 90 days). Older records are exported to Tier 2 and dropped from Tier 1. The export is additive and idempotent (22.4), so a failed or repeated export cannot lose or duplicate audit history.

### 22.3 Restart behavior (closes the Section 15 in-flight-state item)

A restart is not a cold reset. On startup the engine shall reconstruct the following from Tier 0 before accepting new events:
- The dedupe window, with original first-seen timestamps preserved per Section 17.1. A restart occurring inside the 15-minute window must still reject a duplicate rather than admit it (TC-34).
- Any active checkpoint-valley evaluation, including elapsed time against the 45-second classification window and the 30-second grace period (6.2). A job that was uncertain before the restart is still uncertain after it, with the clock continuing rather than restarting — a reset clock would extend staging hold time by up to the full grace period on every restart (TC-35).
- Partially-staged dispatch state (7.2), so that staging already in progress is reconciled rather than re-issued.

**Reconstructed intent does not override measured reality.** Where reconstructed state and measured asset state disagree — the appliance believed a turbine was ramping, the asset reports idle — the measured state wins and a dispatch re-plan is triggered per FR-3.3. The engine shall not assume its pre-restart intent was executed, because the restart may have occurred between issuing a command and its acceptance. The divergence is logged, since a recurring one indicates a connector or asset-control fault rather than a restart artifact (TC-36).

Cold start applies only to a site_id with no Tier 0 record at all, which is the Section 17.3 uncalibrated_site path. A restart of a known site is never a cold start, and the two must not share an implementation branch.

**Consequence for timers.** Control-relevant timers are held as explicit state with a persisted start timestamp. They shall not be implemented as cache TTLs or eviction callbacks. Eviction timing is a property of a store's memory pressure rather than of this specification, which would make the TC-08 boundaries non-reproducible and the classifier non-deterministic on the one decision that gates turbine ramp-down.

### 22.4 Object storage: batching, idempotency, and edge-to-cloud sync

**Every Tier 2 write is a batch, never a single event.** At a site producing on the order of 10 events per second, one object per event is roughly 26 million write operations per month; object-store write operations are billed per million, so per-event writes cost approximately four orders of magnitude more than hourly batches for byte-identical data. Batch interval is configurable, MVP default 1 hour or 64 MB, whichever comes first (TC-39).

**Object key and idempotency.** Keys take the form {site_handle}/{yyyy}/{mm}/{dd}/{batch_id}.parquet, where site_handle is the de-identified handle from 21.4 rather than the site_id itself. A retried upload of an already-written batch_id overwrites byte-identical content and is a no-op — object PUT idempotency by key composes with the Section 17.1 event_id dedupe rather than duplicating it. No separate upload-dedupe mechanism is required, and adding one would introduce a second source of truth for the same question.

**Edge-to-cloud sync** (resolves part of the Section 18.7 open item). The edge appliance writes batches to local disk first and uploads asynchronously. WAN loss is therefore not an error path at all — it is a growing local backlog that drains on reconnect, which is the behavior the extended-outage case requires. Extended-outage capacity is bounded by local disk: the appliance shall alert when the unsynced backlog exceeds a configurable fraction of available local storage (MVP default: 70%), and shall prefer dropping the oldest analytical batches over dropping Tier 0 state or blocking ingestion. Control and audit data are never sacrificed to keep an analytics upload alive (TC-37, TC-38).

### 22.5 Data residency and bucket ownership

Section 21.4 forbids raw payloads, job_id, site_id, and customer identity from leaving the site. Object storage therefore requires two distinct buckets under different ownership. Conflating them is a residency violation rather than a simplification, and the distinction is easy to lose during implementation if it is not stated as a requirement.

| **Bucket** | **Owner** | **Contents** | **Jurisdiction control** |
|---|---|---|---|
| Audit / archive | Customer | Full-fidelity ControlEvent, WorkloadSignal, and quarantine history for that customer's own sites. GridSignal writes using customer-issued credentials and retains no copy | Customer's choice of provider and region; may be customer-operated MinIO on-premises |
| Analytics | GridSignal | De-identified aggregates only, per the 21.4 transformation rules — opaque per-session handles, hardware profiles referenced by anonymized class index | GridSignal's choice, subject to 22.5.1 |

### 22.5.1 Jurisdiction, and what a jurisdiction flag does not buy

The default hosted implementation supports pinning a bucket to a jurisdiction (EU or FedRAMP among them) to satisfy residency requirements, which is directly relevant to the public-sector and defense deployment path. Two cautions are recorded here so that neither is discovered first by a customer's security review:
- **A jurisdiction flag is not a compliance authorization.** A FedRAMP-jurisdiction bucket does not make GridSignal FedRAMP-authorized. Any claim in that direction requires its own program and should not be implied by an architecture diagram.
- **Location is not jurisdiction.** The default hosted provider is a US-incorporated company, so an EU-pinned bucket remains reachable by US legal process. This is the mirror image of the argument recorded in Section 21.3 in favor of an EU-jurisdiction model vendor, and the asymmetry is noted deliberately rather than left for a European prospect to surface. Where an EU-operated processor is a hard requirement, principle 4 of 22.1 permits substituting an EU-domiciled provider or customer-operated MinIO without a code change.

**Air-gapped deployments.** For sites where no cloud endpoint is acceptable, MinIO behind the same S3-compatible interface is the on-premises implementation of Tier 2. This is the single strongest reason to specify the interface rather than the vendor: the defense and national-laboratory segment is otherwise unaddressable without a product fork.

### 22.6 Rejected patterns

Each of the following was proposed in good faith and each would invalidate an existing acceptance test. They are recorded with reasons so the same proposals do not return without new arguments.
- **Vector or approximate-nearest-neighbor search to resolve unmapped hardware profiles.** Section 5.1 deliberately does not guess: an unrecognized SKU receives the conservative generic_fallback rate, a low_confidence: unmapped_hardware tag, a widened confidence band, and an operator alert. Matching an unknown cabinet to a similar known one and inheriting its wattage replaces a visible, flagged degradation with a plausible-looking silent one, and defeats TC-15 and TC-16. A hosted implementation would also require SKU names to reach the index, which 21.4 forbids.
- **Vector store or knowledge graph behind the checkpoint-valley classifier.** Section 6.2 is arithmetic over a trailing window: a percentage drop, a duration, and a recovery threshold. Backing it with an approximate retrieval system makes classification non-reproducible and TC-05 through TC-09 unassertable — on the one decision that gates turbine ramp-down.
- **Cache TTL or eviction callbacks as the source of control-relevant timers.** See 22.3. Eviction is a memory-pressure behavior, not a specified interval.
- **Distributed in-memory compute platforms for the dispatch arithmetic.** The Section 7.2 shortfall calculation is ΔP / r_asset − Δt_lead. It does not require distribution, and adding it introduces a network dependency and a coordination failure mode to a two-operation arithmetic problem.
- **Networked stores of any kind in the control path,** including hosted object storage. Round-trip latency exceeds the Section 3.1 tick by one to two orders of magnitude, and reachability is exactly the property edge placement exists to guarantee.
- **Agent-memory frameworks for control state.** These solve statelessness between model calls. The control plane is a deterministic numeric pipeline whose state is fully specified in Sections 4–12; it does not have that problem, and adopting a solution to it imports non-determinism for no benefit.

### 22.7 Reference implementation and simulator mapping

For the demonstration simulator the three tiers collapse to two without violating any principle in 22.1:
- Tiers 0 and 1 share one embedded write-ahead-logged store file in separate table namespaces, accessed through an ORM so that promoting Tier 1 to PostgreSQL is a connection-string change.
- Tier 2 attaches that same file directly from the analytical engine. The Parquet export path is a later optimization rather than a prerequisite for the demonstration.

Two constraints carry from this section into the Simulator Functional Specification rather than being restated there:
- The simulator's control-plane store must be a local file, not a networked database, even where a hosted one is available in the environment. A demonstration whose persistence layer contradicts the architecture it demonstrates is worse than one with less persistence.
- Store writes must not block the event loop. A synchronous embedded-store write in a single-process asynchronous application surfaces as latency during NFR-2 load testing and is easily misattributed to the forecast path.

### 22.8 Open items

- **ST-1 — Hot-window boundary.** The 90-day Tier 1 retention default is a placeholder. The correct value depends on how far back the Scenario Planner (18.5) and the Section 21.2 error-attribution workstream actually reach, neither of which has been measured.
- **ST-2 — Tier 0 redundancy.** This section specifies a single local store on a single appliance, which makes appliance loss a dispatch outage. It interacts directly with the edge-appliance redundancy question in Section 18.7: a store replicated across a redundant pair is a different Tier 0 design, so the two should be resolved together rather than sequentially.
- **ST-3 — Retention-lock granularity for the audit archive.** Retention locks on the default hosted provider are bucket- or prefix-scoped rather than per-object. Whether that satisfies a given customer's tamper-evidence requirement under NFR-5 is unverified and should not be represented to an auditor until it is.
- **ST-4 — Simulated-clock semantics.** Every interval in this specification — the 15-minute dedupe window, the 45-second and 30-second classification intervals, the 90-day retention boundary — is expressed in real time. A tick-based simulator running faster than real time must decide which clock these are measured against, almost certainly simulated time, and must persist that clock so a restart resumes rather than jumps forward. This belongs to the Simulator Functional Specification but is recorded here because it changes what "survives restart" means for Tier 0, and because Section 11.4's ±2-second NTP requirement is a production constraint the simulator models rather than enforces.

## 23. Controllable Load and Compute Curtailment

### 23.1 What this changes

Sections 1–22 treat compute demand as exogenous: the engine reads what the scheduler intends to run and stages supply to meet it. Curtailment makes demand endogenous. GridSignal becomes able to reduce load rather than only anticipate it, which is a different product with a different risk profile, and the difference should be stated plainly rather than absorbed as a feature.

Three consequences follow immediately, and each is addressed below because none is optional:
- **A feedback loop now exists.** Curtailing reduces P_compute(t), which reduces the predicted shortfall, which removes the justification for the curtailment. Without damping this oscillates. Hysteresis is specified in 23.3, and it is a correctness requirement rather than a tuning preference.
- **GridSignal acquires a write path into the customer's scheduler.** Every integration to this point has been read-only. A write path is a categorically higher-trust relationship — the same credential that can pause a job can disrupt a production training run — and it must be separately negotiated, separately credentialed, and separately revocable from the telemetry read path (23.5).
- **The blast radius of a wrong forecast changes.** A forecast error that over-stages a turbine wastes fuel. A forecast error that preempts a multi-day training job destroys work. Conservative-by-default dispatch sizing (Section 12) was already policy; for curtailment it becomes a hard interlock (23.6).

### 23.2 The curtailment ladder

Curtailment is not an on/off switch on a rack. Treating it as one discards most of the available headroom and all of the cheap options. Four tiers, always exhausted in order:

| **Tier** | **Action** | **Typical yield** | **Cost if wrong** | **Reversibility** |
|---|---|---|---|---|
| A | Defer queued jobs that have not yet been allocated nodes | Prevents future load; yields nothing from present draw | A job starts later than it could have | Full — no work lost |
| B | Power-cap running accelerators (reduce per-device power limit) | Typically 10–30% of capped devices' draw, workload-dependent | Jobs run slower for the duration | Full — cap is lifted |
| C | Suspend checkpointable jobs at their next checkpoint boundary | Full draw of suspended jobs, delayed to the next checkpoint | Work since last checkpoint is preserved; wall-clock time lost | Partial — restart costs Δt_lead plus checkpoint reload |
| D | Preempt running jobs immediately | Full draw of preempted jobs, immediately | All work since last checkpoint is lost | Poor — full restart |

**Ordering is mandatory, not advisory.** The controller shall not invoke a tier while headroom remains at a lower one. Tiers A and B are reversible and cost no completed work; C and D are not. This ordering is what makes bounded autonomous curtailment defensible at all (23.4).

**Yield figures are placeholders.** The power-cap range in the table is an engineering estimate. Actual yield is device- and workload-dependent — a memory-bound job loses little throughput under a cap, a compute-bound one loses roughly in proportion — and must be characterized per hardware profile against measured data (CL-1). Until then, Tier B yield is reported with the same widened confidence treatment as an unmapped hardware profile.

**The restoration asymmetry.** Curtailment is fast and restoration is slow. Lifting a power cap is immediate; restarting a suspended or preempted job costs a full Δt_lead plus model and checkpoint reload. Restoration is therefore itself a predicted step-load and is staged through the ordinary Section 7 path — a controller that restores load without staging for it has simply moved the shortfall later.

**Synchronization breaks the per-device yield assumption.** A distributed training job using all-reduce collectives runs at the pace of its slowest participant. Power-capping a subset of a job's accelerators therefore does not produce proportional savings for proportional slowdown: the whole job decelerates to the capped rate while the uncapped devices consume near-idle power waiting on the collective — the worst of both outcomes, less saving and more delay than the naive model predicts. Tier B is therefore approximately all-or-nothing per synchronized job, and the controller shall apply a cap to every participant of a job or to none of them. The same reasoning bounds Tiers C and D: where a rack forms a single NVLink domain, curtailment granularity may be the rack rather than the node, and a controller expecting to shed an arbitrary fraction of a 230 kW cabinet will find that it cannot.

### 23.3 Placement in dispatch arbitration

Curtailment is the last resource in the arbitration order, invoked only when the Section 7.2 step 4 reserve check predicts a gap that generation and storage cannot close. It extends that rule rather than replacing it.

**Reliability only, in this version.** Curtailment shall not be invoked for economic reasons — because grid price is high, or because generation is more expensive than the work is worth. Economic curtailment is a legitimate capability and a different authorization problem: it trades a customer's throughput for the operator's cost saving, which is a commercial decision that this specification is not the right place to make (CL-3).

**Hysteresis.** Once curtailment is active, the controller shall hold it for a minimum dwell time (MVP default: 120 seconds) before reversing, and shall restore load only when forecast supply headroom exceeds the restored load by a configurable margin (MVP default: 20%). Both defaults are placeholders; what is not negotiable is that some dwell time and some restoration margin exist, because with neither the loop described in 23.1 will oscillate at the tick rate.

### 23.4 Authority

Curtailment is customer-impacting in a way that no other dispatch action in this specification is. Authority is therefore defined per tier and per ladder tier, not per operating mode alone.

| **Operating tier** | **Ladder A and B** | **Ladder C and D** |
|---|---|---|
| Forecast / Advisory | Recommend only | Recommend only |
| Supervised | Requires operator acknowledgment | Requires explicit confirmation naming the affected jobs |
| Autonomous | May execute without acknowledgment, within configured bounds | Requires explicit confirmation regardless of tier |

**Ladder C and D never become autonomous.** There is no operating tier in which this system destroys a customer's completed work without a human deciding that it should. If a site's reliability requirement cannot be met under that constraint, the correct answer is more storage or more generation, not more autonomy.

**Eligibility is customer configuration.** Which jobs are curtailable, at which ladder tier, and in what priority order is site and tenant policy supplied to GridSignal — not a judgment GridSignal makes. The default is that nothing is curtailable until explicitly marked, so an integration that omits the policy degrades to the v1.9 behavior rather than to an unbounded one.

### 23.5 Scheduler write-back: the WorkloadCommand contract

The mirror of the Section 10 WorkloadSignal. Same discipline: explicit contract, idempotent by identifier, validated before use, audited as a control action.

| **Field** | **Type** | **Notes** |
|---|---|---|
| command_id | string | Globally unique, GridSignal-assigned. Dedupe key for retries, on the Section 17.1 pattern |
| site_id / job_id | string | Target of the action |
| action | enum | defer \| power_cap \| suspend \| preempt — the four ladder tiers of 23.2 |
| target_value | number | Required for power_cap (watts per device); otherwise omitted |
| authority | object | Operating tier at issue time, and reviewer identity where acknowledgment was required |
| expires_at | ISO-8601 UTC | After which the scheduler shall revert the action unilaterally — see the dead-man rule in 23.6 |

The scheduler shall acknowledge each command. An unacknowledged command past its timeout escalates to the operator and is not silently retried: a retry loop against a scheduler that is refusing commands produces neither the load reduction nor the alert that the situation requires. Every issued command is recorded as a ControlEvent (18.4) — a curtailment is a control action in exactly the sense a turbine start is, and belongs in the same audit trail.

### 23.6 Safety interlocks

- **Site floor.** A configured minimum load is never curtailed: control-plane infrastructure, cooling, life-safety and building systems. The floor is a hard bound checked before a command is composed, not a policy applied afterward.
- **Degraded forecasts do not curtail.** A forecast segment carrying low_confidence: invalid_payload or low_confidence: unmapped_hardware shall not trigger autonomous curtailment at any ladder tier. Acting destructively on a forecast the system has already flagged as unreliable is the worst available outcome, and it is reachable without this rule.
- **Dead-man expiry.** Every command carries expires_at. If the GridSignal-to-scheduler connection is lost while curtailment is active, the curtailment lapses rather than persisting — a partitioned controller must not be able to hold a customer's fleet down indefinitely.
- **Curtailment is bounded by prediction, not by present state.** The controller may curtail only up to the magnitude of the predicted uncoverable gap. It has no authority to reduce load below what the reserve arithmetic justifies, which prevents a runaway from a single bad forecast.

### 23.7 Scheduler-side ramp limiting, and what prediction adds to it

There is a cheaper way to prevent a synchronized job start from producing an unmanageable step-load than predicting it, and this specification is obliged to state it plainly rather than leave a reader to work it out. Bring every accelerator in a starting job up under a power cap and release the cap over sixty to ninety seconds. The step becomes a ramp, in software, with no forecasting, no electrical integration, and no additional vendor.

**The mechanism is one this document already specifies.** It is Tier B of the curtailment ladder (23.2) applied pre-emptively rather than in response to a shortfall, and it needs the same scheduler write access described in 23.5. A site willing to grant GridSignal that access is a site that could implement a static ramp policy instead, plausibly as a scheduler prolog script. Any positioning that ignores this is positioning against a reader who has not thought about the problem.

**The recommendation is to adopt it.** Where the electrical margin is thin and the throughput cost is tolerable, a static ramp policy is correct engineering and should be the baseline at any site running synchronized training. Recommending it costs this product nothing, because the four limitations below are not addressed by it and are where the value actually is.

### 23.7.1 What a static ramp policy does not solve

- **It taxes every job to protect against a few.** The ramp is applied at every start, including the overwhelming majority that the site's reserve position could have absorbed instantly. The cost is unconditional; the benefit is occasional.
- **It must be tuned for the worst reserve state.** A scheduler applying a fixed ramp has no knowledge of turbine availability, state of charge, renewable output, or grid import at that moment. It must therefore assume the least favorable case at all times, which is precisely when the tax is largest and least often warranted.
- **It addresses one event class in one direction.** Ramp limiting flattens job starts. It does nothing for job endings, where an unmanaged load drop is a frequency excursion in the other direction; nothing for checkpoint valleys (6.2); and nothing at all for the supply-side step-loads of Section 7.1.1 — a severed solar feeder or an inverter trip is a step change with no compute event to rate-limit. The step-load problem is a class; ramp limiting solves its most visible member.
- **It sizes nothing.** A ramp policy prevents an excursion without telling the operator whether their reserve is adequate, how much storage they actually need, or how close to the edge they are running. The insufficient-reserve calculation (7.2 step 4) is a planning instrument independent of real-time dispatch, and is arguably worth more than the dispatch.

### 23.7.2 Adaptive ramp relaxation

The two approaches are not alternatives. Prediction converts a fixed ramp policy into an adaptive one:

| **Reserve position at job start** | **Static policy** | **With GridSignal** |
|---|---|---|
| Ample headroom — turbines online, storage charged, renewable steady | Full ramp applied. Throughput cost paid for no benefit | Ramp relaxed or omitted. The job starts at full rate |
| Marginal headroom | Full ramp applied. Correct, by coincidence | Ramp applied, sized to the measured gap rather than to the worst case |
| Inadequate headroom — reserve check fails | Full ramp applied. May still be insufficient, with no warning either way | Ramp applied, insufficient-reserve alert raised with the shortfall in MW and seconds, and curtailment considered per 23.3 |

Relaxation is issued as a WorkloadCommand of action power_cap (23.5) with a higher target value, and requires no mechanism this specification does not already define. Two constraints govern it:
- **Relaxation requires positively confirmed headroom, not absence of a warning.** The controller shall relax a ramp only where the Section 7.2 reserve check passes against the confidence band's lower bound of available capacity, on the same conservative-by-default principle as Section 12. A forecast segment carrying any low_confidence tag does not support relaxation (TC-75).
- **Loss of the forecast falls back to the static policy, not to no policy.** If GridSignal becomes unavailable, the site's baseline ramp policy remains in force and simply stops being relaxed. The failure direction is toward the conservative behavior the site had before this product was installed (TC-76). This is the same fail-safe posture as LP-1, applied to a capability that could otherwise fail toward an unprotected state.

### 23.7.3 The comparison is quantitative, and the quantities are unmeasured

Whether adaptive relaxation is worth its complexity reduces to two numbers this specification cannot supply:
- **τ_ramp — the throughput cost of a static ramp,** as a fraction of job wall-clock time. Determined by how long the ramp lasts relative to job duration and by how much throughput is lost while capped, which is workload-dependent in the way CL-1 already describes.
- **f — the fraction of job starts at which the reserve check would fail** without intervention. A property of how a site is provisioned relative to its job mix.

The static policy costs approximately τ_ramp on every job. Adaptive relaxation recovers roughly τ_ramp × (1 − f) of that, at the cost of operating a forecasting system. The honest reading of this arithmetic is that it can go either way: a site with a small τ_ramp and a large f should run the static policy and not buy anything, while a site with a material τ_ramp and a small f — well-provisioned, occasionally stressed — is where the value concentrates. Both numbers are measurable in a single design-partner engagement and neither has been measured (CL-5).

**The specification states this because the alternative is worse.** A document that omitted the cheapest competing approach would be discovered to have omitted it, at the least convenient moment, by exactly the kind of technically strong buyer whose adoption matters most.

### 23.8 Open items

- **CL-1 — Power-cap yield per hardware profile.** Tier B yield is unmeasured and is workload-dependent in a way the hardware profile library does not currently express. Needs a per-profile cap-response curve from design-partner data.
- **CL-2 — Checkpoint-boundary latency.** Tier C suspends at the next checkpoint, but the interval between checkpoints is a property of the customer's training configuration and may be many minutes. The controller currently has no way to know when the next boundary will arrive, which makes Tier C's time-to-effect unbounded. Section 6.2 checkpoint detection gives evidence of past cadence; whether that is sufficient to predict the next one is untested.
- **CL-3 — Economic curtailment authority.** Deferred by 23.3. Requires a commercial framework — who is compensated, under what SLA — before it is a specification question.
- **CL-4 — Multi-tenant fairness.** Priority ordering within a curtailment tier is site policy, but nothing here prevents the same tenant being curtailed on every event. Repeated selection of the same victim is a fairness property that policy alone does not guarantee.
- **CL-5 — The throughput tax is unmeasured.** Section 23.7.3 defines the two quantities that decide whether adaptive ramp relaxation is worth operating — τ_ramp and f — and supplies neither. Until both are measured at a real site, the commercial case for this capability rests on an assumption rather than an argument. This is the highest-value measurement in the residual list, because it is cheap to obtain and it can invalidate a positioning claim rather than merely refine a constant.

## 24. Grid Procurement and Reserved Capacity

### 24.1 The supply model

Grid import is not a smooth dial. Modelling it as one — as a bottomless source available on demand — is the single most common way a microgrid model produces answers that do not survive contact with an interconnection agreement. Three distinct quantities:

| **Quantity** | **Availability** | **Lead time** | **Counts toward reserve check?** |
|---|---|---|---|
| P_grid_firm | Contracted capacity, continuously available | None | Yes — firm |
| P_grid_reserved(t) | Purchased in advance for a specific window; firm once held | T_reserve — hours, market-dependent | Yes, within its window |
| P_grid_spot | Whatever the interconnection will carry beyond the above | None, but availability is not guaranteed | No — non-firm |

**The consequence for the reserve check.** Only firm and reserved capacity may be counted in the Section 7.2 step 4 shortfall arithmetic. Non-firm spot import may reduce the load the dispatchable fleet actually serves, but it may not be credited as coverage — the same rule, and for the same reason, as non-dispatchable renewable output in 7.1.1. Capacity that can vanish is not reserve.

**Two clocks, again.** T_reserve is measured in hours; Δt_lead is measured in tens of seconds. Procurement can therefore never respond to a queue event, and no amount of engineering will make it do so. It responds instead to the rolling 15-minute-to-4-hour forecast of FR-1.3 — which makes this the first capability in the specification where the long-horizon forecast drives a real action rather than a dashboard line. The short-horizon loop stages turbines, storage, and curtailment; the long-horizon forecast buys capacity. Conflating them produces a procurement system that is always too late and a dispatch system that is always too slow.

### 24.2 The reservation decision

A ReservationProposal is generated when the FR-1.3 horizon forecast predicts sustained demand exceeding firm capacity plus available generation, for a window long enough that reservation lead time can be met. Inputs: the horizon forecast and its confidence band; the market price curve; existing reservations; marginal cost of on-site generation including the amortized capital term from 21.2; and projected BESS state.

Sizing uses the confidence band's upper bound for demand and its lower bound for available generation — conservative in the same direction as Section 12, because under-reserving is a reliability event while over-reserving is a cost overrun. That asymmetry should be stated in the proposal rather than hidden in a point estimate.

### 24.3 Authority: spending money is a different class of action

**No reservation is ever purchased autonomously, at any operating tier.** This is a deliberate departure from the tiering model that governs every other action in this specification, and the reason is that the failure modes are not comparable. An erroneous turbine ramp costs fuel and is reversible within seconds. An erroneous procurement commitment is a contractual obligation that survives the correction of the forecast that produced it. Autonomy is appropriate where the system can undo its own mistakes, and procurement is the clearest case in the product where it cannot.

**Budget bounds.** Each site carries a configured procurement ceiling per window and per billing period. A proposal exceeding it is rejected at generation time and never reaches a reviewer — the same automatic bounds mechanism as Section 21.6, applied to currency rather than to physical parameters.

### 24.4 Open items

- **GP-1 — Market model.** Reservation products, lead times, and settlement differ substantially between ISOs and RTOs, and again outside North America. This section specifies the shape of the decision, not any particular market's mechanics, and a design-partner interconnection agreement is needed before it can be made concrete.
- **GP-2 — Price feed.** No source, format, or update cadence for the price curve is specified. It is an external dependency of the same weight as the scheduler integration and has had none of the same attention.
- **GP-3 — Demand charges.** Commercial tariffs commonly bill on peak demand within a period, which means a single 15-minute excursion can dominate a monthly bill. Nothing here models that, and it may well dominate the economics the Section 21.2 cost workstream is trying to optimize.
- **GP-4 — Islanded sites.** A site with no grid connection has no procurement surface at all. Page 5 of the console (19.6) and this entire section must degrade cleanly to absent rather than to empty, since islanded operation is a target deployment rather than an edge case.

## 25. Network Telemetry Ingestion

### 25.1 Role, and the causality constraint

Optical switch telemetry — throughput, error counters, and optical power from the interconnect fabric, on current merchant and vendor silicon — see the capability tiers in 25.3 — correlates strongly with training-job activity. Collective-communication traffic rises when a distributed job is running and falls when it is not, and the correlation is tight enough to be tempting as a forecasting input.

**It must not be used as one.** Interconnect traffic is a consequence of compute execution, not an antecedent of it. Traffic appears once the job is already running and already drawing power — it is on the wrong side of the causality chain from the queue events that give Section 2's foundational 30–60 seconds of lead time. A forecast driven by network telemetry would be reactive with extra steps: it would appear to work in testing, correlate well against measured load, and quietly reduce the system's lead time to approximately zero. This is the failure mode that is dangerous precisely because its symptoms look like success.

Network telemetry therefore has no path into the real-time staging loop, and this is a structural exclusion of the same kind as Section 21.1's exclusion of model inference. Four roles remain, and they are genuinely valuable:
- **Corroboration.** For each predicted job start, whether a corresponding traffic rise occurred within Δt_lead plus a margin. A prediction with no corroborating traffic is a false positive; a traffic rise with no preceding prediction is a missed job, most likely a scheduler integration gap. Both feed the forecast-error attribution workstream (21.2) with a signal that measured power alone cannot provide, because power tells you the forecast was wrong and traffic tells you where in the chain it broke.
- **Job-phase discrimination.** A checkpoint write and a job ending look similar in the power trace, which is why Section 6.2 needs a heuristic at all. They look quite different on the fabric: a checkpoint shifts traffic from many-to-many collective patterns toward sustained storage egress — a characteristic elephant-flow signature against a falling collective rate — while a job ending drops both to baseline and does not produce the storage burst. The discriminating feature is the storage flow, not the magnitude of the drop, which is precisely the information the power trace cannot carry. This is an independent signal for exactly the ambiguous case where 6.2 currently holds staging and flags uncertain — see 25.3.
- **Coverage fallback.** At a site where scheduler integration does not yet exist, network telemetry supports degraded, reactive detection. This is explicitly worse than the product's core mechanism and shall be tagged as such, with a data-quality tag and widened confidence band on the same mechanism as Section 5.1. It buys coverage during commissioning; it is not a substitute for the queue integration.
- **Its own operations.** Throughput, link state, error rates, and optical power are worth monitoring for their own sake, and the fabric is a large power consumer in its own right.

### 25.2 Data contract: NetworkTelemetry

| **Field** | **Type** | **Notes** |
|---|---|---|
| switch_id / site_id | string | Source device and its site |
| timestamp | ISO-8601 UTC | Same ±2 s NTP requirement as Section 11.4 |
| interface_id | string | Port or logical interface |
| throughput_rx / tx | number (bps) | Sampled, not counter deltas — the consumer should not have to infer rate from counters |
| error_counters | object | CRC, drops, link flaps |
| optical_power_tx / rx | number (dBm) | For link health and predictive transceiver failure |
| sample_interval_ms | integer | Required: phase discrimination (25.1) needs sub-second granularity and degrades to useless at 30-second polling |

**Streaming, not polling.** Model-driven streaming telemetry (gNMI or equivalent) rather than SNMP polling, because the phase-discrimination role depends on resolving transitions that a polling interval will average away. NetworkTelemetry events pass through the same validation, quarantine, and idempotency path as WorkloadSignal (17.1, 17.2) — a second ingestion path with different rules would be a second set of bugs.

### 25.3 Hardware-plane signals and platform capability tiers

The contract above is the minimum. Current fabric silicon instruments considerably more than throughput and error counters, and several of those signals bear directly on the roles in 25.1 — particularly phase discrimination, which throughput alone serves poorly.

| **Signal class** | **What it provides** | **Serves which role (25.1)** | **Availability** |
|---|---|---|---|
| Port utilization and rate | Baseline throughput per interface | Corroboration; fabric operations | Universal |
| Microburst detection | Sub-millisecond transient congestion that averaged rate reporting hides | Phase discrimination; corroboration timing | Current generation |
| Elephant-flow detection | Identification of large sustained transfers, distinct from many-small collective traffic | Phase discrimination — the checkpoint signature (25.5) | Current generation |
| Congestion and queue-depth tracking | Buffer occupancy and congestion events, including signalling to endpoints | Phase discrimination; fabric operations | Current generation |
| Delay measurement and tail timestamp | Per-hop latency and precise departure timing | Phase discrimination | Newer generations |
| In-band flow telemetry | Per-flow path and timing metadata carried with traffic | Phase discrimination; deep diagnostics | Newer generations; high volume |
| Sampled flow export | Statistical flow records | Corroboration where richer signals are unavailable | Universal |

**Capability tiers, not a hardware requirement.** Fabric silicon is on an annual-refresh cadence and the signal set differs by generation, by platform, and by software release. Current-generation top-of-line parts are announced well ahead of shipment; the orderable platform at any given site is typically a generation behind the announcement that motivated the integration.

| **Tier** | **Representative capability** | **Signals assumed available** | **Consequence for 25.1 roles** |
|---|---|---|---|
| Baseline | Any platform with streaming telemetry export | Utilization, error counters, sampled flow | Corroboration and fabric operations only. Phase discrimination unavailable |
| Current | Deployable today — 51.2 Tbps class, large on-die shared buffer | Baseline plus microburst, elephant flow, congestion tracking | All four roles available at reduced timing resolution |
| Emerging | Announced ahead of shipment — 102.4 Tbps class, 1.6 Tbps ports | Current plus delay measurement, tail timestamp, in-band flow telemetry, PTP discipline | All roles, with fabric-internal timing at sub-microsecond |

**The rule that follows.** The Connector Fabric adapter declares which signal classes a given platform provides, and the engine degrades roles rather than failing ingestion when a class is absent. A contract that required emerging-tier signals would be unimplementable at every site that exists today — the same failure the Section 5.3 profile vintage rule exists to prevent, in a different hardware domain. No role in 25.1 shall be specified as requiring a signal above the baseline tier.

### 25.4 Export plane and subscription model

How telemetry leaves the switch is a separate question from what the silicon measures, and the choice has the same shape as the decision already made in Section 3.1 for the forecast loop.

| **Mode** | **Behavior** | **Disposition** |
|---|---|---|
| Event notification / on-change | The source emits when a value changes, rather than on a timer | Preferred. Matches the event-driven design of Section 3.1 and avoids averaging away the transitions phase discrimination depends on |
| Sampled at interval | Periodic emission at a configured interval | Acceptable fallback. The interval is a required field (25.2) because a role that needs sub-second resolution degrades silently at a 30-second interval rather than failing visibly |
| Polled counter retrieval | The consumer reads counters and infers rate | Not used. Rate inference from counter deltas places the sampling decision in the wrong component and loses transition timing entirely |

Transport is model-driven streaming over a structured schema, using the platform's published telemetry model. Per-platform field mapping belongs to the Connector Fabric adapter (parent spec FR-2.1), not here; what this specification fixes is the subscription semantics and the requirement that the emission mode and interval be reported with the data, so a consumer can tell the difference between "quiet" and "not sampled recently."

### 25.5 Use in checkpoint-valley classification

Section 6.2 defines a precedence: an explicit scheduler checkpoint event is authoritative, and the power-shape heuristic is the fallback. Network corroboration is inserted below both:

**scheduler event > power-shape heuristic > network corroboration**

Its only permitted use is to resolve the ambiguous case — where the heuristic has neither confirmed a checkpoint nor a job end within 45 seconds and the engine is holding staging with the job flagged uncertain. A corroborating fabric signature may resolve that case earlier than the grace period would. It may not override either higher-precedence signal, and it may not shorten the hold when it disagrees with them — a tiebreaker that can overrule the primary signal is not a tiebreaker.

### 25.6 Contribution to calibration, and its limits

Fabric telemetry provides an independent trace against which a predicted job start can be checked, which is genuinely useful to the Section 21.2 error-attribution workstream and to the reconciliation counter that governs a site's exit from uncalibrated_site (17.3). The limit needs stating precisely, because the obvious misuse is easy and the failure would be silent.
- **It corroborates occurrence and timing.** Whether a predicted job actually started, and when, within the resolution of the applicable clock class (11.4).
- **It does not measure magnitude.** Throughput is not power. Fabric traffic correlates with compute activity but the relationship is workload-, model-, and topology-dependent, and no coefficient in this specification converts one to the other. Using throughput as a proxy for MW would produce a calibration loop that validates the forecast against a quantity the forecast does not predict.
- **It therefore cannot alone move a site out of uncalibrated_site.** Section 17.3 requires reconciled step-load observations against measured ground truth, and ground truth for a power forecast is measured power. Fabric telemetry can confirm that a step-load event occurred and should be counted; it cannot supply the measured magnitude that makes the observation a reconciliation.

The net contribution is real but bounded: fabric telemetry improves the quality of the observations counted, and identifies predicted events that never happened — which measured power alone cannot distinguish from a correctly predicted event of smaller magnitude.

### 25.7 Open items

- **NT-1 — Correlation thresholds are unvalidated.** What magnitude and shape of traffic change constitutes corroboration, and what distinguishes a checkpoint signature from a job end on the fabric, are asserted here as plausible and measured nowhere. Until they are characterized against real traffic, 25.3 is specified but should not be enabled.
- **NT-2 — Vendor telemetry models.** The contract in 25.2 is vendor-neutral; actual field names, encodings, and available counters differ by platform and software release, and the mapping belongs in the Connector Fabric (parent spec FR-2.1) rather than here.
- **NT-3 — Fabric visibility is not universal.** A colocation operator may have no visibility into a tenant's interconnect at all. Every role in 25.1 must degrade to absent without affecting forecast availability.
- **NT-4 — Clock-class declaration is unverified at ingest.** Section 11.4 demotes a source whose declared discipline is inconsistent with its observed skew, but the test for that inconsistency is not specified. Distinguishing a genuinely PTP-disciplined source from one that declares PTP and drifts requires a reference the ingestion layer does not currently have.

## 26. Agentic Control Architecture

### 26.1 What "agentic" means here, and what it does not

Sections 23–25 add asset classes and actions that benefit from continuous, domain-specific attention: watching turbine runtime and ramp performance, tracking battery degradation, weighing procurement against generation cost, correlating fabric traffic against forecasts. Organizing that work as a set of domain agents is a good fit. Placing those agents in the control loop is not, and Section 21.1 already explains why at length.

**The rule is unchanged and this section does not weaken it.** No agent dispatches. Agents monitor, correlate, diagnose, and propose. Every agent output is a Recommendation record; none is a command. What causes physical action is the authority gate the recommendation passes through — Section 21.6's promotion gate for parameters, Section 7.2's tiering for dispatch, 23.4 for curtailment, 24.3 for procurement. The agent proposes; the gate disposes; the deterministic control plane acts.

This distinction is what makes an agent architecture safe to add to a real-time control system without changing the system's failure characteristics at all. It also means the agents are individually disposable: any of them can be wrong, slow, or absent without a dispatch decision changing.

### 26.2 Agent inventory

| **Agent** | **Watches** | **Proposes** | **Authority ceiling** |
|---|---|---|---|
| Compute & Workload | Job mix, node and accelerator allocation, curtailment eligibility, restoration cost | Curtailment ladder actions (Sec 23); hardware profile mapping gaps | Ladder A/B in Autonomous; C/D never autonomous (23.4) |
| Storage | State of charge, bridging capability against forecast, cycle count, depth of discharge, degradation | Charge scheduling within bounds; replacement forecasting; capacity re-rating | Charge scheduling in Supervised and above; re-rating via 21.6 |
| Generation | Turbine online state, measured versus configured ramp rate, runtime hours, start reliability | Start/stop staging; r_asset recalibration; maintenance windows | Advisory. A turbine start is supervisory control under NFR-3/NFR-4 |
| Thermal | Measured α(t) and Δt_thermal against model, CDU and pump health, approach-temperature trend, coolant condition | α_max/τ/Δt_thermal recalibration; pre-cooling setpoints within band; cooling capacity re-rating; cleaning and flush windows | Advisory for anything the BMS owns. Bounded pre-staging at Supervised and above, never autonomous |
| Procurement | Horizon forecast, price curve, held reservations, marginal generation cost | ReservationProposals (Sec 24) | Never autonomous, at any tier (24.3) |
| Network Telemetry | Fabric throughput, link and optical health, prediction-to-traffic corroboration | Forecast-error attributions; integration-gap findings; job-phase evidence | Advisory only. No dispatch path exists by construction (25.1) |
| Calibration | Rolling forecast error decomposed by profile, class, and tag | Parameter changes (α_max, τ, Δt_thermal, r_asset, profiles) | Via the Section 21.6 gate — this is the v1.7 learning plane, named |

### 26.3 Recommendation lifecycle

There is one governance path, not two. Agent Recommendations use the Section 21.6 four-state lifecycle — proposed, under_review, applied, rejected — with its evidence requirements, its automatic bounds rejection, and its audit trail, unchanged. A parallel mechanism for agents would double the surface on which the system can be wrong about who authorized what.

The Proposal record is extended with four fields that a multi-agent context requires and a single calibration loop did not:
- **originating_agent** — which agent produced it, so a systematically wrong agent can be identified and disabled without disabling the rest.
- **estimated_impact** — in the units that matter for the action: MW, currency, or job-hours. Recommendations are ranked and triaged on this (19.8).
- **reversibility** — full, partial, or none, drawn from the same classification as the curtailment ladder. This drives both the confirmation treatment in the console and the arbitration ordering in 26.4.
- **expires_at** — a recommendation grounded in a forecast is invalid once that forecast is superseded. Recommendations shall expire rather than accumulate; a stale queue is worse than an empty one.

### 26.4 Inter-agent arbitration

A predicted shortfall is visible to several agents at once. Generation proposes a turbine start, Procurement proposes a reservation, Compute proposes curtailment, Storage proposes deeper discharge. All four are reasonable and only some are needed.

**Agents do not negotiate with each other.** They publish Recommendations against a common shortfall record, and a deterministic ranking function selects among them. The ranking is specified rather than model-mediated, because selecting the response to a predicted shortfall is control-adjacent, and a non-deterministic selection would reintroduce exactly the unreproducibility that Section 21.1 excludes from the control path.

**Selection order for closing a predicted gap:**
- 1. Storage discharge — already owned, sub-100 ms, fully reversible.
- 2. Turbine ramp — already owned, seconds, reversible.
- 3. Firm grid import — contracted, no lead time, no new commitment.
- 4. Reserved grid purchase — where lead time permits; commits money, so authorization is required regardless (24.3).
- 5. Curtailment ladder A/B — reversible, no completed work lost.
- 6. Curtailment ladder C/D — last resort, human authorization always.

The ordering is by reliability sufficiency first, then reversibility, then cost. Cost ranks last deliberately: a system that optimizes cost ahead of reversibility will eventually choose an irreversible cheap option over a reversible expensive one, at the exact moment its forecast is wrong.

### 26.5 Failure and fallback

LP-1 (Section 21.1) extends to every agent in 26.2 without modification. Loss of all agents degrades the console to monitoring and leaves the deterministic control plane fully operational on its last applied parameter set. No agent is required for any dispatch decision, agent disagreement never blocks one, and an agent that cannot state the evidence for a recommendation shall not emit it.

This is testable, and TC-48 tests it: with every agent stopped, dispatch behavior over a scenario run must be bit-identical to a run with agents present but their recommendations un-actioned.

### 26.6 Open items

- **AG-1 — Model assignment per agent.** Section 21.3 assigns model roles by task shape for a single calibration workstream. Six agents with different cadences and cost profiles may not map onto that two-model split cleanly, and the interaction with LP-3's undefined cost ceiling is now six times larger.
- **AG-2 — Placement.** Agents are learning-plane components and may run off-site (22.2 Tier 2 locality). Curtailment recommendations are the exception worth examining: they are latency-tolerant relative to NFR-2 but not relative to a developing shortfall, and a cloud-hosted Compute agent behind a degraded WAN may propose a curtailment that is no longer relevant.
- **AG-3 — Arbitration under partial information.** 26.4 assumes all relevant agents have published before ranking. Nothing specifies how long to wait, or how to rank when Procurement is offline and its option is simply absent from consideration rather than known to be unavailable.
- **AG-4 — Alert volume and review capacity.** Six agents generating recommendations against a single operator's attention is a human-factors problem that will determine whether the 21.6 gate functions as designed. An unread queue is autonomous operation with a compliance artifact attached. Grouping, impact ranking, and bulk disposition are stated as requirements in 19.8, but the sustainable volume is unmeasured and probably needs to be a configured budget rather than an emergent property.

## 27. Prescriptive Maintenance and Asset Availability

### 27.1 What "prescriptive" adds, and why it belongs here

This specification is predictive about load and advisory about dispatch. It has no capability at all concerning asset condition. Sections 21 and 26 recommend how to operate assets on a horizon of seconds to hours; nothing addresses whether those assets will still do what their configuration claims next month.

The obvious objection is that maintenance is a solved category with mature incumbents, and that a forecasting product has no business in it. The objection is right about scope and wrong about placement, for two reasons that both follow from the forecasting IP rather than being bolted onto it:
- **The forecast is the scheduling input.** A conventional maintenance system schedules by runtime hours or calendar date, because that is all it knows. GridSignal knows what demand is coming, so it can place an outage inside a predicted trough instead of discovering after the fact that a turbine was in pieces during the week's largest training run. That is the same asymmetry the whole product rests on — intent before execution — applied on a longer clock.
- **Availability is an input to dispatch that the spec currently lacks.** Section 7.2 step 4 computes the reserve check against "available turbine capacity" without ever defining availability. A turbine out for service cannot close a gap, and a turbine whose measured ramp has degraded closes one more slowly than r_asset claims. Today neither fact reaches the arithmetic. That is a correctness gap in the existing specification, not a new feature.

**The unifying observation:** measuring an asset's actual performance against its rated performance is simultaneously a health signal and a calibration signal. A turbine whose measured ramp has fallen from 0.2 to 0.15 MW/s is both due for investigation and mis-configured in Section 7.2 right now. Prescriptive maintenance and parameter calibration are one instrument read two ways, which is why this section reuses the Section 21.6 gate rather than building a second pipeline.

### 27.2 Asset health and degradation model

| **Asset class** | **Condition signals** | **Degradation mode** | **Prescriptive output** |
|---|---|---|---|
| Turbine / engine | Runtime hours since service, start count and start success rate, measured versus rated ramp, exhaust temperature spread, vibration | Ramp-rate degradation; start failure; derated output | r_asset re-rating; service window; start-reliability warning affecting reserve assumptions |
| BESS | Cycle count, depth-of-discharge distribution, measured capacity against nameplate, cell imbalance, thermal excursion history | Energy capacity fade; power capability fade; accelerating fade from deep cycling | Capacity re-rating; replacement horizon; depth-of-discharge policy change |
| Cooling plant / CDU | Approach-temperature trend, flow against pump speed, coolant chemistry, filter differential pressure | Fouling; flow restriction; pump wear | Cleaning or flush window; α_max and cooling-capacity re-rating |
| Grid interconnect | Transformer loading, harmonic distortion, tap-changer operations | Generally outside GridSignal's control | Advisory only. Reported, not scheduled |
| Compute fleet | Out of scope — the customer's asset and the customer's maintenance regime | — | None. Node health is displayed (19.3) but not managed |

**Degradation is re-rating, not merely alerting.** The output of this model is a changed parameter, not a notification. This is what distinguishes it from condition monitoring: an alert tells an operator that an asset is aging, while a re-rating changes what the dispatch arbitrator believes it can do, today, before the next step-load. Section 15 has always flagged r_asset as an engineering placeholder awaiting vendor data; this is the mechanism that keeps it true after the vendor data arrives.

### 27.3 The prescriptive ladder

Structured deliberately like the curtailment ladder in 23.2 — ordered stages of increasing consequence, each entered only when the previous is insufficient.

| **Stage** | **Trigger** | **Action** |
|---|---|---|
| Monitor | Condition signal within normal band | Tracked and trended. No action, no proposal, no alert |
| Re-rate | Measured capability diverges materially from configured | Parameter change proposed through the Section 21.6 gate. Once applied, it changes dispatch immediately — this is the fastest-acting stage, not the gentlest |
| Schedule | Degradation trend projects a limit within the planning horizon | MaintenanceProposal naming a service window that satisfies the reserve requirement for its full duration (27.4) |
| Escalate | Projected failure precedes the earliest window that satisfies the reserve requirement | No good option exists. The operator is presented with the explicit choice: run to failure, accept a reserve-margin violation during service, or plan curtailment to create the window |

**The escalate stage is the point of the section.** Prescriptive analytics that only ever produces comfortable recommendations is decoration. The case worth building for is the one where the projected failure date precedes any window in which the asset can be spared — because that is a decision a human must make, and making it three weeks early with the trade-off stated is the entire value on offer.

### 27.4 Forecast-aware scheduling and the availability state

A MaintenanceProposal names a window, a duration, and the reserve position throughout it. The binding constraint is that the Section 7.2 reserve check must hold for the whole window under forecast demand, not merely at the moment the window opens. A four-hour turbine service that begins during a quiet period and ends during a scheduled 20 MW training run is not a valid window, and scheduling on instantaneous demand rather than forecast demand is exactly how a conventional maintenance system would produce one.

Sizing uses the forecast band's upper bound for demand and its lower bound for remaining capacity — conservative in the same direction as Section 12 and Section 24.2, because an under-sized maintenance window is a reliability event and an over-sized one is an inconvenience.

**Asset availability becomes explicit state.** Every asset carries one of four states, and the Section 7.2 arithmetic consumes it:

| **State** | **Meaning** | **Treatment in the reserve check** |
|---|---|---|
| available | Operating within rated capability | Counted at configured capability |
| degraded | Operating, with measured capability below configured and a re-rating applied | Counted at re-rated capability — not at nameplate, and not excluded |
| scheduled_out | Removed from service within an approved maintenance window | Not counted for the duration of the window |
| unavailable | Failed or removed unexpectedly | Not counted. Triggers an FR-3.3 dispatch re-plan |

The degraded case is the one most easily got wrong. An asset that is working but slower must be counted at what it can actually do: excluding it over-states the shortfall and triggers unnecessary curtailment, while counting it at nameplate under-states the shortfall and is how a reserve check passes shortly before an excursion.

### 27.5 Authority

- **Re-rating flows through the Section 21.6 gate** unchanged — it is a control-relevant parameter change and is governed as one, with the same evidence requirements, bounds rejection, and audit trail.
- **Scheduling is proposal-only at every tier.** Taking an asset out of service dispatches a technician, not a setpoint. There is no operating mode in which this system removes generation from service on its own initiative.
- **Ratings move down more easily than up.** A proposal that lowers a rating is conservative and is treated as any other calibration proposal. A proposal that raises one asserts that an asset can do more than it was believed to, which if wrong is discovered during a shortfall, and it therefore requires a longer observation window and explicit confirmation. This asymmetry is deliberate and should not be normalized away for consistency.

### 27.6 What this is not

The scope boundary is load-bearing, because this is a mature category and the failure mode is drifting into it. This section is not a CMMS: it holds no work orders, parts inventory, technician scheduling, or compliance records, and it interfaces to a system that does. It is not condition-monitoring hardware: it consumes vibration, thermal, and electrical signals and provides no sensors. It does not track warranty or contractual maintenance obligations. Its entire remit is the intersection where asset condition changes what the dispatch arithmetic should believe — everything outside that intersection belongs to somebody else's product.

### 27.7 Open items

- **PM-1 — The scheduling horizon does not exist yet.** FR-1.3 specifies a rolling 15-minute-to-4-hour forecast. Maintenance scheduling needs days to weeks. Nothing in this specification or the parent produces a forecast on that horizon. The Section 21.2 load-pattern workstream discovers recurring weekly structure and is the obvious raw material, but an extended-horizon forecast is an unspecified capability and 27.4 currently depends on it. This is the blocking item for the section.
- **PM-2 — Degradation models are absent.** The condition signals in 27.2 are named; the functions mapping them to projected capability are not, and they are asset-, vendor-, and duty-cycle-specific. No seed values exist, and unlike the Section 5 profile library there is no vendor nameplate to start from.
- **PM-3 — CMMS integration surface.** 27.6 asserts an interface to a maintenance management system without specifying one. Whether GridSignal emits proposals into a CMMS or the CMMS remains authoritative for scheduling is undecided and affects who owns the calendar.
- **PM-4 — Run-to-failure economics.** The escalate stage presents a choice without costing it. Making it more than an alert requires the failure cost, the unplanned-outage cost, and the curtailment cost in comparable units, which is the same cost model Section 21.2 needs and neither section has.
- **PM-5 — Unplanned loss mid-forecast.** This section addresses planned removal. Sudden asset loss while a step-load is staged is an FR-3.3 re-plan under a reserve position that has just changed discontinuously, and the interaction with an in-flight dispatch is not specified here or in Section 7.

## 28. Physical Execution Layer and Power Management System Integration

### 28.1 Where GridSignal sits

Sections 7 and 18 describe dispatch as though GridSignal commands turbines and batteries directly. At a real site it does not. A behind-the-meter AI campus already has a control stack, and the assets in Section 7.1 are reached through it. This section places GridSignal in that stack, names the layers it must not duplicate, and specifies two interlocks that the earlier sections got wrong by omitting the stack entirely.

Four bands exist below day-ahead planning, and they are distinguished by response time rather than by function:

| **Band** | **Horizon** | **What occupies it** | **GridSignal's relationship** |
|---|---|---|---|
| Economic optimization | 15 minutes to 2 days | Cloud or edge energy management: DER optimization, tariff and demand-response response, weather-driven forecasting | Feeds it. Section 24 procurement and Section 27 maintenance scheduling are inputs to this layer, not replacements for it |
| Workload-predictive staging | 30–60 seconds | Empty in every reviewed vendor stack | This is GridSignal. The entire product occupies a band nothing else fills |
| Real-time power management | Sub-second to seconds | Microgrid controller: islanding transitions, topology management, load sharing, droop secondary regulation, spinning-reserve and genset strategies, priority load shedding | Advises it. Never replaces it — see 28.7 |
| Protection and fast shed | Milliseconds | Protection relays, synchro-check, anti-islanding, fast load shedding at tens of milliseconds over station-bus messaging | Must not conflict with it — see 28.4 |

**The band structure is the differentiation argument, stated in someone else's vocabulary.** Incumbent forecasting operates on 15-minute-to-day-ahead horizons using historical and real-time metering, weather feeds, and utility tariff signals. Incumbent real-time control operates reactively in milliseconds. Neither reads job-scheduler queue state, and the seconds-ahead band between them is unoccupied. Section 2 asserts this as the foundational asymmetry; a vendor-stack review corroborates it rather than merely restating it.

### 28.2 What a dispatch command actually commands

Section 18.4 says commands fan out to physical asset classes. Physically they reach switching devices, and the distinction matters because those devices have their own latencies, transition modes, and failure behaviors that no part of this specification has so far accounted for.

| **Device class** | **Role in dispatch** | **Response time** | **Commanded via** |
|---|---|---|---|
| Medium-voltage switchgear and breakers | Feeder and generation connection; point-of-common-coupling isolation | Mechanism-dependent | IEC 61850, Modbus |
| Low-voltage air circuit breakers | Main and sub-distribution; embedded metering feeds measured load back | Mechanism-dependent | IEC 61850, Modbus |
| Automatic transfer switches | Source selection between utility and on-site generation | Closed transition under 100 ms; open transition is a momentary interruption | Vendor interface, Modbus |
| Static transfer switches | Sub-cycle source transfer for IT loads | Approximately 4 ms — a quarter cycle at 60 Hz | Vendor interface |
| Protection relays | Under/over voltage and frequency, anti-islanding, synchro-check for closed-transition reconnection | Station-bus messaging in single-digit milliseconds | IEC 61850 GOOSE, DNP3, Modbus |

**The latency ordering settles a scope question.** Every device above operates one to four orders of magnitude faster than NFR-2's 2-second decision-to-command budget. GridSignal is not, and should not attempt to be, in the switching path. Its value is entirely upstream: bringing a turbine to load, charging a battery, and pre-staging cooling before the reactive layer has anything to react to. A product that tried to compete on switching speed would be competing against hardware, and losing.

### 28.3 Integration surface

The protocols named in the parent specification's Connector Fabric requirements (FR-2.1–FR-2.3) are the right ones, and a vendor-stack review confirms rather than revises them. What it adds is a mapping from GridSignal output to protocol, and one protocol the specification had not named.

| **GridSignal output** | **Target** | **Transport** |
|---|---|---|
| Predicted step-load and staging advisory | Microgrid controller / power management system | Modbus TCP, IEC 61850, or DNP3; vendor supervisory API where available |
| Pre-island trigger for a forecast event | Controller external-trigger input | IEC 61850, or the controller's documented trigger interface |
| Sub-second advisory, where a site permits it | Protection and station bus | IEC 61850 GOOSE |
| Operator-facing state and forecast | IT-side observability and AI-ops tooling | MQTT, REST |
| Asset state and capability (inbound) | Generation, storage, and switchgear telemetry | Modbus TCP, IEC 61850, DNP3, IEC 60870-5-104, OPC |

**Direction of flow is the notable asymmetry.** Established OT-to-IT bridges publish power and cooling data upward into compute-side tooling. GridSignal runs the other way: it consumes IT-side workload intent and produces OT-side staging advice. The two are complementary rather than competing, and a site running both gets a closed loop that neither provides alone. Connector Fabric adapters own the per-vendor field mapping; nothing above belongs in the Forecast Engine.

### 28.4 Interlock with protective fast load shedding

This subsection corrects an omission in Section 23. A microgrid power management system typically includes a protective fast load-shedding function that acts in tens of milliseconds, using station-bus messaging with emission latencies of a few milliseconds. Published figures across vendors cluster between roughly 15 ms and 80 ms end to end. Section 23 specifies a curtailment ladder operating in seconds to minutes. Both shed load. Nothing in v2.1 prevented them from shedding the same load twice.

**The two mechanisms are not variants of each other.** Protective shedding is reactive and exists to preserve the island when generation has already failed to meet load — it is a last-resort stability function, and it is correctly implemented in the protection layer where GridSignal cannot and should not reach. GridSignal curtailment is predictive and exists so that the protective layer never triggers. Four rules follow:
- **GridSignal never issues curtailment in response to an event the protective layer has already acted on.** A shed that has occurred is a load reduction that is already in the measured data. Treating it as an unmet shortfall and shedding again is the double-count this interlock exists to prevent.
- **A protective shed event puts GridSignal into reconciliation.** Measured load has changed discontinuously and every in-flight forecast is stale. The engine shall treat it as an FR-3.3 dispatch re-plan against measured state, on the same principle as Section 22.3: measured reality overrides reconstructed intent.
- **Priority tables must be reconciled, and the protective layer's wins.** Where GridSignal's curtailment priority order (23.4) disagrees with the power management system's shed priority, the latter is authoritative. A divergence between the two is a commissioning defect and shall be surfaced as one rather than silently tolerated, because it means the two systems disagree about what matters at the moment that question is hardest to answer.
- **Protective shed activity is a forecast-quality signal.** A site whose protective layer trips is a site where predictive staging failed. Shed events shall be recorded and fed to the Section 21.2 error-attribution workstream. In a working deployment this counter trends toward zero, which makes it the cleanest available measure of whether the product is doing its job.

### 28.5 Transition modes and what grid connection actually costs

Grid import is modelled in Section 24 as capacity that is either firm, reserved, or non-firm. Physically it is also a transition. On loss of utility supply the transfer from normal to emergency source is necessarily an open transition — a momentary interruption — because only one source is live and there is nothing to parallel with. The retransfer back to utility once it returns can be closed and seamless, since both sources are then available and a synchro-check permits paralleling.

**The asymmetry has a consequence Section 24 did not capture.** Losing firm grid import is not a smooth capacity reduction; it is an interruption whose duration depends on transfer hardware and whose ride-through depends on UPS and static transfer capability. A site already islanded pays nothing when the utility fails, because it has nothing to transfer. A grid-connected site pays the transition. Grid-tie therefore carries a transition-mode attribute — open, closed, delayed, or soft-load — and the reserve check treats an open-transition site as having a coverage discontinuity that BESS and UPS must ride through, rather than a capacity figure that merely decreases.

### 28.6 Scenario Planner and electrical digital twins

Vendor electrical digital twins now model AI-factory power systems from grid connection through to the rack. That is a substantially better source of site electrical topology than anything the Scenario Planner (18.5) can construct from operational history alone, and it is the natural place for a site's protection settings, transition modes, and anchor-source assignment to come from rather than being hand-entered at commissioning. Recorded as PX-4 rather than specified, since the interface is vendor-specific and no design-partner site has yet exercised it.

### 28.7 What GridSignal does not do

This is the third boundary the specification has drawn, and the three are the same boundary. Section 19.6 defers cooling control to the building management system. Section 27.6 defers work orders and parts to a maintenance management system. This subsection defers electrical execution to the power management and protection layers. The pattern is deliberate: GridSignal forecasts and pre-stages, and domain controllers execute. A product that crosses any of these three lines is competing with a mature incumbent on that incumbent's ground, having abandoned the one thing nobody else does.
- Islanding detection and transition, anti-islanding protection, and synchro-check reconnection. These are protection functions with safety and grid-code obligations attached.
- Load sharing, droop secondary regulation, spinning-reserve management, and genset fuel-optimization strategies. All are existing power management system functions and GridSignal duplicating them would produce two controllers with different views of the same plant.
- Protective load shedding — see 28.4.
- Point-of-common-coupling control and grid-code compliance.
- Day-ahead economic optimization. Section 24 produces a procurement proposal informed by workload forecast; it does not replace a tariff- and market-aware optimizer, and the two are complementary inputs.

### 28.8 Open items

- **PX-1 — Which integration point, per site.** A staging advisory can enter at the economic optimizer, at the microgrid controller's external-trigger input, or directly on the station bus. The choice trades latency against safety review burden and is almost certainly per-site rather than a product decision. No default is specified because none is defensible without a design-partner topology.
- **PX-2 — Anchor droop dynamics.** Where a genset is the grid-forming anchor, its droop and inertia response bounds how quickly load can be added — a constraint the r_asset ramp model in Section 7 does not express. Section 7.1.2 records the consequence; the model does not yet exist.
- **PX-3 — P_anchor_reserve derivation.** Currently a commissioning input from an island stability study. Whether it can be observed rather than declared — inferred from measured frequency response to known disturbances — is unexamined and would remove a manual configuration step from every islanded deployment.
- **PX-4 — Digital-twin ingestion.** See 28.6. Site topology, protection settings, and transition modes are presently hand-entered.
- **PX-5 — The white space is a moving target.** The seconds-ahead workload-predictive band is unoccupied as reviewed, and the finding rests on absence of evidence across vendor documentation rather than on any vendor disclaiming the capability. An OT-to-IT bridge already exists in reference designs; reversing its direction to consume workload telemetry is an incremental step for an incumbent. This is a commercial risk to monitor, not a technical gap to close, and it belongs in the competitive review rather than in an engineering backlog.

## 29. Glossary of Terms

This glossary covers prose and architectural terms introduced across Sections 1–28. It deliberately does not duplicate two tables that are already authoritative: the mathematical symbols in Section 3, and the four reconciled time constants (Δt_lead, Δt_thermal, τ, and the BESS bridging window) in Section 9. Where a term below has a quantitative definition, the "Defined in" column points to it rather than restating the numbers here, so that a threshold has exactly one source of truth.

| **Term** | **Meaning** | **Defined in** |
|---|---|---|
| α(t) / α_max | Incremental cooling-load fraction applied to lagged compute draw, and its steady-state value. Not a PUE component — the two are mutually exclusive overhead buckets. | Sec 4.2, 8 |
| BESS | Battery Energy Storage System. With turbines, one of the two dispatchable asset classes; bridges the gap between prediction and turbine ramp completion. | Sec 7.1 |
| BESS bridging window | Derived interval during which BESS alone must cover the declining shortfall: ΔP / r_asset − Δt_lead, when positive. | Sec 9 |
| Checkpoint valley | A brief, severe compute drop during a training job as it writes a checkpoint, distinguished from job completion so that turbines are not ramped down mid-job. | Sec 6.2 |
| Cold start | The state of a newly onboarded site_id with no calibration record, which runs on MVP global defaults and tags all output uncalibrated_site. Distinct from a restart. | Sec 17.3, 22.3 |
| Control plane | The deterministic real-time path — ingestion, forecast, dispatch — bounded by NFR-2. Contains no model inference and depends on one local store. | Sec 21.1, 22.1 |
| ControlEvent | The immutable, logged record of a single command issued to a physical asset. The audit boundary: no command reaches hardware without one. | Sec 18.4 |
| Data-quality tag | A provenance flag attached to a forecast segment that widens its confidence band. The three defined tags — unmapped_hardware, invalid_payload, uncalibrated_site — are independent and can co-occur. | Sec 5.1, 12, 17.2, 17.3 |
| Dedupe key | The tuple (site_id, job_id, event_type, event_id) used to discard redelivered events within a 15-minute rolling window. | Sec 17.1 |
| DERMS | Distributed Energy Resource Management System. An incumbent product category; relevant as prior art for Section 20. | Sec 20 |
| Dispatch arbitration | The rule that stages turbines and BESS against a predicted step-load: turbines ramp immediately, BESS covers the shortfall and tapers as turbines catch up. | Sec 7.2 |
| DispatchPlan | The ranked, staged sequence of actions produced by the Arbitrator, translated into ControlEvents before reaching any asset. | Sec 18.3, 18.4 |
| Dual-clock staging | Modeling mechanical ramp lag and thermal/cooling lag as two independent delays against one predicted compute event, to avoid the compound step-load. | Sec 2, 7, 8 |
| Edge appliance | The site-local host running the entire control plane and Tier 0 store. Chosen so that no WAN dependency sits inside the NFR-2 budget. | Sec 21.1, 22.1 |
| EMS / BMS | Energy Management System / Building Management System. The incumbent reactive, sensor-driven platforms GridSignal is differentiated against. | Sec 2 |
| generic_fallback | The conservative default hardware profile applied when a reported hardware_profile_id is not in the site library. Degrades precision, never availability. | Sec 5, 5.1 |
| Hardware profile | A versioned, site-configurable entry mapping a hardware identifier to a rated per-node or per-cabinet draw. The library is treated as non-public know-how. | Sec 5, 20 |
| Hot window | The configurable period (default 90 days) for which Tier 1 retains Forecast and ControlEvent records before export to Tier 2. | Sec 22.2 |
| Insufficient-reserve alert | A warning computed at staging time — before any shortfall materializes — when required ramp time exceeds available lead time and bridging capacity. | Sec 7.2, 7.3 |
| Learning plane | The non-real-time analytics layer: correlation, calibration proposals, cost analysis, reporting. May propose parameter changes; may never participate in a control decision. | Sec 21.1, 21.2 |
| Learning store | The per-site, GridSignal-operated state store behind the learning plane. Structured and write-ahead-logged — explicitly not a vector/RAG index. | Sec 21.5 |
| MAPE | Mean Absolute Percentage Error. The forecast-accuracy metric reported per load type, decomposed by hardware profile, workload class, and data-quality tag. | Sec 12, 21.2 |
| Micro-ramp | The small, fast power excursion characteristic of inference serving (±500 kW over ~10 s), modeled from request-queue depth rather than node count. | Sec 6 |
| Net dispatch requirement | P_total(t) − P_renewable(t): the load the dispatchable fleet must actually serve. Section 7.2's ΔP is a change in this quantity, not in P_total(t). | Sec 7.1.1 |
| Non-dispatchable renewable | On-site generation that can be measured and forecast but not commanded — solar PV in this version. An input to the arithmetic, never a participant in it. | Sec 7.1.1 |
| Promotion gate | The four-state review pipeline (proposed, under_review, applied, rejected) through which a machine-derived parameter change must pass before affecting dispatch. | Sec 21.6 |
| Proposal | A single candidate parameter change or correlation derived by the learning plane, carrying its evidence, observation window, and reviewer audit trail. | Sec 21.6 |
| PUE / PUE_base | Power Usage Effectiveness, and the instantaneous, non-cooling portion of it used here (distribution, conversion, and UPS losses). | Sec 3, 4.1 |
| Quarantine | The disposition of an event failing schema or domain validation: logged in full, never applied to a forecast, with a structured rejection returned to the source. | Sec 17.2 |
| Ray / Slurm / Kubernetes | The job schedulers and orchestrators GridSignal reads. Their queue state is the predictive signal the entire product rests on. | Sec 1, 2 |
| S3-compatible object storage | The specified interface for Tier 2, with a hosted default and an on-premises implementation for air-gapped sites. Interface, not vendor. | Sec 22.1, 22.5 |
| SCADA | Supervisory Control and Data Acquisition. A source of facility telemetry, and — being sensor-based — structurally too late in the causality chain to drive proactive dispatch. | Sec 18.1 |
| Step-load | A rapid, sustained change in electrical demand. The event class the entire forecast and staging model exists to anticipate. | Sec 4.4, 6 |
| TDP | Thermal Design Power. The rated sustained draw a processor is designed to dissipate; training jobs run at 95–100% of it. | Sec 6 |
| Tier 0 / Tier 1 / Tier 2 | The three storage tiers: local control-plane state on the edge appliance; site history and audit; analytical and archival object storage. | Sec 22.2 |
| uncalibrated_site | The data-quality tag carried by every forecast from a site still running on MVP global defaults, applied in addition to any other widening. | Sec 17.3 |
| WAL (write-ahead log) | The durability mechanism required of Tier 0 and the learning store, so that "in-memory" describes the read path rather than the durability guarantee. | Sec 21.5, 22.2 |
| WorkloadSignal | The validated, deduplicated job-lifecycle event that is the engine's sole workload input. Its required fields are the input data contract. | Sec 10, 17.1 |
| Curtailment ladder | The four ordered tiers by which load is reduced — defer, power-cap, suspend, preempt — exhausted lowest-cost first. Tiers C and D are never autonomous. | Sec 23.2, 23.4 |
| Corroboration | Confirming after the fact that a predicted job start produced the expected interconnect traffic. A forecast-quality instrument, never a forecast input. | Sec 25.1 |
| Firm capacity | Supply that can be counted toward the reserve check because it cannot vanish without notice. Non-firm supply may reduce served load but never closes a reserve gap. | Sec 24.1, 7.1.1 |
| P_curtailable(t) | The portion of compute draw that site policy has marked eligible for curtailment. Zero by default until explicitly configured. | Sec 3, 23.4 |
| Recommendation | An agent-produced proposal carrying originating agent, estimated impact, reversibility, and expiry. Never a command. | Sec 26.3 |
| Reservation lead time (T_reserve) | The advance notice required to purchase grid capacity — hours, against Δt_lead's tens of seconds. The reason procurement runs on the long-horizon forecast. | Sec 24.1 |
| Restoration asymmetry | Curtailment takes seconds; putting the load back costs a full Δt_lead plus checkpoint reload. Restoration is itself a staged step-load. | Sec 23.2 |
| Site floor | The configured minimum load never curtailed under any circumstance: control infrastructure, cooling, life safety. | Sec 23.6 |
| WorkloadCommand | The write-back mirror of WorkloadSignal: the contract by which GridSignal asks a scheduler to curtail. Idempotent, audited as a ControlEvent, and expiring. | Sec 23.5 |
| Availability state | One of available, degraded, scheduled_out, or unavailable. Consumed directly by the Section 7.2 reserve check. | Sec 27.4 |
| Counting unit | The unit a hardware profile declares node_count to be expressed in — chassis, cabinet, package, die, or accelerator. Undeclared units are a 2× forecast error waiting to happen. | Sec 5.2 |
| MaintenanceProposal | A proposed service window that satisfies the reserve requirement for its full duration under forecast demand. Proposal-only at every tier. | Sec 27.4 |
| Pre-cooling | Lowering cooling setpoints ahead of a predicted step-load, using thermal mass as short-duration storage. Reduces the gap rather than closing it. | Sec 8.1 |
| Prescriptive ladder | Monitor, re-rate, schedule, escalate — ordered stages of response to asset degradation. | Sec 27.3 |
| Profile vintage | The hardware generation a profile describes and the date its rated draw was established. Untracked vintage ages silently across a 15× density range. | Sec 5.3 |
| Re-rating | Changing an asset's configured capability to match measured capability. Affects dispatch immediately once applied; lowers more easily than it raises. | Sec 27.2, 27.5 |
| Shiftable load | Load that can be moved earlier rather than removed — cooling via pre-staging. The third load class alongside firm and curtailable. | Sec 8.1 |
| Thermal headroom | Additional compute load the cooling plant can absorb before approach-to-limit, and the time to reach it. The thermal counterpart of bridging capability. | Sec 19.6 |
| Anchor source | The island's voltage and frequency reference, operating in V/f mode. Where the BESS holds this role its bridging capability is reduced by P_anchor_reserve. | Sec 7.1.2 |
| Closed / open transition | Whether a source transfer parallels both sources (seamless) or breaks before making (momentary interruption). Loss of utility is necessarily an open transition. | Sec 28.5 |
| GOOSE | Station-bus messaging on IEC 61850, with emission latency in single-digit milliseconds. The transport of the protective layer GridSignal must not conflict with. | Sec 28.2, 28.4 |
| Grid-forming / grid-following | Whether an inverter establishes the voltage and frequency reference (V/f) or follows one (P/Q). Determines whether a BESS carries anchor duty. | Sec 7.1.2 |
| Protective fast load shed | The reactive stability function that sheds load in tens of milliseconds when generation has already failed to meet it. Distinct in purpose and layer from Section 23 curtailment. | Sec 28.4 |
| Reconciliation | The state GridSignal enters after a protective shed: measured load has moved discontinuously, in-flight forecasts are stale, and dispatch re-plans against measured reality. | Sec 28.4 |
| Workload-predictive band | The 30–60 second horizon between day-ahead economic optimization and millisecond reactive control. Unoccupied in reviewed vendor stacks; the band this product exists to fill. | Sec 28.1 |
| Capability tier | Baseline, current, or emerging — the fabric signal classes a given platform provides. Roles degrade when a class is absent; ingestion does not fail. | Sec 25.3 |
| Clock class | The timestamp-accuracy requirement for a source class. Cross-source correlation inherits the looser of the two clocks involved. | Sec 11.4 |
| Elephant flow | A large sustained transfer, distinguishable from many-to-many collective traffic. The storage-egress signature that separates a checkpoint write from a job end. | Sec 25.3, 25.5 |
| Event notification / on-change | Telemetry emitted when a value changes rather than on a timer. Preferred over sampling, for the same reason Section 3.1 is event-driven. | Sec 25.4 |
| NetworkTelemetry | The second ingest event class. Shares validation and idempotency with WorkloadSignal; dispatch-path ineligible by contract, not by convention. | Sec 10, 25.2 |
| PTP (IEEE 1588v2) | Sub-microsecond time discipline available on current fabric silicon. Valuable within a clock domain; recovers nothing across domains. | Sec 11.4 |
