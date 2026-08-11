/**
 * GpuLoadEditor.tsx — Interactive SVG point-graph editor for GPU load profiles.
 *
 * Displays a zero-order-hold step function. Operators can:
 *   • Click empty canvas  → add a new point at (time, load %)
 *   • Click a point       → select it (highlighted)
 *   • Drag a point        → adjust time (X) and load % (Y)
 *   • Delete / Backspace  → remove the selected point
 *
 * Profile convention: same zero-order-hold as irradiance_steps.
 * Each point [time_s, fraction] means the fraction applies from time_s onward.
 * The first point's fraction applies from t=0 even if time_s > 0.
 */

import { CSSProperties, useCallback, useRef, useState } from 'react'

// ── SVG coordinate constants ───────────────────────────────────────────────────
const VW = 520        // viewBox width
const VH = 160        // viewBox height
const PAD_L = 38      // left padding  (Y-axis labels)
const PAD_R = 8       // right padding
const PAD_T = 10      // top padding
const PAD_B = 26      // bottom padding (X-axis labels)
const CW = VW - PAD_L - PAD_R   // chart pixel width
const CH = VH - PAD_T - PAD_B   // chart pixel height

const PT_R   = 5      // normal point radius
const PT_R_S = 7      // selected point radius
const HIT_R  = 12     // hit-test radius for click-to-select

// ── Coordinate helpers ─────────────────────────────────────────────────────────

function toSvgX(t: number, dur: number): number {
  return PAD_L + (t / dur) * CW
}

function toSvgY(f: number): number {
  return PAD_T + (1 - f) * CH
}

function fromSvgX(x: number, dur: number): number {
  return Math.max(0, Math.min(dur, ((x - PAD_L) / CW) * dur))
}

function fromSvgY(y: number): number {
  return Math.max(0, Math.min(1, 1 - (y - PAD_T) / CH))
}

// ── Step-function path builder ─────────────────────────────────────────────────

function buildLinePath(pts: [number, number][], dur: number): string {
  if (pts.length === 0) {
    // Empty profile = 100 % flat
    const y = toSvgY(1)
    return `M ${toSvgX(0, dur)} ${y} H ${toSvgX(dur, dur)}`
  }
  // Start at t=0 with the first point's fraction (zero-order-hold applies from t=0)
  const parts: string[] = [`M ${toSvgX(0, dur)} ${toSvgY(pts[0][1])}`]
  for (let i = 0; i < pts.length; i++) {
    const nextT = i < pts.length - 1 ? pts[i + 1][0] : dur
    parts.push(`H ${toSvgX(nextT, dur)}`)   // horizontal to next time
    if (i < pts.length - 1) {
      parts.push(`V ${toSvgY(pts[i + 1][1])}`)   // vertical step to next value
    }
  }
  parts.push(`H ${toSvgX(dur, dur)}`)       // horizontal to end
  return parts.join(' ')
}

function buildAreaPath(pts: [number, number][], dur: number): string {
  const line = buildLinePath(pts, dur)
  return `${line} V ${toSvgY(0)} H ${toSvgX(0, dur)} Z`
}

// ── Time label helper ──────────────────────────────────────────────────────────

function fmtTime(s: number): string {
  if (s >= 3600) return `${(s / 3600).toFixed(1)}h`
  if (s >= 60)   return `${Math.floor(s / 60)}m`
  return `${Math.round(s)}s`
}

// ── Props ──────────────────────────────────────────────────────────────────────

interface GpuLoadEditorProps {
  /** Points sorted ascending by time. Each entry: [time_s, fraction 0-1]. */
  points: [number, number][]
  /** Scenario duration in seconds — sets the X axis. */
  durationSeconds: number
  /** Called with a new sorted points array whenever points change. */
  onChange: (pts: [number, number][]) => void
  style?: CSSProperties
}

// ── Main component ─────────────────────────────────────────────────────────────

