/**
 * PowerSupplySourcesModal.tsx — Select Power Supply modal.
 *
 * Opened from the "Select Power Supply" tag on the Plant Diagram.
 * Shows pill toggles for the five power supply types; reads the
 * current selected scenario spec, lets the operator toggle sources,
 * then PATCHes the scenario on Save.
 *
 * Toggle semantics (match ScenarioBuilder):
 *   BESS            bess_units: [] when off; original units restored on re-enable.
 *   Gas Turbine     turbine_units: [] when off; original units restored on re-enable.
 *   Solar PV        solar_rated_mw: 0 when off; original value restored on re-enable.
 *   Fuel Cell       fuel_cell_enabled: boolean.
 *   Grid Connection island_mode: !srcGrid — Grid on = not islanded.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useScenarioStore } from '../store/scenarioStore'
import type { ScenarioSpec, TurbineUnitSpec, BessUnitSpec } from '../types'

// Pull setSelectedSpec outside render so handleSave can call it without
// adding it to hook dependency lists.
const getSetSelectedSpec = () => useScenarioStore.getState().setSelectedSpec

// ── Fallback unit specs ────────────────────────────────────────────────────────
// Used when enabling a source that was never configured in the spec, or whose
// units were stripped by a prior save.  Values match the demo-20mw baseline.

const FALLBACK_TURBINE_UNITS: TurbineUnitSpec[] = [
  {
    asset_id: 'gt-1', rated_mw: 10.0, r_asset_mw_per_s: 1.0,
    gt_mode: 'frame', hot_standby: false, breaker_closed: true,
    no_load_mw: 0.0, msl_mw: 2.8, sync_relay_state: 'permissive',
  },
]
const FALLBACK_BESS_UNITS: BessUnitSpec[] = [
  { asset_id: 'bess-1', rated_mw: 5.0, usable_mwh: 2.5, initial_soc_fraction: 1.0, grid_forming: false },
]
const FALLBACK_SOLAR_MW = 1.0

// ── Types ──────────────────────────────────────────────────────────────────────

interface SourceState {
  bess:    boolean
  turbine: boolean
  solar:   boolean
  fuelCell:boolean
  grid:    boolean
}

// ── Colour tokens ──────────────────────────────────────────────────────────────

const C = {
  bg:   '#0c1219',
  bg2:  '#101820',
  bd:   '#1c2733',
  bds:  '#2c3b4a',
  tx:   '#d7dde3',
  txd:  '#8b96a3',
  txm:  '#54616f',
  teal: '#3fb6a8',
  bdA:  '#3fb6a8',   // active pill border
}

// ── Pill button ────────────────────────────────────────────────────────────────

function Pill({
  label, active, onClick,
}: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '10px 14px', borderRadius: 6, cursor: 'pointer',
        border: `1.5px solid ${active ? C.bdA : C.bd}`,
        background: active ? 'rgba(63,182,168,0.06)' : C.bg2,
        transition: 'border-color 0.15s, background 0.15s',
        fontFamily: "'JetBrains Mono',ui-monospace,monospace",
        fontSize: 12, color: active ? C.teal : C.txd,
        width: '100%', textAlign: 'left',
      }}
    >
      <span style={{
        width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
        background: active ? C.teal : 'transparent',
        border: `1.5px solid ${active ? C.teal : C.txm}`,
        transition: 'background 0.15s, border-color 0.15s',
      }} />
      {label}
    </button>
  )
}

// ── Main component ─────────────────────────────────────────────────────────────

interface PowerSupplySourcesModalProps {
  onClose: () => void
}

export function PowerSupplySourcesModal({ onClose }: PowerSupplySourcesModalProps) {
  const selectedId = useScenarioStore(s => s.selectedId)

  // Original spec values — used to restore when a source is re-enabled
  const origSpec = useRef<ScenarioSpec | null>(null)

  // Last known non-empty unit arrays / non-zero solar MW.
  // Pre-seeded with fallback defaults so toggling ON always has something to restore,
  // even when the scenario was never configured with that source type.
  const savedTurbineUnits = useRef<TurbineUnitSpec[]>(FALLBACK_TURBINE_UNITS)
  const savedBessUnits    = useRef<BessUnitSpec[]>(FALLBACK_BESS_UNITS)
  const savedSolarMW      = useRef<number>(FALLBACK_SOLAR_MW)

  const [loading, setSaving_] = useState(true)
  const [saving,  setSaving]  = useState(false)
  const [saved,   setSaved]   = useState(false)
  const [error,   setError]   = useState<string | null>(null)

  const [sources, setSources] = useState<SourceState>({
    bess: true, turbine: true, solar: true, fuelCell: false, grid: false,
  })

  const dialogRef   = useRef<HTMLDivElement>(null)
  const closeBtnRef = useRef<HTMLButtonElement>(null)

  // Load current spec on open
  useEffect(() => {
    if (!selectedId) { setSaving_(false); return }
    fetch(`/scenarios/${selectedId}`, { credentials: 'include' })
      .then(r => r.ok ? r.json() : null)
      .then((data: { spec?: ScenarioSpec } | null) => {
        const spec = data?.spec
        if (spec) {
          origSpec.current = spec
          // Update last-known-good refs whenever the spec has real units/values.
          if (spec.turbine_units?.length)  savedTurbineUnits.current = spec.turbine_units
          if (spec.bess_units?.length)     savedBessUnits.current    = spec.bess_units
          if ((spec.solar_rated_mw ?? 0) > 0) savedSolarMW.current  = spec.solar_rated_mw!
          setSources({
            bess:     (spec.bess_units?.length ?? 0) > 0,
            turbine:  (spec.turbine_units?.length ?? 0) > 0,
            solar:    (spec.solar_rated_mw ?? 0) > 0,
            fuelCell: spec.fuel_cell_enabled ?? false,
            grid:     !(spec.island_mode ?? true),
          })
        }
        setSaving_(false)
      })
      .catch(() => setSaving_(false))
  }, [selectedId])

  // Focus
  useEffect(() => { closeBtnRef.current?.focus() }, [])

  // Escape / Tab trap
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') onClose()
    if (e.key === 'Tab' && dialogRef.current) {
      const els = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>('button,[tabindex]:not([tabindex="-1"])')
      ).filter(el => !el.hasAttribute('disabled'))
      if (!els.length) return
      if (e.shiftKey && document.activeElement === els[0]) { e.preventDefault(); els[els.length - 1].focus() }
      else if (!e.shiftKey && document.activeElement === els[els.length - 1]) { e.preventDefault(); els[0].focus() }
    }
  }, [onClose])
  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  const toggle = (key: keyof SourceState) =>
    setSources(prev => ({ ...prev, [key]: !prev[key] }))

  const handleSave = async () => {
    if (!selectedId || !origSpec.current) return
    setSaving(true); setError(null)
    const orig = origSpec.current

    // Build patch fields from toggle states.
    // When re-enabling a source whose units were previously stripped (empty array),
    // fall back to the last known non-empty units saved in the refs, or to the
    // module-level fallback defaults when the spec never had that source type.
    const patch: Partial<ScenarioSpec> = {
      turbine_units:    sources.turbine
        ? (orig.turbine_units?.length ? orig.turbine_units : savedTurbineUnits.current)
        : [],
      bess_units:       sources.bess
        ? (orig.bess_units?.length    ? orig.bess_units    : savedBessUnits.current)
        : [],
      solar_rated_mw:   sources.solar
        ? ((orig.solar_rated_mw ?? 0) > 0 ? orig.solar_rated_mw : savedSolarMW.current)
        : 0,
      fuel_cell_enabled: sources.fuelCell,
      island_mode:       !sources.grid,
    }

    try {
      // API only supports PUT (full spec replacement — no PATCH endpoint).
      // Merge toggle-driven fields into the original spec so unchanged fields are preserved.
      const fullSpec = { ...orig, ...patch }
      const resp = await fetch(`/scenarios/${selectedId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(fullSpec),
      })
      if (!resp.ok) throw new Error(await resp.text())
      setSaved(true)
      // Push the saved spec directly into the shared store so PlantDiagram
      // reflects the change immediately — no round-trip fetch required.
      getSetSelectedSpec()(fullSpec as ScenarioSpec)
      setTimeout(() => { setSaved(false); onClose() }, 900)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const pills: { key: keyof SourceState; label: string }[] = [
    { key: 'bess',     label: 'BESS'                    },
    { key: 'turbine',  label: 'Gas Turbine Fleet'        },
    { key: 'solar',    label: 'Solar PV'                 },
    { key: 'fuelCell', label: 'Fuel Cell Module Array'   },
    { key: 'grid',     label: 'Grid Connection'          },
  ]

  const content = (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Select power supply sources"
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        background: 'rgba(0,0,0,0.60)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 24,
      }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        ref={dialogRef}
        style={{
          width: '100%', maxWidth: 420,
          background: C.bg, border: `1px solid ${C.bds}`,
          borderRadius: 8,
          fontFamily: "'JetBrains Mono',ui-monospace,monospace",
          color: C.tx,
        }}
      >
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '16px 18px 12px', borderBottom: `1px solid ${C.bd}`,
        }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, letterSpacing: '0.06em', color: C.teal }}>
              POWER SUPPLY SOURCES
            </div>
            <div style={{ fontSize: 11, color: C.txd, marginTop: 4, letterSpacing: '0.01em' }}>
              Click to add or remove supply types for this scenario.
            </div>
          </div>
          <button
            ref={closeBtnRef}
            onClick={onClose}
            style={{
              background: 'none', border: 'none', color: C.txm,
              cursor: 'pointer', fontSize: 20, lineHeight: 1, padding: 2, flexShrink: 0,
            }}
            aria-label="Close"
          >×</button>
        </div>

        {/* Pills grid */}
        <div style={{ padding: '16px 18px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          {loading && (
            <div style={{ gridColumn: '1 / -1', fontSize: 11, color: C.txm, padding: '8px 0' }}>
              Loading scenario…
            </div>
          )}
          {!loading && pills.map(({ key, label }) => (
            <Pill
              key={key}
              label={label}
              active={sources[key]}
              onClick={() => toggle(key)}
            />
          ))}
        </div>

        {/* Error */}
        {error && (
          <div style={{
            margin: '0 18px 12px',
            padding: '8px 12px', borderRadius: 5,
            background: 'rgba(248,81,73,0.08)',
            border: '1px solid rgba(248,81,73,0.3)',
            fontSize: 10.5, color: '#f85149',
          }}>
            {error}
          </div>
        )}

        {/* Footer */}
        <div style={{
          display: 'flex', justifyContent: 'flex-end', gap: 8,
          padding: '12px 18px', borderTop: `1px solid ${C.bd}`,
        }}>
          <button
            onClick={onClose}
            style={{
              background: 'transparent', border: `1px solid ${C.bds}`,
              color: C.txd, fontFamily: 'inherit', fontSize: 11,
              padding: '8px 18px', borderRadius: 5, cursor: 'pointer',
              letterSpacing: '0.02em',
            }}
          >
            CANCEL
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !selectedId || loading}
            style={{
              background: saved ? 'rgba(63,182,168,0.15)' : 'transparent',
              border: `1px solid ${saved ? C.teal : 'rgba(63,182,168,0.5)'}`,
              color: saved ? C.teal : 'rgba(63,182,168,0.9)',
              fontFamily: 'inherit', fontSize: 11, fontWeight: 600,
              padding: '8px 18px', borderRadius: 5,
              cursor: saving || !selectedId || loading ? 'not-allowed' : 'pointer',
              letterSpacing: '0.02em',
              opacity: saving || !selectedId || loading ? 0.6 : 1,
              transition: 'all 0.15s',
            }}
          >
            {saved ? '✓ SAVED' : saving ? 'SAVING…' : 'SAVE'}
          </button>
        </div>
      </div>
    </div>
  )

  return createPortal(content, document.body)
}
