"""Append-only private exercise catalog, transactional CAS and durable replays."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import sqlite3
from typing import Any, Iterator
from uuid import UUID

from models.swim_exercise import SwimExerciseDocument, exercise_fingerprint
from models.swim_program import canonical_json


class SwimExerciseError(ValueError):
    def __init__(self, code: str, status: int = 409):
        super().__init__(code)
        self.code, self.status = "swim_exercise_" + code, status


def initialize(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS swim_exercise_versions (
        exercise_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0),
        base_revision INTEGER NOT NULL CHECK(base_revision>=0),
        request_id TEXT UNIQUE NOT NULL, document_json TEXT NOT NULL,
        fingerprint TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY(exercise_id,revision)
    )""")


@contextmanager
def _connection(db: Any, *, write: bool = False) -> Iterator[sqlite3.Connection]:
    conn = None
    try:
        conn = db._connect()
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield conn
        if write:
            conn.commit()
    except sqlite3.Error as exc:
        if conn is not None:
            conn.rollback()
        raise SwimExerciseError("storage_unavailable", 503) from exc
    except Exception:
        if conn is not None:
            conn.rollback()
        raise
    finally:
        if conn is not None:
            conn.close()


def _validated(row: sqlite3.Row) -> dict[str, Any]:
    try:
        document = SwimExerciseDocument.model_validate(json.loads(row["document_json"]))
        instant = datetime.fromisoformat(row["created_at"])
        if (
            str(document.id) != row["exercise_id"]
            or exercise_fingerprint(document) != row["fingerprint"]
            or row["revision"] != row["base_revision"] + 1
            or row["base_revision"] < 0
            or instant.tzinfo is None
            or instant.utcoffset() is None
            or str(UUID(row["request_id"])) != row["request_id"]
        ):
            raise ValueError("stored identity or metadata mismatch")
        return {
            "exercise_id": row["exercise_id"],
            "revision": row["revision"],
            "document": document.model_dump(mode="json"),
            "fingerprint": row["fingerprint"],
            "confirmed_at": row["created_at"],
        }
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise SwimExerciseError("corrupt", 503) from exc


def _row(
    conn: sqlite3.Connection, exercise_id: str, revision: int | None = None
) -> sqlite3.Row | None:
    if revision is None:
        return conn.execute(
            "SELECT * FROM swim_exercise_versions WHERE exercise_id=? ORDER BY revision DESC LIMIT 1",
            (exercise_id,),
        ).fetchone()
    return conn.execute(
        "SELECT * FROM swim_exercise_versions WHERE exercise_id=? AND revision=?",
        (exercise_id, revision),
    ).fetchone()


def confirm(
    db: Any,
    document: SwimExerciseDocument,
    *,
    base_revision: int,
    request_id: str,
    fingerprint: str,
) -> dict[str, Any]:
    if type(base_revision) is not int or base_revision < 0:
        raise ValueError("nonnegative integer base revision required")
    request_id = str(UUID(request_id))
    if fingerprint != exercise_fingerprint(document):
        raise SwimExerciseError("fingerprint_mismatch")
    with _connection(db, write=True) as conn:
        receipt = conn.execute(
            "SELECT * FROM swim_exercise_versions WHERE request_id=?", (request_id,)
        ).fetchone()
        if receipt is not None:
            result = _validated(receipt)
            if (
                receipt["exercise_id"] != str(document.id)
                or receipt["fingerprint"] != fingerprint
                or receipt["base_revision"] != base_revision
            ):
                raise SwimExerciseError("request_conflict")
            return result
        head = _row(conn, str(document.id))
        if head is not None:
            _validated(head)
        if (head["revision"] if head else 0) != base_revision:
            raise SwimExerciseError("stale")
        conn.execute(
            """INSERT INTO swim_exercise_versions
            (exercise_id,revision,base_revision,request_id,document_json,fingerprint,created_at)
            VALUES (?,?,?,?,?,?,?)""",
            (
                str(document.id),
                base_revision + 1,
                base_revision,
                request_id,
                canonical_json(document.model_dump(mode="json")),
                fingerprint,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        result = _validated(_row(conn, str(document.id)))
    from services.snapshot_runtime import mark_committed

    mark_committed(db)
    return result


def get_version(
    db: Any, exercise_id: str, *, revision: int | None = None
) -> dict[str, Any]:
    with _connection(db) as conn:
        row = _row(conn, exercise_id, revision)
        if row is None:
            raise SwimExerciseError("not_found", 404)
        return _validated(row)


def list_exercises(db: Any, *, query: str = "") -> list[dict[str, Any]]:
    if not isinstance(query, str) or len(query) > 200:
        raise ValueError("query limit exceeded")
    needle = query.strip().casefold()
    with _connection(db) as conn:
        rows = conn.execute("""SELECT v.* FROM swim_exercise_versions v
            WHERE revision=(SELECT MAX(revision) FROM swim_exercise_versions WHERE exercise_id=v.exercise_id)
            ORDER BY exercise_id""").fetchall()
        results = []
        for row in rows:
            result = _validated(row)
            doc = result["document"]
            if not needle or any(
                needle in s.casefold()
                for s in (doc["name"], doc["variant"], *doc["aliases"])
            ):
                results.append(result)
        return results
