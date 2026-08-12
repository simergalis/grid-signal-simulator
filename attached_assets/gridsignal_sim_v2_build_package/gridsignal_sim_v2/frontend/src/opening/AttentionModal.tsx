/**
 * AttentionModal.tsx — Lists every subsystem currently flagged ATTENTION.
 *
 * Opened by clicking the "Attention" hero figure in VerdictBand.
 * Reads useSubsystemData() and renders one row per subsystem whose
 * state === 'ATTENTION', plus a dedicated row when the reserve-gap
 * alert is latched (BESS).
 *
 * Follows the same a11y pattern as GenTripModal:
 *   · role="dialog" + aria-modal
 *   · Esc closes
 *   · focus restored to triggering element on close
 */

import { useCallback, useEffect, useRef } from 'react'
import { useSubsystemData } from '../subsystem/useSubsystemData'
import { useTickStore }     from '../store/tickStore'
import { SUBSYSTEMS }       from '../readiness/subsystems'

interface Props {
  onClose: () => void
}

const AMBER = '#f0883e'
const DIM   = '#4b5764'

// Subsystem IDs we surface in this modal (omit advisory-only ones that
// can never reach ATTENTION, e.g. renewable/grid/agents).
const WATCHLIST = [
  'forecast-quality',
  'storage',
  'thermal',
  'gcc',
  'compute',
  'generation',
]

