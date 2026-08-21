#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python -m uvicorn api:app --host 127.0.0.1 --port 8787
