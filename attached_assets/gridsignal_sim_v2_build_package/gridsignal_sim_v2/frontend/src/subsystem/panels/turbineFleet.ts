/**
 * turbineFleet.ts — Gas Turbine Fleet modal (gs-14).
 *
 * AE1: no hardcoded fleet data. All figures derive from tick.turbine_units
 *      (the per-unit spec array stamped onto every TickResult by run_manager).
 *
 * AE3: one modal, two branches driven by unit count:
 *   0 units (no tick / no spec): "not instrumented" state
 *   1 unit:  single-unit view + red N−1=0 line
 *   N units: fleet table + N−1 bullet + ramp-vs-count bullet
 *   Same paralleling inset in all live states (draws one row per unit).
 *
 * Phase 0 field-boundary reconciliation (six contradictions fixed):
 *   0.1 identityLine derived from turbine_units (count, rated_mw, gt_mode).
 *   0.2 SYNC column uses unit.breaker_closed — never inferred from output MW.
 *       FLEET header derives on-bus count from units_on_bus_count.
 *   0.3 Units on-bus count from tick.units_on_bus_count;
 *       contributing MW from tick.on_bus_output_mw — same filtered set (Phase C D-05).
 *   0.4 N−1 margin subtitle states the arithmetic (firm, installed, contingency,
 *       peak) — not a raw unit count.
 *   0.5 Ramp-energy claim capped at installedMW; unbounded integral removed.
 *   0.6 OUTPUT column renamed CURRENT MW; NO-LOAD / MSL column added from
 *       named typed fields no_load_mw and msl_mw.
 */

import React from 'react'
import type { PanelConfig, PanelData } from './index'
import type { TickPayload, HistoryPoint, TurbineUnitSpec } from '../../types'
import { BulletBar } from '../../charts/BulletBar'
import { peakSiteLoadMW } from '../../config/siteParameters'

// ── Colour constants ─────────────────────────────────────────────────────────
const GOLD  = '#e0a458'
const TEAL  = '#3fb6a8'
const RED   = '#f85149'
const AMBER = '#f0883e'
const EMBER = '#d9663d'  // UNLOADING distinction — mockup --ember; gap 5

// GS-DES-CFG-001 §Phase-3: PEAK_LOAD_MW removed.
// Peak site load is derived from run history via peakSiteLoadMW(history).
// Labelled "observed peak this run" — see siteParameters.ts for the caveat
// (understates early in a run before the site has reached its demand peak).
// No LEAD_WINDOW_S constant — the lead horizon is tick.dt_lead_next_s.
// The lead horizon is tick.dt_lead_next_s (the dispatch arbitrator's runtime
// value), passed as horizonS to helpers.  When no step is in-flight the
// horizon is 0 and no ramp requirement is displayed.

const MONO: React.CSSProperties = {
  fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace",
}

// ── Thermal state ─────────────────────────────────────────────────────────────
const THERMAL_COLOUR: Record<string, string> = {
  hot:  AMBER,
  warm: GOLD,
  cold: TEAL,
}

const _THERMAL_ROWS = [
  { state: 'hot',  label: 'Hot',  cond: 'Off < 1 hour',                syncTime: '300 s (5 min)'  },
  { state: 'warm', label: 'Warm', cond: 'Off 1–4 hours',                syncTime: '300 s (5 min)'  },
  { state: 'cold', label: 'Cold', cond: 'Off > 4 hours, or never run',  syncTime: '900 s (15 min)' },
] as const

// Derive thermal state from unit spec; fallback to 'cold' when field absent.
function _thermalOf(u: TurbineUnitSpec): string {
  return (u.thermal_state as string | null | undefined) ?? 'cold'
}

// Stat-row subtitle for the current thermal state — accurate start time.
function _thermalSub(state: string): string {
  if (state === 'hot')  return '300 s (5 min) to sync — recently stopped'
  if (state === 'warm') return '300 s (5 min) to sync — partially cooled'
  return '900 s (15 min) to sync — never run or fully cooled'
}

interface ThermalUnit { asset_id: string; thermal: string; ratedMW: number; rampMWs: number }

// ── ThermalStateWidget ───────────────────────────────────────────────────────
// Standalone React function component — has its own useState for the overlay.
// Renders a clickable "THERMAL STATE · Cold ↗" bar below the fleet table.
// On click: fixed-position overlay with the 3-row start-time guide, current
// state row highlighted (left border + background tint + bold label).
function ThermalStateWidget({ units }: { units: ThermalUnit[] }): React.ReactNode {
  const [open, setOpen] = React.useState(false)
  if (units.length === 0) return null

  // Worst-case state across the set (cold < warm < hot in start-time severity).
  const ORDER = ['cold', 'warm', 'hot']
  const primaryState = units.reduce((worst, u) =>
    ORDER.indexOf(u.thermal) < ORDER.indexOf(worst) ? u.thermal : worst
  , units[0].thermal)

  const primaryColour = THERMAL_COLOUR[primaryState] ?? '#8b949e'
  const primaryLabel  = primaryState.charAt(0).toUpperCase() + primaryState.slice(1)

  // "Ramp to full output" note uses the first unit's actual rate.
  const u0          = units[0]
  const timeToFullS = Math.ceil(u0.ratedMW / u0.rampMWs)
  const rampNote    = `+ up to ${timeToFullS} s at ${u0.rampMWs.toFixed(3)} MW/s`

  const thSt = {
    ...MONO, padding: '6px 10px', textAlign: 'left' as const,
    fontSize: 9, color: '#8b949e', fontWeight: 700,
    letterSpacing: '0.08em', textTransform: 'uppercase' as const,
    borderBottom: '1px solid #2a3a4a',
  }
  const tdSt = (active: boolean) => ({
    ...MONO, padding: '10px 10px', fontSize: 11,
    color: active ? '#c9d1d9' : '#8b949e', borderBottom: '1px solid #1a2535',
  })
  // A row is highlighted when any unit in the set has that thermal state.
  const isActive = (rowState: string) => units.some(u => u.thermal === rowState)

  return React.createElement(React.Fragment, null,

    // ── Clickable bar ─────────────────────────────────────────────────────────
    React.createElement('div', {
      style: {
        ...MONO, display: 'flex', alignItems: 'center',
        justifyContent: 'space-between',
        padding: '8px 0', marginTop: 6,
        borderTop: '1px solid #2a3a4a',
        cursor: 'pointer', userSelect: 'none',
      },
      onClick: () => setOpen(true),
      title: 'View start-time guide',
    },
      React.createElement('span', {
        style: {
          ...MONO, fontSize: 9, fontWeight: 700,
          letterSpacing: '0.1em', textTransform: 'uppercase' as const,
          color: '#8b949e',
        },
      }, 'THERMAL STATE'),
      React.createElement('span', {
        style: { ...MONO, fontSize: 10, fontWeight: 600, color: primaryColour },
      }, `${primaryLabel} \u2197`),
    ),

    // ── Fixed overlay ─────────────────────────────────────────────────────────
    !open ? null : React.createElement('div', {
      style: {
        position: 'fixed', inset: 0, zIndex: 60,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'rgba(0,0,0,0.78)',
      },
      onClick: (e: React.MouseEvent) => { if (e.target === e.currentTarget) setOpen(false) },
    },
      React.createElement('div', {
        style: {
          background: '#0d1117', border: '1px solid #2a3a4a',
          borderRadius: 12, padding: '24px 28px',
          maxWidth: 580, width: '90vw',
          boxShadow: '0 24px 64px rgba(0,0,0,0.65)',
        },
      },

        // Header
        React.createElement('div', {
          style: {
            ...MONO, fontSize: 11, fontWeight: 700,
            letterSpacing: '0.12em', textTransform: 'uppercase' as const,
            color: '#8b949e', marginBottom: 16,
          },
        }, 'Start-Time Guide'),

        // Table
        React.createElement('table', {
          style: { width: '100%', borderCollapse: 'collapse' as const },
        },
          React.createElement('thead', null,
            React.createElement('tr', null,
              ...['Thermal state', 'Condition', 'Time to synchronised', 'Then ramp to full output'].map(h =>
                React.createElement('th', { key: h, style: thSt }, h)
              )
            )
          ),
          React.createElement('tbody', null,
            ..._THERMAL_ROWS.map(row => {
              const act   = isActive(row.state)
              const acCol = THERMAL_COLOUR[row.state]
              return React.createElement('tr', {
                key: row.state,
                style: {
                  background: act ? 'rgba(255,255,255,0.035)' : 'transparent',
                  borderLeft: `3px solid ${act ? acCol : 'transparent'}`,
                },
              },
                React.createElement('td', {
                  style: { ...tdSt(act), fontWeight: act ? 700 : 400, color: act ? acCol : '#8b949e' },
                }, row.label),
                React.createElement('td', { style: tdSt(act) }, row.cond),
                React.createElement('td', { style: tdSt(act) }, row.syncTime),
                React.createElement('td', { style: tdSt(act) },
                  row.state === 'hot' ? rampNote : '+ up to 50 s'
                ),
              )
            })
          )
        ),

        // Close
        React.createElement('div', { style: { marginTop: 20, textAlign: 'right' as const } },
          React.createElement('button', {
            style: {
              background: TEAL, color: '#0d1117', border: 'none',
              borderRadius: 6, padding: '7px 22px',
              ...MONO, fontSize: 11, fontWeight: 700,
              cursor: 'pointer', letterSpacing: '0.04em',
            },
            onClick: () => setOpen(false),
          }, 'Close'),
        ),
      )
    )
  )
}

