import base64
import ctypes
import ipaddress
import json
import logging
import os
import re
from ctypes import wintypes
from dataclasses import dataclass, field, replace
from pathlib import Path
from tempfile import NamedTemporaryFile


DEFAULT_PORT = 554
DEFAULT_USER = 'admin'
SETTINGS_FILE = Path(__file__).resolve().with_name('eyesec_settings.json')
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CameraSettings:
    ip: str = ''
    port: int = DEFAULT_PORT
    username: str = DEFAULT_USER
    password: str = field(default='', repr=False)

    @property
    def endpoint(self):
        return self.ip, self.port

    @property
    def identity(self):
        return self.ip, self.port, self.username


def parse_address(value):
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError('Enter a valid camera IP address.')
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        raise ValueError('Enter a valid camera IP address.') from None
    scope = getattr(address, 'scope_id', None)
    if address.is_unspecified or address.is_multicast or (
        scope is not None and not re.fullmatch(r'[a-zA-Z0-9_.-]+', scope)
    ):
        raise ValueError('Enter a valid camera IP address.')
    return str(address)


def parse_port(value):
    if isinstance(value, str) and re.fullmatch(r'[0-9]{1,5}', value.strip()):
        value = int(value)
    if type(value) is not int or not 1 <= value <= 65535:
        raise ValueError('Enter a port from 1 to 65535.')
    return value


def parse_credential(value, max_length):
    if not isinstance(value, str) or len(value) > max_length or re.search(r'[\x00-\x1f\x7f]', value):
        raise ValueError('Enter valid camera credentials.')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError:
        raise ValueError('Enter valid camera credentials.') from None
    return value


class _DataBlob(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_byte))]


def _dpapi(data, decrypt=False):
    raw = ctypes.create_string_buffer(data, len(data))
    source = _DataBlob(len(data), ctypes.cast(raw, ctypes.POINTER(ctypes.c_byte)))
    target = _DataBlob()
    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    description_type = ctypes.c_void_p if decrypt else ctypes.c_wchar_p
    function = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    function.argtypes = [
        ctypes.POINTER(_DataBlob), description_type, ctypes.POINTER(_DataBlob),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob),
    ]
    function.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    description = None if decrypt else 'EYESEC camera password'
    ui_forbidden = 0x1
    if not function(
        ctypes.byref(source), description, None, None, None, ui_forbidden, ctypes.byref(target),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(target.pbData, ctypes.c_void_p))


def _option(parser, *values):
    for value in values:
        if value is not None and value != '':
            try:
                return parser(value)
            except ValueError:
                continue
    return ''


def load_settings(path=SETTINGS_FILE):
    try:
        saved = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(saved, dict):
            saved = {}
    except FileNotFoundError:
        saved = {}
    except (OSError, ValueError):
        logger.warning('Could not read saved camera settings')
        saved = {}

    def username(value):
        return parse_credential(value, 128)

    remembered = CameraSettings(
        _option(parse_address, saved.get('ip')),
        _option(parse_port, saved.get('port'), DEFAULT_PORT),
        _option(username, saved.get('username'), DEFAULT_USER),
    )
    selected = CameraSettings(
        _option(parse_address, os.environ.get('CAMERA_IP'), remembered.ip),
        _option(parse_port, os.environ.get('CAMERA_PORT'), remembered.port),
        _option(username, os.environ.get('CAMERA_USER'), remembered.username),
    )
    password = _option(lambda value: parse_credential(value, 256), os.environ.get('CAMERA_PASSWORD'))
    if not password and remembered.ip and remembered.identity == selected.identity and os.name == 'nt':
        encrypted = saved.get('password_dpapi')
        if encrypted:
            try:
                blob = base64.b64decode(encrypted, validate=True)
                decoded = _dpapi(blob, decrypt=True).decode('utf-8')
                password = parse_credential(decoded, 256)
            except (OSError, TypeError, ValueError):
                logger.warning('Could not unlock the saved camera password')

    return replace(selected, password=password)


def save_settings(settings, path=SETTINGS_FILE):
    saved = {'ip': settings.ip, 'port': settings.port, 'username': settings.username}
    if os.name == 'nt' and settings.password:
        try:
            encrypted = _dpapi(settings.password.encode('utf-8'))
            saved['password_dpapi'] = base64.b64encode(encrypted).decode('ascii')
        except OSError:
            logger.warning('Could not protect the camera password for this Windows user')

    temp_path = None
    try:
        with NamedTemporaryFile(
            mode='w', encoding='utf-8', dir=path.parent, prefix=path.stem + '.', suffix='.tmp', delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(saved, handle, indent=2)
        temp_path.replace(path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
