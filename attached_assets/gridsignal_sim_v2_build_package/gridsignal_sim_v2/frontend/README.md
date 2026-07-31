# GridSignal Simulator — Frontend

React + TypeScript + Tailwind + Zustand + Recharts console for the GridSignal power-arbitration simulator.

## Quick start

```bash
# From the monorepo root
pnpm --filter @workspace/frontend run dev      # dev server on $PORT

# Build (production)
pnpm --filter @workspace/frontend run build

# Type-check only
pnpm --filter @workspace/frontend exec tsc --noEmit

# Run tests
cd frontend && npx vitest run
```

For the full stack (API + frontend):
```bash
# API server
pnpm --filter @workspace/api-server run dev

# Frontend (separate terminal)
pnpm --filter @workspace/frontend run dev
```

The dev server proxies `/api/*` and `/ws/*` to the API server — see `vite.config.ts`.

---

## Design source

Mockup SVGs live at:
```
gridsignal_sim/docs/mockups/
  gridsignal-01-site-overview.svg      # §19.2 Overview layout
  gridsignal-06-readiness.svg          # §19.7 Readiness tiles layout
  gridsignal-07-generation.svg         # Generation modal
  gridsignal-08-storage.svg            # Energy Storage modal
  gridsignal-09-renewable.svg          # Renewable Supply modal
  gridsignal-10-thermal.svg            # Thermal & Cooling modal
  gridsignal-11-compute.svg            # Compute & Workload modal
  gridsignal-12-grid.svg               # Grid Connection modal
  gridsignal-13-forecast-quality.svg   # Forecast Quality modal
  gridsignal-14-network.svg            # Network Fabric modal
  gridsignal-15-agents.svg             # Optimisation Agents modal
```

Colour vocabulary (`tailwind.config.ts`):
| Class     | Hex       | Meaning                            |
|-----------|-----------|------------------------------------|
| `teal`    | `#3fb6a8` | healthy / ready / compute          |
| `gold`    | `#e0a458` | gas turbine / generation           |
| `solar`   | `#f2c94c` | solar / renewable supply           |
| `battery` | `#4a9fe0` | battery / cooling                  |
| `violet`  | `#9b8ce0` | optimisation agents                |
| `islanded`| `#5a6673` | inactive / islanded / advisory     |
| `warn`    | `#f0883e` | ATTENTION — operator review needed |
| `danger`  | `#f85149` | cannot bridge / critical           |
| `ok`      | `#3fb950` | threshold pass                     |
| `accent`  | `#58a6ff` | tab underline / link               |

---

## Component map

```
src/
├── App.tsx                       Root — layout, page routing (7 tabs)
│
├── readiness/                    U2 — Readiness landing screen (default tab)
│   ├── subsystems.ts             9 static configs (id, name, group, accentColor)
│   ├── SubsystemTile.tsx         Single tile: state + verdict + 3 metrics
│   ├── ReadinessBanner.tsx       Overall verdict + 4 hero figures
│   └── ReadinessScreen.tsx       CSS Grid of tiles grouped under 4 headers
│
├── subsystem/                    U3 — Subsystem detail modals
│   ├── SubsystemModal.tsx        Modal shell (Esc close, focus trap/restore)
│   ├── useSubsystemData.ts       Selectors: tick → tile props (9 subsystems)
│   └── panels/                   Per-subsystem modal content
│       ├── index.ts              PANEL_CONFIGS registry + PanelConfig interface
│       ├── generation.ts         Gold — turbine ramp vs demand
│       ├── storage.ts            Blue — BESS bridge duration + SoC gauge
│       ├── renewable.ts          Yellow — advisory, exposure if lost
│       ├── thermal.ts            Blue — 90 s lag, absorbable headroom
│       ├── compute.ts            Teal — job states, two-stage power draw
│       ├── grid.ts               Grey — islanded by design
│       ├── forecastQuality.ts    Teal — DQ tags, confidence band
│       ├── network.ts            Blue — honest empty state
│       └── agents.ts             Violet — LP-1 guarantee, 6 agents
│
├── charts/                       U1 — Reusable chart primitives
│   ├── TimeSeries.tsx            Recharts multi-line + filled area + ceiling
│   ├── BulletBar.tsx             SVG horizontal bullet: actual vs max + target
│   ├── StatTable.tsx             Two-column metric table with per-cell colour
│   ├── StackBar.tsx              Proportional composition bar + legend
│   ├── GaugeArc.tsx              SVG 200° radial arc gauge (SoC)
│   └── index.ts                  Re-exports
│
├── components/                   Existing components (do not modify alert/latch)
│   ├── RunControlBar.tsx         Scenario picker + start/stop
│   ├── SimClockHeader.tsx        Clock + DQ chips (muted at rest)
│   ├── HeroPanel.tsx             4-cell: Δt_lead, bridge, thermal, AlertDock
│   ├── AlertDock.tsx             F4 rising-edge latch
│   ├── ForecastChart.tsx         Recharts 4-trace forecast
│   ├── AssetReservePanel.tsx     BESS / turbine / reserve breakdown
│   ├── ProposalsPage.tsx         Proposals + ConfirmModal (type-to-confirm)
│   ├── NetworkTelemetryPage.tsx  Read-only network telemetry
│   ├── ProcurementPage.tsx       Grid & procurement
│   ├── ThermalCoolingPage.tsx    Thermal & cooling (live endpoint)
│   ├── ScenarioPlannerPage.tsx   Scenario management
│   ├── ScenarioBuilder.tsx       Slider/radio/pill/dropdown widgets
│   └── ResultsScreen.tsx         Post-run verdict + playback
│
├── store/
│   ├── tickStore.ts              Zustand — ring buffer, drainFrame, alert latch
│   └── scenarioStore.ts          Zustand — scenario CRUD
│
├── ws/
│   └── useTickStream.ts          WebSocket hook
│
├── types.ts                      TickPayload + HistoryPoint + RunMeta + ScenarioSpec
│
└── test/
    ├── smoke_panels.test.tsx      19 existing panel tests (do not modify)
    ├── smoke_charts.test.tsx      11 chart primitive tests (U1)
    └── smoke_readiness.test.tsx   13 readiness + tile + modal tests (U2/U3)
```

