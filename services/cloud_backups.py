"""Opt-in export of validated snapshots; no cloud initialization or pruning."""
from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from typing import Callable

from config.cloud_backup import cloud_context_disabled, cloud_worker_environment
from services import automatic_snapshots as snapshots
from services.sqlite_snapshot_core import inspect_database, readonly_connection

ATTEMPT_SECONDS = 600.0
STAGE_SECONDS = 10.0
_HEX = re.compile(r'^[0-9a-f]{64}$')
_ID = re.compile(r'^[0-9a-f]{32}$')
_REASONS = frozenset({'cloud_busy', 'cloud_config_invalid', 'cloud_identity_unknown',
    'cloud_snapshot_invalid', 'cloud_credentials_unavailable', 'cloud_auth_failed',
    'cloud_network_failed', 'cloud_timeout', 'cloud_state_unwritable',
    'cloud_local_backup_unavailable'})
_FIELDS = frozenset({'version', 'enabled', 'database_path', 'backup_root',
    'source_namespace', 'repository_url', 'expected_repository_id', 'aws_profile',
    'keychain_service'})
_TIMES = ('last_attempt_at', 'last_verified_at', 'last_covered_check_at', 'last_drill_at')


class CloudError(RuntimeError):
    """Stable public reason; never include command output, paths or credentials."""


@dataclass(frozen=True)
class CloudSelection:
    database_path: str
    backup_root: str
    local_enabled: bool
    demo_database_path: str | None = None
    acceptance: bool = False


@dataclass(frozen=True)
class CloudConfig:
    path: Path
    database_path: Path
    backup_root: Path
    source_namespace: str
    repository_url: str
    expected_repository_id: str
    aws_profile: str
    keychain_service: str
    content_digest: str

    @property
    def state_path(self) -> Path:
        return self.path.parent / 'receipt.json'


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _instant(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError('timestamp string required')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timezone required')
    return parsed.astimezone(timezone.utc)


def _safe_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('absolute canonical path required')
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError('linked path')
    return path


def _private(path: Path, *, directory: bool = False) -> None:
    info = path.lstat()
    valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode) and info.st_nlink == 1
    if not valid or (os.name == 'posix' and (info.st_uid != os.getuid() or info.st_mode & 0o077)):
        raise ValueError('private owner path required')


def _outside_checkout(path: Path) -> None:
    if any((item / '.git').exists() or (item / '.git').is_symlink() for item in (path, *path.parents)):
        raise ValueError('checkout is not an artifact directory')


