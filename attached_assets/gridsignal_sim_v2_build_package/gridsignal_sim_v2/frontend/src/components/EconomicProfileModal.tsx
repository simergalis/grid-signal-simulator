/**
 * EconomicProfileModal — §30 "Configure Economics" multi-field modal.
 *
 * Visual / interaction precedent: GpuNodeGeneratorModal.tsx (tabbed surface,
 * design tokens, modal overlay).
 *
 * Persistence: economicProfileStore.ts → POST/PUT /api/economic-profiles/*
 *   (NOT Zustand-only like gpuGeneratorStore — profiles survive server restarts).
 *
 * Two tabs:
 *   1. Cost Configuration — grid rates, turbine/BESS/solar capex, curtailment
 *   2. Tenant Billing — per-tenant billing basis, base rate, contracted
 *      allocation, overage rate (AC-2.5: no overage_rate → flat billing, no error)
 *
 * PROPOSED_HERE amber tag: operator can tag any field as a third-party estimate
 *   pending validation (AC-2.4).
 *
 * AC-2.6: after save + page reload the profile is still present (durable DB).
 *
 * Design tokens — same as MarginContributionReport.tsx and mockup.
 */

import { useState, useEffect } from 'react'
import { useEconomicProfileStore } from '../store/economicProfileStore'

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
} as const

const mono: React.CSSProperties = { fontFamily: "'IBM Plex Mono', monospace" }
const display: React.CSSProperties = { fontFamily: "'Space Grotesk', sans-serif" }

// Default conservative rate card values shown as placeholders (UI hints only —
// not fallback values used in calculation code; see standing rule in T1 prompt)
const DEFAULTS = {
  grid_peak_rate_per_mwh: 70,
  grid_offpeak_rate_per_mwh: 45,
  turbine_fuel_per_mwh: 35,
  turbine_capex_per_mwh: 15,
  bess_marginal_per_mwh: 5,
  bess_capex_per_mwh: 25,
  solar_capex_per_mwh: 12,
  curtailment_per_mwh: 40,
}

const TENANT_DEFS = [
  { tenant_id: 'A', scheduler: 'SLURM', color: '#3fb6a8' },
  { tenant_id: 'B', scheduler: 'Kubernetes', color: '#4a9fe0' },
  { tenant_id: 'C', scheduler: 'Ray', color: '#9b6fe0' },
]

type Tab = 'cost' | 'tenant'

interface CostFields {
  grid_peak_rate_per_mwh: string
  grid_offpeak_rate_per_mwh: string
  turbine_fuel_per_mwh: string
  turbine_capex_per_mwh: string
  bess_marginal_per_mwh: string
  bess_capex_per_mwh: string
  solar_capex_per_mwh: string
  curtailment_per_mwh: string
}

interface TenantFields {
  tenant_id: string
  billing_basis: string
  base_rate: string
  contracted_allocation: string
  overage_rate: string
}

function parseFlt(s: string): number | null {
  const v = parseFloat(s.replace(/,/g, ''))
  return isNaN(v) ? null : v
}

// ── PROPOSED_HERE tag toggle ───────────────────────────────────────────────
function ProposedTag({
  fieldName,
  proposed,
  onToggle,
}: {
  fieldName: string
  proposed: string[]
  onToggle: (f: string) => void
}) {
  const active = proposed.includes(fieldName)
  return (
    <button
      onClick={() => onToggle(fieldName)}
      title={active ? 'Remove PROPOSED_HERE tag' : 'Tag as third-party estimate (PROPOSED_HERE)'}
      style={{
        fontSize: 9.5, fontWeight: 600, padding: '2px 6px', borderRadius: 4,
        cursor: 'pointer', letterSpacing: '.03em',
        ...(active
          ? { background: C.amberDim, color: C.amber, border: `1px solid rgba(245,165,36,0.35)` }
          : { background: 'rgba(92,113,145,0.15)', color: C.textFaint, border: 'none' }),
      }}
    >
      {active ? '● PROPOSED' : '○ PROPOSED'}
    </button>
  )
}

