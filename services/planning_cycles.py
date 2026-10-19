"""Coherent provider-free cycle reads; publication/commands are separate work."""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from config.settings import Settings
from data.database import Database
from data.planning_cycles import PlanningCycleStore
from models.planning_cycle import CycleNotFound, cycle_events, project_cycle_context
from utils.athlete_time import athlete_local_date


def _owned_event_candidates(store: PlanningCycleStore, cycle: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Retain distinct event snapshots from verified cycle-owned versions.

    Prefer the head, then the newest version carrying a repeated key. Repeated
    versions are not ambiguous; a duplicate within any version still is.
    """
    candidates: dict[str, dict[str, Any]] = {}
    ambiguous: set[str] = set()
    for (checkpoint_id,) in store.conn.execute(
        "SELECT checkpoint_id FROM planning_cycle_versions WHERE cycle_id=? "
        "ORDER BY (checkpoint_id=?) DESC,checkpoint_id DESC",
        (cycle["id"], cycle["current_checkpoint_id"]),
    ):
        try:
            events = cycle_events(cycle, store.checkpoint(checkpoint_id))
        except (ValueError, TypeError):
            # An unreadable old snapshot cannot donate an inferred event.
            # The head projection separately reports its corruption reason.
            continue
        for event in events:
            if event["is_ambiguous"]:
                ambiguous.add(event["event_key"])
            candidates.setdefault(event["event_key"], {"checkpoint_id": checkpoint_id, "event": event})
    for key in ambiguous:
        candidates[key]["event"]["is_ambiguous"] = True
    return candidates


def _read_context(
    store: PlanningCycleStore, selection: Mapping[str, Any], cycle_id: str | None,
    day: date, zone: str, has_history: bool, *, historical: bool = False,
) -> dict[str, Any]:
    cycle = store.cycle(cycle_id) if cycle_id else None
    if historical and cycle is None:
        raise CycleNotFound("Planning cycle not found")
    checkpoint_id = (cycle or {}).get("current_checkpoint_id")
    context = project_cycle_context(
        selection=selection, cycle=cycle, checkpoint=store.checkpoint(checkpoint_id),
        athlete_day=day, athlete_timezone=zone, has_history=has_history,
        mapping_valid=cycle_id is not None and store.version_cycle(checkpoint_id) == cycle_id,
        queried_cycle_id=cycle_id if historical else None,
    )
    if cycle and store.version_cycle(checkpoint_id) == cycle_id:
        context["events"] = [row["event"] for row in _owned_event_candidates(store, cycle).values()]
        if context["state"] == "closed" and any(not event["is_ambiguous"] for event in context["events"]):
            if "set_event_outcome" not in context["allowed_actions"]:
                context["allowed_actions"].append("set_event_outcome")
    return context


def current_plan_snapshot(db: Database) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Capture athlete day and all selected context on one read transaction."""
    conn = db._connect()
    try:
        conn.execute("BEGIN")
        store = PlanningCycleStore(conn)
        selection = store.state()
        day, zone = athlete_local_date(), Settings.ATHLETE_TIMEZONE
        context = _read_context(store, selection, selection["current_cycle_id"], day, zone, store.has_history())
        return context, db._get_current_planning_checkpoint(conn)
    finally:
        conn.rollback()
        conn.close()


def current_cycle_context(db: Database) -> dict[str, Any]:
    """Public state uses the same coherent snapshot as every current reader."""
    return current_plan_snapshot(db)[0]


def actionable(context: Mapping[str, Any]) -> bool:
    return context["state"] in {"scheduled", "in_progress"} and context["is_selected"]


def session_checkpoint(db: Database, session_id: str, *, include_retired: bool = True, checkpoint_id: int | None = None) -> dict[str, Any] | None:
    """Explicit session history, independent of current selection or period.

    Explicit checkpoint, selection or saved-match bindings supply context.
    Otherwise only a single known owner may donate its latest matching version;
    ambiguous legacy rows need an explicit checkpoint. Never selects a cycle.
    """
    from models.plan_actual_reconciliation import find_planned_session
    from models.planning_checkpoints import restore_goal_plan_from_checkpoint

    def contains(checkpoint):
        plan = restore_goal_plan_from_checkpoint(checkpoint) or {}
        return find_planned_session(plan.get("session_templates") or [], session_id)[1] is not None

    if checkpoint_id is not None:
        explicit = db.get_planning_checkpoint(checkpoint_id)
        return explicit if contains(explicit) else None
    current_reader = getattr(db, "get_current_planning_checkpoint", None)
    selected = current_reader() if callable(current_reader) else None
    if contains(selected):
        return selected
    # A saved match is an explicit historical binding, not a MAX inference.
    match_reader = getattr(db, "get_latest_plan_actual_match_for_session", None)
    match = match_reader(session_id) if callable(match_reader) else None
    if match and match.get("base_checkpoint_id") is not None:
        bound = db.get_planning_checkpoint(match["base_checkpoint_id"])
        if contains(bound):
            return bound
    reader = getattr(db, "get_planning_checkpoints_for_session", None)
    candidates = list(reader(session_id) or []) if callable(reader) else []
    if not candidates:
        return None
    if hasattr(db, "_connect"):
        conn = db._connect()
        try:
            conn.execute("BEGIN")
            store = PlanningCycleStore(conn)
            owners = {store.version_cycle(row["id"]) or ("unassigned", row["id"]) for row in candidates}
            if len(owners) != 1:
                return None
            if not include_retired and selected is not None and store.version_cycle(candidates[0]["id"]) == store.version_cycle(selected["id"]):
                return None
        finally:
            conn.rollback()
            conn.close()
    elif len(candidates) != 1:
        return None
    return candidates[0]



def historical_cycle_context(db: Database, cycle_id: str) -> dict[str, Any]:
    """Read an explicit historical cycle without choosing or reopening it."""
    conn = db._connect()
    try:
        conn.execute("BEGIN")
        store = PlanningCycleStore(conn)
        return _read_context(store, store.state(), cycle_id, athlete_local_date(),
                             Settings.ATHLETE_TIMEZONE, store.has_history(), historical=True)
    finally:
        conn.rollback()
        conn.close()


def cycle_history(db: Database, *, limit: int = 50) -> list[dict[str, Any]]:
    """Bounded cycle history shares one selection and athlete day for every row."""
    conn = db._connect()
    try:
        conn.execute("BEGIN")
        store = PlanningCycleStore(conn)
        selection = store.state()
        day, zone, history = athlete_local_date(), Settings.ATHLETE_TIMEZONE, store.has_history()
        return [_read_context(store, selection, cycle_id, day, zone, history, historical=True)
                for cycle_id in store.cycle_ids(limit)]
    finally:
        conn.rollback()
        conn.close()


def checkpoint_history(db: Database, *, limit: int = 10) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """History ownership and restore eligibility are server-owned read hints.

    Confirm still rechecks its expected cycle/selection/head under the writer
    lock. Unassigned legacy rows are never associated by browsing them.
    """
    from data.planning_cycle_writes import check_restore_owner
    from models.planning_build_confirmation import PlanningBuildPreviewError

    conn = db._connect()
    try:
        conn.execute("BEGIN")
        store = PlanningCycleStore(conn)
        selection = store.state()
        context = _read_context(store, selection, selection["current_cycle_id"], athlete_local_date(),
                                Settings.ATHLETE_TIMEZONE, store.has_history())
        rows = conn.execute("SELECT id,goal_type,distance,weeks_to_race,checkpoint_data,created_at "
                            "FROM planning_checkpoints ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        result = []
        for row in rows:
            checkpoint = db._deserialize_planning_checkpoint_row(row)
            if checkpoint is None:
                continue
            owner = store.version_cycle(row[0])
            legacy = owner is None
            can_restore = actionable(context) and row[0] != context["checkpoint_id"]
            if can_restore:
                try:
                    check_restore_owner(conn, context, row[0], legacy=legacy)
                except PlanningBuildPreviewError:
                    can_restore = False
            result.append({"checkpoint": checkpoint, "cycle_id": owner, "can_restore": can_restore,
                           "restore_action": "restore_legacy_version" if legacy else "restore_version"})
        return context, result
    finally:
        conn.rollback()
        conn.close()
