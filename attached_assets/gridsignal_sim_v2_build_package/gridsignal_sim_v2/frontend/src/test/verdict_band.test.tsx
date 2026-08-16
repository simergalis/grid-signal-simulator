/**
 * verdict_band.test.tsx — VerdictBand gen-trip cover tile rendering tests.
 *
 * Covers three rendering branches (GT-1 §7.4 / GT-2 TC-84):
 *   Branch 1 — No tick (static default):   tile shows "N−1 ready" in blue
 *   Branch 2 — Running (dt_lead_next_s > 0): tile shows live coverage state
 *   Branch 3 — At-rest (dt_lead_next_s = 0): tile preserves final tick state
 *
 * Also asserts TC-84: console.log fires when contingency_coverage.state
 * changes between ticks.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, cleanup, act, fireEvent } from '@testing-library/react'
import { useTickStore } from '../store/tickStore'
import { VerdictBand } from '../opening/VerdictBand'
import type { TickPayload, ContingencyCoverage } from '../types'

// ---------------------------------------------------------------------------
// Mock GenTripModal and ReserveModal — avoid rendering the full modal trees
// in unit tests; they are tested in isolation elsewhere.
// ---------------------------------------------------------------------------

vi.mock('../opening/GenTripModal', () => ({
  GenTripModal: ({ onClose }: { onClose: () => void }) => (
    <div data-testid="gen-trip-modal-stub">
      <button onClick={onClose} aria-label="close-gen-trip-modal">close</button>
    </div>
  ),
}))

vi.mock('../opening/ReserveModal', () => ({
  ReserveModal: () => <div data-testid="reserve-modal-stub" />,
}))

// ---------------------------------------------------------------------------
// Shared fixtures
// ---------------------------------------------------------------------------

/** A ContingencyCoverage object for the COVERED state. */
const CC_COVERED: ContingencyCoverage = {
  state:                     'COVERED',
  tripped_unit_id:           'GT-1',
  deficit_mw:                7.0,
  headroom_surviving_mw:     10.0,
  r_surviving_mw_per_s:      0.35,
  bess_bridging_available_mw: 9.0,
  bess_usable_energy_mwh:    4.5,
  power_test_passes:         true,
  energy_test_passes:        true,
  closable:                  true,
  time_to_close_s:           30,
  shed_required_mw:          0.0,
  ride_through_s:            2314,
  dispatchable_mw:           45.0,
  renewable_mw:              5.0,
}

/** A ContingencyCoverage object for the COVERED_WITH_SHED state. */
const CC_SHED: ContingencyCoverage = {
  ...CC_COVERED,
  state:                'COVERED_WITH_SHED',
  headroom_surviving_mw: 3.0,
  closable:             false,
  time_to_close_s:      86400,
  shed_required_mw:     4.5,
  ride_through_s:       580,
}

/** A ContingencyCoverage object for the CANNOT_CARRY state. */
const CC_CANNOT: ContingencyCoverage = {
  ...CC_COVERED,
  state:                'CANNOT_CARRY',
  headroom_surviving_mw: 1.0,
  closable:             false,
  time_to_close_s:      86400,
  shed_required_mw:     11.0,
  ride_through_s:       200,
}

