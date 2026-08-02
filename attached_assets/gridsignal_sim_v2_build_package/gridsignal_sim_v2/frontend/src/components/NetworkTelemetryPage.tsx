/**
 * NetworkTelemetryPage — §19.9 Network Telemetry console.
 *
 * Phase 10 rebuild: three sections driven by FabricModel tick data.
 *
 * 1. Per-link utilisation heat strip — one row per fabric; the hotspot is
 *    the point. An aggregate hides it.
 * 2. Phase-annotated compute/storage throughput — checkpoint and weight-load
 *    bands shaded so the storage elephant rising during compute quiescence
 *    is visible.
 * 3. Control-latency decomposition — four terms against the 2000 ms budget,
 *    with the dominant term named and NFR-2 breaches highlighted.
 *
 * Legacy sections (corroboration record, quarantine log) are preserved below
 * the new content for runs that also have network-telemetry ingestor data.
 *
 * Read-only by design, not by omission (§25.1, TC-74).
 */
import { useState, useEffect, useRef } from 'react'
import type { FabricModalView, FabricControlPath, FabricDiscrimination } from '../types'
import { useTickStore } from '../store/tickStore'

// ---------------------------------------------------------------------------
// Legacy types (mirroring core/network_telemetry.py wire shapes)
// ---------------------------------------------------------------------------

type ClockDiscipline     = 'ptp' | 'ntp'
type CapabilityTier      = 'baseline' | 'enhanced'
type CorroborationResult = 'pending' | 'corroborated' | 'missed' | 'authoritative_start'

interface SwitchRow {
  switch_id:            string
  interface_id:         string
  throughput_rx_mbps:   number
  throughput_tx_mbps:   number
  optical_power_tx_dbm: number
  optical_power_rx_dbm: number
  clock_discipline:     ClockDiscipline
  effective_discipline: ClockDiscipline
  observed_skew_ms:     number
  error_count:          number
  sample_time_s:        number
}

interface CorroborationRow {
  job_id:                   string
  predicted_start_sim_time: number
  result:                   CorroborationResult
  authoritative_event:      string | null
  fabric_rise_observed:     boolean
  fabric_rise_sim_time:     number | null
}

interface QuarantineRow {
  event_id:  string
  reason:    string
  sim_time:  number
}

interface LegacyTelemetryState {
  capability:    CapabilityTier
  switches:      SwitchRow[]
  corroboration: CorroborationRow[]
  quarantine:    QuarantineRow[]
  last_updated_s: number
}

function _emptyLegacy(): LegacyTelemetryState {
  return { capability: 'baseline', switches: [], corroboration: [], quarantine: [], last_updated_s: 0 }
}

// ---------------------------------------------------------------------------
// Fabric history point
// ---------------------------------------------------------------------------

interface FabricHistoryPoint {
  sim_time_s: number
  phase: string
  mean_u_compute: number
  mean_u_storage: number
  max_u_storage: number
  latency_ms: number
  congested_links: number
}

const MAX_HISTORY = 120

// ---------------------------------------------------------------------------
// Sub-components — Phase 10
// ---------------------------------------------------------------------------

