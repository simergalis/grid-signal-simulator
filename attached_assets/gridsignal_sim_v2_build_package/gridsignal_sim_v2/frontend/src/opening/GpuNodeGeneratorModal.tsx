/**
 * GpuNodeGeneratorModal.tsx — Operator-configurable GPU job generator.
 *
 * Generates Slurm (Tenant A), Kubernetes (Tenant B), and Ray (Tenant C) jobs
 * asynchronously and randomly, driven by the gpuGeneratorStore engine.
 *
 * Natural-language interface
 * ──────────────────────────
 * The STT text box (type or use the mic) sends commands to
 * POST /api/ai/gpu-generator/interpret, which uses Claude to translate
 * plain English into a GeneratorConfig patch.  Example commands:
 *   "focus all large LLM training jobs on Tenant A, burst every 30 seconds"
 *   "steady stream of small jobs across all tenants, 5 per minute"
 *   "heavy kubernetes workload, medium to large jobs, max 20 per tenant"
 */

import { useState, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { queueWaitColour, fmtQueueWait, compareByQueuedSince } from './queueUtils'
import {
  useGpuGeneratorStore,
  DEFAULT_CONFIG,
  type GeneratorConfig,
  type AnyJob,
} from '../store/gpuGeneratorStore'
import { useTickStore } from '../store/tickStore'
import { useScenarioStore } from '../store/scenarioStore'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtMW(mw: number) { return `${mw.toFixed(2)} MW` }
function fmtTime(ms: number) {
  const s = Math.floor((Date.now() - ms) / 1000)
  if (s < 60) return `${s}s ago`
  return `${Math.floor(s / 60)}m ${s % 60}s ago`
}

const TENANT_COLOUR: Record<string, string> = {
  A: '#3fb6a8', B: '#4a9fe0', C: '#9b6fe0',
}
const SCHEDULER_BADGE: Record<string, string> = {
  A: 'Slurm', B: 'Kubernetes', C: 'Ray',
}
// ── Sub-components ────────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[11px] font-semibold uppercase tracking-wider text-muted mb-2">
      {children}
    </p>
  )
}

function Slider({
  label, value, min, max, step = 0.5, unit = '',
  onChange,
}: {
  label: string; value: number; min: number; max: number; step?: number; unit?: string
  onChange: (v: number) => void
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex justify-between text-xs">
        <span className="text-muted">{label}</span>
        <span className="text-text tabular-nums font-mono">{value}{unit}</span>
      </div>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(parseFloat(e.target.value))}
        className="w-full accent-accent h-1.5 rounded cursor-pointer"
      />
    </div>
  )
}

function Toggle({
  label, value, onChange,
}: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!value)}
      className="flex items-center justify-between w-full"
    >
      <span className="text-xs text-muted">{label}</span>
      <div className={`relative w-8 h-4 rounded-full transition-colors ${value ? 'bg-accent' : 'bg-border'}`}>
        <span className={`absolute top-0.5 w-3 h-3 bg-white rounded-full transition-transform ${value ? 'translate-x-4' : 'translate-x-0.5'}`} />
      </div>
    </button>
  )
}

function WeightRow({
  label, value, colour, onChange,
}: { label: string; value: number; colour: string; onChange: (v: number) => void }) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs w-20 shrink-0" style={{ color: colour }}>{label}</span>
      <input
        type="range" min={0} max={1} step={0.05} value={value}
        onChange={e => onChange(parseFloat(e.target.value))}
        className="flex-1 h-1.5 rounded cursor-pointer"
        style={{ accentColor: colour }}
      />
      <span className="text-xs font-mono text-muted w-8 text-right">{Math.round(value * 100)}%</span>
    </div>
  )
}


