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
import { BulletBar } from '../../charts/BulletBar'
// GS-DES-CFG-001 §Phase-4: bess_rated_mw, bess_usable_mwh, bess_unit_count are now
// broadcast per tick (TickPayload).  BulletBar restored, max from bess_rated_mw.

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

    // GS-DES-CFG-001 §Phase-4: BESS fleet aggregates from TickPayload.
    // bess_output_mw: FLEET-LEVEL sum — accumulated via += in BessArbitrator.tick()
    //   over all bess_units (dispatch.py:681–683, candidate_id "bess-fleet").
    //   Sub-label must state fleet scope so an operator reading "0.5 MW" knows
    //   it is the total discharge across all units, not a per-unit figure.
    // bess_rated_mw / bess_usable_mwh: config nameplate aggregates, NOT from
    //   contingency_coverage.bess_usable_energy_mwh (fault-injected figure).
    const ratedMW   = tick.bess_rated_mw    // FLEET: config nameplate rated power (MW)
    const usableMWh = tick.bess_usable_mwh  // FLEET: config nameplate usable energy (MWh)
    const unitCount = tick.bess_unit_count  // count of BESS units
    const unitLabel = `${unitCount} unit${unitCount !== 1 ? 's' : ''}`

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
      secondary: React.createElement(BulletBar, {
        // FLEET-LEVEL: value = fleet discharge (sum of all units); max = fleet rated power
        // from config nameplate.  max comes from bess_rated_mw, never from outputMW itself
        // (a bar whose max equals its own value is permanently full).
        label:  'Current output vs fleet rated power',
        value:  outputMW,
        max:    ratedMW > 0 ? ratedMW : Math.max(outputMW, 1),
        colour: BATTERY,
        unit:   ' MW',
        note:   ratedMW > 0
          ? `Fleet discharge ${outputMW.toFixed(2)} MW of ${ratedMW.toFixed(2)} MW rated (${unitLabel}). SoC ${socPct}%.`
          : 'Rated power not yet available on this tick',
      }),
      statRows: [
        { label: 'State of charge',   value: `${socPct}%`,                        colour: soc < 0.2 ? RED : soc < 0.4 ? AMBER : undefined },
        { label: 'Rated power',       value: `${ratedMW.toFixed(2)} MW`,           sub: `fleet aggregate — ${unitLabel}` },
        // GS-DES-CFG-001 §Phase-6 / Item-2: bess_anchor_reserve_mw now on wire.
        { label: 'Anchor reserve',    value: `${tick.bess_anchor_reserve_mw.toFixed(1)} MW`,  colour: AMBER, sub: 'withheld for grid-forming (§7.1.2) — catalogue: locked bess_anchor_reserve_mw' },
        { label: 'Current output',    value: `${outputMW.toFixed(2)} MW`,          colour: BATTERY, sub: 'fleet discharge — sum across all units' },
        { label: 'Usable energy',     value: `${usableMWh.toFixed(2)} MWh`,        sub: `fleet aggregate — ${unitLabel}` },
        { label: 'Bridging basis',    value: tick.bridging_basis.replace('_', ' ') },
        { label: 'State of health',   value: 'not modelled',                       sub: 'no degradation curve in this version' },
      ],
      why: [
        'The battery serves two purposes simultaneously: grid-forming anchor and bridge reserve.',
        // GS-DES-CFG-001 §Phase-6 / Item-2 (stale): was hardcoded "One megawatt".
        `${tick.bess_anchor_reserve_mw.toFixed(1)} MW is permanently withheld to regulate frequency — this is the anchor reserve (§7.1.2).`,
        'Bridge duration at current shortfall is the metric that answers the operator question, not SoC percentage.',
      ],
    }
  },
}
