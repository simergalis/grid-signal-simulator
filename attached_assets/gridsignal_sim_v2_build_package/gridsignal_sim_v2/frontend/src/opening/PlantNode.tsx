/**
 * PlantNode.tsx — one node in the one-line plant mimic diagram.
 *
 * Rendered as an SVG <foreignObject> so it lives in the same coordinate
 * space as the flow lines.  Tailwind classes work normally inside.
 *
 * Rules:
 *   · Clickable nodes show a › chevron (top-right).
 *   · Passive nodes (Distribution, PDU) have no chevron and no pointer cursor.
 *   · Grid connection is dashed + grey: islanded by design, never red.
 *   · A coloured state dot appears next to the MW value when active.
 */

import type { NodeDef } from './plantLayout'
import type { TickPayload } from '../types'

interface PlantNodeProps {
  def: NodeDef
  tick: TickPayload | null
  onClick?: (nodeId: string) => void
}

function getMwValue(def: NodeDef, tick: TickPayload | null): number | null {
  if (!def.mwField) return null
  // No tick: use staticMW if defined so nodes show configured capacity at rest.
  // Keep "—" only for nodes that have no meaningful pre-run value (no staticMW).
  if (!tick) return def.staticMW ?? null
  return (tick as unknown as Record<string, unknown>)[def.mwField] as number
}

/** Subtle detail lines shown inside each node. */
function nodeDetail(def: NodeDef, tick: TickPayload | null): string {
  switch (def.id) {
    case 'gas-turbine': {
      const mw = tick?.turbine_output_mw ?? 0
      const online = mw > 0.1 ? 1 : 0
      return online > 0
        ? `${online} unit online · N−1 firm 30.0 MW`
        : `3 units · 0 online · N−1 firm 30.0 MW`
    }
    case 'solar-pv': {
      const mw = tick?.p_renewable_mw ?? 0
      return mw > 0.1 ? `non-dispatchable · 4.99 MW rated` : `non-dispatchable · 4.99 MW rated`
    }
    case 'battery-bess': {
      const soc = tick?.bess_soc_fraction ?? 0.95
      return `armed · ${(soc * 100).toFixed(0)}% · anchor 1.0 MW`
    }
    case 'grid-connection':
      return 'islanded — no utility feed'
    case 'switchgear-pms':
      return 'GridSignal advises —\nnever commands protection'
    case 'distribution':
      return '480 V'
    case 'pdu-rpp':
      return 'rack feeds'
    case 'compute-racks': {
      const jobs = tick ? Object.keys(tick.checkpoint_states).length : 0
      // Node count is 1,900 — from api/routes/scenarios.py line 210:
      // "# 1900-node peak compute (enterprise_8gpu_air, PUE 1.03) → 19.9614 MW."
      return jobs > 0 ? `${jobs} job${jobs > 1 ? 's' : ''} · 19.96 MW at full draw` : `1,900 nodes · 19.96 MW at full draw`
    }
    case 'cooling-plant': {
      // AA1: bind "rated" to rated_cooling_mw, not absorbable_mw.
      // absorbable_mw is headroom (rated − current draw) — very different numbers.
      const rated = tick?.rated_cooling_mw ?? 4.59
      if (tick) {
        const headroom = tick.absorbable_mw
        return `lags compute by 90 s · ${rated.toFixed(2)} MW rated · ${headroom.toFixed(2)} MW headroom`
      }
      return `lags compute by 90 s · ${rated.toFixed(2)} MW rated`
    }
    default:
      return ''
  }
}

