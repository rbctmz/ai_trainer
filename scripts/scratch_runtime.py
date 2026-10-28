"""Owned temporary SQLite scopes for runners; no Settings or product DB hook."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import tempfile
from typing import Any

from config.database_paths import ScratchPathError, database_family, database_namespace_key, sqlite_target_path

_SCOPE_ENV = "AI_TRAINER_SCRATCH_SCOPE"
_MARKER = ".scratch-owner.json"


class ScratchScope:
    """One fresh private directory, identified by inode and a live owner receipt."""

    def __init__(self, root: Path, identity: tuple[int, int], token: str, owner: int) -> None:
        self.root = root
        self.identity = identity
        self.token = token
        self.owner = owner
        self._closed = False
        self._families: dict[str, str] = {}
        for name in ("runtime.db", "demo.db"):
            base = database_namespace_key(root / name)
            self._families.update({database_namespace_key(item): base for item in database_family(root / name)})

    @classmethod
    def create(cls, *, parent: Path | None = None) -> ScratchScope:
        try:
            root = Path(tempfile.mkdtemp(prefix="ai-trainer-scratch-", dir=parent)).resolve()
            os.chmod(root, 0o700)
            info = root.stat()
            scope = cls(root, (info.st_dev, info.st_ino), secrets.token_hex(24), os.getpid())
            with (root / _MARKER).open("x", encoding="utf-8") as marker:
                json.dump(scope.descriptor(), marker)
            os.chmod(root / _MARKER, 0o600)
            return scope
        except (OSError, RuntimeError):
            raise ScratchPathError("scratch_identity_unknown", purpose="bootstrap") from None

    def descriptor(self) -> dict[str, Any]:
        return {"root": str(self.root), "identity": list(self.identity), "token": self.token, "owner": self.owner}

    @classmethod
    def inherit(cls, descriptor: str) -> ScratchScope:
        """A path/env flag alone cannot adopt an existing directory."""
        try:
            data = json.loads(descriptor)
            scope = cls(Path(data["root"]), tuple(data["identity"]), data["token"], data["owner"])
            scope._check_identity()
            if os.name == "nt":
                # kill(pid, 0) is not a harmless liveness query on Windows.
                # Conservative direct-parent handoff until native coverage.
                if scope.owner not in {os.getpid(), os.getppid()}:
                    raise ValueError
            else:
                os.kill(scope.owner, 0)  # Stopped owners cannot be adopted.
            return scope
        except (KeyError, TypeError, ValueError, OSError, RuntimeError):
            raise ScratchPathError("scratch_identity_unknown", purpose="bootstrap") from None

    def _check_identity(self, *, cleanup: bool = False) -> None:
        reason = "scratch_cleanup_unowned" if cleanup else "scratch_identity_unknown"
        try:
            info = self.root.lstat()
            if not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != self.identity:
                raise ValueError
            if os.name == "posix" and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077):
                raise ValueError
            if self.root.resolve() != self.root:
                raise ValueError
            marker = self.root / _MARKER
            receipt = marker.lstat()
            if not stat.S_ISREG(receipt.st_mode) or receipt.st_nlink != 1:
                raise ValueError
            if os.name == "posix" and (receipt.st_uid != os.getuid() or stat.S_IMODE(receipt.st_mode) & 0o077):
                raise ValueError
            if json.loads(marker.read_text(encoding="utf-8")) != self.descriptor():
                raise ValueError
        except (OSError, ValueError, RuntimeError):
            raise ScratchPathError(reason, purpose="cleanup" if cleanup else "scratch") from None

    def validate_directory(self, target: Path, *, cleanup: bool = False) -> Path:
        self._check_identity(cleanup=cleanup)
        try:
            path = target.resolve()
            if not path.is_relative_to(self.root) or path == self.root:
                raise ValueError
            return path
        except (OSError, RuntimeError, ValueError):
            raise ScratchPathError("scratch_cleanup_unowned" if cleanup else "scratch_target_unowned") from None

    def validate_target(self, target: str | os.PathLike[str], *, purpose: str = "scratch") -> Path | None:
        self._check_identity()
        path = sqlite_target_path(target)
        if path is None:
            return None
        try:
            # A filename alias outside the owned root is not owned even if it
            # resolves to an owned inode. Resolve parent and main separately.
            if not path.parent.resolve().is_relative_to(self.root):
                raise ScratchPathError("scratch_target_unowned", purpose=purpose)
            resolved = path.resolve()
            for suffix in ("-wal", "-shm", "-journal"):
                if path.name.endswith(suffix) and Path(str(path)[:-len(suffix)]).exists():
                    raise ScratchPathError("scratch_protected_family", purpose=purpose)
            if not resolved.is_relative_to(self.root) or resolved == self.root:
                raise ScratchPathError("scratch_target_unowned", purpose=purpose)
            for artifact in database_family(path):
                if artifact.is_symlink() and not artifact.exists():
                    raise ScratchPathError("scratch_identity_unknown", purpose=purpose)
                if not artifact.resolve().is_relative_to(self.root):
                    raise ScratchPathError("scratch_target_unowned", purpose=purpose)
                try:
                    info = artifact.stat()
                except FileNotFoundError:
                    continue
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ScratchPathError("scratch_identity_unknown", purpose=purpose)
            base = database_namespace_key(resolved)
            keys = [database_namespace_key(item) for item in database_family(path)]
            if any(key in self._families and self._families[key] != base for key in keys):
                raise ScratchPathError("scratch_protected_family", purpose=purpose)
            self._families.update(dict.fromkeys(keys, base))
            return resolved
        except ScratchPathError:
            raise
        except (OSError, RuntimeError, ValueError):
            raise ScratchPathError("scratch_identity_unknown", purpose=purpose) from None

    def cleanup(self) -> None:
        if self._closed:
            return
        self._check_identity(cleanup=True)
        if self.owner != os.getpid():
            raise ScratchPathError("scratch_cleanup_unowned", purpose="cleanup")
        # rmtree unlinks nested symlinks rather than following them. Never
        # recover a replaced root by resolving it to a different directory.
        try:
            shutil.rmtree(self.root)
        except OSError:
            raise ScratchPathError("scratch_cleanup_unowned", purpose="cleanup") from None
        self._closed = True


def scope_from_environment() -> ScratchScope | None:
    descriptor = os.environ.get(_SCOPE_ENV)
    return ScratchScope.inherit(descriptor) if descriptor else None
