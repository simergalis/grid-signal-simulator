"""
tests/test_checkpoint_classifier.py — Cross-signal agreement between the
stochastic step scheduler and the CheckpointClassifier.

Task #177: When the step scheduler fires a checkpoint long-step
(step_kind="checkpoint"), the within-step power profile produces a sustained
allreduce phase that the CheckpointClassifier must detect as IN_VALLEY or
CHECKPOINT.

This guards against a latent disagreement where the dashboard labels a real
checkpoint as a straggler (NORMAL/UNCERTAIN) or misses it entirely.

Sections
--------
TC-01 : causal check — allreduce onset WITHIN checkpoint long-step triggers
        classifier IN_VALLEY or CHECKPOINT on the same or next tick
TC-01b : wiring check — checkpoint_states is non-empty on the first tick
         where step_kind="checkpoint" appears

Design constraints
------------------
* Full evaluate_tick() loop — exercises the complete wiring:
    KubeDemandAgent.tick() → step_phase propagation → GPUModule.advance() →
    per_job_compute_mw() → CheckpointClassifier.record_and_classify() →
    TickResult.checkpoint_states / step_kind.
* No asyncio, no HTTP — test is self-contained and runs in any Python shell.
* Uses _plane_guard_active() exactly like other direct-evaluate_tick() tests.

Causal-evidence design (TC-01)
-------------------------------
Normal training steps (~0.7 s at 10 Hz) also produce brief allreduce dips
that the heuristic classifier fires on and recovers from.  To distinguish a
checkpoint long-step from a normal training cycle the test uses a three-phase
state machine:

  PHASE 1 — SEEK_CKPT_ENTRY:
    Wait for the first tick where step_kind="checkpoint" AND step_phase < 0.1.
    step_phase ≈ 0 means the step boundary just fired; this is the compute
    phase entry of the checkpoint long-step.

  PHASE 2 — SEEK_ALLREDUCE_IN_CKPT:
    Continue while step_kind remains "checkpoint".  Wait for step_phase to
    cross f_compute (0.72) — the moment the allreduce phase starts WITHIN the
    checkpoint long-step.

  PHASE 3 — ASSERT:
    On the first tick where step_phase >= f_compute AND step_kind="checkpoint",
    assert that checkpoint_states shows IN_VALLEY or CHECKPOINT for the active
    kube job.

This is causally tight:
  - PHASE 1 ensures we are at the START of a checkpoint step (compute phase).
  - PHASE 2 ensures we are still INSIDE the same checkpoint step.
  - PHASE 3 checks the classifier on the tick when the allreduce power drop
    first occurs during that checkpoint — not from any prior training cycle.

Run from gridsignal_sim/:
    PYTHONPATH=. python -m pytest tests/test_checkpoint_classifier.py -v
"""

from __future__ import annotations

import contextlib

from core.dispatch import CheckpointClassifier
from core.kube_demand import KubeConfig, KubeDemandAgent
from core.sim_clock import SimClock
from core.step_config import LoadProfileConfig, StepTimingConfig


# ---------------------------------------------------------------------------
# Plane-guard helper (mirrors test_plane_separation.py / test_f5_sim_time_interval_end.py)
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _plane_guard_active():
    """Set _EVALUATE_TICK_PERMITTED for the duration of a with-block.

    Required before every direct evaluate_tick() call outside the RunContext
    harness — identical to what RunContext.step() does in production.
    """
    from core._plane_guard import _EVALUATE_TICK_PERMITTED
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        yield
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


def _make_clock(sim_time: float, dt: float, tick_seq: int = 0) -> SimClock:
    return SimClock(
        sim_time=sim_time,
        dt_seconds=dt,
        wall_stamp_utc=None,
        rate=1.0,
        tick_seq=tick_seq,
    )


# ---------------------------------------------------------------------------
# Simulation state factory
# ---------------------------------------------------------------------------

# f_compute from LoadProfileConfig: fraction of step spent in compute phase.
# Allreduce starts at step_phase >= F_COMPUTE.
F_COMPUTE = 0.72


