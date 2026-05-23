/**
 * Voice recorder — AudioWorklet → raw PCM Int16 → WebSocket → server
 * Server sends back: {type:"partial"|"final"|"vad"|"emotion", ...}
 */

let ws = null;
let audioContext = null;
let mediaStream = null;
let workletNode = null;
let isRecording = false;

// Waveform state
let waveformData = new Float32Array(256).fill(0);

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
    if (typeof onRecordingStart === 'function') onRecordingStart();
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleServerMessage(msg);
    } catch (e) {}
  };

  ws.onclose = ws.onerror = () => {
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
    // Update waveform
    waveformData = float32.slice(0, 256);
    drawWaveform();

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

  if (workletNode) { workletNode.disconnect(); workletNode = null; }
  if (audioContext) { await audioContext.close(); audioContext = null; }
  if (mediaStream) { mediaStream.getTracks().forEach(t => t.stop()); mediaStream = null; }

  ws = null;
}

function handleServerMessage(msg) {
  switch (msg.type) {
    case 'partial':
      document.getElementById('partial-transcript').textContent = msg.text;
      break;

    case 'final': {
      // Append finalized text to the main textarea
      const ta = document.getElementById('entry-body');
      if (ta) {
        const existing = ta.value.trim();
        ta.value = existing ? existing + '\n\n' + msg.text : msg.text;
      }
      document.getElementById('partial-transcript').textContent = '';
      break;
    }

    case 'vad':
      // Update live emotion indicator
      if (msg.label) {
        document.getElementById('live-emotion').textContent = msg.label;
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
  const partial = document.getElementById('partial-transcript');

  if (active) {
    label.textContent = 'Stop';
    dot.className = 'w-2 h-2 rounded-full bg-red-500 animate-pulse';
    waveformEl.classList.remove('hidden');
    partial.classList.remove('hidden');
    panel.classList.add('recording-active');
  } else {
    label.textContent = 'Record';
    dot.className = 'w-2 h-2 rounded-full bg-gray-600';
    waveformEl.classList.add('hidden');
    partial.classList.add('hidden');
    panel.classList.remove('recording-active');
    document.getElementById('live-emotion').textContent = '';
  }
}

// ── Waveform visualizer ──────────────────────────────────────────────────────

function drawWaveform() {
  const canvas = document.getElementById('waveform');
  if (!canvas || canvas.classList.contains('hidden')) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width, h = canvas.height;
  ctx.fillStyle = '#0a0a0a';
  ctx.fillRect(0, 0, w, h);

  ctx.strokeStyle = '#ffffff';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  const step = w / waveformData.length;
  const mid = h / 2;
  for (let i = 0; i < waveformData.length; i++) {
    const x = i * step;
    const y = mid + waveformData[i] * mid * 0.9;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  }
  ctx.stroke();
}

function animateWaveform() {
  if (!isRecording) return;
  drawWaveform();
  requestAnimationFrame(animateWaveform);
}
