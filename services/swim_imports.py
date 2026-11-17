"""Provider-independent source/draft operations; callers supply a trusted actor."""

from typing import Any
from data import swim_import_store as store
from models.swim_import import CaptureSource, ParseDraft, PatchDraft, PrepareDraft


def capture_source(db: Any, request: CaptureSource) -> dict[str, Any]:
    return store.capture(db, request)


def parse_draft(
    db: Any, import_id: str, request: ParseDraft, *, actor: store.Actor
) -> dict[str, Any]:
    return store.parse(db, import_id, request, actor=actor)


def patch_draft(
    db: Any, import_id: str, request: PatchDraft, *, actor: store.Actor
) -> dict[str, Any]:
    return store.patch(db, import_id, request, actor=actor)


def prepare_preview(db: Any, import_id: str, request: PrepareDraft) -> dict[str, Any]:
    return store.prepare(db, import_id, request)
