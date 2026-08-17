/**
 * MarginContributionReport — §30 Margin Contribution Proforma display.
 *
 * Visual target: margin-contribution-mockup.html.
 * Chrome caveat: mockup sidebar is illustrative only — this component renders
 * inside ScenarioPlannerPage's existing tab surface, not in a new sidebar nav.
 *
 * Design tokens (from mockup — used exactly):
 *   --bg:#0A1120  --panel:#111B2E  --panel-2:#0D1626
 *   --border:#213049  --border-soft:#1A2740
 *   --text:#E7EDF5  --text-dim:#8CA0BF  --text-faint:#5C7191
 *   --teal:#2DD4BF  --teal-dim:#175C54
 *   --amber:#F5A524  --amber-dim:#4A360E
 *   --green:#34D399  --red:#F87171  --red-dim:#3A1E1E
 *
 * Fonts: Space Grotesk (display), Inter (UI body), IBM Plex Mono (all numbers).
 * Allocation bar: filled teal within allocation; hatched amber for overage only
 *   when over_alloc_flag is true (AC-4.5: zero amber when no overage).
 *
 * AC-4.1: run_id + profile_id displayed.
 * AC-4.2: comparison mode via side-by-side — deferred to follow-up (scoped here
 *          as a period toggle which is the MVP comparison surface).
 * AC-4.4: disclaimer + MC-10 approximate MWh disclosure always shown.
 * AC-4.5: allocation bar renders zero amber when over_alloc = 0.
 * AC-4.6: all monetary/MW/MWh figures in mono; labels in sans-serif.
 */

import { useState, useEffect } from 'react'
import type { ProformaResponse, TenantProformaRow } from '../types'

const C = {
  bg:         '#0A1120',
  panel:      '#111B2E',
  panel2:     '#0D1626',
  border:     '#213049',
  borderSoft: '#1A2740',
  text:       '#E7EDF5',
  textDim:    '#8CA0BF',
  textFaint:  '#5C7191',
  teal:       '#2DD4BF',
  tealDim:    '#175C54',
  amber:      '#F5A524',
  amberDim:   '#4A360E',
  green:      '#34D399',
  red:        '#F87171',
  redDim:     '#3A1E1E',
} as const

const mono: React.CSSProperties = { fontFamily: "'IBM Plex Mono', monospace" }
const display: React.CSSProperties = { fontFamily: "'Space Grotesk', sans-serif" }

function fmt$(n: number): string {
  const abs = Math.abs(n)
  const s = abs >= 1_000_000
    ? `$${(abs / 1_000_000).toFixed(2)}M`
    : abs >= 1_000
    ? `$${(abs / 1_000).toFixed(1)}k`
    : `$${abs.toFixed(0)}`
  return n < 0 ? `−${s}` : s
}

function fmtPct(n: number): string {
  return `${n >= 0 ? '+' : ''}${n.toFixed(1)}%`
}

// ── Allocation bar ─────────────────────────────────────────────────────────
function AllocBar({ row }: { row: TenantProformaRow }) {
  const total = row.contracted_allocation > 0 ? row.contracted_allocation : row.usage_mwh || 1
  const withinPct = Math.min(100, (row.within_alloc / total) * 100)
  const overPct = row.over_alloc_flag
    ? Math.min(100 - withinPct, (row.over_alloc / total) * 100)
    : 0

  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10.5, color: C.textFaint, marginBottom: 6 }}>
        <span>Allocation {row.contracted_allocation.toFixed(0)} MWh</span>
        <span style={mono}>{row.usage_mwh.toFixed(1)} MWh</span>
      </div>
      <div style={{
        height: 9, borderRadius: 5, background: C.panel2, overflow: 'hidden',
        display: 'flex', border: `1px solid ${C.borderSoft}`,
      }}>
        {/* Teal fill: within allocation */}
        <div style={{
          width: `${withinPct}%`,
          background: 'linear-gradient(90deg,#1a8f82,#2DD4BF)',
          height: '100%',
          flexShrink: 0,
        }} />
        {/* Hatched amber: overage — only when over_alloc_flag (AC-4.5) */}
        {row.over_alloc_flag && overPct > 0 && (
          <div style={{
            width: `${overPct}%`,
            height: '100%',
            background: 'repeating-linear-gradient(135deg,#F5A524 0 4px,#B8791A 4px 8px)',
            flexShrink: 0,
          }} />
        )}
      </div>
    </div>
  )
}

