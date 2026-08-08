/**
 * tickStore.ts — Zustand store for the live tick stream.
 *
 * Architecture (Design Spec §2.2 / build plan §19.2):
 *   WebSocket messages arrive asynchronously and push into `pendingTicks`.
 *   App.tsx runs a 4 Hz setInterval that calls `drainFrame()` to move ticks
 *   from the pending queue into `latestTick` + `history` ring-buffer.
 *
 *   Frame behaviour:
 *     0 ticks pending (rate ≤ 1, slower than 4 Hz):
 *       Interpolate current display values between the last two ticks for smooth
 *       animation; rendered in visually distinct style (§2.2 "client-side guess").
 *     1 tick pending (rate ≈ 1): use that tick directly, no interpolation.
 *     N > 1 ticks pending (rate > 4 Hz, e.g. rate=60 delivers ~3 ticks/frame):
 *       Use most-recent tick for all current readings.
 *       Add ALL N ticks to history (no interpolation — §2.2 "no fabricated curves").
 *       Expose N as `decimationCount` for the chart badge.
 *
 * F4 — alert latching (rising-edge latch):
 *   `insufficient_reserve_alert` is true on exactly one tick (the staging tick).
 *   If the panel read from `latestTick.insufficient_reserve_alert` directly, the
 *   banner would flash for one frame and vanish before the operator can act.
 *   §7.2.4 requires operator acknowledgment, so we latch on rising edge:
 *     - When any pending tick has insufficient_reserve_alert=true, capture it as
 *       `latchedAlert` (keyed by tick_index — a new alert on a later tick
 *       replaces the latch).
 *     - `latchedAlert` is cleared only by calling `acknowledgeAlert(tickIndex)`.
 *     - AlertDock reads `latchedAlert`, not `latestTick.insufficient_reserve_alert`.
 *   The backend flag is intentionally unchanged: it correctly fires once at staging
 *   time (§7.2.4); the latch is a pure UI concern.
 *
 * Acknowledged alerts are stored by tick_index so a new alert on a later
 * tick re-shows the banner.  Backend acknowledgment (POST /api/alerts/{id}/ack)
 * is deferred to Step 8 — this is local-only dismissal (§19.2 Step 7 boundary).
 */

import { create } from 'zustand'
import type { HistoryPoint, RunMeta, TickPayload } from '../types'

/** Maximum number of points kept in the history ring-buffer (§19.2: 60). */
const HISTORY_MAX = 60

function toHistoryPoint(t: TickPayload): HistoryPoint {
  return {
    sim_time_seconds: t.sim_time_seconds,
    p_compute_mw: t.p_compute_mw,
    p_cooling_mw: t.p_cooling_mw,
    p_total_mw: t.p_total_mw,
    p_renewable_mw: t.p_renewable_mw,
    confidence_lower_mw: t.confidence_lower_mw,
    confidence_upper_mw: t.confidence_upper_mw,
  }
}

/** Linear interpolation between two ticks for smooth 4 Hz display at rate ≤ 1. */
function interpolateTick(a: TickPayload, b: TickPayload, t: number): TickPayload {
  const lerp = (x: number, y: number) => x + (y - x) * t
  return {
    ...b,
    p_compute_mw:     lerp(a.p_compute_mw,     b.p_compute_mw),
    p_cooling_mw:     lerp(a.p_cooling_mw,      b.p_cooling_mw),
    p_total_mw:       lerp(a.p_total_mw,         b.p_total_mw),
    net_demand_mw:    lerp(a.net_demand_mw,       b.net_demand_mw),
    p_renewable_mw:   lerp(a.p_renewable_mw,     b.p_renewable_mw),
    turbine_output_mw: lerp(a.turbine_output_mw, b.turbine_output_mw),
    bess_output_mw:   lerp(a.bess_output_mw,     b.bess_output_mw),
    bess_soc_fraction: lerp(a.bess_soc_fraction, b.bess_soc_fraction),
    confidence_lower_mw: lerp(a.confidence_lower_mw, b.confidence_lower_mw),
    confidence_upper_mw: lerp(a.confidence_upper_mw, b.confidence_upper_mw),
    bess_bridging_seconds: lerp(a.bess_bridging_seconds, b.bess_bridging_seconds),
    dt_lead_next_s:   lerp(a.dt_lead_next_s,     b.dt_lead_next_s),
    // Boolean and string fields: use most-recent tick (b).
    insufficient_reserve_alert: b.insufficient_reserve_alert,
    data_quality_tags: b.data_quality_tags,
    bridging_basis: b.bridging_basis,
  }
}

