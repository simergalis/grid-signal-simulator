# GridSignal — Investor Screen Mock-up

**Three views, 1600 × 1000, dark theme, SVG (vector, scales losslessly) + PNG.**

| File | View |
|---|---|
| `gridsignal-01-ready.svg` / `.png` | Startup state — what you see on launch, before a run |
| `gridsignal-02-live.svg` / `.png` | Live state at T+25 s — the secondary view showing interactivity |
| `gridsignal-03-annotated.svg` / `.png` | Startup state with 10 numbered callouts and explanations |

The SVGs carry **SMIL flow animation** — supply lines pulse in the direction of power flow, and the LIVE dot breathes. Open the `.svg` in a browser to see motion; the `.png` is a static frame of the same thing.

---

## 1. What the screen is arguing

An investor should be able to answer three questions in about five seconds, without a caption:

1. **Where is the power coming from?** → the flow diagram, line thickness proportional to MW
2. **How much time do we have?** → the countdown, and bridge duration in *minutes*
3. **Is the system coping?** → one word: `ARMED` / `SUFFICIENT` / `INSUFFICIENT`

The single most persuasive frame is view 02. A 20 MW job was queued 25 seconds ago, **has not reached full power yet**, and the turbine is already ramping while the battery covers the gap. Nothing waited for a sensor. That is the product in one picture.

---

## 2. Annotations

| # | Element | What it shows and why it matters |
|---|---|---|
| 1 | **Predictive horizon** | GridSignal reads the job scheduler's queue, not a power meter. It knows a step-load is coming 30–60 s before any current flows. Incumbents react after the load lands |
| 2 | **Bridge duration** | Not "battery at 95%". The operator's question is how many minutes of cover the battery buys *at the shortfall actually predicted*. 51 min here |
| 3 | **Reserve verdict** | Computed, not asserted: turbine ramp rate × lead time vs predicted shortfall. If the battery cannot deliver the required **power**, this reads INSUFFICIENT even at 95% charge |
| 4 | **Source cards** | Colour bar lit = contributing. Grid is greyed because this site is islanded — the "bring your own power" case that motivates the product |
| 5 | **Proportional flow** | Line thickness = megawatts, dashed = idle. The energy balance is readable without reading a number |
| 6 | **IT vs cooling split** | Two separate events 90 s apart, not one. Cooling lags compute — the "double whammy" a reactive system meets twice |
| 7 | **Supply mix** | Solar is labelled an input, never a reserve. It can vanish with no warning, so it is subtracted from demand and never counted toward ramp capability |
| 8 | **Storage panel** | Available power is 17.0 MW, not 18.0 — one megawatt is withheld because this unit is the island's grid-forming anchor and must regulate in both directions |
| 9 | **Forecast curve** | Compute reaches full draw at 45 s; cooling settles ~135 s. This shape is the product's signature and the reason one reactive threshold cannot work |
| 10 | **Scenario launcher** | Nine seeded scenarios, one click. Every number traces to a live simulation field |

---

## 3. Data provenance — every number on screen

This is the table that matters if an investor says *"show me."* Nothing here is invented.

| On screen | Value | Source |
|---|---|---|
| Site draw | 23.95 MW | `P_total = P_compute × (1 + α_max)` — 1900 nodes × 10.2 kW × 1.03 PUE |
| IT / accelerators | 19.96 MW | `p_compute_mw` |
| Cooling plant | 3.99 MW | `p_cooling_mw`, α_max = 0.20 |
| Solar PV | 4.99 MW | `p_renewable_mw` — 25% of peak compute (PROTO-7) |
| Gas turbine | 0 → 25.0 MW | `turbine_output_mw`, ramp 0.2 MW/s |
| Battery power | 18.0 MW rated | `BessConfig.rated_mw` |
| Battery available | **17.0 MW** | `bridging_available_mw` = 18.0 − 1.0 anchor reserve (§7.1.2) |
| Battery energy | 8.0 MWh | `BessConfig.usable_mwh` |
| Charge % | 95% | `bess_soc_fraction` |
| Bridge duration | 51 min | `bess_bridging_seconds` / 60, basis `predicted_peak` |
| Countdown | 45 → 0 s | `dt_lead_next_s` |
| Forecast curves | plotted | `evaluate_tick` physics, α(t) = α_max(1 − e^−(t−90)/20) |

`example_usage.py` prints `P_total=23.954 MW` for demo-20mw. The screen says 23.95.

---

## 4. Four requested elements are **not** in the mock-up, because they do not exist

Putting them in would create exactly the gap this build spent forty defects closing — a screen that survives a slide and fails a live demo.

