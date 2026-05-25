# PQ Journal

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A post-quantum encrypted personal journal that runs entirely on your own machine.  
Built by [Meaningful Systems, LLC](https://meaningfulsystems.com).

---

## The case for journaling

Research spanning four decades consistently shows that expressive writing is one of the most effective and accessible tools for mental health. Psychologist James Pennebaker's landmark studies at the University of Texas demonstrated that writing about thoughts and feelings surrounding difficult experiences leads to measurable improvements in immune function, mood, and long-term psychological wellbeing (Pennebaker & Beall, 1986; Pennebaker, 1997). A comprehensive meta-analysis by Frattaroli (2006) examining 146 studies confirmed these effects across a wide range of populations and life circumstances.

**Gratitude journaling** — the practice of regularly writing down what you are thankful for — has its own body of evidence. Emmons and McCullough (2003) found that people who kept weekly gratitude journals reported higher levels of well-being and optimism, exercised more, and reported fewer physical complaints compared to control groups.

**Logotherapy**, developed by Viktor Frankl from his experiences as a psychiatrist and Holocaust survivor, centers on the idea that the search for meaning is the primary human motivation. His work (*Man's Search for Meaning*, 1946) gave rise to a set of reflective practices that help people identify their values, examine purpose, and process suffering through the lens of what matters most to them. PQ Journal includes logotherapy-informed prompts because they go beyond emotional venting — they invite the kind of reflection that research suggests produces lasting change rather than momentary relief.

Voice journaling extends these benefits for people who find writing difficult, think faster than they type, or want to capture emotion as it is happening rather than reconstructing it afterward.

---

## Why security matters

We live in a fully connected world. The data we generate — even data we consider private — is more accessible to more parties than most people realize. For a journal to work as a genuine tool for mental health, the person writing must feel truly safe to be honest. That safety cannot rest on a terms-of-service agreement or a company's stated privacy policy. It needs to rest on mathematics.

PQ Journal encrypts every entry before it is written to disk, using cryptography that remains secure even as computing power advances. Your keys never leave your possession. No company, server, or software update can access what you have written.

### Security in the age of AI

Artificial intelligence has fundamentally changed the threat landscape for digital security. AI-powered tools can now automate the discovery of software vulnerabilities, assist in analyzing encrypted data at scale, and dramatically accelerate the process of testing millions of potential attack vectors. This means that security that felt adequate a few years ago needs to be re-evaluated against a much more capable adversary.

This is not hypothetical. Security researchers and malicious actors alike now routinely use large language models to assist with everything from writing exploit code to identifying cryptographic weaknesses in legacy systems. The bar for what constitutes "good enough" encryption has risen, and PQ Journal is designed to meet that bar today.

### The quantum computing threat

Quantum computers are a different class of machine from classical computers. Rather than processing bits that are either 0 or 1, quantum computers use qubits that can exist in superpositions of both states simultaneously. This allows certain problems — including the mathematical problems that underlie most of today's encryption — to be solved exponentially faster.

RSA encryption and elliptic curve cryptography (ECC), which protect the vast majority of internet traffic today, rely on the fact that factoring very large numbers or computing discrete logarithms takes classical computers an impractically long time. A sufficiently powerful quantum computer running Shor's algorithm could break these schemes in hours rather than millennia.

Large-scale, cryptographically relevant quantum computers do not yet exist. But the threat is real enough that intelligence agencies and standards bodies are already treating it as a planning problem. The concern is what security professionals call **"harvest now, decrypt later"**: adversaries collect encrypted data today and store it, intending to decrypt it once quantum computers mature. For a personal journal, this means that something you write today and believe to be private could — if protected only with classical encryption — become readable in the future.

### Why we chose a hybrid post-quantum algorithm

PQ Journal uses a combination of four cryptographic components. The hybrid design means an attacker would need to break two independent cryptographic systems simultaneously — if one ever falls, the other remains standing.

| Component | Type | What it does | Why it's post-quantum safe |
|-----------|------|-------------|---------------------------|
| **ML-KEM-1024** (CRYSTALS-Kyber) | Key encapsulation | Generates the shared encryption key that seals your entry | Based on the Module Learning with Errors (MLWE) problem — a mathematical structure that quantum computers have no known efficient algorithm to solve |
| **X25519** | Classical key exchange | Contributes to the same shared key alongside ML-KEM | Battle-tested elliptic curve cryptography; paired with ML-KEM so both must be broken simultaneously |
| **AES-256-GCM** | Symmetric encryption | Encrypts the actual content of your entry | 256-bit keys: even using Grover's quantum algorithm, breaking AES-256 still requires ~2¹²⁸ operations — computationally infeasible for any foreseeable machine |

ML-KEM-1024 is a NIST-standardized post-quantum algorithm (FIPS 203), published in 2024 as the first formal post-quantum key encapsulation standard. It is based on the hardness of lattice problems — mathematical structures that have resisted cryptanalysis for decades, including by quantum methods.

In plain language: your journal entries are locked with a key that would take longer to crack than the age of the universe, even for a quantum computer. The key itself never leaves your USB drive.

---

## What PQ Journal does

PQ Journal is a voice-first journaling app. You speak; it transcribes your words, analyzes your emotional tone from voice, facial expression, and content, and stores every entry in an encrypted file that only your key can open.

**Privacy:** Server binds to `127.0.0.1` only. No telemetry, no accounts, no cloud.  
**Offline-first:** Every AI feature — speech transcription, emotion analysis, LLM synthesis — runs locally on your machine. No internet connection required after the one-time model download.

**Emotion tags** captured during voice recording look like:
```
[Emotion summary: calm and present {voice V:0.12 A:0.30 D:-0.14} {video neutral:0.76 happy:0.13 fear:0.09}]
```
The tag has three independent parts: a human-readable phrase generated by a local LLM (using your transcript, average voice tone, and dominant facial expression as inputs); raw voice valence/arousal/dominance readings; and the full distribution of detected facial expressions across the recording window.

---

## Quick Start

> **Just want to get started?** After completing Steps 1–3 (Python + system libraries + git clone), run:
> ```bash
> python scripts/install_all.py
> ```
> This single command creates the virtual environment, installs all dependencies, downloads all AI models (~4.3 GB total), and pulls the Ollama language model. Then `python run.py` to launch.

The steps below explain each stage in detail — useful if something goes wrong or you want more control.

> **New to the command line?** All the setup steps below happen in a terminal (macOS/Linux) or Command Prompt/PowerShell (Windows). On macOS, open Terminal from Applications → Utilities. On Windows, search for "PowerShell" in the Start menu. You type commands and press Enter to run them. Everything you need to type is shown in gray code blocks below.

### Step 1 — Install Python

Python is the programming language PQ Journal runs on. You can check if it is already installed:

```bash
python3 --version
```

If you see `Python 3.11` or higher, skip to Step 2. Otherwise:

- **Windows/macOS:** Download from [python.org/downloads](https://www.python.org/downloads/). During installation, check the box that says **"Add Python to PATH"**.
- **Linux:** `sudo apt install python3.11 python3.11-venv` (Ubuntu/Debian).

### Step 2 — Install system libraries

<details open>
<summary><strong>Linux (Ubuntu / Debian)</strong></summary>

```bash
sudo apt install cmake pkg-config libssl-dev \
                 libpango1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf2.0-0

# Post-quantum crypto library:
sudo apt install liboqs-dev
```

If `liboqs-dev` is not available in your distribution:
```bash
sudo apt install cmake ninja-build
git clone --depth 1 https://github.com/open-quantum-safe/liboqs
cmake -S liboqs -B liboqs/build -DBUILD_SHARED_LIBS=ON
sudo cmake --build liboqs/build --target install
```
</details>

<details>
<summary><strong>macOS</strong></summary>

```bash
# Homebrew is required — install from https://brew.sh if you don't have it
brew install liboqs
# Optional (for PDF export):
brew install pango cairo gdk-pixbuf
```
</details>

<details>
<summary><strong>Windows</strong></summary>

1. Install [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) — select the **"C++ build tools"** workload
2. Install [CMake](https://cmake.org/download/) — check **"Add to PATH"** during install
3. Open a terminal and run:
   ```cmd
   git clone --depth 1 https://github.com/open-quantum-safe/liboqs
   cmake -S liboqs -B liboqs\build -DBUILD_SHARED_LIBS=ON
   cmake --build liboqs\build --config Release --target install
   ```
4. PDF export requires the [GTK3 runtime](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases) — optional, skip if not needed.

> Key file permissions cannot be enforced automatically on Windows. The app will remind you to restrict access manually via right-click → Properties → Security.
</details>

### Step 3 — Download PQ Journal and set up the environment

```bash
git clone https://github.com/meaningfulsystems/pq-journal.git
cd pq-journal
```

> **What is a virtual environment?** It is an isolated folder that holds all of PQ Journal's dependencies without affecting the rest of your system. Think of it as a clean workspace just for this app.

```bash
# macOS / Linux:
python3 -m venv .venv
source .venv/bin/activate

# Windows:
python -m venv .venv
.venv\Scripts\activate
```

Your terminal prompt will now show `(.venv)` to indicate the environment is active.

```bash
pip install -r requirements.txt
```

### Step 4 — Install AI features (recommended)

This step adds speech transcription, emotion analysis, and webcam support. It is optional — the journal works without it.

```bash
pip install -r requirements-optional.txt
```

Then pre-download all AI models so that first startup is instant (one-time, ~750 MB):

```bash
python scripts/prefetch_models.py
```

This fetches:
- **Whisper** speech-to-text model (~500 MB)
- **HuggingFace** emotion classifier (~250 MB)
- **DeepFace** facial emotion model (~6 MB, weights only — TensorFlow dependency is larger)

### Step 5 — Install Ollama for emotion summaries (optional)

Ollama runs a local language model that synthesizes voice, text, and facial data into a single human-readable emotion phrase.

```bash
# Download and install Ollama from https://ollama.com
ollama pull llama3.2:3b
```

### Step 6 — Run

```bash
python run.py
```

Your browser will open to `http://127.0.0.1:8000`. Click **Setup** to generate your key pair and choose where to store it — a USB drive is recommended.

---

## Feature overview

| Feature | Requires | Notes |
|---------|----------|-------|
| Journal (write, search, export) | core only | Always available |
| Voice recording + transcription | `faster-whisper` | English-only, ~500 MB model, auto-downloaded |
| Per-paragraph emotion labels | `transformers` + `torch` | ~250 MB model, auto-downloaded |
| Voice tone (valence/arousal/dominance) | core only | Derived directly from audio signal |
| Webcam facial emotion | `deepface` + `tf-keras` | ~6 MB model, auto-downloaded |
| LLM emotion synthesis | Ollama | Fuses all emotion signals into one phrase |
| PDF export | `weasyprint` | Requires system pango/cairo libs |
| Logotherapy-based prompts | core only | Built into the journal interface |

---

## Architecture

> This section is for developers and security engineers reviewing the system design.

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

Entry files (`.pqj`) are independent encrypted JSON blobs at `{journal_dir}/entries/<uuid>.pqj`.  
A SQLite index at `{journal_dir}/.db/journal.sqlite` stores only title, date, tags, and emotion label — body text never leaves the encrypted file.

---

## Configuration

Settings are stored at `{journal_dir}/settings/settings.yaml` — inside your journal directory. The app writes defaults on first unlock:

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

All settings can also be set as environment variables (uppercase), e.g. `STT_MODEL=small`.

---

## Key management

Keys are generated once and stored in a directory you choose. A USB drive means no copy of your private key remains on your computer when the drive is removed.

```
/your-key-dir/
    ml_kem.pub      ML-KEM-1024 public key
    ml_kem.priv     ML-KEM-1024 private key (passphrase-encrypted)
    key.json        Key metadata
```

Private keys are decrypted into memory only at unlock time and zeroed when the session locks. They are never written to disk in plaintext. Offline key generation:

```bash
python setup_keys.py --key-dir /path/to/key/directory
```

---

## Security hardening summary

> For security engineers: a summary of the application-layer defenses implemented on top of the cryptographic layer.

| Concern | Defense |
|---------|---------|
| Cross-origin browser requests to filesystem API | `Origin` header validation on all pre-auth endpoints |
| Passphrase brute force | Rate limit: 10 attempts / 5 min per IP, 2 s artificial delay per failure |
| Clickjacking / MIME sniffing | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff` |
| Unauthorized script execution | Strict `Content-Security-Policy` — no external scripts except Tailwind CDN |
| LLM prompt injection via journal content | `<user_content>` XML delimiters + server-side 15-word hard truncation |
| Key file exposure | `chmod 600` on all `.priv` files; advisory warning on Windows |
| Session hijacking | `itsdangerous` signed cookie, `SameSite=Strict`, configurable auto-lock |
| Information disclosure before auth | `/api/status` requires authenticated session |

Full threat model and security design: [`docs/design.md`](docs/design.md)

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
    stt.py              faster-whisper (primary) + Vosk (fallback), English-only
    tone.py             ToneEstimator — PCM → Valence/Arousal/Dominance
    emotion_text.py     HuggingFace per-paragraph emotion classifier
    emotion_video.py    DeepFace webcam FER with ResNet50 custom weights fallback
    llm.py              Ollama synthesis with prompt injection defense
    export.py           Markdown + PDF export
  models/
    db.py               SQLAlchemy JournalEntry model
  templates/            Jinja2 + HTMX
  static/js/
    recorder.js         WebSocket voice recorder + waveform + emotion tags
    webcam.js           Webcam frame capture and FER scoring
    search.js           Journal list search

scripts/
  install_all.py        One-command full setup (venv + deps + models + Ollama)
  prefetch_models.py    Pre-download AI models only (run inside active venv)

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

## References

- Pennebaker, J. W., & Beall, S. K. (1986). Confronting a traumatic event: Toward an understanding of inhibition and disease. *Journal of Abnormal Psychology, 95*(3), 274–281.
- Pennebaker, J. W. (1997). *Opening up: The healing power of expressing emotions.* Guilford Press.
- Frattaroli, J. (2006). Experimental disclosure and its moderators: A meta-analysis. *Psychological Bulletin, 132*(6), 823–865.
- Emmons, R. A., & McCullough, M. E. (2003). Counting blessings versus burdens. *Journal of Personality and Social Psychology, 84*(2), 377–389.
- Frankl, V. E. (1946). *Man's search for meaning.* Beacon Press.
- NIST FIPS 203 — Module-Lattice-Based Key-Encapsulation Mechanism Standard (ML-KEM), 2024.

---

© 2026 Meaningful Systems, LLC. Released under the [MIT License](LICENSE).  
Third-party AI model weights (Llama 3.2 via Ollama) carry their own license terms — see [LICENSE](LICENSE) for details.
