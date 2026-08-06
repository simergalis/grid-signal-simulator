/**
 * DemoBar.tsx — bottom demonstration controls bar for the opening screen.
 *
 * Matches the bottom strip in gs-01-opening-rest.svg:
 *   [Demonstration]  [demo-20mw ▾]  [10× speed ▾]  [▶ START]  │  [WHAT THIS DEMONSTRATES + copy]
 *
 * During a run: shows "Running" label, scenario name, speed, and Stop button.
 * After a run: shows a "View Results" button.
 *
 * All API calls mirror RunControlBar exactly — scenario fetch, POST /runs,
 * DELETE /runs/{id}.  The two components share state via useScenarioStore.
 */

import { useEffect, useState } from 'react'
import { useScenarioStore } from '../store/scenarioStore'

const SPEED_OPTIONS = [
  { label: '1×',  value: 1  },
  { label: '5×',  value: 5  },
  { label: '10×', value: 10 },
  { label: '30×', value: 30 },
  { label: 'MAX', value: 0  },
]

/** Sim-seconds for each duration option.  1e15 ≈ unlimited (31 M sim-years). */
const DURATION_OPTIONS = [
  { label: '5 min',    value: 300 },
  { label: '15 min',   value: 900 },
  { label: '30 min',   value: 1800 },
  { label: '1 hour',   value: 3600 },
  { label: '4 hours',  value: 14400 },
  { label: 'No limit', value: 1e15 },
]

/** Demonstration copy — what the demo shows. */
const DEMO_COPY = {
  heading: 'WHAT THIS DEMONSTRATES',
  line1: 'GridSignal reads the job scheduler, not the power meter. It knows a 20 MW step is coming',
  line2: '30–60 seconds before it arrives, and stages generation and storage before the load lands.',
}

/** Running copy — what to watch during the run. */
const RUNNING_COPY = {
  heading: 'WHAT YOU ARE WATCHING',
  line1: 'A 20 MW job was queued 25 seconds ago and has not reached full power yet. The turbine is',
  line2: 'already ramping and the battery is covering the gap.',
}

interface Props {
  runId:        string | null
  lastRunId:    string | null
  onRunStarted: (id: string, speed: number, socFloor?: number, socCeil?: number) => void
  onRunStopped: () => void
  onViewResults:    (id: string) => void
  onManageScenarios:() => void
}

