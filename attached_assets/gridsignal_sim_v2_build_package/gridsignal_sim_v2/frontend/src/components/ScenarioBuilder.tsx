/**
 * ScenarioBuilder.tsx — right-side drawer for creating/editing scenarios (Step 8).
 *
 * Sections:
 *   1. Identity        — name, description
 *   2. Fleet           — BESS units (sliders, pill-toggle grid-forming), turbines
 *   3. Run Parameters  — solar, dt_lead slider, sim duration, PUE slider,
 *                        island_mode radio, hardware_profile dropdown,
 *                        irradiance-steps table
 *   4. PMS Configuration (optional) — enable toggle + transition_mode radio
 *
 * Widget decisions:
 *   · initial_soc_fraction, dt_lead_seconds, pue_base → SliderField
 *     (bounded, continuous, visual feedback more useful than raw number)
 *   · exact-value fields (rated_mw, usable_mwh, …) → NumField with unit suffix
 *   · island_mode → two-option radio with consequence text per option
 *   · grid_forming  → pill toggle with always-visible consequence text
 *   · hardware_profile_id → <select> dropdown
 *   · transition_mode → two-option radio with consequence text
 *   · irradiance_steps → editable two-column table (sim_time_s / irradiance)
 */

import { useEffect, useState } from 'react'
import { useScenarioStore } from '../store/scenarioStore'
import type { BessUnitSpec, KubeJobSpec, TurbineUnitSpec, ScenarioSpec } from '../types'
import { ParameterModal, defaultPhysicsParams } from './ParameterModal'
import type { PhysicsParams } from './ParameterModal'

// ── C-rate helper ─────────────────────────────────────────────────────────────

function cRate(b: BessUnitSpec): number {
  return b.usable_mwh > 0 ? b.rated_mw / b.usable_mwh : 0
}

function cRateWarning(b: BessUnitSpec): string | null {
  const c = cRate(b)
  if (c <= 0) return null
  if (c < 0.25 || c > 4.0) {
    return `${c.toFixed(2)} C — outside 0.25–4.0 C (PROTO-9: no measured basis)`
  }
  return null
}

function CRateBadge({ b }: { b: BessUnitSpec }) {
  const c = cRate(b)
  const warn = cRateWarning(b)
  return (
    <span
      className={`text-[10px] font-mono ${warn ? 'text-orange-400' : 'text-success'}`}
      title={warn ?? 'C-rate within PROTO-9 bounds'}
    >
      {c.toFixed(2)} C{warn ? ' ⚠' : ' ✓'}
    </span>
  )
}

// ── Field widgets ─────────────────────────────────────────────────────────────

/** Exact-value number input with optional unit suffix and range hint in label. */
function NumField({
  label, value, min, max, step = 0.1, unit = '', onChange,
}: {
  label: string; value: number; min?: number; max?: number; step?: number;
  unit?: string; onChange: (v: number) => void
}) {
  const hint = (min !== undefined && max !== undefined)
    ? ` (${min}–${max}${unit ? ' ' + unit : ''})`
    : unit ? ` (${unit})` : ''
  return (
    <label className="flex flex-col gap-0.5">
      <span className="text-[10px] text-muted">{label}{hint}</span>
      <input
        type="number"
        className="w-full rounded border border-border bg-canvas px-2 py-1 text-xs text-text
                   focus:outline-none focus:ring-1 focus:ring-accent"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={e => onChange(Number(e.target.value))}
      />
    </label>
  )
}

/** Slider with live numeric readout and visible min/max. */
function SliderField({
  label, value, min, max, step = 0.01, unit = '', decimals = 2, onChange,
}: {
  label: string; value: number; min: number; max: number; step?: number;
  unit?: string; decimals?: number; onChange: (v: number) => void
}) {
  return (
    <label className="flex flex-col gap-1">
      <div className="flex justify-between items-baseline">
        <span className="text-[10px] text-muted">{label}</span>
        <span className="font-mono text-[10px] text-text tabular-nums">
          {value.toFixed(decimals)}{unit}
        </span>
      </div>
      <input
        type="range"
        className="w-full accent-accent h-1"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
      />
      <div className="flex justify-between text-[9px] text-muted">
        <span>{min}{unit}</span>
        <span>{max}{unit}</span>
      </div>
    </label>
  )
}

/** Two-option radio group with per-option consequence text. */
function RadioGroup<T extends string>({
  label, value, options, onChange,
}: {
  label: string
  value: T
  options: { value: T; label: string; consequence: string }[]
  onChange: (v: T) => void
}) {
  return (
    <fieldset className="space-y-2">
      <legend className="text-[10px] text-muted">{label}</legend>
      {options.map(opt => (
        <label key={opt.value} className="flex gap-2 cursor-pointer">
          <input
            type="radio"
            className="mt-0.5 accent-accent"
            checked={value === opt.value}
            onChange={() => onChange(opt.value)}
          />
          <div>
            <div className="text-xs text-text">{opt.label}</div>
            <div className="text-[10px] text-muted leading-snug">{opt.consequence}</div>
          </div>
        </label>
      ))}
    </fieldset>
  )
}

