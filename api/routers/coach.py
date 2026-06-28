"""Coach endpoints: streaming chat + history."""
from __future__ import annotations

import json
import uuid
from typing import Any, Iterator, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.coach_service import resolve_provider, stream_tokens, supports_streaming
from api.deps import get_database
from data.database import Database
from models.ai_coach_runtime import (
    apply_response_contract_to_final_response,
    collect_tool_results,
    create_chat_synthesis_system_prompt,
    build_chat_synthesis_prompt,
    finalize_ai_chat_response,
    generate_ai_chat_response,
)
from models.ai_tools import AITools
from models.chat_manager import ChatManager
from ui.components.ai_coach_output import format_tool_result
from utils.product_semantics import tool_label

router = APIRouter(prefix="/api/coach", tags=["coach"])


class ChatRequest(BaseModel):
    message: str
    chat_id: Optional[str] = None
    context_days: int = 30
    provider: Optional[str] = None


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _chat_manager() -> ChatManager:
    # Honors Settings.CHATS_DIR, so acceptance/demo isolation keeps working.
    return ChatManager()


@router.post("/chat")
def coach_chat(req: ChatRequest, db: Database = Depends(get_database)) -> StreamingResponse:
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
    chat_manager.add_message(chat_id, "user", message)
    history = chat_manager.get_chat_messages(chat_id)[:-1]
    ai_tools = AITools(db)

    def stream() -> Iterator[str]:
        yield _sse({"type": "meta", "chat_id": chat_id})
        try:
            # First pass: hidden planning/tool-selection step.
            raw = generate_ai_chat_response(
                provider=provider,
                ai_tools=ai_tools,
                user_input=message,
                history_messages=history,
            )
            _rendered_response, tool_results = collect_tool_results(
                raw,
                ai_tools,
                format_tool_result,
            )

            for item in tool_results:
                yield _sse(
                    {
                        "type": "tool_call",
                        "name": tool_label(item["tool_name"]),
                        "tool_name": item["tool_name"],
                        "status": "done",
                    }
                )
                raw_result = item.get("raw_result") or {}
                if raw_result.get("is_proposal"):
                    yield _sse(
                        {
                            "type": "proposal",
                            "action": raw_result.get("action"),
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
                synthesis_system_prompt = create_chat_synthesis_system_prompt()
                streamed_final = ""
                for delta in stream_tokens(
                    provider,
                    synthesis_prompt,
                    system_prompt=synthesis_system_prompt,
                ):
                    streamed_final += delta
                    yield _sse({"type": "token", "content": delta})

                final = (
                    apply_response_contract_to_final_response(streamed_final, None)
                    if streamed_final.strip()
                    else _rendered_response
                )
            else:
                final = finalize_ai_chat_response(
                    raw,
                    ai_tools,
                    format_tool_result,
                    response_contract=None,
                    provider=provider,
                    user_input=message,
                    history_messages=history,
                )
                for chunk in _chunk(final):
                    yield _sse({"type": "token", "content": chunk})

            chat_manager.add_message(chat_id, "assistant", final)

            yield _sse({"type": "done", "message_id": str(uuid.uuid4())[:8], "chat_id": chat_id})
        except Exception as exc:  # surface errors to the client instead of hanging
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/history")
def coach_history() -> dict[str, Any]:
    chats = _chat_manager().get_chat_list()
    return {
        "chats": [
            {
                "id": c["id"],
                "title": c["title"],
                "date": c.get("updated_at"),
                "message_count": c.get("message_count", 0),
            }
            for c in chats
        ]
    }


@router.get("/history/{chat_id}")
def coach_history_detail(chat_id: str) -> dict[str, Any]:
    chat = _chat_manager().load_chat(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return {
        "id": chat["id"],
        "title": chat["title"],
        "messages": [
            {
                "role": m.get("role"),
                "content": m.get("content"),
                "timestamp": m.get("timestamp"),
            }
            for m in chat.get("messages", [])
        ],
    }


def _chunk(text: str) -> Iterator[str]:
    """Yield text in small word-group chunks for a streaming feel."""
    words = (text or "").split(" ")
    group = 4
    for i in range(0, len(words), group):
        piece = " ".join(words[i : i + group])
        yield piece if i + group >= len(words) else piece + " "
