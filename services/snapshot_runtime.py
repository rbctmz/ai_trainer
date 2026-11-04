"""Shared opt-in post-commit boundaries and bounded backup lifecycle (#623 M3)."""
from __future__ import annotations

from contextlib import closing, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
import inspect
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any, Callable, Iterator

from config.settings import Settings
from services.automatic_snapshots import check_snapshot, read_snapshot_status
from services.sqlite_snapshot_core import readonly_connection

INTERVAL_SECONDS = 60
WARNING = 'Данные сохранены, резервная копия не обновлена.'


def empty_status(state: str = 'unknown', reason: str | None = None) -> dict[str, Any]:
    return {'state': state, 'last_checked_at': None, 'last_snapshot_at': None,
            'last_snapshot_id': None, 'reason_code': reason}


def _instant(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (ValueError, TypeError):
        return None


def _dataset_origin(path: str | Path) -> Any:
    # A provenance read must not run Database._connect's writer PRAGMAs or
    # inherit its 30s busy wait before the bounded snapshot worker starts.
    with closing(readonly_connection(Path(path).absolute())) as connection:
        connection.execute('PRAGMA busy_timeout=0')
        row = connection.execute("SELECT value FROM user_settings WHERE key='dataset_origin'").fetchone()
    return row[0] if row else None


def _eligible(db: Any, demo: bool = False) -> bool | None:
    if demo or not Settings.AUTO_BACKUP_ENABLED or Settings.ACCEPTANCE_MODE:
        return False
    path = getattr(db, 'db_path', None)
    if not isinstance(path, (str, Path)):
        return False
    # Selection is server-owned; arbitrary test/admin databases cannot silently
    # opt into the personal store's backup namespace. Core validates identity.
    if Path(path).absolute() != Path(Settings.DATABASE_PATH).absolute():
        return False
    if Path(path).absolute() == Path(Settings.DEMO_DATABASE_PATH).absolute():
        return False
    try:
        return _dataset_origin(path) != 'demo'
    except Exception:
        return None  # Do not back up unknown demo provenance or claim disabled.


class BackupRuntime:
    """One selected store/root; no queue, business replay or source state table."""

    def __init__(self, db: Any, *, now: Callable[[], datetime] | None = None) -> None:
        self.db = db
        self.root = Settings.BACKUP_DIR
        self.now = now or (lambda: datetime.now(timezone.utc))
        self._current: dict[str, Any] | None = None
        self._day = None
        self._stop = Event()
        self._thread: Thread | None = None
        self._lifecycle = Lock()
        self._receipt_lock = Lock()

    def _preflight_failure(self) -> dict[str, Any]:
        if self._current is None or self._current['state'] != 'degraded':
            disk = read_snapshot_status(self.db.db_path, self.root)
            known = max((disk, self._current or {}), key=lambda item:
                        _instant(item.get('last_snapshot_at')) or datetime.min.replace(tzinfo=timezone.utc))
            self._current = {**empty_status('degraded', 'backup_io_error'),
                             'last_checked_at': self.now().isoformat(),
                             'last_snapshot_id': known.get('last_snapshot_id'),
                             'last_snapshot_at': known.get('last_snapshot_at')}
        return dict(self._current)

    def status(self) -> dict[str, Any]:
        eligibility = _eligible(self.db)
        if eligibility is not True:
            return empty_status('disabled') if eligibility is False else self._preflight_failure()
        disk = read_snapshot_status(self.db.db_path, self.root)
        local = self._current
        if disk['state'] in {'unknown', 'degraded'} and disk['last_checked_at'] is None:
            return dict(local) if local is not None and local['state'] == 'degraded' else disk
        if local is not None:
            local_at = _instant(local['last_checked_at'])
            disk_at = _instant(disk['last_checked_at'])
            if local_at is not None and (disk_at is None or local_at >= disk_at):
                return dict(local)
        return disk

    def check(self, reason: str) -> dict[str, Any]:
        eligibility = _eligible(self.db)
        if eligibility is not True:
            return empty_status('disabled') if eligibility is False else self._preflight_failure()
        previous = self.status()
        now = self.now()
        last = _instant(previous['last_checked_at'])
        if previous['state'] == 'degraded' and last is not None and (now - last).total_seconds() < INTERVAL_SECONDS:
            return previous
        try:
            # M2's OS lock already serializes callers within the same deadline.
            # A second runtime lock would skip a committed concurrent operation.
            status = check_snapshot(self.db.db_path, self.root, reason)
        except Exception:
            status = {**previous, 'state': 'degraded', 'reason_code': 'backup_io_error'}
        if status['state'] == 'degraded' and not status.get('last_snapshot_id'):
            status = {**status, 'last_snapshot_id': previous.get('last_snapshot_id'),
                      'last_snapshot_at': previous.get('last_snapshot_at')}
        completed = self.now()
        receipt = {**status, 'last_checked_at': status.get('last_checked_at') or completed.isoformat()}
        # This short assignment lock never encloses the backup. A delayed old
        # success cannot erase a newer failure that could not reach status.json.
        with self._receipt_lock:
            current_at = _instant((self._current or {}).get('last_checked_at'))
            incoming_at = _instant(receipt['last_checked_at'])
            if current_at is None or (incoming_at is not None and incoming_at >= current_at):
                self._current = receipt
        self._day = completed.date()
        return receipt

    def check_due(self, *, startup: bool = False) -> dict[str, Any]:
        status = self.status()
        if status['state'] == 'disabled':
            return status
        if startup or self._day != self.now().date() or status['state'] != 'ready':
            return self.check('startup' if startup else 'daily_or_retry')
        return status

    def start(self) -> None:
        if _eligible(self.db) is False:
            return
        with self._lifecycle:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self.check_due(startup=True)
            self._thread = Thread(target=self._loop, name='backup-lifecycle', daemon=True)
            self._thread.start()

    def _loop(self) -> None:
        while not self._stop.wait(INTERVAL_SECONDS):
            self.check_due()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=11)


