---
name: UI Opening Screen V1–V4
description: One-line SCADA mimic diagram + VerdictBand + SystemStrip + TopologyExplainer; traps and conventions for the opening/ directory.
---

## Rule
`src/opening/OpeningScreen.tsx` is now the Level 0 landing screen. `ReadinessScreen.tsx` is retained as the < 768 px fallback and for smoke tests — do not delete it.

**Why:** The UI-Hierarchy spec replaces the nine-tile grid with a three-band one-line mimic. ReadinessScreen is imported by smoke_readiness.test.tsx directly and is rendered inside OpeningScreen when windowWidth < 768.

## Architecture
- Band 1 (VerdictBand): claim + 4 hero figures + "ⓘ How it works" button.
- Band 2 (PlantDiagram): SVG viewBox 0 0 1200 440, `preserveAspectRatio="xMidYMid meet"`.  
  - Nodes rendered as `<foreignObject>` — same coordinate space as flow lines.
  - Flows rendered as `<path>` with MW-proportional strokeWidth.
  - Lead-time callout as `<foreignObject>` on the far right.
- Band 3 (SystemStrip): three SubsystemTile instances (forecast-quality, network, agents).
- TopologyExplainer: modal for "How it works", Esc closes, focus trapped.

## How to apply
- Node click → `NODE_MODAL_MAP` → `SubsystemModal` (most) or `onNavigate(tabRoute)` (switchgear → overview).
- System strip tiles → `SubsystemModal` via same modal-id.
- VerdictBand "How it works" → `TopologyExplainer`.

## Traps

### TS2352 — TickPayload → Record cast
`(tick as Record<string, unknown>)` fails tsc strict mode.  
Fix: `(tick as unknown as Record<string, unknown>)`.  
Affects any place a TickPayload field is accessed by dynamic string key.

### foreignObject xmlns
React does NOT need `xmlns="http://www.w3.org/1999/xhtml"` on the inner div in modern browsers, but the div needs it to be spec-correct. React typedefs don't include `xmlns` as a div prop → use `// @ts-expect-error` on that div.

### CSS flow animation
`@keyframes flowDash` must be in `index.css` (global scope). The SVG `style={{ animation: 'flowDash ...' }}` on a `<path>` animates `stroke-dashoffset`. The animation only fires when `isActive` (mwValue > 0.01). Idle and grid paths use no animation.

### preserveAspectRatio and foreignObject scaling
foreignObject children scale with the SVG viewport transform. Font sizes specified in px are also scaled. At 768 px container width, the 1200-wide viewBox scales to 0.64×. Source node font-size 9–16 px renders as 6–10 px. Readable but tight — this is the minimum supported width before falling back to ReadinessScreen.

### windowWidth state vs CSS media queries
OpeningScreen uses a `useEffect`+`ResizeObserver`-style `window.addEventListener('resize')` to track width and set the `compact` prop on PlantDiagram and the < 768 fallback. This fires on the client side only — SSR not used here so no hydration mismatch risk.

## Gate results (current)
- `npm run build` (tsc --noEmit && vite build): EXIT 0
- `npx vitest run`: 40/40 (count unchanged — no tests removed)
- `pytest`: 430 passed
- `check_plane_separation.py`: OK
- Load test 1x wall clock: 57.8 s — pre-existing NFR violation (unchanged from prior sessions, zero Python changes)
- Load test compute p50: 920.6 µs (within budget)