def _unique_json(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def _json(path: Path) -> dict:
    _private(path)
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('oversized metadata')
    result = json.loads(path.read_text(), object_pairs_hook=_unique_json)
    if not isinstance(result, dict):
        raise ValueError('object required')
    return result


def load_config(path: str | Path) -> CloudConfig | None:
    """Validate explicit owner config without SQLite, Settings or secret access."""
    try:
        path = _safe_path(path)
        if not path.exists():
            return None
        _private(path.parent, directory=True)
        _outside_checkout(path.parent)
        value = _json(path)
        if set(value) - _FIELDS or type(value.get('version')) is not int or value['version'] != 1 or type(value.get('enabled')) is not bool:
            raise ValueError
        if not value['enabled']:
            return None
        if set(value) != _FIELDS:
            raise ValueError
        source, root = _safe_path(value['database_path']), _safe_path(value['backup_root'])
        private = path.parent
        if source.is_relative_to(private) or root.is_relative_to(private) or private.is_relative_to(root):
            raise ValueError
        url = value['repository_url']
        if not re.fullmatch(r's3:https://s3\.cloud\.ru/ai-trainer-backups/[A-Za-z0-9_/-]+', url):
            raise ValueError
        if any(part in {'.', '..', ''} for part in url.split('/')[4:]):
            raise ValueError
        if not all(_HEX.fullmatch(value[key]) for key in ('source_namespace', 'expected_repository_id')):
            raise ValueError
        if not all(re.fullmatch(r'[A-Za-z0-9_.-]+', value[key]) for key in ('aws_profile', 'keychain_service')):
            raise ValueError
        return CloudConfig(path, source, root, value['source_namespace'], url,
                           value['expected_repository_id'], value['aws_profile'], value['keychain_service'],
                           hashlib.sha256(snapshots._json_bytes(value)).hexdigest())
    except (OSError, ValueError, TypeError, KeyError, RuntimeError):
        raise CloudError('cloud_config_invalid') from None


def _selection() -> CloudSelection:
    # Lazy: disabled/status with no config must not even load owner .env.
    from config.settings import Settings
    return CloudSelection(str(Settings.DATABASE_PATH), str(Settings.BACKUP_DIR),
                          Settings.AUTO_BACKUP_ENABLED, str(Settings.DEMO_DATABASE_PATH), Settings.ACCEPTANCE_MODE)


def _binding(config: CloudConfig, selected: CloudSelection) -> None:
    try:
        if (not selected.local_enabled or selected.acceptance
                or Path(selected.database_path) != config.database_path
                or Path(selected.backup_root) != config.backup_root
                or (selected.demo_database_path is not None and Path(selected.demo_database_path) == config.database_path)):
            raise ValueError
        _, _, identity = snapshots._paths(config.database_path, config.backup_root)
        if identity != config.source_namespace:
            raise ValueError
    except (OSError, ValueError, snapshots.SnapshotError):
        raise CloudError('cloud_local_backup_unavailable') from None


def _receipt(config: CloudConfig, now: datetime) -> dict:
    if not config.state_path.exists() and not config.state_path.is_symlink():
        return {}
    try:
        state = _json(config.state_path)
        allowed = {'version', 'repository_id', 'source_namespace', 'reason_code', 'pending',
                   'snapshot_id', 'source_generation', 'sha256', 'remote_snapshot_id', 'drill_failed', *_TIMES}
        if (set(state) - allowed or type(state.get('version')) is not int or state['version'] != 1
                or state.get('repository_id') != config.expected_repository_id
                or state.get('source_namespace') != config.source_namespace
                or state.get('reason_code') not in _REASONS | {None}
                or type(state.get('pending', False)) is not bool
                or type(state.get('drill_failed', False)) is not bool):
            raise ValueError
        for key in _TIMES:
            if state.get(key) is not None and _instant(state[key]) > now:
                raise ValueError
        evidence = ('snapshot_id', 'source_generation', 'sha256', 'remote_snapshot_id',
                    'last_verified_at', 'last_covered_check_at')
        if any(state.get(key) is not None for key in evidence):
            if (not all(state.get(key) for key in evidence)
                    or not _ID.fullmatch(state['snapshot_id'])
                    or not all(_HEX.fullmatch(state[key]) for key in ('source_generation', 'sha256', 'remote_snapshot_id'))):
                raise ValueError
        return state
    except (OSError, ValueError, TypeError, KeyError):
        raise CloudError('cloud_identity_unknown') from None


def _public(state: str = 'unknown', reason: str | None = None, receipt: dict | None = None,
            *, now: datetime | None = None) -> dict:
    receipt = receipt or {}
    now = now or _now()
    drill = receipt.get('last_drill_at')
    return {'state': state, 'reason_code': reason,
            **{key: receipt.get(key) for key in _TIMES},
            'drill_warning': (None if state == 'disabled' else 'cloud_drill_failed' if receipt.get('drill_failed') else
                'cloud_drill_due' if not drill or now - _instant(drill) >= timedelta(days=30) else None)}


def read_cloud_status(config_path: str | Path, *, selection: CloudSelection | None = None,
                      now: datetime | None = None, demo: bool = False) -> dict:
    """Read operational files only; never construct Database, contact cloud or mutate."""
    if cloud_context_disabled(demo=demo, acceptance=bool(selection and selection.acceptance)):
        return _public('disabled')
    now = now or _now()
    receipt = {}
    try:
        config = load_config(config_path)
        if config is None:
            return _public('disabled')
        receipt = _receipt(config, now)
        _binding(config, selection or _selection())
        if receipt.get('pending') or receipt.get('reason_code'):
            return _public('degraded', receipt.get('reason_code') or 'cloud_network_failed', receipt, now=now)
        if not receipt.get('last_verified_at'):
            return _public(now=now)
        local = snapshots.read_snapshot_status(config.database_path, config.backup_root)
        if local['state'] != 'ready':
            return _public('stale', None, receipt, now=now)
        current = config.backup_root / config.source_namespace / 'snapshots' / str(local['last_snapshot_id'])
        if not current.exists():
            return _public('stale', None, receipt, now=now)
        manifest = _json(current / 'manifest.json')
        _manifest_metadata(manifest, config)
        match = (local['last_snapshot_id'] == receipt['snapshot_id']
                 and manifest['snapshot_id'] == receipt['snapshot_id']
                 and manifest.get('source_generation') == receipt['source_generation']
                 and manifest.get('sha256') == receipt['sha256'])
        fresh = all(timedelta(0) <= now - _instant(receipt[key]) <= timedelta(hours=24)
                    for key in ('last_verified_at', 'last_covered_check_at'))
        return _public('ready' if match and fresh else 'stale', None, receipt, now=now)
    except CloudError as exc:
        return _public('degraded', str(exc), receipt, now=now)
    except (OSError, ValueError, TypeError, KeyError, snapshots.SnapshotError):
        return _public('degraded', 'cloud_snapshot_invalid', receipt, now=now)


def _write_receipt(config: CloudConfig, receipt: dict) -> None:
    try:
        snapshots._write_json(config.state_path, receipt, replace=True)
    except (OSError, ValueError, snapshots.SnapshotError):
        raise CloudError('cloud_state_unwritable') from None


@contextmanager
def _attempt_lock(config: CloudConfig):
    """Publish both success and failure under the same repository exclusion."""
    with snapshots.namespace_lock(config.path.parent, deadline=time.monotonic() + .1):
        previous = _receipt(config, _now())
        try:
            yield previous
        except Exception as exc:
            reason = str(exc) if isinstance(exc, CloudError) and str(exc) in _REASONS else 'cloud_snapshot_invalid'
            if isinstance(exc, sqlite3.Error):
                reason = 'cloud_local_backup_unavailable'
            failure = {'version': 1, 'repository_id': config.expected_repository_id,
                       'source_namespace': config.source_namespace, **previous,
                       'last_attempt_at': _now().isoformat(), 'pending': False, 'reason_code': reason}
            try:
                _write_receipt(config, failure)
            except CloudError:
                reason = 'cloud_state_unwritable'
            raise CloudError(reason) from None


def _manifest_metadata(manifest: dict, config: CloudConfig) -> None:
    """Validate v1 metadata without opening SQLite or hashing the DB on status."""
    if (type(manifest.get('version')) is not int or manifest['version'] != 1
            or manifest.get('source_namespace') != config.source_namespace
            or not _ID.fullmatch(manifest['snapshot_id'])
            or manifest.get('integrity_check') != 'ok'
            or type(manifest['size']) is not int or manifest['size'] <= 0
            or not all(_HEX.fullmatch(manifest[key]) for key in ('sha256', 'source_generation'))
            or _instant(manifest['created_at_utc']) > _now()):
        raise ValueError('invalid manifest metadata')
    fingerprint = manifest['fingerprint']
    if (not isinstance(fingerprint, dict) or fingerprint.get('integrity_check') != 'ok'
            or not _HEX.fullmatch(fingerprint['schema_sha256'])
            or not isinstance(fingerprint['tables'], dict)
            or snapshots._generation(fingerprint) != manifest['source_generation']):
        raise ValueError('invalid fingerprint metadata')
    for table in fingerprint['tables'].values():
        if (not isinstance(table, dict) or type(table['rows']) is not int or table['rows'] < 0
                or not _HEX.fullmatch(table['sha256'])):
            raise ValueError('invalid table metadata')


def _validate_pair(directory: Path, config: CloudConfig, expected: dict | None = None) -> dict:
    try:
        _private(directory, directory=True)
        if set(item.name for item in directory.iterdir()) != {'snapshot.db', 'manifest.json'}:
            raise ValueError
        manifest = _json(directory / 'manifest.json')
        _manifest_metadata(manifest, config)
        db = directory / 'snapshot.db'
        _private(db)
        if (manifest.get('version') != 1 or manifest.get('source_namespace') != config.source_namespace
                or not _ID.fullmatch(manifest['snapshot_id']) or manifest.get('integrity_check') != 'ok'
                or db.stat().st_size != manifest['size'] or snapshots._hash(db) != manifest['sha256']):
            raise ValueError
        fingerprint = inspect_database(db)
        if fingerprint != manifest['fingerprint'] or snapshots._generation(fingerprint) != manifest['source_generation']:
            raise ValueError
        with closing(readonly_connection(db)) as connection:
            connection.execute('PRAGMA busy_timeout=0')
            origin = connection.execute("SELECT value FROM user_settings WHERE key='dataset_origin'").fetchone()
        if not origin or origin[0] != 'real':
            raise ValueError
        if expected is not None and manifest != expected:
            raise ValueError
        return manifest
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error, snapshots.SnapshotInspectionError):
        raise CloudError('cloud_snapshot_invalid') from None