export function DemoBar({
  runId, lastRunId, onRunStarted, onRunStopped, onViewResults, onManageScenarios,
}: Props) {
  const scenarios     = useScenarioStore(s => s.scenarios)
  const selectedId    = useScenarioStore(s => s.selectedId)
  const isLoading     = useScenarioStore(s => s.isLoading)
  const selectScenario = useScenarioStore(s => s.selectScenario)
  const fetchScenarios = useScenarioStore(s => s.fetchScenarios)

  const [speed,    setSpeed]    = useState(1)
  const [duration, setDuration] = useState(1800)
  const [busy,     setBusy]     = useState(false)
  const [error,    setError]    = useState<string | null>(null)

  // Log-test button state
  const [logBusy,  setLogBusy]  = useState(false)
  const [logMsg,   setLogMsg]   = useState<string | null>(null)

  const handleLogTest = async () => {
    setLogBusy(true)
    setLogMsg('Starting…')
    try {
      // 1. Kick off the background job — returns immediately with a job_id.
      const startResp = await fetch('/api/export/telemetry-log', {
        method: 'POST',
        credentials: 'include',
      })
      if (!startResp.ok) {
        const txt = await startResp.text()
        throw new Error(`${startResp.status}: ${txt}`)
      }
      const { job_id, eta_s } = await startResp.json() as { job_id: string; eta_s: number }

      // 2. Poll /status every second until done or error.
      const started = Date.now()
      while (true) {
        await new Promise(r => setTimeout(r, 1000))
        const elapsed = Math.round((Date.now() - started) / 1000)
        setLogMsg(`Logging… ${elapsed}/${Math.round(eta_s)}s`)

        const pollResp = await fetch(`/api/export/telemetry-log/${job_id}/status`, {
          credentials: 'include',
        })
        if (!pollResp.ok) throw new Error(`Poll failed: ${pollResp.status}`)
        const { status, detail } = await pollResp.json() as { status: string; detail: string }

        if (status === 'error') throw new Error(detail || 'Logger failed')
        if (status === 'done')  break
        if (elapsed > eta_s + 35) throw new Error('Timed out waiting for logger')
      }

      // 3. Fetch the finished file and trigger browser download.
      setLogMsg('Downloading…')
      const fileResp = await fetch(`/api/export/telemetry-log/${job_id}/file`, {
        credentials: 'include',
      })
      if (!fileResp.ok) throw new Error(`Download failed: ${fileResp.status}`)
      const blob = await fileResp.blob()
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href     = url
      a.download = 'system_stats.csv'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      setLogMsg('✓ Downloaded')
      setTimeout(() => setLogMsg(null), 3000)
    } catch (e) {
      setLogMsg(`✗ ${String(e)}`)
      setTimeout(() => setLogMsg(null), 5000)
    } finally {
      setLogBusy(false)
    }
  }

  useEffect(() => { fetchScenarios() }, [fetchScenarios])

  // Auto-fill speed + duration from the scenario spec whenever the selection changes.
  // Only fires when no run is active — during a run the controls are hidden anyway.
  useEffect(() => {
    if (!selectedId || runId !== null) return
    let cancelled = false
    fetch(`/scenarios/${selectedId}`)
      .then(r => r.ok ? r.json() : null)
      .then((data: { spec: { default_playback_speed?: number; end_sim_time?: number } } | null) => {
        if (cancelled || !data?.spec) return
        if (data.spec.default_playback_speed != null) setSpeed(data.spec.default_playback_speed)
        if (data.spec.end_sim_time           != null) setDuration(data.spec.end_sim_time)
      })
      .catch(() => {/* leave current values unchanged */})
    return () => { cancelled = true }
  }, [selectedId, runId])

  const handleStart = async () => {
    if (!selectedId) return
    setBusy(true); setError(null)
    try {
      const resp = await fetch('/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario_id: selectedId, playback_speed: speed, end_sim_time: duration }),
      })
      if (!resp.ok) throw new Error(`POST /runs → ${resp.status}: ${await resp.text()}`)
      const data = await resp.json() as { run_id: string; soc_floor_pct?: number; soc_ceil_pct?: number }
      onRunStarted(data.run_id, speed, data.soc_floor_pct, data.soc_ceil_pct)
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const handleStop = async () => {
    if (!runId) return
    setBusy(true); setError(null)
    try {
      const resp = await fetch(`/runs/${runId}`, { method: 'DELETE' })
      if (!resp.ok && resp.status !== 404)
        throw new Error(`DELETE /runs/${runId} → ${resp.status}: ${await resp.text()}`)
      onRunStopped()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const isRunning = runId !== null
  const canView   = !isRunning && lastRunId !== null
  const selectedName = scenarios.find(s => s.scenario_id === selectedId)?.name ?? ''
  const copy = isRunning ? RUNNING_COPY : DEMO_COPY

  return (
    <div
      className="flex items-center gap-0 border-t border-border flex-shrink-0"
      style={{ background: '#111821', minHeight: 74 }}
    >
      {/* ── Left: controls ────────────────────────────────────────────────── */}
      <div className="flex flex-col justify-center px-5 py-3 gap-1" style={{ minWidth: 60 }}>
        <div className="font-sans text-muted" style={{ fontSize: 11 }}>
          {isRunning ? 'Running' : 'Scenario'}
        </div>
      </div>

      {/* ── Scenario row ──────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 px-2">
        {/* Scenario dropdown */}
        <div
          className="flex items-center gap-2 rounded border border-border px-3 py-1.5"
          style={{ background: '#16202b', minWidth: 220 }}
        >
          <select
            className="bg-transparent text-text font-sans text-xs focus:outline-none disabled:opacity-50 flex-1"
            value={selectedId ?? ''}
            disabled={isRunning || isLoading || busy}
            onChange={e => selectScenario(e.target.value)}
          >
            {scenarios.length === 0 && <option value="" disabled style={{ background: '#1a2b3c', color: '#c8d6e5' }}>Loading…</option>}
            {scenarios.map(s => (
              <option key={s.scenario_id} value={s.scenario_id} style={{ background: '#1a2b3c', color: '#c8d6e5' }}>{s.name}</option>
            ))}
          </select>
          <span className="text-muted text-xs">▾</span>
        </div>

        {/* Duration selector */}
        <div
          className="flex items-center gap-1.5 rounded border border-border px-3 py-1.5"
          style={{ background: '#16202b' }}
        >
          <select
            className="bg-transparent text-text font-sans text-xs focus:outline-none disabled:opacity-50"
            value={duration}
            disabled={isRunning || busy}
            onChange={e => setDuration(Number(e.target.value))}
          >
            {DURATION_OPTIONS.map(o => (
              <option key={o.value} value={o.value} style={{ background: '#1a2b3c', color: '#c8d6e5' }}>{o.label}</option>
            ))}
          </select>
          <span className="text-muted text-xs">▾</span>
        </div>

        {/* Speed selector */}
        <div
          className="flex items-center gap-1.5 rounded border border-border px-3 py-1.5"
          style={{ background: '#16202b' }}
        >
          <select
            className="bg-transparent text-text font-sans text-xs focus:outline-none disabled:opacity-50"
            value={speed}
            disabled={isRunning || busy}
            onChange={e => setSpeed(Number(e.target.value))}
          >
            {SPEED_OPTIONS.map(o => (
              <option key={o.value} value={o.value} style={{ background: '#1a2b3c', color: '#c8d6e5' }}>{o.label} speed</option>
            ))}
          </select>
          <span className="text-muted text-xs">▾</span>
        </div>

        {/* Start / Stop */}
        {!isRunning ? (
          <button
            onClick={handleStart}
            disabled={!selectedId || busy}
            className="flex items-center gap-2 rounded px-5 py-2 font-sans font-bold
                       text-sm transition-colors disabled:opacity-40"
            style={{ background: '#3fb6a8', color: '#06231f', minWidth: 100 }}
          >
            <span>▶</span>
            <span>{busy ? 'Starting…' : 'START'}</span>
          </button>
        ) : (
          <button
            onClick={handleStop}
            disabled={busy}
            className="rounded border border-border px-5 py-2 font-sans font-bold
                       text-sm text-text hover:border-muted/60 transition-colors disabled:opacity-40"
          >
            {busy ? 'Stopping…' : 'Stop'}
          </button>
        )}

        {/* View Results */}
        {canView && (
          <button
            onClick={() => onViewResults(lastRunId!)}
            className="rounded border border-accent/50 px-3 py-1.5 font-sans text-xs
                       font-semibold text-accent hover:bg-accent/10 transition-colors"
          >
            View Results
          </button>
        )}

        {/* Scenarios button — opens the Scenario modal */}
        {!isRunning && (
          <button
            onClick={onManageScenarios}
            className="flex flex-col items-center rounded border border-border px-3 py-1 font-sans
                       text-muted hover:text-accent hover:border-accent/50 transition-colors leading-tight"
          >
            <span className="text-xs font-semibold">Scenario</span>
            <span className="text-[9px]">Editor</span>
          </button>
        )}

        {/* Log and Trace button — 60-second telemetry + predictive-variable capture */}
        <button
          onClick={handleLogTest}
          disabled={logBusy}
          title="Capture 60 s of telemetry + predictive variables and download system_stats.csv"
          className="flex items-center gap-1.5 rounded border px-3 py-1.5 font-sans text-xs
                     font-semibold transition-colors disabled:opacity-50"
          style={{
            borderColor: logBusy ? '#3fb6a8' : '#2a3a4a',
            color:        logBusy ? '#3fb6a8' : '#7d8b9c',
            background:   logBusy ? 'rgba(63,182,168,0.08)' : 'transparent',
          }}
        >
          {logBusy ? (
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
                 style={{ animation: 'spin 1s linear infinite' }}>
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4
                       M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
            </svg>
          ) : (
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="12" y1="11" x2="12" y2="17"/>
              <polyline points="9 14 12 17 15 14"/>
            </svg>
          )}
          <span>{logBusy ? logMsg ?? 'Logging…' : 'Log and Trace'}</span>
        </button>
        {logMsg && !logBusy && (
          <span
            className="font-mono max-w-[160px] truncate"
            style={{
              fontSize: 10,
              color: logMsg.startsWith('✓') ? '#3fb6a8' : '#e05c5c',
            }}
            title={logMsg}
          >
            {logMsg}
          </span>
        )}

        {/* Inline error */}
        {error && (
          <span className="font-mono text-[10px] text-danger max-w-[180px] truncate" title={error}>
            {error}
          </span>
        )}
      </div>

      {/* ── Separator ─────────────────────────────────────────────────────── */}
      <div className="self-stretch w-px bg-border mx-4" />

      {/* ── Right: explanatory copy ───────────────────────────────────────── */}
      <div className="flex flex-col justify-center px-4 py-3 flex-1">
        <div
          className="font-sans font-bold uppercase tracking-wider mb-1"
          style={{ fontSize: 9, color: '#4b5764', letterSpacing: '0.14em' }}
        >
          {copy.heading}
        </div>
        <div className="font-sans" style={{ fontSize: 11, color: '#e6ecf2', lineHeight: 1.5 }}>
          {copy.line1}
        </div>
        <div className="font-sans" style={{ fontSize: 11, color: '#7d8b9c', lineHeight: 1.5 }}>
          {copy.line2}
        </div>
      </div>

      {/* Running label — scenario + speed */}
      {isRunning && (
        <div className="flex items-center gap-2 px-5 shrink-0">
          <span
            className="font-mono font-medium"
            style={{ fontSize: 12, color: '#e6ecf2' }}
          >
            {selectedName} · {speed > 0 ? `${speed}×` : 'MAX'} speed
          </span>
        </div>
      )}

    </div>
  )
}
