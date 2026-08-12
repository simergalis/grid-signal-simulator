/**
 * ComputeRacksModal.tsx — Multi-tenant compute racks detail view.
 *
 * Opens when the operator clicks the COMPUTE RACKS node on the plant diagram.
 *
 * Information model
 * ─────────────────
 * • 33 simulated cages across 4 scheduler stacks.
 * • Each cage belongs to a tenant and has a consent tier:
 *     Full         — scheduler telemetry shared; forecast visible; View drill-down
 *     Metered only — only MW draw metered at circuit breaker; no forecast
 * • MW draws are derived deterministically from the live tick's p_compute_mw,
 *   so they always sum to the site IT load GridSignal acts on.
 * • "Tenants reporting" counts cages that have pushed any telemetry this tick.
 *
 * Rollup contract
 * ───────────────
 * GridSignal's commitment decisions use the *consolidated* Site IT draw and
 * Predicted peak numbers shown at the top of this modal.  Individual tenant
 * rows are displayed for operator awareness; the physics engine never acts on
 * per-tenant data directly.
 */

import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import type { TickPayload } from '../types'

// ── Tenant catalogue ──────────────────────────────────────────────────────────
// fractions sum to 1.0; shown[] rows appear in the table; the remainder is
// collapsed into "+ N more cages" at the bottom.

interface TenantDef {
  id:         string
  name:       string
  cage:       string
  scheduler:  string | null          // null → "Not shared"
  tier:       'full' | 'metered'
  frac:       number                 // fraction of total p_compute_mw
  forecastMult: number               // forecast(60s) = draw × forecastMult
}

const SHOWN_TENANTS: TenantDef[] = [
  { id: 'a', name: 'Tenant A', cage: 'Cage 04-B', scheduler: 'Slurm',      tier: 'full',    frac: 0.226, forecastMult: 1.086 },
  { id: 'b', name: 'Tenant B', cage: 'Cage 07-A', scheduler: 'Kubernetes', tier: 'full',    frac: 0.165, forecastMult: 1.088 },
  { id: 'c', name: 'Tenant C', cage: 'Cage 11-C', scheduler: 'Ray',        tier: 'full',    frac: 0.100, forecastMult: 1.098 },
  { id: 'd', name: 'Tenant D', cage: 'Cage 02-A', scheduler: null,         tier: 'metered', frac: 0.136, forecastMult: 0     },
  { id: 'e', name: 'Tenant E', cage: 'Cage 15-B', scheduler: null,         tier: 'metered', frac: 0.078, forecastMult: 0     },
]
// Shown rows cover 70.5 %; remaining 29.5 % belongs to 28 hidden cages
const HIDDEN_CAGE_COUNT = 28
const TOTAL_CAGES       = 33   // 5 shown + 28 hidden
const SCHEDULER_STACKS  = 4
const TENANTS_REPORTING = 21   // demo value

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtMW(mw: number): string {
  return `${mw.toFixed(1)} MW`
}

/** Conservative 60-second forecast multiplier for the hidden cages rollup. */
const HIDDEN_FORECAST_MULT = 1.09

// ── Sub-components ────────────────────────────────────────────────────────────

function StatBox({
  label, value, valueColour,
}: { label: string; value: string; valueColour?: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-muted">{label}</span>
      <span
        className="text-[28px] font-semibold tabular-nums leading-none"
        style={{ color: valueColour ?? '#c8d6e5' }}
      >
        {value}
      </span>
    </div>
  )
}

interface TierPillProps {
  active:   boolean
  label:    string
  count:    number
  onClick:  () => void
}