def _stage(config: CloudConfig, staging: Path, deadline: float) -> dict:
    namespace = config.backup_root / config.source_namespace
    try:
        with snapshots.namespace_lock(namespace, deadline=deadline):
            state = snapshots._read_json(namespace / 'status.json')
            key = state.get('last_snapshot_id')
            if state.get('state') != 'ready' or not isinstance(key, str) or not _ID.fullmatch(key):
                raise CloudError('cloud_snapshot_invalid')
            covered = state['last_checked_at']
            if not timedelta(0) <= _now() - _instant(covered) <= timedelta(hours=24):
                raise CloudError('cloud_snapshot_invalid')
            origin = namespace / 'snapshots' / key
            _safe_path(origin)
            _private(origin, directory=True)
            for name in ('snapshot.db', 'manifest.json'):
                source, target = origin / name, staging / name
                _private(source)
                with source.open('rb') as incoming, target.open('xb') as outgoing:
                    os.chmod(target, 0o600)
                    while block := incoming.read(1024 * 1024):
                        if time.monotonic() >= deadline:
                            raise CloudError('cloud_timeout')
                        outgoing.write(block)
                    outgoing.flush()
                    os.fsync(outgoing.fileno())
            manifest = _validate_pair(staging, config)
            if manifest['snapshot_id'] != key:
                raise CloudError('cloud_snapshot_invalid')
            return {'manifest': manifest, 'covered': covered}
    except snapshots.SnapshotError:
        raise CloudError('cloud_busy') from None


