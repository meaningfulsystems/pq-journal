/**
 * Voice recorder — AudioWorklet → raw PCM Int16 → WebSocket → server
 * Server sends back: {type:"partial"|"final"|"vad"|"emotion", ...}
 */

let ws = null;
let audioContext = null;
let mediaStream = null;
let workletNode = null;
let isRecording = false;

// Emotion window — collect VAD then request a rich LLM summary
// Defaults (overridden from /api/status at recording start): 30s window, 20s min, 10 word min
let _emotionWindowReadings = 60;  // readings × ~500ms = seconds (60 = 30s)
let _emotionMinWords = 10;
let _emotionWindow = []; // each entry: {V, A, D}

// Latest emotion state
let _lastLlmEmotionText = '';  // most recent LLM synthesis text
let _latestVad = { V: 0, A: 0, D: 0 };
let _latestVadLabel = '';
let _transcriptBuffer = '';    // accumulates transcript text since last live_summary call
let _emotionTagTimer = null;   // 2s silence guard before appending emotion tag

// Textarea grow state
let _taOrigHeight = 0;

// Ticker state
let _tickerPixelOffset = 0;    // how far ticker has scrolled left (px)
let _tickerLastUpdateTime = 0; // timestamp of last staged text update
let _tickerPendingText = '';   // next text, applied only when current pass loops
const TICKER_UPDATE_INTERVAL_MS = 5000; // stage a new text at most every 5s
const TICKER_SPEED_PX_PER_FRAME = 0.3;  // ~18px/s at 60fps, matches waveform

// Waveform state — rolling RMS history
const WAVEFORM_HISTORY = 180; // number of bars visible
const WAVEFORM_FRAME_SKIP = 3; // push one bar every N audio frames (~187ms per bar, ~33s full scroll)
let waveformHistory = new Float32Array(WAVEFORM_HISTORY).fill(0);
let waveformFrameCount = 0;

async function toggleRecording() {
  if (isRecording) {
    await stopRecording();
  } else {
    await startRecording();
  }
}

async function startRecording() {
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: {
      sampleRate: 16000,
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
    }});
  } catch (err) {
    alert('Microphone access denied: ' + err.message);
    return;
  }

  // Open WebSocket
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${proto}//${location.host}/ws/record`);
  ws.binaryType = 'arraybuffer';

  ws.onopen = () => {
    isRecording = true;
    setRecordingUI(true);
    startAudioWorklet();
    _fetchAndShowEngineStatus();
    // Capture textarea natural height for auto-grow
    const ta = document.getElementById('entry-body');
    if (ta) _taOrigHeight = ta.scrollHeight;
    if (typeof dbg === 'function') dbg('WebSocket opened. Recording started.');
    if (typeof onRecordingStart === 'function') onRecordingStart();
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleServerMessage(msg);
    } catch (e) {
      if (typeof dbg === 'function') dbg('WS message parse error: ' + e);
    }
  };

  ws.onclose = ws.onerror = () => {
    if (typeof dbg === 'function') dbg('WebSocket closed/error.');
    if (isRecording) stopRecording();
  };
}

