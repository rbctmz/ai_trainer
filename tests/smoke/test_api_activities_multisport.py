"""Activity-list grouping contracts for linked multisport provider rows (#433)."""
from __future__ import annotations

from data.database import Database


EVENT_DATE = "2026-07-26"
ENVELOPE_ID = "23738670433"


def _row(
    activity_id: str,
    sport: str,
    started_at_utc: str,
    duration_minutes: float,
    distance_km: float,
    tss: float,
) -> dict:
    return {
        "activity_id": activity_id,
        "date": EVENT_DATE,
        "started_at_utc": started_at_utc,
        "sport": sport,
        "duration_minutes": duration_minutes,
        "distance_km": distance_km,
        "activity_name": "Minsk Мультитренировка",
        "tss": tss,
        "tss_method": "heuristic_duration_other",
    }


def _seed_multisport(db: Database, *, complete: bool = True) -> None:
    rows = [
        _row(ENVELOPE_ID, "multi_sport", "2026-07-26T07:06:59Z", 206.2, 49.71, 68.7),
        _row("intervals_i169367706", "swimming", "2026-07-26T07:06:59Z", 26.5, 1.06, 34.7),
        _row("intervals_i169367712", "transition", "2026-07-26T07:33:30Z", 10.6, 0.53, 1.6),
    ]
    if complete:
        rows.extend(
            [
                _row("intervals_i169367718", "cycling", "2026-07-26T07:44:02Z", 85.7, 37.85, 133.1),
                _row("intervals_i169367724", "transition", "2026-07-26T09:09:45Z", 5.0, 0.36, 1.2),
                _row("intervals_i169367727", "running", "2026-07-26T09:14:45Z", 78.4, 9.9, 120.9),
            ]
        )
    db.save_activities(rows)

    conn = db._connect()
    try:
        conn.execute(
            """
            INSERT INTO activity_provider_links (
                canonical_activity_id, provider, provider_activity_id,
                external_provider, external_id, provider_tss, match_status
            ) VALUES (?, 'garmin', ?, 'garmin', ?, 576.5, 'unmatched')
            """,
            (ENVELOPE_ID, ENVELOPE_ID, ENVELOPE_ID),
        )
        for row in rows[1:]:
            conn.execute(
                """
                INSERT INTO activity_provider_links (
                    canonical_activity_id, provider, provider_activity_id,
                    external_provider, external_id, provider_tss, match_status
                ) VALUES (?, 'intervals', ?, 'garmin', ?, ?, 'ambiguous')
                """,
                (
                    row["activity_id"],
                    row["activity_id"].removeprefix("intervals_"),
                    ENVELOPE_ID,
                    row["tss"],
                ),
            )
        conn.commit()
    finally:
        conn.close()


def test_complete_triathlon_is_one_activity_with_ordered_stages_and_single_totals(
    tmp_path,
) -> None:
    from api.routers.activities import list_activities

    db = Database(str(tmp_path / "complete.db"))
    _seed_multisport(db)

    payload = list_activities(days=36500, db=db)

    assert payload["count"] == 1
    assert payload["totals"] == {
        "count": 1,
        "distance_km": 49.7,
        "duration_hours": 3.4,
        "tss": 291.5,
    }
    item = payload["items"][0]
    assert item["activity_id"] == ENVELOPE_ID
    assert item["group_kind"] == "multisport"
    assert item["group_label"] == "Триатлон"
    assert item["duration_minutes"] == 206.2
    assert item["distance_km"] == 49.7
    assert item["tss"] == 291.5
    assert item["tss_method"] == "multisport_stages_sum"
    assert item["tss_source"] == "stages"
    assert [stage["sport"] for stage in item["segments"]] == [
        "swim",
        "transition",
        "bike",
        "transition",
        "run",
    ]
    assert [stage["sport_label"] for stage in item["segments"]] == [
        "плавание",
        "транзит",
        "вело",
        "транзит",
        "бег",
    ]
    assert [stage["activity_id"] for stage in item["segments"]] == [
        "intervals_i169367706",
        "intervals_i169367712",
        "intervals_i169367718",
        "intervals_i169367724",
        "intervals_i169367727",
    ]


def test_multisport_detail_and_analysis_use_the_same_grouped_metrics(tmp_path) -> None:
    from api.routers.activities import analyze_activity, get_activity_card

    db = Database(str(tmp_path / "detail.db"))
    _seed_multisport(db)

    detail = get_activity_card(ENVELOPE_ID, db=db)["activity"]
    analysis = analyze_activity(ENVELOPE_ID, db=db)["coach_notes"]

    assert detail["group_kind"] == "multisport"
    assert detail["tss"] == 291.5
    assert len(detail["segments"]) == 5
    assert "292 TSS (источник: сумма этапов)" in analysis


def test_incomplete_multisport_keeps_envelope_load_and_exposes_received_stages(
    tmp_path,
) -> None:
    from api.routers.activities import list_activities

    db = Database(str(tmp_path / "partial.db"))
    _seed_multisport(db, complete=False)

    payload = list_activities(days=36500, db=db)

    assert payload["count"] == 1
    assert payload["totals"]["duration_hours"] == 3.4
    assert payload["totals"]["distance_km"] == 49.7
    assert payload["totals"]["tss"] == 68.7
    item = payload["items"][0]
    assert item["tss"] == 68.7
    assert item["tss_source"] == "heuristic"
    assert [stage["sport"] for stage in item["segments"]] == [
        "swim",
        "transition",
    ]


def test_unlinked_same_day_activity_stays_separate_from_multisport_group(tmp_path) -> None:
    from api.routers.activities import list_activities

    db = Database(str(tmp_path / "unrelated.db"))
    _seed_multisport(db)
    db.save_activities(
        [
            _row(
                "evening-recovery-run",
                "running",
                "2026-07-26T18:00:00Z",
                20.0,
                3.0,
                20.0,
            )
        ]
    )

    payload = list_activities(days=36500, db=db)

    assert payload["count"] == 2
    assert {item["activity_id"] for item in payload["items"]} == {
        ENVELOPE_ID,
        "evening-recovery-run",
    }
    assert payload["totals"]["duration_hours"] == 3.8
    assert payload["totals"]["distance_km"] == 52.7
    assert payload["totals"]["tss"] == 311.5


def test_standalone_multisport_activity_remains_backward_compatible(tmp_path) -> None:
    from api.routers.activities import list_activities

    db = Database(str(tmp_path / "standalone.db"))
    db.save_activities(
        [
            _row(
                ENVELOPE_ID,
                "multi_sport",
                "2026-07-26T07:06:59Z",
                206.2,
                49.71,
                68.7,
            )
        ]
    )

    payload = list_activities(days=36500, db=db)

    assert payload["count"] == 1
    assert payload["items"][0]["activity_id"] == ENVELOPE_ID
    assert "segments" not in payload["items"][0]
    assert payload["totals"]["tss"] == 68.7