// ── 0.1: derive identity line from typed TickPayload fields ──────────────────
// Replaces the hardcoded "3 × 15 MW aeroderivative" literal in subsystems.ts.
// Count, rating, and prime-mover class all come from turbine_units.
function _identityLine(units: TurbineUnitSpec[]): string {
  if (units.length === 0) {
    return 'gas turbine fleet · synchronous · islanded primary generation'
  }
  const n       = units.length
  const ratedMW = units[0].rated_mw.toFixed(0)
  const modeStr = units[0].gt_mode === 'aero' ? 'aeroderivative' : 'frame-class'
  return `${n} × ${ratedMW} MW ${modeStr} · synchronous · islanded primary generation`
}

// ── Derived fleet metrics from a unit list ───────────────────────────────────
// horizonS: dispatch arbitrator's runtime lead time (tick.dt_lead_next_s).
//   When 0 (no step in-flight) rampNeedMWs = 0 — no active requirement.
function deriveFleet(units: TurbineUnitSpec[], horizonS: number, peakMW: number) {
  const installedMW   = units.reduce((s, u) => s + u.rated_mw, 0)
  const maxUnitMW     = units.length > 0 ? Math.max(...units.map(u => u.rated_mw)) : 0
  // U-4 fix: N−1 firm from committed (on-bus) units only — OFFLINE excluded.
  // isOnBus() is a function declaration (hoisted) so this forward-reference is safe.
  const onBusUnits    = units.filter(isOnBus)
  const onBusMW       = onBusUnits.reduce((s, u) => s + u.rated_mw, 0)
  const maxOnBusMW    = onBusUnits.length > 0 ? Math.max(...onBusUnits.map(u => u.rated_mw)) : 0
  const n1FirmMW      = Math.max(0, onBusMW - maxOnBusMW)
  // rampNeedMWs: MW/s needed to cover peak load in the runtime lead window.
  // 0 when no step is in-flight (horizonS = 0) — no active requirement to display.
  const rampNeedMWs   = horizonS > 0 && peakMW > 0 ? peakMW / horizonS : 0
  const n1MarginPct   = n1FirmMW > 0 && peakMW > 0
    ? Math.round((n1FirmMW - peakMW) / peakMW * 100)
    : -100
  // aggRampMWs and maxRamp removed (U-1/U-2): tick.ramp_capability_mw is authoritative.
  return { installedMW, maxUnitMW, n1FirmMW, rampNeedMWs, n1MarginPct, onBusMW, maxOnBusMW, onBusCount: onBusUnits.length }
}

// ── On-bus determination ─────────────────────────────────────────────────────
// Algebraic formula: unit i ∈ A ⟺ state_i ∈ {synchronised, unloading} (is_on_bus).
// Phase C: UNLOADING units are still breaker-closed and producing; they must be
// treated as on-bus by the UI.  RAMPING / AT_TARGET no longer exist.
// Phase 0 fallback: static breaker_closed from spec (absent state field).
function isOnBus(u: TurbineUnitSpec): boolean {
  if (u.state !== undefined) {
    return u.state === 'synchronised' || u.state === 'unloading'
  }
  return u.breaker_closed
}

// ── Operator unit command ─────────────────────────────────────────────────────
// Module-level pending-command map: unit_id → "trip" | "start".
// Persists across renders (modules are singletons) so the button stays disabled
// until the next tick broadcast confirms the state has changed.
// Cleared on state-change confirmation or on fetch error.
const _pending: Map<string, string> = new Map()

function _issueUnitCommand(runId: string, unitId: string, action: string): void {
  if (_pending.has(unitId)) return   // already in-flight
  _pending.set(unitId, action)
  fetch(`/runs/${encodeURIComponent(runId)}/units/${encodeURIComponent(unitId)}/command`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ action }),
  })
    .then(r => {
      if (!r.ok) {
        r.text().then(t => console.warn(`unit command ${action} ${unitId} → ${r.status}: ${t}`))
        _pending.delete(unitId)
      }
      // On success: leave in pending until next tick shows the new state
    })
    .catch(err => {
      console.warn(`unit command ${action} ${unitId} failed:`, err)
      _pending.delete(unitId)
    })
}

