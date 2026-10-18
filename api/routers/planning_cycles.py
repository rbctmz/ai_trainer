"""Safe cycle boundary; reads never select, commands require explicit identity."""
from __future__ import annotations

import sqlite3
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import ValidationError

from api.deps import get_database
from api.planning_cycle_contract import (
    CloseCycleRequest, CycleCommandResponse, CycleContext, CycleHistoryResponse,
    ResolveConstraintScopeRequest, SetEventOutcomeRequest,
)
from data.database import Database
from models.planning_build_confirmation import canonical_json
from models.planning_cycle import CycleCommandError, CycleNotFound, CycleStateCorrupt
from services.planning_cycle_commands import execute_cycle_command
from services.planning_cycles import current_cycle_context, cycle_history, historical_cycle_context


def _error(status: int, code: str, detail: str, retryable: bool = False) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail, "code": code, "retryable": retryable})


class CycleRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def safe_handler(request):
            try:
                return await handler(request)
            except RequestValidationError:
                return _error(422, "invalid_cycle_request", "Проверьте параметры команды или цикла.")
            except CycleCommandError as exc:
                return _error(exc.status, exc.code, str(exc), exc.retryable)
            except CycleNotFound:
                return _error(404, "cycle_not_found", "Цикл не найден.")
            except (CycleStateCorrupt, ValidationError, ResponseValidationError, ValueError, TypeError):
                return _error(500, "cycle_corrupt", "Данные цикла повреждены; требуется проверка хранилища.")
            except sqlite3.OperationalError as exc:
                if getattr(exc, "sqlite_errorcode", 0) & 255 in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
                    return _error(503, "planning_busy", "Хранилище занято — повторите ту же команду.", True)
                return _error(500, "cycle_storage_error", "Не удалось проверить сохранение команды; повторите тот же ID.", True)
            except Exception:
                return _error(500, "cycle_storage_error", "Не удалось проверить сохранение команды; повторите тот же ID.", True)
        return safe_handler


router = APIRouter(prefix="/api/planning/cycles", tags=["planning"], route_class=CycleRoute)


def _validate_command_response(payload: dict) -> None:
    CycleCommandResponse.model_validate(payload)
    # Model validation alone may accept non-finite values inside retained/raw
    # metadata. Ensure the complete response is JSON-safe BEFORE committing.
    canonical_json(payload)


@router.get("/current", response_model=CycleContext)
def current(db: Database = Depends(get_database)):
    return current_cycle_context(db)


@router.get("", response_model=CycleHistoryResponse)
def history(limit: int = Query(50, ge=1, le=50), db: Database = Depends(get_database)):
    return {"cycles": cycle_history(db, limit=limit)}


@router.post("/constraint-scope", response_model=CycleCommandResponse)
def resolve_scope(req: ResolveConstraintScopeRequest, db: Database = Depends(get_database)):
    return execute_cycle_command(db, "resolve_constraint_scope", req.model_dump(mode="json"),
                                 validate_response=_validate_command_response)


@router.get("/{cycle_id}", response_model=CycleContext)
def historical(cycle_id: UUID, db: Database = Depends(get_database)):
    return historical_cycle_context(db, str(cycle_id))


@router.post("/{cycle_id}/close", response_model=CycleCommandResponse)
def close(cycle_id: UUID, req: CloseCycleRequest, db: Database = Depends(get_database)):
    return execute_cycle_command(db, "close", req.model_dump(mode="json"), cycle_id=str(cycle_id),
                                 validate_response=_validate_command_response)


@router.post("/{cycle_id}/event-outcome", response_model=CycleCommandResponse)
def set_outcome(cycle_id: UUID, req: SetEventOutcomeRequest, db: Database = Depends(get_database)):
    return execute_cycle_command(db, "set_event_outcome", req.model_dump(mode="json"), cycle_id=str(cycle_id),
                                 validate_response=_validate_command_response)
