#!/usr/bin/env bash
# build_prod.sh — Step 16 / §10.2 production build step.
#
# Runs at deployment build time (before start_prod.sh).
# Installs Node deps (if missing) and compiles the React dashboard to
# gridsignal_sim_v2/frontend/dist/.
#
# Python deps are already present in the Replit environment via pyproject.toml;
# no pip install step is needed here.
#
# No external database or cloud service is referenced — §22.7 / v2.5 §0.1.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# gridsignal_sim_v2/gridsignal_sim/scripts/ → gridsignal_sim_v2/
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

echo "=== [build_prod] Building React dashboard ==="
echo "    Frontend dir : $FRONTEND_DIR"

cd "$FRONTEND_DIR"

if [[ ! -d node_modules ]]; then
  echo "    npm install (first-run cache miss)"
  npm install
fi

# tsc + vite build (mirrors package.json "build" script)
npm run build

echo "=== [build_prod] Frontend build complete: $FRONTEND_DIR/dist/ ==="
