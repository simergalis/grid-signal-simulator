/**
 * ComputeRacksModal.tsx — Multi-tenant compute racks detail view.
 *
 * Data flow (bottom-up rollup)
 * ────────────────────────────
 * 1. Each job has a seeded base GPU-node count (looks random, stable across renders).
 * 2. Job MW draw = gpuNodes × GPU_TDP_MW (700 W / H100 SXM5).
 * 3. Tenant total = Σ job draws.  When a live tick is present every job's count is
 *    scaled so the tenant total matches tick.p_compute_mw × tenant.frac exactly.
 * 4. Site IT draw shown in the hero = Σ tenant totals = tick.p_compute_mw (with tick)
 *    or Σ baseline tenant MWs (no tick).
 * 5. GridSignal's turbine/BESS decisions act on the consolidated site total only.
 */

import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import type { TickPayload } from '../types'
import { useGpuGeneratorStore, type AnyJob } from '../store/gpuGeneratorStore'
import { GpuNodeGeneratorModal } from './GpuNodeGeneratorModal'

// ── Tenant catalogue ──────────────────────────────────────────────────────────

interface TenantDef {
  id:           string
  name:         string
  cage:         string
  scheduler:    string | null
  tier:         'full' | 'metered'
  frac:         number        // fraction of total p_compute_mw
  forecastMult: number
}

const SHOWN_TENANTS: TenantDef[] = [
  { id: 'a', name: 'Tenant A', cage: 'Cage 04-B', scheduler: 'Slurm',      tier: 'full',    frac: 0.226, forecastMult: 1.086 },
  { id: 'b', name: 'Tenant B', cage: 'Cage 07-A', scheduler: 'Kubernetes', tier: 'full',    frac: 0.165, forecastMult: 1.088 },
  { id: 'c', name: 'Tenant C', cage: 'Cage 11-C', scheduler: 'Ray',        tier: 'full',    frac: 0.100, forecastMult: 1.098 },
  { id: 'd', name: 'Tenant D', cage: 'Cage 02-A', scheduler: null,         tier: 'metered', frac: 0.136, forecastMult: 0     },
  { id: 'e', name: 'Tenant E', cage: 'Cage 15-B', scheduler: null,         tier: 'metered', frac: 0.078, forecastMult: 0     },
]

const _HIDDEN_FRACS = [
  0.013, 0.011, 0.012, 0.010, 0.009, 0.011, 0.013, 0.010,
  0.011, 0.012, 0.009, 0.010, 0.011, 0.012, 0.010, 0.011,
  0.009, 0.012, 0.010, 0.011, 0.013, 0.010, 0.009, 0.011,
  0.012, 0.010, 0.010, 0.007,
]
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

// Per-GPU TDP: H100 SXM5 ~700 W = 0.0007 MW
const GPU_TDP_MW = 0.0007

// ── Job templates with seeded base GPU counts ─────────────────────────────────
// baseGpus are realistic-looking numbers that sum to a plausible rack draw.
// They stay stable across re-renders; the live tick scales them up/down.

interface JobTemplate {
  name:     string
  priority: 'high' | 'medium' | 'low'
  baseGpus: number   // base node count (no-tick baseline)
}

const JOB_TEMPLATES: Record<string, JobTemplate[]> = {
  a: [
    { name: 'llm-finetune-7B',      priority: 'high',   baseGpus: 512 },
    { name: 'embedding-batch-2048', priority: 'medium', baseGpus: 288 },
    { name: 'eval-harness-run',     priority: 'low',    baseGpus: 176 },
    { name: 'data-preproc-v3',      priority: 'low',    baseGpus:  48 },
  ],
  b: [
    { name: 'inference-serving-prod', priority: 'high',   baseGpus: 384 },
    { name: 'batch-rerank-jobs',      priority: 'medium', baseGpus: 192 },
    { name: 'canary-deploy-test',     priority: 'low',    baseGpus:  64 },
  ],
  c: [
    { name: 'distributed-train-v8', priority: 'high',   baseGpus: 256 },
    { name: 'hyperopt-sweep-64',    priority: 'medium', baseGpus:  88 },
  ],
}

