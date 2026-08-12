/**
 * gpuGeneratorStore.ts — GPU Node Generator state + async job engine.
 *
 * Data flow
 * ─────────
 * 1. Operator configures GeneratorConfig (rate, burst, tenant mix, job sizes).
 * 2. start() arms a module-level interval that calls _tick() every 2 s.
 * 3. _tick() decides whether to emit a job batch based on rate/burst config.
 * 4. Each emitted job is a realistic SlurmJob | KubernetesJob | RayJob with
 *    GPU node count, TDP estimate, and scheduler-specific metadata.
 * 5. Jobs lifecycle: PENDING → RUNNING (after ~1 s) → COMPLETING/Succeeded
 *    (after jobDurationRange seconds) → removed from list.
 * 6. ComputeRacksModal reads tenantA/B/C arrays for its drill-down panels.
 */

import { create } from 'zustand'

// ── Config schema ─────────────────────────────────────────────────────────────

export interface GeneratorConfig {
  ratePerMinute: number                       // 0.5 – 20 jobs/min total
  burstMode: boolean
  burstSize: [number, number]                 // [min, max] jobs per burst
  burstIntervalSeconds: [number, number]      // [min, max] s between bursts
  tenantWeights: { a: number; b: number; c: number }  // must sum to 1
  jobSizes: { small: number; medium: number; large: number }  // must sum to 1
  maxJobsPerTenant: number                    // hard cap on live job count per tenant
  jobDurationRange: [number, number]          // [min, max] seconds running
  /** Contracted power ceiling per tenant (MW). Matches colo contract signed values.
   *  The generator will not add a job that would push a tenant over this limit. */
  tenantContracts: { a: number; b: number; c: number }
}

export const DEFAULT_CONFIG: GeneratorConfig = {
  ratePerMinute:        2,
  burstMode:            false,
  burstSize:            [3, 8],
  burstIntervalSeconds: [30, 90],
  tenantWeights:        { a: 0.40, b: 0.35, c: 0.25 },
  jobSizes:             { small: 0.30, medium: 0.50, large: 0.20 },
  maxJobsPerTenant:     12,
  jobDurationRange:     [60, 240],
  // Mirror the contractedMW values in ComputeRacksModal's SHOWN_TENANTS catalogue.
  tenantContracts:      { a: 1.40, b: 1.00, c: 0.60 },
}

// ── Job types ─────────────────────────────────────────────────────────────────

export interface SlurmJob {
  // ── GridSignal internal ────────────────────────────────────────────────────
  type:        'slurm'
  id:          string               // display ID ("JOB-A-0001")
  tdpMW:       number
  priority:    'high' | 'medium' | 'low'
  status:      'PENDING' | 'RUNNING' | 'COMPLETING'
  submittedAt: number               // Date.now() ms
  startsAt:    number
  completesAt: number
  gpusPerNode: number
  totalGPUs:   number
  walltime:    string               // HH:MM:SS display label
  /** slurmrestd JSON snapshot — conforms to GET /slurm/v0.0.40/jobs/{job_id} */
  manifest:    string
  // ── slurmrestd fields (GET /slurm/v0.0.40/jobs) ───────────────────────────
  slurm_job_id:   number            // raw Slurm integer job ID
  name:           string
  user_name:      string
  job_state:      string[]          // ["PENDING"] | ["RUNNING"] | ["COMPLETING"]
  partition:      string
  nodes:          string            // node-range e.g. "gpu-node[014-029]"
  node_count:     number
  cpus:           number
  tres_req_str:   string            // "cpu=N,mem=XG,gres/gpu=Y"
  tres_alloc_str: string            // + ",gres/gpu:h100=Y"
  start_time:     number            // unix epoch seconds
  submit_time:    number
  time_limit:     { set: boolean; number: number }  // minutes
  features:       string            // "h100,nvlink4"
  account:        string
  qos:            string
}

export interface KubernetesJob {
  type:          'kubernetes'
  id:            string
  name:          string
  namespace:     string
  image:         string
  replicas:      number
  gpuPerReplica: number
  totalGPUs:     number
  tdpMW:         number
  priority:      'high' | 'medium' | 'low'
  status:        'Pending' | 'Running' | 'Succeeded'
  submittedAt:   number
  startsAt:      number
  completesAt:   number
  manifest:      string   // YAML snippet
}