async function startAudioWorklet() {
  audioContext = new AudioContext({ sampleRate: 16000 });

  // Register inline AudioWorklet processor
  const processorCode = `
    class PCMProcessor extends AudioWorkletProcessor {
      constructor() { super(); this._buf = []; }
      process(inputs) {
        const ch = inputs[0]?.[0];
        if (!ch) return true;
        // Accumulate ~62.5ms worth of samples (1000 samples at 16kHz)
        for (let s of ch) this._buf.push(s);
        if (this._buf.length >= 1000) {
          this.port.postMessage(new Float32Array(this._buf.splice(0, 1000)));
        }
        return true;
      }
    }
    registerProcessor('pcm-processor', PCMProcessor);
  `;

  const blob = new Blob([processorCode], { type: 'application/javascript' });
  const url = URL.createObjectURL(blob);
  await audioContext.audioWorklet.addModule(url);
  URL.revokeObjectURL(url);

  const source = audioContext.createMediaStreamSource(mediaStream);
  workletNode = new AudioWorkletNode(audioContext, 'pcm-processor');

  workletNode.port.onmessage = (event) => {
    const float32 = event.data;
    // Compute RMS amplitude for this frame and push to scrolling history
    let sum = 0;
    for (let i = 0; i < float32.length; i++) sum += float32[i] * float32[i];
    const rms = Math.sqrt(sum / float32.length);
    waveformFrameCount++;
    if (waveformFrameCount % WAVEFORM_FRAME_SKIP === 0) {
      waveformHistory.copyWithin(0, 1);
      waveformHistory[WAVEFORM_HISTORY - 1] = Math.min(1, rms * 6); // 6x gain boost
    }

    if (ws && ws.readyState === WebSocket.OPEN) {
      // Convert float32 → int16
      const int16 = new Int16Array(float32.length);
      for (let i = 0; i < float32.length; i++) {
        int16[i] = Math.max(-32768, Math.min(32767, float32[i] * 32768));
      }
      ws.send(int16.buffer);
    }
  };

  source.connect(workletNode);
  workletNode.connect(audioContext.destination);

  // Reset ticker scroll position
  _tickerPixelOffset = 0;

  // Start waveform animation
  requestAnimationFrame(animateWaveform);
}

async function stopRecording() {
  isRecording = false;
  setRecordingUI(false);
  if (typeof onRecordingStop === 'function') onRecordingStop();

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'stop' }));
    // Give server a moment to send final transcript
    await new Promise(r => setTimeout(r, 500));
    ws.close();
  }

  waveformHistory.fill(0);
  waveformFrameCount = 0;
  _emotionWindow = [];
  _transcriptBuffer = '';
  if (_emotionTagTimer) { clearTimeout(_emotionTagTimer); _emotionTagTimer = null; }
  _taOrigHeight = 0;
  _tickerPixelOffset = 0;
  _tickerPendingText = '';
  if (workletNode) { workletNode.disconnect(); workletNode = null; }
  if (audioContext) { await audioContext.close(); audioContext = null; }
  if (mediaStream) { mediaStream.getTracks().forEach(t => t.stop()); mediaStream = null; }

  // Hide ticker when not recording
  const tickerWrap = document.getElementById('emotion-ticker-wrap');
  if (tickerWrap) tickerWrap.classList.add('hidden');

  ws = null;
}

function _buildEmotionTag() {
  // Only build a tag when we have an actual LLM result — skip fallback phrases
  if (!_lastLlmEmotionText) return '';
  const v = _latestVad;
  const voicePart = `voice V:${v.V.toFixed(2)} A:${v.A.toFixed(2)} D:${v.D.toFixed(2)}`;

  let videoPart = '';
  if (typeof _faceScores === 'function') {
    const scores = _faceScores();
    const entries = Object.entries(scores);
    if (entries.length > 0) {
      const scoreStr = entries.map(([em, s]) => `${em}:${s.toFixed(2)}`).join(' ');
      videoPart = ` {video ${scoreStr}}`;
    }
  }

  return `[Emotion summary: ${_lastLlmEmotionText} {${voicePart}}${videoPart}]`;
}

function _growAndScrollTextarea(ta) {
  // Capture original height on first call (rows="20" natural height)
  if (!_taOrigHeight) _taOrigHeight = ta.scrollHeight;
  const maxH = _taOrigHeight * 2;
  ta.style.height = 'auto';
  ta.style.height = Math.min(ta.scrollHeight, maxH) + 'px';
  ta.style.overflowY = ta.scrollHeight >= maxH ? 'auto' : 'hidden';
  ta.scrollTop = ta.scrollHeight; // always show bottom
}

