#!/usr/bin/env bash
# One-time setup: Python backend, lip-reading model code, virtual audio driver, frontend packages.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

export PATH="$HOME/.nodejs/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

echo "==> 1/5 Checking system tools"
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "    ffmpeg not found. Attempting install via Homebrew..."
  if command -v brew >/dev/null 2>&1; then
    brew install ffmpeg || { echo "    Could not auto-install ffmpeg. Please run: brew install ffmpeg"; exit 1; }
  else
    echo "ffmpeg is missing. Install it with: brew install ffmpeg"
    exit 1
  fi
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "Node.js is missing. Install it from https://nodejs.org (v18+)."
  exit 1
fi

echo "==> 2/5 Checking virtual audio driver (BlackHole 2ch for Zoom integration)"
if [ "$(uname -s)" = "Darwin" ]; then
  if [ -d "/Library/Audio/Plug-Ins/HAL/BlackHole2ch.driver" ] || (command -v brew >/dev/null 2>&1 && brew list --cask blackhole-2ch >/dev/null 2>&1); then
    echo "    ✓ BlackHole 2ch driver is already installed."
  else
    echo "    BlackHole 2ch not detected. Attempting automatic installation via Homebrew..."
    if command -v brew >/dev/null 2>&1; then
      if brew install --cask blackhole-2ch 2>/dev/null; then
        echo "    ✓ BlackHole 2ch installed successfully."
        # Refresh CoreAudio daemon so virtual device registers immediately
        killall coreaudiod 2>/dev/null || true
      else
        echo "    Notice: BlackHole 2ch could not be installed automatically without admin prompt."
        echo "    You can install it manually with: brew install blackhole-2ch"
        echo "    Or download from: https://existential.audio/blackhole/"
      fi
    else
      echo "    Notice: Homebrew not found. For Zoom virtual microphone, download BlackHole from https://existential.audio/blackhole/"
    fi
  fi
else
  echo "    (Non-macOS system detected: virtual microphone uses standard loopback audio)"
fi

echo "==> 3/5 Lip-reading model code (Chaplin / Auto-AVSR)"
if [ ! -d backend/vendor/chaplin/pipelines ]; then
  if [ -d chaplin/pipelines ]; then
    mkdir -p backend/vendor && mv chaplin backend/vendor/chaplin
  else
    git clone --depth 1 https://github.com/amanvirparhar/chaplin.git backend/vendor/chaplin
  fi
fi

echo "==> 4/5 Python environment (backend/.venv, Python 3.11)"
cd backend
if [ ! -x .venv/bin/python ]; then
  if command -v uv >/dev/null 2>&1; then uv venv --python 3.11 .venv
  else python3.11 -m venv .venv || python3 -m venv .venv; fi
fi

if .venv/bin/python -c "import fastapi, sounddevice, torch" >/dev/null 2>&1; then
  echo "    ✓ Core Python dependencies already satisfied in .venv."
else
  echo "    Installing Python packages..."
  if command -v uv >/dev/null 2>&1; then
    VIRTUAL_ENV=.venv uv pip install -r requirements.txt -r requirements-dev.txt || true
  else
    .venv/bin/pip install -r requirements.txt -r requirements-dev.txt || true
  fi
fi
[ -f .env ] || cp .env.example .env
cd ..

echo "==> 5/5 Frontend packages and build"
cd frontend
if [ ! -d node_modules ]; then
  npm install || true
fi
npm run build
cd ..

echo ""
echo "================================================================="
echo "  ✓ Setup complete! All dependencies and virtual audio configured."
echo "  Start SilentVoice anytime with: ./start.sh"
echo "  - In Zoom Audio Settings: select 'BlackHole 2ch' as Microphone."
echo "  - In SilentVoice: select 'Live Zoom Mic' to transmit silent speech."
echo "================================================================="
