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
 *
 * Drill-down (View →)
 * ───────────────────
 * Full-telemetry tenants expose a per-tenant panel showing live MW draw,
 * 60-second forecast, active job queue, and GPU utilisation.  Job counts are
 * derived deterministically from the live tick so they move with the workload.
 */

import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import type { TickPayload } from '../types'

// ── Tenant catalogue ──────────────────────────────────────────────────────────

interface TenantDef {
  id:           string
  name:         string
  cage:         string
  scheduler:    string | null   // null → "Not shared"
  tier:         'full' | 'metered'
  frac:         number           // fraction of total p_compute_mw
  forecastMult: number           // forecast(60s) = draw × forecastMult
}

const SHOWN_TENANTS: TenantDef[] = [
  { id: 'a', name: 'Tenant A', cage: 'Cage 04-B', scheduler: 'Slurm',      tier: 'full',    frac: 0.226, forecastMult: 1.086 },
  { id: 'b', name: 'Tenant B', cage: 'Cage 07-A', scheduler: 'Kubernetes', tier: 'full',    frac: 0.165, forecastMult: 1.088 },
  { id: 'c', name: 'Tenant C', cage: 'Cage 11-C', scheduler: 'Ray',        tier: 'full',    frac: 0.100, forecastMult: 1.098 },
  { id: 'd', name: 'Tenant D', cage: 'Cage 02-A', scheduler: null,         tier: 'metered', frac: 0.136, forecastMult: 0     },
  { id: 'e', name: 'Tenant E', cage: 'Cage 15-B', scheduler: null,         tier: 'metered', frac: 0.078, forecastMult: 0     },
]

// Shown rows cover 70.5 %; remaining 29.5 % spread across 28 hidden metered cages.
const _HIDDEN_FRACS = [
  0.013, 0.011, 0.012, 0.010, 0.009, 0.011, 0.013, 0.010,
  0.011, 0.012, 0.009, 0.010, 0.011, 0.012, 0.010, 0.011,
  0.009, 0.012, 0.010, 0.011, 0.013, 0.010, 0.009, 0.011,
  0.012, 0.010, 0.010, 0.007,
] // sum = 0.295
const _CAGE_IDS = [
  '01-A','03-B','05-A','06-C','08-A','08-B','09-A','10-B',
  '12-A','12-C','13-A','13-B','14-A','14-C','16-A','17-B',
  '18-A','19-C','20-A','21-B','22-A','23-C','24-A','25-B',
  '26-A','27-C','28-A','29-B',
]
const HIDDEN_TENANTS: TenantDef[] = _HIDDEN_FRACS.map((frac, i) => ({
  id:           `h${i}`,
  name:         `Tenant ${String.fromCharCode(70 + Math.floor(i / 4))}${i % 4 === 0 ? '' : (i % 4).toString()}`,
  cage:         `Cage ${_CAGE_IDS[i]}`,
  scheduler:    null,
  tier:         'metered',
  frac,
  forecastMult: 0,
}))

const TOTAL_CAGES       = 33
const SCHEDULER_STACKS  = 4
const TENANTS_REPORTING = 21
const HIDDEN_FORECAST_MULT = 1.09

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtMW(mw: number): string { return `${mw.toFixed(1)} MW` }

// Per-GPU TDP assumed for node-count estimation (H100 SXM5 ~700 W peak).
const GPU_TDP_MW = 0.0007

// Deterministic job templates per tenant (stable across ticks).
const JOB_TEMPLATES: Record<string, { name: string; priority: string; gpuFrac: number }[]> = {
  a: [
    { name: 'llm-finetune-7B',      priority: 'high',   gpuFrac: 0.48 },
    { name: 'embedding-batch-2048', priority: 'medium', gpuFrac: 0.27 },
    { name: 'eval-harness-run',     priority: 'low',    gpuFrac: 0.18 },
    { name: 'data-preproc-v3',      priority: 'low',    gpuFrac: 0.07 },
  ],
  b: [
    { name: 'inference-serving-prod',  priority: 'high',   gpuFrac: 0.62 },
    { name: 'batch-rerank-jobs',       priority: 'medium', gpuFrac: 0.25 },
    { name: 'canary-deployment-test',  priority: 'low',    gpuFrac: 0.13 },
  ],
  c: [
    { name: 'distributed-train-v8',    priority: 'high',   gpuFrac: 0.71 },
    { name: 'hyperopt-sweep-64',       priority: 'medium', gpuFrac: 0.29 },
  ],
}

