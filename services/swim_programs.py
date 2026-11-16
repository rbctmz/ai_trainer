"""Shared program-library boundary, independent of UI, planner and providers."""
from __future__ import annotations

from typing import Any

from data import swim_program_store as store
from services.snapshot_runtime import backup_operation


def confirm(db: Any, preview_id: str) -> dict[str, Any]:
    with backup_operation(db, "swim_program_confirm"):
        return store.confirm_preview(db, preview_id)
