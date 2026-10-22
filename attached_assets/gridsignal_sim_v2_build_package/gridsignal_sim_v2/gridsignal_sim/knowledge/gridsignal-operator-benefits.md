# GridSignal operator benefits

## The operational gap

GPU job schedulers such as Slurm, Kubernetes, and Ray can commit a job to
hardware before that hardware begins to draw power. Traditional real-time
controls see the measured demand after it appears on the site bus. GridSignal
reads scheduler queue and allocation signals to provide an earlier view of
power demand while the job is still waiting to run.

## How operators use the lead time

The early signal gives the site's existing systems time to prepare for an
expected demand transition. It can inform a turbine start, battery position,
or hall pre-cooling decision before a demand spike reaches the meter.
GridSignal is not another physical control loop; it supplies lead-time
intelligence to the systems that already manage generation, storage, and
cooling.

## Forecast horizons

GridSignal distinguishes observed scheduler intent from long-range
forecasting. Minutes ahead, Slurm, Kubernetes, and Ray queue or allocation
signals can identify GPU work that is committed or waiting to execute before
the GPUs draw their full power. This gives operators advance notice to stage
turbines, BESS, fuel cells, or cooling.

Hours ahead, the rolling planning forecast can project scheduled workload
starts and ends across a roughly 15-minute to 4-hour horizon. This helps
identify planned future peaks and reserve pressure. It is an advisory
planning projection, not a promise that every workload will execute at
exactly the forecast time.

GridSignal cannot know the exact execution time of arbitrary work that has
not been scheduled or exposed through telemetry. Forecast accuracy depends on
the quality and stability of the scheduler signals. GridSignal predicts and
recommends; the site's existing scheduler and power-management systems remain
responsible for execution and equipment control.

## Multi-tenant visibility

Colocation and multi-tenant GPU facilities may have several tenants and
several schedulers, with no single view across pending workloads. GridSignal
turns the scheduler signals that the site already has into a shared early view
of the power demand those workloads are likely to create.

## Advisory and tenant boundary

GridSignal proposes; the existing power management system decides and
executes. It does not replace or directly command turbines, batteries,
cooling systems, protection relays, or fast-shed equipment. Better anticipated
site power can reduce reactive throttling, curtailment, and emergency
load-shedding surprises for tenant jobs. The system uses scheduler telemetry
already available to the site and does not require tenants to expose more
workload detail than they already share with their scheduler.

## Capacity and investment relevance

The value proposition is improved use of generation, storage, and cooling
capacity already on site rather than a rip-and-replace hardware requirement.
GridSignal occupies the gap between long-range forecasting based on weather or
tariffs and millisecond real-time protection response. It provides earlier,
shared visibility and advice while the trusted site systems retain all
physical decision-making authority.