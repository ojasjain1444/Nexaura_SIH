#!/bin/bash
# The ONLY way to start this backend manually. Never run `uvicorn
# app.main:app ...` directly — use this script instead (or, from the
# project root, ./start.sh which calls this).
#
# Checks for a real, already-listening server on port 8000 BEFORE
# invoking uvicorn at all. This matters specifically because of a
# confirmed, reproducible macOS issue: starting a second
# `uvicorn --reload` while one is already running does not just fail
# harmlessly. Its child process correctly detects the conflict and exits,
# but the RELOADER'S PARENT watcher process independently touches the
# socket first and can leave it in a broken CLOSED state that then
# prevents the REAL, already-running server from accepting new
# connections — verified live: `lsof -i :8000` still showed the real
# server as LISTEN, but `nc -zv localhost 8000` reported "Connection
# refused" until the orphaned reloader parent was killed, at which point
# the real server immediately started responding again. The only reliable
# fix is to never let a second uvicorn process touch the socket in the
# first place.
set -e

cd "$(dirname "${BASH_SOURCE[0]}")"

if command -v nc >/dev/null 2>&1 && nc -z -G 1 localhost 8000 2>/dev/null; then
  echo "ERROR: something is already listening on port 8000." >&2
  echo "Do not start a second backend — it can break the running one, not just fail." >&2
  echo "Run ./stop.sh from the project root first if you need to restart." >&2
  exit 1
fi

exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
