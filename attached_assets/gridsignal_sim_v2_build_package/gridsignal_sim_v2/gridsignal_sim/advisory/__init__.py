"""
advisory/ — Step 13: §26.2/§26.5 agent authority layer.

Six buildable agents, each following the five-phase loop defined in
advisory/agents/base.py:

  Observe → Qualify → Transform (de-identify) → Reason → Propose

Agents are ADVISORY ONLY.  No agent dispatches.  Proposals pass through
runtime/advisory_gate.py (TC-30) and may be accepted or rejected by a
reviewer.  TC-48 proves that with proposals un-actioned the dispatch
trace is bit-identical to a run with agents stopped.

Package layout
--------------
advisory/agents/base.py         — BaseAdvisoryAgent (five-phase loop + provenance)
advisory/agents/{name}.py       — Six concrete agents
advisory/agent_registry.py      — AgentRegistry (ON/OFF toggle + cadence)
advisory/prompts/compute.txt    — Canonical system prompt for Compute agent
advisory/prompts/calibration.txt — Canonical system prompt for Calibration agent
"""
