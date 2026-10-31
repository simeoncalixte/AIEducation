#!/usr/bin/env bash
# Deterministic live-server interaction run: fresh temp database, seeded
# demo data, live API server, Storybook, then the test-runner suite.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$DIR/../../.." && pwd)"
PORT="${PORT:-5123}"
API_URL="http://127.0.0.1:${PORT}"
SB_URL="http://127.0.0.1:6006"

SCRATCH="$(mktemp -d)"
export DATABASE_URL="sqlite:///${SCRATCH}/live.db"

cleanup() {
  kill "$FLASK_PID" "$SB_PID" 2>/dev/null || true
  rm -rf "$SCRATCH"
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

echo "==> Starting Storybook on $SB_URL"
cd "$DIR/.."
API_URL="$API_URL" npx storybook dev -p 6006 --host 127.0.0.1 &
SB_PID=$!
for _ in $(seq 1 120); do
  if curl -sf "$SB_URL/iframe.html" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -sf "$SB_URL/iframe.html" >/dev/null

echo "==> Running interaction suite"
npx test-storybook --url "$SB_URL"
