#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install -q -r requirements.txt
REASON_PREVIEW_TOKEN="${REASON_PREVIEW_TOKEN:-$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))')}"
export REASON_PREVIEW_TOKEN
printf '\nREASON SIMULATION PREVIEW\nOpen http://127.0.0.1:8080\nAccess code: %s\nNo real broker or paid AI calls.\n\n' "$REASON_PREVIEW_TOKEN"
exec .venv/bin/python -m uvicorn reason.app:app --host 127.0.0.1 --port 8080 --workers 1
