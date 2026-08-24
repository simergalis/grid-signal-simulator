/**
 * Per-scenario BESS sizing regression coverage.
 *
 * The PlantDiagram owns the selection-side effect that seeds the operator
 * widget. Keep this test at the component boundary so it verifies the real
 * store, effect, and widget together rather than only testing applyPreset().
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { PlantDiagram } from '../opening/PlantDiagram'
import { BessConfigWidget } from '../subsystem/panels/BessConfigWidget'
import { useScenarioStore } from '../store/scenarioStore'
import { useBessConfigStore } from '../store/bessConfigStore'

const DEMO_ISLANDED_RAMP_SPEC = {
  ui_bess_rated_mw: 50,
  ui_bess_usable_mwh: 50,
}

const DEMO_20MW_SPEC = {
  ui_bess_rated_mw: null,
  ui_bess_usable_mwh: null,
}

function mockScenarioDetails() {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const scenarioId = String(input).split('/').pop()
    const spec = scenarioId === 'demo-islanded-ramp'
      ? DEMO_ISLANDED_RAMP_SPEC
      : DEMO_20MW_SPEC
    return {
      ok: true,
      json: async () => ({ scenario_id: scenarioId, spec }),
    } as Response
  }))
}

beforeEach(() => {
  cleanup()
  Object.defineProperty(HTMLElement.prototype, 'scrollTo', {
    configurable: true,
    value: vi.fn(),
  })
  useScenarioStore.setState({ selectedId: null, selectedSpec: null })
  useBessConfigStore.setState({
    ratedMw: 30,
    usableMwh: 30,
    selectedPresetId: 'freq-anchor',
  })
  mockScenarioDetails()
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('scenario-driven BESS widget seeding', () => {
  it('seeds 50 MW / 50 MWh when demo-islanded-ramp is selected', async () => {
    useScenarioStore.setState({ selectedId: 'demo-islanded-ramp' })
    render(<PlantDiagram onNodeClick={() => {}} />)

    await waitFor(() => {
      expect(useBessConfigStore.getState()).toMatchObject({
        selectedPresetId: 'freq-anchor',
        ratedMw: 50,
        usableMwh: 50,
      })
    })

    render(<BessConfigWidget />)
    const freqAnchor = screen.getAllByRole('button', { name: /Freq\. Anchor/i })
      .find(button => button.textContent?.includes('50 MW'))
    if (!freqAnchor) throw new Error('Freq. Anchor card was not rendered with 50 MW')
    expect(freqAnchor).toHaveTextContent(/50 MW/)
    expect(freqAnchor).toHaveTextContent(/\/ 50 MWh/)
  })

  it('resets to the 30 MW / 30 MWh default when switching to demo-20mw', async () => {
    useScenarioStore.setState({ selectedId: 'demo-islanded-ramp' })
    render(<PlantDiagram onNodeClick={() => {}} />)
    await waitFor(() => expect(useBessConfigStore.getState().ratedMw).toBe(50))

    await act(async () => {
      useScenarioStore.getState().selectScenario('demo-20mw')
    })

    await waitFor(() => {
      expect(useBessConfigStore.getState()).toMatchObject({
        selectedPresetId: 'freq-anchor',
        ratedMw: 30,
        usableMwh: 30,
      })
    })

    render(<BessConfigWidget />)
    const freqAnchor = screen.getAllByRole('button', { name: /Freq\. Anchor/i })
      .find(button => button.textContent?.includes('30 MW'))
    if (!freqAnchor) throw new Error('Freq. Anchor card was not rendered with 30 MW')
    expect(freqAnchor).toHaveTextContent(/30 MW/)
    expect(freqAnchor).toHaveTextContent(/\/ 30 MWh/)
  })
})