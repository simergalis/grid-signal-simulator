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
  onClick?: () => void  // if set, the row renders as a clickable link (cursor-pointer)
  /**
   * featured=true renders the row as an amber call-to-action card:
   * amber border + tinted background, pulsing amber dot, and a "click →" hint.
   * Intended for the "Requeued (cap hold)" row in the Compute tile.
   * Only meaningful when onClick is also set.
   */
  featured?: boolean
}

export interface StatTableProps {
  rows: StatRow[]
  dense?: boolean
}

export function StatTable({ rows, dense = false }: StatTableProps) {
  const rowPad  = dense ? 'py-1' : 'py-1.5'
  const fontSize = dense ? 'text-[20px]' : 'text-[24px]'
  const subSize  = dense ? 'text-[18px]' : 'text-[20px]'

  return (
    <div className="divide-y divide-border">
      {rows.map((row, i) => {
        if (row.featured && row.onClick) {
          // Amber call-to-action card — matches the mockup's .requeue-row style
          return (
            <div
              key={i}
              className="flex items-center justify-between gap-3 mx-[-6px] my-1.5 px-2.5 py-2.5 rounded-lg cursor-pointer transition-colors"
              style={{
                border: '1px solid rgba(240,136,62,0.35)',
                background: 'rgba(240,136,62,0.07)',
              }}
              onClick={row.onClick}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') row.onClick!() }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(240,136,62,0.13)' }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(240,136,62,0.07)' }}
            >
              {/* Label with pulsing dot */}
              <div className="flex items-center gap-2">
                {/* Ping animation: outer ring fades out, inner dot stays solid */}
                <span className="relative flex h-[7px] w-[7px] flex-shrink-0">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-60"
                    style={{ background: '#f0883e' }} />
                  <span className="relative inline-flex h-[7px] w-[7px] rounded-full"
                    style={{ background: '#f0883e' }} />
                </span>
                <span className={`font-mono ${fontSize}`} style={{ color: '#e8ecef' }}>
                  {row.label}
                </span>
              </div>
              {/* Value + click hint */}
              <div className="flex items-center gap-2.5">
                <span className={`font-mono tabular-nums ${fontSize} font-semibold`}
                  style={{ color: '#f0883e' }}>
                  {row.value}
                </span>
                <span className="font-mono text-[9px] uppercase tracking-[0.06em]"
                  style={{ color: '#586170' }}>
                  click →
                </span>
              </div>
            </div>
          )
        }

        return (
          <div
            key={i}
            className={`flex items-start justify-between gap-4 ${rowPad}${row.onClick ? ' cursor-pointer hover:bg-white/[0.05] active:bg-white/[0.08] rounded transition-colors' : ''}`}
            onClick={row.onClick}
            role={row.onClick ? 'button' : undefined}
            tabIndex={row.onClick ? 0 : undefined}
            onKeyDown={row.onClick ? (e) => { if (e.key === 'Enter' || e.key === ' ') row.onClick!() } : undefined}
          >
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
        )
      })}
    </div>
  )
}