def _child_env() -> dict[str, str]:
    result = cloud_worker_environment()
    if 'AI_TRAINER_SCRATCH_SCOPE' in result:
        from scripts.scratch_pytest import child_environment
        return child_environment(result)
    return result


@contextmanager
def _owned_work(parent: Path, *, prefix: str):
    """Never adopt or remove a directory that replaced our allocated inode."""
    work = Path(tempfile.mkdtemp(prefix=prefix, dir=parent))
    work.chmod(0o700)
    identity = work.lstat()
    try:
        yield work
    finally:
        current = work.lstat()
        if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino):
            raise CloudError('cloud_identity_unknown')
        shutil.rmtree(work)


def _bounded_stage(config: CloudConfig, staging: Path) -> dict:
    identity = staging.lstat()
    request = {'config_path': str(config.path), 'staging': str(staging),
               'config_digest': config.content_digest,
               'identity': [identity.st_dev, identity.st_ino],
               'deadline': time.monotonic() + STAGE_SECONDS - .05}
    try:
        result = subprocess.run([sys.executable, '-m', __name__, '--stage'],
            input=json.dumps(request), capture_output=True, text=True, env=_child_env(), timeout=STAGE_SECONDS)
        value = json.loads(result.stdout)
        if value.get('error'):
            raise CloudError(value['error'] if value['error'] in _REASONS else 'cloud_snapshot_invalid')
        if result.returncode:
            raise CloudError('cloud_snapshot_invalid')
        return value
    except subprocess.TimeoutExpired:
        raise CloudError('cloud_timeout') from None
    except (OSError, ValueError):
        raise CloudError('cloud_snapshot_invalid') from None


