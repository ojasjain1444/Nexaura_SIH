#!/bin/bash
# Starts the backend (port 8000) and frontend (port 5173) — the ONE way to
# start this app. Refuses to start a duplicate if either port is already
# occupied, instead of silently letting two backends/frontends fight over
# the same port (which happened repeatedly: whichever process wins a given
# request differs unpredictably, so some requests succeed and others fail
# with no obvious cause — exactly the "Couldn't get a response" errors
# seen live). If you need to restart, run ./stop.sh first.
set -e

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/backend" && pwd)"
FRONTEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/frontend" && pwd)"

check_port() {
  local port=$1
  local name=$2
  if lsof -i ":$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "ERROR: port $port is already in use (expected: $name)." >&2
    echo "Something is already running here. Run ./stop.sh first, or check what's using it:" >&2
    echo "  lsof -i :$port" >&2
    exit 1
  fi
}

check_port 8000 "backend (uvicorn)"
check_port 5173 "frontend (vite)"

echo "Starting backend on :8000..."
(cd "$BACKEND_DIR" && nohup ./run.sh > /tmp/nexaura_backend.log 2>&1 &)

echo "Starting frontend on :5173..."
(cd "$FRONTEND_DIR" && nohup npm run dev > /tmp/nexaura_frontend.log 2>&1 &)

# Polls rather than a fixed sleep: the backend pre-loads the embedding
# model at startup (see app/main.py's lifespan hook) so the FIRST real
# chat request is never the slow one — but that means startup itself can
# take anywhere from ~2s (model already cached from a previous run) to
# 60s+ (first run ever, downloading the model). A fixed short sleep was
# confirmed to report a false "backend did not respond" warning while a
# slow-but-healthy warmup was still in progress.
echo "Waiting for backend to finish starting (this can take up to a minute on first run)..."
backend_ready=false
for _ in $(seq 1 60); do
  if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/docs 2>/dev/null | grep -q 200; then
    backend_ready=true
    break
  fi
  sleep 1
done

if [ "$backend_ready" = true ]; then
  echo "Backend is up: http://localhost:8000"
else
  echo "WARNING: backend did not respond within 60s — check /tmp/nexaura_backend.log"
fi

frontend_ready=false
for _ in $(seq 1 15); do
  if curl -s -o /dev/null -w "%{http_code}" http://localhost:5173 2>/dev/null | grep -q 200; then
    frontend_ready=true
    break
  fi
  sleep 1
done

if [ "$frontend_ready" = true ]; then
  echo "Frontend is up: http://localhost:5173"
else
  echo "WARNING: frontend did not respond — check /tmp/nexaura_frontend.log"
fi
