# Setup and troubleshooting

## Network and camera

Run the viewer on a computer that can reach the camera's IP and RTSP port. The viewer listens on `127.0.0.1:5000`. Keep it on loopback because it has no separate viewer login.

The supported camera paths are `/1/h264major` for HIGH and `/1/h264minor` for LOW. The RTSP port defaults to `554`. The camera must expose an audio track on the HIGH stream for audio playback.

## Connect

1. Open the viewer and type the entire camera IP address into **IP**.
2. Enter the RTSP port, then enter the camera username and password. Leaving the username empty uses the saved username for the same camera address and port, or `admin` for a new camera.
3. Click **Connect**. **Camera selected** means the TCP port was reachable. A live image confirms the stream itself is working.
4. Click the speaker button to enable audio. Use the adjacent volume and boost controls to adjust the sound.

Both credential fields start empty. On Windows, DPAPI protects the saved password for the current Windows user. The viewer can reuse it when the address, port, and username match. Delete the local `eyesec_settings.json` with the viewer stopped to clear saved settings. Other operating systems remember the address, port, and username and require the password again after restart.

For scripted launches, the viewer accepts `CAMERA_IP`, `CAMERA_PORT`, `CAMERA_USER`, and `CAMERA_PASSWORD` from the process environment. Keep settings and credentials out of version control.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Camera port unreachable | Check the full IP, RTSP port, network route, and whether the camera has RTSP enabled. |
| Camera selected but no video | Check the credentials and confirm the camera exposes the supported RTSP paths. Try the other quality. |
| No audio | Run `ffmpeg -version`, confirm the HIGH stream has audio, and click the speaker button. |
| FPS or latency is blank | FPS needs recent frames. Latency measures the TCP connection to the camera, separate from video delay. |
| Port 5000 is already in use | Stop the other service or start the viewer on a different loopback port with `waitress-serve --listen=127.0.0.1:5001 app:app` from the activated environment. |
