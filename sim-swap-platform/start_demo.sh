#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python scripts/init_demo.py
printf '\nYour local demo access token (valid two hours):\n'
.venv/bin/python scripts/issue_demo_token.py
printf '\nOpen http://127.0.0.1:8000 and paste this token. Ctrl+C stops the server.\n'
.venv/bin/python scripts/run.py
