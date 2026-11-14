<div align="center">

# EYESEC Web Viewer Offline

**Watch a compatible EYESEC camera in your browser over your local Ethernet or Wi‑Fi network.**

[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask)](https://flask.palletsprojects.com/)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-007808?style=for-the-badge&logo=ffmpeg)](https://ffmpeg.org/)

[Key Features](#-key-features) · [Screenshots](#-screenshots--ui-showcase) · [Architecture](#-technical-architecture) · [Getting Started](#-getting-started) · [Releases](https://github.com/thearticle/EYESEC-Web-Viewer-Offline/releases)

</div>

---

## 📖 Overview

EYESEC Web Viewer Offline is a local browser viewer for compatible EYESEC RTSP cameras. Once the camera and viewer are set up, the computer streams directly from the camera over the same LAN or Wi‑Fi. You can open the viewer even when the internet connection is down, as long as the local network is working.

## 🏠 Why View Locally?

For in-house monitoring, the video travels from the camera to your computer and browser without a vendor cloud relay. Skipping that round trip can reduce viewing delay, especially when the internet connection is slow or busy. Actual delay depends on the camera, network, stream quality, and buffering.

## ✨ Key Features

| Feature | How to use it |
| --- | --- |
| **Zoom in, zoom out, and pan** | Scroll over the image to zoom around the pointer. Drag while zoomed in, or double-click to reset. |
| **Live FPS and latency** | Read the delivered video frame rate and the camera’s TCP connection time in milliseconds. The latency indicator measures network connection time rather than camera-to-screen delay. |
| **Fullscreen** | Use the fullscreen button for a larger camera view. Move the pointer to reveal the controls after they hide. |
| **Editable camera connection** | Change the full IP address, RTSP port, username, and password in the browser. The port defaults to **554** and a new camera’s username defaults to **`admin`**. Enter the camera’s own password. |
| **HIGH and LOW video** | Select HIGH for detail or LOW for a lighter stream when available. |
| **Audio, volume, and boost** | Unmute the camera microphone, adjust playback volume, and enable gain when the feed is quiet. |

## 📱 Screenshots & UI Showcase

![Browser viewer controls on a synthetic test feed](docs/images/viewer-controls.png)

*Viewer on a synthetic test feed. The IP address is reserved for documentation.*

![Setup infographic showing the camera app, local network, and browser controls](docs/images/local-setup.png)

*Illustrated setup guide. Menu names and available options vary by camera model and firmware.*

## 🏗️ Technical Architecture

```text
EYESEC camera ── RTSP over Ethernet or Wi-Fi ── Viewer host ── HTTP loopback ── Browser
```

- **Video** uses OpenCV to read the camera’s HIGH or LOW RTSP stream and serves it as MJPEG.
- **Audio** uses FFmpeg to convert the HIGH stream’s audio track into browser-playable MP3 on demand.
- **Camera settings** stay on the viewer host. Windows DPAPI protects the saved password for the current Windows user.
- **Browser access** uses `127.0.0.1` on the viewer computer. The camera can be elsewhere on the same local network.

## 🛠️ Tech Stack

| Component | Technology |
| --- | --- |
| Local server | Python, Flask, Waitress |
| Video capture | OpenCV with FFmpeg backend |
| Audio transcoding | FFmpeg with libmp3lame |
| Browser controls | HTML, CSS, and JavaScript |

## 🚀 Getting Started

### Prerequisites

- A computer on the same local network as a camera that exposes the EYESEC RTSP stream paths.
- Python and a modern browser. Install FFmpeg on PATH if you want live audio.
- The camera’s local IP address and camera credentials. See the [EYESEC mobile app steps](docs/setup.md#find-the-camera-ip-and-set-its-password).

### Installation

Download the source archive from the [latest release](https://github.com/thearticle/EYESEC-Web-Viewer-Offline/releases/latest), or clone the repository. On Windows, run in PowerShell:

```powershell
git clone https://github.com/thearticle/EYESEC-Web-Viewer-Offline.git
cd EYESEC-Web-Viewer-Offline
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

If you downloaded the archive, extract it, open PowerShell in the extracted folder, and start at `python -m venv .venv`. The initial download and dependency installation typically require internet access.

Open [the local viewer](http://127.0.0.1:5000). Enter the full camera IP, use port **554** unless your camera is configured differently, and enter **`admin`** and the camera password. Click **Connect**. See the [setup and troubleshooting guide](docs/setup.md) for model and connection details.

## 📂 Project Structure

| Path | Purpose |
| --- | --- |
| `app.py` | Local HTTP server, camera connection, and media streaming |
| `templates/viewer.html` | Browser controls and viewer layout |
| `requirements.txt` | Python dependencies |
| `docs/setup.md` | Camera setup and troubleshooting |
| `docs/images/` | Viewer screenshot and illustrated setup |

## 👨‍💻 Author & Credits

Created by [Fauzan Afianto](https://afianto.dev/). The README format follows [KuloWargi](https://github.com/thearticle/kulowargi-family-tree).