// ── Per-unit table ───────────────────────────────────────────────────────────
// syncedCount: from tick.units_on_bus_count — never derived from output.
function FleetTable(
  units: TurbineUnitSpec[],
  aggregateOutputMW: number,
  maxRamp: number,
  syncedCount: number,
  runId: string,
): React.ReactNode {
  // Algebraic per-unit output: p_i from the Phase 2 overlay output_mw field.
  // output_mw is stamped by the server as t.output_mw() for SYNCHRONISED units (the
  // loading layer sets this), and 0.0 for all other states (RAMPING / OFFLINE / STARTING).
  // This replaces the proportional-distribution formula which incorrectly assigned a
  // share of aggregateOutputMW to RAMPING turbines whose advance() ramp is internal.
  // Legacy Phase 0 fallback (no state field): distribute aggregate proportionally.
  const onBusRated = units.reduce((s, u) => s + (isOnBus(u) ? u.rated_mw : 0), 0) || 1
  const unitOutputs = units.map((u: any) => {
    const perUnit = u.output_mw
    if (perUnit !== undefined) return perUnit as number
    // Phase 0 fallback: no live state overlay — distribute proportionally
    return isOnBus(u) ? aggregateOutputMW * (u.rated_mw / onBusRated) : 0
  })

  // 0.2: FLEET header — on-bus count from named field, not hardcoded string.
  const syncedStr   = syncedCount === 0 ? 'NONE ON BUS' : `${syncedCount} ON BUS`
  const unitCountStr = units.length === 1
    ? `1 UNIT · ${syncedStr}`
    : `${units.length} UNITS · ${syncedStr}`

  const hCell: React.CSSProperties = {
    ...MONO, fontSize: 9, fontWeight: 700,
    letterSpacing: '0.1em', color: '#8b949e',
    padding: '0 10px 6px 0', textTransform: 'uppercase' as const,
    borderBottom: '1px solid #2a3a4a', whiteSpace: 'nowrap' as const,
  }
  const dCell = (colour?: string, bold?: boolean): React.CSSProperties => ({
    ...MONO, fontSize: 10,
    color: colour ?? '#c9d1d9', fontWeight: bold ? 600 : 400,
    padding: '5px 10px 5px 0', borderBottom: '1px solid #161f29',
    whiteSpace: 'nowrap' as const,
  })

  const rows = units.map((u, i) => {
    const out      = unitOutputs[i]
    const isDeg    = u.r_asset_mw_per_s < 0.95 * maxRamp
    // 0.2: isOnBus() prefers live state (Phase 2) over static breaker_closed (Phase 0).
    // Never inferred from output MW.
    const onBus    = isOnBus(u)
    // liveSt must be declared before syncStr / stateStr (all reference it).
    const liveSt   = u.state ?? (onBus ? 'synchronised' : 'offline')
    // Item 8: STARTING is in its own phase — neither open-and-idle nor closed.
    const syncStr  = liveSt === 'starting' ? 'syncing' : onBus ? 'closed' : 'open'
    const rampStr  = `${u.r_asset_mw_per_s.toFixed(3)} / ${maxRamp.toFixed(3)}`
    const runHStr  = u.run_hours_h != null
      ? Math.round(u.run_hours_h).toLocaleString()
      : '—'
    // 0.6: no_load_mw and msl_mw from named typed fields — resolves column ambiguity
    // noLoadMslStr removed: data now expressed by the dashed MSL rule in the bar column.

    // ── Operator action button ────────────────────────────────────────────
    // State machine: on-bus → Trip button; OFFLINE → Start button; STARTING → disabled.
    // Pending: command was issued but the next tick hasn't confirmed state change yet.
    // Clear pending when the state we commanded has been reached (tick confirms it).
    // State label derived from live TurbineState (dynamic variable, not hardcoded).
    // 'synchronised' → 'online'   (loading layer managing output: on bus, in A)
    // 'ramping'      → 'ramping'  (auto-staged via advance(); NOT yet in A)
    // 'at_target'    → 'ramping'  (legacy alias; same as ramping — not in A)
    // 'starting'     → 'starting' (command_start() sequence in progress)
    // otherwise      → 'degraded' | 'available' (offline / out_of_service)
    const stateStr =
      liveSt === 'synchronised'
        ? (isDeg ? 'degraded' : 'online')
        : liveSt === 'unloading'
        ? 'unloading'                                    // U-8/Item 8: distinct from synchronised
        : liveSt === 'ramping' || liveSt === 'at_target'
        ? 'ramping'
        : liveSt === 'starting'
        ? 'starting'
        : isDeg ? 'degraded' : 'available'
    const isPending = _pending.has(u.asset_id)

    // Clear stale pending entries when the tick confirms the transition.
    if (isPending) {
      const pendingAction = _pending.get(u.asset_id)!
      const reachedTrip  = pendingAction === 'trip'  && liveSt === 'offline'
      const reachedStart = pendingAction === 'start' && (liveSt === 'starting' || liveSt === 'synchronised')
      if (reachedTrip || reachedStart) _pending.delete(u.asset_id)
    }

    let actionCell: React.ReactNode
    const btnBase: React.CSSProperties = {
      ...MONO, fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
      padding: '3px 8px', borderRadius: 3, cursor: 'pointer',
      border: 'none', outline: 'none',
    }
    if (liveSt === 'starting') {
      // In-flight start — show disabled label
      actionCell = React.createElement('span', {
        style: { ...MONO, fontSize: 9, color: '#8b949e', fontStyle: 'italic' as const }
      }, 'starting…')
    } else if (onBus) {
      // On-bus unit: offer Trip
      const tripping = isPending && _pending.get(u.asset_id) === 'trip'
      actionCell = React.createElement('button', {
        style: {
          ...btnBase,
          background: tripping ? '#3a1a1a' : '#2a1a1a',
          color: tripping ? '#6e7681' : RED,
          borderColor: RED,
          border: `1px solid ${RED}`,
          cursor: tripping ? 'default' : 'pointer',
          opacity: tripping ? 0.6 : 1,
        },
        disabled: tripping,
        title: `Trip ${u.asset_id} — remove from dispatch immediately`,
        onClick: tripping ? undefined : () => _issueUnitCommand(runId, u.asset_id, 'trip'),
      }, tripping ? 'tripping…' : 'Trip')
    } else if (liveSt === 'offline' && !u.hot_standby) {
      // Off-bus OFFLINE non-standby unit: offer Start.
      // hot_standby units are managed by the dispatch arbitrator;
      // command_start() silently ignores them, so we never show Start.
      const starting = isPending && _pending.get(u.asset_id) === 'start'
      actionCell = React.createElement('button', {
        style: {
          ...btnBase,
          background: starting ? '#1a2a1a' : '#142014',
          color: starting ? '#6e7681' : TEAL,
          border: `1px solid ${TEAL}`,
          cursor: starting ? 'default' : 'pointer',
          opacity: starting ? 0.6 : 1,
        },
        disabled: starting,
        title: `Start ${u.asset_id} — enter start sequence and ramp onto bus`,
        onClick: starting ? undefined : () => _issueUnitCommand(runId, u.asset_id, 'start'),
      }, starting ? 'queued…' : 'Start')
    } else {
      // out_of_service or transitional — no operator action available
      actionCell = React.createElement('span', {
        style: { ...MONO, fontSize: 9, color: '#6e7681' }
      }, '—')
    }

    // Gap 1+2 / Gap 5: full-width bar column (≥ 132 px × 16 px) replacing NO-LOAD/MSL.
    // NO-LOAD/MSL column dropped: its data is now expressed by the dashed rule in the
    // bar at mslFrac — showing it twice as a separate text column is redundant.
    // Gap 5: UNLOADING uses ember fill and uid colour so it is visually distinct from
    // a SYNCHRONISED unit at low load, which looks identical at amber/gold.
    const outFrac     = u.rated_mw > 0 ? Math.min(out / u.rated_mw, 1) : 0
    const mslFrac     = u.rated_mw > 0 && u.msl_mw > 0 ? Math.min(u.msl_mw / u.rated_mw, 1) : 0
    const spFrac      = u.rated_mw > 0 && u.setpoint_mw != null ? Math.min(u.setpoint_mw / u.rated_mw, 1) : null
    const countdownS  = u.time_to_online_s != null ? Math.ceil(u.time_to_online_s) : null
    const outLabel    = liveSt === 'starting'
      ? (countdownS != null ? `${countdownS}s` : 'starting…')
      : `${out.toFixed(2)} MW`
    // Gap 5: ember for UNLOADING fill; amber for STARTING; gold otherwise.
    const fillColour  = liveSt === 'unloading' ? EMBER : out > 0.01 ? GOLD : '#6e7681'
    const outColour   = liveSt === 'starting' ? AMBER : fillColour
    const uidColour   = liveSt === 'unloading' ? EMBER : GOLD  // gap 5

    // Bar sub-annotation: tracking progress or stable state label.
    const rampDeltaMW = spFrac != null ? (u.setpoint_mw ?? 0) - out : 0
    const barAnnotation: string | null =
      liveSt === 'starting' ? null
      : spFrac != null && rampDeltaMW > 0.05
        ? `tracking → ${(u.setpoint_mw ?? 0).toFixed(2)} · +${rampDeltaMW.toFixed(2)} MW to go`
        : outFrac >= 0.999
          ? 'at rated · levelled off'
          : (mslFrac > 0 && Math.abs(outFrac - mslFrac) < 0.005)
            ? 'at minimum stable load'
            : null

    // Gap 1+2: full-width bar in its own column.
    //   • Amber/ember fill = output fraction of rated (gap 5: ember when UNLOADING).
    //   • Hatched fill for STARTING (deferred gap 3 — here kept as placeholder fill).
    //   • Teal-shaded region between fill and setpoint = ramp gap (gap 2).
    //   • Dashed rule at mslFrac = MSL; cyan marker at spFrac = setpoint.
    const fullBar = React.createElement('div', null,
      React.createElement('div', {
        style: { position: 'relative' as const, height: 16, background: '#060a0f',
                 border: '1px solid #1a2330', minWidth: 132 },
      },
        // Fill — hatched for STARTING, solid otherwise (gap 5: ember for UNLOADING)
        liveSt === 'starting'
          ? React.createElement('div', {
              style: { position: 'absolute' as const, left: 0, top: 0, bottom: 0,
                       width: `${outFrac * 100}%`,
                       background: 'repeating-linear-gradient(-45deg,#221e3a 0 5px,#171430 5px 10px)' },
            })
          : React.createElement('div', {
              style: { position: 'absolute' as const, left: 0, top: 0, bottom: 0,
                       width: `${outFrac * 100}%`, background: fillColour, opacity: 0.85 },
            }),
        // Gap 2: ramp gap — teal-shaded region from fill to setpoint (closes as unit levels off)
        spFrac != null && spFrac > outFrac + 0.005
          ? React.createElement('div', {
              style: { position: 'absolute' as const, top: 6, height: 3,
                       left: `${outFrac * 100}%`,
                       width: `${(spFrac - outFrac) * 100}%`,
                       background: 'rgba(63,182,168,0.22)' },
            })
          : null,
        // Dashed MSL rule
        mslFrac > 0 ? React.createElement('div', {
          style: { position: 'absolute' as const, left: `${mslFrac * 100}%`,
                   top: -1, bottom: -1, borderLeft: '1px dashed #6b5320' },
        }) : null,
        // Cyan setpoint marker
        spFrac != null ? React.createElement('div', {
          style: { position: 'absolute' as const, left: `${spFrac * 100}%`,
                   top: -3, bottom: -3, width: 2, background: TEAL },
        }) : null,
      ),
      barAnnotation != null
        ? React.createElement('div', {
            style: { ...MONO, fontSize: 9, color: '#5d6b7c', marginTop: 3 }
          }, barAnnotation)
        : null,
    )

    return React.createElement('tr', { key: u.asset_id },
      // Gap 5: ember uid colour for UNLOADING
      React.createElement('td', { style: dCell(uidColour, true) }, u.asset_id),
      // Gap 1+2: full-width bar column (replaces CURRENT MW + NO-LOAD/MSL)
      React.createElement('td', { style: { ...dCell(), minWidth: 140 } }, fullBar),
      // MW value in its own narrow column (bar supplements, does not replace)
      React.createElement('td', { style: dCell(outColour) }, outLabel),
      // 0.2: SYNC driven by isOnBus() — Phase 2 live state preferred, breaker_closed fallback.
      React.createElement('td', { style: dCell(onBus ? GOLD : '#8b949e') }, syncStr),
      React.createElement('td', { style: dCell(isDeg ? AMBER : '#c9d1d9') }, rampStr),
      React.createElement('td', { style: dCell('#8b949e') }, runHStr),
      React.createElement('td', { style: dCell(isDeg ? AMBER : TEAL, true) }, stateStr),
      // Operator action — Trip (on-bus) / Start (offline) / starting… / —
      React.createElement('td', { style: { ...dCell(), paddingRight: 0 } }, actionCell),
    )
  })

  // Per-degraded-unit footnotes (specific to each unit, matching reference).
  const degradedFootnotes = units
    .filter(u => u.r_asset_mw_per_s < 0.95 * maxRamp)
    .map(u => {
      const afterStr = u.run_hours_h != null
        ? ` after ${Math.round(u.run_hours_h).toLocaleString()} h`
        : ''
      return `${u.asset_id} re-rated to ${u.r_asset_mw_per_s.toFixed(3)} MW/s${afterStr}. The reserve check uses the re-rated figure — neither nameplate nor exclusion (§27, TC-58). A raise requires a longer window and confirmation.`
    })

  return React.createElement('div', { style: { overflowX: 'auto' as const } },
    React.createElement('div', {
      style: { ...MONO, fontSize: 9, fontWeight: 700, letterSpacing: '0.1em',
               color: '#8b949e', textTransform: 'uppercase' as const, marginBottom: 8 }
    }, `FLEET — ${unitCountStr}`),
    React.createElement('table', {
      style: { width: '100%', borderCollapse: 'collapse' as const }
    },
      React.createElement('thead', null,
        React.createElement('tr', null,
          React.createElement('th', { style: hCell }, 'UNIT'),
          // Gap 1+2: bar column replaces the old CURRENT MW+minibar and NO-LOAD/MSL columns.
          React.createElement('th', { style: { ...hCell, minWidth: 140 } }, 'Output · setpoint · MSL'),
          React.createElement('th', { style: hCell }, 'MW'),
          React.createElement('th', { style: hCell }, 'SYNC'),
          React.createElement('th', { style: hCell }, 'RAMP meas/cfg'),
          React.createElement('th', { style: hCell }, 'RUN h'),
          React.createElement('th', { style: hCell }, 'STATE'),
          React.createElement('th', { style: hCell }, 'COMMAND'),           // operator Trip/Start
        )
      ),
      React.createElement('tbody', null, ...rows),
    ),
    degradedFootnotes.length > 0 && React.createElement('div', { style: { marginTop: 8 } },
      ...degradedFootnotes.map((note, i) =>
        React.createElement('p', {
          key: i,
          style: { fontFamily: 'Inter,sans-serif', fontSize: 10, color: '#8b949e',
                   lineHeight: 1.5, margin: i > 0 ? '4px 0 0' : '0' }
        }, note)
      )
    ),
  )
}

