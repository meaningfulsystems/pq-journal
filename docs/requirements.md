# PQ Journal — Systems Requirements Specification

**Document ID:** PQJ-SRS-001  
**Version:** 1.0  
**Date:** 2026-05-25  
**Standard:** INCOSE Systems Engineering Handbook v5 / IEEE 29148-2018  

---

## 1. Scope

This document specifies the functional, performance, and security requirements for PQ Journal, a local post-quantum encrypted personal journaling application. All requirements use "shall" for mandatory behaviors. Each requirement is uniquely numbered, categorized, and mapped to a verification method.

---

## 2. Definitions

| Term | Definition |
|------|-----------|
| Entry | A single journal record consisting of a title, body text, tags, and optional emotion data |
| Session | An authenticated in-memory context holding decrypted key material |
| Key Directory | External filesystem location containing the user's encrypted key files |
| Journal Directory | Filesystem location containing entries, database, and settings |
| VAD | Valence-Arousal-Dominance: three-dimensional emotional state vector |
| PQC | Post-Quantum Cryptography |
| ML-KEM | Module-Lattice-Based Key Encapsulation Mechanism (NIST FIPS 203) |

---

## 3. Requirements

### 3.1 System Requirements (SYS)

---

#### R001 — Local-Only Deployment
**Category:** SYS  
**Statement:** The system shall operate entirely on the user's local machine without transmitting any journal data, encryption keys, or authentication credentials to external servers.  
**Rationale:** User privacy is the primary design goal. All cryptographic operations and data storage must remain under user control.  
**Verification:** Inspection (network traffic analysis confirms no outbound connections except locally configured Ollama endpoint)

---

#### R002 — Graceful Degradation
**Category:** SYS  
**Statement:** The system shall remain functional for core journaling (write, read, search, export) when optional dependencies (faster-whisper, HuggingFace transformers, Ollama, webcam) are unavailable.  
**Rationale:** Optional AI features must not block core journal functionality.  
**Verification:** Test — verify core routes respond successfully with optional packages unimported

---

#### R003 — Single-User Process
**Category:** SYS  
**Statement:** The system shall support exactly one authenticated user session per process instance.  
**Rationale:** The in-memory session store and module-level encryption key are not designed for multi-tenant use.  
**Verification:** Inspection (session store is a module-level dict; DB key is a single global variable)

---

#### R004 — Startup Without Journal Path
**Category:** SYS  
**Statement:** The system shall start successfully without any pre-configured journal or key directory, requiring those paths only at user login.  
**Rationale:** No sensitive path metadata shall be required in the application root at startup.  
**Verification:** Test — launch app with empty settings.yaml; verify startup completes and /unlock renders

---

#### R005 — Error Pages
**Category:** SYS  
**Statement:** The system shall return user-facing HTML error pages for HTTP 404 and HTTP 500 responses that do not disclose internal stack traces or file paths.  
**Rationale:** Prevents information disclosure to unauthenticated users.  
**Verification:** Test — trigger 404 and 500; inspect response body for absence of tracebacks

---

### 3.2 Configuration Requirements (CFG)

---

#### R006 — Settings Hierarchy
**Category:** CFG  
**Statement:** The system shall load configuration in the following priority order (highest first): environment variables, journal-specific settings file (`{journal_dir}/settings/settings.yaml`), application-root settings file, system defaults.  
**Rationale:** Allows per-journal configuration without polluting the application root.  
**Verification:** Test — set conflicting values at each level; verify correct precedence

---

#### R007 — Journal Settings Isolation
**Category:** CFG  
**Statement:** The system shall store all user-configurable settings in `{journal_dir}/settings/settings.yaml` after initial setup, and shall not write any path information (journal_dir or key_dir) into any settings file.  
**Rationale:** The application root must not leak the location of encrypted data or keys.  
**Verification:** Inspection — verify no settings file contains a `journal_dir` or `key_dir` field after a save operation

---

#### R008 — Default Session Timeout
**Category:** CFG  
**Statement:** The system shall default the session idle timeout to 10 minutes when no explicit setting is provided.  
**Rationale:** Balances usability with security for a local journaling tool.  
**Verification:** Test — omit auto_lock_minutes from settings; verify session expires at 600 seconds

---

#### R009 — Configurable Session Timeout
**Category:** CFG  
**Statement:** The system shall accept an `auto_lock_minutes` setting in the range [1, 480] minutes and apply it as the session idle timeout.  
**Rationale:** Different users have different threat models and usage patterns.  
**Verification:** Test — set auto_lock_minutes=1; verify session expires after 60 seconds of idle

---

#### R010 — Ollama Auto-Detection
**Category:** CFG  
**Statement:** At startup, if the configured Ollama model is not available in the local Ollama instance, the system shall automatically select the highest-ranked available model from the preference list [phi3, llama3.2, llama3.1, llama3, mistral, tinyllama] and persist that selection to the app-root settings file.  
**Rationale:** Prevents silent emotion synthesis failure after a model is removed.  
**Verification:** Test — configure a non-existent model; start app; verify settings updated to available model

---

#### R011 — Emotion Window Defaults
**Category:** CFG  
**Statement:** The system shall default the emotion summary interval to 30 seconds, the minimum window to 20 seconds, and the minimum words threshold to 10 words.  
**Rationale:** These values represent the minimum meaningful emotion accumulation window for reliable LLM synthesis.  
**Verification:** Test — omit emotion settings; verify defaults applied

---

#### R012 — Emotion Window Validation
**Category:** CFG  
**Statement:** When saving settings, the system shall enforce that `emotion_window_seconds` is not less than `emotion_min_seconds`.  
**Rationale:** Prevents illogical configuration (window shorter than its own minimum).  
**Verification:** Test — post settings with window < min; verify window is clamped to min

---

#### R013 — STT Model Selection
**Category:** CFG  
**Statement:** The system shall accept any faster-whisper model name string as the `stt_model` configuration value and pass it to the whisper engine initialization.  
**Rationale:** Users require flexibility to balance accuracy against model download size.  
**Verification:** Test — set stt_model to "tiny"; verify engine initializes with correct model

---

#### R014 — Debug Mode Warning
**Category:** CFG  
**Statement:** When `enable_debug` is set to true, the system shall print a startup warning to stdout identifying the exact directory where plaintext transcripts will be written.  
**Rationale:** Users must be informed when their data is being stored unencrypted.  
**Verification:** Test — start app with enable_debug=true; verify warning printed to stdout