export interface RayJob {
  // ── GridSignal internal ────────────────────────────────────────────────────
  type:        'ray'
  id:          string            // display ID ("JOB-C-0001")
  entrypoint:  string
  numGPUs:     number
  numWorkers:  number
  totalGPUs:   number
  tdpMW:       number
  rayJobId:    string            // kept for UI display compat
  priority:    'high' | 'medium' | 'low'
  status:      'PENDING' | 'RUNNING' | 'SUCCEEDED'
  submittedAt: number
  startsAt:    number
  completesAt: number
  /** WorkloadSignal event JSON — conforms to spec §10 / ray_workloadsignal_emitter contract */
  manifest:    string
  // ── WorkloadSignal fields (spec §10) ──────────────────────────────────────
  submission_id:       string    // "raysubmit_XXXX" or "serve_deployment_NAME"
  event_id:            string    // ULID: "evt_01J8X7QK3M5N6P8R9T2V4W6Y8Z"
  event_type:          string    // queued|starting|running|scale|checkpoint_start|checkpoint_end|job_end|cancelled
  timestamp:           string    // ISO-8601 UTC (source-clock, per §11.4)
  hardware_profile_id: string    // "nvidia-h100-sxm5-8way"
  node_count:          number    // active nodes at event time
  workload_class:      'training' | 'inference' | 'other'
  site_id:             string
  queue_depth?:        number    // inference only (§6 row 2)
  request_rate?:       number    // inference only — requests/sec
}

export type AnyJob = SlurmJob | KubernetesJob | RayJob

export interface FeedEntry {
  id:      string
  ts:      number
  tenant:  'A' | 'B' | 'C'
  action:  'SUBMITTED' | 'RUNNING' | 'COMPLETED'
  jobId:   string
  jobName: string
  gpus:    number
  tdpMW:   number
}

// ── Name + image catalogues ────────────────────────────────────────────────────

const SLURM_NAMES = [
  'llm-finetune-7B', 'llm-finetune-13B', 'llm-finetune-70B',
  'embedding-batch-512', 'embedding-batch-2048',
  'rlhf-training-v2', 'rlhf-training-v3',
  'eval-harness-run', 'eval-harness-large',
  'data-preproc-gpu', 'data-preproc-v3',
  'vllm-inference-prod', 'model-export-job',
  'speculative-decode-bench', 'dpo-training-run',
]

const SLURM_PARTITIONS = ['gpu-high', 'gpu-medium', 'gpu-preempt', 'gpu-long']

const SLURM_ACCOUNTS  = ['ml-research', 'ml-compute', 'inference-prod', 'data-platform', 'safety-research']
const SLURM_USERS     = ['mlops', 'researcher', 'batch-runner', 'inference-eng', 'training-eng', 'data-eng']
const SLURM_QOS: Record<'high' | 'medium' | 'low', string> = {
  high:   'high-priority',
  medium: 'normal',
  low:    'preemptible',
}

const K8S_NAMES = [
  'inference-serving-prod', 'inference-serving-canary',
  'batch-transcription', 'video-analysis-worker',
  'embedding-api', 'text-classification',
  'ner-pipeline', 'sd-image-gen',
  'speech-to-text', 'model-serving-v2',
  'triton-inference', 'vllm-k8s-prod',
]

const K8S_IMAGES = [
  'nvcr.io/nvidia/pytorch:24.02-py3',
  'nvcr.io/nvidia/tritonserver:24.01-py3',
  'nvcr.io/nvidia/tensorflow:24.01-tf2-py3',
  'ghcr.io/huggingface/text-generation-inference:2.0',
  'vllm/vllm-openai:latest',
]

const K8S_NAMESPACES = ['ml-workloads', 'inference', 'training', 'batch-jobs']

