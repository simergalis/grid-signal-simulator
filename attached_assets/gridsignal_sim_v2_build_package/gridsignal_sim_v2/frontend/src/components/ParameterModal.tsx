/**
 * ParameterModal.tsx — Physics parameter reference and settings modal.
 *
 * GS-DES-CFG-001 §Phase-7: generated entirely from gridsignal_parameters.json.
 * No control is hand-coded here; every entry, range, provenance, and spec_ref is
 * driven by the catalogue.  Adding a control that is NOT in the catalogue reintroduces
 * the drift this spec exists to prevent.
 *
 * Rendering rules:
 *   · adjustable entries with a DESCRIPTOR_KEY_MAP mapping → editable slider
 *   · adjustable entries without a mapping → read-only reference row
 *     (managed in Scenario Builder or pending ScenarioSpec wiring)
 *   · locked entries → read-only table, ALL groups shown (no LOCKED_GROUPS filter)
 *   · CONFORMANCE provenance → read-only regardless of section
 *   · CHOSEN provenance → read-only (deliberate decision, not pending calibration)
 *   · dt_lead (split=false in catalogue) → single slider; CFG-5 deferred
 *   · Every control displays provenance dot and spec_ref
 *
 * Decisions for PROPOSED_HERE values (see test_worked_example.py):
 *   band_pct_calibrated    = 4 %   (calibrated baseline; × 2.0 = 8 % uncal = fixture)
 *   band_mult_uncalibrated = 2.0 × (§17.3 widening; matches worked-example 8 %)
 *   band_mult_unmapped_hw  = 1.5 × (§5.1 unmapped-profile widening)
 *   anchor_reserve_pct     = 8 %   (PROPOSED_HERE placeholder; pending commissioning)
 *
 * bess_anchor_reserve_mw placement: locked/bess.  Confirmed in §Phase-7 Item-5 —
 * operators adjust the reserve fraction via anchor_reserve_pct (adjustable PARAM-09);
 * the catalogue holds the class default used when no per-scenario override is present.
 *
 * CFG-5 deferred: dt_lead split-parameter rendering not implemented.
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
  | 'CHOSEN'   // GS-DES-CFG-001 §Phase-7: deliberate decision without measured basis
  | 'n/a'      // GS-DES-CFG-001 §Phase-7: enumerated entries (not applicable)

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
  provenance_detail?: string
  spec_ref?: string
  note?: string
  ui: { control: string; group: string }
}

interface LockedParam {
  key: string
  value: string | number
  unit?: string
  label?: string           // GS-DES-CFG-001 §Phase-7: from catalogue
  provenance: Provenance
  provenance_detail?: string  // GS-DES-CFG-001 §Phase-7: from catalogue
  spec_ref?: string           // GS-DES-CFG-001 §Phase-7: from catalogue
  reason?: string
  note?: string
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
  // PARAM-28 through PARAM-34 are NOT in the catalogue adjustable section.
  // They are absent from the modal pending catalogue addition; defaults are 0.
  site_latitude: number
  site_utc_offset_h: number
  ambient_temp_base_c: number
  soc_floor_pct: number
  soc_ceil_pct: number
  advisory_interval_s: number
  advisory_max_mw: number
}

/**
 * Build default PhysicsParams from the catalogue (key-based, authoritative).
 *
 * GS-DES-CFG-001 §Phase-7: switched from PARAM-id lookup to catalogue key lookup.
 * PARAM-28 through PARAM-34 are not in the catalogue adjustable section; their
 * defaults are 0 pending catalogue addition.
 */
