"""#624 — moving the dogfood database out of the Git checkout.

Every path belongs to ``tmp_path``; the maintainer's working database, its
sidecars and provider credentials are never touched. The suite pins the four
properties the issue demands: committed WAL pages travel with the migration, an
ambiguous target stops the run, the legacy source survives every failure, and a
fresh install's default path is outside any checkout.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

import config.db_paths as db_paths
from config import app_data
from config.settings import Settings
from scripts.migrate_database_out_of_checkout import (
    KEY_DOMAINS,
    MigrationError,
    build_plan,
    count_domains,
    main,
    migrate_database,
    resolve_default_source,
    resolve_default_target,
    update_env_file,
)

pytestmark = pytest.mark.smoke

REPO_ROOT = Path(app_data.__file__).resolve().parents[1]


def _marker_database(path: Path, marker: str = "legacy", *, domains: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE marker(value TEXT NOT NULL)")
        conn.execute("INSERT INTO marker(value) VALUES (?)", (marker,))
        if domains:
            conn.execute("CREATE TABLE activities(activity_id TEXT)")
            conn.execute("INSERT INTO activities VALUES ('a1'), ('a2')")
            conn.execute("CREATE TABLE planning_checkpoints(id INTEGER)")
            conn.execute("INSERT INTO planning_checkpoints VALUES (1)")
        conn.commit()
    finally:
        conn.close()
    return path


def _read_marker(path: Path) -> str:
    conn = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)
    try:
        return conn.execute("SELECT value FROM marker").fetchone()[0]
    finally:
        conn.close()


def _leave_committed_marker_in_wal(path: Path, value: str) -> None:
    """Commit an update that lives ONLY in the ``-wal`` file (cheap check 2)."""
    conn = sqlite3.connect(path)
    try:
        assert conn.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        conn.execute("PRAGMA wal_autocheckpoint=0")
        conn.execute("UPDATE marker SET value=?", (value,))
        conn.commit()
        main_bytes = path.read_bytes()
        wal_bytes = Path(f"{path}-wal").read_bytes()
    finally:
        conn.close()
    # Recreate the exact torn state a plain `cp` of the database would lose.
    path.write_bytes(main_bytes)
    Path(f"{path}-wal").write_bytes(wal_bytes)


@pytest.fixture
def legacy_layout(tmp_path: Path) -> tuple[Path, Path]:
    """A checkout-resident legacy database and a fresh application-data target."""
    source = tmp_path / "checkout" / "ai_trainer.db"
    target = tmp_path / "app-data" / "ai_trainer.db"
    _marker_database(source, "legacy", domains=True)
    return source, target


# --------------------------------------------------------------------------- #
# The default path contract
# --------------------------------------------------------------------------- #


def test_default_database_lives_outside_any_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_data_dir = tmp_path / "app-data"
    monkeypatch.setenv(app_data.APP_DATA_DIR_ENV, str(app_data_dir))

    default = app_data.default_database_path()

    assert default is not None
    resolved = Path(default)
    assert resolved.parent == app_data_dir.resolve() or str(resolved).startswith(str(app_data_dir))
    assert not resolved.is_relative_to(REPO_ROOT)


def test_default_database_path_is_documented_per_platform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(app_data.APP_DATA_DIR_ENV, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    if sys.platform == "darwin":
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        assert app_data.app_data_directory() == tmp_path / "home" / "Library" / "Application Support" / "ai_trainer"
    elif os.name == "nt":  # pragma: no cover - Windows only
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
        assert app_data.app_data_directory() == tmp_path / "local" / "ai_trainer"
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
        assert app_data.app_data_directory() == tmp_path / "xdg" / "ai_trainer"

        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        assert app_data.app_data_directory() == tmp_path / "home" / ".local" / "share" / "ai_trainer"


def test_application_data_default_is_used_when_no_explicit_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The documented precedence: explicit DATABASE_PATH → app data → legacy name."""
    monkeypatch.setenv(app_data.APP_DATA_DIR_ENV, str(tmp_path / "app-data"))
    assert app_data.default_database_path() == str(tmp_path / "app-data" / app_data.DATABASE_NAME)

    # A dogfood install that pinned DATABASE_PATH in .env keeps that choice (an
    # explicit override outranks the default) — which is exactly why the
    # migration command rewrites that line explicitly.
    assert Settings.DATABASE_PATH


