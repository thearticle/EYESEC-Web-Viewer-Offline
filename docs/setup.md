# Setup and troubleshooting

## Network and camera

Run the viewer on a computer that can reach the camera's IP and RTSP port. The viewer listens on `127.0.0.1:5000`. Keep it on loopback because it has no separate viewer login.

The supported camera paths are `/1/h264major` for HIGH and `/1/h264minor` for LOW. The RTSP port defaults to `554`. The camera must expose an audio track on the HIGH stream for audio playback.

## Find the camera IP and set its password

For compatible camera models that show the ONVIF menu:

1. Open your camera's live view in the **EYESEC** mobile app.
2. Tap the **three dots (⋯)** in the upper-right corner to open the camera's settings.
3. Open **ONVIF** and turn on its switch if available. Note the local **IP address** shown on that screen. You can also check your router's connected-devices list to find the camera's IP address.
4. Use **Reset Password**, if available, to set a new local camera password. Use that password in the viewer. If you change it later, enter the new password on your next connection.
5. On the viewer computer, open [the local viewer](http://127.0.0.1:5000) and enter the camera IP, RTSP port (normally **554**), username (default **`admin`**), and camera password.

The app menu varies by model and firmware. EYESEC notes that some SmartTuya models removed the ONVIF on/off switch. Check the manual for your camera model if the menu or reset option is missing. [EYESEC model notice](https://eyesec.cn/nd.jsp?fromColId=104&id=15)

## Connect

1. Open the viewer and type the entire camera IP address into **IP**.
2. Enter the RTSP port, then enter the camera username and password. Leaving the username empty uses the saved username for the same camera address and port, or `admin` for a new camera.
3. Click **Connect**. **Waiting for video** means the TCP port was reachable. **Live** means the selected RTSP stream is delivering frames.
4. Click the speaker button to enable audio. Use the adjacent volume and boost controls to adjust the sound.

Both credential fields start empty. The password field clears after a successful submission. On Windows, DPAPI protects the saved password for the current Windows user. The viewer can reuse it when the address, port, and username match. Enter the password again after changing any of those settings. Delete the local `eyesec_settings.json` with the viewer stopped to clear saved settings. Other operating systems remember the address, port, and username and require the password again after restart.

For scripted launches, the viewer accepts `CAMERA_IP`, `CAMERA_PORT`, `CAMERA_USER`, and `CAMERA_PASSWORD` from the process environment. Keep settings and credentials out of version control.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Camera port unreachable | Check the full IP, RTSP port, network route, and whether the camera has RTSP enabled. |
| No video | Check the credentials and confirm the camera exposes the supported RTSP paths. Try the other quality. The viewer retries when the feed drops. |
| No audio | Run `ffmpeg -version`, confirm the HIGH stream has audio, and click the speaker button. |
| FPS or latency is blank | FPS needs recent frames. Latency measures the time to open a TCP connection to the camera. |
| Port 5000 is already in use | Start the viewer with `python app.py --port 5001` from the activated environment, then open `http://127.0.0.1:5001`. |