_runtimes: dict[tuple[str, str], BackupRuntime] = {}
_runtime_lock = Lock()


def get_runtime(db: Any) -> BackupRuntime:
    key = (str(getattr(db, 'db_path', '')), str(Settings.BACKUP_DIR))
    with _runtime_lock:
        if key not in _runtimes:
            _runtimes[key] = BackupRuntime(db)
        return _runtimes[key]


def backup_status(db: Any, *, demo: bool = False) -> dict[str, Any]:
    eligibility = _eligible(db, demo)
    if eligibility is False:
        return empty_status('disabled')
    return get_runtime(db).status()


@dataclass
class _Operation:
    db: Any
    reason: str
    dirty: bool = False
    status: dict[str, Any] | None = None


_operations: ContextVar[tuple[_Operation, ...]] = ContextVar('backup_operations', default=())
_deferred: ContextVar[bool] = ContextVar('backup_read_derivation', default=False)


def _same_store(left: Any, right: Any) -> bool:
    if left is right:
        return True
    a, b = getattr(left, 'db_path', None), getattr(right, 'db_path', None)
    return isinstance(a, (str, Path)) and isinstance(b, (str, Path)) and Path(a).absolute() == Path(b).absolute()


def mark_committed(db: Any) -> None:
    """Mark an actual store commit; its boundary flushes after connection close."""
    for scope in reversed(_operations.get()):
        if _same_store(scope.db, db):
            scope.dirty = True
            return



