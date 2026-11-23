'use strict';

const byId = (id) => document.getElementById(id);
const camera = byId('eyesec');
const quality = byId('quality');
const form = byId('connectionForm');
const status = byId('connectionStatus');
const connectButton = byId('connect');
const password = byId('password');
const showPassword = byId('showPassword');
const { videoUrl, metricsUrl, audioUrl } = document.body.dataset;
let connected = document.body.dataset.connected === 'true';
let connecting = false;
let connectionError = false;
let live = false;
let streamVersion = 0;
let metricsTimer;
let videoRetry;
let hideTimer;

function revealToolbar() {
  document.body.classList.remove('hidden-ui');
  clearTimeout(hideTimer);
  if (live && !connecting && !connectionError) {
    hideTimer = setTimeout(() => document.body.classList.add('hidden-ui'), 3500);
  }
}

for (const event of ['pointermove', 'pointerdown', 'keydown', 'focusin']) {
  document.addEventListener(event, revealToolbar, { passive: true });
}

let zoom = 1;
let panX = 0;
let panY = 0;
let drag = null;

function applyZoom() {
  panX = Math.min(0, Math.max(camera.clientWidth * (1 - zoom), panX));
  panY = Math.min(0, Math.max(camera.clientHeight * (1 - zoom), panY));
  camera.style.transform = `translate(${panX}px, ${panY}px) scale(${zoom})`;
  camera.style.cursor = drag ? 'grabbing' : zoom > 1 ? 'grab' : 'zoom-in';
}

function resetZoom() {
  zoom = 1;
  drag = null;
  applyZoom();
}

camera.addEventListener('wheel', (event) => {
  event.preventDefault();
  const next = Math.max(1, Math.min(6, zoom * (event.deltaY < 0 ? 1.15 : 1 / 1.15)));
  if (next === zoom) return;
  const { clientX, clientY } = event;
  panX = clientX - (clientX - panX) * next / zoom;
  panY = clientY - (clientY - panY) * next / zoom;
  zoom = next;
  applyZoom();
}, { passive: false });

camera.addEventListener('pointerdown', (event) => {
  if (zoom <= 1 || drag || (event.button !== 0 && event.button !== 1)) return;
  event.preventDefault();
  drag = { id: event.pointerId, x: event.clientX, y: event.clientY };
  camera.setPointerCapture(drag.id);
  applyZoom();
});

camera.addEventListener('pointermove', (event) => {
  if (drag?.id !== event.pointerId) return;
  panX += event.clientX - drag.x;
  panY += event.clientY - drag.y;
  drag.x = event.clientX;
  drag.y = event.clientY;
  applyZoom();
});

camera.addEventListener('lostpointercapture', () => {
  drag = null;
  applyZoom();
});
camera.addEventListener('auxclick', (event) => {
  if (event.button === 1) event.preventDefault();
});
camera.addEventListener('dblclick', resetZoom);
window.addEventListener('resize', applyZoom);

function urlWithParams(path, params) {
  const url = new URL(path, window.location.href);
  url.search = new URLSearchParams(params);
  return url;
}

const audio = byId('cameraAudio');
const audioToggle = byId('audioToggle');
const audioStatus = byId('audioStatus');
const volume = byId('audioVolume');
const boost = byId('boostLevel');
const boostToggle = byId('boostToggle');
let audioEnabled = false;
let boosted = true;
let audioVersion = 0;
let restartTimer;

function setAudioStatus(message) {
  audioStatus.textContent = message;
  audioStatus.hidden = !message;
  if (message) revealToolbar();
}

function updateVolume() {
  byId('volumeValue').textContent = `${volume.value}%`;
  audio.volume = Number(volume.value) / 100;
  audio.muted = audio.volume === 0;
}

function stopAudio(message = '') {
  audioEnabled = false;
  audioVersion += 1;
  clearTimeout(restartTimer);
  audio.pause();
  audio.removeAttribute('src');
  audio.load();
  audioToggle.setAttribute('aria-pressed', 'false');
  audioToggle.textContent = '🔇';
  setAudioStatus(message);
}

function startAudio() {
  const version = ++audioVersion;
  audio.src = urlWithParams(audioUrl, { boost: boosted ? boost.value : 0, t: Date.now() });
  updateVolume();
  audio.play().catch(() => {
    if (version === audioVersion) stopAudio('Audio unavailable. Check FFmpeg and camera audio.');
  });
}

function restartAudio() {
  if (!audioEnabled) return;
  clearTimeout(restartTimer);
  restartTimer = setTimeout(startAudio, 450);
}