const PRIORITY_COLOUR: Record<string, string> = {
  high:   '#3fb6a8',
  medium: '#c8d6e5',
  low:    '#4b5764',
}

/** Derive simulated jobs from the live tick draw for a given tenant. */
function deriveJobs(tenant: TenantDef, drawMW: number) {
  const templates = JOB_TEMPLATES[tenant.id] ?? []
  const totalGPUs = Math.max(1, Math.round(drawMW / GPU_TDP_MW))
  return templates.map((tmpl, i) => {
    const gpus = Math.max(1, Math.round(totalGPUs * tmpl.gpuFrac))
    return {
      id:       `JOB-${tenant.id.toUpperCase()}${String(i + 1).padStart(3, '0')}`,
      name:     tmpl.name,
      priority: tmpl.priority,
      gpus,
      tdpMW:    gpus * GPU_TDP_MW,
      state:    'RUNNING' as const,
    }
  })
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatBox({ label, value, valueColour }: { label: string; value: string; valueColour?: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-muted">{label}</span>
      <span className="text-[28px] font-semibold tabular-nums leading-none" style={{ color: valueColour ?? '#c8d6e5' }}>
        {value}
      </span>
    </div>
  )
}

interface TierPillProps { active: boolean; label: string; count: number; onClick: () => void }
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
      <span className={`ml-1.5 font-mono text-[10px] ${active ? 'text-accent/70' : 'text-muted/60'}`}>{count}</span>
    </button>
  )
}

// ── Tenant detail drill-down ──────────────────────────────────────────────────

