import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { StrandedPowerPanel } from '../components/StrandedPowerPanel'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
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

    expect(await screen.findByText('Stranded power')).toBeInTheDocument()
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
    fireEvent.change(screen.getByLabelText('Reserve policy'), {
      target: { value: 'derate80' },
    })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(fetchMock.mock.calls[1][0]).toContain('reserve_policy=derate80')
  })
})
