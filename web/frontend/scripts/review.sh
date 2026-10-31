#!/usr/bin/env bash
# One-command reviewer loop (SCRUM-193): seed demo data, start the live
# API server, and open Storybook against it. Ctrl-C stops everything.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$DIR/../../.." && pwd)"
PORT="${PORT:-5001}"
API_URL="http://127.0.0.1:${PORT}"

SCRATCH=""
if [ -z "${DATABASE_URL:-}" ]; then
  SCRATCH="$(mktemp -d)"
  export DATABASE_URL="sqlite:///${SCRATCH}/review.db"
fi

cleanup() {
  kill "$FLASK_PID" 2>/dev/null || true
  if [ -n "$SCRATCH" ]; then
    rm -rf "$SCRATCH"
  fi
}
trap cleanup EXIT

cd "$ROOT"
echo "==> Seeding fresh demo data into $DATABASE_URL"
PYTHONPATH=database:pipeline:service:web \
  service/.venv/bin/python -m evolvingclass_web.seed

echo "==> Starting live API server on $API_URL"
PYTHONPATH=database:pipeline:service:web PORT="$PORT" ALLOW_TEST_RESET=1 \
  service/.venv/bin/python -m evolvingclass_web.app &
FLASK_PID=$!

for _ in $(seq 1 30); do
  if curl -sf "$API_URL/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -sf "$API_URL/api/health" >/dev/null

echo "==> Starting Storybook against the live server"
cd "$DIR/.."
OPEN=""
if [ -t 1 ]; then
  OPEN="--open"
fi
# shellcheck disable=SC2086
API_URL="$API_URL" npx storybook dev -p 6006 --host 127.0.0.1 $OPEN
