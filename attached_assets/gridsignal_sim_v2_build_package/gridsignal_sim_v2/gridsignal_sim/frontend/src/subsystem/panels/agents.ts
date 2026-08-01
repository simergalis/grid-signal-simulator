/**
 * agents.ts — Optimisation Agents subsystem panel config (W2a).
 *
 * Accent: Violet #9b8ce0.
 *
 * LP-1 guarantee: dispatch NEVER waits for an agent. Agents produce proposals;
 * humans approve. The six agents run serially in this build — noted honestly.
 *
 * W2a: all stat rows now derive from tick.advisory_telemetry when available.
 * Falls back to static defaults when no registry is active (LP-1 / no API key).
 */

import React from 'react'
import type { PanelConfig, PanelData } from './index'
import type { TickPayload, HistoryPoint } from '../../types'
import { TimeSeries } from '../../charts/TimeSeries'

const VIOLET = '#9b8ce0'
const TEAL   = '#3fb6a8'
const AMBER  = '#f0883e'
const DIM    = '#6b7280'

const AGENT_NAMES: Array<keyof NonNullable<NonNullable<TickPayload['advisory_telemetry']>['per_agent']>> = [
  'compute', 'storage', 'generation', 'renewable', 'thermal', 'calibration',
]

/** Format sim_time (seconds) as a compact string, e.g. "t=125 s" or "never". */
function fmtSimTime(t: number): string {
  if (t < 0) return 'not yet'
  return `t = ${Math.round(t)} s`
}

/** Format a backend string for display. */
function fmtBackend(b: string | null): string {
  if (!b)              return 'none (LP-1)'
  if (b === 'mistral') return 'Mistral'
  if (b === 'anthropic') return 'Anthropic'
  if (b === 'deterministic') return 'deterministic'
  return b
}

export const agentsPanel: PanelConfig = {
  deriveData(tick: TickPayload | null, _alert, history: HistoryPoint[]): PanelData {
    const at = tick?.advisory_telemetry ?? null

    // ── Live derived values ───────────────────────────────────────────────
    const armed         = at?.agents_armed        ?? 0
    const total         = at?.proposals_total     ?? 0
    const pending       = at?.proposals_pending   ?? 0
    const lastSimTime   = at?.last_proposal_sim_time ?? -1
    const backend       = at?.backend             ?? null
    const hasAgent      = armed > 0

    // State label and colour
    const stateLabel  = !tick ? 'STANDBY' : hasAgent ? 'ARMED' : 'NO KEY'
    const stateColour = !tick ? DIM : hasAgent ? TEAL : AMBER

    // Hero: live X/6 armed count
    const heroValue = tick ? `${armed}/6` : '–/6'
    const heroLabel = hasAgent ? 'armed' : (tick ? 'no LLM key' : 'pre-run')

    // Verdict sentence
    const verdict = !tick
      ? 'Agents stand by — start a run to activate the advisory loop.'
      : !hasAgent
      ? 'LP-1 active — no API key; agents run heuristic fallbacks only.'
      : total === 0
      ? 'Finding patterns a threshold rule cannot — and dispatch never waits.'
      : pending > 0
      ? `${pending} proposal${pending > 1 ? 's' : ''} awaiting review — dispatch never waits for approval.`
      : `${total} proposal${total > 1 ? 's' : ''} generated this run — all resolved, none pending.`

    // Chart: cumulative agent cycles (unchanged — this is genuinely live)
    const chart = React.createElement(TimeSeries, {
      series: [
        {
          label: 'agent cycles (cumulative)',
          colour: VIOLET,
          points: history.map((h, i) => ({ x: h.sim_time_seconds, y: i + 1 })),
          filled: true,
        },
      ],
      xLabel: 'seconds from run start',
      height: 200,
    })

    // ── Stat rows ─────────────────────────────────────────────────────────
    const statRows = [
      {
        label:  'Agents armed',
        value:  tick ? `${armed} / 6` : '— / 6',
        colour: hasAgent ? VIOLET : AMBER,
        sub:    hasAgent ? undefined : 'set MISTRAL_API_KEY or ANTHROPIC_API_KEY',
      },
      {
        label:  'Backend',
        value:  fmtBackend(backend),
        colour: backend ? VIOLET : AMBER,
        sub:    backend === 'deterministic'
          ? 'transport mock — no network calls'
          : backend
          ? undefined
          : 'LP-1: heuristic fallbacks in use',
      },
      {
        label:  'Dispatch authority',
        value:  'none',
        colour: TEAL,
        sub:    'LP-1: dispatch never waits for an agent',
      },
      {
        label:  'Proposal gate',
        value:  'human approval required',
      },
      {
        label:  'Proposals this run',
        value:  tick ? String(total) : '—',
        colour: total > 0 ? VIOLET : undefined,
        sub:    pending > 0 ? `${pending} pending review` : pending === 0 && total > 0 ? 'all resolved' : undefined,
      },
      {
        label:  'Last proposal',
        value:  fmtSimTime(lastSimTime),
        colour: lastSimTime >= 0 ? VIOLET : DIM,
      },
      {
        label:  'Cadence (fast)',
        value:  '30–60 s',
        sub:    'compute, storage, generation',
      },
      {
        label:  'Cadence (slow)',
        value:  '5–60 min',
        sub:    'calibration, thermal',
      },
      {
        label:  'Execution model',
        value:  'serial (this build)',
        colour: AMBER,
        sub:    '6 agents run serially on sync urllib — §3 known gap',
      },
      {
        label:  'Token budget',
        value:  'not enforced',
        colour: AMBER,
        sub:    'soft 2.2 M / hard 15 M per site-day — not implemented',
      },
      // Per-agent last-fired row — live when tick is available
      ...AGENT_NAMES.map(name => {
        const lastT = at?.per_agent?.[name] ?? -1
        return {
          label:  name,
          value:  lastT >= 0 ? `fired ${fmtSimTime(lastT)}` : (tick ? 'armed — not yet fired' : 'armed'),
          colour: lastT >= 0 ? VIOLET : (hasAgent ? TEAL : DIM),
        }
      }),
    ]

    return {
      stateLabel,
      stateColour,
      verdict,
      heroValue,
      heroLabel,
      chartTitle: 'AGENT ACTIVITY — CADENCE FLOORS ARE WALL-CLOCK, NOT SIMULATED TIME',
      chart,
      statRows,
      secondary: undefined,
      why: [
        'Six agents analyse patterns across compute, storage, generation, renewable, thermal, and calibration domains.',
        'No agent has dispatch authority — every proposal requires a human to review and approve (§19.10).',
        'LP-1 guarantee: the dispatch path runs synchronously; agent inference runs asynchronously and never blocks staging.',
      ],
    }
  },
}