// Split by workload_class so submission_id and job_id formats follow the spec
const RAY_TRAIN_NAMES = [
  'distributed-train-v2', 'distributed-train-v3',
  'hyperopt-sweep-64', 'hyperopt-sweep-128',
  'rl-policy-ppo', 'rl-policy-sac',
  'model-parallel-train', 'tune-experiment', 'rllib-training',
]
const RAY_SERVE_NAMES = [
  'llama3-70b-endpoint', 'codellama-34b-endpoint',
  'whisper-large-v3-endpoint', 'clip-vit-large-endpoint',
  'mixtral-8x7b-endpoint', 'llava-13b-endpoint',
]
const RAY_OTHER_NAMES = [
  'data-pipeline-gpu', 'feature-engineering-gpu', 'batch-inference-ray',
]
const RAY_SITES = [
  'site-us-east-04', 'site-us-west-02', 'site-eu-west-01', 'site-ap-northeast-01',
]

// Crockford base32 ULID — 26 chars, 10 timestamp + 16 random (spec §17.1 idempotency key)
const _B32 = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
function makeULID(): string {
  let t = Date.now(), ts = ''
  for (let i = 9; i >= 0; i--) { ts = _B32[t % 32] + ts; t = Math.floor(t / 32) }
  let r = ''
  for (let i = 0; i < 16; i++) r += _B32[Math.floor(Math.random() * 32)]
  return ts + r
}

const GPU_TDP_MW = 0.0007  // H100 SXM5 ~700 W

// ── RNG helpers ───────────────────────────────────────────────────────────────

function rInt(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min
}

function rPick<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)]
}
function rWeighted<T extends string>(weights: Record<T, number>): T {
  const entries = Object.entries(weights) as [T, number][]
  const total = entries.reduce((s, [, w]) => s + w, 0)
  let r = Math.random() * total
  for (const [key, w] of entries) {
    r -= w
    if (r <= 0) return key
  }
  return entries[0][0]
}

let _counter = 1
function nextId(prefix: string): string {
  return `${prefix}-${String(_counter++).padStart(4, '0')}`
}

// ── GPU count by job size ─────────────────────────────────────────────────────

function gpuCountForSize(size: 'small' | 'medium' | 'large'): number {
  switch (size) {
    case 'small':  return rPick([8, 16, 32, 64])
    case 'medium': return rPick([128, 256, 512])
    case 'large':  return rPick([512, 768, 1024, 2048])
  }
}

function priorityForSize(size: 'small' | 'medium' | 'large'): 'high' | 'medium' | 'low' {
  if (size === 'large')  return Math.random() < 0.7 ? 'high'   : 'medium'
  if (size === 'medium') return Math.random() < 0.5 ? 'medium' : 'high'
  return Math.random() < 0.5 ? 'low' : 'medium'
}

