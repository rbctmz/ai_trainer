"""Database selection only; no SQLite opens, imports of Settings or migration."""
from __future__ import annotations

from dataclasses import dataclass
import ntpath
import os
from pathlib import Path
import posixpath
import stat
from typing import Mapping

CHECKOUT_ROOT = Path(__file__).resolve().parents[1]
SIDECAR_SUFFIXES = ("", "-wal", "-shm", "-journal")


class DatabasePathError(RuntimeError):
    """Named, operator-facing configuration/preflight refusal."""


@dataclass(frozen=True)
class DatabasePaths:
    real: str
    demo: str
    origin: str
    launch_cwd: str


def resolve_database_paths(
    env: Mapping[str, str], *, platform: str, home: str | None, cwd: str,
) -> DatabasePaths:
    """Resolve paths without touching the filesystem; inputs are explicit."""
    path = ntpath if platform == "win32" else posixpath

    def absolute(value: str) -> bool:
        return path.isabs(value) and (platform != "win32" or bool(path.splitdrive(value)[0]))

    def normalize(value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise DatabasePathError("database_path_invalid: empty or invalid path")
        if value == "~" or value.startswith(("~/", "~\\")):
            if not home or not absolute(home):
                raise DatabasePathError("database_home_unavailable")
            value = path.join(home, value[2:]) if value != "~" else home
        if not absolute(value):
            if not absolute(cwd) or value.startswith("~"):
                raise DatabasePathError("database_path_invalid: absolute home/cwd required")
            # A rooted Windows path without a drive uses the launch drive.
            value = path.join(cwd, value)
        if not absolute(value):
            raise DatabasePathError("database_path_invalid: cannot resolve path")
        # Freezing cwd is pure; collapsing "link/.." here would change the
        # file selected after following a symlink. Preserve SQLite path semantics.
        return value

    if "DATABASE_PATH" in env:
        real = normalize(env["DATABASE_PATH"])
        origin = "environment"
    else:
        if platform not in {"linux", "darwin", "win32"}:
            raise DatabasePathError("database_platform_unsupported")
        if not home or not absolute(home):
            raise DatabasePathError("database_home_unavailable")
        if platform == "darwin":
            directory = path.join(home, "Library", "Application Support")
        elif platform == "win32":
            candidate = env.get("LOCALAPPDATA", "")
            directory = candidate if absolute(candidate) else path.join(home, "AppData", "Local")
        else:
            candidate = env.get("XDG_DATA_HOME", "")
            directory = candidate if absolute(candidate) else path.join(home, ".local", "share")
        real = normalize(path.join(directory, "ai_trainer", "ai_trainer.db"))
        origin = "platform"
    base, extension = path.splitext(real)
    demo = normalize(env.get("DEMO_DATABASE_PATH", f"{base}_demo{extension or '.db'}"))
    return DatabasePaths(real=real, demo=demo, origin=origin, launch_cwd=normalize(cwd))


def _present(path: Path) -> bool:
    """lstat also sees dangling symlinks; inspection errors are not absence."""
    try:
        path.lstat()
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise DatabasePathError(f"database_path_inspection_failed: {path}") from exc


def _canonical(path: Path) -> str:
    try:
        return os.path.normcase(str(path.resolve()))
    except (OSError, RuntimeError) as exc:
        raise DatabasePathError(f"database_path_inspection_failed: {path}") from exc


def _samefile(first: Path, second: Path) -> bool:
    if not _present(first) or not _present(second):
        return False
    try:
        return first.samefile(second)
    except OSError as exc:
        raise DatabasePathError("database_path_inspection_failed: alias identity unknown") from exc


def _legacy_roots(checkout: Path, cwd: Path) -> list[Path]:
    roots = [cwd, checkout]
    metadata = checkout / ".git"
    if not _present(metadata):
        return roots  # Installed archives/Docker have no Git metadata.
    try:
        if metadata.is_dir():
            return roots
        value = metadata.read_text().strip()
        if not value.startswith("gitdir: ") or "\n" in value:
            raise ValueError("invalid gitfile")
        gitdir = (checkout / value[8:]).resolve(strict=True)
        common_value = (gitdir / "commondir").read_text().strip()
        common = (gitdir / common_value).resolve(strict=True)
        if not common_value or common.name != ".git" or not common.is_dir():
            raise ValueError("ambiguous primary checkout")
        roots.append(common.parent)
    except (OSError, ValueError, RuntimeError) as exc:
        raise DatabasePathError("database_git_metadata_invalid: cannot identify primary checkout") from exc
    return roots


def runtime_database_path(selection: DatabasePaths, *, checkout: Path | None = None) -> str:
    """Refuse a separate legacy family before an implicit default can open."""
    if selection.origin != "platform":
        return selection.real
    target = Path(selection.real)
    # Resolve parents, not the main filename: a main-only alias does not
    # establish ownership of differently named WAL/SHM/journal files.
    def family_name(path: Path) -> str:
        return os.path.normcase(str(Path(_canonical(path.parent)) / path.name))

    selected_name = family_name(target)
    roots = _legacy_roots(checkout or CHECKOUT_ROOT, Path(selection.launch_cwd))
    for repository in roots[1:]:
        if Path(_canonical(target)).is_relative_to(Path(_canonical(repository))):
            raise DatabasePathError("database_default_inside_checkout: choose an external DATABASE_PATH")
    for root in roots:
        legacy = root / "ai_trainer.db"
        same_parent = (
            os.path.normcase(legacy.name) == os.path.normcase(target.name)
            and _samefile(legacy.parent, target.parent)
        )
        if family_name(legacy) == selected_name or same_parent:
            continue  # The selected store and all of its own sidecars.
        if _samefile(legacy, target):
            raise DatabasePathError("database_path_alias_ambiguous: distinct SQLite base names")
        for suffix in SIDECAR_SUFFIXES:
            artifact = Path(str(legacy) + suffix)
            if _present(artifact):
                raise DatabasePathError(
                    f"database_migration_required: legacy={legacy}; selected={target}; "
                    "choose DATABASE_PATH explicitly; no database was moved or created"
                )
    return selection.real


def validate_demo_path(real: str, demo: str) -> None:
    """Refuse real/demo aliases before destructive demo seeding or clearing."""
    first, second = Path(real), Path(demo)
    if _canonical(first) == _canonical(second) or _samefile(first, second):
        raise DatabasePathError("database_demo_alias: real and demo must be different files")


def prepare_private_database_path(path: str) -> None:
    """Create only the selected fresh app store, never clobber an existing DB."""
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as exc:
        raise DatabasePathError(f"database_path_unwritable: {target.parent}") from exc
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        # Existing stores retain contents/permissions; do not touch their mtime.
        if not stat.S_ISREG(target.lstat().st_mode):
            raise DatabasePathError("database_path_invalid: selected store is not a regular file")
    except OSError as exc:
        raise DatabasePathError(f"database_path_unwritable: {target}") from exc
    else:
        os.close(descriptor)


class ScratchPathError(DatabasePathError):
    """Safe refusal: a reason and caller purpose, never a user filesystem path."""

    def __init__(self, reason: str, *, purpose: str = "scratch") -> None:
        self.reason = reason
        # Purposes are labels, not arbitrary values from an exception or argv.
        safe_purpose = purpose if purpose in {"scratch", "sqlite", "pytest", "cleanup", "test", "bootstrap"} else "scratch"
        super().__init__(f"{reason}: {safe_purpose}")


def sqlite_target_path(value: str | os.PathLike[str]) -> Path | None:
    """Parse SQLite filenames/URIs before containment checks; None is memory."""
    from urllib.parse import parse_qsl, unquote, urlsplit

    try:
        raw = os.fspath(value)
        if not isinstance(raw, str) or not raw or "\x00" in raw:
            raise ValueError
        if raw == ":memory:":
            return None
        if raw.startswith("file:"):
            # urlsplit silently strips TAB/CR/LF, while SQLite receives the
            # original URI. Never classify a normalized URI as a memory DB.
            if any(ord(char) < 32 or ord(char) == 127 for char in raw):
                raise ValueError
            uri = urlsplit(raw)
            query = parse_qsl(uri.query, keep_blank_values=True, strict_parsing=True)
            options = dict(query)
            allowed = {"mode": {"ro", "rw", "rwc", "memory"}, "cache": {"private", "shared"}, "immutable": {"0", "1"}}
            if (uri.netloc not in {"", "localhost"} or uri.fragment
                    or len(query) != len(options)
                    or any(key not in allowed or val not in allowed[key] for key, val in query)):
                raise ValueError
            if unquote(uri.path) == ":memory:" or options.get("mode") == "memory":
                return None
            raw = unquote(uri.path)
            if os.name == "nt" and len(raw) > 3 and raw[0] == "/" and raw[2] == ":":
                raw = raw[1:]
        elif ":" in raw and not (os.name == "nt" and ntpath.splitdrive(raw)[0]):
            raise ValueError
        if not raw or "\x00" in raw:
            raise ValueError
        return Path(raw).absolute()  # SQLite treats ~ literally; Settings expands it earlier.
    except (TypeError, ValueError, OSError, RuntimeError):
        raise ScratchPathError("scratch_identity_unknown") from None


def database_family(path: str | os.PathLike[str]) -> tuple[Path, ...]:
    """SQLite's main and all three sidecar names, including absent files."""
    target = Path(path)
    return tuple(Path(str(target) + suffix) for suffix in SIDECAR_SUFFIXES)


def database_namespace_key(path: Path) -> str:
    """Conservative future-name ambiguity key, never a file-selection rule."""
    import unicodedata
    return unicodedata.normalize("NFD", _canonical(path)).casefold()


def assert_disjoint_database_families(
    target: str | os.PathLike[str], protected: list[Path] | tuple[Path, ...],
) -> None:
    """Reject lexical/native aliases and future namespace collisions, no opens."""
    try:
        for first in database_family(target):
            for store in protected:
                for second in database_family(store):
                    if database_namespace_key(first) == database_namespace_key(second) or _samefile(first, second):
                        raise ScratchPathError("scratch_protected_family")
    except ScratchPathError:
        raise
    except (OSError, RuntimeError):
        raise ScratchPathError("scratch_identity_unknown") from None


def database_path_candidates(
    env: Mapping[str, str], *, platform: str, home: str | None, cwd: str,
    checkout: Path = CHECKOUT_ROOT,
) -> tuple[Path, ...]:
    """Capture selection/default/legacy names before a runner rebinds env."""
    try:
        selected = resolve_database_paths(env, platform=platform, home=home, cwd=cwd)
        defaults = resolve_database_paths(
            {key: value for key, value in env.items() if key not in {"DATABASE_PATH", "DEMO_DATABASE_PATH"}},
            platform=platform, home=home, cwd=cwd,
        )
        legacy = [root / "ai_trainer.db" for root in _legacy_roots(checkout, Path(cwd))]
        return tuple(dict.fromkeys(map(Path, [selected.real, selected.demo, defaults.real, defaults.demo, *legacy])))
    except (OSError, RuntimeError, ValueError):
        raise ScratchPathError("scratch_identity_unknown", purpose="bootstrap") from None
