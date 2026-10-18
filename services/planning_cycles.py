"""Coherent provider-free cycle reads; publication/commands are separate work."""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from config.settings import Settings
from data.database import Database
from data.planning_cycles import PlanningCycleStore
from models.planning_cycle import CycleNotFound, project_cycle_context
from utils.athlete_time import athlete_local_date


def _read_context(
    store: PlanningCycleStore, selection: Mapping[str, Any], cycle_id: str | None,
    day: date, zone: str, has_history: bool, *, historical: bool = False,
) -> dict[str, Any]:
    cycle = store.cycle(cycle_id) if cycle_id else None
    if historical and cycle is None:
        raise CycleNotFound("Planning cycle not found")
    checkpoint_id = (cycle or {}).get("current_checkpoint_id")
    return project_cycle_context(
        selection=selection, cycle=cycle, checkpoint=store.checkpoint(checkpoint_id),
        athlete_day=day, athlete_timezone=zone, has_history=has_history,
        mapping_valid=cycle_id is not None and store.version_cycle(checkpoint_id) == cycle_id,
        queried_cycle_id=cycle_id if historical else None,
    )


def current_cycle_context(db: Database) -> dict[str, Any]:
    """Capture athlete day and all selected context on one read transaction."""
    conn = db._connect()
    try:
        conn.execute("BEGIN")
        store = PlanningCycleStore(conn)
        selection = store.state()
        day, zone = athlete_local_date(), Settings.ATHLETE_TIMEZONE
        return _read_context(store, selection, selection["current_cycle_id"], day, zone, store.has_history())
    finally:
        conn.rollback()
        conn.close()


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
