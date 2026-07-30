/**
 * SimClockHeader.tsx — persistent top bar (§19.2 / Design Spec §8.4).
 *
 * Shows:
 *   · Simulated time formatted as HH:MM:SS
 *   · Speed label: "1× real-time" / "60× accelerated" / "max speed"
 *   · Data-quality tag legend (four chips, always visible so the user
 *     knows what ⚑ badges mean before they appear on a panel)
 */

import { useTickStore } from '../store/tickStore'
import { DataQualityBadge } from './DataQualityBadge'

const ALL_DQ_TAGS = ['unmapped_hardware', 'uncalibrated_site', 'invalid_payload', 'stale_profile']

function formatSimTime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  return [h, m, s].map(v => String(v).padStart(2, '0')).join(':')
}

function speedLabel(playback_speed: number): string {
  if (playback_speed <= 0)  return 'max speed'
  if (playback_speed === 1) return '1× real-time'
  return `${playback_speed}× accelerated`
}

export function SimClockHeader() {
  const tick    = useTickStore(s => s.latestTick)
  const meta    = useTickStore(s => s.runMeta)
  const isInterp = useTickStore(s => s.isInterpolated)

  const simTime = tick?.sim_time_seconds ?? 0
  const speed   = meta?.playback_speed ?? 1

  return (
    <header className="flex items-center justify-between gap-4 border-b border-border bg-surface px-4 py-2">
      {/* Left: clock */}
      <div className="flex items-center gap-4">
        <div className="font-mono text-sm">
          <span className="text-muted">sim </span>
          <span className="text-text tabular-nums">{formatSimTime(simTime)}</span>
          {isInterp && (
            <span className="ml-1.5 text-[10px] italic text-muted" title="Client-side interpolation (§2.2)">
              ~interp
            </span>
          )}
        </div>

        {meta && (
          <div className="font-mono text-xs text-muted">
            {speedLabel(speed)}
          </div>
        )}

        {!tick && (
          <div className="font-mono text-xs text-muted animate-pulse">
            waiting for ticks…
          </div>
        )}
      </div>

      {/* Right: DQ legend */}
      <div className="flex items-center gap-1.5">
        <span className="mr-1 font-mono text-[10px] text-muted uppercase tracking-wider">DQ tags</span>
        {ALL_DQ_TAGS.map(tag => (
          <DataQualityBadge key={tag} tag={tag} full />
        ))}
      </div>
    </header>
  )
}
