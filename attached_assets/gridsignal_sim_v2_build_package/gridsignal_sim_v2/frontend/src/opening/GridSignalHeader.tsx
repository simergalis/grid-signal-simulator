/**
 * GridSignalHeader.tsx — GRIDSIGNAL brand navigation bar for the opening screen.
 *
 * Matches gs-01-opening-rest.svg:
 *   [⚡ GRIDSIGNAL / Predictive power management] │ [Site name / tier] │ … │ [ⓘ How it works] [● STANDBY] [UTC clock]
 *
 * This header appears ONLY on the opening screen (Level 0).
 * Inner pages (Overview, Proposals, …) use the existing RunControlBar + SimClockHeader.
 */

import { useEffect, useRef, useState } from 'react'

interface Props {
  runId: string | null
  onHowItWorks: () => void
  displayName?: string
  role?: string
  onLogout?: () => void
  onAdmin?: () => void
  onChangePassword?: () => void
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

const DEFAULT_SITE_NAME = 'Riverbend DC-West'

export function GridSignalHeader({ runId, onHowItWorks, displayName, role, onLogout, onAdmin, onChangePassword }: Props) {
  const [clock, setClock] = useState(utcNow)

  // ── Site name (editable) ──────────────────────────────────────────────────
  const [siteName, setSiteName]   = useState(DEFAULT_SITE_NAME)
  const [hovering, setHovering]   = useState(false)
  const [editing, setEditing]     = useState(false)
  const [editValue, setEditValue] = useState(DEFAULT_SITE_NAME)
  const [saving, setSaving]       = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  // Fetch on mount
  useEffect(() => {
    fetch('/api/site/settings')
      .then(r => r.ok ? r.json() : null)
      .then((d: { site_name?: string } | null) => {
        if (d?.site_name) setSiteName(d.site_name)
      })
      .catch(() => {})
  }, [])

  // Focus input when editing starts
  useEffect(() => {
    if (editing) inputRef.current?.select()
  }, [editing])

  const startEdit = () => {
    setEditValue(siteName)
    setEditing(true)
  }

  const cancelEdit = () => {
    setEditing(false)
    setHovering(false)
  }

  const commitEdit = async () => {
    const trimmed = editValue.trim()
    if (!trimmed || trimmed === siteName) { cancelEdit(); return }
    setSaving(true)
    try {
      const resp = await fetch('/api/site/settings', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ site_name: trimmed }),
      })
      if (resp.ok) {
        const d = await resp.json() as { site_name: string }
        setSiteName(d.site_name)
      }
    } catch { /* keep previous name */ }
    setSaving(false)
    setEditing(false)
    setHovering(false)
  }

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

      {/* ── Site info (click name to rename) ─────────────────────────────── */}
      <div className="flex flex-col justify-center px-5" style={{ minWidth: 200 }}>
        {editing ? (
          <input
            ref={inputRef}
            value={editValue}
            onChange={e => setEditValue(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') { e.preventDefault(); void commitEdit() }
              if (e.key === 'Escape') cancelEdit()
            }}
            onBlur={() => { void commitEdit() }}
            disabled={saving}
            maxLength={80}
            className="font-sans font-medium bg-transparent border-b outline-none"
            style={{
              fontSize: 13,
              color: '#e6ecf2',
              borderColor: '#3fb6a8',
              width: '100%',
              paddingBottom: 1,
            }}
          />
        ) : (
          <button
            onClick={startEdit}
            onMouseEnter={() => setHovering(true)}
            onMouseLeave={() => setHovering(false)}
            className="flex items-center gap-1.5 text-left bg-transparent border-none p-0 cursor-text"
            title="Click to rename"
            style={{ fontFamily: 'inherit' }}
          >
            <span className="font-sans font-medium" style={{ fontSize: 13, color: '#e6ecf2' }}>
              {siteName}
            </span>
            <span
              style={{
                fontSize: 10,
                color: '#3fb6a8',
                opacity: hovering ? 1 : 0,
                transition: 'opacity 0.15s',
                userSelect: 'none',
              }}
              aria-hidden="true"
            >
              ✎
            </span>
          </button>
        )}
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
          {onChangePassword && (
            <button
              onClick={onChangePassword}
              className="px-2 py-1 rounded border border-border font-sans
                         text-muted hover:text-text hover:border-muted/50 transition-colors"
              style={{ fontSize: 10 }}
              aria-label="Change password"
            >
              Change password
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
