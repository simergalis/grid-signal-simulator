/**
 * ScenarioBuilder.tsx — Right-side drawer for creating/editing scenarios (Step 8).
 *
 * Three sections:
 *   1. Identity — name, description
 *   2. Fleet    — BESS units (add/remove, live C-rate indicator) + turbines
 *   3. Run Params — solar, dt_lead, end_sim_time, island_mode, pue_base
 *
 * Props:
 *   editId     — scenario_id to edit, or null to create new
 *   onClose    — dismiss the drawer (no save)
 *   onSaved    — called with scenario_id after successful save
 *
 * D12 / PROTO-9: C-rate warnings appear inline per BESS unit in orange.
 * §7.1.2: the UI allows only one grid_forming=true at a time; selecting
 *         grid_forming on a second unit clears the previous anchor.
 */

import { useEffect, useState } from 'react'
import { useScenarioStore } from '../store/scenarioStore'
import type { BessUnitSpec, TurbineUnitSpec, ScenarioSpec } from '../types'

// ── C-rate helper ────────────────────────────────────────────────────────────

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

// ── CRateBadge ───────────────────────────────────────────────────────────────

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

// ── Defaults ─────────────────────────────────────────────────────────────────

function defaultBess(index: number): BessUnitSpec {
  return {
    asset_id: `bess-${index}`,
    rated_mw: 5.0,
    usable_mwh: 2.5,
    initial_soc_fraction: 0.95,
    grid_forming: index === 0,  // first unit defaults to anchor
  }
}

function defaultTurbine(index: number): TurbineUnitSpec {
  return {
    asset_id: `turbine-${index}`,
    rated_mw: 10.0,
    r_asset_mw_per_s: 0.2,
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
  }
}

// ── Number field helper ───────────────────────────────────────────────────────

