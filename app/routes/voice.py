"""
Voice routes:
  WebSocket /ws/record  — live recording with VAD + streaming transcript
  POST /voice/upload    — transcribe an uploaded audio file
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Cookie, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from app.dependencies import SESSION_COOKIE
from app.services import session as session_svc
from app.services.stt import get_active_engine, transcribe_audio_file, transcribe_pcm
from app.services.tone import ToneEstimator
from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()

# PCM constants (Int16, 16kHz mono, 1000 samples = 62.5ms per frame)
SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2
FRAME_SAMPLES = 1000
FRAME_BYTES = FRAME_SAMPLES * BYTES_PER_SAMPLE  # 2000 bytes = 62.5ms

# Silence detection: 32 frames × 62.5ms = 2.0s of quiet triggers transcription
SILENCE_RMS_THRESHOLD = 0.015
SILENCE_FRAMES_REQUIRED = 32

# Don't transcribe tiny buffers (less than 1s of audio)
MIN_TRANSCRIBE_BYTES = SAMPLE_RATE * BYTES_PER_SAMPLE  # 32000 bytes

# How often to send VAD updates (every N frames)
VAD_INTERVAL_FRAMES = 8


def _frame_rms(pcm_bytes: bytes) -> float:
    """RMS amplitude of a raw int16 PCM frame, normalized to [0,1]."""
    import numpy as np
    if not pcm_bytes:
        return 0.0
    a = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    return float(np.sqrt(np.mean(a * a)))


def _vad_label(V: float, A: float, D: float) -> str:
    """Map (V,A,D) to a human-readable label."""
    if A < 0.25:
        return "calm"
    if A > 0.65:
        return "energetic" if V >= 0 else "agitated"
    if V > 0.3:
        return "positive"
    if V < -0.3:
        return "tense"
    return "neutral"


async def _auth_ws(websocket: WebSocket) -> Optional[object]:
    """Return session data from the session cookie in the WS handshake, or None."""
    cookie_header = websocket.cookies.get(SESSION_COOKIE)
    if not cookie_header:
        return None
    settings = get_settings()
    max_idle = settings.auto_lock_minutes * 60
    return session_svc.get_session(cookie_header, max_idle_seconds=max_idle)


@router.websocket("/ws/record")
async def ws_record(websocket: WebSocket):
    session = await _auth_ws(websocket)
    if session is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()

    tone = ToneEstimator(sr=SAMPLE_RATE)
    audio_buffer: bytearray = bytearray()
    silence_frames = 0
    frame_count = 0
    transcribing = False

    # VAD accumulation for session summary
    vad_v_sum = 0.0
    vad_a_sum = 0.0
    vad_d_sum = 0.0
    vad_count = 0

    # Immediately tell client which STT engine is active
    await websocket.send_text(
        json.dumps({"type": "stt_engine", "engine": get_active_engine()})
    )

    async def run_transcription(pcm_bytes: bytes) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, transcribe_pcm, bytes(pcm_bytes), SAMPLE_RATE)

    try:
        while True:
            msg = await websocket.receive()

            # Client sends {"type": "stop"} as text to end recording
            if msg.get("type") == "websocket.receive" and msg.get("text"):
                try:
                    data = json.loads(msg["text"])
                except ValueError:
                    data = {}
                if data.get("type") == "stop":
                    # Flush remaining buffer
                    if len(audio_buffer) >= MIN_TRANSCRIBE_BYTES and not transcribing:
                        transcribing = True
                        text = await run_transcription(audio_buffer)
                        if text:
                            await websocket.send_text(
                                json.dumps({"type": "final", "text": text})
                            )
                        transcribing = False
                    # Send session-average VAD summary
                    if vad_count > 0:
                        await websocket.send_text(
                            json.dumps({
                                "type": "vad_summary",
                                "V": round(vad_v_sum / vad_count, 3),
                                "A": round(vad_a_sum / vad_count, 3),
                                "D": round(vad_d_sum / vad_count, 3),
                            })
                        )
                    await websocket.send_text(json.dumps({"type": "done"}))
                    break
                continue

            # Binary frame: raw Int16 PCM
            if msg.get("type") == "websocket.receive" and msg.get("bytes"):
                frame = msg["bytes"]
                audio_buffer.extend(frame)
                frame_count += 1

                rms = _frame_rms(frame)
                if rms < SILENCE_RMS_THRESHOLD:
                    silence_frames += 1
                else:
                    silence_frames = 0

                # VAD update every N frames
                if frame_count % VAD_INTERVAL_FRAMES == 0:
                    V, A, D = tone.estimate_vad(frame)
                    vad_v_sum += V
                    vad_a_sum += A
                    vad_d_sum += D
                    vad_count += 1
                    await websocket.send_text(
                        json.dumps({
                            "type": "vad",
                            "V": round(V, 3),
                            "A": round(A, 3),
                            "D": round(D, 3),
                            "label": _vad_label(V, A, D),
                        })
                    )

                # Auto-transcribe on 2s of silence with enough buffered audio
                if (
                    silence_frames >= SILENCE_FRAMES_REQUIRED
                    and len(audio_buffer) >= MIN_TRANSCRIBE_BYTES
                    and not transcribing
                ):
                    transcribing = True
                    pcm_snapshot = bytes(audio_buffer)
                    audio_buffer.clear()
                    silence_frames = 0
                    tone.reset()

                    text = await run_transcription(pcm_snapshot)
                    if text:
                        await websocket.send_text(
                            json.dumps({"type": "partial", "text": text})
                        )
                    transcribing = False

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket /ws/record error: {e}")
        try:
            await websocket.send_text(json.dumps({"type": "error", "detail": str(e)}))
        except Exception:
            pass


@router.post("/voice/upload")
async def voice_upload(file: UploadFile):
    """
    Transcribe an uploaded audio file (WebM, MP3, WAV, OGG).
    Returns {"text": "...", "engine": "whisper|vosk|none"}.
    """
    try:
        file_bytes = await file.read()
        filename = file.filename or "audio"

        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(
            None, transcribe_audio_file, file_bytes, filename
        )
        return JSONResponse({"text": text, "engine": get_active_engine()})
    except Exception as e:
        logger.error(f"voice/upload error: {e}")
        return JSONResponse({"text": "", "engine": "none", "error": str(e)}, status_code=500)