export function PlantNode({ def, tick, onClick }: PlantNodeProps) {
  const mwValue = getMwValue(def, tick)
  const isIdle  = mwValue === null || Math.abs(mwValue) < 0.01
  const detail  = nodeDetail(def, tick)
  const isGrid  = !!def.gridStyle
  const canClick = def.clickable && !def.passive

  // Border colour: teal when active, dim when idle, grey when grid/passive
  const borderColor = isGrid
    ? '#2a3540'
    : def.passive
    ? '#1e2a36'
    : isIdle
    ? '#1e2a36'
    : def.accentColor

  const bgColor = isGrid ? 'transparent' : '#111821'

  const handleClick = () => {
    if (canClick) onClick?.(def.id)
  }

  return (
    <foreignObject
      x={def.x}
      y={def.y}
      width={def.w}
      height={def.h}
    >
      {/* xmlns required for SVG foreignObject HTML content */}
      <div
        // @ts-expect-error — xmlns is required for SVG foreignObject HTML but not in React typedefs
        xmlns="http://www.w3.org/1999/xhtml"
        onClick={canClick ? handleClick : undefined}
        style={{
          width: '100%',
          height: '100%',
          boxSizing: 'border-box',
          borderRadius: 6,
          border: `1.5px ${isGrid ? 'dashed' : 'solid'} ${borderColor}`,
          background: bgColor,
          padding: '6px 8px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          cursor: canClick ? 'pointer' : 'default',
          position: 'relative',
          overflow: 'hidden',
          transition: 'border-color 0.2s',
        }}
      >
        {/* Accent top bar (active only) */}
        {!isIdle && !isGrid && !def.passive && (
          <div style={{
            position: 'absolute', top: 0, left: 0, right: 0, height: 2,
            background: def.accentColor, borderRadius: '6px 6px 0 0',
          }} />
        )}

        {/* Header row: label + state dot + chevron */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 4 }}>
          <div>
            <div style={{
              fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace",
              fontSize: 9,
              fontWeight: 700,
              letterSpacing: '0.08em',
              color: isGrid ? '#3a4a58' : def.passive ? '#3a4a58' : '#8b949e',
              lineHeight: 1.2,
            }}>
              {def.label}
            </div>
            {def.label2 && (
              <div style={{
                fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace",
                fontSize: 9,
                fontWeight: 700,
                letterSpacing: '0.08em',
                color: isGrid ? '#3a4a58' : def.passive ? '#3a4a58' : '#8b949e',
                lineHeight: 1.1,
              }}>
                {def.label2}
              </div>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 3, flexShrink: 0 }}>
            {!isIdle && !isGrid && !def.passive && (
              <div style={{
                width: 5, height: 5, borderRadius: '50%',
                background: def.accentColor, flexShrink: 0,
              }} />
            )}
            {isGrid && (
              <div style={{
                width: 5, height: 5, borderRadius: '50%',
                background: '#3a4a58', flexShrink: 0,
              }} />
            )}
            {canClick && (
              <div style={{
                fontFamily: 'Inter,sans-serif',
                fontSize: 10,
                color: '#4b5764',
                lineHeight: 1,
              }}>›</div>
            )}
          </div>
        </div>

        {/* MW value (middle) */}
        {def.mwField !== undefined && (
          <div style={{
            fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace",
            fontSize: mwValue !== null && mwValue >= 10 ? 16 : 18,
            fontWeight: 500,
            color: isGrid ? '#3a4a58' : isIdle ? '#4b5764' : def.accentColor,
            letterSpacing: '-0.01em',
            lineHeight: 1,
          }}>
            {mwValue !== null ? `${Math.abs(mwValue).toFixed(2)}` : '—'}
            <span style={{ fontSize: 9, fontWeight: 400, marginLeft: 2, color: '#5a6a78' }}>MW</span>
          </div>
        )}

        {/* Detail line (bottom) */}
        {detail && (
          <div style={{
            fontFamily: 'Inter,sans-serif',
            fontSize: 8,
            color: isGrid ? '#2a3540' : def.passive ? '#2e3c48' : '#4b5764',
            lineHeight: 1.3,
            whiteSpace: 'pre-wrap',
            overflow: 'hidden',
          }}>
            {detail}
          </div>
        )}
      </div>
    </foreignObject>
  )
}
