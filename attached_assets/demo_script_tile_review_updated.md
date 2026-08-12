# 2. Tile-by-Tile Review (before pressing play)

Walk the static screen top-to-bottom. Keep this brief — 30–60 seconds per zone — since the live run will re-surface most of it in context.

---

## Header bar

- **Site identity: Riverbend DC-West, islanded microgrid, supervised tier.**
  Call out "islanded" and "supervised" deliberately. Islanded means there is no utility feed to fall back on — every megawatt has to come from on-site assets, which is the hardest version of this problem. "Supervised" means GridSignal is advising and an operator acknowledges actions — not fully autonomous yet. That is an honest maturity signal, not a hedge.

- **Sim clock (top right of header): HH:MM:SS / end, progress bar, speed label.**
  This is the simulation clock, not a wall clock. It shows elapsed sim time, the run endpoint, and the current playback multiplier. Worth a one-line mention — the numbers they are about to see are computed in real time against the physics model, not replayed from a pre-baked trace.

---

## Top status strip (Verdict Band)

- **Run in progress banner ("20s to full load — response already staged"):**
  This is the headline metric of the entire product. Read it exactly as written — the system has already staged turbine and battery response to a load event that has not landed yet. Everything below is detail on how.

- **Data centre / location:**
  Grounds the scenario in a real site profile (San Diego climate, UTC-7). Relevant because thermal lag and solar output are climate-dependent, and the model uses site-specific parameters, not generic defaults.

- **Site Demand / Served / Unserved:**
  Unserved is the number that matters most to this audience. Zero unserved demand, sustained through a step-load event, is the entire value proposition in one field. Point at it now and tell them to watch it stay at zero as the load ramps.

- **Predicted Peak:**
  The forecast output — the number the rest of the system is staging against.

- **Gen-trip cover (N−1 ready / N−1 firm capacity MW):**
  N-1 contingency coverage — can the fleet absorb the loss of its largest online unit without shedding load. Framed in operator vocabulary deliberately; technical investors will recognise it immediately. The MW figure is the firm dispatchable capacity available after the worst single-unit loss. Watch this number narrow during the overload phase.

- **Reserve: sufficient / insufficient:**
  The go/no-go verdict. When this flips to insufficient, the system raises it before the event, not after — that is the point to make if asked "what happens when you are wrong." In the Shaped Load run, watch for this to flip during the overload phase. Flag it in advance: *"this is going to alarm partway through, and that is correct behaviour, not a failure — it is telling us generation alone cannot cover this load. Watch what happens to service anyway."* Do not let an unexplained alarm read as something going wrong live.

---

## Plant column (left)

- **Gas Turbine Fleet:**
  Unit count, online / standby / cold status. This is the slow, expensive, physically constrained asset — the one with the ramp-rate limit that makes prediction valuable in the first place. In the Shaped Load scenario: gt-1 starts hot (online immediately), gt-2 warm (~10 min ramp), gt-3 cold (~5 min ramp). You will see output climb in distinct steps, not a smooth ramp — that stagger is the physical reality the system is working around.

- **Solar PV:**
  Non-dispatchable — an input the system forecasts and works around, not an asset it commands. The weather badge shows live irradiance and sun position. Solar draws from the Mistral weather API at site coordinates; the model uses measured irradiance, not a clear-sky assumption.

- **Battery (BESS):**
  The fast-response bridge. Currently absorbing or charging — worth noting batteries are not just for outages; they are actively cycling to smooth the gap between a step-load landing and turbines catching up. Two limits matter and both are checked continuously: how much power the battery can put out right now, and how much usable energy it has in reserve. A big inverter on a depleted battery cannot help; a full battery behind a small inverter cannot help either. The system evaluates both before it ever tells you reserve is sufficient.

- **Grid Connection (greyed out):**
  Explicitly disabled — this site is islanded. Reinforces that everything served on this dashboard comes from on-site generation alone.

---

## Center narrative panel — "What You Are Watching"

