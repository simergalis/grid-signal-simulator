/**
 * App.tsx — Page 1: Site Overview (§7.1 / §19.2).
 *
 * Layout: SimClockHeader (top bar) + 2×2 grid of panels.
 *   ┌──────────────┬──────────────────────────┐
 *   │  HeroPanel   │  ForecastChart           │
 *   ├──────────────┼──────────────────────────┤
 *   │  AssetReserve│  AlertDock               │
 *   └──────────────┴──────────────────────────┘
 * On narrow screens: single column, panels stack in the same order.
 *
 * Render loop: 4 Hz setInterval (250 ms) calls drainFrame() so the store
 * moves pending WS ticks into display state.  The store handles:
 *   0 ticks pending → interpolate (smooth animation)
 *   1 tick pending  → direct update
 *   N>1 ticks       → latest tick + decimation badge
 *
 * Run lifecycle: POST /runs on mount (with a demo body), then subscribe
 * WebSocket.  In production the run_id would come from the route or from
 * user-provided scenario config; the hardcoded demo scenario is Step 7 scope.
 *
 * The demo scenario mirrors the "demo-20mw" scenario from example_usage.py:
 * a single 20 MW GPU job on a site with one turbine and one BESS.  At
 * playback_speed=1 the scenario takes ~5 min of real time; at max speed
 * (playback_speed=0) it completes in a few seconds.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { SimClockHeader } from './components/SimClockHeader'
import { HeroPanel } from './components/HeroPanel'
import { ForecastChart } from './components/ForecastChart'
import { AssetReservePanel } from './components/AssetReservePanel'
import { AlertDock } from './components/AlertDock'
import { useTickStore } from './store/tickStore'
import { useTickStream } from './ws/useTickStream'

const FRAME_INTERVAL_MS = 250   // 4 Hz render loop

/** Demo scenario body — mirrors example_usage.py "demo-20mw".
 *  In Step 8 this will come from a ScenarioBuilder form. */
const DEMO_RUN_BODY = {
  scenario_id: 'demo-20mw',
  end_sim_time: 14400.0,   // 4 h simulated
  playback_speed: 60,      // 60× accelerated — one real minute = one sim hour
}

export default function App() {
  const [runId, setRunId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const drainFrame  = useTickStore(s => s.drainFrame)
  const setRunMeta  = useTickStore(s => s.setRunMeta)
  const reset       = useTickStore(s => s.reset)

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

  // Start a demo run on mount.
  const startRun = useCallback(async () => {
    reset()
    setError(null)
    try {
      const resp = await fetch('/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(DEMO_RUN_BODY),
      })
      if (!resp.ok) {
        const text = await resp.text()
        throw new Error(`POST /runs → ${resp.status}: ${text}`)
      }
      const data = await resp.json() as { run_id: string; playback_speed?: number }
      setRunId(data.run_id)
      setRunMeta({
        run_id: data.run_id,
        playback_speed: DEMO_RUN_BODY.playback_speed,
      })
    } catch (e) {
      setError(String(e))
    }
  }, [reset, setRunMeta])

  useEffect(() => {
    startRun()
  }, [startRun])

  return (
    <div className="flex h-screen flex-col bg-canvas text-text overflow-hidden">
      {/* Persistent header */}
      <SimClockHeader />

      {/* Error banner */}
      {error && (
        <div className="border-b border-danger/40 bg-danger/10 px-4 py-2 font-mono text-xs text-danger">
          {error}
          <button
            className="ml-3 underline hover:no-underline"
            onClick={startRun}
          >
            retry
          </button>
        </div>
      )}

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

      {/* Run status footer */}
      {runId && (
        <footer className="border-t border-border bg-surface px-4 py-1 font-mono text-[10px] text-muted">
          run {runId}
        </footer>
      )}
    </div>
  )
}
