#!/usr/bin/env bash
# TripStack — start everything needed for a demo.
#
#   ./start.sh            start Ollama (if needed) then the dashboard
#   ./start.sh --check    verify the setup without starting anything
#
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(dirname "$PROJECT_DIR")"
# Prefer the project environment, then the active environment or system Python.
if [ -n "${PYTHON:-}" ]; then
  PY="$PYTHON"
elif [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
  PY="$PROJECT_DIR/.venv/bin/python"
else
  PY="$(command -v python3 || command -v python || true)"
fi
if [ -z "$PY" ] || ! command -v "$PY" >/dev/null 2>&1; then
  echo "Python not found. Install Python 3.11+ and follow README.md."
  exit 1
fi
OLLAMA_BIN="${OLLAMA_BIN:-$(command -v ollama || true)}"
MODEL="${OLLAMA_MODEL:-gemma:2b}"
CPU_MODE="${TRIPSTACK_CPU:-1}"
if [ "$CPU_MODE" = "1" ]; then
  export GGML_METAL_DEVICES=0
fi
PORT="${PORT:-8599}"

check() {
  echo "Project : $PROJECT_DIR"
  echo "Python  : $PY"
  echo "Model   : $MODEL"
  echo

  "$PY" -c "import pydantic, streamlit, httpx; print('deps      OK (pydantic', pydantic.VERSION, 'streamlit', streamlit.__version__)" \
    || { echo "deps      MISSING -> pip install -r requirements.txt"; exit 1; }

  if curl -sf --noproxy '*' "http://127.0.0.1:11434/api/tags" > /dev/null; then
    echo "ollama    running"
    "$OLLAMA_BIN" list 2>/dev/null | tail -n +2 || true
  else
    echo "ollama    NOT running (the app still works; AI page falls back to rules)"
  fi

  if curl -sf --noproxy '*' "http://127.0.0.1:${PORT}" > /dev/null; then
    echo "dashboard running on http://localhost:${PORT}"
  else
    echo "dashboard not running"
  fi

  echo
  (cd "$PROJECT_DIR" && "$PY" -m pytest -q | tail -1)
}

start() {
  if ! curl -sf --noproxy '*' "http://127.0.0.1:11434/api/tags" > /dev/null; then
    if [ -x "$OLLAMA_BIN" ]; then
      echo "Starting Ollama..."
      "$OLLAMA_BIN" serve &
      sleep 3
    else
      echo "Ollama not installed (brew install ollama). Continuing without it."
    fi
  fi

  echo "Starting dashboard on http://localhost:${PORT}"
  cd "$PROJECT_DIR"
  PYTHONPATH="$WORKSPACE_DIR" OLLAMA_MODEL="$MODEL" \
    exec "$PY" -m streamlit run app.py --server.headless true --server.port "$PORT"
}

case "${1:-start}" in
  --check) check ;;
  start|"") start ;;
  *) echo "usage: $0 [--check]" ; exit 1 ;;
esac
