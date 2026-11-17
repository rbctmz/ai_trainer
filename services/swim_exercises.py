"""Shared catalog writes and explicit pinned-definition reuse; no AI/provider I/O."""

from __future__ import annotations
from typing import Any
from data import swim_exercise_store as store
from models.swim_exercise import SwimExerciseDocument, make_step
from services.snapshot_runtime import backup_operation


def confirm(
    db: Any,
    document: SwimExerciseDocument,
    *,
    base_revision: int,
    request_id: str,
    fingerprint: str,
) -> dict[str, Any]:
    with backup_operation(db, "swim_exercise_confirm"):
        return store.confirm(
            db,
            document,
            base_revision=base_revision,
            request_id=request_id,
            fingerprint=fingerprint,
        )


def resolve(
    db: Any,
    *,
    exercise_id: str,
    revision: int,
    node_id: str,
    distance_meters: int,
    instructions: str = "",
) -> dict[str, Any]:
    version = store.get_version(db, exercise_id, revision=revision)
    step = make_step(
        SwimExerciseDocument.model_validate(version["document"]),
        node_id=node_id,
        distance_meters=distance_meters,
        instructions=instructions,
    )
    return {"exercise": version, "step": step.model_dump(mode="json")}
