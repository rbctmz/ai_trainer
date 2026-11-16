"""Private selected-store swim library; source text never enters error payloads."""
from __future__ import annotations

from typing import Annotated, Any, Awaitable, Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.requests import Request
from starlette.responses import Response

from api.deps import get_database
from api.swim_program_contract import (
    SwimProgramConfirmRequest, SwimProgramListResponse, SwimProgramPreviewRequest,
    SwimProgramPreviewResponse, SwimProgramVersionResponse,
)
from data.database import Database
from data import swim_program_store as store
from services import swim_programs


class SafeProgramRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError:
                # Framework errors otherwise include submitted values/original text.
                return JSONResponse(status_code=422, content={"detail": {"code": "swim_program_invalid_request"}})
            except store.SwimProgramError as exc:
                raise HTTPException(status_code=exc.status, detail={"code": exc.code}) from exc
        return handle


router = APIRouter(prefix="/api/swim-programs", tags=["swim-programs"], route_class=SafeProgramRoute)


@router.post("/preview", response_model=SwimProgramPreviewResponse)
def preview(request: SwimProgramPreviewRequest, db: Database = Depends(get_database)) -> dict[str, Any]:
    return store.create_preview(db, request.document.model_dump(mode="json"), base_revision=request.base_revision)


@router.post("/confirm", response_model=SwimProgramVersionResponse)
def confirm(request: SwimProgramConfirmRequest, db: Database = Depends(get_database)) -> dict[str, Any]:
    return swim_programs.confirm(db, str(request.preview_id))


@router.get("", response_model=SwimProgramListResponse)
def programs(db: Database = Depends(get_database)) -> dict[str, Any]:
    return {"items": store.list_programs(db)}


@router.get("/{program_id}", response_model=SwimProgramVersionResponse)
def current(program_id: UUID, db: Database = Depends(get_database)) -> dict[str, Any]:
    return store.get_version(db, str(program_id))


@router.get("/{program_id}/versions/{revision}", response_model=SwimProgramVersionResponse)
def historical(program_id: UUID, revision: Annotated[int, Path(ge=1)], db: Database = Depends(get_database)) -> dict[str, Any]:
    return store.get_version(db, str(program_id), revision=revision)
