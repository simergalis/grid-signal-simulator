/**
 * tooltipStore.ts — multi-pin tooltip store.
 *
 * Any number of tooltips can be pinned open simultaneously.
 * One additional "active" (unpinned) tooltip may also be showing.
 *
 *   open(id, rect)   → if already pinned, unpin+close it; if already active,
 *                       close it; otherwise open as active (replacing previous active).
 *   close(id)        → remove from pinned or clear active, whichever applies.
 *   togglePin(id)    → pin the active tooltip (or unpin if already pinned).
 *   closeUnpinned()  → close the active tooltip without touching pinned ones.
 */

import { create } from 'zustand'

export interface AnchorRect {
  top: number
  left: number
  bottom: number
  right: number
  width: number
  height: number
}

interface TooltipState {
  /** Tooltips that are explicitly pinned open. */
  pinnedIds:   string[]
  /** The one non-pinned tooltip currently in focus (null = none). */
  activeId:    string | null
  /** Anchor rect per tooltip id (all open tooltips, pinned or active). */
  anchorRects: Record<string, AnchorRect>

  open:          (id: string, rect: DOMRect) => void
  close:         (id: string) => void
  togglePin:     (id: string) => void
  closeUnpinned: () => void
}

function toAnchorRect(r: DOMRect): AnchorRect {
  return { top: r.top, left: r.left, bottom: r.bottom, right: r.right, width: r.width, height: r.height }
}

export const useTooltipStore = create<TooltipState>((set) => ({
  pinnedIds:   [],
  activeId:    null,
  anchorRects: {},

  open: (id, rect) => set(s => {
    // Already pinned → clicking ⓘ again unpins + closes it.
    if (s.pinnedIds.includes(id)) {
      const { [id]: _, ...rest } = s.anchorRects
      return {
        pinnedIds:   s.pinnedIds.filter(p => p !== id),
        anchorRects: rest,
      }
    }
    // Already the active (unpinned) tooltip → close it.
    if (s.activeId === id) {
      const { [id]: _, ...rest } = s.anchorRects
      return { activeId: null, anchorRects: rest }
    }
    // Open as new active tooltip; drop previous active rect if any.
    const rects = { ...s.anchorRects }
    if (s.activeId) delete rects[s.activeId]
    rects[id] = toAnchorRect(rect)
    return { activeId: id, anchorRects: rects }
  }),

  close: (id) => set(s => {
    const { [id]: _, ...rest } = s.anchorRects
    return {
      pinnedIds:   s.pinnedIds.filter(p => p !== id),
      activeId:    s.activeId === id ? null : s.activeId,
      anchorRects: rest,
    }
  }),

  togglePin: (id) => set(s => {
    if (s.pinnedIds.includes(id)) {
      // Unpin → close it entirely.
      const { [id]: _, ...rest } = s.anchorRects
      return { pinnedIds: s.pinnedIds.filter(p => p !== id), anchorRects: rest }
    }
    // Pin the active tooltip; clear activeId since it's now pinned.
    return {
      pinnedIds: [...s.pinnedIds, id],
      activeId:  s.activeId === id ? null : s.activeId,
    }
  }),

  closeUnpinned: () => set(s => {
    if (!s.activeId) return s
    const { [s.activeId]: _, ...rest } = s.anchorRects
    return { activeId: null, anchorRects: rest }
  }),
}))
