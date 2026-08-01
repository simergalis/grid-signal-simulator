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
 */

import React from 'react'
import type { PanelConfig, PanelData } from './index'
import type { TickPayload, HistoryPoint, TurbineUnitSpec } from '../../types'
import { BulletBar } from '../../charts/BulletBar'

// ── Colour constants ────────────────────────────────────────────────────────
const GOLD  = '#e0a458'
const TEAL  = '#3fb6a8'
const RED   = '#f85149'
const AMBER = '#f0883e'

// Site constants that come from the scenario config, not the turbine spec.
// PEAK_LOAD_MW matches demo-20mw / demo-3turbine (1,900-node, PUE 1.03).
const PEAK_LOAD_MW    = 23.95
const LEAD_WINDOW_S   = 45.0   // §21 ramp window — matches dt_lead default

const MONO: React.CSSProperties = {
  fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace",
}

// ── Derived fleet metrics from a unit list ──────────────────────────────────
function deriveFleet(units: TurbineUnitSpec[]) {
  const installedMW   = units.reduce((s, u) => s + u.rated_mw, 0)
  const maxUnitMW     = Math.max(...units.map(u => u.rated_mw))
  const n1FirmMW      = installedMW - maxUnitMW        // worst-case: losing largest
  const maxRamp       = Math.max(...units.map(u => u.r_asset_mw_per_s))
  // Nominal aggregate ramp = fleet-max ramp × unit count.
  // Displays the fleet's nameplate capability; the degraded-unit footnote in
  // FleetTable records which units are running below max and by how much.
  // Using the sum of effective ramps (0.560 for a 3-unit fleet with one unit
  // re-rated to 0.16) would conflate a fleet-level headline with a unit-level
  // detail that belongs in the footnote.
  const aggRampMWs    = maxRamp * units.length
  const rampNeedMWs   = PEAK_LOAD_MW / LEAD_WINDOW_S   // MW/s to cover peak in window
  const n1MarginPct   = n1FirmMW > 0
    ? Math.round((n1FirmMW - PEAK_LOAD_MW) / PEAK_LOAD_MW * 100)
    : -100
  return { installedMW, maxUnitMW, n1FirmMW, aggRampMWs, rampNeedMWs, n1MarginPct, maxRamp }
}

// ── Per-unit table ──────────────────────────────────────────────────────────
function FleetTable(
  units: TurbineUnitSpec[],
  aggregateOutputMW: number,
  maxRamp: number,
): React.ReactNode {
  // Distribute aggregate output proportionally by rated_mw.
  const totalRated = units.reduce((s, u) => s + u.rated_mw, 0) || 1
  const unitOutputs = units.map(u => aggregateOutputMW * (u.rated_mw / totalRated))

  const hCell: React.CSSProperties = {
    ...MONO, fontSize: 9, fontWeight: 700,
    letterSpacing: '0.1em', color: '#4b5764',
    padding: '0 10px 6px 0', textTransform: 'uppercase' as const,
    borderBottom: '1px solid #1e2a36', whiteSpace: 'nowrap' as const,
  }
  const dCell = (colour?: string, bold?: boolean): React.CSSProperties => ({
    ...MONO, fontSize: 10,
    color: colour ?? '#8b949e', fontWeight: bold ? 600 : 400,
    padding: '5px 10px 5px 0', borderBottom: '1px solid #111821',
    whiteSpace: 'nowrap' as const,
  })

  const rows = units.map((u, i) => {
    const out      = unitOutputs[i]
    const isDeg    = u.r_asset_mw_per_s < 0.95 * maxRamp
    const syncStr  = out > 0.01 ? 'online' : 'open'
    const rampStr  = `${u.r_asset_mw_per_s.toFixed(3)} / ${maxRamp.toFixed(3)}`
    const stateStr = isDeg ? 'degraded' : 'available'
    const runHStr  = u.run_hours_h != null
      ? Math.round(u.run_hours_h).toLocaleString()
      : '—'

    return React.createElement('tr', { key: u.asset_id },
      React.createElement('td', { style: dCell(GOLD, true) }, u.asset_id),
      React.createElement('td', { style: dCell(out > 0.01 ? GOLD : '#4b5764') }, `${out.toFixed(2)} MW`),
      React.createElement('td', { style: dCell('#4b5764') }, syncStr),
      React.createElement('td', { style: dCell(isDeg ? AMBER : '#8b949e') }, rampStr),
      React.createElement('td', { style: dCell('#4b5764') }, runHStr),
      React.createElement('td', { style: dCell(isDeg ? AMBER : TEAL, true) }, stateStr),
    )
  })

  const unitCountStr = units.length === 1
    ? `1 UNIT` : `${units.length} UNITS, NONE SYNCHRONISED AT REST`

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
               color: '#4b5764', textTransform: 'uppercase' as const, marginBottom: 8 }
    }, `FLEET — ${unitCountStr}`),
    React.createElement('table', {
      style: { width: '100%', borderCollapse: 'collapse' as const }
    },
      React.createElement('thead', null,
        React.createElement('tr', null,
          React.createElement('th', { style: hCell }, 'UNIT'),
          React.createElement('th', { style: hCell }, 'OUTPUT'),
          React.createElement('th', { style: hCell }, 'SYNC'),
          React.createElement('th', { style: hCell }, 'RAMP meas/cfg'),
          React.createElement('th', { style: hCell }, 'RUN h'),
          React.createElement('th', { style: hCell }, 'STATE'),
        )
      ),
      React.createElement('tbody', null, ...rows),
    ),
    degradedFootnotes.length > 0 && React.createElement('div', { style: { marginTop: 8 } },
      ...degradedFootnotes.map((note, i) =>
        React.createElement('p', {
          key: i,
          style: { fontFamily: 'Inter,sans-serif', fontSize: 10, color: '#4b5764',
                   lineHeight: 1.5, margin: i > 0 ? '4px 0 0' : '0' }
        }, note)
      )
    ),
  )
}

