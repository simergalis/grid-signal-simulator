---
name: Gridley RAG grounding
description: The retrieval and safety boundary for Claude-written Ask Gridley responses.
---

Ask Gridley uses a local curated Markdown corpus with deterministic lexical
retrieval for product explanations, alongside a normalized server-side
simulator snapshot for live facts. Claude writes read-only conversational
answers when available, but it does not determine control actions.

**Why:** Product questions arrive in many natural phrasings, while simulator
telemetry and scenario mutations must remain reproducible and safely bounded.
The initial implementation intentionally avoids embeddings, vector databases,
and third-party retrieval services.

**How to apply:** Add approved knowledge as curated Markdown sections and
preserve the distinction between retrieved product guidance and authoritative
simulator values. Keep live-system refusals, scenario validation,
confirmation, audit logging, and mutation execution deterministic. Any future
retrieval replacement must retain source metadata and a grounded fallback.