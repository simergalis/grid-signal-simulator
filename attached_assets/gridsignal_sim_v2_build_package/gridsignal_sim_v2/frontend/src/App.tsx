/**
 * App.tsx — Root routing and run lifecycle (Step 8 / UI-Hierarchy V-2).
 *
 * Two distinct layouts:
 *
 * OPENING LAYOUT  (currentPage === 'readiness' and no resultsRunId)
 *   GridSignalHeader  — brand bar, STANDBY/LIVE badge, UTC clock, "How it works"
 *   OpeningScreen     — three-band SCADA mimic (V-2)
 *   DemoBar           — demo controls (scenario + speed + START)
 *   TopologyExplainer — modal, opened by GridSignalHeader "How it works"
 *
 * INNER PAGE LAYOUT  (all other pages / results screen)
 *   RunControlBar  — scenario picker + speed + start/stop + view results
 *   SimClockHeader — sim clock, decimation badge, DQ legend
 *   Tab navigation — Readiness | Overview | Proposals | … | Scenario Planner
 *   Page content
 *
 * Render loop: 4 Hz setInterval (250 ms) drains pending WS ticks.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { GridSignalHeader }        from './opening/GridSignalHeader'
import { DemoBar }                 from './opening/DemoBar'
import { TopologyExplainer }       from './opening/TopologyExplainer'
import { OpeningScreen }           from './opening/OpeningScreen'
import { SimClockHeader }          from './components/SimClockHeader'
import { HeroPanel }               from './components/HeroPanel'
import { ForecastChart }           from './components/ForecastChart'
import { AssetReservePanel }       from './components/AssetReservePanel'
import { RunControlBar }           from './components/RunControlBar'
import { ScenarioBuilder }         from './components/ScenarioBuilder'
import { ResultsScreen }           from './components/ResultsScreen'
import { ProposalsPage }           from './components/ProposalsPage'
import { NetworkTelemetryPage }    from './components/NetworkTelemetryPage'
import { ProcurementPage }         from './components/ProcurementPage'
import { ThermalCoolingPage }      from './components/ThermalCoolingPage'
import { ScenarioPlannerPage }     from './components/ScenarioPlannerPage'
import { useTickStore }            from './store/tickStore'
import { useScenarioStore }        from './store/scenarioStore'
import { useTickStream }           from './ws/useTickStream'

type PageView = 'readiness' | 'overview' | 'proposals' | 'procurement' | 'network' | 'thermal' | 'scenarios'

const FRAME_INTERVAL_MS = 250   // 4 Hz render loop

export default function App() {
  const [runId,         setRunId]         = useState<string | null>(null)
  const [lastRunId,     setLastRunId]     = useState<string | null>(null)
  const [resultsRunId,  setResultsRunId]  = useState<string | null>(null)
  const [drawerOpen,    setDrawerOpen]    = useState(false)
  const [editId,        setEditId]        = useState<string | null>(null)
  const [currentPage,   setCurrentPage]   = useState<PageView>('readiness')
  const [agentsEnabled, setAgentsEnabled] = useState(true)
  const [topoOpen,      setTopoOpen]      = useState(false)

  const drainFrame     = useTickStore(s => s.drainFrame)
  const setRunMeta     = useTickStore(s => s.setRunMeta)
  const reset          = useTickStore(s => s.reset)
  const selectScenario = useScenarioStore(s => s.selectScenario)

  useTickStream(runId)

  // 4 Hz render loop — drains pending WS ticks into display state.
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  useEffect(() => {
    intervalRef.current = setInterval(drainFrame, FRAME_INTERVAL_MS)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [drainFrame])

  // Run lifecycle callbacks
  const handleRunStarted = useCallback((id: string, speed: number) => {
    reset()
    setRunId(id)
    setLastRunId(id)
    setResultsRunId(null)
    setRunMeta({ run_id: id, playback_speed: speed })
    setCurrentPage('overview')
  }, [reset, setRunMeta])

  const handleRunStopped = useCallback(() => {
    setRunId(null)
    reset()
  }, [reset])

  const handleViewResults = useCallback((id: string) => {
    setResultsRunId(id)
  }, [])

  const handleNewScenario = useCallback(() => {
    setEditId(null)
    setDrawerOpen(true)
  }, [])

  const handleDrawerSaved = useCallback((scenarioId: string) => {
    selectScenario(scenarioId)
    setDrawerOpen(false)
  }, [selectScenario])

  const handleToggleAgents = useCallback(() => {
    const next = !agentsEnabled
    setAgentsEnabled(next)
    fetch('/api/agents/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: next }),
    }).catch(() => {})
  }, [agentsEnabled])

  // ── Results screen (any page) ──────────────────────────────────────────────
  if (resultsRunId !== null) {
    return (
      <div className="flex h-screen flex-col bg-canvas text-text overflow-hidden">
        <ResultsScreen
          runId={resultsRunId}
          onClose={() => setResultsRunId(null)}
        />
      </div>
    )
  }

  // ── Opening layout — no tab nav, brand header, demo bar ───────────────────
  if (currentPage === 'readiness') {
    return (
      <div className="flex h-screen flex-col bg-canvas text-text overflow-hidden">
        <GridSignalHeader
          runId={runId}
          onHowItWorks={() => setTopoOpen(true)}
        />

        <main className="flex-1 overflow-hidden">
          <OpeningScreen onNavigate={(tabId) => setCurrentPage(tabId as PageView)} />
        </main>

        <DemoBar
          runId={runId}
          lastRunId={lastRunId}
          onRunStarted={handleRunStarted}
          onRunStopped={handleRunStopped}
          onViewResults={handleViewResults}
          onNewScenario={handleNewScenario}
        />

        {topoOpen && (
          <TopologyExplainer onClose={() => setTopoOpen(false)} />
        )}

        {drawerOpen && (
          <ScenarioBuilder
            editId={editId}
            onClose={() => setDrawerOpen(false)}
            onSaved={handleDrawerSaved}
          />
        )}
      </div>
    )
  }

  // ── Inner page layout — RunControlBar + SimClockHeader + tabs ─────────────
  return (
    <div className="flex h-screen flex-col bg-canvas text-text overflow-hidden">

      <RunControlBar
        runId={runId}
        lastRunId={lastRunId}
        onRunStarted={handleRunStarted}
        onRunStopped={handleRunStopped}
        onNewScenario={handleNewScenario}
        onViewResults={handleViewResults}
      />

      <SimClockHeader />

      {/* Page navigation tabs */}
      <div className="flex gap-px border-b border-border bg-border flex-shrink-0">
        {([
          ['readiness',   'Readiness'],
          ['overview',    'Overview'],
          ['proposals',   'Proposals & Learning'],
          ['procurement', 'Grid & Procurement'],
          ['network',     'Network Telemetry'],
          ['thermal',     'Thermal & Cooling'],
          ['scenarios',   'Scenario Planner'],
        ] as const).map(([page, label]) => (
          <button
            key={page}
            onClick={() => setCurrentPage(page)}
            className={`px-4 py-2 text-xs font-medium transition-colors ${
              currentPage === page
                ? 'bg-surface text-text border-b-2 border-accent -mb-px'
                : 'bg-canvas text-text-muted hover:text-text hover:bg-surface/50'
            }`}
          >
            {label}
            {page === 'proposals' && agentsEnabled && (
              <span className="ml-1.5 inline-block w-1.5 h-1.5 rounded-full bg-green-400 align-middle" />
            )}
          </button>
        ))}
      </div>

      {/* Page content */}
      {currentPage === 'overview' ? (
        <main className="flex-1 grid grid-cols-2 grid-rows-[auto_1fr] gap-px bg-border overflow-hidden">
          <div className="col-span-2 bg-surface overflow-auto">
            <HeroPanel />
          </div>
          <div className="bg-surface overflow-hidden">
            <ForecastChart />
          </div>
          <div className="bg-surface overflow-auto">
            <AssetReservePanel />
          </div>
        </main>
      ) : currentPage === 'proposals' ? (
        <main className="flex-1 overflow-hidden">
          <ProposalsPage
            runId={runId ?? lastRunId}
            agentsEnabled={agentsEnabled}
            onToggleAgents={handleToggleAgents}
          />
        </main>
      ) : currentPage === 'procurement' ? (
        <main className="flex-1 overflow-hidden">
          <ProcurementPage runId={runId ?? lastRunId} />
        </main>
      ) : currentPage === 'network' ? (
        <main className="flex-1 overflow-hidden">
          <NetworkTelemetryPage runId={runId ?? lastRunId} />
        </main>
      ) : currentPage === 'thermal' ? (
        <main className="flex-1 overflow-hidden">
          <ThermalCoolingPage runId={runId ?? lastRunId} />
        </main>
      ) : (
        <main className="flex-1 overflow-hidden">
          <ScenarioPlannerPage runId={runId ?? lastRunId} />
        </main>
      )}

      {drawerOpen && (
        <ScenarioBuilder
          editId={editId}
          onClose={() => setDrawerOpen(false)}
          onSaved={handleDrawerSaved}
        />
      )}
    </div>
  )
}
