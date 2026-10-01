import os, socket, sqlite3
from pathlib import Path
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
import dotenv
dotenv.load_dotenv = lambda *a, **k: False
dotenv.dotenv_values = lambda *a, **k: {}
_original_connect = sqlite3.connect
def safe_connect(database, *a, **k):
    raw = str(database)
    if raw != ':memory:':
        path = raw.removeprefix('file:').split('?', 1)[0]
        resolved = Path(path).resolve()
        if not str(resolved).startswith('/private/tmp/'):
            raise RuntimeError('AUDIT_BLOCKED_NON_TEMP_DATABASE: ' + str(resolved))
    return _original_connect(database, *a, **k)
sqlite3.connect = safe_connect
_original_socket_connect = socket.socket.connect
_original_socket_connect_ex = socket.socket.connect_ex
def safe_socket_connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6):
        if address[0] not in ('127.0.0.1', 'localhost', '::1'):
            raise RuntimeError('AUDIT_BLOCKED_EXTERNAL_NETWORK')
    return _original_socket_connect(self, address)
def safe_socket_connect_ex(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6):
        if address[0] not in ('127.0.0.1', 'localhost', '::1'):
            raise RuntimeError('AUDIT_BLOCKED_EXTERNAL_NETWORK')
    return _original_socket_connect_ex(self, address)
socket.socket.connect = safe_socket_connect
socket.socket.connect_ex = safe_socket_connect_ex
_original_getaddrinfo = socket.getaddrinfo
def safe_getaddrinfo(host, *a, **k):
    if host not in (None, '127.0.0.1', 'localhost', '::1'):
        raise RuntimeError('AUDIT_BLOCKED_EXTERNAL_DNS')
    return _original_getaddrinfo(host, *a, **k)
socket.getaddrinfo = safe_getaddrinfo
