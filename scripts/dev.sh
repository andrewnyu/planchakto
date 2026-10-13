#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -d .venv ]; then python3 -m venv .venv; .venv/bin/pip install -r backend/requirements.lock.txt; fi
if [ ! -d frontend/node_modules ]; then npm ci --prefix frontend; fi
npm run build --prefix frontend
if [ -f .env ]; then
  exec .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port "${BUILDGRAPH_PORT:-8011}" --env-file .env
else
  exec .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port "${BUILDGRAPH_PORT:-8011}"
fi
