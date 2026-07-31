/**
 * NetworkTelemetryPage — §19.9 Network Telemetry console.
 *
 * Read-only by design, not by omission (§25.1, TC-74).
 * NetworkTelemetry is dispatch-path ineligible by contract: no controls here
 * can influence the dispatch or forecast path.  The page title and subtitle
 * make this explicit so operators are not confused by the absence of controls.
 *
 * Sections:
 *  1. Capability tier indicator (BASELINE / ENHANCED)
 *  2. Per-switch throughput sparklines (read-only)
 *  3. Clock discipline and demotion status (§11.4 — TC-70)
 *  4. Corroboration record — per-job fabric matching (TC-50, TC-51)
 *  5. Quarantine log (TC-72)
 *
 * W3: live data from GET /network-telemetry?run_id=... (active runs only;
 * endpoint returns 409 for completed runs).
 */
import { useState, useEffect, useRef } from 'react'

// ---------------------------------------------------------------------------
// Types (mirroring core/network_telemetry.py wire shapes)
// ---------------------------------------------------------------------------

type ClockDiscipline = 'ptp' | 'ntp'
type CapabilityTier  = 'baseline' | 'enhanced'
type CorroborationResult = 'pending' | 'corroborated' | 'missed' | 'authoritative_start'

interface SwitchRow {
  switch_id:            string
  interface_id:         string
  throughput_rx_mbps:   number
  throughput_tx_mbps:   number
  optical_power_tx_dbm: number
  optical_power_rx_dbm: number
  clock_discipline:     ClockDiscipline
  effective_discipline: ClockDiscipline   // after TC-70 demotion check
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
  event_id:    string
  reason:      string
  sim_time:    number
}

interface TelemetryState {
  capability:    CapabilityTier
  switches:      SwitchRow[]
  corroboration: CorroborationRow[]
  quarantine:    QuarantineRow[]
  last_updated_s: number
}

// ---------------------------------------------------------------------------
// Empty state (no stub data — live API only)
// ---------------------------------------------------------------------------

function _empty(): TelemetryState {
  return { capability: 'baseline', switches: [], corroboration: [], quarantine: [], last_updated_s: 0 }
}