---

#### R015 — Settings Persistence
**Category:** CFG  
**Statement:** After a settings save operation, the system shall reload its configuration cache so that subsequent requests use the updated values without requiring a process restart.  
**Rationale:** Settings changes must take effect immediately.  
**Verification:** Test — save new auto_lock_minutes; verify new timeout applied to next session check

---

### 3.3 Authentication Requirements (AUTH)

---

#### R016 — Setup Key Generation
**Category:** AUTH  
**Statement:** The system shall generate a fresh ML-KEM-1024 keypair and a fresh X25519 keypair during the setup flow, save them to the user-specified key directory, and return a fingerprint of the public keys.  
**Rationale:** Key material must be generated fresh; reuse would undermine forward secrecy.  
**Verification:** Test — run setup; verify two key files exist in key_dir; verify fingerprint returned

---

#### R017 — Passphrase Minimum Length
**Category:** AUTH  
**Statement:** The system shall reject key generation passphrases shorter than 12 characters and return a user-visible error message.  
**Rationale:** Short passphrases provide insufficient protection for the key files.  
**Verification:** Test — submit 11-character passphrase; verify HTTP 200 with error message rendered

---

#### R018 — Passphrase Confirmation
**Category:** AUTH  
**Statement:** The system shall reject key generation when the passphrase and passphrase confirmation fields do not match, and shall return a user-visible error.  
**Rationale:** Prevents key files from being protected by an unintended passphrase.  
**Verification:** Test — submit mismatched passphrases; verify error rendered

---

#### R019 — Unlock Requires Journal and Key Directories
**Category:** AUTH  
**Statement:** The system shall require both a journal directory path and a key directory path to be provided at each login, and shall reject unlock attempts where either field is blank.  
**Rationale:** No path metadata is stored persistently; users must supply both locations each time.  
**Verification:** Test — submit unlock form with blank journal_dir; verify error returned

---

#### R020 — Key Presence Validation
**Category:** AUTH  
**Statement:** Before attempting decryption, the system shall verify that the specified key directory contains valid key files and return a specific error if no key files are found.  
**Rationale:** Provides early, actionable feedback before attempting expensive key derivation.  
**Verification:** Test — specify empty directory; verify "No key files found" error returned

---

#### R021 — Passphrase Authentication
**Category:** AUTH  
**Statement:** The system shall decrypt key files using PBKDF2-HMAC-SHA256 with the provided passphrase and return an authentication error if decryption fails.  
**Rationale:** The passphrase is the sole authentication credential.  
**Verification:** Test — supply wrong passphrase; verify authentication error returned

---

#### R022 — Journal Directory Initialization
**Category:** AUTH  
**Statement:** Upon successful authentication, the system shall create the journal entries directory and initialize the SQLite database if they do not already exist.  
**Rationale:** First-time login must provision all required storage before serving journal routes.  
**Verification:** Test — unlock with new journal_dir; verify entries/ dir and .db/journal.sqlite created

---

#### R023 — Session Cookie
**Category:** AUTH  
**Statement:** Upon successful authentication, the system shall issue an HttpOnly, SameSite=Strict session cookie named `pqj_session` with a maximum age of 86400 seconds.  
**Rationale:** HttpOnly prevents XSS exfiltration; SameSite prevents CSRF; 24h max supports overnight use.  
**Verification:** Test — unlock; inspect Set-Cookie header for required attributes

---

#### R024 — Lock Route
**Category:** AUTH  
**Statement:** Upon receiving a POST to `/lock`, the system shall destroy the active session, zero all in-memory key bytes, clear the database encryption key, delete the session cookie, and redirect to `/unlock`.  
**Rationale:** Explicit lock must leave no recoverable key material in process memory.  
**Verification:** Test — lock; verify session cookie deleted; verify subsequent journal request returns 401/redirect

---

#### R025 — Root Redirect
**Category:** AUTH  
**Statement:** A GET to `/` shall redirect authenticated users to `/journal` and unauthenticated users to `/unlock`.  
**Rationale:** Standard UX entry point.  
**Verification:** Test — GET / with and without valid session; verify redirect destinations

---

#### R026 — Removable Drive Detection
**Category:** AUTH  
**Statement:** The unlock page shall display a list of detected removable drives (USB drives) as quick-fill buttons for the key directory field.  
**Rationale:** Keys are typically stored on USB drives; auto-detection reduces input friction.  
**Verification:** Demonstration — insert USB drive; verify it appears as a button on the unlock page

---

#### R027 — Setup Default Journal Path
**Category:** AUTH  
**Statement:** The setup page shall pre-populate the journal directory field with `~/MeaningfulJournal` as the default suggested path.  
**Rationale:** Provides a sensible default for first-time users.  
**Verification:** Test — GET /setup; verify default_journal_dir equals Path.home() / "MeaningfulJournal"

---

### 3.4 Cryptography Requirements (CRYPT)

---

#### R028 — Post-Quantum Hybrid Encryption
**Category:** CRYPT  
**Statement:** The system shall encrypt journal entries using a hybrid scheme combining ML-KEM-1024 key encapsulation and X25519 ECDH, with shared secrets combined via HKDF-SHA256 and plaintext encrypted using AES-256-GCM.  
**Rationale:** Hybrid PQC provides security against both classical and quantum adversaries.  
**Verification:** Test — encrypt entry; inspect blob fields for kem_ct, x25519_ephemeral_pub, nonce, tag, ct

---

#### R029 — Authenticated Encryption
**Category:** CRYPT  
**Statement:** Every encrypted journal entry shall include an HMAC-SHA256 integrity tag computed over all ciphertext blob fields, and decryption shall fail with a ValueError if the HMAC verification fails.  
**Rationale:** Detects tampering or corruption before decryption succeeds.  
**Verification:** Test — flip a byte in the ciphertext blob; verify decryption raises ValueError

---

#### R030 — Ephemeral X25519 Keys
**Category:** CRYPT  
**Statement:** The system shall generate a fresh X25519 ephemeral keypair for each encryption operation and shall not reuse ephemeral keys.  
**Rationale:** Ephemeral keys provide forward secrecy for each entry.  
**Verification:** Test — encrypt two entries; verify x25519_ephemeral_pub fields differ

---

