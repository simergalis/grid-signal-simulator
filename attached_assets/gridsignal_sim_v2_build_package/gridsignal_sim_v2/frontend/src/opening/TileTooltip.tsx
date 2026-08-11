/**
 * TileTooltip.tsx — floating plain-English pop-out for tile ⓘ buttons.
 *
 * Multiple tooltips can be pinned open at once.  One additional "active"
 * (unpinned) tooltip may also be visible.  Clicking outside the active
 * tooltip closes only that one; pinned tooltips are unaffected.
 *
 * InfoBtn is exported for use in any tile component.
 */

import { useEffect, useRef } from 'react'
import type { CSSProperties } from 'react'
import { useTooltipStore } from '../store/tooltipStore'
import type { AnchorRect }  from '../store/tooltipStore'
import { TILE_TOOLTIPS }    from './tileTooltipContent'

// ── Shared style constants ────────────────────────────────────────────────────

const MONO: CSSProperties = { fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace" }
const TOOLTIP_W = 360
const GAP       = 10   // px from viewport edges / anchor

// ── InfoBtn ───────────────────────────────────────────────────────────────────

/**
 * Small ⓘ button that opens/closes the tile tooltip.
 * Uses <span role="button"> to avoid nested-button HTML issues.
 */
export function InfoBtn({ id, style }: { id: string; style?: CSSProperties }) {
  const open      = useTooltipStore(s => s.open)
  const pinnedIds = useTooltipStore(s => s.pinnedIds)
  const activeId  = useTooltipStore(s => s.activeId)
  const active    = pinnedIds.includes(id) || activeId === id

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
        background: active ? '#3fb6a8' : '#4a9fe0',
        color: '#fff',
        fontSize: 9,
        fontWeight: 700,
        fontStyle: 'italic',
        lineHeight: 1,
        flexShrink: 0,
        userSelect: 'none' as const,
        transition: 'background 0.15s',
        ...style,
      }}
    >
      i
    </span>
  )
}

// ── Single tooltip card ───────────────────────────────────────────────────────

function TooltipCard({ id, anchorRect, pinned }: {
  id:         string
  anchorRect: AnchorRect
  pinned:     boolean
}) {
  const close     = useTooltipStore(s => s.close)
  const togglePin = useTooltipStore(s => s.togglePin)
  const content   = TILE_TOOLTIPS[id]
  if (!content) return null

  // ── Positioning ────────────────────────────────────────────────────────────
  const vw = window.innerWidth
  const vh = window.innerHeight

  let left = anchorRect.right + GAP
  if (left + TOOLTIP_W > vw - GAP) left = anchorRect.left - TOOLTIP_W - GAP
  left = Math.max(GAP, Math.min(left, vw - TOOLTIP_W - GAP))

  let top = anchorRect.top - 4
  if (top + 280 > vh - GAP) top = vh - 280 - GAP
  top = Math.max(GAP, top)

  return (
    <div
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
          <button
            onClick={() => togglePin(id)}
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
          <button
            onClick={() => close(id)}
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
  )
}

// ── TileTooltip root ──────────────────────────────────────────────────────────

export function TileTooltip() {
  const pinnedIds    = useTooltipStore(s => s.pinnedIds)
  const activeId     = useTooltipStore(s => s.activeId)
  const anchorRects  = useTooltipStore(s => s.anchorRects)
  const closeUnpinned = useTooltipStore(s => s.closeUnpinned)

  // Refs for the active (unpinned) card — click-outside closes it.
  const activeRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!activeId) return
    const handler = (e: MouseEvent) => {
      if (activeRef.current && !activeRef.current.contains(e.target as Node)) {
        closeUnpinned()
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [activeId, closeUnpinned])

  // All IDs that need a card rendered (pinned first, then active if distinct).
  const openIds = [
    ...pinnedIds,
    ...(activeId && !pinnedIds.includes(activeId) ? [activeId] : []),
  ]

  if (openIds.length === 0) return null

  return (
    <>
      {/* Transparent backdrop — closes the active (unpinned) tooltip only */}
      {activeId && !pinnedIds.includes(activeId) && (
        <div
          onMouseDown={closeUnpinned}
          style={{ position: 'fixed', inset: 0, zIndex: 1998 }}
        />
      )}

      {openIds.map(id => {
        const rect   = anchorRects[id]
        const pinned = pinnedIds.includes(id)
        if (!rect) return null
        return (
          <div
            key={id}
            ref={!pinned && id === activeId ? activeRef : undefined}
            style={{ position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 1999 }}
          >
            <div style={{ pointerEvents: 'auto', position: 'absolute', top: 0, left: 0 }}>
              <TooltipCard id={id} anchorRect={rect} pinned={pinned} />
            </div>
          </div>
        )
      })}
    </>
  )
}
