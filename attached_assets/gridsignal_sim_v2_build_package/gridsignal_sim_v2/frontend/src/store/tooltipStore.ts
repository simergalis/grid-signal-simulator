/**
 * tooltipStore.ts — lightweight Zustand store for the tile info tooltip.
 *
 * Any component (plant nodes, hero figures, subsystem tiles) can call
 * open(id, rect) to show the tooltip, and the single TileTooltip rendered
 * in OpeningScreen.tsx displays the authored copy.
 */

import { create } from 'zustand'

interface AnchorRect {
  top: number
  left: number
  bottom: number
  right: number
  width: number
  height: number
}

interface TooltipState {
  tooltipId:  string | null
  pinned:     boolean
  anchorRect: AnchorRect | null
  /** Open (or toggle closed if same tile). */
  open:       (id: string, rect: DOMRect) => void
  close:      () => void
  togglePin:  () => void
}

export const useTooltipStore = create<TooltipState>((set) => ({
  tooltipId:  null,
  pinned:     false,
  anchorRect: null,

  open: (id, rect) => set(s => {
    // Clicking the same tile again while unpin­ned toggles the tooltip closed.
    if (s.tooltipId === id && !s.pinned) {
      return { tooltipId: null, pinned: false, anchorRect: null }
    }
    return {
      tooltipId: id,
      anchorRect: {
        top:    rect.top,
        left:   rect.left,
        bottom: rect.bottom,
        right:  rect.right,
        width:  rect.width,
        height: rect.height,
      },
    }
  }),

  close:     () => set({ tooltipId: null, pinned: false, anchorRect: null }),
  togglePin: () => set(s => ({ pinned: !s.pinned })),
}))