#### R031 — Key File PBKDF2
**Category:** CRYPT  
**Statement:** Key files shall be protected using PBKDF2-HMAC-SHA256 with a minimum of 600,000 iterations and a 32-byte random salt unique per key file.  
**Rationale:** 600,000 iterations provides approximately 0.5–1 second per attempt on modern hardware, making brute-force attacks costly.  
**Verification:** Inspection — read key file; verify iteration count in header; test wrong passphrase timing

---

#### R032 — Key File Format Versioning
**Category:** CRYPT  
**Statement:** Key files shall include a version identifier (`v=2`) and the system shall reject key files with unknown version identifiers.  
**Rationale:** Allows future key file format upgrades while preventing silent misinterpretation.  
**Verification:** Test — create key file with v=99; verify load raises ValueError

---

#### R033 — AES-GCM Nonce Uniqueness
**Category:** CRYPT  
**Statement:** Each AES-256-GCM encryption operation shall use a randomly generated 12-byte nonce, and the system shall not reuse nonces.  
**Rationale:** AES-GCM nonce reuse catastrophically weakens confidentiality.  
**Verification:** Test — encrypt 100 entries; verify all nonces are unique

---

#### R034 — HKDF Key Derivation
**Category:** CRYPT  
**Statement:** The combined encryption key for each entry shall be derived using HKDF-SHA256 with the domain separation string `"pq-journal-entry"` and a 32-byte (256-bit) output length.  
**Rationale:** Domain separation prevents cross-context key reuse.  
**Verification:** Inspection — read crypto.py; verify HKDF info parameter and length

---

#### R035 — Database Key Derivation
**Category:** CRYPT  
**Statement:** The SQLite column encryption key shall be derived from the session private keys using HKDF-SHA256 with domain string `"pq-journal-db-v1"` and shall never be stored on disk.  
**Rationale:** Ties database access to possession of the private keys; lost keys mean lost DB access.  
**Verification:** Test — lock app; verify _db_encryption_key module variable is None

---

#### R036 — Column-Level Database Encryption
**Category:** CRYPT  
**Statement:** The `title`, `tags`, `emotion_label`, and `emotion_scores` columns in the JournalEntry table shall be encrypted with AES-256-GCM using the session-derived key; the `id`, `created_at`, `modified_at`, `file_name`, and `word_count` columns shall be stored in plaintext.  
**Rationale:** Encrypted metadata prevents reading journal titles without keys while allowing lightweight queries on non-sensitive fields.  
**Verification:** Test — write entry; read raw SQLite file; verify title column not readable as plaintext

---

#### R037 — Entry File Permissions
**Category:** CRYPT  
**Statement:** Encrypted entry files (`.pqj`) shall be created with filesystem permissions `0o600` (owner read/write only).  
**Rationale:** Prevents other local users from reading encrypted files even without the keys.  
**Verification:** Test — create entry; stat file; verify mode is 0o600

---

#### R038 — Constant-Time HMAC Comparison
**Category:** CRYPT  
**Statement:** HMAC verification during entry decryption shall use `hmac.compare_digest()` for constant-time comparison.  
**Rationale:** Prevents timing oracle attacks that could reveal information about the HMAC.  
**Verification:** Inspection — read crypto.py decryption; verify compare_digest used

---

### 3.5 Session Management Requirements (SESS)

---

#### R039 — In-Memory Sessions Only
**Category:** SESS  
**Statement:** Session data, including all private key bytes, shall be stored exclusively in process memory and shall never be written to disk, database, or any persistent storage.  
**Rationale:** Prevents session recovery after app restart or process inspection.  
**Verification:** Inspection + Test — verify no session data written to any file during normal operation

---

#### R040 — Session Key Zeroing
**Category:** SESS  
**Statement:** Upon session destruction (lock, timeout, or app shutdown), the system shall overwrite all session key bytes with zeros using `ctypes.memset()` before releasing memory.  
**Rationale:** Reduces window for memory forensics to extract private keys.  
**Verification:** Test — lock app; verify SessionData.zero_keys() called; inspect bytearray contents are zeroed

---

#### R041 — Idle Timeout Detection
**Category:** SESS  
**Statement:** The system shall track session idle time using a monotonic clock and shall invalidate any session that has been idle longer than `auto_lock_minutes`.  
**Rationale:** Monotonic clock prevents session extension via system clock manipulation.  
**Verification:** Test — set timeout to 1 minute; wait 61 seconds idle; verify next request redirects to /unlock

---

#### R042 — Background Session Sweep
**Category:** SESS  
**Statement:** The system shall run a background task that checks for and removes expired sessions every 60 seconds.  
**Rationale:** Ensures sessions expire even without incoming requests (e.g., laptop left open).  
**Verification:** Test — create session with 1-minute timeout; wait 2 minutes; verify session removed

---

#### R043 — Signed Session Tokens
**Category:** SESS  
**Statement:** Session tokens shall be cryptographically signed using a process-level secret key, and the system shall reject tokens with invalid signatures or tokens older than 24 hours.  
**Rationale:** Prevents session token forgery or replay of old tokens.  
**Verification:** Test — tamper with session cookie value; verify 401/redirect response

---

#### R044 — Session Destroyed on Last Logout
**Category:** SESS  
**Statement:** When the last active session is destroyed, the system shall clear the database encryption key from process memory.  
**Rationale:** Ensures the database becomes unreadable when no authenticated session exists.  
**Verification:** Test — lock app with single session; verify db encryption key cleared

---

#### R045 — HTMX Session Expiry
**Category:** SESS  
**Statement:** When a session-expired response is detected on an HTMX request, the system shall return a JSON response with `HX-Redirect: /unlock` header rather than an HTML redirect.  
**Rationale:** HTMX partial requests require redirect headers in JSON, not full HTML redirects.  
**Verification:** Test — expire session; make HTMX request; verify HX-Redirect header present in 401 response

---

#### R046 — Client-Side Session Ping
**Category:** SESS  
**Statement:** Authenticated pages shall ping `/api/ping` every 60 seconds and redirect to `/unlock` if the response indicates session expiry.  
**Rationale:** Browser tabs left overnight or with lid-close would otherwise serve stale session state.  
**Verification:** Test — verify ping request sent; mock 401 response; verify redirect to /unlock

---

### 3.6 Journal Entry Requirements (ENTRY)

---

