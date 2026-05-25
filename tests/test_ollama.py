"""
Ollama connectivity and LLM output test.

Run with:
    .venv/bin/python tests/test_ollama.py

Checks:
  1. Ollama is reachable at the configured URL
  2. The configured model is pulled and available
  3. A raw /api/generate call returns a non-empty response
  4. synthesize_live_emotion() returns an LLM phrase (not a fallback)
  5. synthesize_emotion() (used by Analyze button) returns a phrase
"""
import sys
import json
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
import yaml

# ── Load settings ─────────────────────────────────────────────────────────────

def _load_settings() -> dict:
    for candidate in [Path("settings.yaml"), Path.home() / ".pq-journal" / "settings.yaml"]:
        if candidate.exists():
            with open(candidate) as f:
                return yaml.safe_load(f) or {}
    return {}

cfg = _load_settings()
OLLAMA_URL   = cfg.get("ollama_url",   "http://localhost:11434")
OLLAMA_MODEL = cfg.get("ollama_model", "llama3.2:3b")

PASS = "\033[92m  PASS\033[0m"
FAIL = "\033[91m  FAIL\033[0m"
INFO = "\033[94m  INFO\033[0m"

def _hdr(title: str):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")

# ── Test 1: Ollama reachable ───────────────────────────────────────────────────

_hdr("1 · Ollama reachable")
print(f"  URL:   {OLLAMA_URL}")
try:
    r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3.0)
    if r.status_code == 200:
        print(PASS + f"  /api/tags → HTTP {r.status_code}")
        tags_data = r.json()
    else:
        print(FAIL + f"  /api/tags returned HTTP {r.status_code}")
        sys.exit(1)
except Exception as e:
    print(FAIL + f"  Cannot reach Ollama: {e}")
    print("       Is Ollama running?  Try:  ollama serve")
    sys.exit(1)

# ── Test 2: Model is pulled ────────────────────────────────────────────────────

_hdr("2 · Model available")
print(f"  Model: {OLLAMA_MODEL}")
models = [m.get("name", "") for m in tags_data.get("models", [])]
print(f"{INFO}  Pulled models: {models or '(none)'}")
model_found = any(OLLAMA_MODEL in m for m in models)
if model_found:
    print(PASS + f"  '{OLLAMA_MODEL}' is pulled")
else:
    print(FAIL + f"  '{OLLAMA_MODEL}' not found in pulled models")
    print(f"       Fix:  ollama pull {OLLAMA_MODEL}")
    sys.exit(1)

# ── Test 3: Raw generation call ────────────────────────────────────────────────

_hdr("3 · Raw /api/generate call")
PROBE_PROMPT = "Reply with exactly four words describing a calm morning walk."
print(f"  Prompt: \"{PROBE_PROMPT}\"")
try:
    r = httpx.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": PROBE_PROMPT, "stream": False},
        timeout=15.0,
    )
    if r.status_code == 200:
        raw_text = r.json().get("response", "").strip()
        if raw_text:
            print(PASS + f"  Response: \"{raw_text}\"")
        else:
            print(FAIL + "  Response was empty")
            sys.exit(1)
    else:
        print(FAIL + f"  HTTP {r.status_code}: {r.text[:200]}")
        sys.exit(1)
except Exception as e:
    print(FAIL + f"  Request failed: {e}")
    sys.exit(1)

# ── Test 4: synthesize_live_emotion (live recording path) ─────────────────────

_hdr("4 · synthesize_live_emotion()  [live recording path]")
from app.services.llm import synthesize_live_emotion, _live_fallback

test_cases = [
    dict(V=0.5,  A=0.7,  D=0.3,  label="high arousal, positive"),
    dict(V=-0.4, A=0.6,  D=-0.2, label="high arousal, negative"),
    dict(V=0.2,  A=0.2,  D=0.1,  label="low arousal, slightly positive"),
]

all_passed = True
for tc in test_cases:
    V, A, D = tc["V"], tc["A"], tc["D"]
    fallback = _live_fallback(V, A, D, None)
    result   = synthesize_live_emotion(V, A, D, None, OLLAMA_URL, OLLAMA_MODEL)
    is_llm   = result != fallback
    status   = PASS if is_llm else FAIL
    tag      = "LLM ✓" if is_llm else f"FALLBACK (matched rule-based: '{fallback}')"
    print(f"{status}  [{tc['label']}]  V={V} A={A} D={D}")
    print(f"         result:   \"{result}\"")
    print(f"         source:   {tag}")
    if not is_llm:
        all_passed = False

# ── Test 5: synthesize_emotion (Analyze button path) ──────────────────────────

_hdr("5 · synthesize_emotion()  [Analyze Emotion button path]")
from app.services.llm import synthesize_emotion

paragraphs = [
    {"emotion_label": "joy",     "emotion_scores": {"joy": 0.7, "neutral": 0.3}},
    {"emotion_label": "neutral", "emotion_scores": {"joy": 0.2, "neutral": 0.8}},
]
vad = {"V": 0.4, "A": 0.5, "D": 0.1}

result = synthesize_emotion(paragraphs, vad, None, OLLAMA_URL, OLLAMA_MODEL)
print(f"  Input:  paragraphs=[joy, neutral], VAD={vad}")
print(f"  Result: \"{result}\"")
if result and result not in ("", "text emotion is joy and neutral"):
    print(PASS + "  Got a synthesized phrase")
else:
    print(FAIL + "  Result looks like raw context (LLM may not have responded)")
    all_passed = False

# ── Summary ────────────────────────────────────────────────────────────────────

print(f"\n{'═'*60}")
if all_passed:
    print("\033[92m  ALL TESTS PASSED — Ollama LLM is working correctly\033[0m")
else:
    print("\033[91m  SOME TESTS FAILED — LLM is falling back to rule-based phrases\033[0m")
    print("  Check that Ollama is running and the model is responding.")
    print(f"  Try manually:  ollama run {OLLAMA_MODEL}")
print(f"{'═'*60}\n")
