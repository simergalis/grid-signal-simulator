/**
 * ReadinessScreen.tsx — landing screen (U2).
 *
 * Layout:
 *   ReadinessBanner (overall verdict + 4 hero figures)
 *   CSS Grid of SubsystemTile, grouped under 4 section headers:
 *     DATA CENTRE | ENERGY STORAGE | POWER SOURCES | SYSTEM
 *
 * Grid: 3 columns ≥ 1280 px · 2 columns 768–1279 px · 1 column < 768 px.
 * Tiles keep a fixed aspect ratio (aspect-[4/3]) so rows align.
 * CSS Grid, not Flexbox — the alignment requirement is two-dimensional.
 *
 * Tiles read from the tick stream only — no per-tile polling.
 * Modals may poll their endpoint on open (one at a time).
 */

import { useState } from 'react'
import { ReadinessBanner }  from './ReadinessBanner'
import { SubsystemTile }    from './SubsystemTile'
import type { TileState }   from './SubsystemTile'
import { SUBSYSTEMS, GROUP_LABELS, GROUP_ORDER } from './subsystems'
import type { SubsystemGroup } from './subsystems'
import { useSubsystemData } from '../subsystem/useSubsystemData'
import { SubsystemModal }   from '../subsystem/SubsystemModal'

export function ReadinessScreen({
  onNavigate,
}: {
  onNavigate?: (tabId: string) => void
}) {
  const [activeModal, setActiveModal] = useState<string | null>(null)
  const data = useSubsystemData()

  const handleTileClick = (id: string) => {
    setActiveModal(id)
  }

  const handleModalClose = () => setActiveModal(null)

  const handleOpenPage = (tabId: string) => {
    setActiveModal(null)
    onNavigate?.(tabId)
  }

  // Group subsystems
  const grouped: Record<SubsystemGroup, typeof SUBSYSTEMS> = {
    'data-centre': [],
    'storage':     [],
    'supply':      [],
    'system':      [],
  }
  SUBSYSTEMS.forEach(s => grouped[s.group].push(s))

  return (
    <div className="flex flex-col h-full bg-canvas overflow-hidden">
      <ReadinessBanner />

      {/* Scrollable tile grid */}
      <div className="flex-1 overflow-y-auto p-6 space-y-8">
        {GROUP_ORDER.map(group => (
          <section key={group}>
            <h2 className="font-mono text-[9px] uppercase tracking-[0.15em] text-muted mb-3">
              {GROUP_LABELS[group]}
            </h2>
            {/* 3-col ≥1280, 2-col 768–1279, 1-col <768 */}
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
              {grouped[group].map(cfg => {
                const d = data[cfg.id]
                return (
                  <div key={cfg.id} className="aspect-[4/3]">
                    <SubsystemTile
                      id={cfg.id}
                      name={cfg.name}
                      state={d?.state as TileState ?? '—'}
                      accentColor={cfg.accentColor}
                      verdict={d?.verdict ?? 'No active run.'}
                      metrics={d?.metrics ?? [
                        { label: '—', value: '—' },
                        { label: '—', value: '—' },
                        { label: '—', value: '—' },
                      ]}
                      onClick={handleTileClick}
                    />
                  </div>
                )
              })}
            </div>
          </section>
        ))}
      </div>

      {/* Subsystem modal — renders when a tile is clicked */}
      {activeModal && (
        <SubsystemModal
          subsystemId={activeModal}
          onClose={handleModalClose}
          onOpenPage={handleOpenPage}
        />
      )}
    </div>
  )
}
