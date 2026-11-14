<div align="center">

# EYESEC Web Viewer

**Watch a compatible EYESEC RTSP camera in your browser with live audio and on-screen controls.**

[![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-000000?style=flat-square&logo=flask)](https://flask.palletsprojects.com/)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-007808?style=flat-square&logo=ffmpeg)](https://ffmpeg.org/)

[Features](#features) · [Getting started](#getting-started) · [Troubleshooting](docs/setup.md#troubleshooting) · [Credits](#credits)

</div>

## Overview

EYESEC Web Viewer runs on a computer that can reach the camera over the local network. OpenCV reads RTSP video and serves it as MJPEG. FFmpeg converts camera audio to MP3 when you unmute the viewer.

## Features

- Enter a complete camera IP address in one field and edit the RTSP port.
- Switch between HIGH and LOW video. Scroll to zoom, drag to pan, and double-click to reset.
- Toggle audio, adjust volume and boost, and switch to fullscreen.
- See delivered video FPS, TCP connection latency, and the local time. The controls hide when idle.
- Enter camera credentials at runtime. Windows can remember the password using DPAPI under the current user account.

## Getting started

Install Python and put FFmpeg on PATH for audio. In PowerShell, run:

```powershell
git clone https://github.com/thearticle/EYESEC-Web-Viewer.git
cd EYESEC-Web-Viewer
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Open [the local viewer](http://127.0.0.1:5000), enter the camera IP, port, and credentials, then click **Connect**. See the [setup guide](docs/setup.md) for compatible stream paths, configuration, and troubleshooting.

## Credits

Project by [Fauzan Afianto](https://afianto.dev/).
