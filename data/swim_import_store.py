"""Retained sources and append-only draft revisions on the selected SQLite store."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import sqlite3
from typing import Any, Iterator, Literal
from uuid import UUID, uuid4

from pydantic import TypeAdapter, ValidationError

from data import swim_exercise_store as exercises
from data import swim_program_store as library
from models.swim_import import (
    CaptureSource,
    ParseDraft,
    PatchDraft,
    PrepareDraft,
    SourceAcknowledgement,
)
from models.swim_program import canonical_json
from models.swim_program_documents import fingerprint_program, summarize_document
from models.swim_program_v2 import SwimProgramDocumentV2

Actor = Literal["user", "coach"]
ACKS = TypeAdapter(list[SourceAcknowledgement])


class SwimImportError(ValueError):
    def __init__(self, code: str, status: int = 409):
        self.code, self.status = "swim_import_" + code, status
        super().__init__(self.code)


def initialize(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS swim_import_sources (
        import_id TEXT PRIMARY KEY NOT NULL, program_id TEXT UNIQUE NOT NULL,
        request_id TEXT UNIQUE NOT NULL, source_text TEXT NOT NULL,
        source_sha256 TEXT NOT NULL, source_label TEXT, source_week_label TEXT,
        command_json TEXT NOT NULL, metadata_hash TEXT NOT NULL, created_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS swim_import_revisions (
        import_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>=0),
        request_id TEXT UNIQUE NOT NULL, command_json TEXT NOT NULL, command_hash TEXT NOT NULL,
        actor TEXT NOT NULL, document_json TEXT, summary_json TEXT,
        acknowledgements_json TEXT NOT NULL, fingerprint TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY(import_id,revision)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS swim_import_previews (
        preview_id TEXT PRIMARY KEY NOT NULL, import_id TEXT NOT NULL,
        draft_revision INTEGER NOT NULL CHECK(draft_revision>=1),
        request_id TEXT UNIQUE NOT NULL, command_json TEXT NOT NULL, command_hash TEXT NOT NULL,
        fingerprint TEXT NOT NULL
    )""")


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


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
        raise SwimImportError("storage_unavailable", 503) from exc
    except Exception:
        if conn is not None:
            conn.rollback()
        raise
    finally:
        if conn is not None:
            conn.close()


def _meta(conn: sqlite3.Connection, import_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM swim_import_sources WHERE import_id=?", (import_id,)
    ).fetchone()
    if row is None:
        raise SwimImportError("not_found", 404)
    try:
        value = dict(row)
        metadata_hash = value.pop("metadata_hash")
        command = CaptureSource.model_validate_json(row["command_json"])
        for key in ("import_id", "program_id", "request_id"):
            if str(UUID(row[key])) != row[key]:
                raise ValueError("noncanonical UUID")
        library._parse_time(row["created_at"])
        if (
            metadata_hash != _hash(value)
            or row["source_sha256"]
            != hashlib.sha256(row["source_text"].encode()).hexdigest()
            or str(command.request_id) != row["request_id"]
            or any(
                getattr(command, k) != row[k]
                for k in ("source_text", "source_label", "source_week_label")
            )
        ):
            raise ValueError("source metadata mismatch")
        return dict(row)
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise SwimImportError("corrupt", 503) from exc


