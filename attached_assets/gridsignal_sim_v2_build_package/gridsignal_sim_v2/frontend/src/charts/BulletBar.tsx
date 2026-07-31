/**
 * BulletBar.tsx — horizontal bullet bar: actual vs max with optional target marker.
 *
 * Plain SVG — Recharts adds no value for a single bar and costs layout control.
 * Used in subsystem modals to show ramp capability vs predicted shortfall, SOC vs
 * rated, etc.
 *
 * Props in, SVG out. No data fetching.
 * dense=true shrinks padding for tile embedding.
 */

export interface BulletBarProps {
  label: string
  value: number
  max: number
  target?: number   // red marker; value exceeds target = good
  colour: string    // fill colour for the actual bar
  unit?: string
  note?: string     // caption below the bar
  dense?: boolean
}

export function BulletBar({
  label,
  value,
  max,
  target,
  colour,
  unit = '',
  note,
  dense = false,
}: BulletBarProps) {
  const BAR_H = dense ? 8 : 9
  const TRACK_H = dense ? 8 : 9
  const LABEL_MB = dense ? 4 : 6
  const FONT = dense ? 9 : 10
  const NOTE_FONT = dense ? 8 : 9

  // Clamp fractions to [0, 1]
  const valueFrac  = max > 0 ? Math.min(1, Math.max(0, value / max))  : 0
  const targetFrac = max > 0 && target !== undefined
    ? Math.min(1, Math.max(0, target / max)) : null

  return (
    <div className={dense ? 'space-y-0.5' : 'space-y-1'}>
      {/* Label row */}
      <div className="flex items-baseline justify-between" style={{ marginBottom: LABEL_MB }}>
        <span
          className="font-mono text-muted uppercase tracking-wider"
          style={{ fontSize: FONT }}
        >
          {label}
        </span>
        <span
          className="font-mono tabular-nums"
          style={{ fontSize: FONT + 1, color: colour }}
        >
          {value.toFixed(2)}{unit}
        </span>
      </div>

      {/* Track + bar */}
      <div
        className="relative w-full rounded-full overflow-hidden"
        style={{ height: TRACK_H, background: '#1a232d' }}
      >
        <div
          className="absolute inset-y-0 left-0 rounded-full"
          style={{ width: `${valueFrac * 100}%`, background: colour }}
        />
        {/* Target marker */}
        {targetFrac !== null && (
          <div
            className="absolute inset-y-0 w-0.5"
            style={{ left: `${targetFrac * 100}%`, background: '#d9534f' }}
          />
        )}
      </div>

      {/* Note caption */}
      {note && (
        <div className="font-mono text-muted" style={{ fontSize: NOTE_FONT }}>
          {note}
        </div>
      )}
    </div>
  )
}
