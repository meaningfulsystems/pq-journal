"""
Key storage: loading, saving, and detecting key directories.
Keys are always stored on an external location (USB drive, separate directory).
"""
from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Optional

import psutil

from app.services.crypto import (
    generate_kem_keypair,
    generate_x25519_keypair,
    protect_key,
    unprotect_key,
    key_fingerprint,
)

KEY_FILES = {
    "kem_pub": "ml_kem.pub",
    "kem_priv": "ml_kem.priv",
    "x25519_pub": "x25519.pub",
    "x25519_priv": "x25519.priv",
}


def detect_removable_drives() -> list[dict]:
    """
    Return a list of removable drives detected on the system.
    Cross-platform: works on Linux, macOS, and Windows.
    """
    drives = []
    try:
        for part in psutil.disk_partitions(all=False):
            is_removable = False

            if platform.system() == "Windows":
                # On Windows, check drive type via opts string
                is_removable = "removable" in part.opts.lower()
            elif platform.system() == "Darwin":
                # macOS: /Volumes/* that are not the main disk
                is_removable = part.mountpoint.startswith("/Volumes/") and part.mountpoint != "/Volumes/Macintosh HD"
            else:
                # Linux: check /media or /run/media, or opts contains removable
                is_removable = (
                    "/media/" in part.mountpoint
                    or "/run/media/" in part.mountpoint
                    or "removable" in part.opts.lower()
                )

            if is_removable and part.mountpoint:
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    drives.append({
                        "mountpoint": part.mountpoint,
                        "device": part.device,
                        "fstype": part.fstype,
                        "free_gb": round(usage.free / 1e9, 1),
                        "total_gb": round(usage.total / 1e9, 1),
                    })
                except (PermissionError, OSError):
                    drives.append({
                        "mountpoint": part.mountpoint,
                        "device": part.device,
                        "fstype": part.fstype,
                        "free_gb": None,
                        "total_gb": None,
                    })
    except Exception:
        pass
    return drives


def browse_directory(path: str, allowed_root: Optional[str] = None) -> dict:
    """
    Return directory contents for the server-side file browser.
    Rejects path traversal attempts.
    """
    try:
        p = Path(path).resolve()
    except Exception:
        return {"error": "Invalid path", "dirs": [], "files": [], "current": str(path)}

    # Path traversal guard: if allowed_root set, must stay within it
    if allowed_root:
        root = Path(allowed_root).resolve()
        try:
            p.relative_to(root)
        except ValueError:
            return {"error": "Path outside allowed root", "dirs": [], "files": [], "current": str(p)}

    if not p.exists() or not p.is_dir():
        return {"error": "Directory not found", "dirs": [], "files": [], "current": str(p)}

    dirs, files = [], []
    try:
        for entry in sorted(p.iterdir()):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                dirs.append({"name": entry.name, "path": str(entry)})
            elif entry.is_file():
                files.append({
                    "name": entry.name,
                    "path": str(entry),
                    "size": entry.stat().st_size,
                })
    except PermissionError:
        return {"error": "Permission denied", "dirs": [], "files": [], "current": str(p)}

    parent = str(p.parent) if p != p.parent else None
    return {
        "current": str(p),
        "parent": parent,
        "dirs": dirs,
        "files": files,
        "error": None,
    }


def load_keys(key_dir: str, passphrase: str) -> dict:
    """
    Load and decrypt key files from key_dir.
    Returns dict with kem_pub, kem_priv, x25519_pub, x25519_priv as bytes.
    Raises ValueError on wrong passphrase or missing files.
    """
    d = Path(key_dir)
    result = {}
    for key_name, filename in KEY_FILES.items():
        fpath = d / filename
        if not fpath.exists():
            raise ValueError(f"Key file not found: {filename} in {key_dir}")
        content = fpath.read_text(encoding="utf-8")
        if key_name.endswith("_pub"):
            # Public keys stored as raw base64 (no passphrase)
            import base64
            result[key_name] = base64.b64decode(content.strip())
        else:
            # Private keys protected with passphrase
            result[key_name] = unprotect_key(content, passphrase)
    return result


def save_keys(key_dir: str, passphrase: str, keypairs: dict) -> dict:
    """
    Save key files to key_dir.
    keypairs: {kem_pub, kem_priv, x25519_pub, x25519_priv} as bytes.
    Returns fingerprint info.
    """
    import base64
    d = Path(key_dir)
    d.mkdir(parents=True, exist_ok=True)

    # Public keys: raw base64, no protection needed (they're public)
    for pub_key in ("kem_pub", "x25519_pub"):
        fpath = d / KEY_FILES[pub_key]
        fpath.write_text(base64.b64encode(keypairs[pub_key]).decode("ascii"), encoding="utf-8")
        _secure_chmod(fpath)

    # Private keys: passphrase-protected
    for priv_key in ("kem_priv", "x25519_priv"):
        fpath = d / KEY_FILES[priv_key]
        protected = protect_key(keypairs[priv_key], passphrase)
        fpath.write_text(protected, encoding="utf-8")
        _secure_chmod(fpath)

    # Write a key metadata file
    meta = {
        "created": _iso_now(),
        "alg": "ML-KEM-1024+X25519",
        "kem_fingerprint": key_fingerprint(keypairs["kem_pub"]),
        "x25519_fingerprint": key_fingerprint(keypairs["x25519_pub"]),
    }
    import json
    (d / "key.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return meta


def generate_and_save_keys(key_dir: str, passphrase: str) -> dict:
    """Generate a fresh keypair and save it. Returns fingerprint info."""
    kem_pub, kem_priv = generate_kem_keypair()
    x25519_pub, x25519_priv = generate_x25519_keypair()
    keypairs = {
        "kem_pub": kem_pub,
        "kem_priv": kem_priv,
        "x25519_pub": x25519_pub,
        "x25519_priv": x25519_priv,
    }
    return save_keys(key_dir, passphrase, keypairs)


def key_dir_has_keys(key_dir: str) -> bool:
    """Return True if key_dir contains all required key files."""
    d = Path(key_dir)
    return all((d / fn).exists() for fn in KEY_FILES.values())


def _secure_chmod(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass  # Windows doesn't support chmod


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
