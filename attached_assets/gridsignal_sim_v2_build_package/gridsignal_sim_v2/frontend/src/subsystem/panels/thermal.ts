/**
 * thermal.ts — Thermal & Cooling subsystem panel config.
 *
 * Accent: Battery blue #4a9fe0.
 * Copy matches gridsignal-10-thermal.svg.
 *
 * The 90-second lag is the product argument: compute spike and cooling rise are
 * two separate events. A reactive system meets each one after it arrives, and
 * meets the second having already spent its ramp on the first.
 */

import React from 'react'
import type { PanelConfig, PanelData } from './index'
import type { TickPayload, HistoryPoint } from '../../types'
import { TimeSeries } from '../../charts/TimeSeries'
import { BulletBar }  from '../../charts/BulletBar'

const BATTERY = '#4a9fe0'
const TEAL    = '#3fb6a8'
const AMBER   = '#f0883e'

// GS-DES-CFG-001 §Phase-3: no module-scope numeric constants.
// DT_THERMAL_S and ALPHA_MAX are derived from tick.dt_thermal_seconds and tick.alpha_max.

function fmtTime(s: number): string {
  if (s >= 86400) return '—'
  if (s >= 3600)  return `${(s / 3600).toFixed(1)} h`
  if (s >= 60)    return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
  return `${s.toFixed(0)} s`
}

