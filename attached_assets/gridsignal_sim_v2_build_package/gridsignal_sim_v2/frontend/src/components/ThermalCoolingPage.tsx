/**
 * ThermalCoolingPage — §19.6 Thermal & Cooling console.
 *
 * Primary readout: thermal headroom — how much additional compute load the
 * cooling plant can absorb before approach-to-limit, expressed in both:
 *   • MW absorbable (power headroom)
 *   • time-to-limit (how long until headroom = 0 at the current rate of change)
 *
 * §19.6 contract: read-only monitoring surface.  The cooling plant is
 * autonomous (driven by compute load via the §6.1 thermal lag model).
 * No controls here — a maintenance window proposal (§27.3) is the only
 * legitimate way to intervene.
 *
 * TC-55 boundary: inlet-temperature comfort band is shown as a reference line.
 * This page does not gate dispatch — TC-55 interlocks live in the dispatch layer.
 *
 * W3: live data from GET /thermal?run_id=... (active runs only; 409 for completed).
 */
import { useState, useEffect, useRef } from 'react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ThermalHeadroom {
  absorbable_mw:       number   // MW of additional compute load before limit
  time_to_limit_s:     number   // seconds until headroom = 0 at current rate
  current_load_mw:     number   // current cooling plant load
  rated_capacity_mw:   number   // rated plant capacity
  inlet_temp_c:        number   // current inlet temperature (°C)
  inlet_comfort_lo_c:  number   // TC-55 comfort band lower bound
  inlet_comfort_hi_c:  number   // TC-55 comfort band upper bound
  approach_rate_mw_s:  number   // rate of change of load (MW/s, pos = rising)
}

interface CoolingZone {
  zone_id:       string
  zone_name:     string
  load_mw:       number
  capacity_mw:   number
  utilisation:   number   // 0.0–1.0
}

interface CoolingPageState {
  headroom:  ThermalHeadroom
  zones:     CoolingZone[]
  tick_s:    number
}

interface ThermalCoolingPageProps {
  runId: string | null
}

// ---------------------------------------------------------------------------
// Empty state (no stub data — live API only)
// ---------------------------------------------------------------------------

