/**
 * App.tsx — Page 1: Site Overview (§7.1 / §19.2).
 *
 * Layout (Step 8):
 *   RunControlBar      (scenario selector + speed + start/stop + view results)
 *   SimClockHeader     (sim clock, decimation badge)
 *   ┌──────────────┬──────────────────────────┐
 *   │  HeroPanel   │  ForecastChart           │
 *   ├──────────────┼──────────────────────────┤
 *   │  AssetReserve│  AlertDock               │
 *   └──────────────┴──────────────────────────┘
 *
 * Step 9: when resultsRunId is set, the 2×2 grid is replaced by
 * <ResultsScreen> which shows verdict, playback chart, and scrubber.
 * The "View Results" button in RunControlBar becomes visible once a run
 * completes (lastRunId set; runId cleared).
 *
 * Render loop: 4 Hz setInterval (250 ms) calls drainFrame() so the store
 * moves pending WS ticks into display state.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { SimClockHeader }    from './components/SimClockHeader'
import { HeroPanel }         from './components/HeroPanel'
import { ForecastChart }     from './components/ForecastChart'
import { AssetReservePanel } from './components/AssetReservePanel'
import { AlertDock }         from './components/AlertDock'
import { RunControlBar }     from './components/RunControlBar'
import { ScenarioBuilder }   from './components/ScenarioBuilder'
import { ResultsScreen }     from './components/ResultsScreen'
import { useTickStore }      from './store/tickStore'
import { useScenarioStore }  from './store/scenarioStore'
import { useTickStream }     from './ws/useTickStream'

const FRAME_INTERVAL_MS = 250   // 4 Hz render loop

export default function App() {
  const [runId,         setRunId]         = useState<string | null>(null)
  const [lastRunId,     setLastRunId]     = useState<string | null>(null)
  const [resultsRunId,  setResultsRunId]  = useState<string | null>(null)
  const [drawerOpen,    setDrawerOpen]    = useState(false)
  const [editId,        setEditId]        = useState<string | null>(null)

  const drainFrame = useTickStore(s => s.drainFrame)
  const setRunMeta = useTickStore(s => s.setRunMeta)
  const reset      = useTickStore(s => s.reset)
  const selectScenario = useScenarioStore(s => s.selectScenario)

  // Subscribe to the WS tick stream for the active run.
  useTickStream(runId)

  // 4 Hz render loop — drains pending WS ticks into display state.
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  useEffect(() => {
    intervalRef.current = setInterval(drainFrame, FRAME_INTERVAL_MS)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [drainFrame])

  // RunControlBar callbacks
  const handleRunStarted = useCallback((id: string, speed: number) => {
    reset()
    setRunId(id)
    setLastRunId(id)
    setResultsRunId(null)   // close any open results screen
    setRunMeta({ run_id: id, playback_speed: speed })
  }, [reset, setRunMeta])

  const handleRunStopped = useCallback(() => {
    setRunId(null)
    reset()
    // lastRunId stays — "View Results" button remains available.
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

  // Show results screen if a completed run is selected for viewing.
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

  return (
    <div className="flex h-screen flex-col bg-canvas text-text overflow-hidden">

      {/* Run controls — scenario picker, speed, start/stop, view results */}
      <RunControlBar
        runId={runId}
        lastRunId={lastRunId}
        onRunStarted={handleRunStarted}
        onRunStopped={handleRunStopped}
        onNewScenario={handleNewScenario}
        onViewResults={handleViewResults}
      />

      {/* Persistent sim-clock header */}
      <SimClockHeader />

      {/* 2×2 panel grid */}
      <main className="flex-1 grid grid-cols-1 md:grid-cols-2 grid-rows-2 gap-px bg-border overflow-hidden">
        {/* Row 1 */}
        <div className="bg-surface overflow-auto">
          <HeroPanel />
        </div>
        <div className="bg-surface overflow-hidden">
          <ForecastChart />
        </div>

        {/* Row 2 */}
        <div className="bg-surface overflow-auto">
          <AssetReservePanel />
        </div>
        <div className="bg-surface overflow-auto">
          <AlertDock />
        </div>
      </main>

      {/* Scenario Builder drawer */}
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
