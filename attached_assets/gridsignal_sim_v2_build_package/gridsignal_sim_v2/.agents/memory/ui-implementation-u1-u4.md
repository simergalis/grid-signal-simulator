---
name: UI Implementation U1–U4 completion
description: Chart primitives, Readiness screen, 9 subsystem modals, tick wiring — what was built, where, and key lessons.
---

## What was built (U1–U4)

### U1 — Chart primitives (`frontend/src/charts/`)
5 components: TimeSeries (Recharts ComposedChart), BulletBar (plain SVG), StatTable (2-col table), StackBar (proportional), GaugeArc (SVG 200° arc). All exported from `charts/index.ts`. 11 new vitest tests in `smoke_charts.test.tsx`.

### U2 — Readiness screen (`frontend/src/readiness/`)
- `subsystems.ts` — 9 static configs (id, name, group, accentColor, identityLine, tabId)
- `SubsystemTile.tsx` — tile with accent top-bar, state dot, verdict, 3 metrics
- `ReadinessBanner.tsx` — overall verdict + 4 hero figures (4-across ≥768, 2×2 below)
- `ReadinessScreen.tsx` — CSS Grid 3-col/2-col/1-col + group headers
14 new tests in `smoke_readiness.test.tsx`.

### U3 — Subsystem modals (`frontend/src/subsystem/`)
- `SubsystemModal.tsx` — modal shell: Esc close, Tab focus trap, focus restore on unmount, role=dialog aria-modal
- `panels/index.ts` — PANEL_CONFIGS registry, PanelConfig interface with `deriveData(tick, alert, history)`
- 9 panel configs: generation, storage, renewable, thermal, compute, grid, forecastQuality, network, agents

### U4 — Live data wiring
- `useSubsystemData.ts` — selectors from tickStore → tile props for all 9 subsystems
- Tiles read tick stream only (no per-tile polling per plan §6)
- Thermal fields (rated_cooling_mw, absorbable_mw, time_to_limit_s, approach_rate_mw_s) already on TickPayload from previous session

## App.tsx changes
- `PageView` type: added `'readiness'`
- Default `currentPage`: `'readiness'` (was `'overview'`)
- `handleRunStarted`: calls `setCurrentPage('overview')` — readiness hands off on run start
- Tab bar: Readiness tab added as first tab

## Tailwind additions (tailwind.config.ts)
Added: `teal`, `gold`, `solar`, `battery`, `violet`, `islanded` colour tokens.

## Test counts
- Original: 19 (`smoke_panels.test.tsx`)
- Added: 11 (`smoke_charts.test.tsx`) + 14 (`smoke_readiness.test.tsx`)
- Total: **40** — must not fall below 19

## Key lessons
**Why:** `getByText` throws "multiple elements found" when a string appears in both a group header and a tile name (e.g. "Energy Storage" appears in both). Use `getAllByText(...).length > 0` for any name shared between group headers and tiles.

**Why:** TimeSeries uses `ComposedChart` (not `LineChart` or `AreaChart`) to support mixed `Line` + `Area` series in one chart. In JSDOM Recharts logs a 0×0 size warning — harmless, tests pass.
