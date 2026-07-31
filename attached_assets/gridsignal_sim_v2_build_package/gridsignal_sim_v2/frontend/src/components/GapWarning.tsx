/**
 * GapWarning.tsx — Amber banner shown when timeseries gaps exist.
 *
 * Only rendered when droppedTicks > 0 or gapCount > 0.  Explains the
 * H1 gap rule: gaps can make universal assertions (no_alert, max_p_total)
 * INCONCLUSIVE because a dropped tick may have violated the condition.
 */

interface Props {
  droppedTicks: number
  gapCount: number
}

export function GapWarning({ droppedTicks, gapCount }: Props) {
  if (droppedTicks === 0 && gapCount === 0) return null

  return (
    <div className="flex items-start gap-2 rounded border border-amber-600/60
                    bg-amber-900/20 px-3 py-2 text-xs text-amber-300">
      <span className="mt-px shrink-0 text-amber-400">⚠</span>
      <p>
        <strong className="font-semibold">Data gaps detected</strong>
        {' — '}
        {droppedTicks > 0 && `${droppedTicks} tick${droppedTicks !== 1 ? 's' : ''} dropped from write queue`}
        {droppedTicks > 0 && gapCount > 0 && '; '}
        {gapCount > 0 && `${gapCount} sequence gap${gapCount !== 1 ? 's' : ''} in retained rows`}
        {'. Universal assertions ('}
        <code className="font-mono">no_insufficient_reserve_alert</code>
        {', '}
        <code className="font-mono">max_p_total_mw</code>
        {') are marked '}
        <strong>INCONCLUSIVE</strong>
        {' when gaps exist — a dropped tick may have violated the condition.'}
      </p>
    </div>
  )
}
