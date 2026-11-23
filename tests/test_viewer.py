import json
import os
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as viewer
from camera_settings import CameraSettings, load_settings, save_settings


class ViewerTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        for name in ('CAMERA_IP', 'CAMERA_PORT', 'CAMERA_USER', 'CAMERA_PASSWORD'):
            os.environ.pop(name, None)

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.settings = Path(directory.name) / 'eyesec_settings.json'
        self.client = viewer.create_app(self.settings).test_client()
        self.password = secrets.token_urlsafe(24)

    def connect(self, client=None, **overrides):
        data = {'ip': '192.0.2.10', 'port': '8554', 'username': 'operator', 'password': self.password}
        return (client or self.client).post('/connect', json=data | overrides)

    def test_viewer_starts_without_a_camera(self):
        page = self.client.get('/')
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.headers['Cache-Control'], 'no-store')
        self.assertNotRegex(page.text, r'<input[^>]*id="password"[^>]*\bvalue=')
        self.assertEqual(self.client.get('/metrics').json, {'fps': None, 'ping_ms': None, 'state': 'idle'})
        self.assertEqual(self.client.get('/video').status_code, 409)
        self.assertEqual(self.client.get('/audio').status_code, 409)

    def test_connection_accepts_a_whole_ipv4_address_and_scopes_reuse(self):
        with patch('app.socket.create_connection') as probe:
            self.assertEqual(self.connect().json, {'ok': True})
            probe.assert_called_once_with(('192.0.2.10', 8554), timeout=2)
            self.assertEqual(self.connect(password='', username='').status_code, 200)
            for changed in ({'ip': '192.0.2.20'}, {'port': '8555'}, {'username': 'other'}):
                self.assertEqual(self.connect(password='', **changed).status_code, 400)
            self.assertEqual(probe.call_count, 2)

        page = self.client.get('/')
        self.assertIn('value="192.0.2.10"', page.text)
        self.assertNotIn(self.password, page.text)
        self.assertNotRegex(page.text, r'<input[^>]*id="password"[^>]*\bvalue=')
        self.assertEqual(self.client.get('/metrics?quality=unrecognized').status_code, 400)
        self.assertEqual(self.client.get('/video?quality=unrecognized').status_code, 400)

    def test_invalid_inputs_never_reach_the_camera(self):
        invalid = (
            {'ip': '10'}, {'ip': '192.0.2.256'}, {'ip': 'example.test'}, {'ip': '0.0.0.0'},
            {'port': 0}, {'port': 65536}, {'port': 8554.5}, {'port': True},
            {'username': ['operator']}, {'password': '\0'}, {'password': '\ud800'},
        )
        with patch('app.socket.create_connection') as probe:
            for overrides in invalid:
                with self.subTest(field=next(iter(overrides))):
                    self.assertEqual(self.connect(**overrides).status_code, 400)
            probe.assert_not_called()
        self.assertEqual(self.client.post('/connect', json=['192.0.2.10']).status_code, 400)

    def test_unreachable_port_preserves_current_selection(self):
        with patch('app.socket.create_connection'):
            self.assertEqual(self.connect().status_code, 200)
        with patch('app.socket.create_connection', side_effect=OSError):
            self.assertEqual(self.connect(ip='192.0.2.20').status_code, 502)
        self.assertEqual(load_settings(self.settings).ip, '192.0.2.10')
        self.assertIn('value="192.0.2.10"', self.client.get('/').text)

    def test_loopback_host_and_same_origin_connection(self):
        self.assertEqual(self.client.get('/', base_url='http://outside.test').status_code, 400)
        with patch('app.socket.create_connection') as probe:
            response = self.client.post('/connect', json={}, headers={'Origin': 'http://outside.test'})
        self.assertEqual(response.status_code, 403)
        probe.assert_not_called()

    def test_environment_override_cannot_reuse_password_from_a_different_camera(self):
        save_settings(CameraSettings('192.0.2.10', 8554, 'operator', self.password), self.settings)
        for variable, different in [('CAMERA_IP', '192.0.2.20'), ('CAMERA_PORT', '8555'), ('CAMERA_USER', 'other')]:
            with self.subTest(variable=variable), patch.dict(os.environ, {variable: different}):
                self.assertEqual(load_settings(self.settings).password, '')

    def test_plaintext_legacy_settings_and_invalid_port_are_ignored(self):
        self.settings.write_text(json.dumps({'ip': '192.0.2.10', 'port': 'bad', 'password': self.password}))
        with patch.dict(os.environ, {'CAMERA_PORT': 'invalid'}):
            loaded = load_settings(self.settings)
        self.assertEqual(loaded.endpoint, ('192.0.2.10', 554))
        self.assertEqual(loaded.password, '')

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI test')
    def test_dpapi_can_restore_a_password_without_rendering_it(self):
        target = CameraSettings('192.0.2.10', 8554, 'operator', self.password)
        save_settings(target, self.settings)
        contents = self.settings.read_text(encoding='utf-8')
        self.assertNotIn(self.password, contents)
        self.assertNotIn('password', json.loads(contents))
        self.assertEqual(load_settings(self.settings), target)

        reopened = viewer.create_app(self.settings).test_client()
        index = reopened.get('/')
        self.assertIn('data-connected="true"', index.text)
        self.assertNotIn(self.password, index.text)
        self.assertNotRegex(index.text, r'<input[^>]*id="password"[^>]*\bvalue=')
        with patch('app.socket.create_connection'):
            self.assertEqual(self.connect(client=reopened, username='', password='').status_code, 200)

    def test_audio_handles_missing_ffmpeg_and_bounds_boost(self):
        with patch('app.socket.create_connection'):
            self.assertEqual(self.connect().status_code, 200)
        with patch('app.shutil.which', return_value=None):
            self.assertEqual(self.client.get('/audio').status_code, 503)
        with patch('app.shutil.which', return_value='ffmpeg'), patch('app.Camera.audio_chunks') as chunks:
            chunks.return_value = iter([b'audio fixture'])
            response = self.client.get('/audio?boost=100')
            self.assertEqual(response.mimetype, 'audio/mpeg')
            self.assertEqual(response.data, b'audio fixture')
            self.assertEqual(chunks.call_args.args[:2], ('ffmpeg', 40))


if __name__ == '__main__':
    unittest.main()
