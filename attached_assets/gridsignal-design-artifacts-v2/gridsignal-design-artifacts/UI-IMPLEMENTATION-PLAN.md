# GridSignal Console — UI Implementation Plan v1.0

**Extends the existing frontend. Does not rebuild it.**

| Field | Value |
|---|---|
| Date | July 31, 2026 |
| Extends | `frontend/` — React 18 + TypeScript + Vite + Zustand + Tailwind + Recharts |
| Adds | 5 chart primitives · readiness landing screen · 9 subsystem detail modals |
| Absorbs | The outstanding PUB-1 items and the approved-but-unbuilt UI/UX pass |
| Design source | `docs/mockups/` views 01–15 · `MOCKUP-NOTES.md` |
| Test baseline | 19 vitest · `tsc --noEmit` clean · must not regress |

---

## 0. Read this first

### 0.1 This is not a greenfield build

The console exists and works. Seven routed pages, a WebSocket delta protocol, a Zustand store,
and 19 passing component tests. **Rebuilding it would discard six defects that were found the
hard way:**

| Behaviour | Where it lives | Why it exists |
|---|---|---|
| **Alert latch** | `tickStore.latchedAlert` | The backend flag fires for exactly one tick — 0.5 s at 10× speed. Without latching, the banner flashes and vanishes and Acknowledge is unreachable |
| **Bridging basis** | `bridging_basis` on the tick payload | The panel and the alert must never contradict each other. At t=0 one answered "current demand" and the other "predicted peak" — "full reserve" beside "Insufficient reserve" |
| **Interval-end timestamps** | `TickResult.sim_time_seconds` | The tick labelled t=0 describes state at t=5. A 5 s systematic offset is 8–17% of the Δt_lead window |
| **Decimation, not interpolation** | `tickStore.drainFrame` | Above ~4 Hz tick rate the console shows 1 of N and **disables** interpolation. Interpolating across dropped ticks fabricates a curve the simulation did not produce |
| **Slow-client drop** | `WebSocketHub._safe_send` | A backgrounded tab must never back-pressure the run loop. 250 ms per-send timeout, then drop to resync |
| **19 vitest tests** | `src/test/smoke_panels.test.tsx` | The only thing that has ever executed these components — jsdom has never rendered `ForecastChart` |

**Every one of these is invisible until it breaks in a demo.** They are guarded in §7.

### 0.2 Four requested elements have no data behind them

Building UI for these creates the exact gap that produced five stub pages:

| Requested | Reality |
|---|---|
| **State of health (SOH)** | Not modelled. `BessConfig` carries `rated_mw`, `usable_mwh`, `initial_soc_fraction`. No degradation curve, no cycle counting |
| **24-hour BESS forecast** | The forecast horizon is 30–60 s. A 15 min – 4 hr horizon is designed and unbuilt; 24 hr exists nowhere |
| **Wind** | Proposed amendment PA-2, never built. Solar PV only |
| **Thermal heatmap** | One aggregate cooling zone. Zonal config is not in `SiteConfig`, so a heatmap renders as one coloured rectangle |

**Do not build panels for these.** If they matter for the raise, build the model first. SOH and a
longer BESS horizon are the two worth prioritising.

### 0.3 Three decisions that differ from the brief, with reasons

**No blinking.** ISA-101 and high-performance HMI practice reserve blink for *unacknowledged
critical alarms only*. Decorative blink is the fastest way to signal to anyone who has worked in a
control room that the designer has not. Use instead: a 2 s breathing pulse on the LIVE dot, and
directional flow animation on supply lines. Both convey liveness; neither competes with a real
alarm.

**No mock data.** The console has just finished migrating five stub pages to live endpoints
(W1–W3). New panels read live data or render an honest empty state. A panel that looks right on
invented numbers is a liability in a technical demo.

**Zustand stays; no Redux, no Context rewrite.** The store already holds the alert latch, ring
buffer, decimation and scenario state, and it is covered by tests. Adding a second state library
is churn with no benefit. React stays — switching to Svelte or Vue would discard everything above.

---

## 1. Reconciling the three-panel structure with nine subsystems

The brief asks for `DataCenterPanel`, `BESSPanel`, `PowerSourcesPanel`. The mock-ups define nine
subsystem tiles. **These are compatible — the three are groupings, the nine are members** — but
collapsing to three loses the differentiated tiles.

Grouped layout for the readiness screen:

