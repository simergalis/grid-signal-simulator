/**
 * ParameterModal.tsx — Physics parameter reference and settings modal.
 *
 * Generated at runtime from gridsignal_parameters.json.  No value is
 * hard-coded here; every default, range, and provenance tag is read from
 * the JSON at component load time.
 *
 * Design principles (from gridsignal_parameters.json preamble):
 *   · parameters with split=true show PLANT ──🔗── ENGINE two-column sliders
 *     with a link toggle that defaults ON (linked = same value for both)
 *   · locked parameters are displayed read-only with their reason text
 *   · provenance class is shown as a colour dot per parameter
 *   · excluded parameters are never shown
 *
 * Decisions for PROPOSED_HERE values (see test_worked_example.py):
 *   band_pct_calibrated   = 4 %  (calibrated baseline; × 2.0 = 8 % uncal = fixture)
 *   band_mult_uncalibrated = 2.0 × (§17.3 widening; matches worked-example 8 %)
 *   band_mult_unmapped_hw  = 1.5 × (§5.1 unmapped-profile widening)
 *   anchor_reserve_pct     = 8 %  (PROPOSED_HERE placeholder; pending commissioning)
 */

import { useEffect, useRef, useState } from 'react'
import parametersJson from '../parameters.json'

// ---------------------------------------------------------------------------
// JSON shape types (matches actual gridsignal_parameters.json structure)
// ---------------------------------------------------------------------------

type Provenance =
  | 'MEASURED'
  | 'SPEC_DEFAULT'
  | 'VENDOR_RATING'
  | 'ESTIMATE'
  | 'PROPOSED_HERE'
  | 'CONFORMANCE'

interface AdjParam {
  id: string
  key: string
  label: string
  unit: string
  default: number
  min: number
  max: number
  step?: number
  split?: boolean
  provenance: Provenance
  note?: string
  ui: { control: string; group: string }
}

interface LockedParam {
  key: string
  value: string | number
  unit?: string
  provenance: Provenance
  reason?: string
  ui: { control: string; group: string }
}

// ---------------------------------------------------------------------------
// PhysicsParams — the values we write back into ScenarioSpec
// ---------------------------------------------------------------------------

export interface PhysicsParams {
  dt_lead_seconds: number
  plant_dt_lead_seconds: number | null       // null = linked to engine
  dt_thermal_seconds: number
  plant_dt_thermal_seconds: number | null
  alpha_max: number
  plant_alpha_max: number | null
  tau_seconds: number
  plant_tau_seconds: number | null
  pue_base: number
  plant_pue_base: number | null
  anchor_reserve_pct: number
  band_pct_calibrated: number
  band_mult_uncalibrated: number
  band_mult_unmapped_hw: number
}

