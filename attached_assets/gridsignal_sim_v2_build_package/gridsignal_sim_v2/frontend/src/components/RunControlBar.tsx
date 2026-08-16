/**
 * RunControlBar.tsx — Scenario selector + run lifecycle controls (Step 8).
 *
 * Mounted above SimClockHeader in App.tsx.
 * Layout (left-to-right):
 *   [scenario dropdown ▼] [speed selector] [Start / Stop button] [New scenario…]
 *   [View Results button — visible when !isRunning && lastRunId !== null]
 *
 * Props:
 *   runId          — current active run ID (null = idle)
 *   lastRunId      — most recent run ID (set at start, kept after stop)
 *   onRunStarted   — called with (run_id, playback_speed) after POST /runs
 *   onRunStopped   — called after DELETE /runs/{id}
 *   onNewScenario  — called to open the ScenarioBuilder drawer
 *   onViewResults  — called with run_id when "View Results" is clicked
 *
 * The component owns no server-side state; all persistent scenario state
 * lives in useScenarioStore.
 */

import { useEffect, useState } from 'react'
import { useScenarioStore } from '../store/scenarioStore'
import { useBessConfigStore } from '../store/bessConfigStore'
import { useGpuGeneratorStore } from '../store/gpuGeneratorStore'

// ---------------------------------------------------------------------------
// Shared export helper — mirrors DemoBar.handleLogTest but callable anywhere
// ---------------------------------------------------------------------------
async function triggerExport(
  exportRunId: string | null,
  onStatus: (msg: string | null) => void,
): Promise<void> {
  const url = exportRunId
    ? `/api/export/telemetry-log?run_id=${encodeURIComponent(exportRunId)}`
    : '/api/export/telemetry-log'

  const startResp = await fetch(url, { method: 'POST', credentials: 'include' })
  if (!startResp.ok) {
    const txt = await startResp.text()
    throw new Error(`${startResp.status}: ${txt}`)
  }
  const { job_id, eta_s, run_id: resolvedRunId } = await startResp.json() as {
    job_id: string; eta_s: number; run_id: string | null
  }

  const label   = resolvedRunId ? resolvedRunId.slice(-8) : '…'
  const started = Date.now()
  while (true) {
    await new Promise(r => setTimeout(r, 500))
    const elapsed = Math.round((Date.now() - started) / 1000)
    onStatus(`Building log …${label} (${elapsed}s)`)

    const pollResp = await fetch(`/api/export/telemetry-log/${job_id}/status`, { credentials: 'include' })
    if (!pollResp.ok) throw new Error(`Poll failed: ${pollResp.status}`)
    const { status, detail } = await pollResp.json() as { status: string; detail: string }

    if (status === 'error') throw new Error(detail || 'Logger failed')
    if (status === 'done')  break
    if (elapsed > eta_s + 35) throw new Error('Timed out waiting for logger')
  }

  onStatus('Downloading…')
  const fileResp = await fetch(`/api/export/telemetry-log/${job_id}/file`, { credentials: 'include' })
  if (!fileResp.ok) throw new Error(`Download failed: ${fileResp.status}`)
  const blob = await fileResp.blob()
  const objUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href     = objUrl
  a.download = resolvedRunId ? `gridsignal_${resolvedRunId.slice(-12)}.csv` : 'gridsignal_export.csv'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(objUrl)
}

const SPEED_OPTIONS = [
  { label: '1×',   value: 1 },
  { label: '5×',   value: 5 },
  { label: '10×',  value: 10 },
  { label: '30×',  value: 30 },
  { label: 'MAX',  value: 0 },
]

/** Sim-seconds for each duration option.  1e15 ≈ unlimited (31 M sim-years). */
const DURATION_OPTIONS = [
  { label: '5 min',    value: 300 },
  { label: '15 min',   value: 900 },
  { label: '30 min',   value: 1800 },
  { label: '1 hour',   value: 3600 },
  { label: '3 hours',  value: 10800 },
  { label: '4 hours',  value: 14400 },
  { label: 'No limit', value: 1e15 },
]

/** Set of preset second values for fast membership checks. */
const PRESET_VALUES = new Set(DURATION_OPTIONS.map(o => o.value))

/** Format any second count as a concise human-readable label, e.g. 5400 → "90 min". */
function formatDuration(secs: number): string {
  if (secs >= 1e14) return 'No limit'
  const mins = Math.round(secs / 60)
  if (mins < 60) return `${mins} min`
  const h = Math.floor(mins / 60)
  const m = mins % 60
  return m === 0 ? `${h} hour${h === 1 ? '' : 's'}` : `${h}h ${m} min`
}

interface Props {
  runId: string | null
  lastRunId: string | null
  isPaused: boolean
  onRunStarted: (runId: string, playbackSpeed: number, socFloor?: number, socCeil?: number) => void
  onRunStopped: () => void
  onRunPaused: () => void
  onRunResumed: () => void
  onNewScenario: () => void
  onViewResults: (runId: string) => void
}