#### R047 — Entry Creation
**Category:** ENTRY  
**Statement:** The system shall create a new journal entry with a unique UUID, timestamp, title, body, tags, and optional emotion data, storing it as an encrypted `.pqj` file and a corresponding database record.  
**Rationale:** Dual storage (file + DB) supports both full content access and indexed metadata queries.  
**Verification:** Test — POST /journal; verify .pqj file exists and DB record created

---

#### R048 — Entry UUID
**Category:** ENTRY  
**Statement:** Each journal entry shall be assigned a UUID (version 4) as its primary identifier, used for both the `.pqj` filename and the database primary key.  
**Rationale:** UUIDs prevent enumeration attacks and collision in large journals.  
**Verification:** Test — create two entries; verify IDs are valid UUID4 strings and differ

---

#### R049 — Entry Timestamps
**Category:** ENTRY  
**Statement:** The system shall record timezone-aware creation and modification timestamps for each entry, preserving the original `created_at` timestamp across edits.  
**Rationale:** Journal entries have a specific time of authorship that must not be updated on edit.  
**Verification:** Test — create entry; edit entry; verify created_at unchanged; verify modified_at updated

---

#### R050 — Entry Autosave
**Category:** ENTRY  
**Statement:** The system shall support an autosave operation that creates a new entry if no ID is provided, or updates an existing entry if an ID is provided, returning the entry ID and save timestamp.  
**Rationale:** Prevents data loss from accidental browser closure.  
**Verification:** Test — POST /journal/autosave without ID; verify entry created; POST again with ID; verify updated

---

#### R051 — Entry Word Count
**Category:** ENTRY  
**Statement:** The system shall compute and store the word count for each entry as a whitespace-split token count and update it on every save operation.  
**Rationale:** Word count is a useful non-sensitive metric that can be stored unencrypted.  
**Verification:** Test — create entry with known text; verify word_count matches expected value

---

#### R052 — Entry Tags
**Category:** ENTRY  
**Statement:** The system shall parse entry tags as a comma-separated list, trim whitespace from each tag, and store them as an encrypted JSON array.  
**Rationale:** Simple tag parsing without requiring structured input.  
**Verification:** Test — create entry with tags "  work, home , "; verify stored as ["work", "home"]

---

#### R053 — Entry Read and Decrypt
**Category:** ENTRY  
**Statement:** When viewing or editing an entry, the system shall decrypt the `.pqj` file on demand using the session private keys and return the plaintext content.  
**Rationale:** Entries remain encrypted at rest and are only decrypted in memory during access.  
**Verification:** Test — view entry; verify decrypted body matches original

---

#### R054 — Entry Delete
**Category:** ENTRY  
**Statement:** When an entry is deleted, the system shall remove both the `.pqj` file and the database record.  
**Rationale:** Full deletion must remove all evidence of the entry.  
**Verification:** Test — delete entry; verify .pqj file absent; verify DB record absent

---

#### R055 — Search Across Encrypted Entries
**Category:** ENTRY  
**Statement:** The system shall support full-text search across encrypted entries by decrypting entry bodies on-the-fly during search, streaming results as Server-Sent Events with progress updates.  
**Rationale:** Encrypted-at-rest search without a plaintext search index.  
**Verification:** Test — create entries with known text; search for substring; verify matching entry returned in SSE stream

---

#### R056 — Search Metadata Priority
**Category:** ENTRY  
**Statement:** During search, the system shall check encrypted metadata fields (title, tags, emotion_label) before decrypting the entry body, and shall only decrypt the body if no metadata match is found.  
**Rationale:** Minimizes decryption operations for performance.  
**Verification:** Test — search for entry title; verify entry returned without body decryption (single-file journal, SSE returns quickly)

---

#### R057 — Markdown Export
**Category:** ENTRY  
**Statement:** The system shall export any journal entry as a GitHub-flavored Markdown file including metadata (date, tags, emotion) and per-paragraph emotion annotations, delivered as a file download.  
**Rationale:** Standard export format for long-term archival and portability.  
**Verification:** Test — export entry; verify Content-Disposition: attachment header; verify Markdown structure

---

#### R058 — PDF Export
**Category:** ENTRY  
**Statement:** When `weasyprint` is installed, the system shall export any journal entry as a formatted PDF file. When `weasyprint` is not installed, the system shall return a 400 response with installation instructions.  
**Rationale:** PDF is a common archival format; graceful degradation preserves core functionality.  
**Verification:** Test — export without weasyprint; verify 400 with instruction message; install weasyprint; verify PDF returned

---

#### R059 — Random Prompt
**Category:** ENTRY  
**Statement:** The system shall serve a random writing prompt from a user-overridable YAML prompts file, falling back to `"What do you want to explore today?"` if no prompts file is found.  
**Rationale:** Writing prompts support journaling practice.  
**Verification:** Test — GET /journal/prompts/random; verify non-empty text returned

---

#### R060 — Paragraph Emotion Analysis
**Category:** ENTRY  
**Statement:** The system shall analyze each paragraph of a journal entry body independently for emotional content, producing a per-paragraph emotion label and score distribution across seven emotion classes.  
**Rationale:** Per-paragraph analysis reveals emotional arc within a single entry.  
**Verification:** Test — analyze entry with two paragraphs; verify two paragraph objects with emotion_label and emotion_scores returned

---

### 3.7 Voice Recording Requirements (VOICE)

---

#### R061 — WebSocket Voice Recording
**Category:** VOICE  
**Statement:** The system shall accept raw 16-bit mono PCM audio at 16,000 Hz via WebSocket frames from the browser and buffer them for transcription.  
**Rationale:** Direct PCM streaming avoids server-side audio decoding overhead.  
**Verification:** Test — send PCM frames via WebSocket; verify buffering occurs

---

#### R062 — Silence-Triggered Transcription
**Category:** VOICE  
**Statement:** The system shall automatically trigger transcription when 16 consecutive audio frames (approximately 1 second) with RMS amplitude below 0.015 are received and the audio buffer contains at least 32,000 bytes (1 second of audio).  
**Rationale:** Automatic segmentation at natural speech pauses produces coherent transcription chunks.  
**Verification:** Test — send 1s of silence after speech; verify transcription triggered

---

