# PQ Journal Web App — Open Decisions

Each decision below has options, pros/cons, a recommendation, and a space for your direction.  
Work through these before writing any code — several of them gate the others.

---

## D-01: Speech-to-Text Engine

**Context:** The archive uses Vosk (offline, fast, mediocre accuracy). Grok recommends faster-whisper large-v3. These have very different tradeoffs.

### Options

**Option A: faster-whisper large-v3**
- Pros: Best-in-class accuracy; handles accents, mumbling, medical/tech vocab well
- Cons: ~6GB model download; requires modern CPU (AVX2) or GPU for real-time; not truly streaming (must buffer audio)

**Option B: faster-whisper large-v3-turbo**
- Pros: ~4x faster than large-v3; ~1.5GB; accuracy only marginally worse; Whisper team's recommendation for real-time
- Cons: Still not streaming; needs faster-whisper installed

**Option C: faster-whisper small or medium**
- Pros: ~250MB–500MB; runs comfortably on any modern CPU
- Cons: Noticeably lower accuracy, especially with technical vocabulary

**Option D: Vosk (keep existing)**
- Pros: Already working in archive; streams in real-time; ~1GB model; true low-latency partials
- Cons: Significantly lower accuracy than Whisper; older architecture

**Option E: Hybrid — Vosk for real-time partials + faster-whisper for final**
- Pros: Best UX (see words appearing as you speak) + best final accuracy
- Cons: More complex; two model downloads; Vosk partials will differ from final Whisper output (user sees text change)

### Recommendation
**Option B (large-v3-turbo)** with Vosk as graceful fallback if faster-whisper is not installed. For a journaling app with deliberate speech, large-v3-turbo is more than sufficient. Make the model name configurable in settings so the user can switch.

### Your Direction
> _Option B._

---

## D-02: Facial Emotion Detection Library

**Context:** Grok says "use deepface." The archive already has a working PyTorch ResNet50 FER approach. This is a real architectural choice.

### Options

**Option A: Keep PyTorch ResNet50 from archive**
- Pros: Already written and partially tested; no new dependencies; you control the model file; no runtime downloads from external URLs
- Cons: Requires the `FER_static_ResNet50_AffectNet.pt` model weights file (where does the user get this?); the archive shows it had loading issues (too many missing keys fallback)

**Option B: deepface**
- Pros: 3 lines of code; handles face detection + emotion in one call; multiple backend options (tf, torch)
- Cons: Downloads models from GitHub at runtime (privacy concern); requires TensorFlow or adds Torch dependency; less auditable; opaque model selection

**Option C: fer (Python package)**
- Pros: Simple API; uses MTCNN + mini-Xception (lightweight); pip install fer
- Cons: Smaller model; TensorFlow dependency; less accurate than ResNet50

**Option D: No facial emotion — audio + text only**
- Pros: Dramatically simpler; no webcam permission needed; works for users without webcam
- Cons: Loses one modality of emotion signal

**Option E: Make facial emotion entirely optional (default off)**
- Pros: Ships without webcam complexity; user enables it if they want; no model download on first run
- Cons: Feature may be overlooked; adds configuration complexity

### Recommendation
**Option E** — make facial emotion optional and off-by-default. Implement it with Option A (PyTorch) when enabled. The archive's FER loading issues need to be debugged and the weight file source needs to be documented. deepface's runtime model downloads are incompatible with a privacy-first architecture.

### Your Direction
> _I want scary level emotion detection here.  What is the best emotion detector?  Why is deepface a privacy concern?_

---

## D-03: LLM for Emotion Synthesis

**Context:** The archive uses a local llama.cpp server (over HTTP) to synthesize a 3-8 word emotion phrase from multi-modal signals. This was brittle. Grok suggests HuggingFace transformers instead.

### Options

**Option A: Ollama (if running on system)**
- Pros: Clean REST API that doesn't change; easy model management (`ollama pull tinyllama`); completely local; good defaults
- Cons: Requires Ollama installed separately; another external service

**Option B: llama-cpp-python (in-process)**
- Pros: No separate server; model loaded directly in Python; faster startup than HTTP round-trips
- Cons: Heavy C++ compilation dependency; large memory footprint; slower than Ollama for iterative use