// ── Numeric input row ──────────────────────────────────────────────────────
function CostRow({
  label,
  unit,
  fieldName,
  value,
  onChange,
  proposed,
  onProposedToggle,
  placeholder,
}: {
  label: string
  unit: string
  fieldName: string
  value: string
  onChange: (v: string) => void
  proposed: string[]
  onProposedToggle: (f: string) => void
  placeholder: string
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
      <div style={{ flex: 1, fontSize: 12.5, color: C.textDim }}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <ProposedTag fieldName={fieldName} proposed={proposed} onToggle={onProposedToggle} />
        <div style={{ position: 'relative' }}>
          <input
            type="number"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={placeholder}
            step="0.01"
            min="0"
            style={{
              ...mono,
              width: 90, padding: '5px 8px',
              background: C.panel2, color: C.text,
              border: `1px solid ${C.border}`, borderRadius: 5,
              fontSize: 12, textAlign: 'right',
            }}
          />
        </div>
        <div style={{ fontSize: 11, color: C.textFaint, width: 60 }}>{unit}</div>
      </div>
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────
interface EconomicProfileModalProps {
  onClose: () => void
  /** If set, we're editing an existing profile; if null, we're creating new. */
  editProfileId?: string | null
}

export function EconomicProfileModal({ onClose, editProfileId }: EconomicProfileModalProps) {
  const store = useEconomicProfileStore()
  const [tab, setTab] = useState<Tab>('cost')
  const [name, setName] = useState('Conservative Rate Card')
  const [proposed, setProposed] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const [cost, setCost] = useState<CostFields>({
    grid_peak_rate_per_mwh: '',
    grid_offpeak_rate_per_mwh: '',
    turbine_fuel_per_mwh: '',
    turbine_capex_per_mwh: '',
    bess_marginal_per_mwh: '',
    bess_capex_per_mwh: '',
    solar_capex_per_mwh: '',
    curtailment_per_mwh: '',
  })

  const [tenants, setTenants] = useState<TenantFields[]>(
    TENANT_DEFS.map((t) => ({
      tenant_id: t.tenant_id,
      billing_basis: 'per_mwh_consumed',
      base_rate: '',
      contracted_allocation: '',
      overage_rate: '',
    }))
  )

  // Load existing profile for editing
  useEffect(() => {
    if (!editProfileId) return
    store.fetchSelectedProfile()
      .then(() => {
        const p = store.selectedProfile
        if (!p || p.profile_id !== editProfileId) return
        setName(p.name)
        setProposed(p.proposed_here_fields || [])
        setCost({
          grid_peak_rate_per_mwh: p.grid_peak_rate_per_mwh?.toString() ?? '',
          grid_offpeak_rate_per_mwh: p.grid_offpeak_rate_per_mwh?.toString() ?? '',
          turbine_fuel_per_mwh: p.turbine_fuel_per_mwh?.toString() ?? '',
          turbine_capex_per_mwh: p.turbine_capex_per_mwh?.toString() ?? '',
          bess_marginal_per_mwh: p.bess_marginal_per_mwh?.toString() ?? '',
          bess_capex_per_mwh: p.bess_capex_per_mwh?.toString() ?? '',
          solar_capex_per_mwh: p.solar_capex_per_mwh?.toString() ?? '',
          curtailment_per_mwh: p.curtailment_per_mwh?.toString() ?? '',
        })
        if (p.tenant_rates && p.tenant_rates.length > 0) {
          setTenants(
            TENANT_DEFS.map((td) => {
              const tr = p.tenant_rates?.find((r) => r.tenant_id === td.tenant_id)
              return tr
                ? {
                    tenant_id: td.tenant_id,
                    billing_basis: tr.billing_basis,
                    base_rate: tr.base_rate?.toString() ?? '',
                    contracted_allocation: tr.contracted_allocation?.toString() ?? '',
                    overage_rate: tr.overage_rate?.toString() ?? '',
                  }
                : { tenant_id: td.tenant_id, billing_basis: 'per_mwh_consumed', base_rate: '', contracted_allocation: '', overage_rate: '' }
            })
          )
        }
      })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editProfileId])

  const toggleProposed = (f: string) => {
    setProposed((prev) => prev.includes(f) ? prev.filter((x) => x !== f) : [...prev, f])
  }

  const updateTenant = (tid: string, field: keyof TenantFields, value: string) => {
    setTenants((prev) => prev.map((t) => t.tenant_id === tid ? { ...t, [field]: value } : t))
  }

  const handleSave = async () => {
    if (!name.trim()) { setSaveError('Profile name is required'); return }
    setSaving(true)
    setSaveError(null)
    try {
      const body = {
        name: name.trim(),
        grid_peak_rate_per_mwh: parseFlt(cost.grid_peak_rate_per_mwh),
        grid_offpeak_rate_per_mwh: parseFlt(cost.grid_offpeak_rate_per_mwh),
        turbine_fuel_per_mwh: parseFlt(cost.turbine_fuel_per_mwh),
        turbine_capex_per_mwh: parseFlt(cost.turbine_capex_per_mwh),
        bess_marginal_per_mwh: parseFlt(cost.bess_marginal_per_mwh),
        bess_capex_per_mwh: parseFlt(cost.bess_capex_per_mwh),
        solar_capex_per_mwh: parseFlt(cost.solar_capex_per_mwh),
        curtailment_per_mwh: parseFlt(cost.curtailment_per_mwh),
        proposed_here_fields: proposed,
        tenant_rates: tenants
          .filter((t) => parseFlt(t.base_rate) !== null)
          .map((t) => ({
            tenant_id: t.tenant_id,
            billing_basis: t.billing_basis,
            base_rate: parseFlt(t.base_rate) ?? 0,
            contracted_allocation: parseFlt(t.contracted_allocation) ?? 0,
            // AC-2.5: overage_rate absent → flat billing, no error (TC-MC-9)
            overage_rate: parseFlt(t.overage_rate),
          })),
      }
      if (editProfileId) {
        await store.updateProfile(editProfileId, body as never)
      } else {
        await store.createProfile(body as never)
      }
      onClose()
    } catch (e) {
      setSaveError(String(e))
    } finally {
      setSaving(false)
    }
  }

  const COST_FIELDS: Array<{
    label: string; unit: string; key: keyof CostFields; placeholder: number
  }> = [
    { label: 'Grid peak rate', unit: '$/MWh imported', key: 'grid_peak_rate_per_mwh', placeholder: DEFAULTS.grid_peak_rate_per_mwh },
    { label: 'Grid off-peak rate', unit: '$/MWh imported', key: 'grid_offpeak_rate_per_mwh', placeholder: DEFAULTS.grid_offpeak_rate_per_mwh },
    { label: 'Turbine fuel (variable)', unit: '$/MWh generated', key: 'turbine_fuel_per_mwh', placeholder: DEFAULTS.turbine_fuel_per_mwh },
    { label: 'Turbine amortised capital', unit: '$/MWh generated', key: 'turbine_capex_per_mwh', placeholder: DEFAULTS.turbine_capex_per_mwh },
    { label: 'BESS marginal (variable)', unit: '$/MWh dispatched', key: 'bess_marginal_per_mwh', placeholder: DEFAULTS.bess_marginal_per_mwh },
    { label: 'BESS amortised capital', unit: '$/MWh dispatched', key: 'bess_capex_per_mwh', placeholder: DEFAULTS.bess_capex_per_mwh },
    { label: 'Solar amortised capital', unit: '$/MWh generated', key: 'solar_capex_per_mwh', placeholder: DEFAULTS.solar_capex_per_mwh },
    { label: 'Curtailment SLA credit', unit: '$/MWh curtailed', key: 'curtailment_per_mwh', placeholder: DEFAULTS.curtailment_per_mwh },
  ]

  return (
    /* Overlay */
    <div
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 9000,
      }}
    >
      <div style={{
        background: C.panel, border: `1px solid ${C.border}`, borderRadius: 14,
        width: 680, maxHeight: '88vh', display: 'flex', flexDirection: 'column',
        boxShadow: '0 24px 64px rgba(0,0,0,0.5)',
      }}>
        {/* ── Modal header ── */}
        <div style={{
          padding: '18px 22px', borderBottom: `1px solid ${C.border}`,
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <div>
            <div style={{ ...display, fontWeight: 600, fontSize: 16, color: C.text }}>
              {editProfileId ? 'Edit' : 'New'} Economic Profile
            </div>
            <div style={{ fontSize: 12, color: C.textFaint, marginTop: 3 }}>
              Configure energy cost estimates and tenant billing rates
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: C.textFaint, fontSize: 20, cursor: 'pointer', padding: '0 4px' }}
          >
            ×
          </button>
        </div>

        {/* ── Profile name ── */}
        <div style={{ padding: '14px 22px 0', borderBottom: `1px solid ${C.borderSoft}` }}>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Profile name…"
            style={{
              width: '100%', padding: '8px 12px', marginBottom: 14,
              background: C.panel2, color: C.text,
              border: `1px solid ${C.border}`, borderRadius: 7, fontSize: 13,
            }}
          />
        </div>

        {/* ── Tabs ── */}
        <div style={{ display: 'flex', padding: '0 22px', borderBottom: `1px solid ${C.border}`, background: C.panel2 }}>
          {[['cost', 'Cost Configuration'] as const, ['tenant', 'Tenant Billing'] as const].map(([t, label]) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              style={{
                padding: '10px 16px', fontSize: 12.5, fontWeight: 500,
                border: 'none', background: 'none', cursor: 'pointer',
                borderBottom: tab === t ? `2px solid ${C.teal}` : '2px solid transparent',
                color: tab === t ? C.teal : C.textDim,
                marginBottom: -1,
              }}
            >
              {label}
            </button>
          ))}
        </div>

        {/* ── Tab content (scrollable) ── */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '18px 22px' }}>

          {/* ── Cost Configuration tab ── */}
          {tab === 'cost' && (
            <div>
              <div style={{ fontSize: 11, color: C.textFaint, marginBottom: 16, lineHeight: 1.5 }}>
                All fields are optional. Empty fields contribute $0 to the calculation — not a default rate.
                Click <b style={{ color: C.amber }}>● PROPOSED</b> to tag a field as a third-party estimate
                pending validation (shown as amber in the report).
              </div>
              {COST_FIELDS.map(({ label, unit, key, placeholder }) => (
                <CostRow
                  key={key}
                  label={label}
                  unit={unit}
                  fieldName={key}
                  value={cost[key]}
                  onChange={(v) => setCost((prev) => ({ ...prev, [key]: v }))}
                  proposed={proposed}
                  onProposedToggle={toggleProposed}
                  placeholder={placeholder.toString()}
                />
              ))}
            </div>
          )}

          {/* ── Tenant Billing tab ── */}
          {tab === 'tenant' && (
            <div>
              <div style={{ fontSize: 11, color: C.textFaint, marginBottom: 16, lineHeight: 1.5 }}>
                Configure per-tenant billing. Overage rate is optional — a tenant without an overage rate
                bills at base rate only with no error (AC-2.5 / TC-MC-9).
              </div>
              {TENANT_DEFS.map((td) => {
                const tf = tenants.find((t) => t.tenant_id === td.tenant_id)!
                return (
                  <div
                    key={td.tenant_id}
                    style={{
                      background: C.panel2, border: `1px solid ${C.borderSoft}`,
                      borderRadius: 9, padding: '14px 16px', marginBottom: 12,
                      borderLeft: `3px solid ${td.color}`,
                    }}
                  >
                    <div style={{ fontSize: 13, fontWeight: 600, color: C.text, marginBottom: 12 }}>
                      Tenant {td.tenant_id}
                      <span style={{ fontSize: 10.5, color: C.textFaint, marginLeft: 8 }}>
                        {td.scheduler}
                      </span>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px 16px' }}>
                      <div>
                        <label style={{ fontSize: 11, color: C.textFaint, display: 'block', marginBottom: 4 }}>
                          Billing basis
                        </label>
                        <select
                          value={tf.billing_basis}
                          onChange={(e) => updateTenant(td.tenant_id, 'billing_basis', e.target.value)}
                          style={{
                            width: '100%', padding: '5px 8px',
                            background: C.panel, color: C.text,
                            border: `1px solid ${C.border}`, borderRadius: 5, fontSize: 12,
                          }}
                        >
                          <option value="per_mw_committed">per-MW-committed</option>
                          <option value="per_mwh_consumed">per-MWh-consumed</option>
                          <option value="per_gpu_hour">per-GPU-hour</option>
                        </select>
                      </div>
                      <div>
                        <label style={{ fontSize: 11, color: C.textFaint, display: 'block', marginBottom: 4 }}>
                          Base rate ($/MWh or $/MW·mo)
                        </label>
                        <input
                          type="number" min="0" step="0.01"
                          value={tf.base_rate}
                          onChange={(e) => updateTenant(td.tenant_id, 'base_rate', e.target.value)}
                          placeholder="e.g. 95"
                          style={{ ...mono, width: '100%', padding: '5px 8px', background: C.panel, color: C.text, border: `1px solid ${C.border}`, borderRadius: 5, fontSize: 12 }}
                        />
                      </div>
                      <div>
                        <label style={{ fontSize: 11, color: C.textFaint, display: 'block', marginBottom: 4 }}>
                          Contracted allocation (MWh or MW)
                        </label>
                        <input
                          type="number" min="0" step="0.1"
                          value={tf.contracted_allocation}
                          onChange={(e) => updateTenant(td.tenant_id, 'contracted_allocation', e.target.value)}
                          placeholder="e.g. 10000"
                          style={{ ...mono, width: '100%', padding: '5px 8px', background: C.panel, color: C.text, border: `1px solid ${C.border}`, borderRadius: 5, fontSize: 12 }}
                        />
                      </div>
                      <div>
                        <label style={{ fontSize: 11, color: C.textFaint, display: 'block', marginBottom: 4 }}>
                          Overage rate ($/MWh) <span style={{ color: C.textFaint, fontStyle: 'italic' }}>optional</span>
                        </label>
                        <input
                          type="number" min="0" step="0.01"
                          value={tf.overage_rate}
                          onChange={(e) => updateTenant(td.tenant_id, 'overage_rate', e.target.value)}
                          placeholder="leave blank = flat rate"
                          style={{ ...mono, width: '100%', padding: '5px 8px', background: C.panel, color: C.text, border: `1px solid ${C.border}`, borderRadius: 5, fontSize: 12 }}
                        />
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* ── Footer ── */}
        <div style={{
          padding: '14px 22px', borderTop: `1px solid ${C.border}`,
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          {saveError && <div style={{ fontSize: 12, color: C.red, flex: 1, marginRight: 12 }}>{saveError}</div>}
          {!saveError && <div style={{ fontSize: 11.5, color: C.textFaint }}>
            {proposed.length > 0 && (
              <span>
                <b style={{ color: C.amber }}>{proposed.length} field{proposed.length > 1 ? 's' : ''}</b> tagged PROPOSED_HERE
              </span>
            )}
          </div>}
          <div style={{ display: 'flex', gap: 9 }}>
            <button
              onClick={onClose}
              style={{
                padding: '8px 16px', borderRadius: 7, border: `1px solid ${C.border}`,
                background: C.panel2, color: C.textDim, cursor: 'pointer', fontSize: 12.5,
              }}
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              style={{
                padding: '8px 18px', borderRadius: 7, border: 'none',
                background: C.teal, color: '#06231f', fontWeight: 600,
                cursor: saving ? 'not-allowed' : 'pointer', fontSize: 12.5,
                opacity: saving ? 0.7 : 1,
              }}
            >
              {saving ? 'Saving…' : editProfileId ? 'Update Profile' : 'Save Profile'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
