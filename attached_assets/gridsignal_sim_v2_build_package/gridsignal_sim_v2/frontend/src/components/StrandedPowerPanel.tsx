import { useEffect, useMemo, useState } from 'react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { deriveRollingShortfall } from '../alerts/rollingShortfall'
import { useTickStore } from '../store/tickStore'

type ReservePolicy = 'none' | 'fixed_3mw' | 'pct10' | 'derate80'

interface StrandedMinute {
  minute: number
  t_start_s: number
  demand_mean_mw: number
  demand_max_mw: number
  requested_demand_max_mw?: number | null
  forecast_demand_mw?: number | null
  consumed_mw: number
  reserve_held_mw: number
  recoverable_mw: number
  above_cap_bess_mw: number
  above_cap_unserved_mw: number
  scarce: boolean
}

interface StrandedEpisode {
  start_minute: number
  end_minute: number
  length_minutes: number
}

interface StrandedAvailable {
  available: true
  p_avail_mw: number
  reserve_policy: ReservePolicy
  p_res_mw: number
  reserve_label: string
  energy_consumed_mwh: number
  energy_available_mwh: number
  avg_demand_mw: number
  peak_demand_mw: number
  utilisation_of_cap_pct: number
  minutes_above_cap: number
  above_cap_mwh: number
  above_cap_bess_mwh: number
  above_cap_unserved_mwh: number
  avg_stranded_mw: number
  avg_recoverable_mw: number
  recoverable_mwh: number
  recoverable_pct_of_cap: number
  scarce_minutes: number
  scarce_episodes: StrandedEpisode[]
  resample: string
  basis: string
  series: StrandedMinute[]
}

interface StrandedUnavailable {
  available: false
  reason: string
}

type StrandedResponse = StrandedAvailable | StrandedUnavailable

interface Props {
  runId: string
  scenario: string
  live?: boolean
  paused?: boolean
}

interface ForecastDemandSample {
  seconds: number
  demand_mw: number
}

interface ForecastScarceInterval {
  start_s: number
  end_s: number
}

interface ForecastOverlay {
  samples: ForecastDemandSample[]
}

const POLICY_OPTIONS: { value: ReservePolicy; label: string }[] = [
  { value: 'none', label: 'None (0 MW)' },
  { value: 'fixed_3mw', label: 'Fixed 3 MW (central)' },
  { value: 'pct10', label: '10% of cap' },
  { value: 'derate80', label: '80% derating rule' },
]

type SeriesDefinition = {
  key: keyof StrandedMinute
  label: string
  color: string
} & (
  | { style: 'band'; fillOpacity: number }
  | { style: 'line'; lineStyle: 'solid' | 'dashed' | 'dotted'; strokeWidth: number }
)

// Ordered top-to-bottom for the reader. Stacked areas are rendered in reverse
// order below so their visual stacking remains bottom-to-top.
const SERIES_DEFINITIONS: readonly SeriesDefinition[] = [
  {
    key: 'requested_demand_max_mw',
    label: 'Requested demand (incl. queued jobs)',
    color: '#f2cc60',
    style: 'line',
    lineStyle: 'dashed',
    strokeWidth: 1.8,
  },
  {
    key: 'forecast_demand_mw',
    label: 'Forecast demand (15 min–4 h)',
    color: '#ffcc00',
    style: 'line',
    lineStyle: 'dotted',
    strokeWidth: 2,
  },
  {
    key: 'demand_max_mw',
    label: 'Demand peak',
    color: '#f0f3f6',
    style: 'line',
    lineStyle: 'solid',
    strokeWidth: 1.4,
  },
  {
    key: 'above_cap_unserved_mw',
    label: 'Above cap, unserved',
    color: '#da3633',
    style: 'band',
    fillOpacity: 0.9,
  },
  {
    key: 'above_cap_bess_mw',
    label: 'Above cap, BESS-covered',
    color: '#f85149',
    style: 'band',
    fillOpacity: 0.45,
  },
  {
    key: 'recoverable_mw',
    label: 'Recoverable (stranded above reserve)',
    color: '#27b5a5',
    style: 'band',
    fillOpacity: 0.9,
  },
  {
    key: 'reserve_held_mw',
    label: 'Reserve held',
    color: '#8b949e',
    style: 'band',
    fillOpacity: 0.9,
  },
  {
    key: 'consumed_mw',
    label: 'Consumed (served)',
    color: '#3987e8',
    style: 'band',
    fillOpacity: 0.9,
  },
]