interface TickState {
  /** The tick currently displayed — may be interpolated (isInterpolated=true). */
  latestTick: TickPayload | null
  /** True when latestTick was produced by client-side interpolation, not a real tick. */
  isInterpolated: boolean
  /** Most-recent confirmed (non-interpolated) tick — used as interpolation base. */
  prevTick: TickPayload | null
  /** Trailing 60-point ring-buffer for ForecastChart. */
  history: HistoryPoint[]
  /** Ticks received from WS since last frame drain. */
  pendingTicks: TickPayload[]
  /** Number of ticks dropped in the last frame (N-1 when N>1 arrived).
   *  0 = no decimation.  Shown as "showing 1 of N" on the chart. */
  decimationCount: number
  /** Run metadata (id, playback speed). Set on run start/subscription. */
  runMeta: RunMeta | null
  /**
   * F4 — latched alert tick.
   * The tick on which insufficient_reserve_alert last fired (rising edge).
   * Null when no alert is active (either never fired, or was acknowledged).
   * Populated by drainFrame() on rising edge; cleared by acknowledgeAlert().
   * AlertDock reads this, NOT latestTick.insufficient_reserve_alert, so the
   * banner persists until the operator clicks Acknowledge even though the
   * backend flag is true on only one tick.
   */
  latchedAlert: TickPayload | null
  /** tick_index values the user has locally acknowledged (Step 7 only;
   *  Step 8 will add durable server-side ack via POST). */
  acknowledgedAlerts: Set<number>
  /** Wall-clock timestamp of the last frame drain — used to compute interpolation t. */
  _lastFrameWall: number

  // ── Actions ───────────────────────────────────────────────────────────────
  /** Called by the WebSocket consumer on each arriving message. */
  pushTick: (tick: TickPayload) => void
  /** Called by the 4 Hz render loop to move pending ticks into display state. */
  drainFrame: () => void
  setRunMeta: (meta: RunMeta) => void
  /**
   * Acknowledge the latched alert identified by tickIndex.
   * Clears latchedAlert when it matches, and records tickIndex in
   * acknowledgedAlerts so a future alert at the same index doesn't re-latch.
   */
  acknowledgeAlert: (tickIndex: number) => void
  reset: () => void
}

