#!/bin/bash
# Stops whatever is running on the backend (8000) and frontend (5173)
# ports — the counterpart to start.sh. Run this before start.sh if you
# need to restart, instead of starting a second instance on a different
# port (which is what caused the repeated "duplicate process" failures).
for port in 8000 5173; do
  pid=$(lsof -ti ":$port" 2>/dev/null)
  if [ -n "$pid" ]; then
    echo "Stopping process on port $port (pid $pid)..."
    kill $pid
  else
    echo "Nothing running on port $port."
  fi
done

# The single-instance lock (see backend/app/core/single_instance.py)
# releases automatically when the holding process exits, but removing the
# file too avoids any confusion about whether a stale lock is present.
sleep 1
rm -f "$(dirname "${BASH_SOURCE[0]}")/backend/.backend.lock"
