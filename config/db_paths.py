"""Canonical SQLite path safety for the dogfood (production) database (#622/#625).

Why this module exists
----------------------
The 2026-09-20 incident destroyed the working ``ai_trainer.db`` because
diagnostic commands and tests treated the production file — and its
``-wal``/``-shm`` sidecars — as disposable artifacts. Safety depended entirely
on caller discipline. This module makes that boundary explicit and executable:

* one canonical production identity (:func:`production_database_path` and its
  sidecars), classified independently of the caller's working directory;
* fail-closed classification of any candidate path (:func:`assert_safe`), which
  refuses the reproduction, its sidecar siblings, and every alias of either
  *before* the first SQLite write;
* per-run temporary database roots that can only clean up inside themselves
  (:class:`TemporaryDatabaseRoot`).

The canonical destructive boundary (mirrored once in ``AGENTS.md``): tests,
acceptance runs and agent diagnostics never read, create or delete the dogfood
database or its sidecars; temporary checks happen inside a per-run ``mkdtemp``
root; destructive maintenance accepts only a path proven to live in that root or
inside an explicit operator-owned application-data directory.

Deliberate non-goals (issue #625): this is not a defense against an operator
with full OS privileges, it does not replace automatic snapshots (#623) or the
off-device copy (#626), and it never forbids the application's own legitimate
writes to the configured production database.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import uuid
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from config.settings import Settings

__all__ = [
    "DatabasePathViolation",
    "DatabasePathKind",
    "ClassifiedDatabasePath",
    "SIDECAR_SUFFIXES",
    "TEMP_ROOT_PREFIX",
    "GUARD_MODE_ENV",
    "PROTECTED_PATHS_ENV",
    "PRODUCTION_DB_ENV",
    "normalize_path",
    "production_database_path",
    "production_database_directory",
    "production_sidecar_paths",
    "demo_database_path",
    "is_sidecar_path",
    "classify",
    "assert_safe",
    "is_protected_production_path",
    "assert_safe_acceptance_database",
    "acceptance_validation_error",
    "git_ignored_paths",
    "assert_operator_action_target",
    "guarded_protected_paths",
    "guard_active",
    "assert_not_protected",
    "guarded_connect",
    "guard_connect_path",
    "TemporaryDatabaseRoot",
]

#: SQLite sidecar suffixes whose loss corrupts committed production pages.
SIDECAR_SUFFIXES: tuple[str, ...] = ("-wal", "-shm", "-journal")

#: Prefix for per-run temporary database roots so they are recognisable and are
#: never mistaken for an application-data directory.
TEMP_ROOT_PREFIX = "ai-trainer-dbguard-"

#: Environment contract used by test entrypoints to arm the runtime guard:
#: ``AI_TRAINER_DB_GUARD=test`` plus ``AI_TRAINER_PROTECTED_DB`` (``os.pathsep``
#: separated absolute paths). Without them the guard is inert, so operator CLIs
#: that legitimately act on the production database keep working.
GUARD_MODE_ENV = "AI_TRAINER_DB_GUARD"
PROTECTED_PATHS_ENV = "AI_TRAINER_PROTECTED_DB"

#: Frozen production identity, set once by a test entrypoint. Tests routinely
#: rebind ``Settings.DATABASE_PATH`` to a temporary path for their own scenario
#: (cache-routing, demo separation); without freezing, that rebinding would make
#: the guard treat the scenario's temporary file as production and refuse it.
PRODUCTION_DB_ENV = "AI_TRAINER_PRODUCTION_DB"

_DEFAULT_DATABASE_NAME = "ai_trainer.db"
_DEMO_SUFFIX = "_demo"


class DatabasePathViolation(RuntimeError):
    """A path would touch the dogfood database or one of its sidecars.

    Messages name the violated invariant and the *classification* of the
    offending path, never the personal absolute path itself, so public CI logs
    stay free of local directory structure.

    Attributes:
        invariant: Stable machine-readable invariant name.
        kind: Classification of the offending path.
        suffix: Sidecar suffix when the violation is a sidecar sibling.
    """

    def __init__(
        self,
        invariant: str,
        *,
        kind: "DatabasePathKind",
        suffix: str | None = None,
        detail: str | None = None,
    ) -> None:
        self.invariant = invariant
        self.kind = kind
        self.suffix = suffix
        self.detail = detail
        message = f"{invariant}: refused {kind.token}"
        if suffix:
            message += f" sidecar {suffix!r}"
        if detail:
            message += f" ({detail})"
        super().__init__(message)


class DatabasePathKind(str, Enum):
    """What a candidate database path actually is."""

    REAL = "real"
    DEMO = "demo"
    ACCEPTANCE = "acceptance"
    TEST = "test"

    @property
    def token(self) -> str:
        """Opaque, non-personal label safe for logs and CI output."""
        return {
            DatabasePathKind.REAL: "the dogfood database",
            DatabasePathKind.DEMO: "a demo database",
            DatabasePathKind.ACCEPTANCE: "an acceptance database",
            DatabasePathKind.TEST: "a test/temporary database",
        }[self]


@dataclass(frozen=True)
class ClassifiedDatabasePath:
    """Result of classifying one candidate path."""

    path: Path
    kind: DatabasePathKind
    sidecar_suffix: str | None = None
    aliases_production: bool = False

    @property
    def touches_production(self) -> bool:
        """True when this path IS the dogfood DB, a sidecar, or an alias of either."""
        return self.kind is DatabasePathKind.REAL


def normalize_path(path: str | os.PathLike[str]) -> Path:
    """Return an absolute, symlink-resolved, lexically normalised path.

    Missing files are fine: resolution is non-strict, so a target that does not
    exist yet still normalises to the location a writer would create.
    """
    candidate = Path(os.fspath(path)).expanduser()
    try:
        return candidate.resolve(strict=False)
    except OSError:  # pragma: no cover - defensive (unreadable parents)
        return Path(os.path.abspath(candidate))


@lru_cache(maxsize=1)
def _filesystem_is_case_insensitive() -> bool:
    """Probe whether the temp filesystem folds case rather than guessing by OS.

    ``Path.resolve`` on macOS preserves the on-disk name, so a case-only alias
    of the production file can survive resolution. Probing the real filesystem
    is exact, and it also covers a case-insensitive volume mounted on Linux.
    """
    with tempfile.TemporaryDirectory(prefix="ai-trainer-case-probe-") as raw:
        probe = Path(raw) / "case-probe-AbC"
        try:
            probe.write_text("probe", encoding="utf-8")
        except OSError:  # pragma: no cover - unwritable temp dir
            return os.name in {"nt", "darwin"}
        try:
            return (Path(raw) / "case-probe-abc").exists()
        except OSError:  # pragma: no cover - defensive
            return os.name in {"nt", "darwin"}


def _fold_case(path: Path) -> str:
    text = str(path)
    return text.casefold() if _filesystem_is_case_insensitive() else text


def _same_location(first: Path, second: Path) -> bool:
    return _fold_case(first) == _fold_case(second)


def _configured_database() -> str:
    return (Settings.DATABASE_PATH or "").strip() or _DEFAULT_DATABASE_NAME


def production_database_path() -> Path:
    """Canonical absolute path of the dogfood database.

    Resolution follows today's runtime semantics (a relative ``DATABASE_PATH``
    resolves against the current working directory) so the guard protects the
    file the application actually opens. The #624 slice replaces the default
    with an application-data path; the guard keeps working unchanged because it
    always asks the settings object rather than hard-coding a location.

    When a test entrypoint froze the identity in ``AI_TRAINER_PRODUCTION_DB``,
    that value wins: the frozen path is what the session declared as dogfood, so
    a test that rebinds settings for its own scenario cannot move the boundary.
    """
    frozen = os.getenv(PRODUCTION_DB_ENV, "").strip()
    return normalize_path(frozen or _configured_database())


def production_database_directory() -> Path:
    """Directory holding the production database."""
    return production_database_path().parent


def production_sidecar_paths() -> tuple[Path, ...]:
    """Canonical ``-wal``/``-shm``/``-journal`` siblings of the dogfood database."""
    database = production_database_path()
    return tuple(Path(f"{database}{suffix}") for suffix in SIDECAR_SUFFIXES)


def demo_database_path() -> Path:
    """Demo database location, mirroring ``api.deps`` path semantics."""
    base, ext = os.path.splitext(_configured_database())
    return normalize_path(os.getenv("DEMO_DATABASE_PATH", f"{base}{_DEMO_SUFFIX}{ext or '.db'}"))

def is_sidecar_path(path: str | os.PathLike[str]) -> str | None:
    """Return the sidecar suffix this path carries, else ``None``."""
    name = Path(os.fspath(path)).name
    for suffix in SIDECAR_SUFFIXES:
        if name.endswith(suffix):
            return suffix
    return None


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _base_and_suffix(path: Path) -> tuple[Path, str | None]:
    suffix = is_sidecar_path(path)
    if suffix is None:
        return path, None
    return Path(str(path)[: -len(suffix)]), suffix


def _file_identity(path: Path) -> tuple[int, int] | None:
    try:
        info = path.stat()
    except OSError:
        return None
    return (info.st_dev, info.st_ino)


def _alias_of_any(path: Path, targets: tuple[Path, ...]) -> bool:
    """True when ``path`` is another name for one of the existing ``targets``.

    Covers symlinks (already flattened by :func:`normalize_path`), case-only
    spellings on a case-insensitive volume, and hardlinks — which leave no
    path-level trace and are only detectable by device/inode equality.
    """
    if any(_same_location(path, target) for target in targets):
        return True
    candidate_identity = _file_identity(path)
    if candidate_identity is None:
        return False
    return any(
        identity is not None and identity == candidate_identity
        for identity in (_file_identity(target) for target in targets)
    )


def classify(path: str | os.PathLike[str]) -> ClassifiedDatabasePath:
    """Classify a candidate path without touching it.

    Order matters: an alias of the production file is NEVER reported as
    test/demo/acceptance, even when the caller's spelling looks innocuous.
    """
    normalized = normalize_path(path)
    base, sidecar_suffix = _base_and_suffix(normalized)

    production = production_database_path()
    sidecars = production_sidecar_paths()

    aliases_production = _alias_of_any(base, (production,))
    if aliases_production:
        kind = DatabasePathKind.REAL
    elif sidecar_suffix is not None and _alias_of_any(normalized, sidecars):
        kind = DatabasePathKind.REAL
    elif _alias_of_any(base, (demo_database_path(),)):
        kind = DatabasePathKind.DEMO
    elif Settings.ACCEPTANCE_MODE:
        kind = DatabasePathKind.ACCEPTANCE
    else:
        kind = DatabasePathKind.TEST

    return ClassifiedDatabasePath(
        path=normalized,
        kind=kind,
        sidecar_suffix=sidecar_suffix,
        aliases_production=aliases_production or kind is DatabasePathKind.REAL,
    )


def is_protected_production_path(path: str | os.PathLike[str]) -> bool:
    """True when ``path`` is refused as dogfood data (never raises).

    The read-only predicate form of :func:`assert_safe`, for callers that need to
    branch (cleanup helpers, diagnostics) instead of failing.
    """
    try:
        result = classify(path)
    except (OSError, ValueError):  # pragma: no cover - defensive
        return True  # fail closed
    return result.touches_production


def assert_safe(
    path: str | os.PathLike[str],
    *,
    purpose: str,
    invariant: str = "database-path-safety",
) -> ClassifiedDatabasePath:
    """Fail closed when ``path`` could touch dogfood data. Returns the classification.

    Call this *before* the first SQLite write or destructive filesystem
    operation. Raises :class:`DatabasePathViolation` for the production
    database, its ``-wal``/``-shm``/``-journal`` siblings, and every alias of
    either (symlink, hardlink, case-only spelling).
    """
    result = classify(path)
    if result.kind is not DatabasePathKind.REAL:
        return result
    if result.sidecar_suffix is not None:
        raise DatabasePathViolation(
            invariant,
            kind=result.kind,
            suffix=result.sidecar_suffix,
            detail=f"{purpose} must not touch production sidecars",
        )
    raise DatabasePathViolation(
        invariant,
        kind=result.kind,
        detail=(
            f"{purpose} must use a per-run temporary database"
            if not result.aliases_production or result.path == production_database_path()
            else f"{purpose} resolved to an alias of the production file"
        ),
    )


# --------------------------------------------------------------------------- #
# Runtime guard for test entrypoints
# --------------------------------------------------------------------------- #


def guarded_protected_paths() -> tuple[Path, ...]:
    """Protected absolute paths declared by the active test entrypoint."""
    raw = os.getenv(PROTECTED_PATHS_ENV, "")
    declared = [item for item in raw.split(os.pathsep) if item.strip()]
    if declared:
        return tuple(normalize_path(item) for item in declared)
    if guard_active():
        # Armed without an explicit list: protect the configured production file.
        return (production_database_path(),)
    return ()


def guard_active() -> bool:
    """Whether a test entrypoint armed the runtime guard for this process."""
    if os.getenv(GUARD_MODE_ENV, "").strip().lower() in {"1", "true", "yes", "on", "test"}:
        return True
    return bool([item for item in os.getenv(PROTECTED_PATHS_ENV, "").split(os.pathsep) if item.strip()])


def _matches_declared(path: Path, declared: tuple[Path, ...]) -> bool:
    base, suffix = _base_and_suffix(path)
    identity = _file_identity(path)
    for protected in declared:
        if _same_location(path, protected) or _same_location(base, protected):
            return True
        if suffix is not None and _same_location(normalize_path(f"{base}{suffix}"), protected):
            return True
        protected_identity = _file_identity(protected)
        if identity is not None and protected_identity is not None and identity == protected_identity:
            return True
    return False


def assert_not_protected(
    path: str | os.PathLike[str],
    *,
    purpose: str,
    invariant: str = "test-must-not-touch-production-database",
) -> Path:
    """Refuse a path that the active test entrypoint declared as production.

    This is the runtime half of the guard: :func:`assert_safe` encodes static
    policy from settings, while this one catches a ``DATABASE_PATH`` the
    entrypoint resolved at runtime — including a relative spelling evaluated
    from another working directory. Inert when no entrypoint armed the guard.
    """
    normalized = normalize_path(path)
    declared = guarded_protected_paths()
    if not declared:
        return normalized
    if _matches_declared(normalized, declared):
        raise DatabasePathViolation(
            invariant,
            kind=DatabasePathKind.REAL,
            suffix=is_sidecar_path(normalized),
            detail=(
                f"{purpose} resolved to the running entrypoint's production database; "
                "point DATABASE_PATH at a per-run temporary directory"
            ),
        )
    return normalized


def assert_safe_acceptance_database(
    path: str | os.PathLike[str],
    *,
    acceptance_root: str | os.PathLike[str] | None = None,
) -> Path:
    """Refuse an acceptance runtime pointed at dogfood data (#625).

    Acceptance mode seeds or clears its dataset, and ``run_acceptance.sh`` exposes
    ``ACCEPTANCE_DB_PATH`` as an override. A typo there previously resolved the
    *production* file and would have wiped it, so the invariant is explicit: the
    acceptance database must resolve inside this run's acceptance root and must
    never be the production database or one of its sidecars.
    """
    resolved = assert_safe(
        path,
        purpose="an acceptance run",
        invariant="acceptance-database-must-not-be-production",
    ).path

    root = acceptance_root or os.getenv("ACCEPTANCE_ROOT", "").strip()
    if not root:
        return resolved

    resolved_root = normalize_path(root)
    if not _within(resolved, resolved_root):
        raise DatabasePathViolation(
            "acceptance-database-must-be-isolated",
            kind=DatabasePathKind.ACCEPTANCE,
            detail=(
                "the acceptance database must live inside this run's "
                "ACCEPTANCE_ROOT temporary directory"
            ),
        )
    return resolved


def guarded_connect(db_path: str | os.PathLike[str], **kwargs):
    """Open a SQLite connection, failing closed on any dogfood artifact.

    Enforces both guard layers: the static policy of :func:`assert_safe` (the
    configured production file, its sidecars and every alias of either) and the
    runtime declaration of :func:`assert_not_protected`. The sanctioned factory
    for test-scoped code; delegates to :func:`sqlite3.connect` unchanged for
    safe paths.
    """
    import sqlite3

    assert_safe(db_path, purpose="a test SQLite write")
    assert_not_protected(db_path, purpose="a SQLite write")
    return sqlite3.connect(os.fspath(db_path), **kwargs)


def guard_connect_path(
    db_path: str | os.PathLike[str],
    *,
    purpose: str = "opening a SQLite connection",
) -> None:
    """Fail closed when an armed test process targets dogfood data.

    The hook is shared by production and test code, so an ordinary application
    process must be allowed to open its configured production database. Test
    entrypoints arm the guard and freeze the production identity before module
    collection; only those processes apply the static classification here.
    """
    if guard_active():
        assert_safe(db_path, purpose=purpose, invariant="test-must-not-touch-production-database")
    assert_not_protected(db_path, purpose=purpose)


# --------------------------------------------------------------------------- #
# Per-run temporary roots
# --------------------------------------------------------------------------- #


class TemporaryDatabaseRoot:
    """A per-run temporary directory that may only clean up inside itself.

    :meth:`cleanup_candidate` refuses absolute paths outside the root, traversal
    escapes, and symlinks that resolve outside the root, so a cleanup helper can
    never be pointed at the dogfood database by a relative spelling or a planted
    link.
    """

    def __init__(self, *, label: str = "db") -> None:
        # Normalised at construction so containment checks compare like with
        # like: on macOS ``mkdtemp`` returns ``/var/...`` while resolution
        # yields ``/private/var/...`` and every child would look "outside".
        self.path = normalize_path(tempfile.mkdtemp(prefix=f"{TEMP_ROOT_PREFIX}{label}-"))

    def allocate(self, name: str) -> Path:
        """Return a database path inside this root, creating nothing yet."""
        if not name or os.path.basename(name) != name or name in {".", ".."}:
            raise ValueError(f"temporary database name must be a bare filename: {name!r}")
        target = normalize_path(self.path / name)
        self._require_within_root(target, purpose="allocate a temporary database")
        assert_safe(target, purpose="allocate a temporary database")
        return target

    def unique(self, stem: str = "scratch", *, suffix: str = ".db") -> Path:
        """Return a collision-free database path inside this root."""
        return self.allocate(f"{stem}-{uuid.uuid4().hex[:12]}{suffix}")

    def cleanup_candidate(self, path: str | os.PathLike[str]) -> Path:
        """Validate that ``path`` may be deleted, then return it.

        Raises :class:`DatabasePathViolation` when the candidate escapes the run
        root or aliases dogfood data.
        """
        raw = Path(os.fspath(path)).expanduser()
        candidate = raw if raw.is_absolute() else self.path / raw
        resolved = self._require_within_root(candidate, purpose="delete a temporary artifact")
        assert_safe(resolved, purpose="delete a temporary artifact")
        return resolved

    def cleanup(self) -> None:
        """Remove this run's root. Never follows a symlink out of the root.

        ``shutil.rmtree`` unlinks symlinked entries instead of recursing through
        them, so a link planted inside the root cannot redirect deletion to an
        external target.
        """
        if self.path.exists():
            shutil.rmtree(self.path, ignore_errors=False)

    def __enter__(self) -> "TemporaryDatabaseRoot":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.cleanup()

    def _require_within_root(self, candidate: Path, *, purpose: str) -> Path:
        root = normalize_path(self.path)
        if candidate.is_symlink():
            resolved = candidate.resolve(strict=False)
            if not _within(resolved, root):
                raise DatabasePathViolation(
                    "temporary-root-confinement",
                    kind=DatabasePathKind.TEST,
                    detail=f"{purpose} through a symlink leaving this run's temporary root",
                )
        resolved = normalize_path(candidate)
        if resolved == root:
            return root
        if not _within(resolved, root):
            raise DatabasePathViolation(
                "temporary-root-confinement",
                kind=DatabasePathKind.TEST,
                detail=f"{purpose} outside this run's temporary root",
            )
        return resolved



def acceptance_validation_error(
    path: str | os.PathLike[str],
    *,
    acceptance_root: str | os.PathLike[str] | None = None,
) -> str | None:
    """Return the refusal reason for an acceptance database, or ``None`` if safe.

    Shell entrypoints (``run_acceptance.sh``) cannot raise a Python exception, so
    this is the message-returning form of
    :func:`assert_safe_acceptance_database`: the launcher prints it and exits
    before starting any process that could write.
    """
    try:
        assert_safe_acceptance_database(path, acceptance_root=acceptance_root)
    except DatabasePathViolation as exc:
        return str(exc)
    return None


def _main(argv: list[str] | None = None) -> int:
    """Entrypoint used by shell launchers to validate a configured database path."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validate-acceptance-db",
        metavar="PATH",
        required=True,
        help="Fail (exit 2) when PATH would make an acceptance run touch dogfood data.",
    )
    parser.add_argument(
        "--acceptance-root",
        default=None,
        help="Root directory the acceptance database must stay inside.",
    )
    args = parser.parse_args(argv)

    error = acceptance_validation_error(args.validate_acceptance_db, acceptance_root=args.acceptance_root)
    if error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print("ok: acceptance database path is isolated from dogfood data")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