def _drill_due(receipt: dict) -> bool:
    return (not receipt.get('last_drill_at')
            or _now() - _instant(receipt['last_drill_at']) >= timedelta(days=30))


def _perform_drill(config: CloudConfig, previous: dict, parent: Path, deadline: float,
                   transport_factory: Callable | None = None) -> dict:
    """Caller owns repository lock; upload evidence never changes in this slice."""
    state = {'version': 1, 'repository_id': config.expected_repository_id,
             'source_namespace': config.source_namespace, **previous}
    try:
        with _owned_work(parent, prefix='drill-') as work:
            if transport_factory is None:
                from services.cloud_backup_transport import ResticTransport
                transport_factory = ResticTransport
            transport = transport_factory(config, work, deadline)
            if transport.repository_id() != config.expected_repository_id:
                raise CloudError('cloud_identity_unknown')
            remote_id = transport.latest_snapshot_id()
            if not isinstance(remote_id, str) or not _HEX.fullmatch(remote_id):
                raise CloudError('cloud_snapshot_invalid')
            restored = work / 'restored'
            transport.restore(remote_id, restored)
            manifest = _validate_pair(restored, config)
            from services.cloud_backup_drill import verify_domains
            verify_domains(restored / 'snapshot.db')
            if inspect_database(restored / 'snapshot.db') != manifest['fingerprint']:
                raise CloudError('cloud_snapshot_invalid')
        # Cleanup is part of success: a replaced directory never grants success.
        state.update(last_drill_at=_now().isoformat(), drill_failed=False)
    except Exception:
        # Public drill warning is independent of upload reason/coverage.
        state['drill_failed'] = True
    _write_receipt(config, state)
    return state


def _drill_once(config_path: str | Path, *, transport_factory: Callable | None = None,
                work_parent: Path | None = None) -> dict:
    """Recover remote data even when source, local snapshots and receipt are lost."""
    previous = {}
    if cloud_context_disabled():
        return _public('disabled')
    try:
        config = load_config(config_path)
        if config is None:
            return _public('disabled')
        with snapshots.namespace_lock(config.path.parent, deadline=time.monotonic() + .1):
            previous = _receipt(config, _now())  # Never overwrite foreign/corrupt state.
            previous = _perform_drill(config, previous, work_parent or config.path.parent,
                                      time.monotonic() + ATTEMPT_SECONDS, transport_factory)
        # Local coverage cannot be inferred from a remote-only operation.
        return _public('unknown', previous.get('reason_code'), previous)
    except CloudError as exc:
        return _public('degraded', str(exc), {**previous, 'drill_failed': True})
    except snapshots.SnapshotError:
        return _public('degraded', 'cloud_busy', {**previous, 'drill_failed': True})
    except (OSError, ValueError, TypeError, KeyError):
        return _public('degraded', 'cloud_snapshot_invalid', {**previous, 'drill_failed': True})


