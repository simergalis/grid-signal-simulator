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
 *       FLEET header derives on-bus count from units_synchronised_count.
 *   0.3 Units synchronised count from tick.units_synchronised_count;
 *       contributing MW from tick.synchronised_output_mw — same filtered set.
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

// ── Colour constants ─────────────────────────────────────────────────────────
const GOLD  = '#e0a458'
const TEAL  = '#3fb6a8'
const RED   = '#f85149'
const AMBER = '#f0883e'

// Site constant — matches demo-20mw / demo-3turbine (1 900-node, PUE 1.03).
// compute 19.96 + cooling 3.99 = 23.95 MW.
const PEAK_LOAD_MW = 23.95
// No LEAD_WINDOW_S constant — Task #198 item 3.
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
  { state: 'hot',  label: 'Hot',  cond: 'Off < 1 hour',                syncTime: '60 s (1 min)'   },
  { state: 'warm', label: 'Warm', cond: 'Off 1–4 hours',                syncTime: '300 s (5 min)'  },
  { state: 'cold', label: 'Cold', cond: 'Off > 4 hours, or never run',  syncTime: '900 s (15 min)' },
] as const

// Derive thermal state from unit spec; fallback to 'cold' when field absent.
function _thermalOf(u: TurbineUnitSpec): string {
  return (u.thermal_state as string | null | undefined) ?? 'cold'
}