// ── Paralleling inset ────────────────────────────────────────────────────────
function ParallelingInset(units: TurbineUnitSpec[]): React.ReactNode {
  const genRows = units.map(u =>
    React.createElement('div', {
      key: u.asset_id,
      style: { display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 },
    },
      React.createElement('div', {
        style: {
          width: 26, height: 26, borderRadius: '50%',
          border: `1.5px solid ${GOLD}`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0,
          ...MONO, fontSize: 9, fontWeight: 700, color: GOLD,
        }
      }, 'G'),
      React.createElement('div', {
        style: { ...MONO, fontSize: 9, color: '#8b949e', flexShrink: 0, minWidth: 76 }
      }, u.asset_id),
      React.createElement('div', { style: { flex: 1, display: 'flex', alignItems: 'center', gap: 2 } },
        React.createElement('div', { style: { height: 1.5, flex: 1, background: '#2a3f52', minWidth: 10 } }),
        React.createElement('div', {
          style: {
            width: 16, height: 16, border: '1.5px solid #3a5060', borderRadius: 2,
            display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            ...MONO, fontSize: 7, color: '#8b949e',
          }
        }, 'CB'),
        React.createElement('div', { style: { height: 1.5, flex: 1, background: '#2a3f52', minWidth: 6 } }),
      ),
    )
  )

  return React.createElement('div', {
    style: { borderTop: '1px solid #1e2a36', borderBottom: '1px solid #1e2a36', padding: '12px 0' }
  },
    React.createElement('div', {
      style: { ...MONO, fontSize: 9, fontWeight: 700, letterSpacing: '0.1em',
               color: '#8b949e', textTransform: 'uppercase' as const, marginBottom: 12 }
    }, 'PARALLELING — AC BUS, SYNCHRO-CHECK BEFORE CLOSE'),
    React.createElement('div', {
      style: { display: 'flex', gap: 24, alignItems: 'flex-start', flexWrap: 'wrap' as const }
    },
      React.createElement('div', { style: { minWidth: 240 } },
        ...genRows,
        React.createElement('div', {
          style: { display: 'flex', alignItems: 'center', gap: 8, marginTop: 4, marginLeft: 104 }
        },
          React.createElement('div', { style: { height: 2, flex: 1, background: GOLD, borderRadius: 1 } }),
          React.createElement('div', {
            style: { ...MONO, fontSize: 9, fontWeight: 700, color: GOLD, whiteSpace: 'nowrap' as const }
          }, '13.8 kV BUS'),
          React.createElement('div', {
            style: { ...MONO, fontSize: 9, color: '#8b949e', whiteSpace: 'nowrap' as const }
          }, '▶ switchgear / PMS'),
        ),
      ),
      React.createElement('div', { style: { flex: 1, minWidth: 200 } },
        React.createElement('p', {
          style: { fontFamily: 'Inter,sans-serif', fontSize: 10, color: '#b1bac4', lineHeight: 1.6, margin: 0 }
        }, (() => {
          // 0.2: relay footer reads sync_relay_state — separate from the breaker_closed
          // SYNC column. Phase 0: derived from hot_standby; Phase 1: real-time.
          const checkingN = units.filter(u => u.sync_relay_state === 'checking').length
          return checkingN > 0
            ? `${checkingN} unit${checkingN > 1 ? 's' : ''} in synchro-check sequence — matching voltage, frequency, phase.`
            : 'All units on bus — synchro-check relay at rest.'
        })()),
        React.createElement('p', {
          style: { fontFamily: 'Inter,sans-serif', fontSize: 10, color: RED, lineHeight: 1.6,
                   margin: '4px 0 0', fontWeight: 600 }
        }, 'GridSignal never issues this command — TC-68'),
        React.createElement('p', {
          style: { fontFamily: 'Inter,sans-serif', fontSize: 10, color: '#8b949e', lineHeight: 1.6, margin: '8px 0 0' }
        }, 'Synchronous generators produce AC directly. No rectifier or DC link in this path — unlike the BESS and solar inverters, which are DC-coupled and grid-following.'),
      ),
    ),
  )
}

