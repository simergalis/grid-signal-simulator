/**
 * gcc.ts — Generation Commitment Controller (GCC) subsystem panel.
 *
 * Accent: Gold #e0a458 — GCC drives generation dispatch decisions.
 *
 * The GCC monitors fleet utilisation each tick and decides whether to:
 *   "commit"   — fire command_start() on the next available standby unit
 *   "hold"     — current fleet is sufficient; no action
 *   "decommit" — excess capacity; shut down an on-bus unit
 *
 * Data source: tick.commitment_block (Phase E+ backend field).
 */

import React from 'react'
import type { PanelConfig, PanelData } from './index'
import type { TickPayload, HistoryPoint } from '../../types'
import { BulletBar } from '../../charts/BulletBar'

type GccEvent = { ts: string; body: string }

const GOLD   = '#e0a458'
const TEAL   = '#3fb6a8'
const BLUE   = '#4a9fe0'
const RED    = '#d9534f'
const MUTED  = '#5a6673'

// Commit utilisation threshold matches commitment.py default (0.80).
const COMMIT_UTIL_THRESHOLD = 0.80

function pct(v: number): string { return `${(v * 100).toFixed(1)} %` }
function fmtMW(v: number): string { return `${v.toFixed(2)} MW` }

function actionColour(action: string): string {
  if (action === 'commit')   return GOLD
  if (action === 'decommit') return BLUE
  return TEAL  // hold
}

function actionLabel(action: string): string {
  if (action === 'commit')   return 'COMMITTING'
  if (action === 'decommit') return 'DECOMMITTING'
  return 'HOLDING'
}

