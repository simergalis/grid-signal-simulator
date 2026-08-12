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
  type:        'slurm'
  id:          string
  name:        string
  partition:   string
  nodes:       number
  gpusPerNode: number
  totalGPUs:   number
  tdpMW:       number
  walltime:    string
  priority:    'high' | 'medium' | 'low'
  status:      'PENDING' | 'RUNNING' | 'COMPLETING'
  submittedAt: number   // Date.now()
  startsAt:    number
  completesAt: number
  manifest:    string   // #SBATCH script snippet
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
  type:        'ray'
  id:          string
  entrypoint:  string
  numGPUs:     number
  numWorkers:  number
  totalGPUs:   number
  tdpMW:       number
  rayJobId:    string
  priority:    'high' | 'medium' | 'low'
  status:      'PENDING' | 'RUNNING' | 'SUCCEEDED'
  submittedAt: number
  startsAt:    number
  completesAt: number
  manifest:    string   // Ray submission snippet
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

const RAY_NAMES = [
  'distributed-train-v2', 'distributed-train-v3',
  'hyperopt-sweep-64', 'hyperopt-sweep-128',
  'rl-policy-ppo', 'rl-policy-sac',
  'data-pipeline-gpu', 'feature-engineering-gpu',
  'model-parallel-train', 'batch-inference-ray',
  'tune-experiment', 'rllib-training',
]

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

// ── Job factories ─────────────────────────────────────────────────────────────

function makeSlurmJob(cfg: GeneratorConfig, now: number): SlurmJob {
  const size      = rWeighted(cfg.jobSizes)
  const totalGPUs = gpuCountForSize(size)
  const gpusPerNode = rPick([4, 8])
  const nodes     = Math.max(1, Math.ceil(totalGPUs / gpusPerNode))
  const id        = nextId('JOB-A')
  const name      = rPick(SLURM_NAMES)
  const partition = rPick(SLURM_PARTITIONS)
  const priority  = priorityForSize(size)
  const walltime  = walltimeForSize(size)
  const tdpMW     = totalGPUs * GPU_TDP_MW
  const dur       = rInt(cfg.jobDurationRange[0], cfg.jobDurationRange[1]) * 1000
  const manifest  = [
    `#!/bin/bash`,
    `#SBATCH --job-name=${name}`,
    `#SBATCH --partition=${partition}`,
    `#SBATCH --nodes=${nodes}`,
    `#SBATCH --ntasks-per-node=1`,
    `#SBATCH --gres=gpu:h100:${gpusPerNode}`,
    `#SBATCH --time=${walltime}`,
    `#SBATCH --mem-per-gpu=120G`,
    `#SBATCH --cpus-per-gpu=12`,
    `#SBATCH --output=logs/%x_%j_%N.out`,
    `#SBATCH --error=logs/%x_%j_%N.err`,
    `#SBATCH --account=ml-compute`,
    `#SBATCH --exclusive`,
    ``,
    `module purge`,
    `module load cuda/12.3 nccl/2.19 pytorch/2.2`,
    ``,
    `export NCCL_DEBUG=INFO`,
    `export NCCL_IB_DISABLE=0`,
    `export MASTER_ADDR=$(scontrol show hostnames "$SLURM_JOB_NODELIST" | head -n1)`,
    `export MASTER_PORT=29500`,
    ``,
    `srun --kill-on-bad-exit=1 \\`,
    `  python ${name.replace(/-/g, '_')}.py \\`,
    `    --nodes ${nodes} \\`,
    `    --gpus-per-node ${gpusPerNode}`,
  ].join('\n')
  return {
    type: 'slurm', id, name, partition, nodes, gpusPerNode, totalGPUs,
    tdpMW, walltime, priority, status: 'PENDING', manifest,
    submittedAt: now, startsAt: now + 1200, completesAt: now + dur,
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
  const name       = rPick(RAY_NAMES)
  const id         = nextId('JOB-C')
  const rayJobId   = `raysubmit_${Math.random().toString(36).slice(2, 10).toUpperCase()}`
  const priority   = priorityForSize(size)
  const tdpMW      = totalGPUs * GPU_TDP_MW
  const dur        = rInt(cfg.jobDurationRange[0], cfg.jobDurationRange[1]) * 1000
  const entrypoint = `python ${name.replace(/-/g, '_')}.py --num-gpus ${gpusEach} --num-workers ${numWorkers}`
  const cpuEach  = gpusEach * 12
  const memBytes = gpusEach * 120 * 1024 ** 3   // bytes — Ray memory arg
  const manifest   = [
    `import ray`,
    `from ray.runtime_env import RuntimeEnv`,
    ``,
    `ray.init(`,
    `    address="ray://ray-head.ray-system:10001",`,
    `    runtime_env=RuntimeEnv(`,
    `        pip=["torch==2.2.0", "transformers==4.40.0"],`,
    `        env_vars={"NCCL_DEBUG": "INFO", "NCCL_IB_DISABLE": "0"},`,
    `    ),`,
    `)`,
    ``,
    `@ray.remote(`,
    `    num_gpus=${gpusEach},`,
    `    num_cpus=${cpuEach},`,
    `    memory=${memBytes},`,
    `    accelerator_type="H100",`,
    `)`,
    `class GPUWorker:`,
    `    def train(self): ...`,
    ``,
    `# ${numWorkers} workers × ${gpusEach} GPUs = ${totalGPUs} total GPUs`,
    `workers = [GPUWorker.remote() for _ in range(${numWorkers})]`,
    `ray.get([w.train.remote() for w in workers])`,
  ].join('\n')
  return {
    type: 'ray', id, entrypoint, numGPUs: gpusEach, numWorkers, totalGPUs,
    tdpMW, rayJobId, priority, status: 'PENDING', manifest,
    submittedAt: now, startsAt: now + 800, completesAt: now + dur,
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
          if (j.status === 'PENDING'     && now >= j.startsAt)    return { ...j, status: 'RUNNING'     as const }
          if (j.status === 'RUNNING'     && now >= j.completesAt) return { ...j, status: 'COMPLETING'  as const }
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
          if (j.status === 'PENDING'  && now >= j.startsAt)    return { ...j, status: 'RUNNING'   as const }
          if (j.status === 'RUNNING'  && now >= j.completesAt) return { ...j, status: 'SUCCEEDED' as const }
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