export function defaultPhysicsParams(): PhysicsParams {
  const adj = (parametersJson as { adjustable: AdjParam[] }).adjustable
  const def = (key: string) => adj.find(a => a.key === key)?.default ?? 0
  return {
    dt_lead_seconds:           def('dt_lead'),
    plant_dt_lead_seconds:     null,
    dt_thermal_seconds:        def('dt_thermal'),
    plant_dt_thermal_seconds:  null,
    alpha_max:                 def('alpha_max'),
    plant_alpha_max:           null,
    tau_seconds:               def('tau'),
    plant_tau_seconds:         null,
    pue_base:                  def('pue_base'),
    plant_pue_base:            null,
    anchor_reserve_pct:        def('anchor_reserve_pct'),
    band_pct_calibrated:       def('band_pct_calibrated'),
    band_mult_uncalibrated:    def('band_mult_uncalibrated'),
    band_mult_unmapped_hw:     def('band_mult_unmapped_hw'),
    // Not in catalogue adjustable section → 0 defaults
    site_latitude:             0,
    site_utc_offset_h:         0,
    ambient_temp_base_c:       0,
    soc_floor_pct:             0,
    soc_ceil_pct:              0,
    advisory_interval_s:       0,
    advisory_max_mw:           0,
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
  // GS-DES-CFG-001 §Phase-7: new provenance classes
  CHOSEN:         { bg: '#a16207', label: 'Deliberate design choice — no measured basis' },
  'n/a':          { bg: '#374151', label: 'Not applicable (enumerated / fixed)' },
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
// Catalogue key → PhysicsParams key mapping
//
// GS-DES-CFG-001 §Phase-7: replaces hand-written PARAM_MAP (id-based).
// Only entries listed here render as editable controls.  Adjustable entries
// in the catalogue that are absent from this map render as read-only reference
// rows (managed via the Scenario Builder or pending ScenarioSpec wiring).
//
// dt_lead: split=false in catalogue (CFG-5 deferred — split rendering not implemented).
// ---------------------------------------------------------------------------

const DESCRIPTOR_KEY_MAP: Record<string, [keyof PhysicsParams, keyof PhysicsParams | null]> = {
  'dt_lead':               ['dt_lead_seconds',        'plant_dt_lead_seconds'],
  'dt_thermal':            ['dt_thermal_seconds',     'plant_dt_thermal_seconds'],
  'alpha_max':             ['alpha_max',              'plant_alpha_max'],
  'tau':                   ['tau_seconds',            'plant_tau_seconds'],
  'pue_base':              ['pue_base',               'plant_pue_base'],
  'anchor_reserve_pct':    ['anchor_reserve_pct',     null],
  'band_pct_calibrated':   ['band_pct_calibrated',    null],
  'band_mult_uncalibrated':['band_mult_uncalibrated', null],
  'band_mult_unmapped_hw': ['band_mult_unmapped_hw',  null],
}

// Display ordering for adjustable groups (UX preference — not a filter).
// Groups not in this list are shown at the end in discovery order.
const ADJUSTABLE_GROUP_ORDER = [
  'timing', 'thermal', 'load', 'storage', 'supply', 'generation', 'advisory', 'confidence',
]

// Display ordering for locked groups.
const LOCKED_GROUP_ORDER = [
  'thermal', 'solar', 'bess', 'turbine', 'engine', 'classifier', 'integrity',
]

const GROUP_LABELS: Record<string, string> = {
  site:        'Site',
  timing:      'Timing',
  thermal:     'Thermal',
  load:        'Load',
  storage:     'Storage',
  supply:      'Supply',
  generation:  'Generation',
  advisory:    'Advisory Agents',
  confidence:  'Confidence Band (INV-2)',
  bess:        'BESS',
  classifier:  'Classifier',
  engine:      'Engine',
  integrity:   'Integrity',
  turbine:     'Turbine',
  solar:       'Solar',
  authority:   'Authority',
  scenario:    'Scenario',
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
        {param.spec_ref && (
          <span className="text-[9px] text-muted opacity-35 flex-none ml-1 font-mono">
            {param.spec_ref}
          </span>
        )}
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
// Reference-only row (adjustable entry without a DESCRIPTOR_KEY_MAP mapping)
// ---------------------------------------------------------------------------

/**
 * Read-only reference display for catalogue adjustable entries that are managed
 * outside this modal (e.g. Scenario Builder) or are pending ScenarioSpec wiring.
 *
 * GS-DES-CFG-001 §Phase-7: these entries ARE in the catalogue adjustable section
 * and are shown here so operators can see their current default values and
 * provenance.  They are not editable here; the Scenario Builder is the SoT.
 */
function RefRow({ param }: { param: AdjParam }) {
  const valStr =
    typeof param.default !== 'undefined'
      ? `${param.default}${param.unit ? ' ' + param.unit : ''}`
      : '—'
  return (
    <div className="mb-2.5 opacity-55">
      <div className="flex items-center gap-1.5">
        <ProvenanceDot prov={param.provenance as Provenance} />
        <span className="text-[10px] text-muted flex-1 leading-tight">{param.label}</span>
        <span className="font-mono text-[10px] text-muted tabular-nums">{valStr}</span>
        {param.spec_ref && (
          <span className="text-[9px] text-muted opacity-40 flex-none ml-1 font-mono">
            {param.spec_ref}
          </span>
        )}
      </div>
      <p className="ml-4 text-[9px] text-muted opacity-40 leading-snug mt-0.5">
        Managed in Scenario Builder — reference only
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Locked params table
// ---------------------------------------------------------------------------

/** Derive a human label from a snake_case key (fallback when label absent). */
function keyToLabel(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())
}

/**
 * GS-DES-CFG-001 §Phase-7: shows ALL locked entries (no group filter).
 * Added spec_ref column; uses catalogue label; shows provenance_detail or reason.
 */
function LockedTable({ params }: { params: LockedParam[] }) {
  if (!params.length) return null
  return (
    <table className="w-full text-[10px] border-collapse">
      <thead>
        <tr className="text-muted text-left">
          <th className="py-1 pr-2 font-semibold w-4" />
          <th className="py-1 pr-3 font-semibold">Parameter</th>
          <th className="py-1 pr-3 font-semibold text-right">Value</th>
          <th className="py-1 pr-2 font-semibold text-[9px] whitespace-nowrap">Spec ref</th>
          <th className="py-1 font-semibold">Provenance / reason</th>
        </tr>
      </thead>
      <tbody>
        {params.map(p => (
          <tr key={p.key} className="border-t border-border/30">
            <td className="py-1 pr-2">
              <ProvenanceDot prov={p.provenance as Provenance} size={5} />
            </td>
            <td className="py-1 pr-3 text-muted">{p.label ?? keyToLabel(p.key)}</td>
            <td className="py-1 pr-3 font-mono text-right text-text whitespace-nowrap">
              {p.value}{p.unit ? ' ' + p.unit : ''}
            </td>
            <td className="py-1 pr-2 text-muted opacity-50 text-[9px] font-mono whitespace-nowrap">
              {p.spec_ref ?? '—'}
            </td>
            <td className="py-1 text-muted opacity-60 leading-snug">
              {p.reason ?? p.provenance_detail ?? p.note ?? '—'}
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
    // GS-DES-CFG-001 §Phase-7: use catalogue key, not PARAM-id
    json.adjustable
      .filter(p => p.split && DESCRIPTOR_KEY_MAP[p.key])
      .forEach(p => { initLinked[p.key] = true })
    setLinked(initLinked)
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!open) return null

  // ── Value accessors ──────────────────────────────────────────────────
  // GS-DES-CFG-001 §Phase-7: all accessors keyed by catalogue key, not PARAM-id.
  const engineVal = (key: string): number => {
    const k = DESCRIPTOR_KEY_MAP[key]?.[0]
    return k ? (vals[k] as number) : 0
  }
  const plantVal = (key: string): number => {
    const spec = DESCRIPTOR_KEY_MAP[key]
    if (!spec?.[1]) return engineVal(key)
    const v = vals[spec[1] as keyof PhysicsParams]
    return v == null ? engineVal(key) : (v as number)
  }
  const setEngineVal = (key: string, v: number) => {
    const k = DESCRIPTOR_KEY_MAP[key]?.[0]
    if (k) setVals(prev => ({ ...prev, [k]: v }))
  }
  const setPlantVal = (key: string, v: number) => {
    const spec = DESCRIPTOR_KEY_MAP[key]
    if (spec?.[1]) setVals(prev => ({ ...prev, [spec[1] as keyof PhysicsParams]: v }))
  }
  const toggleLink = (key: string) => {
    const nowLinked = !linked[key]
    setLinked(prev => ({ ...prev, [key]: nowLinked }))
    const spec = DESCRIPTOR_KEY_MAP[key]
    if (spec?.[1]) {
      setVals(prev => ({
        ...prev,
        [spec[1] as keyof PhysicsParams]: nowLinked ? null : engineVal(key),
      }))
    }
  }

  // ── Group all adjustable params by their catalogue group ─────────────
  // GS-DES-CFG-001 §Phase-7: no showableIds filter — all catalogue entries shown.
  // Entries in DESCRIPTOR_KEY_MAP → editable slider.
  // Entries not in map → RefRow (read-only reference).
  const byGroup = new Map<string, AdjParam[]>()
  for (const p of json.adjustable) {
    const g = p.ui?.group ?? 'other'
    if (!byGroup.has(g)) byGroup.set(g, [])
    byGroup.get(g)!.push(p)
  }

  // Ordered group list: ADJUSTABLE_GROUP_ORDER first, then any remaining in discovery order
  const discoveredGroups = Array.from(byGroup.keys())
  const orderedGroups = [
    ...ADJUSTABLE_GROUP_ORDER.filter(g => byGroup.has(g)),
    ...discoveredGroups.filter(g => !ADJUSTABLE_GROUP_ORDER.includes(g)),
  ]

  // ── All locked params, ordered by LOCKED_GROUP_ORDER ────────────────
  // GS-DES-CFG-001 §Phase-7: LOCKED_GROUPS filter removed — all locked entries shown.
  // Group by ui.group, apply LOCKED_GROUP_ORDER, then any remaining.
  const byLockedGroup = new Map<string, LockedParam[]>()
  for (const p of json.locked) {
    const g = p.ui?.group ?? 'other'
    if (!byLockedGroup.has(g)) byLockedGroup.set(g, [])
    byLockedGroup.get(g)!.push(p)
  }
  const discoveredLockedGroups = Array.from(byLockedGroup.keys())
  const orderedLockedGroups = [
    ...LOCKED_GROUP_ORDER.filter(g => byLockedGroup.has(g)),
    ...discoveredLockedGroups.filter(g => !LOCKED_GROUP_ORDER.includes(g)),
  ]
  // Flatten in ordered group sequence
  const visibleLocked = orderedLockedGroups.flatMap(g => byLockedGroup.get(g) ?? [])

  // ── Provenance counts ────────────────────────────────────────────────
  const proposedCount =
    json.adjustable.filter(p => p.provenance === 'PROPOSED_HERE').length +
    json.locked.filter(p => p.provenance === 'PROPOSED_HERE').length
  const chosenCount =
    json.locked.filter(p => p.provenance === 'CHOSEN').length

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.65)' }}
      onClick={e => { if (e.target === overlayRef.current) onClose() }}
    >
      <div
        className="relative flex flex-col bg-canvas border border-border rounded-lg shadow-2xl
                   w-[720px] max-w-[96vw] max-h-[88vh] overflow-hidden"
      >
        {/* ── Header ─────────────────────────────────────────────── */}
        <div className="flex items-center gap-2 px-5 py-3 border-b border-border flex-shrink-0 flex-wrap">
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

          {chosenCount > 0 && (
            <span
              className="text-[9px] rounded px-1.5 py-0.5 font-mono flex-none"
              style={{ background: '#a1620720', color: '#d97706', border: '1px solid #a1620740' }}
              title={`${chosenCount} parameters with CHOSEN provenance — deliberate design decision, no measured basis`}
            >
              ○ {chosenCount}× CHOSEN
            </span>
          )}

          {/* Legend */}
          <div className="flex gap-2.5 items-center ml-auto flex-wrap">
            {(['MEASURED', 'SPEC_DEFAULT', 'PROPOSED_HERE', 'CHOSEN', 'CONFORMANCE'] as Provenance[]).map(k => (
              <span key={k} className="flex items-center gap-1" title={PROVENANCE_COLORS[k].label}>
                <span style={{
                  display:'inline-block', width:6, height:6,
                  borderRadius:'50%', background: PROVENANCE_COLORS[k].bg,
                }} />
                <span className="text-[9px] text-muted">
                  {k === 'SPEC_DEFAULT' ? 'SPEC' : k === 'PROPOSED_HERE' ? 'PROP' : k.split('_')[0]}
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

          {/* Adjustable param groups
              GS-DES-CFG-001 §Phase-7: all catalogue adjustable entries shown.
              Entries with DESCRIPTOR_KEY_MAP mapping → editable slider.
              Entries without mapping → RefRow (reference only). */}
          {orderedGroups.map(group => {
            const groupParams = byGroup.get(group)!
            return (
              <div key={group}>
                <SectionHead title={GROUP_LABELS[group] ?? group} />
                {groupParams.map(p => {
                  const isEditable = !!DESCRIPTOR_KEY_MAP[p.key]
                  if (!isEditable) return <RefRow key={p.key} param={p} />
                  return (
                    <SplitSliderRow
                      key={p.key}
                      param={p}
                      engineValue={engineVal(p.key)}
                      plantValue={plantVal(p.key)}
                      linked={linked[p.key] ?? true}
                      onEngineChange={v => {
                        setEngineVal(p.key, v)
                        if (linked[p.key] ?? true) setPlantVal(p.key, v)
                      }}
                      onPlantChange={v => setPlantVal(p.key, v)}
                      onToggleLink={() => toggleLink(p.key)}
                    />
                  )
                })}
              </div>
            )
          })}

          {/* Locked section
              GS-DES-CFG-001 §Phase-7: ALL locked entries shown (LOCKED_GROUPS filter removed).
              Grouped by ui.group in LOCKED_GROUP_ORDER, then remaining groups.
              Includes cooling_margin (thermal), solar_fraction_of_peak (solar),
              bess_anchor_reserve_mw / p_anchor_reserve_mw_san_diego (bess),
              p_min_stable_frac_demo (turbine) — previously hidden by LOCKED_GROUPS filter. */}
          {visibleLocked.length > 0 && (
            <>
              <SectionHead title="Locked — read-only constants (CONFORMANCE and CHOSEN)" />
              <LockedTable params={visibleLocked} />
            </>
          )}

          {/* Footer note */}
          <div className="mt-4 rounded bg-surface/30 border border-border/30 px-3 py-2">
            <p className="text-[9px] text-muted leading-snug">
              <strong>GS-DES-CFG-001:</strong> all entries, ranges, and provenance tags are read
              from <code className="font-mono">gridsignal_parameters.json</code> — none are
              hand-coded in this component.  Adjustable entries without a slider are managed
              in the <strong>Scenario Builder</strong> (bess_rated_mw, r_asset, soc_pct,
              p_renewable_mw).  Enumerated entries (clock discipline, grid mode, hardware
              profile, etc.) are scenario-configuration values shown in the Scenario Builder.
              PARAM-28–34 are not yet in the catalogue adjustable section.
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
