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
# Use if/else — the original ${KEY:+word}${KEY:-fallback} pattern concatenates
# both branches when KEY is set (":+" gives "word", ":-" gives the key VALUE),
# leaking the secret into the log.  Proper conditionals avoid that.
if [ -n "${MISTRAL_API_KEY:-}" ]; then
    echo "    MISTRAL_API_KEY  : SET (LP-1 Mistral path active)"
else
    echo "    MISTRAL_API_KEY  : ABSENT (LP-1 no-op active)"
fi
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    echo "    ANTHROPIC_API_KEY: SET (LP-1 Anthropic path active)"
else
    echo "    ANTHROPIC_API_KEY: ABSENT (LP-1 no-op active)"
fi
echo ""

cd "$BACKEND_DIR"

# AA6: uvicorn requires the `websockets` (or `wsproto`) library to handle
# WebSocket upgrades.  Without it every WS request returns HTTP 404.
# The Nix store is read-only, so we install into .pythonlibs — the same
# writable directory that uvicorn itself lives in.  The check is a fast
# no-op when the package is already present.
PYTHONLIBS_SITE="/home/runner/workspace/.pythonlibs/lib/python3.13/site-packages"
python3 -c "import websockets" 2>/dev/null || \
  pip3 install --target="$PYTHONLIBS_SITE" websockets --quiet 2>&1 | tail -1 || true

# asyncpg is required when DATABASE_URL is set (Replit managed PostgreSQL).
# Without it user accounts are stored in a SQLite file inside the container
# image and are wiped on every publish.
python3 -c "import asyncpg" 2>/dev/null || \
  pip3 install --target="$PYTHONLIBS_SITE" asyncpg --quiet 2>&1 | tail -1 || true

# Use `python3 -m uvicorn` rather than bare `uvicorn` so the module is found
# via the Python path (.pythonlibs) rather than requiring uvicorn on $PATH.
# PYTHONPATH must include the backend root so `from core.xxx import ...` resolves.
exec env PYTHONPATH="$BACKEND_DIR:${PYTHONPATH:-}" \
  python3 -m uvicorn api.app:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --log-level info
