"""Activities endpoint: recent training sessions from the local cache."""
from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import get_database
from api.operational_state import build_operational_state, latest_iso_from_frame
from data.database import Database
from models.activity_lineage import (
    identify_multisport_groups,
    project_multisport_activity,
)
from models.activity_card import (
    build_activity_analysis,
    feedback_for_activity,
    foster_load_au,
)
from models.plan_intervals import planned_intervals_for_match
from models.plan_vs_fact import match_plan_vs_fact, plan_replanned_after_delivery
from services.activity_intervals import fetch_activity_intervals
from services.best_efforts import fetch_activity_power_curve
from utils.product_semantics import format_date_label, normalize_sport_key, sport_label

router = APIRouter(prefix="/api/activities", tags=["activities"])

_NUMERIC = (
    "duration_minutes",
    "moving_duration_minutes",
    "distance_km",
    "tss",
    "garmin_training_load",
    "source_tss",
    "tss_ftp_used",
    "tss_pace_used",
    "avg_hr",
    "max_hr",
    "elevation_gain",
    "calories",
)


def _text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _num(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None


def _base_item(row: Any) -> dict[str, Any]:
    """Базовый элемент карточки активности из строки БД (без enrich-полей)."""
    raw_sport = row.get("sport") or "—"
    tss_method = _text(row.get("tss_method"))
    if tss_method and tss_method.startswith("power_tss_"):
        tss_source = "power"
    elif tss_method and tss_method.startswith("pace_tss_"):
        tss_source = "pace"
    elif tss_method and (
        tss_method.startswith("hr_tss_") or tss_method.startswith("hr_zone_tss_")
    ):
        tss_source = "heart_rate"
    elif tss_method and tss_method.startswith("heuristic_"):
        tss_source = "heuristic"
    elif tss_method == "no_duration":
        tss_source = "none"
    else:
        tss_source = "unknown"
    return {
        "activity_id": _text(row.get("activity_id")) or "",
        "date": pd.to_datetime(row["date"]).strftime("%Y-%m-%d"),
        "date_label": format_date_label(row.get("date")),
        "sport": normalize_sport_key(raw_sport),
        "sport_label": sport_label(raw_sport),
        **{key: _num(row.get(key)) for key in _NUMERIC},
        "tss_method": tss_method,
        "tss_source": tss_source,
    }


def _projected_base_item(db: Database, row: Any) -> dict[str, Any]:
    """Return the same event-grain activity DTO for list, detail, and analysis."""
    item = _base_item(row)
    date_key = item["date"]
    frame = pd.DataFrame(db.get_activities_between(date_key, date_key))
    if frame.empty:
        return item
    group = next(
        (
            candidate
            for candidate in identify_multisport_groups(frame)
            if candidate.envelope_id == item["activity_id"]
        ),
        None,
    )
    if group is None:
        return item
    rows_by_id = {
        base["activity_id"]: base
        for base in (_base_item(candidate) for _, candidate in frame.iterrows())
    }
    stages = [
        rows_by_id[stage_id]
        for stage_id in group.stage_ids
        if stage_id in rows_by_id
    ]
    return project_multisport_activity(item, stages, group)


@router.get("")
def list_activities(
    days: int = 30,
    demo: bool = False,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    df = db.get_activities(days)
    if df is None or df.empty:
        return {
            "has_data": False,
            "count": 0,
            "totals": {},
            "items": [],
            "operational_state": build_operational_state(db, demo=demo, has_data=False),
        }

    df = df.sort_values("date", ascending=False, kind="stable")
    tags_by_activity = db.get_all_activity_tags()
    notes_by_activity = db.get_all_activity_coach_notes()
    latest_feedbacks = db.get_latest_session_feedbacks()
    items_by_id: dict[str, dict[str, Any]] = {}
    for _, row in df.iterrows():
        item = _base_item(row)
        activity_id = item["activity_id"]
        item["feedback"] = feedback_for_activity(activity_id, latest_feedbacks)
        if item["feedback"]:
            item["feedback"]["foster_load"] = foster_load_au(
                item["feedback"].get("session_rpe_1_10"),
                item.get("duration_minutes"),
            )
        item["tags"] = tags_by_activity.get(activity_id, [])
        item["coach_notes"] = notes_by_activity.get(activity_id)
        items_by_id[activity_id] = item

    groups = identify_multisport_groups(df)
    groups_by_envelope = {group.envelope_id: group for group in groups}
    grouped_stage_ids = {
        stage_id for group in groups for stage_id in group.stage_ids
    }
    items: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        activity_id = str(row.get("activity_id"))
        if activity_id in grouped_stage_ids:
            continue
        item = items_by_id[activity_id]
        group = groups_by_envelope.get(activity_id)
        if group is not None:
            segments = [
                items_by_id[stage_id]
                for stage_id in group.stage_ids
                if stage_id in items_by_id
            ]
            item = project_multisport_activity(item, segments, group)
        items.append(item)

    totals = {
        "count": len(items),
        "distance_km": _num(sum(item.get("distance_km") or 0.0 for item in items)),
        "duration_hours": _num(
            sum(item.get("duration_minutes") or 0.0 for item in items) / 60
        ),
        "tss": _num(sum(item.get("tss") or 0.0 for item in items)),
    }

    return {
        "has_data": True,
        "count": len(items),
        "totals": totals,
        "items": items,
        "operational_state": build_operational_state(
            db,
            demo=demo,
            has_data=True,
            latest_data_at=latest_iso_from_frame(df),
        ),
    }


class TagRequest(BaseModel):
    tag: str


class CoachNotesRequest(BaseModel):
    body: str
    source: str = "coach"


@router.get("/{activity_id}")
def get_activity_card(
    activity_id: str,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    row = db.get_activity(activity_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    item = _projected_base_item(db, row)
    item["feedback"] = feedback_for_activity(
        activity_id, db.get_latest_session_feedbacks()
    )
    if item["feedback"]:
        item["feedback"]["foster_load"] = foster_load_au(
            item["feedback"].get("session_rpe_1_10"),
            item.get("duration_minutes"),
        )
    item["tags"] = db.get_activity_tags(activity_id)
    item["coach_notes"] = db.get_activity_coach_notes(activity_id)
    item["intervals"] = fetch_activity_intervals(db, activity_id)
    item["power_curve"] = fetch_activity_power_curve(db, activity_id)
    planned_match = db.get_plan_actual_match_for_activity(activity_id)
    planned_intervals = None
    if planned_match is not None:
        checkpoint_id = planned_match.get("base_checkpoint_id")
        checkpoint_data = (
            db.get_checkpoint_data(checkpoint_id) if checkpoint_id is not None else None
        )
        planned_intervals = planned_intervals_for_match(planned_match, checkpoint_data)
    item["planned_intervals"] = planned_intervals
    if planned_intervals is None:
        item["plan_vs_fact"] = None
    else:
        actual = item.get("intervals")
        actual_intervals = actual.get("intervals") if isinstance(actual, dict) else []
        plan_vs_fact = match_plan_vs_fact(
            planned_intervals, actual_intervals or []
        )
        checkpoint = (
            db.get_planning_checkpoint(planned_match["base_checkpoint_id"])
            if planned_match.get("base_checkpoint_id") is not None
            else None
        )
        plan_vs_fact["plan_replanned_after_delivery"] = (
            plan_replanned_after_delivery(
                planned_match,
                checkpoint,
                db.get_approved_recovery_replan_deliveries(),
            )
        )
        item["plan_vs_fact"] = plan_vs_fact
    return {"activity": item}


@router.post("/{activity_id}/tags")
def add_activity_tag(
    activity_id: str,
    payload: TagRequest,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    if db.get_activity(activity_id) is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    db.add_activity_tag(activity_id, payload.tag)
    return {"activity_id": activity_id, "tags": db.get_activity_tags(activity_id)}


@router.delete("/{activity_id}/tags/{tag}")
def remove_activity_tag(
    activity_id: str,
    tag: str,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    if db.get_activity(activity_id) is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    db.remove_activity_tag(activity_id, tag)
    return {"activity_id": activity_id, "tags": db.get_activity_tags(activity_id)}


@router.put("/{activity_id}/coach-notes")
def save_coach_notes(
    activity_id: str,
    payload: CoachNotesRequest,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    if db.get_activity(activity_id) is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    db.save_activity_coach_notes(activity_id, payload.body, source=payload.source)
    return {
        "activity_id": activity_id,
        "coach_notes": db.get_activity_coach_notes(activity_id),
    }


@router.post("/{activity_id}/analyze")
def analyze_activity(
    activity_id: str,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    """Детерминированный разбор по реальным данным; результат в coach_notes."""
    from services.readiness_snapshot import build_readiness_snapshot

    row = db.get_activity(activity_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    item = _projected_base_item(db, row)
    activity_date = pd.to_datetime(row["date"]).date()
    readiness = build_readiness_snapshot(db, as_of=activity_date)
    feedback = feedback_for_activity(
        activity_id, db.get_latest_session_feedbacks()
    )
    body = build_activity_analysis(item, feedback, readiness)
    db.save_activity_coach_notes(activity_id, body, source="auto")
    return {"activity_id": activity_id, "coach_notes": body}