async function _fetchAndShowEngineStatus() {
  const statusRow = document.getElementById('engine-status');
  if (!statusRow) return;
  try {
    const res = await fetch('/api/status');
    const data = await res.json();

    const _badge = (id, label, active) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.textContent = label;
      el.className = `px-1.5 py-0.5 rounded border font-mono text-xs ${
        active ? 'border-green-800 text-green-400' : 'border-red-900 text-red-400'
      }`;
    };

    // Apply emotion timing settings from server config
    const minSec = data.emotion_min_seconds || 20;
    const windowSec = Math.max(minSec, data.emotion_window_seconds || 30);
    _emotionWindowReadings = windowSec * 2;  // ~500ms per reading
    _emotionMinWords = data.emotion_min_words || 10;

    _badge('status-stt',     'STT: ' + data.stt_engine,       data.stt_engine !== 'none');
    _badge('status-emotion', 'HF: ' + (data.emotion_engine === 'hf' ? 'active' : 'inactive'), data.emotion_engine === 'hf');

    const llmLabel = data.llm_ok
      ? 'LLM: ' + data.ollama_model
      : (data.ollama_available ? 'LLM: ' + data.ollama_model + ' (no response)' : 'LLM: offline');
    _badge('status-llm', llmLabel, data.llm_ok);

    statusRow.classList.remove('hidden');

    if (typeof dbg === 'function') {
      const llmStatus = data.llm_ok
        ? data.ollama_model + ' ✓'
        : (data.ollama_available ? data.ollama_model + ' (no response)' : 'OFFLINE');
      const ferStatus = data.fer_engine && data.fer_engine !== 'none' ? data.fer_engine + ' ✓' : 'none';
      dbg(`Engine status — STT:${data.stt_engine} | HF:${data.emotion_engine} | FER:${ferStatus} | LLM:${llmStatus} | emotion window:${windowSec}s / min:${minSec}s / min-words:${_emotionMinWords}`);
    }
  } catch (e) {
    if (typeof dbg === 'function') dbg('ERROR fetching /api/status: ' + e);
  }
}