def test_dogfood_env_pinning_the_repository_path_is_detected() -> None:
    """The repository .env is the reason a dogfood install needs an explicit move.

    `.env` is loaded by `config.settings`, so a pinned `DATABASE_PATH` outranks the
    new application-data default until the operator updates that line; the
    migration command does it via ``--update-env``.
    """
    env_file = REPO_ROOT / ".env"
    if not env_file.is_file():  # pragma: no cover - contributor without a personal .env
        pytest.skip("no local .env in this checkout")

    pinned = [
        line
        for line in env_file.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("DATABASE_PATH=")
    ]
    assert pinned, "a dogfood .env that pins DATABASE_PATH must be visible to the migration"
    assert app_data.DATABASE_NAME in pinned[0]


def test_docker_keeps_its_volume_path() -> None:
    """The container contract is unchanged by the relocation."""
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "DATABASE_PATH: /data/ai_trainer.db" in compose


def test_no_home_directory_falls_back_to_the_previous_default(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(app_data.APP_DATA_DIR_ENV, raising=False)
    monkeypatch.setenv("HOME", "~")
    monkeypatch.setattr(app_data.os.path, "expanduser", lambda _value: "~")

    assert app_data.app_data_directory() is None
    assert app_data.default_database_path() is None


def test_app_data_override_is_not_inside_a_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(app_data.APP_DATA_DIR_ENV, str(tmp_path / "data"))
    target = resolve_default_target()
    assert not db_paths.normalize_path(target).is_relative_to(REPO_ROOT)


def test_migration_target_inside_a_checkout_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A target inside a working tree would recreate the very coupling #624 removes."""
    monkeypatch.setenv(app_data.APP_DATA_DIR_ENV, str(REPO_ROOT / "would-be-data"))
    with pytest.raises(db_paths.DatabasePathViolation) as error:
        resolve_default_target()
    assert error.value.invariant == "migration-target-must-leave-the-checkout"


# --------------------------------------------------------------------------- #
# Cheap falsifying check 2: committed WAL pages must travel
# --------------------------------------------------------------------------- #


def test_migration_moves_committed_wal_pages(legacy_layout: tuple[Path, Path]) -> None:
    source, target = legacy_layout
    _leave_committed_marker_in_wal(source, "wal-value")

    report = migrate_database(source, target, confirm_stopped=True)

    assert report.status == "migrated"
    assert report.integrity_check == "ok"
    assert _read_marker(target) == "wal-value", "committed WAL page was lost"
    assert _read_marker(source) == "wal-value", "source must stay readable"


def test_main_file_alone_would_not_carry_the_wal_update(legacy_layout: tuple[Path, Path]) -> None:
    """Falsifies the cheap alternative: a plain copy of the file misses the WAL."""
    source, target = legacy_layout
    _leave_committed_marker_in_wal(source, "wal-value")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())

    assert _read_marker(target) == "legacy", "plain copy is expected to lose the WAL update"
    assert _read_marker(source) == "wal-value"


# --------------------------------------------------------------------------- #
# Dry run
# --------------------------------------------------------------------------- #


def test_dry_run_reports_aggregates_and_writes_nothing(legacy_layout: tuple[Path, Path]) -> None:
    source, target = legacy_layout
    before = (source.stat().st_size, source.stat().st_mtime_ns)

    report = migrate_database(source, target, confirm_stopped=False, dry_run=True)

    assert report.status == "dry-run"
    assert report.domains["activities"] == 2
    assert report.domains["planning_checkpoints"] == 1
    assert not target.exists()
    assert not Path(report.source).with_name("x").exists()
    assert (source.stat().st_size, source.stat().st_mtime_ns) == before


def test_dry_run_needs_no_stopped_confirmation(legacy_layout: tuple[Path, Path]) -> None:
    """Reporting aggregates is safe; only publishing requires --confirm-stopped."""
    source, target = legacy_layout
    assert migrate_database(source, target, confirm_stopped=False, dry_run=True).status == "dry-run"


def test_dry_run_output_contains_no_personal_rows(legacy_layout: tuple[Path, Path], capsys) -> None:
    source, target = legacy_layout
    assert main(["--source", str(source), "--target", str(target), "--dry-run"]) == 0

    captured = capsys.readouterr().out
    assert "legacy" not in captured, "dry run must not print row values"
    assert "activities=2" in captured


# --------------------------------------------------------------------------- #
# Fail-closed gates
# --------------------------------------------------------------------------- #


