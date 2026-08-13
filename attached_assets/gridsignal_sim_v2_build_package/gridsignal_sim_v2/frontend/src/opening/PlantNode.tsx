/**
 * PlantNode.tsx — one node in the one-line plant mimic diagram.
 *
 * Rendered as an SVG <foreignObject> so it lives in the same coordinate
 * space as the flow lines.  Tailwind classes work normally inside.
 *
 * Rules:
 *   · Clickable nodes show a › chevron (top-right).
 *   · Passive nodes (Distribution, PDU) have no chevron and no pointer cursor.
 *   · Grid connection is dashed + grey: islanded by design, never red.
 *   · A coloured state dot appears next to the MW value when active.
 *   · Solar PV node shows a weather badge when solarPreview is provided.
 */

import type { NodeDef } from './plantLayout'
import type { TickPayload, TurbineUnitSpec } from '../types'
import { InfoBtn } from './TileTooltip'

/** Weather preview data from GET /solar-preview */
export interface SolarPreview {
  weather:           string   // "clear" | "partly_cloudy" | "overcast" | "marine_layer" | "physics_estimate"
  conditions:        string   // human-readable sentence
  source:            string   // "mistral" | "physics"
  local_time:        string   // "HH:MM" local time
  // Task-75 additions — sun position and expected output at preview time
  sun_elevation_deg: number   // degrees; negative = below horizon
  expected_fraction: number   // physics fraction [0, 1]
  lat:               number   // site latitude degrees North
  utc_offset_h:      number   // DST-aware UTC offset used for computation
  plant_rated_ac_mw: number   // AC rated capacity in MW
}

/**
 * Compute real-time sun elevation angle in degrees.
 * Matches the Python _sun_elevation_deg() physics in api/routes/solar.py.
 * Returns negative values when the sun is below the horizon.
 */
function computeSunElevationDeg(lat: number, utcOffsetH: number): number {
  const now = new Date()
  const utcH = now.getUTCHours() + now.getUTCMinutes() / 60 + now.getUTCSeconds() / 3600
  const localH = ((utcH + utcOffsetH) % 24 + 24) % 24
  const hourAngleRad = ((localH - 12.0) * 15.0) * Math.PI / 180
  // Day of year
  const startOfYear = Date.UTC(now.getUTCFullYear(), 0, 1)
  const dayOfYear = Math.floor((now.getTime() - startOfYear) / 86_400_000) + 1
  const declRad = 23.45 * Math.sin((360.0 / 365.0 * (dayOfYear - 81)) * Math.PI / 180) * Math.PI / 180
  const latRad = lat * Math.PI / 180
  const sinElev = (
    Math.sin(latRad) * Math.sin(declRad)
    + Math.cos(latRad) * Math.cos(declRad) * Math.cos(hourAngleRad)
  )
  return Math.asin(Math.max(-1.0, Math.min(1.0, sinElev))) * 180 / Math.PI
}

interface PlantNodeProps {
  def: NodeDef
  tick: TickPayload | null
  onClick?: (nodeId: string) => void
  /** Optional solar forecast preview — only consumed by the solar-pv node. */
  solarPreview?: SolarPreview | null
  /**
   * Live solar MW polled from GET /api/solar/state at 1.5 Hz.
   * When provided, the Solar PV tile prefers this over tick.p_renewable_mw so
   * the tile stays in sync with the Renewable Supply modal and reflects the
   * real-time SolarSim aggregate rather than a stale WebSocket tick value.
   */
  liveSolarMW?: number | null
}

function getMwValue(def: NodeDef, tick: TickPayload | null): number | null {
  if (!def.mwField) return null
  // No tick: use staticMW if defined so nodes show configured capacity at rest.
  // Keep "—" only for nodes that have no meaningful pre-run value (no staticMW).
  if (!tick) return def.staticMW ?? null
  return (tick as unknown as Record<string, unknown>)[def.mwField] as number
}