def _make_state_with_kube(
    *,
    rng_seed: int,
    ckpt_interval_steps: int,
    ckpt_jitter_steps: int = 0,
    node_count: int = 500,
):
    """Build a SimulationState with an attached KubeDemandAgent that has a
    step scheduler (step_config) and a load profile (load_config on GPUModule).

    Parameters
    ----------
    rng_seed            : seed for the KubeDemandAgent / StepScheduler.
    ckpt_interval_steps : how many normal steps between checkpoints.  Use a
                          small value (e.g. 5) so checkpoints appear quickly.
    ckpt_jitter_steps   : ±jitter on the interval; 0 → deterministic interval.
    node_count          : admitted GPU node count for the kube cluster baseline.
    """
    from runtime.scenario_factory import build_run_context

    ctx = build_run_context(
        "ckpt-classifier-test",
        job_id="placeholder",
        node_count=0,          # no scripted workload; kube agent drives load
        turbine_rated_mw=20.0,
        bess_rated_mw=5.0,
        bess_usable_mwh=3.0,
        bess_grid_forming=False,
        end_sim_time=3600.0,
    )
    state = ctx.sim_state

    # ── Step timing: fire a checkpoint every `ckpt_interval_steps` steps ─────
    step_cfg = StepTimingConfig(
        ckpt_interval_steps=ckpt_interval_steps,
        ckpt_jitter_steps=ckpt_jitter_steps,
        # Keep default median_step_s=0.7 s so steps fire at ~10 Hz tick rate.
    )
    # ── Load profile: enables compute↔allreduce power oscillation ─────────────
    load_cfg = LoadProfileConfig(
        f_compute=F_COMPUTE,   # 72% of step at full compute power
        p_comm_ratio=0.55,     # allreduce phase at 55% → ~38% effective drop
        tau_gpu_s=0.06,        # fast lag: transitions in ~1 tick at 10 Hz
        phase_coherence=0.85,  # fleet is 85% coherent → effective drop ≈ 38%
    )

    kube_cfg = KubeConfig(
        max_nodes=node_count * 3,
        min_nodes=node_count,   # always `node_count` nodes active
        hardware_profile_id="enterprise_8gpu_air",
        mean_job_nodes=node_count,
        job_node_std=0,
        min_job_nodes=node_count,
        mean_interarrival_s=9999.0,   # one stable job, no further admissions
        mean_job_duration_s=9999.0,
        min_job_duration_s=9999.0,
        reorder_window_s=0.0,
        ntp_jitter_s=0.0,
        rng_seed=rng_seed,
        step_config=step_cfg,
        load_config=load_cfg,
    )
    kube_agent = KubeDemandAgent(kube_cfg, site_id=state.site.site_id)
    state.kube_agent = kube_agent

    # ── Wire load_config onto GPUModule ───────────────────────────────────────
    # simulation_core propagates step_phase each tick; GPUModule needs
    # load_config set so per_job_compute_mw() applies the profile.
    for gpu in state.gpu_modules:
        gpu.load_config = load_cfg
        # Zero ramp so the job reaches full power on the first tick — avoids
        # a slowly-rising baseline that would obscure the allreduce dip.
        gpu.ramp_seconds = 0.0

    return state


# ---------------------------------------------------------------------------
# TC-01: causal check — allreduce onset WITHIN checkpoint long-step triggers
#         classifier IN_VALLEY or CHECKPOINT on the same tick
# ---------------------------------------------------------------------------

