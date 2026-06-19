#!/usr/bin/env python3
"""
Crime Analysis Mapper — One-Command Launcher
============================================

Usage:
    python run.py --check      # Check system requirements
"""
import subprocess
import sys
import os
import time
import threading
import argparse
from pathlib import Path

ROOT = Path(__file__).parent
PYTHON = sys.executable


def check_requirements():
    """Check all system requirements and print status."""
    print("\n=== System Requirements Check ===")
    ok = True

    # Python packages
    packages = [
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("streamlit", "streamlit"),
        ("aiohttp", "aiohttp"),
        ("ddgs", "ddgs"),
        ("mcp", "mcp"),
        ("ollama", "ollama"),
        ("bs4", "beautifulsoup4"),
        ("sqlalchemy", "sqlalchemy"),
        ("pydantic", "pydantic"),
    ]
    for mod, pkg in packages:
        try:
            __import__(mod)
            print(f"  [OK] {pkg}")
        except ImportError:
            print(f"  [MISSING] {pkg}  ->  pip install {pkg}")
            ok = False

    # Ollama service
    import urllib.request
    print("\n--- Ollama ---")
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            import json
            data = json.loads(r.read())
            models = [m["name"] for m in data.get("models", [])]
            print(f"  [OK] Ollama running. Models: {models}")
            if not models:
                print("  [WARN] No models pulled. Run: ollama pull qwen2.5:0.5b")
    except Exception as e:
        print(f"  [MISSING] Ollama not running: {e}")
        print("           Install: https://ollama.ai | Then run: ollama serve")
        ok = False

    # MCP server script
    print("\n--- MCP Server ---")
    mcp_path = ROOT / "new_version" / "osint-tools-mcp-server" / "src" / "osint_tools_mcp_server.py"
    if mcp_path.exists():
        print(f"  [OK] {mcp_path}")
    else:
        print(f"  [MISSING] {mcp_path}")

    # Database
    print("\n--- Database ---")
    db_path = ROOT / "data" / "crime_analysis.db"
    if db_path.exists():
        print(f"  [OK] SQLite DB: {db_path} ({db_path.stat().st_size} bytes)")
    else:
        print(f"  [INFO] SQLite DB will be created on first run.")

    print(f"\nOverall: {'READY' if ok else 'ISSUES FOUND — fix above before running'}")
    return ok


def run_backend():
    """Start FastAPI backend on port 8000."""
    print("[Backend] Starting FastAPI on http://localhost:8000 ...")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    proc = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "backend.api.main:app",
         "--host", "0.0.0.0", "--port", "8000", "--reload"],
        cwd=ROOT,
        env=env,
    )
    return proc


def run_frontend():
    """Start Streamlit frontend on port 8501."""
    print("[Frontend] Starting Streamlit on http://localhost:8501 ...")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    proc = subprocess.Popen(
        [PYTHON, "-m", "streamlit", "run",
         str(ROOT / "frontend" / "app.py"),
         "--server.port", "8501",
         "--server.address", "0.0.0.0",
         "--server.headless", "true"],
        cwd=ROOT,
        env=env,
    )
    return proc


def run_celery():
    """Start Celery worker."""
    print("[Celery] Starting Celery worker ...")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    # Using 'celery' command, assuming it is installed. On Windows, --pool=solo is often needed.
    proc = subprocess.Popen(
        [PYTHON, "-m", "celery", "-A", "backend.workers.celery_app", "worker", "--loglevel=info", "--pool=solo"],
        cwd=ROOT,
        env=env,
    )
    return proc

def main():
    parser = argparse.ArgumentParser(description="Crime Analysis Mapper Launcher")
    parser.add_argument("--backend", action="store_true", help="Start backend only")
    parser.add_argument("--frontend", action="store_true", help="Start frontend only")
    parser.add_argument("--check", action="store_true", help="Check requirements")
    args = parser.parse_args()

    if args.check:
        check_requirements()
        return

    procs = []

    if args.backend:
        procs.append(run_backend())
        procs.append(run_celery())
    elif args.frontend:
        procs.append(run_frontend())
    else:
        # Both
        backend_proc = run_backend()
        procs.append(backend_proc)
        celery_proc = run_celery()
        procs.append(celery_proc)
        # Wait a moment for backend to start before opening frontend
        time.sleep(3)
        procs.append(run_frontend())
        print("\n" + "="*60)
        print(" Crime Analysis Mapper is starting!")
        print(" Backend  API: http://localhost:8000")
        print(" Frontend UI:  http://localhost:8501")
        print(" Celery   :    Running background tasks")
        print(" API Docs:     http://localhost:8000/docs")
        print("="*60)
        print(" Press Ctrl+C to stop all services")
        print("="*60 + "\n")

    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        print("\n[*] Shutting down...")
        for p in procs:
            p.terminate()
        print("[*] Done.")


if __name__ == "__main__":
    main()
