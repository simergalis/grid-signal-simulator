/**
 * agents.ts — Optimisation Agents subsystem panel config.
 *
 * Accent: Violet #9b8ce0.
 * Copy matches gridsignal-15-agents.svg.
 *
 * LP-1 guarantee: dispatch NEVER waits for an agent. Agents produce proposals;
 * humans approve. The six agents run serially in this build — noted honestly.
 */

import React from 'react'
import type { PanelConfig, PanelData } from './index'
import type { TickPayload, HistoryPoint } from '../../types'
import { TimeSeries } from '../../charts/TimeSeries'

const VIOLET = '#9b8ce0'
const TEAL   = '#3fb6a8'
const AMBER  = '#f0883e'

const AGENT_NAMES = [
  'compute', 'storage', 'generation', 'renewable', 'thermal', 'calibration',
]

export const agentsPanel: PanelConfig = {
  deriveData(tick: TickPayload | null, _alert, history: HistoryPoint[]): PanelData {
    const chart = React.createElement(TimeSeries, {
      series: [
        { label: 'agent cycles (cumulative)', colour: VIOLET,
          points: history.map((h, i) => ({ x: h.sim_time_seconds, y: i + 1 })), filled: true },
      ],
      xLabel:  'seconds from run start',
      height:  200,
    })

    return {
      stateLabel:  'ARMED',
      stateColour: TEAL,
      verdict:     'Finding patterns a threshold rule cannot — and dispatch never waits.',
      heroValue:   '6/6',
      heroLabel:   'armed',
      chartTitle:  'AGENT ACTIVITY — CADENCE FLOORS ARE WALL-CLOCK, NOT SIMULATED TIME',
      chart,
      statRows: [
        { label: 'Agents armed',        value: '6 / 6', colour: VIOLET },
        { label: 'Dispatch authority',  value: 'none',  colour: TEAL, sub: 'LP-1: dispatch never waits for an agent' },
        { label: 'Proposal gate',       value: 'human approval required' },
        { label: 'Cadence (fast)',       value: '30–60 s', sub: 'compute, storage, generation' },
        { label: 'Cadence (slow)',       value: '5–60 min', sub: 'calibration, thermal' },
        { label: 'Execution model',     value: 'serial (this build)', colour: AMBER, sub: '6 agents run serially on sync urllib — §3 known gap' },
        { label: 'Token budget',        value: 'not enforced', colour: AMBER, sub: 'soft 2.2 M / hard 15 M per site-day — not implemented' },
        { label: 'generated_by',        value: tick ? 'see Proposals page' : '—' },
        ...AGENT_NAMES.map(n => ({ label: n, value: 'armed', colour: VIOLET })),
      ],
      secondary: undefined,
      why: [
        'Six agents analyse patterns across compute, storage, generation, renewable, thermal, and calibration domains.',
        'No agent has dispatch authority — every proposal requires a human to review and approve (§19.10).',
        'LP-1 guarantee: the dispatch path runs synchronously; agent inference runs asynchronously and never blocks staging.',
      ],
    }
  },
}
