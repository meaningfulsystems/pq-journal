#!/usr/bin/env python3
"""Start the PQ Journal server."""
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path


def _ensure_secret_key():
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("SECRET_KEY="):
                os.environ.setdefault("SECRET_KEY", line.split("=", 1)[1].strip())
                return
    key = secrets.token_hex(32)
    with env_file.open("a") as f:
        f.write(f"SECRET_KEY={key}\n")
    os.environ["SECRET_KEY"] = key


def _ollama_running() -> bool:
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
        return True
    except Exception:
        return False


def _start_ollama():
    import shutil
    if not shutil.which("ollama"):
        print("[run.py] Ollama not installed — skipping. Install from https://ollama.com for emotion summaries.")
        return
    if _ollama_running():
        print("[run.py] Ollama already running.")
        return
    print("[run.py] Starting Ollama...")
    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait up to 8s for it to become ready
    for _ in range(16):
        time.sleep(0.5)
        if _ollama_running():
            print("[run.py] Ollama ready.")
            return
    print("[run.py] Ollama did not start in time — continuing without it.")


def _open_browser(url: str):
    import threading
    def _open():
        time.sleep(1.5)
        import webbrowser
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()


if __name__ == "__main__":
    _ensure_secret_key()
    _start_ollama()

    url = "http://127.0.0.1:8000"
    print(f"[run.py] Opening {url}")
    _open_browser(url)

    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
