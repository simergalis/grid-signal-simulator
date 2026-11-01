/**
 * ResultsScreen.tsx — Results and playback container (Step 9).
 *
 * Replaces the 2×2 panel grid in App.tsx when resultsRunId is set.
 *
 * Lifecycle:
 *   1. Mount → fetch GET /runs/{runId}/result (verdict, assertions)
 *   2. Mount → fetch GET /runs/{runId}/timeseries (full tick history)
 *   3. Render VerdictBanner + GapWarning + AssertionList (left column)
 *   4. Render PlaybackChart (main) + PlaybackScrubber + TickDetail (right)
 *
 * cursorIdx is a zero-based index into the rows array.  The scrubber and
 * chart both reflect the same cursor; TickDetail shows the row at cursor.
 *
 * Layout:
 *   ┌─────────────────────────────────────────────────────┐
 *   │ ← Back to live  |  VerdictBanner                    │  (header)
 *   ├─────────────────┬───────────────────────────────────┤
 *   │ GapWarning      │  PlaybackChart                    │
 *   │ AssertionList   │  PlaybackScrubber                 │
 *   │ EnergyCostPanel │  TickDetail                       │
 *   └─────────────────┴───────────────────────────────────┘
 */

import { useEffect, useState } from 'react'
import type { RunResult, TimeseriesRow } from '../types'
import { VerdictBanner }    from './VerdictBanner'
import { GapWarning }       from './GapWarning'
import { AssertionList }    from './AssertionList'
import { EnergyCostPanel }  from './EnergyCostPanel'
import { PlaybackChart }    from './PlaybackChart'
import { PlaybackScrubber } from './PlaybackScrubber'
import { StrandedPowerPanel } from './StrandedPowerPanel'
import { TickDetail }       from './TickDetail'

interface Props {
  runId:    string
  onClose:  () => void
  onRerun?: (scenarioId: string) => void
}

type LoadState = 'loading' | 'error' | 'ready'

