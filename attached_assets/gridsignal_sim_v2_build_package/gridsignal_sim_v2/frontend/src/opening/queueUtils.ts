/**
 * queueUtils.ts — Pure helpers for the Queue tab in GpuNodeGeneratorModal.
 *
 * Kept in a separate module so tests can import the logic without pulling in
 * the full React component tree.
 */

// ── Wait-time colour thresholds ───────────────────────────────────────────────
//
// PROPOSED_HERE — no measured basis.  Values chosen to align with typical K8s
// admission-latency expectations at the demo-run tick cadence (5 s/tick):
//   < 30 s  → within ~6 ticks  → green  (normal queuing latency)
//   30–120 s → 6–24 ticks      → amber  (elevated; operator should notice)
//   > 120 s  → >24 ticks       → red    (stalled; likely floor headroom issue)
//
// Revisit against p90 queue-wait measurements from production runs before GA.
// The thresholds are exclusive (strictly > threshold switches to the next band).
export const QUEUE_WAIT_AMBER_THRESHOLD_S = 30   // PROPOSED_HERE
export const QUEUE_WAIT_RED_THRESHOLD_S   = 120  // PROPOSED_HERE

/**
 * CSS colour for a queue wait duration.
 *
 * Boundary contract (strictly-greater-than):
 *   wait ≤ 30   → '#3fb6a8'  (teal  — normal)
 *   wait = 30.0 → '#3fb6a8'  (teal  — exactly at threshold → NOT amber)
 *   wait = 30.1 → '#f0883e'  (amber — strictly above threshold)
 *   wait = 120.0→ '#f0883e'  (amber — exactly at threshold → NOT red)
 *   wait = 120.1→ '#f85149'  (red   — strictly above threshold)
 */
export function queueWaitColour(waitSeconds: number): string {
  if (waitSeconds > QUEUE_WAIT_RED_THRESHOLD_S)   return '#f85149'
  if (waitSeconds > QUEUE_WAIT_AMBER_THRESHOLD_S) return '#f0883e'
  return '#3fb6a8'
}

/**
 * Format a wait duration (seconds) as a compact human-readable string.
 *
 *   secs < 0  → '—'       (no data / not yet queued)
 *   secs < 60 → 'Xs'      (e.g. '29s')
 *   secs ≥ 60 → 'Xm Ys'  (e.g. '2m 5s'; omits 's' component if it is 0)
 */
export function fmtQueueWait(secs: number): string {
  if (secs < 0) return '—'
  if (secs < 60) return `${Math.floor(secs)}s`
  const m = Math.floor(secs / 60)
  const s = Math.floor(secs % 60)
  return s > 0 ? `${m}m ${s}s` : `${m}m`
}

/**
 * Comparator: sorts QueuedJobSummary records longest-waiting-first
 * (ascending queued_since_s — smaller sim-time value = entered queue earlier).
 *
 * Exported so the sort is tested directly and not via the rendered component.
 */
export function compareByQueuedSince<T extends { queued_since_s: number }>(
  a: T, b: T,
): number {
  return a.queued_since_s - b.queued_since_s
}
