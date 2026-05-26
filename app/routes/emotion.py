"""
Emotion analysis routes.
  POST /emotion/analyze       — text + VAD + face → per-paragraph emotion + overall
  POST /emotion/video/frame   — JPEG frame → face emotion label
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import get_settings
from app.dependencies import require_unlocked
from app.services.session import SessionData
from app.services import emotion_text as text_svc
from app.services import emotion_video as video_svc
from app.services import llm as llm_svc

from app.templating import templates

router = APIRouter(prefix="/emotion", tags=["emotion"])
logger = logging.getLogger(__name__)


@router.post("/analyze", response_class=HTMLResponse)
async def analyze_text(
    request: Request,
    body: str = Form(default=""),
    vad_summary: str = Form(default="{}"),
    face_emotion: str = Form(default=""),
    session: SessionData = Depends(require_unlocked),
):
    """
    Classify emotions in journal text. Returns an HTML partial that replaces
    #emotion-panel and OOB-swaps the hidden emotion fields.
    """
    if not body.strip():
        return templates.TemplateResponse(
            "components/emotion_panel.html",
            {
                "request": request,
                "paragraphs": [],
                "overall": "",
                "vad": {},
                "engine": text_svc.get_emotion_engine(),
                "empty": True,
            },
        )

    loop = asyncio.get_event_loop()
    cfg = get_settings()

    # Classify paragraphs (runs in thread pool — HF model is CPU-bound)
    paragraphs = await loop.run_in_executor(
        None, text_svc.classify_paragraphs, body, cfg.ollama_url, cfg.ollama_model
    )

    try:
        vad = json.loads(vad_summary) if vad_summary.strip() else {}
    except Exception:
        vad = {}

    face_str = face_emotion.strip() or None

    # Attach session VAD to each paragraph (session-level, not per-para)
    if vad:
        for p in paragraphs:
            p["vad"] = vad
    if face_str and face_str not in ("no face", "no face detected"):
        for p in paragraphs:
            p["face_emotion"] = face_str

    # Build overall from text + VAD + face (rule-based)
    overall_rule = text_svc.synthesize_overall_emotion(paragraphs, vad, face_str)

    # Optionally upgrade with LLM synthesis (non-blocking, short timeout)
    overall = overall_rule
    try:
        llm_result = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                llm_svc.synthesize_emotion,
                paragraphs,
                vad or None,
                face_str,
                cfg.ollama_url,
                cfg.ollama_model,
            ),
            timeout=6.0,
        )
        if llm_result and llm_result.strip():
            overall = llm_result
    except (asyncio.TimeoutError, Exception):
        pass

    return templates.TemplateResponse(
        "components/emotion_panel.html",
        {
            "request": request,
            "paragraphs": paragraphs,
            "overall": overall,
            "vad": vad,
            "engine": text_svc.get_emotion_engine(),
            "empty": False,
        },
    )


@router.post("/live_summary")
async def live_emotion_summary(
    request: Request,
    vad_v: float = Form(default=0.0),
    vad_a: float = Form(default=0.0),
    vad_d: float = Form(default=0.0),
    face_emotion: str = Form(default=""),
    transcript: str = Form(default=""),
    session: SessionData = Depends(require_unlocked),
):
    """Generate a rich emotional summary from accumulated VAD + face data."""
    cfg = get_settings()
    loop = asyncio.get_event_loop()
    source = "llm"
    try:
        summary = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                llm_svc.synthesize_live_emotion,
                vad_v, vad_a, vad_d,
                face_emotion or None,
                cfg.ollama_url,
                cfg.ollama_model,
                transcript,
            ),
            timeout=10.0,
        )
        # Detect if LLM fell back to rule-based
        fallback_check = llm_svc._live_fallback(vad_v, vad_a, vad_d, face_emotion or None)
        if summary == fallback_check:
            source = "fallback"
    except (asyncio.TimeoutError, Exception) as e:
        logger.warning(f"live_summary error: {e}")
        summary = llm_svc._live_fallback(vad_v, vad_a, vad_d, face_emotion or None)
        source = "fallback"
    return JSONResponse({"summary": summary, "source": source})


@router.post("/video/frame")
async def video_frame(
    file: UploadFile,
    session: SessionData = Depends(require_unlocked),
):
    """Classify facial emotion from an uploaded JPEG frame."""
    if video_svc.get_fer_engine() == "none":
        return JSONResponse({"emotion_label": "", "scores": {}, "engine": "none"})

    try:
        jpeg_bytes = await file.read()
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, video_svc.classify_frame, jpeg_bytes)
        if result is None:
            return JSONResponse({"emotion_label": "", "scores": {}, "engine": "none"})
        return JSONResponse({**result, "engine": video_svc.get_fer_engine()})
    except Exception as e:
        logger.error(f"/emotion/video/frame error: {e}")
        return JSONResponse(
            {"emotion_label": "", "scores": {}, "engine": "none", "error": str(e)},
            status_code=500,
        )
