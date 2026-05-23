# PQ Journal

A post-quantum encrypted personal journal that runs locally in your browser.  
Built by [Meaningful Systems, LLC](https://meaningfulsystems.com).

---

## Features

- **Post-quantum encryption** — every entry encrypted with ML-KEM-1024 + X25519 hybrid KEM and AES-256-GCM. Signed with ML-DSA-65. Resistant to "harvest now, decrypt later" attacks.
- **USB key management** — private keys stored on a removable drive, not on disk. Passphrase-protected with PBKDF2-HMAC-SHA256 (600 000 iterations).
- **Voice journaling** — browser `MediaRecorder` → WebSocket streaming → faster-whisper or Vosk transcription. No cloud STT.
- **Emotion analysis** — per-paragraph HuggingFace classifier (`j-hartmann/emotion-english-distilroberta-base`) with keyword heuristic fallback. Voice tone (VAD) and optional webcam FER fused into an overall emotion label.
- **LLM synthesis** — optional Ollama or llama-cpp-python integration for empathetic emotion summaries. Works without any LLM.
- **Local only** — server binds to `127.0.0.1`. No telemetry, no accounts, no cloud.
- **FastAPI + HTMX** — server-side rendering with minimal JavaScript. No build step required.

---

## Architecture

```
Browser (HTMX + Tailwind + WebAudio API)
    │
    │  HTTP/WebSocket (localhost only — 127.0.0.1)
    ▼
FastAPI app
    ├── routes/     auth · journal · voice · emotion · settings
    ├── services/   crypto · stt · tone · emotion_text · emotion_video · llm · key_store
    ├── models/     SQLAlchemy (metadata index only — plaintext never written to DB)
    └── templates/  Jinja2 + HTMX partials
```

Entry files (`.pqj`) live at `~/MeaningfulJournal/entries/<uuid>.pqj`. Each is an independent encrypted JSON blob. A SQLite index at `~/MeaningfulJournal/.db/journal.sqlite` stores only metadata (title, date, tags, emotion label — no body text).

---

## Prerequisites

- Python 3.11+
- `liboqs` C shared library (required for ML-KEM / ML-DSA)

**Linux (apt):**
```bash
sudo apt install cmake pkg-config libssl-dev
pip install liboqs-python
```

**macOS (Homebrew):**
```bash
brew install liboqs
pip install liboqs-python
```

---

## Quick Start

```bash
git clone git@github.com:meaningfulsystems/pq-journal.git
cd pq-journal

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env and set a strong SECRET_KEY, or let run.py generate one automatically

python run.py
# Open http://localhost:8000
```

On first run, go to **Setup** (linked from the unlock screen) to generate your key pair and save it to a USB drive or a local directory.

---

## Optional Dependencies

Install any subset depending on which features you want:

```bash
pip install -r requirements-optional.txt
```

| Package | Feature |
|---------|---------|
| `faster-whisper>=1.0` | High-accuracy speech-to-text (recommended; ~1.5 GB model download on first use) |
| `vosk>=0.3.45` | Offline STT fallback (~50 MB, less accurate) |
| `transformers>=4.40` + `torch>=2.2` | HuggingFace per-paragraph emotion classification |
| `opencv-python` + `torchvision` | Webcam facial expression recognition (requires FER weights; see below) |
| `weasyprint>=62` | PDF export |
| `soundfile>=0.12` | Audio file upload transcription |

**Webcam FER weights:**  
The FER model expects `~/.pq-journal/fer_resnet50.pth` (ResNet50 fine-tuned on FER-2013). If absent, the feature is silently disabled. Enable webcam in `settings.yaml`:
```yaml
enable_webcam: true
```

**Ollama (LLM emotion synthesis):**  
Install [Ollama](https://ollama.com) and pull a model:
```bash
ollama pull llama3.2:3b
```
Configure in `settings.yaml`:
```yaml
ollama_url: http://localhost:11434
ollama_model: llama3.2:3b
```

---

## Configuration

Copy `settings.yaml.example` to `settings.yaml` and edit:

```yaml
journal_dir: ~/MeaningfulJournal   # Where entries and DB are stored
auto_lock_minutes: 15              # Auto-lock after N minutes idle (0 = never)
stt_model: large-v3-turbo          # faster-whisper model name
enable_webcam: false               # Set true to enable webcam FER
ollama_url: http://localhost:11434
ollama_model: llama3.2:3b
```

All values can also be set as environment variables (uppercase, e.g. `JOURNAL_DIR`). Environment variables override `settings.yaml`.

See `.env.example` for the full list.

---

## Key Management

Keys are generated once and stored on a USB drive (or any directory you control):

```
/your-usb-drive/meaningful-journal/
    ml_kem.pub      ML-KEM-1024 public key
    ml_kem.priv     ML-KEM-1024 private key (passphrase-encrypted)
    ml_dsa.pub      ML-DSA-65 public key
    ml_dsa.priv     ML-DSA-65 private key (passphrase-encrypted)
    key.json        Key metadata
```

Private keys are decrypted into memory only at unlock time and zeroed on session lock. They are never written to disk in plaintext.

Use `setup_keys.py` as a standalone key-generation tool if the web UI is unavailable:
```bash
python setup_keys.py --key-dir /path/to/key/directory
```

---

## Security Notes

1. **Bind address**: The server is hardcoded to `127.0.0.1`. Do not reverse-proxy without careful consideration.
2. **Nonce safety**: AES-GCM nonces are `os.urandom(12)` per entry — never sequential.
3. **Session tokens**: Signed with `itsdangerous`, httpOnly + SameSite=Strict cookie, auto-expire.
4. **File permissions**: `.pqj` files and the SQLite DB are created with `chmod 600`.
5. **No body in DB**: The SQLite index stores only title, date, tags, emotion label, and word count. Entry body text never leaves the encrypted file.
6. **Memory zeroing**: Session keys are overwritten with `bytearray` zero-fill on lock.

---

## Development

```bash
# Run with auto-reload (development only)
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Run tests
pip install pytest httpx
pytest
```

The `archive/` directory contains the original PyQt6 desktop app (`pq-journal-improved-20251127-1435.py`) from which this project was derived. It is kept as reference only and is not used by the web app.

---

## Project Structure

```
app/
  main.py               FastAPI app + lifespan
  config.py             Settings (YAML + env vars)
  dependencies.py       FastAPI dependency helpers (session, DB)
  routes/
    auth.py             /unlock  /lock  /setup
    journal.py          /journal  CRUD + export
    voice.py            /ws/record  /voice/upload
    emotion.py          /emotion/analyze  /emotion/video/frame
    settings.py         /settings
    files.py            /api/drives  /api/browse
  services/
    crypto.py           ML-KEM + AES-256-GCM encrypt/decrypt
    key_store.py        USB detection, key gen, key load
    session.py          In-memory session store
    stt.py              faster-whisper / Vosk
    tone.py             ToneEstimator — audio VAD → V/A/D
    emotion_text.py     HuggingFace paragraph classifier
    emotion_video.py    ResNet50 FER from webcam frames
    llm.py              Ollama / llama-cpp-python synthesis
    export.py           Markdown + PDF export
  models/
    db.py               SQLAlchemy JournalEntry model
  templates/            Jinja2 + HTMX
  static/
    js/
      recorder.js       WebSocket voice recorder + waveform
      webcam.js         Webcam frame capture (Slice 5)
      search.js         Journal list search
data/
  prompts.yaml          Reflective journal prompts (Logotherapy-based)
  emotion_matrix.json   VAD → emotion label grid
docs/
  pq-journal-web.md     Architecture document
  decisions.md          Design decisions log
archive/                Original PyQt6 monolith (reference only)
```

---

© 2025 Meaningful Systems, LLC — Private repository. All rights reserved.
