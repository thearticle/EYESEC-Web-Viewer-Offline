import os
import time
import threading
import subprocess
import shutil
import socket
import ipaddress
import json
import ctypes
from ctypes import wintypes
from pathlib import Path
from collections import deque
from urllib.parse import quote

import cv2
from flask import Flask, Response, abort, render_template, request, jsonify

HOST = '127.0.0.1'
PORT = 5000
# Store camera settings beside this script. Windows DPAPI protects the password
# for the current Windows user; plaintext passwords are never written to disk.
SETTINGS_FILE = Path(__file__).resolve().with_name('eyesec_settings.json')

class _DATA_BLOB(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_byte))]

def _dpapi(data, decrypt=False):
    if os.name != 'nt':
        raise RuntimeError('Secure password persistence requires Windows DPAPI')
    raw = ctypes.create_string_buffer(data, len(data))
    source = _DATA_BLOB(len(data), ctypes.cast(raw, ctypes.POINTER(ctypes.c_byte)))
    target = _DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    crypt32.CryptProtectData.argtypes = [ctypes.POINTER(_DATA_BLOB), ctypes.c_wchar_p, ctypes.POINTER(_DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DATA_BLOB)]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(_DATA_BLOB), ctypes.c_void_p, ctypes.POINTER(_DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DATA_BLOB)]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    ctypes.windll.kernel32.LocalFree.restype = ctypes.c_void_p
    fn = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    if decrypt:
        ok = fn(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target))
    else:
        ok = fn(ctypes.byref(source), 'EYESEC camera password', None, None, None, 0, ctypes.byref(target))
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(target.pbData, ctypes.c_void_p))

def _load_settings():
    try:
        saved = json.loads(SETTINGS_FILE.read_text(encoding='utf-8'))
        if not isinstance(saved, dict):
            return {}
        saved.pop('password', None)
        if saved.get('password_dpapi'):
            import base64
            saved['password'] = _dpapi(base64.b64decode(saved['password_dpapi']), decrypt=True).decode('utf-8')
        return saved
    except (OSError, ValueError, RuntimeError):
        print('[EYESEC settings] Could not load saved settings', flush=True)
        return {}

def _save_settings(ip, port, username, password):
    import base64
    saved = {'ip': ip, 'port': port, 'username': username}
    try:
        saved['password_dpapi'] = base64.b64encode(_dpapi(password.encode('utf-8'))).decode('ascii')
    except (OSError, RuntimeError) as exc:
        print(f'[EYESEC settings] Password not saved: {exc}', flush=True)
    temp = SETTINGS_FILE.with_suffix('.tmp')
    temp.write_text(json.dumps(saved, indent=2), encoding='utf-8')
    temp.replace(SETTINGS_FILE)

_saved = _load_settings()
IP = os.environ.get('CAMERA_IP') or _saved.get('ip') or ''
RTSP_PORT = int(os.environ.get('CAMERA_PORT') or _saved.get('port') or 554)
USER = os.environ.get('CAMERA_USER') or _saved.get('username') or 'admin'
PASSWORD = os.environ.get('CAMERA_PASSWORD') or _saved.get('password') or ''
connection_lock = threading.RLock()

# TCP RTSP and short read/open timeouts. No changes to camera firmware/FPS.
os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp|timeout;5000000'
app = Flask(__name__)

class Camera:
    def __init__(self, quality, url):
        self.quality = quality
        self.url = url
        self.lock = threading.Lock()
        self.changed = threading.Condition(self.lock)
        self.frame = None
        self.sequence = 0
        self.running = False
        self.stopped = False
        self.last_used = 0
        self.frame_times = deque(maxlen=50)

    def stop(self):
        with self.changed:
            self.stopped = True
            self.running = False
            self.frame = None
            self.changed.notify_all()

    def start(self):
        with self.changed:
            if self.stopped:
                return
            self.last_used = time.monotonic()
            if not self.running:
                self.running = True
                threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            while True:
                with self.changed:
                    if self.stopped or time.monotonic() - self.last_used > 45:
                        return
                cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
                try:
                    if cap.isOpened():
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        while cap.isOpened():
                            with self.changed:
                                if self.stopped or time.monotonic() - self.last_used > 45:
                                    return
                            ok, frame = cap.read()
                            if not ok:
                                break
                            height, width = frame.shape[:2]
                            if width > 2304:
                                frame = cv2.resize(frame, (2304, round(height * 2304 / width)))
                            ok, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                            if ok:
                                with self.changed:
                                    if self.stopped:
                                        return
                                    self.frame = encoded.tobytes()
                                    self.sequence += 1
                                    self.frame_times.append(time.monotonic())
                                    self.changed.notify_all()
                finally:
                    cap.release()
                with self.changed:
                    if self.stopped:
                        return
                    self.changed.wait(timeout=1)
        finally:
            with self.changed:
                self.running = False
                self.changed.notify_all()

    def next_frame(self, previous_sequence):
        with self.changed:
            if self.stopped:
                return self.sequence, None, True
            self.last_used = time.monotonic()
            self.changed.wait_for(
                lambda: self.sequence != previous_sequence or self.stopped or not self.running,
                timeout=2
            )
            self.last_used = time.monotonic()
            return self.sequence, self.frame, self.stopped


