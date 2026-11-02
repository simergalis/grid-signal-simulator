import { StrandedPowerPanel } from './StrandedPowerPanel'

interface Props {
  runId: string | null
  scenario: string
  active: boolean
  paused: boolean
}

export function LivePowerPage({ runId, scenario, active, paused }: Props) {
  return (
    <main className="h-full overflow-y-auto bg-canvas px-4 py-4 md:px-6">
      <header className="mb-4 flex flex-wrap items-end justify-between gap-3 border-b border-border pb-3">
        <div>
          <p className="font-mono text-[9px] font-bold uppercase tracking-[0.16em] text-accent">
            Power capacity · live instrument
          </p>
          <h1 className="mt-1 font-mono text-lg font-semibold text-foreground">
            Live stranded capacity
          </h1>
          <p className="mt-1 max-w-2xl text-xs leading-5 text-muted">
            Facility demand measured against the scenario import cap. Minute samples and totals are
            supplied by the simulator and refreshed while the run is active.
          </p>
        </div>
        {runId && (
          <div className="font-mono text-[10px] text-muted">
            RUN <span className="text-foreground">{runId}</span>
          </div>
        )}
      </header>

      {!runId ? (
        <section
          className="rounded border border-border bg-surface p-5"
          data-testid="live-power-empty-run"
        >
          <p className="font-mono text-xs font-semibold uppercase tracking-wider text-foreground">
            No active run
          </p>
          <p className="mt-2 max-w-xl text-xs leading-5 text-muted">
            Start a scenario to see cumulative stranded-capacity statistics and the 1-minute demand
            trace. The most recent run remains available here after completion.
          </p>
        </section>
      ) : (
        <StrandedPowerPanel
          runId={runId}
          scenario={scenario}
          live={active}
          paused={paused}
        />
      )}
    </main>
  )
}