def _run_once(config_path: str | Path, *, selection: CloudSelection | None = None,
              transport_factory: Callable | None = None, work_parent: Path | None = None) -> dict:
    if cloud_context_disabled(acceptance=bool(selection and selection.acceptance)):
        return _public('disabled')
    config = None
    previous = {}
    try:
        config = load_config(config_path)
        if config is None:
            return _public('disabled')
        previous = _receipt(config, _now())  # Unknown identity never grants overwrite.
        _binding(config, selection or _selection())
        deadline = time.monotonic() + ATTEMPT_SECONDS
        with _attempt_lock(config) as locked_previous:
            previous = locked_previous
            state = {'version': 1, 'repository_id': config.expected_repository_id,
                     'source_namespace': config.source_namespace, **previous,
                     'last_attempt_at': _now().isoformat(), 'pending': True, 'reason_code': None}
            _write_receipt(config, state)
            # Read provenance without Database initialization, migrations or writer PRAGMAs.
            with closing(readonly_connection(config.database_path)) as connection:
                connection.execute('PRAGMA busy_timeout=0')
                row = connection.execute("SELECT value FROM user_settings WHERE key='dataset_origin'").fetchone()
            if not row or row[0] != 'real':
                raise CloudError('cloud_local_backup_unavailable')
            checked = snapshots.check_snapshot(config.database_path, config.backup_root, 'cloud_upload')
            if checked['state'] != 'ready':
                raise CloudError('cloud_local_backup_unavailable')
            # The context removes only this freshly allocated directory, never an old orphan.
            with _owned_work(work_parent or config.path.parent, prefix='attempt-') as work:
                payload = work / 'payload'
                payload.mkdir(mode=0o700)
                staged = _bounded_stage(config, payload)
                manifest = staged['manifest']
                if transport_factory is None:
                    from services.cloud_backup_transport import ResticTransport
                    transport_factory = ResticTransport
                transport = transport_factory(config, work, deadline)
                if transport.repository_id() != config.expected_repository_id:
                    raise CloudError('cloud_identity_unknown')
                unchanged = all(previous.get(key) == manifest[key] for key in ('snapshot_id', 'source_generation', 'sha256'))
                remote_id = previous['remote_snapshot_id'] if unchanged else transport.backup(payload)
                if not isinstance(remote_id, str) or not _HEX.fullmatch(remote_id):
                    raise CloudError('cloud_snapshot_invalid')
                restored = work / 'restored'
                transport.restore(remote_id, restored)
                _validate_pair(restored, config, manifest)
                verified = {**state, 'pending': False, 'reason_code': None,
                    'snapshot_id': manifest['snapshot_id'], 'sha256': manifest['sha256'],
                    'source_generation': manifest['source_generation'], 'remote_snapshot_id': remote_id,
                    'last_verified_at': _now().isoformat(), 'last_covered_check_at': staged['covered']}
                _write_receipt(config, verified)
                if _drill_due(verified):
                    _perform_drill(config, verified, work, deadline, transport_factory)
            return read_cloud_status(config.path, selection=selection)
    except CloudError as exc:
        reason = str(exc)
    except snapshots.SnapshotError:
        reason = 'cloud_busy'
    except (OSError, ValueError, TypeError, KeyError):
        reason = 'cloud_snapshot_invalid'
    return _public('degraded', reason, previous)


def _worker_failure(config_path: str | Path, reason: str, *, drill: bool = False) -> dict:
    previous = {}
    try:
        config = load_config(config_path)
        if config is None:
            return _public('disabled')
        with snapshots.namespace_lock(config.path.parent, deadline=time.monotonic() + .1):
            previous = _receipt(config, _now())
            failed = {'version': 1, 'repository_id': config.expected_repository_id,
                      'source_namespace': config.source_namespace, **previous}
            if drill:
                failed['drill_failed'] = True
            else:
                failed.update(last_attempt_at=_now().isoformat(), pending=False, reason_code=reason)
            _write_receipt(config, failed)
    except (CloudError, snapshots.SnapshotError, OSError):
        reason = 'cloud_state_unwritable'
    return _public('degraded', reason, {**previous, 'drill_failed': True} if drill else previous)