**Option C: HuggingFace text generation pipeline**
- Pros: Consistent with text emotion classifier; one dependency (transformers already required)
- Cons: Smaller models (GPT-2 class) are poor at following the emotion phrase format; larger models are slow on CPU

**Option D: Just use the HF emotion classifier label directly (no LLM)**
- Pros: No LLM needed; the classifier output is already a human-readable label ("joy", "sadness"); combine with VAD to produce a phrase programmatically like the archive's `EmotionSummarizer`
- Cons: Less creative/natural phrasing; loses the "hopeful yet uneasy" nuance

**Option E: Offer LLM as a plugin (optional config)**
- Pros: Core app works without LLM; users with Ollama get the richer synthesis; clear separation
- Cons: Two code paths to maintain

### Recommendation
**Option E** — design the emotion pipeline so Option D is the default output, but the LLM synthesis slot is injectable. If Ollama is detected at startup, enable it automatically. Do not bundle or auto-download an LLM. This keeps the app fast and simple for most users while supporting the richer experience for those who set up Ollama.

### Your Direction
> _Option E... but i want ollama strongly recommended._

---

## D-04: Real-time Audio Streaming Architecture

**Context:** A journaling app needs to show transcription and emotion feedback in near-real-time. HTMX alone cannot handle this. A design decision is needed.

### Options

**Option A: WebSocket for audio streaming**
- Pros: True bidirectional; can stream audio chunks and receive transcription updates simultaneously; lowest latency
- Cons: More complex server-side (WebSocket handler + audio buffer management); HTMX doesn't help here, need custom JS

**Option B: HTTP chunked upload + SSE for results**
- Pros: Simpler than WebSocket; SSE is well-supported; works with HTMX `hx-ext="sse"`
- Cons: Two connections (upload POST + SSE stream); more latency than WebSocket

**Option C: Buffer entire recording, upload on stop, display result**
- Pros: Simplest architecture; no streaming complexity; HTMX handles the POST/swap cleanly
- Cons: No live feedback during recording; user must wait for full upload + transcription after stopping

**Option D: Vosk for real-time browser display + faster-whisper on stop**
- Pros: Good UX (live partials); accurate final transcript; well-established pattern
- Cons: Requires Vosk running in parallel with faster-whisper; text replacement on final can be jarring

### Recommendation
**Option A (WebSocket)** for the recording flow. Accept that this requires ~100 lines of custom JavaScript. The journaling loop is the core UX — it should feel responsive. Use HTMX for everything else (CRUD, navigation, settings). Document the WebSocket protocol clearly.

If WebSocket feels like too much scope for Slice 2, start with Option C (buffer and upload) and upgrade later — the server-side API doesn't change.

### Your Direction
> _Option A_

---

## D-05: USB Key Detection and UX

**Context:** Grok says "prompt for USB insertion at startup." This is the most Linux-specific feature and needs a concrete design.

### Options

**Option A: Poll `/media/<user>/` and `/run/media/<user>/` at startup**
- Pros: Works on most Linux desktop distros (GNOME, KDE auto-mount); simple implementation
- Cons: Polling; misses non-auto-mounted drives; different path on some distros; breaks on headless/server Linux

**Option B: Use `pyinotify` or `watchdog` to watch mount dirs**
- Pros: Event-driven; no polling; reacts immediately when USB is inserted
- Cons: Additional dependency; inotify on `/media` may not fire on auto-mount depending on distro config

**Option C: Use `lsblk --json` to detect removable media**
- Pros: Works across distros; detects mount point; doesn't require polling dirs
- Cons: Requires subprocess; need to handle mount/unmount loop; may need `udisks2` on some systems

**Option D: User manually types or pastes the key directory path**
- Pros: No detection logic needed; works everywhere including network drives, mounted ISOs, NFS
- Cons: Worse UX; user must know the path; defeats the "just insert USB" vision

**Option E: File picker in browser pointing to server-side path**
- Pros: User browses filesystem; familiar UX
- Cons: Browser file pickers don't show the server's filesystem; requires a custom file browser API endpoint