export function ResultsScreen({ runId, onClose, onRerun }: Props) {
  const [loadState,  setLoadState]  = useState<LoadState>('loading')
  const [error,      setError]      = useState<string | null>(null)
  const [result,     setResult]     = useState<RunResult | null>(null)
  const [rows,       setRows]       = useState<TimeseriesRow[]>([])
  const [cursorIdx,  setCursorIdx]  = useState(0)

  // Fetch result + timeseries on mount.
  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoadState('loading')
      setError(null)
      try {
        const [resResult, resTimeseries] = await Promise.all([
          fetch(`/runs/${runId}/result`),
          fetch(`/runs/${runId}/timeseries`),
        ])

        if (!resResult.ok) {
          const body = await resResult.text()
          throw new Error(`GET /runs/${runId}/result → ${resResult.status}: ${body}`)
        }
        if (!resTimeseries.ok) {
          const body = await resTimeseries.text()
          throw new Error(`GET /runs/${runId}/timeseries → ${resTimeseries.status}: ${body}`)
        }

        const resultData     = await resResult.json() as RunResult
        const timeseriesData = await resTimeseries.json() as { rows: TimeseriesRow[] }

        if (!cancelled) {
          setResult(resultData)
          setRows(timeseriesData.rows)
          // Start cursor at the last tick so the final state is immediately visible.
          setCursorIdx(Math.max(0, timeseriesData.rows.length - 1))
          setLoadState('ready')
        }
      } catch (e) {
        if (!cancelled) {
          setError(String(e))
          setLoadState('error')
        }
      }
    }

    load()
    return () => { cancelled = true }
  }, [runId])

  // ── Loading / error states ───────────────────────────────────────────────

  if (loadState === 'loading') {
    return (
      <div className="flex flex-1 items-center justify-center text-muted font-mono text-sm">
        Loading results…
      </div>
    )
  }

  if (loadState === 'error' || !result) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3">
        <p className="font-mono text-sm text-danger">Failed to load results</p>
        {error && (
          <p className="max-w-lg text-center font-mono text-[10px] text-muted">{error}</p>
        )}
        <button
          className="rounded border border-border px-3 py-1 text-xs text-muted
                     hover:border-accent hover:text-accent transition-colors"
          onClick={onClose}
        >
          ← Back to live view
        </button>
      </div>
    )
  }

  const cursorRow = rows[cursorIdx] ?? null

  // ── Ready state ──────────────────────────────────────────────────────────

  return (
    <div className="flex flex-1 flex-col overflow-hidden">

      {/* Header: back button + verdict banner + re-run button */}
      <div className="flex items-center gap-2 border-b border-border bg-surface px-4 py-2">
        <button
          className="shrink-0 rounded border border-border px-2 py-1 text-xs text-muted
                     hover:border-accent hover:text-accent transition-colors"
          onClick={onClose}
        >
          ← Live
        </button>
        <div className="flex-1 min-w-0">
          <VerdictBanner result={result} />
        </div>
        {onRerun && result.scenario_id?.startsWith('fabric-s') && (
          <button
            className="shrink-0 rounded border border-accent/60 px-3 py-1 text-xs font-semibold
                       text-accent hover:bg-accent/10 transition-colors"
            onClick={() => onRerun(result.scenario_id!)}
            title={`Re-run ${result.scenario_id}`}
          >
            ↺ Re-run
          </button>
        )}
      </div>

      {/* Body: two-column layout */}
      <div className="flex flex-1 overflow-hidden">

        {/* Left column: gap warning + assertion list */}
        <aside className="w-72 shrink-0 flex flex-col gap-3 border-r border-border
                          overflow-y-auto px-3 py-3">
          <div>
            <h2 className="mb-1 font-mono text-[10px] uppercase tracking-wider text-muted">
              Data quality
            </h2>
            <GapWarning
              droppedTicks={result.dropped_ticks}
              gapCount={result.gap_count}
            />
          </div>

          <div>
            <h2 className="mb-1 font-mono text-[10px] uppercase tracking-wider text-muted">
              Assertions
            </h2>
            <AssertionList assertions={result.assertions} />
          </div>

          <div>
            <h2 className="mb-1 font-mono text-[10px] uppercase tracking-wider text-muted">
              Energy cost
            </h2>
            <EnergyCostPanel result={result} />
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between">
              <h2 className="font-mono text-[10px] uppercase tracking-wider text-muted">
                Turbine commitment
              </h2>
              <span className={`font-mono text-[10px] ${
                result.turbine_commitment_constraints_valid
                  ? 'text-emerald-400'
                  : 'text-amber-400'
              }`}>
                {result.turbine_commitment_constraints_valid ? 'VALID' : 'FLAGGED'}
              </span>
            </div>
            {!result.turbine_commitment_constraints_valid && (
              <p className="mb-2 text-[10px] leading-4 text-amber-300">
                Savings are not reportable: a hard reserve or unserved-energy
                constraint was violated.
              </p>
            )}
            {result.turbine_commitment_logs.length === 0 ? (
              <p className="text-[10px] text-muted">No controller actions recorded.</p>
            ) : (
              <div className="space-y-1.5">
                {result.turbine_commitment_logs.map((entry, index) => (
                  <div
                    key={`${entry.sim_time_s}-${entry.unit_id}-${index}`}
                    className="rounded border border-border/70 px-2 py-1.5 text-[10px]"
                  >
                    <div className="flex items-center justify-between font-mono">
                      <span className="font-semibold text-foreground">
                        {entry.action.toUpperCase()} · {entry.unit_id}
                      </span>
                      <span className="text-muted">t={entry.sim_time_s.toFixed(0)}s</span>
                    </div>
                    <div className="mt-0.5 leading-4 text-muted">
                      {entry.reason}
                    </div>
                    <div className="mt-0.5 font-mono text-muted">
                      forecast {entry.forecast_mw.toFixed(2)} MW · sync{' '}
                      {entry.synchronized_capacity_mw.toFixed(2)} MW · SoC{' '}
                      {(entry.bess_soc_fraction * 100).toFixed(1)}%
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </aside>

        {/* Right column: chart + scrubber + tick detail */}
        <main className="flex flex-1 flex-col overflow-y-auto">

          {/* Playback chart */}
          <div className="h-[min(45vh,420px)] min-h-[260px] shrink-0 p-2">
            <PlaybackChart rows={rows} cursorIdx={cursorIdx} />
          </div>

          {/* Scrubber */}
          <div className="border-t border-border">
            <PlaybackScrubber
              totalTicks={rows.length}
              cursorIdx={cursorIdx}
              onChange={setCursorIdx}
            />
          </div>

          {/* Facility-cap and recoverable-power view */}
          <div className="shrink-0 px-2 py-3">
            <StrandedPowerPanel runId={runId} scenario={result.scenario_name} />
          </div>

          {/* Tick detail */}
          <div className="border-t border-border overflow-y-auto px-3 py-2"
               style={{ maxHeight: '200px' }}>
            <h2 className="mb-1 font-mono text-[10px] uppercase tracking-wider text-muted">
              Tick detail
            </h2>
            <TickDetail row={cursorRow} />
          </div>
        </main>
      </div>
    </div>
  )
}
