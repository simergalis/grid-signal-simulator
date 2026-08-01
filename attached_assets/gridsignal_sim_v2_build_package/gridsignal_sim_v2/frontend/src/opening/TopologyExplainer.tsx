/**
 * TopologyExplainer.tsx — "How it works" modal (V-4, Level 1a).
 *
 * Opened from the VerdictBand "ⓘ How it works" button.
 * Onboarding content, not operations.  Esc closes, focus trapped.
 *
 * Content mirrors the gs-04-topology-explainer.svg design:
 *   "Power flows left to right. The signal that controls it flows the
 *    other way — and arrives first."
 *
 * Three planes are explained: Control, Data, Protection.
 * GridSignal sits in the Control plane; it never touches Protection.
 */

import { useCallback, useEffect, useRef } from 'react'

interface Props {
  onClose: () => void
}

interface PlaneRow {
  label: string
  sub: string
  colour: string
  items: string[]
  forbidden?: string[]
}

const PLANES: PlaneRow[] = [
  {
    label: 'CONTROL PLANE',
    sub: 'reads intent · issues setpoints · never touches protection',
    colour: '#3fb6a8',
    items: [
      'turbine_setpoint — MW ramp target for gas turbine',
      'bess_charge_setpoint — charge/discharge power',
      'precool_setpoint — shift cooling load, bounded by inlet temperature',
      'load_curtailment — defer or cap workload — tiers C/D need a human',
    ],
  },
  {
    label: 'DATA PLANE',
    sub: 'reads state · builds forecast · never writes a setpoint',
    colour: '#4a9fe0',
    items: [
      'job scheduler events (Slurm · Kubernetes · Ray)',
      'training framework hooks (PyTorch checkpoint events)',
      'power meter readings — 1 s resolution',
      'switchgear telemetry — breaker position, voltage',
    ],
  },
  {
    label: 'PROTECTION PLANE',
    sub: 'switchgear hardware — GridSignal never commands these',
    colour: '#f85149',
    items: [],
    forbidden: [
      'islanding',
      'synchro-check',
      'anti-islanding',
      'droop control',
      'protective load shed',
    ],
  },
]

export function TopologyExplainer({ onClose }: Props) {
  const dialogRef   = useRef<HTMLDivElement>(null)
  const closeBtnRef = useRef<HTMLButtonElement>(null)
  const returnRef   = useRef<Element | null>(null)

  useEffect(() => {
    returnRef.current = document.activeElement
    closeBtnRef.current?.focus()
  }, [])

  useEffect(() => {
    return () => {
      const el = returnRef.current
      if (el && 'focus' in el) (el as HTMLElement).focus()
    }
  }, [])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { onClose(); return }
    if (e.key === 'Tab' && dialogRef.current) {
      const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
        'button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])'
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

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="How GridSignal works"
        onKeyDown={handleKeyDown}
        className="relative flex flex-col w-full max-w-[92vw] xl:max-w-[960px]
                   max-h-[90vh] rounded-xl overflow-hidden border border-border
                   bg-surface shadow-2xl"
      >
        {/* Accent bar */}
        <div className="absolute inset-x-0 top-0 h-[4px] rounded-t-xl" style={{ background: '#3fb6a8' }} />

        {/* Header */}
        <div className="flex items-start justify-between px-7 pt-7 pb-4">
          <div>
            <h2 className="font-mono text-lg font-bold tracking-wide text-text">
              WHERE GRIDSIGNAL SITS
            </h2>
            <p className="font-mono text-xs text-muted mt-1">
              Power flows left to right. The signal that controls it flows the other way — and arrives first.
            </p>
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

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-7 py-5 space-y-5">

          {/* The claim */}
          <div
            className="rounded-lg px-5 py-4 border"
            style={{ borderColor: '#3fb6a8', background: '#0d1a22' }}
          >
            <p className="font-mono text-sm text-text">
              GridSignal reads the{' '}
              <span style={{ color: '#3fb6a8' }}>job scheduler</span>, not the power meter.
              It knows a 20 MW step is coming 30–60 seconds before it arrives, and stages
              generation and storage before the load lands.
            </p>
            <p className="font-mono text-xs text-muted mt-2">
              A power-sensor system learns about the load at 0 s — after it has already happened.
              That gap is the product.
            </p>
          </div>

          {/* Three planes */}
          {PLANES.map(plane => (
            <div
              key={plane.label}
              className="rounded-lg border"
              style={{ borderColor: '#1e2a36', background: '#0d141b' }}
            >
              <div className="px-5 py-3 border-b border-border/40 flex items-center gap-3">
                <div
                  className="w-2 h-2 rounded-full flex-shrink-0"
                  style={{ background: plane.colour }}
                />
                <span
                  className="font-mono text-xs font-bold tracking-wider uppercase"
                  style={{ color: plane.colour }}
                >
                  {plane.label}
                </span>
                <span className="font-mono text-[10px] text-muted">{plane.sub}</span>
              </div>
              <div className="px-5 py-3 space-y-2">
                {plane.items.map((item, i) => (
                  <div key={i} className="flex items-start gap-2">
                    <span style={{ color: plane.colour }} className="text-xs mt-0.5 flex-shrink-0">●</span>
                    <span className="font-mono text-xs text-text/80">{item}</span>
                  </div>
                ))}
                {plane.forbidden && plane.forbidden.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-border/40">
                    <div className="font-mono text-[9px] uppercase tracking-wider text-muted mb-2">
                      GridSignal never commands
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {plane.forbidden.map(item => (
                        <div key={item} className="flex items-center gap-1.5">
                          <span className="text-xs" style={{ color: '#f85149' }}>✕</span>
                          <span className="font-mono text-xs" style={{ color: '#e6edf3' }}>{item}</span>
                        </div>
                      ))}
                    </div>
                    <p className="font-mono text-[10px] text-muted mt-3">
                      Protection is the switchgear's job and stays there. GridSignal stages and advises;
                      it never contests a relay.
                    </p>
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Signal flow */}
          <div className="rounded-lg border border-border/40 bg-canvas px-5 py-4">
            <div className="font-mono text-[9px] uppercase tracking-wider text-muted mb-3">
              Signal flow
            </div>
            <div className="flex items-center gap-2 flex-wrap font-mono text-xs">
              {[
                { label: 'Scheduler', colour: '#3fb6a8' },
                { label: '→', colour: '#4b5764' },
                { label: 'GridSignal', colour: '#3fb6a8' },
                { label: '→', colour: '#4b5764' },
                { label: 'Turbine setpoint', colour: '#e0a458' },
                { label: '→', colour: '#4b5764' },
                { label: 'Turbine', colour: '#e0a458' },
                { label: '→', colour: '#4b5764' },
                { label: 'Switchgear', colour: '#5a6673' },
                { label: '→', colour: '#4b5764' },
                { label: 'Compute racks', colour: '#3fb6a8' },
              ].map((step, i) => (
                <span key={i} style={{ color: step.colour }}>{step.label}</span>
              ))}
            </div>
            <p className="font-mono text-[10px] text-muted mt-2">
              The control signal travels before the power. By the time electrons flow, generation is already at the setpoint.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-7 py-4 border-t border-border">
          <button
            onClick={onClose}
            className="px-5 py-2 rounded text-xs font-semibold font-mono transition-colors"
            style={{ background: '#3fb6a8', color: '#0d1117' }}
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  )
}
