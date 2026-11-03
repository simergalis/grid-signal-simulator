import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { RunControlBar } from '../components/RunControlBar'
import { DemoBar } from '../opening/DemoBar'
import { useScenarioStore } from '../store/scenarioStore'

const QUEUE_SCENARIO_ID = 'proxim8-5mw-24h-queue'
const originalFetchScenarios = useScenarioStore.getState().fetchScenarios

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  useScenarioStore.setState({ fetchScenarios: originalFetchScenarios })
})

describe('scenario picker labels', () => {
  it('shows the friendly queue-stress name while keeping the scenario ID as the option value', async () => {
    useScenarioStore.setState({
      scenarios: [],
      selectedId: QUEUE_SCENARIO_ID,
      selectedSpec: null,
      isLoading: false,
      error: null,
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{
        scenario_id: QUEUE_SCENARIO_ID,
        name: QUEUE_SCENARIO_ID,
        description: '',
        created_at: '',
      }],
    }))

    render(
      <RunControlBar
        runId={null}
        lastRunId={null}
        isPaused={false}
        onRunStarted={() => {}}
        onRunStopped={() => {}}
        onRunPaused={() => {}}
        onRunResumed={() => {}}
        onNewScenario={() => {}}
        onViewResults={() => {}}
      />,
    )

    const option = await screen.findByRole('option', { name: 'Proxim8 with queue-stress' })
    expect(option).toHaveValue(QUEUE_SCENARIO_ID)
  })

  it('shows the friendly queue-stress name in the opening-screen picker and run label', () => {
    useScenarioStore.setState({
      scenarios: [{
        scenario_id: QUEUE_SCENARIO_ID,
        name: QUEUE_SCENARIO_ID,
        description: '',
        created_at: '',
      }],
      selectedId: QUEUE_SCENARIO_ID,
      selectedSpec: null,
      isLoading: false,
      error: null,
      fetchScenarios: vi.fn().mockResolvedValue(undefined),
    })

    render(
      <DemoBar
        runId="active-run"
        lastRunId={null}
        isPaused={false}
        onRunStarted={() => {}}
        onRunStopped={() => {}}
        onRunPaused={() => {}}
        onRunResumed={() => {}}
        onViewResults={() => {}}
        onManageScenarios={() => {}}
      />,
    )

    const option = screen.getByRole('option', { name: 'Proxim8 with queue-stress' })
    expect(option).toHaveValue(QUEUE_SCENARIO_ID)
    expect(screen.getByText('Proxim8 with queue-stress · 1× speed')).toBeInTheDocument()
  })
})
