"""
Facial expression recognition from JPEG frames using PyTorch ResNet50.
Disabled gracefully when model weights or dependencies are missing.

Expected weights: ~/.pq-journal/fer_resnet50.pth
7 classes: angry, disgust, fear, happy, neutral, sad, surprise
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

EMOTIONS = ["angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"]
WEIGHTS_PATH = Path.home() / ".pq-journal" / "fer_resnet50.pth"

_model = None
_transform = None
_face_cascade = None
_engine: str = "none"


def init_fer() -> None:
    """Attempt to load FER model. Silently disabled if unavailable."""
    global _model, _transform, _face_cascade, _engine
    if _model is not None:
        return

    if not WEIGHTS_PATH.exists():
        logger.info(f"FER weights not found at {WEIGHTS_PATH}; facial emotion detection disabled")
        return

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
        logger.info("FER model loaded successfully")

    except ImportError as e:
        logger.info(f"FER dependencies not installed ({e}); facial emotion disabled")
    except Exception as e:
        logger.warning(f"FER model load failed: {e}")


def get_fer_engine() -> str:
    return _engine


def classify_frame(jpeg_bytes: bytes) -> Optional[dict]:
    """
    Classify emotion from a JPEG frame.
    Returns {emotion_label, scores} or None if engine not available.
    """
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
        logger.error(f"FER classify_frame error: {e}")
        return None