### Recommendation
**Option A + C combined**: At startup (and on a 5-second poll), run `lsblk --json` to find removable media and their mount points. Display detected drives as options in the unlock screen. Also show a text input for manual path entry (Option D fallback). This covers 90% of desktop Linux users without fragile path assumptions.

**Critical question for you:** Is this app only for your own use on your machine, or do you intend to share/distribute it? If it's just for you, Option D (hardcoded or configured path) is the fastest path to working software.

### Your Direction
> _I intend to share and distribute this at pq-journal on meaningfulsystems page for github.  Keypoint is you want the keys to be in a different location than the journal.  USB drive helps with that, but I think we want a file picker for the key directory.  Agree?_

---

## D-06: Encryption: Hybrid Classical+PQC or PQC Only

**Context:** Grok says "Hybrid: PQC + classical (X25519 + AES-256-GCM)." ML-KEM already provides quantum resistance. Adding X25519 provides defense-in-depth against PQC being broken.

### Options

**Option A: PQC only (ML-KEM-1024 + AES-256-GCM)**
- Pros: Simpler key material; no classical key to manage; ML-KEM is NIST-finalized; archive already does this
- Cons: If ML-KEM is broken by a future attack, all entries are exposed (harvest-now-decrypt-later attack on classical is reversed)

**Option B: Hybrid (ML-KEM-1024 + X25519 + AES-256-GCM)**
- Pros: Defense-in-depth; if either algorithm is broken, entries remain secure; this is what Signal, Chrome, and Cloudflare use in production
- Cons: More complex key management (two key pairs); slightly larger ciphertext; harder to audit

**Option C: Classical only (X25519 + AES-256-GCM)**
- Pros: Simpler; well-understood; no liboqs dependency
- Cons: Vulnerable to quantum adversary with a future large-scale quantum computer; defeats the point of the app

### Recommendation
**Option B (Hybrid)**. The app is named "PQ Journal" — if the user is encrypting their personal thoughts, the harvest-now-decrypt-later threat is real (an adversary records ciphertext today to decrypt in 10 years). Hybrid gives best of both worlds. The key management complexity is manageable: store both key pairs in the USB directory.

### Your Direction
> _Option B_

---

## D-07: Signing Each Entry

**Context:** Grok specifies ML-DSA for signing. The question is: sign with what key, for what purpose?

### Options

**Option A: Sign each entry with the user's ML-DSA private key**
- Pros: Proves the entry was written by the key holder; detects tampering; non-repudiation
- Cons: The only person who can verify is the user themselves (no external verifier); adds complexity; if the private key is on USB, signing requires USB present for every save

**Option B: HMAC-SHA256 the entry with a derived key (integrity only)**
- Pros: Simpler; fast; detects tampering without asymmetric signing; key stays symmetric
- Cons: Not a signature (no non-repudiation); anyone with the key can forge

**Option C: Sign only the key material, not every entry**
- Pros: Authenticates the key bundle; simpler than per-entry signing
- Cons: Doesn't detect per-entry tampering

**Option D: No signing (encryption only)**
- Pros: Simplest; encryption already provides integrity via GCM authentication tag
- Cons: AES-GCM tag only proves the decryption key was correct, not who wrote it

### Recommendation
**Option B (HMAC per entry)**. AES-256-GCM's authentication tag already protects against random bit flips. An HMAC adds a check that the file hasn't been replaced with a different encrypted blob. Full ML-DSA signing is meaningful only if there's a verifier who doesn't have the private key — for a personal journal, that verifier doesn't exist. Save the complexity.

If you specifically want "I can prove I wrote this entry on this date" as a feature (e.g., legal/journalistic use), then ML-DSA signing becomes worth it. Tell me.

### Your Direction
> _Option B_

---

## D-08: Full-text Search vs. Metadata-only Search

**Context:** Grok says "Full-text search." This conflicts with "all decryption in memory only" unless carefully designed.

### Options

**Option A: Metadata-only search (title, date, tags, emotion label)**
- Pros: No decryption needed for search; fast; works while locked
- Cons: Can't find entries by body content

**Option B: Decrypt-and-search at query time**
- Pros: True full-text search; simple to implement
- Cons: Slow on large journals (~100ms per entry to decrypt); all entries in memory during search; side-channel risk