export const useTickStore = create<TickState>((set, get) => ({
  latestTick: null,
  isInterpolated: false,
  prevTick: null,
  history: [],
  pendingTicks: [],
  decimationCount: 0,
  runMeta: null,
  latchedAlert: null,
  acknowledgedAlerts: new Set(),
  _lastFrameWall: 0,

  pushTick(tick) {
    set(s => ({ pendingTicks: [...s.pendingTicks, tick] }))
  },

  drainFrame() {
    const now = Date.now()
    const s = get()
    const pending = s.pendingTicks

    if (pending.length === 0) {
      // ── 0 ticks: interpolate on EVERY drain frame for smooth display ───────
      // Re-run each 250 ms call so the display value continuously slides from
      // prevTick toward latestTick rather than snapping to a single midpoint.
      // The !isInterpolated guard was removed: one-shot interpolation caused a
      // visible stutter (display jumped once then froze until the next real tick).
      // _lastFrameWall is NOT updated here so elapsed grows monotonically from
      // the last real-tick wall time — giving a correct t in [0, 0.99].
      //
      // Safety guard: only interpolate when prevTick and latestTick are
      // near-consecutive (indexGap ≤ 2).  When the gap is larger — e.g. after a
      // WebSocket burst delivered many ticks at once and prevTick was left behind
      // from an earlier drain — lerping p_compute_mw (and other energy fields)
      // from the old prevTick while non-lerped fields (checkpoint_states,
      // on_bus_output_mw, turbine_units) come from the newer latestTick produces
      // internally inconsistent display values: e.g. 0.18 MW compute alongside
      // 27 jobs and 30 MW turbines.  Skipping interpolation in that case keeps
      // all tile values consistent with the same confirmed tick.
      if (s.prevTick && s.latestTick) {
        const indexGap = s.latestTick.tick_index - s.prevTick.tick_index
        if (indexGap <= 2) {
          const elapsed = (now - s._lastFrameWall) / 1000
          const rate = s.runMeta?.playback_speed ?? 1.0
          // For max-speed runs (rate ≤ 0) the inter-tick wall time is near-zero;
          // use a short simInterval so the display snaps to latestTick within one
          // frame instead of lingering at prevTick values for seconds.
          const simInterval = rate > 0 ? 5.0 / rate : 0.1
          const t = Math.min(0.99, elapsed / simInterval)
          const interpolated = interpolateTick(s.prevTick, s.latestTick, t)
          set({ latestTick: interpolated, isInterpolated: true, decimationCount: 0 })
        }
        // indexGap > 2: latestTick already holds the correct confirmed values —
        // leave it unchanged; the next real tick will close the gap naturally.
      }
      return
    }

    // ── 1 or N ticks: advance history ─────────────────────────────────────
    const addedHistory = pending.map(toHistoryPoint)
    const nextHistory = [...s.history, ...addedHistory].slice(-HISTORY_MAX)
    const newest = pending[pending.length - 1]
    const secondNewest = pending.length > 1 ? pending[pending.length - 2]
      : (s.isInterpolated ? s.prevTick : s.latestTick)

    // F4: rising-edge alert latch.
    // Scan all pending ticks for an alert flag.  If any tick has
    // insufficient_reserve_alert=true AND it is a newer event than the current
    // latch (higher tick_index), update the latch.  The already-acknowledged
    // set prevents re-latching an event the operator has already cleared.
    let newLatchedAlert = s.latchedAlert
    for (const t of pending) {
      if (
        t.insufficient_reserve_alert &&
        !s.acknowledgedAlerts.has(t.tick_index) &&
        (newLatchedAlert === null || t.tick_index > newLatchedAlert.tick_index)
      ) {
        newLatchedAlert = t
      }
    }

    set({
      latestTick: newest,
      isInterpolated: false,
      prevTick: secondNewest ?? newest,
      history: nextHistory,
      pendingTicks: [],
      decimationCount: pending.length > 1 ? pending.length : 0,
      latchedAlert: newLatchedAlert,
      _lastFrameWall: now,
    })
  },

  setRunMeta(meta) {
    set({ runMeta: meta })
  },

  acknowledgeAlert(tickIndex) {
    set(s => ({
      acknowledgedAlerts: new Set([...s.acknowledgedAlerts, tickIndex]),
      // Clear the latch only when it matches the acknowledged event.
      // If a newer alert has already replaced it, leave the new latch in place.
      latchedAlert:
        s.latchedAlert?.tick_index === tickIndex ? null : s.latchedAlert,
    }))
  },

  reset() {
    set({
      latestTick: null, isInterpolated: false, prevTick: null,
      history: [], pendingTicks: [], decimationCount: 0,
      runMeta: null, latchedAlert: null, acknowledgedAlerts: new Set(),
      _lastFrameWall: 0,
    })
  },
}))