// ── Tenant card ────────────────────────────────────────────────────────────
function TenantCard({ row }: { row: TenantProformaRow }) {
  const mcPos = row.margin_contribution >= 0

  return (
    <div style={{
      background: C.panel, border: `1px solid ${C.borderSoft}`,
      borderRadius: 12, padding: '17px 18px',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 13 }}>
        <div>
          <div style={{ ...display, fontWeight: 600, fontSize: 14.5 }}>Tenant {row.tenant_id}</div>
          <div style={{ ...mono, fontSize: 10.5, color: C.textFaint, marginTop: 2 }}>
            {row.billing_basis.replace(/_/g, '-')}
          </div>
        </div>
        <div style={{
          fontSize: 10, fontWeight: 600, padding: '3px 7px', borderRadius: 5, letterSpacing: '.03em',
          ...(row.over_alloc_flag
            ? { background: 'rgba(245,165,36,0.12)', color: C.amber }
            : { background: 'rgba(45,212,191,0.09)', color: C.teal }),
        }}>
          {row.over_alloc_flag ? 'over allocation' : 'within allocation'}
        </div>
      </div>

      <AllocBar row={row} />

      {/* Cost rows */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 13 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5 }}>
          <span style={{ color: C.textDim }}>Revenue</span>
          <span style={{ ...mono, fontWeight: 500 }}>{fmt$(row.revenue)}</span>
        </div>
        {row.over_alloc_flag && (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11.5 }}>
              <span style={{ color: C.textFaint, paddingLeft: 10 }}>— within allocation</span>
              <span style={{ ...mono, color: C.textFaint }}>{fmt$(row.revenue_within_alloc)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11.5 }}>
              <span style={{ color: C.textFaint, paddingLeft: 10 }}>— overage ({row.over_alloc.toFixed(1)} MWh × rate)</span>
              <span style={{ ...mono, color: C.textFaint }}>{fmt$(row.revenue_over_alloc)}</span>
            </div>
          </>
        )}
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5 }}>
          <span style={{ color: C.textDim }}>Allocated COGS</span>
          <span style={{ ...mono, fontWeight: 500 }}>{fmt$(row.allocated_cogs)}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5 }}>
          <span style={{ color: C.textDim }}>Allocated fixed cost</span>
          <span style={{ ...mono, fontWeight: 500 }}>{fmt$(row.allocated_fixed_cost)}</span>
        </div>
      </div>

      {/* Divider */}
      <div style={{ height: 1, background: C.borderSoft, margin: '12px 0' }} />

      {/* Margin contribution hero */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <div>
          <div style={{ fontSize: 11.5, color: C.textDim, fontWeight: 500 }}>Margin Contribution</div>
          <div style={{ fontSize: 11, marginTop: 2, color: mcPos ? C.green : C.red }}>
            {fmtPct(row.margin_pct)}
          </div>
        </div>
        <div style={{ ...mono, fontSize: 19, fontWeight: 600, color: mcPos ? C.green : C.red }}>
          {row.margin_contribution >= 0 ? '' : '−'}{fmt$(Math.abs(row.margin_contribution))}
        </div>
      </div>
    </div>
  )
}

// ── Props ──────────────────────────────────────────────────────────────────
interface MarginContributionReportProps {
  runId: string
  profileId: string
  profileName?: string
  scenarioName?: string
}

