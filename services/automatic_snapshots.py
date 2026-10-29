"""Bounded snapshot core. No lifecycle hooks, Settings or automatic activation."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid

from config.database_paths import database_family, database_namespace_key
from services.sqlite_snapshot_core import SnapshotInspectionError, copy_sqlite, inspect_database

DEADLINE_SECONDS = 10.0
_ID = re.compile(r'^[0-9a-f]{32}$')


class SnapshotError(RuntimeError):
    """A stable reason suitable for API status, without paths or row values."""


def _status(state: str, reason: str | None = None, previous: dict | None = None) -> dict:
    previous = previous or {}
    return {'state': state, 'reason_code': reason,
            'last_checked_at': datetime.now(timezone.utc).isoformat(),
            'last_snapshot_at': previous.get('last_snapshot_at'),
            'last_snapshot_id': previous.get('last_snapshot_id')}


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def _generation(fingerprint: dict) -> str:
    return hashlib.sha256(_json_bytes(fingerprint)).hexdigest()


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda: file.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _regular(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise SnapshotError('backup_identity_unknown')


def _private_directory(path: Path) -> bool:
    try:
        path.mkdir(mode=0o700)
        created = True
    except FileExistsError:
        created = False
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise SnapshotError('backup_identity_unknown')
    if os.name == 'posix' and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077):
        raise SnapshotError('backup_identity_unknown')
    return created


def _source_namespace(source: Path) -> str:
    # Use the filesystem's actual entry spellings. Casefold/NFC would merge
    # distinct files on Linux; raw caller spelling would split native aliases.
    canonical = Path(source.anchor)
    for part in source.parts[1:]:
        target = canonical / part
        wanted = target.stat()
        with os.scandir(canonical) as entries:
            actual = next((entry.name for entry in entries
                           if entry.stat(follow_symlinks=False).st_ino == wanted.st_ino and
                           entry.stat(follow_symlinks=False).st_dev == wanted.st_dev), None)
        if actual is None:
            raise SnapshotError('backup_identity_unknown')
        canonical = canonical / actual
    return hashlib.sha256(os.path.normcase(str(canonical)).encode()).hexdigest()


def _paths(source: str | Path, root: str | Path) -> tuple[Path, Path, str]:
    source, root = Path(source), Path(root)
    if not source.is_absolute() or not root.is_absolute():
        raise SnapshotError('backup_identity_unknown')
    _regular(source)
    for member in database_family(source):
        if member.exists() or member.is_symlink():
            _regular(member)
    # Reject linked endpoints and aliases through existing parents. The caller
    # supplies the canonical selected path, as the ordinary path resolver does.
    for path in (source, root):
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            raise SnapshotError('backup_identity_unknown')
    source, root = source.resolve(strict=True), root.resolve()
    if any((parent / '.git').exists() or (parent / '.git').is_symlink() for parent in (root, *root.parents)):
        raise SnapshotError('backup_identity_unknown')
    if root == source or source.is_relative_to(root):
        raise SnapshotError('backup_identity_unknown')
    for member in database_family(source):
        if database_namespace_key(root) == database_namespace_key(member):
            raise SnapshotError('backup_identity_unknown')
    identity = _source_namespace(source)
    return source, root, identity


def _fsync_directory(path: Path) -> None:
    if os.name == 'nt':
        return  # Native Windows durability requires separate acceptance.
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_json(path: Path, value: dict, *, replace: bool = False) -> None:
    if path.exists() or path.is_symlink():
        _regular(path)
        if not replace:
            raise SnapshotError('backup_identity_unknown')
    descriptor, raw = tempfile.mkstemp(prefix='.json-', dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, 'wb') as file:
            os.fchmod(file.fileno(), 0o600)
            file.write(_json_bytes(value))
            file.flush()
            os.fsync(file.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def namespace_lock(directory: Path, *, deadline: float | None = None):
    """OS-owned advisory lock, including independent callers/worker processes."""
    path = directory / 'lock'
    if path.exists() or path.is_symlink():
        _regular(path)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        _regular(path)
        if os.name == 'posix':
            import fcntl
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if deadline is not None and time.monotonic() >= deadline:
                        raise SnapshotError('backup_busy')
                    time.sleep(.02)
        elif os.name == 'nt':
            import msvcrt
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b'0')
            while True:
                try:
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if deadline is not None and time.monotonic() >= deadline:
                        raise SnapshotError('backup_busy')
                    time.sleep(.02)
        else:
            raise SnapshotError('backup_identity_unknown')
        yield
    finally:
        os.close(descriptor)  # OS releases the lock on normal exit or kill.


def _read_json(path: Path) -> dict:
    _regular(path)
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise SnapshotError('backup_integrity_failed')
    return value


def _latest(directory: Path, namespace: str) -> tuple[dict | None, dict | None]:
    candidates = []
    for item in directory.iterdir():
        if not _ID.fullmatch(item.name):
            continue  # Do not adopt, delete or read unknown/temp artifacts.
        if item.is_symlink() or not item.is_dir():
            raise SnapshotError('backup_identity_unknown')
        try:
            manifest = _read_json(item / 'manifest.json')
            if manifest.get('version') != 1 or manifest.get('source_namespace') != namespace or manifest.get('snapshot_id') != item.name:
                continue
            candidates.append((manifest['created_at_utc'], item, manifest))
        except (OSError, ValueError, KeyError):
            continue
    for _, item, manifest in sorted(candidates, reverse=True):
        try:
            db = item / 'snapshot.db'
            _regular(db)
            fingerprint = inspect_database(db)
            if _hash(db) != manifest['sha256'] or db.stat().st_size != manifest['size']:
                continue
            if _generation(fingerprint) != manifest['source_generation'] or fingerprint != manifest['fingerprint']:
                continue
            return manifest, fingerprint
        except (OSError, ValueError, KeyError, SnapshotInspectionError):
            continue
    return None, None


def _publish(temporary: Path, destination: Path) -> None:
    # O_EXCL directory reservation prevents replacement of even an empty foreign
    # directory. It has no manifest and is never a restore candidate. Only this
    # call's own empty reservation is replaced atomically under the OS lock.
    destination.mkdir(mode=0o700)
    info = destination.lstat()
    try:
        os.rename(temporary, destination)
        _fsync_directory(destination.parent)
    except BaseException:
        if destination.exists():
            current = destination.lstat()
            if (current.st_dev, current.st_ino) == (info.st_dev, info.st_ino):
                destination.rmdir()
        raise


def _prepare_root(root: Path) -> None:
    missing = []
    parent = root
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for path in reversed(missing):
        _private_directory(path)
    _private_directory(root)


def _run(source: str | Path, root: str | Path, temporary: Path | None = None, *, deadline: float | None = None) -> dict:
    source, root, identity = _paths(source, root)
    _prepare_root(root)
    namespace = root / identity
    created = _private_directory(namespace)
    marker = namespace / 'namespace.json'
    expected = {'version': 1, 'source_namespace': identity}
    if created:
        _write_json(marker, expected)
    else:
        # A concurrent creator may be publishing its marker; never adopt an
        # existing empty/unknown directory merely because its name matches.
        limit = time.monotonic() + .5
        while not marker.exists() and time.monotonic() < limit:
            time.sleep(.01)
        if not marker.exists():
            raise SnapshotError('backup_identity_unknown')
    with namespace_lock(namespace, deadline=deadline):
        if _read_json(marker) != expected:
            raise SnapshotError('backup_identity_unknown')
        output = namespace / 'snapshots'
        _private_directory(output)
        state_path = namespace / 'status.json'
        old = _read_json(state_path) if state_path.exists() else {}
        pins = old.get('reset_pins', {})
        if not isinstance(pins, dict):
            raise SnapshotError('backup_state_unwritable')
        previous, _ = _latest(output, identity)
        known = {'last_snapshot_id': previous['snapshot_id'], 'last_snapshot_at': previous['created_at_utc']} if previous else {}
        if temporary is None:
            temporary = Path(tempfile.mkdtemp(prefix='.candidate-', dir=root))
        elif temporary.parent != root or temporary.is_symlink() or not temporary.is_dir():
            raise SnapshotError('backup_identity_unknown')
        try:
            target = temporary / 'snapshot.db'
            copy_sqlite(source, target)
            target.chmod(0o600)
            fingerprint = inspect_database(target)
            generation = _generation(fingerprint)
            if previous and previous['source_generation'] == generation:
                status = _status('ready', previous=known)
            else:
                snapshot_id = uuid.uuid4().hex
                created = datetime.now(timezone.utc).isoformat()
                manifest = {'version': 1, 'snapshot_id': snapshot_id,
                            'source_namespace': identity, 'source_generation': generation,
                            'created_at_utc': created, 'size': target.stat().st_size,
                            'sha256': _hash(target), 'fingerprint': fingerprint,
                            'integrity_check': 'ok'}
                with target.open('rb') as file:
                    os.fsync(file.fileno())
                _write_json(temporary / 'manifest.json', manifest)
                _fsync_directory(temporary)
                _publish(temporary, output / snapshot_id)
                status = _status('ready', previous={'last_snapshot_id': snapshot_id, 'last_snapshot_at': created})
            try:
                _write_json(state_path, {**status, 'reset_pins': pins}, replace=True)
            except (OSError, ValueError, SnapshotError):
                return _status('degraded', 'backup_state_unwritable', status)
            return status
        except (SnapshotInspectionError, OSError) as exc:
            reason = 'backup_integrity_failed' if isinstance(exc, SnapshotInspectionError) else 'backup_io_error'
            status = _status('degraded', reason, known)
            try:
                _write_json(state_path, {**status, 'reset_pins': pins}, replace=True)
            except (OSError, ValueError, SnapshotError):
                pass  # Current response remains degraded even if status cannot persist.
            return status
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)  # Only this call's freshly created candidate.


def _record_timeout(root: Path, namespace_id: str) -> dict:
    status = _status('degraded', 'backup_timeout')
    directory = root / namespace_id
    try:
        if not directory.is_dir() or directory.is_symlink():
            return status
        with namespace_lock(directory, deadline=time.monotonic() + .05):
            expected = {'version': 1, 'source_namespace': namespace_id}
            if _read_json(directory / 'namespace.json') != expected:
                return status
            path = directory / 'status.json'
            old = _read_json(path) if path.exists() else {}
            pins = old.get('reset_pins', {})
            if not isinstance(pins, dict):
                return status
            status = _status('degraded', 'backup_timeout', old)
            _write_json(path, {**status, 'reset_pins': pins}, replace=True)
    except (OSError, ValueError, SnapshotError):
        pass  # The caller still receives degraded if persistence is unavailable.
    return status


def check_snapshot(database_path: str | Path, backup_root: str | Path, reason: str) -> dict:
    """One explicitly requested attempt; the worker bounds even SQLite C calls.

    A separate process is needed to stop integrity checks/Python sorting within
    the accepted deadline. No jobs are queued and no user runtime hook exists.
    """
    temporary = None
    identity = None
    try:
        source, root, namespace_id = _paths(database_path, backup_root)
        _prepare_root(root)
        temporary = Path(tempfile.mkdtemp(prefix='.attempt-', dir=root))
        info = temporary.lstat()
        identity = (info.st_dev, info.st_ino)
        payload = {'source': str(source), 'root': str(root), 'temporary': str(temporary),
                   'deadline': time.monotonic() + max(.01, DEADLINE_SECONDS - .1)}
        with subprocess.Popen([sys.executable, '-m', __name__, '--worker'],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, text=True) as process:
            try:
                output, _ = process.communicate(json.dumps(payload), timeout=DEADLINE_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                return _record_timeout(root, namespace_id)
            if process.returncode:
                return _status('degraded', 'backup_io_error')
            return json.loads(output)
    except SnapshotError as exc:
        return _status('degraded', str(exc))
    except (OSError, ValueError):
        return _status('degraded', 'backup_io_error')
    finally:
        if temporary is not None:
            try:
                info = temporary.lstat()
            except FileNotFoundError:
                pass  # The candidate was atomically published.
            except OSError:
                return _status('degraded', 'backup_identity_unknown')
            else:
                if not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != identity:
                    return _status('degraded', 'backup_identity_unknown')
                try:
                    shutil.rmtree(temporary)
                except OSError:
                    return _status('degraded', 'backup_io_error')


def _main() -> None:
    if sys.argv[1:] != ['--worker']:
        raise SystemExit(2)
    try:
        request = json.load(sys.stdin)
        status = _run(request['source'], request['root'], Path(request['temporary']), deadline=request['deadline'])
    except SnapshotError as exc:
        status = _status('degraded', str(exc))
    except SnapshotInspectionError:
        status = _status('degraded', 'backup_integrity_failed')
    except (OSError, ValueError, KeyError):
        status = _status('degraded', 'backup_io_error')
    print(json.dumps(status))


if __name__ == '__main__':
    _main()
