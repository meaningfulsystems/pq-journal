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

_LIVE_PROMPT_TEMPLATE = (
    "You are an empathetic journaling assistant. Someone is speaking aloud while journaling.\n"
    "{transcript_section}"
    "Voice tone — valence={V:.2f} (-1=negative, +1=positive), "
    "arousal={A:.2f} (0=calm, 1=energetic), dominance={D:.2f} (0=submissive, 1=assertive)"
    "{face_str}.\n"
    "Write a single nuanced phrase (4-8 words) capturing their emotional state right now, "
    "grounded in what they said and how they said it. First-person, specific and human, not clinical. "
    "Examples: 'playful and energized by silly wordplay', 'content after a good weekend', "
    "'a little worried but mostly at ease'. "
    "Respond with only the phrase, no punctuation at the end."
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


def synthesize_live_emotion(
    V: float,
    A: float,
    D: float,
    face_emotion: Optional[str] = None,
    ollama_url: str = "http://localhost:11434",
    ollama_model: str = "llama3.2:3b",
    transcript: str = "",
) -> str:
    """
    Generate a rich real-time emotional summary from transcript + VAD + optional face data.
    Falls back to a rule-based phrase if Ollama is unavailable.
    """
    face_str = ""
    if face_emotion and face_emotion not in ("", "no face", "no face detected"):
        face_str = f", facial expression: {face_emotion}"

    transcript_section = ""
    if transcript.strip():
        transcript_section = f"Over the last minute they said: \"{transcript.strip()}\"\n"

    prompt = _LIVE_PROMPT_TEMPLATE.format(
        V=V, A=A, D=D, face_str=face_str, transcript_section=transcript_section
    )

    try:
        import httpx
        r = httpx.post(
            f"{ollama_url}/api/generate",
            json={"model": ollama_model, "prompt": prompt, "stream": False},
            timeout=8.0,
        )
        if r.status_code == 200:
            text = r.json().get("response", "").strip().strip(".")
            if text:
                logger.info(f"LLM live summary: '{text}' (V={V:.2f} A={A:.2f} D={D:.2f})")
                return text
    except Exception as e:
        logger.debug(f"Ollama unavailable for live summary: {e}")

    fallback = _live_fallback(V, A, D, face_emotion)
    logger.info(f"Live summary fallback: '{fallback}' (V={V:.2f} A={A:.2f} D={D:.2f})")
    return fallback


def _live_fallback(V: float, A: float, D: float, face_emotion: Optional[str]) -> str:
    """Rule-based fallback: produces a human phrase from V/A/D values."""
    if A < 0.2:
        mood = "subdued and still" if V >= 0 else "quiet and withdrawn"
    elif A < 0.45:
        if V > 0.3:
            mood = "calm and content"
        elif V < -0.3:
            mood = "low-key but unsettled"
        else:
            mood = "measured and steady"
    elif A < 0.65:
        if V > 0.3:
            mood = "engaged and warm"
        elif V < -0.3:
            mood = "tense and guarded"
        else:
            mood = "focused and present"
    else:
        mood = "energetic and expressive" if V >= 0 else "intense and agitated"

    if face_emotion and face_emotion not in ("", "no face", "no face detected"):
        return f"{mood}, appearing {face_emotion}"
    return mood


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
