"""Source retention, bounded edits and the common human-confirmation boundary."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
import sqlite3
from uuid import uuid4

import pytest

from data.database import Database
from data import swim_import_store as store
from data import swim_program_store as library
from data import swim_exercise_store as catalog
from models.swim_import import CaptureSource, ParseDraft, PatchDraft, PrepareDraft
from models.swim_exercise import SwimExerciseDocument, exercise_fingerprint
from tests.smoke._swim_import_fixtures import SOURCE, rich_program
from tests.smoke.test_swim_exercise import definition
from tests.smoke.test_swim_program_store import NOW

pytestmark = pytest.mark.smoke


def request_id():
    return str(uuid4())


def content():
    raw = rich_program()
    return {key: deepcopy(raw[key]) for key in ("title", "source_spans", "workouts")}


def capture(db, text=SOURCE):
    return store.capture(db, CaptureSource(source_text=text, request_id=request_id()))


def parse(db, draft, **overrides):
    return store.parse(
        db,
        draft["import_id"],
        ParseDraft(
            expected_revision=draft["revision"],
            request_id=request_id(),
            content={**content(), **overrides},
        ),
        actor="user",
    )


def patch(db, draft, operation):
    return store.patch(
        db,
        draft["import_id"],
        PatchDraft(
            expected_revision=draft["revision"],
            request_id=request_id(),
            operation=operation,
        ),
        actor="user",
    )


def prepare(db, draft, base=0):
    return store.prepare(
        db,
        draft["import_id"],
        PrepareDraft(
            draft_revision=draft["revision"],
            base_library_revision=base,
            request_id=request_id(),
        ),
        now=NOW,
    )


def test_empty_source_survives_restart_and_capture_replay(tmp_path):
    db = Database(str(tmp_path / "source.sqlite"))
    command = CaptureSource(source_text="  🏊 Original\n\n", request_id=request_id())
    original = store.capture(db, command)
    assert original["revision"] == 0 and original["document"] is None
    assert original["source_text"] == command.source_text
    assert store.capture(Database(db.db_path), command) == original
    assert store.get_draft(db, original["import_id"]) == original
    changed = command.model_copy(update={"source_text": "changed"})
    with pytest.raises(store.SwimImportError, match="request_conflict"):
        store.capture(db, changed)
    assert len(store.list_drafts(db)) == 1


def test_parse_once_bounded_pause_edit_and_historical_readback(tmp_path):
    db = Database(str(tmp_path / "draft.sqlite"))
    empty = capture(db)
    raw = content()
    raw["workouts"][0]["steps"].append(
        {
            "kind": "rest",
            "id": "pause",
            "mode": "approximate",
            "seconds": {"minimum": 60, "maximum": 70},
        }
    )
    draft = parse(db, empty, **raw)
    original = deepcopy(draft["document"])
    command = PatchDraft(
        expected_revision=1,
        request_id=request_id(),
        operation={
            "op": "set_rest",
            "node_id": "pause",
            "mode": "fixed",
            "seconds": {"minimum": 90, "maximum": 90},
        },
    )
    changed = store.patch(db, empty["import_id"], command, actor="user")
    expected = deepcopy(original)
    expected["workouts"][0]["steps"][-1].update(
        mode="fixed", seconds={"minimum": 90, "maximum": 90}
    )
    assert changed["document"] == expected
    assert changed["revision"] == 2
    assert store.patch(db, empty["import_id"], command, actor="user") == changed
    assert (
        store.get_draft(Database(db.db_path), empty["import_id"], revision=1)[
            "document"
        ]
        == original
    )
    with pytest.raises(store.SwimImportError, match="already_parsed"):
        parse(db, changed)
    with pytest.raises(store.SwimImportError, match="stale"):
        patch(db, draft, {"op": "set_title", "title": "Stale"})
    with pytest.raises(store.SwimImportError, match="request_conflict"):
        store.patch(
            db,
            empty["import_id"],
            command.model_copy(update={"expected_revision": 2}),
            actor="user",
        )


def test_generic_confirm_rejects_stale_import_and_applied_replay_is_stable(tmp_path):
    db = Database(str(tmp_path / "stale.sqlite"))
    draft = parse(db, capture(db))
    first = prepare(db, draft)
    changed = patch(db, draft, {"op": "set_title", "title": "Reviewed edit"})
    with pytest.raises(library.SwimProgramError, match="swim_import_stale"):
        library.confirm_preview(db, first["preview_id"], now=NOW)
    current = prepare(db, changed)
    saved = library.confirm_preview(db, current["preview_id"], now=NOW)
    assert saved["document"] == changed["document"]
    assert saved["summary"]["distance_meters"] is None
    assert library.get_version(Database(db.db_path), saved["program_id"]) == saved
    later = patch(db, changed, {"op": "set_title", "title": "Later draft"})
    second = prepare(db, later, base=1)
    library.confirm_preview(db, second["preview_id"], now=NOW)
    assert (
        library.confirm_preview(db, current["preview_id"], now=NOW + timedelta(days=10))
        == saved
    )
    assert library.list_programs(db)[0]["schema_version"] == 2


def test_exact_exercise_revision_is_snapshotted_without_prescription_inheritance(
    tmp_path,
):
    db = Database(str(tmp_path / "exercise.sqlite"))
    document = SwimExerciseDocument.model_validate(definition())
    catalog.confirm(
        db,
        document,
        base_revision=0,
        request_id=request_id(),
        fingerprint=exercise_fingerprint(document),
    )
    draft = parse(
        db,
        capture(db),
        exercise_references=[
            {"node_id": "one.fixed", "exercise_id": str(document.id), "revision": 1}
        ],
    )
    before = deepcopy(draft["document"])
    document.instructions = "A newer catalog version"
    catalog.confirm(
        db,
        document,
        base_revision=1,
        request_id=request_id(),
        fingerprint=exercise_fingerprint(document),
    )
    assert draft["document"]["workouts"][0]["steps"][0]["equipment"] == []
    assert (
        draft["document"]["exercise_bindings"][0]["document"]["instructions"]
        == "Keep original instruction."
    )
    saved = library.confirm_preview(db, prepare(db, draft)["preview_id"], now=NOW)
    assert saved["document"] == before
    with db._connect() as conn:
        conn.execute("DELETE FROM swim_exercise_versions")
    assert library.get_version(db, saved["program_id"]) == saved
    incompatible = patch(
        db,
        draft,
        {"op": "set_context", "workout_id": "one", "environment": "open_water"},
    )
    with pytest.raises(store.SwimImportError, match="not_ready"):
        prepare(db, incompatible, base=1)


def test_unresolved_and_source_gaps_need_explicit_resolution(tmp_path):
    db = Database(str(tmp_path / "coverage.sqlite"))
    raw = content()
    raw["source_spans"] = []
    raw["workouts"][0]["steps"] = [
        {
            "kind": "unresolved",
            "id": "unknown",
            "instructions": "Original retained",
            "question": "Which dose?",
        }
    ]
    draft = parse(db, capture(db), **raw)
    with pytest.raises(store.SwimImportError, match="not_ready"):
        prepare(db, draft)
    resolved = patch(
        db,
        draft,
        {
            "op": "resolve_node",
            "node_id": "unknown",
            "node": {
                "kind": "swim",
                "id": "unknown",
                "name": "Skill",
                "quantity": {"kind": "open"},
            },
        },
    )
    with pytest.raises(store.SwimImportError, match="not_ready"):
        prepare(db, resolved)
    operation = {
        "op": "acknowledge_source",
        "span": {"start": 0, "end": len(SOURCE)},
        "reason": "Reviewed heading",
    }
    command = PatchDraft(
        expected_revision=resolved["revision"],
        request_id=request_id(),
        operation=operation,
    )
    with pytest.raises(store.SwimImportError, match="human_required"):
        store.patch(db, resolved["import_id"], command, actor="coach")
    ready = store.patch(db, resolved["import_id"], command, actor="user")
    assert (
        library.confirm_preview(db, prepare(db, ready)["preview_id"], now=NOW)[
            "revision"
        ]
        == 1
    )


def test_revision_race_one_winner_and_preview_binding_rollback(tmp_path):
    db = Database(str(tmp_path / "race.sqlite"))
    draft = parse(db, capture(db))

    def edit(title):
        try:
            return patch(db, draft, {"op": "set_title", "title": title})["revision"]
        except store.SwimImportError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(map(str, pool.map(edit, ["A", "B"]))) == [
            "2",
            "swim_import_stale",
        ]
    conn = db._connect()
    try:
        conn.execute(
            "CREATE TRIGGER fail_binding BEFORE INSERT ON swim_import_previews BEGIN SELECT RAISE(ABORT,'synthetic'); END"
        )
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(store.SwimImportError):
        prepare(db, store.get_draft(db, draft["import_id"]))
    conn = db._connect()
    try:
        assert (
            conn.execute("SELECT COUNT(*) FROM swim_program_previews").fetchone()[0]
            == 0
        )
    finally:
        conn.close()


@pytest.mark.parametrize("kind", ["source", "draft", "binding"])
def test_corruption_fails_closed_without_fallback(tmp_path, kind):
    db = Database(str(tmp_path / "corrupt.sqlite"))
    draft = parse(db, capture(db))
    preview = prepare(db, draft)
    conn = db._connect()
    try:
        if kind == "source":
            conn.execute("UPDATE swim_import_sources SET source_text='PRIVATE_CANARY'")
        elif kind == "draft":
            conn.execute(
                "UPDATE swim_import_revisions SET document_json='{}' WHERE revision=1"
            )
        else:
            conn.execute("DELETE FROM swim_import_previews")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(library.SwimProgramError) as error:
        library.confirm_preview(db, preview["preview_id"], now=NOW)
    assert error.value.status == 503 and "PRIVATE_CANARY" not in str(error.value)
    assert library.list_programs(db) == []


def test_backup_restore_and_full_reset_include_every_import_table(tmp_path):
    db = Database(str(tmp_path / "restore.sqlite"))
    draft = parse(db, capture(db))
    preview = prepare(db, draft)
    saved = library.confirm_preview(db, preview["preview_id"], now=NOW)
    snapshot = tmp_path / "snapshot.sqlite"
    source, target = db._connect(), sqlite3.connect(snapshot)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    restored = Database(str(snapshot))
    assert store.get_draft(restored, draft["import_id"]) == draft
    assert library.confirm_preview(restored, preview["preview_id"], now=NOW) == saved
    db.clear_all_data()
    assert store.list_drafts(db) == []
    conn = db._connect()
    try:
        for table in (
            "swim_import_sources",
            "swim_import_revisions",
            "swim_import_previews",
        ):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    finally:
        conn.close()
    assert library.get_version(restored, saved["program_id"]) == saved


def test_preview_request_replay_after_edit_returns_original_token(tmp_path):
    db = Database(str(tmp_path / "preview.sqlite"))
    draft = parse(db, capture(db))
    command = PrepareDraft(
        draft_revision=1, base_library_revision=0, request_id=request_id()
    )
    preview = store.prepare(db, draft["import_id"], command, now=NOW)
    patch(db, draft, {"op": "set_title", "title": "Another title"})
    assert store.prepare(db, draft["import_id"], command, now=NOW) == preview
    with pytest.raises(library.SwimProgramError, match="swim_import_stale"):
        library.confirm_preview(db, preview["preview_id"], now=NOW)


def test_structural_edits_preserve_source_and_reject_cycles_and_roots(tmp_path):
    db = Database(str(tmp_path / "structure.sqlite"))
    draft = parse(db, capture(db))
    added = patch(
        db,
        draft,
        {
            "op": "add_node",
            "parent_id": "one.timed",
            "index": 1,
            "node": {
                "kind": "rest",
                "id": "new.pause",
                "mode": "open",
                "breaths": {"minimum": 3, "maximum": 4},
            },
        },
    )
    moved = patch(
        db,
        added,
        {"op": "move_node", "node_id": "new.pause", "parent_id": "one", "index": 2},
    )
    assert moved["document"]["workouts"][0]["steps"][-1]["id"] == "new.pause"
    assert moved["document"]["source_text"] == SOURCE
    for operation in [
        {
            "op": "move_node",
            "node_id": "one.timed",
            "parent_id": "one.timed",
            "index": 0,
        },
        {"op": "remove_node", "node_id": "one"},
        {"op": "set_rest", "node_id": "one.fixed", "mode": "open"},
        {
            "op": "resolve_node",
            "node_id": "one.fixed",
            "node": {
                "kind": "swim",
                "id": "one.fixed",
                "name": "X",
                "quantity": {"kind": "open"},
            },
        },
    ]:
        with pytest.raises(store.SwimImportError):
            patch(db, moved, operation)
        assert store.get_draft(db, draft["import_id"]) == moved
    removed = patch(db, moved, {"op": "remove_node", "node_id": "new.pause"})
    assert removed["document"] == draft["document"]


def test_retained_command_actor_tamper_is_corruption(tmp_path):
    db = Database(str(tmp_path / "actor.sqlite"))
    draft = parse(db, capture(db))
    with db._connect() as conn:
        conn.execute("UPDATE swim_import_revisions SET actor='coach' WHERE revision=1")
    with pytest.raises(store.SwimImportError, match="corrupt"):
        store.get_draft(db, draft["import_id"])


def test_source_capture_failure_and_version_failure_leave_no_partial_rows(tmp_path):
    db = Database(str(tmp_path / "atomic.sqlite"))
    with db._connect() as conn:
        conn.execute(
            "CREATE TRIGGER fail_revision BEFORE INSERT ON swim_import_revisions BEGIN SELECT RAISE(ABORT,'synthetic'); END"
        )
    with pytest.raises(store.SwimImportError):
        capture(db)
    assert store.list_drafts(db) == []
    with db._connect() as conn:
        conn.execute("DROP TRIGGER fail_revision")
    draft = parse(db, capture(db))
    preview = prepare(db, draft)
    with db._connect() as conn:
        conn.execute(
            "CREATE TRIGGER fail_receipt BEFORE UPDATE ON swim_program_previews BEGIN SELECT RAISE(ABORT,'synthetic'); END"
        )
    with pytest.raises(library.SwimProgramError):
        library.confirm_preview(db, preview["preview_id"], now=NOW)
    assert library.list_programs(db) == []
    assert store.get_draft(db, draft["import_id"]) == draft
    with db._connect() as conn:
        conn.execute("DROP TRIGGER fail_receipt")
    assert library.confirm_preview(db, preview["preview_id"], now=NOW)["revision"] == 1


def test_confirm_snapshot_observes_complete_import_and_replay_does_not_repeat(
    tmp_path, monkeypatch
):
    from config.settings import Settings
    from services import snapshot_runtime as runtime
    from services.swim_programs import confirm

    db = Database(str(tmp_path / "snapshot-commit.sqlite"))
    monkeypatch.setattr(Settings, "AUTO_BACKUP_ENABLED", True)
    monkeypatch.setattr(Settings, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(Settings, "DATABASE_PATH", db.db_path)
    monkeypatch.setattr(Settings, "ACCEPTANCE_MODE", False)
    runtime.reset_for_tests()
    calls = []

    def check(*args):
        reopened = Database(db.db_path)
        calls.append(
            (
                store.get_draft(reopened, draft["import_id"]),
                library.get_version(reopened, draft["program_id"]),
            )
        )
        return runtime.empty_status("degraded", "backup_io_error")

    monkeypatch.setattr(runtime, "check_snapshot", check)
    try:
        draft = parse(db, capture(db))
        preview = store.prepare(
            db,
            draft["import_id"],
            PrepareDraft(
                draft_revision=1, base_library_revision=0, request_id=request_id()
            ),
        )
        assert not calls
        saved = confirm(db, preview["preview_id"])
        assert calls == [(draft, saved)]
        assert confirm(db, preview["preview_id"]) == saved and calls == [(draft, saved)]
    finally:
        runtime.reset_for_tests()