function handleServerMessage(msg) {
  switch (msg.type) {
    case 'transcribing':
      document.getElementById('partial-transcript').textContent = '…transcribing';
      if (typeof dbg === 'function') dbg('Transcribing audio buffer...');
      break;

    case 'partial':
      document.getElementById('partial-transcript').textContent = msg.text;
      break;

    case 'final': {
      if (typeof dbg === 'function') dbg(`Final transcript: "${msg.text.slice(0, 80)}${msg.text.length > 80 ? '…' : ''}"`);
      // Accumulate for next live_summary call
      _transcriptBuffer += (_transcriptBuffer ? ' ' : '') + msg.text;

      // Append text immediately — no emotion tag yet
      const ta = document.getElementById('entry-body');
      if (ta) {
        const existing = ta.value.trim();
        ta.value = existing ? existing + '\n\n' + msg.text : msg.text;
        _growAndScrollTextarea(ta);
        if (typeof _scheduleAutoSave === 'function') _scheduleAutoSave();
      }
      document.getElementById('partial-transcript').textContent = '';

      // Cancel any pending emotion tag — restart the 2s silence guard
      if (_emotionTagTimer) { clearTimeout(_emotionTagTimer); _emotionTagTimer = null; }
      if (_lastLlmEmotionText) {
        _emotionTagTimer = setTimeout(() => {
          _emotionTagTimer = null;
          const tag = _buildEmotionTag();
          if (!tag) return;
          _lastLlmEmotionText = ''; // consumed
          const ta2 = document.getElementById('entry-body');
          if (ta2) {
            ta2.value += '\n' + tag;
            _growAndScrollTextarea(ta2);
            if (typeof _scheduleAutoSave === 'function') _scheduleAutoSave();
          }
          if (typeof dbg === 'function') dbg(`Emotion tag (after 2s silence): ${tag}`);
          if (typeof triggerAnalyze === 'function') setTimeout(triggerAnalyze, 800);
        }, 2000);
        if (typeof dbg === 'function') dbg('LLM text ready — waiting 2s silence before appending tag');
      } else {
        if (typeof dbg === 'function') dbg('LLM text: none — tag skipped');
      }

      // Auto-analyze emotion after each transcription chunk
      if (typeof triggerAnalyze === 'function') {
        if (typeof dbg === 'function') dbg('Triggering emotion analyze...');
        setTimeout(triggerAnalyze, 800);
      }
      break;
    }

    case 'vad':
      _latestVad = { V: msg.V || 0, A: msg.A || 0, D: msg.D || 0 };
      _latestVadLabel = msg.label || '';

      if (msg.label) {
        document.getElementById('live-emotion').textContent = msg.label;
        if (typeof updateRealtimeEmotion === 'function') updateRealtimeEmotion(msg.label);
      }
      _emotionWindow.push({ V: msg.V || 0, A: msg.A || 0, D: msg.D || 0 });
      if (_emotionWindow.length >= _emotionWindowReadings) {
        const snapshot = _emotionWindow.splice(0);
        const avgV = snapshot.reduce((s, x) => s + x.V, 0) / snapshot.length;
        const avgA = snapshot.reduce((s, x) => s + x.A, 0) / snapshot.length;
        const avgD = snapshot.reduce((s, x) => s + x.D, 0) / snapshot.length;
        const faceEmotion = (typeof _dominantEmotion === 'function') ? _dominantEmotion() : '';
        const transcriptSnap = _transcriptBuffer;
        // Don't clear buffer yet — only clear when we actually send (so short bursts accumulate)
        const wordCount = transcriptSnap.trim().split(/\s+/).filter(w => w.length > 0).length;
        const windowSec = Math.round(_emotionWindowReadings * 0.5);
        if (typeof dbg === 'function') dbg(`${windowSec}s window complete. transcript: ${wordCount} words — avg V:${avgV.toFixed(2)} A:${avgA.toFixed(2)} D:${avgD.toFixed(2)}`);
        if (wordCount < _emotionMinWords) {
          if (typeof dbg === 'function') dbg(`Skipping live_summary — only ${wordCount} words (min: ${_emotionMinWords}), buffering for next window`);
        } else {
          _transcriptBuffer = ''; // consumed
          const fd = new FormData();
          fd.append('vad_v', avgV.toFixed(4));
          fd.append('vad_a', avgA.toFixed(4));
          fd.append('vad_d', avgD.toFixed(4));
          fd.append('face_emotion', faceEmotion);
          fd.append('transcript', transcriptSnap);
          fetch('/emotion/live_summary', { method: 'POST', body: fd })
            .then(r => r.json())
            .then(data => {
              if (typeof dbg === 'function') dbg(`live_summary response: ${JSON.stringify(data)} [source: ${data.source || 'unknown'}]`);
              if (data.summary) {
                _lastLlmEmotionText = data.summary;
                if (typeof dbg === 'function') dbg(`Emotion set: "${data.summary}" (${data.source === 'fallback' ? 'FALLBACK — LLM matched rule-based or failed' : 'LLM ✓'})`);
              }
            })
            .catch(e => {
              if (typeof dbg === 'function') dbg(`live_summary FAILED: ${e}`);
            });
        }
      } else if (_emotionWindow.length % 20 === 0 && typeof dbg === 'function') {
        const elapsed = Math.round(_emotionWindow.length * 0.5);
        const total = Math.round(_emotionWindowReadings * 0.5);
        dbg(`VAD window: ${_emotionWindow.length}/${_emotionWindowReadings} readings (${elapsed}s / ${total}s)`);
      }
      break;

    case 'vad_summary': {
      // Store session-average VAD for the Analyze Emotion button
      const vadField = document.getElementById('vad-summary');
      if (vadField) {
        vadField.value = JSON.stringify({ V: msg.V, A: msg.A, D: msg.D });
      }
      break;
    }

    case 'stt_engine':
      document.getElementById('stt-badge').textContent = msg.engine;
      break;
  }
}

