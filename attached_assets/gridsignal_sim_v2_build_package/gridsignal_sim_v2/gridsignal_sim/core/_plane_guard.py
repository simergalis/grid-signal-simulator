"""
Control-plane purity sentinel — Step 4 / Design Spec §4.3.

A ContextVar that evaluate_tick() reads at entry.  When the sentinel is
absent (default False) evaluate_tick() raises RuntimeError, blocking any
call that bypasses the runtime harness.

Placement contract
------------------
DEFINED HERE (core/) so evaluate_tick() can check it with a plain
relative import, keeping core/ free of any runtime/ dependency.

SET BY THE CALLER: runtime/run_manager.py:RunContext.step() wraps each
evaluate_tick() call in _EVALUATE_TICK_PERMITTED.set(True) / .reset().
evaluate_tick() itself never sets the sentinel — that would be self-
signing and would defeat the purpose of the guard.

Test code that needs to call evaluate_tick() directly must import this
variable and manage the token itself, or use the plane_guard_active()
context manager in tests/test_plane_separation.py.
"""

import contextvars
from typing import Final

_EVALUATE_TICK_PERMITTED: Final[contextvars.ContextVar[bool]] = (
    contextvars.ContextVar("_EVALUATE_TICK_PERMITTED", default=False)
)
