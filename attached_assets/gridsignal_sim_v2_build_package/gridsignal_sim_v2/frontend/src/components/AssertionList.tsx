/**
 * AssertionList.tsx — Scrollable list of per-assertion outcomes.
 *
 * Each row shows: status icon, assertion check name, and detail string.
 * Empty assertions list shows a "No assertions configured" placeholder.
 */

import type { AssertionResult } from '../types'

const STATUS_ICON: Record<string, string> = {
  PASS:         '✓',
  FAIL:         '✗',
  INCONCLUSIVE: '?',
}
const STATUS_COLOR: Record<string, string> = {
  PASS:         'text-green-400',
  FAIL:         'text-red-400',
  INCONCLUSIVE: 'text-amber-400',
}

interface Props {
  assertions: AssertionResult[]
}

export function AssertionList({ assertions }: Props) {
  if (assertions.length === 0) {
    return (
      <div className="rounded border border-border px-3 py-3 text-xs text-muted italic">
        No assertions configured for this scenario — verdict is INCONCLUSIVE.
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-1">
      {assertions.map((a, i) => {
        const icon  = STATUS_ICON[a.status]  ?? '?'
        const color = STATUS_COLOR[a.status] ?? 'text-muted'
        return (
          <div
            key={i}
            className="flex items-start gap-2 rounded border border-border
                       bg-surface px-3 py-2 text-xs"
          >
            <span className={`shrink-0 font-mono font-bold text-sm ${color}`}>
              {icon}
            </span>
            <div className="min-w-0 flex-1">
              <span className="font-mono text-text">
                {a.check}
              </span>
              <span className={`ml-2 font-mono text-[10px] font-semibold uppercase ${color}`}>
                {a.status}
              </span>
              <p className="mt-0.5 text-muted leading-snug">{a.detail}</p>
            </div>
          </div>
        )
      })}
    </div>
  )
}