/**
 * Mark the projected portions of the rolling forecast that cross the safe
 * limit. Forecast points are interpolated only for drawing the yellow window;
 * the simulator's demand and dispatch values are not changed.
 */
export function buildForecastScarceIntervals(
  samples: readonly ForecastDemandSample[],
  safeLimitMw: number,
): ForecastScarceInterval[] {
  const intervals: ForecastScarceInterval[] = []
  if (!Number.isFinite(safeLimitMw) || samples.length < 2) return intervals

  for (let index = 0; index < samples.length - 1; index += 1) {
    const left = samples[index]
    const right = samples[index + 1]
    if (!Number.isFinite(left.seconds) || !Number.isFinite(right.seconds) ||
        !Number.isFinite(left.demand_mw) || !Number.isFinite(right.demand_mw) ||
        right.seconds <= left.seconds) continue

    const leftAbove = left.demand_mw > safeLimitMw
    const rightAbove = right.demand_mw > safeLimitMw
    if (!leftAbove && !rightAbove) continue

    let start = left.seconds
    let end = right.seconds
    if (leftAbove !== rightAbove) {
      const fraction = (safeLimitMw - left.demand_mw) /
        (right.demand_mw - left.demand_mw)
      const crossing = left.seconds + fraction * (right.seconds - left.seconds)
      if (leftAbove) end = crossing
      else start = crossing
    }

    const previous = intervals[intervals.length - 1]
    if (previous && Math.abs(previous.end_s - start) < 1e-6) {
      previous.end_s = end
    } else {
      intervals.push({ start_s: start, end_s: end })
    }
  }

  return intervals
}

interface TooltipPayloadItem {
  dataKey?: string | number
  value?: unknown
}

interface StrandedTooltipProps {
  active?: boolean
  label?: unknown
  payload?: TooltipPayloadItem[]
}

