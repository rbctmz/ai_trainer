"""Explicit test clocks; CLI subprocesses use the real athlete-local date."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from config.settings import Settings
from models import ai_coach_runtime


def actual_runtime_today() -> date:
    return datetime.now(ZoneInfo(Settings.ATHLETE_TIMEZONE)).date()


def freeze_runtime_calendar(monkeypatch, today: date) -> None:
    original = ai_coach_runtime._today_context_line
    monkeypatch.setattr(ai_coach_runtime, "_today_context_line",
                        lambda value=None: original(today if value is None else value))