#### R063 — Stop Command
**Category:** VOICE  
**Statement:** Upon receiving a `{"type": "stop"}` JSON message on the WebSocket, the system shall flush the remaining audio buffer, send a `vad_summary` message with session-average VAD values, and send a `{"type": "done"}` message.  
**Rationale:** Ensures final audio segment is transcribed and summary data is delivered.  
**Verification:** Test — send audio then stop; verify final transcript and vad_summary received before done

---

#### R064 — STT Engine Announcement
**Category:** VOICE  
**Statement:** Upon WebSocket connection, the system shall send a `{"type": "stt_engine", "engine": "..."}` message identifying the active transcription engine.  
**Rationale:** Allows the UI to display which engine is active.  
**Verification:** Test — connect to WebSocket; verify stt_engine message received as first message

---

#### R065 — VAD Streaming
**Category:** VOICE  
**Statement:** The system shall compute and transmit Valence, Arousal, and Dominance values to the client every 8 audio frames (approximately 500 milliseconds).  
**Rationale:** Near-real-time feedback enables live emotion visualization during recording.  
**Verification:** Test — stream audio; verify vad messages received at ~500ms intervals

---

#### R066 — Faster-Whisper Primary Engine
**Category:** VOICE  
**Statement:** When `faster-whisper` is installed, the system shall use it as the primary transcription engine with hallucination filtering (rejecting phrases like "thank you", "[music]") and VAD pre-filtering.  
**Rationale:** Whisper provides high-accuracy transcription; hallucination filtering removes common false positives.  
**Verification:** Test — transcribe silence with whisper; verify empty string returned (hallucination filtered)

---

#### R067 — Vosk Fallback Engine
**Category:** VOICE  
**Statement:** When `faster-whisper` is not installed but Vosk is configured, the system shall use Vosk as the transcription engine.  
**Rationale:** Vosk provides offline transcription when Whisper is unavailable.  
**Verification:** Test — uninstall faster-whisper; configure vosk_model_dir; verify vosk engine used

---

#### R068 — File Upload Transcription
**Category:** VOICE  
**Statement:** The system shall accept audio file uploads (WebM, MP3, WAV, OGG) via POST to `/voice/upload` and return a transcription and engine identifier, and shall reject this endpoint without a valid session.  
**Rationale:** Supports transcription of pre-recorded audio; authentication prevents unauthorized access.  
**Verification:** Test — POST audio file with and without session; verify transcript returned with session; 401 without

---

#### R069 — WebSocket Authentication
**Category:** VOICE  
**Statement:** The WebSocket recording endpoint shall authenticate the client using the session cookie before accepting the WebSocket upgrade, closing with code 4401 if no valid session exists.  
**Rationale:** Prevents unauthenticated access to the recording pipeline.  
**Verification:** Test — connect without session cookie; verify WebSocket closed with code 4401

---

### 3.8 Emotion Analysis Requirements (EMOT)

---

#### R070 — Live Emotion Synthesis
**Category:** EMOT  
**Statement:** The system shall accept averaged VAD values, an optional transcript, and an optional face emotion label via POST to `/emotion/live_summary` and return a synthesized 4–8 word emotional phrase.  
**Rationale:** Synthesizes multi-modal data into human-readable emotional context for live journaling.  
**Verification:** Test — POST with VAD values and transcript; verify phrase returned

---

#### R071 — LLM Emotion Synthesis
**Category:** EMOT  
**Statement:** When Ollama is available and the transcript meets the minimum word threshold, the system shall synthesize the emotion phrase using an LLM prompt that includes the transcript text, VAD values, and optional face emotion.  
**Rationale:** LLM synthesis produces more nuanced and contextually relevant phrases than rule-based fallback.  
**Verification:** Test — POST with sufficient transcript and running Ollama; verify LLM-sourced phrase returned

---

#### R072 — Rule-Based Fallback
**Category:** EMOT  
**Statement:** When Ollama is unavailable or times out, the system shall synthesize an emotion phrase using a rule-based algorithm mapping (V, A, D) values to predefined mood phrases.  
**Rationale:** Emotion display must never be blocked by external service unavailability.  
**Verification:** Test — mock Ollama timeout; verify fallback phrase returned

---

#### R073 — Minimum Transcript Words Guard
**Category:** EMOT  
**Statement:** The system shall not invoke the LLM for live emotion synthesis when the transcript buffer contains fewer than `emotion_min_words` words, but shall retain the unprocessed words in the buffer for the next synthesis window.  
**Rationale:** Prevents meaningless LLM calls on short utterances while preserving transcript continuity.  
**Verification:** Test — POST with 5-word transcript and min_words=10; verify no LLM called; verify transcript accumulates

---

#### R074 — Text Emotion Classification
**Category:** EMOT  
**Statement:** The system shall classify the emotional content of each paragraph into one of seven classes (joy, sadness, anger, fear, disgust, neutral, surprise) using HuggingFace DistilRoBERTa if available, Ollama if available, or a keyword heuristic as final fallback.  
**Rationale:** Three-tier fallback ensures classification always produces a result.  
**Verification:** Test — classify paragraph with each engine disabled progressively; verify result always returned

---

#### R075 — Facial Emotion Detection
**Category:** EMOT  
**Statement:** When `enable_webcam` is true and the required dependencies are installed, the system shall accept JPEG video frames via POST to `/emotion/video/frame`, detect faces using Haar cascade, and classify the dominant emotion using the loaded ResNet50 model.  
**Rationale:** Facial expression adds a third modality to emotion analysis.  
**Verification:** Test — POST JPEG frame with detectable face; verify emotion_label returned

---

#### R076 — No Face Response
**Category:** EMOT  
**Statement:** When a video frame contains no detectable face, the system shall return `{"emotion_label": "no face", "scores": {}}` without error.  
**Rationale:** No-face is a valid state during recording (user moved away from camera).  
**Verification:** Test — POST blank JPEG frame; verify "no face" label returned

---

#### R077 — Emotion Analysis Security
**Category:** EMOT  
**Statement:** The `/emotion/analyze` and `/emotion/live_summary` endpoints shall require a valid session and shall return 401 for unauthenticated requests.  
**Rationale:** Prevents unauthorized emotion analysis of user-supplied text.  
**Verification:** Test — POST to emotion endpoints without session; verify 401 returned

---

### 3.9 File Browser Requirements (FILE)

---