| Requested | Status |
|---|---|
| **Wind** | Never built. Proposed as spec amendment PA-2; the codebase models solar PV only. A wind turbine icon would be a promise with no code behind it |
| **State of health (SOH)** | Not modelled. `BessConfig` has `rated_mw`, `usable_mwh`, `initial_soc_fraction`. No degradation curve, no cycle counting, no SOH |
| **24-hour BESS forecast** | The forecast horizon is 30–60 s (Δt_lead). A 15 min–4 hr horizon is designed but unbuilt; 24 hr exists nowhere |
| **Thermal heatmap / zones** | One aggregate cooling zone. Zonal configuration is not in `SiteConfig`, so a heatmap would be one coloured rectangle |
| **Grid reliability** | Procurement models firm / reserved / non-firm capacity and a seeded price curve. Reliability is not modelled |

Each is a straightforward addition if it matters for the raise — SOH and a longer BESS horizon are the two I would prioritise. But they should be built, then shown.

---

## 5. One requested behaviour deliberately not used: **blinking**

Blinking is reserved, in ISA-101 and high-performance HMI practice, for *unacknowledged critical alarms only*. Using it decoratively is the single fastest way to signal to an operator — or to an investor who has seen a real control room — that the designer has not been in one.

What is used instead, and is standard: a slow **breathing pulse on the LIVE dot** (2 s cycle) and **directional flow animation** on the supply lines. Both convey liveness. Neither competes with a genuine alarm.

Related: the alert dock uses **latched** state, not a per-tick flag. The reserve alert fires once at staging time and clears on the next tick — under half a second at 10× speed. Without latching the banner would flash and vanish and the Acknowledge button would be unreachable.

---

## 6. Colour discipline

Colour carries meaning; it is never decorative.

| Colour | Reserved for |
|---|---|
| Teal | Healthy flow, system armed, compute |
| Gold | Gas turbine |
| Yellow | Solar |
| Blue | Battery, cooling |
| Grey | Inactive / not connected |
| Amber | Attention — countdown under pressure, alert dock |
| Red | Cannot bridge, irreversible action |

Everything else — labels, axes, asset IDs, structure — is muted grey. This is why the screen reads calm at rest and why an amber alert dock is unmissable when it appears.

---

## 7. Responsive behaviour

| Width | Layout |
|---|---|
| ≥ 1440 px | As drawn: hero strip 4-across, flow diagram and side panels 2-column |
| 1024–1439 px | Side panels drop below the flow diagram; hero stays 4-across |
| 768–1023 px (tablet) | Hero becomes 2 × 2. Flow diagram collapses to a vertical stack: sources → site → load |
| < 768 px | Single column, hero as a 4-row list. Flow diagram replaced by the supply-mix bars — a proportional flow diagram is not legible below ~700 px |

The hero row is the responsive anchor: countdown, predicted peak, bridge duration, and status survive at every breakpoint. Everything else can fold.

---

## 8. What to change before a raise

- **Site name is placeholder** — "Riverbend DC-West" is invented. Use a design partner's site if you have one, or something obviously generic
- **Cell 3 of the live hero** currently shows bridge duration; once the thermal fields are serialised into `TickResult` (agreed in the last UI pass), thermal headroom in MW-absorbable and time-to-limit is the stronger fourth number
- **The forecast chart is the most under-used asset on the screen.** It is the only element showing the two-stage rise, and it sits at the bottom. For a pitch specifically, consider promoting it above the flow diagram

---

## 9. Topology diagram (`gridsignal-04-topology`)

Answers the question the dashboard cannot: **where does GridSignal sit?**

Three bands. **Control plane** on top — signal sources on the right, GridSignal on the left, `WorkloadSignal` flowing right-to-left between them. **Power path** in the middle — turbine, solar, BESS → switchgear/PMS → distribution → PDU → racks → heat → cooling, left to right. **Integration boundary** at the bottom — what GridSignal commands, and what it never commands.

**The crossing is the argument.** Power moves left→right. The signal moves right→left. GridSignal reads intent at the *load* end and acts at the *source* end, before any current flows.

### Three deliberate departures from a conventional data-centre one-line