// ── Defaults ──────────────────────────────────────────────────────────────────

function defaultBess(index: number): BessUnitSpec {
  return {
    asset_id: `bess-${index}`,
    rated_mw: 5.0,
    usable_mwh: 2.5,
    initial_soc_fraction: 0.95,
    grid_forming: index === 0,
  }
}

function defaultTurbine(index: number): TurbineUnitSpec {
  return {
    asset_id: `turbine-${index}`,
    rated_mw: 10.0,
    r_asset_mw_per_s: 0.2,
    // Phase 0 §0.1/0.2/0.6 defaults — match scenario_factory.py defaults.
    gt_mode:           'frame',
    hot_standby:       false,
    breaker_closed:    true,
    no_load_mw:        0.0,
    msl_mw:            0.0,
    sync_relay_state:  'permissive',  // Phase 0 §0.2: relay at rest for on-bus unit
    thermal_state:     'cold',
  }
}

function blankSpec(): ScenarioSpec {
  return {
    name: '',
    description: '',
    workload_events: [],
    hardware_profile_id: 'enterprise_8gpu_air',
    dt_lead_seconds: 30,
    bess_units: [defaultBess(0)],
    turbine_units: [defaultTurbine(0)],
    solar_rated_mw: 0,
    irradiance_steps: [[0.0, 1.0]],
    island_mode: true,
    pue_base: 1.03,
    end_sim_time: 300,
    default_playback_speed: 1,
    demo_description: '',
    pms_config: null,
  }
}

// ── Run-length and speed options (mirrors DemoBar) ────────────────────────────

const DURATION_OPTIONS = [
  { label: '5 min',    value: 300   },
  { label: '15 min',   value: 900   },
  { label: '30 min',   value: 1800  },
  { label: '1 hour',   value: 3600  },
  { label: '3 hours',  value: 10800 },
  { label: '4 hours',  value: 14400 },
  { label: 'No limit', value: 1e15  },
]

const SPEED_OPTIONS = [
  { label: '1×  (real-time)',  value: 1  },
  { label: '5×',              value: 5  },
  { label: '10×',             value: 10 },
  { label: '30×',             value: 30 },
  { label: 'MAX (no limit)',  value: 0  },
]

/** Find the closest DURATION_OPTIONS entry, falling back to the raw value. */
function nearestDuration(v: number): number {
  const match = DURATION_OPTIONS.find(o => Math.abs(o.value - v) < 1)
  return match ? match.value : v
}

// ── Known hardware profiles ───────────────────────────────────────────────────
// Add new profile IDs here as they are commissioned.

const HARDWARE_PROFILES = [
  { id: 'enterprise_8gpu_air', label: 'enterprise_8gpu_air — 8× GPU air-cooled (10.2 kW/node)' },
  { id: 'nextgen_rack_liquid', label: 'nextgen_rack_liquid — liquid-cooled (126 kW/node)' },
]

/** Nameplate draw per node (kW) — must match runtime/scenario_factory.py HW_PROFILES. */
const HW_KW_PER_NODE: Record<string, number> = {
  enterprise_8gpu_air: 10.2,
  nextgen_rack_liquid: 126.0,
}

/** Estimated peak demand in MW given node config + site PUE. */
function peakMw(k: { hardware_profile_id: string; max_nodes: number }, pue: number): number {
  return (k.max_nodes * (HW_KW_PER_NODE[k.hardware_profile_id] ?? 10.2) * pue) / 1000
}

function defaultKube(): KubeJobSpec {
  return { hardware_profile_id: 'enterprise_8gpu_air', max_nodes: 1000, min_nodes: 100 }
}

// ── Section header ────────────────────────────────────────────────────────────