export function RunControlBar({ runId, lastRunId, isPaused, onRunStarted, onRunStopped, onRunPaused, onRunResumed, onNewScenario, onViewResults }: Props) {
  const scenarios      = useScenarioStore(s => s.scenarios)
  const selectedId     = useScenarioStore(s => s.selectedId)
  const selectedSpec   = useScenarioStore(s => s.selectedSpec)
  const isLoading      = useScenarioStore(s => s.isLoading)
  const selectScenario = useScenarioStore(s => s.selectScenario)
  const fetchScenarios = useScenarioStore(s => s.fetchScenarios)

  const [speed,      setSpeed]      = useState(1)
  const [duration,   setDuration]   = useState(1800)
  const [customMins, setCustomMins] = useState(90)
  const [busy,        setBusy]        = useState(false)
  const [error,       setError]       = useState<string | null>(null)
  const [exportBusy,  setExportBusy]  = useState(false)
  const [exportMsg,   setExportMsg]   = useState<string | null>(null)
  // BESS size overrides — configured via the Energy Storage modal, read here at run-start
  const bessRatedMw   = useBessConfigStore(s => s.ratedMw)
  const bessUsableMwh = useBessConfigStore(s => s.usableMwh)

  // Fetch scenario list on mount
  useEffect(() => { fetchScenarios() }, [fetchScenarios])

  // When the selected scenario changes, sync duration to its end_sim_time.
  // If the scenario's value is a known preset the select shows the right label
  // automatically; if not, we enter custom mode showing "X min" + an input.
  useEffect(() => {
    const t = selectedSpec?.end_sim_time
    if (!t) return
    setDuration(t)
    if (!PRESET_VALUES.has(t)) setCustomMins(Math.round(t / 60))
  }, [selectedSpec?.end_sim_time])

  const handleStart = async () => {
    if (!selectedId) return
    setBusy(true)
    setError(null)
    try {
      const resp = await fetch('/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenario_id: selectedId,
          playback_speed: speed,
          end_sim_time: duration,
          // Only include BESS overrides when the operator has explicitly set them
          ...(bessRatedMw   !== null && { bess_rated_mw_override:   bessRatedMw }),
          ...(bessUsableMwh !== null && { bess_usable_mwh_override: bessUsableMwh }),
        }),
      })
      if (!resp.ok) {
        const text = await resp.text()
        throw new Error(`POST /runs → ${resp.status}: ${text}`)
      }
      const data = await resp.json() as { run_id: string; soc_floor_pct?: number; soc_ceil_pct?: number }
      onRunStarted(data.run_id, speed, data.soc_floor_pct, data.soc_ceil_pct)
      // Auto-arm the GPU Generator if the scenario has a generator_config preset.
      // restartWith() is a single atomic set() so the button jumps directly to
      // "⏹ Stop" with no intermediate running:false flash.
      if (selectedSpec?.generator_config) {
        const gen = useGpuGeneratorStore.getState()
        gen.restartWith(selectedSpec.generator_config as Parameters<typeof gen.restartWith>[0])
      }
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

  const handlePause = async () => {
    if (!runId) return
    setBusy(true)
    setError(null)
    try {
      const resp = await fetch(`/runs/${runId}/pause`, { method: 'POST' })
      if (!resp.ok) {
        const text = await resp.text()
        throw new Error(`POST /runs/${runId}/pause → ${resp.status}: ${text}`)
      }
      onRunPaused()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const handleResume = async () => {
    if (!runId) return
    setBusy(true)
    setError(null)
    try {
      const resp = await fetch(`/runs/${runId}/resume`, { method: 'POST' })
      if (!resp.ok) {
        const text = await resp.text()
        throw new Error(`POST /runs/${runId}/resume → ${resp.status}: ${text}`)
      }
      onRunResumed()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const handleExport = async () => {
    setExportBusy(true)
    setExportMsg('Starting…')
    try {
      await triggerExport(runId ?? lastRunId, setExportMsg)
      setExportMsg('✓ Downloaded')
      setTimeout(() => setExportMsg(null), 3000)
    } catch (e) {
      setExportMsg(`✗ ${String(e)}`)
      setTimeout(() => setExportMsg(null), 5000)
    } finally {
      setExportBusy(false)
    }
  }

  const isRunning = runId !== null
  const canViewResults = !isRunning && lastRunId !== null
  const canExport = runId !== null || lastRunId !== null

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

      {/* Duration selector */}
      {(() => {
        const isCustom = !PRESET_VALUES.has(duration)
        return (
          <>
            <label className="text-xs text-muted shrink-0">Duration</label>
            <select
              className="rounded border border-border bg-canvas px-2 py-1 text-xs text-text
                         focus:outline-none focus:ring-1 focus:ring-accent disabled:opacity-50"
              value={isCustom ? '__custom__' : String(duration)}
              disabled={isRunning || busy}
              onChange={e => {
                const v = e.target.value
                if (v === '__other__') {
                  // "Other…" chosen — keep current customMins
                  setDuration(customMins * 60)
                } else {
                  setDuration(Number(v))
                }
              }}
            >
              {DURATION_OPTIONS.map(o => (
                <option key={o.value} value={String(o.value)}>{o.label}</option>
              ))}
              {/* Dynamic option shown when scenario specifies a non-preset (e.g. "90 min") */}
              {isCustom && (
                <option value="__custom__">{formatDuration(duration)}</option>
              )}
              <option value="__other__">Other…</option>
            </select>
            {/* Custom minutes input — shown for non-preset values */}
            {isCustom && (
              <div className="flex items-center gap-1">
                <input
                  type="number"
                  min={1}
                  step={1}
                  value={customMins}
                  disabled={isRunning || busy}
                  onChange={e => {
                    const m = Math.max(1, Math.floor(Number(e.target.value)))
                    setCustomMins(m)
                    setDuration(m * 60)
                  }}
                  className="w-14 rounded border border-border bg-canvas px-2 py-1 text-xs text-text
                             focus:outline-none focus:ring-1 focus:ring-accent disabled:opacity-50"
                />
                <span className="text-xs text-muted">min</span>
              </div>
            )}
          </>
        )
      })()}

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

      {/* Start / Pause / Resume / Stop — three-state machine */}
      {!isRunning ? (
        <button
          className="rounded bg-accent px-3 py-1 text-xs font-semibold text-white
                     hover:bg-accent/80 disabled:opacity-40 transition-colors"
          disabled={!selectedId || busy}
          onClick={handleStart}
        >
          {busy ? 'Starting…' : 'Start'}
        </button>
      ) : isPaused ? (
        <>
          {/* PAUSED indicator — must be explicit per spec, not inferred from buttons */}
          <span className="rounded border border-amber-400/70 px-2 py-0.5 font-mono
                           text-[10px] font-semibold text-amber-400 animate-pulse select-none"
                title="Simulation paused — simulated clock is frozen">
            ⏸ PAUSED
          </span>
          <button
            className="rounded bg-accent px-3 py-1 text-xs font-semibold text-white
                       hover:bg-accent/80 disabled:opacity-40 transition-colors"
            disabled={busy}
            onClick={handleResume}
          >
            {busy ? 'Resuming…' : 'Resume'}
          </button>
          <button
            className="rounded border border-danger px-3 py-1 text-xs font-semibold text-danger
                       hover:bg-danger/10 disabled:opacity-40 transition-colors"
            disabled={busy}
            onClick={handleStop}
          >
            {busy ? 'Stopping…' : 'Stop'}
          </button>
        </>
      ) : (
        <>
          <button
            className="rounded border border-border px-3 py-1 text-xs font-semibold text-muted
                       hover:border-amber-400/60 hover:text-amber-400 disabled:opacity-40
                       transition-colors"
            disabled={busy}
            onClick={handlePause}
            title="Freeze the simulated clock between ticks"
          >
            {busy ? 'Pausing…' : 'Pause'}
          </button>
          <button
            className="rounded border border-danger px-3 py-1 text-xs font-semibold text-danger
                       hover:bg-danger/10 disabled:opacity-40 transition-colors"
            disabled={busy}
            onClick={handleStop}
          >
            {busy ? 'Stopping…' : 'Stop'}
          </button>
        </>
      )}

      {/* View Results — visible when idle and a run has completed */}
      {canViewResults && (
        <button
          className="rounded border border-accent/60 px-3 py-1 text-xs font-semibold
                     text-accent hover:bg-accent/10 transition-colors"
          onClick={() => onViewResults(lastRunId!)}
          title={`View results for ${lastRunId}`}
        >
          View Results
        </button>
      )}

      {/* Export CSV — available during a run and after completion */}
      <button
        className="flex items-center gap-1.5 rounded border px-3 py-1 text-xs font-semibold
                   transition-colors disabled:opacity-50"
        style={{
          borderColor: exportBusy ? '#3fb6a8' : canExport ? '#2a3a4a' : '#1a2530',
          color:        exportBusy ? '#3fb6a8' : canExport ? '#7d8b9c' : '#3a4a5a',
          background:   exportBusy ? 'rgba(63,182,168,0.08)' : 'transparent',
          cursor:       canExport ? 'pointer' : 'not-allowed',
        }}
        disabled={exportBusy || !canExport}
        onClick={handleExport}
        title={
          !canExport
            ? 'Start a run first — export is available once data has been recorded'
            : exportMsg ?? 'Export full-run telemetry and predictive variables as CSV (up to 60 min)'
        }
      >
        {exportBusy ? exportMsg : '↓ Export CSV'}
      </button>

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
