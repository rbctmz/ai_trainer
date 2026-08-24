"""Coach endpoints: streaming chat + history."""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.coach_service import resolve_provider, stream_tokens, supports_streaming
from api.deps import get_database
from api.operational_state import build_operational_state, latest_iso_from_database
from api.readiness_conflicts import build_readiness_conflict_report
from api.readiness_snapshot import build_readiness_snapshot
from api.recovery_replan_loop import run_recovery_replan_loop
from api.today_snapshot import build_coach_session_evidence
from config.settings import Settings
from data.database import Database
from models.ai_coach_runtime import (
    apply_response_contract_to_final_response,
    build_grounding_tool_results,
    create_chat_synthesis_system_prompt,
    build_chat_synthesis_prompt,
    resolve_turn_tool_results,
    synthesize_ai_chat_response,
)
from models.coach_decisions import CoachDecision, build_coach_decision
from models.coach_narrative_evidence import (
    build_coach_narrative_evidence,
    fail_closed_coach_narrative,
    validate_coach_narrative,
)
from models.ai_tools import AITools
from models.chat_manager import ChatManager
from api.planning_service import get_active_plan
from models.coach_tool_presenter import format_tool_result
from services.intervals_plan_delivery import athlete_local_date
from utils.product_semantics import tool_label

router = APIRouter(prefix="/api/coach", tags=["coach"])


class ChatRequest(BaseModel):
    message: str
    chat_id: Optional[str] = None
    context_days: int = 30
    provider: Optional[str] = None


class ChatRenameRequest(BaseModel):
    title: str


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _chat_manager() -> ChatManager:
    # Honors Settings.CHATS_DIR, so acceptance/demo isolation keeps working.
    return ChatManager()


