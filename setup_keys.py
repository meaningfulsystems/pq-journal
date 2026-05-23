#!/usr/bin/env python3
"""
PQ Journal — First-time key generation wizard.

Generates ML-KEM-1024 + X25519 keypairs, protects private keys with a
passphrase, and saves them to a directory you choose (ideally a USB drive).

Usage:
    python setup_keys.py
    python setup_keys.py --key-dir /path/to/usb/meaningful-journal-keys
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="PQ Journal key generation")
    parser.add_argument("--key-dir", help="Directory to save keys (created if needed)")
    args = parser.parse_args()

    print()
    print("  PQ Journal — Key Generation")
    print("  ============================")
    print()

    # Check dependencies
    try:
        import oqs  # noqa: F401
    except ImportError:
        print("ERROR: pyoqs is not installed.")
        print("  Install with: pip install pyoqs")
        print()
        print("  On Windows, you may need Visual Studio Build Tools first.")
        print("  See README.md for platform-specific instructions.")
        sys.exit(1)

    try:
        from app.services.key_store import (
            detect_removable_drives,
            generate_and_save_keys,
            key_dir_has_keys,
        )
    except ImportError as e:
        print(f"ERROR: Cannot import app modules: {e}")
        print("Make sure you're running from the pq-journal directory with the venv active.")
        sys.exit(1)

    # Key directory selection
    if args.key_dir:
        key_dir = args.key_dir
    else:
        # Show detected drives
        drives = detect_removable_drives()
        if drives:
            print("  Detected removable drives:")
            for i, d in enumerate(drives, 1):
                free = f"{d['free_gb']}GB free" if d.get('free_gb') is not None else "?"
                print(f"    [{i}] {d['mountpoint']} ({d['device']}, {free})")
            print()

        default_dir = str(Path.home() / "meaningful-journal-keys")
        key_dir = input(f"  Key directory [{default_dir}]: ").strip()
        if not key_dir:
            key_dir = default_dir

    key_dir = str(Path(key_dir).expanduser().resolve())
    print(f"\n  Keys will be saved to: {key_dir}")

    if key_dir_has_keys(key_dir):
        overwrite = input("\n  Key files already exist. Overwrite? [y/N]: ").strip().lower()
        if overwrite != "y":
            print("  Aborted.")
            sys.exit(0)

    # Passphrase
    print()
    while True:
        passphrase = getpass.getpass("  Passphrase (min 12 chars): ")
        if len(passphrase) < 12:
            print("  Passphrase too short. Try again.")
            continue
        confirm = getpass.getpass("  Confirm passphrase: ")
        if passphrase != confirm:
            print("  Passphrases do not match. Try again.")
            continue
        break

    # Generate keys
    print()
    print("  Generating ML-KEM-1024 + X25519 keypairs...")
    try:
        meta = generate_and_save_keys(key_dir, passphrase)
    except Exception as e:
        print(f"\n  ERROR: Key generation failed: {e}")
        sys.exit(1)

    print()
    print("  ✓ Keys generated successfully!")
    print()
    print(f"  Algorithm:        ML-KEM-1024 + X25519")
    print(f"  KEM fingerprint:  {meta['kem_fingerprint']}")
    print(f"  X25519 fingerprint: {meta['x25519_fingerprint']}")
    print(f"  Created:          {meta['created']}")
    print()
    print("  Files saved:")
    for fname in ["ml_kem.pub", "ml_kem.priv", "x25519.pub", "x25519.priv", "key.json"]:
        print(f"    {key_dir}/{fname}")
    print()
    print("  IMPORTANT: Back up these key files.")
    print("  Without them (and your passphrase), your journal entries")
    print("  cannot be decrypted.")
    print()
    print(f"  Next step: uvicorn app.main:app --host 127.0.0.1 --port 8000")
    print(f"  Then open:  http://127.0.0.1:8000")
    print()


if __name__ == "__main__":
    main()