```
DATA CENTRE            ENERGY STORAGE         POWER SOURCES
├ Compute & Workload   └ Energy Storage       ├ Generation
└ Thermal & Cooling                           ├ Renewable Supply
                                              └ Grid Connection

SYSTEM
├ Forecast Quality     ├ Network Fabric       └ Optimisation Agents
```

**The SYSTEM row is the one to defend.** Forecast Quality tells an operator how much to trust the
panel — rare, and the tile an engineer will linger on. Optimisation Agents states LP-1 on the
landing screen. Neither belongs inside a "data centre" grouping, and folding them away to reach
exactly three panels would remove what makes the screen more than a DCIM clone.

Group headers are labels over a CSS Grid, not separate components. Three components named
`DataCentreGroup`, `StorageGroup`, `SupplyGroup` would each wrap one or two identical tiles — the
grouping is layout, and `SubsystemTile` is the component.

---

## 2. Component architecture

New files only. Existing files are listed where they are touched.

```
frontend/src/
├── charts/                          ← NEW · 5 primitives, the whole visual vocabulary
│   ├── TimeSeries.tsx                 multi-line, grid, event markers, rated ceiling
│   ├── BulletBar.tsx                  actual vs max with a target marker
│   ├── StatTable.tsx                  entity list, per-cell colour
│   ├── StackBar.tsx                   proportional composition
│   ├── GaugeArc.tsx                   radial, for state of charge
│   └── index.ts
│
├── readiness/                       ← NEW · the landing screen
│   ├── ReadinessScreen.tsx            group headers + CSS Grid of tiles
│   ├── ReadinessBanner.tsx            overall verdict + 4 hero figures
│   ├── SubsystemTile.tsx              ONE component, nine instances
│   └── subsystems.ts                  the nine configs — data, not components
│
├── subsystem/                       ← NEW · detail modals
│   ├── SubsystemModal.tsx             shell: header, verdict, 2-col body, why, actions
│   ├── panels/                        nine config objects, one per subsystem
│   │   ├── generation.ts   storage.ts   renewable.ts
│   │   ├── thermal.ts      compute.ts   grid.ts
│   │   └── forecastQuality.ts  network.ts  agents.ts
│   └── useSubsystemData.ts            selectors mapping tick + endpoints → panel props
│
├── components/                      ← EXISTING · touched, not replaced
│   ├── SimClockHeader.tsx             MODIFY: mute DQ chips at rest, relabel "Legend"
│   ├── ProposalsPage.tsx              MODIFY: add type-to-confirm modal
│   ├── ConfirmConsequence.tsx         NEW: the modal itself
│   └── (all others unchanged)
│
├── store/tickStore.ts               ← EXISTING · ADD selectors only. DO NOT touch latch logic
└── App.tsx                          ← MODIFY: Readiness becomes the default route
```

**`SubsystemTile` and `SubsystemModal` are each one component rendered nine times from config.**
Nine hand-written tile components would drift within a week. The configs in `subsystems.ts` and
`panels/` hold the verdict text, metric list, chart selection and thresholds.

---

## 3. Phased plan

Each phase is a separate prompt. Run the gates before starting the next.

### Phase U1 — Chart primitives

```
Build frontend/src/charts/ — five components, no application logic, no data fetching. Props in,
SVG out. Reference docs/mockups/gridsignal-07..15 for the visual grammar; the SVG source files
are the specification.

  TimeSeries   series[] of {label,colour,points,filled}, yMax, markers[], ceiling?, xLabel
  BulletBar    label, value, max, target?, colour, unit, note
  StatTable    columns[], rows[][] with per-cell colour override
  StackBar     rows[] of {label,value,colour}
  GaugeArc     fraction, colour, bigLabel, smallLabel

Use Recharts where it fits (TimeSeries) and plain SVG where it does not (BulletBar, GaugeArc) —
Recharts adds no value for a single bar and costs layout control.

Every component takes a `dense` boolean that reduces padding and font size for tile use; the same
component serves both tile and modal.

Add a vitest per primitive asserting it mounts and renders with representative props.
```

**Gate:** 5 components, 5 new tests, `tsc` clean, existing 19 tests still pass.

### Phase U2 — Readiness screen