/** Baseline tenant MW computed entirely from base GPU counts. */
function tenantBaseMW(tenantId: string): number {
  const templates = JOB_TEMPLATES[tenantId] ?? []
  return templates.reduce((s, t) => s + t.baseGpus, 0) * GPU_TDP_MW
}

interface Job {
  id:       string
  name:     string
  priority: string
  gpus:     number
  tdpMW:    number
  state:    'RUNNING'
}

/**
 * Derive job list for a full-telemetry tenant.
 *
 * drawMW may be:
 *   • tick.p_compute_mw × tenant.frac   (live run) — jobs scaled so Σ tdpMW = drawMW
 *   • 0 or absent (no run)              — fall back to base GPU counts
 */
function deriveJobs(tenant: TenantDef, drawMW: number): Job[] {
  const templates = JOB_TEMPLATES[tenant.id] ?? []
  const baseTotal = templates.reduce((s, t) => s + t.baseGpus, 0)
  const baseMW    = baseTotal * GPU_TDP_MW
  // Scale factor: stretch/compress base counts to hit actual draw.
  // If no tick or draw is near zero, use scale=1 (show baseline).
  const scale = drawMW > 0.001 && baseMW > 0 ? drawMW / baseMW : 1.0

  return templates.map((tmpl, i) => {
    const gpus  = Math.max(1, Math.round(tmpl.baseGpus * scale))
    const tdpMW = gpus * GPU_TDP_MW
    return {
      id:       `JOB-${tenant.id.toUpperCase()}${String(i + 1).padStart(3, '0')}`,
      name:     tmpl.name,
      priority: tmpl.priority,
      gpus,
      tdpMW,
      state:    'RUNNING',
    }
  })
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtMW(mw: number): string { return `${mw.toFixed(1)} MW` }

const PRIORITY_COLOUR: Record<string, string> = {
  high:   '#3fb6a8',
  medium: '#c8d6e5',
  low:    '#4b5764',
}

// ── Sub-components ────────────────────────────────────────────────────────────

/**
 * InfoTooltip — a small ⓘ badge that reveals a styled card on hover.
 * Written in plain CSS-in-JS (no extra library) so it works in the
 * existing Tailwind + inline-style setup.
 */
function InfoTooltip({ children }: { children: React.ReactNode }) {
  return (
    <span className="relative inline-flex items-center group/tip ml-1.5 cursor-default">
      {/* Badge */}
      <span
        className="inline-flex items-center justify-center rounded-full text-[10px] font-bold leading-none select-none"
        style={{
          width: 14, height: 14,
          background: '#1e2a36',
          border: '1px solid #2e3d4d',
          color: '#5a7a96',
        }}
      >ⓘ</span>

      {/* Card — appears above the badge */}
      <span
        className="pointer-events-none absolute z-[200] hidden group-hover/tip:flex flex-col gap-2
                   rounded-lg border shadow-2xl text-left"
        style={{
          bottom: 'calc(100% + 8px)',
          left: '50%',
          transform: 'translateX(-50%)',
          width: 300,
          background: '#0f1923',
          borderColor: '#2e3d4d',
          padding: '14px 16px',
        }}
      >
        {/* Arrow */}
        <span
          className="absolute"
          style={{
            top: '100%', left: '50%',
            transform: 'translateX(-50%)',
            width: 0, height: 0,
            borderLeft: '7px solid transparent',
            borderRight: '7px solid transparent',
            borderTop: '7px solid #2e3d4d',
          }}
        />
        {children}
      </span>
    </span>
  )
}

function StatBox({ label, value, valueColour, sub }: {
  label: string; value: string; valueColour?: string; sub?: string
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-muted">{label}</span>
      <span className="text-[24px] font-semibold tabular-nums leading-none" style={{ color: valueColour ?? '#c8d6e5' }}>
        {value}
      </span>
      {sub && <span className="text-[10px] text-muted font-mono">{sub}</span>}
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
  tenant, tick, onBack, generatorJobs = [],
}: { tenant: TenantDef; tick: TickPayload | null; onBack: () => void; generatorJobs?: AnyJob[] }) {
  // Actual draw: from tick when live, else derive from base GPU counts
  const siteMW  = tick?.p_compute_mw ?? 0
  const drawMW  = tick ? siteMW * tenant.frac : tenantBaseMW(tenant.id)

  // When the generator is running and has jobs for this tenant, show those.
  // Otherwise fall back to the static template-derived jobs.
  const useGeneratorJobs = generatorJobs.length > 0
  const jobs: Job[] = useGeneratorJobs
    ? generatorJobs.map(j => ({
        id:       j.id,
        name:     j.type === 'slurm' ? (j as any).name
                  : j.type === 'kubernetes' ? (j as any).name
                  : ((j as any).entrypoint?.split(' ')[1] ?? 'ray-job'),
        priority: j.priority,
        gpus:     j.totalGPUs,
        tdpMW:    j.tdpMW,
        state:    (j.status === 'RUNNING' || j.status === 'Running') ? 'RUNNING' : j.status as any,
      }))
    : deriveJobs(tenant, drawMW)
  const totalGPUs    = jobs.reduce((s, j) => s + j.gpus, 0)
  const rolledUpMW   = useGeneratorJobs ? jobs.reduce((s, j) => s + j.tdpMW, 0) : drawMW
  const forecastMW   = rolledUpMW * tenant.forecastMult
  // Seed utilisation from tenant ID so each tenant shows a distinct stable value.
  const _utilSeed    = tenant.id.charCodeAt(0) % 8          // 0-7
  const utilPct      = 91 + _utilSeed                        // 91-98 %, stable per tenant

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Breadcrumb */}
      <div className="px-8 pt-4 pb-3 flex-shrink-0 flex items-center gap-2">
        <button onClick={onBack} className="text-xs text-muted hover:text-accent transition-colors">
          ← GPU Colo Center
        </button>
        <span className="text-muted text-xs">/</span>
        <span className="text-xs text-text font-medium">{tenant.name}</span>
        <span className="text-muted text-xs">·</span>
        <span className="text-xs text-muted font-mono">{tenant.cage}</span>
      </div>

      {/* Tenant hero card */}
      <div className="px-8 pb-4 flex-shrink-0">
        <div className="rounded-lg border border-border/60 bg-canvas px-6 py-4">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h3 className="text-lg font-bold text-text leading-none">{tenant.name}</h3>
              <p className="text-xs text-muted mt-1">{tenant.scheduler} · {tenant.cage} · Full telemetry shared</p>
            </div>
            <span className="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider"
              style={{ background: '#3fb6a822', color: '#3fb6a8', border: '1px solid #3fb6a844' }}>
              reporting
            </span>
          </div>
          <div className="grid grid-cols-4 gap-6">
            {/* IT draw — rolled up from job TDP sum */}
            <StatBox
              label="IT draw"
              value={fmtMW(rolledUpMW)}
              sub={`Σ ${jobs.length} jobs`}
            />
            {/* Forecast */}
            <StatBox
              label="Forecast 60s"
              value={fmtMW(forecastMW)}
              valueColour="#3fb6a8"
            />
            {/* GPU nodes — rolled up from job node sum */}
            <StatBox
              label="GPU nodes"
              value={totalGPUs.toLocaleString()}
              sub={`Σ ${jobs.length} active jobs`}
            />
            {/* Utilisation */}
            <StatBox
              label="Utilisation"
              value={`${utilPct}%`}
            />
          </div>
        </div>
      </div>

      {/* Section label */}
      <div className="px-8 pb-2 flex-shrink-0 flex items-center justify-between">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">Active job queue</p>
        <p className="text-[10px] text-muted font-mono">
          {totalGPUs.toLocaleString()} nodes · {fmtMW(rolledUpMW)} rollup → site IT draw
        </p>
      </div>

      {/* Job table */}
      <div className="flex-1 overflow-y-auto px-8 pb-6">
        <table className="w-full text-sm border-separate border-spacing-0">
          <thead>
            <tr>
              {['Job ID', 'Name', 'Priority', 'GPU nodes', 'Est. draw', 'State'].map((h, i) => (
                <th key={i}
                  className="text-left pb-2 pr-4 text-[11px] font-medium uppercase tracking-wider text-muted border-b border-border">
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
                  <span className="text-xs font-semibold" style={{ color: PRIORITY_COLOUR[job.priority] ?? '#c8d6e5' }}>
                    {job.priority}
                  </span>
                </td>
                {/* GPU nodes — the randomly generated count */}
                <td className="py-3 pr-4 font-mono tabular-nums text-text font-semibold">
                  {job.gpus.toLocaleString()}
                </td>
                {/* Est. draw — derived from GPU nodes × TDP */}
                <td className="py-3 pr-4 font-mono tabular-nums text-muted">
                  {fmtMW(job.tdpMW)}
                </td>
                <td className="py-3">
                  <span className="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider"
                    style={{ background: '#3fb6a822', color: '#3fb6a8' }}>
                    {job.state}
                  </span>
                </td>
              </tr>
            ))}
            {/* Rollup row */}
            <tr className="border-t-2 border-border">
              <td colSpan={3} className="pt-3 pb-1 text-[11px] text-muted uppercase tracking-wider">Tenant total</td>
              <td className="pt-3 pb-1 font-mono tabular-nums font-bold text-text">
                {totalGPUs.toLocaleString()}
              </td>
              <td className="pt-3 pb-1 font-mono tabular-nums font-bold" style={{ color: '#3fb6a8' }}>
                {fmtMW(rolledUpMW)}
              </td>
              <td className="pt-3 pb-1 text-[10px] text-muted">→ site draw</td>
            </tr>
          </tbody>
        </table>

        {/* Data-sharing scope */}
        <div className="mt-5 rounded-lg border border-border/50 bg-canvas px-4 py-3 space-y-1">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">Data-sharing scope</p>
          <p className="text-xs text-muted leading-relaxed">
            {tenant.name} has opted into <span className="text-text font-semibold">full telemetry sharing</span>.
            GridSignal receives scheduler job state, GPU node counts, and 60-second load forecasts from
            this tenant's {tenant.scheduler} stack. This data is used solely for grid dispatch optimisation
            and is never shared with other tenants.
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
  const [generatorOpen,  setGeneratorOpen]  = useState(false)

  // GPU Node Generator store
  const { tenantA: genA, tenantB: genB, tenantC: genC, running: genRunning } =
    useGpuGeneratorStore()

  // Map tenant ID → generator jobs (only full-telemetry tenants match)
  const generatorJobsForTenant = (id: string): AnyJob[] => {
    if (id === 'a') return genA
    if (id === 'b') return genB
    if (id === 'c') return genC
    return []
  }

  // Esc: drill-down → table → close (generator handled by its own modal)
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      if (generatorOpen) return           // let generator modal handle its own Esc
      if (selectedTenant) setSelectedTenant(null)
      else onClose()
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose, selectedTenant, generatorOpen])

  // ── Site-level hero numbers ───────────────────────────────────────────────
  // With a tick: site IT draw comes from tick directly (most accurate).
  // Without a tick: sum baseline MWs of all full-telemetry tenants + fracs of metered ones.
  const ALL_TENANTS = [...SHOWN_TENANTS, ...HIDDEN_TENANTS]
  const siteMW = tick
    ? tick.p_compute_mw
    : (() => {
        // Baseline from full-telemetry tenants
        const fullBase = SHOWN_TENANTS
          .filter(t => t.tier === 'full')
          .reduce((s, t) => s + tenantBaseMW(t.id), 0)
        // Metered tenants: scale their frac relative to full-telemetry total frac
        const fullFrac    = SHOWN_TENANTS.filter(t => t.tier === 'full').reduce((s, t) => s + t.frac, 0)
        const totalFrac   = ALL_TENANTS.reduce((s, t) => s + t.frac, 0)   // ≈ 1.0
        const siteMWEst   = fullFrac > 0 ? fullBase / fullFrac * totalFrac : fullBase
        return siteMWEst
      })()

  const predictedMW  = siteMW * 1.28
  const reserveOk    = tick ? !tick.insufficient_reserve_alert : null
  const reserveLabel = reserveOk === null ? '—' : reserveOk ? 'Sufficient' : 'Insufficient'

  // ── Filter + expand ───────────────────────────────────────────────────────
  const filteredAll = tab === 'full'    ? ALL_TENANTS.filter(t => t.tier === 'full')
    : tab === 'metered' ? ALL_TENANTS.filter(t => t.tier === 'metered')
    : ALL_TENANTS
  const visibleRows    = expanded ? filteredAll : filteredAll.filter(t => SHOWN_TENANTS.includes(t))
  const fullCount      = SHOWN_TENANTS.filter(t => t.tier === 'full').length
  const meteredCount   = ALL_TENANTS.filter(t => t.tier === 'metered').length
  const hiddenFiltered = filteredAll.filter(t => HIDDEN_TENANTS.includes(t))

  // ── Portal render ─────────────────────────────────────────────────────────
  const modal = (
    <div
      role="dialog" aria-modal="true" aria-label="GPU Colo Center"
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/70"
      onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        className="relative flex flex-col rounded-xl border border-border bg-surface shadow-2xl overflow-hidden"
        style={{ width: 860, maxWidth: '95vw', maxHeight: '88vh' }}
        onMouseDown={e => e.stopPropagation()}
      >
        <div className="absolute inset-x-0 top-0 h-[3px] bg-accent" />

        {/* ── Header ─────────────────────────────────────────────────────── */}
        <div className="flex items-start justify-between px-8 pt-7 pb-5 flex-shrink-0">
          <div>
            <h2 className="text-[28px] font-bold text-text leading-none">GPU Colo Center</h2>
            <p className="text-sm text-muted mt-1.5">
              {TOTAL_CAGES} cages · {SCHEDULER_STACKS} scheduler stacks · facility-wide GPU IT load
            </p>
          </div>
          <div className="flex items-center gap-3 ml-4 mt-1">
            {/* GPU Node Generator button */}
            <button
              onClick={() => setGeneratorOpen(true)}
              className="flex items-center gap-1.5 rounded border px-3 py-1.5 text-xs font-semibold transition-colors"
              style={genRunning
                ? { borderColor: '#3fb6a8', color: '#3fb6a8', background: '#3fb6a815' }
                : { borderColor: 'var(--border)', color: 'var(--muted)' }}
              title="Open GPU Node Generator"
            >
              <span>⚡</span>
              <span>GPU Generator</span>
              {genRunning && <span className="ml-0.5 text-[10px] animate-pulse">●</span>}
            </button>
            <button onClick={onClose} className="text-muted hover:text-text text-2xl leading-none" aria-label="Close">×</button>
          </div>
        </div>

        {/* ── Hero stats ─────────────────────────────────────────────────── */}
        <div className="px-8 pb-5 flex-shrink-0">
          <div className="grid grid-cols-4 gap-8 py-5 border-y border-border">
            <StatBox
              label="Site IT draw"
              value={fmtMW(siteMW)}
              sub={tick ? 'live tick' : 'baseline est.'}
            />
            <StatBox
              label="Predicted peak"
              value={fmtMW(predictedMW)}
              sub="30 min horizon"
            />
            <StatBox
              label="Reserve cover"
              value={reserveLabel}
              valueColour={reserveOk === null ? '#4b5764' : reserveOk ? '#3fb6a8' : '#f85149'}
            />
            <StatBox
              label="Tenants reporting"
              value={`${TENANTS_REPORTING} / ${TOTAL_CAGES}`}
            />
          </div>
        </div>

        {/* ── Body ────────────────────────────────────────────────────────── */}
        {selectedTenant ? (
          <TenantDetailPanel
            tenant={selectedTenant}
            tick={tick}
            onBack={() => setSelectedTenant(null)}
            generatorJobs={generatorJobsForTenant(selectedTenant.id)}
          />
        ) : (
          <>
            {/* Filter tabs */}
            <div className="px-8 pb-3 flex items-center gap-2 flex-shrink-0">
              <TierPill active={tab === 'all'}     label="All"                   count={TOTAL_CAGES}  onClick={() => { setTab('all');     setExpanded(true)  }} />
              <TierPill active={tab === 'full'}    label="Full telemetry shared" count={fullCount}    onClick={() => { setTab('full');    setExpanded(false) }} />
              <TierPill active={tab === 'metered'} label="Metered draw only"     count={meteredCount} onClick={() => { setTab('metered'); setExpanded(true)  }} />
            </div>

            {/* Tenant table */}
            <div className="flex-1 overflow-y-auto px-8 pb-6">
              <table className="w-full text-sm border-separate border-spacing-0">
                <thead>
                  <tr>
                    {['Tenant / cage', 'Scheduler', 'MW draw', 'GPU nodes', 'Forecast (60s)', 'Consent tier', ''].map((h, i) => (
                      <th key={i} className={[
                        'text-left pb-2 pr-4 text-[11px] font-medium uppercase tracking-wider text-muted border-b border-border',
                        i === 6 ? 'text-right pr-0' : '',
                      ].join(' ')}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.map(t => {
                    // Per-tenant MW: from job rollup (full) or tick frac (metered)
                    const jobs = t.tier === 'full' ? deriveJobs(t, siteMW * t.frac) : []
                    const tenantMW = t.tier === 'full'
                      ? jobs.reduce((s, j) => s + j.tdpMW, 0)
                      : siteMW * t.frac
                    const forecast = t.tier === 'full' ? tenantMW * t.forecastMult : null
                    // GPU node count: exact from job rollup (full) or estimated from MW (metered)
                    const gpuNodes = t.tier === 'full'
                      ? jobs.reduce((s, j) => s + j.gpus, 0)
                      : Math.round(tenantMW / GPU_TDP_MW)
                    const gpuLabel = tenantMW < 0.0001
                      ? '—'
                      : t.tier === 'full'
                        ? gpuNodes.toLocaleString()
                        : `~${gpuNodes.toLocaleString()}`
                    return (
                      <tr key={t.id} className="group border-b border-border hover:bg-white/[0.025] transition-colors">
                        <td className="py-4 pr-4">
                          <div className="flex items-center gap-1.5">
                            <span className="font-semibold text-text">{t.name}</span>
                            {t.tier === 'metered' && (
                              <span className="text-muted text-[11px]" title="Metered draw only">🔒</span>
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
                          <span className="font-mono font-semibold text-text tabular-nums">{fmtMW(tenantMW)}</span>
                        </td>
                        <td className="py-4 pr-4">
                          <span
                            className="font-mono tabular-nums"
                            style={{ color: t.tier === 'full' ? '#c8d6e5' : '#4b5764' }}
                            title={t.tier === 'metered' ? 'Estimated from circuit MW ÷ 700 W/GPU (H100 TDP). Scheduler data not shared.' : 'Exact count from job rollup'}
                          >
                            {gpuLabel}
                          </span>
                        </td>
                        <td className="py-4 pr-4">
                          {forecast !== null
                            ? <span className="font-mono text-text tabular-nums">{fmtMW(forecast)}</span>
                            : <span className="text-muted">—</span>}
                        </td>
                        <td className="py-4 pr-4">
                          {t.tier === 'full'
                            ? (
                              <span className="inline-flex items-center">
                                <span className="text-text">Full</span>
                                <InfoTooltip>
                                  <span className="text-[11px] font-semibold uppercase tracking-wider"
                                    style={{ color: '#5a7a96' }}>
                                    What is full telemetry sharing?
                                  </span>
                                  <span className="text-xs leading-relaxed" style={{ color: '#8ca8c0' }}>
                                    This tenant has <strong style={{ color: '#c8d6e5' }}>opted in</strong> to
                                    sharing their job queue, GPU node counts, and 60-second load forecasts
                                    directly with GridSignal. Think of it as giving the grid operator a
                                    real-time view into their scheduler — so the system can see a big
                                    job coming <em>before</em> it starts drawing power.
                                  </span>
                                  <span className="text-xs leading-relaxed" style={{ color: '#8ca8c0' }}>
                                    This lets GridSignal pre-position turbines and battery reserves
                                    30–60 seconds earlier than it could from a power meter alone.
                                    Data is used only for grid dispatch and is never shared with
                                    other tenants.
                                  </span>
                                </InfoTooltip>
                              </span>
                            )
                            : (
                              <span className="inline-flex items-center">
                                <span className="text-muted">Metered only</span>
                                <InfoTooltip>
                                  <span className="text-[11px] font-semibold uppercase tracking-wider"
                                    style={{ color: '#5a7a96' }}>
                                    What is circuit metering?
                                  </span>
                                  <span className="text-xs leading-relaxed" style={{ color: '#8ca8c0' }}>
                                    This tenant has agreed to share <strong style={{ color: '#c8d6e5' }}>only
                                    their power meter reading</strong> — the total electricity flowing into
                                    their cage, measured at the circuit breaker. Think of it like a utility
                                    bill: the data centre knows how many kilowatts are being used, but not
                                    what's running inside.
                                  </span>
                                  <span className="text-xs leading-relaxed" style={{ color: '#8ca8c0' }}>
                                    They have <strong style={{ color: '#c8d6e5' }}>not opted in</strong> to
                                    sharing job schedules, GPU node counts, or workload details.
                                    GridSignal still manages the site's total power supply using their
                                    meter reading — it just can't see inside their operation.
                                  </span>
                                  <span className="text-[10px] leading-relaxed" style={{ color: '#4b6375' }}>
                                    The ~ GPU estimate is reverse-engineered from their power draw
                                    (watts ÷ 700 W per H100), not data they have shared.
                                  </span>
                                </InfoTooltip>
                              </span>
                            )}
                        </td>
                        <td className="py-4 text-right">
                          {t.tier === 'full' ? (
                            <button
                              onClick={() => setSelectedTenant(t)}
                              className="inline-flex items-center gap-1 rounded border border-border
                                         px-3 py-1 text-xs text-muted hover:border-accent hover:text-accent
                                         transition-colors"
                            >View <span>→</span></button>
                          ) : (
                            <button className="text-xs text-muted hover:text-accent transition-colors"
                              title="View circuit breaker metering data">Circuit data</button>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>

              {/* Expand hidden */}
              {hiddenFiltered.length > 0 && !expanded && (
                <div className="mt-4 flex items-center gap-3">
                  <button onClick={() => setExpanded(true)}
                    className="text-sm text-accent hover:underline focus:outline-none">
                    + {hiddenFiltered.length} more cages ▾
                  </button>
                  <span className="text-xs text-muted font-mono">
                    {fmtMW(siteMW * hiddenFiltered.reduce((s, t) => s + t.frac, 0))} draw
                    · {fmtMW(siteMW * hiddenFiltered.reduce((s, t) => s + t.frac, 0) * HIDDEN_FORECAST_MULT)} forecast
                  </span>
                </div>
              )}
              {expanded && hiddenFiltered.length > 0 && (
                <div className="mt-2">
                  <button onClick={() => setExpanded(false)}
                    className="text-xs text-muted hover:text-accent transition-colors focus:outline-none">
                    ▴ collapse
                  </button>
                </div>
              )}

              {/* Rollup explainer */}
              <div className="mt-6 rounded-lg border border-border/50 bg-canvas px-4 py-3 space-y-1">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">Rollup contract</p>
                <p className="text-xs text-muted leading-relaxed">
                  Each tenant's GPU node commitments roll up to their cage MW draw.
                  All {TOTAL_CAGES} cage draws sum to the consolidated
                  <span className="text-text font-mono mx-1">{fmtMW(siteMW)}</span>
                  Site IT draw{predictedMW > 0 && <> (predicted peak <span className="text-text font-mono">{fmtMW(predictedMW)}</span>)</>}.
                  GridSignal's turbine commitment and BESS dispatch act on this site total only —
                  per-tenant rows are for operator awareness.
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
              : `baseline est. · ${TENANTS_REPORTING} / ${TOTAL_CAGES} reporting`}
          </p>
          <div className="flex items-center gap-3">
            {selectedTenant && (
              <button
                onClick={() => setSelectedTenant(null)}
                className="rounded px-4 py-1.5 text-sm font-medium text-muted border border-border
                           hover:border-muted/60 hover:text-text transition-colors"
              >← Back</button>
            )}
            <button onClick={onClose}
              className="rounded px-4 py-1.5 text-sm font-semibold text-white transition-colors"
              style={{ background: '#3fb6a8' }}>
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  )

  return (
    <>
      {createPortal(modal, document.body)}
      {generatorOpen && <GpuNodeGeneratorModal onClose={() => setGeneratorOpen(false)} />}
    </>
  )
}