| Conventional (e.g. MEP Academy's chain) | Here |
|---|---|
| Utility is the primary source | **Grid box is dashed and greyed — "not connected."** Islanded microgrid; this is the "bring your own power" case |
| Generators are `N+1` **backup** | Turbines are **primary generation**, ramp-limited at 0.2 MW/s |
| UPS provides ride-through until gensets start | BESS is the **grid-forming anchor** *and* the bridge — one megawatt of its rating is withheld for frequency regulation |

### Two signal sources, not one

The box is **not** labelled "job scheduler." The contract spans two integration surfaces:

- **Scheduler / orchestrator** (Slurm, Kubernetes, Ray) → `queued`, `starting`, `running`, `scale`, `job_end`, `cancelled`
- **Training framework** (PyTorch, DeepSpeed hooks) → `checkpoint_start`, `checkpoint_end` — *optional*

"Job scheduler" is exact for Slurm and imprecise for the other two: Kubernetes is a container orchestrator, Ray a distributed execution framework. More importantly, no scheduler knows when a training job writes a checkpoint — that comes from framework instrumentation, which is why §6.2 carries a shape heuristic as fallback.

Recorded as **PA-7** (contract split, TC-05/TC-51 wording) and **PA-8** (umbrella terminology) in Build Plan v2.2.

Marking the checkpoint source *optional* makes the integration story stronger, not weaker: two independent sources with a heuristic fallback is more robust than a single dependency.

### The line worth pointing at

The PMS/switchgear box reads **"GridSignal advises — never commands."** The red panel lists islanding, synchro-check, anti-islanding, droop control, and protective load shed. The TC-68 audit on a fully loaded 60-tick run recorded 71 allowed commands and **zero** in all five protection categories. Most vendors will not state that boundary; stating it is what makes everything else credible.

---

## 10. Opening screen — subsystem readiness (`05` / `06`)

Replaces the earlier "ready state" landing screen. Nine clickable subsystem tiles, each opening
a detail modal.

### The reframe: readiness, not health

"Health" is the wrong axis. A conventional DCIM already shows green/amber/red on equipment — an
opening screen that does the same says *"we built a monitoring tool."* GridSignal can answer a
question no incumbent can compute: **not "is this asset working" but "can it do its job when the
next step-load lands."**

So every tile's verdict line is phrased against forecast demand, not against equipment status:

| Tile | Verdict, not status |
|---|---|
| Generation | "Can cover a 9.0 MW gap within the lead window" |
| Energy storage | "Can bridge the predicted peak for 51 minutes" |
| Thermal & cooling | "Full headroom — 4.59 MW absorbable before approach" |
| Renewable supply | "Contributing 4.99 MW — never counted toward reserve" |
| Forecast quality | "Uncalibrated site — confidence bands widened 8%" |

### The two tiles that differentiate

**Forecast quality** is the only tile that reads ATTENTION, and deliberately. A fresh site is
`uncalibrated_site`, so the bands are widened and dispatch sizes off the lower bound. A dashboard
that tells you *how much to trust it* is unusual, and showing that state honestly at startup is
worth more than nine green lights.

**Optimisation agents** reads "6 agents analysing — dispatch never waits for them." The label
says what they do; the verdict carries the constraint. Both halves are needed — "advisory agents"
was internal vocabulary that described what they *aren't*.

### Grid connection is grey, not red

Islanded is the design, not a fault. Colouring it red would misread the entire market position.

### The modal (view 06 — Energy Storage)

Six rows, and the third is the one that matters:

```
Rated power              18.0 MW    nameplate
Anchor reserve           −1.0 MW    withheld for frequency regulation · §7.1.2
Available for bridging   17.0 MW    what the reserve check actually uses
Usable energy            7.60 MWh   of 8.0 MWh usable window
C-rate                   2.25 C     within 0.25–4.0 C plausible band · PROTO-9
Predicted peak shortfall 8.96 MW    below the 17.0 MW ceiling — can deliver
```

The footer explains why the panel is not "battery at 95%": a full battery that cannot deliver the
required **power** bridges for zero seconds. The check is energy ÷ power at the predicted
shortfall, and it returns 0 above the unit's ceiling — so this panel can read CANNOT BRIDGE at
95% charge. That is finding D11 rendered as an operator-facing explanation.

### Build cost, honestly

The tiles are mostly assembly — every field except one already exists in `TickResult` or an
endpoint. The exception: **thermal `absorbable_mw`, `time_to_limit_s` and `approach_rate_mw_s` are
still API-only** (AA3 finding) and must be serialised into `TickResult` before that tile is live.
Same fix already agreed in the UI/UX pass.

### Verification caveat

Same as the topology diagram: the image viewer stopped returning content, so **views 05 and 06
were not visually confirmed.** Checked structurally — 112 texts on the overview and 34 modal-only
texts, zero overflow and zero overlaps in both, with the modal checked by diffing against the base
screen so occluded tile text behind the panel is excluded. That check found and fixed two real
collisions. It does not tell you whether it looks good.

---

## 11. Subsystem detail panels (`07`–`15`)

Nine modals, one template, generated from a shared chart library so the visual grammar is
identical across all of them. Each opens from its tile on the readiness screen.

### Template

```
● SUBSYSTEM NAME          STATUS                              ✕
  identifier line
─────────────────────────────────────────────────────────────────
  VERDICT — one sentence                          [ hero number ]
─────────────────────────────┬───────────────────────────────────
  PRIMARY CHART              │  8 KEY METRICS
  (time-series, 300 s)       │  label            value
                             │  sub-line          ↑ colour = state
─────────────────────────────┤
  SECONDARY (bullets/table)  │
─────────────────────────────┴───────────────────────────────────
  WHY THIS MATTERS — three lines of plain prose
                              [ Open full page ]      [ Close ]
```

### Chart primitives

Five, and they compose into all nine panels — the same decomposition the React build should use:

| Primitive | Where |
|---|---|
| `timeseries` — multi-line, grid, event markers, optional rated ceiling | every panel |
| `bullet` — actual against a max, with a target marker | generation, storage, renewable, thermal |
| `table` — entity list with per-cell colour | compute, grid, forecast quality, network, agents |
| `stackbar` — proportional composition | grid connection |
| `arc` — radial gauge | storage |

### The chart chosen per panel, and why

| Panel | Primary chart | The point it makes |
|---|---|---|
| **07 Generation** | turbine output vs dispatch required, rated ceiling dashed | 5 MW of nameplate sits unused — **ramp rate is the constraint, not capacity** |
| **08 Storage** | SoC falling while discharge rises | bridging is a *duration*, and it consumes the thing that provides it |
| **09 Renewable** | flat output, plus a red trace showing demand **if solar vanished** | the exposure, not the contribution |
| **10 Thermal** | compute and cooling overlaid with 45 s and 135 s markers | the two-stage rise — the product's signature, in one chart |
| **11 Compute** | ramp curve with container-init and full-TDP markers | Δt_lead is a shape, not a scalar |
| **12 Grid** | seeded price curve; firmness stack below | non-firm reduces load but **does not close the reserve gap** |
| **13 Forecast quality** | three traces — upper, point, **lower** | dispatch sizes off the lower bound, so a wider band means more conservative staging |
| **14 Network** | per-switch throughput | it corroborates after the fact; it never originates a forecast |
| **15 Agents** | cumulative agent cycles against the cadence floor | activity is bounded by wall-clock rate limits, not simulation speed |

### Three panels earn their place beyond monitoring

**13 · Forecast quality** is the unusual one. Three traces, and the *lower* bound is the labelled
one because that is what dispatch sizes against. The table below shows each data-quality tag,
its additive widening factor, and whether it is currently active. A panel that tells you how much
to trust it is rare, and it is the one an engineer will linger on.

**09 · Renewable supply** plots a red trace for *"if solar vanished"* — showing the exposure
rather than the contribution. That is §7.1.1 made visible: renewable output is subtracted from
demand and never added to ramp capability.

**15 · Optimisation agents** states the token-budget and spend-tracking gaps in red, on the panel,
rather than hiding them. Two known gaps shown honestly cost less credibility than one discovered
by a reviewer.

### Grounding

Every chart is computed from demo-20mw physics — the same `comp()`, `cool()`, `turb()`, `bess()`
and `soc_series()` functions that produce the other mock-ups. The metric values trace to real
fields; where a value does not exist yet it says so (`"not enforced"`, `"not instrumented"`,
`"not configured"`) rather than showing a plausible number.

### Verification

Structural only — the image viewer has not returned content since partway through this session.
All nine checked: **0 overlaps, 0 overflows** across 520 text elements, after the checker caught
and fixed one marker collision on the compute panel. That check finds clipping and collision, not
whether the result looks good. **Review before use.**


---

## 12. Naming: "optimisation agents", not "advisory agents"

**UI label changed. Internal naming deliberately unchanged.**

| Layer | Term | Why |
|---|---|---|
| Console tile and panel | **OPTIMISATION AGENTS** | Says what they do. A reader who has never seen §26 understands it immediately |
| Code package, spec sections | `advisory/`, "advisory plane" (§21, §26) | Says what they *aren't* — they advise, they do not dispatch. Renaming would break every cross-reference to §21.1, §26.1 and the LP-1 argument |

That split is intentional, not an oversight. The verdict line does the reconciling work:
*"6 agents analysing — dispatch never waits for them."* Label states the function; verdict states
the constraint. "Advisory agents" only ever stated the constraint, which is why it read as
internal vocabulary.

**One consistency note:** the parent specification uses **optimize** (American, 4 occurrences).
The console now uses **optimisation** (British). Pick one register across specs, code comments and
UI copy — it is trivial to fix now and irritating to notice later in a demo.
