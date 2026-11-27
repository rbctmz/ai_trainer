"""Import-only Coach turns: source first, bounded native tools, server status."""

from typing import Any, Callable, Iterator

from api.swim_coach_contract import SWIM_COACH_EVENT, SwimCoachTurnRequest
from data import swim_import_store as drafts
from models.ai_coach_runtime import NativeToolProviderError, run_native_tool_loop
from models.swim_coach_tools import (
    SwimCoachTools,
    TOOL_SPECS,
    draft_questions,
    contains_completion_claim,
)
from models.swim_program import canonical_json

LABELS = {
    "get_swim_import": "Просмотр программы",
    "search_swim_exercises": "Поиск упражнения",
    "get_swim_exercise": "Просмотр варианта упражнения",
    "get_swim_program": "Просмотр библиотеки",
    "parse_swim_import": "Разбор программы тренера",
    "patch_swim_import": "Правка черновика",
    "ask_swim_import_question": "Уточнение задания",
    "unsupported": "Недоступное действие",
}

PROVIDER_ERRORS = {
    "swim_coach_provider_payment_required": "На балансе провайдера ИИ недостаточно средств.",
    "swim_coach_provider_failed": "Провайдер ИИ не смог обработать запрос.",
}


class SwimCoachTurnError(ValueError):
    def __init__(self, code: str, status: int, request: SwimCoachTurnRequest):
        self.code, self.status = code, status
        self.detail = {
            "code": code,
            "import_id": str(request.import_id),
            "revision": request.expected_revision,
        }
        super().__init__(code)


def _event(**value: Any) -> dict[str, Any]:
    return SWIM_COACH_EVENT.validate_python(value).model_dump(mode="json")


def prepare_turn(
    db: Any,
    request: SwimCoachTurnRequest,
    *,
    provider_resolver: Callable,
    chat_manager_factory: Callable,
) -> Iterator[dict[str, Any]]:
    """Preflight synchronously before creating a stream or touching a provider."""
    try:
        tools = SwimCoachTools(
            db,
            import_id=str(request.import_id),
            expected_revision=request.expected_revision,
            request_id=str(request.request_id),
        )
    except drafts.SwimImportError as exc:
        raise SwimCoachTurnError(exc.code, exc.status, request) from exc
    try:
        provider = provider_resolver(request.provider)
        if provider is None:
            raise SwimCoachTurnError("swim_coach_provider_unavailable", 503, request)
        available = getattr(provider, "is_available", None)
        if callable(available) and not available():
            raise SwimCoachTurnError("swim_coach_provider_unavailable", 503, request)
        supports = getattr(provider, "supports_native_tools", None)
        if (
            not callable(supports)
            or not supports()
            or not callable(getattr(provider, "generate_with_tools", None))
        ):
            raise SwimCoachTurnError("swim_coach_native_required", 422, request)
    except SwimCoachTurnError:
        raise
    except Exception as exc:
        raise SwimCoachTurnError(
            "swim_coach_provider_unavailable", 503, request
        ) from exc
    try:
        manager = chat_manager_factory()
        chat_id = request.chat_id or manager.create_new_chat("Программа тренера")
        if manager.load_chat(chat_id) is None:
            raise SwimCoachTurnError("swim_coach_chat_not_found", 404, request)
        history = manager.get_chat_messages(chat_id)
        if not manager.add_message(chat_id, "user", request.message):
            raise OSError("chat write unavailable")
    except SwimCoachTurnError:
        raise
    except Exception as exc:
        raise SwimCoachTurnError(
            "swim_coach_history_unavailable", 503, request
        ) from exc
    return _stream_turn(db, request, tools, provider, manager, chat_id, history)


def _stream_turn(
    db: Any,
    request: SwimCoachTurnRequest,
    tools: SwimCoachTools,
    provider: Any,
    manager: Any,
    chat_id: str,
    history: list,
) -> Iterator[dict[str, Any]]:
    yield _event(type="meta", chat_id=chat_id, import_id=request.import_id)
    code = None
    results = []
    try:
        # Free-form model text is deliberately not a completion/status receipt.
        _untrusted_text, results = run_native_tool_loop(
            provider,
            tools,
            request.message,
            history,
            lambda _name, data: canonical_json(data),
            max_rounds=2,
            system_prompt_override=tools.system_prompt(),
            raise_provider_errors=True,
        )
        if any(not result["success"] for result in results):
            code = (
                "swim_coach_unverified_claim"
                if any(
                    call["code"] == "swim_coach_unverified_claim"
                    for call in tools.calls
                )
                else "swim_coach_tool_failed"
            )
    except NativeToolProviderError as exc:
        results = exc.tool_results
        code = (
            "swim_coach_provider_payment_required"
            if exc.code == "payment_required"
            else "swim_coach_provider_failed"
        )
    except Exception:
        # A previous successful write may already be committed: always read back.
        code = "swim_coach_provider_failed"
    for result in results:
        name = (
            result["tool_name"] if result["tool_name"] in TOOL_SPECS else "unsupported"
        )
        yield _event(
            type="tool_call",
            name=LABELS[name],
            tool_name=name,
            status="done" if result["success"] else "error",
            native=True,
        )
    try:
        current = drafts.get_draft(db, str(request.import_id))
        revision = current["revision"]
        readback_status = "current"
        if revision != request.expected_revision + int(tools.mutated):
            code = "swim_import_stale"
        questions = list(
            dict.fromkeys([*tools.questions, *draft_questions(current["document"])])
        )[:10]
        if any(contains_completion_claim(q) for q in questions):
            code = code or "swim_coach_unverified_claim"
            questions = [q for q in questions if not contains_completion_claim(q)]
        status = "draft" if current["document"] is not None else "unparsed"
    except drafts.SwimImportError as exc:
        revision = tools.last_confirmed_revision
        readback_status = "unavailable"
        questions, status, code = [], "error", exc.code
    if code is not None:
        status = "error"
        if text := PROVIDER_ERRORS.get(code):
            text += (
                " Черновик уже обновился. Проверьте изменения перед повтором."
                if tools.mutated
                else " Исходник сохранён."
            )
        else:
            text = "Не удалось завершить ответ Коуча. Откройте актуальный черновик и проверьте результат."
    elif tools.mutated:
        text = "Черновик обновлён. Проверьте программу и подтвердите сохранение."
    elif questions:
        text = "Нужно уточнить задание тренера."
    else:
        code = "swim_coach_no_change"
        text = (
            "Коуч ответил, но не запустил разбор. Исходник сохранён."
            if status == "unparsed"
            else "Коуч ответил. Черновик остался без изменений."
        )
    if questions:
        text += "\n\n" + "\n".join(f"• {question}" for question in questions)
    try:
        if not manager.add_message(chat_id, "assistant", text):
            raise OSError("chat write unavailable")
    except Exception:
        status, code = "error", "swim_coach_history_unavailable"
        text = "История диалога недоступна. Откройте актуальный черновик и проверьте результат."
    yield _event(
        type="swim_import",
        import_id=request.import_id,
        revision=revision,
        status=status,
        code=code,
        library_saved=False,
        readback_status=readback_status,
    )
    yield _event(type="token", content=text)
    yield _event(
        type="done",
        chat_id=chat_id,
        import_id=request.import_id,
        revision=revision,
        readback_status=readback_status,
    )
