import os
import subprocess
import threading
import time
from collections import deque
from urllib.parse import quote

# Set these before importing OpenCV. Debug messages can contain the RTSP URL.
os.environ['OPENCV_LOG_LEVEL'] = 'OFF'
os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp'
os.environ['OPENCV_FFMPEG_LOGLEVEL'] = '-8'

import cv2


STREAM_PATHS = {'major': '/1/h264major', 'minor': '/1/h264minor'}
RTSP_TIMEOUT_MS = 5000
IDLE_SECONDS = 5


def stream_url(settings, quality):
    host = f'[{settings.ip}]' if ':' in settings.ip else settings.ip
    user = quote(settings.username, safe='')
    password = quote(settings.password, safe='')
    return f'rtsp://{user}:{password}@{host}:{settings.port}{STREAM_PATHS[quality]}'


class Camera:
    def __init__(self, settings, quality):
        self.url = stream_url(settings, quality)
        self.changed = threading.Condition()
        self.frame = None
        self.sequence = 0
        self.frame_times = deque(maxlen=120)
        self.viewers = 0
        self.idle_until = 0
        self.worker = None
        self.stopped = False
        self.failed = False
        self.audio_processes = set()

    def stop(self):
        with self.changed:
            self.stopped = True
            for process in self.audio_processes:
                process.terminate()
            self.changed.notify_all()

    def _in_use(self):
        return not self.stopped and (self.viewers > 0 or time.monotonic() < self.idle_until)

    def _read(self):
        params = [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, RTSP_TIMEOUT_MS,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC, RTSP_TIMEOUT_MS,
        ]
        try:
            while True:
                with self.changed:
                    if not self._in_use():
                        return
                capture = cv2.VideoCapture()
                try:
                    if capture.open(self.url, cv2.CAP_FFMPEG, params):
                        self._decode(capture)
                except cv2.error:
                    pass
                finally:
                    capture.release()
                with self.changed:
                    self.frame = None
                    self.frame_times.clear()
                    self.failed = self.viewers > 0
                    if not self._in_use():
                        return
                    self.changed.wait_for(lambda: self.stopped, timeout=1)
        finally:
            with self.changed:
                self.worker = None
                self.changed.notify_all()

    def _decode(self, capture):
        while True:
            with self.changed:
                if not self._in_use():
                    return
            ok, frame = capture.read()
            if not ok:
                return
            height, width = frame.shape[:2]
            if width > 2304:
                frame = cv2.resize(frame, (2304, max(1, round(height * 2304 / width))))
            ok, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ok:
                with self.changed:
                    if self.stopped:
                        return
                    self.frame = encoded.tobytes()
                    self.sequence += 1
                    self.frame_times.append(time.monotonic())
                    self.failed = False
                    self.changed.notify_all()

    def frames(self, disconnected):
        with self.changed:
            self.viewers += 1
        previous = -1
        try:
            while not disconnected():
                with self.changed:
                    if self.stopped:
                        return
                    if self.worker is None:
                        self.worker = threading.Thread(target=self._read, daemon=True)
                        self.worker.start()
                    self.changed.wait_for(
                        lambda: self.stopped or (self.frame is not None and self.sequence != previous),
                        timeout=1,
                    )
                    if self.stopped:
                        return
                    if self.frame is None or self.sequence == previous:
                        continue
                    previous, frame = self.sequence, self.frame
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
        finally:
            with self.changed:
                self.viewers -= 1
                if self.viewers == 0:
                    self.idle_until = time.monotonic() + IDLE_SECONDS

    def video_metrics(self):
        with self.changed:
            now = time.monotonic()
            times = [stamp for stamp in self.frame_times if now - stamp <= 3]
            if self.stopped:
                return None, 'waiting'
            fps = None
            if len(times) > 1 and times[-1] > times[0]:
                fps = round((len(times) - 1) / (times[-1] - times[0]), 1)
            state = 'live' if times else 'offline' if self.failed else 'waiting'
            return fps, state

    def audio_chunks(self, ffmpeg, boost, disconnected):
        command = [
            ffmpeg, '-hide_banner', '-nostdin', '-loglevel', 'quiet',
            '-rtsp_transport', 'tcp', '-timeout', str(RTSP_TIMEOUT_MS * 1000), '-i', self.url,
            '-map', '0:a:0', '-vn', '-sn', '-dn',
            '-af', f'volume={boost}dB,alimiter=limit=0.95', '-ac', '1', '-ar', '24000',
            '-c:a', 'libmp3lame', '-b:a', '48k', '-flush_packets', '1', '-f', 'mp3', 'pipe:1',
        ]
        environment = {key: value for key, value in os.environ.items() if key not in {'FFREPORT', 'CAMERA_PASSWORD'}}
        with self.changed:
            if self.stopped or disconnected():
                return
            try:
                process = subprocess.Popen(
                    command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, bufsize=0, env=environment,
                )
            except OSError:
                return
            self.audio_processes.add(process)

        try:
            with process.stdout as output:
                while not disconnected():
                    chunk = output.read(4096)
                    if not chunk:
                        return
                    yield chunk
        finally:
            with self.changed:
                self.audio_processes.discard(process)
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
