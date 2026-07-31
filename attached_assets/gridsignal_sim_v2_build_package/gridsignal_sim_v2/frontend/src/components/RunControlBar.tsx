/**
 * RunControlBar.tsx — Scenario selector + run lifecycle controls (Step 8).
 *
 * Mounted above SimClockHeader in App.tsx.
 * Layout (left-to-right):
 *   [scenario dropdown ▼] [speed selector] [Start / Stop button] [New scenario…]
 *
 * Props:
 *   runId          — current active run ID (null = idle)
 *   onRunStarted   — called with (run_id, playback_speed) after POST /runs
 *   onRunStopped   — called after DELETE /runs/{id}
 *   onNewScenario  — called to open the ScenarioBuilder drawer
 *
 * The component owns no server-side state; all persistent scenario state
 * lives in useScenarioStore.
 */

import { useEffect, useState } from 'react'
import { useScenarioStore } from '../store/scenarioStore'

const SPEED_OPTIONS = [
  { label: '1×',   value: 1 },
  { label: '5×',   value: 5 },
  { label: '10×',  value: 10 },
  { label: '30×',  value: 30 },
  { label: 'MAX',  value: 0 },
]

interface Props {
  runId: string | null
  onRunStarted: (runId: string, playbackSpeed: number) => void
  onRunStopped: () => void
  onNewScenario: () => void
}

export function RunControlBar({ runId, onRunStarted, onRunStopped, onNewScenario }: Props) {
  const scenarios    = useScenarioStore(s => s.scenarios)
  const selectedId   = useScenarioStore(s => s.selectedId)
  const isLoading    = useScenarioStore(s => s.isLoading)
  const selectScenario = useScenarioStore(s => s.selectScenario)
  const fetchScenarios = useScenarioStore(s => s.fetchScenarios)

  const [speed, setSpeed]       = useState(10)
  const [busy,  setBusy]        = useState(false)
  const [error, setError]       = useState<string | null>(null)

  // Fetch scenario list on mount
  useEffect(() => { fetchScenarios() }, [fetchScenarios])

  const handleStart = async () => {
    if (!selectedId) return
    setBusy(true)
    setError(null)
    try {
      const resp = await fetch('/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario_id: selectedId, playback_speed: speed }),
      })
      if (!resp.ok) {
        const text = await resp.text()
        throw new Error(`POST /runs → ${resp.status}: ${text}`)
      }
      const data = await resp.json() as { run_id: string }
      onRunStarted(data.run_id, speed)
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const handleStop = async () => {
    if (!runId) return
    setBusy(true)
    setError(null)
    try {
      const resp = await fetch(`/runs/${runId}`, { method: 'DELETE' })
      if (!resp.ok && resp.status !== 404) {
        const text = await resp.text()
        throw new Error(`DELETE /runs/${runId} → ${resp.status}: ${text}`)
      }
      onRunStopped()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const isRunning = runId !== null

  return (
    <div className="flex items-center gap-2 border-b border-border bg-surface px-4 py-2 text-sm">
      {/* Scenario dropdown */}
      <label className="text-xs text-muted shrink-0">Scenario</label>
      <select
        className="flex-1 max-w-[220px] rounded border border-border bg-canvas px-2 py-1 text-xs text-text
                   focus:outline-none focus:ring-1 focus:ring-accent disabled:opacity-50"
        value={selectedId ?? ''}
        disabled={isRunning || isLoading || busy}
        onChange={e => selectScenario(e.target.value)}
      >
        {scenarios.length === 0 && (
          <option value="" disabled>Loading…</option>
        )}
        {scenarios.map(s => (
          <option key={s.scenario_id} value={s.scenario_id}>
            {s.name}
          </option>
        ))}
      </select>

      {/* New scenario button */}
      <button
        className="rounded border border-border px-2 py-1 text-xs text-muted
                   hover:border-accent hover:text-accent disabled:opacity-40
                   transition-colors"
        disabled={busy}
        onClick={onNewScenario}
        title="Open Scenario Builder"
      >
        + New
      </button>

      {/* Speed selector */}
      <label className="text-xs text-muted shrink-0">Speed</label>
      <select
        className="rounded border border-border bg-canvas px-2 py-1 text-xs text-text
                   focus:outline-none focus:ring-1 focus:ring-accent disabled:opacity-50"
        value={speed}
        disabled={isRunning || busy}
        onChange={e => setSpeed(Number(e.target.value))}
      >
        {SPEED_OPTIONS.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>

      {/* Start / Stop */}
      {!isRunning ? (
        <button
          className="rounded bg-accent px-3 py-1 text-xs font-semibold text-white
                     hover:bg-accent/80 disabled:opacity-40 transition-colors"
          disabled={!selectedId || busy}
          onClick={handleStart}
        >
          {busy ? 'Starting…' : 'Start'}
        </button>
      ) : (
        <button
          className="rounded border border-danger px-3 py-1 text-xs font-semibold text-danger
                     hover:bg-danger/10 disabled:opacity-40 transition-colors"
          disabled={busy}
          onClick={handleStop}
        >
          {busy ? 'Stopping…' : 'Stop'}
        </button>
      )}

      {/* Inline error */}
      {error && (
        <span className="ml-2 max-w-[200px] truncate font-mono text-[10px] text-danger" title={error}>
          {error}
        </span>
      )}

      {/* Active run badge */}
      {runId && (
        <span className="ml-auto font-mono text-[10px] text-muted truncate max-w-[140px]" title={runId}>
          {runId}
        </span>
      )}
    </div>
  )
}