/** Subtle detail lines shown inside each node. */
function nodeDetail(
  def: NodeDef,
  tick: TickPayload | null,
  solarPreview?: SolarPreview | null,
): string {
  switch (def.id) {
    case 'gas-turbine': {
      const units = tick?.turbine_units ?? []
      if (units.length === 0) return 'fleet — start a scenario to see units'
      const installed = units.reduce((s: number, u: { rated_mw: number }) => s + u.rated_mw, 0)
      const maxUnit   = Math.max(...units.map((u: { rated_mw: number }) => u.rated_mw))
      const n1Firm    = installed - maxUnit
      const online    = (tick as any)?.units_on_bus_count ?? 0

      // Classify non-bus units by thermal_state into the three standby tiers.
      // "On bus" = state is synchronised/unloading; or (no live state) breaker closed and not hot_standby.
      const standby = { hot: 0, warm: 0, cold: 0 }
      for (const u of units as TurbineUnitSpec[]) {
        const s = u.state
        const onBus = s
          ? (s === 'synchronised' || s === 'unloading')
          : (u.breaker_closed && !u.hot_standby)
        if (!onBus) {
          const t = u.thermal_state ?? 'cold'
          if (t === 'hot')       standby.hot++
          else if (t === 'warm') standby.warm++
          else                   standby.cold++
        }
      }

      const fleetLine   = `${units.length} unit${units.length === 1 ? '' : 's'} · ${online} online · N−1 firm ${n1Firm.toFixed(1)} MW`
      const standbyLine = `${standby.hot} hot standby · ${standby.warm} warm standby · ${standby.cold} cold standby`
      return `${fleetLine}\n${standbyLine}`
    }
    case 'solar-pv': {
      if (tick) {
        // Live run: expected MW from bank telemetry + real-time sun elevation
        const exp      = (tick as unknown as Record<string, number>).p_expected_mw ?? 0
        const lat      = solarPreview?.lat ?? 32.72
        const utcOff   = solarPreview?.utc_offset_h ?? -8.0
        const elev     = computeSunElevationDeg(lat, utcOff)
        const elevStr  = elev >= 0
          ? `sun ${Math.round(elev)}° above horizon`
          : 'sun below horizon'
        return `exp ${exp.toFixed(2)} MW · ${elevStr}`
      }
      // Pre-run: expected MW and sun position from solar-preview
      if (solarPreview) {
        const plantMW = solarPreview.plant_rated_ac_mw ?? 4.99
        const expMW   = solarPreview.expected_fraction * plantMW
        const elev    = solarPreview.sun_elevation_deg
        const elevStr = elev >= 0
          ? `sun ${Math.round(elev)}° above horizon`
          : 'sun below horizon'
        return `expected ${expMW.toFixed(2)} MW · ${elevStr}`
      }
      return 'non-dispatchable · 4.99 MW rated'
    }
    case 'battery-bess': {
      const soc     = tick?.bess_soc_fraction ?? 0.95
      const socPct  = (soc * 100).toFixed(0)
      if (!tick) return `armed · ${socPct}% SoC · anchor 1.0 MW`
      const disch   = tick.bess_output_mw ?? 0
      const setpt   = tick.bess_setpoint_mw ?? 0
      // Excess generation (turbine + solar over current load) flows into BESS as charging
      const excess  = Math.max(0,
        (tick.turbine_output_mw ?? 0) + (tick.p_renewable_mw ?? 0)
        - (tick.p_total_mw ?? 0) - disch
      )
      // B4: gate the "discharging" label on bess_setpoint_mw (the dispatch command),
      // not bess_output_mw (which lags from a previous discharge due to the BESS
      // first-order lag).  This prevents "BESS standby" while the battery still
      // shows residual output from a frame-earlier dispatch.
      if (setpt > 0.1)  return `discharging · ${disch.toFixed(1)} MW · ${socPct}% SoC · anchor 1.0 MW`
      if (excess > 0.1) return `absorbing · ${excess.toFixed(1)} MW · ${socPct}% SoC · anchor 1.0 MW`
      return `standby · ${socPct}% SoC · anchor 1.0 MW`
    }
    case 'fuel-cell':
      return 'H₂ fuel cell array · advisory — not yet dispatched by engine'
    case 'grid-connection':
      return 'islanded — no utility feed'
    case 'switchgear-pms':
      return 'GridSignal advises —\nnever commands protection'
    case 'distribution':
      return '480 V'
    case 'pdu-rpp':
      return 'rack feeds'
    case 'compute-racks': {
      // Show p_compute_mw (GPU rack draw only), not p_total_mw (total site
      // including cooling, BESS, renewables).  The compute-racks node should
      // reflect what the racks themselves are drawing, not the full site balance.
      //
      // Job + node counts differ between kube and workload-event scenarios:
      //  • kube:  kube_metrics carries admitted_nodes (scheduler-admitted) and
      //           active_jobs (gang count).  Use these so operators see the
      //           actual admitted footprint, not just the classified-job count.
      //  • non-kube: checkpoint_states has one entry per active training job;
      //           node count comes from summing workload-event node_counts, but
      //           that total isn't in the tick payload — show job count only.
      //           Display uses the same admitted/queued layout as the kube path
      //           so the tile is visually consistent across scenario types; the
      //           queue is always 0 for scripted workload-event runs.
      if (tick?.kube_metrics) {
        const km        = tick.kube_metrics
        const computeMW = (tick.p_compute_mw ?? 0).toFixed(2)
        const admitted  = `${km.active_jobs} admitted`
        const queued    = `${km.queued_jobs ?? 0} queued`
        const nodes     = `${km.admitted_nodes.toLocaleString()} nodes`
        const capBadge  = km.power_cap_active ? ' · cap active' : ''
        return `${admitted} · ${queued} · ${nodes} · ${computeMW} MW${capBadge}`
      }
      const jobs = tick ? Object.keys(tick.checkpoint_states).length : 0
      if (jobs > 0) {
        const computeMW = (tick?.p_compute_mw ?? 0).toFixed(2)
        const jw = jobs === 1 ? 'job' : 'jobs'
        return `${jobs} ${jw} admitted · 0 queued · ${computeMW} MW`
      }
      return '600 – 1,900 nodes · up to 19.96 MW'
    }
    case 'cooling-plant': {
      // AA1: bind "rated" to rated_cooling_mw, not absorbable_mw.
      // absorbable_mw is headroom (rated − current draw) — very different numbers.
      const rated = tick?.rated_cooling_mw ?? 4.59
      if (tick) {
        const headroom = tick.absorbable_mw
        return `lags compute by 90 s · ${rated.toFixed(2)} MW rated · ${headroom.toFixed(2)} MW headroom`
      }
      return `lags compute by 90 s · ${rated.toFixed(2)} MW rated`
    }
    default:
      return ''
  }
}