function TierPill({ active, label, count, onClick }: TierPillProps) {
  return (
    <button
      onClick={onClick}
      className={[
        'px-3 py-1 rounded-full text-xs font-medium transition-colors',
        active
          ? 'bg-accent/20 text-accent border border-accent/40'
          : 'bg-transparent text-muted border border-border hover:border-muted/60 hover:text-text',
      ].join(' ')}
    >
      {label}
      <span className={`ml-1.5 font-mono text-[10px] ${active ? 'text-accent/70' : 'text-muted/60'}`}>
        {count}
      </span>
    </button>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

type FilterTab = 'all' | 'full' | 'metered'

interface Props {
  tick:    TickPayload | null
  onClose: () => void
}

export function ComputeRacksModal({ tick, onClose }: Props) {
  const [tab, setTab] = useState<FilterTab>('all')

  // Esc to close
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  // ── Derive live numbers from tick ─────────────────────────────────────────
  const siteMW      = tick?.p_compute_mw ?? 0
  const peakMult    = 1.28                                       // ~30-min forecast headroom
  const predictedMW = siteMW * peakMult

  const reserveOk   = tick ? !tick.insufficient_reserve_alert : false
  const reserveLabel = tick
    ? (reserveOk ? 'Sufficient' : 'Insufficient')
    : '—'

  // ── Filter rows by tab ────────────────────────────────────────────────────
  const visibleRows = tab === 'all'     ? SHOWN_TENANTS
    : tab === 'full'    ? SHOWN_TENANTS.filter(t => t.tier === 'full')
    : SHOWN_TENANTS.filter(t => t.tier === 'metered')

  const fullCount    = SHOWN_TENANTS.filter(t => t.tier === 'full').length
  const meteredCount = SHOWN_TENANTS.filter(t => t.tier === 'metered').length

  // ── Portal render ─────────────────────────────────────────────────────────
  const modal = (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Compute Racks"
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/70"
      onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        className="relative flex flex-col rounded-xl border border-border bg-surface shadow-2xl
                   overflow-hidden"
        style={{ width: 860, maxWidth: '95vw', maxHeight: '88vh' }}
        onMouseDown={e => e.stopPropagation()}
      >
        {/* Teal accent bar */}
        <div className="absolute inset-x-0 top-0 h-[3px] bg-accent" />

        {/* ── Header ─────────────────────────────────────────────────────── */}
        <div className="flex items-start justify-between px-8 pt-7 pb-5 flex-shrink-0">
          <div>
            <h2 className="text-[28px] font-bold text-text leading-none">Compute racks</h2>
            <p className="text-sm text-muted mt-1.5">
              {TOTAL_CAGES} cages · {SCHEDULER_STACKS} scheduler stacks · facility-wide GPU IT load
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-muted hover:text-text text-2xl leading-none ml-4 mt-1"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {/* ── Hero stats ─────────────────────────────────────────────────── */}
        <div className="px-8 pb-5 flex-shrink-0">
          <div className="grid grid-cols-4 gap-8 py-5 border-y border-border">
            <StatBox label="Site IT draw"    value={tick ? fmtMW(siteMW)      : '—'} />
            <StatBox label="Predicted peak"  value={tick ? fmtMW(predictedMW) : '—'} />
            <StatBox
              label="Reserve cover"
              value={reserveLabel}
              valueColour={!tick ? '#4b5764' : reserveOk ? '#3fb6a8' : '#f85149'}
            />
            <StatBox
              label="Tenants reporting"
              value={tick ? `${TENANTS_REPORTING} / ${TOTAL_CAGES}` : '—'}
            />
          </div>
        </div>

        {/* ── Filter tabs ─────────────────────────────────────────────────── */}
        <div className="px-8 pb-3 flex items-center gap-2 flex-shrink-0">
          <TierPill active={tab === 'all'}     label="All"                   count={TOTAL_CAGES}    onClick={() => setTab('all')} />
          <TierPill active={tab === 'full'}    label="Full telemetry shared" count={fullCount}      onClick={() => setTab('full')} />
          <TierPill active={tab === 'metered'} label="Metered draw only"     count={meteredCount}   onClick={() => setTab('metered')} />
        </div>

        {/* ── Tenant table ─────────────────────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto px-8 pb-6">
          <table className="w-full text-sm border-separate border-spacing-0">
            <thead>
              <tr>
                {['Tenant / cage', 'Scheduler', 'MW draw', 'Forecast (60s)', 'Consent tier', ''].map((h, i) => (
                  <th
                    key={i}
                    className={[
                      'text-left pb-2 pr-4 text-[11px] font-medium uppercase tracking-wider text-muted',
                      'border-b border-border',
                      i === 5 ? 'text-right pr-0' : '',
                    ].join(' ')}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibleRows.map(t => {
                const draw     = siteMW * t.frac
                const forecast = t.tier === 'full' ? draw * t.forecastMult : null

                return (
                  <tr key={t.id} className="group border-b border-border hover:bg-white/[0.025] transition-colors">

                    {/* Tenant / cage */}
                    <td className="py-4 pr-4">
                      <div className="flex items-center gap-1.5">
                        <span className="font-semibold text-text">
                          {t.name}
                        </span>
                        {t.tier === 'metered' && (
                          <span className="text-muted text-[11px]" title="Metered draw only — scheduler not shared">🔒</span>
                        )}
                        <span className="text-muted">·</span>
                        <span className="text-muted font-mono text-xs">{t.cage}</span>
                      </div>
                    </td>

                    {/* Scheduler */}
                    <td className="py-4 pr-4">
                      {t.scheduler ? (
                        <span className="text-text">{t.scheduler}</span>
                      ) : (
                        <span className="text-muted">Not shared</span>
                      )}
                    </td>

                    {/* MW draw */}
                    <td className="py-4 pr-4">
                      <span className="font-mono font-semibold text-text tabular-nums">
                        {tick ? fmtMW(draw) : '—'}
                      </span>
                    </td>

                    {/* Forecast (60s) */}
                    <td className="py-4 pr-4">
                      {forecast !== null && tick ? (
                        <span className="font-mono text-text tabular-nums">{fmtMW(forecast)}</span>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>

                    {/* Consent tier */}
                    <td className="py-4 pr-4">
                      {t.tier === 'full' ? (
                        <span className="text-text">Full</span>
                      ) : (
                        <span className="text-muted">Metered only</span>
                      )}
                    </td>

                    {/* Action */}
                    <td className="py-4 text-right">
                      {t.tier === 'full' ? (
                        <button
                          className="inline-flex items-center gap-1 rounded border border-border
                                     px-3 py-1 text-xs text-muted hover:border-accent hover:text-accent
                                     transition-colors"
                        >
                          View <span>→</span>
                        </button>
                      ) : (
                        <button
                          className="text-xs text-muted hover:text-accent transition-colors"
                          title="View circuit breaker metering data"
                        >
                          Circuit data
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>

          {/* Hidden cages rollup */}
          {(tab === 'all' || tab === 'metered') && (
            <div className="mt-4 flex items-center gap-3">
              <button className="text-sm text-accent hover:underline">
                + {HIDDEN_CAGE_COUNT} more cages
              </button>
              {tick && (
                <span className="text-xs text-muted font-mono">
                  {fmtMW(siteMW * (1 - SHOWN_TENANTS.reduce((s, t) => s + t.frac, 0)))} draw
                  · {fmtMW(siteMW * (1 - SHOWN_TENANTS.reduce((s, t) => s + t.frac, 0)) * HIDDEN_FORECAST_MULT)} forecast
                </span>
              )}
            </div>
          )}

          {/* Rollup explainer */}
          <div className="mt-6 rounded-lg border border-border/50 bg-canvas px-4 py-3 space-y-1">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">Rollup contract</p>
            <p className="text-xs text-muted leading-relaxed">
              GridSignal's turbine commitment and BESS dispatch decisions use the consolidated
              <span className="text-text font-mono mx-1">{tick ? fmtMW(siteMW) : '—'}</span>
              Site IT draw and
              <span className="text-text font-mono mx-1">{tick ? fmtMW(predictedMW) : '—'}</span>
              predicted peak derived from all {TOTAL_CAGES} cages. Per-tenant rows are
              displayed for operator awareness only — the physics engine acts on site-wide
              aggregates, not individual tenant signals.
            </p>
          </div>
        </div>

        {/* ── Footer ─────────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between px-8 py-3 border-t border-border flex-shrink-0">
          <p className="text-[11px] text-muted font-mono">
            {tick
              ? `sim t = ${Math.round(tick.sim_time_seconds)} s · ${TENANTS_REPORTING} / ${TOTAL_CAGES} reporting`
              : 'No active run — start a scenario to see live draw'}
          </p>
          <button
            onClick={onClose}
            className="rounded px-4 py-1.5 text-sm font-semibold text-white transition-colors"
            style={{ background: '#3fb6a8' }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )

  return createPortal(modal, document.body)
}