#### R078 — Server-Side Directory Browser
**Category:** FILE  
**Statement:** The system shall provide a server-side filesystem browser at `/api/browse` that returns the current directory path, parent directory path, and list of subdirectories for any requested path.  
**Rationale:** Allows users to navigate the server filesystem to locate key and journal directories without typing full paths.  
**Verification:** Test — GET /api/browse?path=/tmp; verify dirs, current, parent fields returned

---

#### R079 — Directory Name Validation
**Category:** FILE  
**Statement:** The `/api/mkdir` endpoint shall reject directory names containing `/`, `\`, `.`, or `..`, or that are empty, returning HTTP 400 with an error message.  
**Rationale:** Prevents directory traversal and creation of hidden or conflicting paths.  
**Verification:** Test — POST mkdir with name "../../etc"; verify 400 returned

---

#### R080 — Removable Drive Enumeration
**Category:** FILE  
**Statement:** The system shall enumerate removable drives (USB, external storage) across macOS (/Volumes/), Linux (/media/, /run/media/), and Windows (removable drive type) and return them via `/api/drives`.  
**Rationale:** USB-stored keys require easy drive selection.  
**Verification:** Test — mock psutil partitions with removable flag; verify drive returned

---

#### R081 — Debug Log Save Authentication
**Category:** FILE  
**Statement:** The `/api/debug/save` endpoint shall require a valid authenticated session and shall sanitize filenames to contain only alphanumeric characters, hyphens, underscores, and periods.  
**Rationale:** Prevents path traversal via filename injection; authentication prevents unauthorized writes.  
**Verification:** Test — POST with filename "../../../etc/evil"; verify sanitized filename used; verify 401 without session

---

#### R082 — Status Endpoint
**Category:** FILE  
**Statement:** The `/api/status` endpoint shall return the current active STT engine, emotion classifier engine, Ollama availability (including model test), HuggingFace availability, and emotion timing settings.  
**Rationale:** Single endpoint for UI engine status display.  
**Verification:** Test — GET /api/status; verify all required fields present in response

---

### 3.10 Settings Requirements (SET)

---

#### R083 — Settings Page Authentication
**Category:** SET  
**Statement:** The settings page and settings save endpoint shall require a valid authenticated session.  
**Rationale:** Settings modification requires authentication.  
**Verification:** Test — GET/POST /settings without session; verify redirect to /unlock

---

#### R084 — Settings Display
**Category:** SET  
**Statement:** The settings page shall display the current journal directory, key directory, active STT engine, active emotion engine, and Ollama connectivity status.  
**Rationale:** Users need a single view of system status alongside configurable settings.  
**Verification:** Test — GET /settings with authenticated session; verify journal_dir and key_dir displayed

---

#### R085 — Debug Mode Warning UI
**Category:** SET  
**Statement:** The settings page shall display a confirmation dialog before enabling debug mode, and when debug is enabled, shall display a persistent red warning banner showing the exact path where plaintext transcripts will be written.  
**Rationale:** Users must be explicitly warned before enabling insecure behavior.  
**Verification:** Inspection — read settings template; verify confirm dialog and conditional red banner

---

### 3.11 Security Requirements (SEC)

---

#### R086 — No Swagger/ReDoc
**Category:** SEC  
**Statement:** The system shall disable Swagger UI and ReDoc API documentation endpoints in all deployment configurations.  
**Rationale:** API documentation exposes endpoint structure and facilitates automated attacks.  
**Verification:** Test — GET /docs and /redoc; verify 404 returned

---

#### R087 — Authenticated Journal Routes
**Category:** SEC  
**Statement:** All journal, voice, emotion, and settings routes shall require a valid authenticated session and shall redirect unauthenticated requests to `/unlock`.  
**Rationale:** All user data routes must be protected.  
**Verification:** Test — request each protected route without session; verify redirect to /unlock

---

#### R088 — Input Sanitization for File Paths
**Category:** SEC  
**Statement:** Server-side filesystem operations initiated by user input (browse, mkdir) shall resolve paths to absolute form before use and shall not allow traversal outside the filesystem root.  
**Rationale:** Prevents directory traversal attacks.  
**Verification:** Test — request browse with path "../../../../etc"; verify response contains valid absolute path

---

#### R089 — No Plaintext Key Storage
**Category:** SEC  
**Statement:** Private key material shall never be written to disk in plaintext form; key files on disk shall always be encrypted with PBKDF2-HMAC-SHA256 + AES-256-GCM.  
**Rationale:** Prevents key recovery from disk forensics.  
**Verification:** Inspection — read key files; verify they contain only encrypted fields

---

#### R090 — No Plaintext Entry Storage
**Category:** SEC  
**Statement:** Journal entry content shall never be written to disk in plaintext form except when `enable_debug` is explicitly true.  
**Rationale:** Prevents content recovery without the passphrase.  
**Verification:** Test — create entry with debug=false; verify no plaintext version exists anywhere on disk

---

#### R091 — Ollama Timeout Enforcement
**Category:** SEC  
**Statement:** All outbound HTTP requests to the Ollama endpoint shall enforce explicit timeouts: 3 seconds for model availability checks, 1.5 seconds for ping checks, 8 seconds for model generation calls.  
**Rationale:** Prevents LLM slowness from blocking journal operations.  
**Verification:** Test — configure Ollama to a non-responsive host; verify requests fail within stated timeouts

---

#### R092 — Debug Mode Default Off
**Category:** SEC  
**Statement:** The `enable_debug` setting shall default to `false` and shall require explicit user confirmation to enable via the settings UI.  
**Rationale:** Insecure behavior must be opt-in, not opt-out.  
**Verification:** Test — initialize with no settings file; verify enable_debug is False

---

#### R101 — Pre-Authentication API Origin Validation
**Category:** SEC  
**Statement:** The filesystem browser endpoints (`/api/browse`, `/api/mkdir`, `/api/drives`, `/api/home`) shall reject any request where the `Origin` header is present but does not match the application's configured host and port, returning HTTP 403 Forbidden.  
**Rationale:** These endpoints operate before authentication and can enumerate the local filesystem. A malicious website running while the app is open can make background fetch requests to localhost; the `Origin` header distinguishes same-app requests from cross-origin attacks. Direct API calls (no `Origin` header, e.g., curl) are permitted.  
**Verification:** Test — make request to /api/browse with Origin: https://evil.com; verify 403 returned. Make same request with Origin: http://localhost:8000; verify 200 returned.

---

#### R102 — Authenticated Status Endpoint
**Category:** SEC  
**Statement:** The `/api/status` endpoint shall require a valid authenticated session and shall return HTTP 401 for unauthenticated requests.  
**Rationale:** Engine version and configuration data (Ollama model name, STT engine) aids attacker reconnaissance. Restricting to authenticated sessions limits exposure.  
**Verification:** Test — GET /api/status without session; verify 401 returned. GET with valid session; verify 200 returned.

---

#### R103 — Unlock Attempt Rate Limiting
**Category:** SEC  
**Statement:** The `/unlock` POST endpoint shall enforce a minimum 2-second processing delay after each failed authentication attempt. After 10 failed attempts from the same source within any 5-minute window, the system shall return HTTP 429 Too Many Requests until the window expires.  
**Rationale:** Without rate limiting, a local script or malware can attempt thousands of passphrase guesses per second. A 2-second delay reduces the attempt rate to 30/minute; the 429 lockout caps total attempts to 10 per 5 minutes per source.  
**Verification:** Test — submit 11 failed unlock attempts in sequence; verify 429 returned on 11th attempt; verify each failed attempt takes ≥ 2 seconds to respond.

---

#### R104 — HTTP Security Response Headers
**Category:** SEC  
**Statement:** All HTTP responses shall include the following headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and a `Content-Security-Policy` restricting script sources to `'self'`, `cdn.tailwindcss.com`, and `unpkg.com`; style sources to `'self'` and `fonts.googleapis.com`; font sources to `fonts.gstatic.com`; and connection sources to `'self'` and WebSocket localhost.  
**Rationale:** `nosniff` prevents MIME-type confusion attacks; `X-Frame-Options: DENY` prevents clickjacking; CSP restricts script and data exfiltration vectors to known-good origins.  
**Verification:** Test — GET /unlock; verify all three headers present in response with correct values.

---

#### R105 — LLM Prompt Injection Defense
**Category:** SEC  
**Statement:** All user-supplied text (journal content, voice transcripts) included in LLM prompts shall be enclosed in `<user_content>` XML delimiter tags, and each prompt shall explicitly instruct the model to treat content within those tags as data only and to ignore any instructions embedded within them.  
**Rationale:** Without delimiters, a user (or their journal content) could embed instructions that override the intended LLM behavior ("jailbreaking"), potentially producing unexpected or harmful LLM outputs.  
**Verification:** Inspection — read LLM prompt templates in llm.py; verify user content is wrapped in `<user_content>` tags and prompt includes injection-defense instruction.

---

#### R106 — Windows Key File Permission Advisory
**Category:** SEC  
**Statement:** On Windows systems, after writing key files to disk, the system shall emit a console warning that Unix file permissions (`0o600`) are not enforced by the OS and that the user must manually restrict access to the key directory using Windows ACLs or folder permissions.  
**Rationale:** `os.chmod` silently succeeds on Windows but has no security effect, leaving key files potentially readable by other local user accounts. The advisory ensures Windows users are not misled into believing files are protected.  
**Verification:** Test — mock `platform.system()` to return "Windows"; write a key file; verify warning message printed.

---

### 3.12 Performance Requirements (PERF)

---

#### R093 — Search Streaming
**Category:** PERF  
**Statement:** The search endpoint shall stream results progressively as Server-Sent Events, yielding control after processing each entry, rather than waiting for all entries to be processed before responding.  
**Rationale:** Prevents timeout and UI blocking on large journals.  
**Verification:** Test — search across 50 entries; verify SSE events arrive incrementally before all entries processed

---

#### R094 — Non-Blocking STT Initialization
**Category:** PERF  
**Statement:** Speech-to-text engine initialization, including model download, shall occur asynchronously in a thread pool executor and shall not block application startup or request handling.  
**Rationale:** Whisper model downloads (500MB–3GB) must not prevent the app from serving requests.  
**Verification:** Test — cold-start app; verify /unlock serves within 5 seconds despite STT not ready

---

#### R095 — Non-Blocking Emotion Initialization
**Category:** PERF  
**Statement:** Emotion classifier and facial recognition model initialization shall occur asynchronously and shall not block application startup.  
**Rationale:** Large model downloads must not delay serving the unlock page.  
**Verification:** Test — cold-start app; verify /unlock serves within 5 seconds despite emotion models not ready

---

#### R096 — VAD Update Frequency
**Category:** PERF  
**Statement:** The system shall deliver VAD updates to the client at a minimum rate of one update per 500 milliseconds during active recording.  
**Rationale:** Sub-second updates enable smooth live emotion visualization.  
**Verification:** Test — record 5 seconds; verify at least 8 vad messages received

---

#### R097 — Database Re-initialization Safety
**Category:** PERF  
**Statement:** The `init_db()` function shall dispose of any existing database engine before creating a new one, ensuring safe re-use across multiple login sessions.  
**Rationale:** Prevents connection leaks when a user logs in multiple times during a process lifecycle.  
**Verification:** Test — call init_db() twice; verify no connection pool errors; verify second call succeeds

---

#### R098 — Settings Cache Invalidation
**Category:** PERF  
**Statement:** The settings cache shall be invalidated immediately after any settings write operation, so that the next request reads the updated values.  
**Rationale:** Stale cache would cause settings changes to silently not apply.  
**Verification:** Test — save settings; read settings in same process; verify updated values returned

---

#### R099 — Audio Buffer Minimum
**Category:** PERF  
**Statement:** The system shall not attempt transcription of audio buffers smaller than 32,000 bytes (equivalent to 1 second of audio at 16kHz, 16-bit).  
**Rationale:** Transcribing very short fragments produces poor results and wastes compute.  
**Verification:** Test — send 15,000 bytes of audio then silence; verify transcription not triggered

---

#### R100 — Waveform Visualization
**Category:** PERF  
**Statement:** The browser-side recording interface shall display a real-time audio waveform visualization updated at a minimum rate of 5 Hz (one bar per ~187 milliseconds) during active recording.  
**Rationale:** Visual feedback confirms microphone is active and capturing audio.  
**Verification:** Demonstration — start recording; observe waveform updates in real time

---

## 4. Requirements Traceability Summary

| ID | Category | Short Title | Verification |
|----|----------|-------------|--------------|
| R001 | SYS | Local-Only Deployment | Inspection |
| R002 | SYS | Graceful Degradation | Test |
| R003 | SYS | Single-User Process | Inspection |
| R004 | SYS | Startup Without Journal Path | Test |
| R005 | SYS | Error Pages | Test |
| R006 | CFG | Settings Hierarchy | Test |
| R007 | CFG | Journal Settings Isolation | Inspection |
| R008 | CFG | Default Session Timeout | Test |
| R009 | CFG | Configurable Session Timeout | Test |
| R010 | CFG | Ollama Auto-Detection | Test |
| R011 | CFG | Emotion Window Defaults | Test |
| R012 | CFG | Emotion Window Validation | Test |
| R013 | CFG | STT Model Selection | Test |
| R014 | CFG | Debug Mode Warning | Test |
| R015 | CFG | Settings Persistence | Test |
| R016 | AUTH | Setup Key Generation | Test |
| R017 | AUTH | Passphrase Minimum Length | Test |
| R018 | AUTH | Passphrase Confirmation | Test |
| R019 | AUTH | Unlock Requires Both Directories | Test |
| R020 | AUTH | Key Presence Validation | Test |
| R021 | AUTH | Passphrase Authentication | Test |
| R022 | AUTH | Journal Directory Initialization | Test |
| R023 | AUTH | Session Cookie | Test |
| R024 | AUTH | Lock Route | Test |
| R025 | AUTH | Root Redirect | Test |
| R026 | AUTH | Removable Drive Detection | Demonstration |
| R027 | AUTH | Setup Default Journal Path | Test |
| R028 | CRYPT | Post-Quantum Hybrid Encryption | Test |
| R029 | CRYPT | Authenticated Encryption | Test |
| R030 | CRYPT | Ephemeral X25519 Keys | Test |
| R031 | CRYPT | Key File PBKDF2 | Inspection |
| R032 | CRYPT | Key File Format Versioning | Test |
| R033 | CRYPT | AES-GCM Nonce Uniqueness | Test |
| R034 | CRYPT | HKDF Key Derivation | Inspection |
| R035 | CRYPT | Database Key Derivation | Test |
| R036 | CRYPT | Column-Level Database Encryption | Test |
| R037 | CRYPT | Entry File Permissions | Test |
| R038 | CRYPT | Constant-Time HMAC | Inspection |
| R039 | SESS | In-Memory Sessions Only | Inspection |
| R040 | SESS | Session Key Zeroing | Test |
| R041 | SESS | Idle Timeout Detection | Test |
| R042 | SESS | Background Session Sweep | Test |
| R043 | SESS | Signed Session Tokens | Test |
| R044 | SESS | DB Key Cleared on Last Logout | Test |
| R045 | SESS | HTMX Session Expiry | Test |
| R046 | SESS | Client-Side Session Ping | Test |
| R047 | ENTRY | Entry Creation | Test |
| R048 | ENTRY | Entry UUID | Test |
| R049 | ENTRY | Entry Timestamps | Test |
| R050 | ENTRY | Entry Autosave | Test |
| R051 | ENTRY | Entry Word Count | Test |
| R052 | ENTRY | Entry Tags | Test |
| R053 | ENTRY | Entry Read and Decrypt | Test |
| R054 | ENTRY | Entry Delete | Test |
| R055 | ENTRY | Search Encrypted Entries | Test |
| R056 | ENTRY | Search Metadata Priority | Test |
| R057 | ENTRY | Markdown Export | Test |
| R058 | ENTRY | PDF Export | Test |
| R059 | ENTRY | Random Prompt | Test |
| R060 | ENTRY | Paragraph Emotion Analysis | Test |
| R061 | VOICE | WebSocket Voice Recording | Test |
| R062 | VOICE | Silence-Triggered Transcription | Test |
| R063 | VOICE | Stop Command | Test |
| R064 | VOICE | STT Engine Announcement | Test |
| R065 | VOICE | VAD Streaming | Test |
| R066 | VOICE | Faster-Whisper Engine | Test |
| R067 | VOICE | Vosk Fallback | Test |
| R068 | VOICE | File Upload Transcription | Test |
| R069 | VOICE | WebSocket Authentication | Test |
| R070 | EMOT | Live Emotion Synthesis | Test |
| R071 | EMOT | LLM Emotion Synthesis | Test |
| R072 | EMOT | Rule-Based Fallback | Test |
| R073 | EMOT | Min Transcript Words Guard | Test |
| R074 | EMOT | Text Emotion Classification | Test |
| R075 | EMOT | Facial Emotion Detection | Demonstration |
| R076 | EMOT | No Face Response | Test |
| R077 | EMOT | Emotion Analysis Security | Test |
| R078 | FILE | Server-Side Directory Browser | Test |
| R079 | FILE | Directory Name Validation | Test |
| R080 | FILE | Removable Drive Enumeration | Test |
| R081 | FILE | Debug Log Save Authentication | Test |
| R082 | FILE | Status Endpoint | Test |
| R083 | SET | Settings Page Authentication | Test |
| R084 | SET | Settings Display | Test |
| R085 | SET | Debug Mode Warning UI | Inspection |
| R086 | SEC | No Swagger/ReDoc | Test |
| R087 | SEC | Authenticated Journal Routes | Test |
| R088 | SEC | Input Sanitization for Paths | Test |
| R089 | SEC | No Plaintext Key Storage | Inspection |
| R090 | SEC | No Plaintext Entry Storage | Test |
| R091 | SEC | Ollama Timeout Enforcement | Test |
| R092 | SEC | Debug Mode Default Off | Test |
| R101 | SEC | Pre-Auth API Origin Validation | Test |
| R102 | SEC | Authenticated Status Endpoint | Test |
| R103 | SEC | Unlock Rate Limiting | Test |
| R104 | SEC | HTTP Security Headers | Test |
| R105 | SEC | LLM Prompt Injection Defense | Inspection |
| R106 | SEC | Windows Key Permission Advisory | Test |
| R093 | PERF | Search Streaming | Test |
| R094 | PERF | Non-Blocking STT Init | Test |
| R095 | PERF | Non-Blocking Emotion Init | Test |
| R096 | PERF | VAD Update Frequency | Test |
| R097 | PERF | Database Re-initialization Safety | Test |
| R098 | PERF | Settings Cache Invalidation | Test |
| R099 | PERF | Audio Buffer Minimum | Test |
| R100 | PERF | Waveform Visualization | Demonstration |

---

*End of PQJ-SRS-001 v1.0*
