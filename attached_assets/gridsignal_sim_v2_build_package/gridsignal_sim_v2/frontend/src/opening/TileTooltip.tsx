/**
 * TileTooltip.tsx — floating plain-English pop-out for tile ⓘ buttons.
 *
 * Behaviour:
 *   • Click ⓘ → open; click ⓘ again → close (toggle).
 *   • Click outside the popout → close (unless pinned).
 *   • 📌 pin button → keeps the popout open regardless of outside clicks.
 *   • × close button → always closes and clears pin.
 *
 * Rendered once in OpeningScreen.tsx; uses fixed positioning so it floats
 * above the SVG diagram and all other content.
 *
 * InfoBtn is exported for use in any tile component.
 */

import { useEffect, useRef } from 'react'
import type { CSSProperties } from 'react'
import { useTooltipStore } from '../store/tooltipStore'
import { TILE_TOOLTIPS }   from './tileTooltipContent'

// ── Shared style constants ────────────────────────────────────────────────────

const MONO: CSSProperties = { fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace" }
const TOOLTIP_W = 360
const GAP       = 10   // px from viewport edges / anchor

// ── InfoBtn ───────────────────────────────────────────────────────────────────

/**
 * Small ⓘ button that opens/closes the tile tooltip.
 * Safe to use inside or alongside any element including <button>.
 * Uses <span role="button"> to avoid nested-button HTML issues.
 */
export function InfoBtn({ id, style }: { id: string; style?: CSSProperties }) {
  const open      = useTooltipStore(s => s.open)
  const tooltipId = useTooltipStore(s => s.tooltipId)
  const active    = tooltipId === id

  if (!TILE_TOOLTIPS[id]) return null

  return (
    <span
      role="button"
      tabIndex={0}
      title="What is this?"
      onMouseDown={e => e.stopPropagation()}
      onClick={e => {
        e.stopPropagation()
        open(id, (e.currentTarget as HTMLElement).getBoundingClientRect())
      }}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          e.stopPropagation()
          open(id, (e.currentTarget as HTMLElement).getBoundingClientRect())
        }
      }}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 14,
        height: 14,
        borderRadius: '50%',
        cursor: 'pointer',
        border: `1px solid ${active ? '#3fb6a8' : '#4a9fe0'}`,
        color: active ? '#3fb6a8' : '#4a9fe0',
        background: active ? 'rgba(63,182,168,0.12)' : 'rgba(74,159,224,0.08)',
        fontSize: 8,
        lineHeight: 1,
        flexShrink: 0,
        userSelect: 'none' as const,
        transition: 'color 0.15s, border-color 0.15s, background 0.15s',
        ...style,
      }}
    >
      ⓘ
    </span>
  )
}

// ── TileTooltip ───────────────────────────────────────────────────────────────

export function TileTooltip() {
  const { tooltipId, pinned, anchorRect, close, togglePin } = useTooltipStore()
  const ref = useRef<HTMLDivElement>(null)

  // Click-outside to close (unless pinned).
  useEffect(() => {
    if (!tooltipId || pinned) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) close()
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [tooltipId, pinned, close])

  if (!tooltipId || !anchorRect) return null
  const content = TILE_TOOLTIPS[tooltipId]
  if (!content) return null

  // ── Positioning ────────────────────────────────────────────────────────────
  const vw = window.innerWidth
  const vh = window.innerHeight

  // Prefer right of anchor; fall back to left.
  let left = anchorRect.right + GAP
  if (left + TOOLTIP_W > vw - GAP) left = anchorRect.left - TOOLTIP_W - GAP
  left = Math.max(GAP, Math.min(left, vw - TOOLTIP_W - GAP))

  // Align top with anchor; shift up if it would go off-screen.
  let top = anchorRect.top - 4
  if (top + 250 > vh - GAP) top = vh - 250 - GAP
  top = Math.max(GAP, top)

  return (
    <>
      {/* Transparent backdrop — mousedown closes tooltip unless pinned */}
      {!pinned && (
        <div
          onMouseDown={close}
          style={{ position: 'fixed', inset: 0, zIndex: 1998 }}
        />
      )}

      {/* Popout card */}
      <div
        ref={ref}
        style={{
          position: 'fixed',
          left,
          top,
          width: TOOLTIP_W,
          zIndex: 1999,
          background: '#0d1721',
          border: `1px solid ${pinned ? '#e0a458' : '#2a4a5a'}`,
          borderRadius: 8,
          boxShadow: '0 8px 32px rgba(0,0,0,0.72)',
          fontFamily: 'Inter,system-ui,sans-serif',
          transition: 'border-color 0.2s',
        }}
      >
        {/* Header: title + pin + close */}
        <div style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 8,
          padding: '11px 12px 9px',
          borderBottom: '1px solid #1a2a36',
        }}>
          <div style={{
            ...MONO,
            fontSize: 18,
            fontWeight: 700,
            letterSpacing: '0.12em',
            color: '#3fb6a8',
            textTransform: 'uppercase' as const,
            lineHeight: 1.4,
            flex: 1,
          }}>
            {content.title}
          </div>

          <div style={{ display: 'flex', gap: 1, flexShrink: 0, marginTop: -1 }}>
            {/* Pin */}
            <button
              onClick={togglePin}
              title={pinned ? 'Unpin' : 'Pin open'}
              style={{
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                padding: '2px 4px',
                fontSize: 11,
                color: pinned ? '#e0a458' : '#4b5764',
                lineHeight: 1,
                borderRadius: 3,
              }}
            >
              📌
            </button>
            {/* Close */}
            <button
              onClick={close}
              title="Close"
              style={{
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                padding: '0px 5px 2px',
                fontSize: 18,
                color: '#4b5764',
                lineHeight: 1,
                borderRadius: 3,
              }}
            >
              ×
            </button>
          </div>
        </div>

        {/* Body */}
        <div style={{
          padding: '10px 13px 12px',
          fontSize: 22,
          color: '#9ab4c8',
          lineHeight: 1.65,
        }}>
          {content.body}
        </div>

        {/* Pinned indicator */}
        {pinned && (
          <div style={{
            padding: '0 13px 10px',
            ...MONO,
            fontSize: 16,
            color: '#e0a45875',
            letterSpacing: '0.06em',
          }}>
            PINNED — click 📌 to release
          </div>
        )}
      </div>
    </>
  )
}
