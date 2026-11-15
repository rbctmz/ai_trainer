"""#756: a disappeared SQLite sidecar permits one complete ownership recheck."""
import os
from pathlib import Path

import pytest

from config.database_paths import ScratchPathError
from scripts.scratch_runtime import ScratchScope


class UnlinkedStat:
    """Inject the race when link count is inspected, not during resolve()."""
    def __init__(self, info, unlink):
        self.info, self.unlink = info, unlink

    def __getattr__(self, name):
        return getattr(self.info, name)

    @property
    def st_nlink(self):
        self.unlink()
        return 0


@pytest.mark.parametrize('suffix', ['-wal', '-shm', '-journal'])
def test_unlinked_optional_sidecar_rechecks_the_complete_scope(tmp_path, monkeypatch, suffix):
    scope = ScratchScope.create(parent=tmp_path)
    target = scope.root / 'case.db'
    target.write_bytes(b'synthetic database sentinel')
    sidecar = Path(str(target) + suffix)
    sidecar.write_bytes(b'synthetic sidecar')
    native = Path.stat
    checks = []
    check = scope._check_identity
    def check_root(**kwargs):
        checks.append(True)
        return check(**kwargs)
    def disappearing(path, *args, **kwargs):
        info = native(path, *args, **kwargs)
        if path == sidecar:
            return UnlinkedStat(info, path.unlink)
        return info
    with monkeypatch.context() as patch:
        patch.setattr(scope, '_check_identity', check_root)
        patch.setattr(Path, 'stat', disappearing)
        assert scope.validate_target(target, purpose='sqlite') == target
    assert len(checks) == 2
    assert target.read_bytes() == b'synthetic database sentinel'
    scope.cleanup()


@pytest.mark.parametrize('replacement', ['hardlink', 'external_symlink', 'fifo',
    'main_hardlink', 'root', 'still_unlinked', 'inspection_error'])
def test_revalidation_never_adopts_unsafe_or_unstable_replacements(tmp_path, monkeypatch, replacement):
    if replacement == 'fifo' and not hasattr(os, 'mkfifo'):
        pytest.skip('POSIX FIFO characterization')
    scope = ScratchScope.create(parent=tmp_path)
    target = scope.root / 'case.db'
    target.write_bytes(b'synthetic database sentinel')
    sidecar = Path(str(target) + '-wal')
    sidecar.write_bytes(b'synthetic sidecar')
    foreign = tmp_path / 'foreign-sentinel'
    foreign.write_bytes(b'keep')
    old_root = scope.root.with_name(scope.root.name + '-original')
    native = Path.stat
    calls = []
    def changed(path, *args, **kwargs):
        if path == sidecar:
            if calls and replacement == 'inspection_error':
                raise PermissionError('synthetic lookup denial')
            info = native(path, *args, **kwargs)
            def replace():
                calls.append(True)
                path.unlink()
                if replacement == 'hardlink':
                    os.link(foreign, path)
                elif replacement == 'external_symlink':
                    path.symlink_to(foreign)
                elif replacement == 'fifo':
                    os.mkfifo(path)
                elif replacement == 'main_hardlink':
                    target.unlink()
                    os.link(foreign, target)
                elif replacement == 'root':
                    scope.root.rename(old_root)
                    scope.root.mkdir(mode=0o700)
                else:
                    path.write_bytes(b'new synthetic sidecar')
            if not calls or replacement == 'still_unlinked':
                return UnlinkedStat(info, replace)
            return info
        return native(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'stat', changed)
        with pytest.raises(ScratchPathError):
            scope.validate_target(target, purpose='sqlite')
    assert len(calls) <= 2
    assert foreign.read_bytes() == b'keep'
    if replacement == 'root':
        assert old_root.exists() and scope.root.exists()
        scope.root.rmdir()
        old_root.rename(scope.root)
    scope.cleanup()


def test_unlinked_main_is_refused_without_retry(tmp_path, monkeypatch):
    scope = ScratchScope.create(parent=tmp_path)
    target = scope.root / 'case.db'
    target.write_bytes(b'synthetic database sentinel')
    native = Path.stat
    calls = []
    def missing_main(path, *args, **kwargs):
        info = native(path, *args, **kwargs)
        if path == target:
            return UnlinkedStat(info, lambda: calls.append(True))
        return info
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'stat', missing_main)
        with pytest.raises(ScratchPathError):
            scope.validate_target(target, purpose='sqlite')
    assert len(calls) == 1
    assert target.read_bytes() == b'synthetic database sentinel'
    scope.cleanup()
