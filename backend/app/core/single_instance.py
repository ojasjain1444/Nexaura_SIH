"""
Single-instance guard for the backend process.

Two things were confirmed via live testing before landing on this
approach:

1. Relying on the port bind alone is not sufficient on macOS: a second
   `uvicorn --host 0.0.0.0 --port 8000` did not fail — both processes
   stayed alive and both appeared in `lsof -i:8000`.

2. Checking INSIDE the ASGI lifespan hook is too late: by the time
   lifespan runs, uvicorn (and especially `--reload`'s separate parent
   watcher process) has already touched the socket. Rejecting the
   duplicate at that point still left a broken CLOSED-state socket
   reference from the reloader's parent process, which then prevented the
   REAL, already-running server from accepting new connections — `lsof`
   still showed it as LISTEN, but `nc -zv localhost 8000` reported
   "Connection refused" until the orphaned reloader parent was killed.

The fix: check at true Python MODULE IMPORT time (called from the top of
app/main.py, before the FastAPI app object or lifespan exists at all) —
confirmed via direct timing that `import app.main` completes before
uvicorn does any socket work, so exiting here happens early enough that
the duplicate process never touches the socket in the first place.

This must NOT fire when pytest imports app.main (TestClient(app) is a
legitimate concurrent in-process "instance" that never binds a real
socket) — detected via "pytest" in sys.modules, the standard way to tell
whether the current process is a pytest run, since pytest always imports
itself before collecting test files.
"""

import fcntl
import sys
from pathlib import Path

_LOCK_PATH = Path(__file__).resolve().parent.parent.parent / ".backend.lock"
_lock_file = None  # kept open for the process lifetime — closing it releases the lock


def acquire_or_exit() -> None:
    if "pytest" in sys.modules:
        return

    global _lock_file
    _lock_file = open(_LOCK_PATH, "w")
    try:
        fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print(
            "ERROR: another instance of this backend is already running "
            f"(lock held: {_LOCK_PATH}). Run ./stop.sh from the project root first.",
            file=sys.stderr,
        )
        sys.exit(1)
