# PQ Journal Web App — Architecture Document

**Status:** Pre-planning  
**Based on:** Archive `pq-journal-improved-20251127-1435.py` (3,917 lines, PyQt6 desktop)  
**Author:** Generated for Andrew Fried / Meaningful Systems, LLC

---

## What the Archive Actually Proves

Before planning anything new, it's worth being honest about what the existing code tells us.

**What works and should be kept:**
- The `ToneEstimator` class (spectral centroid, RMS dB, flux → VAD) is well-tuned and runs on CPU with no model download. Reuse it server-side.
- The `EmotionSummarizer` + emotion matrix JSON pattern is clever and editable without code changes. Keep it.
- ML-KEM encapsulation via `oqs` works; the encrypt/decrypt blob format is clean and auditable.
- The emotion state machine (IDLE → LISTENING → WAITING_MODEL → READY_NEXT) is the right mental model for a streaming journaling loop. Adapt it.
- Per-paragraph emotion timing and the `EmotionQueueWorker` pattern are worth keeping, even if the LLM changes.

**What the archive reveals as pain points:**
- 3,917 lines in one file. The web app must not repeat this.
- The Llama auto-start logic is deeply fragile (binary path search, 60-second polling loop, model name guessing). This needs a clean design.
- Vosk produces acceptable-but-rough transcripts. The app clearly wants better.
- The PyQt6 video widget forces everything onto the same thread as the GUI. A web browser handles video natively — this whole problem disappears.
- There is no concept of "entries as individual files" — the existing app writes a single monolithic notebook JSON. The proposed design changes this.

---

## Proposed Architecture

### Philosophy

The app should be **local-first, privacy-preserving, and incrementally adoptable**. Every feature should work at a degraded-but-useful level without optional dependencies. A user without a webcam should still be able to journal. A user without a GPU should still get transcription. Encryption is not optional.

### Layer Overview

```
Browser (HTMX + Tailwind + WebAudio API)
    │
    │  HTTP/WebSocket (localhost only, bound to 127.0.0.1)
    ▼
FastAPI app (Python 3.11+)
    ├── routes/
    │     ├── journal.py      — entry CRUD, search, export
    │     ├── voice.py        — upload + streaming transcription
    │     ├── emotion.py      — multi-modal emotion pipeline
    │     └── auth.py         — session unlock, key management
    │
    ├── services/
    │     ├── crypto.py       — PQC encrypt/decrypt (liboqs + AESGCM)
    │     ├── stt.py          — speech-to-text (faster-whisper or Vosk)
    │     ├── tone.py         — audio VAD → valence/arousal/dominance
    │     ├── emotion_text.py — per-paragraph HuggingFace classifier
    │     ├── emotion_video.py— webcam FER (PyTorch ResNet50 or deepface)
    │     ├── llm.py          — optional local LLM emotion synthesis
    │     └── key_store.py    — USB key detection and management
    │
    ├── models/
    │     └── db.py           — SQLAlchemy models (entry metadata only)
    │
    └── templates/            — Jinja2 + HTMX
          ├── layout.html
          ├── journal_list.html
          ├── entry_editor.html
          └── components/
```

### Data Flow: Voice Entry Creation

```
1. User clicks Record
2. Browser captures audio via MediaRecorder API
3. Audio chunks → POST /voice/stream (WebSocket or SSE)
4. Server: faster-whisper transcribes chunk → partial text
5. Server: ToneEstimator extracts VAD from raw PCM
6. Browser: simultaneously streams webcam JPEG frames → POST /emotion/video/frame
7. Server: FER model extracts facial emotion per frame
8. On silence pause (>2s): server runs per-paragraph emotion classifier
9. Optional: LLM synthesizes multi-modal emotion phrase
10. HTMX swaps emotion annotation into paragraph display
11. User reviews/edits entry + emotion annotations
12. User clicks Save → entry serialized → encrypted → written to ~/MeaningfulJournal/entries/<uuid>.pqj
13. Metadata (title, date, tags, emotion summary) written to SQLite
```

### File Layout (Disk)

