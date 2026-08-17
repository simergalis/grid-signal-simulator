/**
 * ScenarioPlannerPage — §19.1 Page 9 surface / §18.5 FR-4.4 Scenario Planner.
 *
 * Answers "what if we added more BESS instead of a second turbine?" over
 * persisted run history, not assumptions.
 *
 * §21.2 cost model:
 *   • Grid import:    price_per_mwh × energy_mwh
 *   • On-site gen:    amortised capital against duty cycle + variable O&M
 *                     (turbine is debt-financed; relevant question is how often
 *                      it runs against what it costs to own)
 *   • Storage RT:     charge cost + round-trip loss cost
 *
 * W3: run history fetched from GET /runs/{run_id}/energy-summary (completed runs
 * only — the endpoint returns 409 for active runs).  Each new run_id arriving
 * via props is polled until it completes, then added to the run history list.
 *
 * This page is a what-if surface over actual run history.  It commits nothing.
 * Reservations and capacity changes are proposed via the advisory gate.
 */
import { useState, useCallback, useEffect, useRef } from 'react'
import { EconomicProfileModal } from './EconomicProfileModal'
import { MarginContributionReport } from './MarginContributionReport'
import { useEconomicProfileStore } from '../store/economicProfileStore'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AssetMixSpec {
  turbine_rated_mw:   number
  bess_rated_mwh:     number
  bess_rated_mw:      number
  label:              string
}

interface RunHistoryEntry {
  run_id:              string
  label:               string
  duration_hours:      number
  grid_import_mwh:     number
  generation_mwh:      number
  storage_charge_mwh:  number
  // AB2: Python §21.2 CostModelEngine result (PROTO-21-COST defaults).
  // Present for completed runs fetched from GET /runs/{id}/energy-summary.
  cost_breakdown?:     CostBreakdown
  cost_model_config?:  Record<string, number>
  turbine_rated_mw?:   number
}

interface CostBreakdown {
  grid_import_cost:          number
  generation_cost:           number
  storage_cost:              number
  total_cost:                number
  generation_duty_fraction:  number
  grid_fraction:             number
}

interface ScenarioResult {
  run_id:      string
  asset_label: string
  baseline:    CostBreakdown
  alternative: CostBreakdown
  cost_delta:  number
  cost_delta_pct: number
  grid_fraction_delta: number
}

interface ScenarioPlannerPageProps {
  runId: string | null
}

// ---------------------------------------------------------------------------
// §21.2 cost computation (mirrors core/cost_model.py PROTO-21-COST defaults)
//
// AB2: The Python CostModelEngine is now the authoritative §21.2 implementation.
// The completed-run cost_breakdown is fetched from GET /runs/{id}/energy-summary
// and surfaced via RunHistoryEntry.cost_breakdown.
//
// _computeCost is retained for the what-if surface only — it applies these
// constants to hypothetical asset-mix parameters (different turbine_rated_mw,
// bess_rated_mwh) against the energy totals of an actual completed run.
//
// IMPORTANT: these constants MUST stay in sync with core/cost_model.py
// _COST_CFG_DEFAULTS (PROTO-21-COST).  The test in test_step16_wiring.py
// (test_energy_summary_includes_cost_breakdown) guards this via the
// cost_model_config key in the energy-summary response.
// ---------------------------------------------------------------------------

const COST_CONFIG = {
  grid_import_price_per_mwh:      120.0,  // GBP/MWh  (PROTO-21-COST)
  turbine_capital_per_mw_year:  45000.0,  // GBP/MW/year — amortised debt service
  turbine_variable_per_mwh:       55.0,   // GBP/MWh variable O&M
  storage_roundtrip_efficiency:    0.88,
  storage_charge_price_per_mwh:   60.0,
  storage_discharge_price_per_mwh: 0.0,
}

