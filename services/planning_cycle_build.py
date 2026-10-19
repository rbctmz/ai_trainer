"""Cycle-owned build context and calendar boundaries, without training formulas."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
import json
from typing import Any, Mapping
from uuid import uuid4

from config.settings import Settings
from data.database import Database
from data.planning_cycles import PlanningCycleStore
from models.planning_build_confirmation import PlanningBuildPreviewError
from models.planning_cycle import stored_day
from models.planning_checkpoints import restore_goal_plan_from_checkpoint
from models.training_planner import derive_weekly_sport_buckets_from_sessions
from services.planning_cycles import _read_context
from services.planning_contracts import DAY_MAP, DISTANCE_MAP, GOAL_TYPE_MAP
from utils.athlete_time import athlete_local_date


def _refuse(code: str, detail: str, status: int = 409):
    raise PlanningBuildPreviewError(code, detail, status=status)


def _editable(context: Mapping[str, Any]) -> None:
    if context["state"] not in {"scheduled", "in_progress"}:
        code = {"period_ended": "cycle_period_ended", "closed": "cycle_closed",
                "indeterminate": "cycle_indeterminate"}.get(context["state"], "cycle_not_current")
        _refuse(code, "Этот цикл нельзя изменять — начните новый или откройте историю.")


def capture_lifecycle(store: PlanningCycleStore, raw: dict, day: date, *, frozen: dict | None = None) -> tuple[dict, dict]:
    """Validate expected selection and reserve identity only on the initial read."""
    selection = store.state()
    context = _read_context(store, selection, selection["current_cycle_id"], day,
                            Settings.ATHLETE_TIMEZONE, store.has_history())
    cycle = store.cycle(context["cycle_id"]) if context["cycle_id"] else None
    if frozen is not None:
        raw = {**raw, "action": frozen["action"], "base_cycle_id": frozen["source_cycle_id"],
               "base_cycle_revision": frozen["base_cycle_revision"],
               "base_selection_revision": frozen["base_selection_revision"],
               "base_checkpoint_id": frozen["base_checkpoint_id"],
               "start_date": frozen["start_date"], "replace_current_cycle": frozen["closes_cycle_id"] is not None}
    action = raw.get("action")
    if action not in {"start_new", "edit_current"}:
        _refuse("cycle_context_required", "Выберите новый цикл или изменение текущего.")
    if any(key not in raw for key in ("base_cycle_id", "base_cycle_revision", "base_selection_revision",
                                      "base_checkpoint_id", "replace_current_cycle", "start_date")):
        _refuse("cycle_context_required", "Обновите контекст цикла перед предпросмотром.")
    if (type(raw["base_selection_revision"]) is not int or type(raw["base_checkpoint_id"]) is not int
            or (raw["base_cycle_revision"] is not None and type(raw["base_cycle_revision"]) is not int)
            or type(raw["replace_current_cycle"]) is not bool):
        _refuse("invalid_cycle_request", "Проверьте типы полей контекста цикла.", 422)
    expected = (raw["base_cycle_id"], raw["base_cycle_revision"], raw["base_selection_revision"], raw["base_checkpoint_id"])
    actual = (context["cycle_id"], context["cycle_revision"], context["selection_revision"], context["checkpoint_id"] or 0)
    if expected != actual:
        _refuse("cycle_stale", "Цикл изменился — обновите контекст.")
    if action == "edit_current":
        _editable(context)
    start = stored_day(raw["start_date"])
    if start is None or raw["start_date"] != start.isoformat():
        _refuse("invalid_start_date", "Укажите дату начала в формате ГГГГ-ММ-ДД.", 422)
    if action == "edit_current":
        if start.isoformat() != context["start_date"] or raw["replace_current_cycle"] is not False:
            _refuse("invalid_start_date", "Изменение сохраняет начало и принадлежность цикла.", 422)
    else:
        if "start_new" not in context["allowed_actions"]:
            _refuse("cycle_indeterminate", "Не удалось проверить выбранный цикл.")
        if raw["replace_current_cycle"] is not (context["cycle_id"] is not None):
            _refuse("replacement_confirmation_required", "Явно подтвердите замену выбранного цикла.")
        if start < day:
            _refuse("invalid_start_date", "Новый цикл не может начинаться в прошлом.", 422)
    monday = (start - timedelta(days=start.weekday())).isoformat()
    if raw.get("start_week") and raw["start_week"] != monday:
        _refuse("invalid_start_date", "Неделя календаря должна соответствовать дате начала.", 422)
    lifecycle = {"action": action, "source_cycle_id": context["cycle_id"],
                 "target_cycle_id": (frozen["target_cycle_id"] if frozen else str(uuid4()))
                 if action == "start_new" else context["cycle_id"],
                 "base_cycle_revision": context["cycle_revision"],
                 "base_selection_revision": context["selection_revision"], "base_checkpoint_id": actual[3],
                 "start_date": start.isoformat(), "end_date": None,
                 "closes_cycle_id": context["cycle_id"] if action == "start_new" else None}
    return lifecycle, {"selection": selection, "cycle": cycle, "calendar_week_start": monday}


def scoped_constraints(rows: list[dict], target_cycle_id: str, known_cycle_ids: set[str]) -> list[dict]:
    unknown = [row["id"] for row in rows if row.get("cycle_scope") not in {"athlete", "cycle"}
               or (row.get("cycle_scope") == "cycle" and row.get("cycle_id") not in known_cycle_ids)]
    if unknown:
        error = PlanningBuildPreviewError("constraint_scope_required", "Уточните принадлежность ограничений перед предпросмотром.")
        error.context = {"constraint_ids": unknown}
        raise error
    return [row for row in rows if row["cycle_scope"] == "athlete" or row.get("cycle_id") == target_cycle_id]


def cycle_build_context(db: Database, action: str) -> dict[str, Any]:
    conn = db._connect()
    try:
        conn.execute("BEGIN")
        store, day = PlanningCycleStore(conn), athlete_local_date()
        selection = store.state()
        context = _read_context(store, selection, selection["current_cycle_id"], day,
                                Settings.ATHLETE_TIMEZONE, store.has_history())
        inputs = {key: None for key in ("goal_type", "distance", "intent", "planning_mode", "focus",
                                       "horizon_weeks", "event_date", "manual_phases", "available_hours", "demand")}
        inputs.update(start_date=day.isoformat(), calendar_week_start=(day - timedelta(days=day.weekday())).isoformat(),
                      events=[], available_days=[])
        sources = {key: "new_choice_required" for key in inputs}
        for key in ("start_date", "calendar_week_start", "events", "event_date", "manual_phases"):
            sources[key] = "new_cycle_default"
        if action == "edit_current":
            _editable(context)
            plan = restore_goal_plan_from_checkpoint(store.checkpoint(context["checkpoint_id"]))
            constraints = plan.get("constraint_summary") or {}
            inputs.update(goal_type=plan.get("goal_type"), distance=plan.get("distance"),
                          intent=plan.get("planning_intent"), planning_mode=plan.get("planning_mode"),
                          focus=plan.get("planning_focus"), horizon_weeks=plan.get("horizon_weeks"),
                          event_date=plan.get("event_date") or None, events=plan.get("events") or [],
                          manual_phases=plan.get("phases") if plan.get("planning_mode") == "manual" else None,
                          available_hours=constraints.get("available_hours"),
                          available_days=[list(DAY_MAP)[i] for i in constraints.get("available_day_indices", [])],
                          demand=plan.get("demand_level"), start_date=context["start_date"],
                          calendar_week_start=(stored_day(context["start_date"]) - timedelta(
                              days=stored_day(context["start_date"]).weekday())).isoformat())
            sources = {key: "selected_checkpoint" for key in inputs}
            for key, choices in (("goal_type", GOAL_TYPE_MAP), ("distance", DISTANCE_MAP)):
                inputs[key] = next((name for name, label in choices.items() if label == inputs[key]), inputs[key])
        elif action == "start_new":
            from services.planning_profile import normalize_profile
            row = conn.execute("SELECT value FROM user_settings WHERE key='planning_profile'").fetchone()
            if row:
                try:
                    profile = normalize_profile(json.loads(row[0]))
                except (ValueError, TypeError, KeyError):
                    profile = {}
                for key in ("available_hours", "available_days", "focus", "demand"):
                    if profile.get(key) is not None:
                        inputs[key], sources[key] = profile[key], "profile_suggestion"
        else:
            _refuse("invalid_cycle_request", "Неизвестное действие цикла.", 422)
        return {"action": action, "inputs": inputs, "input_sources": sources, "cycle_context": context}
    finally:
        conn.rollback()
        conn.close()


def bound_prescriptions(plan: dict, lifecycle: Mapping, existing: dict | None, day: date) -> dict:
    """Clip actual days, preserve past edits and recount by calendar date, not position."""
    result = deepcopy(plan)
    start, end = date.fromisoformat(lifecycle["start_date"]), date.fromisoformat(lifecycle["end_date"])
    pairs = {item[0].date(): (item, template) for item, template in zip(result["daily_plan"], result["session_templates"])
             if start <= item[0].date() <= end}
    if lifecycle["action"] == "edit_current":
        for item, template in zip(existing["daily_plan"], existing["session_templates"]):
            if item[0].date() < day:
                pairs[item[0].date()] = (deepcopy(item), deepcopy(template))
    result["daily_plan"], result["session_templates"] = map(list, zip(*(pairs[key] for key in sorted(pairs))))
    rows, phases = [], []
    for index, raw in enumerate(result["weekly_summary"]):
        value = raw["week_start"]
        week = stored_day(value) if isinstance(value, str) else value.date() if hasattr(value, "date") else value
        if week > end or week + timedelta(days=6) < start:
            continue
        templates = [template for dt, (_item, template) in pairs.items() if week <= dt < week + timedelta(days=7)]
        row = derive_weekly_sport_buckets_from_sessions([raw], templates)[0]
        rows.append(row)
        phases.append(result["phases"][index])
    result.update(weekly_summary=rows, weekly_tss_plan=[row["weekly_tss"] for row in rows], phases=phases,
                  horizon_weeks=len(rows))
    for key in ("event_overlays", "microcycle_changes", "race_forecast_loads"):
        result[key] = [row for row in result.get(key, []) if (dt := stored_day(row.get("date"))) and start <= dt <= end]
    result["protected_dates"] = [value for value in result.get("protected_dates", []) if start <= stored_day(value) <= end]
    return result