def _state(
    conn: sqlite3.Connection, import_id: str, revision: int | None = None
) -> dict[str, Any]:
    meta = _meta(conn, import_id)
    if revision is None:
        row = conn.execute(
            "SELECT * FROM swim_import_revisions WHERE import_id=? ORDER BY revision DESC LIMIT 1",
            (import_id,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM swim_import_revisions WHERE import_id=? AND revision=?",
            (import_id, revision),
        ).fetchone()
    if row is None:
        raise SwimImportError(
            "corrupt" if revision is None else "not_found",
            503 if revision is None else 404,
        )
    try:
        acknowledgements = [
            a.model_dump(mode="json")
            for a in ACKS.validate_json(row["acknowledgements_json"])
        ]
        if len(acknowledgements) > 1000 or any(
            a["span"]["end"] > len(meta["source_text"]) for a in acknowledgements
        ):
            raise ValueError("invalid acknowledgement")
        command = json.loads(row["command_json"])
        if (
            row["actor"] not in ("user", "coach")
            or _hash(command) != row["command_hash"]
            or command["actor"] != row["actor"]
        ):
            raise ValueError("invalid command receipt")
        request_model = (
            CaptureSource
            if row["revision"] == 0
            else (ParseDraft if row["revision"] == 1 else PatchDraft)
        )
        retained_request = request_model.model_validate(command["request"])
        if str(retained_request.request_id) != row["request_id"] or (
            row["revision"] > 0
            and retained_request.expected_revision != row["revision"] - 1
        ):
            raise ValueError("invalid command identity")
        library._parse_time(row["created_at"])
        if row["revision"] == 0:
            if (
                row["document_json"] is not None
                or row["summary_json"] is not None
                or acknowledgements
                or row["actor"] != "user"
                or retained_request.model_dump(mode="json")
                != json.loads(meta["command_json"])
            ):
                raise ValueError("invalid unparsed revision")
            document, summary = None, None
        else:
            model = SwimProgramDocumentV2.model_validate_json(row["document_json"])
            document, summary = model.model_dump(mode="json"), summarize_document(model)
            expected_source = {
                "source_id": meta["import_id"],
                "id": meta["program_id"],
                "source_text": meta["source_text"],
                "source_sha256": meta["source_sha256"],
                "source_label": meta["source_label"],
                "source_week_label": meta["source_week_label"],
            }
            if (
                any(document[key] != value for key, value in expected_source.items())
                or canonical_json(summary) != row["summary_json"]
            ):
                raise ValueError("draft source or summary mismatch")
        if (
            _hash({"document": document, "acknowledgements": acknowledgements})
            != row["fingerprint"]
        ):
            raise ValueError("draft fingerprint mismatch")
        return {
            "import_id": import_id,
            "program_id": meta["program_id"],
            "source_text": meta["source_text"],
            "source_sha256": meta["source_sha256"],
            "source_label": meta["source_label"],
            "source_week_label": meta["source_week_label"],
            "revision": row["revision"],
            "document": document,
            "summary": summary,
            "acknowledgements": acknowledgements,
            "fingerprint": row["fingerprint"],
            "actor": row["actor"],
            "updated_at": row["created_at"],
        }
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise SwimImportError("corrupt", 503) from exc


def _command(request: Any, actor: Actor) -> dict[str, Any]:
    if actor not in ("user", "coach"):
        raise SwimImportError("invalid_actor", 422)
    return {"actor": actor, "request": request.model_dump(mode="json")}


def _replay(
    conn: sqlite3.Connection, import_id: str, request: Any, actor: Actor
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM swim_import_revisions WHERE request_id=?",
        (str(request.request_id),),
    ).fetchone()
    if row is None:
        return None
    result = _state(conn, row["import_id"], row["revision"])
    if row["import_id"] != import_id or _command(request, actor) != json.loads(
        row["command_json"]
    ):
        raise SwimImportError("request_conflict")
    return result


def _append(
    conn: sqlite3.Connection,
    import_id: str,
    revision: int,
    request: Any,
    actor: Actor,
    document: dict[str, Any] | None,
    acknowledgements: list[dict[str, Any]],
) -> dict[str, Any]:
    command = _command(request, actor)
    model = (
        SwimProgramDocumentV2.model_validate(document) if document is not None else None
    )
    canonical = model.model_dump(mode="json") if model is not None else None
    summary = summarize_document(model) if model is not None else None
    if len(acknowledgements) > 1000:
        raise SwimImportError("acknowledgement_limit", 422)
    conn.execute(
        """INSERT INTO swim_import_revisions
        (import_id,revision,request_id,command_json,command_hash,actor,document_json,summary_json,acknowledgements_json,fingerprint,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            import_id,
            revision,
            str(request.request_id),
            canonical_json(command),
            _hash(command),
            actor,
            canonical_json(canonical) if canonical is not None else None,
            canonical_json(summary) if summary is not None else None,
            canonical_json(acknowledgements),
            _hash({"document": canonical, "acknowledgements": acknowledgements}),
            library._instant(None).isoformat(),
        ),
    )
    return _state(conn, import_id, revision)


def capture(db: Any, request: CaptureSource) -> dict[str, Any]:
    with _connection(db, write=True) as conn:
        existing = conn.execute(
            "SELECT import_id FROM swim_import_sources WHERE request_id=?",
            (str(request.request_id),),
        ).fetchone()
        if existing is not None:
            result = _replay(conn, existing["import_id"], request, "user")
            if result is None:
                raise SwimImportError("corrupt", 503)
            return result
        if conn.execute(
            "SELECT 1 FROM swim_import_revisions WHERE request_id=?",
            (str(request.request_id),),
        ).fetchone():
            raise SwimImportError("request_conflict")
        meta = {
            "import_id": str(uuid4()),
            "program_id": str(uuid4()),
            "request_id": str(request.request_id),
            "source_text": request.source_text,
            "source_sha256": hashlib.sha256(request.source_text.encode()).hexdigest(),
            "source_label": request.source_label,
            "source_week_label": request.source_week_label,
            "command_json": canonical_json(request.model_dump(mode="json")),
            "created_at": library._instant(None).isoformat(),
        }
        conn.execute(
            """INSERT INTO swim_import_sources
            (import_id,program_id,request_id,source_text,source_sha256,source_label,source_week_label,command_json,created_at,metadata_hash)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (*meta.values(), _hash(meta)),
        )
        return _append(conn, meta["import_id"], 0, request, "user", None, [])


def _binding(conn: sqlite3.Connection, reference: Any) -> dict[str, Any]:
    row = exercises._row(conn, str(reference.exercise_id), reference.revision)
    if row is None:
        raise SwimImportError("exercise_not_found", 404)
    try:
        version = exercises._validated(row)
    except exercises.SwimExerciseError as exc:
        raise SwimImportError("exercise_corrupt", 503) from exc
    return {
        "node_id": reference.node_id,
        "exercise_id": version["exercise_id"],
        "revision": version["revision"],
        "fingerprint": version["fingerprint"],
        "document": version["document"],
    }


def parse(
    db: Any, import_id: str, request: ParseDraft, *, actor: Actor
) -> dict[str, Any]:
    with _connection(db, write=True) as conn:
        replay = _replay(conn, import_id, request, actor)
        if replay is not None:
            return replay
        current = _state(conn, import_id)
        if current["revision"] != request.expected_revision:
            raise SwimImportError("stale")
        if current["document"] is not None:
            raise SwimImportError("already_parsed")
        content = request.content.model_dump(
            mode="json", exclude={"exercise_references"}
        )
        document = {
            **content,
            "schema_version": 2,
            "origin": "trainer_authored",
            "id": current["program_id"],
            "source_id": import_id,
            **{
                key: current[key]
                for key in (
                    "source_text",
                    "source_sha256",
                    "source_label",
                    "source_week_label",
                )
            },
            "exercise_bindings": [
                _binding(conn, ref) for ref in request.content.exercise_references
            ],
        }
        try:
            return _append(
                conn, import_id, current["revision"] + 1, request, actor, document, []
            )
        except ValidationError as exc:
            raise SwimImportError("invalid_document", 422) from exc


def _nodes(
    document: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, tuple[list, int]]]:
    nodes, parents = {}, {}

    def visit(part: dict[str, Any]) -> None:
        nodes[part["id"]] = part
        for index, child in enumerate(part.get("steps", [])):
            parents[child["id"]] = (part["steps"], index)
            visit(child)

    for workout in document["workouts"]:
        visit(workout)
    return nodes, parents


