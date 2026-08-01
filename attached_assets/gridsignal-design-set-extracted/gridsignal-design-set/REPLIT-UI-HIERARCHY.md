# GridSignal Console — UI Hierarchy Implementation

**Paste this to Replit. Attach `docs/mockups/` (13 SVGs) alongside it.**

---

## What this changes

The opening screen becomes a **one-line mimic diagram** — the standard SCADA screen type — with a
verdict band above it and a system strip below. It replaces the nine-tile grid built in U2.

**This is a layout change, not a rebuild.** `SubsystemTile`, the nine subsystem configs, all nine
detail modals, the chart primitives and every existing page survive untouched. Only
`ReadinessScreen`'s arrangement changes, and six of its nine tiles become clickable diagram
elements instead of grid cells.

---

## The hierarchy

```
LEVEL 0   Opening screen  ·  gs-01-opening-rest.svg / gs-02-opening-live.svg
          ├─ verdict band      one computed claim + 4 hero figures
          ├─ plant band        one-line mimic, 8 clickable elements
          └─ system strip      3 tiles that are not power assets

LEVEL 1   Detail modals  ·  gs-05 … gs-13
          nine panels, opened from any Level 0 element

LEVEL 1a  Topology explainer  ·  gs-04-topology-explainer.svg
          opened from the "ⓘ How it works" header control. Onboarding, not operations

LEVEL 2   Full pages  ·  existing routes, reached from a modal's "Open full page"
          Overview (run view) · Results · Proposals · Procurement · Network · Thermal · Planner
```

**Level 0 → Level 1 → Level 2.** Each level is one click deeper and answers a narrower question.

---

## Level 0 — three bands

### Band 1 · Verdict (h ≈ 108 px)

One computed claim on the left, four figures on the right.

| State | Claim | Figures |
|---|---|---|
| At rest | **READY** to stage a 24 MW step-load | Dispatchable · Lead time · Bridge · Attention |
| Running | **20 s** to full load — response already staged | Site draw · Predicted peak · Bridge · Reserve |

The claim is the whole differentiator. It is not equipment status — it is *can this plant cope
with what is coming*. Never reword it to status phrasing.

### Band 2 · Plant — the one-line mimic (h ≈ 516 px)

Eight elements, left to right. **Six are clickable** and open their Level 1 modal.

```
[GAS TURBINE]──┐
[SOLAR PV]─────┤
[BATTERY]──────┼──▶[SWITCHGEAR/PMS]──▶[DISTRIBUTION]──▶[PDU/RPP]──▶[COMPUTE RACKS]
[GRID ⌁]───────┘                                                         │
                                                                          ▼
                                                                   [COOLING PLANT]
```

| Element | Clickable | Modal |
|---|---|---|
| Gas turbine | ✓ | `gs-05-generation` |
| Solar PV | ✓ | `gs-07-renewable` |
| Battery (BESS) | ✓ | `gs-06-storage` |
| Grid connection | ✓ | `gs-10-grid` |
| Switchgear / PMS | ✓ | *(no modal yet — route to Overview)* |
| Distribution, PDU | ✗ | passive, no telemetry |
| Compute racks | ✓ | `gs-09-compute` |
| Cooling plant | ✓ | `gs-08-thermal` |

Rules that must survive implementation:

- **Flow-line thickness is proportional to MW.** Idle flows are dashed and grey, never zero-width.
- **Grid is dashed and greyed — "not connected."** Islanded is the design, not a fault. Never red.
- **Each element carries its live value.** Turbine MW, solar MW, battery MW, racks MW, cooling MW,
  all from the tick stream.
- **A `›` chevron marks a clickable element.** Distribution and PDU have none.
- **The lead-time callout on the right** shows 45 s at rest and counts down during a run.

### Band 3 · System strip (h ≈ 108 px)

Three tiles that are **not power assets** and have no place on a one-line:

| Tile | Verdict | Why it is here |
|---|---|---|
| **Forecast quality** | "Uncalibrated site — bands widened 8%" | Tells the operator how much to trust the screen |
| **Network fabric** | "2 switches reporting — one at NTP only" | Corroborates predictions; never drives dispatch |
| **Optimisation agents** | "6 agents analysing — dispatch never waits" | States LP-1 on the landing screen |

**Do not fold these into the plant band to save space.** Forecast quality reading ATTENTION on
first load is deliberate and is the tile an engineer will ask about.

---

## Implementation

### Files