```
Build frontend/src/readiness/. ReadinessScreen renders four group headers (DATA CENTRE, ENERGY
STORAGE, POWER SOURCES, SYSTEM) over a CSS Grid of SubsystemTile.

SubsystemTile props: name, state, stateColour, accent, verdict, metrics[3], onClick.
subsystems.ts holds nine configs — see docs/mockups/gridsignal-05-readiness.svg for exact copy.

Every verdict line is phrased against FORECAST DEMAND, not equipment status:
  not "turbine operational"  but  "can cover a 9.0 MW gap within the lead window"
  not "battery 95%"          but  "can bridge the predicted peak for 51 minutes"
That distinction is the product. Do not reword the verdicts to status phrasing.

ReadinessBanner shows the overall verdict plus four figures: dispatchable, lead time, bridge,
subsystems needing attention.

Grid: 3 columns ≥1280px · 2 columns 768–1279px · 1 column <768px. Tiles keep a fixed aspect so
rows align. Use CSS Grid, not Flexbox — the alignment requirement is two-dimensional.

Make Readiness the default route in App.tsx. Keep all seven existing pages reachable; the
existing Overview becomes the live-run view that Readiness hands off to on Start.
```

**Gate:** renders at all three breakpoints; every tile click logs its subsystem id; existing pages
still route.

### Phase U3 — Subsystem modals

```
Build frontend/src/subsystem/. SubsystemModal is the shell — header with status dot, verdict
strip with hero figure, two-column body (chart left, 8 metrics right), secondary row, "why this
matters" prose, and two actions: Open full page (routes to the existing page) and Close.

Nine panel configs in panels/. Each declares: identity line, verdict, hero value, primary chart
spec, secondary element (bullets | table | stackbar), 8 metric rows, and 3 prose lines.
docs/mockups/gridsignal-07..15 are the specification — match copy exactly.

Two rules on metric rows:
  - Where a value does not exist yet, print the honest string ("not enforced", "not instrumented",
    "not configured"). NEVER a plausible placeholder number.
  - Colour carries state: TEAL = confirms readiness, WARN = attention, DANGER = a hard constraint
    or a known gap. Everything else default.

Modal is keyboard-dismissible (Esc), traps focus, and restores focus to the originating tile on
close.
```

**Gate:** nine modals open and close; `tsc` clean; a11y — Esc closes, focus returns, dialog role
set.

### Phase U4 — Live data

```
Wire the tiles and modals to real data. useSubsystemData.ts holds selectors: tick fields from
tickStore, endpoint data from the existing /thermal, /procurement, /network-telemetry,
/proposals routes.

BLOCKER TO CLEAR FIRST: thermal absorbable_mw, time_to_limit_s and approach_rate_mw_s are
computed in api/routes/advisory.py and exist only in the /thermal response — they are not on
TickResult (AA3 audit finding). Serialise all three plus rated_cooling_mw into TickResult and
_tick_result_to_dict so the thermal tile is live rather than polling a second endpoint per tick.
This is the same computed-but-unserialised gap as pre_staging_shift_mw (AA1) and the five fields
in AB3.

Where a subsystem genuinely has no data at rest, render the honest empty state — "no jobs queued",
"no approach in progress" — not a zero that reads as a measurement.
```

**Gate:** start `demo-20mw` and confirm every tile changes state during the run. A tile that never
moves is not wired.

### Phase U5 — The outstanding UI/UX items

```
Three items approved earlier and not yet built:

(a) DQ legend chips render fully coloured on an idle site with no run — four apparent warnings
    that mean nothing, on the first screen anyone sees. Mute to grey borders until the tag is
    present in the current tick. Relabel the row "Legend".

(b) ProposalsPage shows a requires_confirmation badge but Approve is still a direct POST. Add
    ConfirmConsequence.tsx: names the affected jobs, requires TYPING to enable the confirm
    button. Ladder C/D and reservation authorization are the only irreversible actions in the
    console and must not be one click.
    Do NOT compute lost job-hours as estimated_impact_mw × job_count × remaining_ramp_s / 3600 —
    that does not resolve to job-hours. Show affected job count and restoration cost (Δt_lead per
    job) and label it as such.

(c) Configuration widgets in ScenarioBuilder:
      bounded continuous, approximate  → slider + numeric readout + visible min/max
      exact values (rated_mw, mwh)     → numeric input + stepper, NOT a slider
      mutually exclusive ≤5            → radio group with inline consequence text
      larger sets                      → dropdown
      booleans with consequence        → toggle + consequence text, not a tooltip
      piecewise profiles               → small editable table
```

**Gate:** DQ chips grey at rest; C/D approve requires typing; `tsc` clean; 19+ tests pass.

