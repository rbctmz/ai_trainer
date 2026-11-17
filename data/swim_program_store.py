"""Immutable swim-library versions and retained preview receipts on owned SQLite."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from typing import Any, Iterator
from uuid import uuid4

from pydantic import ValidationError
from models.swim_program import SwimProgramDocument, canonical_json
from models.swim_program_documents import (
    validate_program_document,
    fingerprint_program,
    summarize_document,
)


class SwimProgramError(ValueError):
    def __init__(self, code: str, status: int = 409):
        super().__init__(code)
        self.code, self.status = code, status


def initialize(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS swim_program_previews (
        preview_id TEXT PRIMARY KEY NOT NULL, program_id TEXT NOT NULL,
        base_revision INTEGER NOT NULL CHECK(base_revision >= 0),
        document_json TEXT NOT NULL, summary_json TEXT NOT NULL, fingerprint TEXT NOT NULL,
        created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
        applied_revision INTEGER, applied_at TEXT,
        CHECK ((applied_revision IS NULL AND applied_at IS NULL) OR
               (applied_revision > 0 AND applied_at IS NOT NULL))
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS swim_program_versions (
        program_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision > 0),
        preview_id TEXT NOT NULL UNIQUE, document_json TEXT NOT NULL,
        summary_json TEXT NOT NULL, fingerprint TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY(program_id, revision)
    )""")


def _instant(now: datetime | None) -> datetime:
    result = now or datetime.now(timezone.utc)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("explicit timezone-aware clock required")
    return result.astimezone(timezone.utc)


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("stored time must include timezone")
    return parsed.astimezone(timezone.utc)


@contextmanager
def _connection(db: Any, *, write: bool = False) -> Iterator[sqlite3.Connection]:
    try:
        conn = db._connect()
    except sqlite3.Error as exc:
        raise SwimProgramError("swim_program_storage_unavailable", 503) from exc
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield conn
        if write:
            conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        raise SwimProgramError("swim_program_storage_unavailable", 503) from exc
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _validated(row: sqlite3.Row) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        document = validate_program_document(json.loads(row["document_json"]))
        if (
            str(document.id) != row["program_id"]
            or fingerprint_program(document) != row["fingerprint"]
        ):
            raise ValueError("stored content hash mismatch")
        summary = summarize_document(document)
        if canonical_json(summary) != row["summary_json"]:
            raise ValueError("stored summary mismatch")
        _parse_time(row["created_at"])
        return document.model_dump(mode="json"), summary
    except (ValueError, TypeError, KeyError, ValidationError) as exc:
        raise SwimProgramError("swim_program_corrupt", 503) from exc


def _head(conn: sqlite3.Connection, program_id: str) -> int:
    row = conn.execute(
        "SELECT * FROM swim_program_versions WHERE program_id=? ORDER BY revision DESC LIMIT 1",
        (program_id,),
    ).fetchone()
    if row is None:
        return 0
    _validated(row)
    return int(row["revision"])


