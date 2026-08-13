/**
 * GridConnectionModal.tsx — Grid Connection configuration modal.
 *
 * Implements GS-DES-GRID-001: two independent sections (INBOUND / OUTBOUND)
 * with full parameter surface from the schema document.
 *
 * Advisory boundary:
 *   Anti-islanding, droop, reverse-power, and PCC control are read-only rows.
 *   GridSignal advises; PMS owns. Hardcoded per §8 of GS-DES-GRID-001.
 *
 * GP-4: The entire OUTBOUND section is absent (not just disabled) when
 * connectionMode === 'islanded'.
 *
 * Data:
 *   config   — local React state; "Save" persists within the session.
 *   telemetry — live tick fields (grid_import_mw / grid_export_mw); falls back
 *               to 0 for islanded runs where no PCC meter is wired.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import type { TickPayload } from '../types'

// ── Types (GS-DES-GRID-001 §5) ───────────────────────────────────────────────

type ConnectionMode        = 'islanded' | 'grid_tied' | 'hybrid'
type TransitionMode        = 'open' | 'closed' | 'delayed' | 'soft_load'
type PriceFeedSource       = 'utility_tou_tariff' | 'iso_day_ahead' | 'fixed_rate'
type ExportMode            = 'none' | 'net_metering' | 'wholesale_economic'
                           | 'demand_response' | 'vpp_dispatch' | 'emergency_grid_support'
type ExportPriceFeedSource = 'iso_real_time_lmp' | 'bilateral_ppa_rate' | 'none'

interface GridConfig {
  connectionMode:                      ConnectionMode
  pGridFirmMw:                         number
  pGridReservedMw:                     number
  tReserveHours:                       number
  spotImportEnabled:                   boolean
  pGridSpotCapMw:                      number
  transitionMode:                      TransitionMode
  pccImportLimitMw:                    number
  demandChargeThresholdMw:             number | null
  procurementBudgetWindowUsd:          string
  procurementBudgetPeriodUsd:          string
  priceFeedSource:                     PriceFeedSource
  exportEnabled:                       boolean
  exportMode:                          ExportMode
  pExportMaxMw:                        number
  exportRampRateLimitMwPerMin:         number | null
  powerFactorMin:                      number
  exportPriceFeedSource:               ExportPriceFeedSource
  utilityCurtailExportChannelEnabled:  boolean
  backupGensetExportEligible:          boolean
}

// ── Advisory boundary constants (GS-DES-GRID-001 §8) ─────────────────────────

const ADVISORY_INBOUND = [
  { label: 'Anti-islanding protection',  authority: 'PMS owns · always commands' }, // §11 — PG&E mandated trip-on-grid-loss
  { label: 'Droop secondary regulation', authority: 'PMS owns · never commands'  }, // §12 — no secondary regulation unless grid services enrolled
] as const

const ADVISORY_OUTBOUND = [
  { label: 'Reverse-power protection',          authority: 'PMS owns · never commands'       },
  { label: 'Point-of-common-coupling control',  authority: 'PMS owns · grid-code compliance' },
] as const

// ── Default state ──────────────────────────────────────────────────────────────

// PG&E B-19 TOU recommended defaults for a GPU data-centre interconnect.
// Source: GS-DES-GRID-001 §5 + PG&E interconnection guidance.
const DEFAULT_CONFIG: GridConfig = {
  connectionMode:                     'grid_tied',   // §1 — continuous grid connectivity
  pGridFirmMw:                        50,            // §2 — mid-to-large GPU farm contracted capacity
  pGridReservedMw:                    10,            // §3 — 20 % headroom for future GPU scaling
  tReserveHours:                      24,            // §4 — PG&E 24–48 h reservation lead time
  spotImportEnabled:                  true,          // §5 — non-firm off-peak cost savings
  pGridSpotCapMw:                     5,             // §5 — conservative non-firm spot cap
  transitionMode:                     'closed',      // §6 — synchronized (closed-transition) switching
  pccImportLimitMw:                   50,            // §7 — matches firm contracted capacity
  demandChargeThresholdMw:            40,            // §8 — 80 % of firm cap; avoids demand-charge penalty
  procurementBudgetWindowUsd:         '100000',      // §9 — monthly window budget
  procurementBudgetPeriodUsd:         '100000',      // §9 — period ceiling
  priceFeedSource:                    'utility_tou_tariff', // §10 — PG&E B-19 TOU tariff
  exportEnabled:                      false,
  exportMode:                         'none',
  pExportMaxMw:                       0,
  exportRampRateLimitMwPerMin:        null,
  powerFactorMin:                     0.95,
  exportPriceFeedSource:              'none',
  utilityCurtailExportChannelEnabled: true,
  backupGensetExportEligible:         false,
}

// ── Colour tokens (match design HTML) ─────────────────────────────────────────

const C = {
  bg:   '#0a0f16',
  bg2:  '#101820',
  bg3:  '#0c1219',
  bd:   '#1c2733',
  bds:  '#2c3b4a',
  tx:   '#d7dde3',
  txd:  '#8b96a3',
  txm:  '#54616f',
  teal: '#5dcaa5',
  amber:'#e8b563',
  coral:'#e8916b',
  blue: '#7fa8d8',
}

// ── Shared sub-components ─────────────────────────────────────────────────────

function SectionHeader({
  dir, label, extra,
}: {
  dir: 'in' | 'out'
  label: string
  extra?: React.ReactNode
}) {
  const color = dir === 'in' ? C.blue : C.coral
  const arrow = dir === 'in' ? '↓' : '↑'
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '10px 0 8px', borderBottom: `1px solid ${C.bd}`, marginBottom: 2,
    }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 7,
                     fontSize: 11, letterSpacing: '0.08em', color: C.txd }}>
        <span style={{ color, fontSize: 14 }}>{arrow}</span>
        {label}
      </span>
      {extra}
    </div>
  )
}

function Row({
  label, hint, children,
}: {
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '9px 0', borderBottom: `1px solid ${C.bg2}`, gap: 16,
    }}>
      <div style={{ fontSize: 11.5, color: C.txd, letterSpacing: '0.01em', flex: 1, lineHeight: 1.4 }}>
        {label}
        {hint && (
          <span style={{ display: 'block', fontSize: 9.5, color: C.txm, marginTop: 2, letterSpacing: '0.01em' }}>
            {hint}
          </span>
        )}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
        {children}
      </div>
    </div>
  )
}

function AdvisoryRow({ label, authority }: { label: string; authority: string }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '9px 0', borderBottom: `1px solid ${C.bg2}`,
    }}>
      <span style={{ fontSize: 11.5, color: C.txd }}>{label}</span>
      <div style={{ textAlign: 'right' }}>
        <span style={{ fontSize: 11, color: C.teal }}>GridSignal advises</span>
        <span style={{ display: 'block', fontSize: 9.5, color: C.txm, marginTop: 1 }}>{authority}</span>
      </div>
    </div>
  )
}

const INPUT_STYLE: React.CSSProperties = {
  width: 82, background: C.bg2, border: `1px solid ${C.bd}`,
  color: C.tx, fontFamily: 'inherit', fontSize: 12,
  padding: '5px 7px', borderRadius: 4, textAlign: 'right',
  outline: 'none',
}
const SELECT_STYLE: React.CSSProperties = {
  background: C.bg2, border: `1px solid ${C.bd}`,
  color: C.tx, fontFamily: 'inherit', fontSize: 11.5,
  padding: '5px 7px', borderRadius: 4, outline: 'none',
}
const UNIT_STYLE: React.CSSProperties = { fontSize: 10.5, color: C.txm }

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label style={{ position: 'relative', width: 32, height: 18, flexShrink: 0, cursor: 'pointer', display: 'inline-block' }}>
      <input
        type="checkbox"
        checked={checked}
        onChange={e => onChange(e.target.checked)}
        style={{ opacity: 0, width: 0, height: 0 }}
      />
      <span style={{
        position: 'absolute', inset: 0,
        background: checked ? 'rgba(93,202,165,0.25)' : C.bd,
        borderRadius: 9, transition: '0.15s',
      }}>
        <span style={{
          position: 'absolute', width: 14, height: 14, top: 2,
          left: checked ? 16 : 2, background: checked ? C.teal : C.txd,
          borderRadius: '50%', transition: '0.15s', display: 'block',
        }} />
      </span>
    </label>
  )
}

// ── Validation ────────────────────────────────────────────────────────────────

function validate(cfg: GridConfig): string[] {
  const errors: string[] = []
  if (cfg.pccImportLimitMw <= 0) errors.push('PCC import limit must be > 0 MW')
  if (cfg.pGridFirmMw + cfg.pGridReservedMw > cfg.pccImportLimitMw) {
    errors.push('Firm + reserved capacity exceeds PCC import limit')
  }
  if (cfg.connectionMode === 'islanded' && cfg.exportEnabled) {
    errors.push('Export must be disabled when islanded (GP-4)')
  }
  if (cfg.exportMode === 'wholesale_economic' && cfg.exportPriceFeedSource === 'none') {
    errors.push('Wholesale export requires a price feed source')
  }
  if (cfg.powerFactorMin < 0.80 || cfg.powerFactorMin > 1.00) {
    errors.push('Power factor must be between 0.80 and 1.00')
  }
  return errors
}

// ── Main component ─────────────────────────────────────────────────────────────

interface GridConnectionModalProps {
  tick:    TickPayload | null
  onClose: () => void
}

export function GridConnectionModal({ tick, onClose }: GridConnectionModalProps) {
  const [cfg,     setCfg]     = useState<GridConfig>(DEFAULT_CONFIG)
  const [saved,   setSaved]   = useState(false)
  const [errors,  setErrors]  = useState<string[]>([])

  const dialogRef   = useRef<HTMLDivElement>(null)
  const closeBtnRef = useRef<HTMLButtonElement>(null)

  // Live telemetry from tick (0 for islanded scenarios with no PCC meter)
  const mwImported = (tick as unknown as Record<string, number>)?.grid_import_mw ?? 0
  const mwExported = (tick as unknown as Record<string, number>)?.grid_export_mw ?? 0

  // Derived (per schema §4)
  const firmHeadroomMw    = Math.max(0, cfg.pGridFirmMw - mwImported)
  const exportHeadroomMw  = cfg.exportEnabled ? Math.max(0, cfg.pExportMaxMw - mwExported) : 0
  const netPccMw          = mwImported - mwExported

  const isIslanded = cfg.connectionMode === 'islanded'

  // Focus management
  useEffect(() => {
    closeBtnRef.current?.focus()
  }, [])

  // Escape key
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') onClose()
    // Tab trap
    if (e.key === 'Tab' && dialogRef.current) {
      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(
          'button,input,select,[tabindex]:not([tabindex="-1"])'
        )
      ).filter(el => !el.hasAttribute('disabled'))
      if (!focusable.length) return
      const first = focusable[0]
      const last  = focusable[focusable.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault(); last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault(); first.focus()
      }
    }
  }, [onClose])

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  const patch = (partial: Partial<GridConfig>) =>
    setCfg(prev => ({ ...prev, ...partial }))

  const handleSave = () => {
    const errs = validate(cfg)
    if (errs.length > 0) { setErrors(errs); return }
    setErrors([])
    setSaved(true)
    setTimeout(() => setSaved(false), 2500)
  }

  const connModeLabel: Record<ConnectionMode, string> = {
    islanded: 'ISLANDED', grid_tied: 'GRID-TIED', hybrid: 'HYBRID',
  }
  const badgeColor = isIslanded ? C.txm : C.teal

  const content = (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Grid connection configuration"
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        background: 'rgba(0,0,0,0.65)',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
        padding: '24px 12px', overflowY: 'auto',
      }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        ref={dialogRef}
        style={{
          width: '100%', maxWidth: 600,
          background: C.bg, border: `1px solid ${C.bds}`,
          borderRadius: 8, color: C.tx,
          fontFamily: "'JetBrains Mono',ui-monospace,'SF Mono',monospace",
        }}
      >
        {/* ── Header ──────────────────────────────────────────────────── */}
        <div style={{
          display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
          padding: '18px 20px 14px', borderBottom: `1px solid ${C.bd}`,
        }}>
          <div>
            <div style={{ fontSize: 14, letterSpacing: '0.08em', fontWeight: 500,
                          display: 'flex', alignItems: 'center', gap: 8 }}>
              GRID CONNECTION
              <span style={{
                fontSize: 10, letterSpacing: '0.06em', padding: '2px 8px',
                borderRadius: 3, background: `${badgeColor}1e`,
                color: badgeColor, border: `1px solid ${badgeColor}4d`,
              }}>
                {connModeLabel[cfg.connectionMode]}
              </span>
            </div>
            <div style={{ fontSize: 11, color: C.txd, marginTop: 4, letterSpacing: '0.02em' }}>
              bidirectional interconnection · point of common coupling
            </div>
          </div>
          <button
            ref={closeBtnRef}
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: C.txm,
                     cursor: 'pointer', fontSize: 20, lineHeight: 1, padding: 2 }}
            aria-label="Close"
          >×</button>
        </div>

        {/* ── Body ────────────────────────────────────────────────────── */}
        <div style={{ padding: '16px 20px 4px' }}>

          {/* Live stats */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 18 }}>
            {/* MW Imported */}
            <div style={{ background: C.bg2, border: `1px solid ${C.bd}`,
                          borderRadius: 6, padding: '10px 12px' }}>
              <div style={{ fontSize: 9, letterSpacing: '0.08em', color: C.txm, marginBottom: 4 }}>
                MW IMPORTED
              </div>
              <div style={{ fontSize: 20, fontWeight: 500, color: C.tx }}>
                {mwImported.toFixed(2)}
                <span style={{ fontSize: 11, color: C.txd, marginLeft: 2 }}>MW</span>
              </div>
              <div style={{ fontSize: 9, color: C.txm, marginTop: 3 }}>
                headroom: {firmHeadroomMw.toFixed(2)} MW firm · net {netPccMw >= 0 ? '+' : ''}{netPccMw.toFixed(2)} MW
              </div>
            </div>
            {/* MW Exported */}
            <div style={{ background: C.bg2, border: `1px solid ${C.bd}`,
                          borderRadius: 6, padding: '10px 12px' }}>
              <div style={{ fontSize: 9, letterSpacing: '0.08em', color: C.txm, marginBottom: 4 }}>
                MW EXPORTED
              </div>
              <div style={{ fontSize: 20, fontWeight: 500, color: C.txm }}>
                {mwExported.toFixed(2)}
                <span style={{ fontSize: 11, color: C.txm, marginLeft: 2 }}>MW</span>
              </div>
              {cfg.exportEnabled && (
                <div style={{ fontSize: 9, color: C.txm, marginTop: 3 }}>
                  headroom: {exportHeadroomMw.toFixed(2)} MW
                </div>
              )}
              {!cfg.exportEnabled && (
                <div style={{ fontSize: 9, color: C.txm, marginTop: 3 }}>
                  export disabled
                </div>
              )}
            </div>
          </div>

          {/* ── INBOUND ─────────────────────────────────────────────── */}
          <div style={{ marginBottom: 6 }}>
            <SectionHeader dir="in" label="INBOUND · IMPORT" />

            <Row label="Connection mode">
              <select
                value={cfg.connectionMode}
                onChange={e => {
                  const m = e.target.value as ConnectionMode
                  // GP-4: disable export when switching to islanded
                  patch({ connectionMode: m, ...(m === 'islanded' ? { exportEnabled: false } : {}) })
                }}
                style={SELECT_STYLE}
              >
                <option value="islanded">islanded</option>
                <option value="grid_tied">grid-tied</option>
                <option value="hybrid">hybrid (auto-transfer)</option>
              </select>
            </Row>

            <Row label="Firm contracted capacity"
                 hint="P_grid_firm · always available, no lead time">
              <input type="number" min={0} step={0.5} style={INPUT_STYLE}
                value={cfg.pGridFirmMw}
                onChange={e => patch({ pGridFirmMw: Math.max(0, Number(e.target.value)) })} />
              <span style={UNIT_STYLE}>MW</span>
            </Row>

            <Row label="Reserved capacity block"
                 hint="held for a window · counts toward reserve within it">
              <input type="number" min={0} step={0.5} style={INPUT_STYLE}
                value={cfg.pGridReservedMw}
                onChange={e => patch({ pGridReservedMw: Math.max(0, Number(e.target.value)) })} />
              <span style={UNIT_STYLE}>MW</span>
            </Row>

            <Row label="Reservation lead time"
                 hint="T_reserve · market-dependent">
              <input type="number" min={0} step={0.25} style={INPUT_STYLE}
                value={cfg.tReserveHours}
                onChange={e => patch({ tReserveHours: Math.max(0, Number(e.target.value)) })} />
              <span style={UNIT_STYLE}>hrs</span>
            </Row>

            <Row label="Non-firm spot import"
                 hint="reduces load served · never credited to reserve check">
              <Toggle
                checked={cfg.spotImportEnabled}
                onChange={v => patch({ spotImportEnabled: v })} />
              <input
                type="number" min={0} step={0.5}
                style={{ ...INPUT_STYLE, width: 60,
                         opacity: cfg.spotImportEnabled ? 1 : 0.35,
                         pointerEvents: cfg.spotImportEnabled ? 'auto' : 'none' }}
                value={cfg.pGridSpotCapMw}
                onChange={e => patch({ pGridSpotCapMw: Math.max(0, Number(e.target.value)) })} />
              <span style={UNIT_STYLE}>MW cap</span>
            </Row>

            <Row label="Transition mode"
                 hint="on loss of utility supply">
              <select
                value={cfg.transitionMode}
                onChange={e => patch({ transitionMode: e.target.value as TransitionMode })}
                style={SELECT_STYLE}
              >
                <option value="open">open</option>
                <option value="closed">closed</option>
                <option value="delayed">delayed</option>
                <option value="soft_load">soft-load</option>
              </select>
            </Row>

            <Row label="PCC interconnection limit"
                 hint="hard ceiling per interconnection agreement">
              <input type="number" min={0.1} step={1} style={INPUT_STYLE}
                value={cfg.pccImportLimitMw}
                onChange={e => patch({ pccImportLimitMw: Math.max(0.1, Number(e.target.value)) })} />
              <span style={UNIT_STYLE}>MW</span>
            </Row>

            <Row label="Demand charge threshold"
                 hint="peak-demand billing ratchet, per period">
              <input
                type="number" min={0} step={1}
                style={INPUT_STYLE}
                placeholder="—"
                value={cfg.demandChargeThresholdMw ?? ''}
                onChange={e => patch({
                  demandChargeThresholdMw: e.target.value === '' ? null : Math.max(0, Number(e.target.value))
                })} />
              <span style={UNIT_STYLE}>MW</span>
            </Row>

            <Row label="Procurement budget ceiling"
                 hint="per window / per billing period · auto-rejects over">
              <input
                type="text" placeholder="$0" style={{ ...INPUT_STYLE, width: 70 }}
                value={cfg.procurementBudgetWindowUsd}
                onChange={e => patch({ procurementBudgetWindowUsd: e.target.value })} />
              <span style={UNIT_STYLE}>/</span>
              <input
                type="text" placeholder="$0" style={{ ...INPUT_STYLE, width: 60 }}
                value={cfg.procurementBudgetPeriodUsd}
                onChange={e => patch({ procurementBudgetPeriodUsd: e.target.value })} />
            </Row>

            <Row label="Price feed"
                 hint="tariff / ISO-RTO market reference">
              <select
                value={cfg.priceFeedSource}
                onChange={e => patch({ priceFeedSource: e.target.value as PriceFeedSource })}
                style={SELECT_STYLE}
              >
                <option value="utility_tou_tariff">utility TOU tariff</option>
                <option value="iso_day_ahead">ISO day-ahead</option>
                <option value="fixed_rate">fixed rate</option>
              </select>
            </Row>

            {/* Advisory rows — read-only */}
            {ADVISORY_INBOUND.map(a => (
              <AdvisoryRow key={a.label} label={a.label} authority={a.authority} />
            ))}
          </div>

          {/* ── OUTBOUND (hidden when islanded per GP-4) ────────────── */}
          {!isIslanded && (
            <div style={{ marginBottom: 6 }}>
              <SectionHeader
                dir="out"
                label="OUTBOUND · EXPORT"
                extra={
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8,
                                fontSize: 10, color: C.txm, letterSpacing: '0.04em' }}>
                    enabled
                    <Toggle
                      checked={cfg.exportEnabled}
                      onChange={v => patch({ exportEnabled: v })} />
                  </div>
                }
              />

              <div style={{
                opacity: cfg.exportEnabled ? 1 : 0.35,
                pointerEvents: cfg.exportEnabled ? 'auto' : 'none',
                transition: 'opacity 0.15s',
              }}>
                <Row label="Export mode"
                     hint="what the exported MW is for">
                  <select
                    value={cfg.exportMode}
                    onChange={e => patch({ exportMode: e.target.value as ExportMode })}
                    style={SELECT_STYLE}
                  >
                    <option value="none">none</option>
                    <option value="net_metering">net metering</option>
                    <option value="wholesale_economic">wholesale (economic)</option>
                    <option value="demand_response">demand response</option>
                    <option value="vpp_dispatch">VPP dispatch</option>
                    <option value="emergency_grid_support">emergency grid support</option>
                  </select>
                </Row>

                <Row label="Export cap"
                     hint="P_export_max · per interconnection agreement">
                  <input type="number" min={0} step={0.5} style={INPUT_STYLE}
                    value={cfg.pExportMaxMw}
                    onChange={e => patch({ pExportMaxMw: Math.max(0, Number(e.target.value)) })} />
                  <span style={UNIT_STYLE}>MW</span>
                </Row>

                <Row label="Export ramp rate limit"
                     hint="utility-imposed rate of change">
                  <input
                    type="number" min={0.01} step={0.1}
                    style={INPUT_STYLE}
                    placeholder="—"
                    value={cfg.exportRampRateLimitMwPerMin ?? ''}
                    onChange={e => patch({
                      exportRampRateLimitMwPerMin: e.target.value === '' ? null : Math.max(0.01, Number(e.target.value))
                    })} />
                  <span style={UNIT_STYLE}>MW/min</span>
                </Row>

                <Row label="Power factor at PCC"
                     hint="required band during export (0.80 – 1.00)">
                  <input type="number" min={0.80} max={1.00} step={0.01} style={INPUT_STYLE}
                    value={cfg.powerFactorMin}
                    onChange={e => patch({ powerFactorMin: Math.min(1, Math.max(0.8, Number(e.target.value))) })} />
                  <span style={UNIT_STYLE}>min</span>
                </Row>

                <Row label="Compensation / price feed"
                     hint="applies when export mode is wholesale">
                  <select
                    value={cfg.exportPriceFeedSource}
                    onChange={e => patch({ exportPriceFeedSource: e.target.value as ExportPriceFeedSource })}
                    style={SELECT_STYLE}
                  >
                    <option value="iso_real_time_lmp">ISO real-time LMP</option>
                    <option value="bilateral_ppa_rate">bilateral PPA rate</option>
                    <option value="none">none</option>
                  </select>
                </Row>

                <Row label="Utility curtail-export channel"
                     hint="utility can call a DR/curtailment event">
                  <Toggle
                    checked={cfg.utilityCurtailExportChannelEnabled}
                    onChange={v => patch({ utilityCurtailExportChannelEnabled: v })} />
                </Row>

                <Row label="Backup genset export eligibility"
                     hint="off unless certified for parallel export">
                  <Toggle
                    checked={cfg.backupGensetExportEligible}
                    onChange={v => patch({ backupGensetExportEligible: v })} />
                </Row>

                {ADVISORY_OUTBOUND.map(a => (
                  <AdvisoryRow key={a.label} label={a.label} authority={a.authority} />
                ))}
              </div>
            </div>
          )}

          {/* GP-4 note when islanded */}
          {isIslanded && (
            <div style={{
              background: C.bg2, borderRadius: 6, padding: '10px 14px',
              marginBottom: 14, fontSize: 10.5, color: C.txm, lineHeight: 1.6,
            }}>
              <span style={{ color: C.txd, fontWeight: 500 }}>GP-4: </span>
              Export configuration is not available in islanded mode. Switch to
              grid-tied or hybrid to configure outbound parameters.
            </div>
          )}

          {/* Validation errors */}
          {errors.length > 0 && (
            <div style={{
              background: 'rgba(248,81,73,0.08)', border: '1px solid rgba(248,81,73,0.3)',
              borderRadius: 6, padding: '10px 14px', marginBottom: 14,
            }}>
              {errors.map(err => (
                <div key={err} style={{ fontSize: 10.5, color: '#f85149', lineHeight: 1.6 }}>
                  · {err}
                </div>
              ))}
            </div>
          )}

          {/* Why this matters */}
          <div style={{
            background: C.bg2, borderRadius: 6, padding: '12px 14px',
            margin: '16px 0 14px', fontSize: 11, color: C.txd, lineHeight: 1.6,
          }}>
            <span style={{ color: C.tx, fontWeight: 500 }}>Why this matters. </span>
            Import and export share one PCC but have independent limits, protection
            settings, and compensation models. GridSignal reads both directions and
            forecasts against them — it never writes a setpoint to switchgear, transfer
            hardware, or protection relays on either side of the boundary.
          </div>
        </div>

        {/* ── Footer ──────────────────────────────────────────────────── */}
        <div style={{
          display: 'flex', justifyContent: 'flex-end', gap: 8,
          padding: '14px 20px', borderTop: `1px solid ${C.bd}`,
        }}>
          <button
            onClick={onClose}
            style={{
              background: 'transparent', border: `1px solid ${C.bds}`,
              color: C.txd, fontFamily: 'inherit', fontSize: 11,
              padding: '8px 16px', borderRadius: 5, cursor: 'pointer',
              letterSpacing: '0.02em',
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            style={{
              background: 'transparent',
              border: `1px solid ${saved ? 'rgba(93,202,165,0.6)' : 'rgba(93,202,165,0.4)'}`,
              color: saved ? '#3fb6a8' : C.teal,
              fontFamily: 'inherit', fontSize: 11,
              padding: '8px 16px', borderRadius: 5, cursor: 'pointer',
              letterSpacing: '0.02em', transition: 'border-color 0.15s, color 0.15s',
            }}
          >
            {saved ? '✓ Saved' : 'Save configuration'}
          </button>
        </div>
      </div>
    </div>
  )

  return createPortal(content, document.body)
}
