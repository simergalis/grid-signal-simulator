/**
 * GridSignalHeader.tsx — GRIDSIGNAL brand navigation bar for the opening screen.
 *
 * Matches gs-01-opening-rest.svg:
 *   [⚡ GRIDSIGNAL / Predictive power management] │ [Site name / tier] │ … │ [ⓘ How it works] [● STANDBY] [UTC clock]
 *
 * This header appears ONLY on the opening screen (Level 0).
 * Inner pages (Overview, Proposals, …) use the existing RunControlBar + SimClockHeader.
 */

import { useEffect, useState } from 'react'

interface Props {
  runId: string | null
  onHowItWorks: () => void
  displayName?: string
  role?: string
  onLogout?: () => void
  onAdmin?: () => void
}

function utcNow(): string {
  const now = new Date()
  return (
    now.getUTCHours().toString().padStart(2, '0') + ':' +
    now.getUTCMinutes().toString().padStart(2, '0') + ':' +
    now.getUTCSeconds().toString().padStart(2, '0') +
    ' UTC'
  )
}

export function GridSignalHeader({ runId, onHowItWorks, displayName, role, onLogout, onAdmin }: Props) {
  const [clock, setClock] = useState(utcNow)

  useEffect(() => {
    const id = setInterval(() => setClock(utcNow()), 1000)
    return () => clearInterval(id)
  }, [])

  const isLive = runId !== null
  const statusDot  = isLive ? '#3fb6a8' : '#7d8b9c'
  const statusText = isLive ? 'LIVE'    : 'STANDBY'

  return (
    <header
      className="flex items-center gap-0 border-b border-border flex-shrink-0"
      style={{ background: '#111821', height: 58 }}
    >
      {/* ── Logo ──────────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 px-4" style={{ minWidth: 230 }}>
        {/* Lightning bolt icon */}
        <svg width="22" height="26" viewBox="0 0 22 26" aria-hidden="true">
          <path
            d="M14 2L2 14h8l-2 10 12-14h-8z"
            fill="#3fb6a8"
            strokeLinejoin="round"
          />
        </svg>
        <div>
          <div
            className="font-sans font-bold tracking-[0.1em]"
            style={{ fontSize: 16, color: '#e6ecf2', letterSpacing: '0.1em' }}
          >
            GRIDSIGNAL
          </div>
          <div className="font-sans" style={{ fontSize: 10, color: '#4b5764', marginTop: 1 }}>
            Predictive power management
          </div>
        </div>
      </div>

      {/* ── Separator ─────────────────────────────────────────────────────── */}
      <div className="self-stretch w-px bg-border mx-0" />

      {/* ── Site info ─────────────────────────────────────────────────────── */}
      <div className="flex flex-col justify-center px-5" style={{ minWidth: 200 }}>
        <div className="font-sans font-medium" style={{ fontSize: 13, color: '#e6ecf2' }}>
          Riverbend DC-West
        </div>
        <div className="font-sans" style={{ fontSize: 10, color: '#7d8b9c', marginTop: 2 }}>
          Islanded microgrid · supervised tier
        </div>
      </div>

      {/* ── Spacer ────────────────────────────────────────────────────────── */}
      <div className="flex-1" />

      {/* ── "How it works" button ─────────────────────────────────────────── */}
      <button
        onClick={onHowItWorks}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-border
                   font-sans text-muted hover:text-text hover:border-muted/50 transition-colors"
        style={{ fontSize: 10 }}
        aria-label="Open topology explainer"
      >
        ⓘ &nbsp;How it works
      </button>

      {/* ── Signed-in user + admin + logout ──────────────────────────────── */}
      {displayName && (
        <div className="flex items-center gap-2 px-3">
          <span className="font-sans" style={{ fontSize: 11, color: '#7d8b9c' }}>
            {displayName}
          </span>
          {role === 'admin' && onAdmin && (
            <button
              onClick={onAdmin}
              className="px-2 py-1 rounded border border-border font-sans
                         text-muted hover:text-text hover:border-muted/50 transition-colors"
              style={{ fontSize: 10 }}
              aria-label="Admin panel"
            >
              ⚙ Admin
            </button>
          )}
          {onLogout && (
            <button
              onClick={onLogout}
              className="px-2 py-1 rounded border border-border font-sans
                         text-muted hover:text-text hover:border-muted/50 transition-colors"
              style={{ fontSize: 10 }}
              aria-label="Sign out"
            >
              Sign out
            </button>
          )}
        </div>
      )}

      {/* ── Status badge ──────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 px-5">
        <div
          className="w-2 h-2 rounded-full flex-shrink-0"
          style={{
            background: statusDot,
            boxShadow: isLive ? `0 0 6px ${statusDot}` : 'none',
          }}
        />
        <span
          className="font-sans font-bold tracking-wider"
          style={{ fontSize: 12, color: statusDot, letterSpacing: '0.12em' }}
        >
          {statusText}
        </span>
      </div>

      {/* ── Separator ─────────────────────────────────────────────────────── */}
      <div className="self-stretch w-px bg-border" />

      {/* ── UTC clock ─────────────────────────────────────────────────────── */}
      <div className="flex flex-col items-end justify-center px-5">
        <div
          className="tabular-nums"
          style={{ fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace", fontSize: 12, color: '#e6ecf2' }}
        >
          {clock}
        </div>
        <div className="font-sans" style={{ fontSize: 10, color: '#4b5764', marginTop: 2 }}>
          {isLive ? 'run active' : 'no run active'}
        </div>
      </div>
    </header>
  )
}