function fmtMs(ms: number | undefined | null): string {
  if (ms == null) return '—'
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)} s`
  return `${ms.toFixed(1)} ms`
}

// Link utilisation heat strip
function HeatStrip({ fabricId, entries }: { fabricId: string; entries: Array<{ id: string; u: number }> }) {
  const COLOURS: Record<string, string> = {
    compute:  '#4a9fe0',
    storage:  '#e0a84a',
    frontend: '#4ae0a8',
  }
  const colour = COLOURS[fabricId] ?? '#888'
  const maxU = Math.max(...entries.map(e => e.u), 0.01)

  return (
    <div>
      <div className="flex items-center gap-2 mb-1">
        <span className="font-mono text-[10px] text-text-muted uppercase w-16">{fabricId}</span>
        <span className="text-[10px] text-text-muted">{entries.length} links</span>
        <span className="text-[10px] text-text-muted ml-auto">
          max u = {(maxU * 100).toFixed(1)}%
        </span>
      </div>
      <div className="flex gap-px h-5 overflow-hidden rounded bg-zinc-900">
        {entries.map(({ id, u }) => {
          const opacity = Math.max(0.06, u / maxU)
          const isHot = u >= 0.85
          return (
            <div
              key={id}
              className="flex-1 h-full cursor-default"
              style={{
                backgroundColor: isHot ? '#e05050' : colour,
                opacity,
              }}
              title={`${id}: u = ${(u * 100).toFixed(1)}%${isHot ? ' ⚠ congested' : ''}`}
            />
          )
        })}
      </div>
      {maxU >= 0.85 && (
        <p className="text-[10px] text-red-400 mt-0.5">
          ⚠ ECMP hotspot — {entries.filter(e => e.u >= 0.85).length} link(s) at ≥ 85%
        </p>
      )}
    </div>
  )
}

// Control-latency bar against budget
function LatencyBar({ cp }: { cp: FabricControlPath | undefined }) {
  if (!cp) return <p className="text-xs text-text-muted">No control-path data yet.</p>

  const TERMS: Array<{ key: keyof FabricControlPath; label: string; colour: string }> = [
    { key: 'l_fabric_ms',     label: 'Fabric',      colour: '#4a9fe0' },
    { key: 'l_gateway_ms',    label: 'Gateway',     colour: '#e0a84a' },
    { key: 'l_retransmit_ms', label: 'Retransmit',  colour: '#e05050' },
    { key: 'l_asset_ack_ms',  label: 'Asset ack',   colour: '#4ae0a8' },
  ]
  const budget = cp.budget_ms || 2000
  const total  = cp.l_fabric_ms + cp.l_gateway_ms + cp.l_retransmit_ms + cp.l_asset_ack_ms

  return (
    <div className="space-y-2">
      {/* Stacked bar */}
      <div className="relative h-4 bg-zinc-900 rounded overflow-hidden">
        {(() => {
          let left = 0
          return TERMS.map(t => {
            const val = (cp[t.key] as number) || 0
            const w = Math.min(100, (val / budget) * 100)
            const el = (
              <div
                key={t.key}
                className="absolute top-0 h-full"
                style={{
                  left:  `${left}%`,
                  width: `${w}%`,
                  backgroundColor: t.colour,
                  opacity: t.label === cp.dominant_term ? 1.0 : 0.55,
                }}
                title={`${t.label}: ${fmtMs(val)}`}
              />
            )
            left += w
            return el
          })
        })()}
        {/* Budget marker at 100% */}
        <div className="absolute right-0 top-0 w-px h-full bg-white/30" />
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {TERMS.map(t => {
          const val = (cp[t.key] as number) || 0
          const isDominant = t.key === `l_${cp.dominant_term}_ms`
          return (
            <span key={t.key} className="flex items-center gap-1 text-xs">
              <span className="w-2 h-2 rounded-sm flex-shrink-0" style={{ backgroundColor: t.colour }} />
              <span className={isDominant ? 'text-text font-medium' : 'text-text-muted'}>
                {t.label}
              </span>
              <span className="text-text-muted">{fmtMs(val)}</span>
            </span>
          )
        })}
        <span className="text-xs text-text-muted ml-auto">
          Total: <span className={cp.breached ? 'text-red-400 font-medium' : 'text-text'}>
            {fmtMs(total)}
          </span>
          <span className="text-text-muted"> / {fmtMs(budget)}</span>
        </span>
      </div>

      {cp.breached && (
        <div className="rounded border border-red-700/50 bg-red-900/20 px-2 py-1.5">
          <p className="text-xs text-red-300">
            <strong>NFR-2 breach</strong> — control latency exceeds {fmtMs(budget)}.
            Dominant term: <strong>{cp.dominant_term}</strong>.
            A {cp.dominant_term === 'gateway' ? 'congested protocol gateway' :
               cp.dominant_term === 'retransmit' ? 'retransmission cascade' :
               'fabric transit congestion'} is delaying staging commands.
          </p>
        </div>
      )}
    </div>
  )
}

// Throughput / discrimination history chart
function DiscriminationPanel({ history }: { history: FabricHistoryPoint[] }) {
  if (history.length === 0) {
    return <p className="text-xs text-text-muted py-2">Waiting for fabric ticks…</p>
  }

  const h = 60  // chart height in px
  const w = history.length

  // Compute SVG paths
  const computePoints = history.map((p, i) =>
    `${i},${h - p.mean_u_compute * h}`).join(' ')
  const storagePoints = history.map((p, i) =>
    `${i},${h - p.max_u_storage * h}`).join(' ')

  const lastDisc = history[history.length - 1]

  return (
    <div className="space-y-2">
      <div className="relative rounded bg-zinc-900 overflow-hidden" style={{ height: h }}>
        <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
          {/* Checkpoint phase bands */}
          {history.map((p, i) => p.phase === 'checkpoint' ? (
            <rect key={i} x={i} y={0} width={1} height={h}
              fill="#e0a84a" opacity={0.12} />
          ) : p.phase === 'starting.weight_load' ? (
            <rect key={i} x={i} y={0} width={1} height={h}
              fill="#4a9fe0" opacity={0.10} />
          ) : null)}
          {/* Compute mean_u */}
          <polyline
            points={computePoints}
            fill="none" stroke="#4a9fe0" strokeWidth="0.8" opacity={0.8}
          />
          {/* Storage max_u */}
          <polyline
            points={storagePoints}
            fill="none" stroke="#e0a84a" strokeWidth="0.8" opacity={0.9}
          />
          {/* u=0.85 congestion threshold */}
          <line x1={0} y1={h * 0.15} x2={w} y2={h * 0.15}
            stroke="#e05050" strokeWidth="0.5" strokeDasharray="2 2" opacity={0.5} />
        </svg>
        {/* Legend overlay */}
        <div className="absolute bottom-1 right-1 flex gap-2">
          <span className="flex items-center gap-0.5 text-[9px] text-text-muted">
            <span className="w-2 h-0.5 bg-blue-400" /> compute
          </span>
          <span className="flex items-center gap-0.5 text-[9px] text-text-muted">
            <span className="w-2 h-0.5 bg-amber-400" /> storage max
          </span>
          <span className="flex items-center gap-0.5 text-[9px] text-text-muted">
            <span className="w-2 h-px bg-red-400 opacity-60" style={{ borderTop: '1px dashed' }} /> u=0.85
          </span>
        </div>
      </div>

      {/* Discrimination verdict */}
      <div className="flex items-center gap-2 text-xs">
        <span className="text-text-muted">Phase discrimination:</span>
        <VerdictBadge verdict={lastDisc.phase === 'checkpoint' ? 'checkpoint' : 'other'} />
      </div>
    </div>
  )
}

function VerdictBadge({ verdict }: { verdict: string }) {
  if (verdict === 'checkpoint') {
    return (
      <span className="px-1.5 py-0.5 rounded-full text-[10px] bg-amber-900/50 text-amber-300 border border-amber-700/50">
        CHECKPOINT phase
      </span>
    )
  }
  return (
    <span className="px-1.5 py-0.5 rounded-full text-[10px] bg-zinc-800 text-zinc-400">
      {verdict}
    </span>
  )
}

function DiscriminationBlock({ disc }: { disc: FabricDiscrimination | undefined }) {
  if (!disc) return null
  const isCorroborated = disc.verdict === 'checkpoint_corroborated'
  return (
    <div className={`rounded border px-3 py-2 text-xs space-y-1 ${
      isCorroborated
        ? 'border-amber-700/50 bg-amber-900/10'
        : 'border-border bg-surface'
    }`}>
      <div className="flex items-center justify-between">
        <span className="text-text-muted font-medium uppercase tracking-wide text-[10px]">
          Phase Discrimination §25.5
        </span>
        <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-medium ${
          isCorroborated          ? 'bg-amber-900/60 text-amber-300' :
          disc.verdict === 'no_corroboration' ? 'bg-zinc-800 text-zinc-400' :
          disc.verdict === 'unavailable'      ? 'bg-red-900/40 text-red-400' :
          'bg-zinc-800 text-zinc-400'
        }`}>
          {disc.verdict}
        </span>
      </div>
      <div className="flex gap-4 text-[10px] text-text-muted">
        <span>Compute quiesced: <strong className="text-text">{disc.compute_quiesced ? 'yes' : 'no'}</strong></span>
        <span>Storage elephant sustained: <strong className="text-text">{disc.storage_elephant_sustained ? 'yes' : 'no'}</strong></span>
        <span>Tier: <strong className="text-text">{disc.capability_tier}</strong></span>
      </div>
      <p className="text-[10px] text-text-muted leading-relaxed border-t border-border/50 pt-1 mt-1">
        {disc.precedence_note}
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Legacy sub-components
// ---------------------------------------------------------------------------