export function AttentionModal({ onClose }: Props) {
  const overlayRef  = useRef<HTMLDivElement>(null)
  const closeRef    = useRef<HTMLButtonElement>(null)

  const data  = useSubsystemData()
  const alert = useTickStore(s => s.latchedAlert)
  const tick  = useTickStore(s => s.latestTick)

  // Collect subsystems in ATTENTION state from the watchlist
  const attentionItems = WATCHLIST
    .map(id => {
      const cfg = SUBSYSTEMS.find(s => s.id === id)
      const d   = data[id]
      if (!cfg || !d) return null
      if (d.state !== 'ATTENTION') return null
      return { id, name: cfg.name, verdict: d.verdict, metrics: d.metrics }
    })
    .filter(Boolean) as { id: string; name: string; verdict: string; metrics: { label: string; value: string; colour?: string }[] }[]

  // If reserve-gap alert is latched and storage isn't already listed
  const hasStorageAlert = alert !== null && !attentionItems.find(i => i.id === 'storage')
  if (hasStorageAlert) {
    const cfg = SUBSYSTEMS.find(s => s.id === 'storage')
    const d   = data['storage']
    if (cfg && d) {
      attentionItems.unshift({ id: 'storage', name: cfg.name, verdict: d.verdict, metrics: d.metrics })
    }
  }

  // Close on Esc
  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // Focus close button on open
  useEffect(() => { closeRef.current?.focus() }, [])

  const handleOverlay = useCallback((e: React.MouseEvent) => {
    if (e.target === overlayRef.current) onClose()
  }, [onClose])

  const count = attentionItems.length

  return (
    <div
      ref={overlayRef}
      role="dialog"
      aria-modal="true"
      aria-label="Subsystems needing attention"
      onClick={handleOverlay}
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(0,0,0,0.65)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 9999,
      }}
    >
      <div
        style={{
          background: '#111821',
          border: `1.5px solid ${AMBER}`,
          borderRadius: 10,
          width: '100%',
          maxWidth: 580,
          maxHeight: '80vh',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          margin: '0 24px',
        }}
      >
        {/* ── Header ─────────────────────────────────────────────────────── */}
        <div
          style={{
            padding: '18px 22px 14px',
            borderBottom: '1px solid #1e2d3d',
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: 12,
            flexShrink: 0,
          }}
        >
          <div>
            <div
              style={{
                fontFamily: 'monospace',
                fontSize: 9,
                fontWeight: 700,
                letterSpacing: '0.16em',
                textTransform: 'uppercase',
                color: DIM,
                marginBottom: 4,
              }}
            >
              ATTENTION
            </div>
            <div
              style={{
                fontFamily: 'monospace',
                fontSize: 22,
                fontWeight: 700,
                color: AMBER,
                lineHeight: 1.1,
              }}
            >
              {count === 0
                ? 'All clear'
                : `${count} subsystem${count > 1 ? 's' : ''} flagged`}
            </div>
            <div style={{ fontFamily: 'monospace', fontSize: 10, color: DIM, marginTop: 4 }}>
              {count === 0
                ? 'No subsystems are currently flagged.'
                : 'Each subsystem below requires operator awareness before further dispatch.'}
            </div>
          </div>

          <button
            ref={closeRef}
            onClick={onClose}
            aria-label="Close attention modal"
            style={{
              background: 'none',
              border: '1px solid #1e2d3d',
              borderRadius: 6,
              color: '#7d8fa1',
              cursor: 'pointer',
              fontSize: 16,
              lineHeight: 1,
              padding: '4px 9px',
              flexShrink: 0,
            }}
          >
            ✕
          </button>
        </div>

        {/* ── Subsystem list ─────────────────────────────────────────────── */}
        <div style={{ overflowY: 'auto', flex: 1, padding: '4px 0 8px' }}>
          {count === 0 ? (
            <div
              style={{
                padding: '28px 22px',
                fontFamily: 'monospace',
                fontSize: 12,
                color: '#3fb6a8',
                textAlign: 'center',
              }}
            >
              No subsystems are currently in ATTENTION state.
            </div>
          ) : (
            attentionItems.map((item, idx) => (
              <div
                key={item.id}
                style={{
                  padding: '14px 22px',
                  borderTop: idx > 0 ? '1px solid #1a2535' : undefined,
                }}
              >
                {/* Name row */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
                  <div
                    style={{
                      width: 7,
                      height: 7,
                      borderRadius: '50%',
                      background: AMBER,
                      flexShrink: 0,
                    }}
                  />
                  <span
                    style={{
                      fontFamily: 'monospace',
                      fontSize: 11,
                      fontWeight: 700,
                      color: '#c9d1d9',
                      textTransform: 'uppercase',
                      letterSpacing: '0.06em',
                    }}
                  >
                    {item.name}
                  </span>
                  <span
                    style={{
                      fontFamily: 'monospace',
                      fontSize: 9,
                      color: AMBER,
                      background: 'rgba(240,136,62,0.12)',
                      border: `1px solid rgba(240,136,62,0.25)`,
                      borderRadius: 3,
                      padding: '1px 5px',
                      letterSpacing: '0.08em',
                    }}
                  >
                    ATTENTION
                  </span>
                </div>

                {/* Verdict */}
                <div
                  style={{
                    fontFamily: 'monospace',
                    fontSize: 11,
                    color: '#7d8fa1',
                    lineHeight: 1.5,
                    marginBottom: 8,
                    paddingLeft: 15,
                  }}
                >
                  {item.verdict}
                </div>

                {/* Metrics row */}
                <div
                  style={{
                    display: 'flex',
                    gap: 20,
                    paddingLeft: 15,
                  }}
                >
                  {item.metrics.map((m, mi) => (
                    <div key={mi}>
                      <div
                        style={{
                          fontFamily: 'monospace',
                          fontSize: 8,
                          textTransform: 'uppercase',
                          letterSpacing: '0.1em',
                          color: DIM,
                          marginBottom: 2,
                        }}
                      >
                        {m.label}
                      </div>
                      <div
                        style={{
                          fontFamily: 'monospace',
                          fontSize: 12,
                          fontWeight: 600,
                          color: m.colour ?? '#c9d1d9',
                        }}
                      >
                        {m.value}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>

        {/* ── Footer ─────────────────────────────────────────────────────── */}
        {alert && (
          <div
            style={{
              padding: '10px 22px',
              borderTop: '1px solid #1e2d3d',
              fontFamily: 'monospace',
              fontSize: 10,
              color: DIM,
              flexShrink: 0,
            }}
          >
            Reserve-gap alert latched at tick {alert.tick_index}
            {tick ? ` · sim ${Math.round(tick.sim_time_seconds)}s` : ''}.
            Acknowledge in the AlertDock before further dispatch.
          </div>
        )}
      </div>
    </div>
  )
}