/** Minimal complete TickPayload. dt_lead_next_s > 0 = "running". */
function makeTick(
  cc: ContingencyCoverage | null,
  dt_lead_next_s = 40.0,
  sim_time_seconds = 5.0,
): TickPayload {
  return {
    run_id:                    'test-run',
    tick_index:                1,
    sim_time_seconds,
    // Core power fields
    p_compute_mw:              10.0,
    p_cooling_mw:              2.0,
    p_total_mw:                12.0,
    net_demand_mw:             7.0,
    // GS-CHG-2026-08-08 Phase 2 — supply/served contract
    p_compute_demand_mw:       10.0,
    p_compute_served_mw:       null,
    p_compute_unserved_mw:     null,
    p_cooling_demand_mw:       2.0,
    p_cooling_served_mw:       null,
    p_cooling_unserved_mw:     null,
    p_demand_mw:               12.0,
    p_served_mw:               null,
    p_unserved_mw:             null,
    p_generation_mw:           9.0,
    p_imbalance_mw:            null,
    // Generation assets
    turbine_output_mw:         9.0,
    bess_output_mw:            0.0,
    fuel_cell_output_mw:       0.0,
    bess_setpoint_mw:          0.0,
    bess_soc_fraction:         0.95,
    bess_soc_corrupted_fraction: null,
    // BESS fleet aggregates
    bess_rated_mw:             30.0,
    bess_usable_mwh:           60.0,
    bess_unit_count:           1,
    // Thermal site parameters
    dt_thermal_seconds:        30.0,
    alpha_max:                 0.98,
    bess_anchor_reserve_mw:    1.0,
    design_peak_load_mw:       14.0,
    // EDL / PMS
    edl_dispatch_cost_usd:     null,
    pms_shortfall_log:         [],
    source_audit_violations:   [],
    // Confidence band + forecast
    confidence_lower_mw:       10.0,
    confidence_upper_mw:       14.0,
    forecast_mw:               12.0,
    // Balance decomposition channels
    grid_exchange_mw:          0.0,
    frequency_forcing_mw:      0.0,
    asset_delivery_error_mw:   0.0,
    model_error_mw:            0.0,
    binding_constraint:        null,
    // Frequency
    frequency_hz:              60.0,
    frequency_nominal_hz:      60.0,
    // Island collapse
    island_collapsed:          false,
    collapse_reason:           null,
    collapse_tick_index:       null,
    collapse_frequency_hz:     null,
    // Protection
    protection_provisional:    false,
    // Renewable
    p_renewable_mw:            5.0,
    p_renewable_curtailed_mw:  0.0,
    // Bridging / lead
    bess_bridging_seconds:     3060,
    bridging_basis:            'predicted_peak',
    turbine_ramp_credit_mw:    0.0,
    peak_shortfall_mw:         0.0,
    dt_lead_next_s,
    // Thermal headroom
    rated_cooling_mw:          4.59,
    absorbable_mw:             4.59,
    time_to_limit_s:           86400,
    approach_rate_mw_s:        0.0,
    // Turbine fleet
    turbine_units:             [],
    units_on_bus_count:        1,
    on_bus_output_mw:          9.0,
    ramp_capability_mw:        0.0,
    // Flags / misc
    insufficient_reserve_alert: false,
    data_quality_tags:         [],
    checkpoint_states:         {},
    kube_metrics:              null,
    solar_weather:             'clear',
    solar_conditions:          'good',
    contingency_coverage:      cc,
    advisory_telemetry:        null,
    fabric:                    null,
    // Pre-staging
    pre_staging_shift_mw:      0.0,
    pre_staging_precool_mw:    0.0,
    // PMS
    pms_fast_shed_active:      false,
    pms_order_conflict:        null,
    unrecognised_profile_alerts: [],
    curtailment_proposal_tiers:  [],
    scada_commands_issued:     0,
  } as unknown as TickPayload  // cast needed — fixture omits rarely-read fields
}

function seedTick(tick: TickPayload) {
  const store = useTickStore.getState()
  store.setRunMeta({ run_id: tick.run_id, playback_speed: 10 })
  store.pushTick(tick)
  store.drainFrame()
}

beforeEach(() => {
  useTickStore.getState().reset()
  cleanup()
})

// ---------------------------------------------------------------------------
// Branch 1 — Static default (no tick at all)
// ---------------------------------------------------------------------------

