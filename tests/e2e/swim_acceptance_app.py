"""Owned E2E app only: synthetic native calls through the real Coach/store routes.

This is transport/UI integration evidence, not live model interpretation evidence.
Never import this module into the production application.
"""

import json
import os

from scripts.acceptance_launcher import validate_acceptance_child_environment
from scripts.scratch_runtime import scope_from_environment

if os.environ.get("AI_TRAINER_E2E_SCOPE") != "1" or scope_from_environment() is None:
    raise RuntimeError("swim acceptance requires an owned E2E scope")
validate_acceptance_child_environment(dict(os.environ))

from api.main import app  # noqa: E402,F401
from api.deps import get_database  # noqa: E402
from api.routers import coach  # noqa: E402
from fastapi import Depends  # noqa: E402
from data.database import Database  # noqa: E402
from uuid import UUID  # noqa: E402
from tests.smoke._swim_import_fixtures import exact_program_v2  # noqa: E402
from services import swim_delivery  # noqa: E402
from tests.swim_delivery_fixtures import IntervalsSandbox  # noqa: E402


class SyntheticNativeProvider:
    """Only the named anonymous fixture; no network, environment or AI SDK."""

    def supports_native_tools(self):
        return True

    def generate_with_tools(self, messages, tools, system_prompt=""):
        draft = json.loads(system_prompt.split("\nSOURCE_DATA_JSON\n", 1)[1])
        document = exact_program_v2()
        if draft["source_text"] != document["source_text"]:
            raise RuntimeError("unsupported synthetic source")
        if messages[-1]["role"] == "tool":
            return {"text": "UNTRUSTED_COMPLETION_CANARY saved and sent", "tool_calls": []}
        message = messages[-1]["content"]
        if draft["document"] is None:
            calls = [
                {"id": "parse", "name": "parse_swim_import", "arguments": {
                    "content": {key: document[key] for key in ("title", "source_spans", "workouts")}
                }},
                {"id": "question", "name": "ask_swim_import_question", "arguments": {
                    "question": "Оставить бассейн 25 м или выбрать 50 м?"
                }},
            ]
        elif message == "Первую тренировку в бассейне 50 м":
            calls = [{"id": "context", "name": "patch_swim_import", "arguments": {
                "operation": {"op": "set_context", "workout_id": "one", "environment": "pool", "pool_length_meters": 50}
            }}]
        else:
            calls = [{"id": "question", "name": "ask_swim_import_question", "arguments": {
                "question": "Какой элемент программы нужно изменить?"
            }}]
        return {"text": "", "tool_calls": calls}


coach.resolve_provider = lambda _: SyntheticNativeProvider()


@app.post("/_e2e/swim-previews/{preview_id}/expire")
def expire_preview(preview_id: UUID, db: Database = Depends(get_database)):
    """Explicit owned-test fault, never registered by api.main production imports."""
    conn = db._connect()
    try:
        conn.execute("UPDATE swim_program_previews SET expires_at=? WHERE preview_id=?", ("2000-01-01T00:00:00+00:00", str(preview_id)))
        conn.commit()
    finally:
        conn.close()
    return {"expired": str(preview_id)}


delivery_transport = IntervalsSandbox()
swim_delivery.get_client = lambda: delivery_transport


@app.get("/_e2e/swim-delivery-state")
def swim_delivery_state():
    return {"creates": delivery_transport.creates}
