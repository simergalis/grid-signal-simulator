/**
 * OpeningScreen.tsx — Level 0 landing screen (V-2).
 *
 * Three bands stacked vertically:
 *   Band 1  VerdictBand    — computed claim + 4 hero figures      (~100 px)
 *   Band 2  PlantDiagram   — one-line mimic, 8 elements           (flex-1)
 *   Band 3  SystemStrip    — forecast quality, network, agents     (~108 px)
 *
 * Responsive:
 *   ≥ 768 px  → three-band layout (this component)
 *   < 768 px  → ReadinessScreen tile grid (proven fallback)
 *
 * Topology explainer modal is managed by App.tsx (opened via GridSignalHeader).
 *
 * Click-through (V-4):
 *   Plant nodes → SubsystemModal (or tab navigation for switchgear)
 *   System strip tiles → SubsystemModal
 */

import { useState, useEffect, useRef } from 'react'
import { useTickStore } from '../store/tickStore'
import { TileTooltip, InfoBtn } from './TileTooltip'
import { VerdictBand }      from './VerdictBand'
import { PlantDiagram }     from './PlantDiagram'
import type { SolarPreview } from './PlantNode'
import { SubsystemModal }   from '../subsystem/SubsystemModal'
import { ComputeRacksModal } from './ComputeRacksModal'
import { SubsystemTile }    from '../readiness/SubsystemTile'
import type { TileState }   from '../readiness/SubsystemTile'
import { ReadinessScreen }  from '../readiness/ReadinessScreen'
import { useSubsystemData } from '../subsystem/useSubsystemData'
import { SUBSYSTEMS }       from '../readiness/subsystems'

/** Map from plant node id → subsystem modal id or tabRoute */
const NODE_MODAL_MAP: Record<string, { modalId?: string; tabRoute?: string }> = {
  'gas-turbine':     { modalId: 'gas-turbine-fleet' },
  'solar-pv':        { modalId: 'renewable' },
  'battery-bess':    { modalId: 'storage' },
  'grid-connection': { modalId: 'grid' },
  'switchgear-pms':  { tabRoute: 'overview' },
  'compute-racks':   { modalId: 'compute' },
  'cooling-plant':   { modalId: 'thermal' },
}

/** The three subsystem ids shown in the system strip (Band 3). */
const SYSTEM_STRIP_IDS = ['forecast-quality', 'gcc', 'agents']

interface OpeningScreenProps {
  onNavigate?: (tabId: string) => void
}

