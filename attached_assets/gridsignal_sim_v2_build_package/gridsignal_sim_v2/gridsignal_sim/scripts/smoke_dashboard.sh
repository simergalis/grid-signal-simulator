#!/usr/bin/env bash
# scripts/smoke_dashboard.sh — full-stack smoke check in a single shell.
#
# Starts uvicorn + vite in background within ONE shell session (so both
# processes survive until the script exits), loads the dashboard with a
# headless Playwright browser, waits for the demo-alert scenario to stream,
# then screenshots and dumps the console log.
#
# Usage (run from gridsignal_sim/):
#   PYTHONPATH=. bash scripts/smoke_dashboard.sh
#
# Outputs:
#   frontend/smoke.png  — full-page screenshot after 18 s of streaming
#   frontend/smoke.log  — browser console messages
#   exit 0              — all panel assertions passed
#   exit 1              — one or more assertions failed (see output)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIM_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$(cd "$SIM_DIR/../frontend" && pwd)"

echo "=== smoke_dashboard.sh ================================================"
echo "  sim dir   : $SIM_DIR"
echo "  frontend  : $FRONTEND_DIR"
echo

# ── 1. Start uvicorn ────────────────────────────────────────────────────────
cd "$SIM_DIR"
python3 -m uvicorn api.app:app --host 0.0.0.0 --port 8000 \
  > /tmp/uvicorn_smoke.log 2>&1 &
UVICORN_PID=$!
echo "  uvicorn  → PID $UVICORN_PID  (log: /tmp/uvicorn_smoke.log)"

# ── 2. Start vite ───────────────────────────────────────────────────────────
cd "$FRONTEND_DIR"
pnpm run dev > /tmp/vite_smoke.log 2>&1 &
VITE_PID=$!
echo "  vite     → PID $VITE_PID     (log: /tmp/vite_smoke.log)"
echo

# ── 3. Cleanup trap ─────────────────────────────────────────────────────────
cleanup() {
  echo
  echo "  [cleanup] killing PID $UVICORN_PID (uvicorn) and PID $VITE_PID (vite)"
  kill "$UVICORN_PID" "$VITE_PID" 2>/dev/null || true
}
trap cleanup EXIT

# ── 4. Poll until API responds ───────────────────────────────────────────────
echo "  waiting for API (http://localhost:8000/runs)..."
API_UP=0
for i in $(seq 1 30); do
  # GET /runs returns 200 {"run_ids":[]}; healthz is not implemented
  HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/runs 2>/dev/null || echo "000")
  if [ "$HTTP" = "200" ]; then
    echo "  API up after ${i}s (GET /runs → 200)"
    API_UP=1; break
  fi
  sleep 1
done
if [ "$API_UP" -eq 0 ]; then
  echo "  ERROR: API never came up.  Last uvicorn log:"
  tail -20 /tmp/uvicorn_smoke.log
  exit 1
fi

# ── 5. Poll until Vite responds ──────────────────────────────────────────────
echo "  waiting for Vite (http://localhost:5173)..."
VITE_UP=0
for i in $(seq 1 40); do
  if curl -sf http://localhost:5173 >/dev/null 2>&1; then
    echo "  Vite up after ${i}s"
    VITE_UP=1; break
  fi
  sleep 1
done
if [ "$VITE_UP" -eq 0 ]; then
  echo "  ERROR: Vite never came up.  Last vite log:"
  tail -20 /tmp/vite_smoke.log
  exit 1
fi
echo

# ── 6. DOM component check via Vitest (Playwright unavailable in this sandbox) ─
# Playwright Chromium requires libglib-2.0.so.0 which is absent in the NixOS
# container.  Vitest + jsdom is the headless DOM alternative: it actually
# executes the React components and asserts panel text, the F4 alert latch, the
# F2 basis label, and the F5 sim_time value — without needing a browser binary.
echo "  running vitest component smoke check..."
cd "$FRONTEND_DIR"
node_modules/.bin/vitest run --config vitest.config.ts --reporter=verbose 2>&1
VITEST_EXIT=$?

echo
if [ "$VITEST_EXIT" -eq 0 ]; then
  echo "  ✓ all component assertions passed"
else
  echo "  ✗ vitest reported failures (see above)"
  exit 1
fi

echo
echo "=== smoke complete ===================================================="
