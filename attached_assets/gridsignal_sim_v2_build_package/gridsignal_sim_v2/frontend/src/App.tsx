/**
 * App.tsx — Root routing and run lifecycle (Step 8 / UI-Hierarchy V-2).
 *
 * Two distinct layouts:
 *
 * OPENING LAYOUT  (currentPage === 'readiness' and no resultsRunId)
 *   GridSignalHeader  — brand bar, STANDBY/LIVE badge, UTC clock, "How it works"
 *   OpeningScreen     — three-band SCADA mimic (V-2)
 *   DemoBar           — demo controls (scenario + speed + START)
 *   TopologyExplainer — modal, opened by GridSignalHeader "How it works"
 *
 * INNER PAGE LAYOUT  (all other pages / results screen)
 *   RunControlBar  — scenario picker + speed + start/stop + view results
 *   SimClockHeader — sim clock, decimation badge, DQ legend
 *   Tab navigation — Readiness | Overview | Proposals | … | Scenario Planner
 *   Page content
 *
 * Render loop: 4 Hz setInterval (250 ms) drains pending WS ticks.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { LoginPage }               from './components/LoginPage'
import { GridSignalHeader }        from './opening/GridSignalHeader'
import { DemoBar }                 from './opening/DemoBar'
import { TopologyExplainer }       from './opening/TopologyExplainer'
import { OpeningScreen }           from './opening/OpeningScreen'
import { SimClockHeader }          from './components/SimClockHeader'
import { HeroPanel }               from './components/HeroPanel'
import { ForecastChart }           from './components/ForecastChart'
import { AssetReservePanel }       from './components/AssetReservePanel'
import { RunControlBar }           from './components/RunControlBar'
import { ScenarioBuilder }         from './components/ScenarioBuilder'
import { ResultsScreen }           from './components/ResultsScreen'
import { ProposalsPage }           from './components/ProposalsPage'
import { NetworkTelemetryPage }    from './components/NetworkTelemetryPage'
import { ProcurementPage }         from './components/ProcurementPage'
import { ThermalCoolingPage }      from './components/ThermalCoolingPage'
import { ScenarioPlannerPage }     from './components/ScenarioPlannerPage'
import { ScenarioManagerPage }     from './components/ScenarioManagerPage'
import { ScenarioModal }           from './components/ScenarioModal'
import { AdminPage }               from './components/AdminPage'
import { ChangePasswordModal }     from './components/ChangePasswordModal'
import { useTickStore }            from './store/tickStore'
import { useScenarioStore }        from './store/scenarioStore'
import { useTickStream }           from './ws/useTickStream'

type PageView = 'readiness' | 'overview' | 'proposals' | 'procurement' | 'network' | 'thermal' | 'scenarios' | 'scenario-manager' | 'admin'

const FRAME_INTERVAL_MS = 250   // 4 Hz render loop

export default function App() {
  // ── Auth state ─────────────────────────────────────────────────────────────
  // null = not yet checked, false = unauthenticated, string = display name
  const [authUser,      setAuthUser]      = useState<string | false | null>(null)
  const [userRole,      setUserRole]      = useState<string>('operator')

  // Check session on mount by calling /api/auth/me
  useEffect(() => {
    fetch('/api/auth/me', { credentials: 'include' })
      .then(r => r.ok ? r.json() : null)
      .then((data: { display_name: string; role: string } | null) => {
        if (data) {
          setAuthUser(data.display_name)
          setUserRole(data.role)
        } else {
          setAuthUser(false)
        }
      })
      .catch(() => setAuthUser(false))
  }, [])

  const handleAuthenticated = useCallback((displayName: string, role: string) => {
    setAuthUser(displayName)
    setUserRole(role)
  }, [])

  const handleLogout = useCallback(async () => {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' })
    setAuthUser(false)
  }, [])

  // ── Auth gate ──────────────────────────────────────────────────────────────
  if (authUser === null) {
    // Still checking session — show minimal loading state
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: '#0b1017' }}>
        <span className="font-sans" style={{ color: '#4b5764', fontSize: 13 }}>Loading…</span>
      </div>
    )
  }
  if (authUser === false) {
    const isAdminPath = window.location.pathname === '/admin'
    return <LoginPage onAuthenticated={handleAuthenticated} adminMode={isAdminPath} />
  }

  // ── Authenticated — render the main interface ──────────────────────────────
  return <AuthenticatedApp displayName={authUser} role={userRole} onLogout={handleLogout} />
}

interface AuthAppProps {
  displayName: string
  role: string
  onLogout: () => void
}

function AuthenticatedApp({ displayName, role, onLogout }: AuthAppProps) {
  const [runId,         setRunId]         = useState<string | null>(null)
  const [lastRunId,     setLastRunId]     = useState<string | null>(null)
  const [resultsRunId,  setResultsRunId]  = useState<string | null>(null)
  const [isPaused,      setIsPaused]      = useState(false)
  const [drawerOpen,    setDrawerOpen]    = useState(false)
  const [editId,        setEditId]        = useState<string | null>(null)
  const [currentPage,   setCurrentPage]   = useState<PageView>(() =>
    role === 'admin' && window.location.pathname === '/admin' ? 'admin' : 'readiness'
  )
  const [agentsEnabled,       setAgentsEnabled]       = useState(true)
  const [topoOpen,            setTopoOpen]            = useState(false)
  const [scenariosOpen,       setScenariosOpen]       = useState(false)
  const [changePasswordOpen,  setChangePasswordOpen]  = useState(false)

  const drainFrame     = useTickStore(s => s.drainFrame)
  const setRunMeta     = useTickStore(s => s.setRunMeta)
  const reset          = useTickStore(s => s.reset)
  const setRunPaused   = useTickStore(s => s.setRunPaused)
  const selectScenario = useScenarioStore(s => s.selectScenario)

  // 4 Hz render loop — drains pending WS ticks into display state.
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  useEffect(() => {
    intervalRef.current = setInterval(drainFrame, FRAME_INTERVAL_MS)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [drainFrame])

  // Run lifecycle callbacks
  const handleRunStarted = useCallback((id: string, speed: number, socFloor?: number, socCeil?: number) => {
    reset()
    setIsPaused(false)
    setRunPaused(false)
    setRunId(id)
    setLastRunId(id)
    setResultsRunId(null)
    setRunMeta({ run_id: id, playback_speed: speed, soc_floor_pct: socFloor, soc_ceil_pct: socCeil })
    // Stay on opening screen — flow lines thicken as the turbine ramps.
    // User navigates to Overview via the tab strip or a modal link.
  }, [reset, setRunMeta, setRunPaused])

  // Auto-detect a run started externally (e.g. via curl / another client).
  // Polls GET /runs every 2 s when idle; stops once a run is tracked.
  useEffect(() => {
    if (runId !== null) return
    const poll = async () => {
      try {
        const resp = await fetch('/runs')
        if (!resp.ok) return
        const data = await resp.json() as { run_ids: string[] }
        if (data.run_ids.length > 0) {
          const id = data.run_ids[0]
          reset()
          setRunId(id)
          setLastRunId(id)
          setRunMeta({ run_id: id, playback_speed: 10 })
        }
      } catch { /* ignore */ }
    }
    poll()
    const timer = setInterval(poll, 2000)
    return () => clearInterval(timer)
  }, [runId, reset, setRunMeta])

  const handleRunStopped = useCallback(() => {
    setRunId(null)
    setIsPaused(false)
    setRunPaused(false)
    reset()
  }, [reset, setRunPaused])

  const handleRunPaused = useCallback(() => {
    setIsPaused(true)
    setRunPaused(true)
  }, [setRunPaused])

  const handleRunResumed = useCallback(() => {
    setIsPaused(false)
    setRunPaused(false)
  }, [setRunPaused])

  // WS tick stream — must be called after handleRunStopped so the run_complete
  // sentinel from the server transitions the UI to the completed state instead
  // of spinning in a reconnect loop.
  useTickStream(runId, handleRunStopped)

  const handleViewResults = useCallback((id: string) => {
    setResultsRunId(id)
  }, [])

  const handleRerun = useCallback((scenarioId: string) => {
    setResultsRunId(null)
    selectScenario(scenarioId)
    // Ensure the RunControlBar is visible (inner page layout).
    setCurrentPage(prev => prev === 'readiness' ? 'overview' : prev)
  }, [selectScenario])

  const handleNewScenario = useCallback(() => {
    setEditId(null)
    setDrawerOpen(true)
  }, [])

  const handleEditScenario = useCallback((id: string) => {
    setEditId(id)
    setDrawerOpen(true)
  }, [])

  const handleDrawerSaved = useCallback((scenarioId: string) => {
    selectScenario(scenarioId)
    setDrawerOpen(false)
  }, [selectScenario])

  const handleToggleAgents = useCallback(() => {
    const next = !agentsEnabled
    setAgentsEnabled(next)
    fetch('/api/agents/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: next }),
    }).catch(() => {})
  }, [agentsEnabled])

  // ── Results screen (any page) ──────────────────────────────────────────────
  if (resultsRunId !== null) {
    return (
      <div className="flex h-screen flex-col bg-canvas text-text overflow-hidden">
        <ResultsScreen
          runId={resultsRunId}
          onClose={() => setResultsRunId(null)}
          onRerun={handleRerun}
        />
      </div>
    )
  }

  // ── Opening layout — no tab nav, brand header, demo bar ───────────────────
  if (currentPage === 'readiness') {
    return (
      <div className="flex h-screen flex-col bg-canvas text-text overflow-hidden">
        <GridSignalHeader
          runId={runId}
          onHowItWorks={() => setTopoOpen(true)}
          displayName={displayName}
          role={role}
          onLogout={onLogout}
          onAdmin={role === 'admin' ? () => setCurrentPage('admin') : undefined}
          onChangePassword={() => setChangePasswordOpen(true)}
        />

        <main className="flex-1 overflow-hidden">
          <OpeningScreen onNavigate={(tabId) => setCurrentPage(tabId as PageView)} />
        </main>

        <DemoBar
          runId={runId}
          lastRunId={lastRunId}
          isPaused={isPaused}
          onRunStarted={handleRunStarted}
          onRunStopped={handleRunStopped}
          onRunPaused={handleRunPaused}
          onRunResumed={handleRunResumed}
          onViewResults={handleViewResults}
          onManageScenarios={() => setScenariosOpen(true)}
        />

        {topoOpen && (
          <TopologyExplainer onClose={() => setTopoOpen(false)} />
        )}

        {changePasswordOpen && (
          <ChangePasswordModal onClose={() => setChangePasswordOpen(false)} />
        )}

        {scenariosOpen && (
          <ScenarioModal
            onClose={() => setScenariosOpen(false)}
            onNew={() => { setScenariosOpen(false); handleNewScenario() }}
            onEdit={id => { setScenariosOpen(false); handleEditScenario(id) }}
            onExecute={(runId, speed, socFloor, socCeil) => {
              setScenariosOpen(false)
              handleRunStarted(runId, speed, socFloor, socCeil)
            }}
          />
        )}

        {drawerOpen && (
          <ScenarioBuilder
            editId={editId}
            onClose={() => setDrawerOpen(false)}
            onSaved={handleDrawerSaved}
          />
        )}
      </div>
    )
  }

  // ── Inner page layout — RunControlBar + SimClockHeader + tabs ─────────────
  return (
    <div className="flex h-screen flex-col bg-canvas text-text overflow-hidden">

      <RunControlBar
        runId={runId}
        lastRunId={lastRunId}
        isPaused={isPaused}
        onRunStarted={handleRunStarted}
        onRunStopped={handleRunStopped}
        onRunPaused={handleRunPaused}
        onRunResumed={handleRunResumed}
        onNewScenario={handleNewScenario}
        onViewResults={handleViewResults}
      />

      <SimClockHeader onChangePassword={() => setChangePasswordOpen(true)} isPaused={isPaused} />

      {/* Page navigation tabs */}
      <div className="flex gap-px border-b border-border bg-border flex-shrink-0">
        {([
          ['readiness',   'Readiness'],
          ['overview',    'Overview'],
          ['proposals',   'Proposals & Learning'],
          ['procurement', 'Grid & Procurement'],
          ['network',     'Network Telemetry'],
          ['thermal',     'Thermal & Cooling'],
          ['scenarios',         'Scenario Planner'],
          ['scenario-manager',  'Scenarios'],
        ] as const).map(([page, label]) => (
          <button
            key={page}
            onClick={() => setCurrentPage(page)}
            className={`px-4 py-2 text-xs font-medium transition-colors ${
              currentPage === page
                ? 'bg-surface text-text border-b-2 border-accent -mb-px'
                : 'bg-canvas text-text-muted hover:text-text hover:bg-surface/50'
            }`}
          >
            {label}
            {page === 'proposals' && agentsEnabled && (
              <span className="ml-1.5 inline-block w-1.5 h-1.5 rounded-full bg-green-400 align-middle" />
            )}
          </button>
        ))}
        {/* Renewable Console — external link to /solar-console */}
        <a
          href="/solar-console"
          target="_blank"
          rel="noopener noreferrer"
          className="px-4 py-2 text-xs font-medium transition-colors text-text-muted hover:text-text hover:bg-surface/50"
          style={{ textDecoration: 'none' }}
        >
          ☀ Renewable Console ↗
        </a>

        {/* Admin tab — only visible to admin-role users */}
        {role === 'admin' && (
          <button
            onClick={() => setCurrentPage('admin')}
            className={`px-4 py-2 text-xs font-medium transition-colors ml-auto ${
              currentPage === 'admin'
                ? 'bg-surface text-text border-b-2 border-accent -mb-px'
                : 'bg-canvas text-text-muted hover:text-text hover:bg-surface/50'
            }`}
          >
            ⚙ Admin
          </button>
        )}
      </div>

      {/* Page content */}
      {currentPage === 'overview' ? (
        <main className="flex-1 grid grid-cols-2 grid-rows-[auto_1fr] gap-px bg-border overflow-hidden">
          <div className="col-span-2 bg-surface overflow-auto">
            <HeroPanel />
          </div>
          <div className="bg-surface overflow-hidden">
            <ForecastChart />
          </div>
          <div className="bg-surface overflow-auto">
            <AssetReservePanel />
          </div>
        </main>
      ) : currentPage === 'proposals' ? (
        <main className="flex-1 overflow-hidden">
          <ProposalsPage
            runId={runId ?? lastRunId}
            agentsEnabled={agentsEnabled}
            onToggleAgents={handleToggleAgents}
          />
        </main>
      ) : currentPage === 'procurement' ? (
        <main className="flex-1 overflow-hidden">
          <ProcurementPage runId={runId ?? lastRunId} />
        </main>
      ) : currentPage === 'network' ? (
        <main className="flex-1 overflow-hidden">
          <NetworkTelemetryPage runId={runId ?? lastRunId} />
        </main>
      ) : currentPage === 'thermal' ? (
        <main className="flex-1 overflow-hidden">
          <ThermalCoolingPage runId={runId ?? lastRunId} />
        </main>
      ) : currentPage === 'scenario-manager' ? (
        <main className="flex-1 overflow-hidden">
          <ScenarioManagerPage
            onNewScenario={handleNewScenario}
            onEditScenario={handleEditScenario}
            onExecute={(runId, speed, socFloor, socCeil) =>
              handleRunStarted(runId, speed, socFloor, socCeil)
            }
          />
        </main>
      ) : currentPage === 'admin' && role === 'admin' ? (
        <main className="flex-1 overflow-hidden">
          <AdminPage />
        </main>
      ) : (
        <main className="flex-1 overflow-hidden">
          <ScenarioPlannerPage runId={runId ?? lastRunId} />
        </main>
      )}

      {drawerOpen && (
        <ScenarioBuilder
          editId={editId}
          onClose={() => setDrawerOpen(false)}
          onSaved={handleDrawerSaved}
        />
      )}

      {changePasswordOpen && (
        <ChangePasswordModal onClose={() => setChangePasswordOpen(false)} />
      )}
    </div>
  )
}
