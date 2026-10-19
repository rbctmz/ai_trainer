"""Coherent selected-cycle CAS for append-only plan mutations."""
from __future__ import annotations

import sqlite3
from typing import Any

from config.settings import Settings
from data.planning_cycles import PlanningCycleStore
from models.planning_build_confirmation import PlanningBuildPreviewError, fingerprint
from models.planning_cycle import checkpoint_period, project_cycle_context, CycleStateCorrupt
from utils.athlete_time import athlete_local_date

TOKEN_FIELDS = ("cycle_id", "cycle_revision", "selection_revision", "checkpoint_id", "athlete_day", "constraint_fingerprint")


def write_token(context: dict) -> dict:
    return {key: context[key] for key in TOKEN_FIELDS}


def read_write_context(conn: sqlite3.Connection, *, allow_inactive: bool = False) -> dict[str, Any]:
    try:
        return _read_write_context(conn, allow_inactive=allow_inactive)
    except PlanningBuildPreviewError:
        raise
    except (CycleStateCorrupt, ValueError, TypeError, KeyError) as exc:
        raise PlanningBuildPreviewError("cycle_corrupt", "Состояние цикла повреждено; требуется проверка.", status=500) from exc


def _read_write_context(conn: sqlite3.Connection, *, allow_inactive: bool) -> dict[str, Any]:
    if not conn.in_transaction:
        raise RuntimeError("Cycle write context requires a transaction")
    store = PlanningCycleStore(conn)
    selection = store.state()
    cycle = store.cycle(selection["current_cycle_id"]) if selection["current_cycle_id"] else None
    checkpoint = store.checkpoint(cycle["current_checkpoint_id"]) if cycle else None
    if cycle and cycle["origin"] == "explicit" and checkpoint:
        snapshot = checkpoint.get("goal_plan_snapshot")
        if not isinstance(snapshot, dict) or snapshot.get("identity_namespace") != cycle["id"]:
            raise CycleStateCorrupt("Cycle identity namespace is invalid")
    context = project_cycle_context(selection=selection, cycle=cycle, checkpoint=checkpoint,
        athlete_day=athlete_local_date(), athlete_timezone=Settings.ATHLETE_TIMEZONE,
        has_history=store.has_history(), mapping_valid=bool(cycle and store.version_cycle(cycle["current_checkpoint_id"]) == cycle["id"]))
    rows = conn.execute("SELECT * FROM coach_constraints WHERE date>=? AND (? IS NULL OR date<=?) ORDER BY id",
                        (context["start_date"] or context["athlete_day"], context["end_date"], context["end_date"])).fetchall()
    context["constraint_fingerprint"] = fingerprint([list(row) for row in rows])
    if not allow_inactive:
        require_actionable(context)
    return context


def require_actionable(context: dict) -> None:
    if context["state"] not in {"scheduled", "in_progress"}:
        code = {"period_ended": "cycle_period_ended", "closed": "cycle_closed",
                "indeterminate": "cycle_indeterminate"}.get(context["state"], "cycle_not_current")
        raise PlanningBuildPreviewError(code, "Этот цикл нельзя изменять. Обновите контекст плана.")


def guard_write(conn: sqlite3.Connection, expected: dict | None, *, allow_inactive: bool = False) -> dict:
    if not isinstance(expected, dict) or any(key not in expected for key in TOKEN_FIELDS):
        raise PlanningBuildPreviewError("cycle_context_required", "Нужен актуальный контекст цикла.")
    actual = read_write_context(conn, allow_inactive=True)
    if write_token(actual) != write_token(expected):
        raise PlanningBuildPreviewError("cycle_stale", "Цикл или версия изменились. Обновите предпросмотр.")
    if not allow_inactive:
        require_actionable(actual)
    return actual


def check_restore_owner(conn: sqlite3.Connection, context: dict, checkpoint_id: int, *, legacy: bool = False) -> None:
    store = PlanningCycleStore(conn)
    owner = store.version_cycle(checkpoint_id)
    if owner == context["cycle_id"] and not legacy:
        return
    cycle = store.cycle(context["cycle_id"]) if context["cycle_id"] else None
    if (owner is None and legacy and cycle and cycle["origin"] == "legacy_import"
            and not conn.execute("SELECT 1 FROM planning_cycles WHERE origin='explicit' LIMIT 1").fetchone()
            and store.checkpoint(checkpoint_id)):
        return
    raise PlanningBuildPreviewError("cycle_not_current", "Версия принадлежит другому циклу или требует явного legacy-восстановления.")


def append_cycle_child(conn: sqlite3.Connection, context: dict, checkpoint: dict, checkpoint_id: int,
                       *, action: str = "adjustment", restore_legacy: bool = False) -> None:
    store = PlanningCycleStore(conn)
    if restore_legacy and action != "restore":
        raise PlanningBuildPreviewError("invalid_cycle_request", "Требуется явное действие legacy-восстановления.", status=422)
    snapshot = checkpoint.get("goal_plan_snapshot") or {}
    previous = store.checkpoint(context["checkpoint_id"])
    if (not previous or snapshot.get("checkpoint_parent_id") != context["checkpoint_id"]
            or snapshot.get("identity_namespace") != previous["goal_plan_snapshot"].get("identity_namespace")):
        raise PlanningBuildPreviewError("cycle_not_current", "Нарушена принадлежность новой версии циклу.")
    restored = snapshot.get("checkpoint_restored_from_checkpoint_id")
    if restored is not None:
        check_restore_owner(conn, context, int(restored), legacy=restore_legacy)
    period = checkpoint_period(checkpoint)
    if period.reason_code:
        raise PlanningBuildPreviewError("cycle_indeterminate", "Не удалось проверить период новой версии.")
    cycle = store.cycle(context["cycle_id"])
    if action != "restore" and (period.start.isoformat(), period.end.isoformat()) != (cycle["start_date"], cycle["end_date"]):
        raise PlanningBuildPreviewError("cycle_not_current", "Изменение не может менять период цикла.")
    conn.execute("INSERT INTO planning_cycle_versions VALUES(?,?,?)", (checkpoint_id, context["cycle_id"], action))
    conn.execute("UPDATE planning_cycles SET current_checkpoint_id=?,revision=revision+1,start_date=?,end_date=? WHERE id=?",
                 (checkpoint_id, period.start.isoformat(), period.end.isoformat(), context["cycle_id"]))
