import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { StrandedChartTooltip, StrandedPowerPanel } from '../components/StrandedPowerPanel'
import { useTickStore } from '../store/tickStore'
import type { TickPayload } from '../types'

afterEach(() => {
  cleanup()
  useTickStore.setState({ latestTick: null })
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

const availableResponse = {
  available: true,
  p_avail_mw: 60,
  reserve_policy: 'fixed_3mw',
  p_res_mw: 3,
  reserve_label: 'illustrative',
  energy_consumed_mwh: 1,
  energy_available_mwh: 1,
  avg_demand_mw: 10,
  peak_demand_mw: 12,
  utilisation_of_cap_pct: 10,
  minutes_above_cap: 0,
  minutes_requested_above_cap: 17,
  peak_requested_demand_mw: 42.5,
  above_cap_mwh: 0,
  above_cap_bess_mwh: 0,
  above_cap_unserved_mwh: 0,
  avg_stranded_mw: 50,
  avg_recoverable_mw: 47,
  recoverable_mwh: 0.8,
  recoverable_pct_of_cap: 8,
  scarce_minutes: 0,
  scarce_episodes: [],
  resample: '1-minute: mean for energy layers, max for demand line',
  basis: 'facility demand, not grid import',
  series: [{
    minute: 0,
    t_start_s: 0,
    demand_mean_mw: 10,
    demand_max_mw: 12,
    requested_demand_max_mw: 13,
    consumed_mw: 10,
    reserve_held_mw: 3,
    recoverable_mw: 47,
    above_cap_bess_mw: 0,
    above_cap_unserved_mw: 0,
    scarce: false,
  }],
}

describe('StrandedPowerPanel', () => {
  it('shows only the title and no-cap explanation when there is no cap', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        available: false,
        reason: 'no grid_import_limit_mw; no available-capacity basis defined',
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const { container } = render(
      <StrandedPowerPanel runId="run-no-cap" scenario="uncapped-demo" />,
    )

    await waitFor(() => expect(screen.getByText('Stranded power')).toBeInTheDocument())
    expect(screen.getByText(
      'No available-capacity basis defined for this scenario (no grid import cap). Stranded power is not computed.',
    )).toBeInTheDocument()
    expect(container.querySelector('[data-testid="select-reserve-policy"]')).toBeNull()
    expect(container.querySelector('[data-testid="scarce-episode-strip"]')).toBeNull()
  })

  it('renders the chart legend and refetches when reserve policy changes', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => availableResponse,
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<StrandedPowerPanel runId="run-cap" scenario="S11b" />)

    expect(await screen.findByText(
      'Facility demand vs the 60.0 MW import cap (1-minute samples)',
    )).toBeInTheDocument()
    expect(screen.getByText('Consumed (served)')).toBeInTheDocument()
    expect(screen.getByText('Reserve held')).toBeInTheDocument()
    expect(screen.getByText('Recoverable (stranded above reserve)')).toBeInTheDocument()
    expect(screen.getByText('Above cap, BESS-covered')).toBeInTheDocument()
    expect(screen.getByText('Above cap, unserved')).toBeInTheDocument()
    expect(screen.getByTestId('legend-requested-demand')).toHaveTextContent(
      'Requested demand (incl. queued jobs)',
    )
    expect(screen.getByText('Minutes requested demand exceeded the cap')).toBeInTheDocument()
    expect(screen.getByText('Peak requested demand')).toBeInTheDocument()
    expect(screen.getByText('17')).toBeInTheDocument()
    expect(screen.getByText('42.5 MW')).toBeInTheDocument()
    const legend = screen.getByTestId('stranded-chart-legend')
    expect(legend).toHaveAttribute('data-order', 'top-to-bottom')
    fireEvent.change(screen.getByLabelText('Reserve policy'), {
      target: { value: 'derate80' },
    })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(fetchMock.mock.calls[1][0]).toContain('reserve_policy=derate80')
  })

  it('renders tooltip and legend series in matching top-to-bottom order', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => availableResponse,
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<StrandedPowerPanel runId="run-ordered" scenario="S11b" />)
    render(
      <StrandedChartTooltip
        active
        label={0}
        payload={[
          { dataKey: 'requested_demand_max_mw', value: 13 },
          { dataKey: 'demand_max_mw', value: 12 },
          { dataKey: 'above_cap_unserved_mw', value: 0 },
          { dataKey: 'above_cap_bess_mw', value: 0 },
          { dataKey: 'recoverable_mw', value: 47 },
          { dataKey: 'reserve_held_mw', value: 3 },
          { dataKey: 'consumed_mw', value: 10 },
        ]}
      />,
    )

    const expectedLabels = [
      'Requested demand (incl. queued jobs)',
      'Demand peak',
      'Above cap, unserved',
      'Above cap, BESS-covered',
      'Recoverable (stranded above reserve)',
      'Reserve held',
      'Consumed (served)',
    ]
    await screen.findByTestId('stranded-chart-legend')
    const rowLabels = (container: Element | null) =>
      Array.from(container?.children ?? [])
        .map(row => row.querySelector('[data-series-label]')?.textContent?.trim())

    const tooltip = screen.getByTestId('stranded-chart-tooltip')
    expect(rowLabels(tooltip.querySelector('.space-y-1'))).toEqual(expectedLabels)
    expect(rowLabels(screen.getByTestId('stranded-chart-legend'))).toEqual(expectedLabels)
  })

  it('hides requested-demand display when the telemetry field is absent', async () => {
    const { requested_demand_max_mw: _ignored, ...minuteWithoutRequested } =
      availableResponse.series[0]
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ...availableResponse,
        minutes_requested_above_cap: null,
        peak_requested_demand_mw: null,
        series: [minuteWithoutRequested],
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<StrandedPowerPanel runId="run-no-requested" scenario="S11" />)

    await screen.findByText(
      'Facility demand vs the 60.0 MW import cap (1-minute samples)',
    )
    expect(screen.queryByTestId('legend-requested-demand')).toBeNull()
    expect(screen.queryByText('Peak requested demand')).toBeNull()
  })

  it('overlays forecast demand and yellow scarce windows on the live chart', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ...availableResponse,
        p_avail_mw: 5,
        p_res_mw: 3,
      }),
    })
    vi.stubGlobal('fetch', fetchMock)
    useTickStore.setState({
      latestTick: {
        run_id: 'run-live-forecast',
        sim_time_seconds: 300,
        p_demand_mw: 1.5,
        p_compute_mw: 0.5,
        forecast_mw: 3,
        planning_forecast_mw: [{ minutes_from_now: 15, forecast_mw: 3 }],
        dt_lead_next_s: 0,
        contingency_coverage: null,
        p_generation_mw: 0,
        p_renewable_mw: 0,
      } as unknown as TickPayload,
    })

    render(
      <StrandedPowerPanel
        runId="run-live-forecast"
        scenario="Proxim8 — queue stress"
        live
      />,
    )

    expect(await screen.findByTestId('forecast-scarce-episode-0')).toBeInTheDocument()
    expect(screen.getByTestId('forecast-scarce-legend')).toHaveTextContent('Forecast')
    expect(screen.getByTestId('forecast-overlay-note')).toHaveTextContent(
      '15-minute steps, up to 4 hours ahead',
    )
    expect(screen.getByText('Forecast demand (15 min–4 h)')).toBeInTheDocument()
  })

  it('polls the active run endpoint and replaces visible cumulative data', async () => {
    vi.useFakeTimers()
    let requestCount = 0
    const fetchMock = vi.fn().mockImplementation(() => {
      requestCount += 1
      return Promise.resolve({
        ok: true,
        json: async () => ({
          ...availableResponse,
          energy_consumed_mwh: requestCount === 1 ? 1.2 : 2.4,
          series: requestCount === 1
            ? availableResponse.series
            : [...availableResponse.series, { ...availableResponse.series[0], minute: 1, t_start_s: 60 }],
        }),
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<StrandedPowerPanel runId="run-live-7" scenario="S11b" live />)

    await act(async () => { await Promise.resolve(); await Promise.resolve() })
    expect(screen.getByText('1.2 MWh')).toBeInTheDocument()
    expect(screen.getByTestId('live-power-status')).toHaveTextContent('LIVE · UPDATING')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][0]).toBe('/runs/run-live-7/stranded?reserve_policy=fixed_3mw')

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
      await Promise.resolve()
    })

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(screen.getByText('2.4 MWh')).toBeInTheDocument()
    expect(screen.getByTestId('panel-stranded-power')).toBeInTheDocument()
  })
})