// ── No-tick panel ────────────────────────────────────────────────────────────
function noTickPanel(peakMW: number | null): PanelData {
  const peakStr = peakMW !== null ? `${peakMW.toFixed(2)} MW` : '—'
  return {
    stateLabel:   '—',
    stateColour:  '#6e7681',
    verdict:      'No active run. Start a scenario to see fleet readiness.',
    heroValue:    '—',
    heroLabel:    'MW firm, N−1',
    chartTitle:   '',
    identityLine: 'gas turbine fleet · synchronous · islanded primary generation',
    chart: React.createElement('div', {
      style: { fontFamily: 'Inter,sans-serif', fontSize: 11, color: '#8b949e',
               padding: '32px 0', textAlign: 'center' as const }
    }, 'No data — start a scenario to populate the fleet table.'),
    statRows: [
      { label: 'Units installed',    value: '—' },
      { label: 'N−1 firm capacity',  value: 'not instrumented' },
      { label: 'Aggregate ramp',     value: 'not instrumented' },
      { label: 'Peak site load',     value: peakStr, sub: 'observed peak this run' },
      { label: 'Start time, cold',   value: '5–10 min', sub: 'a cold unit contributes nothing to a 45 s event' },
    ],
    secondary: undefined,
    why: [
      'N−1 firm capacity is the number that matters — not installed MW. A single-unit site has zero N−1 protection.',
      'Aggregate ramp scales with unit count: three 15 MW units answer a step-load three times faster than one 25 MW unit.',
      'Per-unit ramp re-rating (§27, TC-58) is decisive in a reserve calculation and invisible in an aggregate figure.',
    ],
  }
}