// Stat-row subtitle for the current thermal state — accurate start time.
function _thermalSub(state: string): string {
  if (state === 'hot')  return '60 s (1 min) to sync — recently stopped'
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
function deriveFleet(units: TurbineUnitSpec[], horizonS: number) {
  const installedMW   = units.reduce((s, u) => s + u.rated_mw, 0)
  const maxUnitMW     = Math.max(...units.map(u => u.rated_mw))
  const n1FirmMW      = installedMW - maxUnitMW        // worst-case: losing largest
  const maxRamp       = Math.max(...units.map(u => u.r_asset_mw_per_s))
  // Nominal aggregate ramp = fleet-max ramp × unit count.
  // Displays the fleet's nameplate capability; the degraded-unit footnote in
  // FleetTable records which units are running below max and by how much.
  const aggRampMWs    = maxRamp * units.length
  // rampNeedMWs: MW/s needed to cover peak load in the runtime lead window.
  // 0 when no step is in-flight (horizonS = 0) — no active requirement to display.
  const rampNeedMWs   = horizonS > 0 ? PEAK_LOAD_MW / horizonS : 0
  const n1MarginPct   = n1FirmMW > 0
    ? Math.round((n1FirmMW - PEAK_LOAD_MW) / PEAK_LOAD_MW * 100)
    : -100
  return { installedMW, maxUnitMW, n1FirmMW, aggRampMWs, rampNeedMWs, n1MarginPct, maxRamp }
}

// ── On-bus determination ─────────────────────────────────────────────────────
// Algebraic formula: unit i ∈ A ⟺ state_i == 'synchronised' (not hot_standby).
// A is the allocated set managed by the loading layer.  RAMPING / AT_TARGET are
// legacy pre-staging states whose output accumulates via advance(); they are NOT
// in A and are NOT considered on-bus from the operator perspective.
// Phase 0 fallback: static breaker_closed from spec (absent state field).
function isOnBus(u: TurbineUnitSpec): boolean {
  if (u.state !== undefined) {
    return u.state === 'synchronised'
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
// syncedCount: from tick.units_synchronised_count — never derived from output.
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
    const syncStr  = onBus ? 'closed' : 'open'
    const rampStr  = `${u.r_asset_mw_per_s.toFixed(3)} / ${maxRamp.toFixed(3)}`
    const runHStr  = u.run_hours_h != null
      ? Math.round(u.run_hours_h).toLocaleString()
      : '—'
    // 0.6: no_load_mw and msl_mw from named typed fields — resolves column ambiguity
    const noLoadMslStr = `${u.no_load_mw.toFixed(2)} / ${u.msl_mw.toFixed(2)}`

    // ── Operator action button ────────────────────────────────────────────
    // State machine: on-bus → Trip button; OFFLINE → Start button; STARTING → disabled.
    // Pending: command was issued but the next tick hasn't confirmed state change yet.
    // Clear pending when the state we commanded has been reached (tick confirms it).
    const liveSt   = u.state ?? (onBus ? 'synchronised' : 'offline')
    // State label derived from live TurbineState (dynamic variable, not hardcoded).
    // 'synchronised' → 'online'   (loading layer managing output: on bus, in A)
    // 'ramping'      → 'ramping'  (auto-staged via advance(); NOT yet in A)
    // 'at_target'    → 'ramping'  (legacy alias; same as ramping — not in A)
    // 'starting'     → 'starting' (command_start() sequence in progress)
    // otherwise      → 'degraded' | 'available' (offline / out_of_service)
    const stateStr =
      liveSt === 'synchronised'
        ? (isDeg ? 'degraded' : 'online')
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

    return React.createElement('tr', { key: u.asset_id },
      React.createElement('td', { style: dCell(GOLD, true) }, u.asset_id),
      // 0.6: column labelled CURRENT MW — distinct from no-load and MSL.
      // Non-zero only for on-bus units; off-bus units show 0.00 MW (isOnBus fix).
      React.createElement('td', { style: dCell(out > 0.01 ? GOLD : '#6e7681') }, `${out.toFixed(2)} MW`),
      // 0.6: explicit NO-LOAD / MSL column from named typed fields
      React.createElement('td', { style: dCell('#8b949e') }, noLoadMslStr),
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
          React.createElement('th', { style: hCell }, 'CURRENT MW'),        // 0.6: labelled
          React.createElement('th', { style: hCell }, 'NO-LOAD / MSL MW'), // 0.6: new column
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
function noTickPanel(): PanelData {
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
      { label: 'Peak site load',     value: `${PEAK_LOAD_MW.toFixed(2)} MW`, sub: 'compute 19.96 + cooling 3.99' },
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
function singleUnitPanel(tick: TickPayload, units: TurbineUnitSpec[]): PanelData {
  const u          = units[0]
  // Algebraic: use synchronised_output_mw (Σ_{i∈A} p_i) for active-state check
  // and for the FleetTable aggregate — not turbine_output_mw (includes RAMPING path).
  const syncedCount = tick.units_synchronised_count
  const syncedMW    = tick.synchronised_output_mw
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
    heroValue:    (tick.turbine_output_mw ?? 0).toFixed(2),
    heroLabel:    'MW output',
    chartTitle:   '',
    // 0.1: derived from typed fields — count, rating, gt_mode
    identityLine: _identityLine(units),
    chart,
    statRows: [
      { label: 'Units installed',    value: '1',                                  sub: `${u.rated_mw.toFixed(0)} MW · ${u.asset_id}` },
      // 0.3: count from named field; MW from synchronised_output_mw (same filtered set)
      { label: 'Units synchronised', value: `${syncedCount}`,
        colour: syncedCount > 0 ? GOLD : undefined,
        sub: syncedCount > 0 ? `contributing ${syncedMW.toFixed(2)} MW` : 'none on bus' },
      { label: 'N−1 firm capacity',  value: '0.0 MW',                             colour: RED, sub: 'single unit — no redundancy' },
      { label: 'Peak site load',     value: `${PEAK_LOAD_MW.toFixed(2)} MW`,      sub: 'compute 19.96 + cooling 3.99' },
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
function fleetPanel(tick: TickPayload, units: TurbineUnitSpec[]): PanelData {
  // Algebraic: synchronised_output_mw = Σ_{i∈A} p_i (loading-layer-managed only).
  // turbine_output_mw includes auto-staged RAMPING turbines; those are not in A.
  const onlineN  = tick.units_synchronised_count
  const syncedMW = tick.synchronised_output_mw

  // Task #198 item 3: runtime lead horizon from the dispatch arbitrator.
  const horizonS = tick.dt_lead_next_s ?? 0

  const {
    installedMW, maxUnitMW, n1FirmMW, aggRampMWs,
    rampNeedMWs, n1MarginPct, maxRamp,
  } = deriveFleet(units, horizonS)

  const n1Covers    = n1FirmMW >= PEAK_LOAD_MW
  const rampCovers  = aggRampMWs >= rampNeedMWs
  const stateLabel  = n1Covers && rampCovers ? 'READY' : 'ATTENTION'
  const stateColour = n1Covers && rampCovers ? TEAL : AMBER

  const marginStr    = n1MarginPct >= 0 ? `+${n1MarginPct}%` : `${n1MarginPct}%`
  const marginColour = n1MarginPct >= 0 ? TEAL : RED

  // Phase 1b + Task #198 item 3: ramp_capability_mw is the sole authoritative source.
  // It is computed by the backend at the runtime lead horizon (dt_lead_next_s).
  // STARTING units contribute zero (item 2 — not on bus; starts fail).
  // The Phase 0.5 display-level cap and LEAD_WINDOW_S constant have been removed.
  const rampEnergyMW = tick.ramp_capability_mw ?? (aggRampMWs * horizonS)

  const offlineUnits = units.filter(u => !isOnBus(u))
  const thermalUnits = offlineUnits.map(u => ({
    asset_id: u.asset_id, thermal: _thermalOf(u),
    ratedMW: u.rated_mw, rampMWs: u.r_asset_mw_per_s,
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
      value:  n1FirmMW,
      max:    installedMW,
      target: PEAK_LOAD_MW,
      colour: n1Covers ? GOLD : RED,
      unit:   ' MW',
      note:   `red marker = ${PEAK_LOAD_MW.toFixed(2)} MW peak load  ·  ${marginStr} margin with any one unit out`,
    }),
    React.createElement(BulletBar, {
      label:  'Aggregate ramp with all units online',
      value:  aggRampMWs,
      max:    Math.max(aggRampMWs * 1.5, rampNeedMWs * 1.5 || aggRampMWs * 1.5),
      target: rampNeedMWs,
      colour: rampCovers ? GOLD : RED,
      unit:   ' MW/s',
      note:   horizonS > 0
        ? `red marker = ${rampNeedMWs.toFixed(3)} MW/s to cover ${PEAK_LOAD_MW.toFixed(2)} MW step in ${horizonS.toFixed(0)} s  ·  ramp scales with unit count`
        : `no active ramp event — dt_lead_next_s = 0  ·  ramp scales with unit count`,
    }),
    ParallelingInset(units),
  )

  const rampWith1 = units.length > 0
    ? (aggRampMWs / units.length).toFixed(3)
    : '—'

  return {
    stateLabel,
    stateColour,
    verdict: n1Covers
      ? `N−1 firm capacity ${n1FirmMW.toFixed(1)} MW covers the ${PEAK_LOAD_MW.toFixed(2)} MW peak with ${marginStr} margin.`
      : `N−1 firm capacity ${n1FirmMW.toFixed(1)} MW is below the ${PEAK_LOAD_MW.toFixed(2)} MW peak — site cannot survive a unit loss.`,
    heroValue:   (tick.turbine_output_mw ?? 0).toFixed(2),
    heroLabel:   'MW output',
    chartTitle:  '',
    // 0.1: derived from typed fields — count, rating, gt_mode
    identityLine: _identityLine(units),
    chart,
    statRows: [
      { label: 'Units installed',    value: `${units.length}`,               sub: `${maxUnitMW.toFixed(0)} MW each · ${installedMW.toFixed(0)} MW total` },
      // 0.3: both values from the same filtered set via named tick fields
      { label: 'Units synchronised', value: `${onlineN}`,
        sub: onlineN > 0 ? `contributing ${syncedMW.toFixed(2)} MW` : 'none on bus',
        colour: onlineN > 0 ? GOLD : undefined },
      { label: 'N−1 firm capacity',  value: `${n1FirmMW.toFixed(1)} MW`,    colour: n1Covers ? GOLD : RED, sub: 'with any one unit unavailable' },
      { label: 'Peak site load',     value: `${PEAK_LOAD_MW.toFixed(2)} MW`, sub: 'compute 19.96 + cooling 3.99' },
      // 0.4: subtitle states the arithmetic — not a raw unit count
      { label: 'N−1 margin',         value: marginStr,                        colour: marginColour,
        sub: `${installedMW.toFixed(0)} MW − ${maxUnitMW.toFixed(0)} MW contingency = ${n1FirmMW.toFixed(0)} MW firm  ·  peak ${PEAK_LOAD_MW.toFixed(2)} MW` },
      // Phase 1b + Task #198 item 3: backend ramp_capability_mw at runtime horizon
      { label: 'Aggregate ramp',     value: `${aggRampMWs.toFixed(3)} MW/s`, colour: rampCovers ? GOLD : RED,
        sub: horizonS > 0
          ? `${rampEnergyMW.toFixed(1)} MW capability in ${horizonS.toFixed(0)} s (SYNCHRONISED only — starts excluded)`
          : `${rampEnergyMW.toFixed(1)} MW capability — no active ramp event` },
      { label: 'Ramp with 1 unit',   value: `${rampWith1} MW/s`,
        sub: horizonS > 0
          ? `${(parseFloat(rampWith1) * horizonS).toFixed(0)} MW in ${horizonS.toFixed(0)} s — BESS covers the remainder`
          : 'no active ramp event' },
      { label: 'Cold-start sync',    value: '900 s (15 min)',                  sub: 'STARTING units contribute 0 to ramp reserve · see thermal guide' },
    ],
    secondary,
    why: [
      `Installed capacity is not the number that matters — N−1 firm capacity is. ${units.length} × ${maxUnitMW.toFixed(0)} MW gives ${n1FirmMW.toFixed(1)} MW firm against a ${PEAK_LOAD_MW.toFixed(2)} MW peak.`,
      `Aggregate ramp scales with unit count, not megawatts: ${units.length} units deliver ${aggRampMWs.toFixed(3)} MW/s — ${units.length}× the rate of a single equivalent unit.`,
      'Degraded = effective ramp below 95% of fleet maximum. The reserve check uses the effective figure (§27, TC-58) — a quietly degraded unit is decisive in a reserve calculation.',
    ],
  }
}

// ── Panel config ─────────────────────────────────────────────────────────────
export const turbineFleetPanel: PanelConfig = {
  deriveData(tick: TickPayload | null, _alert: TickPayload | null, _history: HistoryPoint[]): PanelData {
    if (!tick) return noTickPanel()

    const units = tick.turbine_units ?? []

    if (units.length === 0) {
      return {
        ...noTickPanel(),
        stateLabel: '—',
        verdict: 'No turbine units found in this scenario spec.',
      }
    }

    if (units.length === 1) return singleUnitPanel(tick, units)

    return fleetPanel(tick, units)
  },
}