This is annotation, not decoration — it describes the load profile the simulation is about to run through, the generation assets responding to it, and what each phase is testing. For the Shaped Load scenario it covers all five phases (warm-up → 40% normal → 120% overload → recovery → coast), the generation fleet composition, and what to watch for as an operator versus as an investor. Let them skim it themselves; reference it only if they ask "how do I read this diagram."

---

## Delivery path (center)

- **Switchgear / PMS → Distribution → PDU/RPP → Compute Racks:**
  The physical delivery chain the forecast is protecting. The PMS tile explicitly states "GridSignal advises — never commands protection." Point at that line directly — it is the clearest on-screen proof of the advisory boundary.

- **Cooling Plant:**
  Runs on its own thermal lag, staged on a separate clock against the same predicted event. A compute spike does not ambush the chiller plant thirty seconds later because the chiller was pre-staged from the same scheduler signal — not from a power sensor that fires after the load has already landed.

---

## Compute Racks tile and modal

Rack draw is the demand signal the whole system is built around. Click the tile to open the Compute Racks modal — this is worth spending sixty seconds on.

**Modal hero row (top of modal):**
Site IT draw live MW, Site contracted MW ceiling, Reserve cover status (from the same insufficient-reserve flag as the Verdict Band), and Tenants reporting (33 cages total, 21 actively reporting in this scenario).

**Tenant table — three full-telemetry tenants:**

| Tenant | Cage | Scheduler | What it shows |
|---|---|---|---|
| Tenant A | 04-B | **Slurm** | Live jobs from the Slurm queue in slurmrestd wire format — the exact JSON a real `GET /slurm/v0.0.40/jobs/{id}` call returns. Each job shows node range (e.g. `gpu-node[014-029]`), TRES resource strings (`cpu=1536,mem=1920G,gres/gpu=128,gres/gpu:h100=128`), `time_limit`, `features`, `account`, `qos`, and `job_state` array advancing `["PENDING"] → ["RUNNING"] → ["COMPLETING"]` in real time. |
| Tenant B | 07-A | **Kubernetes** | Live jobs as `batch/v1 Job` manifests — the same format returned by `kubectl get job -o json`. Includes `apiVersion`, `metadata.labels`, `spec.template.spec.containers[].resources.limits` (GPU count, CPU, memory), namespace, replicas, and image. |
| Tenant C | 11-C | **Ray** | Live jobs as WorkloadSignal §10 events — the spec GridSignal uses for real Slurm ingestion. Each event carries a ULID `event_id`, `submission_id` (`raysubmit_*` for training, `serve_deployment_*` for Ray Serve inference endpoints), `event_type` transitioning `queued → starting → job_end`, `hardware_profile_id: nvidia-h100-sxm5-8way`, `node_count`, `workload_class`, and — for inference deployments — live `queue_depth` and `request_rate`. |

**Per-tenant row fields:** Scheduler type badge, Draw vs. contracted MW ceiling (the system will not submit new jobs that would push a tenant over their co-location contract), active GPU node count, 60-second ahead forecast draw, consent tier (full-telemetry shared for A/B/C; metered-draw-only for the remaining 28 tenants visible when expanded).

**Point to make:** These are not decorative status badges — the manifest shown in each row is the literal wire-format payload the scheduler would send to GridSignal in a real integration. For Slurm that means a customer can point their existing slurmrestd poller directly at the ingest endpoint today. No middleware, no translation layer.

During the overload phase watch the tenant draw bars approach their contracted MW ceilings as the queue fills faster than jobs complete — that is the exact condition causing the power spike the physics engine is responding to.

---

## Step-Load Incoming panel (LeadTimeCallout)

Four states, advancing in sequence: **AT REST → COUNTING DOWN → RESERVE SHORT → LANDED.**

This is the live prediction surfaced as an operator interface — seconds until full draw, what has already been staged (turbines pre-committed, BESS headroom confirmed, GCC action logged), and — critically — "Nothing required." That is the operator-facing payoff: the system already has this covered, no action needed from the human. Contrast with a reactive system, where this panel would not exist at all — you would find out when the frequency moved.

---

## AlertDock (reserve-gap banner)