// ── Single-unit panel (AE3 branch 1) ────────────────────────────────────────
// GS-DES-CFG-001 §Phase-6 / Item-4: peakMW = declared design peak; observedPeakMW = run maximum.
// GS-DES-CFG-001 §Phase-7 / Item-2: isDeclaredPeak flag controls labels when wire sends 0.
function singleUnitPanel(tick: TickPayload, units: TurbineUnitSpec[], peakMW: number, observedPeakMW: number): PanelData {
  const u          = units[0]
  const isDeclaredPeak = tick.design_peak_load_mw > 0
  // Algebraic: use on_bus_output_mw (Σ_{i∈A} p_i) for active-state check
  // and for the FleetTable aggregate — not turbine_output_mw.
  const syncedCount = tick.units_on_bus_count
  const syncedMW    = tick.on_bus_output_mw
  const stateLabel  = syncedCount > 0 ? 'ACTIVE' : 'READY'
  // Task #198 item 3: use runtime lead horizon from the dispatch arbitrator.
  // When dt_lead_next_s is 0 (no active step) the ramp figure is also 0.
  const horizonS    = tick.dt_lead_next_s ?? 0
  // 0.5: ramp energy bounded at rated_mw for single unit
  const rampEnergy  = Math.min(u.r_asset_mw_per_s * horizonS, u.rated_mw)

  const thermalState = _thermalOf(u)
  const thermalLabel = thermalState.charAt(0).toUpperCase() + thermalState.slice(1)
  const chart = React.createElement(React.Fragment, null,
    FleetTable(units, syncedMW, u.r_asset_mw_per_s, syncedCount, tick.run_id),
    React.createElement(ThermalStateWidget, {
      units: [{ asset_id: u.asset_id, thermal: thermalState, ratedMW: u.rated_mw, rampMWs: u.r_asset_mw_per_s }],
    }),
  )

  const secondary = React.createElement('div', { className: 'space-y-3' },
    // Red N−1=0 warning
    React.createElement('div', {
      style: {
        borderRadius: 6, border: `1px solid ${RED}`,
        background: '#1a0e0e', padding: '10px 14px',
        fontFamily: 'Inter,sans-serif', fontSize: 11, color: RED, lineHeight: 1.6,
      }
    },
      React.createElement('span', { style: { fontWeight: 700 } }, 'N−1 firm 0.0 MW — '),
      'a unit loss takes the site down after the battery empties.',
    ),
    ParallelingInset(units),
  )

  return {
    stateLabel,
    stateColour:  TEAL,
    verdict:      `Single-unit site — N−1 firm capacity 0.0 MW. A unit loss leaves BESS bridge only (~20 min).`,
    heroValue:    (tick.on_bus_output_mw ?? 0).toFixed(2),
    heroLabel:    'MW output',
    chartTitle:   '',
    // 0.1: derived from typed fields — count, rating, gt_mode
    identityLine: _identityLine(units),
    chart,
    statRows: [
      { label: 'Units installed',    value: '1',                                  sub: `${u.rated_mw.toFixed(0)} MW · ${u.asset_id}` },
      // 0.3: count from named field; MW from on_bus_output_mw (same filtered set)
      { label: 'Units on bus', value: `${syncedCount}`,
        colour: syncedCount > 0 ? GOLD : undefined,
        sub: syncedCount > 0 ? `contributing ${syncedMW.toFixed(2)} MW` : 'none on bus' },
      { label: 'N−1 firm capacity',  value: '0.0 MW',                             colour: RED, sub: 'single unit — no redundancy' },
      // GS-DES-CFG-001 §Phase-7 / Item-2: conditional on design_peak_load_mw > 0 on wire.
      ...(isDeclaredPeak ? [
        { label: 'Design peak load', value: peakMW > 0 ? `${peakMW.toFixed(2)} MW` : '—', sub: 'declared at scenario design point' },
        { label: 'Observed peak',    value: observedPeakMW > 0 ? `${observedPeakMW.toFixed(2)} MW` : 'no peak yet', sub: 'observed this run' },
      ] as const : [
        { label: 'Observed peak',    value: observedPeakMW > 0 ? `${observedPeakMW.toFixed(2)} MW` : 'no peak yet', sub: 'observed this run (design peak not broadcast)' },
      ] as const),
      { label: 'N−1 margin',         value: 'none',                               colour: RED },
      // 0.5: ramp energy bounded at rated_mw — integral is not unbounded
      { label: 'Ramp (configured)',  value: `${u.r_asset_mw_per_s.toFixed(3)} MW/s`,
        sub: horizonS > 0
          ? `${rampEnergy.toFixed(1)} MW in ${horizonS.toFixed(0)} s (bounded at ${u.rated_mw.toFixed(0)} MW rated)`
          : `${u.rated_mw.toFixed(0)} MW rated — no active ramp event` },
      { label: 'Rated output',       value: `${u.rated_mw.toFixed(1)} MW`,        sub: 'nameplate' },
      { label: 'Thermal state',      value: thermalLabel,                          colour: THERMAL_COLOUR[thermalState], sub: _thermalSub(thermalState) },
    ],
    secondary,
    why: [
      `Installed capacity is not the number that matters — N−1 firm capacity is. A single ${u.rated_mw.toFixed(0)} MW unit has zero N−1 firm capacity.`,
      'A unit loss takes the site down after the battery empties: ~20 minutes of BESS bridge, then dark. This would not survive a customer reliability review.',
      'To achieve N−1 protection, replace this unit with a fleet of two or more units — N−1 firm capacity = (N−1) × unit_rated_mw.',
    ],
  }
}