function SectionHeader({ title }: { title: string }) {
  return (
    <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">{title}</h3>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  editId: string | null
  onClose: () => void
  onSaved: (scenarioId: string) => void
}

export function ScenarioBuilder({ editId, onClose, onSaved }: Props) {
  const createScenario = useScenarioStore(s => s.createScenario)
  const updateScenario = useScenarioStore(s => s.updateScenario)

  const [spec,          setSpec]          = useState<ScenarioSpec>(blankSpec())
  const [busy,          setBusy]          = useState(false)
  const [err,           setErr]           = useState<string | null>(null)
  const [warnings,      setWarnings]      = useState<string[]>([])
  const [physicsOpen,   setPhysicsOpen]   = useState(false)
  const [physicsParams, setPhysicsParams] = useState<PhysicsParams>(defaultPhysicsParams())
  const [aiBusy,        setAiBusy]        = useState(false)
  const [aiErr,         setAiErr]         = useState<string | null>(null)

  // If editing, load the existing spec
  useEffect(() => {
    if (!editId) {
      setSpec(blankSpec())
      return
    }
    fetch(`/scenarios/${editId}`)
      .then(r => r.json())
      .then(d => {
        const loaded = d.spec as ScenarioSpec
        setSpec({ ...loaded, pms_config: (loaded as ScenarioSpec & { pms_config?: typeof loaded.pms_config }).pms_config ?? null })
        setWarnings(d.c_rate_warnings ?? [])
        // Re-seed physicsParams from the loaded spec so editing preserves existing values.
        const defaults = defaultPhysicsParams()
        setPhysicsParams({
          dt_lead_seconds:           loaded.dt_lead_seconds          ?? defaults.dt_lead_seconds,
          plant_dt_lead_seconds:     loaded.plant_dt_lead_seconds     ?? null,
          dt_thermal_seconds:        loaded.dt_thermal_seconds        ?? defaults.dt_thermal_seconds,
          plant_dt_thermal_seconds:  loaded.plant_dt_thermal_seconds  ?? null,
          alpha_max:                 loaded.alpha_max                 ?? defaults.alpha_max,
          plant_alpha_max:           loaded.plant_alpha_max           ?? null,
          tau_seconds:               loaded.tau_seconds               ?? defaults.tau_seconds,
          plant_tau_seconds:         loaded.plant_tau_seconds         ?? null,
          pue_base:                  loaded.pue_base                  ?? defaults.pue_base,
          plant_pue_base:            loaded.plant_pue_base            ?? null,
          anchor_reserve_pct:        loaded.anchor_reserve_pct        ?? defaults.anchor_reserve_pct,
          band_pct_calibrated:       loaded.band_pct_calibrated       ?? defaults.band_pct_calibrated,
          band_mult_uncalibrated:    loaded.band_mult_uncalibrated    ?? defaults.band_mult_uncalibrated,
          band_mult_unmapped_hw:     loaded.band_mult_unmapped_hw     ?? defaults.band_mult_unmapped_hw,
          // Site / advisory (new operator-adjustable params)
          site_latitude:             loaded.site_latitude       ?? defaults.site_latitude,
          site_utc_offset_h:         loaded.site_utc_offset_h   ?? defaults.site_utc_offset_h,
          ambient_temp_base_c:       loaded.ambient_temp_base_c ?? defaults.ambient_temp_base_c,
          soc_floor_pct:             loaded.soc_floor_pct       ?? defaults.soc_floor_pct,
          soc_ceil_pct:              loaded.soc_ceil_pct        ?? defaults.soc_ceil_pct,
          advisory_interval_s:       loaded.advisory_interval_s ?? defaults.advisory_interval_s,
          advisory_max_mw:           loaded.advisory_max_mw     ?? defaults.advisory_max_mw,
        })
      })
      .catch(e => setErr(String(e)))
  }, [editId])

  // Patch helpers
  const patch = (partial: Partial<ScenarioSpec>) =>
    setSpec(prev => ({ ...prev, ...partial }))

  // ── BESS mutations ────────────────────────────────────────────────────────
  const patchBess = (i: number, partial: Partial<BessUnitSpec>) => {
    const updated = spec.bess_units.map((b, idx) => idx === i ? { ...b, ...partial } : b)
    if (partial.grid_forming) {
      patch({ bess_units: updated.map((b, idx) => ({ ...b, grid_forming: idx === i })) })
    } else {
      patch({ bess_units: updated })
    }
  }

  const addBess = () =>
    patch({ bess_units: [...spec.bess_units, defaultBess(spec.bess_units.length)] })

  const removeBess = (i: number) => {
    if (spec.bess_units.length <= 1) return
    const next = spec.bess_units.filter((_, idx) => idx !== i)
    const hasForming = next.some(b => b.grid_forming)
    patch({ bess_units: hasForming ? next : next.map((b, idx) => ({ ...b, grid_forming: idx === 0 })) })
  }

  // ── Turbine mutations ─────────────────────────────────────────────────────
  const patchTurbine = (i: number, partial: Partial<TurbineUnitSpec>) =>
    patch({ turbine_units: spec.turbine_units.map((t, idx) => idx === i ? { ...t, ...partial } : t) })

  const patchKube = (partial: Partial<KubeJobSpec>) =>
    patch({ kube_config: spec.kube_config ? { ...spec.kube_config, ...partial } : { ...defaultKube(), ...partial } })

  const addTurbine = () =>
    patch({ turbine_units: [...spec.turbine_units, defaultTurbine(spec.turbine_units.length)] })

  const removeTurbine = (i: number) => {
    if (spec.turbine_units.length <= 1) return
    patch({ turbine_units: spec.turbine_units.filter((_, idx) => idx !== i) })
  }

  // ── Irradiance step mutations ─────────────────────────────────────────────
  const patchIrr = (i: number, col: 0 | 1, value: number) => {
    const next = spec.irradiance_steps.map((row, idx) =>
      idx === i ? (col === 0 ? [value, row[1]] : [row[0], value]) as [number, number] : row
    )
    patch({ irradiance_steps: next })
  }

  const addIrrStep = () => {
    const last = spec.irradiance_steps[spec.irradiance_steps.length - 1]
    const t = last ? last[0] + 60 : 0
    patch({ irradiance_steps: [...spec.irradiance_steps, [t, 1.0]] })
  }

  const removeIrrStep = (i: number) => {
    if (spec.irradiance_steps.length <= 1) return
    patch({ irradiance_steps: spec.irradiance_steps.filter((_, idx) => idx !== i) })
  }

  // ── Demo description helpers ──────────────────────────────────────────────

  const handleStt = () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const w = window as any
    const SR: (new () => any) | undefined = w.SpeechRecognition ?? w.webkitSpeechRecognition
    if (!SR) { alert('Speech recognition is not supported in this browser.'); return }
    const rec = new SR()
    rec.lang = 'en-US'
    rec.interimResults = false
    rec.maxAlternatives = 1
    rec.onresult = (e: any) => {
      const transcript: string = e.results[0][0].transcript
      patch({ demo_description: (spec.demo_description ? spec.demo_description + ' ' : '') + transcript })
    }
    rec.start()
  }

  const handleImproveWithAI = async () => {
    setAiBusy(true)
    setAiErr(null)
    try {
      const resp = await fetch('/api/ai/improve-description', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          text:                 spec.demo_description ?? '',
          scenario_name:        spec.name,
          scenario_description: spec.description,
        }),
      })
      if (!resp.ok) throw new Error(`${resp.status}: ${await resp.text()}`)
      const data = await resp.json() as { improved: string }
      patch({ demo_description: data.improved })
    } catch (e) {
      setAiErr(String(e))
    } finally {
      setAiBusy(false)
    }
  }

  // ── Save ──────────────────────────────────────────────────────────────────
  const handleSave = async () => {
    if (!spec.name.trim()) { setErr('Name is required'); return }
    setBusy(true)
    setErr(null)
    try {
      // Merge physicsParams into spec before saving.
      // null plant_* values (linked) are omitted; the server uses the engine value.
      const specWithPhysics: ScenarioSpec = {
        ...spec,
        // Thermal — engine values
        dt_thermal_seconds: physicsParams.dt_thermal_seconds,
        alpha_max:           physicsParams.alpha_max,
        tau_seconds:         physicsParams.tau_seconds,
        // Plant variants (null = linked = server uses engine value)
        plant_dt_thermal_seconds: physicsParams.plant_dt_thermal_seconds ?? undefined,
        plant_alpha_max:          physicsParams.plant_alpha_max ?? undefined,
        plant_tau_seconds:        physicsParams.plant_tau_seconds ?? undefined,
        plant_pue_base:           physicsParams.plant_pue_base ?? undefined,
        plant_dt_lead_seconds:    physicsParams.plant_dt_lead_seconds ?? undefined,
        // Reserve check
        anchor_reserve_pct:       physicsParams.anchor_reserve_pct,
        band_pct_calibrated:      physicsParams.band_pct_calibrated,
        band_mult_uncalibrated:   physicsParams.band_mult_uncalibrated,
        band_mult_unmapped_hw:    physicsParams.band_mult_unmapped_hw,
        // Site
        site_latitude:            physicsParams.site_latitude,
        site_utc_offset_h:        physicsParams.site_utc_offset_h,
        ambient_temp_base_c:      physicsParams.ambient_temp_base_c,
        // Storage display bounds
        soc_floor_pct:            physicsParams.soc_floor_pct,
        soc_ceil_pct:             physicsParams.soc_ceil_pct,
        // Advisory agents
        advisory_interval_s:      physicsParams.advisory_interval_s,
        advisory_max_mw:          physicsParams.advisory_max_mw,
      }
      const result = editId
        ? await updateScenario(editId, specWithPhysics)
        : await createScenario(specWithPhysics)
      setWarnings(result.c_rate_warnings)
      onSaved(result.scenario_id)
    } catch (e) {
      setErr(String(e))
    } finally {
      setBusy(false)
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/60"
      onClick={onClose}
    >
      <div
        className="relative z-50 flex flex-col w-[820px] max-h-[92vh] rounded-xl border border-border bg-surface shadow-2xl overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4 flex-shrink-0">
          <h2 className="text-sm font-semibold text-text">
            {editId ? 'Edit Scenario' : 'New Scenario'}
          </h2>
          <button
            onClick={onClose}
            className="text-muted hover:text-text text-lg leading-none"
            aria-label="Close"
          >×</button>
        </div>

        {/* Scrollable body — two-column layout */}
        <div className="flex-1 overflow-y-auto text-sm">
        <div className="grid grid-cols-2 gap-0 divide-x divide-border">

          {/* ── Left column: Identity + Fleet ───────────────────────────── */}
          <div className="px-6 py-4 space-y-6">

          {/* ── Section 1: Identity ─────────────────────────────────────── */}
          <section>
            <SectionHeader title="Identity" />
            <div className="space-y-2">
              <label className="flex flex-col gap-0.5">
                <span className="text-[10px] text-muted">Name *</span>
                <input
                  className="w-full rounded border border-border bg-canvas px-2 py-1 text-xs text-text
                             focus:outline-none focus:ring-1 focus:ring-accent"
                  value={spec.name}
                  placeholder="my-scenario"
                  onChange={e => patch({ name: e.target.value })}
                />
              </label>
              <label className="flex flex-col gap-0.5">
                <span className="text-[10px] text-muted">Description</span>
                <textarea
                  className="w-full rounded border border-border bg-canvas px-2 py-1 text-xs text-text
                             focus:outline-none focus:ring-1 focus:ring-accent resize-y"
                  rows={5}
                  value={spec.description}
                  onChange={e => patch({ description: e.target.value })}
                />
              </label>

              {/* ── Scenario Presentation copy ──────────────────────────── */}
              <div className="flex flex-col gap-1">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-muted">Scenario Presentation</span>
                  <div className="flex gap-1">
                    <button
                      type="button"
                      onClick={handleStt}
                      title="Dictate with microphone (browser STT)"
                      className="rounded border border-border px-2 py-0.5 text-[10px] text-muted
                                 hover:border-accent hover:text-accent transition-colors"
                    >
                      🎤 STT
                    </button>
                    <button
                      type="button"
                      onClick={handleImproveWithAI}
                      disabled={aiBusy}
                      title="Generate or improve with Mistral AI"
                      className="rounded border border-accent/60 px-2 py-0.5 text-[10px] text-accent
                                 hover:bg-accent/10 disabled:opacity-40 transition-colors"
                    >
                      {aiBusy ? '…generating' : '✨ Improve With AI'}
                    </button>
                  </div>
                </div>
                <textarea
                  className="w-full rounded border border-border bg-canvas px-2 py-1 text-xs text-text
                             focus:outline-none focus:ring-1 focus:ring-accent resize-none"
                  rows={3}
                  placeholder="Write what this scenario demonstrates for operators watching live…"
                  value={spec.demo_description ?? ''}
                  onChange={e => patch({ demo_description: e.target.value })}
                />
                {aiErr && (
                  <p className="text-[10px] text-danger font-mono truncate" title={aiErr}>{aiErr}</p>
                )}
              </div>
            </div>
          </section>

          {/* ── Section 2: Fleet ────────────────────────────────────────── */}
          <section>
            <SectionHeader title="Fleet" />

            {/* BESS units */}
            <div className="mb-4">
              <div className="mb-1 flex items-center justify-between">
                <span className="text-[10px] text-muted">BESS Units</span>
                <button className="text-[10px] text-accent hover:underline" onClick={addBess}>
                  + Add BESS
                </button>
              </div>
              <div className="space-y-3">
                {spec.bess_units.map((b, i) => (
                  <div key={i} className="rounded border border-border bg-canvas p-3 space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-mono text-muted">{b.asset_id}</span>
                      <div className="flex items-center gap-2">
                        <CRateBadge b={b} />
                        {spec.bess_units.length > 1 && (
                          <button className="text-[10px] text-danger hover:underline"
                            onClick={() => removeBess(i)}>remove</button>
                        )}
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <NumField label="Rated" unit="MW" value={b.rated_mw} min={0.1} step={0.5}
                        onChange={v => patchBess(i, { rated_mw: v })} />
                      <NumField label="Usable" unit="MWh" value={b.usable_mwh} min={0.1} step={0.5}
                        onChange={v => patchBess(i, { usable_mwh: v })} />
                    </div>

                    <SliderField
                      label="Initial SoC"
                      value={b.initial_soc_fraction}
                      min={0.1} max={1.0} step={0.05}
                      unit=""
                      decimals={2}
                      onChange={v => patchBess(i, { initial_soc_fraction: v })}
                    />

                    {/* Grid-forming pill toggle */}
                    <div className="space-y-1">
                      <button
                        onClick={() => patchBess(i, { grid_forming: !b.grid_forming })}
                        className={`px-2.5 py-1 rounded text-[10px] font-mono transition-colors border
                          ${b.grid_forming
                            ? 'bg-accent/15 text-accent border-accent/40'
                            : 'bg-canvas text-muted border-border hover:border-text-muted'
                          }`}
                      >
                        {b.grid_forming ? '● Grid-forming anchor' : '○ Grid-following'}
                      </button>
                      <p className="text-[9px] text-muted leading-snug">
                        {b.grid_forming
                          ? 'Provides voltage/frequency reference for the islanded network. §7.1.2: one unit only.'
                          : 'Takes reference from the anchor unit or upstream grid.'}
                      </p>
                    </div>

                    {cRateWarning(b) && (
                      <p className="text-[9px] text-orange-400">{cRateWarning(b)}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Turbine units */}
            <div>
              <div className="mb-1 flex items-center justify-between">
                <span className="text-[10px] text-muted">Turbine Units</span>
                <button className="text-[10px] text-accent hover:underline" onClick={addTurbine}>
                  + Add Turbine
                </button>
              </div>
              <div className="space-y-2">
                {spec.turbine_units.map((t, i) => (
                  <div key={i} className="rounded border border-border bg-canvas p-2 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-mono text-muted">{t.asset_id}</span>
                      {spec.turbine_units.length > 1 && (
                        <button className="text-[10px] text-danger hover:underline"
                          onClick={() => removeTurbine(i)}>remove</button>
                      )}
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <NumField label="Rated" unit="MW" value={t.rated_mw} min={0.1} step={1}
                        onChange={v => patchTurbine(i, { rated_mw: v })} />
                      <NumField label="Ramp rate" unit="MW/s" value={t.r_asset_mw_per_s} min={0.01} step={0.05}
                        onChange={v => patchTurbine(i, { r_asset_mw_per_s: v })} />
                    </div>
                    {/* Initial standby tier — determines start-sequence duration */}
                    <div className="flex flex-col gap-0.5">
                      <span className="text-[10px] text-muted">Initial standby</span>
                      <div className="grid grid-cols-3 gap-1">
                        {(['hot', 'warm', 'cold'] as const).map(tier => {
                          const active = (t.thermal_state ?? 'cold') === tier
                          const label  = tier.charAt(0).toUpperCase() + tier.slice(1)
                          const hint   = tier === 'hot' ? '~5 min' : tier === 'warm' ? '~10 min' : '~15 min'
                          return (
                            <button
                              key={tier}
                              onClick={() => patchTurbine(i, { thermal_state: tier })}
                              className={[
                                'flex flex-col items-center py-1 rounded border text-[9px] leading-tight transition-colors',
                                active
                                  ? 'border-accent bg-accent/10 text-accent font-semibold'
                                  : 'border-border text-muted hover:border-accent/50',
                              ].join(' ')}
                            >
                              <span>{label}</span>
                              <span className="opacity-60">{hint}</span>
                            </button>
                          )
                        })}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* ── GPU Compute Fleet ───────────────────────────────────────── */}
            <div>
              <div className="mb-1 flex items-center justify-between">
                <span className="text-[10px] text-muted">GPU Compute Fleet</span>
                <button
                  className="text-[10px] text-accent hover:underline"
                  onClick={() => patch({ kube_config: spec.kube_config ? null : defaultKube() })}
                >
                  {spec.kube_config ? '− Disable' : '+ Enable'}
                </button>
              </div>

              {spec.kube_config ? (
                <div className="rounded border border-border bg-canvas p-3 space-y-3">
                  {/* Hardware profile */}
                  <div className="flex flex-col gap-0.5">
                    <span className="text-[10px] text-muted">Hardware profile</span>
                    <select
                      className="w-full rounded border border-border bg-canvas px-2 py-1 text-xs text-text
                                 focus:outline-none focus:ring-1 focus:ring-accent"
                      value={spec.kube_config.hardware_profile_id}
                      onChange={e => patchKube({ hardware_profile_id: e.target.value })}
                    >
                      {HARDWARE_PROFILES.map(p => (
                        <option key={p.id} value={p.id}>{p.label}</option>
                      ))}
                    </select>
                  </div>

                  {/* Peak nodes + computed MW */}
                  <div className="grid grid-cols-2 gap-3">
                    <div className="flex flex-col gap-0.5">
                      <span className="text-[10px] text-muted">GPU nodes (peak)</span>
                      <input
                        type="number"
                        min={1}
                        step={50}
                        className="w-full rounded border border-border bg-canvas px-2 py-1 text-xs text-text
                                   focus:outline-none focus:ring-1 focus:ring-accent"
                        value={spec.kube_config.max_nodes}
                        onChange={e => patchKube({ max_nodes: Math.max(1, parseInt(e.target.value) || 1) })}
                      />
                    </div>
                    <div className="flex flex-col gap-0.5 justify-end">
                      <span className="text-[10px] text-muted">Peak demand</span>
                      <div className="flex items-center h-[26px] px-2 rounded border border-accent/30 bg-accent/5">
                        <span className="text-xs font-mono text-accent font-semibold">
                          {peakMw(spec.kube_config, spec.pue_base).toFixed(1)} MW
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Idle nodes + computed idle MW */}
                  <div className="grid grid-cols-2 gap-3">
                    <div className="flex flex-col gap-0.5">
                      <span className="text-[10px] text-muted">GPU nodes (idle)</span>
                      <input
                        type="number"
                        min={1}
                        step={25}
                        className="w-full rounded border border-border bg-canvas px-2 py-1 text-xs text-text
                                   focus:outline-none focus:ring-1 focus:ring-accent"
                        value={spec.kube_config.min_nodes}
                        onChange={e => patchKube({ min_nodes: Math.max(1, parseInt(e.target.value) || 1) })}
                      />
                    </div>
                    <div className="flex flex-col gap-0.5 justify-end">
                      <span className="text-[10px] text-muted">Idle demand</span>
                      <div className="flex items-center h-[26px] px-2 rounded border border-border/50 bg-canvas">
                        <span className="text-xs font-mono text-muted">
                          {peakMw({ ...spec.kube_config, max_nodes: spec.kube_config.min_nodes }, spec.pue_base).toFixed(1)} MW
                        </span>
                      </div>
                    </div>
                  </div>

                  <p className="text-[9px] text-muted leading-snug">
                    Peak = nodes × {(HW_KW_PER_NODE[spec.kube_config.hardware_profile_id] ?? 10.2).toFixed(1)} kW/node × PUE {spec.pue_base.toFixed(2)} ÷ 1000
                  </p>
                </div>
              ) : (
                <p className="text-[9px] text-muted mt-1 leading-snug">
                  Enable to add a stochastic Kubernetes demand agent — Poisson job arrivals
                  drive the load instead of scripted workload events.
                </p>
              )}
            </div>
          </section>

          </div>{/* /left column */}

          {/* ── Right column: Run Parameters + PMS ──────────────────────── */}
          <div className="px-6 py-4 space-y-6">

          {/* ── Section 3: Run Parameters ────────────────────────────────── */}
          <section>
            <SectionHeader title="Run Parameters" />
            <div className="space-y-4">

              {/* dt_lead slider */}
              <SliderField
                label="Δt_lead — ramp-up lead time"
                value={spec.dt_lead_seconds}
                min={0} max={300} step={5}
                unit=" s"
                decimals={0}
                onChange={v => patch({ dt_lead_seconds: v })}
              />

              {/* PUE slider */}
              <SliderField
                label="PUE base — power usage effectiveness"
                value={spec.pue_base}
                min={1.0} max={2.0} step={0.01}
                unit=""
                decimals={2}
                onChange={v => patch({ pue_base: v })}
              />

              <div className="grid grid-cols-2 gap-2">
                <NumField label="Solar capacity" unit="MW" value={spec.solar_rated_mw} min={0} step={0.5}
                  onChange={v => patch({ solar_rated_mw: v })} />

                {/* Run length — mapped to end_sim_time */}
                <label className="flex flex-col gap-0.5">
                  <span className="text-[10px] text-muted">Run length</span>
                  <select
                    value={nearestDuration(spec.end_sim_time)}
                    onChange={e => patch({ end_sim_time: Number(e.target.value) })}
                    className="w-full rounded border border-border bg-canvas px-2 py-1 text-xs text-text
                               focus:outline-none focus:ring-1 focus:ring-accent"
                  >
                    {DURATION_OPTIONS.map(o => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </label>
              </div>

              {/* Playback speed stored with the scenario */}
              <label className="flex flex-col gap-0.5">
                <span className="text-[10px] text-muted">Default speed</span>
                <select
                  value={spec.default_playback_speed ?? 1}
                  onChange={e => patch({ default_playback_speed: Number(e.target.value) })}
                  className="w-full rounded border border-border bg-canvas px-2 py-1 text-xs text-text
                             focus:outline-none focus:ring-1 focus:ring-accent"
                >
                  {SPEED_OPTIONS.map(o => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </label>

              {/* Hardware profile dropdown */}
              <label className="flex flex-col gap-0.5">
                <span className="text-[10px] text-muted">Hardware profile</span>
                <select
                  value={spec.hardware_profile_id}
                  onChange={e => patch({ hardware_profile_id: e.target.value })}
                  className="w-full rounded border border-border bg-canvas px-2 py-1 text-xs text-text
                             focus:outline-none focus:ring-1 focus:ring-accent"
                >
                  {HARDWARE_PROFILES.map(p => (
                    <option key={p.id} value={p.id}>{p.label}</option>
                  ))}
                </select>
              </label>

              {/* Island mode radio */}
              <RadioGroup
                label="Operating mode"
                value={spec.island_mode ? 'island' : 'grid'}
                options={[
                  {
                    value: 'island',
                    label: 'Island',
                    consequence: 'No grid backup. §7.1.2 anchor reserve active; BESS must bridge any deficit.',
                  },
                  {
                    value: 'grid',
                    label: 'Grid-connected',
                    consequence: 'Grid provides backup; anchor reserve constraint is relaxed.',
                  },
                ]}
                onChange={v => patch({ island_mode: v === 'island' })}
              />

              {/* Physics Parameters button */}
              <div className="rounded border border-border/60 px-3 py-2 space-y-1">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-[10px] text-muted block">Physics parameters</span>
                    <span className="text-[9px] text-muted opacity-60">
                      Thermal · cooling band · reserve check (INV-2)
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setPhysicsOpen(true)}
                    className="rounded border border-accent/50 px-2 py-1 text-[10px] text-accent
                               hover:bg-accent/10 transition-colors font-mono"
                  >
                    ≡ Parameters
                  </button>
                </div>
                {/* Quick summary of non-default values */}
                {physicsParams.band_pct_calibrated > 0 && (
                  <p className="text-[9px] text-muted font-mono">
                    Band ±{physicsParams.band_pct_calibrated}%
                    {physicsParams.anchor_reserve_pct > 0 && ` · anchor ${physicsParams.anchor_reserve_pct}%`}
                    {physicsParams.plant_dt_thermal_seconds != null && ' · thermal unlinked'}
                  </p>
                )}
              </div>

              {/* Irradiance steps table */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] text-muted">Solar irradiance profile (zero-order hold)</span>
                  <button className="text-[10px] text-accent hover:underline" onClick={addIrrStep}>
                    + Add step
                  </button>
                </div>
                <table className="w-full text-[10px] font-mono">
                  <thead>
                    <tr className="text-muted">
                      <th className="text-left pb-1 pr-2 font-normal">t (s)</th>
                      <th className="text-left pb-1 pr-2 font-normal">Irradiance [0–1]</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {spec.irradiance_steps.map(([t, ir], i) => (
                      <tr key={i} className="align-middle">
                        <td className="pr-2 pb-1">
                          <input
                            type="number"
                            className="w-20 rounded border border-border bg-canvas px-1.5 py-0.5 text-text
                                       focus:outline-none focus:ring-1 focus:ring-accent"
                            value={t}
                            min={0}
                            step={1}
                            onChange={e => patchIrr(i, 0, Number(e.target.value))}
                          />
                        </td>
                        <td className="pr-2 pb-1">
                          <input
                            type="number"
                            className="w-20 rounded border border-border bg-canvas px-1.5 py-0.5 text-text
                                       focus:outline-none focus:ring-1 focus:ring-accent"
                            value={ir}
                            min={0} max={1} step={0.05}
                            onChange={e => patchIrr(i, 1, Number(e.target.value))}
                          />
                        </td>
                        <td className="pb-1">
                          {spec.irradiance_steps.length > 1 && (
                            <button
                              onClick={() => removeIrrStep(i)}
                              className="text-muted hover:text-danger transition-colors"
                              aria-label="Remove step"
                            >×</button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="text-[9px] text-muted mt-0.5">
                  Value holds from t until the next step. First step must start at t = 0.
                </p>
              </div>
            </div>
          </section>

          {/* ── Section 4: PMS Configuration ────────────────────────────── */}
          <section>
            <SectionHeader title="PMS Configuration" />
            <div className="space-y-3">
              <label className="flex items-start gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  className="mt-0.5 accent-accent"
                  checked={spec.pms_config !== null}
                  onChange={e => patch({
                    pms_config: e.target.checked ? { transition_mode: 'open_transition' } : null
                  })}
                />
                <div>
                  <div className="text-xs text-text">Enable PMS integration</div>
                  <div className="text-[9px] text-muted leading-snug">
                    Wires a Protection & Management System layer (§28).
                    Exposes fast-shed interlock (TC-64) and SCADA commissioning checks (TC-65).
                  </div>
                </div>
              </label>

              {spec.pms_config !== null && (
                <RadioGroup
                  label="Transition mode"
                  value={spec.pms_config.transition_mode}
                  options={[
                    {
                      value: 'open_transition',
                      label: 'Open transition',
                      consequence: 'Brief coverage discontinuity during source switchover. '
                        + 'Load must ride through the gap.',
                    },
                    {
                      value: 'closed_transition',
                      label: 'Closed transition',
                      consequence: 'Momentary parallel connection: no coverage discontinuity. '
                        + 'Requires both sources live simultaneously.',
                    },
                  ]}
                  onChange={v => patch({ pms_config: { transition_mode: v as 'open_transition' | 'closed_transition' } })}
                />
              )}
            </div>
          </section>

          {/* PROTO-9 C-rate warnings (from last save) */}
          {warnings.length > 0 && (
            <section className="rounded border border-orange-500/30 bg-orange-500/5 p-2">
              <p className="mb-1 text-[10px] font-semibold text-orange-400">PROTO-9 C-rate warnings</p>
              {warnings.map((w, i) => (
                <p key={i} className="text-[9px] text-orange-300">{w}</p>
              ))}
              <p className="mt-1 text-[9px] text-muted">Scenario saved. Warnings are advisory only.</p>
            </section>
          )}

          {err && (
            <p className="text-xs text-danger">{err}</p>
          )}
          </div>{/* /right column */}
        </div>{/* /grid */}
        </div>{/* /scrollable body */}

        {/* Physics Parameters modal (rendered outside the scroll container) */}
        <ParameterModal
          open={physicsOpen}
          onClose={() => setPhysicsOpen(false)}
          initial={physicsParams}
          onApply={setPhysicsParams}
        />

        {/* Footer */}
        <div className="border-t border-border px-4 py-3 flex justify-end gap-2">
          <button
            className="rounded border border-border px-3 py-1 text-xs text-muted hover:text-text"
            onClick={onClose}
            disabled={busy}
          >Cancel</button>
          <button
            className="rounded bg-accent px-3 py-1 text-xs font-semibold text-white
                       hover:bg-accent/80 disabled:opacity-40"
            onClick={handleSave}
            disabled={busy || !spec.name.trim()}
          >{busy ? 'Saving…' : (editId ? 'Update' : 'Create')}</button>
        </div>
      </div>
    </div>
  )
}