export function OpeningScreen({ onNavigate }: OpeningScreenProps) {
  const [windowWidth,   setWindowWidth]   = useState(() => window.innerWidth)
  const [activeModal,      setActiveModal]      = useState<string | null>(null)
  const [computeRacksOpen, setComputeRacksOpen] = useState(false)
  const [compact,       setCompact]       = useState(false)
  const [solarPreview,  setSolarPreview]  = useState<SolarPreview | null>(null)
  const [liveSolarMW,   setLiveSolarMW]   = useState<number | null>(null)
  const solarFetched = useRef(false)

  const data = useSubsystemData()
  const tick = useTickStore(s => s.latestTick)

  useEffect(() => {
    function onResize() {
      setWindowWidth(window.innerWidth)
      setCompact(window.innerWidth < 1440)
    }
    onResize()
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  // Fetch the solar forecast preview once on mount so the Solar PV node shows
  // today's Mistral weather label before the user starts a run.
  useEffect(() => {
    if (solarFetched.current) return
    solarFetched.current = true
    fetch('/solar-preview')
      .then(r => r.ok ? r.json() : null)
      .then((d: SolarPreview | null) => { if (d) setSolarPreview(d) })
      .catch(() => { /* silently ignore — endpoint is best-effort */ })
  }, [])

  // Poll GET /api/solar/state at 1.5 Hz so the Solar PV tile stays in sync
  // with the Renewable Supply modal.  Both now read the same live
  // solar_sim.live_aggregate_mw() value rather than the modal polling fresh
  // while the tile shows a stale WebSocket tick (e.g. after a run ends and
  // clear_run_sync() has switched the SolarSim back to standalone POA mode).
  useEffect(() => {
    const poll = () => {
      fetch('/api/solar/state')
        .then(r => r.ok ? r.json() : null)
        .then((d: { power?: { p_renewable_mw?: number } } | null) => {
          if (d?.power?.p_renewable_mw !== undefined) {
            setLiveSolarMW(d.power.p_renewable_mw)
          }
        })
        .catch(() => { /* silently ignore — non-critical */ })
    }
    poll()  // immediate first call
    const id = setInterval(poll, 1500)
    return () => clearInterval(id)
  }, [])

  // ── Below 768 px: fall back to the proven tile-grid layout ──────────────

  if (windowWidth < 768) {
    return <ReadinessScreen onNavigate={onNavigate} />
  }

  // ── Node click handler ──────────────────────────────────────────────────

  const handleNodeClick = (nodeId: string) => {
    // COMPUTE RACKS gets its own multi-tenant modal instead of the generic subsystem view.
    if (nodeId === 'compute-racks') {
      setComputeRacksOpen(true)
      return
    }
    const target = NODE_MODAL_MAP[nodeId]
    if (!target) return
    if (target.tabRoute) {
      onNavigate?.(target.tabRoute)
    } else if (target.modalId) {
      setActiveModal(target.modalId)
    }
  }

  return (
    <div className="flex flex-col h-full bg-canvas overflow-hidden">

      {/* ── Band 1: Verdict ────────────────────────────────────────────── */}
      <VerdictBand onLocationChanged={() => {
        solarFetched.current = false
        fetch('/solar-preview')
          .then(r => r.ok ? r.json() : null)
          .then((d: SolarPreview | null) => { if (d) setSolarPreview(d) })
          .catch(() => {})
      }} />

      {/* ── Band 2: Plant mimic ────────────────────────────────────────── */}
      <div className="flex-1 overflow-hidden relative">
        <div
          className="absolute top-2 left-4 z-10 font-mono text-[9px] font-bold
                     uppercase tracking-[0.12em] select-none"
          style={{ color: '#3fb6a8' }}
        >
          PLANT
          <span className="font-normal ml-2" style={{ color: '#4b5764' }}>
            Islanded microgrid · every element opens its detail view
          </span>
        </div>

        <div className="w-full h-full pt-6">
          <PlantDiagram onNodeClick={handleNodeClick} compact={compact} solarPreview={solarPreview} liveSolarMW={liveSolarMW} />
        </div>
      </div>

      {/* ── Band 3: System strip ───────────────────────────────────────── */}
      <SystemStrip
        ids={SYSTEM_STRIP_IDS}
        data={data}
        onTileClick={(id) => setActiveModal(id)}
      />

      {/* ── Modals ─────────────────────────────────────────────────────── */}
      {activeModal && (
        <SubsystemModal
          subsystemId={activeModal}
          onClose={() => setActiveModal(null)}
          onOpenPage={(tabId) => {
            setActiveModal(null)
            onNavigate?.(tabId)
          }}
        />
      )}

      {computeRacksOpen && (
        <ComputeRacksModal
          tick={tick}
          onClose={() => setComputeRacksOpen(false)}
        />
      )}

      {/* ── Tile tooltip — single fixed-position instance ──────────────── */}
      <TileTooltip />
    </div>
  )
}

// ─── System strip (Band 3) ───────────────────────────────────────────────────

interface SystemStripProps {
  ids: string[]
  data: ReturnType<typeof useSubsystemData>
  onTileClick: (id: string) => void
}

function SystemStrip({ ids, data, onTileClick }: SystemStripProps) {
  const gccFlashAt = useTickStore(s => s.gccFlashAt)
  const [gccFlashKey, setGccFlashKey] = useState(0)

  useEffect(() => {
    if (!gccFlashAt) return
    setGccFlashKey(k => k + 1)
  }, [gccFlashAt])
  return (
    <div
      className="flex-shrink-0 border-t border-border"
      style={{ background: '#0a0e13' }}
    >
      <div
        className="px-4 pt-2 pb-1 font-mono text-[9px] font-bold
                   uppercase tracking-[0.12em]"
        style={{ color: '#4b5764' }}
      >
        SYSTEM
        <span className="font-normal ml-2">
          not power assets — how much to trust the forecast, and what is analysing it
        </span>
      </div>

      <div className="flex gap-px px-4 pb-3" style={{ height: 106 }}>
        {ids.map(id => {
          const cfg = SUBSYSTEMS.find(s => s.id === id)
          const d   = data[id]
          if (!cfg || !d) return null

          return (
            <div
              key={id}
              className="flex-1 min-w-0"
              style={{ position: 'relative' }}
            >
              {/* Amber glow overlay — remounts on each GCC action to restart the animation */}
              {id === 'gcc' && gccFlashKey > 0 && (
                <div
                  key={gccFlashKey}
                  style={{
                    position: 'absolute', inset: 0, borderRadius: 8,
                    pointerEvents: 'none', zIndex: 2,
                    animation: 'gccFlash 5s ease-out forwards',
                  }}
                />
              )}
              <SubsystemTile
                id={id}
                name={cfg.name}
                state={d.state as TileState}
                accentColor={cfg.accentColor}
                verdict={d.verdict}
                metrics={d.metrics}
                onClick={onTileClick}
              />
              {/* ⓘ info button — floats above top-right corner of tile */}
              <InfoBtn
                id={id}
                style={{ position: 'absolute', top: 6, right: 6, zIndex: 3, width: 11, height: 11, fontSize: 6 }}
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}
