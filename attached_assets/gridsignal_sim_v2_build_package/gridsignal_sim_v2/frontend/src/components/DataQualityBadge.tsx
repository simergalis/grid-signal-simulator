/**
 * DataQualityBadge.tsx — inline chip for a DataQualityTag value (§19.11).
 *
 * Rendered wherever a tagged value appears: HeroPanel confidence band,
 * ForecastChart legend, AssetReservePanel readings.  The chip is compact
 * (single-line text, short code) so it can sit inline without disrupting
 * the surrounding layout.
 *
 * The SimClockHeader renders the full legend once; these badges are the
 * per-value flags.
 */

export type DQTag =
  | 'unmapped_hardware'
  | 'uncalibrated_site'
  | 'invalid_payload'
  | 'stale_profile'

const TAG_META: Record<DQTag, { code: string; label: string; color: string }> = {
  unmapped_hardware: { code: 'UMH', label: 'Unmapped hardware',  color: 'bg-warn/20 text-warn border-warn/40' },
  uncalibrated_site: { code: 'UCS', label: 'Uncalibrated site', color: 'bg-accent/20 text-accent border-accent/40' },
  invalid_payload:   { code: 'INV', label: 'Invalid payload',   color: 'bg-danger/20 text-danger border-danger/40' },
  stale_profile:     { code: 'STL', label: 'Stale profile',     color: 'bg-muted/20 text-muted border-muted/40' },
}

interface Props {
  tag: string
  /** Show full label instead of 3-letter code.  Used in the header legend. */
  full?: boolean
  /**
   * When false (legend chips at rest), render muted grey regardless of tag type.
   * Defaults to true so inline badges on data panels remain coloured.
   */
  active?: boolean
}

export function DataQualityBadge({ tag, full = false, active = true }: Props) {
  const meta = TAG_META[tag as DQTag]
  if (!meta) return null
  const colorClass = active
    ? meta.color
    : 'bg-canvas text-muted border-border opacity-50'
  return (
    <span
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-xs leading-tight transition-colors ${colorClass}`}
      title={meta.label}
    >
      ⚑ {full ? meta.label : meta.code}
    </span>
  )
}