// ── Fleet panel (AE3 branch 2) — N > 1 units ────────────────────────────────
// GS-DES-CFG-001 §Phase-6 / Item-4: peakMW = declared design peak; observedPeakMW = run maximum.
// GS-DES-CFG-001 §Phase-7 / Item-2: isDeclaredPeak/peakLabel controls labels when wire sends 0.
function fleetPanel(tick: TickPayload, units: TurbineUnitSpec[], peakMW: number, observedPeakMW: number): PanelData {
  // Algebraic: on_bus_output_mw = Σ_{i∈A} p_i where A = {synchronised, unloading}.
  // Phase C D-05: renamed from units_synchronised_count / synchronised_output_mw.
  const onlineN  = tick.units_on_bus_count
  const syncedMW = tick.on_bus_output_mw

  // Task #198 item 3: runtime lead horizon from the dispatch arbitrator.
  const horizonS = tick.dt_lead_next_s ?? 0

  const {
    installedMW, maxUnitMW, n1FirmMW,
    rampNeedMWs, n1MarginPct, onBusMW, maxOnBusMW, onBusCount,
  } = deriveFleet(units, horizonS, peakMW)

  const maxRamp     = units.length > 0 ? Math.max(...units.map(u => u.r_asset_mw_per_s)) : 0
  const n1Covers       = n1FirmMW >= peakMW
  const isDeclaredPeak = tick.design_peak_load_mw > 0
  const peakLabel      = isDeclaredPeak ? 'declared design peak' : 'observed peak'

  // U-2 fix: ramp_capability_mw is authoritative; fallback removed.
  // (U-1 fix: aggRampMWs was counting all units at fleet-max rate — deleted.)
  const rampEnergyMW = tick.ramp_capability_mw ?? 0
  // Rate in MW/s derived from energy figure — consistent with how backend computes it.
  const rampRateMWs  = horizonS > 0 ? rampEnergyMW / horizonS : 0
  // U-2 fix: rampCovers now compares energy to peak (same units).
  const rampCovers  = horizonS <= 0 || rampEnergyMW >= peakMW
  const stateLabel  = n1Covers && rampCovers ? 'READY' : 'ATTENTION'
  const stateColour = n1Covers && rampCovers ? TEAL : AMBER

  const marginStr    = n1MarginPct >= 0 ? `+${n1MarginPct}%` : `${n1MarginPct}%`
  const marginColour = n1MarginPct >= 0 ? TEAL : RED

  // U-3 fix: divisor counts on-bus units only (OFFLINE/STARTING contribute 0 to ramp).
  // Clamp to headroom (rated_mw − output_mw), not nameplate — a unit at 12 MW on a
  // 15 MW machine can contribute at most 3 MW more, whatever the horizon.
  const _onBusForRamp = units.filter(isOnBus)
  const _onBusCntRamp = Math.max(_onBusForRamp.length, 1)
  const _maxHeadroom  = _onBusForRamp.length > 0
    ? Math.max(..._onBusForRamp.map(u => u.rated_mw - (u.output_mw ?? 0)))
    : 0
  const _perUnitRamp  = rampEnergyMW / _onBusCntRamp
  const rampWith1MW   = Math.min(_perUnitRamp, _maxHeadroom)
  const rampWith1Rate = horizonS > 0 ? rampWith1MW / horizonS : 0

  // U-5: cold-start time from per-unit spec; fallback to CHOSEN catalogue default.
  // hot_start_s and warm_start_s are passed through thermalUnits for ThermalStateWidget.
  const coldS = units[0]?.cold_start_s ?? 900

  const offlineUnits = units.filter(u => !isOnBus(u))
  const thermalUnits = offlineUnits.map(u => ({
    asset_id: u.asset_id, thermal: _thermalOf(u),
    ratedMW: u.rated_mw, rampMWs: u.r_asset_mw_per_s,
    hotStartS:  u.hot_start_s  ?? 300,
    warmStartS: u.warm_start_s ?? 300,
    coldStartS: u.cold_start_s ?? 900,
  }))
  const chart = thermalUnits.length > 0
    ? React.createElement(React.Fragment, null,
        FleetTable(units, syncedMW, maxRamp, onlineN, tick.run_id),
        React.createElement(ThermalStateWidget, { units: thermalUnits }),
      )
    : FleetTable(units, syncedMW, maxRamp, onlineN, tick.run_id)

  const secondary = React.createElement('div', { className: 'space-y-3' },
    React.createElement(BulletBar, {
      label:  'N−1 firm capacity against peak site load',
      // U-4 fix: n1FirmMW is now from committed (on-bus) units only.
      value:  n1FirmMW,
      max:    installedMW,
      target: peakMW > 0 ? peakMW : undefined,
      colour: n1Covers ? GOLD : RED,
      unit:   ' MW',
      // GS-DES-CFG-001 §Phase-7 / Item-2: label reflects broadcast source.
      note:   peakMW > 0
        ? `red marker = ${peakMW.toFixed(2)} MW ${peakLabel}  ·  ${marginStr} margin with any one unit out`
        : `N−1 firm ${n1FirmMW.toFixed(1)} MW  ·  ${marginStr} margin (no peak available)`,
    }),
    React.createElement(BulletBar, {
      // U-2 fix: value from backend energy; rate derived consistently.
      label:  'Aggregate ramp capability (SYNCHRONISED only)',
      value:  rampRateMWs,
      max:    Math.max(rampRateMWs * 1.5 || 1, rampNeedMWs * 1.5 || 1),
      target: rampNeedMWs,
      colour: rampCovers ? GOLD : RED,
      unit:   ' MW/s',
      note:   horizonS > 0
        ? `backend: ${rampEnergyMW.toFixed(1)} MW over ${horizonS.toFixed(0)} s  ·  red marker = ${rampNeedMWs.toFixed(3)} MW/s to cover ${peakMW > 0 ? peakMW.toFixed(2) : '—'} MW ${peakLabel}`
        : `${rampEnergyMW.toFixed(1)} MW capability — no active ramp event`,
    }),
    ParallelingInset(units),
  )

  // Commitment block — null on legacy payloads without Phase E+ backend.
  const cb = (tick as any).commitment_block as {
    action: string; target_unit_id: string | null; reason: string; blocked_by: string
    committed_rated_mw: number; reserve_floor_mw: number; reserve_satisfied: boolean
    utilisation: number; pending_start_unit_id: string | null
  } | null | undefined

  return {
    stateLabel,
    stateColour,
    // GS-DES-CFG-001 §Phase-7 / Item-2: label reflects broadcast source.
    verdict: peakMW > 0
      ? (n1Covers
          ? `N−1 firm capacity ${n1FirmMW.toFixed(1)} MW covers the ${peakMW.toFixed(2)} MW ${peakLabel} with ${marginStr} margin.`
          : `N−1 firm capacity ${n1FirmMW.toFixed(1)} MW is below the ${peakMW.toFixed(2)} MW ${peakLabel} — site cannot survive a unit loss.`)
      : `N−1 firm capacity ${n1FirmMW.toFixed(1)} MW (no peak available).`,
    heroValue:   (tick.on_bus_output_mw ?? 0).toFixed(2),
    heroLabel:   'MW output',
    chartTitle:  '',
    // 0.1: derived from typed fields — count, rating, gt_mode
    identityLine: _identityLine(units),
    chart,
    statRows: [
      { label: 'Units installed',    value: `${units.length}`,               sub: `${maxUnitMW.toFixed(0)} MW each · ${installedMW.toFixed(0)} MW total` },
      // 0.3: both values from the same filtered set via named tick fields
      { label: 'Units on bus', value: `${onlineN}`,
        sub: onlineN > 0 ? `contributing ${syncedMW.toFixed(2)} MW` : 'none on bus',
        colour: onlineN > 0 ? GOLD : undefined },
      // U-4 fix: N−1 firm uses committed (on-bus) units, not all installed.
      { label: 'N−1 firm capacity',  value: `${n1FirmMW.toFixed(1)} MW`,    colour: n1Covers ? GOLD : RED, sub: 'with any one committed unit unavailable' },
      // GS-DES-CFG-001 §Phase-7 / Item-2: conditional on design_peak_load_mw > 0 on wire.
      ...(isDeclaredPeak ? [
        { label: 'Design peak load', value: peakMW > 0 ? `${peakMW.toFixed(2)} MW` : '—', sub: 'declared at scenario design point' },
        { label: 'Observed peak',    value: observedPeakMW > 0 ? `${observedPeakMW.toFixed(2)} MW` : 'no peak yet', sub: 'observed this run' },
      ] as const : [
        { label: 'Observed peak',    value: observedPeakMW > 0 ? `${observedPeakMW.toFixed(2)} MW` : 'no peak yet', sub: 'observed this run (design peak not broadcast)' },
      ] as const),
      // U-4 fix: N-1 margin uses on-bus arithmetic, not installed-capacity arithmetic.
      { label: 'N−1 margin',         value: marginStr,                        colour: marginColour,
        sub: `${onBusMW.toFixed(0)} MW committed − ${maxOnBusMW.toFixed(0)} MW contingency = ${n1FirmMW.toFixed(0)} MW firm${peakMW > 0 ? `  ·  ${peakLabel} ${peakMW.toFixed(2)} MW` : ''}` },
      // U-2 fix: energy figure from backend (authoritative); rate derived.
      { label: 'Aggregate ramp',     value: `${rampEnergyMW.toFixed(1)} MW`, colour: rampCovers ? GOLD : RED,
        sub: horizonS > 0
          ? `${rampRateMWs.toFixed(3)} MW/s over ${horizonS.toFixed(0)} s horizon (SYNCHRONISED only — starts excluded)`
          : `${rampRateMWs.toFixed(3)} MW/s — no active ramp event` },
      // U-3 fix: energy per on-bus unit, clamped to headroom (not nameplate).
      { label: 'Ramp with 1 unit',   value: `${rampWith1MW.toFixed(1)} MW`,
        sub: horizonS > 0
          ? `${rampWith1Rate.toFixed(3)} MW/s · clamped to ${_maxHeadroom.toFixed(1)} MW headroom — BESS covers the remainder`
          : 'no active ramp event' },
      // U-5 fix: cold-start time derived from per-unit spec, not hardcoded.
      { label: 'Cold-start sync',    value: `${coldS} s (${Math.round(coldS/60)} min)`,  sub: 'STARTING units contribute 0 to ramp reserve · see thermal guide' },
      // Item 7: commitment engine summary rows — present when commitment block is on wire.
      ...(cb ? [
        { label: 'Committed MW',
          value: `${cb.committed_rated_mw.toFixed(1)} MW`,
          colour: cb.reserve_satisfied ? GOLD : RED,
          sub: `${Math.round(cb.utilisation * 100)}% utilisation · ${cb.reserve_satisfied ? 'floor met' : 'floor violated'}` },
        // Gap 7: dedicated reserve floor row — arithmetic explicit in sub-label so operator
        // can see why a commit fired below the utilisation threshold (floor governs).
        { label: 'Reserve floor',
          value: `${cb.reserve_floor_mw.toFixed(1)} MW`,
          colour: cb.reserve_satisfied ? GOLD : RED,
          sub: cb.reserve_satisfied
            ? `${(cb.committed_rated_mw - cb.reserve_floor_mw).toFixed(1)} MW margin · demand + largest committed unit`
            : `short ${(cb.reserve_floor_mw - cb.committed_rated_mw).toFixed(1)} MW · demand + largest committed unit` },
        // Gap 9: blocked_by and reason rendered as separate rows so an operator can see
        // BOTH why the fleet is constrained AND what the engine last decided.
        // Previously blocked_by hid reason — a constrained fleet looked the same as a
        // satisfied one because the decision reason was suppressed.
        ...(cb.blocked_by ? [{ label: 'Blocked', value: cb.blocked_by, colour: '#7b6bb0',
          sub: 'further commitment held' }] : []),
        { label: 'Last decision',
          value: cb.action.toUpperCase(),
          colour: cb.action === 'commit' ? TEAL : cb.action === 'decommit' ? AMBER : undefined,
          sub: cb.reason || 'no active condition' },
        ...(cb.pending_start_unit_id ? [{
          label: 'Starting',
          value: cb.pending_start_unit_id,
          colour: AMBER,
          sub: 'in start sequence — not counted toward committed capacity or ramp',
        }] : []),
      ] as const : []),
    ],
    secondary,
    why: [
      `N−1 firm capacity is what matters, not installed capacity. ${onBusCount} committed units give ${n1FirmMW.toFixed(1)} MW firm (${onBusMW.toFixed(0)} MW committed − ${maxOnBusMW.toFixed(0)} MW contingency)${peakMW > 0 ? ` against a ${peakMW.toFixed(2)} MW ${peakLabel}` : ''}.`,
      `Ramp capability is reported by the backend loading layer at the runtime lead horizon (${horizonS.toFixed(0)} s). Starts and offline units contribute zero — the figure is already from SYNCHRONISED units only.`,
      'Degraded = effective ramp below 95% of fleet maximum. The reserve check uses the effective figure (§27, TC-58) — a quietly degraded unit is decisive in a reserve calculation.',
    ],
  }
}