// ---------------------------------------------------------------------------
// Sub-components
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
  const [state, setState] = useState<TelemetryState>(_empty())
  const [status, setStatus] = useState<'idle' | 'loading' | 'live' | 'completed' | 'error'>('idle')
  const [errorMsg, setErrorMsg] = useState('')
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!runId) { setState(_empty()); setStatus('idle'); return }

    let alive = true
    async function fetchTelemetry() {
      try {
        const r = await fetch(`/network-telemetry?run_id=${encodeURIComponent(runId!)}`)
        if (!alive) return
        if (r.status === 409) {
          // Run completed — stop polling, keep last state.
          setStatus('completed')
          if (pollRef.current) clearInterval(pollRef.current)
          return
        }
        if (!r.ok) { setStatus('error'); setErrorMsg(`HTTP ${r.status}`); return }
        const data: TelemetryState = await r.json()
        setState(data)
        setStatus('live')
      } catch (e: unknown) {
        if (alive) { setStatus('error'); setErrorMsg(String(e)) }
      }
    }

    setStatus('loading')
    fetchTelemetry()
    pollRef.current = setInterval(fetchTelemetry, 2000)
    return () => {
      alive = false
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [runId])

  const maxThroughput = Math.max(
    ...state.switches.flatMap(s => [s.throughput_rx_mbps, s.throughput_tx_mbps]),
    1,
  )

  if (!runId) {
    return (
      <div className="h-full flex items-center justify-center text-sm text-text-muted">
        Start a run to see network telemetry.
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4 text-sm">

      {/* Page header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-base font-semibold text-text">Network Telemetry</h2>
          <p className="text-xs text-text-muted mt-0.5">
            §19.9 · Read-only by design, not by omission (§25.1). No controls on this page
            can influence dispatch or forecast. Fabric evidence is informational only (TC-74).
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {status === 'loading' && (
            <span className="text-xs text-text-muted animate-pulse">connecting…</span>
          )}
          {status === 'completed' && (
            <span className="text-xs text-amber-300">run complete</span>
          )}
          {status === 'error' && (
            <span className="text-xs text-red-400">{errorMsg}</span>
          )}
          <CapabilityBadge tier={state.capability} />
          <span className="text-xs text-text-muted">t={state.last_updated_s.toFixed(0)}s</span>
        </div>
      </div>

      {/* TC-71 warning for BASELINE */}
      {state.capability === 'baseline' && state.switches.length > 0 && (
        <div className="rounded-lg border border-amber-700/40 bg-amber-900/10 p-3">
          <p className="text-xs text-amber-300">
            <strong>BASELINE capability:</strong> Ingestion continues normally.
            Optical monitoring, clock-class analysis, and corroboration are degraded (TC-71).
          </p>
        </div>
      )}

      {/* §11.4 Clock-class demotion notice */}
      {state.switches.some(s => s.clock_discipline !== s.effective_discipline) && (
        <div className="rounded-lg border border-amber-700/40 bg-amber-900/10 p-3">
          <p className="text-xs text-amber-300">
            <strong>TC-70:</strong> One or more sources declared PTP discipline but showed skew
            &gt; ±2 ms — demoted to NTP-class clock. Cross-source correlation uses the looser
            2-second bound (TC-69).
          </p>
        </div>
      )}

      {/* Empty state */}
      {status !== 'loading' && state.switches.length === 0 && (
        <p className="text-xs text-text-muted px-2 py-4 text-center">
          {status === 'completed'
            ? 'Run completed — telemetry snapshot frozen above.'
            : 'Waiting for first tick of telemetry data…'}
        </p>
      )}

      {/* Switch throughput table */}
      {state.switches.length > 0 && (
        <section className="rounded-lg border border-border bg-surface overflow-hidden">
          <div className="px-3 py-2 border-b border-border">
            <h3 className="text-xs font-medium text-text-muted uppercase tracking-wide">
              Switch Interfaces
            </h3>
          </div>
          <div className="divide-y divide-border">
            {state.switches.map(sw => (
              <div key={`${sw.switch_id}:${sw.interface_id}`} className="px-3 py-2.5 space-y-1.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-text">{sw.switch_id}</span>
                    <span className="text-text-muted text-xs">{sw.interface_id}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <ClockBadge
                      discipline={sw.clock_discipline}
                      effective={sw.effective_discipline}
                      skew={sw.observed_skew_ms}
                    />
                    {sw.error_count > 0 && (
                      <span className="px-1.5 py-0.5 text-xs rounded bg-red-900/40 text-red-400">
                        {sw.error_count} err
                      </span>
                    )}
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <p className="text-xs text-text-muted mb-0.5">RX</p>
                    <ThroughputBar value={sw.throughput_rx_mbps} max={maxThroughput} />
                  </div>
                  <div>
                    <p className="text-xs text-text-muted mb-0.5">TX</p>
                    <ThroughputBar value={sw.throughput_tx_mbps} max={maxThroughput} />
                  </div>
                </div>
                <div className="flex gap-4 text-xs text-text-muted">
                  <span>TX opt: <span className="text-text">{sw.optical_power_tx_dbm.toFixed(1)} dBm</span></span>
                  <span>RX opt: <span className="text-text">{sw.optical_power_rx_dbm.toFixed(1)} dBm</span></span>
                  <span>Skew: <span className="text-text">{sw.observed_skew_ms.toFixed(1)} ms</span></span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Corroboration record */}
      <section className="rounded-lg border border-border bg-surface overflow-hidden">
        <div className="px-3 py-2 border-b border-border flex items-center justify-between">
          <h3 className="text-xs font-medium text-text-muted uppercase tracking-wide">
            Corroboration Record
          </h3>
          <span className="text-xs text-text-muted">
            Fabric traffic matching per predicted job start
          </span>
        </div>
        {state.corroboration.length === 0 ? (
          <p className="px-3 py-4 text-xs text-text-muted">
            No job predictions recorded yet.
          </p>
        ) : (
          <div className="divide-y divide-border">
            {state.corroboration.map(row => (
              <div key={row.job_id} className="px-3 py-2.5 flex items-center gap-3">
                <CorrobBadge result={row.result} />
                <div className="flex-1 min-w-0">
                  <span className="font-mono text-xs text-text">{row.job_id}</span>
                  {row.authoritative_event && (
                    <span className="ml-2 text-xs text-sky-400">
                      via {row.authoritative_event} (TC-51)
                    </span>
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
        )}
        <div className="px-3 py-2 border-t border-border bg-canvas/50">
          <p className="text-xs text-text-muted">
            TC-73: Fabric corroboration does not count toward the §17.3 reconciliation
            threshold — throughput is not a magnitude proxy.
          </p>
        </div>
      </section>

      {/* Quarantine log */}
      {state.quarantine.length > 0 && (
        <section className="rounded-lg border border-border bg-surface overflow-hidden">
          <div className="px-3 py-2 border-b border-border">
            <h3 className="text-xs font-medium text-text-muted uppercase tracking-wide">
              Quarantine — §17.2
            </h3>
          </div>
          <div className="divide-y divide-border">
            {state.quarantine.map(q => (
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
