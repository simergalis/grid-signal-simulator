---
name: CoolingModule deque cursor design (P1)
description: O(1) amortised lagged-sample lookup using absolute cursor + pruned_count. THE TRAP with popleft() shifting plain integer indices.
---

**The problem (P1):**
`min(env.history, key=lambda s: abs(s[0]-t))` is O(N) per envelope per tick. At 250 envelopes × 38 samples = ~9,500 comparisons/tick. p50 went 719→919 µs (+27%), 2x wall 28.1 s near 30 s budget.

**The fix:**
`_LoadEnvelope.history: deque` (was list). Two new fields:
- `_cursor_abs: int` — absolute index into the conceptual "all samples ever appended" sequence.
- `_pruned_count: int` — samples removed via `popleft()`.
- Deque-relative index: `cursor_rel = _cursor_abs - _pruned_count`.
- `_lagged_mw` advances cursor while `history[cursor_rel+1][0] <= target_time`. O(1) amortised (lag_time is monotonically increasing each tick).

**THE TRAP:**
If you hold a plain `int` index into a `deque` and call `popleft()`, the index silently refers to the NEXT element — no error, wrong value. The absolute counter + pruned_count pair avoids this: after `popleft()`, increment `_pruned_count`, so `cursor_rel = _cursor_abs - _pruned_count` stays correct.

**Pruning guard:**
After pruning, if `_cursor_abs < _pruned_count`, pin `_cursor_abs = _pruned_count`. This handles the edge case where rapid pruning advances past a stale cursor.

**Retention rule (P3):**
Envelope retained for `dt_thermal + 5τ` seconds after `end_t`. Pruning happens in `advance()` each tick. `load_mw` must NOT be zeroed on close (scalar path) — `_lagged_mw` returns `load_mw` for `target_time ≤ end_t`, so P_cooling stays elevated for ~dt_thermal after job end and decays naturally. Zeroing causes instantaneous P_cooling drop (discontinuity).

**Why:** Pruning earlier causes discontinuous P_cooling drop. Never pruning leaks one envelope per job. Zeroing load_mw on close causes P_cooling to collapse in one tick instead of decaying over dt_thermal.