def _edit(
    conn: sqlite3.Connection, current: dict[str, Any], operation: Any, actor: Actor
) -> tuple[dict[str, Any], list]:
    document, acknowledgements = (
        deepcopy(current["document"]),
        deepcopy(current["acknowledgements"]),
    )
    if document is None:
        raise SwimImportError("not_parsed")
    nodes, parents = _nodes(document)
    op = operation.model_dump(mode="json")
    kind = op.pop("op")
    node_id = op.pop("node_id", None)
    node = nodes.get(node_id)
    if node_id is not None and node is None:
        raise SwimImportError("node_not_found", 404)
    if kind == "acknowledge_source":
        if actor != "user":
            raise SwimImportError("human_required", 403)
        if op["span"]["end"] > len(current["source_text"]):
            raise SwimImportError("invalid_span", 422)
        if op not in acknowledgements:
            acknowledgements.append(op)
    elif kind == "set_title":
        target = (
            document
            if op["workout_id"] is None
            else next(
                (w for w in document["workouts"] if w["id"] == op["workout_id"]), None
            )
        )
        if target is None:
            raise SwimImportError("workout_not_found", 404)
        target["title"] = op["title"]
    elif kind == "set_context":
        target = next(
            (w for w in document["workouts"] if w["id"] == op["workout_id"]), None
        )
        if target is None:
            raise SwimImportError("workout_not_found", 404)
        target.update({key: op[key] for key in ("environment", "pool_length_meters")})
    elif kind == "set_binding":
        if node.get("kind") != "swim" or (
            operation.reference is not None and operation.reference.node_id != node_id
        ):
            raise SwimImportError("invalid_target", 422)
        document["exercise_bindings"] = [
            b for b in document["exercise_bindings"] if b["node_id"] != node_id
        ]
        if operation.reference is not None:
            document["exercise_bindings"].append(_binding(conn, operation.reference))
    elif kind in ("set_rest", "set_quantity", "set_repeat", "set_instructions"):
        required = {
            "set_rest": "rest",
            "set_quantity": "swim",
            "set_repeat": "group",
        }.get(kind)
        if (
            required is not None and node.get("kind") != required
        ) or "kind" not in node:
            raise SwimImportError("invalid_target", 422)
        node.update(op)
    elif kind in (
        "replace_node",
        "resolve_node",
        "remove_node",
        "move_node",
        "add_node",
    ):
        if kind != "add_node" and node_id not in parents:
            raise SwimImportError("invalid_target", 422)
        if kind == "resolve_node" and node.get("kind") != "unresolved":
            raise SwimImportError("invalid_target", 422)
        if kind in ("add_node", "move_node"):
            target = nodes.get(op["parent_id"])
            if target is None or "steps" not in target:
                raise SwimImportError("invalid_parent", 422)
            if kind == "move_node":
                descendants, _ = _nodes({"workouts": [node]})
                if op["parent_id"] in descendants:
                    raise SwimImportError("invalid_parent", 422)
                source, index = parents[node_id]
                source.pop(index)
            if op["index"] > len(target["steps"]):
                raise SwimImportError("invalid_index", 422)
            target["steps"].insert(
                op["index"], node if kind == "move_node" else op["node"]
            )
        else:
            source, index = parents[node_id]
            if kind == "remove_node":
                source.pop(index)
            else:
                if op["node"]["id"] != node_id:
                    raise SwimImportError("identity_change", 422)
                source[index] = op["node"]
        # Removed/replaced subtrees cannot leave bindings pointing to absent/non-swim IDs.
        remaining, _ = _nodes(document)
        document["exercise_bindings"] = [
            b
            for b in document["exercise_bindings"]
            if remaining.get(b["node_id"], {}).get("kind") == "swim"
        ]
    else:
        raise SwimImportError("invalid_operation", 422)
    return document, acknowledgements