// ── Paralleling inset ───────────────────────────────────────────────────────
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
        style: { ...MONO, fontSize: 9, color: '#4b5764', flexShrink: 0, minWidth: 76 }
      }, u.asset_id),
      React.createElement('div', { style: { flex: 1, display: 'flex', alignItems: 'center', gap: 2 } },
        React.createElement('div', { style: { height: 1.5, flex: 1, background: '#2a3f52', minWidth: 10 } }),
        React.createElement('div', {
          style: {
            width: 16, height: 16, border: '1.5px solid #3a5060', borderRadius: 2,
            display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            ...MONO, fontSize: 7, color: '#4b5764',
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
               color: '#4b5764', textTransform: 'uppercase' as const, marginBottom: 12 }
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
            style: { ...MONO, fontSize: 9, color: '#4b5764', whiteSpace: 'nowrap' as const }
          }, '▶ switchgear / PMS'),
        ),
      ),
      React.createElement('div', { style: { flex: 1, minWidth: 200 } },
        React.createElement('p', {
          style: { fontFamily: 'Inter,sans-serif', fontSize: 10, color: '#8b949e', lineHeight: 1.6, margin: 0 }
        }, 'Synchro-check relay closes each breaker after matching voltage, frequency, phase.'),
        React.createElement('p', {
          style: { fontFamily: 'Inter,sans-serif', fontSize: 10, color: RED, lineHeight: 1.6,
                   margin: '4px 0 0', fontWeight: 600 }
        }, 'GridSignal never issues this command — TC-68'),
        React.createElement('p', {
          style: { fontFamily: 'Inter,sans-serif', fontSize: 10, color: '#4b5764', lineHeight: 1.6, margin: '8px 0 0' }
        }, 'Synchronous generators produce AC directly. No rectifier or DC link in this path — unlike the BESS and solar inverters, which are DC-coupled and grid-following.'),
      ),
    ),
  )
}

