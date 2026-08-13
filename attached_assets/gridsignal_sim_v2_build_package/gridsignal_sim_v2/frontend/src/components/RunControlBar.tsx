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
  onRunStarted: (runId: string, playbackSpeed: number, socFloor?: number, socCeil?: number) => void
  onRunStopped: () => void
  onNewScenario: () => void
  onViewResults: (runId: string) => void
}

export function RunControlBar({ runId, lastRunId, onRunStarted, onRunStopped, onNewScenario, onViewResults }: Props) {
  const scenarios      = useScenarioStore(s => s.scenarios)
  const selectedId     = useScenarioStore(s => s.selectedId)
  const selectedSpec   = useScenarioStore(s => s.selectedSpec)
  const isLoading      = useScenarioStore(s => s.isLoading)
  const selectScenario = useScenarioStore(s => s.selectScenario)
  const fetchScenarios = useScenarioStore(s => s.fetchScenarios)

  const [speed,      setSpeed]      = useState(1)
  const [duration,   setDuration]   = useState(1800)
  const [customMins, setCustomMins] = useState(90)
  const [busy,       setBusy]       = useState(false)
  const [error,      setError]      = useState<string | null>(null)
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
      // Auto-arm the GPU Generator if the scenario has a generator_config preset
      if (selectedSpec?.generator_config) {
        const gen = useGpuGeneratorStore.getState()
        gen.stop()
        gen.reset()
        gen.updateConfig(selectedSpec.generator_config as Parameters<typeof gen.updateConfig>[0])
        gen.start()
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

  const isRunning = runId !== null
  const canViewResults = !isRunning && lastRunId !== null

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
