#!/usr/bin/env bash
# Starts the backend (FastAPI on :8000) and frontend (Vite on :5173) together.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$HOME/.nodejs/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

if [ ! -x "$ROOT/backend/.venv/bin/uvicorn" ] || [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "First run: setting things up..."
  "$ROOT/setup.sh"
fi

# Free our ports if an older SilentVoice (uvicorn / vite) is still running on them.
for PORT in 8000 5173; do
  for PID in $(lsof -ti tcp:$PORT -sTCP:LISTEN 2>/dev/null || true); do
    CMD="$(ps -o command= -p "$PID" 2>/dev/null || true)"
    if echo "$CMD" | grep -Eq "uvicorn|vite"; then
      echo "Stopping old SilentVoice process on port $PORT (pid $PID)"
      kill "$PID" 2>/dev/null || true
    else
      echo "Port $PORT is used by another program: $CMD"
      echo "Close it and run ./start.sh again."
      exit 1
    fi
  done
done
sleep 1

cleanup() {
  echo ""
  echo "Stopping SilentVoice..."
  if [ -n "${BACK:-}" ] && kill -0 "$BACK" 2>/dev/null; then
    kill "$BACK" 2>/dev/null || true
  fi
  if [ -n "${FRONT:-}" ] && kill -0 "$FRONT" 2>/dev/null; then
    kill "$FRONT" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

(cd "$ROOT/backend" && exec .venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000) &
BACK=$!
(cd "$ROOT/frontend" && exec npm run dev -- --host 127.0.0.1) &
FRONT=$!

echo ""
echo "  SilentVoice:      http://localhost:5173   (open in Chrome)"
echo "  API health:       http://127.0.0.1:8000/api/health"
echo "  Zoom Virtual Mic: Select 'BlackHole 2ch' in Zoom Settings > Audio > Microphone"
echo "  The lip-reading model loads in the background (about 20-60 s)."
echo "  Press Ctrl+C to stop."
echo ""
wait