function walltimeForSize(size: 'small' | 'medium' | 'large'): string {
  const h = size === 'large' ? rInt(4, 24) : size === 'medium' ? rInt(1, 8) : rInt(0, 2)
  const m = rInt(0, 59)
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:00`
}

/** Convert "HH:MM:SS" walltime to whole minutes (Slurm time_limit.number). */
function walltimeToMinutes(wt: string): number {
  const [h, m] = wt.split(':').map(Number)
  return h * 60 + m
}

/** Build a Slurm node-range string e.g. "gpu-node[014-029]" for `count` nodes. */
function nodeRangeStr(count: number): string {
  const base = rInt(0, 230)
  const end  = base + count - 1
  if (count === 1) return `gpu-node-${String(base).padStart(3, '0')}`
  return `gpu-node[${String(base).padStart(3, '0')}-${String(end).padStart(3, '0')}]`
}

// ── Job factories ─────────────────────────────────────────────────────────────

function makeSlurmJob(cfg: GeneratorConfig, now: number): SlurmJob {
  const size        = rWeighted(cfg.jobSizes)
  const totalGPUs   = gpuCountForSize(size)
  const gpusPerNode = rPick([4, 8])
  const node_count  = Math.max(1, Math.ceil(totalGPUs / gpusPerNode))
  const id          = nextId('JOB-A')
  const name        = rPick(SLURM_NAMES)
  const partition   = rPick(SLURM_PARTITIONS)
  const priority    = priorityForSize(size)
  const walltime    = walltimeForSize(size)
  const tdpMW       = totalGPUs * GPU_TDP_MW
  const dur         = rInt(cfg.jobDurationRange[0], cfg.jobDurationRange[1]) * 1000
  const account     = rPick(SLURM_ACCOUNTS)
  const user_name   = rPick(SLURM_USERS)
  const qos         = SLURM_QOS[priority]

  // slurmrestd resource strings
  const cpus           = totalGPUs * 12                        // 12 vCPU per H100
  const memGB          = totalGPUs * 120                       // 120 GiB per H100
  const tres_req_str   = `cpu=${cpus},mem=${memGB}G,gres/gpu=${totalGPUs}`
  const tres_alloc_str = `${tres_req_str},gres/gpu:h100=${totalGPUs}`
  const nodes          = nodeRangeStr(node_count)
  const slurm_job_id   = rInt(4_000_000, 9_999_999)
  const submit_time    = Math.floor(now / 1000)
  const start_time     = Math.floor((now + 1_200_000) / 1000)  // +20 min queue wait

  // slurmrestd-conformant JSON snapshot (GET /slurm/v0.0.40/jobs/{job_id})
  const slurmObj = {
    job_id:         slurm_job_id,
    name,
    user_name,
    job_state:      ['PENDING'],
    partition,
    nodes,
    node_count,
    cpus,
    tres_req_str,
    tres_alloc_str,
    submit_time,
    start_time,
    time_limit:     { set: true, number: walltimeToMinutes(walltime) },
    features:       'h100,nvlink4',
    account,
    qos,
  }
  const manifest = JSON.stringify(slurmObj, null, 2)

  return {
    type: 'slurm', id, tdpMW, priority, status: 'PENDING',
    submittedAt: now, startsAt: now + 1_200_000, completesAt: now + dur,
    gpusPerNode, totalGPUs, walltime, manifest,
    // slurmrestd fields
    slurm_job_id, name, user_name, job_state: ['PENDING'],
    partition, nodes, node_count, cpus,
    tres_req_str, tres_alloc_str,
    submit_time, start_time,
    time_limit: { set: true, number: walltimeToMinutes(walltime) },
    features: 'h100,nvlink4', account, qos,
  }
}

function makeKubernetesJob(cfg: GeneratorConfig, now: number): KubernetesJob {
  const size         = rWeighted(cfg.jobSizes)
  const totalGPUs    = gpuCountForSize(size)
  const gpuPerReplica = rPick([1, 2, 4, 8])
  const replicas     = Math.max(1, Math.ceil(totalGPUs / gpuPerReplica))
  const id           = nextId('JOB-B')
  const name         = rPick(K8S_NAMES)
  const namespace    = rPick(K8S_NAMESPACES)
  const image        = rPick(K8S_IMAGES)
  const priority     = priorityForSize(size)
  const tdpMW        = totalGPUs * GPU_TDP_MW
  const dur          = rInt(cfg.jobDurationRange[0], cfg.jobDurationRange[1]) * 1000
  const cpuReq  = gpuPerReplica * 12          // 12 vCPU per H100 (192-core node ÷ 8 GPUs × ratio)
  const cpuLim  = gpuPerReplica * 24          // 2× headroom for burst
  const memReq  = gpuPerReplica * 120         // 120 GiB per GPU (matches H100 SXM5 HBM headroom)
  const memLim  = Math.round(memReq * 1.25)   // +25% for framework overhead
  const prioClass = priority === 'high' ? 'gpu-high-priority'
                  : priority === 'medium' ? 'gpu-standard-priority'
                  : 'gpu-preemptible'
  const manifest     = [
    `apiVersion: batch/v1`,
    `kind: Job`,
    `metadata:`,
    `  name: ${name}`,
    `  namespace: ${namespace}`,
    `  labels:`,
    `    app: ${name}`,
    `    scheduler: kubernetes`,
    `    nvidia.com/gpu-job: "true"`,
    `spec:`,
    `  parallelism: ${replicas}`,
    `  completions: ${replicas}`,
    `  backoffLimit: 0`,
    `  template:`,
    `    metadata:`,
    `      labels:`,
    `        app: ${name}`,
    `    spec:`,
    `      priorityClassName: ${prioClass}`,
    `      restartPolicy: Never`,
    `      containers:`,
    `      - name: worker`,
    `        image: ${image}`,
    `        resources:`,
    `          requests:`,
    `            cpu: "${cpuReq}"`,
    `            memory: "${memReq}Gi"`,
    `            nvidia.com/gpu: "${gpuPerReplica}"`,
    `          limits:`,
    `            cpu: "${cpuLim}"`,
    `            memory: "${memLim}Gi"`,
    `            nvidia.com/gpu: "${gpuPerReplica}"`,
    `      nodeSelector:`,
    `        nvidia.com/gpu.product: H100-SXM5-80GB`,
    `      tolerations:`,
    `      - key: "nvidia.com/gpu"`,
    `        operator: "Exists"`,
    `        effect: "NoSchedule"`,
  ].join('\n')
  return {
    type: 'kubernetes', id, name, namespace, image, replicas, gpuPerReplica,
    totalGPUs, tdpMW, priority, status: 'Pending', manifest,
    submittedAt: now, startsAt: now + 1500, completesAt: now + dur,
  }
}

function makeRayJob(cfg: GeneratorConfig, now: number): RayJob {
  const size       = rWeighted(cfg.jobSizes)
  const totalGPUs  = gpuCountForSize(size)
  const numWorkers = Math.max(1, Math.floor(totalGPUs / 8))
  const gpusEach   = Math.ceil(totalGPUs / numWorkers)
  const id         = nextId('JOB-C')
  const priority   = priorityForSize(size)
  const tdpMW      = totalGPUs * GPU_TDP_MW
  const dur        = rInt(cfg.jobDurationRange[0], cfg.jobDurationRange[1]) * 1000
  const site_id    = rPick(RAY_SITES)
  const hardware_profile_id = 'nvidia-h100-sxm5-8way'  // H100 → ACCELERATOR_TO_PROFILE map

  // Workload class selection: 65% training, 20% inference (Serve), 15% other
  const roll = Math.random()
  let name: string
  let workload_class: 'training' | 'inference' | 'other'
  let submission_id: string
  let entrypoint: string
  let queue_depth: number | undefined
  let request_rate: number | undefined

  if (roll < 0.65) {
    name           = rPick(RAY_TRAIN_NAMES)
    workload_class = 'training'
    submission_id  = `raysubmit_${makeULID().slice(10)}`   // 16-char random suffix
    entrypoint     = `python ${name.replace(/-/g, '_')}.py --num-gpus ${gpusEach} --num-workers ${numWorkers}`
  } else if (roll < 0.85) {
    name           = rPick(RAY_SERVE_NAMES)
    workload_class = 'inference'
    submission_id  = `serve_deployment_${name}`
    entrypoint     = `serve run ${name}:deployment --num-replicas ${numWorkers}`
    queue_depth    = rInt(5, 500)
    request_rate   = Math.round(Math.random() * 200 * 10) / 10
  } else {
    name           = rPick(RAY_OTHER_NAMES)
    workload_class = 'other'
    submission_id  = `raysubmit_${makeULID().slice(10)}`
    entrypoint     = `python ${name.replace(/-/g, '_')}.py`
  }

  // Initial event: PENDING → "queued" (per spec mapping table)
  const event_id  = `evt_${makeULID()}`
  const timestamp = new Date(now).toISOString()
  const node_count = numWorkers

  const wsEvent: Record<string, unknown> = {
    job_id:  submission_id, event_id, event_type: 'queued',
    timestamp, hardware_profile_id, node_count, workload_class, site_id,
  }
  if (workload_class === 'inference') {
    wsEvent.queue_depth  = queue_depth
    wsEvent.request_rate = request_rate
  }

  return {
    type: 'ray', id, entrypoint, numGPUs: gpusEach, numWorkers, totalGPUs,
    tdpMW, rayJobId: submission_id, priority, status: 'PENDING',
    manifest: JSON.stringify(wsEvent, null, 2),
    submittedAt: now, startsAt: now + 800, completesAt: now + dur,
    // WorkloadSignal fields
    submission_id, event_id, event_type: 'queued', timestamp,
    hardware_profile_id, node_count, workload_class, site_id,
    queue_depth, request_rate,
  }
}

// ── Tick logic ────────────────────────────────────────────────────────────────

let _lastEmitAt   = 0
let _nextBurstAt  = 0
let _intervalId: ReturnType<typeof setInterval> | null = null

function _shouldEmitSteady(cfg: GeneratorConfig, now: number): boolean {
  const intervalMs = (60 / cfg.ratePerMinute) * 1000
  return now - _lastEmitAt >= intervalMs
}

function _shouldEmitBurst(cfg: GeneratorConfig, now: number): boolean {
  if (_nextBurstAt === 0) {
    _nextBurstAt = now + rInt(cfg.burstIntervalSeconds[0], cfg.burstIntervalSeconds[1]) * 1000
  }
  return now >= _nextBurstAt
}

// ── Store ─────────────────────────────────────────────────────────────────────

interface GpuGeneratorState {
  config:  GeneratorConfig
  running: boolean
  tenantA: SlurmJob[]
  tenantB: KubernetesJob[]
  tenantC: RayJob[]
  feed:    FeedEntry[]

  start:        () => void
  stop:         () => void
  reset:        () => void
  updateConfig: (patch: Partial<GeneratorConfig>) => void
  _tick:        () => void
}

export const useGpuGeneratorStore = create<GpuGeneratorState>((set, get) => ({
  config:  DEFAULT_CONFIG,
  running: false,
  tenantA: [],
  tenantB: [],
  tenantC: [],
  feed:    [],

  start() {
    if (get().running) return
    _lastEmitAt  = 0
    _nextBurstAt = 0
    set({ running: true })
    _intervalId = setInterval(() => get()._tick(), 2000)
  },

  stop() {
    if (_intervalId) { clearInterval(_intervalId); _intervalId = null }
    set({ running: false })
  },

  reset() {
    get().stop()
    _counter     = 1
    _lastEmitAt  = 0
    _nextBurstAt = 0
    set({ tenantA: [], tenantB: [], tenantC: [], feed: [], running: false })
  },

  updateConfig(patch) {
    set(s => ({ config: { ...s.config, ...patch } }))
  },

  _tick() {
    const { config, tenantA, tenantB, tenantC, feed } = get()
    const now = Date.now()

    // ── Advance job lifecycle ─────────────────────────────────────────────
    function advanceSlurm(jobs: SlurmJob[]): SlurmJob[] {
      return jobs
        .map(j => {
          if (j.status === 'PENDING'  && now >= j.startsAt)
            return { ...j, status: 'RUNNING'    as const, job_state: ['RUNNING'],    start_time: Math.floor(now / 1000) }
          if (j.status === 'RUNNING'  && now >= j.completesAt)
            return { ...j, status: 'COMPLETING' as const, job_state: ['COMPLETING'] }
          return j
        })
        .filter(j => !(j.status === 'COMPLETING' && now >= j.completesAt + 3000))
    }
    function advanceK8s(jobs: KubernetesJob[]): KubernetesJob[] {
      return jobs
        .map(j => {
          if (j.status === 'Pending' && now >= j.startsAt)    return { ...j, status: 'Running'   as const }
          if (j.status === 'Running' && now >= j.completesAt) return { ...j, status: 'Succeeded' as const }
          return j
        })
        .filter(j => !(j.status === 'Succeeded' && now >= j.completesAt + 3000))
    }
    function advanceRay(jobs: RayJob[]): RayJob[] {
      return jobs
        .map(j => {
          if (j.status === 'PENDING' && now >= j.startsAt) {
            // PENDING → RUNNING: first observation → event_type "starting" (spec mapping table)
            const event_id  = `evt_${makeULID()}`
            const timestamp = new Date(now).toISOString()
            const wsEvent: Record<string, unknown> = {
              job_id: j.submission_id, event_id, event_type: 'starting',
              timestamp, hardware_profile_id: j.hardware_profile_id,
              node_count: j.node_count, workload_class: j.workload_class, site_id: j.site_id,
            }
            if (j.workload_class === 'inference') {
              wsEvent.queue_depth = j.queue_depth; wsEvent.request_rate = j.request_rate
            }
            return { ...j, status: 'RUNNING' as const, event_type: 'starting', event_id, timestamp, manifest: JSON.stringify(wsEvent, null, 2) }
          }
          if (j.status === 'RUNNING' && now >= j.completesAt) {
            // RUNNING → SUCCEEDED: event_type "job_end"
            const event_id  = `evt_${makeULID()}`
            const timestamp = new Date(now).toISOString()
            const wsEvent   = {
              job_id: j.submission_id, event_id, event_type: 'job_end',
              timestamp, hardware_profile_id: j.hardware_profile_id,
              node_count: j.node_count, workload_class: j.workload_class, site_id: j.site_id,
            }
            return { ...j, status: 'SUCCEEDED' as const, event_type: 'job_end', event_id, timestamp, manifest: JSON.stringify(wsEvent, null, 2) }
          }
          return j
        })
        .filter(j => !(j.status === 'SUCCEEDED' && now >= j.completesAt + 3000))
    }

    const nextA = advanceSlurm(tenantA)
    const nextB = advanceK8s(tenantB)
    const nextC = advanceRay(tenantC)
    const feedUpdates: FeedEntry[] = []

    // ── Emit new jobs ─────────────────────────────────────────────────────
    let newJobs = 0
    const shouldEmit = config.burstMode
      ? _shouldEmitBurst(config, now)
      : _shouldEmitSteady(config, now)

    if (shouldEmit) {
      _lastEmitAt = now
      if (config.burstMode) {
        _nextBurstAt = now + rInt(config.burstIntervalSeconds[0], config.burstIntervalSeconds[1]) * 1000
        newJobs = rInt(config.burstSize[0], config.burstSize[1])
      } else {
        newJobs = 1
      }
    }

    // Live MW draw per tenant (sum of active/pending job TDP)
    const liveMW = {
      a: nextA.filter(j => j.status !== 'COMPLETING').reduce((s, j) => s + j.tdpMW, 0),
      b: nextB.filter(j => j.status !== 'Succeeded').reduce((s, j) => s + j.tdpMW, 0),
      c: nextC.filter(j => j.status !== 'SUCCEEDED').reduce((s, j) => s + j.tdpMW, 0),
    }

    for (let i = 0; i < newJobs; i++) {
      const tenant = rWeighted(config.tenantWeights)
      if (tenant === 'a' && nextA.length < config.maxJobsPerTenant) {
        const j = makeSlurmJob(config, now)
        // Respect contracted ceiling — skip if this job would exceed it
        if (liveMW.a + j.tdpMW > config.tenantContracts.a) continue
        nextA.push(j)
        liveMW.a += j.tdpMW
        feedUpdates.push({ id: `fe-${now}-${i}`, ts: now, tenant: 'A', action: 'SUBMITTED', jobId: j.id, jobName: j.name, gpus: j.totalGPUs, tdpMW: j.tdpMW })
      } else if (tenant === 'b' && nextB.length < config.maxJobsPerTenant) {
        const j = makeKubernetesJob(config, now)
        if (liveMW.b + j.tdpMW > config.tenantContracts.b) continue
        nextB.push(j)
        liveMW.b += j.tdpMW
        feedUpdates.push({ id: `fe-${now}-${i}`, ts: now, tenant: 'B', action: 'SUBMITTED', jobId: j.id, jobName: j.name, gpus: j.totalGPUs, tdpMW: j.tdpMW })
      } else if (tenant === 'c' && nextC.length < config.maxJobsPerTenant) {
        const j = makeRayJob(config, now)
        if (liveMW.c + j.tdpMW > config.tenantContracts.c) continue
        nextC.push(j)
        liveMW.c += j.tdpMW
        feedUpdates.push({ id: `fe-${now}-${i}`, ts: now, tenant: 'C', action: 'SUBMITTED', jobId: j.id, jobName: j.entrypoint.split(' ')[1] ?? 'ray-job', gpus: j.totalGPUs, tdpMW: j.tdpMW })
      }
    }

    const nextFeed = [...feedUpdates, ...feed].slice(0, 80)
    set({ tenantA: nextA, tenantB: nextB, tenantC: nextC, feed: nextFeed })
  },
}))
