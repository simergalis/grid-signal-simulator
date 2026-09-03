"""
This module has been moved to runtime/scenario_factory.py.

It was relocated because build_run_context() and build_load_test_context()
both construct and return RunContext — a runtime/ concept — and must import
InMemoryTimeseriesSink and RunContext from runtime.run_manager.  That import
edge violated the core/ -> runtime/ layering invariant required by v2.5 §21.1
and Design Spec §2 principle 2 (core/ must not depend on runtime/).

Update your import:
    # before
    from core.scenario_factory import build_run_context
    # after
    from runtime.scenario_factory import build_run_context
"""
raise ImportError(
    "core.scenario_factory has moved to runtime.scenario_factory. "
    "Update your import: from runtime.scenario_factory import ..."
)