```
frontend/src/opening/                   ← NEW, replaces readiness/ layout
├── OpeningScreen.tsx                     three bands, responsive
├── VerdictBand.tsx                       claim + 4 hero figures
├── PlantDiagram.tsx                      SVG mimic, live-bound
├── PlantNode.tsx                         one clickable element, 8 instances
├── FlowLine.tsx                          proportional-width curve + animation
└── plantLayout.ts                        node positions and flow endpoints

frontend/src/readiness/
├── SubsystemTile.tsx                    ← KEEP, now used only in the system strip
└── subsystems.ts                        ← KEEP, all nine configs unchanged

frontend/src/subsystem/                  ← UNCHANGED, all nine modals
frontend/src/charts/                     ← UNCHANGED, five primitives
```

`ReadinessScreen.tsx` is superseded — keep the file, stop routing to it, and note in a comment
that the tile-grid layout is retained as an alternative. Do not delete it.

### PlantDiagram must be SVG, not divs

Curved proportional-width flow lines and precise node positioning are what SVG is for. Positions
live in `plantLayout.ts` as data so the responsive variants share one source of truth.

### Responsive

| Width | Plant band |
|---|---|
| ≥ 1440 px | Full mimic as drawn |
| 1024–1439 | Same topology, tighter node widths, lead-time callout moves below |
| 768–1023 | Sources stack into a 2 × 2 block; single flow into the chain |
| < 768 px | **Diagram replaced by the nine-tile grid** — a proportional flow diagram is not legible below ~700 px. This is what `ReadinessScreen.tsx` is retained for |

The verdict band and system strip persist at every breakpoint.

---

## Do not touch

These behaviours each cost a defect cycle to find. An agent reorganising a UI will reasonably
rewrite them. It must not.

| File / behaviour | Rule |
|---|---|
| `tickStore.latchedAlert`, `drainFrame`, `acknowledgeAlert` | **Do not modify.** The backend alert fires for one tick — 0.5 s at 10× speed. The latch is why the banner is reachable |
| `bridging_basis` handling | **Do not modify.** Panel and alert must never contradict |
| `sim_time_seconds` as interval-end | **Do not re-derive from `tick_index`** |
| Decimation vs interpolation | **Do not interpolate across dropped ticks** |
| `WebSocketHub._safe_send` | Extend, never replace |
| `src/test/smoke_panels.test.tsx` | **Do not modify or delete any of the 19 tests** |
| `frontend/package.json` `"build"` | Must stay `tsc --noEmit && vite build`. **Do not remove the typecheck** |
| `@types/react` override pinning 18.x | **Do not remove.** pnpm's workspace catalog hoists 19.x and breaks Recharts typing |
| Zustand · React 18 · Vite | No Redux, no Context rewrite, no framework change |

If any of these appears to need changing, **stop and say so** rather than changing it.

---

## Phases

**V-1 · PlantDiagram** — `plantLayout.ts`, `FlowLine`, `PlantNode`, `PlantDiagram`. Static props
first, no data binding. Gate: renders at 1440/1024/768; chevrons on the six clickable nodes only.

**V-2 · OpeningScreen** — `VerdictBand`, three-band composition, system strip reusing
`SubsystemTile`. Route Level 0 here. Gate: all three breakpoints; below 768 px falls back to the
tile grid.

**V-3 · Live binding** — flow widths and node values from `tickStore`. Gate: start `demo-20mw` and
confirm the turbine line thickens as it ramps and the battery line appears when it bridges. A flow
that never changes width is not bound.

**V-4 · Click-through** — each clickable node opens its Level 1 modal; header `ⓘ` opens the
topology explainer. Gate: eight targets, correct modal each, Esc closes, focus returns.

**V-5 · Outstanding items** — the type-to-confirm modal for ladder C/D and reservation
authorization, if not already shipped. Verify against the running build, not the source.

---

## Gate after every phase

```
cd frontend && npm run build && npx vitest run
cd ../gridsignal_sim && PYTHONPATH=. python -m pytest tests/ ../audit_tests/ -q
PYTHONPATH=. python scripts/check_plane_separation.py
PYTHONPATH=. python scripts/load_test.py     # report 1x wall clock AND compute p50, labelled
```

`npm run build` must exit 0 — it runs `tsc --noEmit` first, and `vite build` alone cannot fail on
types. **The vitest count must not fall.** A test that disappears during a UI reorganisation is a
behaviour that stopped being checked.

---

## One instruction that matters more than the rest

**After V-2, load the page in a real browser and describe what you see.** Not "the endpoint returns
200" — what renders. Neither the opening screen nor the tile grid it replaces has ever been seen
outside jsdom, and jsdom has never rendered Recharts correctly. Screenshot it.