@contextmanager
def backup_operation(db: Any, reason: str, *, changed: bool = False) -> Iterator[_Operation]:
    """Coalesce nested writes for this handle; preserve partial commits on error."""
    existing = next((scope for scope in reversed(_operations.get()) if _same_store(scope.db, db)), None)
    if existing is not None:
        existing.dirty |= changed
        yield existing
        return
    scope = _Operation(db, reason, dirty=changed)
    token = _operations.set((*_operations.get(), scope))
    try:
        yield scope
    finally:
        _operations.reset(token)
        if scope.dirty and _eligible(db) is not False:
            scope.status = get_runtime(db).check(reason)
        else:
            scope.status = backup_status(db)


def backup_boundary(reason: str, *, database_arg: str = 'db', response: bool = False,
                    changed: bool = False) -> Callable:
    """Declare an outer operation; never alter stored domain return values."""
    def decorate(function):
        try:
            signature = inspect.signature(function, eval_str=True)
        except NameError:  # TYPE_CHECKING-only domain annotations, never routes.
            signature = inspect.signature(function)
        @wraps(function)
        def wrapped(*args, **kwargs):
            db = signature.bind(*args, **kwargs).arguments[database_arg]
            if database_arg == 'state':
                db = db.database
            with backup_operation(db, reason, changed=changed) as operation:
                result = function(*args, **kwargs)
            if response and isinstance(result, dict):
                result = {**result, 'backup': operation.status or backup_status(db)}
            elif response and hasattr(result, 'backup'):
                result.backup = operation.status
            return result
        wrapped.__signature__ = signature
        return wrapped
    return decorate


def backup_write(function: Callable) -> Callable:
    """Explicit committed Database writer, not a connection/SQL interception."""
    @wraps(function)
    def wrapped(self, *args, **kwargs):
        if _deferred.get():
            return function(self, *args, **kwargs)
        with backup_operation(self, function.__name__) as operation:
            result = function(self, *args, **kwargs)
            operation.dirty = True
        return result
    return wrapped


def reset_for_tests() -> None:
    with _runtime_lock:
        runners = list(_runtimes.values())
        _runtimes.clear()
    for runner in runners:
        runner.stop()


def attach_sync_backup(payload: dict[str, Any], status: dict[str, Any] | None) -> dict[str, Any]:
    if status is None:
        return payload  # Nested service; the outer sync boundary owns its result.
    payload = {**payload, 'backup': status}
    if status['state'] == 'degraded':
        codes = list(payload.get('warning_codes') or [])
        if 'backup_failed' not in codes:
            codes.append('backup_failed')
        payload['warning_codes'] = codes
        notices = list(payload.get('notices') or [])
        if WARNING not in notices:
            notices.append(WARNING)
        payload['notices'] = notices
        if payload.get('sync_state') == 'succeeded':
            payload['sync_state'] = 'partial'
        payload['severity'] = 'warning' if payload.get('severity') != 'error' else 'error'
    envelope = payload.get('operational_state')
    if isinstance(envelope, dict):
        payload['operational_state'] = {**envelope, 'backup': status, 'sync_state': payload.get('sync_state', envelope.get('sync_state'))}
    return payload


def defer_derived_backup(function: Callable) -> Callable:
    """Read-owned reproducible audit/cache writes use the daily safety check.

    This is explicit on the recovery projection, not a global HTTP/SQL rule.
    A coach command's later durable decision still performs its own snapshot.
    """
    @wraps(function)
    def wrapped(*args, **kwargs):
        token = _deferred.set(True)
        try:
            return function(*args, **kwargs)
        finally:
            _deferred.reset(token)
    return wrapped


def prepare_reset(db: Any) -> None:
    """Require a checked copy and durable 14-day pin before a real-store reset.

    The caller already holds BEGIN IMMEDIATE; release the source connection
    before post-reset backup. A failed precondition must precede every DELETE.
    """
    eligibility = _eligible(db)
    if eligibility is False:
        return
    status = get_runtime(db).check('pre_reset') if eligibility is True else get_runtime(db)._preflight_failure()
    if status['state'] != 'ready':
        raise RuntimeError('Очистка не выполнена: резервную копию перед очисткой не удалось защитить.')