function setRecordingUI(active) {
  const panel = document.querySelector('.border.border-border.rounded-lg');
  const btn = document.getElementById('record-btn');
  const label = document.getElementById('record-label');
  const dot = document.getElementById('record-dot');
  const waveformEl = document.getElementById('waveform');
  const tickerWrap = document.getElementById('emotion-ticker-wrap');
  const partial = document.getElementById('partial-transcript');

  if (active) {
    label.textContent = 'Recording in progress';
    btn.className = 'flex items-center gap-2 px-3 py-1.5 rounded border border-red-700 bg-red-950 text-xs text-red-400 transition-colors';
    dot.className = 'w-2 h-2 rounded-full bg-red-500 animate-pulse';
    waveformEl.classList.remove('hidden');
    partial.classList.remove('hidden');
    panel.classList.add('recording-active');
  } else {
    label.textContent = 'Record';
    btn.className = 'flex items-center gap-2 px-3 py-1.5 rounded border border-border text-xs text-subtle hover:border-muted hover:text-primary transition-colors';
    dot.className = 'w-2 h-2 rounded-full bg-gray-600';
    waveformEl.classList.add('hidden');
    if (tickerWrap) tickerWrap.classList.add('hidden');
    partial.classList.add('hidden');
    panel.classList.remove('recording-active');
    const engineStatus = document.getElementById('engine-status');
    if (engineStatus) engineStatus.classList.add('hidden');
    document.getElementById('live-emotion').textContent = '';
  }
}

// ── Waveform + ticker visualizer ─────────────────────────────────────────────

function drawWaveform() {
  const canvas = document.getElementById('waveform');
  if (!canvas || canvas.classList.contains('hidden')) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width, h = canvas.height;
  ctx.fillStyle = '#0a0a0a';
  ctx.fillRect(0, 0, w, h);

  const barW = w / WAVEFORM_HISTORY;
  const mid = h / 2;
  ctx.fillStyle = '#ffffff';
  for (let i = 0; i < WAVEFORM_HISTORY; i++) {
    const amp = waveformHistory[i];
    const barH = Math.max(1, amp * h * 0.9);
    const x = i * barW;
    ctx.globalAlpha = 0.4 + amp * 0.6; // quieter bars are more transparent
    ctx.fillRect(x, mid - barH / 2, Math.max(1, barW - 1), barH);
  }
  ctx.globalAlpha = 1;
}

function updateEmotionTicker() {
  const wrap = document.getElementById('emotion-ticker-wrap');
  const el = document.getElementById('emotion-ticker-text');
  if (!wrap || !el) return;

  // Stage a text update (applied only when current scroll pass completes)
  const now = Date.now();
  if (now - _tickerLastUpdateTime >= TICKER_UPDATE_INTERVAL_MS) {
    const displayText = _lastLlmEmotionText || _latestVadLabel;
    if (displayText) {
      _tickerPendingText = displayText;
      _tickerLastUpdateTime = now;
    }
  }

  // If no text is showing yet, start immediately with pending text
  if (!el.textContent && _tickerPendingText) {
    el.textContent = _tickerPendingText;
    _tickerPendingText = '';
    wrap.classList.remove('hidden');
    _tickerPixelOffset = 0;
  }

  // Scroll continuously — never reset mid-pass
  if (!wrap.classList.contains('hidden') && el.textContent) {
    _tickerPixelOffset += TICKER_SPEED_PX_PER_FRAME;
    const containerW = wrap.offsetWidth || 600;
    const textW = el.scrollWidth;
    if (_tickerPixelOffset > containerW + textW) {
      // Loop: apply any staged text update at the natural boundary
      _tickerPixelOffset = 0;
      if (_tickerPendingText) {
        el.textContent = _tickerPendingText;
        _tickerPendingText = '';
      }
    }
    el.style.transform = `translateY(-50%) translateX(${containerW - _tickerPixelOffset}px)`;
  }
}

function animateWaveform() {
  if (!isRecording) return;
  drawWaveform();
  updateEmotionTicker();
  requestAnimationFrame(animateWaveform);
}
