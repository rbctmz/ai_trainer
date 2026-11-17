"""Explicit Coach import endpoint, separate from readiness/planning side effects."""

from typing import Any, Awaitable, Callable

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.requests import Request
from starlette.responses import Response

from api.deps import get_database
from api.routers.swim_programs import SafeProgramRoute
from api.swim_coach_contract import SwimCoachTurnRequest
from api.swim_coach_service import prepare_turn, SwimCoachTurnError
from data.database import Database


class SafeSwimCoachRoute(SafeProgramRoute):
    invalid_request_code = "swim_coach_invalid_request"

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await original(request)
            except SwimCoachTurnError as exc:
                return JSONResponse(
                    status_code=exc.status, content={"detail": exc.detail}
                )

        return handle


router = APIRouter(route_class=SafeSwimCoachRoute)


@router.post("/swim-import")
def swim_import(
    request: SwimCoachTurnRequest, db: Database = Depends(get_database)
) -> StreamingResponse:
    # Resolve factories at request time, preserving the existing Coach boundary.
    from api.routers import coach

    events = prepare_turn(
        db,
        request,
        provider_resolver=coach.resolve_provider,
        chat_manager_factory=coach._chat_manager,
    )

    def stream() -> Any:
        for event in events:
            yield coach._sse(event)

    return StreamingResponse(stream(), media_type="text/event-stream")