def _run_operator(config_path: str | Path, *, demo: bool = False, drill: bool = False) -> dict:
    """Bound all work, including SQLite C calls, in one disposable process group."""
    try:
        if cloud_context_disabled(demo=demo):
            return _public('disabled')
        config = load_config(config_path)
        if config is None:
            return _public('disabled')
        # Parent ownership lets a timeout remove even a SIGKILLed child's staging.
        with _owned_work(config.path.parent, prefix='attempt-process-') as work:
            info = work.lstat()
            args = [sys.executable, '-m', __name__, '--drill' if drill else '--run', str(config.path), str(work),
                    str(info.st_dev), str(info.st_ino)]
            with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, env=_child_env(), start_new_session=True) as worker:
                try:
                    output, _ = worker.communicate(timeout=ATTEMPT_SECONDS)
                    value = json.loads(output)
                    if not worker.returncode and isinstance(value, dict) and value.get('state') in {'ready', 'stale', 'unknown', 'degraded', 'disabled'}:
                        return value
                except subprocess.TimeoutExpired:
                    os.killpg(worker.pid, signal.SIGKILL)
                    worker.communicate()
                    return _worker_failure(config.path, 'cloud_timeout', drill=drill)
        return _worker_failure(config.path, 'cloud_network_failed', drill=drill)
    except CloudError as exc:
        return _public('degraded', str(exc))
    except (OSError, ValueError):
        return _public('degraded', 'cloud_state_unwritable')


def run_cloud_backup(config_path: str | Path, *, demo: bool = False) -> dict:
    """Bound upload and any due drill in one process group and one deadline."""
    return _run_operator(config_path, demo=demo)


def run_cloud_drill(config_path: str | Path, *, demo: bool = False) -> dict:
    """Explicit bounded remote-only drill; never restore over a selected source."""
    return _run_operator(config_path, demo=demo, drill=True)


def _main() -> None:
    try:
        if sys.argv[1:] == ['--stage']:
            request = json.load(sys.stdin)
            config = load_config(request['config_path'])
            if config is None or config.content_digest != request['config_digest']:
                raise CloudError('cloud_config_invalid')
            staging = _safe_path(request['staging'])
            _private(staging, directory=True)
            info = staging.lstat()
            if (staging.name != 'payload' or not staging.is_relative_to(config.path.parent)
                    or [info.st_dev, info.st_ino] != request['identity'] or any(staging.iterdir())):
                raise CloudError('cloud_identity_unknown')
            print(json.dumps(_stage(config, staging, request['deadline'])))
        elif len(sys.argv) == 6 and sys.argv[1] in {'--run', '--drill'}:
            config = load_config(sys.argv[2])
            work = _safe_path(sys.argv[3])
            _private(work, directory=True)
            info = work.lstat()
            if config is None or work.parent != config.path.parent or (info.st_dev, info.st_ino) != (int(sys.argv[4]), int(sys.argv[5])):
                raise CloudError('cloud_identity_unknown')
            operation = _drill_once if sys.argv[1] == '--drill' else _run_once
            print(json.dumps(operation(config.path, work_parent=work)))
        else:
            raise SystemExit(2)
    except CloudError as exc:
        print(json.dumps({'error': str(exc)}))
        raise SystemExit(2) from None
    except (OSError, ValueError, TypeError, KeyError):
        print(json.dumps({'error': 'cloud_snapshot_invalid'}))
        raise SystemExit(2) from None


if __name__ == '__main__':
    # Keep worker/staging dispatch and transport exception types in one module.
    from services.cloud_backups import _main as entrypoint
    entrypoint()
