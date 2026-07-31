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