export function GpuLoadEditor({ points, durationSeconds, onChange, style }: GpuLoadEditorProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [selected, setSelected]   = useState<number | null>(null)
  const [hovering, setHovering]   = useState<number | null>(null)
  const [dragIdx,  setDragIdx]    = useState<number | null>(null)

  // Sorted guarantee — always render sorted so the path is valid
  const sorted: [number, number][] = [...points].sort((a, b) => a[0] - b[0])

  // ── SVG coord from screen pointer event ──────────────────────────────────────
  const svgCoord = useCallback((e: React.PointerEvent): { x: number; y: number } => {
    const svg = svgRef.current
    if (!svg) return { x: 0, y: 0 }
    const rect = svg.getBoundingClientRect()
    return {
      x: ((e.clientX - rect.left) / rect.width)  * VW,
      y: ((e.clientY - rect.top)  / rect.height) * VH,
    }
  }, [])

  // ── Find closest point within hit radius ─────────────────────────────────────
  const hitTest = useCallback((svgX: number, svgY: number): number | null => {
    let closest: number | null = null
    let minDist = HIT_R
    sorted.forEach(([t, f], i) => {
      const dx = svgX - toSvgX(t, durationSeconds)
      const dy = svgY - toSvgY(f)
      const d  = Math.hypot(dx, dy)
      if (d < minDist) { minDist = d; closest = i }
    })
    return closest
  }, [sorted, durationSeconds])

  // ── Pointer handlers ─────────────────────────────────────────────────────────

  function onSvgDown(e: React.PointerEvent<SVGSVGElement>) {
    const { x, y } = svgCoord(e)

    // Ignore clicks outside chart area
    if (x < PAD_L - 4 || x > VW - PAD_R + 4) return
    if (y < PAD_T - 4 || y > VH - PAD_B + 4) return

    const hit = hitTest(x, y)
    if (hit !== null) {
      // Click on existing point → select and prepare drag
      setSelected(hit)
      setDragIdx(hit)
      e.currentTarget.setPointerCapture(e.pointerId)
      return
    }

    // Click on empty space → add new point
    const t = Math.round(fromSvgX(x, durationSeconds))
    const f = parseFloat(fromSvgY(y).toFixed(2))
    const next: [number, number][] = ([...sorted, [t, f] as [number, number]]).sort((a, b) => a[0] - b[0])
    onChange(next)
    const newIdx = next.findIndex(p => p[0] === t && p[1] === f)
    setSelected(newIdx >= 0 ? newIdx : null)
    setDragIdx(null)
  }

  function onSvgMove(e: React.PointerEvent<SVGSVGElement>) {
    if (dragIdx === null) return
    const { x, y } = svgCoord(e)
    const t = Math.round(fromSvgX(x, durationSeconds))
    const f = parseFloat(fromSvgY(y).toFixed(2))
    const next: [number, number][] = sorted.map((p, i) => (i === dragIdx ? [t, f] : p) as [number, number])
    const resorted = [...next].sort((a, b) => a[0] - b[0])
    // Track the new position of the dragged point
    const newIdx = resorted.findIndex(p => p[0] === t && p[1] === f)
    onChange(resorted)
    if (newIdx >= 0) {
      setDragIdx(newIdx)
      setSelected(newIdx)
    }
  }

  function onSvgUp() {
    setDragIdx(null)
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if ((e.key === 'Delete' || e.key === 'Backspace') && selected !== null) {
      e.preventDefault()
      const next = sorted.filter((_, i) => i !== selected)
      onChange(next)
      setSelected(null)
    }
    if (e.key === 'Escape') setSelected(null)
  }

  // ── Axis labels ───────────────────────────────────────────────────────────────
  const xTicks = 5
  const yLabels: number[] = [0, 0.25, 0.5, 0.75, 1.0]

  // ── Active fraction label ─────────────────────────────────────────────────────
  const activeIdx = hovering ?? selected
  const activePoint = activeIdx !== null ? sorted[activeIdx] : null

  // ── Render ────────────────────────────────────────────────────────────────────
  return (
    <div style={style} className="space-y-1">
      {/* Active point readout */}
      <div className="flex items-center justify-between min-h-[16px]">
        {activePoint ? (
          <span className="font-mono text-[10px] text-accent tabular-nums">
            t = {fmtTime(activePoint[0])} · {(activePoint[1] * 100).toFixed(0)}%
            {activeIdx === selected && sorted.length > 0 && (
              <span className="text-muted ml-2">[Delete to remove]</span>
            )}
          </span>
        ) : (
          <span className="font-mono text-[10px] text-muted">
            {sorted.length === 0
              ? 'click canvas to add a point'
              : `${sorted.length} point${sorted.length === 1 ? '' : 's'} · click to select, drag to move`}
          </span>
        )}
        {selected !== null && (
          <button
            className="text-[9px] text-danger hover:underline"
            onClick={() => {
              const next = sorted.filter((_, i) => i !== selected)
              onChange(next)
              setSelected(null)
            }}
          >
            remove
          </button>
        )}
      </div>

      {/* SVG canvas */}
      <svg
        ref={svgRef}
        viewBox={`0 0 ${VW} ${VH}`}
        width="100%"
        style={{
          cursor: dragIdx !== null ? 'grabbing' : 'crosshair',
          display: 'block',
          outline: 'none',
          userSelect: 'none',
        }}
        tabIndex={0}
        onPointerDown={onSvgDown}
        onPointerMove={onSvgMove}
        onPointerUp={onSvgUp}
        onPointerCancel={onSvgUp}
        onKeyDown={onKeyDown}
        onMouseLeave={() => setHovering(null)}
      >
        {/* Background */}
        <rect
          x={PAD_L} y={PAD_T}
          width={CW} height={CH}
          fill="#0a0e13"
          stroke="#1e2a36"
          strokeWidth={1}
          rx={3}
        />

        {/* Y grid lines + labels */}
        {yLabels.map(f => {
          const svgY = toSvgY(f)
          return (
            <g key={f}>
              <line
                x1={PAD_L} y1={svgY} x2={PAD_L + CW} y2={svgY}
                stroke="#1e2a36" strokeWidth={1}
                strokeDasharray={f === 0 || f === 1 ? '0' : '3 3'}
              />
              <text
                x={PAD_L - 4} y={svgY + 3.5}
                textAnchor="end"
                fontSize={9}
                fontFamily="'SF Mono','Roboto Mono',monospace"
                fill="#4b5764"
              >
                {(f * 100).toFixed(0)}%
              </text>
            </g>
          )
        })}

        {/* X axis tick labels */}
        {Array.from({ length: xTicks + 1 }, (_, i) => {
          const t = (i / xTicks) * durationSeconds
          const svgX = toSvgX(t, durationSeconds)
          return (
            <text
              key={i}
              x={svgX} y={VH - PAD_B + 14}
              textAnchor={i === 0 ? 'start' : i === xTicks ? 'end' : 'middle'}
              fontSize={9}
              fontFamily="'SF Mono','Roboto Mono',monospace"
              fill="#4b5764"
            >
              {fmtTime(t)}
            </text>
          )
        })}

        {/* Area fill */}
        <path
          d={buildAreaPath(sorted, durationSeconds)}
          fill="#4a9fe020"
          clipPath={`url(#chart-clip)`}
        />

        {/* Clip path */}
        <defs>
          <clipPath id="chart-clip">
            <rect x={PAD_L} y={PAD_T} width={CW} height={CH} />
          </clipPath>
        </defs>

        {/* Step line */}
        <path
          d={buildLinePath(sorted, durationSeconds)}
          fill="none"
          stroke="#4a9fe0"
          strokeWidth={1.5}
          clipPath="url(#chart-clip)"
        />

        {/* Empty-profile hint line */}
        {sorted.length === 0 && (
          <path
            d={buildLinePath([], durationSeconds)}
            fill="none"
            stroke="#1e2a36"
            strokeWidth={1}
            strokeDasharray="4 4"
            clipPath="url(#chart-clip)"
          />
        )}

        {/* Points */}
        {sorted.map(([t, f], i) => {
          const cx = toSvgX(t, durationSeconds)
          const cy = toSvgY(f)
          const isSel  = i === selected
          const isHov  = i === hovering
          const r = isSel || isHov ? PT_R_S : PT_R
          return (
            <g
              key={i}
              style={{ cursor: dragIdx !== null && dragIdx === i ? 'grabbing' : 'grab' }}
              onMouseEnter={() => setHovering(i)}
              onMouseLeave={() => setHovering(null)}
            >
              {/* Hit area */}
              <circle cx={cx} cy={cy} r={HIT_R} fill="transparent" />
              {/* Visual circle */}
              <circle
                cx={cx} cy={cy} r={r}
                fill={isSel ? '#3fb6a8' : isHov ? '#6ab8e8' : '#4a9fe0'}
                stroke={isSel ? '#3fb6a8' : '#4a9fe0'}
                strokeWidth={isSel ? 2 : 1}
                style={{ transition: dragIdx !== null ? 'none' : 'r 0.1s, fill 0.1s' }}
              />
              {/* Crosshair verticals for selected */}
              {isSel && (
                <>
                  <line
                    x1={cx} y1={PAD_T} x2={cx} y2={cy - r - 1}
                    stroke="#3fb6a840" strokeWidth={1} strokeDasharray="2 2"
                  />
                  <line
                    x1={cx} y1={cy + r + 1} x2={cx} y2={PAD_T + CH}
                    stroke="#3fb6a840" strokeWidth={1} strokeDasharray="2 2"
                  />
                  <line
                    x1={PAD_L} y1={cy} x2={cx - r - 1} y2={cy}
                    stroke="#3fb6a840" strokeWidth={1} strokeDasharray="2 2"
                  />
                </>
              )}
            </g>
          )
        })}
      </svg>
    </div>
  )
}
