"""Selected-store exercise catalog; errors never echo private source values."""

from typing import Annotated, Any, Awaitable, Callable
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.requests import Request
from starlette.responses import Response
from api.deps import get_database
from api.swim_exercise_contract import (
    SwimExerciseConfirmRequest,
    SwimExerciseListResponse,
    SwimExercisePreviewRequest,
    SwimExercisePreviewResponse,
    SwimExerciseResolveRequest,
    SwimExerciseResolveResponse,
    SwimExerciseVersionResponse,
)
from data.database import Database
from data import swim_exercise_store as store
from models.swim_exercise import exercise_fingerprint
from services import swim_exercises


class SafeExerciseRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError:
                return JSONResponse(
                    status_code=422,
                    content={"detail": {"code": "swim_exercise_invalid_request"}},
                )
            except store.SwimExerciseError as exc:
                raise HTTPException(
                    status_code=exc.status, detail={"code": exc.code}
                ) from exc

        return handle


router = APIRouter(
    prefix="/api/swim-exercises", tags=["swim-exercises"], route_class=SafeExerciseRoute
)


@router.post("/preview", response_model=SwimExercisePreviewResponse)
def preview(request: SwimExercisePreviewRequest) -> dict[str, Any]:
    return {
        "document": request.document.model_dump(mode="json"),
        "fingerprint": exercise_fingerprint(request.document),
    }


@router.post("/confirm", response_model=SwimExerciseVersionResponse)
def confirm(
    request: SwimExerciseConfirmRequest, db: Database = Depends(get_database)
) -> dict[str, Any]:
    return swim_exercises.confirm(
        db,
        request.document,
        base_revision=request.base_revision,
        request_id=str(request.request_id),
        fingerprint=request.fingerprint,
    )


@router.post("/resolve", response_model=SwimExerciseResolveResponse)
def resolve(
    request: SwimExerciseResolveRequest, db: Database = Depends(get_database)
) -> dict[str, Any]:
    return swim_exercises.resolve(
        db,
        exercise_id=str(request.exercise_id),
        revision=request.revision,
        node_id=request.node_id,
        distance_meters=request.distance_meters,
        instructions=request.instructions,
    )


@router.get("", response_model=SwimExerciseListResponse)
def exercises(
    q: Annotated[str, Query(max_length=200)] = "", db: Database = Depends(get_database)
) -> dict[str, Any]:
    return {"items": store.list_exercises(db, query=q)}


@router.get("/{exercise_id}", response_model=SwimExerciseVersionResponse)
def current(exercise_id: UUID, db: Database = Depends(get_database)) -> dict[str, Any]:
    return store.get_version(db, str(exercise_id))


@router.get(
    "/{exercise_id}/versions/{revision}", response_model=SwimExerciseVersionResponse
)
def historical(
    exercise_id: UUID,
    revision: Annotated[int, Path(ge=1)],
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    return store.get_version(db, str(exercise_id), revision=revision)
