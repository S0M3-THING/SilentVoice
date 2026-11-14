#!/usr/bin/env bash
# One-time setup: Python backend, lip-reading model code, frontend packages.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "==> Checking tools"
command -v ffmpeg >/dev/null || { echo "ffmpeg is missing. Install it with: brew install ffmpeg"; exit 1; }
command -v npm >/dev/null || { echo "Node.js is missing. Install it from https://nodejs.org (v18+)."; exit 1; }

echo "==> Lip-reading model code (Chaplin / Auto-AVSR)"
if [ ! -d backend/vendor/chaplin/pipelines ]; then
  if [ -d chaplin/pipelines ]; then
    mkdir -p backend/vendor && mv chaplin backend/vendor/chaplin
  else
    git clone --depth 1 https://github.com/amanvirparhar/chaplin.git backend/vendor/chaplin
  fi
fi

echo "==> Python environment (backend/.venv, Python 3.11)"
cd backend
if [ ! -x .venv/bin/python ]; then
  if command -v uv >/dev/null; then uv venv --python 3.11 .venv
  else python3.11 -m venv .venv || python3 -m venv .venv; fi
fi
if command -v uv >/dev/null; then
  VIRTUAL_ENV=.venv uv pip install -r requirements.txt -r requirements-dev.txt
else
  .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
fi
[ -f .env ] || cp .env.example .env
cd ..

echo "==> Frontend packages"
(cd frontend && npm install)

echo ""
echo "Setup done. Start SilentVoice with ./start.sh"
echo "The lip-reading model (~1 GB) downloads automatically the first time the backend starts."