/** Human-readable label for a weather code. */
function weatherLabel(weather: string): string {
  switch (weather) {
    case 'clear':            return 'clear'
    case 'partly_cloudy':    return 'partly cloudy'
    case 'overcast':         return 'overcast'
    case 'marine_layer':     return 'marine layer'
    case 'physics_estimate': return 'est.'
    default:                 return weather.replace(/_/g, ' ')
  }
}

/**
 * BalanceRows — Phase 4 (GS-CHG-2026-08-08).
 *
 * Compact three-line supply/served/unserved display for Compute Racks and
 * Cooling Plant tiles.  Replaces the single MW hero value.
 *
 * Rendering rules (§4.3 of the spec):
 *   - Order: Served / Demand / Unserved (top-to-bottom)
 *   - null  → "not modelled" in muted colour — never "0.00" or bare "—"
 *   - Unserved > 0 → prominent amber (#f0883e) to signal urgency
 *   - No arithmetic on the Phase-2 null fields; values read directly from props
 */
function BalanceRows({
  servedMW,
  demandMW,
  unservedMW,
  accentColor,
  queuedDemandMW,
}: {
  servedMW:         number | null
  demandMW:         number
  unservedMW:       number | null
  accentColor:      string
  queuedDemandMW?:  number | null   // pending queued jobs — shown dimmed below unserved
}) {
  const NULL_COLOUR  = '#4b5764'   // muted — unambiguously unavailable
  const NULL_LABEL   = 'not modelled'

  const unservedAlert = unservedMW !== null && unservedMW > 0.005

  const rows: Array<{ key: string; valueStr: string; valueColour: string }> = [
    {
      key: 'served',
      valueStr:    servedMW !== null ? `${servedMW.toFixed(2)} MW` : NULL_LABEL,
      valueColour: servedMW !== null ? accentColor : NULL_COLOUR,
    },
    {
      key: 'demand',
      valueStr:    `${demandMW.toFixed(2)} MW`,
      valueColour: accentColor,
    },
    {
      key: 'unserved',
      valueStr:    unservedMW !== null ? `${unservedMW.toFixed(2)} MW` : NULL_LABEL,
      valueColour: unservedMW !== null
        ? (unservedAlert ? '#f0883e' : '#3fb6a8')
        : NULL_COLOUR,
    },
  ]

  const ROW_STYLE: React.CSSProperties = {
    fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace",
    fontSize: 7,
    color: '#4b5764',
    letterSpacing: '0.06em',
    textTransform: 'uppercase' as const,
    flexShrink: 0,
  }
  const VAL_STYLE = (colour: string): React.CSSProperties => ({
    fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace",
    fontSize: 9,
    color: colour,
    fontWeight: 500,
    letterSpacing: '-0.01em',
    textAlign: 'right' as const,
  })

  const showQueued = queuedDemandMW != null && queuedDemandMW > 0.005

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      {rows.map(({ key, valueStr, valueColour }) => (
        <div
          key={key}
          style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 4 }}
        >
          <span style={ROW_STYLE}>{key}</span>
          <span style={VAL_STYLE(valueColour)}>{valueStr}</span>
        </div>
      ))}
      {/* Queued Demand — dimmed amber, only shown when jobs are waiting */}
      {showQueued && (
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 4,
          marginTop: 1,
          paddingTop: 2,
          borderTop: '1px dashed #1e2a36',
        }}>
          <span style={{ ...ROW_STYLE, color: '#3a4a58' }}>Queued Demand</span>
          <span style={VAL_STYLE('#6a7d52')}>
            +{queuedDemandMW!.toFixed(2)} MW
          </span>
        </div>
      )}
    </div>
  )
}

