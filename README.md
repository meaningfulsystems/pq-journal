# PQ Journal

A post-quantum encrypted personal journal that runs entirely on your own machine.  
Built by [Meaningful Systems, LLC](https://meaningfulsystems.com).

---

## Why journaling — and why security matters

Decades of research in psychology and neuroscience show that expressive writing is one of the most accessible tools for mental health. Regular journaling has been shown to reduce symptoms of anxiety and depression, accelerate emotional processing after difficult events, and strengthen the sense of narrative identity that grounds people through trauma and change. Therapists in trauma-focused modalities — EMDR, somatic work, DBT — frequently recommend journaling between sessions precisely because writing creates a container for feelings that are too charged to hold in working memory alone.

But journaling's benefits depend entirely on honesty, and honesty requires safety. Many people with trauma histories stop journaling — or never start — because they cannot shake the fear that what they write might be read: by an abuser who shares their home, a cloud provider scanning for ad targeting, an employer's IT policy, a future data breach, or a government subpoena. That fear is not paranoia. It is a rational response to a world where data is routinely collected and disclosure of trauma can carry real consequences.

PQ Journal was built to remove that fear at the technical level, not just as a policy promise. Your entries are encrypted before they touch disk, using cryptography designed to remain unbreakable even against future quantum computers. Your keys live on a USB drive in your hand — not in a server, not in the cloud, not accessible to the app itself when you are not actively writing. No company, no server, no breach can read what you have written. What you write here is yours.

---

## What it is

PQ Journal is a voice-first journaling app with no cloud dependency. You speak; it transcribes, analyzes your emotional tone, and stores every entry in an encrypted file that only your key can open. The keys live on a USB drive you control.

**Encryption:** ML-KEM-1024 + X25519 hybrid KEM, AES-256-GCM, ML-DSA-65 signatures — resistant to "harvest now, decrypt later" quantum attacks.  
**Privacy:** Server binds to `127.0.0.1` only. No telemetry, no accounts, no cloud.  
**Offline-first:** Every AI feature (STT, emotion, LLM) runs locally. Internet connection not required after model download.

---

## Quick Start

### 1. System prerequisites

<details open>
<summary><strong>Linux (Ubuntu / Debian)</strong></summary>

```bash
# Python, build tools, and PDF rendering libs
sudo apt install python3.11 python3.11-venv cmake pkg-config libssl-dev \
                 libpango1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf2.0-0

# liboqs C library (post-quantum crypto)
sudo apt install liboqs-dev
# If liboqs-dev is not in your distro, build from source:
#   sudo apt install cmake ninja-build
#   git clone --depth 1 https://github.com/open-quantum-safe/liboqs
#   cmake -S liboqs -B liboqs/build -DBUILD_SHARED_LIBS=ON
#   sudo cmake --build liboqs/build --target install
```
</details>

<details>
<summary><strong>macOS</strong></summary>

```bash
# Homebrew required (https://brew.sh)
brew install liboqs
# Pango/Cairo for PDF export (optional):
brew install pango cairo gdk-pixbuf
```
</details>

<details>
<summary><strong>Windows</strong></summary>

1. Install [Python 3.11+](https://www.python.org/downloads/) — check **"Add to PATH"**
2. Install [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) — select **"C++ build tools"** workload
3. Install [CMake](https://cmake.org/download/) — check **"Add to PATH"**
4. Build and install liboqs:
   ```cmd
   git clone --depth 1 https://github.com/open-quantum-safe/liboqs
   cmake -S liboqs -B liboqs\build -DBUILD_SHARED_LIBS=ON
   cmake --build liboqs\build --config Release --target install
   ```
5. PDF export (`weasyprint`) requires the [GTK3 runtime for Windows](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases). Optional — skip if you don't need PDF export.

> **Windows key file permissions:** The app will warn you to manually restrict key file access via right-click → Properties → Security, since `chmod` is not available on Windows.
</details>

### 2. Create the environment and install core packages

```bash
git clone git@github.com:meaningfulsystems/pq-journal.git
cd pq-journal

# macOS / Linux:
python3.11 -m venv .venv
source .venv/bin/activate

# Windows:
# python -m venv .venv
# .venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Install AI features (optional but recommended)

```bash
pip install -r requirements-optional.txt
```

Then pre-download all models so first startup is instant:

```bash
python scripts/prefetch_models.py
```

This fetches (~750 MB total, one-time):
- Whisper `small` STT model
- HuggingFace emotion classifier
- DeepFace facial emotion model

### 4. Install Ollama for LLM emotion summaries (optional)

```bash
# Install Ollama: https://ollama.com
ollama pull llama3.2:3b
```

### 5. Run

```bash
python run.py
# Opens http://127.0.0.1:8000 automatically
```

On first run, click **Setup** to generate your key pair and choose where to store it (USB drive recommended).

---

## Feature overview

| Feature | Requires | Notes |
|---------|----------|-------|
| Journal (CRUD, search, export) | core only | Always available |
| Voice recording + transcription | `faster-whisper` | ~500 MB model, auto-downloaded |
| Per-paragraph emotion labels | `transformers` + `torch` | ~250 MB model, auto-downloaded |
| Voice tone (VAD) | core only | Valence/Arousal/Dominance from audio |
| Webcam facial emotion | `deepface` + `tf-keras` | ~6 MB model, auto-downloaded |
| LLM emotion synthesis | Ollama | Fuses all signals into one phrase |
| PDF export | `weasyprint` | Needs system pango/cairo libs |

**Emotion tags** in the journal look like:
```
[Emotion summary: calm and present {voice V:0.12 A:0.30 D:-0.14} {video neutral:0.76 happy:0.13 fear:0.09}]
```

---

## Architecture

```
Browser  (HTMX + Tailwind + WebAudio API)
    │
    │  HTTP/WebSocket  (localhost only — 127.0.0.1)
    ▼
FastAPI app
    ├── routes/     auth · journal · voice · emotion · settings · files
    ├── services/   crypto · stt · tone · emotion_text · emotion_video · llm · key_store
    ├── models/     SQLAlchemy metadata index (entry body never written to DB)
    └── templates/  Jinja2 + HTMX partials
```

Entry files (`.pqj`) are independent encrypted JSON blobs stored at `{journal_dir}/entries/<uuid>.pqj`.  
A SQLite index at `{journal_dir}/.db/journal.sqlite` stores only title, date, tags, and emotion label — body text never leaves the encrypted file.

---

## Configuration

Settings are stored at `{journal_dir}/settings/settings.yaml` — inside your journal directory, not in the app root. The app writes defaults on first unlock; edit to customize:

```yaml
auto_lock_minutes: 15              # idle auto-lock (0 = never)
stt_model: small                   # faster-whisper model (tiny/base/small/medium/large-v3)
enable_webcam: false               # set true to enable facial emotion capture
ollama_url: http://localhost:11434
ollama_model: llama3.2:3b
emotion_window_seconds: 30         # rolling window for LLM emotion synthesis
emotion_min_seconds: 20
emotion_min_words: 20
```

All settings can also be set as environment variables (uppercase, e.g. `STT_MODEL=small`).

---

## Key management

Keys are generated once and stored in a directory you choose (USB drive recommended):

```
/your-key-dir/
    ml_kem.pub      ML-KEM-1024 public key
    ml_kem.priv     ML-KEM-1024 private key (passphrase-encrypted)
    ml_dsa.pub      ML-DSA-65 public key
    ml_dsa.priv     ML-DSA-65 private key (passphrase-encrypted)
    key.json        Key metadata
```

Private keys are decrypted into memory only at unlock time and zeroed when the session locks. They are never written to disk in plaintext.

Offline key generation:
```bash
python setup_keys.py --key-dir /path/to/key/directory
```

---

## Security model

| Concern | Defense |
|---------|---------|
| Cross-origin browser requests to filesystem API | `Origin` header validation on all pre-auth endpoints |
| Passphrase brute force | Rate limit: 10 attempts / 5 min per IP, 2 s delay per failure |
| Clickjacking / MIME sniffing | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff` |
| Script injection via CSP | Strict `Content-Security-Policy`; no external script sources except Tailwind CDN |
| LLM prompt injection via journal content | `<user_content>` XML delimiters + server-side 15-word truncation |
| Key file permissions | `chmod 600` on all `.priv` files; advisory warning on Windows |
| Session expiry | `itsdangerous` signed cookie, `SameSite=Strict`, configurable auto-lock |

---

## Project structure

```
app/
  main.py               FastAPI app + lifespan + security middleware
  config.py             Settings (YAML + env vars)
  routes/
    auth.py             /unlock  /lock  /setup  (rate-limited)
    journal.py          /journal  CRUD + export
    voice.py            /ws/record  /voice/upload
    emotion.py          /emotion/analyze  /emotion/video/frame
    settings.py         /settings
    files.py            /api/drives  /api/browse  /api/home  /api/mkdir
  services/
    crypto.py           ML-KEM-1024 + AES-256-GCM encrypt/decrypt
    key_store.py        USB detection, key generation, key loading
    session.py          In-memory session store with auto-lock
    stt.py              faster-whisper (primary) + Vosk (fallback)
    tone.py             ToneEstimator — PCM → Valence/Arousal/Dominance
    emotion_text.py     HuggingFace per-paragraph emotion classifier
    emotion_video.py    DeepFace webcam FER (ResNet50 custom weights fallback)
    llm.py              Ollama LLM synthesis with prompt injection defense
    export.py           Markdown + PDF export
  models/
    db.py               SQLAlchemy JournalEntry model
  templates/            Jinja2 + HTMX
  static/js/
    recorder.js         WebSocket voice recorder + waveform + emotion tags
    webcam.js           Webcam frame capture and FER scoring
    search.js           Journal list search

scripts/
  prefetch_models.py    Pre-download all AI models (run once after setup)

data/
  prompts.yaml          Reflective journal prompts (Logotherapy-based)
  emotion_matrix.json   VAD → emotion label grid

docs/
  requirements.md       INCOSE requirements (R001–R106)
  design.md             Architecture + security design document
  diagrams/             PlantUML source + rendered PNGs
```

---

## Development

```bash
# Auto-reload dev server
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Tests
pip install pytest httpx
pytest
```

The `archive/` directory contains the original PyQt6 desktop app from which this project was derived. Reference only.

---

© 2025 Meaningful Systems, LLC — Private repository. All rights reserved.