def _version(
    conn: sqlite3.Connection, program_id: str, revision: int | None = None
) -> dict[str, Any]:
    if revision is None:
        row = conn.execute(
            "SELECT * FROM swim_program_versions WHERE program_id=? ORDER BY revision DESC LIMIT 1",
            (program_id,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM swim_program_versions WHERE program_id=? AND revision=?",
            (program_id, revision),
        ).fetchone()
    if row is None:
        raise SwimProgramError("swim_program_not_found", 404)
    document, summary = _validated(row)
    return {
        "program_id": row["program_id"],
        "revision": row["revision"],
        "document": document,
        "summary": summary,
        "fingerprint": row["fingerprint"],
        "confirmed_at": row["created_at"],
    }


def create_preview(
    db: Any, payload: dict[str, Any], *, base_revision: int, now: datetime | None = None
) -> dict[str, Any]:
    document = SwimProgramDocument.model_validate(payload)
    with _connection(db, write=True) as conn:
        return _create_preview(
            conn, document, base_revision=base_revision, instant=_instant(now)
        )


def _create_preview(
    conn: sqlite3.Connection, document: Any, *, base_revision: int, instant: datetime
) -> dict[str, Any]:
    """Caller owns the transaction, including any source/revision binding."""
    if type(base_revision) is not int or base_revision < 0:
        raise ValueError("nonnegative integer base revision required")
    text = canonical_json(document.model_dump(mode="json"))
    summary = summarize_document(document)
    fingerprint = fingerprint_program(document)
    preview_id = str(uuid4())
    expires_at = (instant + timedelta(hours=24)).isoformat()
    if _head(conn, str(document.id)) != base_revision:
        raise SwimProgramError("swim_program_stale")
    # Import previews retain a replay receipt; their authority still expires in24h.
    conn.execute(
        """DELETE FROM swim_program_previews WHERE applied_revision IS NULL AND expires_at <= ?
        AND preview_id NOT IN (SELECT preview_id FROM swim_import_previews)""",
        (instant.isoformat(),),
    )
    conn.execute(
        """INSERT INTO swim_program_previews
        (preview_id,program_id,base_revision,document_json,summary_json,fingerprint,created_at,expires_at)
        VALUES (?,?,?,?,?,?,?,?)""",
        (
            preview_id,
            str(document.id),
            base_revision,
            text,
            canonical_json(summary),
            fingerprint,
            instant.isoformat(),
            expires_at,
        ),
    )
    return {
        "preview_id": preview_id,
        "base_revision": base_revision,
        "document": document.model_dump(mode="json"),
        "summary": summary,
        "fingerprint": fingerprint,
        "expires_at": expires_at,
    }


def confirm_preview(
    db: Any, preview_id: str, *, now: datetime | None = None
) -> dict[str, Any]:
    instant = _instant(now)
    with _connection(db, write=True) as conn:
        row = conn.execute(
            "SELECT * FROM swim_program_previews WHERE preview_id=?", (preview_id,)
        ).fetchone()
        if row is None:
            raise SwimProgramError("swim_program_not_found", 404)
        document, _ = _validated(row)
        if document["schema_version"] == 2:
            from data.swim_import_store import validate_confirmation_binding

            validate_confirmation_binding(conn, row)
        if row["applied_revision"] is not None:
            try:
                result = _version(conn, row["program_id"], row["applied_revision"])
            except SwimProgramError as exc:
                if exc.status == 404:
                    raise SwimProgramError("swim_program_corrupt", 503) from exc
                raise
            version_row = conn.execute(
                "SELECT preview_id FROM swim_program_versions WHERE program_id=? AND revision=?",
                (row["program_id"], row["applied_revision"]),
            ).fetchone()
            if (
                not version_row
                or version_row[0] != preview_id
                or result["fingerprint"] != row["fingerprint"]
                or result["confirmed_at"] != row["applied_at"]
            ):
                raise SwimProgramError("swim_program_corrupt", 503)
            return result
        try:
            expiry = _parse_time(row["expires_at"])
        except (ValueError, TypeError) as exc:
            raise SwimProgramError("swim_program_corrupt", 503) from exc
        if instant >= expiry:
            raise SwimProgramError("swim_program_preview_expired")
        if _head(conn, row["program_id"]) != row["base_revision"]:
            raise SwimProgramError("swim_program_stale")
        revision = row["base_revision"] + 1
        conn.execute(
            """INSERT INTO swim_program_versions
            (program_id,revision,preview_id,document_json,summary_json,fingerprint,created_at)
            VALUES (?,?,?,?,?,?,?)""",
            (
                row["program_id"],
                revision,
                preview_id,
                row["document_json"],
                row["summary_json"],
                row["fingerprint"],
                instant.isoformat(),
            ),
        )
        conn.execute(
            "UPDATE swim_program_previews SET applied_revision=?,applied_at=? WHERE preview_id=?",
            (revision, instant.isoformat(), preview_id),
        )
        result = _version(conn, row["program_id"], revision)
    from services.snapshot_runtime import mark_committed

    mark_committed(db)
    return result


def get_version(
    db: Any, program_id: str, *, revision: int | None = None
) -> dict[str, Any]:
    with _connection(db) as conn:
        return _version(conn, program_id, revision)


def list_programs(db: Any) -> list[dict[str, Any]]:
    with _connection(db) as conn:
        rows = conn.execute("""SELECT v.* FROM swim_program_versions v
            WHERE revision=(SELECT MAX(revision) FROM swim_program_versions WHERE program_id=v.program_id)
            ORDER BY created_at DESC,program_id""").fetchall()
        results = []
        for row in rows:
            document, summary = _validated(row)
            results.append(
                {
                    "program_id": row["program_id"],
                    "revision": row["revision"],
                    "schema_version": document["schema_version"],
                    "title": document["title"],
                    "source_week_label": document["source_week_label"],
                    "workout_count": len(document["workouts"]),
                    "distance_meters": summary["distance_meters"],
                    "known_distance_meters": summary.get(
                        "known_distance_meters", summary["distance_meters"]
                    ),
                    "updated_at": row["created_at"],
                }
            )
        return results