function ManifestDrawer({ job, onClose }: { job: AnyJob; onClose: () => void }) {
  const manifest = job.type === 'slurm' ? job.manifest
    : job.type === 'kubernetes' ? job.manifest
    : job.manifest
  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/60"
      onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="relative bg-canvas border border-border rounded-xl shadow-2xl"
        style={{ width: 600, maxWidth: '90vw', maxHeight: '70vh' }}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-border">
          <div>
            <span className="text-xs font-semibold text-text">{job.id}</span>
            <span className="text-xs text-muted ml-3">{job.type === 'slurm' ? 'Slurm batch script' : job.type === 'kubernetes' ? 'Kubernetes manifest' : 'Ray submission'}</span>
          </div>
          <button onClick={onClose} className="text-muted hover:text-text text-lg">×</button>
        </div>
        <div className="overflow-y-auto p-5">
          <pre className="text-[11px] text-text font-mono leading-relaxed whitespace-pre-wrap"
            style={{ background: '#0a0e13', padding: '12px', borderRadius: 6 }}>
            {manifest}
          </pre>
        </div>
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  onClose: () => void
  /** When provided, the modal opens directly on this tab (used when navigating
   *  from the Compute tile's "Requeued (cap hold)" row). */
  initialTab?: 'config' | 'jobs' | 'feed' | 'queue'
}

