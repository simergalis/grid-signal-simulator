/**
 * storage.ts — Energy Storage subsystem panel config.
 *
 * Accent: Battery blue #4a9fe0.
 * Copy matches gridsignal-08-storage.svg.
 *
 * Key distinction: "battery 95%" is equipment status.
 * "can bridge the predicted peak for 51 minutes" is the product argument.
 *
 * One megawatt is withheld as anchor reserve (§7.1.2) when grid-forming.
 * We show bridging_available = bess_output_mw-based figure from the tick.
 */

import React from 'react'
import type { PanelConfig, PanelData } from './index'
import type { TickPayload, HistoryPoint } from '../../types'
import { GaugeArc }  from '../../charts/GaugeArc'
// BulletBar removed: BESS rated MW is not on the tick payload (bess_units is on
// ScenarioSpec, not TickPayload).  A bar whose max equals its own value is
// permanently full regardless of actual headroom.  Phase 4 restores it.

const BATTERY = '#4a9fe0'
const AMBER   = '#f0883e'
const RED     = '#f85149'

function fmtBridge(s: number): string {
  if (s >= 86400) return 'full reserve'
  if (s >= 3600)  return `${(s / 3600).toFixed(1)} h`
  if (s >= 60)    return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
  return `${s.toFixed(0)} s`
}

export const storagePanel: PanelConfig = {
  deriveData(tick: TickPayload | null, alert, _history: HistoryPoint[]): PanelData {
    if (!tick) {
      return {
        stateLabel:  '—',
        stateColour: '#30363d',
        verdict:     'No active run. Start a scenario to see storage readiness.',
        heroValue:   '—',
        heroLabel:   'bridge duration',
        chartTitle:  'STATE OF CHARGE',
        chart: React.createElement('div', { className: 'font-mono text-xs text-muted py-12 text-center' }, 'No data'),
        statRows: [],
        why: [
          'The battery serves two purposes: grid-forming anchor and bridge reserve.',
          'One megawatt is permanently withheld to regulate frequency — anchor reserve (§7.1.2).',
          'Bridge duration is the only metric that answers the operator question: how long can we cover the gap?',
        ],
      }
    }

    const soc       = tick.bess_soc_fraction
    const socPct    = Math.round(soc * 100)
    const bridge_s  = tick.bess_bridging_seconds
    const bridgeStr = fmtBridge(bridge_s)
    const outputMW  = tick.bess_output_mw

    // GS-DES-CFG-001 §Phase-3 / Item-2 correction:
    // tick.bess_units is on ScenarioSpec, not TickPayload — absent from the wire
    // format (_tick_result_to_dict does not emit it).  Rated power and usable
    // energy are therefore "not instrumented" at this panel scope.
    // Phase 4 will add bess_rated_mw + bess_usable_mwh to the TickResult and
    // serialiser so they are broadcast per tick.

    const stateLabel  = alert ? 'ATTENTION' : bridge_s > 0 ? 'READY' : 'ATTENTION'
    const stateColour = alert ? AMBER : bridge_s > 0 ? '#3fb6a8' : RED

    const chart = React.createElement(GaugeArc, {
      fraction:   soc,
      colour:     soc < 0.2 ? RED : soc < 0.4 ? AMBER : BATTERY,
      bigLabel:   `${socPct}%`,
      smallLabel: 'state of charge',
    })

    return {
      stateLabel,
      stateColour,
      verdict: bridge_s >= 86400
        ? 'Full reserve — can bridge the predicted peak for the run duration.'
        : bridge_s > 0
        ? `Can bridge the predicted peak for ${bridgeStr}.`
        : 'Cannot bridge — BESS power below predicted peak shortfall.',
      heroValue:  bridgeStr,
      heroLabel:  'bridge duration',
      chartTitle: 'STATE OF CHARGE',
      chart,
      statRows: [
        { label: 'State of charge',   value: `${socPct}%`,        colour: soc < 0.2 ? RED : soc < 0.4 ? AMBER : undefined },
        { label: 'Rated power',       value: 'not instrumented',  sub: 'bess_units not on tick payload — Phase 4 scope' },
        { label: 'Anchor reserve',    value: '1.0 MW',            colour: AMBER, sub: 'withheld for grid-forming (§7.1.2)' },
        { label: 'Current output',    value: `${outputMW.toFixed(2)} MW`, colour: BATTERY },
        { label: 'Usable energy',     value: 'not instrumented',  sub: 'bess_units not on tick payload — Phase 4 scope' },
        { label: 'Bridging basis',    value: tick.bridging_basis.replace('_', ' ') },
        { label: 'State of health',   value: 'not modelled',      sub: 'no degradation curve in this version' },
      ],
      why: [
        'The battery serves two purposes simultaneously: grid-forming anchor and bridge reserve.',
        'One megawatt is permanently withheld to regulate frequency — this is the anchor reserve (§7.1.2).',
        'Bridge duration at current shortfall is the metric that answers the operator question, not SoC percentage.',
      ],
    }
  },
}
