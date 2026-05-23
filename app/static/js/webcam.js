/**
 * Webcam emotion capture (Slice 5).
 * Loaded only when enable_webcam=true in settings.
 * Hooks into recorder.js via onRecordingStart / onRecordingStop.
 */

let webcamStream = null;
let webcamInterval = null;
let faceEmotionCounts = {};
let faceFramesSent = 0;

async function onRecordingStart() {
  const video = document.getElementById('webcam-video');
  if (!video) return;

  faceEmotionCounts = {};
  faceFramesSent = 0;

  try {
    webcamStream = await navigator.mediaDevices.getUserMedia({
      video: { width: 320, height: 240, facingMode: 'user' },
    });
    video.srcObject = webcamStream;
    video.classList.remove('hidden');
    webcamInterval = setInterval(_captureFrame, 500);
  } catch (err) {
    console.warn('Webcam unavailable:', err.message);
  }
}

function onRecordingStop() {
  if (webcamInterval) { clearInterval(webcamInterval); webcamInterval = null; }
  if (webcamStream) {
    webcamStream.getTracks().forEach(t => t.stop());
    webcamStream = null;
  }

  const video = document.getElementById('webcam-video');
  if (video) video.classList.add('hidden');

  const dominant = _dominantEmotion();
  const field = document.getElementById('face-emotion');
  if (field) field.value = dominant;

  const lbl = document.getElementById('face-emotion-label');
  if (lbl) lbl.textContent = dominant ? `Face: ${dominant}` : '';
}

async function _captureFrame() {
  const video = document.getElementById('webcam-video');
  const canvas = document.getElementById('webcam-canvas');
  if (!video || !canvas || video.readyState < 2) return;

  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

  canvas.toBlob(async (blob) => {
    if (!blob) return;
    const fd = new FormData();
    fd.append('file', blob, 'frame.jpg');
    try {
      const r = await fetch('/emotion/video/frame', { method: 'POST', body: fd });
      if (!r.ok) return;
      const data = await r.json();
      const em = data.emotion_label;
      if (em && em !== 'no face' && em !== '') {
        faceEmotionCounts[em] = (faceEmotionCounts[em] || 0) + 1;
        faceFramesSent++;
        const lbl = document.getElementById('face-emotion-label');
        if (lbl) lbl.textContent = `Face: ${em}`;
      }
    } catch (_) {}
  }, 'image/jpeg', 0.7);
}

function _dominantEmotion() {
  let best = '', count = 0;
  for (const [em, n] of Object.entries(faceEmotionCounts)) {
    if (n > count) { best = em; count = n; }
  }
  return best;
}