export function StrandedChartTooltip({ active, label, payload }: StrandedTooltipProps) {
  if (!active || !payload?.length) return null
  const requestedIsPresent = payload.some(item => item.dataKey === 'requested_demand_max_mw')
  const forecastIsPresent = payload.some(item => item.dataKey === 'forecast_demand_mw')
  const visibleSeries = SERIES_DEFINITIONS.filter(
    series =>
      (series.key !== 'requested_demand_max_mw' || requestedIsPresent) &&
      (series.key !== 'forecast_demand_mw' || forecastIsPresent),
  )

  return (
    <div
      className="rounded border border-border bg-surface px-3 py-2 font-mono text-[11px]"
      data-testid="stranded-chart-tooltip"
    >
      <div className="mb-2 text-foreground">
        {typeof label === 'number' ? clock(label) : ''}
      </div>
      <div className="space-y-1">
        {visibleSeries.map(series => {
          const entry = payload.find(item => item.dataKey === series.key)
          if (entry?.value == null) return null
          return (
            <div key={series.key} className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className={series.style === 'band' ? 'h-2.5 w-2.5 shrink-0' : 'w-4 shrink-0'}
                style={series.style === 'band'
                  ? { backgroundColor: series.color }
                  : {
                       borderTop: `${series.strokeWidth}px ${series.lineStyle} ${series.color}`,
                    }}
              />
              <span style={{ color: series.color }} data-series-label={series.key}>
                {series.label}
              </span>
              <span>{fmt(Number(entry.value))} MW</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function fmt(value: number): string {
  return value.toFixed(1)
}

function clock(seconds: number): string {
  const totalMinutes = Math.floor(seconds / 60)
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`
}

function SummaryTable({ data, live }: { data: StrandedAvailable; live: boolean }) {
  const requestedValues = data.series
    .map(row => row.requested_demand_max_mw)
    .filter((value): value is number => value != null)
  const hasRequestedDemand = requestedValues.length > 0
  const rows: [string, string][] = [
    ['Energy consumed', `${fmt(data.energy_consumed_mwh)} MWh`],
    ['Energy available at the cap', `${fmt(data.energy_available_mwh)} MWh`],
    ['Average / peak demand', `${fmt(data.avg_demand_mw)} / ${fmt(data.peak_demand_mw)} MW`],
    ['Utilisation of the cap', `${fmt(data.utilisation_of_cap_pct)}%`],
    ['Minutes above the cap', String(data.minutes_above_cap)],
    ['Above-cap energy (BESS-covered / unserved)', `${fmt(data.above_cap_bess_mwh)} / ${fmt(data.above_cap_unserved_mwh)} MWh`],
    ['Average stranded power', `${fmt(data.avg_stranded_mw)} MW`],
    ['Average recoverable power', `${fmt(data.avg_recoverable_mw)} MW`],
    ['Recoverable energy', `${fmt(data.recoverable_mwh)} MWh · ${fmt(data.recoverable_pct_of_cap)}% of cap`],
    ['Scarce minutes', `${data.scarce_minutes} / ${data.scarce_episodes.length} episodes`],
  ]
  if (hasRequestedDemand) {
    rows.push(
      [
        'Minutes requested demand exceeded the cap',
        String(requestedValues.filter(value => value > data.p_avail_mw).length),
      ],
      ['Peak requested demand', `${fmt(Math.max(...requestedValues))} MW`],
    )
  }

  return (
    <div className="min-w-[260px] rounded border border-border bg-surface px-3 py-2">
      <h3 className="mb-2 font-mono text-[10px] uppercase tracking-wider text-muted">
        {live ? 'Live-to-date summary' : 'Run summary'}
      </h3>
      <dl className="space-y-1">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-baseline justify-between gap-4 text-[11px]">
            <dt className="text-muted">{label}</dt>
            <dd className="text-right font-mono tabular-nums text-foreground">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function AvailablePanel({
  data,
  runId,
  scenario,
  live,
  forecast,
}: {
  data: StrandedAvailable
  runId: string
  scenario: string
  live: boolean
  forecast: ForecastOverlay | null
}) {
  const { series, p_avail_mw: cap, p_res_mw: reserve } = data
  const requestedValues = series
    .map(row => row.requested_demand_max_mw)
    .filter((value): value is number => value != null)
  const hasRequestedDemand = requestedValues.length > 0
  const forecastIntervals = useMemo(
    () => forecast
      ? buildForecastScarceIntervals(forecast.samples, cap - reserve)
      : [],
    [cap, forecast, reserve],
  )
  const hasForecast = Boolean(forecast && forecast.samples.length > 1)
  const chartData = useMemo(() => {
    const observedRows = series.map(row => ({
      ...row,
      forecast_demand_mw: null,
    }))
    if (!forecast) return observedRows

    const forecastRows = forecast.samples.map(sample => ({
      minute: sample.seconds / 60,
      t_start_s: sample.seconds,
      demand_mean_mw: null,
      demand_max_mw: null,
      requested_demand_max_mw: null,
      forecast_demand_mw: sample.demand_mw,
      consumed_mw: null,
      reserve_held_mw: null,
      recoverable_mw: null,
      above_cap_bess_mw: null,
      above_cap_unserved_mw: null,
      scarce: false,
    }))
    return [...observedRows, ...forecastRows].sort((left, right) => left.t_start_s - right.t_start_s)
  }, [forecast, series])
  const bounds = useMemo(() => {
    const firstMinute = series[0]?.minute ?? 0
    const lastMinute = series[series.length - 1]?.minute ?? firstMinute
    const start = firstMinute * 60
    const observedEnd = (lastMinute + 1) * 60
    const forecastEnd = forecast?.samples[forecast.samples.length - 1]?.seconds ?? observedEnd
    const end = Math.max(observedEnd, forecastEnd)
    const duration = Math.max(60, end - start)
    const maxDemand = Math.max(0, ...series.map(row => row.demand_max_mw))
    const maxRequested = Math.max(
      0,
      ...series.map(row => row.requested_demand_max_mw ?? 0),
    )
    const maxForecast = Math.max(0, ...(forecast?.samples.map(point => point.demand_mw) ?? []))
    const yMax = Math.max(cap, maxDemand, maxRequested, maxForecast) * 1.05 || cap
    const step = duration >= 12 * 3600 ? 3 * 3600 : Math.max(3600, Math.ceil(duration / 6 / 3600) * 3600)
    const firstTick = Math.ceil(start / step) * step
    const ticks: number[] = [start]
    for (let tick = firstTick; tick < end; tick += step) {
      if (tick > start) ticks.push(tick)
    }
    if (ticks[ticks.length - 1] !== end) ticks.push(end)
    const yTicks = Array.from(new Set([0, cap - reserve, cap, yMax])).sort((a, b) => a - b)
    return { start, end, yMax, xTicks: ticks, yTicks }
  }, [cap, forecast, reserve, series])

  return (
    <section className="rounded border border-border bg-background p-3" data-testid="panel-stranded-power">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-mono text-sm font-semibold text-foreground">
          Facility demand vs the {fmt(cap)} MW import cap (1-minute samples)
        </h2>
      </div>

      <div className="mb-1 flex flex-wrap items-center gap-2 text-[10px] text-muted">
        <span className="shrink-0">Scarce activity (demand above safe limit)</span>
        <span className="inline-flex items-center gap-1" data-testid="observed-scarce-legend">
          <span aria-hidden="true" className="h-2.5 w-3 bg-red-500" />
          Observed
        </span>
        {hasForecast && (
          <span className="inline-flex items-center gap-1" data-testid="forecast-scarce-legend">
            <span aria-hidden="true" className="h-2.5 w-3 bg-amber-300" />
            Forecast
          </span>
        )}
        <div
          className="relative h-3 min-w-24 flex-1 rounded-sm bg-surface"
          aria-label="Observed and forecast scarce periods"
          data-testid="scarce-episode-strip"
        >
          {data.scarce_episodes.map((episode, index) => {
            const span = Math.max(1, bounds.end / 60 - bounds.start / 60)
            const left = ((episode.start_minute - bounds.start / 60) / span) * 100
            const width = (episode.length_minutes / span) * 100
            return (
              <span
                key={`${episode.start_minute}-${episode.end_minute}`}
                className="absolute top-0 h-3 bg-red-500"
                style={{ left: `${left}%`, width: `${width}%` }}
                title={`Episode ${index + 1}: ${episode.length_minutes} minutes`}
                data-testid={`scarce-episode-${index}`}
              />
            )
          })}
          {forecastIntervals.map((interval, index) => {
            const span = Math.max(1, bounds.end - bounds.start)
            const left = ((interval.start_s - bounds.start) / span) * 100
            const width = ((interval.end_s - interval.start_s) / span) * 100
            return (
              <span
                key={`forecast-${interval.start_s}-${interval.end_s}`}
                className="absolute top-0 h-3 bg-amber-300"
                style={{ left: `${left}%`, width: `${Math.max(width, 0.15)}%` }}
                title={`Forecast scarce window: ${clock(interval.start_s)}–${clock(interval.end_s)}`}
                data-testid={`forecast-scarce-episode-${index}`}
              />
            )
          })}
        </div>
      </div>
      {hasForecast && (
        <p className="mb-2 font-mono text-[9px] text-muted" data-testid="forecast-overlay-note">
          Yellow overlay: advisory simulator demand projection at 15-minute steps, up to 4 hours ahead.
        </p>
      )}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_220px]">
        <div className="h-[300px] min-w-0">
          {series.length === 0 ? (
            <div className="flex h-full items-center justify-center font-mono text-xs text-muted">
              No minute samples available.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} margin={{ top: 20, right: 28, bottom: 18, left: 8 }}>
                <CartesianGrid stroke="#30363d" strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="t_start_s"
                  type="number"
                  domain={[bounds.start, bounds.end]}
                  ticks={bounds.xTicks}
                  tickFormatter={clock}
                  tick={{ fill: '#8b949e', fontSize: 10, fontFamily: 'monospace' }}
                  label={{
                    value: 'Replay clock (hh:mm)',
                    position: 'insideBottom',
                    offset: -10,
                    fill: '#8b949e',
                    fontSize: 10,
                  }}
                />
                <YAxis
                  domain={[0, bounds.yMax]}
                  ticks={bounds.yTicks}
                  tickFormatter={fmt}
                  tick={{ fill: '#8b949e', fontSize: 10, fontFamily: 'monospace' }}
                  label={{ value: 'MW', angle: -90, position: 'insideLeft', fill: '#8b949e', fontSize: 10 }}
                />
                <Tooltip
                  content={props => <StrandedChartTooltip {...props} />}
                />
                <ReferenceLine
                  y={cap}
                  stroke="#000000"
                  strokeWidth={2}
                  label={{ value: `Import cap ${fmt(cap)} MW`, position: 'insideTopRight', fill: '#111827', fontSize: 10 }}
                />
                <ReferenceLine
                  y={cap - reserve}
                  stroke="#d2d8de"
                  strokeDasharray="5 4"
                  strokeWidth={1.5}
                  label={{
                    value: `Safe limit ${fmt(cap - reserve)} MW (${fmt(reserve)} MW reserve, illustrative)`,
                    position: 'insideTopLeft',
                    fill: '#d2d8de',
                    fontSize: 10,
                  }}
                />
                {[...SERIES_DEFINITIONS].reverse().map(series => {
                  if (series.key === 'requested_demand_max_mw' && !hasRequestedDemand) return null
                  if (series.key === 'forecast_demand_mw' && !hasForecast) return null
                  if (series.style === 'band') {
                    return (
                      <Area
                        key={series.key}
                        type="stepAfter"
                        dataKey={series.key}
                        stackId="power"
                        stroke={series.color}
                        fill={series.color}
                        fillOpacity={series.fillOpacity}
                        isAnimationActive={false}
                        name={series.label}
                      />
                    )
                  }
                  return (
                    <Line
                      key={series.key}
                      type="monotone"
                      dataKey={series.key}
                      stroke={series.color}
                      strokeWidth={series.strokeWidth}
                      strokeDasharray={series.lineStyle === 'dashed'
                        ? '6 4'
                        : series.lineStyle === 'dotted' ? '2 3' : undefined}
                      dot={false}
                      isAnimationActive={false}
                      name={series.label}
                    />
                  )
                })}
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>

        <div
          className="flex flex-col justify-between gap-2 py-3 text-[10px] text-muted"
          aria-label="Chart legend"
          data-testid="stranded-chart-legend"
          data-order="top-to-bottom"
        >
          {SERIES_DEFINITIONS
            .filter(series => series.key !== 'requested_demand_max_mw' || hasRequestedDemand)
            .filter(series => series.key !== 'forecast_demand_mw' || hasForecast)
            .map(series => (
              <span
                key={series.key}
                className="inline-flex items-center gap-1.5"
              >
                <span
                  aria-hidden="true"
                  className={series.style === 'band' ? 'h-2.5 w-2.5 shrink-0 rounded-sm' : 'w-4 shrink-0'}
                  style={series.style === 'band'
                    ? { backgroundColor: series.color }
                    : {
                        borderTop: `${series.strokeWidth}px ${series.lineStyle} ${series.color}`,
                      }}
                />
                <span
                  data-testid={series.key === 'requested_demand_max_mw' ? 'legend-requested-demand' : undefined}
                  data-series-label={series.key}
                >
                  {series.label}
                </span>
              </span>
            ))}
        </div>
      </div>

      <div className="mt-3 grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(280px,0.7fr)]">
        <p className="self-end text-[10px] leading-4 text-muted">
          Source: {scenario} run {runId}. Reserve {fmt(reserve)} MW is illustrative.
          {' '}Recoverable = stranded − reserve. Basis: facility demand, not grid import.
        </p>
        <SummaryTable data={data} live={live} />
      </div>
    </section>
  )
}

export function StrandedPowerPanel({ runId, scenario, live = false, paused = false }: Props) {
  const [reservePolicy, setReservePolicy] = useState<ReservePolicy>('fixed_3mw')
  const [state, setState] = useState<'loading' | 'error' | 'ready'>('loading')
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<StrandedResponse | null>(null)
  const [retryKey, setRetryKey] = useState(0)
  const latestTick = useTickStore(state => state.latestTick)
  const forecast = useMemo<ForecastOverlay | null>(() => {
    if (!live || !latestTick || latestTick.run_id !== runId) return null
    const projection = deriveRollingShortfall(latestTick)
    if (!projection) return null
    return {
      samples: [
        {
          seconds: latestTick.sim_time_seconds,
          demand_mw: Math.max(0, latestTick.p_demand_mw),
        },
        ...projection.points.map(point => ({
          seconds: latestTick.sim_time_seconds + point.minutesFromNow * 60,
          demand_mw: point.projectedDemandMw,
        })),
      ],
    }
  }, [latestTick, live, runId])

  useEffect(() => {
    let cancelled = false
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | null = null
    let receivedData = false
    let hasRequested = false

    async function load() {
      if (!hasRequested && !receivedData && !data) setState('loading')
      hasRequested = true
      try {
        const response = await fetch(
          `/runs/${encodeURIComponent(runId)}/stranded?reserve_policy=${reservePolicy}`,
          { signal: controller.signal },
        )
        if (!response.ok) {
          throw new Error(`GET /runs/${runId}/stranded → ${response.status}: ${await response.text()}`)
        }
        const body = await response.json() as StrandedResponse
        if (!cancelled) {
          receivedData = true
          setData(body)
          setState('ready')
          setError(null)
        }
      } catch (cause) {
        if (!cancelled && !(cause instanceof DOMException && cause.name === 'AbortError')) {
          setError(String(cause))
          if (!receivedData && !data) setState('error')
        }
      } finally {
        if (live && !paused && !cancelled) timer = setTimeout(load, 2000)
      }
    }

    void load()
    return () => {
      cancelled = true
      controller.abort()
      if (timer) clearTimeout(timer)
    }
  }, [reservePolicy, runId, live, paused, retryKey])

  if (state === 'loading') {
    return (
      <section className="rounded border border-border bg-background p-3" data-testid="panel-stranded-power">
        <div className="flex items-center gap-2">
          <h2 className="font-mono text-sm font-semibold text-foreground">Stranded power</h2>
          {live && (
            <span data-testid="live-power-status" className="font-mono text-[9px] font-bold tracking-wider text-emerald-300">
              {paused ? 'PAUSED' : 'LIVE · UPDATING'}
            </span>
          )}
        </div>
        <p className="mt-2 font-mono text-xs text-muted">
          {live
            ? paused ? 'Run paused · waiting for the first minute sample.' : 'Waiting for the first minute sample…'
            : 'Loading stranded power…'}
        </p>
      </section>
    )
  }

  if (state === 'error') {
    return (
      <section className="rounded border border-border bg-background p-3" data-testid="panel-stranded-power">
        <h2 className="font-mono text-sm font-semibold text-foreground">Stranded power</h2>
        <p className="mt-2 font-mono text-xs text-red-400">Unable to load stranded power.</p>
        {error && <p className="mt-1 break-all font-mono text-[10px] text-muted">{error}</p>}
        {live && <p className="mt-1 font-mono text-[10px] text-muted">Live updates retry every 2 seconds.</p>}
        <button
          type="button"
          className="mt-2 rounded border border-border px-2 py-1 font-mono text-[10px] text-foreground hover:border-accent"
          onClick={() => { setState('loading'); setRetryKey(value => value + 1) }}
          data-testid="button-retry-stranded"
        >
          Retry
        </button>
      </section>
    )
  }

  if (data?.available === false) {
    return (
      <section className="rounded border border-border bg-background p-3" data-testid="panel-stranded-power">
        <h2 className="font-mono text-sm font-semibold text-foreground">Stranded power</h2>
        <p className="mt-2 text-xs text-muted">
          No available-capacity basis defined for this scenario (no grid import cap). Stranded power is not computed.
        </p>
      </section>
    )
  }

  if (!data) return null

  return (
    <div className="space-y-2">
      <section className="flex items-center justify-between gap-3 rounded border border-border bg-background px-3 py-2">
        <div className="flex items-center gap-2">
          <h2 className="font-mono text-sm font-semibold text-foreground">Stranded power</h2>
          {live && (
            <span
              data-testid="live-power-status"
              className={`rounded border px-1.5 py-0.5 font-mono text-[9px] font-bold tracking-wider ${
                paused ? 'border-amber-500/40 text-amber-300' : 'border-emerald-500/40 text-emerald-300'
              }`}
            >
              {paused ? 'PAUSED' : 'LIVE · UPDATING'}
            </span>
          )}
        </div>
        <label className="flex items-center gap-2 font-mono text-[11px] text-muted">
          Reserve policy
          <select
            aria-label="Reserve policy"
            data-testid="select-reserve-policy"
            className="rounded border border-border bg-surface px-2 py-1 text-foreground"
            value={reservePolicy}
            onChange={event => setReservePolicy(event.target.value as ReservePolicy)}
          >
            {POLICY_OPTIONS.map(option => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
      </section>
      {live && (
        <p className="px-1 font-mono text-[10px] text-muted" data-testid="live-power-update-note">
          {paused
            ? 'Run paused · last received minute retained; polling resumes when the run resumes.'
            : error
              ? 'Update delayed · retaining the last received data and retrying.'
              : 'Cumulative run-to-date statistics · refreshes every 2 seconds while active.'}
        </p>
      )}
      <AvailablePanel
        data={data}
        runId={runId}
        scenario={scenario}
        live={live}
        forecast={forecast}
      />
    </div>
  )
}
