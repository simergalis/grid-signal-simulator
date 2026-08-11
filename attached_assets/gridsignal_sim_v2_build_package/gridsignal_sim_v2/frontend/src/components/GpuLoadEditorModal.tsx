/**
 * GpuLoadEditorModal.tsx
 *
 * Full-screen-centred modal wrapper around GpuLoadEditor.
 * Holds a local draft so Save / Cancel work atomically:
 *   • Save   → calls onSave(draft) and closes
 *   • Cancel → discards draft and closes (onCancel)
 *   • Esc / backdrop click → same as Cancel
 */

import { useEffect, useState } from 'react'
import { GpuLoadEditor } from './GpuLoadEditor'

interface Props {
  /** Current committed points (copied into draft on open). */
  points: [number, number][]
  /** Scenario duration in seconds — drives the X axis. */
  durationSeconds: number
  /** Called with the new points array when the operator clicks Save. */
  onSave: (pts: [number, number][]) => void
  /** Called when the operator clicks Cancel or dismisses the modal. */
  onCancel: () => void
}

export function GpuLoadEditorModal({ points, durationSeconds, onSave, onCancel }: Props) {
  // Draft is a local copy — changes here don't touch the scenario spec until Save.
  const [draft, setDraft] = useState<[number, number][]>(() => [...points])

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onCancel() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onCancel])

  const handleSave = () => onSave(draft)

  const handleReset = () => setDraft([])

  return (
    /* Backdrop — sits above the ScenarioBuilder (z-50) */
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70"
      onMouseDown={e => { if (e.target === e.currentTarget) onCancel() }}
    >
      {/* Panel */}
      <div
        className="relative flex flex-col rounded-xl border border-border bg-surface shadow-2xl"
        style={{ width: 740, maxWidth: '95vw', maxHeight: '85vh' }}
        onMouseDown={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-5 py-3 flex-shrink-0">
          <div>
            <h3 className="text-sm font-semibold text-text">GPU Load Profile</h3>
            <p className="text-[10px] text-muted mt-0.5">
              Zero-order hold · shapes compute demand over the run duration
            </p>
          </div>
          <button
            onClick={onCancel}
            className="ml-4 rounded border border-border w-7 h-7 flex items-center justify-center
                       text-muted hover:text-text hover:border-muted/60 transition-colors text-sm"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {/* Editor body */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          <GpuLoadEditor
            points={draft}
            durationSeconds={durationSeconds}
            onChange={setDraft}
          />

          {/* Usage hints */}
          <p className="text-[10px] text-muted leading-relaxed">
            <strong className="text-text">Click</strong> empty canvas to add a point.&ensp;
            <strong className="text-text">Drag</strong> a point to adjust time and load %.&ensp;
            <strong className="text-text">Delete / Backspace</strong> to remove the selected point.&ensp;
            Empty profile = constant 100 % (full TDP) for the entire run.
          </p>

          {/* Current point count summary */}
          <div className="flex items-center gap-3">
            <span className="text-[10px] font-mono text-muted">
              {draft.length === 0
                ? 'No points — flat 100 % load'
                : `${draft.length} point${draft.length === 1 ? '' : 's'} defined`}
            </span>
            {draft.length > 0 && (
              <button
                onClick={handleReset}
                className="text-[10px] text-muted hover:text-danger transition-colors"
              >
                reset to flat
              </button>
            )}
          </div>
        </div>

        {/* Footer — Save / Cancel */}
        <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-3 flex-shrink-0">
          <button
            onClick={onCancel}
            className="rounded border border-border px-4 py-1.5 text-xs text-muted
                       hover:text-text transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className="rounded bg-accent px-4 py-1.5 text-xs font-semibold text-white
                       hover:bg-accent/80 transition-colors"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  )
}