function CapabilityBadge({ tier }: { tier: CapabilityTier }) {
  return tier === 'enhanced' ? (
    <span className="px-2 py-0.5 text-xs rounded-full bg-green-900/50 text-green-300 border border-green-700">
      ENHANCED
    </span>
  ) : (
    <span className="px-2 py-0.5 text-xs rounded-full bg-amber-900/50 text-amber-300 border border-amber-700">
      BASELINE — roles degraded
    </span>
  )
}

function ClockBadge({ discipline, effective, skew }: {
  discipline: ClockDiscipline
  effective:  ClockDiscipline
  skew:       number
}) {
  const demoted = discipline === 'ptp' && effective === 'ntp'
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 text-xs rounded ${
      effective === 'ptp'
        ? 'bg-blue-900/40 text-blue-300'
        : 'bg-amber-900/40 text-amber-300'
    }`}>
      {effective.toUpperCase()}
      {demoted && (
        <span className="text-amber-400" title={`Declared PTP demoted — skew ${skew.toFixed(1)} ms > 2 ms (TC-70)`}>
          ↓
        </span>
      )}
    </span>
  )
}

function CorrobBadge({ result }: { result: CorroborationResult }) {
  const map: Record<CorroborationResult, { label: string; cls: string }> = {
    pending:             { label: 'Pending',      cls: 'bg-zinc-700 text-zinc-300' },
    corroborated:        { label: 'Corroborated', cls: 'bg-green-900/50 text-green-300' },
    missed:              { label: 'Missed',       cls: 'bg-red-900/40 text-red-400' },
    authoritative_start: { label: 'Authoritative',cls: 'bg-sky-900/50 text-sky-300' },
  }
  const { label, cls } = map[result]
  return (
    <span className={`px-2 py-0.5 text-xs rounded-full ${cls}`}>{label}</span>
  )
}

function ThroughputBar({ value, max }: { value: number; max: number }) {
  const pct = Math.min(100, (value / Math.max(max, 1)) * 100)
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div
          className="h-full bg-sky-500 rounded-full"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-text-muted w-16 text-right">
        {value >= 1000 ? `${(value / 1000).toFixed(1)} Gbps` : `${value} Mbps`}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

interface NetworkTelemetryPageProps {
  runId: string | null
}

export function NetworkTelemetryPage({ runId }: NetworkTelemetryPageProps) {
  // Phase 10: live fabric data from the tick stream
  const tick = useTickStore(s => s.latestTick)
  const fabric: FabricModalView | null = tick?.fabric ?? null

  // Fabric utilisation by fabric group
  const linksByFabric: Record<string, Array<{ id: string; u: number }>> = {}
  if (fabric?.link_utilisation) {
    for (const [id, u] of Object.entries(fabric.link_utilisation)) {
      const fab = id.split('/')[0]
      if (!linksByFabric[fab]) linksByFabric[fab] = []
      linksByFabric[fab].push({ id, u })
    }
  }

  // Rolling history for the throughput chart
  const [history, setHistory] = useState<FabricHistoryPoint[]>([])
  useEffect(() => {
    if (!tick || !fabric) return
    const disc = fabric.discrimination
    // Derive the dominant phase from discrimination state
    const phase = disc?.compute_quiesced && disc?.storage_elephant_sustained
      ? 'checkpoint'
      : tick.checkpoint_states && Object.keys(tick.checkpoint_states).length > 0
      ? 'training'
      : 'idle'

    const computeLinks  = Object.entries(fabric.link_utilisation ?? {}).filter(([id]) => id.startsWith('compute'))
    const storageLinks  = Object.entries(fabric.link_utilisation ?? {}).filter(([id]) => id.startsWith('storage'))
    const meanUCompute  = computeLinks.length ? computeLinks.reduce((a, [, u]) => a + u, 0) / computeLinks.length : 0
    const maxUStorage   = storageLinks.length ? Math.max(...storageLinks.map(([, u]) => u)) : 0

    setHistory(prev => {
      const next = [...prev, {
        sim_time_s: tick.sim_time_seconds,
        phase,
        mean_u_compute: meanUCompute,
        mean_u_storage: 0,
        max_u_storage: maxUStorage,
        latency_ms: fabric.control_latency_ms ?? 0,
        congested_links: fabric.congested_links ?? 0,
      }]
      return next.length > MAX_HISTORY ? next.slice(-MAX_HISTORY) : next
    })
  }, [tick?.tick_index])  // only append when tick_index changes

  // Legacy telemetry (from /network-telemetry endpoint)
  const [legacy, setLegacy]       = useState<LegacyTelemetryState>(_emptyLegacy())
  const [_legacyStatus, setLegacyStatus] = useState<'idle' | 'loading' | 'live' | 'completed' | 'error'>('idle')
  const [_legacyError,  setLegacyError]  = useState('')
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!runId) { setLegacy(_emptyLegacy()); setLegacyStatus('idle'); return }

    let alive = true
    async function fetchLegacy() {
      try {
        const r = await fetch(`/network-telemetry?run_id=${encodeURIComponent(runId!)}`)
        if (!alive) return
        if (r.status === 409) { setLegacyStatus('completed'); if (pollRef.current) clearInterval(pollRef.current); return }
        if (!r.ok) { setLegacyStatus('error'); setLegacyError(`HTTP ${r.status}`); return }
        const data: LegacyTelemetryState = await r.json()
        setLegacy(data)
        setLegacyStatus('live')
      } catch (e: unknown) {
        if (alive) { setLegacyStatus('error'); setLegacyError(String(e)) }
      }
    }

    setLegacyStatus('loading')
    fetchLegacy()
    pollRef.current = setInterval(fetchLegacy, 3000)
    return () => {
      alive = false
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [runId])

  if (!runId) {
    return (
      <div className="h-full flex items-center justify-center text-sm text-text-muted">
        Start a run to see network telemetry.
      </div>
    )
  }

  const maxThroughput = Math.max(
    ...legacy.switches.flatMap(s => [s.throughput_rx_mbps, s.throughput_tx_mbps]), 1)

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4 text-sm">

      {/* Page header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-base font-semibold text-text">Network Telemetry</h2>
          <p className="text-xs text-text-muted mt-0.5">
            §19.9 · Read-only by design (§25.1). Fabric evidence is advisory only (TC-74).
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {fabric && (
            <span className={`px-2 py-0.5 text-xs rounded-full border ${
              fabric.control?.breached
                ? 'bg-red-900/50 text-red-300 border-red-700'
                : (fabric.congested_links ?? 0) > 0
                ? 'bg-amber-900/50 text-amber-300 border-amber-700'
                : 'bg-green-900/50 text-green-300 border-green-700'
            }`}>
              {fabric.control?.breached ? 'NFR-2 BREACH' :
               (fabric.congested_links ?? 0) > 0 ? 'CONGESTED' : 'NOMINAL'}
            </span>
          )}
          {!fabric && runId && (
            <span className="text-xs text-text-muted animate-pulse">awaiting fabric…</span>
          )}
        </div>
      </div>

      {/* ── Section 1: Per-link utilisation heat strip ─────────────────── */}
      <section className="rounded-lg border border-border bg-surface p-3 space-y-3">
        <h3 className="text-xs font-medium text-text-muted uppercase tracking-wide">
          Link Utilisation — {Object.values(fabric?.link_utilisation ?? {}).length} links
        </h3>
        {fabric?.link_utilisation && Object.keys(fabric.link_utilisation).length > 0 ? (
          <div className="space-y-3">
            {Object.entries(linksByFabric).map(([fab, links]) => (
              <HeatStrip key={fab} fabricId={fab} entries={links} />
            ))}
          </div>
        ) : (
          <p className="text-xs text-text-muted">Waiting for first fabric tick…</p>
        )}
        <p className="text-[10px] text-text-muted">
          Each cell = one leaf-uplink. Red = congested (u ≥ 85% for ≥ 2 ticks).
          Storage hotspots appear during checkpoint; compute stays flat (allreduce sprayed evenly).
        </p>
      </section>

      {/* ── Section 2: Phase-annotated throughput ──────────────────────── */}
      <section className="rounded-lg border border-border bg-surface p-3 space-y-3">
        <h3 className="text-xs font-medium text-text-muted uppercase tracking-wide">
          Fabric Utilisation History
        </h3>
        <div className="flex gap-3 text-[10px] text-text-muted">
          <span><span className="inline-block w-3 h-2 rounded-sm bg-amber-500 opacity-40 mr-1" />checkpoint phase</span>
          <span><span className="inline-block w-3 h-2 rounded-sm bg-blue-500 opacity-30 mr-1" />weight load</span>
        </div>
        <DiscriminationPanel history={history} />
        {fabric?.discrimination && (
          <DiscriminationBlock disc={fabric.discrimination} />
        )}
      </section>

      {/* ── Section 3: Control-latency decomposition ───────────────────── */}
      <section className="rounded-lg border border-border bg-surface p-3 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-medium text-text-muted uppercase tracking-wide">
            Control-Path Latency
          </h3>
          {fabric?.control && (
            <span className="text-xs text-text-muted">
              t = {fmtMs(fabric.control_latency_ms)} / {fmtMs(fabric.control?.budget_ms)} NFR-2
            </span>
          )}
        </div>
        <LatencyBar cp={fabric?.control} />
        <p className="text-[10px] text-text-muted">
          Four terms: fabric transit (serialisation + propagation + M/M/1 queueing) ·
          gateway poll cycle · retransmission backoff · asset acknowledgement.
          Under normal load the gateway + asset-ack terms dominate. A saturated frontend
          fabric drives the gateway term to {'>'}1800 ms and breaches the 2000 ms NFR-2 budget.
        </p>
      </section>

      {/* ── Legacy: switch throughput ──────────────────────────────────── */}
      {legacy.switches.length > 0 && (
        <section className="rounded-lg border border-border bg-surface overflow-hidden">
          <div className="px-3 py-2 border-b border-border flex items-center justify-between">
            <h3 className="text-xs font-medium text-text-muted uppercase tracking-wide">
              Switch Interfaces (network-telemetry ingestor)
            </h3>
            <CapabilityBadge tier={legacy.capability} />
          </div>
          <div className="divide-y divide-border">
            {legacy.switches.map(sw => (
              <div key={`${sw.switch_id}:${sw.interface_id}`} className="px-3 py-2.5 space-y-1.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-text">{sw.switch_id}</span>
                    <span className="text-text-muted text-xs">{sw.interface_id}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <ClockBadge discipline={sw.clock_discipline} effective={sw.effective_discipline} skew={sw.observed_skew_ms} />
                    {sw.error_count > 0 && (
                      <span className="px-1.5 py-0.5 text-xs rounded bg-red-900/40 text-red-400">
                        {sw.error_count} err
                      </span>
                    )}
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div><p className="text-xs text-text-muted mb-0.5">RX</p><ThroughputBar value={sw.throughput_rx_mbps} max={maxThroughput} /></div>
                  <div><p className="text-xs text-text-muted mb-0.5">TX</p><ThroughputBar value={sw.throughput_tx_mbps} max={maxThroughput} /></div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Legacy: corroboration record ──────────────────────────────── */}
      {legacy.corroboration.length > 0 && (
        <section className="rounded-lg border border-border bg-surface overflow-hidden">
          <div className="px-3 py-2 border-b border-border flex items-center justify-between">
            <h3 className="text-xs font-medium text-text-muted uppercase tracking-wide">Corroboration Record</h3>
            <span className="text-xs text-text-muted">Fabric traffic matching per predicted job start</span>
          </div>
          <div className="divide-y divide-border">
            {legacy.corroboration.map(row => (
              <div key={row.job_id} className="px-3 py-2.5 flex items-center gap-3">
                <CorrobBadge result={row.result} />
                <div className="flex-1 min-w-0">
                  <span className="font-mono text-xs text-text">{row.job_id}</span>
                  {row.authoritative_event && (
                    <span className="ml-2 text-xs text-sky-400">via {row.authoritative_event} (TC-51)</span>
                  )}
                </div>
                <div className="text-xs text-text-muted text-right">
                  <span>predict t={row.predicted_start_sim_time}s</span>
                  {row.fabric_rise_observed && row.fabric_rise_sim_time != null && (
                    <span className="ml-2">fabric t={row.fabric_rise_sim_time.toFixed(0)}s</span>
                  )}
                  {!row.fabric_rise_observed && (
                    <span className="ml-2 text-red-400">no fabric rise</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Quarantine log */}
      {legacy.quarantine.length > 0 && (
        <section className="rounded-lg border border-border bg-surface overflow-hidden">
          <div className="px-3 py-2 border-b border-border">
            <h3 className="text-xs font-medium text-text-muted uppercase tracking-wide">Quarantine — §17.2</h3>
          </div>
          <div className="divide-y divide-border">
            {legacy.quarantine.map(q => (
              <div key={q.event_id} className="px-3 py-2.5">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-xs text-red-400">{q.event_id}</span>
                  <span className="text-xs text-text-muted">t={q.sim_time}s</span>
                </div>
                <p className="text-xs text-text-muted">{q.reason}</p>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