function _empty(): CoolingPageState {
  return {
    headroom: {
      absorbable_mw: 0, time_to_limit_s: 86400,
      current_load_mw: 0, rated_capacity_mw: 0,
      inlet_temp_c: 21, inlet_comfort_lo_c: 18, inlet_comfort_hi_c: 24,
      approach_rate_mw_s: 0,
    },
    zones: [],
    tick_s: 0,
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function _fmtSeconds(s: number): string {
  if (s >= 86400) return '∞'
  if (s < 60)  return `${Math.round(s)}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
}

function _utilColour(u: number): string {
  if (u >= 0.90) return '#ef4444'   // red
  if (u >= 0.75) return '#f59e0b'   // amber
  return '#22c55e'                   // green
}

function _headroomColour(absorbable: number, rated: number): string {
  if (rated <= 0) return '#94a3b8'
  const ratio = absorbable / rated
  if (ratio <= 0.10) return '#ef4444'
  if (ratio <= 0.25) return '#f59e0b'
  return '#22c55e'
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ThermalCoolingPage({ runId }: ThermalCoolingPageProps) {
  const [st, setSt] = useState<CoolingPageState>(_empty())
  const [pollStatus, setPollStatus] = useState<'idle' | 'loading' | 'live' | 'completed' | 'error'>('idle')
  const [errorMsg, setErrorMsg] = useState('')
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!runId) { setSt(_empty()); setPollStatus('idle'); return }

    let alive = true
    async function fetchThermal() {
      try {
        const r = await fetch(`/thermal?run_id=${encodeURIComponent(runId!)}`)
        if (!alive) return
        if (r.status === 409) {
          setPollStatus('completed')
          if (pollRef.current) clearInterval(pollRef.current)
          return
        }
        if (!r.ok) { setPollStatus('error'); setErrorMsg(`HTTP ${r.status}`); return }
        const raw = await r.json()
        setSt({
          headroom: {
            absorbable_mw:      raw.absorbable_mw,
            time_to_limit_s:    raw.time_to_limit_s,
            current_load_mw:    raw.current_load_mw,
            rated_capacity_mw:  raw.rated_capacity_mw,
            inlet_temp_c:       raw.inlet_temp_c,
            inlet_comfort_lo_c: raw.inlet_comfort_lo_c,
            inlet_comfort_hi_c: raw.inlet_comfort_hi_c,
            approach_rate_mw_s: raw.approach_rate_mw_s,
          },
          zones: raw.zones ?? [],
          tick_s: raw.tick_s ?? 0,
        })
        setPollStatus('live')
      } catch (e: unknown) {
        if (alive) { setPollStatus('error'); setErrorMsg(String(e)) }
      }
    }

    setPollStatus('loading')
    fetchThermal()
    pollRef.current = setInterval(fetchThermal, 1000)
    return () => {
      alive = false
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [runId])

  const { headroom, zones } = st

  if (!runId) {
    return (
      <div style={{ padding: '24px', fontFamily: 'monospace', color: '#e2e8f0', background: '#0f172a', minHeight: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ color: '#64748b' }}>Start a run to see thermal &amp; cooling data.</span>
      </div>
    )
  }

  const utilisationPct = headroom.rated_capacity_mw > 0
    ? (headroom.current_load_mw / headroom.rated_capacity_mw) * 100
    : 0
  const headroomColour = _headroomColour(headroom.absorbable_mw, headroom.rated_capacity_mw)
  const inletOk = headroom.inlet_temp_c >= headroom.inlet_comfort_lo_c
                && headroom.inlet_temp_c <= headroom.inlet_comfort_hi_c

  return (
    <div style={{ padding: '24px', fontFamily: 'monospace', color: '#e2e8f0', background: '#0f172a', minHeight: '100%' }}>

      {/* ── Header ── */}
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '18px', color: '#f1f5f9' }}>
            §19.6 Thermal &amp; Cooling
          </h2>
          <p style={{ margin: '4px 0 0', fontSize: '12px', color: '#64748b' }}>
            Read-only monitoring surface · Cooling plant is autonomous
          </p>
        </div>
        <div style={{ fontSize: '11px', color: '#64748b' }}>
          {pollStatus === 'loading' && <span style={{ color: '#94a3b8' }}>connecting…</span>}
          {pollStatus === 'live' && <span style={{ color: '#22c55e' }}>● live t={st.tick_s.toFixed(0)}s</span>}
          {pollStatus === 'completed' && <span style={{ color: '#f59e0b' }}>run complete</span>}
          {pollStatus === 'error' && <span style={{ color: '#ef4444' }}>error: {errorMsg}</span>}
        </div>
      </div>

      {/* Loading state */}
      {pollStatus === 'loading' && headroom.rated_capacity_mw === 0 && (
        <div style={{ textAlign: 'center', padding: '48px', color: '#475569' }}>
          Waiting for first tick…
        </div>
      )}

      {headroom.rated_capacity_mw > 0 && (
        <>
          {/* ── Primary readout: thermal headroom ── */}
          <div style={{
            display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '24px',
          }}>

            {/* MW absorbable */}
            <div style={{ background: '#1e293b', borderRadius: '8px', padding: '20px', border: `1px solid ${headroomColour}` }}>
              <div style={{ fontSize: '11px', color: '#94a3b8', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                Thermal Headroom (MW)
              </div>
              <div style={{ fontSize: '40px', fontWeight: 700, color: headroomColour }}>
                {headroom.absorbable_mw.toFixed(1)}
                <span style={{ fontSize: '16px', color: '#94a3b8', marginLeft: '4px' }}>MW</span>
              </div>
              <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                Additional compute load before approach-to-limit
              </div>
            </div>

            {/* Time to limit */}
            <div style={{ background: '#1e293b', borderRadius: '8px', padding: '20px', border: `1px solid ${headroomColour}` }}>
              <div style={{ fontSize: '11px', color: '#94a3b8', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                Time to Limit
              </div>
              <div style={{ fontSize: '40px', fontWeight: 700, color: headroomColour }}>
                {_fmtSeconds(headroom.time_to_limit_s)}
              </div>
              <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                At current approach rate: {headroom.approach_rate_mw_s.toFixed(4)} MW/s
              </div>
            </div>
          </div>

          {/* ── Plant utilisation bar ── */}
          <div style={{ background: '#1e293b', borderRadius: '8px', padding: '16px', marginBottom: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '12px', color: '#94a3b8' }}>
              <span>Plant Utilisation</span>
              <span>{headroom.current_load_mw.toFixed(1)} / {headroom.rated_capacity_mw.toFixed(1)} MW ({utilisationPct.toFixed(0)}%)</span>
            </div>
            <div style={{ height: '10px', background: '#334155', borderRadius: '4px', overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${utilisationPct}%`, background: headroomColour, transition: 'width 0.3s' }} />
            </div>
          </div>

          {/* ── Inlet temperature ── */}
          <div style={{ background: '#1e293b', borderRadius: '8px', padding: '16px', marginBottom: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: '11px', color: '#94a3b8', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                  Inlet Temperature (TC-55 comfort band)
                </div>
                <div style={{ fontSize: '24px', fontWeight: 700, color: inletOk ? '#22c55e' : '#ef4444' }}>
                  {headroom.inlet_temp_c.toFixed(1)}°C
                </div>
              </div>
              <div style={{ textAlign: 'right', fontSize: '12px', color: '#64748b' }}>
                <div>Band: {headroom.inlet_comfort_lo_c}°C – {headroom.inlet_comfort_hi_c}°C</div>
                <div style={{ color: inletOk ? '#22c55e' : '#ef4444', fontWeight: 600 }}>
                  {inletOk ? '● In comfort band' : '● OUTSIDE comfort band'}
                </div>
              </div>
            </div>
          </div>

          {/* ── Zone breakdown ── */}
          {zones.length > 0 && (
            <div style={{ background: '#1e293b', borderRadius: '8px', padding: '16px' }}>
              <div style={{ fontSize: '11px', color: '#94a3b8', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                Cooling Zones
              </div>
              {zones.map(zone => {
                const colour = _utilColour(zone.utilisation)
                return (
                  <div key={zone.zone_id} style={{ marginBottom: '10px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                      <span style={{ color: '#cbd5e1' }}>{zone.zone_name}</span>
                      <span style={{ color: '#94a3b8' }}>
                        {zone.load_mw.toFixed(1)} / {zone.capacity_mw.toFixed(1)} MW
                        <span style={{ color: colour, marginLeft: '8px' }}>
                          {(zone.utilisation * 100).toFixed(0)}%
                        </span>
                      </span>
                    </div>
                    <div style={{ height: '6px', background: '#334155', borderRadius: '3px', overflow: 'hidden' }}>
                      <div style={{ height: '100%', width: `${zone.utilisation * 100}%`, background: colour }} />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}

      {/* ── Footer note ── */}
      <div style={{ marginTop: '16px', fontSize: '11px', color: '#475569', textAlign: 'center' }}>
        §19.6 read-only · Maintenance window proposals live in Proposals &amp; Learning ·
        TC-55 dispatch interlock is in the dispatch layer, not this page
      </div>
    </div>
  )
}
