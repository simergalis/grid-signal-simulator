/**
 * PowerManagementModal.tsx — SWITCHGEAR / PMS power management configuration.
 *
 * Opens when the operator clicks the SWITCHGEAR / PMS plant-diagram node.
 *
 * Three tabs:
 *   1. Dispatch Authority — site operating tier, per-source authority tiers,
 *                          EDL TOU calendar month
 *   2. TOU Reference     — PG&E B-20 rate table (read-only)
 *   3. Operator Profile  — OperatorResponseProfile editor for PMSTestDouble
 *
 * Data flow:
 *   Reads selectedSpec from useScenarioStore; saves back via updateScenario.
 *   Local state is initialised from the spec on open; changes are not applied
 *   until the operator clicks "Save to scenario".
 *
 * Advisory boundary (GS-IMPL-PSP-002 §6.1):
 *   GridSignal never issues southbound writes.  Operating tier and authority tiers
 *   configure the advisory dispatch loop only — the PMS and operator remain the
 *   authoritative decision-makers for all physical switching actions.
 */

import { useState, useEffect, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { useScenarioStore } from '../store/scenarioStore'
import type { AuthorityTier, OperatingTier, OperatorProfileSpec, ScenarioSpec } from '../types'

// ── TOU constants (PG&E B-20, Cal. PUC Sheet 61081-E, eff. March 1, 2026) ──────

const TOU_SUMMER = [
  { period: 'Peak',       hours: '12 pm – 6 pm (daily)',      rate: 177.02, note: 'Jun – Sep' },
  { period: 'Part-peak',  hours: '2–4 pm · 9–11 pm (daily)', rate: 142.27, note: 'Jun – Sep' },
  { period: 'Off-peak',   hours: 'All other hours',           rate: 114.82, note: 'Jun – Sep' },
] as const

const TOU_WINTER = [
  { period: 'Peak',           hours: '4 pm – 9 pm (daily)',   rate: 156.32, note: 'Oct – May' },
  { period: 'Super off-peak', hours: '9 am – 2 pm (daily)',   rate:  58.72, note: 'Mar – May only' },
  { period: 'Off-peak',       hours: 'All other hours',       rate: 114.60, note: 'Oct – May' },
] as const

const BESS_MARGINAL_COST = 38.0

const MONTHS = [
  'January','February','March','April','May','June',
  'July','August','September','October','November','December',
]

// ── Operating tier options ────────────────────────────────────────────────────────

const OPERATING_TIERS: { value: OperatingTier; label: string; desc: string; color: string }[] = [
  {
    value: 'advisory',
    label: 'Advisory',
    desc: 'All recommendations require human approval before any action. No autonomous dispatch.',
    color: 'text-orange-400 border-orange-400/40 bg-orange-400/5',
  },
  {
    value: 'supervised',
    label: 'Supervised',
    desc: 'Autonomous dispatch within pre-approved limits. Deviations require confirmation.',
    color: 'text-yellow-400 border-yellow-400/40 bg-yellow-400/5',
  },
  {
    value: 'autonomous',
    label: 'Autonomous',
    desc: 'Full GridSignal autonomous dispatch. No per-action operator approval required.',
    color: 'text-accent border-accent/40 bg-accent/5',
  },
]

// ── Authority tier options ────────────────────────────────────────────────────────

const AUTHORITY_TIERS: { value: AuthorityTier; label: string; short: string; desc: string }[] = [
  {
    value: 'autonomous',
    label: 'Autonomous',
    short: 'Auto',
    desc: 'EDL dispatches without operator action (§23.4 Tier A)',
  },
  {
    value: 'confirm',
    label: 'Confirm',
    short: 'Confirm',
    desc: 'Operator/PMS must confirm before dispatch — shortfall escalated',
  },
  {
    value: 'human_only',
    label: 'Human only',
    short: 'Human',
    desc: 'Operator commands directly — always escalated on shortfall',
  },
]

// ── Source row types ──────────────────────────────────────────────────────────────

interface EditableSourceRow {
  key: string          // unique identifier
  label: string
  type: string
  ratedMw?: number
  tier: AuthorityTier
  editable: boolean    // false for solar (always excluded)
}

function sourcesFromSpec(spec: ScenarioSpec): EditableSourceRow[] {
  const rows: EditableSourceRow[] = []
  spec.bess_units.forEach(b => rows.push({
    key: `bess-${b.asset_id}`,
    label: b.asset_id,
    type: 'BESS',
    ratedMw: b.rated_mw,
    tier: (b.authority_tier as AuthorityTier | undefined) ?? 'autonomous',
    editable: true,
  }))
  spec.turbine_units.forEach(t => rows.push({
    key: `turb-${t.asset_id}`,
    label: t.asset_id,
    type: 'Gas Turbine',
    ratedMw: t.rated_mw,
    tier: (t.authority_tier as AuthorityTier | undefined) ?? 'autonomous',
    editable: true,
  }))
  if (spec.fuel_cell_enabled) rows.push({
    key: 'fuel-cell',
    label: 'Fuel Cell Array',
    type: 'Fuel Cell',
    ratedMw: (spec.fuel_cell_rated_mw ?? 1.8) * (spec.fuel_cell_stack_count ?? 3),
    tier: 'confirm',
    editable: false,  // advisory-only in this build
  })
  if (!spec.island_mode) rows.push({
    key: 'grid',
    label: 'Grid Connection',
    type: 'Grid',
    ratedMw: undefined,
    tier: 'confirm',
    editable: false,  // grid authority managed by PMS via GridConnectionModal
  })
  if (spec.solar_rated_mw > 0) rows.push({
    key: 'solar',
    label: 'Solar PV',
    type: 'Solar',
    ratedMw: spec.solar_rated_mw,
    tier: 'autonomous',
    editable: false,  // solar is always excluded from EDL ranking — not configurable
  })
  return rows
}

// ── Tab type ────────────────────────────────────────────────────────────────────

type Tab = 'authority' | 'tou' | 'profile'

// ── Default OperatorProfileSpec ──────────────────────────────────────────────────

const DEFAULT_PROFILE: OperatorProfileSpec = {
  response_latency_s: { 1: 30, 2: 30, 3: 30 },
  approve: { 1: true, 2: true, 3: true },
  default_latency_s: 30,
  default_approve: true,
}

// ═══════════════════════════════════════════════════════════════════════════════
// Main component
// ═══════════════════════════════════════════════════════════════════════════════

interface PowerManagementModalProps {
  onClose: () => void
}

export function PowerManagementModal({ onClose }: PowerManagementModalProps) {
  const { selectedId, selectedSpec, updateScenario, setSelectedSpec } = useScenarioStore()

  const [tab, setTab] = useState<Tab>('authority')
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState<string | null>(null)

  // ── Local editable state, initialised from selectedSpec ──────────────────────
  const [operatingTier, setOperatingTier] = useState<OperatingTier>(
    () => (selectedSpec?.operating_tier as OperatingTier | undefined) ?? 'supervised'
  )
  const [edlMonth, setEdlMonth] = useState<number>(
    () => selectedSpec?.edl_calendar_month ?? new Date().getMonth() + 1
  )
  // Map: sourceKey → AuthorityTier (editable sources only)
  const [sourceTiers, setSourceTiers] = useState<Record<string, AuthorityTier>>(() => {
    if (!selectedSpec) return {}
    const map: Record<string, AuthorityTier> = {}
    selectedSpec.bess_units.forEach(b => {
      map[`bess-${b.asset_id}`] = (b.authority_tier as AuthorityTier | undefined) ?? 'autonomous'
    })
    selectedSpec.turbine_units.forEach(t => {
      map[`turb-${t.asset_id}`] = (t.authority_tier as AuthorityTier | undefined) ?? 'autonomous'
    })
    return map
  })
  const [profile, setProfile] = useState<OperatorProfileSpec>(
    () => selectedSpec?.operator_response_profile ?? DEFAULT_PROFILE
  )

  // Sync if spec changes while modal is open
  useEffect(() => {
    if (!selectedSpec) return
    setOperatingTier((selectedSpec.operating_tier as OperatingTier | undefined) ?? 'supervised')
    setEdlMonth(selectedSpec.edl_calendar_month ?? new Date().getMonth() + 1)
    const map: Record<string, AuthorityTier> = {}
    selectedSpec.bess_units.forEach(b => {
      map[`bess-${b.asset_id}`] = (b.authority_tier as AuthorityTier | undefined) ?? 'autonomous'
    })
    selectedSpec.turbine_units.forEach(t => {
      map[`turb-${t.asset_id}`] = (t.authority_tier as AuthorityTier | undefined) ?? 'autonomous'
    })
    setSourceTiers(map)
    setProfile(selectedSpec.operator_response_profile ?? DEFAULT_PROFILE)
  }, [selectedId])

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  // ── Build the updated spec ───────────────────────────────────────────────────
  const buildUpdatedSpec = useCallback((): ScenarioSpec | null => {
    if (!selectedSpec) return null
    return {
      ...selectedSpec,
      operating_tier: operatingTier,
      edl_calendar_month: edlMonth,
      operator_response_profile: profile,
      bess_units: selectedSpec.bess_units.map(b => ({
        ...b,
        authority_tier: sourceTiers[`bess-${b.asset_id}`] ?? b.authority_tier ?? 'autonomous',
      })),
      turbine_units: selectedSpec.turbine_units.map(t => ({
        ...t,
        authority_tier: sourceTiers[`turb-${t.asset_id}`] ?? t.authority_tier ?? 'autonomous',
      })),
    }
  }, [selectedSpec, operatingTier, edlMonth, profile, sourceTiers])

  const handleSave = async () => {
    if (!selectedId || !selectedSpec) return
    const updated = buildUpdatedSpec()
    if (!updated) return
    setSaving(true)
    setSaveMsg(null)
    try {
      await updateScenario(selectedId, updated)
      setSelectedSpec(updated)
      setSaveMsg('Saved.')
      setTimeout(() => setSaveMsg(null), 2000)
    } catch (err) {
      setSaveMsg(`Save failed: ${err instanceof Error ? err.message : 'unknown error'}`)
    } finally {
      setSaving(false)
    }
  }

  const sources = selectedSpec ? sourcesFromSpec(selectedSpec) : []
  const hasScenario = !!selectedId && !!selectedSpec

  // ── Season badge for current edl month ──────────────────────────────────────
  const isSummer = edlMonth >= 6 && edlMonth <= 9
  const seasonLabel = isSummer ? 'Summer (Jun–Sep)' : 'Winter (Oct–May)'
  const isSuperOffPeak = !isSummer && edlMonth >= 3 && edlMonth <= 5

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-[2px]"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        className="relative flex flex-col bg-[#0d1117] border border-border rounded-lg shadow-2xl
                   w-full max-w-2xl max-h-[90vh] overflow-hidden"
        style={{ fontFamily: 'ui-monospace, monospace' }}
      >
        {/* ── Header ──────────────────────────────────────────────────────── */}
        <div className="flex items-start justify-between px-5 pt-5 pb-3 border-b border-border">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold tracking-[0.15em] uppercase"
                    style={{ color: '#3fb6a8' }}>
                ⚡ SWITCHGEAR / PMS
              </span>
            </div>
            <h2 className="text-sm font-semibold text-text mt-0.5">
              Power Management Configuration
            </h2>
            <p className="text-[9px] text-muted mt-0.5 leading-snug max-w-md">
              Advisory boundary: GridSignal never issues southbound writes.
              Authority tiers configure the dispatch advisory loop only —
              the PMS and operator retain physical switching authority (§6.1).
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-muted hover:text-text text-lg leading-none mt-0.5 ml-4 flex-shrink-0"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {/* ── Tabs ────────────────────────────────────────────────────────── */}
        <div className="flex gap-0 border-b border-border px-5 pt-2">
          {([
            { id: 'authority', label: 'Dispatch Authority' },
            { id: 'tou',       label: 'TOU Reference' },
            { id: 'profile',   label: 'Operator Profile' },
          ] as { id: Tab; label: string }[]).map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={[
                'px-4 py-2 text-[11px] font-semibold border-b-2 transition-colors -mb-px',
                tab === t.id
                  ? 'border-accent text-accent'
                  : 'border-transparent text-muted hover:text-text',
              ].join(' ')}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* ── Tab content (scrollable) ─────────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">

          {/* ─────────────────── TAB 1: DISPATCH AUTHORITY ──────────────────── */}
          {tab === 'authority' && (
            <>
              {!hasScenario && (
                <div className="rounded border border-border bg-canvas px-3 py-2 text-[10px] text-muted">
                  No scenario selected. Select a scenario to configure authority tiers.
                </div>
              )}

              {/* Operating tier */}
              <div>
                <h3 className="text-[10px] font-bold tracking-wider uppercase text-muted mb-2">
                  Site Operating Tier · §23.4 Ladder A
                </h3>
                <div className="space-y-2">
                  {OPERATING_TIERS.map(opt => {
                    const active = operatingTier === opt.value
                    return (
                      <button
                        key={opt.value}
                        onClick={() => setOperatingTier(opt.value)}
                        className={[
                          'w-full flex items-start gap-3 rounded border px-3 py-2.5 text-left transition-colors',
                          active ? opt.color : 'border-border text-muted bg-canvas hover:border-border/80',
                        ].join(' ')}
                      >
                        <div className={`mt-0.5 w-3 h-3 rounded-full border-2 flex-shrink-0 transition-colors
                          ${active ? 'border-current bg-current' : 'border-muted bg-transparent'}`}
                        />
                        <div>
                          <div className={`text-[11px] font-semibold ${active ? '' : 'text-text'}`}>
                            {opt.label}
                          </div>
                          <div className={`text-[9px] leading-snug mt-0.5 ${active ? 'opacity-80' : 'text-muted'}`}>
                            {opt.desc}
                          </div>
                        </div>
                      </button>
                    )
                  })}
                </div>
              </div>

              {/* Divider */}
              <div className="border-t border-border" />

              {/* EDL calendar month */}
              <div>
                <h3 className="text-[10px] font-bold tracking-wider uppercase text-muted mb-2">
                  TOU Calendar Month · EDL Dispatch Pricing
                </h3>
                <div className="flex items-center gap-3">
                  <select
                    className="rounded border border-border bg-canvas px-2 py-1.5 text-xs text-text
                               focus:outline-none focus:ring-1 focus:ring-accent flex-shrink-0"
                    value={edlMonth}
                    onChange={e => setEdlMonth(Number(e.target.value))}
                  >
                    {MONTHS.map((m, i) => (
                      <option key={i + 1} value={i + 1}>{m}</option>
                    ))}
                  </select>
                  <div>
                    <span className="text-[10px] font-mono" style={{ color: '#3fb6a8' }}>
                      {seasonLabel}{isSuperOffPeak && ' · Super off-peak eligible'}
                    </span>
                    <p className="text-[9px] text-muted mt-0.5 leading-snug">
                      Season used by EconomicDispatchLoop.step() for PG&amp;E B-20 TOU pricing.
                      Defaults to the current calendar month if unset.
                    </p>
                  </div>
                </div>
              </div>

              {/* Divider */}
              <div className="border-t border-border" />

              {/* Per-source authority tiers */}
              <div>
                <h3 className="text-[10px] font-bold tracking-wider uppercase text-muted mb-2">
                  Per-Source Dispatch Authority · §2.1 / §6.3
                </h3>
                {sources.length === 0 ? (
                  <p className="text-[9px] text-muted">
                    No power sources configured in the selected scenario.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {sources.map(src => {
                      const tier = src.editable
                        ? (sourceTiers[src.key] ?? src.tier)
                        : src.tier
                      const tierInfo = AUTHORITY_TIERS.find(a => a.value === tier)
                      return (
                        <div
                          key={src.key}
                          className="rounded border border-border bg-canvas p-2.5"
                        >
                          <div className="flex items-center justify-between mb-2">
                            <div>
                              <span className="text-[11px] font-mono text-text">{src.label}</span>
                              <span className="ml-2 text-[9px] text-muted">{src.type}</span>
                              {src.ratedMw !== undefined && (
                                <span className="ml-2 text-[9px] font-mono text-muted">
                                  {src.type === 'Solar' ? 'rated ' : ''}{src.ratedMw.toFixed(1)} MW
                                </span>
                              )}
                            </div>
                            {!src.editable && (
                              <span className="text-[9px] text-muted italic">
                                {src.type === 'Solar' ? 'Always excluded' : 'Managed by PMS'}
                              </span>
                            )}
                          </div>
                          {src.editable ? (
                            <div className="grid grid-cols-3 gap-1">
                              {AUTHORITY_TIERS.map(opt => {
                                const active = tier === opt.value
                                return (
                                  <button
                                    key={opt.value}
                                    onClick={() => setSourceTiers(prev => ({
                                      ...prev, [src.key]: opt.value,
                                    }))}
                                    title={opt.desc}
                                    className={[
                                      'flex flex-col items-center py-1.5 rounded border text-[9px]',
                                      'leading-tight transition-colors',
                                      active
                                        ? 'border-accent bg-accent/10 text-accent font-semibold'
                                        : 'border-border text-muted hover:border-accent/40',
                                    ].join(' ')}
                                  >
                                    <span>{opt.short}</span>
                                    <span className="opacity-60 text-[8px] mt-0.5 text-center leading-tight">
                                      {opt.value === 'autonomous' ? 'EDL dispatches'
                                        : opt.value === 'confirm' ? 'Needs approval'
                                        : 'Manual only'}
                                    </span>
                                  </button>
                                )
                              })}
                            </div>
                          ) : (
                            <div className="flex items-center gap-2 px-1">
                              <span className={[
                                'text-[9px] font-mono px-2 py-0.5 rounded border',
                                src.type === 'Solar'
                                  ? 'border-border text-muted'
                                  : 'border-border text-muted',
                              ].join(' ')}>
                                {tierInfo?.label ?? tier}
                              </span>
                              <span className="text-[9px] text-muted">{tierInfo?.desc}</span>
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            </>
          )}

          {/* ─────────────────── TAB 2: TOU REFERENCE ───────────────────────── */}
          {tab === 'tou' && (
            <>
              <div className="text-[9px] text-muted leading-relaxed">
                PG&amp;E Schedule B-20 (secondary voltage) · Cal. PUC Sheet No. 61081-E, eff. March 1, 2026.
                Energy-only component; demand charges excluded. Source: GS-IMPL-PSP-002 §7.
                <br />
                Rates are read-only catalogue values. Modify in{' '}
                <code className="text-text">gridsignal_parameters.json</code>.
              </div>

              {/* Summer table */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <h3 className="text-[10px] font-bold tracking-wider uppercase"
                      style={{ color: '#f0a500' }}>
                    Summer Season
                  </h3>
                  <span className="text-[9px] text-muted">June – September</span>
                </div>
                <table className="w-full text-[10px] border-collapse">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left py-1.5 text-muted font-normal">Period</th>
                      <th className="text-left py-1.5 text-muted font-normal">Hours (local time)</th>
                      <th className="text-right py-1.5 text-muted font-normal">Rate ($/MWh)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {TOU_SUMMER.map(row => (
                      <tr key={row.period} className="border-b border-border/40">
                        <td className="py-2 font-mono text-text">{row.period}</td>
                        <td className="py-2 text-muted">{row.hours}</td>
                        <td className="py-2 text-right font-mono text-text tabular-nums">
                          {row.rate.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Winter table */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <h3 className="text-[10px] font-bold tracking-wider uppercase"
                      style={{ color: '#60a0c8' }}>
                    Winter Season
                  </h3>
                  <span className="text-[9px] text-muted">October – May</span>
                </div>
                <table className="w-full text-[10px] border-collapse">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left py-1.5 text-muted font-normal">Period</th>
                      <th className="text-left py-1.5 text-muted font-normal">Hours (local time)</th>
                      <th className="text-right py-1.5 text-muted font-normal">Rate ($/MWh)</th>
                      <th className="text-right py-1.5 text-muted font-normal">Applies</th>
                    </tr>
                  </thead>
                  <tbody>
                    {TOU_WINTER.map(row => (
                      <tr key={row.period} className="border-b border-border/40">
                        <td className="py-2 font-mono text-text">{row.period}</td>
                        <td className="py-2 text-muted">{row.hours}</td>
                        <td className="py-2 text-right font-mono text-text tabular-nums">
                          {row.rate.toFixed(2)}
                        </td>
                        <td className="py-2 text-right text-muted text-[9px]">{row.note}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* BESS reference */}
              <div className="rounded border border-border bg-canvas px-3 py-2.5">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-[10px] font-mono text-text">BESS marginal cost</span>
                    <p className="text-[9px] text-muted mt-0.5 leading-snug">
                      All-in capex per MWh (Ember Oct 2025, LFP utility-scale).
                      PSP-6 resolved. Replace with site contract before production.
                    </p>
                  </div>
                  <span className="text-sm font-mono font-bold tabular-nums"
                        style={{ color: '#3fb6a8' }}>
                    ${BESS_MARGINAL_COST.toFixed(2)}/MWh
                  </span>
                </div>
              </div>

              {/* Merit-order note */}
              <div className="rounded border border-border/50 bg-canvas/50 px-3 py-2 text-[9px] text-muted leading-relaxed">
                <strong className="text-text">Merit order (cheapest first):</strong>{' '}
                BESS (${BESS_MARGINAL_COST}/MWh) →
                Summer off-peak (${TOU_SUMMER[2].rate}) →
                Winter super off-peak (${TOU_WINTER[1].rate}) →
                Summer part-peak (${TOU_SUMMER[1].rate}) →
                Winter off-peak (${TOU_WINTER[2].rate}) →
                Winter peak (${TOU_WINTER[0].rate}) →
                Summer peak (${TOU_SUMMER[0].rate}).
                Solar is always excluded from EDL ranking (dispatchable = false).
              </div>
            </>
          )}

          {/* ─────────────────── TAB 3: OPERATOR PROFILE ────────────────────── */}
          {tab === 'profile' && (
            <>
              <div className="text-[9px] text-muted leading-relaxed">
                OperatorResponseProfile consumed by PMSTestDouble at simulator startup (§3.4).
                Generated offline by{' '}
                <code className="text-text">scripts/scenario_author.py</code>; this panel
                provides a visual editor for the JSON. Never used in a production harness
                (<code className="text-text">GS_PRODUCTION_HARNESS</code> set).
              </div>

              {/* Default behaviour */}
              <div>
                <h3 className="text-[10px] font-bold tracking-wider uppercase text-muted mb-2">
                  Default Behaviour
                </h3>
                <div className="grid grid-cols-2 gap-3">
                  <label className="flex flex-col gap-1">
                    <span className="text-[10px] text-muted">Default latency (s)</span>
                    <input
                      type="number"
                      min={0}
                      max={300}
                      step={5}
                      className="w-full rounded border border-border bg-canvas px-2 py-1.5 text-xs text-text
                                 focus:outline-none focus:ring-1 focus:ring-accent font-mono"
                      value={profile.default_latency_s ?? 30}
                      onChange={e => setProfile(p => ({
                        ...p, default_latency_s: Math.max(0, Number(e.target.value)),
                      }))}
                    />
                  </label>
                  <div className="flex flex-col gap-1">
                    <span className="text-[10px] text-muted">Default approve</span>
                    <div className="flex gap-2 pt-0.5">
                      {([true, false] as const).map(v => (
                        <button
                          key={String(v)}
                          onClick={() => setProfile(p => ({ ...p, default_approve: v }))}
                          className={[
                            'flex-1 py-1.5 rounded border text-[10px] font-mono transition-colors',
                            (profile.default_approve ?? true) === v
                              ? 'border-accent bg-accent/10 text-accent font-semibold'
                              : 'border-border text-muted hover:border-accent/40',
                          ].join(' ')}
                        >
                          {v ? 'Approve' : 'Reject'}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              {/* Per-rank overrides */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-[10px] font-bold tracking-wider uppercase text-muted">
                    Per-Rank Overrides (1 = cheapest ranked source)
                  </h3>
                  <button
                    className="text-[9px] text-accent hover:underline"
                    onClick={() => setProfile(DEFAULT_PROFILE)}
                  >
                    Reset to defaults
                  </button>
                </div>

                <table className="w-full text-[10px] border-collapse">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left py-1.5 text-muted font-normal w-16">Rank</th>
                      <th className="text-left py-1.5 text-muted font-normal">
                        Response latency (s)
                      </th>
                      <th className="text-center py-1.5 text-muted font-normal w-32">Decision</th>
                      <th className="text-right py-1.5 text-muted font-normal w-10">
                        <button
                          className="text-accent hover:underline"
                          title="Add rank override"
                          onClick={() => {
                            const existing = Object.keys(profile.response_latency_s ?? {}).map(Number)
                            const next = (Math.max(0, ...existing) + 1).toString()
                            setProfile(p => ({
                              ...p,
                              response_latency_s: { ...p.response_latency_s, [next]: p.default_latency_s ?? 30 },
                              approve: { ...p.approve, [next]: p.default_approve ?? true },
                            }))
                          }}
                        >
                          + Add
                        </button>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.keys(profile.response_latency_s ?? {})
                      .map(Number)
                      .sort((a, b) => a - b)
                      .map(rank => {
                        const latency = profile.response_latency_s[rank] ?? (profile.default_latency_s ?? 30)
                        const approved = profile.approve[rank] ?? (profile.default_approve ?? true)
                        return (
                          <tr key={rank} className="border-b border-border/40">
                            <td className="py-2 font-mono text-text">#{rank}</td>
                            <td className="py-2 pr-4">
                              <input
                                type="range"
                                min={0}
                                max={300}
                                step={5}
                                value={latency}
                                className="w-full accent-accent h-1"
                                onChange={e => setProfile(p => ({
                                  ...p,
                                  response_latency_s: { ...p.response_latency_s, [rank]: Number(e.target.value) },
                                }))}
                              />
                              <div className="flex justify-between text-[8px] text-muted mt-0.5">
                                <span>0 s</span>
                                <span className="font-mono text-text">{latency} s</span>
                                <span>300 s</span>
                              </div>
                            </td>
                            <td className="py-2 text-center">
                              <div className="flex gap-1 justify-center">
                                {([true, false] as const).map(v => (
                                  <button
                                    key={String(v)}
                                    onClick={() => setProfile(p => ({
                                      ...p, approve: { ...p.approve, [rank]: v },
                                    }))}
                                    className={[
                                      'px-2 py-0.5 rounded border text-[9px] font-mono transition-colors',
                                      approved === v
                                        ? v
                                          ? 'border-accent bg-accent/10 text-accent'
                                          : 'border-red-500/50 bg-red-500/10 text-red-400'
                                        : 'border-border text-muted hover:border-border/80',
                                    ].join(' ')}
                                  >
                                    {v ? 'Approve' : 'Reject'}
                                  </button>
                                ))}
                              </div>
                            </td>
                            <td className="py-2 text-right">
                              <button
                                className="text-[9px] text-muted hover:text-danger"
                                title="Remove rank override"
                                onClick={() => setProfile(p => {
                                  const { [rank]: _a, ...restLatency } = p.response_latency_s
                                  const { [rank]: _b, ...restApprove } = p.approve
                                  return { ...p, response_latency_s: restLatency, approve: restApprove }
                                })}
                              >
                                ×
                              </button>
                            </td>
                          </tr>
                        )
                      })}
                    {Object.keys(profile.response_latency_s ?? {}).length === 0 && (
                      <tr>
                        <td colSpan={4} className="py-3 text-center text-[9px] text-muted">
                          No rank overrides — all ranks use the defaults above.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              {/* JSON preview */}
              <div>
                <h3 className="text-[10px] font-bold tracking-wider uppercase text-muted mb-1">
                  JSON Preview
                </h3>
                <pre className="text-[9px] font-mono text-muted bg-canvas rounded border border-border
                               px-3 py-2 overflow-x-auto whitespace-pre-wrap">
                  {JSON.stringify(profile, null, 2)}
                </pre>
              </div>
            </>
          )}

        </div>

        {/* ── Footer: save + status ────────────────────────────────────────── */}
        <div className="border-t border-border px-5 py-3 flex items-center justify-between">
          <div className="text-[9px] text-muted">
            {hasScenario ? (
              <>
                Scenario: <span className="font-mono text-text">{selectedSpec?.name}</span>
              </>
            ) : (
              <span className="text-orange-400">No scenario selected — changes cannot be saved.</span>
            )}
          </div>
          <div className="flex items-center gap-3">
            {saveMsg && (
              <span className={`text-[10px] font-mono ${saveMsg.startsWith('Save failed') ? 'text-red-400' : 'text-accent'}`}>
                {saveMsg}
              </span>
            )}
            <button
              onClick={onClose}
              className="px-3 py-1.5 rounded border border-border text-[10px] text-muted
                         hover:border-text-muted transition-colors"
            >
              Close
            </button>
            <button
              onClick={handleSave}
              disabled={!hasScenario || saving}
              className="px-4 py-1.5 rounded border text-[10px] font-semibold transition-colors
                         border-accent bg-accent/10 text-accent hover:bg-accent/20
                         disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {saving ? 'Saving…' : 'Save to scenario'}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  )
}