// ── No-tick panel ───────────────────────────────────────────────────────────
function noTickPanel(): PanelData {
  return {
    stateLabel:  '—',
    stateColour: '#30363d',
    verdict:     'No active run. Start a scenario to see fleet readiness.',
    heroValue:   '—',
    heroLabel:   'MW firm, N−1',
    chartTitle:  '',
    chart: React.createElement('div', {
      style: { fontFamily: 'Inter,sans-serif', fontSize: 11, color: '#4b5764',
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

// ── Single-unit panel (AE3 branch 1) ───────────────────────────────────────
function singleUnitPanel(tick: TickPayload, units: TurbineUnitSpec[]): PanelData {
  const u         = units[0]
  const outputMW  = tick.turbine_output_mw
  const stateLabel = outputMW > 0.1 ? 'ACTIVE' : 'READY'

  const chart = FleetTable(units, outputMW, u.r_asset_mw_per_s)

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
    stateColour: TEAL,
    verdict:     `Single-unit site — N−1 firm capacity 0.0 MW. A unit loss leaves BESS bridge only (~20 min).`,
    heroValue:   '0',
    heroLabel:   'MW firm, N−1',
    chartTitle:  '',
    chart,
    statRows: [
      { label: 'Units installed',    value: '1',                                  sub: `${u.rated_mw.toFixed(0)} MW · ${u.asset_id}` },
      { label: 'Units synchronised', value: outputMW > 0.1 ? '1' : '0',          colour: outputMW > 0.1 ? GOLD : undefined },
      { label: 'N−1 firm capacity',  value: '0.0 MW',                             colour: RED, sub: 'single unit — no redundancy' },
      { label: 'Peak site load',     value: `${PEAK_LOAD_MW.toFixed(2)} MW`,     sub: 'compute 19.96 + cooling 3.99' },
      { label: 'N−1 margin',         value: 'none',                               colour: RED },
      { label: 'Ramp (configured)',  value: `${u.r_asset_mw_per_s.toFixed(3)} MW/s`, sub: `${(u.r_asset_mw_per_s * LEAD_WINDOW_S).toFixed(1)} MW in ${LEAD_WINDOW_S.toFixed(0)} s window` },
      { label: 'Rated output',       value: `${u.rated_mw.toFixed(1)} MW`,       sub: 'nameplate' },
      { label: 'Start time, cold',   value: '5–10 min',                           sub: 'a cold unit contributes nothing to a 45 s event' },
    ],
    secondary,
    why: [
      `Installed capacity is not the number that matters — N−1 firm capacity is. A single ${u.rated_mw.toFixed(0)} MW unit has zero N−1 firm capacity.`,
      'A unit loss takes the site down after the battery empties: ~20 minutes of BESS bridge, then dark. This would not survive a customer reliability review.',
      'To achieve N−1 protection, replace this unit with a fleet of two or more units — N−1 firm capacity = (N−1) × unit_rated_mw.',
    ],
  }
}

// ── Fleet panel (AE3 branch 2) — N > 1 units ───────────────────────────────
function fleetPanel(tick: TickPayload, units: TurbineUnitSpec[]): PanelData {
  const outputMW  = tick.turbine_output_mw
  const onlineN   = outputMW > 0.1 ? 1 : 0  // aggregate only; unit-level sync not in tick

  const {
    installedMW, maxUnitMW, n1FirmMW, aggRampMWs,
    rampNeedMWs, n1MarginPct, maxRamp,
  } = deriveFleet(units)

  const n1Covers   = n1FirmMW >= PEAK_LOAD_MW
  const rampCovers = aggRampMWs >= rampNeedMWs
  const stateLabel = n1Covers && rampCovers ? 'READY' : 'ATTENTION'
  const stateColour = n1Covers && rampCovers ? TEAL : AMBER

  const marginStr = n1MarginPct >= 0
    ? `+${n1MarginPct}%` : `${n1MarginPct}%`
  const marginColour = n1MarginPct >= 0 ? TEAL : RED

  const chart = FleetTable(units, outputMW, maxRamp)

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
      max:    Math.max(aggRampMWs * 1.5, rampNeedMWs * 1.5),
      target: rampNeedMWs,
      colour: rampCovers ? GOLD : RED,
      unit:   ' MW/s',
      note:   `red marker = ${rampNeedMWs.toFixed(3)} MW/s to cover ${PEAK_LOAD_MW.toFixed(2)} MW step in ${LEAD_WINDOW_S.toFixed(0)} s  ·  ramp scales with unit count`,
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
    heroValue: n1FirmMW.toFixed(0),
    heroLabel: 'MW firm, N−1',
    chartTitle: '',
    chart,
    statRows: [
      { label: 'Units installed',      value: `${units.length}`,               sub: `${maxUnitMW.toFixed(0)} MW each · ${installedMW.toFixed(0)} MW total` },
      { label: 'Units synchronised',   value: `${onlineN}`,                    sub: onlineN > 0 ? `contributing ${outputMW.toFixed(2)} MW` : 'none online at rest', colour: onlineN > 0 ? GOLD : undefined },
      { label: 'N−1 firm capacity',    value: `${n1FirmMW.toFixed(1)} MW`,     colour: n1Covers ? GOLD : RED, sub: 'with any one unit unavailable' },
      { label: 'Peak site load',       value: `${PEAK_LOAD_MW.toFixed(2)} MW`, sub: 'compute 19.96 + cooling 3.99' },
      { label: 'N−1 margin',           value: marginStr,                        colour: marginColour, sub: `${units.length} units with headroom` },
      { label: 'Aggregate ramp',       value: `${aggRampMWs.toFixed(3)} MW/s`, colour: rampCovers ? GOLD : RED, sub: `${(aggRampMWs * LEAD_WINDOW_S).toFixed(0)} MW in ${LEAD_WINDOW_S.toFixed(0)} s window` },
      { label: 'Ramp with 1 unit',     value: `${rampWith1} MW/s`,             sub: `${(parseFloat(rampWith1) * LEAD_WINDOW_S).toFixed(0)} MW in ${LEAD_WINDOW_S.toFixed(0)} s — BESS covers the remainder` },
      { label: 'Start time, cold',     value: '5–10 min',                      sub: 'a cold unit contributes nothing to a 45 s event' },
    ],
    secondary,
    why: [
      `Installed capacity is not the number that matters — N−1 firm capacity is. ${units.length} × ${maxUnitMW.toFixed(0)} MW gives ${n1FirmMW.toFixed(1)} MW firm against a ${PEAK_LOAD_MW.toFixed(2)} MW peak.`,
      `Aggregate ramp scales with unit count, not megawatts: ${units.length} units deliver ${aggRampMWs.toFixed(3)} MW/s — ${units.length}× the rate of a single equivalent unit.`,
      'Degraded = effective ramp below 95% of fleet maximum. The reserve check uses the effective figure (§27, TC-58) — a quietly degraded unit is decisive in a reserve calculation.',
    ],
  }
}

// ── Panel config ────────────────────────────────────────────────────────────
export const turbineFleetPanel: PanelConfig = {
  deriveData(tick: TickPayload | null, _alert: TickPayload | null, _history: HistoryPoint[]): PanelData {
    if (!tick) return noTickPanel()

    const units = tick.turbine_units ?? []

    if (units.length === 0) {
      // Spec path delivered no units — treat as "not instrumented".
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
