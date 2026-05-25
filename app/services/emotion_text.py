"""
Per-paragraph emotion classification.
Primary: j-hartmann/emotion-english-distilroberta-base (HuggingFace)
Fallback: keyword heuristic (no dependencies)
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Optional

logger = logging.getLogger(__name__)

_classifier = None
_engine: str = "keywords"

_LABELS = {
    "joy": "joyful",
    "sadness": "melancholic",
    "anger": "frustrated",
    "fear": "anxious",
    "disgust": "unsettled",
    "neutral": "calm",
    "surprise": "surprised",
}

_KEYWORDS: dict[str, list[str]] = {
    "joy": ["happy", "joy", "great", "wonderful", "love", "excited", "grateful", "awesome", "glad", "delight"],
    "sadness": ["sad", "unhappy", "depressed", "miss", "loss", "grief", "lonely", "hurt", "cry", "sorrow"],
    "anger": ["angry", "furious", "rage", "hate", "mad", "frustrated", "annoyed", "outraged", "bitter"],
    "fear": ["afraid", "scared", "anxious", "worried", "nervous", "terror", "dread", "panic", "uneasy"],
    "surprise": ["surprised", "shocked", "unexpected", "amazed", "astonished", "sudden", "wow"],
    "disgust": ["disgusting", "horrible", "gross", "awful", "repulsive", "revolting", "nauseating"],
    "neutral": [],
}


def init_emotion_classifier() -> None:
    """Try to load the HuggingFace classifier. Called at app startup."""
    global _classifier, _engine
    if _classifier is not None:
        return
    try:
        from transformers import pipeline
        logger.info("Loading emotion classifier: j-hartmann/emotion-english-distilroberta-base")
        _classifier = pipeline(
            "text-classification",
            model="j-hartmann/emotion-english-distilroberta-base",
            top_k=None,
            device=-1,
        )
        _engine = "hf"
        logger.info("Emotion classifier ready")
    except Exception as e:
        logger.warning(f"HuggingFace emotion classifier unavailable: {e}")
        logger.info("Falling back to keyword heuristic emotion classifier")


def get_emotion_engine() -> str:
    return _engine


def classify_paragraph(text: str, ollama_url: str = "", ollama_model: str = "") -> dict:
    """Return {emotion_label, emotion_scores} for a single text block."""
    if not text.strip():
        return {"emotion_label": "", "emotion_scores": {}}

    if _classifier is not None:
        try:
            results = _classifier(text[:512])
            if results and results[0]:
                scores = {r["label"].lower(): round(r["score"], 4) for r in results[0]}
                top = max(scores, key=scores.get)
                return {"emotion_label": top, "emotion_scores": scores}
        except Exception as e:
            logger.error(f"HF classify failed: {e}")

    if ollama_url:
        result = _ollama_classify(text, ollama_url, ollama_model)
        if result:
            return result

    return _keyword_classify(text)


def _ollama_classify(text: str, ollama_url: str, ollama_model: str) -> dict | None:
    """Use Ollama to classify emotion when HuggingFace is unavailable."""
    prompt = (
        "Classify the emotional content of this journal text. "
        "Return ONLY a JSON object with these exact keys and float values 0.0-1.0: "
        "{\"joy\": 0.0, \"sadness\": 0.0, \"anger\": 0.0, \"fear\": 0.0, "
        "\"disgust\": 0.0, \"neutral\": 0.0, \"surprise\": 0.0}. "
        "Values must sum to 1.0. Text: \"" + text[:300] + "\""
    )
    try:
        import httpx, json as _json
        r = httpx.post(
            f"{ollama_url}/api/generate",
            json={"model": ollama_model, "prompt": prompt, "stream": False},
            timeout=8.0,
        )
        if r.status_code != 200:
            return None
        raw = r.json().get("response", "")
        # Extract JSON from response
        start, end = raw.find("{"), raw.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        scores = _json.loads(raw[start:end])
        scores = {k: round(float(v), 4) for k, v in scores.items() if k in _KEYWORDS or k == "neutral"}
        if not scores:
            return None
        top = max(scores, key=scores.get)
        return {"emotion_label": top, "emotion_scores": scores}
    except Exception as e:
        logger.debug(f"Ollama emotion classify failed: {e}")
        return None


def classify_paragraphs(text: str, ollama_url: str = "", ollama_model: str = "") -> list[dict]:
    """Split text into paragraphs and classify each. Returns list of para dicts."""
    raw_paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not raw_paras and text.strip():
        raw_paras = [text.strip()]
    return [{"text": p, **classify_paragraph(p, ollama_url, ollama_model)} for p in raw_paras]


def synthesize_overall_emotion(
    paragraphs: list[dict],
    vad: Optional[dict] = None,
    face_emotion: Optional[str] = None,
) -> str:
    """Human-readable overall emotion from paragraph scores + optional VAD + face."""
    parts: list[str] = []

    if paragraphs:
        agg: dict[str, float] = {}
        count = 0
        for para in paragraphs:
            scores = para.get("emotion_scores", {})
            if scores:
                count += 1
                for k, v in scores.items():
                    agg[k] = agg.get(k, 0.0) + v
        if agg and count:
            averaged = {k: v / count for k, v in agg.items()}
            top2 = sorted(averaged.items(), key=lambda x: -x[1])[:2]
            emotion_parts = [_LABELS.get(k, k) for k, v in top2 if v > 0.1]
            if emotion_parts:
                parts.append(" and ".join(emotion_parts))

    if vad:
        v_val = vad.get("V", 0.0)
        a_val = vad.get("A", 0.0)
        tone = _vad_label(v_val, a_val)
        if tone and tone != "neutral":
            parts.append(f"voiced with {tone} energy")

    if face_emotion and face_emotion not in ("", "no face detected", "none"):
        parts.append(f"facial expression: {face_emotion}")

    return "; ".join(parts) if parts else "neutral"


def _vad_label(V: float, A: float) -> str:
    if A < 0.2:
        return "quiet"
    if A > 0.65:
        return "intense" if V >= 0 else "agitated"
    if V > 0.3:
        return "warm"
    if V < -0.3:
        return "tense"
    return "neutral"


def _keyword_classify(text: str) -> dict:
    lower = text.lower()
    scores: dict[str, float] = {k: 0.0 for k in _KEYWORDS}
    scores["neutral"] = 0.30

    for emotion, words in _KEYWORDS.items():
        for word in words:
            if word in lower:
                scores[emotion] = min(1.0, scores[emotion] + 0.20)

    total = sum(scores.values()) or 1.0
    normalized = {k: round(v / total, 4) for k, v in scores.items()}
    top = max(normalized, key=normalized.get)
    return {"emotion_label": top, "emotion_scores": normalized}
