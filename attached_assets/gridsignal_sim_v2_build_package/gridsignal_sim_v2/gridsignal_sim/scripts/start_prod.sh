#!/usr/bin/env bash
# start_prod.sh — Step 16 / §10.2 single-process production entrypoint.
#
# §10.2 "single Repl process, single port" model:
#   1. (Build step is done by build_prod.sh; frontend/dist/ must already exist.)
#   2. Start uvicorn on $PORT (default 8080), serving both the FastAPI API
#      and the pre-built React frontend as static files via api/app.py.
#
# LP-1 guarantee:
#   MISTRAL_API_KEY and ANTHROPIC_API_KEY are NOT required.  When both are
#   absent the advisory router is a no-op and the sim runs deterministically
#   with the heuristic fallback.  The deployment is fully functional without
#   any LLM keys — LP-1 is re-verified post-deploy by GETs against this server.
#
# No external database or cloud service is referenced — §22.7 / v2.5 §0.1.
#   All state is in-process (RunManager, WebSocketHub).  A restart clears
#   in-flight runs; completed run history is in-memory (scope boundary,
#   Step 9 durability note).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# gridsignal_sim_v2/gridsignal_sim/scripts/ → gridsignal_sim_v2/gridsignal_sim/
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

PORT="${PORT:-8080}"

echo "=== [start_prod] GridSignal Simulator v2 ==="
echo "    Backend dir  : $BACKEND_DIR"
echo "    Listening on : 0.0.0.0:$PORT"
echo "    MISTRAL_API_KEY  : ${MISTRAL_API_KEY:+SET (LP-1 Mistral path active)}${MISTRAL_API_KEY:-ABSENT (LP-1 no-op active)}"
echo "    ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:+SET (LP-1 Anthropic path active)}${ANTHROPIC_API_KEY:-ABSENT (LP-1 no-op active)}"
echo ""

cd "$BACKEND_DIR"

# PYTHONPATH must include the backend root so `from core.xxx import ...` resolves.
exec env PYTHONPATH="$BACKEND_DIR:${PYTHONPATH:-}" \
  uvicorn api.app:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --log-level info
