"""
Hybrid post-quantum + classical encryption.

Scheme: ML-KEM-1024 (NIST FIPS 203) + X25519 ECDH, both shared secrets
combined via HKDF-SHA256 → AES-256-GCM. HMAC-SHA256 over the ciphertext
blob for integrity / tamper detection.

Key file protection: PBKDF2-HMAC-SHA256 (600k iterations) + AES-256-GCM.
"""
from __future__ import annotations

import base64
import hashlib
import hmac as _hmac
import json
import os
from pathlib import Path
from typing import Tuple

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_OQS_AVAILABLE = False
oqs = None  # type: ignore

def _try_load_oqs() -> bool:
    """
    Lazily attempt to load liboqs. Returns True if available.

    liboqs-python's auto-install behavior can be aggressive, so we pre-check
    for the shared library file before importing the Python wrapper.
    """
    global oqs, _OQS_AVAILABLE
    if _OQS_AVAILABLE:
        return True

    # Quick pre-check: does liboqs shared library exist anywhere findable?
    import ctypes.util
    import importlib
    lib_name = ctypes.util.find_library("oqs")
    if lib_name is None:
        # Also check common explicit paths
        import glob
        candidates = (
            glob.glob("/usr/lib*/liboqs*")
            + glob.glob("/usr/local/lib*/liboqs*")
            + glob.glob("/home/*/_oqs/lib*/liboqs*")
            + glob.glob("/opt/homebrew/lib*/liboqs*")
        )
        if not candidates:
            return False

    try:
        _oqs = importlib.import_module("oqs")
        _ = _oqs.get_enabled_kem_mechanisms()
        oqs = _oqs
        _OQS_AVAILABLE = True
        return True
    except Exception:
        return False

KEM_ALG = "ML-KEM-1024"
PBKDF2_ITERATIONS = 600_000
ALG_LABEL = "ML-KEM-1024+X25519+AES-256-GCM+HMAC-SHA256"

# ── helpers ─────────────────────────────────────────────────────────────────

def _b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")

def _b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))

def _hkdf(keymat: bytes, length: int = 32, info: bytes = b"pq-journal-entry") -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=None,
        info=info,
    ).derive(keymat)