class TestCheckpointSchedulerClassifierAgreement:
    """Two-signal cross-check: StepScheduler step_kind vs CheckpointClassifier.

    TC-01: The classifier fires IN_VALLEY or CHECKPOINT on the tick where
           the checkpoint long-step's allreduce phase first becomes active —
           causally distinct from normal training allreduce cycles.

    TC-01b: checkpoint_states is non-empty on the same tick step_kind="checkpoint"
            first appears, confirming the evaluate_tick() wiring is intact.
    """

    DT_S = 0.1        # 10 Hz — ~7 ticks per median step (0.7 s)
    MAX_SIM_TIME_S = 600.0   # enough for 5+ checkpoints at ckpt_interval_steps=5

    def test_TC01_checkpoint_allreduce_onset_fires_classifier(self):
        """Causal three-phase state machine: the checkpoint long-step's allreduce
        onset (step_phase crossing f_compute=0.72 while step_kind="checkpoint")
        must fire the classifier IN_VALLEY or CHECKPOINT on that tick.

        Why this is causally sound
        --------------------------
        Normal training allreduce cycles span ~2 ticks (0.14 s) at 10 Hz; their
        classifier state is NOT checked here.  The test only asserts the
        classifier state on the first tick where BOTH conditions hold:
            (a) step_kind == "checkpoint"   — scheduler is in a checkpoint step
            (b) step_phase >= f_compute     — the allreduce phase has just started
                                              WITHIN that checkpoint step

        A regression that prevents the checkpoint long-step's allreduce from
        producing a power drop (e.g. load_config not wired, step_phase not
        propagated, or the classifier disconnected from per_job_compute_mw)
        would leave checkpoint_states in NORMAL on that tick, failing this test.
        """
        from core.simulation_core import evaluate_tick

        state = _make_state_with_kube(
            rng_seed=42,
            ckpt_interval_steps=5,   # checkpoint fires after every 5 steps
            ckpt_jitter_steps=0,     # deterministic — no jitter
        )

        n_ticks = round(self.MAX_SIM_TIME_S / self.DT_S)

        # ── State machine ──────────────────────────────────────────────────────
        # SEEK_CKPT_ENTRY  → waiting for step_kind="checkpoint" AND step_phase < 0.1
        # SEEK_ALLREDUCE   → inside checkpoint step; waiting for step_phase >= f_compute
        # ASSERT_DONE      → assertion made; loop exits
        SEEK_CKPT_ENTRY = 0
        SEEK_ALLREDUCE  = 1
        ASSERT_DONE     = 2

        sm_phase = SEEK_CKPT_ENTRY
        ckpt_entry_sim_time = None   # sim_time when checkpoint step compute phase began

        # Assertion results (filled in SEEK_ALLREDUCE → ASSERT_DONE)
        allreduce_onset_sim_time = None
        classifier_state_at_onset = None   # the state string, or None if no active job

        for i in range(n_ticks):
            sim_time = i * self.DT_S
            clock = _make_clock(sim_time, self.DT_S, tick_seq=i)

            with _plane_guard_active():
                result = evaluate_tick(state, clock)

            # ── SEEK_CKPT_ENTRY ───────────────────────────────────────────────
            if sm_phase == SEEK_CKPT_ENTRY:
                # step_phase < 0.1 means the step boundary just fired this tick
                # (phase is 0.0 at exact fire; tiny positive values possible on
                # the next tick due to elapsed/duration arithmetic at 10 Hz).
                if result.step_kind == "checkpoint" and result.step_phase < 0.1:
                    ckpt_entry_sim_time = sim_time
                    sm_phase = SEEK_ALLREDUCE
                continue

            # ── SEEK_ALLREDUCE ────────────────────────────────────────────────
            if sm_phase == SEEK_ALLREDUCE:
                # If the checkpoint step ended before allreduce started (can
                # happen if a new step fires mid-window), restart the search.
                if result.step_kind != "checkpoint":
                    sm_phase = SEEK_CKPT_ENTRY
                    ckpt_entry_sim_time = None
                    continue

                # The allreduce phase of the checkpoint step has started when
                # step_phase >= f_compute.  The first-order lag (tau_gpu_s=0.06s)
                # transitions power within ~1 tick at 10 Hz, so the drop is
                # observable on this same tick.
                if result.step_phase >= F_COMPUTE:
                    allreduce_onset_sim_time = sim_time
                    # Record the classifier state for any active kube job.
                    if result.checkpoint_states:
                        # Pick the first job — there is exactly one stable job
                        # (min_nodes=node_count, mean_interarrival_s=9999).
                        classifier_state_at_onset = next(
                            iter(result.checkpoint_states.values())
                        )
                    sm_phase = ASSERT_DONE
                continue

            # ── ASSERT_DONE ───────────────────────────────────────────────────
            if sm_phase == ASSERT_DONE:
                break

        # ── Assertions ────────────────────────────────────────────────────────

        assert ckpt_entry_sim_time is not None, (
            f"No checkpoint step entry (step_kind='checkpoint', step_phase<0.1) "
            f"appeared in {self.MAX_SIM_TIME_S:.0f} s at {1/self.DT_S:.0f} Hz. "
            f"Check KubeDemandAgent step_config and ckpt_interval_steps."
        )

        assert allreduce_onset_sim_time is not None, (
            f"Checkpoint step started at sim_time={ckpt_entry_sim_time:.2f} s "
            f"but step_phase never reached f_compute={F_COMPUTE} while "
            f"step_kind remained 'checkpoint'.  The checkpoint step may have "
            f"been superseded before its allreduce phase — increase ckpt_min_s "
            f"or reduce DT_S so the long-step spans multiple ticks."
        )

        assert classifier_state_at_onset is not None, (
            f"checkpoint_states was empty on the tick where the checkpoint "
            f"allreduce phase began (sim_time={allreduce_onset_sim_time:.2f} s). "
            f"No active kube job is visible to the classifier.  This means the "
            f"kube STARTING signal was not applied, or no job is registered on "
            f"the GPU module, so record_and_classify() was never called."
        )

        assert classifier_state_at_onset in ("in_valley", "checkpoint"), (
            f"Classifier state was '{classifier_state_at_onset}' on the tick "
            f"where the checkpoint long-step's allreduce phase began "
            f"(sim_time={allreduce_onset_sim_time:.2f} s, checkpoint entry at "
            f"{ckpt_entry_sim_time:.2f} s).  Expected 'in_valley' or 'checkpoint'.\n\n"
            f"The two signals disagree: the scheduler fired a checkpoint long-step "
            f"and its allreduce phase is active (step_phase={F_COMPUTE:.2f}+ while "
            f"step_kind='checkpoint'), but the CheckpointClassifier has NOT detected "
            f"the associated power drop.  This would cause the dashboard to label the "
            f"checkpoint as NORMAL/straggler rather than a confirmed checkpoint.\n\n"
            f"Possible causes:\n"
            f"  (1) load_config not wired to GPUModule → per_job_compute_mw() is flat "
            f"      and the allreduce drop never reaches the classifier;\n"
            f"  (2) step_phase not propagated from kube_agent to GPUModule before "
            f"      advance() → the lag state does not update;\n"
            f"  (3) CheckpointClassifier.record_and_classify() disconnected from the "
            f"      per-job draw in the evaluate_tick() loop."
        )

    def test_TC01b_checkpoint_states_populated_on_first_checkpoint_tick(self):
        """Wiring check: checkpoint_states must be non-empty on the same tick
        that step_kind='checkpoint' first appears.

        If checkpoint_states is empty while step_kind='checkpoint', the wiring
        between KubeDemandAgent and CheckpointClassifier in evaluate_tick() is
        broken — the scheduler signals 'checkpoint' but the classifier never
        saw the job's power draw.

        This is separate from TC-01: it checks the wiring exists at checkpoint
        entry (step_phase≈0, compute phase), not whether the allreduce drop
        fires the classifier.
        """
        from core.simulation_core import evaluate_tick

        state = _make_state_with_kube(
            rng_seed=42,
            ckpt_interval_steps=5,
            ckpt_jitter_steps=0,
        )

        n_ticks = round(self.MAX_SIM_TIME_S / self.DT_S)
        first_ckpt_tick_sim_time = None
        checkpoint_states_at_entry = None

        for i in range(n_ticks):
            sim_time = i * self.DT_S
            clock = _make_clock(sim_time, self.DT_S, tick_seq=i)

            with _plane_guard_active():
                result = evaluate_tick(state, clock)

            if result.step_kind == "checkpoint" and first_ckpt_tick_sim_time is None:
                first_ckpt_tick_sim_time = sim_time
                checkpoint_states_at_entry = dict(result.checkpoint_states)
                break

        assert first_ckpt_tick_sim_time is not None, (
            "No checkpoint step appeared in the run window. "
            "Check KubeDemandAgent step_config."
        )

        assert checkpoint_states_at_entry, (
            f"checkpoint_states was empty on the first tick where "
            f"step_kind='checkpoint' (sim_time={first_ckpt_tick_sim_time:.2f} s). "
            f"The scheduler and classifier wiring is broken: evaluate_tick() sets "
            f"step_kind from kube_agent.current_step_kind but the checkpoint_states "
            f"dict was not populated by CheckpointClassifier.record_and_classify(). "
            f"Check that active_training_jobs() returns jobs for the active kube job."
        )