/** Build default PhysicsParams from JSON (authoritative). */
export function defaultPhysicsParams(): PhysicsParams {
  const adj = (parametersJson as { adjustable: AdjParam[] }).adjustable
  const def = (id: string) => adj.find(a => a.id === id)?.default ?? 0
  return {
    dt_lead_seconds:           def('PARAM-01'),
    plant_dt_lead_seconds:     null,
    dt_thermal_seconds:        def('PARAM-02'),
    plant_dt_thermal_seconds:  null,
    alpha_max:                 def('PARAM-03'),
    plant_alpha_max:           null,
    tau_seconds:               def('PARAM-04'),
    plant_tau_seconds:         null,
    pue_base:                  def('PARAM-06'),
    plant_pue_base:            null,
    anchor_reserve_pct:        def('PARAM-09'),
    band_pct_calibrated:       def('PARAM-13'),
    band_mult_uncalibrated:    def('PARAM-14'),
    band_mult_unmapped_hw:     def('PARAM-15'),
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const PROVENANCE_COLORS: Record<Provenance, { bg: string; label: string }> = {
  MEASURED:       { bg: '#22c55e', label: 'Calibrated measurement' },
  SPEC_DEFAULT:   { bg: '#3b82f6', label: 'From design spec' },
  VENDOR_RATING:  { bg: '#a78bfa', label: 'Vendor nameplate' },
  ESTIMATE:       { bg: '#facc15', label: 'Engineering estimate' },
  PROPOSED_HERE:  { bg: '#f97316', label: 'Proposed — needs calibration' },
  CONFORMANCE:    { bg: '#6b7280', label: 'Conformance requirement' },
}

function ProvenanceDot({ prov, size = 6 }: { prov: Provenance; size?: number }) {
  const meta = PROVENANCE_COLORS[prov] ?? PROVENANCE_COLORS.ESTIMATE
  return (
    <span
      title={`${prov}: ${meta.label}`}
      style={{
        display: 'inline-block',
        width: size,
        height: size,
        borderRadius: '50%',
        background: meta.bg,
        flexShrink: 0,
        cursor: 'help',
      }}
    />
  )
}

function SectionHead({ title }: { title: string }) {
  return (
    <h3 className="mt-5 mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted border-b border-border/40 pb-1">
      {title}
    </h3>
  )
}

// ---------------------------------------------------------------------------
// Split-param slider row (PLANT ──🔗── ENGINE or single column)
// ---------------------------------------------------------------------------

function SplitSliderRow({
  param,
  engineValue,
  plantValue,
  linked,
  onEngineChange,
  onPlantChange,
  onToggleLink,
}: {
  param: AdjParam
  engineValue: number
  plantValue: number
  linked: boolean
  onEngineChange: (v: number) => void
  onPlantChange: (v: number) => void
  onToggleLink: () => void
}) {
  const step     = param.step ?? (param.max - param.min > 10 ? 1 : 0.01)
  const decimals = step < 0.1 ? 2 : step < 1 ? 1 : 0
  const isSplit  = param.split === true

  return (
    <div className="mb-3">
      {/* Label row */}
      <div className="flex items-center gap-1.5 mb-1">
        <ProvenanceDot prov={param.provenance as Provenance} />
        <span className="text-[10px] text-muted flex-1 leading-tight">{param.label}</span>
        <span className="text-[9px] text-muted opacity-50 flex-none">
          {param.min}–{param.max} {param.unit}
        </span>
      </div>

      {isSplit ? (
        /* Two-column layout: PLANT │ 🔗 │ ENGINE */
        <div className="flex items-center gap-1">
          {/* Plant column */}
          <div className="flex-1 min-w-0">
            <div className="text-[9px] mb-0.5 text-center"
                 style={{ color: linked ? '#6b7280' : '#f97316' }}>
              PLANT{!linked && ' ⊹'}
            </div>
            <div className="flex items-center gap-1">
              <input
                type="range"
                className="flex-1 h-1"
                style={{ accentColor: linked ? '#6b7280' : '#f97316' }}
                min={param.min}
                max={param.max}
                step={step}
                value={plantValue}
                disabled={linked}
                onChange={e => onPlantChange(Number(e.target.value))}
              />
              <span className="font-mono text-[10px] text-text tabular-nums w-11 text-right">
                {plantValue.toFixed(decimals)}{param.unit === 's' ? ' s' : ''}
              </span>
            </div>
          </div>

          {/* Link toggle */}
          <button
            onClick={onToggleLink}
            title={linked ? 'Unlink plant/engine — simulate model divergence' : 'Re-link plant/engine values'}
            className="flex-none text-base leading-none px-0.5 py-0.5 rounded transition-opacity"
            style={{ opacity: 0.8 }}
          >
            {linked ? '🔗' : '🔓'}
          </button>

          {/* Engine column */}
          <div className="flex-1 min-w-0">
            <div className="text-[9px] text-accent text-center mb-0.5">ENGINE</div>
            <div className="flex items-center gap-1">
              <input
                type="range"
                className="flex-1 accent-accent h-1"
                min={param.min}
                max={param.max}
                step={step}
                value={engineValue}
                onChange={e => {
                  const v = Number(e.target.value)
                  onEngineChange(v)
                  if (linked) onPlantChange(v)
                }}
              />
              <span className="font-mono text-[10px] text-text tabular-nums w-11 text-right">
                {engineValue.toFixed(decimals)}{param.unit === 's' ? ' s' : ''}
              </span>
            </div>
          </div>
        </div>
      ) : (
        /* Single slider */
        <div className="flex items-center gap-1">
          <input
            type="range"
            className="flex-1 accent-accent h-1"
            min={param.min}
            max={param.max}
            step={step}
            value={engineValue}
            onChange={e => onEngineChange(Number(e.target.value))}
          />
          <span className="font-mono text-[10px] text-text tabular-nums w-14 text-right">
            {engineValue.toFixed(decimals)} {param.unit}
          </span>
        </div>
      )}

      {param.note && (
        <p className="mt-0.5 text-[9px] text-muted leading-snug opacity-60">{param.note}</p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Locked params table
// ---------------------------------------------------------------------------

/** Derive a human label from a snake_case key. */
function keyToLabel(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())
}

function LockedTable({ params }: { params: LockedParam[] }) {
  if (!params.length) return null
  return (
    <table className="w-full text-[10px] border-collapse">
      <thead>
        <tr className="text-muted text-left">
          <th className="py-1 pr-2 font-semibold w-4" />
          <th className="py-1 pr-3 font-semibold">Parameter</th>
          <th className="py-1 pr-3 font-semibold text-right">Value</th>
          <th className="py-1 font-semibold">Reason locked</th>
        </tr>
      </thead>
      <tbody>
        {params.map(p => (
          <tr key={p.key} className="border-t border-border/30">
            <td className="py-1 pr-2">
              <ProvenanceDot prov={p.provenance as Provenance} size={5} />
            </td>
            <td className="py-1 pr-3 text-muted">{keyToLabel(p.key)}</td>
            <td className="py-1 pr-3 font-mono text-right text-text whitespace-nowrap">
              {p.value}{p.unit ? ' ' + p.unit : ''}
            </td>
            <td className="py-1 text-muted opacity-60 leading-snug">
              {p.reason ?? '—'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// ---------------------------------------------------------------------------
// Main modal
// ---------------------------------------------------------------------------

export interface Props {
  open: boolean
  onClose: () => void
  /** Current physics param values (from scenario spec or defaults). */
  initial: PhysicsParams
  onApply: (params: PhysicsParams) => void
}

/** Maps PARAM-id to [engineKey, plantKey | null] in PhysicsParams. */
const PARAM_MAP: Record<string, [keyof PhysicsParams, keyof PhysicsParams | null]> = {
  'PARAM-01': ['dt_lead_seconds',        'plant_dt_lead_seconds'],
  'PARAM-02': ['dt_thermal_seconds',     'plant_dt_thermal_seconds'],
  'PARAM-03': ['alpha_max',              'plant_alpha_max'],
  'PARAM-04': ['tau_seconds',            'plant_tau_seconds'],
  'PARAM-06': ['pue_base',               'plant_pue_base'],
  'PARAM-09': ['anchor_reserve_pct',     null],
  'PARAM-13': ['band_pct_calibrated',    null],
  'PARAM-14': ['band_mult_uncalibrated', null],
  'PARAM-15': ['band_mult_unmapped_hw',  null],
}

const GROUP_ORDER = ['timing', 'thermal', 'storage', 'confidence']
const GROUP_LABELS: Record<string, string> = {
  timing:      'Timing',
  thermal:     'Thermal',
  storage:     'Storage',
  confidence:  'Confidence Band (INV-2)',
}
const LOCKED_GROUPS = ['classifier', 'engine', 'storage', 'integrity']

export function ParameterModal({ open, onClose, initial, onApply }: Props) {
  const json         = parametersJson as { adjustable: AdjParam[]; locked: LockedParam[] }
  const overlayRef   = useRef<HTMLDivElement>(null)
  const [vals, setVals] = useState<PhysicsParams>(initial)
  const [linked, setLinked] = useState<Record<string, boolean>>({})

  /* Sync from prop each time the modal opens */
  useEffect(() => {
    if (!open) return
    setVals(initial)
    const initLinked: Record<string, boolean> = {}
    json.adjustable
      .filter(p => p.split && PARAM_MAP[p.id])
      .forEach(p => { initLinked[p.id] = true })
    setLinked(initLinked)
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!open) return null

  // ── Value accessors ──────────────────────────────────────────────────
  const engineVal = (id: string): number => {
    const k = PARAM_MAP[id]?.[0]
    return k ? (vals[k] as number) : 0
  }
  const plantVal = (id: string): number => {
    const spec = PARAM_MAP[id]
    if (!spec?.[1]) return engineVal(id)
    const v = vals[spec[1] as keyof PhysicsParams]
    return v == null ? engineVal(id) : (v as number)
  }
  const setEngineVal = (id: string, v: number) => {
    const k = PARAM_MAP[id]?.[0]
    if (k) setVals(prev => ({ ...prev, [k]: v }))
  }
  const setPlantVal = (id: string, v: number) => {
    const spec = PARAM_MAP[id]
    if (spec?.[1]) setVals(prev => ({ ...prev, [spec[1] as keyof PhysicsParams]: v }))
  }
  const toggleLink = (id: string) => {
    const nowLinked = !linked[id]
    setLinked(prev => ({ ...prev, [id]: nowLinked }))
    const spec = PARAM_MAP[id]
    if (spec?.[1]) {
      setVals(prev => ({
        ...prev,
        [spec[1] as keyof PhysicsParams]: nowLinked ? null : engineVal(id),
      }))
    }
  }

  // ── Group visible params ─────────────────────────────────────────────
  const showableIds = new Set(Object.keys(PARAM_MAP))
  const byGroup = new Map<string, AdjParam[]>()
  for (const p of json.adjustable) {
    const g = p.ui?.group
    if (!showableIds.has(p.id) || !g) continue
    if (!byGroup.has(g)) byGroup.set(g, [])
    byGroup.get(g)!.push(p)
  }

  // ── Locked params (all locked groups, minus excluded) ────────────────
  const visibleLocked = json.locked.filter(p => LOCKED_GROUPS.includes(p.ui?.group ?? ''))

  // ── PROPOSED_HERE count ──────────────────────────────────────────────
  const proposedCount = json.adjustable.filter(
    p => showableIds.has(p.id) && p.provenance === 'PROPOSED_HERE'
  ).length

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.65)' }}
      onClick={e => { if (e.target === overlayRef.current) onClose() }}
    >
      <div
        className="relative flex flex-col bg-canvas border border-border rounded-lg shadow-2xl
                   w-[700px] max-w-[96vw] max-h-[88vh] overflow-hidden"
      >
        {/* ── Header ─────────────────────────────────────────────── */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-border flex-shrink-0">
          <h2 className="text-sm font-semibold text-text">Parameter Reference</h2>

          {proposedCount > 0 && (
            <span
              className="text-[9px] rounded px-1.5 py-0.5 font-mono flex-none"
              style={{ background: '#f9731620', color: '#f97316', border: '1px solid #f9731640' }}
              title={`${proposedCount} parameters with PROPOSED_HERE provenance — pending calibration`}
            >
              ⚠ {proposedCount}× PROPOSED_HERE
            </span>
          )}

          {/* Legend */}
          <div className="flex gap-3 items-center ml-auto">
            {(['MEASURED', 'SPEC_DEFAULT', 'PROPOSED_HERE', 'CONFORMANCE'] as Provenance[]).map(k => (
              <span key={k} className="flex items-center gap-1" title={PROVENANCE_COLORS[k].label}>
                <span style={{
                  display:'inline-block', width:6, height:6,
                  borderRadius:'50%', background: PROVENANCE_COLORS[k].bg,
                }} />
                <span className="text-[9px] text-muted">
                  {k === 'SPEC_DEFAULT' ? 'SPEC' : k.split('_')[0]}
                </span>
              </span>
            ))}
          </div>

          <button
            onClick={onClose}
            className="ml-2 text-muted hover:text-text text-xl leading-none"
            aria-label="Close"
          >×</button>
        </div>

        {/* ── Body ───────────────────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto px-5 pb-3">

          {/* Plant / Engine column header */}
          <div className="sticky top-0 bg-canvas pt-3 pb-1.5 border-b border-border/20 mb-1 z-10">
            <div className="flex items-center gap-1 text-[9px] text-muted">
              <span className="flex-1">Split parameters show:</span>
              <span style={{ color: '#f97316' }} className="font-mono">PLANT</span>
              <span className="mx-1">──🔗──</span>
              <span className="text-accent font-mono">ENGINE</span>
              <span className="ml-2 flex-1 opacity-70">
                (plant = simulation reality · engine = forecast model belief)
              </span>
            </div>
          </div>

          {/* Adjustable param groups */}
          {GROUP_ORDER.map(group => {
            const groupParams = byGroup.get(group)
            if (!groupParams?.length) return null
            return (
              <div key={group}>
                <SectionHead title={GROUP_LABELS[group] ?? group} />
                {groupParams.map(p => (
                  <SplitSliderRow
                    key={p.id}
                    param={p}
                    engineValue={engineVal(p.id)}
                    plantValue={plantVal(p.id)}
                    linked={linked[p.id] ?? true}
                    onEngineChange={v => {
                      setEngineVal(p.id, v)
                      if (linked[p.id] ?? true) setPlantVal(p.id, v)
                    }}
                    onPlantChange={v => setPlantVal(p.id, v)}
                    onToggleLink={() => toggleLink(p.id)}
                  />
                ))}
              </div>
            )
          })}

          {/* Locked section */}
          {visibleLocked.length > 0 && (
            <>
              <SectionHead title="Locked — conformance (read-only)" />
              <LockedTable params={visibleLocked} />
            </>
          )}

          {/* Footer note */}
          <div className="mt-4 rounded bg-surface/30 border border-border/30 px-3 py-2">
            <p className="text-[9px] text-muted leading-snug">
              <strong>Note:</strong> r_asset (turbine ramp), BESS rated MW, initial SOC, hardware
              profile, dt_lead, and P_renewable are managed in the Scenario Builder above.
              Values here are supplementary physics configuration.
              Source: <code className="font-mono">gridsignal_parameters.json</code> — never hand-coded.
            </p>
          </div>
        </div>

        {/* ── Footer ─────────────────────────────────────────────── */}
        <div className="flex items-center gap-3 px-5 py-3 border-t border-border flex-shrink-0">
          <button
            onClick={onClose}
            className="rounded border border-border px-3 py-1.5 text-xs text-muted
                       hover:text-text hover:border-text/40 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => { onApply(vals); onClose() }}
            className="rounded bg-accent px-4 py-1.5 text-xs font-semibold text-white
                       hover:bg-accent/90 transition-colors"
          >
            Apply to Scenario
          </button>
        </div>
      </div>
    </div>
  )
}
