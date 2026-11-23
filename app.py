import argparse
import logging
import shutil
import socket
import threading
import time

from flask import Flask, Response, abort, jsonify, render_template, request

from camera import Camera, STREAM_PATHS
from camera_settings import (
    DEFAULT_PORT, DEFAULT_USER, SETTINGS_FILE, CameraSettings,
    load_settings, parse_address, parse_credential, parse_port, save_settings,
)


HOST = '127.0.0.1'
PORT = 5000
REQUEST_LIMIT = 8192
logger = logging.getLogger(__name__)


def create_app(settings_file=SETTINGS_FILE):
    viewer = Flask(__name__)
    viewer.config.update(TRUSTED_HOSTS=[HOST, 'localhost'], MAX_CONTENT_LENGTH=REQUEST_LIMIT)
    connection_lock = threading.Lock()
    settings = load_settings(settings_file)
    cameras = {quality: Camera(settings, quality) for quality in STREAM_PATHS} if settings.ip and settings.password else {}

    @viewer.after_request
    def protect_response(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
        )
        return response

    @viewer.get('/')
    def index():
        with connection_lock:
            ip, port = settings.endpoint
            connected = bool(cameras)
        return render_template('viewer.html', camera_ip=ip, camera_port=port, connected=connected)

    @viewer.post('/connect')
    def connect():
        nonlocal settings, cameras
        if request.headers.get('Origin') not in (None, request.host_url.rstrip('/')):
            return jsonify(error='Open the viewer directly on this computer.'), 403

        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error='Enter camera settings in the viewer.'), 400

        try:
            ip = parse_address(data.get('ip'))
            port = parse_port(data.get('port', DEFAULT_PORT))
            username = parse_credential(data.get('username', ''), 128)
            password = parse_credential(data.get('password', ''), 256)
        except ValueError as exc:
            return jsonify(error=str(exc)), 400

        with connection_lock:
            previous = settings
        same_endpoint = (ip, port) == previous.endpoint
        username = username or (previous.username if same_endpoint else DEFAULT_USER)
        reuse_password = not password
        if reuse_password and (ip, port, username) == previous.identity:
            password = previous.password
        if not password:
            return jsonify(error='Enter this camera’s password.'), 400

        try:
            with socket.create_connection((ip, port), timeout=2):
                pass
        except OSError:
            return jsonify(error='Camera port unreachable.'), 502

        with connection_lock:
            if reuse_password and settings is not previous:
                return jsonify(error='Camera selection changed. Try again.'), 409
            target = CameraSettings(ip, port, username, password)
            new_cameras = {quality: Camera(target, quality) for quality in STREAM_PATHS}
            for camera in cameras.values():
                camera.stop()
            settings, cameras = target, new_cameras
            try:
                save_settings(settings, settings_file)
            except OSError:
                logger.warning('Could not write camera settings')
        return jsonify(ok=True)

    def selected_stream():
        quality = request.args.get('quality', 'major')
        if quality not in STREAM_PATHS:
            abort(400)
        with connection_lock:
            return cameras.get(quality), settings.endpoint

    @viewer.get('/metrics')
    def metrics():
        camera, endpoint = selected_stream()
        if camera is None:
            return jsonify(fps=None, ping_ms=None, state='idle')
        fps, state = camera.video_metrics()
        ping = None
        try:
            start = time.perf_counter()
            with socket.create_connection(endpoint, timeout=0.6):
                ping = round((time.perf_counter() - start) * 1000, 1)
        except OSError:
            pass
        return jsonify(fps=fps, ping_ms=ping, state=state)

    @viewer.get('/video')
    def video():
        camera, _ = selected_stream()
        if camera is None:
            abort(409)
        disconnected = request.environ.get('waitress.client_disconnected', lambda: False)
        return Response(camera.frames(disconnected), mimetype='multipart/x-mixed-replace; boundary=frame')

    @viewer.get('/audio')
    def audio():
        with connection_lock:
            camera = cameras.get('major')
        if camera is None:
            abort(409)
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            return Response('FFmpeg not found on PATH', status=503, mimetype='text/plain')
        boost = max(0, min(40, request.args.get('boost', default=30, type=int)))
        disconnected = request.environ.get('waitress.client_disconnected', lambda: False)
        return Response(
            camera.audio_chunks(ffmpeg, boost, disconnected),
            mimetype='audio/mpeg', headers={'X-Accel-Buffering': 'no'},
        )

    return viewer


app = create_app()


if __name__ == '__main__':
    from waitress import serve

    parser = argparse.ArgumentParser(description='Run EYESEC Web Viewer Offline.')
    parser.add_argument('--port', type=parse_port, default=PORT, help='Local viewer port (default: 5000)')
    args = parser.parse_args()
    print(f'EYESEC Web Viewer Offline running at http://{HOST}:{args.port}', flush=True)
    serve(
        app, host=HOST, port=args.port, threads=8,
        channel_request_lookahead=1, max_request_body_size=REQUEST_LIMIT,
    )
