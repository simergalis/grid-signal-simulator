/**
 * FlowLine.tsx — one proportional-width flow line in the one-line mimic.
 *
 * Rules (from REPLIT-UI-HIERARCHY.md):
 *   · Stroke width is proportional to MW — thicker = more power.
 *   · Idle flows (mwValue ≈ 0) are dashed and grey; never zero-width.
 *   · Grid connection is always dashed + grey (islanded by design).
 *   · Live flows use a subtle dash-offset animation ("water flowing").
 */

interface FlowLineProps {
  d: string
  mwValue: number   // live MW (0 when idle)
  maxMW: number     // reference maximum for width scaling
  color: string     // active stroke colour
  isGrid?: boolean  // grid connection — always dashed, always grey
  marker?: string   // SVG marker-end id
}

/** Map an MW value to a stroke width in SVG coordinate space. */
function mwToStroke(mwValue: number, maxMW: number): number {
  const fraction = Math.max(0, Math.min(1, Math.abs(mwValue) / maxMW))
  return 1.5 + fraction * 7.5
}

export function FlowLine({ d, mwValue, maxMW, color, isGrid, marker }: FlowLineProps) {
  const isIdle   = Math.abs(mwValue) < 0.01
  const isActive = !isIdle && !isGrid

  const strokeColor = (isGrid || isIdle) ? '#3a4a58' : color
  const strokeWidth = mwToStroke(mwValue, maxMW)
  const dashArray   = (isGrid || isIdle) ? '5 7' : undefined
  const opacity     = isIdle ? 0.45 : 1.0

  return (
    <path
      d={d}
      fill="none"
      stroke={strokeColor}
      strokeWidth={strokeWidth}
      strokeDasharray={dashArray}
      strokeLinecap="round"
      strokeLinejoin="round"
      opacity={opacity}
      markerEnd={marker ? `url(#${marker})` : undefined}
      style={isActive ? {
        animation: 'flowDash 1.2s linear infinite',
      } : undefined}
    />
  )
}

/**
 * ArrowMarker — SVG <marker> defs for flow arrowheads.
 * Render once inside <defs> in the parent SVG.
 */
export function FlowMarkers() {
  return (
    <defs>
      <marker
        id="arrow-teal"
        markerWidth="8"
        markerHeight="8"
        refX="4"
        refY="4"
        orient="auto"
      >
        <path d="M0,1 L7,4 L0,7 Z" fill="#3fb6a8" />
      </marker>
      <marker
        id="arrow-grey"
        markerWidth="8"
        markerHeight="8"
        refX="4"
        refY="4"
        orient="auto"
      >
        <path d="M0,1 L7,4 L0,7 Z" fill="#3a4a58" />
      </marker>
    </defs>
  )
}