---

## Page tabs

| Tab              | Default | Route key      | Description                                      |
|------------------|---------|----------------|--------------------------------------------------|
| Readiness        | ✓       | `readiness`    | 9 subsystem tiles; click → modal. Hands off to Overview on run start. |
| Overview         |         | `overview`     | Live 4-cell hero + forecast chart + asset reserve |
| Proposals & Learning |     | `proposals`    | Agent proposals, confirm-modal approval           |
| Grid & Procurement |       | `procurement`  | Price curves, contracted capacity                 |
| Network Telemetry |        | `network`      | Read-only topology + latency (TC-74)              |
| Thermal & Cooling |        | `thermal`      | Cooling headroom, approach curve                  |
| Scenario Planner |         | `scenarios`    | Scenario CRUD                                     |

---

## Data flow

```
WebSocket /ws/{run_id}
    │
    ▼
useTickStream  →  tickStore.pushTick (pending queue)
                       │
               App.tsx setInterval 250 ms
                       │
               tickStore.drainFrame
                  ├── latestTick  →  all components reading live tick
                  ├── history[]   →  TimeSeries charts
                  └── latchedAlert → AlertDock (F4 rising-edge latch)

Readiness tiles: read latestTick only (no per-tile polling)
Modals (on open): may poll REST endpoints once
  GET /api/thermal
  GET /api/procurement
  GET /api/network-telemetry
  GET /api/proposals
```

---

## Do-not-touch register

These identifiers must not be renamed or restructured:

| Item | Reason |
|------|--------|
| `tickStore.latchedAlert` | F4 rising-edge latch — alert must survive until operator ack |
| `tickStore.drainFrame`   | 4 Hz render loop contract — App.tsx owns the timing |
| `tickStore.acknowledgeAlert` | Clearing path for the latch |
| `bridging_basis`         | Enum value — matches Python enum |
| `sim_time_seconds`       | Interval start, not end — read stored value only |
| `smoke_panels.test.tsx`  | 19 tests — must not regress below this count |
| `WebSocketHub._safe_send`| Python backend — extend, never replace |

---

## Known gaps (honest state)

| Gap | Notes |
|-----|-------|
| Agent execution is serial | 6 agents run serially on sync urllib — §3 known gap |
| Token budget not enforced | Soft 2.2 M / hard 15 M per site-day — not implemented |
| Ramp rate re-rating (§27.5) | Measured ramp rate not instrumented; StatTable shows "not instrumented" |
| Network telemetry on tick | Tick payload does not carry network fields; network tile shows honest empty state |
| State-of-health model | No BESS degradation curve in this version |