function _computeCost(
  entry: RunHistoryEntry,
  mix: AssetMixSpec,
): CostBreakdown {
  const c = COST_CONFIG
  const gridCost  = entry.grid_import_mwh * c.grid_import_price_per_mwh

  const dutyFrac  = mix.turbine_rated_mw > 0 && entry.duration_hours > 0
    ? Math.min(1.0, entry.generation_mwh / (mix.turbine_rated_mw * entry.duration_hours))
    : 0.0

  const capital   = c.turbine_capital_per_mw_year * mix.turbine_rated_mw * (entry.duration_hours / 8760)
  const genCost   = capital + entry.generation_mwh * c.turbine_variable_per_mwh

  const lossKwh   = entry.storage_charge_mwh * (1 - c.storage_roundtrip_efficiency)
  const storageCost = entry.storage_charge_mwh * c.storage_charge_price_per_mwh
                    + lossKwh * c.storage_discharge_price_per_mwh

  const totalMwh  = entry.grid_import_mwh + entry.generation_mwh
  const gridFrac  = totalMwh > 0 ? entry.grid_import_mwh / totalMwh : 0

  return {
    grid_import_cost: +gridCost.toFixed(2),
    generation_cost:  +genCost.toFixed(2),
    storage_cost:     +storageCost.toFixed(2),
    total_cost:       +(gridCost + genCost + storageCost).toFixed(2),
    generation_duty_fraction: +dutyFrac.toFixed(4),
    grid_fraction:    +gridFrac.toFixed(4),
  }
}

// ---------------------------------------------------------------------------
// Asset mix options (what-if parameterisation)
// ---------------------------------------------------------------------------

