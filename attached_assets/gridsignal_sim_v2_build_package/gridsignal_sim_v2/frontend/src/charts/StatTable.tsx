/**
 * StatTable.tsx — entity list with per-cell colour override.
 *
 * Two-column: label (muted) on the left, value on the right.
 * An optional sub-label sits below the value in dim text.
 * colour overrides the value text colour (use for TEAL/WARN/DANGER state signals).
 *
 * dense=true tightens row spacing for tile embedding.
 */

export interface StatRow {
  label: string
  value: string
  sub?: string
  colour?: string  // CSS hex or Tailwind class-safe value; defaults to text colour
}

export interface StatTableProps {
  rows: StatRow[]
  dense?: boolean
}

export function StatTable({ rows, dense = false }: StatTableProps) {
  const rowPad = dense ? 'py-1' : 'py-1.5'
  const fontSize = dense ? 'text-[10px]' : 'text-xs'
  const subSize  = dense ? 'text-[9px]' : 'text-[10px]'

  return (
    <div className="divide-y divide-border">
      {rows.map((row, i) => (
        <div key={i} className={`flex items-start justify-between gap-4 ${rowPad}`}>
          <span className={`font-mono text-muted ${fontSize} shrink-0`}>
            {row.label}
          </span>
          <div className="text-right">
            <span
              className={`font-mono tabular-nums ${fontSize} font-medium`}
              style={row.colour ? { color: row.colour } : undefined}
            >
              {row.value}
            </span>
            {row.sub && (
              <div className={`font-mono ${subSize} text-muted`} style={{ color: '#4b5764' }}>
                {row.sub}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
