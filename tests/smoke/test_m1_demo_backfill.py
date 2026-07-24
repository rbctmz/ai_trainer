"""M1 D6 gate — демо-поверхность живёт в provider-link модели (#270 §9 D6, §11 шаг 6).

Демо-сид (`services/demo_mode.activate_demo_mode`) пишет активности напрямую через
`database.save_activities`, минуя ingest — то есть до D6 демо-датасет был единственной
поверхностью БЕЗ provider-link'ов. Это ломало инвариант M0/M1 «каждая каноническая
активность покрыта хотя бы одной связью»: демо-режим вёл себя иначе, чем реальный синк,
и любой код, читающий связи (проекция, coexistence-резолвер, будущий M4/M5), видел
демо-данные как пустоту.

D6: после сидирования прогоняется офлайновый `backfill_provider_links`, который
классифицирует `demo_activity_*` как провайдер `demo` (ADR-0008 п.7,
`services/activity_ingest.classify_activity_id`).

Гейты:
  - M1-T9   : после активации демо каждая демо-активность покрыта РОВНО одной связью
              `demo`; ни одной `garmin`/`legacy_unknown`; нет осиротевших связей.
  - M1-T9b  : идемпотентность — повторная активация и повторный backfill не плодят
              связей; проекция не портит поля демо-активностей.
  - M1-T9c  : деактивация (clear_all_data) не оставляет осиротевших связей.
  - M1-T9d  : изоляция — сид и backfill трогают только свою БД.
"""
from __future__ import annotations

import sqlite3

import pytest

from data.database import Database
from services import demo_mode as demo_service
from services.activity_ingest import backfill_provider_links


pytestmark = pytest.mark.smoke


def _state_for(db: Database):
    from api.deps import make_headless_state

    return make_headless_state(database=db)


def _link_rows(db: Database) -> list[tuple]:
    conn = sqlite3.connect(db.db_path)
    rows = conn.execute(
        "SELECT canonical_activity_id, provider, provider_activity_id, external_provider,"
        " external_id, match_status FROM activity_provider_links"
        " ORDER BY canonical_activity_id"
    ).fetchall()
    conn.close()
    return rows


def _activity_rows(db: Database) -> dict[str, tuple]:
    conn = sqlite3.connect(db.db_path)
    rows = conn.execute(
        "SELECT activity_id, date, sport, duration_minutes, distance_km, tss FROM activities"
    ).fetchall()
    conn.close()
    return {row[0]: row for row in rows}


def _orphan_count(db: Database) -> int:
    conn = sqlite3.connect(db.db_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM activity_provider_links l "
        "LEFT JOIN activities a ON a.activity_id = l.canonical_activity_id "
        "WHERE a.activity_id IS NULL"
    ).fetchone()[0]
    conn.close()
    return count


def test_m1_t9_demo_seed_covers_every_activity_with_a_demo_link(tmp_path):
    """M1-T9: демо-сид оставляет каждую активность покрытой ровно одной связью `demo`."""
    db = Database(str(tmp_path / "demo.db"))

    counts = demo_service.activate_demo_mode(_state_for(db))

    activities = _activity_rows(db)
    assert counts["activities"] == len(activities) > 0

    links = _link_rows(db)
    assert len(links) == len(activities), "ровно одна связь на демо-активность"

    providers = {row[1] for row in links}
    assert providers == {"demo"}, f"демо-сид не должен порождать иных провайдеров: {providers}"

    for canonical_id, provider, provider_activity_id, external_provider, external_id, status in links:
        assert canonical_id in activities
        assert canonical_id.startswith("demo_activity_")
        # Связь self-anchored: демо не имеет внешней координаты, но описывает сама себя.
        assert provider_activity_id == canonical_id
        assert external_provider is None and external_id is None
        assert status == "unmatched"

    assert _orphan_count(db) == 0


def test_m1_t9b_repeat_activation_and_backfill_stay_idempotent(tmp_path):
    """M1-T9b: повтор сида/backfill не плодит связей и не портит поля активностей."""
    db = Database(str(tmp_path / "demo.db"))

    demo_service.activate_demo_mode(_state_for(db))
    first_links = _link_rows(db)
    first_activities = _activity_rows(db)

    # (1) Повторный офлайновый backfill поверх уже покрытого датасета — ноль новых связей.
    result = backfill_provider_links(db)
    assert result["demo"] == 0
    assert result["garmin"] == 0
    assert result["legacy_unknown"] == 0
    assert result["skipped_existing"] == len(first_activities)
    assert _link_rows(db) == first_links

    # (2) Повторная активация (clear_all_data → пересид) — тот же детерминированный набор.
    demo_service.activate_demo_mode(_state_for(db))
    assert _activity_rows(db) == first_activities
    assert len(_link_rows(db)) == len(first_links)
    assert {row[1] for row in _link_rows(db)} == {"demo"}
    assert _orphan_count(db) == 0


def test_m1_t9c_deactivation_leaves_no_orphan_links(tmp_path):
    """M1-T9c: выход из демо чистит и активности, и их связи."""
    db = Database(str(tmp_path / "demo.db"))
    state = _state_for(db)

    demo_service.activate_demo_mode(state)
    assert _link_rows(db)

    demo_service.deactivate_demo_mode(state)

    assert _activity_rows(db) == {}
    assert _link_rows(db) == []
    assert _orphan_count(db) == 0


def test_m1_t9d_demo_backfill_does_not_touch_another_database(tmp_path):
    """M1-T9d: сид+backfill изолированы своей БД (реальная база не получает связей)."""
    real = Database(str(tmp_path / "real.db"))
    real.save_activities(
        [
            {
                "activity_id": "12345678",
                "date": "2026-06-20",
                "sport": "cycling",
                "duration_minutes": 60,
                "distance_km": 30.0,
                "tss": 55.0,
            }
        ]
    )

    demo_db = Database(str(tmp_path / "demo.db"))
    demo_service.activate_demo_mode(_state_for(demo_db))

    assert len(_activity_rows(real)) == 1
    assert _link_rows(real) == [], "backfill демо-БД не должен трогать чужую базу"