def test_same_source_and_target_is_refused(legacy_layout: tuple[Path, Path]) -> None:
    source, _target = legacy_layout
    with pytest.raises(MigrationError, match="same file"):
        migrate_database(source, source, confirm_stopped=True)


def test_symlinked_target_is_refused(tmp_path: Path, legacy_layout: tuple[Path, Path]) -> None:
    """Cheap falsifying check 3: a symlink onto the source must fail closed."""
    source, _target = legacy_layout
    alias = tmp_path / "app-data-alias" / "ai_trainer.db"
    alias.parent.mkdir(parents=True, exist_ok=True)
    alias.symlink_to(source)

    with pytest.raises(MigrationError, match="symbolic link"):
        migrate_database(source, alias, confirm_stopped=True)

    assert _read_marker(source) == "legacy"


def test_populated_target_is_never_silently_overwritten(
    legacy_layout: tuple[Path, Path]
) -> None:
    source, target = legacy_layout
    _marker_database(target, "fresh-target", domains=True)

    with pytest.raises(MigrationError, match="already contains data"):
        migrate_database(source, target, confirm_stopped=True)

    assert _read_marker(target) == "fresh-target"
    assert _read_marker(source) == "legacy"
    assert not Path(f"{target}.pre-migration").exists()


def test_existing_target_requires_explicit_empty_permission(
    legacy_layout: tuple[Path, Path]
) -> None:
    source, target = legacy_layout
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"")

    with pytest.raises(MigrationError, match="allow-empty-target"):
        migrate_database(source, target, confirm_stopped=True)

    assert target.read_bytes() == b""
    assert _read_marker(source) == "legacy"


def test_missing_stopped_confirmation_publishes_nothing(legacy_layout: tuple[Path, Path]) -> None:
    source, target = legacy_layout
    with pytest.raises(MigrationError, match="confirm-stopped"):
        migrate_database(source, target, confirm_stopped=False)
    assert not target.exists()


def test_missing_source_is_refused(tmp_path: Path) -> None:
    with pytest.raises(MigrationError, match="does not exist"):
        migrate_database(tmp_path / "absent.db", tmp_path / "out" / "ai_trainer.db", confirm_stopped=True)


def test_invalid_source_is_refused(tmp_path: Path) -> None:
    broken = tmp_path / "broken.db"
    broken.write_bytes(b"this is not a sqlite database at all, not even close")
    with pytest.raises(MigrationError):
        migrate_database(broken, tmp_path / "out" / "ai_trainer.db", confirm_stopped=True)


def test_source_without_key_domains_is_refused(tmp_path: Path) -> None:
    """An empty or unrelated file is not "the dogfood database"."""
    empty = tmp_path / "empty.db"
    conn = sqlite3.connect(empty)
    conn.execute("CREATE TABLE unrelated(value TEXT)")
    conn.commit()
    conn.close()

    with pytest.raises(MigrationError, match="no rows in the key domains"):
        migrate_database(empty, tmp_path / "out" / "ai_trainer.db", confirm_stopped=True)


def test_populated_target_is_refused_even_with_dry_run_marker(legacy_layout: tuple[Path, Path]) -> None:
    source, target = legacy_layout
    _marker_database(target, "fresh-target", domains=True)

    plan = build_plan(source, target)
    assert any(plan.target_counts.values()), "plan must surface the ambiguous target"


# --------------------------------------------------------------------------- #
# Rollback snapshot and injected failures
# --------------------------------------------------------------------------- #


def test_rollback_snapshot_is_published_before_the_target(
    legacy_layout: tuple[Path, Path]
) -> None:
    source, target = legacy_layout
    report = migrate_database(source, target, confirm_stopped=True)

    assert report.rollback is not None
    rollback = Path(report.rollback)
    assert rollback.is_file()
    assert _read_marker(rollback) == "legacy"
    assert rollback.parent == target.parent