---

## 4. Colour discipline

Colour carries meaning. It is never decorative.

| Colour | Reserved for |
|---|---|
| Teal | Confirms readiness, healthy flow, compute |
| Gold | Gas turbine |
| Yellow | Solar |
| Blue | Battery, cooling |
| Violet | Optimisation agents |
| Grey | Inactive, not connected, advisory-only |
| Amber | Attention — countdown under pressure, alert dock, uncalibrated |
| Red | Cannot bridge, irreversible action, known gap |

Everything else — labels, axes, asset IDs, structure — is muted grey. **Green is not used for
"normal."** Normal is quiet. This is why an amber alert dock is unmissable when it appears.

**Grid Connection is grey, not red.** Islanded is the design, not a fault.

---

## 5. Responsive behaviour

| Width | Layout |
|---|---|
| ≥ 1440 px | Readiness 3 columns; modal 1120 px wide, two-column body |
| 1024–1439 | Readiness 3 columns, tighter gutters; modal 92vw |
| 768–1023 | Readiness 2 columns; modal body collapses to single column, chart above metrics |
| < 768 px | Readiness 1 column; modal is full-screen; hero banner becomes 2 × 2 |

The four hero figures are the responsive anchor — they survive every breakpoint. Everything else
may fold.

---

## 6. Data flow

```
FastAPI ──WS /ws/{run_id}──▶ useTickStream ──▶ tickStore (Zustand)
                                                 │
                                                 ├─▶ ReadinessScreen tiles (selectors)
                                                 ├─▶ SubsystemModal (selectors)
                                                 └─▶ existing Overview / pages

FastAPI ──REST──▶ /thermal · /procurement · /network-telemetry · /proposals
                     └─▶ useSubsystemData (poll on modal open, not per tick)
```

Two rules: **tiles read from the tick stream only** — no per-tile polling, or nine tiles produce
nine request loops. **Modals may poll their endpoint on open**, because only one is open at a time.

---

## 7. Do-not-touch register

An agent asked to "reorganize the entire UI" will reasonably rewrite these. It must not.

| File / behaviour | Rule |
|---|---|
| `tickStore.latchedAlert`, `drainFrame`, `acknowledgeAlert` | **Do not modify.** The latch is why the alert banner is reachable at speed. Add selectors alongside; change no existing logic |
| `bridging_basis` handling | **Do not modify.** Panel and alert must never contradict |
| `sim_time_seconds` as interval-end | **Do not re-derive from tick_index.** Read the stored value |
| Decimation / interpolation split | **Do not interpolate across dropped ticks** |
| `WebSocketHub._safe_send` | Extend, never replace. Per-send timeout then drop is deliberate |
| `src/test/smoke_panels.test.tsx` | **Do not modify or delete any of the 19 tests.** Add new ones |
| Zustand | No Redux, no Context rewrite |
| React 18 + Vite | No framework change |
| Backend `insufficient_reserve_alert` | Fires once at staging time and clears. The latch is a UI concern. **Do not make the backend latch** |

If any of these appears to need changing, **stop and say so** rather than changing it.

---

## 8. Deliverables

| # | Item |
|---|---|
| 1 | `frontend/src/charts/` — 5 primitives + tests |
| 2 | `frontend/src/readiness/` — screen, banner, tile, 9 configs |
| 3 | `frontend/src/subsystem/` — modal shell, 9 panel configs, data selectors |
| 4 | `ConfirmConsequence.tsx` + `SimClockHeader` legend fix |
| 5 | Thermal fields serialised into `TickResult` |
| 6 | `frontend/README.md` — how to run in Replit, component map, where the design source lives |
| 7 | Screenshots of the readiness screen at three breakpoints, plus two modals |

**Documentation rule:** comments explain *why*, not *what*. `// mute at rest — four lit chips on
an idle site read as four warnings` is worth writing. `// set colour` is not.

---

## 9. Gate to run after every phase

```
cd frontend && npx tsc --noEmit && npm run build && npx vitest run
cd ../gridsignal_sim && PYTHONPATH=. python -m pytest tests/ ../audit_tests/ -q
PYTHONPATH=. python scripts/check_plane_separation.py
PYTHONPATH=. python scripts/load_test.py       # 1x wall clock and compute p50
```

Report all four. **The vitest count must not fall.** A test that disappears during a UI
reorganisation is a behaviour that stopped being checked.
