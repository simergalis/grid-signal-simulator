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

import { useState, useEffect, useRef } from 'react'
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

// ── Shared style constants ─────────────────────────────────────────────────
const _SANS: React.CSSProperties = { fontFamily: 'Inter,sans-serif' }
const _MONO: React.CSSProperties = {
  fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace",
}
const _RULE: React.CSSProperties = { height: 1, background: '#1e2a36', margin: '2px 0' }
const _BODY: React.CSSProperties = {
  ..._SANS, fontSize: 10, color: '#7d8b9c', lineHeight: 1.5, whiteSpace: 'pre-wrap' as const,
}
const _LABEL = (color: string): React.CSSProperties => ({
  ..._SANS, fontSize: 9, fontWeight: 700,
  letterSpacing: '0.12em', textTransform: 'uppercase' as const, color,
})
const _BIG = (color: string): React.CSSProperties => ({
  ..._MONO, fontSize: 48, fontWeight: 500, color, lineHeight: 1, letterSpacing: '-0.02em',
})

/**
 * LeadTimeCallout — four-state operational panel (ISA-101 colour discipline).
 *
 * Spec vocabulary: "step-load" (37× in spec), "Δt_lead".
 * "load event" and "next load event" do not appear in the spec.
 *
 * State 1  AT REST       grey  — "NO STEP-LOAD INCOMING"
 * State 2  COUNTING DOWN amber — "STEP-LOAD INCOMING / 23 s / Nothing required"
 * State 3  RESERVE SHORT red   — "STEP-LOAD INCOMING — RESERVE SHORT / Acknowledge"
 * State 4  LANDED        teal  — "STEP-LOAD LANDED / Staged X s ahead" (30 s hold)
 *
 * ISA-101: permanently-amber trains operators to stop seeing amber.
 * The panel is muted at rest and gains colour only when action matters.
 *
 * "last event X min ago" in the at-rest body proves the scheduler feed is
 * alive — a dead integration and an empty queue look identical otherwise.
 *
 * Pitch copy belongs in the "How it works" topology explainer (onboarding,
 * opened deliberately). An operator running a plant should not see it.
 */
