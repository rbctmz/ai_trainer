"""Append-only persistence for durable athlete-entered feedback facts."""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable, Mapping


CleanValue = Callable[[Any], Any]
FACT_RULE_VERSION = "athlete_feedback_fact_v1"


def create_athlete_feedback_facts_table(conn: sqlite3.Connection) -> None:
    """Create the M0 feedback-fact ledger when it is not present."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS athlete_feedback_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT NOT NULL UNIQUE,
            target_key TEXT NOT NULL,
            revision INTEGER NOT NULL,
            supersedes_fact_id INTEGER,
            feedback_id INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            fact_type TEXT NOT NULL,
            value_json TEXT NOT NULL,
            provenance_json TEXT NOT NULL,
            status TEXT NOT NULL,
            rule_version TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(target_key, revision)
        )
        """
    )


class AthleteFeedbackFactStore:
    """Store facts over a caller-owned SQLite connection.

    The caller owns the transaction. This is important because the feedback
    journal and its durable fact must commit or roll back together.
    """

    def __init__(self, conn: sqlite3.Connection, clean_value: CleanValue):
        self._conn = conn
        self._clean_value = clean_value

    def append_from_feedback(self, feedback: Mapping[str, Any]) -> dict[str, Any]:
        """Append one fact for one already-stored feedback revision."""
        feedback_id = int(feedback["id"])
        fingerprint = f"session-feedback-fact:{feedback['fingerprint']}"
        existing = self._conn.execute(
            "SELECT * FROM athlete_feedback_facts WHERE fingerprint = ? LIMIT 1",
            (fingerprint,),
        ).fetchone()
        if existing is not None:
            return self._deserialize(existing)

        target_key = str(feedback["target_key"])
        previous = self._conn.execute(
            """
            SELECT id, revision
            FROM athlete_feedback_facts
            WHERE target_key = ?
            ORDER BY revision DESC, id DESC
            LIMIT 1
            """,
            (target_key,),
        ).fetchone()
        revision = int(previous[1]) + 1 if previous else 1
        status = "withdrawn" if feedback.get("status") == "tombstone" else "active"
        value = {
            "completion_pct": self._clean_value(feedback.get("completion_pct")),
            "completion_status": str(feedback.get("completion_status") or ""),
            "quality_rating_1_5": self._clean_value(feedback.get("quality_rating_1_5")),
            "session_rpe_1_10": self._clean_value(feedback.get("session_rpe_1_10")),
        }
        provenance = {
            "label": (
                "athlete-entered"
                if feedback.get("source") == "user_web"
                else "administrative"
            ),
            "owner": "athlete" if feedback.get("source") == "user_web" else "system",
            "source": "session_feedback",
            "source_feedback_fingerprint": str(feedback["fingerprint"]),
            "source_feedback_id": feedback_id,
            "source_feedback_revision": int(feedback["revision"]),
            "source_rule_version": str(feedback.get("rule_version") or ""),
            "match_revision_id": feedback.get("match_revision_id"),
            "session_end_at_utc": feedback.get("session_end_at_utc"),
            "session_end_provenance": str(
                feedback.get("session_end_provenance") or ""
            ),
        }
        cursor = self._conn.execute(
            """
            INSERT INTO athlete_feedback_facts (
                fingerprint, target_key, revision, supersedes_fact_id,
                feedback_id, session_id, fact_type, value_json,
                provenance_json, status, rule_version
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fingerprint,
                target_key,
                revision,
                previous[0] if previous else None,
                feedback_id,
                str(feedback["session_id"]),
                "session_feedback",
                json.dumps(value, ensure_ascii=False, sort_keys=True, default=str),
                json.dumps(
                    provenance, ensure_ascii=False, sort_keys=True, default=str
                ),
                status,
                FACT_RULE_VERSION,
            ),
        )
        row = self._conn.execute(
            "SELECT * FROM athlete_feedback_facts WHERE id = ?",
            (int(cursor.lastrowid),),
        ).fetchone()
        return self._deserialize(row)

    def get_latest(self, target_key: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT * FROM athlete_feedback_facts
            WHERE target_key = ?
            ORDER BY revision DESC, id DESC
            LIMIT 1
            """,
            (str(target_key),),
        ).fetchone()
        return self._deserialize(row)

    def get_history(self, target_key: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT * FROM athlete_feedback_facts
            WHERE target_key = ?
            ORDER BY revision, id
            """,
            (str(target_key),),
        ).fetchall()
        return [self._deserialize(row) for row in rows]

    @staticmethod
    def _deserialize(row: sqlite3.Row | tuple | None) -> dict[str, Any] | None:
        if row is None:
            return None

        def _json(value: Any) -> dict[str, Any]:
            try:
                parsed = json.loads(value) if value else {}
            except (TypeError, json.JSONDecodeError):
                return {}
            return parsed if isinstance(parsed, dict) else {}

        return {
            "id": row[0],
            "fingerprint": row[1],
            "target_key": row[2],
            "revision": row[3],
            "supersedes_fact_id": row[4],
            "feedback_id": row[5],
            "session_id": row[6],
            "fact_type": row[7],
            "value": _json(row[8]),
            "provenance": _json(row[9]),
            "status": row[10],
            "rule_version": row[11],
            "created_at": row[12],
        }