def _pbkdf2(password: bytes, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(password)

# ── key generation ──────────────────────────────────────────────────────────

def generate_kem_keypair() -> Tuple[bytes, bytes]:
    """Return (public_key_bytes, private_key_bytes) for ML-KEM-1024."""
    if not _try_load_oqs():
        raise RuntimeError(
            "liboqs not available. Install cmake + liboqs, then: pip install liboqs-python\n"
            "See README.md for platform-specific instructions."
        )
    with oqs.KeyEncapsulation(KEM_ALG) as kem:
        pub = kem.generate_keypair()
        priv = kem.export_secret_key()
    return pub, priv

def generate_x25519_keypair() -> Tuple[bytes, bytes]:
    """Return (public_key_bytes, private_key_bytes) for X25519."""
    priv_key = X25519PrivateKey.generate()
    pub_key = priv_key.public_key()
    priv_bytes = priv_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    pub_bytes = pub_key.public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return pub_bytes, priv_bytes

# ── encryption ───────────────────────────────────────────────────────────────

def encrypt_entry(plaintext: bytes, kem_pub: bytes, x25519_pub: bytes) -> dict:
    """
    Encrypt plaintext for the holder of (kem_priv, x25519_priv).
    Returns a JSON-serialisable dict (the .pqj blob outer envelope).
    """
    if not _try_load_oqs():
        raise RuntimeError(
            "liboqs not available — cannot encrypt. See README.md for install instructions."
        )

    # ML-KEM encapsulation
    with oqs.KeyEncapsulation(KEM_ALG) as kem:
        kem_ct, kem_ss = kem.encap_secret(kem_pub)

    # X25519 ECDH with an ephemeral keypair
    eph_priv = X25519PrivateKey.generate()
    eph_pub_bytes = eph_priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    peer_pub = X25519PublicKey.from_public_bytes(x25519_pub)
    x25519_ss = eph_priv.exchange(peer_pub)

    # Combine both shared secrets via HKDF
    combined = _hkdf(kem_ss + x25519_ss)

    # AES-256-GCM
    nonce = os.urandom(12)
    aesgcm = AESGCM(combined)
    ct_with_tag = aesgcm.encrypt(nonce, plaintext, None)
    ct, tag = ct_with_tag[:-16], ct_with_tag[-16:]

    blob = {
        "version": 2,
        "alg": ALG_LABEL,
        "kem_ct": _b64e(kem_ct),
        "x25519_ephemeral_pub": _b64e(eph_pub_bytes),
        "nonce": _b64e(nonce),
        "tag": _b64e(tag),
        "ct": _b64e(ct),
    }

    # HMAC-SHA256 over the stable fields (everything except "hmac" itself)
    blob["hmac"] = _compute_hmac(blob, combined)
    return blob


def decrypt_entry(blob: dict, kem_priv: bytes, x25519_priv: bytes) -> bytes:
    """
    Decrypt a .pqj blob. Raises ValueError on authentication failure.
    """
    if not _try_load_oqs():
        raise RuntimeError(
            "liboqs not available — cannot decrypt. See README.md for install instructions."
        )

    # ML-KEM decapsulation
    with oqs.KeyEncapsulation(KEM_ALG, secret_key=kem_priv) as kem:
        kem_ss = kem.decap_secret(_b64d(blob["kem_ct"]))

    # X25519 ECDH
    eph_pub = X25519PublicKey.from_public_bytes(_b64d(blob["x25519_ephemeral_pub"]))
    our_priv = X25519PrivateKey.from_private_bytes(x25519_priv)
    x25519_ss = our_priv.exchange(eph_pub)

    combined = _hkdf(kem_ss + x25519_ss)

    # Verify HMAC before decrypting
    expected = _compute_hmac({k: v for k, v in blob.items() if k != "hmac"}, combined)
    if not _hmac.compare_digest(expected, blob.get("hmac", "")):
        raise ValueError("HMAC verification failed — entry may be tampered")

    # AES-256-GCM decrypt
    aesgcm = AESGCM(combined)
    ct_with_tag = _b64d(blob["ct"]) + _b64d(blob["tag"])
    return aesgcm.decrypt(_b64d(blob["nonce"]), ct_with_tag, None)


def _compute_hmac(blob_without_hmac: dict, key: bytes) -> str:
    """Canonical HMAC over sorted JSON of blob fields (excluding 'hmac')."""
    canonical = json.dumps(
        {k: v for k, v in blob_without_hmac.items() if k != "hmac"},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _b64e(_hmac.new(key, canonical, hashlib.sha256).digest())

# ── key file protection ──────────────────────────────────────────────────────

def protect_key(raw: bytes, passphrase: str) -> str:
    """Encrypt raw key bytes with passphrase. Returns a multi-line text string."""
    salt = os.urandom(32)
    key = _pbkdf2(passphrase.encode("utf-8"), salt)
    nonce = os.urandom(12)
    ct_with_tag = AESGCM(key).encrypt(nonce, raw, None)
    ct, tag = ct_with_tag[:-16], ct_with_tag[-16:]
    return (
        f"v=2\n"
        f"salt={_b64e(salt)}\n"
        f"nonce={_b64e(nonce)}\n"
        f"tag={_b64e(tag)}\n"
        f"ct={_b64e(ct)}\n"
    )

def unprotect_key(protected: str, passphrase: str) -> bytes:
    """Decrypt a protected key file. Raises ValueError on wrong passphrase."""
    kv: dict[str, str] = {}
    for line in protected.strip().splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            kv[k.strip()] = v.strip()
    if kv.get("v") != "2":
        raise ValueError("Unknown key file version")
    salt = _b64d(kv["salt"])
    nonce = _b64d(kv["nonce"])
    tag = _b64d(kv["tag"])
    ct = _b64d(kv["ct"])
    key = _pbkdf2(passphrase.encode("utf-8"), salt)
    try:
        return AESGCM(key).decrypt(nonce, ct + tag, None)
    except Exception:
        raise ValueError("Wrong passphrase or corrupted key file")

def key_fingerprint(pub_bytes: bytes) -> str:
    """SHA256 fingerprint of a public key, colon-hex format (first 8 groups)."""
    digest = hashlib.sha256(pub_bytes).hexdigest()
    groups = [digest[i:i+4] for i in range(0, 32, 4)]
    return ":".join(groups)
