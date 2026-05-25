"""
Facial expression recognition from JPEG frames.

Two backends, tried in order:
  1. Custom ResNet50 weights at ~/.pq-journal/fer_resnet50.pth  (highest accuracy)
  2. DeepFace  (auto-downloads ~6 MB emotion weights on first use, no manual setup)

Disabled gracefully when both are unavailable.
7 classes: angry, disgust, fear, happy, neutral, sad, surprise
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

# Force legacy Keras for TensorFlow 2.16+ compatibility with DeepFace
os.environ["TF_USE_LEGACY_KERAS"] = "1"

logger = logging.getLogger(__name__)

EMOTIONS = ["angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"]
WEIGHTS_PATH = Path.home() / ".pq-journal" / "fer_resnet50.pth"

_model = None
_transform = None
_face_cascade = None
_engine: str = "none"
_deepface_ready: bool = False


def init_fer() -> None:
    """Attempt to load FER model. Falls back to DeepFace. Silently disabled if neither available."""
    global _model, _transform, _face_cascade, _engine, _deepface_ready

    if _engine != "none":
        return  # already initialised

    # ── Backend 1: custom ResNet50 weights ───────────────────────────────────
    if WEIGHTS_PATH.exists():
        try:
            import torch
            import torch.nn as nn
            import torchvision.models as models
            import torchvision.transforms as transforms
            import cv2

            m = models.resnet50(weights=None)
            m.fc = nn.Linear(m.fc.in_features, len(EMOTIONS))
            m.load_state_dict(torch.load(str(WEIGHTS_PATH), map_location="cpu"))
            m.eval()
            _model = m

            _transform = transforms.Compose([
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ])

            _face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )

            _engine = "resnet50_fer"
            logger.info("FER model loaded successfully (ResNet50 custom weights)")
            return

        except ImportError as e:
            logger.info(f"ResNet50 FER dependencies not installed ({e}); trying DeepFace")
        except Exception as e:
            logger.warning(f"ResNet50 FER model load failed: {e}; trying DeepFace")
    else:
        logger.info(f"FER weights not found at {WEIGHTS_PATH}; trying DeepFace fallback")

    # ── Backend 2: DeepFace (auto-downloads weights) ─────────────────────────
    try:
        from deepface import DeepFace  # noqa: F401 — just test import
        _deepface_ready = True
        _engine = "deepface"
        logger.info("FER engine: DeepFace (weights will be downloaded on first frame)")
    except ImportError:
        logger.info("DeepFace not installed; facial emotion detection disabled. "
                    "Install with: pip install deepface")


def get_fer_engine() -> str:
    return _engine


def classify_frame(jpeg_bytes: bytes) -> Optional[dict]:
    """
    Classify emotion from a JPEG frame.
    Returns {emotion_label, scores} or None if engine not available.
    """
    if _engine == "resnet50_fer":
        return _classify_resnet50(jpeg_bytes)
    if _engine == "deepface":
        return _classify_deepface(jpeg_bytes)
    return None


def _classify_resnet50(jpeg_bytes: bytes) -> Optional[dict]:
    if _model is None:
        return None
    try:
        import cv2
        import numpy as np
        import torch
        from PIL import Image

        arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        img_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img_bgr is None:
            return None

        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        faces = _face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(48, 48)
        )

        if len(faces) == 0:
            return {"emotion_label": "no face", "scores": {}}

        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        face_bgr = img_bgr[y : y + h, x : x + w]
        face_rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(face_rgb)

        tensor = _transform(pil_img).unsqueeze(0)
        with torch.no_grad():
            probs = torch.softmax(_model(tensor), dim=1)[0].tolist()

        scores = {EMOTIONS[i]: round(probs[i], 4) for i in range(len(EMOTIONS))}
        top = max(scores, key=scores.get)
        return {"emotion_label": top, "scores": scores}

    except Exception as e:
        logger.error(f"ResNet50 classify_frame error: {e}")
        return None


def _classify_deepface(jpeg_bytes: bytes) -> Optional[dict]:
    try:
        from deepface import DeepFace
        import cv2
        import numpy as np

        arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        img_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img_bgr is None:
            return None

        results = DeepFace.analyze(
            img_path=img_bgr,
            actions=["emotion"],
            enforce_detection=False,
            silent=True,
        )

        if not results:
            return {"emotion_label": "no face", "scores": {}}

        face = results[0]
        raw_scores = face.get("emotion", {})
        # DeepFace returns percentages (0-100) as np.float32; convert to plain float for JSON
        total = float(sum(raw_scores.values())) or 1.0
        scores = {k: round(float(v) / total, 4) for k, v in raw_scores.items()}
        dominant = face.get("dominant_emotion", max(scores, key=scores.get))
        return {"emotion_label": dominant, "scores": scores}

    except Exception as e:
        logger.error(f"DeepFace classify_frame error: {e}")
        return None
