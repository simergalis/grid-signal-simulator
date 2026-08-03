/**
 * renewable.ts — Renewable Supply subsystem panel config.
 *
 * Accent: Solar yellow #f2c94c.
 * Copy matches gridsignal-09-renewable.svg.
 *
 * Key distinction: "solar output" vs "reserve contribution" — never the same.
 * Solar is subtracted from demand (reduces the load the fleet must serve).
 * It is NEVER counted toward ramp capability. An inverter trip is a step change
 * with Δt_lead = 0. This is the "availability vs dispatchability" argument.
 *
 * Secondary section: BankFleetPanel polls GET /api/solar/state at 1.5 Hz and
 * renders the 4-feeder × 5-bank list (feeder grouping, per-bank bullet bars,
 * state classifier chips, N−1 footer).  The component is defined once outside
 * deriveData so the React reference is stable across ticks.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react'
import type { PanelConfig, PanelData } from './index'
import type { TickPayload, HistoryPoint } from '../../types'
import { TimeSeries } from '../../charts/TimeSeries'
import { BulletBar }  from '../../charts/BulletBar'

const SOLAR  = '#f2c94c'
const TEAL   = '#3fb6a8'
const RED    = '#f85149'
const AMBER  = '#f0883e'
const MUTED  = '#5a6673'

// ── Types from GET /api/solar/state ─────────────────────────────────────────

interface BankSnap {
  id: string
  feeder_id: string
  rated_mw: number
  output_mw: number
  expected_mw: number
  counted_output_mw: number
  state: 'nominal' | 'degraded' | 'out' | 'no_comms'
  reason: string | null
  strings_out: number
  strings_total: number
  inverter_temp_c: number
  telemetry_age_s: number
  operator_shutdown: boolean
}

interface FeederSnap {
  id: string
  label: string
  output_mw: number
  expected_mw: number
  bank_ids: string[]
  state: string
  operator_shutdown: boolean
}

interface Advisory {
  code: string
  scope: string
  feeder?: string
  banks?: string[]
  message: string
}

interface SolarState {
  t: number
  power: {
    p_renewable_mw:  number
    p_expected_mw:   number
    banks_reporting: number
    banks_total:     number
  }
  site: {
    plant_rated_ac_mw: number
  }
  feeders: FeederSnap[]
  banks: BankSnap[]
  exposure: {
    largest_feeder_mw: number
    largest_feeder_id: string
    largest_bank_mw: number
    plant_loss_mw: number
  }
  reserve: {
    n1_feeder: { passes: boolean; delta_p_mw: number }
    n1_bank:   { passes: boolean; delta_p_mw: number }
  }
  advisories: Advisory[]
}

// ── State colour helpers ─────────────────────────────────────────────────────

function stateColour(state: BankSnap['state']): string {
  switch (state) {
    case 'nominal':  return SOLAR
    case 'degraded': return AMBER
    case 'out':      return RED
    case 'no_comms': return MUTED
  }
}

function stateLabel(state: BankSnap['state'], reason: string | null): string {
  switch (state) {
    case 'nominal':  return 'nominal'
    case 'degraded': return reason ? reason.replace(/_/g, '\u00a0') : 'degraded'
    case 'out':      return 'out'
    case 'no_comms': return 'no\u00a0comms'
  }
}

function feederStateColour(state: string): string {
  if (state === 'nominal') return SOLAR
  if (state === 'all_out') return RED
  return AMBER
}

// ── BankFleetPanel component ─────────────────────────────────────────────────
// Defined outside deriveData so the React reference is stable across ticks and
// the useEffect polling timer is not torn down and recreated on every tick.

interface BankFleetPanelProps {
  /** Plant-level solar MW from the live WS tick — same value shown in the
   *  verdict headline.  When provided, the "Current output against rated" bar
   *  uses this instead of power.p_renewable_mw so both displays share one
   *  computation path (AT-9). */
  tickSolarMW?: number
}
function BankFleetPanel({ tickSolarMW }: BankFleetPanelProps): React.ReactElement {
  const [solar, setSolar]         = useState<SolarState | null>(null)
  const [error, setError]         = useState(false)
  const [busy, setBusy]           = useState<string | null>(null)   // kind currently in-flight
  const [flash, setFlash]         = useState<string | null>(null)   // brief result message
  const activeRef                 = useRef(true)
  const pollRef                   = useRef<() => void>(() => {})

  const poll = useCallback(async () => {
    try {
      const resp = await fetch('/api/solar/state')
      if (resp.ok && activeRef.current) {
        const data = await resp.json() as SolarState
        setSolar(data)
        setError(false)
      } else if (activeRef.current) {
        setError(true)
      }
    } catch {
      if (activeRef.current) setError(true)
    }
  }, [])

  // Keep pollRef current so inject() can call it without stale closure
  pollRef.current = poll

  useEffect(() => {
    activeRef.current = true
    poll()
    const timer = setInterval(poll, 1500)
    return () => { activeRef.current = false; clearInterval(timer) }
  }, [poll])

  const inject = useCallback(async (kind: string, target?: string) => {
    const busyKey = target ? `${kind}:${target}` : kind
    if (busy) return
    setBusy(busyKey)
    setFlash(null)
    try {
      const url = target
        ? `/api/solar/inject/${kind}?target=${encodeURIComponent(target)}`
        : `/api/solar/inject/${kind}`
      const resp = await fetch(url, { method: 'POST' })
      const data = await resp.json() as { ok: boolean; kind?: string; message?: string; error?: string }
      setFlash(data.message ?? data.error ?? (data.ok ? 'done' : 'failed'))
      // Immediate refresh so state reflects the injection without waiting 1.5 s
      await pollRef.current()
    } catch {
      setFlash('network error')
    } finally {
      setBusy(null)
      // Auto-clear flash after 4 s
      setTimeout(() => setFlash(null), 4000)
    }
  }, [busy])

  if (error) {
    return React.createElement('div', {
      className: 'font-mono text-[10px] text-muted py-2 text-center',
    }, 'Solar Array Console — server unreachable')
  }

  if (!solar) {
    return React.createElement('div', {
      className: 'font-mono text-[10px] text-muted py-2 text-center animate-pulse',
    }, 'Loading bank fleet…')
  }

  const { power, site, feeders, banks, exposure, reserve, advisories } = solar

  // ── Live output bars ─────────────────────────────────────────────────────
  // barMW is the authoritative plant total for every display on this panel.
  // When a run is active, tickSolarMW carries the WS-tick value (same source
  // as the verdict headline) so both reads are identical — AT-9 invariant.
  // Snapshot power.p_renewable_mw is used only when no tick is available
  // (standalone console view, no active run).
  const barMW    = tickSolarMW ?? power.p_renewable_mw
  const ratedMW  = site.plant_rated_ac_mw || Math.max(barMW, 5)
  const liveOutputBars = React.createElement('div', { className: 'space-y-2 mb-3' },
    React.createElement(BulletBar, {
      label:  'Current output against rated',
      value:  barMW,
      max:    ratedMW,
      colour: SOLAR,
      unit:   ` / ${ratedMW.toFixed(2)} MW`,
      note:   ratedMW > 0 && barMW / ratedMW >= 0.98
        ? 'at rated output'
        : barMW > 0
          ? `${(barMW / ratedMW * 100).toFixed(0)}% of rated`
          : 'zero output — full load falls to dispatchable sources',
    }),
    React.createElement(BulletBar, {
      label:  'If solar stopped this second',
      value:  barMW,
      max:    ratedMW,
      colour: RED,
      unit:   ` / ${ratedMW.toFixed(2)} MW`,
      note:   'POI breaker or plant-controller trip · step change · Δt_lead = 0',
    }),
  )

  // Build a map from bank ID → BankSnap for quick lookup
  const bankMap: Record<string, BankSnap> = {}
  for (const b of banks) bankMap[b.id] = b

  // ── Feeder + bank rows ────────────────────────────────────────────────────

  const feederRows = feeders.map(feeder => {
    const feederBanks = feeder.bank_ids.map(id => bankMap[id]).filter(Boolean)

    // Feeder header
    const feederHeader = React.createElement('div', {
      key: `fdr-hdr-${feeder.id}`,
      className: 'flex items-center justify-between pt-2 pb-1',
    },
      React.createElement('div', {
        className: 'flex items-center gap-1.5',
      },
        // Feeder state dot
        React.createElement('div', {
          style: {
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: feederStateColour(feeder.state),
            flexShrink: 0,
          },
        }),
        React.createElement('span', {
          className: 'font-mono text-[10px] font-bold uppercase tracking-widest',
          style: { color: feederStateColour(feeder.state) },
        }, feeder.label),
      ),
      // Feeder subtotal + operator toggle
      React.createElement('div', { className: 'flex items-center gap-2' },
        React.createElement('div', { className: 'flex items-baseline gap-1' },
          React.createElement('span', {
            className: 'font-mono text-[10px]',
            style: { color: feeder.state === 'nominal' ? SOLAR : feederStateColour(feeder.state) },
          }, `${feeder.output_mw.toFixed(3)} MW`),
          feeder.expected_mw > 0
            ? React.createElement('span', { className: 'font-mono text-[9px] text-muted' },
                `/ ${feeder.expected_mw.toFixed(3)} exp`,
              )
            : null,
        ),
        // Feeder-level operator shutdown toggle
        (() => {
          const isOff    = feeder.operator_shutdown
          const nextKind = isOff ? 'feeder_on' : 'feeder_off'
          const bKey     = `${nextKind}:${feeder.id}`
          return React.createElement('button', {
            title: isOff ? `Restore ${feeder.label}` : `Shut down ${feeder.label}`,
            disabled: busy !== null,
            onClick: () => { void inject(nextKind, feeder.id) },
            className: 'font-mono text-[8px] rounded px-1 py-0.5 shrink-0 transition-opacity',
            style: {
              background: isOff ? 'rgba(63,182,168,0.10)' : 'rgba(90,102,115,0.08)',
              border:     `1px solid ${isOff ? 'rgba(63,182,168,0.30)' : 'rgba(90,102,115,0.25)'}`,
              color:      isOff ? TEAL : MUTED,
              cursor:     busy !== null ? 'not-allowed' : 'pointer',
              opacity:    busy !== null && busy !== bKey ? 0.4 : 1,
            },
          }, busy === bKey ? '…' : (isOff ? '▶ on' : '■ off'))
        })(),
      ),
    )

    // Bank rows
    const bankRows = feederBanks.map(bank => {
      const isNoComms      = bank.state === 'no_comms'
      // counted_output_mw is already 0 for operator-offline and out/no_comms banks.
      // Using it directly means Feeder A = bank-01 + bank-02 + … by simple addition.
      const scaledOutputMW = bank.counted_output_mw
      const maxMW          = Math.max(bank.expected_mw, scaledOutputMW, 0.001)
      const dotColour      = stateColour(bank.state)
      const chipLabel      = stateLabel(bank.state, bank.reason)

      return React.createElement('div', {
        key: bank.id,
        className: 'flex items-center gap-2 py-0.5',
        style: isNoComms
          ? { border: '1px dashed rgba(90,102,115,0.4)', borderRadius: 3, padding: '2px 4px', marginBottom: 1 }
          : {},
      },
        // State dot
        React.createElement('div', {
          style: {
            width: 5,
            height: 5,
            borderRadius: '50%',
            background: dotColour,
            flexShrink: 0,
          },
        }),

        // Bank ID
        React.createElement('span', {
          className: 'font-mono text-[9px] text-muted w-[42px] shrink-0',
        }, bank.id),

        // Bullet bar (expands to fill remaining width)
        React.createElement('div', { className: 'flex-1 min-w-0' },
          isNoComms
            ? React.createElement('div', {
                style: {
                  height: 6,
                  borderRadius: 2,
                  background: 'rgba(90,102,115,0.15)',
                  border: '1px dashed rgba(90,102,115,0.3)',
                },
              })
            : React.createElement(BulletBar, {
                label:  '',
                value:  scaledOutputMW,
                max:    maxMW,
                colour: dotColour,
                unit:   '',
                dense:  true,
              }),
        ),

        // MW value
        React.createElement('span', {
          className: 'font-mono text-[9px] w-[38px] text-right shrink-0',
          style: { color: isNoComms ? MUTED : dotColour },
        }, isNoComms ? '—' : `${scaledOutputMW.toFixed(3)}`),

        // State chip
        React.createElement('span', {
          className: 'font-mono text-[8px] w-[46px] text-right shrink-0',
          style: { color: bank.operator_shutdown ? MUTED : dotColour },
        }, bank.operator_shutdown ? 'offline' : chipLabel),

        // Per-bank operator shutdown toggle
        (() => {
          const isOff    = bank.operator_shutdown
          const nextKind = isOff ? 'bank_on' : 'bank_off'
          const bKey     = `${nextKind}:${bank.id}`
          return React.createElement('button', {
            title:    isOff ? `Restore ${bank.id}` : `Shut down ${bank.id}`,
            disabled: busy !== null,
            onClick:  () => { void inject(nextKind, bank.id) },
            className: 'font-mono text-[8px] rounded px-1 py-0.5 shrink-0 transition-opacity',
            style: {
              background: isOff ? 'rgba(63,182,168,0.10)' : 'rgba(90,102,115,0.07)',
              border:     `1px solid ${isOff ? 'rgba(63,182,168,0.30)' : 'rgba(90,102,115,0.22)'}`,
              color:      isOff ? TEAL : MUTED,
              cursor:     busy !== null ? 'not-allowed' : 'pointer',
              opacity:    busy !== null && busy !== bKey ? 0.35 : 1,
              minWidth:   22,
            },
          }, busy === bKey ? '…' : (isOff ? '▶' : '■'))
        })(),
      )
    })

    return React.createElement('div', {
      key: feeder.id,
      className: 'border-t border-border',
    },
      feederHeader,
      ...bankRows,
    )
  })

  // ── N−1 footer ────────────────────────────────────────────────────────────

  const n1Label = exposure.largest_feeder_id
    ? exposure.largest_feeder_id.replace('fdr-', 'Feeder ')
    : 'largest feeder'

  const n1Passes  = reserve.n1_feeder?.passes ?? true
  const n1MW      = exposure.largest_feeder_mw ?? 0

  const n1Footer = React.createElement('div', {
    className: 'border-t border-border mt-1 pt-2 flex items-center justify-between',
  },
    React.createElement('div', { className: 'flex items-center gap-1' },
      React.createElement('span', {
        className: 'font-mono text-[9px] uppercase tracking-wider text-muted',
      }, 'N\u22121 exposure:'),
      React.createElement('span', {
        className: 'font-mono text-[9px]',
        style: { color: n1Passes ? SOLAR : RED },
      }, `${n1Label} · ${n1MW.toFixed(3)} MW`),
    ),
    React.createElement('span', {
      className: 'font-mono text-[8px] rounded px-1.5 py-0.5',
      style: {
        background: n1Passes ? 'rgba(63,182,168,0.12)' : 'rgba(248,81,73,0.12)',
        color:      n1Passes ? TEAL : RED,
        border: `1px solid ${n1Passes ? 'rgba(63,182,168,0.3)' : 'rgba(248,81,73,0.3)'}`,
      },
    }, n1Passes ? 'reserve OK' : 'reserve gap'),
  )

  // ── Advisory strip ────────────────────────────────────────────────────────

  const advisoryStrip = advisories.length > 0
    ? React.createElement('div', {
        className: 'border-t border-border mt-1 pt-2 space-y-1',
      },
        ...advisories.map((adv, i) =>
          React.createElement('div', {
            key: i,
            className: 'flex items-start gap-1.5',
          },
            React.createElement('span', {
              className: 'font-mono text-[8px] px-1 py-0.5 rounded shrink-0',
              style: {
                background: 'rgba(240,136,62,0.12)',
                border: '1px solid rgba(240,136,62,0.3)',
                color: AMBER,
              },
            }, adv.code === 'common_cause' ? 'COMMON CAUSE' : 'RECON'),
            React.createElement('span', {
              className: 'font-mono text-[9px] leading-relaxed',
              style: { color: AMBER },
            }, adv.message),
          ),
        ),
      )
    : null

  // ── Fault injection strip ──────────────────────────────────────────────────

  type Btn = { kind: string; label: string; colour: string; bg: string; border: string }
  const INJECT_BUTTONS: Btn[] = [
    { kind: 'bank_trip',   label: 'Trip bank',      colour: AMBER, bg: 'rgba(240,136,62,0.10)', border: 'rgba(240,136,62,0.35)' },
    { kind: 'feeder_open', label: 'Open Feeder B',  colour: AMBER, bg: 'rgba(240,136,62,0.10)', border: 'rgba(240,136,62,0.35)' },
    { kind: 'comms_loss',  label: 'Comms loss',     colour: AMBER, bg: 'rgba(240,136,62,0.10)', border: 'rgba(240,136,62,0.35)' },
    { kind: 'reset',       label: 'Reset',          colour: TEAL,  bg: 'rgba(63,182,168,0.10)', border: 'rgba(63,182,168,0.35)' },
  ]

  const injectionStrip = React.createElement('div', {
    className: 'border-t border-border mt-1 pt-2',
  },
    // Label row
    React.createElement('div', {
      className: 'font-mono text-[8px] uppercase tracking-widest mb-1.5',
      style: { color: MUTED },
    }, 'Fault injection'),
    // Button row
    React.createElement('div', { className: 'flex flex-wrap gap-1' },
      ...INJECT_BUTTONS.map(btn =>
        React.createElement('button', {
          key: btn.kind,
          disabled: busy !== null,
          onClick: () => { void inject(btn.kind) },
          className: 'font-mono text-[9px] rounded px-2 py-0.5 transition-opacity',
          style: {
            background: btn.bg,
            border: `1px solid ${btn.border}`,
            color: busy === btn.kind ? MUTED : btn.colour,
            cursor: busy !== null ? 'not-allowed' : 'pointer',
            opacity: busy !== null && busy !== btn.kind ? 0.45 : 1,
          },
        }, busy === btn.kind ? '…' : btn.label),
      ),
    ),
    // Flash message
    flash
      ? React.createElement('div', {
          className: 'font-mono text-[9px] mt-1.5 leading-snug',
          style: { color: flash.includes('error') || flash.includes('fail') ? RED : TEAL },
        }, flash)
      : null,
  )

  return React.createElement('div', { className: 'mt-2 pt-2 space-y-0' },
    liveOutputBars,
    // Section header
    React.createElement('div', {
      className: 'flex items-baseline justify-between mb-1',
    },
      React.createElement('div', {
        className: 'font-mono text-[9px] font-bold uppercase tracking-[0.14em]',
        style: { color: MUTED },
      }, 'BANK FLEET — LIVE'),
      React.createElement('div', {
        className: 'font-mono text-[9px] text-muted',
      }, (() => {
        const offlineCount = banks.filter(b => b.operator_shutdown).length
        const reporting    = banks.filter(b => !b.operator_shutdown && b.state !== 'no_comms').length
        if (offlineCount > 0) {
          // Denominator is always banks_total so the scale of the outage is visible
          return `${reporting} / ${banks.length} reporting · ${offlineCount} operator-offline`
        }
        return `${reporting} / ${banks.length} reporting`
      })()),
    ),
    ...feederRows,
    n1Footer,
    injectionStrip,
    advisoryStrip,
  )
}

