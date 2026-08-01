/**
 * SubsystemModal.tsx — modal shell for all nine subsystem detail views (U3).
 *
 * Structure (from mockup gridsignal-06..15):
 *   [title + state dot]      [×]
 *   [identity line]
 *   ────────────────────────────
 *   [VERDICT strip + hero value]
 *   ────────────────────────────
 *   [chart (60%)] | [StatTable (40%)]
 *   [BulletBar / StackBar secondary row]
 *   ────────────────────────────
 *   WHY THIS MATTERS
 *   [3 prose lines]
 *   [Open full page]  [Close]
 *
 * Accessibility (§ Phase U3 gate):
 *   · role="dialog" + aria-modal
 *   · Esc closes
 *   · focus trapped inside the modal
 *   · focus restored to originating element on close
 *
 * Width: 1120 px max at ≥ 1440 px, 92vw at 1024–1439 px, full-screen < 768 px.
 * Body: 2-col (chart left, metrics right) ≥ 768 px; single-col below.
 */

import { useCallback, useEffect, useRef } from 'react'
import { SUBSYSTEMS } from '../readiness/subsystems'
import { PANEL_CONFIGS } from './panels/index'
import { useTickStore } from '../store/tickStore'
import { StatTable }    from '../charts/StatTable'

export function SubsystemModal({
  subsystemId,
  onClose,
  onOpenPage,
}: {
  subsystemId: string
  onClose: () => void
  onOpenPage: (tabId: string) => void
}) {
  const cfg    = SUBSYSTEMS.find(s => s.id === subsystemId)
  const panel  = PANEL_CONFIGS[subsystemId]
  const tick   = useTickStore(s => s.latestTick)
  const alert  = useTickStore(s => s.latchedAlert)
  const history = useTickStore(s => s.history)

  const dialogRef      = useRef<HTMLDivElement>(null)
  const closeBtnRef    = useRef<HTMLButtonElement>(null)
  // The element that had focus before the modal opened — restored on close
  const returnFocusRef = useRef<Element | null>(null)

  // Capture the current focus target before dialog mounts
  useEffect(() => {
    returnFocusRef.current = document.activeElement
    // Move focus to the close button immediately
    closeBtnRef.current?.focus()
  }, [])

  // Restore focus on unmount
  useEffect(() => {
    return () => {
      const el = returnFocusRef.current
      if (el && 'focus' in el) (el as HTMLElement).focus()
    }
  }, [])

  // Esc to close
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') onClose()
    // Trap Tab inside dialog
    if (e.key === 'Tab' && dialogRef.current) {
      const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )
      if (!focusable.length) { e.preventDefault(); return }
      const first = focusable[0]
      const last  = focusable[focusable.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault(); last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault(); first.focus()
      }
    }
  }, [onClose])

  if (!cfg || !panel) return null

  // Derive live values for the modal from the tick
  const panelData = panel.deriveData(tick, alert, history)

  return (
    // Backdrop
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      {/* Dialog */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={cfg.name}
        className={`
          relative flex flex-col
          w-full max-w-[92vw] xl:max-w-[1120px]
          max-h-[90vh]
          rounded-xl overflow-hidden
          border border-border bg-surface shadow-2xl
        `}
        onKeyDown={handleKeyDown}
      >
        {/* Accent top bar */}
        <div
          className="absolute inset-x-0 top-0 h-[4px]"
          style={{ background: cfg.accentColor }}
        />

        {/* ── Header ─────────────────────────────────────────────────────── */}
        <div className="flex items-start justify-between px-7 pt-7 pb-4">
          <div className="space-y-0.5">
            <div className="flex items-center gap-2">
              <h2 className="font-mono text-lg font-bold tracking-wide text-text">
                {cfg.name.toUpperCase()}
              </h2>
              <div
                className="w-2 h-2 rounded-full"
                style={{ background: panelData.stateColour }}
              />
              <span
                className="font-mono text-xs font-bold tracking-wider uppercase"
                style={{ color: panelData.stateColour }}
              >
                {panelData.stateLabel}
              </span>
            </div>
            <div className="font-mono text-xs text-muted">{cfg.identityLine}</div>
          </div>

          <button
            ref={closeBtnRef}
            onClick={onClose}
            className="ml-4 shrink-0 text-muted hover:text-text text-lg leading-none px-1"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div className="h-px bg-border mx-7" />

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-7 py-5 space-y-5">

          {/* ── Verdict strip ─────────────────────────────────────────── */}
          <div
            className="flex items-center gap-4 px-4 py-4 rounded-lg border"
            style={{ borderColor: cfg.accentColor, background: '#16222e' }}
          >
            <div className="flex-1">
              <div className="font-mono text-[9px] uppercase tracking-[0.14em] mb-1"
                   style={{ color: '#4b5764' }}>
                VERDICT
              </div>
              <p className="font-mono text-sm text-text">{panelData.verdict}</p>
            </div>
            <div className="text-right shrink-0">
              <div
                className="font-mono text-3xl font-semibold tabular-nums"
                style={{ color: cfg.accentColor }}
              >
                {panelData.heroValue}
              </div>
              <div className="font-mono text-[9px] text-muted mt-0.5">
                {panelData.heroLabel}
              </div>
            </div>
          </div>

          {/* ── Main body: chart left, metrics right ──────────────────── */}
          <div className="flex flex-col md:flex-row gap-6">
            {/* Chart area (left / top on small screens) */}
            <div className="md:w-[58%]">
              {panelData.chartTitle && (
                <div className="font-mono text-[9px] uppercase tracking-[0.14em] mb-2"
                     style={{ color: '#4b5764' }}>
                  {panelData.chartTitle}
                </div>
              )}
              {panelData.chart}
            </div>

            {/* Metrics (right / bottom) */}
            <div className="md:flex-1">
              <StatTable rows={panelData.statRows} />
            </div>
          </div>

          {/* ── Secondary row: bullets or stack ───────────────────────── */}
          {panelData.secondary && (
            <div className="space-y-3">
              {panelData.secondary}
            </div>
          )}

          <div className="h-px bg-border" />

          {/* ── Why this matters ──────────────────────────────────────── */}
          <div>
            <div className="font-mono text-[9px] uppercase tracking-[0.14em] mb-3"
                 style={{ color: '#4b5764' }}>
              WHY THIS MATTERS
            </div>
            <div className="space-y-1">
              {panelData.why.map((line, i) => (
                <p key={i} className="font-mono text-xs text-muted leading-relaxed">{line}</p>
              ))}
            </div>
          </div>
        </div>

        {/* ── Footer actions ─────────────────────────────────────────────── */}
        <div className="flex items-center justify-end gap-3 px-7 py-4 border-t border-border">
          {cfg.tabId && (
            <button
              onClick={() => onOpenPage(cfg.tabId!)}
              className="px-4 py-2 rounded border border-border text-xs text-muted
                         hover:text-text hover:border-muted transition-colors font-mono"
            >
              Open full page
            </button>
          )}
          <button
            onClick={onClose}
            className="px-5 py-2 rounded text-xs font-semibold font-mono transition-colors"
            style={{ background: cfg.accentColor, color: '#0d1117' }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