```
~/MeaningfulJournal/
    entries/
        <uuid>.pqj       — encrypted JSON blob per entry
    .db
        journal.sqlite   — metadata index (never contains plaintext body)
```

Entry `.pqj` format (encrypted):

```json
{
  "version": 2,
  "alg": "ML-KEM-1024+AES-256-GCM",
  "kem_ct": "<base64>",
  "nonce": "<base64>",
  "tag": "<base64>",
  "ct": "<base64>",
  "sig": "<base64 ML-DSA signature over kem_ct+nonce+tag+ct>"
}
```

Decrypted plaintext is:

```json
{
  "id": "<uuid>",
  "title": "...",
  "created": "ISO8601",
  "tags": ["..."],
  "paragraphs": [
    {
      "text": "...",
      "emotion_label": "calm and reflective",
      "emotion_scores": { "joy": 0.1, "sadness": 0.05, ... },
      "vad": { "V": 0.2, "A": 0.3, "D": 0.1 },
      "face_emotion": { "happy": 0.6, "neutral": 0.3 }
    }
  ],
  "overall_emotion": "..."
}
```

### Encryption Scheme (Corrected from Grok)

Grok mentioned ML-KEM + ML-DSA + SLH-DSA without specifying what each does. Here is a precise design:

| Algorithm | Role | Justification |
|-----------|------|---------------|
| ML-KEM-1024 | Key encapsulation for AES-256-GCM entry encryption | NIST FIPS 203 finalized |
| AES-256-GCM | Symmetric encryption of entry plaintext | Battle-tested, fast |
| ML-DSA-65 | Signs each `.pqj` file (authenticates writes) | NIST FIPS 204 finalized |
| X25519 (optional) | Classical hybrid component | Defense-in-depth against PQC break |
| SLH-DSA | Not recommended for this app | Too slow (~seconds per sign), signature size ~50KB. Only relevant if signing is done offline for archival. |

The master key structure on the USB drive:

```
/usb/
    meaningful-journal/
        ml_kem.pub      — ML-KEM-1024 public key
        ml_kem.priv     — ML-KEM-1024 private key (encrypted with passphrase)
        ml_dsa.pub      — ML-DSA-65 public key
        ml_dsa.priv     — ML-DSA-65 private key (encrypted with passphrase)
        key.json        — Key metadata and creation timestamp
```

Key files encrypted at rest with PBKDF2-HMAC-SHA256 (600,000 iterations) + AES-256-GCM before writing to USB. The passphrase never touches disk.

### Session Management

On startup:
1. App detects USB drives at `/media/<user>/` and `/run/media/<user>/`
2. User selects key directory
3. User enters passphrase → private keys decrypted into memory only
4. Session token issued (signed JWT, stored in httpOnly cookie)
5. Auto-lock after configurable inactivity (default: 15 min)
6. On lock: private key bytes zeroed in memory

### Frontend Architecture

HTMX is a reasonable choice for most of the app. However, two areas require careful thought:

**Real-time audio recording:** The browser's `MediaRecorder` API sends audio blobs. These cannot be handled by HTMX's declarative model. A thin JavaScript class (~100 lines) handles recording state, sends chunks to the server via `fetch`, and updates the HTMX-managed DOM with swapped partials. This is not a contradiction — HTMX handles navigation and CRUD; a small JS module handles the hardware interface.

**Webcam feed:** Similar to above. `getUserMedia` returns a stream. A JavaScript handler sends JPEG frames to `/emotion/video/frame` every 500ms during recording. The server responds with an emotion label that HTMX swaps into the sidebar.

Tailwind CSS via CDN (play CDN) is acceptable for a localhost app where there is no build toolchain. If the user wants a production build, `npm run build` can be added later.

### STT Engine

The existing app uses Vosk (offline, fast, ~1GB model, mediocre accuracy). Grok proposes faster-whisper large-v3.

Reality check on faster-whisper large-v3:
- Model size: ~6GB download
- Requires AVX2 or GPU for reasonable speed
- large-v3-turbo: ~1.5GB, ~4x faster than large-v3, marginally worse WER
- For a journaling app where the user speaks slowly and clearly, large-v3-turbo is a better default