**Option C: Blind index (HMAC of each word stored in SQLite)**
- Pros: Private; fast; doesn't decrypt entries for search
- Cons: Significant implementation complexity; requires re-indexing on key change; reveals word frequency patterns to anyone with DB access but not key

**Option D: Tantivy/SQLite FTS with encrypted index**
- Pros: Best performance; real FTS features (stemming, ranking)
- Cons: Very complex; key rotation nightmare

### Recommendation
**Start with Option A** (metadata only). For a personal journal, you usually know approximately when you wrote something or what tags you used. Add Option B as an explicit "search body" button with a progress indicator and privacy notice. Do not build the blind index — it's complex, fragile on key rotation, and overkill for a personal app.

### Your Direction
> _I think Option B is the most interesting here, perhaps we can have a cool UI while the searching is happening indicating the decryption is happening which slows down the search.  _

---

## D-09: Reflective / Systems-thinking Prompts

**Context:** Grok mentions "optional reflective / systems-thinking prompts" without defining what these are. This needs to be defined before building.

### Options

**Option A: Hardcoded list of prompts in the app**
- Pros: Simple; no model needed; always works; you can write prompts that fit your systems-thinking framework
- Cons: Static; can't be updated without code change

**Option B: User-editable YAML/JSON prompt library**
- Pros: User can add/remove/edit prompts; can be versioned; aligns with Meaningful Systems brand
- Cons: Needs a UI for editing; slightly more complex

**Option C: LLM-generated contextual prompts based on entry content**
- Pros: Dynamic and relevant; could reference prior entries
- Cons: Requires LLM; privacy tradeoff (entry content sent to LLM, even if local); complex to implement well

**Option D: Skip for initial version**
- Pros: Reduces scope; doesn't block Slices 1-6
- Cons: Feature never gets built

### Recommendation
**Option B** — a user-editable JSON/YAML file of prompts. Ship with 20-30 curated systems-thinking prompts that reflect the Meaningful Systems philosophy. This is a lightweight feature that adds real value without model complexity. Skip Option C until the LLM layer is mature.

### Your Direction
> _Add prompts based on logotherapy by default.  then do option B so it is editable and users can add/remove entries._

---

## D-10: Target User and Distribution

**Context:** This shapes almost every decision above. The Grok prompt was written for one user (you). But "production-ready" implies otherwise.

### Options

**Option A: Personal use only — you, your machine, your hardware**
- Implications: Simplify USB detection (hardcode path); don't worry about installer; can use your GPU; skip PDF export; skip multi-OS; move fast
- Tradeoffs: Nothing you build is generalizable

**Option B: Distribute to technical users (developers, researchers)**
- Implications: Document dependencies carefully; graceful fallbacks are essential; README must be excellent; test on clean Ubuntu install
- Tradeoffs: More setup complexity; must handle hardware diversity (no GPU, different distros)

**Option C: Distribute to non-technical users**
- Implications: Need a one-command installer (`./install.sh`); bundle models; GUI wrapper for key generation; simplify or hide encryption details
- Tradeoffs: Significant packaging work; conflicts with "production-ready" Python app model

### Recommendation
**Decide this first.** Everything else (fallback complexity, installer effort, model download strategy) flows from this. My read: start with Option A to get to a working app quickly, design for Option B from the start (good fallbacks, clear README), and defer Option C entirely.

### Your Direction
> _Option B.  I want it to run on windows, mac, and linux with a series of terminal commands to clone the directory and install packages, potentially with a .venv. This should be runnable by anyone on any computer anywhere in the world who has claude or codex installed and wants to get the app running.  _

---

## Summary Checklist

| # | Decision | Status |
|---|----------|--------|
| D-01 | STT Engine | Open |
| D-02 | Facial Emotion Library | Open |
| D-03 | LLM for Emotion Synthesis | Open |
| D-04 | Real-time Audio Streaming | Open |
| D-05 | USB Key Detection UX | Open |
| D-06 | Hybrid vs PQC-only Crypto | Open |
| D-07 | Entry Signing | Open |
| D-08 | Full-text Search | Open |
| D-09 | Reflective Prompts | Open |
| D-10 | Target User / Distribution | Open — **do this first** |
