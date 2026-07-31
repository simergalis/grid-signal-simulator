/**
 * StackBar.tsx — proportional composition bar (horizontal stacked).
 *
 * Segments are rendered in order, left to right, proportional to value.
 * A legend row below shows label + value for each segment.
 *
 * dense=true shrinks the bar height and legend font for tile use.
 */

export interface StackSegment {
  label: string
  value: number
  colour: string
}

export interface StackBarProps {
  segments: StackSegment[]
  total?: number    // explicit total; defaults to sum of segment values
  unit?: string
  dense?: boolean
}

export function StackBar({
  segments,
  total,
  unit = '',
  dense = false,
}: StackBarProps) {
  const sum = total ?? segments.reduce((s, seg) => s + seg.value, 0)
  const BAR_H = dense ? 8 : 12
  const FONT  = dense ? 9 : 10

  return (
    <div className="space-y-1.5">
      {/* Track */}
      <div
        className="flex w-full overflow-hidden rounded"
        style={{ height: BAR_H, background: '#1a232d' }}
      >
        {segments.map((seg, i) => {
          const frac = sum > 0 ? seg.value / sum : 0
          return (
            <div
              key={i}
              style={{
                width: `${frac * 100}%`,
                background: seg.colour,
                minWidth: frac > 0 ? 2 : 0,
              }}
            />
          )
        })}
      </div>

      {/* Legend */}
      <div className="flex flex-col gap-0.5">
        {segments.map((seg, i) => (
          <div key={i} className="flex items-center gap-2">
            <div
              className="shrink-0 rounded-sm"
              style={{ width: 9, height: 9, background: seg.colour }}
            />
            <span className="font-mono text-muted flex-1" style={{ fontSize: FONT }}>
              {seg.label}
            </span>
            <span
              className="font-mono tabular-nums"
              style={{ fontSize: FONT, color: seg.colour }}
            >
              {seg.value.toFixed(2)}{unit}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
