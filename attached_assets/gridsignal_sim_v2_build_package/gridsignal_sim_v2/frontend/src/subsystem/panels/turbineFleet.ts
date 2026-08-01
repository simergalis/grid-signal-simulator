/**
 * turbineFleet.ts — Gas Turbine Fleet modal panel (gs-14).
 *
 * Accent: Gold #e0a458.
 *
 * What this panel argues that the generation panel cannot:
 *   · N−1 firm capacity is the headline, not installed capacity.
 *   · Aggregate ramp scales with unit count, not megawatts.
 *   · Per-unit re-rating (§27, TC-58) is decisive in a reserve calculation.
 *
 * All per-unit data is static — the live tick carries only the aggregate
 * turbine_output_mw.  Unit-level breakdown requires a fleet scenario
 * (demo-3turbine, not yet seeded); the table is grounded in the 3×15 MW
 * aeroderivative config from the mockup notes.
 */

import React from 'react'
import type { PanelConfig, PanelData } from './index'
import type { TickPayload, HistoryPoint } from '../../types'
import { BulletBar } from '../../charts/BulletBar'

// ── Fleet constants (3 × 15 MW aeroderivative) ─────────────────────────────
const GOLD             = '#e0a458'
const TEAL             = '#3fb6a8'
const RED_ALERT        = '#f85149'
const AMBER            = '#f0883e'

const UNIT_RATED_MW    = 15.0   // per-unit nameplate
const UNIT_COUNT       = 3
const INSTALLED_MW     = UNIT_COUNT * UNIT_RATED_MW  // 45 MW
const N1_FIRM_MW       = (UNIT_COUNT - 1) * UNIT_RATED_MW  // 30 MW
const PEAK_LOAD_MW     = 23.95  // demo-20mw P_total (compute + cooling)
const N1_MARGIN_PCT    = Math.round((N1_FIRM_MW - PEAK_LOAD_MW) / PEAK_LOAD_MW * 100) // 25 %
const AGG_RAMP_MW_S    = 0.600  // 3 × 0.200 MW/s
const RAMP_NEED_MW_S   = 0.532  // needed to close 23.95 MW step in 45 s window
const AGG_RAMP_MAX     = 0.800  // axis ceiling for bullet bar

const FLEET_UNITS = [
  { id: 'turbine-01', rampMeas: 0.200, rampCfg: 0.200, runH: 1284, state: 'available' },
  { id: 'turbine-02', rampMeas: 0.200, rampCfg: 0.200, runH: 1197, state: 'available' },
  { id: 'turbine-03', rampMeas: 0.160, rampCfg: 0.200, runH: 2041, state: 'degraded'  },
]

function fmtRunH(h: number): string {
  return h.toLocaleString()
}

// ── Per-unit table ──────────────────────────────────────────────────────────
function FleetTable(outputMW: number): React.ReactNode {
  // Distribute live output: turbine-01 carries the aggregate (single-turbine demo).
  // In a real fleet scenario, per-unit output would come from the tick directly.
  const unit1Out = outputMW
  const unit2Out = 0
  const unit3Out = 0

  const MONO: React.CSSProperties = {
    fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace",
  }
  const hCell: React.CSSProperties = {
    ...MONO,
    fontSize: 9,
    fontWeight: 700,
    letterSpacing: '0.1em',
    color: '#4b5764',
    padding: '0 8px 6px 0',
    textTransform: 'uppercase' as const,
    borderBottom: '1px solid #1e2a36',
    whiteSpace: 'nowrap' as const,
  }
  const dCell = (colour?: string, bold?: boolean): React.CSSProperties => ({
    ...MONO,
    fontSize: 10,
    color: colour ?? '#8b949e',
    fontWeight: bold ? 600 : 400,
    padding: '5px 8px 5px 0',
    borderBottom: '1px solid #111821',
    whiteSpace: 'nowrap' as const,
  })

  const rows = FLEET_UNITS.map((u, i) => {
    const out   = i === 0 ? unit1Out : i === 1 ? unit2Out : unit3Out
    const isDeg = u.state === 'degraded'
    const outStr = `${out.toFixed(2)} MW`
    const rampStr = `${u.rampMeas.toFixed(3)} / ${u.rampCfg.toFixed(3)}`

    return React.createElement('tr', { key: u.id },
      React.createElement('td', { style: dCell(GOLD, true) }, u.id),
      React.createElement('td', { style: dCell(out > 0.01 ? GOLD : '#4b5764') }, outStr),
      React.createElement('td', { style: dCell('#4b5764') }, 'open'),
      React.createElement('td', {
        style: dCell(isDeg ? AMBER : '#8b949e'),
      }, rampStr),
      React.createElement('td', { style: dCell('#4b5764') }, fmtRunH(u.runH)),
      React.createElement('td', {
        style: dCell(isDeg ? AMBER : TEAL, true),
      }, u.state),
    )
  })

  const thead = React.createElement('thead', null,
    React.createElement('tr', null,
      React.createElement('th', { style: hCell }, 'UNIT'),
      React.createElement('th', { style: hCell }, 'OUTPUT'),
      React.createElement('th', { style: hCell }, 'SYNC'),
      React.createElement('th', { style: hCell }, 'RAMP meas/cfg'),
      React.createElement('th', { style: hCell }, 'RUN h'),
      React.createElement('th', { style: hCell }, 'STATE'),
    )
  )

  const tbody = React.createElement('tbody', null, ...rows)

  const table = React.createElement('table', {
    style: { width: '100%', borderCollapse: 'collapse' as const },
  }, thead, tbody)

  return React.createElement('div', { style: { overflowX: 'auto' as const } },
    // Section header
    React.createElement('div', {
      style: {
        ...MONO,
        fontSize: 9,
        fontWeight: 700,
        letterSpacing: '0.1em',
        color: '#4b5764',
        textTransform: 'uppercase' as const,
        marginBottom: 8,
      }
    }, `FLEET — ${UNIT_COUNT} UNITS, NONE SYNCHRONISED AT REST`),
    table,
    // Re-rating footnote
    React.createElement('p', {
      style: {
        fontFamily: 'Inter,sans-serif',
        fontSize: 10,
        color: '#4b5764',
        marginTop: 8,
        lineHeight: 1.5,
      }
    }, 'turbine-03 re-rated to 0.160 MW/s after 2,041 h. The reserve check uses the re-rated figure — neither nameplate nor exclusion (§27, TC-58). A raise requires a longer window and confirmation.'),
  )
}