// ── Panel config ─────────────────────────────────────────────────────────────
export const turbineFleetPanel: PanelConfig = {
  deriveData(tick: TickPayload | null, _alert: TickPayload | null, history: HistoryPoint[]): PanelData {
    // GS-DES-CFG-001 §Phase-3: derive peak load from run history (not hardcoded).
    const peakMW = peakSiteLoadMW(history) ?? 0
    // GS-DES-CFG-001 §Phase-6 / Item-4: declared design peak for N−1 / ramp checks.
    // peakMW (observed run maximum) is kept for display alongside the declared figure.
    // Falls back to observed peak when design_peak_load_mw is not yet broadcast (0).

    if (!tick) return noTickPanel(peakMW > 0 ? peakMW : null)
    const designPeakMW = (tick.design_peak_load_mw ?? 0) > 0 ? tick.design_peak_load_mw! : peakMW

    const units = tick.turbine_units ?? []

    if (units.length === 0) {
      return {
        ...noTickPanel(peakMW > 0 ? peakMW : null),
        stateLabel: '—',
        verdict: 'No turbine units found in this scenario spec.',
      }
    }

    if (units.length === 1) return singleUnitPanel(tick, units, designPeakMW, peakMW)

    return fleetPanel(tick, units, designPeakMW, peakMW)
  },
}