Recommendation: Use faster-whisper with a configurable model name (default: `large-v3-turbo`). Fall back to Vosk if faster-whisper is not installed, so the app doesn't break for users on older hardware.

Streaming transcription: faster-whisper does not stream in real-time like Whisper.cpp does. Options:
- Buffer 10-15s of audio, transcribe, show result (simple, works)
- Use `whisper-streaming` library for true streaming (complex, but better UX)
- Use Vosk for real-time partials, re-transcribe full recording with faster-whisper on stop

### Facial Emotion Detection

Grok proposes deepface. The existing app already has a PyTorch ResNet50 approach.

deepface concerns:
- Requires TensorFlow or PyTorch as backend (extra dependency)
- Model zoo is a blackbox (downloads from github/gdrive at runtime)
- Less control over the model weights being used
- However: it's 3 lines of code vs. the existing 200-line PyTorch implementation

Recommendation: Keep the PyTorch ResNet50 approach from the archive (it's already written and tested). Wrap it in the `emotion_video.py` service. deepface can be a fallback if the user does not have the FER model weights file.

### Per-Paragraph Text Emotion

The Grok prompt specifies `j-hartmann/emotion-english-distilroberta-base`. This is a real, good model. The existing app uses a custom lexicon approach (`TextValenceEstimator`) which is less accurate.

The HuggingFace approach:
- 7 emotions: anger, disgust, fear, joy, neutral, sadness, surprise
- Model size: ~265MB download
- Runs on CPU in ~100ms per paragraph on modern hardware
- First load is slow (model download + cache)

This is a clear upgrade from the existing lexicon approach. Worth implementing.

### Local LLM for Emotion Synthesis

The existing app's Llama integration is overly complex (binary search, 60-second wait, model name guessing over HTTP). The problem is that llama.cpp's HTTP API is not stable across versions.

Better options:
1. **Ollama** — a much cleaner LLM server with stable API, auto-model-management. `ollama run tinyllama` just works.
2. **llama-cpp-python** — Python bindings, no HTTP server needed, load model directly
3. **None** — just use the HF classifier output directly; it's good enough

Recommendation: Make LLM synthesis optional. Implement a clean `llm.py` service that tries Ollama first (if running), then llama-cpp-python if installed. Fall back to the HuggingFace emotion label directly. The emotion label from the classifier is already human-readable ("This paragraph carries joy and anticipation").

### Search

Full-text search on encrypted entries requires decrypting them. Options:
1. **Decrypt at search time** — iterate all `.pqj` files, decrypt, search. Slow for large journals but private.
2. **Encrypted search index** — store a HMAC of each word in the metadata DB. Private, fast, but complex.
3. **SQLite metadata only** — search on title, tags, date, emotion label (stored unencrypted in SQLite). Fast, but misses body text.

Recommendation: Start with option 3. Title, tags, emotion labels, and date are searchable without decryption. Body search can be added later as an explicit "decrypt and search" operation with a clear privacy notice.

### Export

- **Markdown**: Straightforward — decrypt entry, format as Markdown with emotion annotations.
- **PDF**: Requires `weasyprint` or `reportlab`. Both are heavy. `weasyprint` is easier if the user has it; otherwise skip.

---

## What Grok Got Right

- FastAPI + Jinja2 + HTMX is a good fit. Not debatable for a localhost app.
- Tailwind for styling is fine.
- Individual encrypted files per entry (not monolithic notebook) is better for backup, sync, and recovery.
- liboqs-python for PQC is correct.
- USB key storage is a genuinely good privacy architecture for a threat model where the machine could be seized.
- Per-paragraph emotion statements are the most interesting feature in the spec and worth building.

## What Grok Got Wrong or Left Vague

1. **"Use ML-KEM for hybrid encryption, ML-DSA for signing, and SLH-DSA where appropriate"** — SLH-DSA is not appropriate here. It signs in ~1-5 seconds and produces 8-50KB signatures. This would make every save operation perceptibly slow.

2. **"Facial Expression Emotion: Use deepface"** — deepface downloads models at runtime from external URLs. This breaks the privacy-first architecture. Use the existing PyTorch approach from the archive.

3. **"faster-whisper large-v3"** — 6GB model is too aggressive as a default. large-v3-turbo at ~1.5GB is the right default, with user override.

4. **"Support microphone push-to-talk and audio file upload"** — These are architecturally different flows and should be designed separately. Push-to-talk via browser requires careful handling of WebSocket backpressure.

5. **"Session-based unlocking with auto-lock on inactivity"** — Left completely undesigned. This is one of the most security-critical pieces and needs a real spec.

6. **"Optional reflective / systems-thinking prompts"** — Not defined. What prompts? Where do they come from? Are they hardcoded, user-editable, or LLM-generated?

7. **"Educational tooltips about PQC algorithms"** — Low value. Could be a static page instead of cluttering the UI.

8. **Monolithic prompt implies monolithic code** — The Grok prompt will generate one large Python file, just like the archive. Enforce a modular project structure from the start.

---

## Recommended Build Sequence

Build the app in vertical slices, each usable end-to-end:

### Slice 1: Core Loop (No Audio, No Emotion)
- FastAPI + Jinja2 + HTMX + Tailwind
- USB key detection and passphrase unlock
- Key generation (ML-KEM + ML-DSA)
- Create / view / edit / delete entries (typed text only)
- Encrypt to `.pqj` per entry on save
- SQLite metadata
- Basic list + search (title/date/tags)

### Slice 2: Transcription
- Audio recording in browser (MediaRecorder)
- Upload to server
- faster-whisper transcription
- Display transcribed text in editor
- Vosk fallback

### Slice 3: Text Emotion
- Per-paragraph HuggingFace emotion classifier
- Emotion annotation display in editor
- User edit/remove annotations before save

### Slice 4: Audio Tone Emotion
- Port `ToneEstimator` from archive
- VAD from PCM during recording
- Fuse with text emotion in `EmotionSummarizer`
- Display real-time emotion indicator during recording

### Slice 5: Facial Emotion
- Browser `getUserMedia` → JPEG frames to server
- PyTorch FER on frames during recording
- Fuse into overall emotion

### Slice 6: LLM Synthesis (Optional)
- Ollama/llama-cpp-python integration
- Multi-modal emotion phrase synthesis
- Clean fallback if LLM not present

### Slice 7: Polish
- Export (Markdown, PDF)
- Systems-thinking prompts
- Meaningful Systems logo and branding
- Dark mode refinements

---

## Dependencies (Realistic List)

```
# Core
fastapi>=0.111
uvicorn[standard]>=0.29
jinja2>=3.1
python-multipart>=0.0.9
sqlalchemy>=2.0
aiosqlite>=0.20

# Crypto
pyoqs>=0.10          # liboqs-python bindings
cryptography>=42

# STT (choose one)
faster-whisper>=1.0  # preferred
vosk>=0.3.45         # fallback (smaller, faster, less accurate)

# Audio
sounddevice>=0.4     # optional, for server-side mic capture if needed
numpy>=1.26

# Text emotion
transformers>=4.40
torch>=2.2           # CPU-only sufficient for classification

# Video emotion
opencv-python>=4.9
torchvision>=0.17    # for ResNet50 FER

# Export
weasyprint>=62       # optional, PDF export

# Development
pytest
httpx             # for testing FastAPI
```

---

## Security Considerations

1. **Bind to 127.0.0.1 only.** The server must never listen on 0.0.0.0.
2. **No key material in logs.** Log sanitization must be enforced.
3. **Nonce reuse is catastrophic.** AES-GCM nonces must be `os.urandom(12)` per encryption, never derived or sequential.
4. **Session tokens.** Use `itsdangerous` or similar. Short TTL (15-30 min inactivity). httpOnly, SameSite=Strict cookies.
5. **USB detection.** Never auto-mount or auto-read keys. User must explicitly select the key file through the UI.
6. **Memory zeroing.** Python does not guarantee memory zeroing. For key bytes, use `ctypes.memset` or `bytearray` and overwrite on session lock.
7. **CSRF.** Include a CSRF token even on localhost (defense in depth against CSRF via malicious local pages).
8. **File permissions.** All `.pqj` files and the SQLite DB should be chmod 600.