// ── Panel config ─────────────────────────────────────────────────────────────

export const renewablePanel: PanelConfig = {
  deriveData(tick: TickPayload | null, _alert, history: HistoryPoint[]): PanelData {
    if (!tick) {
      return {
        stateLabel:  'ADVISORY',
        stateColour: '#5a6673',
        verdict:     'Non-dispatchable — subtracts from demand, never closes a gap.',
        heroValue:   '—',
        heroLabel:   'MW, uncounted',
        chartTitle:  'CONTRIBUTION, AND EXPOSURE IF IT STOPS',
        chart: React.createElement('div', { className: 'font-mono text-xs text-muted py-12 text-center' }, 'No data'),
        statRows: [],
        why: [
          'Renewable output is subtracted from the load generators and the battery must serve.',
          'It is never added to ramp capability — it cannot be commanded, and carries no lead time on loss.',
          'A 5 MW solar collapse and a 5 MW compute spike are the same event to the arbitrator.',
        ],
      }
    }

    const solarMW    = tick.p_renewable_mw        // three-tier bank aggregation (AT-9)
    const totalMW    = tick.p_total_mw            // compute + cooling (gross site draw)
    // Recompute from the aggregated solar value — do not read tick.net_demand_mw
    // which was computed pre-fix from rated_mw * fraction (AT-11).
    const netDemand  = Math.max(0, totalMW - solarMW)
    // Share: solar exceeds draw only when strictly greater (not >=), so that
    // 100% = exactly equal does not fabricate a BESS-absorption message (AT-12).
    const solarExceedsDraw = totalMW > 0 && solarMW > totalMW
    const sharePct = totalMW > 0
      ? Math.min(100, solarMW / totalMW * 100).toFixed(0)
      : '0'
    const shareDisplay = solarExceedsDraw ? '≥ 100%' : `${sharePct}%`
    const shareNote    = solarExceedsDraw
      ? 'solar exceeds current draw · surplus absorbed by BESS'
      : 'at current compute load'

    const chart = React.createElement(TimeSeries, {
      series: [
        { label: 'solar output',                colour: SOLAR, points: history.map(h => ({ x: h.sim_time_seconds, y: h.p_renewable_mw })), filled: true },
        { label: 'dispatch required with solar', colour: TEAL,  points: history.map(h => ({ x: h.sim_time_seconds, y: h.confidence_lower_mw })) },
        { label: 'if solar vanished',            colour: RED,   points: history.map(h => ({ x: h.sim_time_seconds, y: h.p_total_mw })) },
      ],
      xLabel:  'seconds from run start',
      height:  200,
    })

    // BankFleetPanel owns the bars (uses snapshot physics) and the
    // live bank fleet.  Passing solarMW keeps bars in lock-step with the hero.
    // Pass the tick-derived solarMW so the bar and the verdict share one value.
    const secondary = React.createElement(BankFleetPanel, { tickSolarMW: solarMW })

    return {
      stateLabel:  'ADVISORY',
      stateColour: '#5a6673',
      verdict:     solarMW > 0
        ? `Contributing ${solarMW.toFixed(2)} MW — and it can vanish with no warning.`
        : 'No renewable output. Dispatch required equals total load.',
      heroValue:  solarMW.toFixed(2),
      heroLabel:  'MW, uncounted',
      chartTitle: 'CONTRIBUTION, AND EXPOSURE IF IT STOPS',
      chart,
      statRows: [
        { label: 'Output',                  value: `${solarMW.toFixed(2)} MW`, sub: 'real-time · instantaneous' },
        // net_demand_mw is the live interpolated field the fleet must cover after solar
        // offset — it changes visibly as compute ramps from idle (near 0) to full draw
        { label: 'Generators and battery covering', value: `${netDemand.toFixed(2)} MW`, colour: netDemand > 0 ? TEAL : SOLAR, sub: 'net demand after solar offset · live' },
        { label: 'Share of what the site is using', value: shareDisplay, sub: shareNote },
        // Solar weather forecast from Mistral — constant per run, stamped on every tick.
        // weather label drives the colour: physics_estimate shown in muted grey.
        (() => {
          const w = tick.solar_weather
          const c = tick.solar_conditions
          if (!w || w === 'physics_estimate') {
            return { label: 'Conditions', value: 'Physics estimate', sub: 'San Diego baseline — Mistral unavailable', colour: '#5a6673' }
          }
          const label = w.replace(/_/g, ' ')
          return { label: 'Conditions', value: label, sub: c || 'Mistral solar forecast · San Diego', colour: SOLAR }
        })(),
        // PROTO-32-AMB: ambient temperature row — hidden when ambient_avg_c is 0
        // (no solar forecast was generated for this run, so the adjustment is absent).
        ...(tick.ambient_avg_c > 0 ? [(() => {
          const pct = (tick.ambient_alpha_scale - 1) * 100
          const sign = pct >= 0 ? '+' : ''
          const adj = Math.abs(pct) < 0.1
            ? 'cooling nominal (19 °C baseline)'
            : `cooling ${sign}${pct.toFixed(0)} % vs 19 °C baseline`
          return { label: 'Ambient temp', value: `${tick.ambient_avg_c.toFixed(1)} °C avg`, sub: adj, colour: pct > 0 ? AMBER : TEAL }
        })()] : []),
        { label: 'Counted toward reserve',  value: 'never', colour: AMBER, sub: 'availability, not dispatchability · §7.1.1' },
        { label: 'Control surface',         value: 'none', sub: 'passive collector — nothing to command' },
        { label: 'Lead time on loss',       value: '0 s', colour: RED, sub: 'no advance signal exists' },
        { label: 'Forecast treatment',      value: 'subtracted', sub: 'reduces demand, never closes a gap' },
        { label: 'Agent authority',         value: 'advisory only', sub: 'by construction — no dispatch path' },
      ],
      secondary,
      why: [
        'Renewable output is subtracted from the load generators and the battery must serve.',
        'It is never added to ramp capability, because it cannot be commanded and carries no lead time on loss.',
        `Generators and battery are covering ${netDemand.toFixed(1)} MW right now. A ${solarMW.toFixed(1)} MW solar collapse instantly adds ${solarMW.toFixed(1)} MW to that figure with no advance warning.`,
      ],
    }
  },
}
