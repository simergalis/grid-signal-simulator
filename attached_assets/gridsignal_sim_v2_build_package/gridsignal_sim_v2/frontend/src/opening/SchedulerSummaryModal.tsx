/**
 * SchedulerSummaryModal.tsx
 *
 * Full-screen overlay modal that asks Claude (via POST /api/ai/scheduler-summary)
 * to produce a plain-English summary of the Scheduler Feed log and the current
 * live tick readings.  Rendered via ReactDOM.createPortal so it escapes the SVG
 * foreignObject context and covers the entire viewport.
 */

import { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import type { TickPayload } from '../types'

export interface FeedEntry {
  ts: string
  body: string
}

interface Props {
  feedEntries: FeedEntry[]
  tick: TickPayload | null
  onClose: () => void
}

export function SchedulerSummaryModal({ feedEntries, tick, onClose }: Props) {
  const [summary, setSummary] = useState<string | null>(null)
  const [error,   setError]   = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  // Fire the API call once on mount — ignore the result if the modal is closed early.
  useEffect(() => {
    let cancelled = false

    async function fetchSummary() {
      try {
        const res = await fetch('/api/ai/scheduler-summary', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            feed_entries: feedEntries,
            tick: tick ?? null,
          }),
        })
        if (!res.ok) {
          const detail = await res.json().catch(() => ({ detail: res.statusText }))
          throw new Error(detail.detail ?? res.statusText)
        }
        const data = await res.json()
        if (!cancelled) setSummary(data.summary)
      } catch (err: unknown) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetchSummary()
    return () => { cancelled = true }
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const _MONO: React.CSSProperties = {
    fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace",
  }
  const _BODY: React.CSSProperties = {
    fontFamily: 'Inter, system-ui, sans-serif',
  }

  const modal = (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="AI Summary"
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'rgba(0,0,0,0.72)',
        backdropFilter: 'blur(3px)',
        WebkitBackdropFilter: 'blur(3px)',
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div style={{
        background: '#0d1b26',
        border: '1px solid #2a4a5a',
        borderRadius: 8,
        boxShadow: '0 24px 64px rgba(0,0,0,0.65)',
        maxWidth: 540,
        width: '90%',
        padding: '18px 22px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: 0,
      }}>

        {/* ── Header ──────────────────────────────────────────────────── */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          marginBottom: 10,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 13, color: '#3fb6a8', lineHeight: 1 }}>✦</span>
            <span style={{
              ..._MONO, fontSize: 10, fontWeight: 700,
              letterSpacing: '0.08em', color: '#3fb6a8',
            }}>
              AI SUMMARY
            </span>
            <span style={{
              ..._MONO, fontSize: 8, color: '#2a5060',
              letterSpacing: '0.04em', marginLeft: 4,
            }}>
              SCHEDULER FEED
            </span>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            style={{
              background: 'transparent', border: 'none', cursor: 'pointer',
              color: '#3a4a58', fontSize: 20, lineHeight: 1,
              padding: '0 2px', marginRight: -2,
              transition: 'color 0.15s',
            }}
            onMouseEnter={e => (e.currentTarget.style.color = '#c8d6e5')}
            onMouseLeave={e => (e.currentTarget.style.color = '#3a4a58')}
          >
            ×
          </button>
        </div>

        <div style={{ width: '100%', height: 1, background: '#1e2a36', marginBottom: 14 }} />

        {/* ── Body ────────────────────────────────────────────────────── */}
        {loading && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 10,
            padding: '14px 0 18px',
          }}>
            <div style={{
              width: 13, height: 13, borderRadius: '50%',
              border: '2px solid #1e3040', borderTopColor: '#3fb6a8',
              animation: 'gridsignal-spin 0.75s linear infinite',
              flexShrink: 0,
            }} />
            <span style={{ ..._BODY, fontSize: 12, color: '#4b5764' }}>
              Claude is reading the feed…
            </span>
          </div>
        )}

        {error && !loading && (
          <div style={{
            ..._BODY, fontSize: 12, color: '#e05a5a',
            lineHeight: 1.65, padding: '8px 0 12px',
          }}>
            {error}
          </div>
        )}

        {summary && !loading && (
          <div style={{
            ..._BODY, fontSize: 13.5, color: '#c8d6e5',
            lineHeight: 1.8, padding: '4px 0 12px',
          }}>
            {summary}
          </div>
        )}

        {/* ── Footer ──────────────────────────────────────────────────── */}
        <div style={{ width: '100%', height: 1, background: '#1e2a36', marginTop: 2, marginBottom: 10 }} />
        <div style={{
          ..._MONO, fontSize: 8, color: '#253545',
          letterSpacing: '0.04em', lineHeight: 1.4,
        }}>
          {feedEntries.length} feed {feedEntries.length === 1 ? 'entry' : 'entries'}
          {tick ? `  ·  sim t=${Math.round(tick.sim_time_seconds)}s` : '  ·  no live tick'}
          {'  ·  claude-haiku-4-5'}
        </div>
      </div>
    </div>
  )

  return createPortal(
    <>
      <style>{`@keyframes gridsignal-spin { to { transform: rotate(360deg); } }`}</style>
      {modal}
    </>,
    document.body,
  )
}