export const thermalPanel: PanelConfig = {
  deriveData(tick: TickPayload | null, _alert, history: HistoryPoint[]): PanelData {
    if (!tick) {
      return {
        stateLabel:  '—',
        stateColour: '#30363d',
        verdict:     'No active run. Start a scenario to see thermal readiness.',
        heroValue:   '—',
        heroLabel:   'MW absorbable',
        chartTitle:  'THE 90-SECOND LAG — TWO EVENTS, NOT ONE',
        chart: React.createElement('div', { className: 'font-mono text-xs text-muted py-12 text-center' }, 'No data'),
        statRows: [],
        why: [
          'A compute step and its cooling response are two separate events roughly 90 seconds apart.',
          'A reactive controller meets each one after it arrives, and meets the second having already spent its ramp on the first.',
          'The lag is why one threshold cannot work.',
        ],
      }
    }

    const absorbMW  = tick.absorbable_mw
    const ratedMW   = tick.rated_cooling_mw
    const fraction  = ratedMW > 0 ? absorbMW / ratedMW : 1
    const limitTime = tick.time_to_limit_s
    const approach  = tick.approach_rate_mw_s
    const lowHdr    = fraction < 0.05

    // GS-DES-CFG-001 §Phase-4: thermal site parameters now on TickPayload.
    // dt_thermal_seconds: base thermal lag — SiteConfig value, unscaled.
    // alpha_max: base cooling fraction — SiteConfig value, NOT × ambient_alpha_scale.
    //   ambient_alpha_scale (already on wire) is the FACTOR; a panel must keep
    //   base and effective clearly separate to avoid misleading during heat stress.
    const dtThermalS = tick.dt_thermal_seconds    // base thermal lag from SiteConfig (s)
    const alphaMax   = tick.alpha_max             // base α_max from SiteConfig
    const alphaEff   = alphaMax * tick.ambient_alpha_scale  // effective (with ambient scaling)

    // GS-DES-CFG-001 §Phase-5 / Item-1: the ratio ratedMW / (alphaMax × p_compute)
    // algebraically recovers the factory sizing margin (_COOLING_MARGIN = 1.15 in
    // scenario_factory.py tagged PROTO-10-MARGIN).  This is a circular round-trip,
    // not a derivation — it reads 15% because the demo plant was sized that way, and
    // at low compute the ratio inflates without bound.  The margin is a design
    // parameter (PROTO-10), not a runtime observation.  Sub-label removed.

    const stateLabel  = lowHdr ? 'ATTENTION' : 'READY'
    const stateColour = lowHdr ? AMBER : '#3fb6a8'

    const chart = React.createElement(TimeSeries, {
      series: [
        { label: 'compute draw', colour: TEAL,    points: history.map(h => ({ x: h.sim_time_seconds, y: h.p_compute_mw })) },
        { label: 'cooling draw', colour: BATTERY, points: history.map(h => ({ x: h.sim_time_seconds, y: h.p_cooling_mw })), filled: true },
      ],
      ceiling: ratedMW > 0 ? { y: ratedMW, label: 'rated ceiling', colour: '#d9534f' } : undefined,
      xLabel:  'seconds from run start',
      height:  200,
    })

    const secondary = React.createElement('div', { className: 'space-y-2' },
      React.createElement(BulletBar, {
        label:  'Absorbable before approach to limit',
        value:  absorbMW,
        max:    ratedMW > 0 ? ratedMW : absorbMW + 1,
        colour: BATTERY,
        unit:   ' MW',
        note:   ratedMW > 0
          ? `full headroom at rest. Rated ceiling ${ratedMW.toFixed(2)} MW.`
          : 'rated capacity not available in this tick',
      }),
      React.createElement(BulletBar, {
        // GS-DES-CFG-001 §Phase-4/§Phase-5 / Item-2: α_max bar rescaled against catalogue maximum.
        // max = 30 (catalogue alpha_max max = 0.3 = 30%;
        //   gridsignal_parameters.json adjustable alpha_max max=0.3, spec_ref v2.5 §8).
        // Justification: base α_max (20%) sits at 2/3 of full scale; as ambient stress
        //   pushes alphaEff toward the catalogue ceiling (30%), the bar approaches 100% —
        //   a defined physical event, not an arbitrary endpoint.  With max=100 the full
        //   operating range was a thin sliver and ambient-stress displacement was invisible.
        // value: effective fraction (base × ambient_alpha_scale) as %.
        // target: base fraction (α_max alone) as % — SiteConfig nameplate.
        label:  'Steady-state cooling as fraction of compute',
        value:  Math.round(alphaEff * 1000) / 10,    // effective % (with ambient scale)
        max:    30,                                   // catalogue maximum for alpha_max (30%)
        target: Math.round(alphaMax * 1000) / 10,    // base % (SiteConfig nameplate)
        colour: BATTERY,
        unit:   '%',
        note:   `base α_max ${(alphaMax * 100).toFixed(1)}% · ambient scale ×${tick.ambient_alpha_scale.toFixed(2)} → effective ${(alphaEff * 100).toFixed(1)}%`,
      }),
    )

    return {
      stateLabel,
      stateColour,
      verdict: lowHdr
        ? `Low headroom — only ${absorbMW.toFixed(2)} MW absorbable before approach.`
        : `Full headroom — ${absorbMW.toFixed(2)} MW absorbable before approach.`,
      heroValue:  absorbMW.toFixed(2),
      heroLabel:  'MW absorbable',
      // GS-DES-CFG-001 §Phase-5 / Item-4 (stale): chartTitle used hardcoded "90".
      // dt_thermal_seconds is now on the wire — use it so the title matches the
      // actual configured lag (catalogue range 60–120 s; default 90 s).
      chartTitle: `THE ${tick.dt_thermal_seconds.toFixed(0)}-SECOND LAG — TWO EVENTS, NOT ONE`,
      chart,
      statRows: [
        { label: 'Plant load',       value: `${tick.p_cooling_mw.toFixed(2)} MW`, sub: tick.p_compute_mw === 0 ? 'no compute running' : undefined },
        { label: 'Rated capacity',   value: ratedMW > 0 ? `${ratedMW.toFixed(2)} MW` : 'not instrumented' },
        { label: 'Absorbable now',   value: `${absorbMW.toFixed(2)} MW`, colour: lowHdr ? AMBER : '#3fb6a8', sub: 'additional load before approach' },
        { label: 'Time to limit',    value: fmtTime(limitTime), sub: limitTime >= 86400 ? 'no approach in progress' : 'at current approach rate' },
        { label: 'Approach rate',    value: `${approach.toFixed(3)} MW/s`, sub: 'rate of headroom consumption' },
        {
          label: 'Unserved load',
          value: tick.p_cooling_unserved_mw != null ? `${tick.p_cooling_unserved_mw.toFixed(2)} MW` : '—',
          colour: (tick.p_cooling_unserved_mw ?? 0) > 0.01 ? AMBER : undefined,
          sub: 'cooling\'s pro-rata share of any site-wide generation shortfall — not a chiller fault',
        },
        { label: 'Δt_thermal',       value: dtThermalS > 0 ? `${dtThermalS.toFixed(0)} s` : 'not populated', sub: 'base thermal lag — from SiteConfig, unscaled' },
        { label: 'τ rise constant',  value: '20 s', sub: 'first-order settling — catalogue default (tau min=10, max=40 s) · not broadcast on tick' },
        { label: 'Pre-staging',      value: 'not configured', sub: 'shiftable load unavailable in this scenario' },
      ],
      secondary,
      why: [
        // GS-DES-CFG-001 §Phase-5 / Item-4 (stale): was hardcoded "90 seconds".
        // dt_thermal_seconds is now on the wire (catalogue default 90 s, range 60–120 s).
        `A compute step and its cooling response are two separate events roughly ${tick.dt_thermal_seconds.toFixed(0)} s apart.`,
        'A reactive controller meets each one after it arrives, and meets the second having already spent its ramp on the first.',
        'The lag is why one threshold cannot work — GridSignal reads the scheduler queue before any current flows.',
        'The "Unserved load" figure is not a cooling failure. When the plant runs short of total generation, ' +
        'the shortfall is split across compute and cooling in proportion to how much each draws. ' +
        'Cooling has no internal capacity limit that triggers this number — if the plant has enough power, it always reads zero.',
      ],
    }
  },
}
