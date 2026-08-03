"""BDD acceptance gates for UI beta v2 M2 (#266): Coach dialog lifecycle.

Chats become manageable: rename, search, archive, restore and safe delete,
with backward-compatible legacy JSON, strict chat-id validation (no path
traversal), explicit 404/422 contracts, and lifecycle UI in the Coach page.
Tests use a temporary CHATS_DIR and no live AI provider.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from config.settings import Settings
from models.chat_manager import ChatManager
from api.routers import coach as coach_router


pytestmark = pytest.mark.smoke
REPO_ROOT = Path(__file__).resolve().parents[2]
PAGE = REPO_ROOT / "web/app/coach/page.tsx"
TYPES = REPO_ROOT / "web/lib/types.ts"
API = REPO_ROOT / "web/lib/api.ts"


@pytest.fixture()
def manager(tmp_path, monkeypatch):
    chats_dir = tmp_path / "chats"
    monkeypatch.setattr(Settings, "CHATS_DIR", str(chats_dir))
    return ChatManager()


def _chat(manager: ChatManager, title: str = "Чат", messages: int = 2) -> str:
    chat_id = manager.create_new_chat(title)
    for index in range(messages):
        manager.add_message(chat_id, "user", f"сообщение {index}")
    return chat_id


def test_legacy_json_without_archive_field_is_active(manager):
    chat_id = _chat(manager)
    raw = manager.load_chat(chat_id)
    assert "archived" not in raw

    items = manager.get_chat_list(scope="active")

    assert [item["id"] for item in items] == [chat_id]
    assert items[0]["archived"] is False
    assert manager.get_chat_messages(chat_id) == raw["messages"]


def test_archive_restore_preserves_messages_and_timestamps(manager):
    chat_id = _chat(manager, messages=3)
    messages_before = manager.get_chat_messages(chat_id)

    assert manager.set_archived(chat_id, True) is True
    assert [item["id"] for item in manager.get_chat_list(scope="active")] == []
    archived = manager.get_chat_list(scope="archive")
    assert [item["id"] for item in archived] == [chat_id]
    assert archived[0]["archived"] is True
    assert manager.get_chat_messages(chat_id) == messages_before

    assert manager.set_archived(chat_id, False) is True
    assert [item["id"] for item in manager.get_chat_list(scope="active")] == [chat_id]
    assert manager.get_chat_messages(chat_id) == messages_before


def test_rename_validates_and_persists(manager):
    chat_id = _chat(manager)

    assert manager.update_chat_title(chat_id, "  Новое имя  ") is True
    assert manager.load_chat(chat_id)["title"] == "Новое имя"
    with pytest.raises(ValueError):
        manager.update_chat_title(chat_id, "   ")
    with pytest.raises(ValueError):
        manager.update_chat_title(chat_id, "x" * 121)


def test_chat_id_path_traversal_is_blocked(manager):
    _chat(manager)
    for bad_id in ("../escape", "a/b", "..", "x.json", ""):
        with pytest.raises(ValueError):
            manager.load_chat(bad_id)
        with pytest.raises(ValueError):
            manager.delete_chat(bad_id)
        with pytest.raises(ValueError):
            manager.set_archived(bad_id, True)
    assert not list(Path(manager.chats_dir).parent.glob("escape.json"))


def test_search_matches_title_and_messages(manager):
    intervals = _chat(manager, title="Интервалы")
    other = _chat(manager, title="Другой чат")
    manager.update_chat_title(intervals, "Интервалы")
    manager.update_chat_title(other, "Другой чат")

    by_title = manager.search_chats("интервалы")
    by_message = manager.search_chats("сообщение 0")

    assert [item["id"] for item in by_title] == [intervals]
    assert sorted(item["id"] for item in by_message) == sorted([intervals, other])


def test_coach_lifecycle_routes_registered():
    main = importlib.import_module("api.main")
    paths = set(main.app.openapi()["paths"].keys())

    assert {
        "/api/coach/history",
        "/api/coach/history/{chat_id}",
        "/api/coach/search",
        "/api/coach/chats/{chat_id}/rename",
        "/api/coach/chats/{chat_id}/archive",
        "/api/coach/chats/{chat_id}/restore",
        "/api/coach/chats/{chat_id}",
    } <= paths


def test_coach_rename_endpoint_contracts(manager):
    chat_id = _chat(manager)
    from fastapi import HTTPException

    result = coach_router.coach_chat_rename(chat_id, coach_router.ChatRenameRequest(title="Новое имя"))
    assert result["id"] == chat_id
    assert result["title"] == "Новое имя"
    assert manager.load_chat(chat_id)["title"] == "Новое имя"

    with pytest.raises(HTTPException) as exc:
        coach_router.coach_chat_rename("missing", coach_router.ChatRenameRequest(title="X"))
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        coach_router.coach_chat_rename(chat_id, coach_router.ChatRenameRequest(title="   "))
    assert exc.value.status_code == 422


def test_coach_archive_restore_delete_endpoints(manager):
    chat_id = _chat(manager)
    from fastapi import HTTPException

    assert coach_router.coach_chat_archive(chat_id)["archived"] is True
    assert coach_router.coach_chat_restore(chat_id)["archived"] is False
    assert coach_router.coach_chat_delete(chat_id)["deleted"] is True
    with pytest.raises(HTTPException) as exc:
        coach_router.coach_chat_delete(chat_id)
    assert exc.value.status_code == 404


def test_coach_planning_page_has_lifecycle_ui():
    page = PAGE.read_text(encoding="utf-8")
    types = TYPES.read_text(encoding="utf-8")
    api = API.read_text(encoding="utf-8")

    assert "/api/coach/search" in page
    assert "/api/coach/chats/" in page
    assert "Активные" in page and "Архив" in page
    assert "Переименовать" in page
    assert "Удалить" in page
    assert "archived" in types and "preview" in types
    assert "deleteJSON" in api


def test_coach_upcoming_workouts_lists_leaf_sessions(tmp_path):
    from datetime import datetime, timedelta

    from api import planning_service as ps
    from models.ai_tools import AITools
    from models.planning_checkpoints import (
        build_planning_checkpoint,
        restore_goal_plan_from_checkpoint,
    )
    from tests.smoke.test_api_planning import _seeded_db

    db = _seeded_db(tmp_path)
    event_date = (datetime.now().date() + timedelta(weeks=9)).isoformat()
    ps.build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=event_date,
        available_hours=12,
        persist=True,
    )
    goal_plan = restore_goal_plan_from_checkpoint(db.get_latest_planning_checkpoint())
    assert goal_plan is not None
    today = datetime.now().date()

    daily_plan = list(goal_plan["daily_plan"])
    templates = list(goal_plan["session_templates"])
    today_index = None
    for index, item in enumerate(daily_plan):
        dt = item[0]
        session_date = dt.date() if hasattr(dt, "date") else dt
        if session_date == today:
            today_index = index
            break
    assert today_index is not None, "plan must have a row for today"

    templates[today_index] = {
        "date": today.isoformat(),
        "sport": "brick",
        "sport_label": "вело → бег",
        "phase": "Base",
        "kind": "composite",
        "session_id": "composite-today",
        "sessions": [
            {
                "session_id": "leaf-bike",
                "sport": "bike",
                "sport_label": "вело",
                "total_tss": 60,
                "export_name": "Вело-интервалы",
                "template_name": "Вело",
                "kind": "single",
            },
            {
                "session_id": "leaf-run",
                "sport": "run",
                "sport_label": "бег",
                "total_tss": 40,
                "export_name": "Бег после вела",
                "template_name": "Бег",
                "kind": "single",
            },
        ],
    }
    daily_plan[today_index] = (today, 100.0, {"bike": 60.0, "run": 40.0})
    goal_plan["daily_plan"] = daily_plan
    goal_plan["session_templates"] = templates
    db.save_planning_checkpoint(build_planning_checkpoint(goal_plan))

    tools = AITools(db)
    result = tools.get_upcoming_workouts(days=0)

    today_sessions = [session for session in result["sessions"] if session["date"] == today.isoformat()]
    assert len(today_sessions) == 2
    assert {session["sport"] for session in today_sessions} == {"bike", "run"}
    assert {session["name"] for session in today_sessions} == {"Вело-интервалы", "Бег после вела"}


def test_coach_history_sidebar_scrolls_and_uses_compact_menu():
    page = PAGE.read_text(encoding="utf-8")

    assert "max-h-[calc(100vh-320px)]" in page
    assert "overflow-y-auto" in page
    assert "⋯" in page
    assert "defaultOpen" in page
    assert "aria-expanded={open}" in page