When the overload phase fires, a latched "Insufficient reserve" banner appears in the top-right of the Overview panel. It shows:
- Which tick the alert fired on and the corresponding sim timestamp
- A plain-language explanation: BESS cannot sustain the ramp gap at this load level
- An **Acknowledge** button

The latch is deliberate — a one-tick transient does not reset it. The alert stays visible until an operator acknowledges it. This is what a supervised-tier system looks like: it raises, explains, and waits for a human decision rather than auto-resolving. Point at the Acknowledge button and note: "In a fully autonomous tier, this would self-clear after the reserve conditions are met. In supervised mode, the operator is in the loop."

---

## Scheduler Feed / AI Summary

Timestamped log of scheduler events — jobs admitted, node counts, forecast draw — narrated in plain language. This is the literal proof that the signal driving everything above comes from the compute scheduler, not from power telemetry. The log entries are queue events, not sensor readings. That is the lead-time claim made concrete: the system knew about this load 20-plus seconds before it landed because the scheduler told it directly.

In this run the feed is driven by three tenant queues — one on each scheduler protocol the platform supports:

- **Slurm (Tenant A):** HPC batch jobs in slurmrestd format — the same wire protocol a real `slurmctld` cluster uses. Job IDs are real Slurm submission IDs (`raysubmit_*`-equivalent numeric IDs), partitions, accounts, and QoS classes.
- **Kubernetes (Tenant B):** GPU training workloads submitted as `batch/v1` Jobs — the Kubernetes-native job format.
- **Ray (Tenant C):** Distributed training and inference deployments emitting WorkloadSignal §10 events with ULID event IDs and hardware profile mappings.

The feed does not move in neat, evenly-spaced steps — it clusters and bursts the way three independent customer queues actually would. That is deliberate. It is there so this does not look like a scripted trace.

---

## Bottom row — system trust tiles

- **Forecast Quality (flagged "Attention"):**
  Confidence band status. Worth calling out unprompted — showing a live data-quality flag rather than a uniformly green dashboard is a credibility signal. The system knows when its own confidence is degraded and says so. The DQ legend chips in the sim clock header (unmapped hardware / uncalibrated site / invalid payload / stale profile) are the same signal surfaced at a glance — each chip lights when that data-quality condition is active for the current run.

- **Generation Commitment Controller ("Ready"):**
  Holds fleet utilisation and reserve state. Flashes in the UI when a GCC action is logged to the tick stream — turbine commitment decisions, BESS dispatch confirmations. Currently idle and holding.

- **Optimisation Agents ("Armed"):**
  Six human-gated analysis agents. Framed as you would want a technical investor to hear it: "finding patterns a threshold rule cannot — dispatch never waits." Static rules apply a worst-case response to every event; this is what makes the response proportionate rather than blunt.

---

## Run controls (bottom bar)

**Scenario: Shaped Load — 5% → 40% → 120% → 40% → 20% of site capacity.**

State the shape explicitly before pressing play: this is not a simple ramp to peak and hold — it deliberately overshoots to 120%, well past nominal nameplate, then pulls back down. That overshoot is the point: you are watching the system handle a genuine overload event and recover, not a comfortable load that stays within design bounds.

**Site fleet, worth stating up front:** Three 10 MW gas turbines (30 MW total), a 5 MW solar array, and a 6 MW / 8 MWh battery starting at 85% charge. Together reliably good for roughly 40 MW. The scenario pushes demand to approximately 48 MW — 8 MW above nameplate — for a twenty-minute window. Naming the numbers before the run starts is what makes the overshoot land as real rather than abstract.

**GPU Generator auto-arms on start:** When the run begins, the system automatically activates the Compute Racks job generator from the scenario's preset configuration — no manual step required. Jobs begin populating all three tenant queues (Slurm, Kubernetes, Ray) within the first few seconds of the run, with bursts every two to five minutes throughout all five load phases. The scheduler and the physics engine are live-coupled from the moment you press play.

**Speed / duration:** Default is 1× real-time with a 90-minute sim window. Set speed to 10× for a nine-minute walkthrough. The physics, scheduler events, and alert timing all compress proportionally.
