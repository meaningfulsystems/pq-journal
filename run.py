#!/usr/bin/env python3
"""Start the PQ Journal server."""
import os
import secrets
from pathlib import Path


def _ensure_secret_key():
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("SECRET_KEY="):
                os.environ.setdefault("SECRET_KEY", line.split("=", 1)[1].strip())
                return
    # Generate and persist a new key
    key = secrets.token_hex(32)
    with env_file.open("a") as f:
        f.write(f"SECRET_KEY={key}\n")
    os.environ["SECRET_KEY"] = key


if __name__ == "__main__":
    _ensure_secret_key()
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