function TenantDetailPanel({
  tenant,
  tick,
  onBack,
}: { tenant: TenantDef; tick: TickPayload | null; onBack: () => void }) {
  const siteMW   = tick?.p_compute_mw ?? 0
  const drawMW   = siteMW * tenant.frac
  const forecastMW = drawMW * tenant.forecastMult
  const jobs     = deriveJobs(tenant, drawMW)
  const totalGPUs = Math.max(1, Math.round(drawMW / GPU_TDP_MW))
  const utilPct  = tick ? Math.min(99, Math.round((drawMW / (drawMW * 1.05)) * 100)) : null

  return (
    <div className="flex flex-col h-full">
      {/* Breadcrumb */}
      <div className="px-8 pt-5 pb-3 flex-shrink-0 flex items-center gap-2">
        <button
          onClick={onBack}
          className="text-xs text-muted hover:text-accent transition-colors flex items-center gap-1"
        >
          ← Compute racks
        </button>
        <span className="text-muted text-xs">/</span>
        <span className="text-xs text-text font-medium">{tenant.name}</span>
        <span className="text-muted text-xs">·</span>
        <span className="text-xs text-muted font-mono">{tenant.cage}</span>
      </div>

      {/* Tenant hero */}
      <div className="px-8 pb-5 flex-shrink-0">
        <div className="rounded-lg border border-border/60 bg-canvas px-6 py-4">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h3 className="text-lg font-bold text-text leading-none">{tenant.name}</h3>
              <p className="text-xs text-muted mt-1">
                {tenant.scheduler} · {tenant.cage} · Full telemetry shared
              </p>
            </div>
            <span
              className="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider"
              style={{ background: '#3fb6a8' + '22', color: '#3fb6a8', border: '1px solid #3fb6a8' + '44' }}
            >
              reporting
            </span>
          </div>
          <div className="grid grid-cols-4 gap-6">
            <div className="flex flex-col gap-1">
              <span className="text-[11px] text-muted uppercase tracking-wider">IT draw</span>
              <span className="text-xl font-semibold tabular-nums text-text">{tick ? fmtMW(drawMW) : '—'}</span>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-[11px] text-muted uppercase tracking-wider">Forecast 60s</span>
              <span className="text-xl font-semibold tabular-nums" style={{ color: '#3fb6a8' }}>
                {tick ? fmtMW(forecastMW) : '—'}
              </span>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-[11px] text-muted uppercase tracking-wider">GPU nodes</span>
              <span className="text-xl font-semibold tabular-nums text-text">{tick ? totalGPUs.toLocaleString() : '—'}</span>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-[11px] text-muted uppercase tracking-wider">Utilisation</span>
              <span className="text-xl font-semibold tabular-nums text-text">{utilPct !== null ? `${utilPct}%` : '—'}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Job queue */}
      <div className="px-8 flex-shrink-0 mb-1">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted mb-2">Active job queue</p>
      </div>
      <div className="flex-1 overflow-y-auto px-8 pb-6">
        <table className="w-full text-sm border-separate border-spacing-0">
          <thead>
            <tr>
              {['Job ID', 'Name', 'Priority', 'GPU nodes', 'Est. draw', 'State'].map((h, i) => (
                <th
                  key={i}
                  className="text-left pb-2 pr-4 text-[11px] font-medium uppercase tracking-wider text-muted border-b border-border"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {jobs.map(job => (
              <tr key={job.id} className="border-b border-border hover:bg-white/[0.025] transition-colors">
                <td className="py-3 pr-4 font-mono text-xs text-muted">{job.id}</td>
                <td className="py-3 pr-4 font-medium text-text">{job.name}</td>
                <td className="py-3 pr-4">
                  <span
                    className="text-xs font-semibold"
                    style={{ color: PRIORITY_COLOUR[job.priority] ?? '#c8d6e5' }}
                  >
                    {job.priority}
                  </span>
                </td>
                <td className="py-3 pr-4 font-mono tabular-nums text-text">
                  {tick ? job.gpus.toLocaleString() : '—'}
                </td>
                <td className="py-3 pr-4 font-mono tabular-nums text-muted">
                  {tick ? fmtMW(job.tdpMW) : '—'}
                </td>
                <td className="py-3">
                  <span
                    className="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider"
                    style={{ background: '#3fb6a822', color: '#3fb6a8' }}
                  >
                    {job.state}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Consent scope reminder */}
        <div className="mt-6 rounded-lg border border-border/50 bg-canvas px-4 py-3 space-y-1">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">Data-sharing scope</p>
          <p className="text-xs text-muted leading-relaxed">
            {tenant.name} has opted into <span className="text-text">full telemetry sharing</span>. GridSignal
            receives scheduler job state, GPU node counts, and 60-second load forecasts from this tenant's
            {' '}{tenant.scheduler} stack. This data is used solely for grid dispatch optimisation and is never
            shared with other tenants.
          </p>
        </div>
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

type FilterTab = 'all' | 'full' | 'metered'

interface Props {
  tick:    TickPayload | null
  onClose: () => void
}

export function ComputeRacksModal({ tick, onClose }: Props) {
  const [tab,            setTab]            = useState<FilterTab>('all')
  const [expanded,       setExpanded]       = useState(false)
  const [selectedTenant, setSelectedTenant] = useState<TenantDef | null>(null)

  // Esc: go back to table first, then close modal.
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      if (selectedTenant) { setSelectedTenant(null) } else { onClose() }
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose, selectedTenant])

  // ── Live numbers ─────────────────────────────────────────────────────────
  const siteMW      = tick?.p_compute_mw ?? 0
  const predictedMW = siteMW * 1.28
  const reserveOk   = tick ? !tick.insufficient_reserve_alert : false
  const reserveLabel = tick ? (reserveOk ? 'Sufficient' : 'Insufficient') : '—'

  // ── Filter + expand ───────────────────────────────────────────────────────
  const ALL_TENANTS  = [...SHOWN_TENANTS, ...HIDDEN_TENANTS]
  const filteredAll  = tab === 'full'    ? ALL_TENANTS.filter(t => t.tier === 'full')
    : tab === 'metered' ? ALL_TENANTS.filter(t => t.tier === 'metered')
    : ALL_TENANTS
  const visibleRows  = expanded
    ? filteredAll
    : filteredAll.filter(t => SHOWN_TENANTS.includes(t))
  const fullCount    = SHOWN_TENANTS.filter(t => t.tier === 'full').length
  const meteredCount = ALL_TENANTS.filter(t => t.tier === 'metered').length
  const hiddenFiltered = filteredAll.filter(t => HIDDEN_TENANTS.includes(t))

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
        className="relative flex flex-col rounded-xl border border-border bg-surface shadow-2xl overflow-hidden"
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

        {/* ── Body: table view OR tenant drill-down ───────────────────────── */}
        {selectedTenant ? (
          // ── Tenant detail panel ─────────────────────────────────────────
          <TenantDetailPanel
            tenant={selectedTenant}
            tick={tick}
            onBack={() => setSelectedTenant(null)}
          />
        ) : (
          <>
            {/* ── Filter tabs ─────────────────────────────────────────────── */}
            <div className="px-8 pb-3 flex items-center gap-2 flex-shrink-0">
              <TierPill active={tab === 'all'}     label="All"                   count={TOTAL_CAGES}  onClick={() => { setTab('all');     setExpanded(true)  }} />
              <TierPill active={tab === 'full'}    label="Full telemetry shared" count={fullCount}    onClick={() => { setTab('full');    setExpanded(false) }} />
              <TierPill active={tab === 'metered'} label="Metered draw only"     count={meteredCount} onClick={() => { setTab('metered'); setExpanded(true)  }} />
            </div>

            {/* ── Tenant table ─────────────────────────────────────────────── */}
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
                        <td className="py-4 pr-4">
                          <div className="flex items-center gap-1.5">
                            <span className="font-semibold text-text">{t.name}</span>
                            {t.tier === 'metered' && (
                              <span className="text-muted text-[11px]" title="Metered draw only — scheduler not shared">🔒</span>
                            )}
                            <span className="text-muted">·</span>
                            <span className="text-muted font-mono text-xs">{t.cage}</span>
                          </div>
                        </td>
                        <td className="py-4 pr-4">
                          {t.scheduler
                            ? <span className="text-text">{t.scheduler}</span>
                            : <span className="text-muted">Not shared</span>}
                        </td>
                        <td className="py-4 pr-4">
                          <span className="font-mono font-semibold text-text tabular-nums">
                            {tick ? fmtMW(draw) : '—'}
                          </span>
                        </td>
                        <td className="py-4 pr-4">
                          {forecast !== null && tick
                            ? <span className="font-mono text-text tabular-nums">{fmtMW(forecast)}</span>
                            : <span className="text-muted">—</span>}
                        </td>
                        <td className="py-4 pr-4">
                          {t.tier === 'full'
                            ? <span className="text-text">Full</span>
                            : <span className="text-muted">Metered only</span>}
                        </td>
                        <td className="py-4 text-right">
                          {t.tier === 'full' ? (
                            <button
                              onClick={() => setSelectedTenant(t)}
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

              {/* Hidden cages rollup / expand toggle */}
              {hiddenFiltered.length > 0 && !expanded && (
                <div className="mt-4 flex items-center gap-3">
                  <button
                    onClick={() => setExpanded(true)}
                    className="text-sm text-accent hover:underline focus:outline-none"
                  >
                    + {hiddenFiltered.length} more cages ▾
                  </button>
                  {tick && (
                    <span className="text-xs text-muted font-mono">
                      {fmtMW(siteMW * hiddenFiltered.reduce((s, t) => s + t.frac, 0))} draw
                      · {fmtMW(siteMW * hiddenFiltered.reduce((s, t) => s + t.frac, 0) * HIDDEN_FORECAST_MULT)} forecast
                    </span>
                  )}
                </div>
              )}
              {expanded && hiddenFiltered.length > 0 && (
                <div className="mt-2">
                  <button
                    onClick={() => setExpanded(false)}
                    className="text-xs text-muted hover:text-accent transition-colors focus:outline-none"
                  >
                    ▴ collapse
                  </button>
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
          </>
        )}

        {/* ── Footer ─────────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between px-8 py-3 border-t border-border flex-shrink-0">
          <p className="text-[11px] text-muted font-mono">
            {tick
              ? `sim t = ${Math.round(tick.sim_time_seconds)} s · ${TENANTS_REPORTING} / ${TOTAL_CAGES} reporting`
              : 'No active run — start a scenario to see live draw'}
          </p>
          <div className="flex items-center gap-3">
            {selectedTenant && (
              <button
                onClick={() => setSelectedTenant(null)}
                className="rounded px-4 py-1.5 text-sm font-medium text-muted border border-border
                           hover:border-muted/60 hover:text-text transition-colors"
              >
                ← Back
              </button>
            )}
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
    </div>
  )

  return createPortal(modal, document.body)
}
