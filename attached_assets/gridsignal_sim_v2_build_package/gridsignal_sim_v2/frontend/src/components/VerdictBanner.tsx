/**
 * VerdictBanner.tsx — PASS / FAIL / INCONCLUSIVE chip with run metadata.
 *
 * Displayed at the top of ResultsScreen.  The chip colour drives the
 * visual hierarchy: green (PASS), red (FAIL), amber (INCONCLUSIVE).
 */

import type { RunResult } from '../types'

const CHIP: Record<string, { bg: string; text: string; label: string }> = {
  PASS:         { bg: 'bg-green-900/40 border-green-600',   text: 'text-green-400',  label: '✓ PASS' },
  FAIL:         { bg: 'bg-red-900/40 border-red-600',       text: 'text-red-400',    label: '✗ FAIL' },
  INCONCLUSIVE: { bg: 'bg-amber-900/30 border-amber-600',   text: 'text-amber-400',  label: '? INCONCLUSIVE' },
}

interface Props {
  result: RunResult
}

export function VerdictBanner({ result }: Props) {
  const chip = CHIP[result.overall] ?? CHIP.INCONCLUSIVE
  const ts   = new Date(result.completed_at).toLocaleString()

  return (
    <div className={`flex items-center gap-3 rounded border px-4 py-2 ${chip.bg}`}>
      {/* Verdict chip */}
      <span className={`font-mono text-sm font-bold tracking-wide ${chip.text}`}>
        {chip.label}
      </span>

      {/* Scenario info */}
      <div className="flex-1 min-w-0">
        <p className="truncate text-sm font-semibold text-text">
          {result.scenario_name || 'Unknown scenario'}
        </p>
        <p className="font-mono text-[10px] text-muted truncate">
          {result.run_id} · completed {ts}
        </p>
      </div>

      {/* Stats */}
      <div className="flex items-center gap-4 text-right shrink-0">
        <div>
          <div className="font-mono text-xs text-muted">ticks</div>
          <div className="font-mono text-sm text-text">{result.tick_count}</div>
        </div>
        {result.dropped_ticks > 0 && (
          <div>
            <div className="font-mono text-xs text-muted">dropped</div>
            <div className="font-mono text-sm text-amber-400">{result.dropped_ticks}</div>
          </div>
        )}
      </div>
    </div>
  )
}