def patch(
    db: Any, import_id: str, request: PatchDraft, *, actor: Actor
) -> dict[str, Any]:
    with _connection(db, write=True) as conn:
        replay = _replay(conn, import_id, request, actor)
        if replay is not None:
            return replay
        current = _state(conn, import_id)
        if current["revision"] != request.expected_revision:
            raise SwimImportError("stale")
        document, acknowledgements = _edit(conn, current, request.operation, actor)
        try:
            return _append(
                conn,
                import_id,
                current["revision"] + 1,
                request,
                actor,
                document,
                acknowledgements,
            )
        except ValidationError as exc:
            raise SwimImportError("invalid_document", 422) from exc


def _ready(draft: dict[str, Any]) -> None:
    if draft["document"] is None:
        raise SwimImportError("not_ready", 422)
    summary = draft["summary"]
    if any(
        w["code"] in ("unresolved_source", "exercise_environment_mismatch")
        for w in summary["warnings"]
    ):
        raise SwimImportError("not_ready", 422)
    # Every non-whitespace uncovered code point must be acknowledged by a human.
    text = draft["source_text"]
    for gap in summary["source_gaps"]:
        covered = bytearray(gap["end"] - gap["start"])
        for acknowledgement in draft["acknowledgements"]:
            span = acknowledgement["span"]
            start, end = max(gap["start"], span["start"]), min(gap["end"], span["end"])
            if end > start:
                covered[start - gap["start"] : end - gap["start"]] = b"\x01" * (
                    end - start
                )
        if any(
            not flag and not char.isspace()
            for char, flag in zip(text[gap["start"] : gap["end"]], covered)
        ):
            raise SwimImportError("not_ready", 422)


