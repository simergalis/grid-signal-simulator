/**
 * PlantDiagram.tsx — one-line mimic diagram for the plant band (V-1).
 *
 * Layout: SVG viewBox 1200×440, preserveAspectRatio xMidYMid meet.
 * Flow lines are SVG paths; node boxes are <foreignObject> HTML overlays.
 *
 * Rules:
 *   · Flow width ∝ MW — nodes and flows bound to tickStore.
 *   · Grid connection always dashed + grey — never red.
 *   · Only clickable nodes respond to pointer events.
 *   · Lead-time callout on the far right (moves below on compact layout).
 */

import { useTickStore } from '../store/tickStore'
import { NODES, FLOWS, LEADTIME_BOX, DIAGRAM_W, DIAGRAM_H } from './plantLayout'
import { FlowLine, FlowMarkers } from './FlowLine'
import { PlantNode } from './PlantNode'
import type { TickPayload } from '../types'

interface PlantDiagramProps {
  /** Called when a clickable node is activated. Passes the node id. */
  onNodeClick: (nodeId: string) => void
  /** True when horizontal space is constrained (1024–1440 px). */
  compact?: boolean
}

function getMwForFlow(
  mwField: string | undefined,
  staticMW: number | undefined,
  tick: TickPayload | null,
): number {
  // No tick: use staticMW so solar (4.99) renders live and animated at rest.
  if (!tick) return staticMW ?? 0
  if (!mwField) return 0
  return Math.abs((tick as unknown as Record<string, unknown>)[mwField] as number) || 0
}

/** Lead-time callout — always-visible contextual card. */
function LeadTimeCallout({
  tick,
  compact,
}: {
  tick: TickPayload | null
  compact?: boolean
}) {
  const running   = tick !== null && tick.dt_lead_next_s > 0
  const secondsRaw = tick?.dt_lead_next_s ?? 45
  const seconds   = Math.max(0, Math.round(secondsRaw))
  const label     = running ? `${seconds} s remaining` : `${seconds} s`
  const sub       = running
    ? 'remaining before the racks reach full draw'
    : 'between the scheduler signal\nand the load reaching the racks'

  const box = LEADTIME_BOX

  // On compact mode, push the callout to the bottom of the diagram
  const x = compact ? DIAGRAM_W - box.w - 4 : box.x
  const y = compact ? DIAGRAM_H - box.h - 4 : box.y

  return (
    <foreignObject x={x} y={y} width={box.w} height={box.h}>
      <div
        // @ts-expect-error — xmlns required for SVG foreignObject HTML
        xmlns="http://www.w3.org/1999/xhtml"
        style={{
          width: '100%',
          height: '100%',
          boxSizing: 'border-box',
          borderRadius: 8,
          border: '1.5px solid #e0a458',
          background: '#0f1a22',
          padding: '16px 18px',
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
        }}
      >
        {/* Title */}
        <div style={{
          fontFamily: 'Inter,sans-serif',
          fontSize: 9,
          fontWeight: 700,
          letterSpacing: '0.12em',
          color: '#e0a458',
          textTransform: 'uppercase',
        }}>
          THE LEAD TIME
        </div>

        {/* Big number */}
        <div style={{
          fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace",
          fontSize: 48,
          fontWeight: 500,
          color: '#e0a458',
          lineHeight: 1,
          letterSpacing: '-0.02em',
        }}>
          {label}
        </div>

        {/* Subtitle */}
        <div style={{
          fontFamily: 'Inter,sans-serif',
          fontSize: 10,
          color: '#7d8b9c',
          lineHeight: 1.5,
          whiteSpace: 'pre-wrap',
        }}>
          {sub}
        </div>

        {/* Divider */}
        <div style={{ height: 1, background: '#1e2a36', margin: '4px 0' }} />

        {/* Body */}
        <div style={{
          fontFamily: 'Inter,sans-serif',
          fontSize: 10,
          color: '#7d8b9c',
          lineHeight: 1.55,
        }}>
          A power-sensor system learns about the load at 0 s — after it has already happened.
        </div>

        {/* Emphasis */}
        <div style={{
          fontFamily: 'Inter,sans-serif',
          fontSize: 11,
          color: '#e0a458',
          fontStyle: 'italic',
          fontWeight: 600,
        }}>
          That gap is the product.
        </div>
      </div>
    </foreignObject>
  )
}

export function PlantDiagram({ onNodeClick, compact }: PlantDiagramProps) {
  const tick = useTickStore(s => s.latestTick)

  return (
    <svg
      viewBox={`0 0 ${DIAGRAM_W} ${DIAGRAM_H}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ width: '100%', height: '100%', display: 'block', overflow: 'visible' }}
      aria-label="Plant one-line mimic diagram"
    >
      <FlowMarkers />

      {/* ── Flow lines (behind nodes) ───────────────────────────────────── */}
      {FLOWS.map(flow => (
        <FlowLine
          key={flow.id}
          d={flow.d}
          mwValue={getMwForFlow(flow.mwField, flow.staticMW, tick)}
          maxMW={flow.maxMW}
          color={flow.color}
          isGrid={flow.isGrid}
          marker={flow.marker}
        />
      ))}

      {/* ── Nodes ───────────────────────────────────────────────────────── */}
      {NODES.map(node => (
        <PlantNode
          key={node.id}
          def={node}
          tick={tick}
          onClick={onNodeClick}
        />
      ))}

      {/* ── Lead-time callout ─────────────────────────────────────────── */}
      <LeadTimeCallout tick={tick} compact={compact} />
    </svg>
  )
}
