"""
Optional LLM synthesis for multi-modal emotion phrases.
Priority: Ollama → llama-cpp-python → rule-based fallback (no LLM needed).
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Optional

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = (
    "You are an empathetic writing assistant. In one sentence, describe the emotional "
    "state expressed by someone journaling, given these observations: {context}. "
    "Be warm and specific. Do not list the labels verbatim."
)


def synthesize_emotion(
    paragraphs: list[dict],
    vad_summary: Optional[dict] = None,
    face_emotion: Optional[str] = None,
    ollama_url: str = "http://localhost:11434",
    ollama_model: str = "llama3.2:3b",
) -> str:
    """
    Synthesize a human-readable emotion phrase from multi-modal data.
    Falls back to a rule-based phrase if no LLM is reachable.
    """
    context = _build_context(paragraphs, vad_summary, face_emotion)
    if not context:
        return ""

    result = _try_ollama(context, ollama_url, ollama_model)
    if result:
        return result

    result = _try_llamacpp(context)
    if result:
        return result

    return context


def _build_context(
    paragraphs: list[dict],
    vad: Optional[dict],
    face_emotion: Optional[str],
) -> str:
    parts: list[str] = []

    if paragraphs:
        labels = [p.get("emotion_label", "") for p in paragraphs if p.get("emotion_label")]
        if labels:
            common = Counter(labels).most_common(2)
            emotion_str = " and ".join(label for label, _ in common)
            parts.append(f"text emotion is {emotion_str}")

    if vad:
        v, a = vad.get("V", 0.0), vad.get("A", 0.0)
        tone = _vad_phrase(v, a)
        if tone:
            parts.append(f"voice tone is {tone}")

    if face_emotion and face_emotion not in ("", "no face", "no face detected"):
        parts.append(f"facial expression shows {face_emotion}")

    return "; ".join(parts)


def _try_ollama(context: str, url: str, model: str) -> Optional[str]:
    try:
        import httpx
        prompt = _PROMPT_TEMPLATE.format(context=context)
        r = httpx.post(
            f"{url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=8.0,
        )
        if r.status_code == 200:
            text = r.json().get("response", "").strip()
            if text:
                return text
    except Exception as e:
        logger.debug(f"Ollama not available: {e}")
    return None


def _try_llamacpp(context: str) -> Optional[str]:
    try:
        from llama_cpp import Llama  # type: ignore
        # Would need a configured model path — skip until user configures one
    except ImportError:
        pass
    return None


def _vad_phrase(V: float, A: float) -> str:
    if A < 0.2:
        return "quiet and restrained"
    if A > 0.65:
        return "energetic and expressive" if V >= 0 else "intense and agitated"
    if V > 0.3:
        return "warm and positive"
    if V < -0.3:
        return "tense and guarded"
    return ""