def _prepared(conn: sqlite3.Connection, binding: sqlite3.Row) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM swim_program_previews WHERE preview_id=?",
        (binding["preview_id"],),
    ).fetchone()
    if row is None:
        raise SwimImportError("corrupt", 503)
    document, summary = library._validated(row)
    try:
        command = PrepareDraft.model_validate_json(binding["command_json"])
        if (
            _hash(command.model_dump(mode="json")) != binding["command_hash"]
            or str(command.request_id) != binding["request_id"]
            or command.draft_revision != binding["draft_revision"]
            or command.base_library_revision != row["base_revision"]
            or binding["fingerprint"] != row["fingerprint"]
        ):
            raise ValueError("preview binding mismatch")
        library._parse_time(row["expires_at"])
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise SwimImportError("corrupt", 503) from exc
    return {
        "preview_id": row["preview_id"],
        "base_revision": row["base_revision"],
        "document": document,
        "summary": summary,
        "fingerprint": row["fingerprint"],
        "expires_at": row["expires_at"],
        "import_id": binding["import_id"],
        "draft_revision": binding["draft_revision"],
    }


def prepare(
    db: Any, import_id: str, request: PrepareDraft, *, now: datetime | None = None
) -> dict[str, Any]:
    with _connection(db, write=True) as conn:
        receipt = conn.execute(
            "SELECT * FROM swim_import_previews WHERE request_id=?",
            (str(request.request_id),),
        ).fetchone()
        if receipt is not None:
            result = _prepared(conn, receipt)
            if receipt["import_id"] != import_id or request.model_dump(
                mode="json"
            ) != json.loads(receipt["command_json"]):
                raise SwimImportError("request_conflict")
            return result
        current = _state(conn, import_id)
        if current["revision"] != request.draft_revision:
            raise SwimImportError("stale")
        _ready(current)
        model = SwimProgramDocumentV2.model_validate(current["document"])
        preview = library._create_preview(
            conn,
            model,
            base_revision=request.base_library_revision,
            instant=library._instant(now),
        )
        command = request.model_dump(mode="json")
        conn.execute(
            """INSERT INTO swim_import_previews
            (preview_id,import_id,draft_revision,request_id,command_json,command_hash,fingerprint)
            VALUES (?,?,?,?,?,?,?)""",
            (
                preview["preview_id"],
                import_id,
                request.draft_revision,
                str(request.request_id),
                canonical_json(command),
                _hash(command),
                preview["fingerprint"],
            ),
        )
        return {
            **preview,
            "import_id": import_id,
            "draft_revision": request.draft_revision,
        }


def validate_confirmation_binding(
    conn: sqlite3.Connection, preview: sqlite3.Row
) -> None:
    """Runs inside the common library writer transaction, including applied retries."""
    try:
        binding = conn.execute(
            "SELECT * FROM swim_import_previews WHERE preview_id=?",
            (preview["preview_id"],),
        ).fetchone()
        if binding is None:
            raise SwimImportError("corrupt", 503)
        prepared = _prepared(conn, binding)
        historical = _state(conn, binding["import_id"], binding["draft_revision"])
        _ready(historical)
        if (
            historical["document"] != prepared["document"]
            or fingerprint_program(
                SwimProgramDocumentV2.model_validate(historical["document"])
            )
            != binding["fingerprint"]
        ):
            raise SwimImportError("corrupt", 503)
        if (
            preview["applied_revision"] is None
            and _state(conn, binding["import_id"])["revision"]
            != binding["draft_revision"]
        ):
            raise SwimImportError("stale")
    except SwimImportError as exc:
        # Missing referenced source/history is corruption, not a disappeared public resource.
        status = (
            503
            if exc.status == 404 or exc.code == "swim_import_not_ready"
            else exc.status
        )
        raise library.SwimProgramError(
            "swim_import_corrupt" if status == 503 else exc.code, status
        ) from exc


def get_draft(
    db: Any, import_id: str, *, revision: int | None = None
) -> dict[str, Any]:
    with _connection(db) as conn:
        return _state(conn, import_id, revision)


def list_drafts(db: Any) -> list[dict[str, Any]]:
    with _connection(db) as conn:
        return [
            _state(conn, row[0])
            for row in conn.execute(
                "SELECT import_id FROM swim_import_sources ORDER BY created_at DESC,import_id"
            ).fetchall()
        ]