/**
 * WeatherBadge — compact weather chip shown on the Solar PV node before a run.
 * Disappears once a tick arrives (live run takes over the display).
 */
function WeatherBadge({ preview }: { preview: SolarPreview }) {
  const label = weatherLabel(preview.weather)

  // Colour varies by condition for quick scanning
  const color =
    preview.weather === 'clear'            ? '#e0a458' :
    preview.weather === 'partly_cloudy'    ? '#a8c5da' :
    preview.weather === 'overcast'         ? '#6a7d8e' :
    preview.weather === 'marine_layer'     ? '#7ab8d4' :
    /* physics_estimate */                   '#4b5764'

  return (
    <div style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 3,
      marginTop: 2,
      padding: '1px 5px',
      borderRadius: 3,
      border: `1px solid ${color}33`,
      background: `${color}14`,
    }}>
      {/* Source dot — dim for physics, coloured for Mistral */}
      <div style={{
        width: 4,
        height: 4,
        borderRadius: '50%',
        background: preview.source === 'mistral' ? color : '#3a4a58',
        flexShrink: 0,
      }} />
      <span style={{
        fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace",
        fontSize: 8,
        color,
        letterSpacing: '0.04em',
        lineHeight: 1.4,
      }}>
        {label} · {preview.local_time} PST
      </span>
    </div>
  )
}

