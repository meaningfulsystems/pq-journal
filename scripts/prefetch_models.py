#!/usr/bin/env python3
"""
Pre-download all optional AI models so first-run startup is instant.

Run once after installing requirements-optional.txt:
    python scripts/prefetch_models.py

Models fetched:
    DeepFace emotion weights  ~6 MB   -> ~/.deepface/weights/
    Whisper STT model         ~500 MB -> ~/.cache/huggingface/hub/
    HuggingFace emotion model ~250 MB -> ~/.cache/huggingface/hub/
"""
from __future__ import annotations

import sys


def _header(label: str) -> None:
    print(f"\n{'─' * 50}")
    print(f"  {label}")
    print(f"{'─' * 50}")


def _ok(msg: str) -> None:
    print(f"  ✓  {msg}")


def _skip(msg: str) -> None:
    print(f"  –  {msg} (already cached)")


def _fail(msg: str) -> None:
    print(f"  ✗  {msg}", file=sys.stderr)


# ── 1. DeepFace emotion model ────────────────────────────────────────────────

def fetch_deepface() -> None:
    _header("DeepFace facial emotion model (~6 MB)")
    try:
        from pathlib import Path
        weights = Path.home() / ".deepface" / "weights" / "facial_expression_model_weights.h5"
        if weights.exists():
            _skip(f"facial_expression_model_weights.h5  ({weights.stat().st_size // 1024} KB)")
            return

        import numpy as np
        from deepface import DeepFace
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        DeepFace.analyze(img_path=img, actions=["emotion"], enforce_detection=False, silent=True)
        _ok(f"Downloaded to {weights}")
    except ImportError:
        _fail("deepface not installed — run: pip install deepface tf-keras")
    except Exception as e:
        _fail(f"DeepFace prefetch failed: {e}")


# ── 2. Whisper STT model ─────────────────────────────────────────────────────

def fetch_whisper(model_name: str = "small") -> None:
    _header(f"Whisper STT model '{model_name}' (~500 MB for 'small')")
    try:
        from pathlib import Path
        import re
        # faster-whisper caches to ~/.cache/huggingface/hub/
        cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "-", model_name)
        existing = list(cache_dir.glob(f"*whisper*{safe_name}*")) if cache_dir.exists() else []
        if existing:
            _skip(f"whisper-{model_name}  (found in {cache_dir})")
            return

        print(f"  Downloading whisper/{model_name} — this may take a few minutes...")
        from faster_whisper import WhisperModel
        WhisperModel(model_name, device="cpu", compute_type="int8")
        _ok(f"Whisper '{model_name}' ready")
    except ImportError:
        _fail("faster-whisper not installed — run: pip install faster-whisper")
    except Exception as e:
        _fail(f"Whisper prefetch failed: {e}")


# ── 3. HuggingFace text emotion model ───────────────────────────────────────

def fetch_hf_emotion() -> None:
    model_id = "j-hartmann/emotion-english-distilroberta-base"
    _header(f"HuggingFace emotion model (~250 MB)")
    try:
        from pathlib import Path
        cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
        slug = model_id.replace("/", "--")
        existing = list(cache_dir.glob(f"models--{slug}")) if cache_dir.exists() else []
        if existing:
            _skip(f"{model_id}  (found in {cache_dir})")
            return

        print(f"  Downloading {model_id} — this may take a minute...")
        from transformers import pipeline
        pipeline("text-classification", model=model_id, top_k=None)
        _ok(f"HuggingFace emotion model ready")
    except ImportError:
        _fail("transformers not installed — run: pip install transformers torch")
    except Exception as e:
        _fail(f"HuggingFace prefetch failed: {e}")


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Pre-download PQ Journal AI models")
    parser.add_argument("--whisper-model", default="small",
                        help="Whisper model name (default: small)")
    parser.add_argument("--skip-whisper", action="store_true")
    parser.add_argument("--skip-deepface", action="store_true")
    parser.add_argument("--skip-hf", action="store_true")
    args = parser.parse_args()

    print("\nPQ Journal — model prefetch")
    print("Cached models load instantly on next server start.\n")

    if not args.skip_deepface:
        fetch_deepface()
    if not args.skip_whisper:
        fetch_whisper(args.whisper_model)
    if not args.skip_hf:
        fetch_hf_emotion()

    print(f"\n{'─' * 50}")
    print("  All done. Start the server with:  python run.py")
    print(f"{'─' * 50}\n")