// ── Paralleling inset ───────────────────────────────────────────────────────
function ParallelingInset(): React.ReactNode {
  const MONO: React.CSSProperties = {
    fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace",
  }

  // One generator row: label (G) ──[CB]──
  function GenRow(id: string): React.ReactNode {
    return React.createElement('div', {
      key: id,
      style: { display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 },
    },
      // Generator circle
      React.createElement('div', {
        style: {
          width: 28, height: 28, borderRadius: '50%',
          border: `1.5px solid ${GOLD}`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0,
          ...MONO, fontSize: 9, fontWeight: 700, color: GOLD,
        }
      }, 'G'),
      // id label
      React.createElement('div', {
        style: { ...MONO, fontSize: 9, color: '#4b5764', flexShrink: 0, minWidth: 72 }
      }, id),
      // wire + breaker + wire
      React.createElement('div', {
        style: { flex: 1, display: 'flex', alignItems: 'center', gap: 2 }
      },
        // left wire
        React.createElement('div', {
          style: { height: 1.5, flex: 1, background: '#2a3f52', minWidth: 12 }
        }),
        // breaker box
        React.createElement('div', {
          style: {
            width: 16, height: 16,
            border: '1.5px solid #3a5060',
            borderRadius: 2,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
            ...MONO, fontSize: 7, color: '#4b5764',
          }
        }, 'CB'),
        // right wire
        React.createElement('div', {
          style: { height: 1.5, flex: 1, background: '#2a3f52', minWidth: 8 }
        }),
      ),
    )
  }

  return React.createElement('div', {
    style: {
      borderTop: '1px solid #1e2a36',
      borderBottom: '1px solid #1e2a36',
      padding: '12px 0',
    }
  },
    // Section label
    React.createElement('div', {
      style: {
        ...MONO,
        fontSize: 9, fontWeight: 700,
        letterSpacing: '0.1em',
        color: '#4b5764',
        textTransform: 'uppercase' as const,
        marginBottom: 12,
      }
    }, 'PARALLELING — AC BUS, SYNCHRO-CHECK BEFORE CLOSE'),

    React.createElement('div', {
      style: { display: 'flex', gap: 24, alignItems: 'flex-start', flexWrap: 'wrap' as const }
    },
      // Left: generator rows + bus
      React.createElement('div', { style: { minWidth: 260 } },
        GenRow('turbine-01'),
        GenRow('turbine-02'),
        GenRow('turbine-03'),
        // Vertical bus stub + bus label
        React.createElement('div', {
          style: { display: 'flex', alignItems: 'center', gap: 8, marginTop: 4, marginLeft: 110 }
        },
          React.createElement('div', {
            style: {
              height: 2, flex: 1,
              background: GOLD,
              borderRadius: 1,
            }
          }),
          React.createElement('div', {
            style: {
              ...MONO, fontSize: 9, fontWeight: 700,
              color: GOLD, whiteSpace: 'nowrap' as const,
            }
          }, '13.8 kV BUS'),
          React.createElement('div', {
            style: {
              ...MONO, fontSize: 9, color: '#4b5764',
              whiteSpace: 'nowrap' as const,
            }
          }, '▶ switchgear / PMS'),
        ),
      ),

      // Right: explanatory text
      React.createElement('div', {
        style: { flex: 1, minWidth: 200 }
      },
        React.createElement('p', {
          style: {
            fontFamily: 'Inter,sans-serif',
            fontSize: 10, color: '#8b949e', lineHeight: 1.6, margin: 0,
          }
        }, 'Synchro-check relay closes each breaker after matching voltage, frequency, phase.'),
        React.createElement('p', {
          style: {
            fontFamily: 'Inter,sans-serif',
            fontSize: 10, color: RED_ALERT, lineHeight: 1.6, margin: '4px 0 0',
            fontWeight: 600,
          }
        }, 'GridSignal never issues this command — TC-68'),
        React.createElement('p', {
          style: {
            fontFamily: 'Inter,sans-serif',
            fontSize: 10, color: '#4b5764', lineHeight: 1.6, margin: '8px 0 0',
          }
        }, 'Synchronous generators produce AC directly. No rectifier or DC link in this path — unlike the BESS and solar inverters, which are DC-coupled and grid-following.'),
      ),
    ),
  )
}