const ASSET_MIXES: AssetMixSpec[] = [
  { turbine_rated_mw: 20.0, bess_rated_mwh: 4.0,  bess_rated_mw: 4.0,  label: 'Baseline (20 MW turbine + 4 MWh BESS)' },
  { turbine_rated_mw: 20.0, bess_rated_mwh: 10.0, bess_rated_mw: 6.0,  label: '+BESS (20 MW turbine + 10 MWh BESS)' },
  { turbine_rated_mw: 30.0, bess_rated_mwh: 4.0,  bess_rated_mw: 4.0,  label: '+Turbine (30 MW turbine + 4 MWh BESS)' },
  { turbine_rated_mw: 15.0, bess_rated_mwh: 8.0,  bess_rated_mw: 6.0,  label: 'Smaller turbine + larger BESS' },
]

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ScenarioPlannerPage({ runId }: ScenarioPlannerPageProps) {
  // Live run history — fetched from /runs/{run_id}/energy-summary as runs complete.
  const [runs, setRuns] = useState<RunHistoryEntry[]>([])
  const [fetchingIds, setFetchingIds] = useState<Set<string>>(new Set())
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const [selectedRunIdx, setSelectedRunIdx] = useState(0)
  const [baselineMixIdx, setBaselineMixIdx] = useState(0)
  const [altMixIdx,      setAltMixIdx]      = useState(1)
  const [result, setResult] = useState<ScenarioResult | null>(null)

  // ── §30 Margin Contribution Tool state ────────────────────────────────
  const [economicModalOpen, setEconomicModalOpen] = useState(false)
  const [reportRunId, setReportRunId] = useState<string | null>(null)
  const econStore = useEconomicProfileStore()

  // Fetch economic profiles once on mount so the selector is populated.
  useEffect(() => {
    econStore.fetchProfiles()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // When runId changes, poll energy-summary until the run completes.
  // (409 = still active; 200 = sealed — add to history.)
  useEffect(() => {
    if (!runId) return
    if (fetchingIds.has(runId)) return

    setFetchingIds(prev => new Set([...prev, runId!]))

    let alive = true
    async function poll() {
      try {
        const r = await fetch(`/runs/${runId}/energy-summary`)
        if (!alive) return
        if (r.status === 409) return          // still active — keep polling
        if (!r.ok) {
          if (pollRef.current) clearInterval(pollRef.current)
          return
        }
        const entry: RunHistoryEntry = await r.json()
        setRuns(prev => {
          if (prev.some(e => e.run_id === entry.run_id)) return prev
          return [...prev, entry]
        })
        if (pollRef.current) clearInterval(pollRef.current)
      } catch { /* network error — keep polling */ }
    }

    pollRef.current = setInterval(poll, 3000)
    poll()   // immediate first attempt

    return () => {
      alive = false
      if (pollRef.current) clearInterval(pollRef.current)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId])

  const runScenario = useCallback(() => {
    if (runs.length === 0) return
    const idx   = Math.min(selectedRunIdx, runs.length - 1)
    const entry    = runs[idx]
    const baseline = _computeCost(entry, ASSET_MIXES[baselineMixIdx])
    const alt      = _computeCost(entry, ASSET_MIXES[altMixIdx])
    const delta    = alt.total_cost - baseline.total_cost
    const deltaPct = baseline.total_cost > 0 ? delta / baseline.total_cost * 100 : 0

    setResult({
      run_id:      entry.run_id,
      asset_label: ASSET_MIXES[altMixIdx].label,
      baseline,
      alternative: alt,
      cost_delta:      +delta.toFixed(2),
      cost_delta_pct:  +deltaPct.toFixed(2),
      grid_fraction_delta: +(alt.grid_fraction - baseline.grid_fraction).toFixed(4),
    })
  }, [runs, selectedRunIdx, baselineMixIdx, altMixIdx])

  const deltaColour = result
    ? (result.cost_delta < 0 ? '#22c55e' : result.cost_delta > 0 ? '#ef4444' : '#94a3b8')
    : '#94a3b8'

  return (
    <div style={{ padding: '24px', fontFamily: 'monospace', color: '#e2e8f0', background: '#0f172a', minHeight: '100%' }}>

      {/* ── Header ── */}
      <div style={{ marginBottom: '24px' }}>
        <h2 style={{ margin: 0, fontSize: '18px', color: '#f1f5f9' }}>
          §19.1 Scenario Planner
        </h2>
        <p style={{ margin: '4px 0 0', fontSize: '12px', color: '#64748b' }}>
          §18.5 FR-4.4 · What-if over actual run history · Commits nothing
        </p>
      </div>

      {/* ── Controls ── */}
      <div style={{ background: '#1e293b', borderRadius: '8px', padding: '16px', marginBottom: '16px' }}>
        <div style={{ fontSize: '11px', color: '#94a3b8', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
          Scenario Parameters
        </div>

        {runs.length === 0 ? (
          <div style={{ color: '#475569', fontSize: '12px', padding: '8px 0' }}>
            {runId
              ? 'Waiting for run to complete — energy summary will appear here.'
              : 'No completed runs yet. Start and finish a run to unlock scenario planning.'}
          </div>
        ) : (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px', marginBottom: '16px' }}>
              <div>
                <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>
                  Run History ({runs.length} completed)
                </label>
                <select
                  value={Math.min(selectedRunIdx, runs.length - 1)}
                  onChange={e => setSelectedRunIdx(+e.target.value)}
                  style={{ width: '100%', background: '#0f172a', color: '#e2e8f0', border: '1px solid #334155', borderRadius: '4px', padding: '6px', fontSize: '12px' }}
                >
                  {runs.map((r, i) => (
                    <option key={r.run_id} value={i}>{r.label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>
                  Baseline Asset Mix
                </label>
                <select
                  value={baselineMixIdx}
                  onChange={e => setBaselineMixIdx(+e.target.value)}
                  style={{ width: '100%', background: '#0f172a', color: '#e2e8f0', border: '1px solid #334155', borderRadius: '4px', padding: '6px', fontSize: '12px' }}
                >
                  {ASSET_MIXES.map((m, i) => (
                    <option key={i} value={i}>{m.label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>
                  Alternative Asset Mix
                </label>
                <select
                  value={altMixIdx}
                  onChange={e => setAltMixIdx(+e.target.value)}
                  style={{ width: '100%', background: '#0f172a', color: '#e2e8f0', border: '1px solid #334155', borderRadius: '4px', padding: '6px', fontSize: '12px' }}
                >
                  {ASSET_MIXES.map((m, i) => (
                    <option key={i} value={i}>{m.label}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* ── §30 Economics selector ── */}
            <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: 200 }}>
                <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>
                  Economic Profile (Margin Contribution)
                </label>
                <select
                  value={econStore.selectedProfileId ?? ''}
                  onChange={(e) => econStore.selectProfile(e.target.value || null)}
                  style={{ width: '100%', background: '#0f172a', color: '#e2e8f0', border: '1px solid #334155', borderRadius: '4px', padding: '6px', fontSize: '12px' }}
                >
                  <option value="">— no profile selected —</option>
                  {econStore.profiles.map((p) => (
                    <option key={p.profile_id} value={p.profile_id}>
                      {p.name}{p.proposed_here_count > 0 ? ` [${p.proposed_here_count} PROPOSED]` : ''}
                    </option>
                  ))}
                </select>
              </div>
              <button
                onClick={() => setEconomicModalOpen(true)}
                style={{
                  padding: '6px 13px', fontSize: '11px', cursor: 'pointer',
                  background: 'rgba(45,212,191,0.1)', color: '#2DD4BF',
                  border: '1px solid rgba(45,212,191,0.35)', borderRadius: '4px',
                  marginTop: '16px', whiteSpace: 'nowrap',
                }}
              >
                + Configure Economics
              </button>
            </div>

            <div style={{ display: 'flex', gap: 10 }}>
              <button
                onClick={runScenario}
                style={{
                  padding: '8px 20px', background: '#3b82f6', color: '#fff',
                  border: 'none', borderRadius: '4px', fontSize: '12px', cursor: 'pointer',
                  fontFamily: 'monospace',
                }}
              >
                Run Scenario →
              </button>
              {result && econStore.selectedProfileId && (
                <button
                  onClick={() => setReportRunId(reportRunId === result.run_id ? null : result.run_id)}
                  style={{
                    padding: '8px 16px', fontSize: '12px', cursor: 'pointer',
                    background: reportRunId === result.run_id
                      ? 'rgba(45,212,191,0.25)' : 'rgba(45,212,191,0.1)',
                    color: '#2DD4BF',
                    border: '1px solid rgba(45,212,191,0.35)', borderRadius: '4px',
                    fontFamily: 'monospace',
                  }}
                >
                  {reportRunId === result.run_id ? '▲ Hide Margin Report' : '▼ Show Margin Report'}
                </button>
              )}
            </div>
          </>
        )}
      </div>

      {/* ── Result ── */}
      {result && (
        <>
          {/* Cost delta hero */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px', marginBottom: '16px' }}>
            <div style={{ background: '#1e293b', borderRadius: '8px', padding: '16px', border: `1px solid ${deltaColour}` }}>
              <div style={{ fontSize: '11px', color: '#94a3b8', marginBottom: '6px', textTransform: 'uppercase' }}>Cost Delta</div>
              <div style={{ fontSize: '32px', fontWeight: 700, color: deltaColour }}>
                {result.cost_delta >= 0 ? '+' : ''}£{result.cost_delta.toFixed(0)}
              </div>
              <div style={{ fontSize: '11px', color: '#64748b' }}>
                {result.cost_delta_pct >= 0 ? '+' : ''}{result.cost_delta_pct.toFixed(1)}% vs baseline
              </div>
            </div>

            <div style={{ background: '#1e293b', borderRadius: '8px', padding: '16px' }}>
              <div style={{ fontSize: '11px', color: '#94a3b8', marginBottom: '6px', textTransform: 'uppercase' }}>Grid Fraction Δ</div>
              <div style={{ fontSize: '32px', fontWeight: 700, color: result.grid_fraction_delta < 0 ? '#22c55e' : '#f59e0b' }}>
                {result.grid_fraction_delta >= 0 ? '+' : ''}{(result.grid_fraction_delta * 100).toFixed(1)}pp
              </div>
              <div style={{ fontSize: '11px', color: '#64748b' }}>
                alt grid share: {(result.alternative.grid_fraction * 100).toFixed(1)}%
              </div>
            </div>

            <div style={{ background: '#1e293b', borderRadius: '8px', padding: '16px' }}>
              <div style={{ fontSize: '11px', color: '#94a3b8', marginBottom: '6px', textTransform: 'uppercase' }}>Turbine Duty Δ</div>
              <div style={{ fontSize: '32px', fontWeight: 700, color: '#cbd5e1' }}>
                {(result.alternative.generation_duty_fraction * 100).toFixed(1)}%
              </div>
              <div style={{ fontSize: '11px', color: '#64748b' }}>
                baseline: {(result.baseline.generation_duty_fraction * 100).toFixed(1)}% · §21.2 amortised capital
              </div>
            </div>
          </div>

          {/* Side-by-side breakdown */}
          <div style={{ background: '#1e293b', borderRadius: '8px', padding: '16px' }}>
            <div style={{ fontSize: '11px', color: '#94a3b8', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
              §21.2 Cost Breakdown — {result.run_id}
            </div>

            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #334155' }}>
                  <th style={{ textAlign: 'left', padding: '6px', color: '#94a3b8' }}>Cost stream</th>
                  <th style={{ textAlign: 'right', padding: '6px', color: '#94a3b8' }}>Baseline</th>
                  <th style={{ textAlign: 'right', padding: '6px', color: '#94a3b8' }}>Alternative</th>
                  <th style={{ textAlign: 'right', padding: '6px', color: '#94a3b8' }}>Δ</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ['Grid import', result.baseline.grid_import_cost, result.alternative.grid_import_cost],
                  ['Generation (capital + var)', result.baseline.generation_cost, result.alternative.generation_cost],
                  ['Storage round-trip', result.baseline.storage_cost, result.alternative.storage_cost],
                  ['Total', result.baseline.total_cost, result.alternative.total_cost],
                ].map(([label, base, alt], i) => {
                  const d = (alt as number) - (base as number)
                  const isTotal = i === 3
                  return (
                    <tr key={label as string} style={{ borderBottom: isTotal ? 'none' : '1px solid #1e293b', fontWeight: isTotal ? 700 : 400 }}>
                      <td style={{ padding: '6px', color: '#cbd5e1' }}>{label as string}</td>
                      <td style={{ textAlign: 'right', padding: '6px', color: '#94a3b8' }}>£{(base as number).toFixed(2)}</td>
                      <td style={{ textAlign: 'right', padding: '6px', color: '#94a3b8' }}>£{(alt as number).toFixed(2)}</td>
                      <td style={{ textAlign: 'right', padding: '6px', color: d < 0 ? '#22c55e' : d > 0 ? '#ef4444' : '#94a3b8' }}>
                        {d >= 0 ? '+' : ''}£{d.toFixed(2)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {!result && runs.length > 0 && (
        <div style={{ textAlign: 'center', padding: '48px', color: '#475569', fontSize: '14px' }}>
          Select a run and two asset mixes, then click <strong>Run Scenario →</strong>
        </div>
      )}

      {/* ── §30 Margin Contribution Report ── */}
      {reportRunId && econStore.selectedProfileId && (
        <MarginContributionReport
          runId={reportRunId}
          profileId={econStore.selectedProfileId}
          profileName={econStore.selectedProfile?.name}
          scenarioName={result?.run_id}
        />
      )}

      <div style={{ marginTop: '16px', fontSize: '11px', color: '#475569', textAlign: 'center' }}>
        §21.2 workstream-3 cost model · Turbine cost = amortised capital vs duty cycle · Commits nothing
      </div>

      {/* ── §30 Economic Profile modal ── */}
      {economicModalOpen && (
        <EconomicProfileModal
          onClose={() => setEconomicModalOpen(false)}
          editProfileId={econStore.selectedProfileId}
        />
      )}
    </div>
  )
}