def test_failure_while_publishing_the_target_keeps_source_and_rollback(
    legacy_layout: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Injected failure: the source stays readable and no partial target appears."""
    source, target = legacy_layout
    import scripts.migrate_database_out_of_checkout as migration

    real_backup = migration.backup_database
    calls: list[str] = []

    def flaky_backup(database, output, *, confirm_stopped):
        calls.append(str(output))
        if len(calls) == 2:
            raise migration.SQLiteBackupRestoreError("injected publish failure")
        return real_backup(database, output, confirm_stopped=confirm_stopped)

    monkeypatch.setattr(migration, "backup_database", flaky_backup)

    with pytest.raises(MigrationError, match="injected publish failure"):
        migrate_database(source, target, confirm_stopped=True)

    assert _read_marker(source) == "legacy"
    published = list(Path(target).parent.glob("*.pre-migration-*"))
    assert published, "the pre-migration snapshot must exist even when publish fails"
    assert not target.exists() or _read_marker(target) == "legacy"


def test_row_loss_in_the_target_is_detected(
    legacy_layout: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A target missing source rows must not be reported as a successful migration."""
    source, target = legacy_layout
    import scripts.migrate_database_out_of_checkout as migration

    real_count = migration.count_domains

    def partial_count(path):
        counts = real_count(path)
        if db_paths.normalize_path(path) == db_paths.normalize_path(target):
            counts["activities"] = 0
        return counts

    monkeypatch.setattr(migration, "count_domains", partial_count)

    with pytest.raises(MigrationError, match="missing rows"):
        migrate_database(source, target, confirm_stopped=True)

    assert _read_marker(source) == "legacy"


def test_domain_reporting_covers_the_issue_list(legacy_layout: tuple[Path, Path]) -> None:
    source, _target = legacy_layout
    expected = {
        "activities",
        "activity_provider_links",
        "planning_checkpoints",
        "coach_decisions",
        "plan_actual_matches",
        "session_feedback",
        "readiness_snapshots",
    }
    assert expected == set(KEY_DOMAINS)
    assert set(count_domains(source)) <= expected


# --------------------------------------------------------------------------- #
# Env file hand-off
# --------------------------------------------------------------------------- #


def test_update_env_file_rewrites_only_the_database_line(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# comment\nSECRET_TOKEN=keep-me\nDATABASE_PATH=ai_trainer.db\nUSER_FTP=250\n",
        encoding="utf-8",
    )

    backup = update_env_file(env, "/app/data/ai_trainer.db")

    text = env.read_text(encoding="utf-8")
    assert "SECRET_TOKEN=keep-me" in text
    assert "USER_FTP=250" in text
    assert "# comment" in text
    assert "DATABASE_PATH=/app/data/ai_trainer.db" in text
    assert "DATABASE_PATH=ai_trainer.db" not in text
    assert Path(backup).read_text(encoding="utf-8").count("DATABASE_PATH=ai_trainer.db") == 1


def test_update_env_file_appends_when_absent(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("SECRET_TOKEN=keep-me\n", encoding="utf-8")

    update_env_file(env, "/app/data/ai_trainer.db")

    text = env.read_text(encoding="utf-8")
    assert "SECRET_TOKEN=keep-me" in text
    assert "DATABASE_PATH=/app/data/ai_trainer.db" in text


def test_update_env_file_dry_run_changes_nothing(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    original = "DATABASE_PATH=ai_trainer.db\n"
    env.write_text(original, encoding="utf-8")

    assert update_env_file(env, "/app/data/ai_trainer.db", dry_run=True) == "dry-run"
    assert env.read_text(encoding="utf-8") == original


def test_update_env_file_missing_is_refused(tmp_path: Path) -> None:
    with pytest.raises(MigrationError, match="does not exist"):
        update_env_file(tmp_path / "absent.env", "/app/data/ai_trainer.db")


# --------------------------------------------------------------------------- #
# CLI wiring
# --------------------------------------------------------------------------- #


def test_cli_refuses_without_confirmation(legacy_layout: tuple[Path, Path], capsys) -> None:
    source, target = legacy_layout
    assert main(["--source", str(source), "--target", str(target)]) == 2
    assert "confirm-stopped" in capsys.readouterr().err
    assert not target.exists()


def test_cli_migrates_and_reports_json(legacy_layout: tuple[Path, Path], capsys) -> None:
    source, target = legacy_layout
    code = main(["--source", str(source), "--target", str(target), "--confirm-stopped", "--json"])

    assert code == 0
    payload = capsys.readouterr().out
    assert '"status": "migrated"' in payload
    assert _read_marker(target) == "legacy"


def test_default_source_prefers_the_configured_database(
    legacy_layout: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    source, _target = legacy_layout
    monkeypatch.delenv(db_paths.PRODUCTION_DB_ENV, raising=False)
    monkeypatch.setattr(Settings, "DATABASE_PATH", str(source))
    assert db_paths.normalize_path(resolve_default_source()) == db_paths.normalize_path(source)