export function GpuNodeGeneratorModal({ onClose, initialTab }: Props) {
  const { config, running, feed, start, stop, reset, updateConfig } =
    useGpuGeneratorStore()
  const latestTick   = useTickStore(s => s.latestTick)
  const selectedSpec = useScenarioStore(s => s.selectedSpec)
  // Both the legacy shared kube_config and heterogeneous kube_clusters paths
  // create scheduler demand agents and eventually emit kube_metrics.
  const usesKubeDemand = (
    selectedSpec?.kube_config != null
    || (selectedSpec?.kube_clusters?.length ?? 0) > 0
  )

  const [nlText,       setNlText]       = useState('')
  const [nlLoading,    setNlLoading]    = useState(false)
  const [nlExplanation, setNlExplanation] = useState<string | null>(null)
  const [activeTab,    setActiveTab]    = useState<'config' | 'jobs' | 'feed' | 'queue'>(initialTab ?? 'config')
  const [previewJob,   setPreviewJob]   = useState<AnyJob | null>(null)
  const [listening,    setListening]    = useState(false)
  const recognitionRef = useRef<any>(null)

  // Esc to close
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape' && !previewJob) onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose, previewJob])

  // Web Speech API
  const startListening = () => {
    const SpeechRecognition = (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition
    if (!SpeechRecognition) return
    const r = new SpeechRecognition()
    r.lang = 'en-US'
    r.continuous = false
    r.interimResults = false
    r.onresult = (e: any) => {
      setNlText(e.results[0][0].transcript)
      setListening(false)
    }
    r.onerror = () => setListening(false)
    r.onend   = () => setListening(false)
    recognitionRef.current = r
    r.start()
    setListening(true)
  }

  const applyNlCommand = async () => {
    if (!nlText.trim()) return
    setNlLoading(true)
    setNlExplanation(null)
    try {
      const res = await fetch('/api/ai/gpu-generator/interpret', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: nlText.trim(), current_config: config }),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      if (data.config) updateConfig(data.config)
      setNlExplanation(data.explanation ?? 'Configuration updated.')
    } catch (err) {
      setNlExplanation(`Error: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setNlLoading(false)
    }
  }

  // Normalise weights so they sum to 1
  const normaliseTenantWeight = (key: 'a' | 'b' | 'c', value: number) => {
    const other = { a: config.tenantWeights.b + config.tenantWeights.c,
                    b: config.tenantWeights.a + config.tenantWeights.c,
                    c: config.tenantWeights.a + config.tenantWeights.b }[key]
    const total = value + (other || 0.001)
    const norm  = { ...config.tenantWeights, [key]: value }
    const scale = 1 / total
    updateConfig({ tenantWeights: { a: norm.a * scale, b: norm.b * scale, c: norm.c * scale } })
  }
  const normaliseJobSize = (key: 'small' | 'medium' | 'large', value: number) => {
    const rest = Object.entries(config.jobSizes)
      .filter(([k]) => k !== key)
      .reduce((s, [, v]) => s + v, 0) || 0.001
    const scale = (1 - value) / rest
    const next  = { ...config.jobSizes, [key]: value }
    for (const k of ['small', 'medium', 'large'] as const) {
      if (k !== key) next[k] = config.jobSizes[k] * scale
    }
    updateConfig({ jobSizes: next })
  }

  // Live job data from the physics engine broadcast (JOBQ-001 Phase B).
  // Source of truth for the Jobs tab; gpuGeneratorStore is for pre-run config only.
  const kube = latestTick?.kube_metrics
  // Distinct states for the two "no kube data yet" situations (Fix 1 — GENRESTART-001).
  // stillConnecting: run is active, scenario uses kube demand, data hasn't arrived yet.
  // notApplicable:   run is active but this scenario has no kube_config at all.
  const stillConnecting = running && !!latestTick && usesKubeDemand && !kube
  const notApplicable   = running && !!latestTick && !usesKubeDemand
  type LiveJobRow = { job: { event_id: string; tenant_id: string; scheduler_type: string; node_count: number; est_draw_mw: number; capacity_unit?: 'node' | 'rack' }; status: 'RUNNING' | 'QUEUED' }
  const allLiveJobs: LiveJobRow[] = [
    ...(kube?.active_jobs_detail ?? []).map(j => ({ job: j, status: 'RUNNING' as const })),
    ...(kube?.pending_jobs        ?? []).map(j => ({ job: j, status: 'QUEUED'  as const })),
  ]
  const liveTotalNodes = (kube?.active_jobs_detail ?? []).reduce((s, j) => s + j.node_count, 0)
  const liveTotalMW    = (kube?.active_jobs_detail ?? []).reduce((s, j) => s + j.est_draw_mw, 0)

  // Scheduler badge styles — per-type colors matching the mockup.
  // K8S=steel-blue, SLURM=lavender, RAY=teal (signal color).
  const SCHEDULER_BADGE_STYLE: Record<string, { bg: string; color: string; label: string }> = {
    SLURM: { bg: 'rgba(192,132,252,0.15)', color: '#D4A8FD', label: 'SLURM' },
    K8S:   { bg: 'rgba(93,157,217,0.15)',  color: '#7FB2E8', label: 'K8S'   },
    RAY:   { bg: 'rgba(93,217,193,0.15)',  color: '#5DD9C1', label: 'RAY'   },
  }
  const TENANT_COLOUR_BY_ID: Record<string, string> = {
    A: '#5B9DD9', B: '#C084FC', C: '#5DD9C1',
  }

  // ── Render ────────────────────────────────────────────────────────────────
  const modal = (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70"
      onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="relative flex flex-col rounded-xl border border-border bg-surface shadow-2xl overflow-hidden"
        style={{ width: 900, maxWidth: '96vw', maxHeight: '90vh' }}
        onMouseDown={e => e.stopPropagation()}>

        {/* Accent bar */}
        <div className="absolute inset-x-0 top-0 h-[3px]"
          style={{ background: 'linear-gradient(90deg, #3fb6a8, #4a9fe0, #9b6fe0)' }} />

        {/* ── Header ────────────────────────────────────────────────────── */}
        <div className="flex items-start justify-between px-8 pt-7 pb-4 flex-shrink-0">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-[26px] font-bold text-text leading-none">GPU Node Generator</h2>
              <span className={`px-2 py-0.5 rounded-full text-[11px] font-semibold uppercase tracking-wider ${running ? 'text-accent bg-accent/15' : 'text-muted bg-border/40'}`}>
                {running ? '● RUNNING' : '○ STOPPED'}
              </span>
            </div>
            <p className="text-sm text-muted mt-1.5">
              Generates Slurm · Kubernetes · Ray jobs asynchronously across tenants
            </p>
          </div>
          <button onClick={onClose} className="text-muted hover:text-text text-2xl leading-none ml-4 mt-1">×</button>
        </div>

        {/* ── NL Command bar ─────────────────────────────────────────────── */}
        <div className="px-8 pb-4 flex-shrink-0">
          <div className="rounded-lg border border-border/60 bg-canvas px-4 py-3">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-muted mb-2">
              Natural language configuration
            </p>
            <div className="flex gap-2">
              <textarea
                value={nlText}
                onChange={e => setNlText(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) applyNlCommand() }}
                placeholder={`e.g. "burst mode, focus on Tenant A large LLM jobs, 5 bursts per minute"\nor "steady stream, even split, small and medium jobs only"`}
                className="flex-1 rounded border border-border bg-surface px-3 py-2 text-sm text-text
                           placeholder:text-muted/50 resize-none focus:outline-none focus:border-accent/60"
                rows={2}
              />
              <div className="flex flex-col gap-1.5">
                <button
                  onClick={startListening}
                  title="Speak a command"
                  className={`w-10 h-10 rounded border flex items-center justify-center text-base transition-colors ${listening ? 'border-accent text-accent animate-pulse' : 'border-border text-muted hover:border-accent/60 hover:text-accent'}`}
                >🎙</button>
                <button
                  onClick={applyNlCommand}
                  disabled={nlLoading || !nlText.trim()}
                  className="flex-1 px-3 py-1 rounded text-sm font-semibold text-white transition-colors disabled:opacity-40"
                  style={{ background: '#3fb6a8' }}
                >
                  {nlLoading ? '…' : 'Apply'}
                </button>
              </div>
            </div>
            {nlExplanation && (
              <p className={`mt-2 text-xs leading-relaxed ${nlExplanation.startsWith('Error') ? 'text-red-400' : 'text-accent'}`}>
                ✓ {nlExplanation}
              </p>
            )}
          </div>
        </div>

        {/* ── Controls + live stats ───────────────────────────────────────── */}
        <div className="px-8 pb-3 flex-shrink-0 flex items-center justify-between gap-4">
          <div className="flex gap-2">
            <button
              onClick={running ? stop : start}
              className="px-5 py-1.5 rounded text-sm font-semibold text-white transition-colors"
              style={{ background: running ? '#f85149' : '#3fb6a8' }}
            >
              {running ? '⏹ Stop' : '▶ Start'}
            </button>
            <button
              onClick={reset}
              className="px-4 py-1.5 rounded text-sm font-medium text-muted border border-border hover:border-muted/60 hover:text-text transition-colors"
            >
              Reset
            </button>
          </div>

          {/* Live stats */}
          <div className="flex items-center gap-6 text-xs font-mono">
            <div>
              <span className="text-muted">Active jobs  </span>
              <span className="text-text font-semibold">{allLiveJobs.filter(({ status }) => status === 'RUNNING').length}</span>
            </div>
            <div>
              <span className="text-muted">GPU nodes  </span>
              <span className="text-text font-semibold">{liveTotalNodes.toLocaleString()}</span>
            </div>
            <div>
              <span className="text-muted">Est. draw  </span>
              <span style={{ color: '#3fb6a8' }} className="font-semibold">{fmtMW(liveTotalMW)}</span>
            </div>
            <div>
              <span className="text-muted">Feed events  </span>
              <span className="text-text">{feed.length}</span>
            </div>
          </div>
        </div>

        {/* ── Tab strip (underline style, matches mockup) ─────────────────── */}
        <div className="flex-shrink-0 border-b border-border/60 px-8">
          <div className="flex gap-0">
            {(['config', 'jobs', 'queue', 'feed'] as const).map(tab => {
              const queueCount = kube?.pending_jobs?.length ?? 0
              const isActive = activeTab === tab
              const isAmberTab = tab === 'queue' && queueCount > 0
              return (
                <button key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`relative flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium transition-colors capitalize
                    border-b-2 -mb-px
                    ${isActive
                      ? isAmberTab
                        ? 'text-[#f0883e] border-[#f0883e]'
                        : 'text-accent border-accent font-semibold'
                      : 'text-muted border-transparent hover:text-text'
                    }`}
                >
                  {tab === 'jobs'  ? `Jobs` :
                   tab === 'feed'  ? `Feed` :
                   tab === 'queue' ? 'Queue' :
                   'Config'}
                  {/* Count badges */}
                  {tab === 'jobs' && allLiveJobs.length > 0 && (
                    <span className="font-mono text-[10px] px-1.5 py-0 rounded-full"
                      style={{ background: 'rgba(255,255,255,0.08)', color: '#7c8794' }}>
                      {allLiveJobs.length}
                    </span>
                  )}
                  {tab === 'feed' && feed.length > 0 && (
                    <span className="font-mono text-[10px] px-1.5 py-0 rounded-full"
                      style={{ background: 'rgba(255,255,255,0.08)', color: '#7c8794' }}>
                      {feed.length}
                    </span>
                  )}
                  {tab === 'queue' && queueCount > 0 && (
                    <span className="font-mono text-[10px] font-semibold px-1.5 py-0 rounded-full"
                      style={{ background: 'rgba(240,136,62,0.15)', color: '#f0883e' }}>
                      {queueCount}
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        </div>

        {/* ── Body ─────────────────────────────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto px-8 pb-6">

          {/* CONFIG tab */}
          {activeTab === 'config' && (
            <div className="grid grid-cols-2 gap-8">
              {/* Left column */}
              <div className="space-y-6">
                <div className="space-y-4">
                  <SectionLabel>Job rate</SectionLabel>
                  <Slider label="Jobs per minute" value={config.ratePerMinute} min={0.5} max={20} step={0.5} unit="/min"
                    onChange={v => updateConfig({ ratePerMinute: v })} />
                  <Toggle label="Burst mode (emit batches instead of steady stream)"
                    value={config.burstMode}
                    onChange={v => updateConfig({ burstMode: v })} />
                  {config.burstMode && (
                    <div className="pl-4 border-l border-border/40 space-y-3 mt-2">
                      <Slider label="Burst size min" value={config.burstSize[0]} min={2} max={20} step={1}
                        onChange={v => updateConfig({ burstSize: [v, Math.max(v, config.burstSize[1])] })} />
                      <Slider label="Burst size max" value={config.burstSize[1]} min={2} max={50} step={1}
                        onChange={v => updateConfig({ burstSize: [Math.min(config.burstSize[0], v), v] })} />
                      <Slider label="Burst interval min (s)" value={config.burstIntervalSeconds[0]} min={10} max={120} step={5} unit="s"
                        onChange={v => updateConfig({ burstIntervalSeconds: [v, Math.max(v, config.burstIntervalSeconds[1])] })} />
                      <Slider label="Burst interval max (s)" value={config.burstIntervalSeconds[1]} min={10} max={300} step={5} unit="s"
                        onChange={v => updateConfig({ burstIntervalSeconds: [Math.min(config.burstIntervalSeconds[0], v), v] })} />
                    </div>
                  )}
                </div>

                <div className="space-y-3">
                  <SectionLabel>Job lifecycle</SectionLabel>
                  <Slider label="Min duration (s)" value={config.jobDurationRange[0]} min={30} max={300} step={10} unit="s"
                    onChange={v => updateConfig({ jobDurationRange: [v, Math.max(v + 30, config.jobDurationRange[1])] })} />
                  <Slider label="Max duration (s)" value={config.jobDurationRange[1]} min={60} max={600} step={10} unit="s"
                    onChange={v => updateConfig({ jobDurationRange: [Math.min(config.jobDurationRange[0], v - 30), v] })} />
                  <Slider label="Max live jobs per tenant" value={config.maxJobsPerTenant} min={3} max={30} step={1}
                    onChange={v => updateConfig({ maxJobsPerTenant: v })} />
                </div>
              </div>

              {/* Right column */}
              <div className="space-y-6">
                <div className="space-y-3">
                  <SectionLabel>Tenant mix (Slurm · K8s · Ray)</SectionLabel>
                  <WeightRow label="Tenant A (Slurm)"      colour={TENANT_COLOUR.A} value={config.tenantWeights.a} onChange={v => normaliseTenantWeight('a', v)} />
                  <WeightRow label="Tenant B (Kubernetes)" colour={TENANT_COLOUR.B} value={config.tenantWeights.b} onChange={v => normaliseTenantWeight('b', v)} />
                  <WeightRow label="Tenant C (Ray)"        colour={TENANT_COLOUR.C} value={config.tenantWeights.c} onChange={v => normaliseTenantWeight('c', v)} />
                  {/* Visual bar */}
                  <div className="flex h-2 rounded-full overflow-hidden mt-1">
                    <div style={{ width: `${config.tenantWeights.a * 100}%`, background: TENANT_COLOUR.A }} />
                    <div style={{ width: `${config.tenantWeights.b * 100}%`, background: TENANT_COLOUR.B }} />
                    <div style={{ width: `${config.tenantWeights.c * 100}%`, background: TENANT_COLOUR.C }} />
                  </div>
                </div>

                <div className="space-y-3">
                  <SectionLabel>Job size distribution</SectionLabel>
                  <div className="text-xs text-muted mb-1">Small: 8–64 GPUs · Medium: 128–512 · Large: 512–2048</div>
                  <WeightRow label="Small"  colour="#4b5764" value={config.jobSizes.small}  onChange={v => normaliseJobSize('small', v)} />
                  <WeightRow label="Medium" colour="#c8d6e5" value={config.jobSizes.medium} onChange={v => normaliseJobSize('medium', v)} />
                  <WeightRow label="Large"  colour="#3fb6a8" value={config.jobSizes.large}  onChange={v => normaliseJobSize('large', v)} />
                  <div className="flex h-2 rounded-full overflow-hidden mt-1">
                    <div style={{ width: `${config.jobSizes.small * 100}%`, background: '#4b5764' }} />
                    <div style={{ width: `${config.jobSizes.medium * 100}%`, background: '#c8d6e5' }} />
                    <div style={{ width: `${config.jobSizes.large * 100}%`, background: '#3fb6a8' }} />
                  </div>
                </div>

                {/* Preset buttons */}
                <div className="space-y-2">
                  <SectionLabel>Presets</SectionLabel>
                  <div className="flex flex-wrap gap-2">
                    {[
                      { label: 'Steady light',     cfg: { ratePerMinute: 1,  burstMode: false, jobSizes: { small: 0.6, medium: 0.35, large: 0.05 } } },
                      { label: 'Mixed steady',      cfg: { ratePerMinute: 3,  burstMode: false, jobSizes: { small: 0.3, medium: 0.5,  large: 0.2  } } },
                      { label: 'LLM burst',         cfg: { ratePerMinute: 8,  burstMode: true,  burstSize: [5, 15] as [number,number], burstIntervalSeconds: [20, 60] as [number,number], jobSizes: { small: 0.05, medium: 0.25, large: 0.70 } } },
                      { label: 'Inference flood',   cfg: { ratePerMinute: 15, burstMode: true,  burstSize: [8, 20] as [number,number], burstIntervalSeconds: [10, 30] as [number,number], jobSizes: { small: 0.5, medium: 0.45, large: 0.05 } } },
                      { label: 'Training ramp',     cfg: { ratePerMinute: 4,  burstMode: false, tenantWeights: { a: 0.60, b: 0.25, c: 0.15 }, jobSizes: { small: 0.1, medium: 0.3, large: 0.6 } } },
                    ].map(p => (
                      <button key={p.label}
                        onClick={() => updateConfig(p.cfg as Partial<GeneratorConfig>)}
                        className="px-3 py-1 rounded border border-border text-xs text-muted hover:border-accent/60 hover:text-accent transition-colors"
                      >
                        {p.label}
                      </button>
                    ))}
                    <button
                      onClick={() => updateConfig(DEFAULT_CONFIG)}
                      className="px-3 py-1 rounded border border-border text-xs text-muted hover:border-muted/60 hover:text-text transition-colors"
                    >
                      Reset defaults
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* JOBS tab — sourced exclusively from physics engine broadcast (JOBQ-001) */}
          {activeTab === 'jobs' && (
            <div>
              {allLiveJobs.length === 0 ? (
                <div className="py-12 text-center text-muted text-sm">
                  {kube
                    ? 'No jobs running or queued this tick.'
                    : stillConnecting
                      ? 'Run restarting to connect generator — jobs will appear shortly.'
                      : notApplicable
                        ? "This scenario doesn't use scheduler-driven demand — Queue tab isn't populated here."
                        : 'Start a run to see live job data here.'}
                </div>
              ) : (
                <table className="w-full text-sm border-separate border-spacing-0">
                  <thead>
                    <tr>
                      {['Scheduler', 'Job ID', 'Units', 'Est. draw', 'Status'].map((h, i) => (
                        <th key={i} className="text-left pb-2 pr-3 text-[11px] font-medium uppercase tracking-wider text-muted border-b border-border">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {allLiveJobs.map(({ job, status }) => {
                      const colour = TENANT_COLOUR_BY_ID[job.tenant_id] ?? '#4b5764'
                      return (
                        <tr key={job.event_id}
                          className="border-b border-border/40 hover:bg-white/[0.025] transition-colors">
                          <td className="py-2 pr-3">
                            <span className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded"
                              style={{ background: colour + '22', color: colour }}>
                              {SCHEDULER_BADGE_STYLE[job.scheduler_type]?.label ?? job.scheduler_type}
                            </span>
                          </td>
                          <td className="py-2 pr-3 font-mono text-xs text-muted max-w-[130px] truncate">{job.event_id}</td>
                          <td className="py-2 pr-3 font-mono text-xs tabular-nums text-text font-semibold">
                            {job.node_count.toLocaleString()} {job.capacity_unit ?? 'node'}{job.node_count === 1 ? '' : 's'}
                          </td>
                          <td className="py-2 pr-3 font-mono text-xs text-muted">{fmtMW(job.est_draw_mw)}</td>
                          <td className="py-2">
                            <span className="text-[10px] font-semibold"
                              style={{ color: status === 'RUNNING' ? '#3fb6a8' : '#4b5764' }}>
                              {status}
                            </span>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                  <tfoot>
                    <tr>
                      <td colSpan={2} className="pt-3 text-[11px] text-muted uppercase tracking-wider">Total (running)</td>
                      <td className="pt-3 font-mono font-bold text-text">{liveTotalNodes.toLocaleString()}</td>
                      <td className="pt-3 font-mono font-bold" style={{ color: '#3fb6a8' }}>{fmtMW(liveTotalMW)}</td>
                      <td />
                    </tr>
                  </tfoot>
                </table>
              )}
            </div>
          )}

          {/* QUEUE tab — jobs held by power-cap, sorted longest-waiting first */}
          {activeTab === 'queue' && (() => {
            const simNow = latestTick?.sim_time_seconds ?? 0
            const sortedQueue = [...(kube?.pending_jobs ?? [])].sort(compareByQueuedSince)
            return (
              <div className="-mx-8 -mt-6">
                {/* Banner bar — styled monospace note matching the mockup */}
                <div className="flex items-center px-8 py-2.5 font-mono text-[11px] border-b border-border/60"
                  style={{ color: '#7c8794', background: 'rgba(255,255,255,0.015)' }}>
                  Jobs held by power-cap — waiting for grid headroom before admission.
                </div>

                {sortedQueue.length === 0 ? (
                  <div className="py-10 text-center font-mono text-xs px-8" style={{ color: '#586170' }}>
                    {kube
                      ? 'No jobs currently held in the power-cap queue.'
                      : 'Start a run to see queued jobs here.'}
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm border-collapse">
                      <thead>
                        <tr>
                          {['Scheduler', 'Job ID', 'Tenant', 'Units', 'Est. draw', 'Queued at', 'Wait', 'Requeued'].map((h, i) => (
                            <th key={i}
                              className="text-left py-2.5 pr-3 font-mono text-[10px] font-semibold uppercase tracking-[0.08em] border-b border-border/60 whitespace-nowrap"
                              style={{ color: '#586170', paddingLeft: i === 0 ? 32 : undefined }}
                            >
                              {h}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {sortedQueue.map(job => {
                          const tenantColour = TENANT_COLOUR_BY_ID[job.tenant_id] ?? '#4b5764'
                          const schedStyle = SCHEDULER_BADGE_STYLE[job.scheduler_type]
                          const wait = simNow - job.queued_since_s
                          const isRequeued = job.requeue_count > 0
                          return (
                            <tr key={job.event_id}
                              className="border-b border-border/40 hover:bg-white/[0.02] transition-colors">
                              {/* Scheduler badge — type-specific color */}
                              <td className="py-2.5 pr-3 pl-8 whitespace-nowrap">
                                <span className="font-mono text-[10px] font-bold tracking-[0.03em] px-1.5 py-0.5 rounded"
                                  style={schedStyle
                                    ? { background: schedStyle.bg, color: schedStyle.color }
                                    : { background: '#4b576422', color: '#4b5764' }}>
                                  {schedStyle?.label ?? job.scheduler_type}
                                </span>
                              </td>
                              {/* Job ID */}
                              <td className="py-2.5 pr-3 font-mono text-xs whitespace-nowrap max-w-[130px] truncate"
                                style={{ color: '#7c8794' }}>
                                {job.event_id}
                              </td>
                              {/* Tenant chip — dot + "Tenant X" label */}
                              <td className="py-2.5 pr-3 whitespace-nowrap">
                                <span className="flex items-center gap-1.5 text-xs font-sans">
                                  <span className="inline-block w-[7px] h-[7px] rounded-full flex-shrink-0"
                                    style={{ background: tenantColour }} />
                                  <span style={{ color: '#e8ecef' }}>Tenant {job.tenant_id}</span>
                                </span>
                              </td>
                              {/* Nodes */}
                              <td className="py-2.5 pr-3 font-mono text-xs tabular-nums font-semibold whitespace-nowrap"
                                style={{ color: '#e8ecef' }}>
                                {job.node_count.toLocaleString()} {job.capacity_unit ?? 'node'}{job.node_count === 1 ? '' : 's'}
                              </td>
                              {/* Est. draw */}
                              <td className="py-2.5 pr-3 font-mono text-xs tabular-nums whitespace-nowrap"
                                style={{ color: '#7c8794' }}>
                                {fmtMW(job.est_draw_mw)}
                              </td>
                              {/* Queued at (sim tick time) */}
                              <td className="py-2.5 pr-3 font-mono text-xs tabular-nums whitespace-nowrap"
                                style={{ color: '#7c8794' }}>
                                t={job.queued_since_s.toFixed(0)}s
                              </td>
                              {/* Wait — color-coded */}
                              <td className="py-2.5 pr-3 font-mono text-xs tabular-nums font-semibold whitespace-nowrap"
                                style={{ color: queueWaitColour(wait) }}>
                                {fmtQueueWait(wait)}
                              </td>
                              {/* Requeued count */}
                              <td className="py-2.5 font-mono text-xs tabular-nums whitespace-nowrap">
                                {isRequeued
                                  ? <span style={{ color: '#f0883e', fontWeight: 600 }}>×{job.requeue_count}</span>
                                  : <span style={{ color: '#586170' }}>—</span>}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )
          })()}

          {/* FEED tab */}
          {activeTab === 'feed' && (
            <div>
              {feed.length === 0 ? (
                <div className="py-12 text-center text-muted text-sm">
                  {running ? 'Waiting for first job submission…' : 'Start the generator to see the event feed.'}
                </div>
              ) : (
                <div className="space-y-1">
                  {feed.map(entry => (
                    <div key={entry.id} className="flex items-center gap-3 py-1.5 border-b border-border/30 text-xs">
                      <span className="font-mono text-muted w-16 shrink-0">{fmtTime(entry.ts)}</span>
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase shrink-0"
                        style={{ background: TENANT_COLOUR[entry.tenant] + '22', color: TENANT_COLOUR[entry.tenant] }}>
                        {SCHEDULER_BADGE[entry.tenant]}
                      </span>
                      <span className={`text-[10px] font-semibold w-20 shrink-0 ${entry.action === 'SUBMITTED' ? 'text-muted' : entry.action === 'RUNNING' ? 'text-accent' : 'text-muted/50'}`}>
                        {entry.action}
                      </span>
                      <span className="font-mono text-muted shrink-0">{entry.jobId}</span>
                      <span className="text-text flex-1 truncate">{entry.jobName}</span>
                      <span className="font-mono text-muted shrink-0">{entry.gpus.toLocaleString()} GPUs</span>
                      <span className="font-mono shrink-0" style={{ color: '#3fb6a8' }}>{fmtMW(entry.tdpMW)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Footer ─────────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between px-8 py-3 border-t border-border flex-shrink-0">
          <p className="text-[11px] text-muted font-mono">
            {kube
              ? `Live run · ${kube.active_jobs} running · ${kube.queued_jobs} queued`
              : stillConnecting
                ? 'Reconnecting — run restarting to wire generator into backend…'
                : notApplicable
                  ? "This scenario doesn't use scheduler-driven demand — Queue tab isn't populated here."
                  : running
                    ? 'Generator active — start a run to see live job data'
                    : 'Generator stopped'}
          </p>
          <button onClick={onClose}
            className="rounded px-4 py-1.5 text-sm font-semibold text-white transition-colors"
            style={{ background: '#3fb6a8' }}>
            Close
          </button>
        </div>
      </div>

      {/* Manifest drawer */}
      {previewJob && <ManifestDrawer job={previewJob} onClose={() => setPreviewJob(null)} />}
    </div>
  )

  return createPortal(modal, document.body)
}