# --------------------------------------------------------------------------- #
# Path-pattern checks without filesystem materialization
# --------------------------------------------------------------------------- #


def git_ignored_paths(
    candidates: Iterable[str],
    *,
    repo_root: str | os.PathLike[str] | None = None,
    timeout: float = 10.0,
) -> set[str]:
    """Return which candidate paths Git would ignore — creating nothing on disk.

    The 2026-09-20 incident began with a diagnostic check of ignore rules that
    *created* the real database names and then removed them. Git can answer the
    same question from path patterns alone (``git check-ignore --stdin``, with
    ``--no-index`` so tracked paths are answered too), so no probe should ever
    materialize ``ai_trainer.db`` or its ``-wal``/``-shm`` siblings.

    Returns the subset of ``candidates`` that Git reports as ignored. An empty
    result is also returned when Git is unavailable: callers that add new ignore
    rules assert on the filesystem artifact instead of trusting this helper.
    """
    import subprocess

    names = [str(candidate) for candidate in candidates]
    if not names:
        return set()
    root = repo_root or Path(__file__).resolve().parents[1]
    try:
        completed = subprocess.run(
            ["git", "check-ignore", "--no-index", "--stdin"],
            cwd=str(root),
            input="\n".join(names) + "\n",
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - no git on PATH
        return set()
    if completed.returncode not in (0, 1):  # 1 == nothing ignored
        return set()
    return {line.strip() for line in completed.stdout.splitlines() if line.strip()}


# --------------------------------------------------------------------------- #
# Operator-owned destructive actions
# --------------------------------------------------------------------------- #


def assert_operator_action_target(
    path: str | os.PathLike[str],
    *,
    purpose: str,
    invariant: str = "operator-action-target",
    forbidden_root: str | os.PathLike[str] | None = None,
) -> Path:
    """Refuse a destructive operator action on a database inside a Git checkout.

    Separate from :func:`assert_safe`: an operator CLI legitimately acts on the
    configured production database (that is its whole job), but it must never act
    on a database that lives inside a working tree, because that is the artifact
    sources, tests and diagnostic probes share fate with — the 2026-09-20
    deletion shape. Deleting a reproduced file is not recoverable from Git.

    Returns the resolved path so the caller prints exactly what it will change.
    """
    import subprocess

    resolved = normalize_path(path)
    root = normalize_path(forbidden_root) if forbidden_root is not None else resolved.parent
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(root if root.exists() else Path.cwd()),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - no git on PATH
        return resolved

    if completed.returncode != 0 or not completed.stdout.strip():
        return resolved

    checkout = normalize_path(completed.stdout.strip())
    if _within(resolved, checkout):
        raise DatabasePathViolation(
            invariant,
            kind=DatabasePathKind.REAL,
            detail=(
                f"{purpose} must not target a database inside a Git checkout; "
                "move it to the application-data directory first"
            ),
        )
    return resolved
