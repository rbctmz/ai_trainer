"""Private selected-store source capture and human draft editing/preview."""

from typing import Annotated, Any, Awaitable, Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path
from starlette.requests import Request
from starlette.responses import Response

from api.deps import get_database
from api.routers.swim_programs import SafeProgramRoute
from api.swim_import_contract import (
    SwimImportDraftResponse,
    SwimImportListResponse,
    SwimImportPreviewResponse,
)
from data.database import Database
from data import swim_import_store as store
from models.swim_import import CaptureSource, ParseDraft, PatchDraft, PrepareDraft
from services import swim_imports


class SafeImportRoute(SafeProgramRoute):
    invalid_request_code = "swim_import_invalid_request"

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await original(request)
            except store.SwimImportError as exc:
                raise HTTPException(
                    status_code=exc.status, detail={"code": exc.code}
                ) from exc

        return handle


router = APIRouter(
    prefix="/api/swim-imports", tags=["swim-imports"], route_class=SafeImportRoute
)


@router.post("", response_model=SwimImportDraftResponse)
def capture(
    request: CaptureSource, db: Database = Depends(get_database)
) -> dict[str, Any]:
    return swim_imports.capture_source(db, request)


@router.get("", response_model=SwimImportListResponse)
def drafts(db: Database = Depends(get_database)) -> dict[str, Any]:
    return {"items": store.list_drafts(db)}


@router.get("/{import_id}", response_model=SwimImportDraftResponse)
def current(import_id: UUID, db: Database = Depends(get_database)) -> dict[str, Any]:
    return store.get_draft(db, str(import_id))


@router.get("/{import_id}/revisions/{revision}", response_model=SwimImportDraftResponse)
def historical(
    import_id: UUID,
    revision: Annotated[int, Path(ge=0)],
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    return store.get_draft(db, str(import_id), revision=revision)


@router.post("/{import_id}/parse", response_model=SwimImportDraftResponse)
def parse(
    import_id: UUID, request: ParseDraft, db: Database = Depends(get_database)
) -> dict[str, Any]:
    return swim_imports.parse_draft(db, str(import_id), request, actor="user")


@router.post("/{import_id}/patch", response_model=SwimImportDraftResponse)
def patch(
    import_id: UUID, request: PatchDraft, db: Database = Depends(get_database)
) -> dict[str, Any]:
    return swim_imports.patch_draft(db, str(import_id), request, actor="user")


@router.post("/{import_id}/preview", response_model=SwimImportPreviewResponse)
def preview(
    import_id: UUID, request: PrepareDraft, db: Database = Depends(get_database)
) -> dict[str, Any]:
    return swim_imports.prepare_preview(db, str(import_id), request)
