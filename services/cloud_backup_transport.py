"""Fixed restic S3 adapter; owner credentials never enter command arguments/logs."""
from __future__ import annotations

import configparser
import ctypes
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from services.cloud_backups import CloudConfig, CloudError, _HEX, _private, _safe_path

RESTIC_EXECUTABLE = '/opt/homebrew/bin/restic'
KEYCHAIN_ACCOUNT = 'ai-trainer-cloud-backup'


def _keychain_password(service: str) -> str:
    """Read one explicitly provisioned item with Keychain UI disabled in-process."""
    if sys.platform != 'darwin':
        raise CloudError('cloud_credentials_unavailable')
    library = ctypes.CDLL('/System/Library/Frameworks/Security.framework/Security')
    find = library.SecKeychainFindGenericPassword
    find.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p,
                     ctypes.c_uint32, ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint32),
                     ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
    find.restype = ctypes.c_int32
    library.SecKeychainGetUserInteractionAllowed.argtypes = [ctypes.POINTER(ctypes.c_ubyte)]
    library.SecKeychainSetUserInteractionAllowed.argtypes = [ctypes.c_ubyte]
    library.SecKeychainItemFreeContent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    original = ctypes.c_ubyte()
    if library.SecKeychainGetUserInteractionAllowed(ctypes.byref(original)) != 0:
        raise CloudError('cloud_credentials_unavailable')
    if library.SecKeychainSetUserInteractionAllowed(0) != 0:
        raise CloudError('cloud_credentials_unavailable')
    length, data = ctypes.c_uint32(), ctypes.c_void_p()
    try:
        account, name = KEYCHAIN_ACCOUNT.encode(), service.encode()
        status = find(None, len(name), name, len(account), account,
                      ctypes.byref(length), ctypes.byref(data), None)
        if status != 0 or not data.value or not length.value:
            raise CloudError('cloud_credentials_unavailable')
        return ctypes.string_at(data, length.value).decode('utf-8')
    finally:
        if data.value:
            library.SecKeychainItemFreeContent(None, data)
        library.SecKeychainSetUserInteractionAllowed(original)


def _credentials(config: CloudConfig) -> tuple[str, str, str]:
    try:
        path = _safe_path(Path.home() / '.aws' / 'credentials')
        _private(path)
        if path.stat().st_size > 1024 * 1024:
            raise ValueError
        profile = configparser.ConfigParser(interpolation=None)
        profile.read_string(path.read_text())
        if profile.defaults() or not profile.has_section(config.aws_profile):
            raise ValueError
        key = profile.get(config.aws_profile, 'aws_access_key_id')
        secret = profile.get(config.aws_profile, 'aws_secret_access_key')
        if not key or not secret or profile.has_option(config.aws_profile, 'aws_session_token'):
            raise ValueError
        password = _keychain_password(config.keychain_service)
        if not password or '\n' in password or '\x00' in password:
            raise ValueError
        return key, secret, password
    except (OSError, ValueError, configparser.Error):
        raise CloudError('cloud_credentials_unavailable') from None


class ResticTransport:
    """Use only an existing repository: cat config, backup and exact-ID restore."""

    def __init__(self, config: CloudConfig, work: Path, deadline: float) -> None:
        self.config, self.work, self.deadline = config, work, deadline
        key, secret, password = _credentials(config)
        self.env = {k: os.environ[k] for k in ('HOME', 'PATH', 'TMPDIR', 'SSL_CERT_FILE', 'SSL_CERT_DIR') if k in os.environ}
        self.env.update({'AWS_ACCESS_KEY_ID': key, 'AWS_SECRET_ACCESS_KEY': secret,
            'AWS_DEFAULT_REGION': 'ru-central-1', 'AWS_EC2_METADATA_DISABLED': 'true',
            'RESTIC_PASSWORD': password, 'RESTIC_HOST': 'ai-trainer'})
        if 'AI_TRAINER_SCRATCH_SCOPE' in os.environ:
            from scripts.scratch_pytest import child_environment
            self.env = child_environment(self.env)
        version = self._command(['version'], repository=False)
        if not re.match(r'^restic 0\.19\.1(?:\s|$)', version):
            raise CloudError('cloud_config_invalid')

    def _command(self, command: list[str], *, repository: bool = True, cwd: Path | None = None) -> str:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise CloudError('cloud_timeout')
        args = [RESTIC_EXECUTABLE]
        if repository:
            args += ['--repo', self.config.repository_url, '--no-cache', '--json',
                '-o', 's3.region=ru-central-1', '-o', 's3.bucket-lookup=path',
                '-o', 's3.storage-class=STANDARD', '-o', 's3.retries=1',
                '--stuck-request-timeout', '20s']
        try:
            # No new session here: the outer operator worker owns the whole group.
            result = subprocess.run(args + command, cwd=cwd, env=self.env, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    text=True, timeout=remaining)
        except subprocess.TimeoutExpired:
            raise CloudError('cloud_timeout') from None
        except OSError:
            raise CloudError('cloud_credentials_unavailable') from None
        if result.returncode:
            reason = {10: 'cloud_identity_unknown', 11: 'cloud_busy', 12: 'cloud_auth_failed'}
            raise CloudError(reason.get(result.returncode, 'cloud_network_failed'))
        return result.stdout

    def repository_id(self) -> str:
        try:
            value = json.loads(self._command(['cat', 'config']))
            return value['id'] if value.get('version') == 2 and _HEX.fullmatch(value['id']) else ''
        except (ValueError, KeyError, TypeError):
            raise CloudError('cloud_identity_unknown') from None

    def backup(self, payload: Path) -> str:
        output = self._command(['backup', 'snapshot.db', 'manifest.json', '--host', 'ai-trainer'], cwd=payload)
        try:
            summaries = [value for line in output.splitlines() if (value := json.loads(line)).get('message_type') == 'summary']
            if len(summaries) != 1 or not _HEX.fullmatch(summaries[0]['snapshot_id']):
                raise ValueError
            return summaries[0]['snapshot_id']
        except (ValueError, KeyError, TypeError):
            raise CloudError('cloud_snapshot_invalid') from None

    def restore(self, snapshot_id: str, target: Path) -> None:
        if not _HEX.fullmatch(snapshot_id) or target.exists() or target.is_symlink():
            raise CloudError('cloud_snapshot_invalid')
        self._command(['restore', snapshot_id, '--target', str(target), '--verify'])