function NumField({
  label, value, min, max, step = 0.1, onChange,
}: {
  label: string; value: number; min?: number; max?: number; step?: number;
  onChange: (v: number) => void
}) {
  return (
    <label className="flex flex-col gap-0.5">
      <span className="text-[10px] text-muted">{label}</span>
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

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  editId: string | null
  onClose: () => void
  onSaved: (scenarioId: string) => void
}

export function ScenarioBuilder({ editId, onClose, onSaved }: Props) {
  const createScenario = useScenarioStore(s => s.createScenario)
  const updateScenario = useScenarioStore(s => s.updateScenario)

  const [spec, setSpec]   = useState<ScenarioSpec>(blankSpec())
  const [busy, setBusy]   = useState(false)
  const [err,  setErr]    = useState<string | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])

  // If editing, load the existing spec
  useEffect(() => {
    if (!editId) {
      setSpec(blankSpec())
      return
    }
    fetch(`/scenarios/${editId}`)
      .then(r => r.json())
      .then(d => {
        setSpec(d.spec as ScenarioSpec)
        setWarnings(d.c_rate_warnings ?? [])
      })
      .catch(e => setErr(String(e)))
  }, [editId])

  // Patch helpers
  const patch = (partial: Partial<ScenarioSpec>) =>
    setSpec(prev => ({ ...prev, ...partial }))

  // ── BESS mutations ───────────────────────────────────────────────────────
  const patchBess = (i: number, partial: Partial<BessUnitSpec>) => {
    const updated = spec.bess_units.map((b, idx) => idx === i ? { ...b, ...partial } : b)
    // §7.1.2: if setting grid_forming on unit i, clear others
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
    // Ensure at least one grid_forming if all removed the anchor
    const hasForming = next.some(b => b.grid_forming)
    patch({ bess_units: hasForming ? next : next.map((b, idx) => ({ ...b, grid_forming: idx === 0 })) })
  }

  // ── Turbine mutations ────────────────────────────────────────────────────
  const patchTurbine = (i: number, partial: Partial<TurbineUnitSpec>) =>
    patch({ turbine_units: spec.turbine_units.map((t, idx) => idx === i ? { ...t, ...partial } : t) })

  const addTurbine = () =>
    patch({ turbine_units: [...spec.turbine_units, defaultTurbine(spec.turbine_units.length)] })

  const removeTurbine = (i: number) => {
    if (spec.turbine_units.length <= 1) return
    patch({ turbine_units: spec.turbine_units.filter((_, idx) => idx !== i) })
  }

  // ── Save ─────────────────────────────────────────────────────────────────
  const handleSave = async () => {
    if (!spec.name.trim()) { setErr('Name is required'); return }
    setBusy(true)
    setErr(null)
    try {
      const result = editId
        ? await updateScenario(editId, spec)
        : await createScenario(spec)
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
    /* Backdrop */
    <div className="fixed inset-0 z-40 flex" onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      {/* Transparent left area — click to close */}
      <div className="flex-1" />

      {/* Drawer */}
      <aside className="relative z-50 flex h-full w-[400px] flex-col border-l border-border bg-surface shadow-xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold text-text">
            {editId ? 'Edit Scenario' : 'New Scenario'}
          </h2>
          <button
            onClick={onClose}
            className="text-muted hover:text-text text-lg leading-none"
            aria-label="Close"
          >×</button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5 text-sm">

          {/* ── Section 1: Identity ── */}
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Identity</h3>
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
                             focus:outline-none focus:ring-1 focus:ring-accent resize-none"
                  rows={2}
                  value={spec.description}
                  onChange={e => patch({ description: e.target.value })}
                />
              </label>
            </div>
          </section>

          {/* ── Section 2: Fleet ── */}
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Fleet</h3>

            {/* BESS units */}
            <div className="mb-3">
              <div className="mb-1 flex items-center justify-between">
                <span className="text-[10px] text-muted">BESS Units</span>
                <button
                  className="text-[10px] text-accent hover:underline"
                  onClick={addBess}
                >+ Add BESS</button>
              </div>
              <div className="space-y-3">
                {spec.bess_units.map((b, i) => (
                  <div key={i} className="rounded border border-border bg-canvas p-2 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-mono text-muted">{b.asset_id}</span>
                      <div className="flex items-center gap-2">
                        <CRateBadge b={b} />
                        {spec.bess_units.length > 1 && (
                          <button
                            className="text-[10px] text-danger hover:underline"
                            onClick={() => removeBess(i)}
                          >remove</button>
                        )}
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-2">
                      <NumField label="Rated MW" value={b.rated_mw} min={0.1} step={0.5}
                        onChange={v => patchBess(i, { rated_mw: v })} />
                      <NumField label="Usable MWh" value={b.usable_mwh} min={0.1} step={0.5}
                        onChange={v => patchBess(i, { usable_mwh: v })} />
                      <NumField label="Initial SoC" value={b.initial_soc_fraction} min={0.1} max={1.0} step={0.05}
                        onChange={v => patchBess(i, { initial_soc_fraction: v })} />
                      <label className="flex flex-col gap-1 pt-3">
                        <span className="text-[10px] text-muted">Grid-forming anchor</span>
                        <input
                          type="checkbox"
                          className="h-3 w-3 accent-accent"
                          checked={b.grid_forming}
                          onChange={e => patchBess(i, { grid_forming: e.target.checked })}
                        />
                        <span className="text-[9px] text-muted">§7.1.2 — one unit max</span>
                      </label>
                    </div>

                    {/* C-rate warning detail */}
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
                <button
                  className="text-[10px] text-accent hover:underline"
                  onClick={addTurbine}
                >+ Add Turbine</button>
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
                      <NumField label="Rated MW" value={t.rated_mw} min={0.1} step={1}
                        onChange={v => patchTurbine(i, { rated_mw: v })} />
                      <NumField label="Ramp MW/s" value={t.r_asset_mw_per_s} min={0.01} step={0.05}
                        onChange={v => patchTurbine(i, { r_asset_mw_per_s: v })} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* ── Section 3: Run Parameters ── */}
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Run Parameters</h3>
            <div className="grid grid-cols-2 gap-2">
              <NumField label="Solar rated MW" value={spec.solar_rated_mw} min={0} step={0.5}
                onChange={v => patch({ solar_rated_mw: v })} />
              <NumField label="dt_lead (s)" value={spec.dt_lead_seconds} min={0} max={300} step={5}
                onChange={v => patch({ dt_lead_seconds: v })} />
              <NumField label="Sim duration (s)" value={spec.end_sim_time} min={60} max={86400} step={60}
                onChange={v => patch({ end_sim_time: v })} />
              <NumField label="PUE base" value={spec.pue_base} min={1.0} max={2.0} step={0.01}
                onChange={v => patch({ pue_base: v })} />
            </div>

            <div className="mt-2 flex items-center gap-2">
              <input
                id="island_mode"
                type="checkbox"
                className="h-3 w-3 accent-accent"
                checked={spec.island_mode}
                onChange={e => patch({ island_mode: e.target.checked })}
              />
              <label htmlFor="island_mode" className="text-xs text-text cursor-pointer">
                Island mode (§7.1.2 anchor reserve active)
              </label>
            </div>
          </section>

          {/* API-level C-rate warnings (from last save) */}
          {warnings.length > 0 && (
            <section className="rounded border border-orange-500/30 bg-orange-500/5 p-2">
              <p className="mb-1 text-[10px] font-semibold text-orange-400">PROTO-9 C-rate warnings</p>
              {warnings.map((w, i) => (
                <p key={i} className="text-[9px] text-orange-300">{w}</p>
              ))}
              <p className="mt-1 text-[9px] text-muted">Scenario saved successfully. Warnings are advisory only.</p>
            </section>
          )}

          {/* Error */}
          {err && (
            <p className="text-xs text-danger">{err}</p>
          )}
        </div>

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
      </aside>
    </div>
  )
}
