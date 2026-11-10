#!/usr/bin/env bash
# Ejecuta la suite del harness. No llama al LLM real.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-venv/bin/python}"
if [ ! -x "$PY" ]; then
  PY="python3"
fi
"$PY" -m py_compile agent.py agent_core/*.py
"$PY" -m unittest discover -s tests -v
