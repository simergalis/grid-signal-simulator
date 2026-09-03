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

validate_startup_secrets() {
    # Required auth group: auth_utils accepts either key for JWT signing.
    # Email login is a production path, so SendGrid must fail closed rather
    # than silently falling back to a console OTP.
    local missing=()
    if [ -z "${JWT_SECRET:-}" ] && [ -z "${SESSION_SECRET:-}" ]; then
        missing+=("JWT_SECRET or SESSION_SECRET")
    fi
    if [ -z "${SENDGRID_API_KEY:-}" ]; then
        missing+=("SENDGRID_API_KEY")
    fi
    if [ -z "${SENDGRID_FROM_EMAIL:-}" ]; then
        missing+=("SENDGRID_FROM_EMAIL")
    fi
    if [ "${#missing[@]}" -gt 0 ]; then
        echo "ERROR: production startup blocked: missing required production secret(s): ${missing[*]}. Configure them in Replit Secrets." >&2
        return 1
    fi

    echo "    JWT_SECRET / SESSION_SECRET: REQUIRED (one present)"
    echo "    SENDGRID_API_KEY          : REQUIRED (email login)"
    echo "    SENDGRID_FROM_EMAIL       : REQUIRED (email login)"
    if [ -n "${MISTRAL_API_KEY:-}" ]; then
        echo "    MISTRAL_API_KEY  : OPTIONAL (LP-1 Mistral path active)"
    else
        echo "    MISTRAL_API_KEY  : OPTIONAL (LP-1 no-op active)"
    fi
    if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
        echo "    ANTHROPIC_API_KEY: OPTIONAL (LP-1 Anthropic path active)"
    else
        echo "    ANTHROPIC_API_KEY: OPTIONAL (LP-1 no-op active)"
    fi
}

echo "=== [start_prod] GridSignal Simulator v2 ==="
echo "    Backend dir  : $BACKEND_DIR"
echo "    Listening on : 0.0.0.0:$PORT"
validate_startup_secrets
echo ""

if [ "${1:-}" = "--check-secrets" ] || [ "${GRIDSIGNAL_STARTUP_CHECK_ONLY:-0}" = "1" ]; then
    exit 0
fi

cd "$BACKEND_DIR"

# openpyxl is declared in pyproject.toml, but the published runtime may not
# install project packages before invoking this entrypoint.  The reference
# forecast bootstrap reads an .xlsx workbook, so keep the runtime guard
# alongside the other deployment-only dependency guards below.
PYTHONLIBS_SITE="/home/runner/workspace/.pythonlibs/lib/python3.13/site-packages"
python3 -c "import openpyxl" 2>/dev/null || \
  pip3 install --target="$PYTHONLIBS_SITE" openpyxl --quiet 2>&1 | tail -1 || true

# The published database is separate from development and may not contain the
# read-only 52-week reference forecast even when the route and dev data exist.
# The importer is idempotent by dataset_id: it seeds a missing baseline and
# reports "skipped existing" on subsequent starts.
if [ -n "${DATABASE_URL:-}" ]; then
    echo "    Reference forecast : ensuring 52-week baseline is available"
    python3 -m scripts.import_reference_forecast
fi

# AA6: uvicorn requires the `websockets` (or `wsproto`) library to handle
# WebSocket upgrades.  Without it every WS request returns HTTP 404.
# The Nix store is read-only, so we install into .pythonlibs — the same
# writable directory that uvicorn itself lives in.  The check is a fast
# no-op when the package is already present.
python3 -c "import websockets" 2>/dev/null || \
  pip3 install --target="$PYTHONLIBS_SITE" websockets --quiet 2>&1 | tail -1 || true

# asyncpg is required when DATABASE_URL is set (Replit managed PostgreSQL).
# Without it user accounts are stored in a SQLite file inside the container
# image and are wiped on every publish.
python3 -c "import asyncpg" 2>/dev/null || \
  pip3 install --target="$PYTHONLIBS_SITE" asyncpg --quiet 2>&1 | tail -1 || true

# tzdata is required by Python's zoneinfo module (stdlib ≥ 3.9) on systems
# that don't ship IANA timezone data (e.g. minimal Linux containers).
# Without it current_utc_offset_h() silently falls back to the standard-time
# offset, breaking the DST correction for the location clock and solar model.
python3 -c "import zoneinfo; zoneinfo.ZoneInfo('America/Los_Angeles')" 2>/dev/null || \
  pip3 install --target="$PYTHONLIBS_SITE" tzdata --quiet 2>&1 | tail -1 || true

# Use `python3 -m uvicorn` rather than bare `uvicorn` so the module is found
# via the Python path (.pythonlibs) rather than requiring uvicorn on $PATH.
# PYTHONPATH must include the backend root so `from core.xxx import ...` resolves.
exec env PYTHONPATH="$BACKEND_DIR:${PYTHONPATH:-}" \
  python3 -m uvicorn api.app:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --log-level info
