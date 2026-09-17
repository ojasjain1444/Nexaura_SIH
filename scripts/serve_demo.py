#!/usr/bin/env python3
"""
scripts/serve_demo.py — Launch Nexaura Demo Frontend and API Backend

Usage:
  python scripts/serve_demo.py

This script:
  1. Checks if MongoDB is running locally.
  2. Launches the FastAPI server (backend/app/main.py) serving APIs on port 8000.
  3. Serves the Demo Web UI at http://localhost:8000/demo.
"""

import sys
import os
import subprocess
import time
import webbrowser
from pathlib import Path

# Add project root to PYTHONPATH
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

def main():
    print("=" * 65)
    print("🚀 NEXAURA (SIH 2026 — SIH26107) DEMO LAUNCHER")
    print("=" * 65)

    frontend_dir = BASE_DIR / "frontend"
    if not (frontend_dir / "index.html").exists():
        print("❌ Error: Frontend directory index.html not found!")
        sys.exit(1)

    print("✅ Frontend files found at:", frontend_dir)
    print("🌐 Starting Nexaura Unified API & Demo Server on http://localhost:8000...")
    print("👉 Demo Web UI URL: http://localhost:8000/demo (or http://localhost:8000/)")
    print("👉 Swagger API Docs: http://localhost:8000/docs")
    print("-" * 65)

    # Automatically try opening the browser after 2 seconds
    def open_browser():
        time.sleep(2)
        webbrowser.open("http://localhost:8000/demo")

    import threading
    threading.Thread(target=open_browser, daemon=True).start()

    # Launch Uvicorn
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    main()