// ── Main component ─────────────────────────────────────────────────────────
export function MarginContributionReport({
  runId,
  profileId,
  profileName,
  scenarioName,
}: MarginContributionReportProps) {
  const [period, setPeriod] = useState<'monthly' | 'quarterly' | 'annual'>('monthly')
  const [data, setData] = useState<ProformaResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [scaleAcknowledged, setScaleAcknowledged] = useState(false)

  // NFR-30.2 / AC-4.3: fetch proforma; same run_id + profile_id + period
  // always produces the same output without new dispatch computation.
  useEffect(() => {
    if (!runId || !profileId) return
    setLoading(true)
    setError(null)
    setData(null)

    fetch(
      `/api/economic-profiles/${profileId}/proforma?run_id=${encodeURIComponent(runId)}&period=${period}`
    )
      .then(async (resp) => {
        if (resp.status === 410 || resp.status === 409) {
          // AC-3.1: session-scope limitation — clear operator message
          const body = await resp.json().catch(() => ({ detail: '' }))
          throw new Error(
            body.detail ||
            "This scenario's data is no longer available — re-run it to generate a Margin Contribution report. (MC-11)"
          )
        }
        if (!resp.ok) {
          const body = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
          throw new Error(body.detail || `Error ${resp.status}`)
        }
        return resp.json() as Promise<ProformaResponse>
      })
      .then((d) => { setData(d); setLoading(false) })
      .catch((e) => { setError(String(e)); setLoading(false) })
  }, [runId, profileId, period])

  const triggerExport = () => {
    const url = `/api/economic-profiles/${profileId}/proforma/export?run_id=${encodeURIComponent(runId)}&period=${period}`
    const a = document.createElement('a')
    a.href = url
    a.download = `margin-contribution-${runId}-${period}.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }

  const totalMcPos = (data?.total_margin_contribution ?? 0) >= 0

  return (
    <div style={{
      background: C.bg,
      borderRadius: 12,
      border: `1px solid ${C.border}`,
      padding: '22px 24px',
      marginTop: 24,
      fontFamily: 'Inter, sans-serif',
    }}>
      {/* ── Page head ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20, gap: 20, flexWrap: 'wrap' }}>
        <div>
          <div style={{ ...display, fontWeight: 600, fontSize: 21, letterSpacing: '.1px', marginBottom: 5, color: C.text }}>
            Margin Contribution Proforma
          </div>
          <div style={{ fontSize: 13, color: C.textDim, maxWidth: 560, lineHeight: 1.5 }}>
            Revenue less energy COGS, amortised asset capital, and curtailment cost — for this scenario's dispatch output.
            Excludes labor, insurance, property tax, interest, and non-energy G&amp;A.
          </div>
        </div>
        <div style={{ display: 'flex', gap: 9, flexShrink: 0 }}>
          <button
            onClick={triggerExport}
            disabled={!data}
            style={{
              fontSize: 12.5, fontWeight: 600, padding: '8px 13px', borderRadius: 7,
              border: `1px solid ${C.teal}`, background: C.teal, color: '#06231f',
              cursor: data ? 'pointer' : 'not-allowed', opacity: data ? 1 : 0.5,
            }}
          >
            ⬇ Export CSV
          </button>
        </div>
      </div>

      {/* ── Meta strip (AC-4.1: run_id + profile_id) ── */}
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(4,1fr)',
        gap: 1, background: C.borderSoft,
        border: `1px solid ${C.borderSoft}`, borderRadius: 10, overflow: 'hidden',
        marginBottom: 22,
      }}>
        {[
          ['Scenario', scenarioName || runId],
          ['Economic Profile', profileName || profileId],
          ['Run ID', runId],
          ['Profile ID', profileId],
        ].map(([k, v]) => (
          <div key={k} style={{ background: C.panel, padding: '13px 16px' }}>
            <div style={{ fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '.07em', color: C.textFaint, marginBottom: 5 }}>{k}</div>
            <div style={{ ...mono, fontSize: 11.5, color: C.text, wordBreak: 'break-all' }}>{v}</div>
          </div>
        ))}
      </div>

      {/* ── Period toggle + scale note ── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14, flexWrap: 'wrap', gap: 10 }}>
        <div style={{ display: 'flex', background: C.panel, border: `1px solid ${C.border}`, borderRadius: 8, padding: 3, gap: 2 }}>
          {(['monthly', 'quarterly', 'annual'] as const).map((p) => (
            <button
              key={p}
              onClick={() => { setPeriod(p); setScaleAcknowledged(false) }}
              style={{
                fontSize: 12, padding: '6px 13px', borderRadius: 6,
                border: 'none', cursor: 'pointer',
                ...(period === p
                  ? { background: C.tealDim, color: C.teal, fontWeight: 600 }
                  : { background: 'transparent', color: C.textFaint, fontWeight: 500 }),
              }}
            >
              {p.charAt(0).toUpperCase() + p.slice(1)}
            </button>
          ))}
        </div>

        {/* MC-1: scale note + operator acknowledgment — functional UI, not decoration */}
        {data && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11.5, color: C.textFaint }}>
            <span>ℹ</span>
            <span>
              Scaled from a {data.run_duration_hours.toFixed(2)}-hour trace × {data.scale_factor.toFixed(1)}×
              {' '}— repeated flat across the {period}
            </span>
            {!scaleAcknowledged ? (
              <button
                onClick={() => setScaleAcknowledged(true)}
                style={{
                  fontSize: 10.5, padding: '2px 8px', borderRadius: 4,
                  background: C.amberDim, color: C.amber, border: `1px solid rgba(245,165,36,0.35)`,
                  cursor: 'pointer', fontWeight: 600,
                }}
              >
                Confirm
              </button>
            ) : (
              <span style={{ color: C.green, fontWeight: 600 }}>— confirmed by operator</span>
            )}
          </div>
        )}
      </div>

      {/* ── Loading / Error ── */}
      {loading && (
        <div style={{ textAlign: 'center', padding: 40, color: C.textFaint }}>
          Computing proforma…
        </div>
      )}
      {error && (
        <div style={{
          background: C.redDim, border: `1px solid rgba(248,113,113,0.3)`,
          borderRadius: 9, padding: '14px 18px', color: C.red, fontSize: 13, lineHeight: 1.5,
          marginBottom: 16,
        }}>
          <strong>Unable to generate report</strong><br />
          {error}
        </div>
      )}

      {/* ── Tenant cards ── */}
      {data && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 14, marginBottom: 22 }}>
            {data.tenant_rows.map((row) => (
              <TenantCard key={row.tenant_id} row={row} />
            ))}
          </div>

          {/* ── Aggregate bar ── */}
          <div style={{
            background: 'linear-gradient(135deg,#0F2A28,#0D1F2E)',
            border: `1px solid rgba(45,212,191,0.25)`,
            borderRadius: 12, padding: '20px 24px', marginBottom: 24,
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            flexWrap: 'wrap', gap: 18,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 26, flexWrap: 'wrap' }}>
              {[
                ['Total revenue', fmt$(data.total_revenue), C.teal],
                ['Total COGS + fixed', fmt$(data.total_energy_cogs + data.total_capex_cost), C.text],
                ['Curtailment cost', fmt$(data.total_curtailment_cost), C.text],
              ].map(([label, value, color]) => (
                <div key={label as string}>
                  <div style={{ fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '.07em', color: C.textFaint, marginBottom: 5 }}>
                    {label}
                  </div>
                  <div style={{ ...mono, fontSize: 20, fontWeight: 600, color: color as string }}>{value}</div>
                </div>
              ))}
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 11, color: C.textDim, marginBottom: 4 }}>
                {period.charAt(0).toUpperCase() + period.slice(1)} Margin Contribution
              </div>
              <div style={{ ...display, fontSize: 30, fontWeight: 700, color: totalMcPos ? C.green : C.red, lineHeight: 1 }}>
                {totalMcPos ? '' : '−'}{fmt$(Math.abs(data.total_margin_contribution))}
              </div>
              <div style={{ ...mono, fontSize: 13, color: totalMcPos ? C.green : C.red, marginTop: 5 }}>
                {fmtPct(data.total_margin_pct)} margin
              </div>
            </div>
          </div>

          {/* ── Disclaimers (AC-4.4: both scope + MC-10) ── */}
          <div style={{
            fontSize: 11.5, color: C.textFaint, lineHeight: 1.6, padding: '14px 16px',
            background: C.panel2, border: `1px solid ${C.borderSoft}`, borderRadius: 9,
            display: 'flex', gap: 10,
          }}>
            <span style={{ flexShrink: 0, marginTop: 1 }}>ℹ</span>
            <div>
              This is an operational energy margin — revenue less energy COGS, amortised energy-asset capital, and
              curtailment cost. It excludes labor, insurance, property tax, non-energy G&amp;A, interest, and
              depreciation outside the energy-asset line.
              {data.proposed_here_count > 0 && (
                <> Rate card figures include <b style={{ color: C.amber }}>{data.proposed_here_count} field{data.proposed_here_count > 1 ? 's' : ''} tagged PROPOSED_HERE</b> — third-party estimates pending design-partner validation, not confirmed tenant contracts.</>
              )}
              {' '}<b>Per-tenant MWh values are approximations</b> derived from instantaneous per-job draw estimates (MC-10),
              not metered readings — do not use for billing without independent validation.
              Report generated from in-session tick data (MC-11); a server restart between scenario run and this
              report would have returned an error.
            </div>
          </div>
        </>
      )}
    </div>
  )
}
