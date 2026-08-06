"""Smoke: карточка завершённой тренировки (шаг 1 из #379).

ExecPlan: docs/activity_card_execplan.md. Проверяет чистую модель (grade,
поиск фидбека, разбор) и контракты API (теги, coach notes, analyze).
"""
from __future__ import annotations

from datetime import datetime

import pytest

from data.database import Database
from models.activity_card import (
    build_activity_analysis,
    feedback_for_activity,
    grade_from_quality,
)


pytestmark = pytest.mark.smoke


def _activity_row(activity_id: str = "act-1") -> dict:
    return {
        "activity_id": activity_id,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "sport": "cycling",
        "sport_label": "Вело",
        "duration_minutes": 60.0,
        "distance_km": 30.0,
        "tss": 60.0,
        "tss_method": "power_tss_v1",
        "tss_source": "power",
        "avg_hr": 140.0,
        "max_hr": 175.0,
    }


def _feedback_row(
    activity_id: str = "act-1",
    *,
    rpe: int = 8,
    quality: int = 5,
    status: str = "active",
) -> dict:
    return {
        "session_id": "s-1",
        "actual_activity_ids": [activity_id],
        "session_rpe_1_10": rpe,
        "quality_rating_1_5": quality,
        "note": "Тяжело, но по плану",
        "status": status,
        "submitted_at": "2026-08-06T10:00:00Z",
    }


def _seed_activity(db: Database, activity_id: str = "act-1") -> None:
    db.save_activities(
        [
            {
                "activity_id": activity_id,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "sport": "cycling",
                "duration_minutes": 60,
                "distance_km": 30.0,
                "tss": 60.0,
                "tss_method": "power_tss_v1",
                "avg_hr": 140,
                "max_hr": 175,
            }
        ]
    )


def _seed_feedback(
    db: Database,
    activity_id: str = "act-1",
    *,
    rpe: int = 8,
    quality: int = 5,
) -> None:
    db.save_session_feedback(
        {
            "fingerprint": f"fp-{activity_id}",
            "target_key": f"tk-{activity_id}",
            "session_id": f"s-{activity_id}",
            "match_snapshot": {"match_status": "matched"},
            "actual_activity_ids": [activity_id],
            "completion_status": "completed",
            "source": "athlete",
            "session_end_provenance": "local",
            "status": "active",
            "rule_version": "test",
            "submitted_at": "2026-08-06T10:00:00Z",
            "session_rpe_1_10": rpe,
            "quality_rating_1_5": quality,
        }
    )


def test_grade_mapping_matches_quality_scale():
    assert grade_from_quality(5) == "A"
    assert grade_from_quality(4) == "B"
    assert grade_from_quality(3) == "C"
    assert grade_from_quality(2) == "D"
    assert grade_from_quality(1) == "E"
    assert grade_from_quality(None) is None


def test_feedback_for_activity_matches_by_actual_ids_and_skips_tombstones():
    found = feedback_for_activity("act-1", [_feedback_row("act-1")])
    assert found is not None
    assert found["session_rpe_1_10"] == 8
    assert found["grade"] == "A"
    assert found["quality_rating_1_5"] == 5

    other = feedback_for_activity("act-2", [_feedback_row("act-1")])
    assert other is None

    tombstoned = feedback_for_activity(
        "act-1", [_feedback_row("act-1", status="tombstone")]
    )
    assert tombstoned is None


def test_analysis_builder_is_deterministic_and_includes_real_numbers():
    analysis = build_activity_analysis(_activity_row(), _feedback_row(), None)

    assert analysis.startswith("## Разбор тренировки")
    assert "60 мин" in analysis
    assert "30.0 км" in analysis
    assert "60 TSS" in analysis
    assert "RPE 8/10" in analysis
    assert "grade A" in analysis
    assert build_activity_analysis(_activity_row(), _feedback_row(), None) == analysis


def test_db_tag_and_notes_methods(tmp_path):
    db = Database(str(tmp_path / "card.db"))
    _seed_activity(db)

    db.add_activity_tag("act-1", "Восстановление")
    db.add_activity_tag("act-1", "восстановление")  # дубликат -> игнор
    db.add_activity_tag("act-1", "техника")

    assert db.get_activity_tags("act-1") == ["восстановление", "техника"]
    assert db.get_all_activity_tags() == {"act-1": ["восстановление", "техника"]}

    db.remove_activity_tag("act-1", "техника")
    assert db.get_activity_tags("act-1") == ["восстановление"]

    assert db.get_activity_coach_notes("act-1") is None
    db.save_activity_coach_notes("act-1", "Первая версия", source="coach")
    db.save_activity_coach_notes("act-1", "Обновлённая версия", source="coach")
    assert db.get_activity_coach_notes("act-1") == "Обновлённая версия"
    assert db.get_all_activity_coach_notes() == {"act-1": "Обновлённая версия"}


def test_activity_card_api_enriches_list_and_endpoints(tmp_path):
    from api.routers.activities import (
        add_activity_tag,
        analyze_activity,
        get_activity_card,
        list_activities,
        remove_activity_tag,
        save_coach_notes,
    )
    from api.routers.activities import CoachNotesRequest, TagRequest

    db = Database(str(tmp_path / "api.db"))
    _seed_activity(db)
    _seed_feedback(db)

    payload = list_activities(days=30, db=db)
    assert payload["has_data"] is True
    item = payload["items"][0]
    assert item["feedback"]["session_rpe_1_10"] == 8
    assert item["feedback"]["grade"] == "A"
    assert item["tags"] == []
    assert item["coach_notes"] is None

    added = add_activity_tag("act-1", TagRequest(tag="Техника"), db=db)
    assert added["tags"] == ["техника"]
    removed = remove_activity_tag("act-1", "техника", db=db)
    assert removed["tags"] == []

    saved = save_coach_notes(
        "act-1", CoachNotesRequest(body="Заметка тренера"), db=db
    )
    assert saved["coach_notes"] == "Заметка тренера"

    card = get_activity_card("act-1", db=db)
    assert card["activity"]["feedback"]["grade"] == "A"
    assert card["activity"]["coach_notes"] == "Заметка тренера"

    analyzed = analyze_activity("act-1", db=db)
    assert analyzed["coach_notes"].startswith("## Разбор тренировки")
    assert db.get_activity_coach_notes("act-1") == analyzed["coach_notes"]