// ── Panel config ────────────────────────────────────────────────────────────
export const turbineFleetPanel: PanelConfig = {
  deriveData(tick: TickPayload | null, _alert: TickPayload | null, _history: HistoryPoint[]): PanelData {

    if (!tick) {
      return {
        stateLabel:  'READY',
        stateColour: TEAL,
        verdict:     `N−1 firm capacity ${N1_FIRM_MW.toFixed(1)} MW covers the ${PEAK_LOAD_MW.toFixed(2)} MW peak with ${N1_MARGIN_PCT}% margin.`,
        heroValue:   `${N1_FIRM_MW.toFixed(0)}`,
        heroLabel:   'MW firm, N−1',
        chartTitle:  '',
        chart: FleetTable(0),
        statRows: [
          { label: 'Units installed',      value: `${UNIT_COUNT}`,                        sub: `${UNIT_RATED_MW.toFixed(0)} MW each · ${INSTALLED_MW.toFixed(0)} MW total` },
          { label: 'Units synchronised',   value: '0',                                    sub: 'none online at rest' },
          { label: 'N−1 firm capacity',    value: `${N1_FIRM_MW.toFixed(1)} MW`,          colour: GOLD, sub: 'with any one unit unavailable' },
          { label: 'Peak site load',       value: `${PEAK_LOAD_MW.toFixed(2)} MW`,        sub: 'compute 19.96 + cooling 3.99' },
          { label: 'N−1 margin',           value: `+${N1_MARGIN_PCT}%`,                   colour: TEAL, sub: '3 units with headroom' },
          { label: 'Aggregate ramp',       value: `${AGG_RAMP_MW_S.toFixed(3)} MW/s`,     colour: GOLD, sub: `3 units online — ${(AGG_RAMP_MW_S * 45).toFixed(0)} MW in a 45 s window` },
          { label: 'Ramp with 1 unit',     value: `${(AGG_RAMP_MW_S / UNIT_COUNT).toFixed(3)} MW/s`, sub: '9 MW in 45 s — BESS covers the remainder' },
          { label: 'Start time from cold', value: '5–10 min',                             sub: 'a cold unit contributes nothing to a 45 s event' },
        ],
        secondary: React.createElement('div', { className: 'space-y-3' },
          React.createElement(BulletBar, {
            label:  'N−1 firm capacity against peak site load',
            value:  N1_FIRM_MW,
            max:    INSTALLED_MW,
            target: PEAK_LOAD_MW,
            colour: GOLD,
            unit:   ' MW',
            note:   `red marker = ${PEAK_LOAD_MW.toFixed(2)} MW peak load  ·  ${N1_MARGIN_PCT}% margin with any one unit out`,
          }),
          React.createElement(BulletBar, {
            label:  'Aggregate ramp with all units online',
            value:  AGG_RAMP_MW_S,
            max:    AGG_RAMP_MAX,
            target: RAMP_NEED_MW_S,
            colour: GOLD,
            unit:   ' MW/s',
            note:   `red marker = ${RAMP_NEED_MW_S.toFixed(3)} MW/s needed to cover a ${PEAK_LOAD_MW.toFixed(2)} MW step in 45 s  ·  ramp scales with unit count, not megawatts`,
          }),
          ParallelingInset(),
        ),
        why: [
          `Installed capacity is not the number that matters — N−1 firm capacity is. A single 25 MW unit has zero N−1 firm capacity; its failure leaves ~20 minutes of battery and then dark.`,
          `Aggregate ramp scales with unit count, not megawatts: three 15 MW units answer a step-load at 0.600 MW/s — three times the rate of a single 25 MW unit.`,
          `turbine-03 re-rated to 0.160 MW/s after 2,041 h (§27, TC-58). A unit quietly delivering 80% of configured ramp is invisible in an aggregate and decisive in a reserve calculation.`,
        ],
      }
    }

    // ── Live run ────────────────────────────────────────────────────────────
    const outputMW  = tick.turbine_output_mw
    const onlineCount = outputMW > 0.1 ? 1 : 0  // single-turbine demo; fleet would report more

    const stateLabel  = onlineCount > 0 ? 'ACTIVE' : 'READY'
    const stateColour = TEAL

    const chart = FleetTable(outputMW)

    const secondary = React.createElement('div', { className: 'space-y-3' },
      React.createElement(BulletBar, {
        label:  'N−1 firm capacity against peak site load',
        value:  N1_FIRM_MW,
        max:    INSTALLED_MW,
        target: PEAK_LOAD_MW,
        colour: GOLD,
        unit:   ' MW',
        note:   `red marker = ${PEAK_LOAD_MW.toFixed(2)} MW peak load  ·  ${N1_MARGIN_PCT}% margin with any one unit out`,
      }),
      React.createElement(BulletBar, {
        label:  'Aggregate ramp with all units online',
        value:  AGG_RAMP_MW_S,
        max:    AGG_RAMP_MAX,
        target: RAMP_NEED_MW_S,
        colour: GOLD,
        unit:   ' MW/s',
        note:   `red marker = ${RAMP_NEED_MW_S.toFixed(3)} MW/s needed to cover a ${PEAK_LOAD_MW.toFixed(2)} MW step in 45 s  ·  ramp scales with unit count, not megawatts`,
      }),
      ParallelingInset(),
    )

    return {
      stateLabel,
      stateColour,
      verdict: `N−1 firm capacity ${N1_FIRM_MW.toFixed(1)} MW covers the ${PEAK_LOAD_MW.toFixed(2)} MW peak with ${N1_MARGIN_PCT}% margin.`,
      heroValue: `${N1_FIRM_MW.toFixed(0)}`,
      heroLabel: 'MW firm, N−1',
      chartTitle: '',
      chart,
      statRows: [
        { label: 'Units installed',      value: `${UNIT_COUNT}`,                        sub: `${UNIT_RATED_MW.toFixed(0)} MW each · ${INSTALLED_MW.toFixed(0)} MW total` },
        { label: 'Units synchronised',   value: `${onlineCount}`,                       sub: onlineCount > 0 ? `${onlineCount} unit contributing ${outputMW.toFixed(2)} MW` : 'none online at rest', colour: onlineCount > 0 ? GOLD : undefined },
        { label: 'N−1 firm capacity',    value: `${N1_FIRM_MW.toFixed(1)} MW`,          colour: GOLD, sub: 'with any one unit unavailable' },
        { label: 'Peak site load',       value: `${PEAK_LOAD_MW.toFixed(2)} MW`,        sub: 'compute 19.96 + cooling 3.99' },
        { label: 'N−1 margin',           value: `+${N1_MARGIN_PCT}%`,                   colour: TEAL, sub: '3 units with headroom' },
        { label: 'Aggregate ramp',       value: `${AGG_RAMP_MW_S.toFixed(3)} MW/s`,     colour: GOLD, sub: `3 units online — ${(AGG_RAMP_MW_S * 45).toFixed(0)} MW in a 45 s window` },
        { label: 'Ramp with 1 unit',     value: `${(AGG_RAMP_MW_S / UNIT_COUNT).toFixed(3)} MW/s`, sub: '9 MW in 45 s — BESS covers the remainder' },
        { label: 'Start time from cold', value: '5–10 min',                             sub: 'a cold unit contributes nothing to a 45 s event' },
      ],
      secondary,
      why: [
        `Installed capacity is not the number that matters — N−1 firm capacity is. A single 25 MW unit has zero N−1 firm capacity; its failure leaves ~20 minutes of battery and then dark.`,
        `Aggregate ramp scales with unit count, not megawatts: three 15 MW units answer a step-load at 0.600 MW/s — three times the rate of a single 25 MW unit.`,
        `turbine-03 re-rated to 0.160 MW/s after 2,041 h (§27, TC-58). A unit quietly delivering 80% of configured ramp is invisible in an aggregate and decisive in a reserve calculation.`,
      ],
    }
  },
}
