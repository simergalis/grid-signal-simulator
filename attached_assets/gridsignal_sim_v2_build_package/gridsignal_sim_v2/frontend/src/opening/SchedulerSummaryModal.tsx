/**
 * SchedulerSummaryModal.tsx
 *
 * Full-screen overlay modal that asks Claude (via POST /api/ai/scheduler-summary)
 * to produce a plain-English summary of the Scheduler Feed log and the current
 * live tick readings.  Rendered via ReactDOM.createPortal so it escapes the SVG
 * foreignObject context and covers the entire viewport.
 *
 * UX features:
 *   · Wide, horizontally-resizable dialog (min 520 px, default 780 px)
 *   · Scrollable summary body with max-height so the modal never overflows
 *   · Each sentence rendered on its own line for readability
 *   · A▾ / A▴ buttons to decrease / increase the summary font size (11–20 px)
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

const FONT_MIN = 11
const FONT_MAX = 20
const FONT_DEFAULT = 13.5

/** Split summary prose into individual sentences for line-by-line rendering. */
function splitSentences(text: string): string[] {
  // Replace sentence-ending punctuation + whitespace with a newline marker,
  // then split.  Handles ". ", "! ", "? " and their combinations.
  return text
    .replace(/([.!?]+)\s+/g, '$1\n')
    .split('\n')
    .map(s => s.trim())
    .filter(Boolean)
}

export function SchedulerSummaryModal({ feedEntries, tick, onClose }: Props) {
  const [summary,  setSummary]  = useState<string | null>(null)
  const [error,    setError]    = useState<string | null>(null)
  const [loading,  setLoading]  = useState(true)
  const [fontSize, setFontSize] = useState(FONT_DEFAULT)

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

  // Shared style for the A▾ / A▴ font-size buttons
  const fontBtnBase: React.CSSProperties = {
    ..._MONO,
    background: 'transparent',
    border: '1px solid #1e3040',
    borderRadius: 3,
    cursor: 'pointer',
    color: '#3a5a6a',
    lineHeight: 1,
    padding: '2px 5px',
    transition: 'color 0.12s, border-color 0.12s',
    userSelect: 'none' as const,
  }

  const sentences = summary ? splitSentences(summary) : []

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
      {/* ── Dialog box — wide, horizontally resizable ──────────────────── */}
      <div style={{
        background: '#0d1b26',
        border: '1px solid #2a4a5a',
        borderRadius: 8,
        boxShadow: '0 24px 64px rgba(0,0,0,0.65)',
        /* Resizable: the browser renders a drag handle at the bottom-right.
           overflow:hidden keeps the resize handle visible and clips content
           to the box — the body section has its own scroll independently. */
        resize: 'horizontal' as const,
        overflow: 'hidden' as const,
        minWidth: 520,
        maxWidth: '96vw',
        width: 780,
        padding: '18px 22px 16px',
        display: 'flex',
        flexDirection: 'column' as const,
        gap: 0,
        /* Push the resize handle away from the footer text */
        paddingBottom: 20,
      }}>

        {/* ── Header ──────────────────────────────────────────────────── */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          marginBottom: 10, flexShrink: 0,
        }}>
          {/* Left: icon + title + sub-label */}
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

          {/* Right: font-size controls + close */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {/* Font decrease */}
            <button
              onClick={() => setFontSize(s => Math.max(FONT_MIN, +(s - 1).toFixed(1)))}
              title="Decrease text size"
              style={{ ...fontBtnBase, fontSize: 10 }}
              onMouseEnter={e => {
                e.currentTarget.style.color = '#c8d6e5'
                e.currentTarget.style.borderColor = '#3fb6a8'
              }}
              onMouseLeave={e => {
                e.currentTarget.style.color = '#3a5a6a'
                e.currentTarget.style.borderColor = '#1e3040'
              }}
            >
              A▾
            </button>
            {/* Font increase */}
            <button
              onClick={() => setFontSize(s => Math.min(FONT_MAX, +(s + 1).toFixed(1)))}
              title="Increase text size"
              style={{ ...fontBtnBase, fontSize: 13 }}
              onMouseEnter={e => {
                e.currentTarget.style.color = '#c8d6e5'
                e.currentTarget.style.borderColor = '#3fb6a8'
              }}
              onMouseLeave={e => {
                e.currentTarget.style.color = '#3a5a6a'
                e.currentTarget.style.borderColor = '#1e3040'
              }}
            >
              A▴
            </button>

            {/* Divider */}
            <div style={{ width: 1, height: 14, background: '#1e3040' }} />

            {/* Close */}
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
        </div>

        <div style={{ width: '100%', height: 1, background: '#1e2a36', marginBottom: 14, flexShrink: 0 }} />

        {/* ── Body — scrollable ────────────────────────────────────────── */}
        <div style={{
          overflowY: 'auto' as const,
          maxHeight: '62vh',
          paddingRight: 4,
          /* Thin scrollbar */
          scrollbarWidth: 'thin' as const,
          scrollbarColor: '#2a3a4a transparent',
          flexShrink: 1,
        }}>
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

          {/* Sentence-per-line rendering */}
          {sentences.length > 0 && !loading && (
            <div style={{ padding: '4px 0 14px' }}>
              {sentences.map((sentence, i) => (
                <p
                  key={i}
                  style={{
                    ..._BODY,
                    fontSize: fontSize,
                    color: '#c8d6e5',
                    lineHeight: 1.8,
                    margin: 0,
                    marginBottom: i < sentences.length - 1 ? '0.9em' : 0,
                  }}
                >
                  {sentence}
                </p>
              ))}
            </div>
          )}
        </div>

        {/* ── Footer ──────────────────────────────────────────────────── */}
        <div style={{ width: '100%', height: 1, background: '#1e2a36', marginTop: 10, marginBottom: 10, flexShrink: 0 }} />
        <div style={{
          ..._MONO, fontSize: 8, color: '#253545',
          letterSpacing: '0.04em', lineHeight: 1.4,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          flexShrink: 0,
        }}>
          <span>
            {feedEntries.length} feed {feedEntries.length === 1 ? 'entry' : 'entries'}
            {tick ? `  ·  sim t=${Math.round(tick.sim_time_seconds)}s` : '  ·  no live tick'}
            {'  ·  claude-haiku-4-5'}
          </span>
          <span style={{ color: '#1e3040' }}>
            {fontSize}px  ·  drag corner to resize
          </span>
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