export function PlantNode({ def, tick, onClick, solarPreview, liveSolarMW }: PlantNodeProps) {
  // Solar PV tile: prefer the live solar API value when available so the
  // tile stays consistent with the Renewable Supply modal.  Both ultimately
  // read solar_sim.live_aggregate_mw() — but after a run ends the tick value
  // goes stale while the 1.5 Hz poll always returns the current aggregate.
  const mwValue = (def.id === 'solar-pv' && liveSolarMW != null)
    ? liveSolarMW
    : getMwValue(def, tick)
  const detail  = nodeDetail(def, tick, solarPreview)
  const isGrid  = !!def.gridStyle
  const canClick = def.clickable && !def.passive

  // BESS charging flow: excess generation (turbine + solar − load − discharge) absorbed by battery.
  // Use liveSolarMW (same value shown on the solar tile) so the BESS excess
  // stays consistent: turbine + solar_tile − load = what the operator sees.
  const isBess = def.id === 'battery-bess'
  const solarForBess = liveSolarMW ?? tick?.p_renewable_mw ?? 0
  // Use on_bus_output_mw (not turbine_output_mw) so the BESS excess
  // matches exactly what the GT tile shows: only loading-layer-managed units.
  // turbine_output_mw includes RAMPING/AT_TARGET auto-staged units whose output
  // is real but not yet visible on any tile, making the BESS figure misleading.
  const bessExcess = isBess && tick
    ? Math.max(0,
        (tick.on_bus_output_mw ?? 0) + solarForBess
        - (tick.p_total_mw ?? 0) - (tick.bess_output_mw ?? 0)
      )
    : 0
  const bessIsCharging = isBess && bessExcess > 0.1 && (mwValue ?? 0) <= 0.1
  const bessIsDischarging = isBess && (mwValue ?? 0) > 0.1

  // When BESS is absorbing, show charging flow as the primary MW figure
  const displayMw   = bessIsCharging ? bessExcess : mwValue
  const isIdle      = displayMw === null || Math.abs(displayMw) < 0.01

  // Show weather badge on solar-pv only before a run starts (no tick yet)
  const showWeather = def.id === 'solar-pv' && !tick && solarPreview != null

  // Border colour: teal when active, dim when idle, grey when grid/passive
  const borderColor = isGrid
    ? '#2a3540'
    : def.passive
    ? '#1e2a36'
    : isIdle
    ? '#1e2a36'
    : def.accentColor

  const bgColor = isGrid ? 'transparent' : '#111821'

  const handleClick = () => {
    if (canClick) onClick?.(def.id)
  }

  return (
    <foreignObject
      x={def.x}
      y={def.y}
      width={def.w}
      height={def.h}
    >
      {/* xmlns required for SVG foreignObject HTML content */}
      <div
        // @ts-expect-error — xmlns is required for SVG foreignObject HTML but not in React typedefs
        xmlns="http://www.w3.org/1999/xhtml"
        onClick={canClick ? handleClick : undefined}
        style={{
          width: '100%',
          height: '100%',
          boxSizing: 'border-box',
          borderRadius: 6,
          border: `1.5px ${isGrid ? 'dashed' : 'solid'} ${borderColor}`,
          background: bgColor,
          padding: '6px 8px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          cursor: canClick ? 'pointer' : 'default',
          position: 'relative',
          overflow: 'hidden',
          transition: 'border-color 0.2s',
        }}
      >
        {/* Accent top bar (active only) */}
        {!isIdle && !isGrid && !def.passive && (
          <div style={{
            position: 'absolute', top: 0, left: 0, right: 0, height: 2,
            background: def.accentColor, borderRadius: '6px 6px 0 0',
          }} />
        )}

        {/* Header row: label + state dot + chevron */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 4 }}>
          <div>
            <div style={{
              fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace",
              fontSize: 9,
              fontWeight: 700,
              letterSpacing: '0.08em',
              color: isGrid ? '#3a4a58' : def.passive ? '#3a4a58' : '#8b949e',
              lineHeight: 1.2,
            }}>
              {def.label}
            </div>
            {def.label2 && (
              <div style={{
                fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace",
                fontSize: 9,
                fontWeight: 700,
                letterSpacing: '0.08em',
                color: isGrid ? '#3a4a58' : def.passive ? '#3a4a58' : '#8b949e',
                lineHeight: 1.1,
              }}>
                {def.label2}
              </div>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 3, flexShrink: 0 }}>
            <InfoBtn id={def.id} />
            {!isIdle && !isGrid && !def.passive && (
              <div style={{
                width: 5, height: 5, borderRadius: '50%',
                background: def.accentColor, flexShrink: 0,
              }} />
            )}
            {isGrid && (
              <div style={{
                width: 5, height: 5, borderRadius: '50%',
                background: '#3a4a58', flexShrink: 0,
              }} />
            )}
            {canClick && (
              <div style={{
                fontFamily: 'Inter,sans-serif',
                fontSize: 10,
                color: '#4b5764',
                lineHeight: 1,
              }}>›</div>
            )}
          </div>
        </div>

        {/* Compute Racks: one-line pointer to gen-trip cover */}
        {def.id === 'compute-racks' && (
          <div style={{
            fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace",
            fontSize: 7,
            color: '#3a4a5a',
            lineHeight: 1.3,
            marginTop: 1,
            marginBottom: 2,
          }}>
            Rack draw is what gen-trip cover is measured against — if the fleet can't cover a unit
            trip, this is the load that pauses. → gen-trip cover tile
          </div>
        )}

        {/* Phase 4 (GS-CHG-2026-08-08): balance rows for compute and cooling tiles */}
        {(def.id === 'compute-racks' || def.id === 'cooling-plant') && tick && (
          <BalanceRows
            servedMW={
              def.id === 'compute-racks'
                ? tick.p_compute_served_mw
                : tick.p_cooling_served_mw
            }
            demandMW={
              def.id === 'compute-racks'
                ? tick.p_compute_demand_mw
                : tick.p_cooling_demand_mw
            }
            unservedMW={
              def.id === 'compute-racks'
                ? tick.p_compute_unserved_mw
                : tick.p_cooling_unserved_mw
            }
            accentColor={def.accentColor ?? '#3fb6a8'}
            queuedDemandMW={(() => {
              // Only compute-racks shows queued demand; cooling never has a queue.
              if (def.id !== 'compute-racks') return null
              const km = tick.kube_metrics
              if (!km || km.queued_nodes <= 0) return null
              // Estimate MW proportionally from the current admitted draw.
              // All nodes share the same hardware profile, so kW/node is constant.
              if (km.admitted_nodes > 0) {
                return (km.queued_nodes / km.admitted_nodes) * tick.p_compute_demand_mw
              }
              // No admitted jobs yet — use node_count (includes min_nodes floor) as proxy.
              if (km.node_count > 0) {
                return (km.queued_nodes / km.node_count) * tick.p_compute_demand_mw
              }
              return null
            })()}
          />
        )}

        {/* MW value (middle) — hidden for compute/cooling (replaced by balance rows) */}
        {def.mwField !== undefined
          && def.id !== 'compute-racks'
          && def.id !== 'cooling-plant'
          && (
          <div style={{ lineHeight: 1 }}>
            <div style={{
              fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace",
              fontSize: displayMw !== null && Math.abs(displayMw) >= 10 ? 16 : 18,
              fontWeight: 500,
              color: isGrid ? '#3a4a58' : isIdle ? '#4b5764' : def.accentColor,
              letterSpacing: '-0.01em',
              lineHeight: 1,
            }}>
              {displayMw !== null ? `${Math.abs(displayMw).toFixed(2)}` : '—'}
              <span style={{ fontSize: 9, fontWeight: 400, marginLeft: 2, color: '#5a6a78' }}>MW</span>
            </div>
            {/* BESS direction badge */}
            {isBess && tick && (
              <div style={{
                fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace",
                fontSize: 8,
                marginTop: 2,
                color: bessIsCharging ? '#4a9fe0' : bessIsDischarging ? '#e0a458' : '#3a4a58',
                letterSpacing: '0.04em',
              }}>
                {bessIsCharging ? '↓ absorbing' : bessIsDischarging ? '↑ discharging' : '◦ standby'}
              </div>
            )}
          </div>
        )}

        {/* Amber warning: sun is up but output is zero during a live run */}
        {def.id === 'solar-pv' && tick && (() => {
          const exp    = (tick as unknown as Record<string, number>).p_expected_mw ?? 0
          const actual = (tick as unknown as Record<string, number>).p_renewable_mw ?? 0
          if (exp > 0.05 && actual < 0.01) {
            return (
              <div style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 3,
                marginTop: 2,
                padding: '1px 5px',
                borderRadius: 3,
                border: '1px solid rgba(240,136,62,0.35)',
                background: 'rgba(240,136,62,0.10)',
              }}>
                <div style={{
                  width: 4, height: 4, borderRadius: '50%',
                  background: '#f0883e', flexShrink: 0,
                }} />
                <span style={{
                  fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace",
                  fontSize: 8, color: '#f0883e', letterSpacing: '0.04em',
                }}>
                  sun up · zero output
                </span>
              </div>
            )
          }
          return null
        })()}

        {/* Weather badge — solar-pv only, pre-run */}
        {showWeather && <WeatherBadge preview={solarPreview!} />}

        {/* Detail line (bottom) */}
        {detail && (
          <div style={{
            fontFamily: 'Inter,sans-serif',
            fontSize: 8,
            color: isGrid ? '#2a3540' : def.passive ? '#2e3c48' : '#4b5764',
            lineHeight: 1.3,
            whiteSpace: 'pre-wrap',
            overflow: 'hidden',
          }}>
            {detail}
          </div>
        )}
      </div>
    </foreignObject>
  )
}
