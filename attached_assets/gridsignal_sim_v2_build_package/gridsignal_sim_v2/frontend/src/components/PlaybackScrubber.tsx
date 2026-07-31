/**
 * PlaybackScrubber.tsx — Range-input scrubber with Prev / Next buttons.
 *
 * Props:
 *   totalTicks — length of the rows array
 *   cursorIdx  — current zero-based index into rows
 *   onChange   — called with new index when the user moves the cursor
 */

interface Props {
  totalTicks: number
  cursorIdx:  number
  onChange:   (idx: number) => void
}

export function PlaybackScrubber({ totalTicks, cursorIdx, onChange }: Props) {
  const max = Math.max(0, totalTicks - 1)

  const prev = () => onChange(Math.max(0, cursorIdx - 1))
  const next = () => onChange(Math.min(max, cursorIdx + 1))

  return (
    <div className="flex items-center gap-2 px-2 py-1">
      {/* Prev */}
      <button
        className="rounded border border-border px-2 py-0.5 text-xs text-muted
                   hover:border-accent hover:text-accent disabled:opacity-30 transition-colors"
        disabled={cursorIdx <= 0}
        onClick={prev}
        aria-label="Previous tick"
      >
        ‹ Prev
      </button>

      {/* Range input */}
      <input
        type="range"
        min={0}
        max={max}
        value={cursorIdx}
        onChange={e => onChange(Number(e.target.value))}
        className="flex-1 accent-accent h-1"
        aria-label="Playback cursor"
      />

      {/* Next */}
      <button
        className="rounded border border-border px-2 py-0.5 text-xs text-muted
                   hover:border-accent hover:text-accent disabled:opacity-30 transition-colors"
        disabled={cursorIdx >= max}
        onClick={next}
        aria-label="Next tick"
      >
        Next ›
      </button>

      {/* Position indicator */}
      <span className="shrink-0 font-mono text-[10px] text-muted w-[64px] text-right">
        {totalTicks > 0 ? `${cursorIdx + 1} / ${totalTicks}` : '0 / 0'}
      </span>
    </div>
  )
}