function LeadTimeCallout({
  tick,
  compact,
}: {
  tick: TickPayload | null
  compact?: boolean
}) {
  const latchedAlert     = useTickStore(s => s.latchedAlert)
  const acknowledgeAlert = useTickStore(s => s.acknowledgeAlert)

  // ── Landing-state tracking ─────────────────────────────────────────────────
  // When Δt_lead transitions from > 0 to 0, show STEP-LOAD LANDED for 30 s.
  const [landedUntil,      setLandedUntil]      = useState(0)
  const [stagedSecs,       setStagedSecs]       = useState(45)
  const [turbineAtLanding, setTurbineAtLanding] = useState(0)
  const prevDtLead  = useRef(0)
  const maxDtLead   = useRef(0)            // peak Δt_lead during current ramp
  const lastLandedAt = useRef<number>(0)  // wall-clock of most recent landing

  useEffect(() => {
    if (!tick) return
    const cur  = tick.dt_lead_next_s
    const prev = prevDtLead.current
    if (cur > maxDtLead.current) maxDtLead.current = cur
    // Rising-to-falling edge: step-load just landed
    if (prev > 0 && cur <= 0) {
      const now = Date.now()
      setLandedUntil(now + 30_000)
      setStagedSecs(Math.round(maxDtLead.current))
      setTurbineAtLanding(tick.turbine_output_mw)
      lastLandedAt.current = now
      maxDtLead.current = 0
    }
    prevDtLead.current = cur
  }, [tick])

  // Clear the landed banner after 30 s
  useEffect(() => {
    if (!landedUntil) return
    const ms = landedUntil - Date.now()
    if (ms <= 0) { setLandedUntil(0); return }
    const id = setTimeout(() => setLandedUntil(0), ms)
    return () => clearTimeout(id)
  }, [landedUntil])

  // ── Derive state ───────────────────────────────────────────────────────────
  const isLanded  = landedUntil > 0 && Date.now() < landedUntil
  const isRunning = tick !== null && tick.dt_lead_next_s > 0
  const hasAlert  = latchedAlert !== null

  // "last event X min ago" — proves scheduler feed is alive at rest
  const lastEventStr = (() => {
    if (!lastLandedAt.current) return 'no events this session'
    const minsAgo = Math.floor((Date.now() - lastLandedAt.current) / 60_000)
    return minsAgo < 1 ? 'last event < 1 min ago' : `last event ${minsAgo} min ago`
  })()

  // ISA-101 colour by state
  const accent =
    isLanded   ? '#3fb6a8' :
    !isRunning ? '#2a3a4a' :
    hasAlert   ? '#f85149' :
    /* ok */    '#e0a458'

  // Geometry
  const box = LEADTIME_BOX
  const x   = compact ? DIAGRAM_W - box.w - 4 : box.x
  const y   = compact ? DIAGRAM_H - box.h - 4 : box.y

  return (
    <foreignObject x={x} y={y} width={box.w} height={box.h}>
      <div
        // @ts-expect-error — xmlns required for SVG foreignObject HTML
        xmlns="http://www.w3.org/1999/xhtml"
        style={{
          width: '100%', height: '100%', boxSizing: 'border-box',
          borderRadius: 8, border: `1.5px solid ${accent}`,
          background: '#0f1a22', padding: '14px 16px',
          display: 'flex', flexDirection: 'column', gap: 5,
          transition: 'border-color 0.35s',
        }}
      >

        {/* ── STATE 4: STEP-LOAD LANDED ────────────────────────────────── */}
        {isLanded && <>
          <div style={_LABEL(accent)}>STEP-LOAD LANDED</div>
          <div style={_RULE} />
          <div style={{ ..._MONO, fontSize: 20, fontWeight: 600, color: '#e6edf3', lineHeight: 1.25 }}>
            Staged {stagedSecs} s ahead of arrival
          </div>
          <div style={_BODY}>
            Turbine {turbineAtLanding.toFixed(2)} MW · BESS standby
          </div>
        </>}

        {/* ── STATE 3: RESERVE SHORT ───────────────────────────────────── */}
        {!isLanded && isRunning && hasAlert && (() => {
          const secs      = Math.max(0, Math.round(tick!.dt_lead_next_s))
          const predicted = tick!.confidence_upper_mw
          const avail     = tick!.turbine_output_mw + tick!.bess_output_mw + tick!.p_renewable_mw
          const shortfall = Math.max(0, predicted - avail)
          return <>
            <div style={_LABEL(accent)}>STEP-LOAD INCOMING — RESERVE SHORT</div>
            <div style={_RULE} />
            <div style={_BIG(accent)}>{secs} s</div>
            <div style={{ ..._BODY, color: '#e6edf3' }}>
              {`until racks reach full draw\n+${predicted.toFixed(1)} MW · ${
                shortfall > 0.1
                  ? `${shortfall.toFixed(1)} MW will be uncovered`
                  : 'insufficient reserve'
              }`}
            </div>
            <button
              onClick={() => latchedAlert && acknowledgeAlert(latchedAlert.tick_index)}
              style={{
                marginTop: 4, padding: '3px 10px', borderRadius: 4,
                border: `1px solid ${accent}`, background: 'transparent',
                color: accent, cursor: 'pointer', alignSelf: 'flex-start',
                ..._MONO, fontSize: 9, fontWeight: 700, letterSpacing: '0.06em',
              }}
            >
              Acknowledge
            </button>
          </>
        })()}

        {/* ── STATE 2: COUNTING DOWN ───────────────────────────────────── */}
        {!isLanded && isRunning && !hasAlert && (() => {
          const secs      = Math.max(0, Math.round(tick!.dt_lead_next_s))
          const predicted = tick!.confidence_upper_mw
          return <>
            <div style={_LABEL(accent)}>STEP-LOAD INCOMING</div>
            <div style={_RULE} />
            <div style={_BIG(accent)}>{secs} s</div>
            <div style={{ ..._BODY, color: '#e6edf3' }}>
              {`until racks reach full draw\n+${predicted.toFixed(1)} MW · turbine ramping · BESS armed`}
            </div>
            <div style={{ ..._BODY, color: '#3fb6a8', fontWeight: 600 }}>Nothing required</div>
          </>
        })()}

        {/* ── STATE 1: AT REST ─────────────────────────────────────────── */}
        {!isLanded && !isRunning && <>
          <div style={_LABEL(accent)}>NO STEP-LOAD INCOMING</div>
          <div style={_RULE} />
          <div style={{ ..._BODY, color: '#4b5764', lineHeight: 1.65 }}>
            {`Scheduler feed healthy · ${lastEventStr}\nNotice on next: 30–60 s`}
          </div>
        </>}

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