const _MONO = { fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace" }
const _SANS = { fontFamily: 'Inter,system-ui,sans-serif' }

function renderEventLog(events: GccEvent[]): React.ReactElement {
  if (events.length === 0) {
    return React.createElement('div', {
      style: { ..._MONO, fontSize: 10, color: '#3a4a58', padding: '10px 0', textAlign: 'center' },
    }, 'No GCC decisions recorded this run.')
  }
  // Show most-recent first
  const reversed = [...events].reverse()
  return React.createElement('div', {
    style: {
      display: 'flex', flexDirection: 'column', gap: 6,
      maxHeight: 240, overflowY: 'auto',
      paddingRight: 2, scrollbarWidth: 'thin', scrollbarColor: '#2a3a4a transparent',
    },
  }, ...reversed.map((ev, i) =>
    React.createElement('div', {
      key: i,
      style: {
        display: 'flex', flexDirection: 'column', gap: 2,
        borderLeft: `2px solid ${i === 0 ? '#2a5060' : '#1e2a36'}`,
        paddingLeft: 8,
      },
    },
      React.createElement('span', {
        style: { ..._MONO, fontSize: 8, color: '#3a5a6a', lineHeight: 1.4 },
      }, ev.ts),
      React.createElement('span', {
        style: { ..._SANS, fontSize: 10, color: i === 0 ? '#c8d6e5' : '#4b5764', lineHeight: 1.5 },
      }, ev.body),
    )
  ))
}

export const gccPanel: PanelConfig = {
  deriveData(tick: TickPayload | null, _alert, _history: HistoryPoint[], extra?: unknown): PanelData {
    const events = (Array.isArray(extra) ? extra : []) as GccEvent[]

    if (!tick) {
      return {
        stateLabel:  '—',
        stateColour: MUTED,
        verdict:     'No active run. Start a scenario to see GCC decisions.',
        heroValue:   '—',
        heroLabel:   'fleet utilisation',
        chartTitle:  'COMMITMENT DECISION',
        chart: React.createElement('div', {
          style: { fontFamily: "'SF Mono',Menlo,monospace", fontSize: 10,
                   color: '#3a4a58', padding: '24px 0', textAlign: 'center' }
        }, 'No data'),
        statRows: [
          { label: 'Last action',       value: '—' },
          { label: 'Reason',            value: '—' },
          { label: 'Fleet utilisation', value: '—' },
          { label: 'Committed rated',   value: '—' },
          { label: 'Reserve floor',     value: '—', sub: 'N-1 floor — p_demand + largest unit' },
          { label: 'Reserve satisfied', value: '—' },
          { label: 'Pending start',     value: '—' },
        ],
        secondary: React.createElement('div', null,
          React.createElement('div', {
            style: { ..._MONO, fontSize: 9, color: '#3a5a6a', letterSpacing: '0.08em',
                     textTransform: 'uppercase', marginBottom: 6 },
          }, 'GCC EVENT LOG'),
          renderEventLog(events),
        ),
        why: [
          'The GCC monitors fleet utilisation each tick and fires command_start() when it exceeds the commit threshold.',
          'The N-1 reserve floor ensures enough on-bus capacity to survive the sudden loss of the largest committed unit.',
          'Start a scenario to see live commitment decisions.',
        ],
      }
    }

    const cb = tick.commitment_block

    // Safe defaults when commitment_block is null (pre-Phase-E+ backend).
    const action        = cb?.action              ?? 'hold'
    const reason        = cb?.reason              ?? '—'
    const blockedBy     = cb?.blocked_by          ?? ''
    const targetUnit    = cb?.target_unit_id      ?? null
    const committedMW   = cb?.committed_rated_mw  ?? 0
    const reserveFloor  = cb?.reserve_floor_mw    ?? 0
    const reserveOk     = cb?.reserve_satisfied   ?? true
    const utilisation   = cb?.utilisation         ?? 0
    const pendingUnit   = cb?.pending_start_unit_id ?? null

    const colour = actionColour(action)

    // ── Verdict ──────────────────────────────────────────────────────────────
    let verdict = ''
    if (action === 'commit') {
      verdict = targetUnit
        ? `Committing ${targetUnit} — ${reason}.`
        : `Committing a standby unit — ${reason}.`
    } else if (action === 'decommit') {
      verdict = targetUnit
        ? `Releasing ${targetUnit} — ${reason}.`
        : `Releasing an on-bus unit — ${reason}.`
    } else {
      verdict = `Holding — ${reason}.`
      if (blockedBy) verdict += ` Blocked by: ${blockedBy}.`
    }

    // ── Chart — two BulletBars ───────────────────────────────────────────────
    const chart = React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 10, padding: '6px 0' } },
      // Utilisation vs commit threshold
      React.createElement(BulletBar, {
        label:  'Fleet utilisation',
        value:  utilisation * 100,
        max:    100,
        target: COMMIT_UTIL_THRESHOLD * 100,
        colour: colour,
        unit:   ' %',
        note:   `Red marker = commit threshold (${pct(COMMIT_UTIL_THRESHOLD)}). Above this the GCC fires command_start() on the next available standby unit.`,
      }),
      // Committed rated vs reserve floor
      React.createElement(BulletBar, {
        label:  'Committed rated MW vs N-1 floor',
        value:  committedMW,
        max:    Math.max(committedMW, reserveFloor, 1),
        target: reserveFloor,
        colour: reserveOk ? TEAL : RED,
        unit:   ' MW',
        note:   `Red marker = N-1 reserve floor (${fmtMW(reserveFloor)}). Committed rated (${fmtMW(committedMW)}) must exceed this floor to satisfy contingency coverage.`,
      }),
    )

    // ── Stat rows ────────────────────────────────────────────────────────────
    const statRows = [
      { label: 'Last action',
        value: action.toUpperCase(),
        colour: colour },
      { label: 'Reason',
        value: reason,
        sub: blockedBy ? `blocked by: ${blockedBy}` : undefined },
      { label: 'Fleet utilisation',
        value: pct(utilisation),
        colour: utilisation >= COMMIT_UTIL_THRESHOLD ? GOLD : TEAL,
        sub: `threshold ${pct(COMMIT_UTIL_THRESHOLD)}` },
      { label: 'Committed rated MW',
        value: fmtMW(committedMW),
        sub: 'Σ rated_mw for SYNCHRONISED units only' },
      { label: 'Reserve floor (N-1)',
        value: fmtMW(reserveFloor),
        sub: 'p_demand + largest committed unit' },
      { label: 'Reserve satisfied',
        value: reserveOk ? 'YES' : 'NO',
        colour: reserveOk ? TEAL : RED },
      { label: 'Pending start',
        value: pendingUnit ?? '—',
        sub: pendingUnit ? 'unit currently in STARTING state' : 'no unit starting' },
      { label: 'Ramp credit',
        value: tick.turbine_ramp_credit_mw > 0 ? fmtMW(tick.turbine_ramp_credit_mw) : '—',
        sub: tick.turbine_ramp_credit_mw > 0
          ? `of ${fmtMW(tick.confidence_upper_mw)} forecast step`
          : 'no active ramp' },
    ]

    // ── Secondary — GCC event log ────────────────────────────────────────────
    const secondary = React.createElement('div', null,
      React.createElement('div', {
        style: { ..._MONO, fontSize: 9, color: '#3a5a6a', letterSpacing: '0.08em',
                 textTransform: 'uppercase', marginBottom: 6 },
      }, `GCC EVENT LOG — ${events.length} decision${events.length !== 1 ? 's' : ''} this run`),
      renderEventLog(events),
    )

    return {
      stateLabel:  actionLabel(action),
      stateColour: colour,
      verdict,
      heroValue:   pct(utilisation),
      heroLabel:   'fleet utilisation',
      chartTitle:  'COMMITMENT DECISION — UTILISATION & RESERVE',
      chart,
      statRows,
      secondary,
      why: [
        `The GCC fires command_start() when fleet utilisation exceeds ${pct(COMMIT_UTIL_THRESHOLD)} — ensuring a standby unit is spinning before the step-load peaks.`,
        `The N-1 reserve floor (${fmtMW(reserveFloor)}) is the minimum committed capacity needed to survive the loss of the largest on-bus unit without shedding load.`,
        `Ramp credit (${fmtMW(tick.turbine_ramp_credit_mw)}) is the MW a starting turbine can deliver by the time the step arrives — the BESS bridges the remainder.`,
      ],
    }
  },
}