def _camera_url(quality):
    path = 'h264major' if quality == 'major' else 'h264minor'
    host = f'[{IP}]' if ':' in IP else IP
    return f'rtsp://{quote(USER, safe="")}:{quote(PASSWORD, safe="")}@{host}:{RTSP_PORT}/1/{path}'

cameras = {q: Camera(q, _camera_url(q)) for q in ('minor', 'major')} if IP and PASSWORD else {}


@app.get('/')
def index():
    with connection_lock:
        html = render_template('viewer.html', camera_ip=IP, camera_port=RTSP_PORT, connected=bool(cameras))
    return Response(html, headers={'Cache-Control': 'no-store'})


@app.post('/connect')
def connect():
    global IP, RTSP_PORT, USER, PASSWORD
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='Expected camera settings'), 400
    try:
        ip = str(ipaddress.ip_address(str(data.get('ip', '')).strip()))
        if ipaddress.ip_address(ip).is_multicast or ipaddress.ip_address(ip).is_unspecified:
            raise ValueError('Invalid camera address')
        port = int(data.get('port', 554))
        if not 1 <= port <= 65535:
            raise ValueError('Invalid port')
        username = data.get('username', '')
        password = data.get('password', '')
        if not isinstance(username, str) or not isinstance(password, str):
            raise ValueError('Invalid credentials')
        with connection_lock:
            if ip == IP and port == RTSP_PORT:
                username = username or USER
                if username == USER:
                    password = password or PASSWORD
            username = username or 'admin'
        if not username or not password or len(username) > 128 or len(password) > 256:
            raise ValueError('Username/password required')
    except (ValueError, TypeError):
        return jsonify(error='Invalid IP, port or credentials'), 400
    try:
        with socket.create_connection((ip, port), timeout=2):
            pass
    except OSError:
        return jsonify(error='Camera port unreachable'), 502
    with connection_lock:
        global cameras
        IP, RTSP_PORT, USER, PASSWORD = ip, port, username, password
        old_cameras = cameras
        cameras = {q: Camera(q, _camera_url(q)) for q in ('minor', 'major')}
        for old in old_cameras.values():
            old.stop()
        try:
            _save_settings(IP, RTSP_PORT, USER, PASSWORD)
        except OSError as exc:
            print(f'[EYESEC settings] Save failed: {exc}', flush=True)
    return jsonify(ok=True)


@app.get('/metrics')
def metrics():
    quality = request.args.get('quality', 'major')
    if quality not in ('major', 'minor'):
        abort(400)
    with connection_lock:
        camera = cameras.get(quality)
    if camera is None:
        return jsonify(fps=None, ping_ms=None)
    with camera.lock:
        now = time.monotonic()
        times = [t for t in camera.frame_times if now-t <= 3]
        fps = round((len(times)-1)/(times[-1]-times[0]), 1) if len(times)>1 and times[-1]>times[0] else None
    ping = None
    try:
        t0 = time.perf_counter()
        with socket.create_connection((IP, RTSP_PORT), timeout=0.6):
            ping = round((time.perf_counter()-t0)*1000, 1)
    except OSError:
        pass
    return jsonify(fps=fps,ping_ms=ping)


@app.get('/video')
def video():
    quality = request.args.get('quality', 'major')
    if quality not in ('major', 'minor'):
        abort(400)
    with connection_lock:
        camera = cameras.get(quality)
    if camera is None:
        abort(409)
    camera.start()

    def frames():
        sequence = -1
        while True:
            sequence, frame, stopped = camera.next_frame(sequence)
            if stopped:
                return
            if frame:
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'

    return Response(frames(), mimetype='multipart/x-mixed-replace; boundary=frame', headers={
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'
    })


@app.get('/audio')
def audio():
    """Transcode the camera's G.711 mu-law microphone to live MP3 for browsers."""
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        return Response('FFmpeg not found on PATH', status=503, mimetype='text/plain')

    with connection_lock:
        if not cameras:
            abort(409)
        url = _camera_url('major')
    boost = max(0, min(40, request.args.get('boost', default=30, type=int)))
    command = [
        ffmpeg, '-hide_banner', '-nostdin', '-loglevel', 'error',
        '-rtsp_transport', 'tcp', '-i', url,
        '-map', '0:a:0', '-vn', '-sn', '-dn',
        '-af', f'volume={boost}dB,alimiter=limit=0.95',
        '-ac', '1', '-ar', '24000',
        '-c:a', 'libmp3lame', '-b:a', '48k',
        '-f', 'mp3', 'pipe:1'
    ]

    def chunks():
        process = None
        try:
            process = subprocess.Popen(
                command, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                bufsize=0
            )
            while True:
                data = process.stdout.read(4096)
                if not data:
                    break
                yield data
        except (OSError, ValueError) as exc:
            print(f'[EYESEC audio] {type(exc).__name__}: {exc}', flush=True)
        finally:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                if process.stdout:
                    process.stdout.close()
                if process.stderr:
                    process.stderr.close()

    return Response(chunks(), mimetype='audio/mpeg', headers={
        'Cache-Control': 'no-store, no-cache, must-revalidate',
        'X-Content-Type-Options': 'nosniff',
        'X-Accel-Buffering': 'no',
    })


if __name__ == '__main__':
    from waitress import serve
    print(f'EYESEC-only viewer running at http://{HOST}:{PORT}', flush=True)
    serve(app, host=HOST, port=PORT, threads=8)