@router.post("/chat")
def coach_chat(
    req: ChatRequest,
    db: Database = Depends(get_database),
    demo: bool = False,
) -> StreamingResponse:
    request_started_at = time.monotonic()
    message = (req.message or "").strip()
    if not message:
        raise HTTPException(status_code=422, detail="message is empty")

    provider = resolve_provider(req.provider)
    if provider is None:
        raise HTTPException(
            status_code=503,
            detail="No AI provider available. Set a key in .env (e.g. DEEPSEEK_API_KEY).",
        )

    chat_manager = _chat_manager()
    chat_id = req.chat_id or chat_manager.create_new_chat()
    decision_event_id = str(uuid.uuid4())
    observed_at_utc = datetime.now(timezone.utc)
    try:
        local_today = athlete_local_date(observed_at_utc)
    except Exception:
        local_today = None
    chat_manager.add_message(chat_id, "user", message)
    history = chat_manager.get_chat_messages(chat_id)[:-1]
    ai_tools = AITools(db)
    load_metrics_context = _load_metrics_context(ai_tools)
    goal_plan = get_active_plan(db)
    latest_data_at = latest_iso_from_database(db)
    has_data = latest_data_at is not None
    readiness_snapshot = (
        build_readiness_snapshot(
            db,
            as_of=local_today,
            observed_at_utc=observed_at_utc,
        )
        if local_today is not None
        else {
            "score": None,
            "status": "unknown",
            "reason": "ATHLETE_TIMEZONE is invalid.",
            "missing_inputs": ["sleep", "hrv", "resting_hr"],
        }
    )
    if local_today is not None:
        try:
            session_evidence = build_coach_session_evidence(
                db,
                as_of=local_today,
            )
        except Exception:
            session_evidence = {"status": "unavailable", "rows": []}
    else:
        session_evidence = {"status": "unavailable", "rows": []}
    try:
        if local_today is None:
            raise ValueError("ATHLETE_TIMEZONE is invalid")
        recovery_replan = run_recovery_replan_loop(
            db,
            today=local_today,
            decision_event_id=decision_event_id,
        )
        readiness_conflicts = recovery_replan["readiness_conflicts"]
    except Exception as exc:
        # Audit persistence must never block a coach answer.
        readiness_conflicts = (
            build_readiness_conflict_report(db, today=local_today)
            if local_today is not None
            else {"data_gap": True, "reason": str(exc), "conflicts": []}
        )
        recovery_replan = {
            "outcome": "error",
            "decision": None,
            "proposal": None,
            "proposal_gap": str(exc),
            "readiness_conflicts": readiness_conflicts,
        }

    def stream() -> Iterator[str]:
        message_id = str(uuid.uuid4())[:8]
        # ASR-PERF-2 (Issue #241): time-to-first-token, observation not a
        # gate — provider latency isn't deterministic even across live runs.
        first_token_ms: Optional[float] = None
        yield _sse(
            {
                "type": "meta",
                "chat_id": chat_id,
                "metrics_window_days": load_metrics_context.get("metrics_window_days"),
                "as_of_date": load_metrics_context.get("as_of_date"),
                "load_metrics": load_metrics_context,
                "readiness_snapshot": readiness_snapshot,
                "readiness_conflicts": readiness_conflicts,
                "recovery_replan": recovery_replan,
                "operational_state": build_operational_state(
                    db,
                    demo=demo,
                    has_data=has_data,
                    latest_data_at=latest_data_at,
                ),
            }
        )
        recovery_proposal = recovery_replan.get("proposal")
        if isinstance(recovery_proposal, dict) and recovery_proposal.get("status") == "pending":
            yield _sse(
                {
                    "type": "proposal",
                    "proposal_id": recovery_proposal.get("id"),
                    "action": recovery_proposal.get("action"),
                    "status": recovery_proposal.get("status"),
                    "params": recovery_proposal.get("params") or {},
                    "preview": recovery_proposal.get("preview") or {},
                }
            )
        try:
            # Скрытый шаг выбора инструментов: нативный tools-цикл для
            # провайдеров с function calling, маркерный первый проход — для
            # остальных (Issue #190). Форма tool_results одинаковая.
            turn = resolve_turn_tool_results(
                provider=provider,
                ai_tools=ai_tools,
                user_input=message,
                history_messages=history,
                tool_result_formatter=format_tool_result,
            )
            _rendered_response = turn["rendered_response"]
            tool_results = turn["tool_results"]
            native_used = bool(turn["native"])
            grounding_used = False
            if not tool_results:
                # Ни одного вызова инструментов ни на одном из путей — без
                # данных сырой ответ уходит сфабрикованным (issue #188).
                # Собираем базовый набор реальных данных и синтезируем по ним.
                tool_results = build_grounding_tool_results(ai_tools, format_tool_result)
                grounding_used = bool(tool_results)

            for item in tool_results:
                yield _sse(
                    {
                        "type": "tool_call",
                        "name": tool_label(item["tool_name"]),
                        "tool_name": item["tool_name"],
                        "status": "done",
                        "auto": grounding_used,
                        "native": native_used and not grounding_used,
                    }
                )
                raw_result = item.get("raw_result") or {}
                if raw_result.get("is_proposal"):
                    saved_proposal = db.save_coach_proposal(
                        action=raw_result.get("action"),
                        params=raw_result.get("params", {}),
                        preview=raw_result.get("preview", {}),
                        chat_id=chat_id,
                        message_id=message_id,
                        decision_event_id=decision_event_id,
                        source="coach_tool",
                    )
                    yield _sse(
                        {
                            "type": "proposal",
                            "proposal_id": saved_proposal.get("id"),
                            "action": raw_result.get("action"),
                            "status": saved_proposal.get("status"),
                            "params": raw_result.get("params", {}),
                            "preview": raw_result.get("preview", {}),
                        }
                    )

            if tool_results and supports_streaming(provider):
                synthesis_prompt = build_chat_synthesis_prompt(
                    history_messages=history,
                    user_input=message,
                    tool_results=tool_results,
                )
                synthesis_system_prompt = create_chat_synthesis_system_prompt(goal_plan=goal_plan)
                streamed_final = ""
                for delta in stream_tokens(
                    provider,
                    synthesis_prompt,
                    system_prompt=synthesis_system_prompt,
                ):
                    streamed_final += delta

                final = (
                    apply_response_contract_to_final_response(streamed_final, None)
                    if streamed_final.strip()
                    else _rendered_response
                )
            else:
                # Инструменты уже выполнены выше — синтезируем напрямую,
                # не прогоняя их второй раз через finalize_ai_chat_response.
                if tool_results:
                    final = (
                        synthesize_ai_chat_response(
                            provider=provider,
                            history_messages=history,
                            user_input=message,
                            tool_results=tool_results,
                            goal_plan=goal_plan,
                        )
                        or _rendered_response
                    )
                else:
                    final = _rendered_response
                final = apply_response_contract_to_final_response(final, None)

            try:
                evidence = build_coach_narrative_evidence(
                    readiness_snapshot=readiness_snapshot,
                    tool_results=tool_results,
                    session_evidence=session_evidence,
                    goal_plan=goal_plan,
                    athlete_timezone=Settings.ATHLETE_TIMEZONE,
                    observed_at_utc=observed_at_utc,
                )
                gate_result = validate_coach_narrative(final, evidence)
            except Exception:
                gate_result = fail_closed_coach_narrative()
            final = gate_result.delivered_text
            for chunk in _chunk(final):
                if first_token_ms is None:
                    first_token_ms = (time.monotonic() - request_started_at) * 1000
                yield _sse({"type": "token", "content": chunk})

            _save_decision(
                db,
                final,
                chat_id=chat_id,
                message_id=message_id,
                decision_event_id=decision_event_id,
                load_metrics_context=load_metrics_context,
                evidence_gate=gate_result.metadata(),
            )
            chat_manager.add_message(chat_id, "assistant", final)

            yield _sse(
                {
                    "type": "done",
                    "message_id": message_id,
                    "chat_id": chat_id,
                    "first_token_ms": first_token_ms,
                    "evidence_gate": gate_result.metadata(),
                }
            )
        except Exception as exc:  # surface errors to the client instead of hanging
            error_message = str(exc)
            yield _sse(
                {
                    "type": "error",
                    "message": error_message,
                    "readiness_snapshot": readiness_snapshot,
                    "operational_state": build_operational_state(
                        db,
                        demo=demo,
                        has_data=has_data,
                        latest_data_at=latest_data_at,
                        error={"message": error_message},
                    ),
                }
            )

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/history")
def coach_history(
    scope: str = "all",
    demo: bool = False,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    if scope not in {"all", "active", "archive"}:
        raise HTTPException(status_code=422, detail="scope must be all, active or archive")
    chats = _chat_manager().get_chat_list(scope=scope)
    return {
        "chats": [
            {
                "id": c["id"],
                "title": c["title"],
                "date": c.get("updated_at"),
                "message_count": c.get("message_count", 0),
                "archived": bool(c.get("archived", False)),
                "preview": c.get("preview", ""),
            }
            for c in chats
        ],
        "operational_state": build_operational_state(
            db,
            demo=demo,
            has_data=latest_iso_from_database(db) is not None,
        ),
    }


@router.get("/history/{chat_id}")
def coach_history_detail(
    chat_id: str,
    demo: bool = False,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    chat = _chat_manager().load_chat(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return {
        "id": chat["id"],
        "title": chat["title"],
        "archived": bool(chat.get("archived", False)),
        "created_at": chat.get("created_at"),
        "updated_at": chat.get("updated_at"),
        "messages": [
            {
                "role": m.get("role"),
                "content": m.get("content"),
                "timestamp": m.get("timestamp"),
            }
            for m in chat.get("messages", [])
        ],
        "operational_state": build_operational_state(
            db,
            demo=demo,
            has_data=latest_iso_from_database(db) is not None,
        ),
    }


@router.post("/chats/{chat_id}/rename")
def coach_chat_rename(chat_id: str, req: ChatRenameRequest) -> dict[str, Any]:
    manager = _chat_manager()
    try:
        updated = manager.update_chat_title(chat_id, req.title)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not updated:
        raise HTTPException(status_code=404, detail="chat not found")
    chat = manager.load_chat(chat_id)
    return {"id": chat_id, "title": chat["title"] if chat else req.title}


@router.post("/chats/{chat_id}/archive")
def coach_chat_archive(chat_id: str) -> dict[str, Any]:
    manager = _chat_manager()
    try:
        updated = manager.set_archived(chat_id, True)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid chat id")
    if not updated:
        raise HTTPException(status_code=404, detail="chat not found")
    return {"id": chat_id, "archived": True}


@router.post("/chats/{chat_id}/restore")
def coach_chat_restore(chat_id: str) -> dict[str, Any]:
    manager = _chat_manager()
    try:
        updated = manager.set_archived(chat_id, False)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid chat id")
    if not updated:
        raise HTTPException(status_code=404, detail="chat not found")
    return {"id": chat_id, "archived": False}


@router.delete("/chats/{chat_id}")
def coach_chat_delete(chat_id: str) -> dict[str, Any]:
    manager = _chat_manager()
    try:
        deleted = manager.delete_chat(chat_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid chat id")
    if not deleted:
        raise HTTPException(status_code=404, detail="chat not found")
    return {"id": chat_id, "deleted": True}


@router.get("/search")
def coach_search(
    q: str = "",
    scope: str = "all",
) -> dict[str, Any]:
    if scope not in {"all", "active", "archive"}:
        raise HTTPException(status_code=422, detail="scope must be all, active or archive")
    chats = _chat_manager().search_chats(q, scope=scope)
    return {
        "query": q,
        "chats": [
            {
                "id": c["id"],
                "title": c["title"],
                "date": c.get("updated_at"),
                "message_count": c.get("message_count", 0),
                "archived": bool(c.get("archived", False)),
                "preview": c.get("preview", ""),
            }
            for c in chats
        ],
    }


def _chunk(text: str) -> Iterator[str]:
    """Yield text in small word-group chunks for a streaming feel."""
    words = (text or "").split(" ")
    group = 4
    for i in range(0, len(words), group):
        piece = " ".join(words[i : i + group])
        yield piece if i + group >= len(words) else piece + " "


def _load_metrics_context(ai_tools: AITools) -> dict[str, Any]:
    try:
        metrics = ai_tools.get_performance_metrics()
    except Exception:
        return {}
    if not isinstance(metrics, dict):
        return {}
    return {
        "ctl": metrics.get("ctl"),
        "atl": metrics.get("atl"),
        "tsb": metrics.get("tsb"),
        "metrics_window_days": metrics.get("metrics_window_days"),
        "as_of_date": metrics.get("as_of_date"),
    }


def _save_decision(
    db: Database,
    final: str,
    *,
    chat_id: str,
    message_id: str,
    decision_event_id: str,
    load_metrics_context: dict[str, Any] | None = None,
    evidence_gate: dict[str, Any] | None = None,
) -> None:
    try:
        gate = dict(evidence_gate or {})
        if gate.get("outcome") in {"replaced", "data_gap"}:
            codes = ", ".join(str(code) for code in gate.get("reason_codes") or [])
            decision = CoachDecision(
                "Monitor",
                f"Evidence gate отклонил вывод коуча: {codes or 'reason unavailable'}.",
            )
        else:
            decision = build_coach_decision(final, db=db)
        load_metrics_context = load_metrics_context or {}
        db.save_coach_decision(
            decision_type=decision.decision_type,
            reason=decision.reason,
            workout_id=decision.workout_id,
            chat_id=chat_id,
            message_id=message_id,
            decision_event_id=decision_event_id,
            metrics_window_days=load_metrics_context.get("metrics_window_days"),
            as_of_date=load_metrics_context.get("as_of_date"),
            narrative_gate=evidence_gate,
        )
    except Exception:
        # Decision logging must not block the coach answer delivery.
        return
