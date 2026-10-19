"""Private initialization for empty, explicitly synthetic evaluation databases."""
from __future__ import annotations

from data.database import Database
from data.planning_cycles import PlanningCycleStore, initialize_cycle_store


def _seed_legacy_checkpoint(db: Database, checkpoint: dict) -> dict:
    """Initialize once using the genuine legacy-import path, never replace data."""
    conn = db._connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        store = PlanningCycleStore(conn)
        if store.has_history() or store.state()["current_cycle_id"] or store.cycle_ids():
            raise ValueError("Synthetic initialization requires empty planning history")
        saved = db._insert_planning_checkpoint(conn, checkpoint)
        conn.execute("DELETE FROM planning_cycle_state")
        initialize_cycle_store(conn)
        conn.commit()
        return saved
    finally:
        conn.close()
