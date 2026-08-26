/**
 * Task #339 — GPU Generator auto-arm on run start.
 *
 * RunControlBar.handleStart() must arm the GPU Generator from the started
 * scenario's `generator_config` preset without the operator touching it, and
 * this must hold even when the scenarioStore's async spec fetch has not
 * resolved yet at the moment Start is clicked (page-load / scenario-switch
 * race described in the task).
 */

import { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { RunControlBar } from '../components/RunControlBar'
import { useScenarioStore } from '../store/scenarioStore'
import { useBessConfigStore } from '../store/bessConfigStore'
import { useGpuGeneratorStore, DEFAULT_CONFIG } from '../store/gpuGeneratorStore'

const BURST_STORM_CONFIG = {
  ratePerMinute: 6,
  burstMode: true,
  burstSize: [4, 10],
  burstIntervalSeconds: [30, 90],
  tenantWeights: { a: 0.40, b: 0.35, c: 0.25 },
  jobSizes: { small: 0.20, medium: 0.40, large: 0.40 },
  maxJobsPerTenant: 15,
  jobDurationRange: [90, 300],
  tenantContracts: { a: 1.40, b: 1.00, c: 0.60 },
}

const SCENARIO_ID = 'scenario-burst-storm-demo'

/** Mirrors how App.tsx wires runId: it is owned by the parent, set from
 *  onRunStarted's callback argument, not by RunControlBar itself. */
function RunControlBarHarness() {
  const [runId, setRunId] = useState<string | null>(null)
  return (
    <RunControlBar
      runId={runId}
      lastRunId={null}
      isPaused={false}
      onRunStarted={(id) => setRunId(id)}
      onRunStopped={() => setRunId(null)}
      onRunPaused={() => {}}
      onRunResumed={() => {}}
      onNewScenario={() => {}}
      onViewResults={() => {}}
    />
  )
}

function renderRunControlBar() {
  return render(<RunControlBarHarness />)
}

function mockFetchRoutes(generatorConfig: unknown) {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url === '/runs' && init?.method === 'POST') {
      return {
        ok: true,
        json: async () => ({ run_id: 'run-abc123', soc_floor_pct: 10, soc_ceil_pct: 95 }),
      } as Response
    }
    if (url === `/scenarios/${SCENARIO_ID}`) {
      return {
        ok: true,
        json: async () => ({
          scenario_id: SCENARIO_ID,
          spec: { generator_config: generatorConfig },
        }),
      } as Response
    }
    if (url === '/scenarios') {
      return { ok: true, json: async () => [] } as Response
    }
    throw new Error(`Unexpected fetch: ${url}`)
  }))
}

beforeEach(() => {
  cleanup()
  useGpuGeneratorStore.getState().reset()
  useGpuGeneratorStore.setState({ config: DEFAULT_CONFIG })
  useBessConfigStore.setState({ ratedMw: null, usableMwh: null, selectedPresetId: null })
  useScenarioStore.setState({
    scenarios: [{ scenario_id: SCENARIO_ID, name: 'Burst Storm Demo', description: '', created_at: '' }],
    selectedId: SCENARIO_ID,
    selectedSpec: null,
    isLoading: false,
    error: null,
  })
})

afterEach(() => {
  cleanup()
  useGpuGeneratorStore.getState().reset()
  vi.unstubAllGlobals()
})

describe('GPU Generator auto-arm on run start', () => {
  it('arms the generator with the preset once selectedSpec has already loaded', async () => {
    mockFetchRoutes(BURST_STORM_CONFIG)
    useScenarioStore.setState({ selectedSpec: { generator_config: BURST_STORM_CONFIG } as never })

    renderRunControlBar()
    fireEvent.click(screen.getByRole('button', { name: /start/i }))

    await waitFor(() => {
      expect(useGpuGeneratorStore.getState().running).toBe(true)
    })
    expect(useGpuGeneratorStore.getState().config).toEqual(BURST_STORM_CONFIG)
  })

  it('still arms the generator when selectedSpec has not resolved yet (scenarioStore fetch race)', async () => {
    // Simulates the page-load / scenario-switch race: selectedId is set but
    // the async fetchSelectedSpec() has not populated selectedSpec yet.
    mockFetchRoutes(BURST_STORM_CONFIG)
    useScenarioStore.setState({ selectedSpec: null })

    renderRunControlBar()
    fireEvent.click(screen.getByRole('button', { name: /start/i }))

    await waitFor(() => {
      expect(useGpuGeneratorStore.getState().running).toBe(true)
    })
    expect(useGpuGeneratorStore.getState().config).toEqual(BURST_STORM_CONFIG)
  })

  it('does not arm the generator for a scenario with no generator_config preset', async () => {
    mockFetchRoutes(null)
    useScenarioStore.setState({ selectedSpec: null })

    renderRunControlBar()
    fireEvent.click(screen.getByRole('button', { name: /start/i }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /stop/i })).toBeInTheDocument()
    })
    expect(useGpuGeneratorStore.getState().running).toBe(false)
  })

  it('does not overwrite an operator-armed generator config with the scenario preset', async () => {
    mockFetchRoutes(BURST_STORM_CONFIG)
    useScenarioStore.setState({ selectedSpec: { generator_config: BURST_STORM_CONFIG } as never })
    const operatorConfig = { ...DEFAULT_CONFIG, ratePerMinute: 11 }
    useGpuGeneratorStore.getState().restartWith(operatorConfig)

    renderRunControlBar()
    fireEvent.click(screen.getByRole('button', { name: /start/i }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /stop/i })).toBeInTheDocument()
    })
    expect(useGpuGeneratorStore.getState().config).toEqual(operatorConfig)
  })
})