audioToggle.addEventListener('click', () => {
  if (audioEnabled) {
    stopAudio();
    return;
  }
  if (!connected) {
    setAudioStatus('Connect a camera to play audio.');
    return;
  }
  setAudioStatus('');
  audioEnabled = true;
  audioToggle.setAttribute('aria-pressed', 'true');
  audioToggle.textContent = '🔊';
  startAudio();
});
volume.addEventListener('input', updateVolume);
boost.addEventListener('input', () => {
  byId('boostValue').textContent = `${boost.value} dB`;
  restartAudio();
});
boostToggle.addEventListener('click', () => {
  boosted = !boosted;
  boostToggle.setAttribute('aria-pressed', String(boosted));
  boostToggle.textContent = boosted ? '⚡' : '⊘';
  restartAudio();
});
audio.addEventListener('error', () => {
  if (audioEnabled && audio.error) stopAudio('Audio unavailable. Check FFmpeg and camera audio.');
});

function renderMetrics({ fps = null, ping_ms: ping = null, state }) {
  byId('fps').textContent = fps === null ? '-- FPS' : `${fps.toFixed(1)} FPS`;
  byId('ping').textContent = ping === null ? '-- ms' : `${ping} ms`;
  const wasLive = live;
  live = state === 'live';
  if (wasLive !== live) revealToolbar();
  if (connecting || connectionError) return;
  status.textContent = {
    live: 'Live',
    offline: 'No video. Check camera settings.',
    waiting: 'Waiting for video…',
    unavailable: 'Viewer unavailable.',
  }[state] ?? 'Ready';
}

async function pollMetrics() {
  const version = streamVersion;
  try {
    const response = await fetch(urlWithParams(metricsUrl, { quality: quality.value }), { cache: 'no-store' });
    if (!response.ok) throw new Error();
    const metrics = await response.json();
    if (version === streamVersion) renderMetrics(metrics);
  } catch {
    if (version === streamVersion) renderMetrics({ state: 'unavailable' });
  } finally {
    if (version === streamVersion) metricsTimer = setTimeout(pollMetrics, 2500);
  }
}

function requestVideo() {
  camera.src = urlWithParams(videoUrl, { quality: quality.value, t: Date.now() });
}

function reloadVideo() {
  if (!connected) return;
  streamVersion += 1;
  clearTimeout(metricsTimer);
  clearTimeout(videoRetry);
  resetZoom();
  renderMetrics({ state: 'waiting' });
  requestVideo();
  pollMetrics();
}

camera.addEventListener('error', () => {
  if (!connected) return;
  clearTimeout(videoRetry);
  videoRetry = setTimeout(requestVideo, 2500);
});
quality.addEventListener('change', reloadVideo);

function togglePassword(visible) {
  password.type = visible ? 'text' : 'password';
  showPassword.setAttribute('aria-pressed', String(visible));
  showPassword.setAttribute('aria-label', visible ? 'Hide password' : 'Show password');
}

showPassword.addEventListener('click', () => togglePassword(password.type === 'password'));
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (connecting) return;
  connecting = true;
  connectionError = false;
  connectButton.disabled = true;
  status.textContent = 'Connecting…';
  revealToolbar();

  try {
    const response = await fetch(form.action, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.fromEntries(new FormData(form))),
    });
    const result = await response.json();
    if (!response.ok) {
      connectionError = true;
      status.textContent = result.error || 'Connection failed.';
      return;
    }
    password.value = '';
    togglePassword(false);
    stopAudio();
    connected = true;
    status.textContent = 'Waiting for video…';
    reloadVideo();
  } catch {
    connectionError = true;
    status.textContent = 'Could not reach the viewer. Try again.';
  } finally {
    connecting = false;
    connectButton.disabled = false;
    revealToolbar();
  }
});

const fullscreen = byId('fullscreen');
fullscreen.disabled = !document.fullscreenEnabled;
fullscreen.addEventListener('click', async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await document.documentElement.requestFullscreen();
    fullscreen.blur();
  } catch {
    fullscreen.title = 'Fullscreen unavailable';
  }
});
document.addEventListener('fullscreenchange', () => {
  fullscreen.setAttribute('aria-label', document.fullscreenElement ? 'Exit fullscreen' : 'Enter fullscreen');
  revealToolbar();
});

const clock = new Intl.DateTimeFormat('en-GB', {
  day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
});
function updateClock() {
  byId('clock').textContent = clock.format(new Date());
}

updateClock();
setInterval(updateClock, 10000);
reloadVideo();
