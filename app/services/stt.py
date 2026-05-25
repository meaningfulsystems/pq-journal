"""
Speech-to-text service: faster-whisper (primary) + Vosk (fallback).

Both are optional; if neither is available, transcription returns empty string.
Model loading is lazy and cached after first use.
"""
from __future__ import annotations

import io
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_whisper_model = None
_vosk_model = None
_active_engine: str = "none"


def _try_load_whisper(model_name: str) -> bool:
    global _whisper_model, _active_engine
    if _whisper_model is not None:
        return True
    try:
        from faster_whisper import WhisperModel
        logger.info(f"Loading faster-whisper model: {model_name}")
        _whisper_model = WhisperModel(model_name, device="auto", compute_type="int8")
        _active_engine = "whisper"
        logger.info("faster-whisper ready")
        return True
    except Exception as e:
        logger.warning(f"faster-whisper unavailable: {e}")
        return False


def _try_load_vosk(model_dir: Optional[Path]) -> bool:
    global _vosk_model, _active_engine
    if _vosk_model is not None:
        return True
    if not model_dir or not model_dir.exists():
        return False
    try:
        from vosk import Model, SetLogLevel
        SetLogLevel(-1)
        logger.info(f"Loading Vosk model from: {model_dir}")
        _vosk_model = Model(str(model_dir))
        _active_engine = "vosk"
        logger.info("Vosk ready")
        return True
    except Exception as e:
        logger.warning(f"Vosk unavailable: {e}")
        return False


def init_stt(model_name: str = "large-v3-turbo", vosk_model_dir: Optional[Path] = None) -> None:
    """Try to load STT engines. Called at app startup."""
    if not _try_load_whisper(model_name):
        _try_load_vosk(vosk_model_dir)


def get_active_engine() -> str:
    return _active_engine


def transcribe_pcm(pcm_bytes: bytes, sample_rate: int = 16000) -> str:
    """
    Transcribe raw 16-bit mono PCM bytes. Returns empty string if no engine available.
    Runs synchronously — call in a thread pool executor from async code.
    """
    if not pcm_bytes:
        return ""

    if _whisper_model is not None:
        return _transcribe_whisper(pcm_bytes, sample_rate)
    if _vosk_model is not None:
        return _transcribe_vosk(pcm_bytes, sample_rate)
    return ""


_HALLUCINATIONS = {
    "thank you.", "thank you", "thanks.", "thanks", "thank you for watching.",
    "thanks for watching.", "you.", "you", "bye.", "bye", "goodbye.", "goodbye",
    "okay.", "okay", "ok.", "ok", "uh.", "um.", "hmm.", "[music]", "[applause]",
    "subtitles by", "transcript by",
}


def _filter_segments(segments) -> str:
    parts = []
    for seg in segments:
        # Drop segments where whisper itself isn't confident there's speech
        if getattr(seg, "no_speech_prob", 0.0) > 0.6:
            continue
        text = seg.text.strip()
        if not text:
            continue
        # Drop known hallucination phrases
        if text.lower().rstrip(".!?,") in _HALLUCINATIONS or text.lower() in _HALLUCINATIONS:
            continue
        parts.append(text)
    return " ".join(parts).strip()


def _transcribe_whisper(pcm_bytes: bytes, sample_rate: int) -> str:
    import numpy as np
    audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    segments, _ = _whisper_model.transcribe(
        audio,
        language=None,
        condition_on_previous_text=False,
        no_speech_threshold=0.5,
        vad_filter=True,
        vad_parameters={
            "threshold": 0.3,
            "min_silence_duration_ms": 500,
            "speech_pad_ms": 400,
        },
    )
    return _filter_segments(segments)


def _transcribe_vosk(pcm_bytes: bytes, sample_rate: int) -> str:
    import json
    from vosk import KaldiRecognizer
    rec = KaldiRecognizer(_vosk_model, sample_rate)
    rec.SetWords(True)
    chunk_size = 4000
    for i in range(0, len(pcm_bytes), chunk_size):
        rec.AcceptWaveform(pcm_bytes[i : i + chunk_size])
    result = json.loads(rec.FinalResult())
    return result.get("text", "").strip()


def transcribe_audio_file(file_bytes: bytes, filename: str = "audio") -> str:
    """
    Transcribe an uploaded audio file (WebM, MP3, WAV, etc.).
    Uses soundfile to convert to PCM first; falls back to writing a temp file for whisper.
    """
    if _whisper_model is not None:
        # faster-whisper can accept raw file bytes via a temp file
        suffix = Path(filename).suffix or ".webm"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        try:
            segments, _ = _whisper_model.transcribe(
                tmp_path,
                language=None,
                vad_filter=True,
            )
            return " ".join(seg.text.strip() for seg in segments).strip()
        finally:
            os.unlink(tmp_path)

    # Vosk path: decode with soundfile → PCM
    if _vosk_model is not None:
        try:
            import numpy as np
            import soundfile as sf
            audio, sr = sf.read(io.BytesIO(file_bytes), dtype="int16", always_2d=False)
            if audio.ndim > 1:
                audio = audio[:, 0]
            return _transcribe_vosk(audio.tobytes(), sr)
        except Exception as e:
            logger.error(f"Audio file decode failed: {e}")

    return ""
