"""
ToneEstimator — CPU-light VAD + Valence/Arousal/Dominance from raw PCM.

Ported from archive ToneEstimator (lines 1304–1413).
Removed PyQt6 / webrtcvad dependencies; kept pure numpy/stdlib.
"""
from __future__ import annotations

import math
from array import array
from collections import deque
from typing import Tuple

import numpy as np

try:
    import webrtcvad as _webrtcvad
except Exception:
    _webrtcvad = None


class ToneEstimator:
    """
    Returns (V, A, D): Valence∈[-1,1], Arousal∈[0,1], Dominance∈[-1,1]
    from raw 16-bit mono PCM bytes.

    Features: RMS dB, spectral centroid/tilt (1kHz split), spectral flux.
    Session calibration via running percentile scaling (600-frame windows).
    WebRTC VAD gating when webrtcvad is installed (optional).
    """

    def __init__(self, sr: int = 16000):
        self.sr = sr
        self._vad = _webrtcvad.Vad(2) if _webrtcvad else None
        self._rms_db_hist: deque = deque(maxlen=600)
        self._centroid_hist: deque = deque(maxlen=600)
        self._flux_hist: deque = deque(maxlen=600)
        self._prev_mag: np.ndarray | None = None

    def _is_speech(self, pcm_bytes: bytes) -> bool:
        if not self._vad:
            return True
        frame_ms = 20
        bytes_per_ms = int(self.sr / 1000) * 2
        if len(pcm_bytes) < frame_ms * bytes_per_ms:
            return True
        frame = pcm_bytes[: frame_ms * bytes_per_ms]
        try:
            return self._vad.is_speech(frame, self.sr)
        except Exception:
            return True

    def _fft_features(self, pcm: array) -> Tuple[float, float, float]:
        x = np.asarray(pcm, dtype=np.float32) / 32768.0
        if x.size == 0:
            return 0.0, 0.0, 0.0
        w = np.hanning(x.size).astype(np.float32)
        X = np.fft.rfft(x * w)
        mag = np.abs(X) + 1e-9

        freqs = np.fft.rfftfreq(x.size, d=1.0 / self.sr)
        centroid = float(np.sum(freqs * mag) / np.sum(mag))

        split = max(1, int(1000 * x.size / self.sr))
        low = float(np.sum(mag[:split]))
        high = float(np.sum(mag[split:]))
        tilt = float((low - high) / (low + high + 1e-6))

        if self._prev_mag is None or self._prev_mag.shape != mag.shape:
            flux = 0.0
        else:
            diff = mag - self._prev_mag
            flux = float(np.sum(np.clip(diff, 0, None)) / (mag.size + 1e-6))
        self._prev_mag = mag
        return centroid, tilt, flux

    def estimate_vad(self, pcm_bytes: bytes) -> Tuple[float, float, float]:
        """Return (V, A, D) for this audio frame."""
        a: array = array("h")
        a.frombytes(pcm_bytes)

        if not self._is_speech(pcm_bytes) or len(a) == 0:
            return 0.0, 0.05, -0.2

        x = np.asarray(a, dtype=np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(x * x)) + 1e-12)
        db = 20.0 * math.log10(rms + 1e-12)

        centroid, tilt, flux = self._fft_features(a)

        self._rms_db_hist.append(db)
        self._centroid_hist.append(centroid)
        self._flux_hist.append(flux)

        def _pct_scaled(val: float, hist: deque, lo_q: float = 0.1, hi_q: float = 0.9) -> float:
            if len(hist) < 10:
                return 0.35
            arr = np.fromiter(hist, dtype=np.float32)
            lo = float(np.quantile(arr, lo_q))
            hi = float(np.quantile(arr, hi_q))
            if hi <= lo:
                return 0.35
            return float(max(0.0, min(1.0, (val - lo) / (hi - lo))))

        A_rms = _pct_scaled(db, self._rms_db_hist)
        A_flux = _pct_scaled(flux, self._flux_hist)
        A = max(0.0, min(1.0, 0.60 * A_rms + 0.10 * A_flux))

        V = max(-1.0, min(1.0, 0.60 * tilt + 0.10 * (2 * A_flux - 1.0)))

        Cn = _pct_scaled(centroid, self._centroid_hist)
        D = max(-1.0, min(1.0, (A * 1.00 - 0.40) + 0.15 * (2 * Cn - 1.0)))

        return float(V), float(A), float(D)

    def reset(self) -> None:
        self._rms_db_hist.clear()
        self._centroid_hist.clear()
        self._flux_hist.clear()
        self._prev_mag = None
