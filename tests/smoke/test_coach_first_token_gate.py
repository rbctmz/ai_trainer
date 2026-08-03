"""BDD gate for TD-007 (#352): deterministic coach first-token latency budget.

ASR-PERF-2: the SSE `done` event reports `first_token_ms`, but the 5-second
budget was only an observation. This test turns it into a deterministic gate on
the controlled local runtime (`provider="mock"`, temporary database, no network):
the first token must arrive within `COACH_FIRST_TOKEN_BUDGET_MS`. Live provider
latency stays an observed metric and is never gated here.
"""
from __future__ import annotations

import asyncio
import json
import time

import pytest

from data.database import Database


pytestmark = pytest.mark.smoke


async def _first_token_elapsed_ms(response) -> float:
    started = time.monotonic()
    async for raw in response.body_iterator:
        text = raw if isinstance(raw, str) else raw.decode()
        if not text.startswith("data:"):
            continue
        event = json.loads(text[5:].strip())
        if event.get("type") == "token":
            return (time.monotonic() - started) * 1000
    raise AssertionError("stream completed without a token event")


def test_coach_first_token_arrives_within_budget(tmp_path, monkeypatch):
    from config.settings import Settings

    monkeypatch.setattr(Settings, "CHATS_DIR", str(tmp_path / "chats"), raising=False)

    from api.coach_service import COACH_FIRST_TOKEN_BUDGET_MS
    from api.routers import coach as coach_mod

    req = coach_mod.ChatRequest(message="Привет", provider="mock")
    response = coach_mod.coach_chat(req, Database(str(tmp_path / "c.db")))

    elapsed_ms = asyncio.run(_first_token_elapsed_ms(response))

    assert elapsed_ms < COACH_FIRST_TOKEN_BUDGET_MS
