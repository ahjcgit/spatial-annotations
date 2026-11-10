#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/dev_env.sh
if command -v uv >/dev/null; then
  [[ -x .venv/bin/python ]] || uv venv --python 3.11 .venv
  uv pip install --python .venv/bin/python -r backend/requirements-dev.txt
else
  [[ -x .venv/bin/python ]] || python3 -m venv .venv
  .venv/bin/python -m pip install -r backend/requirements-dev.txt
fi
java -version
printf '%s\n' 'Environment ready. Run: source scripts/dev_env.sh && .venv/bin/python scripts/demo.py'