describe('VerdictBand — Branch 1: no tick (static default)', () => {
  it('shows the gen-trip cover label', () => {
    render(<VerdictBand />)
    expect(screen.getByText(/Gen-trip cover/i)).toBeInTheDocument()
  })

  it('shows "N−1 ready" as the value', () => {
    render(<VerdictBand />)
    expect(screen.getByText('N−1 ready')).toBeInTheDocument()
  })

  it('renders the gen-trip tile in blue (#4a9fe0)', () => {
    render(<VerdictBand />)
    const valueEl = screen.getByText('N−1 ready')
    expect(valueEl).toHaveStyle({ color: '#4a9fe0' })
  })

  it('the gen-trip tile is clickable (renders as a button)', () => {
    render(<VerdictBand />)
    const btn = screen.getByRole('button', {
      name: /Gen-trip cover.*click for plain-English explanation/i,
    })
    expect(btn).toBeInTheDocument()
  })

  it('shows "click to learn more" sub-text', () => {
    render(<VerdictBand />)
    expect(screen.getByText(/click to learn more/i)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Branch 2 — Running tick (dt_lead_next_s > 0)
// ---------------------------------------------------------------------------

describe('VerdictBand — Branch 2: running tick', () => {
  it('COVERED: shows covered text with deficit and time-to-close', () => {
    seedTick(makeTick(CC_COVERED, 40.0))
    render(<VerdictBand />)
    // genTripValue: "covered · 7.0 MW · closes in 30 s"
    expect(screen.getByText(/covered · 7\.0 MW · closes in 30 s/i)).toBeInTheDocument()
  })

  it('COVERED: value element rendered in teal (#3fb6a8)', () => {
    seedTick(makeTick(CC_COVERED, 40.0))
    render(<VerdictBand />)
    const valueEl = screen.getByText(/covered · 7\.0 MW/i)
    expect(valueEl).toHaveStyle({ color: '#3fb6a8' })
  })

  it('COVERED: shows "N−1 gen-trip covered" sub-text', () => {
    seedTick(makeTick(CC_COVERED, 40.0))
    render(<VerdictBand />)
    expect(screen.getByText(/N−1 gen-trip covered/i)).toBeInTheDocument()
  })

  it('COVERED_WITH_SHED: shows shed and ride-through figures', () => {
    seedTick(makeTick(CC_SHED, 40.0))
    render(<VerdictBand />)
    // genTripValue: "4.5 MW shed · 580 s ride-through"
    expect(screen.getByText(/4\.5 MW shed · 580 s ride-through/i)).toBeInTheDocument()
  })

  it('COVERED_WITH_SHED: value element rendered in amber (#f0883e)', () => {
    seedTick(makeTick(CC_SHED, 40.0))
    render(<VerdictBand />)
    const valueEl = screen.getByText(/4\.5 MW shed · 580 s ride-through/i)
    expect(valueEl).toHaveStyle({ color: '#f0883e' })
  })

  it('COVERED_WITH_SHED: shows shed sub-text', () => {
    seedTick(makeTick(CC_SHED, 40.0))
    render(<VerdictBand />)
    // genTripSub: "4.5 MW shed to cover · click for details"
    expect(screen.getByText(/4\.5 MW shed to cover/i)).toBeInTheDocument()
  })

  it('CANNOT_CARRY: shows uncovered deficit and ride-through', () => {
    seedTick(makeTick(CC_CANNOT, 40.0))
    render(<VerdictBand />)
    // genTripValue: "7.0 MW uncov · 200 s ride-through"
    expect(screen.getByText(/7\.0 MW uncov · 200 s ride-through/i)).toBeInTheDocument()
  })

  it('CANNOT_CARRY: value element rendered in red (#e05252)', () => {
    seedTick(makeTick(CC_CANNOT, 40.0))
    render(<VerdictBand />)
    const valueEl = screen.getByText(/7\.0 MW uncov · 200 s ride-through/i)
    expect(valueEl).toHaveStyle({ color: '#e05252' })
  })

  it('CANNOT_CARRY: shows "insufficient generation + shed" sub-text', () => {
    seedTick(makeTick(CC_CANNOT, 40.0))
    render(<VerdictBand />)
    expect(screen.getByText(/insufficient generation \+ shed/i)).toBeInTheDocument()
  })

  it('gen-trip tile is still clickable (button) when running', () => {
    seedTick(makeTick(CC_COVERED, 40.0))
    render(<VerdictBand />)
    const btn = screen.getByRole('button', {
      name: /Gen-trip cover.*click for plain-English explanation/i,
    })
    expect(btn).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Branch 3 — At-rest after run (dt_lead_next_s = 0)
// ---------------------------------------------------------------------------

describe('VerdictBand — Branch 3: at-rest after run (dt_lead_next_s = 0)', () => {
  it('COVERED: preserves covered text from final tick', () => {
    seedTick(makeTick(CC_COVERED, 0.0))
    render(<VerdictBand />)
    expect(screen.getByText(/covered · 7\.0 MW · closes in 30 s/i)).toBeInTheDocument()
  })

  it('COVERED: preserves teal colour from final tick', () => {
    seedTick(makeTick(CC_COVERED, 0.0))
    render(<VerdictBand />)
    const valueEl = screen.getByText(/covered · 7\.0 MW/i)
    expect(valueEl).toHaveStyle({ color: '#3fb6a8' })
  })

  it('COVERED_WITH_SHED: preserves amber colour from final tick', () => {
    seedTick(makeTick(CC_SHED, 0.0))
    render(<VerdictBand />)
    const valueEl = screen.getByText(/4\.5 MW shed · 580 s ride-through/i)
    expect(valueEl).toHaveStyle({ color: '#f0883e' })
  })

  it('CANNOT_CARRY: preserves red colour from final tick', () => {
    seedTick(makeTick(CC_CANNOT, 0.0))
    render(<VerdictBand />)
    const valueEl = screen.getByText(/7\.0 MW uncov · 200 s ride-through/i)
    expect(valueEl).toHaveStyle({ color: '#e05252' })
  })

  it('does not revert to "N−1 ready" when dt_lead_next_s = 0', () => {
    seedTick(makeTick(CC_COVERED, 0.0))
    render(<VerdictBand />)
    expect(screen.queryByText('N−1 ready')).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// TC-84 — console.log fires on state transitions
// ---------------------------------------------------------------------------

describe('VerdictBand — TC-84: gen-trip state-transition log', () => {
  it('logs transition when state changes from COVERED to COVERED_WITH_SHED', async () => {
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {})

    // Seed first tick: COVERED
    const tick1 = makeTick(CC_COVERED, 40.0, 5.0)
    tick1.tick_index = 1
    seedTick(tick1)
    render(<VerdictBand />)

    // Push second tick with a different coverage state
    const tick2 = makeTick(CC_SHED, 40.0, 10.0)
    tick2.tick_index = 2

    await act(async () => {
      useTickStore.getState().pushTick(tick2)
      useTickStore.getState().drainFrame()
    })

    // Find the transition log call
    const calls = logSpy.mock.calls
    const transitionCall = calls.find(args =>
      typeof args[0] === 'string' &&
      args[0].includes('[VerdictBand]') &&
      args[0].includes('COVERED') &&
      args[0].includes('COVERED_WITH_SHED'),
    )
    expect(transitionCall).toBeDefined()

    logSpy.mockRestore()
  })

  it('logs transition when state changes from COVERED_WITH_SHED to CANNOT_CARRY', async () => {
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {})

    const tick1 = makeTick(CC_SHED, 40.0, 5.0)
    tick1.tick_index = 1
    seedTick(tick1)
    render(<VerdictBand />)

    const tick2 = makeTick(CC_CANNOT, 40.0, 10.0)
    tick2.tick_index = 2

    await act(async () => {
      useTickStore.getState().pushTick(tick2)
      useTickStore.getState().drainFrame()
    })

    const calls = logSpy.mock.calls
    const transitionCall = calls.find(args =>
      typeof args[0] === 'string' &&
      args[0].includes('[VerdictBand]') &&
      args[0].includes('COVERED_WITH_SHED') &&
      args[0].includes('CANNOT_CARRY'),
    )
    expect(transitionCall).toBeDefined()

    logSpy.mockRestore()
  })

  it('does NOT log when state stays the same between ticks', async () => {
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {})

    const tick1 = makeTick(CC_COVERED, 40.0, 5.0)
    tick1.tick_index = 1
    seedTick(tick1)
    render(<VerdictBand />)

    const tick2 = makeTick(CC_COVERED, 40.0, 10.0)
    tick2.tick_index = 2

    await act(async () => {
      useTickStore.getState().pushTick(tick2)
      useTickStore.getState().drainFrame()
    })

    const verdictCalls = logSpy.mock.calls.filter(args =>
      typeof args[0] === 'string' && args[0].includes('[VerdictBand]'),
    )
    expect(verdictCalls).toHaveLength(0)

    logSpy.mockRestore()
  })

  it('includes deficit_mw in the transition log', async () => {
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {})

    const tick1 = makeTick(CC_COVERED, 40.0, 5.0)
    tick1.tick_index = 1
    seedTick(tick1)
    render(<VerdictBand />)

    const tick2 = makeTick(CC_CANNOT, 40.0, 10.0)
    tick2.tick_index = 2

    await act(async () => {
      useTickStore.getState().pushTick(tick2)
      useTickStore.getState().drainFrame()
    })

    const transitionCall = logSpy.mock.calls.find(args =>
      typeof args[0] === 'string' && args[0].includes('[VerdictBand]'),
    )
    expect(transitionCall).toBeDefined()
    // The log spreads multiple args; one should contain "deficit="
    const logLine = transitionCall!.join(' ')
    expect(logLine).toMatch(/deficit=/)

    logSpy.mockRestore()
  })
})

// ---------------------------------------------------------------------------
// Modal open/close — clicking gen-trip tile opens GenTripModal; onClose closes it
// ---------------------------------------------------------------------------

describe('VerdictBand — gen-trip modal: Branch 1 (static)', () => {
  it('modal is not shown before click', () => {
    render(<VerdictBand />)
    expect(screen.queryByTestId('gen-trip-modal-stub')).not.toBeInTheDocument()
  })

  it('opens GenTripModal when gen-trip tile is clicked', () => {
    render(<VerdictBand />)
    const btn = screen.getByRole('button', {
      name: /Gen-trip cover.*click for plain-English explanation/i,
    })
    fireEvent.click(btn)
    expect(screen.getByTestId('gen-trip-modal-stub')).toBeInTheDocument()
  })

  it('closes GenTripModal when onClose is called', () => {
    render(<VerdictBand />)
    fireEvent.click(
      screen.getByRole('button', {
        name: /Gen-trip cover.*click for plain-English explanation/i,
      }),
    )
    expect(screen.getByTestId('gen-trip-modal-stub')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /close-gen-trip-modal/i }))
    expect(screen.queryByTestId('gen-trip-modal-stub')).not.toBeInTheDocument()
  })
})

describe('VerdictBand — gen-trip modal: Branch 2 (running tick)', () => {
  it('modal is not shown before click', () => {
    seedTick(makeTick(CC_COVERED, 40.0))
    render(<VerdictBand />)
    expect(screen.queryByTestId('gen-trip-modal-stub')).not.toBeInTheDocument()
  })

  it('opens GenTripModal when gen-trip tile is clicked while running', () => {
    seedTick(makeTick(CC_COVERED, 40.0))
    render(<VerdictBand />)
    const btn = screen.getByRole('button', {
      name: /Gen-trip cover.*click for plain-English explanation/i,
    })
    fireEvent.click(btn)
    expect(screen.getByTestId('gen-trip-modal-stub')).toBeInTheDocument()
  })

  it('closes GenTripModal when onClose is called (running)', () => {
    seedTick(makeTick(CC_COVERED, 40.0))
    render(<VerdictBand />)
    fireEvent.click(
      screen.getByRole('button', {
        name: /Gen-trip cover.*click for plain-English explanation/i,
      }),
    )
    expect(screen.getByTestId('gen-trip-modal-stub')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /close-gen-trip-modal/i }))
    expect(screen.queryByTestId('gen-trip-modal-stub')).not.toBeInTheDocument()
  })
})

describe('VerdictBand — gen-trip modal: Branch 3 (at-rest after run)', () => {
  it('modal is not shown before click', () => {
    seedTick(makeTick(CC_COVERED, 0.0))
    render(<VerdictBand />)
    expect(screen.queryByTestId('gen-trip-modal-stub')).not.toBeInTheDocument()
  })

  it('opens GenTripModal when gen-trip tile is clicked at-rest', () => {
    seedTick(makeTick(CC_COVERED, 0.0))
    render(<VerdictBand />)
    const btn = screen.getByRole('button', {
      name: /Gen-trip cover.*click for plain-English explanation/i,
    })
    fireEvent.click(btn)
    expect(screen.getByTestId('gen-trip-modal-stub')).toBeInTheDocument()
  })

  it('closes GenTripModal when onClose is called (at-rest)', () => {
    seedTick(makeTick(CC_COVERED, 0.0))
    render(<VerdictBand />)
    fireEvent.click(
      screen.getByRole('button', {
        name: /Gen-trip cover.*click for plain-English explanation/i,
      }),
    )
    expect(screen.getByTestId('gen-trip-modal-stub')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /close-gen-trip-modal/i }))
    expect(screen.queryByTestId('gen-trip-modal-stub')).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Reserve tile — sufficient / insufficient states (running branch only)
// ---------------------------------------------------------------------------

describe('VerdictBand — Reserve tile: no alert (running)', () => {
  it('shows "sufficient" when no alert is active', () => {
    seedTick(makeTick(CC_COVERED, 40.0))
    render(<VerdictBand />)
    expect(screen.getByText('sufficient')).toBeInTheDocument()
  })

  it('Reserve tile value rendered in teal (#3fb6a8) when no alert', () => {
    seedTick(makeTick(CC_COVERED, 40.0))
    render(<VerdictBand />)
    const valueEl = screen.getByText('sufficient')
    expect(valueEl).toHaveStyle({ color: '#3fb6a8' })
  })

  it('Reserve tile is clickable (renders as a button) even without an alert', () => {
    seedTick(makeTick(CC_COVERED, 40.0))
    render(<VerdictBand />)
    const btn = screen.getByRole('button', {
      name: /Reserve.*click for plain-English explanation/i,
    })
    expect(btn).toBeInTheDocument()
  })

  it('opens ReserveModal when Reserve tile is clicked without an alert', () => {
    seedTick(makeTick(CC_COVERED, 40.0))
    render(<VerdictBand />)
    expect(screen.queryByTestId('reserve-modal-stub')).not.toBeInTheDocument()
    fireEvent.click(
      screen.getByRole('button', { name: /Reserve.*click for plain-English explanation/i }),
    )
    expect(screen.getByTestId('reserve-modal-stub')).toBeInTheDocument()
  })
})

describe('VerdictBand — Reserve tile: insufficient_reserve_alert=true', () => {
  /** Helper: make a running tick that carries the alert flag. */
  function makeAlertTick(): TickPayload {
    return { ...makeTick(CC_COVERED, 40.0), insufficient_reserve_alert: true }
  }

  it('shows "insufficient" when the alert is latched', () => {
    seedTick(makeAlertTick())
    render(<VerdictBand />)
    expect(screen.getByText('insufficient')).toBeInTheDocument()
  })

  it('Reserve tile value rendered in amber (#f0883e) when alert is latched', () => {
    seedTick(makeAlertTick())
    render(<VerdictBand />)
    const valueEl = screen.getByText('insufficient')
    expect(valueEl).toHaveStyle({ color: '#f0883e' })
  })

  it('Reserve tile renders as a button when alert is latched', () => {
    seedTick(makeAlertTick())
    render(<VerdictBand />)
    const btn = screen.getByRole('button', {
      name: /Reserve.*click for plain-English explanation/i,
    })
    expect(btn).toBeInTheDocument()
  })

  it('ReserveModal is not shown before the tile is clicked', () => {
    seedTick(makeAlertTick())
    render(<VerdictBand />)
    expect(screen.queryByTestId('reserve-modal-stub')).not.toBeInTheDocument()
  })

  it('opens ReserveModal when the Reserve tile is clicked during an alert', () => {
    seedTick(makeAlertTick())
    render(<VerdictBand />)
    fireEvent.click(
      screen.getByRole('button', { name: /Reserve.*click for plain-English explanation/i }),
    )
    expect(screen.getByTestId('reserve-modal-stub')).toBeInTheDocument()
  })

  it('tile reverts to "sufficient" after acknowledgeAlert() is called', async () => {
    const alertTick = makeAlertTick()
    seedTick(alertTick)
    render(<VerdictBand />)

    // Alert is latched — tile reads "insufficient"
    expect(screen.getByText('insufficient')).toBeInTheDocument()

    // Operator acknowledges the alert
    await act(async () => {
      useTickStore.getState().acknowledgeAlert(alertTick.tick_index)
    })

    // latchedAlert is now null → tile reverts to "sufficient"
    expect(screen.getByText('sufficient')).toBeInTheDocument()
    expect(screen.queryByText('insufficient')).not.toBeInTheDocument()
  })
})
