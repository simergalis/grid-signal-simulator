/**
 * GaugeArc.tsx — radial arc gauge, primarily for BESS state of charge.
 *
 * Plain SVG — Recharts adds no value for a single arc.
 * 180° arc, fraction fills from left to right.
 * bigLabel is the primary value; smallLabel is the unit or sub-label.
 *
 * dense=true shrinks the arc for tile embedding.
 */

export interface GaugeArcProps {
  fraction: number    // [0, 1]
  colour: string      // fill colour
  bigLabel: string    // e.g. "95%"
  smallLabel: string  // e.g. "state of charge"
  dense?: boolean
}

function describeArc(cx: number, cy: number, r: number, startAngle: number, endAngle: number): string {
  const toRad = (deg: number) => (deg * Math.PI) / 180
  const x1 = cx + r * Math.cos(toRad(startAngle))
  const y1 = cy + r * Math.sin(toRad(startAngle))
  const x2 = cx + r * Math.cos(toRad(endAngle))
  const y2 = cy + r * Math.sin(toRad(endAngle))
  const largeArc = endAngle - startAngle > 180 ? 1 : 0
  return `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`
}

export function GaugeArc({
  fraction,
  colour,
  bigLabel,
  smallLabel,
  dense = false,
}: GaugeArcProps) {
  const SIZE = dense ? 80 : 120
  const CX   = SIZE / 2
  const CY   = SIZE / 2 + (dense ? 8 : 12)
  const R    = dense ? 28 : 44
  const SW   = dense ? 6  : 8    // stroke-width

  // Arc spans 200° (from 190° to 350°, i.e., 190° → 190°+200°=390°=30°)
  const START = 190
  const END   = 350
  const SPAN  = END - START

  const clamped = Math.min(1, Math.max(0, fraction))
  const fillEnd = START + SPAN * clamped

  const trackPath = describeArc(CX, CY, R, START, END)
  const fillPath  = clamped > 0 ? describeArc(CX, CY, R, START, fillEnd) : ''

  return (
    <div className="flex flex-col items-center">
      <svg width={SIZE} height={SIZE * 0.65} viewBox={`0 0 ${SIZE} ${SIZE}`}>
        {/* Track */}
        <path
          d={trackPath}
          fill="none"
          stroke="#1a232d"
          strokeWidth={SW}
          strokeLinecap="round"
        />
        {/* Fill */}
        {fillPath && (
          <path
            d={fillPath}
            fill="none"
            stroke={colour}
            strokeWidth={SW}
            strokeLinecap="round"
          />
        )}
        {/* Big label */}
        <text
          x={CX}
          y={CY + 4}
          textAnchor="middle"
          fill="#e6edf3"
          fontSize={dense ? 16 : 22}
          fontFamily="JetBrains Mono, monospace"
          fontWeight="600"
        >
          {bigLabel}
        </text>
        {/* Small label */}
        <text
          x={CX}
          y={CY + (dense ? 16 : 22)}
          textAnchor="middle"
          fill="#8b949e"
          fontSize={dense ? 7 : 8}
          fontFamily="JetBrains Mono, monospace"
        >
          {smallLabel}
        </text>
      </svg>
    </div>
  )
}
