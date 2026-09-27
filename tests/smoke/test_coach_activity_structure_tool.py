"""Контракт issue #639: Коуч видит фактическую структуру выполненной активности.

Дефект: интервалы факта считаются только для веб-карточки
(`api/routers/activities.py` → `fetch_activity_intervals`), а в наборе
инструментов Коуча структурных нет вовсе. На вопрос о прошедшей интервальной
сессии Коуч отвечает по агрегатам (TSS, средние) и в вакууме подставляет общие
знания — тот же механизм, что дал «4–5 × 1 мин» в issue #638.

Контракт среза:
* read-only инструмент `get_activity_structure` отдаёт отрезки факта из
  существующего кэша `activity_intervals` (#390/#435) — своей проекции не пишем;
* на горячем пути хода Коуча нет сетевого fetch: инструмент читает кэш и не
  зовёт провайдера (решение владельца среза, зафиксировано в issue #639);
* отсутствие данных честное: нет кэша, нет связи с провайдером или битый
  payload → `structure_status=unavailable` с причиной, а не пустой список
  отрезков, который читается как «отрезков не было»;
* презентер доводит структуру до `formatted_result` — модель видит только его.
"""
from __future__ import annotations

from typing import Any

import pytest

from models.ai_tools import AITools
from models.coach_tool_presenter import format_tool_result


pytestmark = pytest.mark.smoke

_DAY = "2026-09-24"


def _activity(
    activity_id: str,
    *,
    date: str = _DAY,
    sport: str = "bike",
    name: str = "VO2max 4x2",
    duration_minutes: float = 62.0,
    tss: float = 55.0,
) -> dict[str, Any]:
    return {
        "activity_id": activity_id,
        "date": date,
        "sport": sport,
        "activity_name": name,
        "duration_minutes": duration_minutes,
        "distance_km": 32.5,
        "avg_hr": 141,
        "avg_power": 178,
        "tss": tss,
    }


def _provider_cache(intervals: Any = None, **overrides: Any) -> dict[str, Any]:
    """Компактный кэш провайдера в форме normalize_intervals_payload (#435)."""
    payload: dict[str, Any] = {
        "source": "intervals",
        "analyzed": "2026-09-24T18:00:00Z",
        "intervals": [
            {
                "start_index": 0,
                "moving_time": 660,
                "elapsed_time": 660,
                "average_watts": 128,
                "average_heartrate": 118,
                "max_heartrate": 130,
                "average_cadence": 88,
                "zone": 1,
                "training_load": 4,
                "average_speed": 7.4,
                "distance_km": 1.35,
            },
            {
                "start_index": 660,
                "moving_time": 120,
                "elapsed_time": 120,
                "average_watts": 198,
                "average_heartrate": 158,
                "max_heartrate": 166,
                "average_cadence": 94,
                "zone": 4,
                "training_load": 9,
                "average_speed": 10.1,
                "distance_km": 0.34,
            },
        ],
        "groups": [],
        "paired_event_id": 991,
        # Провайдер отдаёт соответствие уже в процентах (веб: Math.round(...)%).
        "compliance": 91.9,
    }
    if intervals is not None:
        payload["intervals"] = intervals
    payload.update(overrides)
    return payload


def _garmin_cache() -> dict[str, Any]:
    return {
        "source": "garmin",
        "analyzed": None,
        "intervals": [
            {
                "start_index": 0,
                "moving_time": 1200,
                "elapsed_time": 1205,
                "average_watts": None,
                "average_heartrate": 132,
                "min_heartrate": 101,
                "max_heartrate": 149,
                "average_cadence": 84,
                "zone": None,
                "training_load": None,
                "average_speed": 2.9,
                "distance_km": 0.97,
                "intensity_type": "interval",
            }
        ],
        "groups": [],
    }


class _StubDB:
    """Минимальный двойник Database: только то, что читает инструмент."""

    def __init__(
        self,
        activities: list[dict[str, Any]] | None = None,
        intervals: dict[str, Any] | None = None,
        links: dict[str, str] | None = None,
    ) -> None:
        self._activities = list(activities or [])
        self._intervals = dict(intervals or {})
        self._links = dict(links or {})

    def get_activity(self, activity_id: str) -> dict[str, Any] | None:
        for row in self._activities:
            if str(row.get("activity_id")) == str(activity_id):
                return dict(row)
        return None

    def get_activities_between(self, start_date: Any, end_date: Any) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self._activities
            if str(start_date) <= str(row.get("date")) <= str(end_date)
        ]

    def get_activity_intervals(self, activity_id: str) -> Any:
        return self._intervals.get(str(activity_id))

    def get_intervals_provider_activity_id(self, activity_id: str) -> str | None:
        return self._links.get(str(activity_id))


def _tools(
    *,
    activities: list[dict[str, Any]] | None = None,
    intervals: dict[str, Any] | None = None,
    links: dict[str, str] | None = None,
) -> AITools:
    return AITools(
        _StubDB(activities=activities, intervals=intervals, links=links)  # type: ignore[arg-type]
    )


def _cached_tools() -> AITools:
    return _tools(
        activities=[_activity("act-bike")],
        intervals={"act-bike": _provider_cache()},
        links={"act-bike": "i991"},
    )


# ---------------------------------------------------------------------------
# Регистрация инструмента
# ---------------------------------------------------------------------------

def test_tool_is_registered_schema_and_prompted() -> None:
    tools = _cached_tools()
    assert "get_activity_structure" in tools.tools

    schema = next(
        item
        for item in tools.get_tool_schemas()
        if item["name"] == "get_activity_structure"
    )
    assert "date" in schema["parameters"]["properties"]
    assert "activity_id" in schema["parameters"]["properties"]

    assert "get_activity_structure" in tools.get_available_tools()

    prompt = tools.format_tool_descriptions_for_ai()
    assert "get_activity_structure, date=2026-09-24" in prompt
    assert "get_activity_structure" in prompt
    assert callable(getattr(AITools, "get_activity_structure"))


def test_tool_has_russian_label() -> None:
    from utils.product_semantics import TOOL_LABELS_RU

    assert TOOL_LABELS_RU.get("get_activity_structure")


# ---------------------------------------------------------------------------
# Чтение кэша
# ---------------------------------------------------------------------------

def test_structure_by_date_reads_cached_provider_intervals() -> None:
    result = _cached_tools().get_activity_structure(date=_DAY)

    assert result["count"] == 1
    activity = result["activities"][0]
    assert activity["activity_id"] == "act-bike"
    assert activity["date"] == _DAY
    assert activity["structure_status"] == "structured"
    assert activity["has_structure"] is True
    assert activity["source"] == "intervals"
    assert activity["interval_count"] == 2
    # Провайдерская мета доезжает до модели: спаривание и compliance.
    assert activity["paired_event_id"] == 991
    assert activity["compliance"] == 91.9

    work = activity["intervals"][1]
    assert work["index"] == 2
    assert work["duration_seconds"] == 120
    assert work["avg_watts"] == 198
    assert work["avg_hr"] == 158
    assert work["max_hr"] == 166
    assert work["avg_cadence"] == 94
    assert work["zone"] == 4
    assert work["distance_km"] == 0.34


def test_structure_by_activity_id() -> None:
    result = _cached_tools().get_activity_structure(activity_id="act-bike")

    assert result["count"] == 1
    assert result["activities"][0]["activity_id"] == "act-bike"


def test_garmin_laps_are_served_with_their_own_source() -> None:
    tools = _tools(
        activities=[_activity("act-run", sport="run")],
        intervals={"act-run": _garmin_cache()},
    )

    activity = tools.get_activity_structure(date=_DAY)["activities"][0]

    assert activity["source"] == "garmin"
    assert activity["interval_count"] == 1
    assert activity["intervals"][0]["avg_hr"] == 132
    assert activity["intervals"][0]["intensity"] == "interval"


def test_multi_activity_day_returns_both_and_filters_by_sport() -> None:
    """Brick-день: на одну дату две активности, Коуч должен уметь выбрать ногу."""
    tools = _tools(
        activities=[
            _activity("act-bike", sport="bike", name="Brick bike"),
            _activity("act-run", sport="run", name="Brick run"),
        ],
        intervals={
            "act-bike": _provider_cache(),
            "act-run": _garmin_cache(),
        },
        links={"act-bike": "i991"},
    )

    everything = tools.get_activity_structure(date=_DAY)
    assert everything["count"] == 2
    assert {item["sport"] for item in everything["activities"]} == {"bike", "run"}

    only_run = tools.get_activity_structure(date=_DAY, sport="run")
    assert only_run["count"] == 1
    assert only_run["activities"][0]["activity_id"] == "act-run"


# ---------------------------------------------------------------------------
# Честное отсутствие данных
# ---------------------------------------------------------------------------

def test_missing_cache_is_unavailable_not_an_empty_list() -> None:
    """Кэша нет → это «недоступно», а не «отрезков не было»."""
    tools = _tools(
        activities=[_activity("act-bike")],
        links={"act-bike": "i991"},
    )

    activity = tools.get_activity_structure(date=_DAY)["activities"][0]

    assert activity["structure_status"] == "unavailable"
    assert activity["has_structure"] is False
    assert activity["reason"] == "not_fetched"
    assert "intervals" not in activity
    assert "недоступна" in activity["message"].lower()


def test_activity_without_provider_link_is_reported_separately() -> None:
    tools = _tools(activities=[_activity("act-garmin-only")])

    activity = tools.get_activity_structure(date=_DAY)["activities"][0]

    assert activity["structure_status"] == "unavailable"
    assert activity["reason"] == "no_provider_link"


def test_corrupt_cache_is_unavailable() -> None:
    """Битый payload не должен читаться как «отрезков нет»."""
    tools = _tools(
        activities=[_activity("act-bike")],
        intervals={"act-bike": {"source": "intervals", "intervals": "broken"}},
        links={"act-bike": "i991"},
    )

    activity = tools.get_activity_structure(date=_DAY)["activities"][0]

    assert activity["structure_status"] == "unavailable"
    assert activity["reason"] == "corrupt_cache"
    assert "intervals" not in activity


def test_non_mapping_cache_row_is_unavailable() -> None:
    tools = _tools(
        activities=[_activity("act-bike")],
        intervals={"act-bike": "not-a-dict"},
        links={"act-bike": "i991"},
    )

    activity = tools.get_activity_structure(date=_DAY)["activities"][0]

    assert activity["structure_status"] == "unavailable"
    assert activity["reason"] == "corrupt_cache"


def test_analyzed_but_empty_structure_is_not_unavailable() -> None:
    """Провайдер проанализировал сессию, отрезков не нашёл — это факт, не сбой."""
    tools = _tools(
        activities=[_activity("act-bike")],
        intervals={"act-bike": _provider_cache(intervals=[])},
        links={"act-bike": "i991"},
    )

    activity = tools.get_activity_structure(date=_DAY)["activities"][0]

    assert activity["structure_status"] == "empty"
    assert activity["has_structure"] is False
    assert activity["interval_count"] == 0
    assert "отрезков" in activity["message"].lower()


def test_unknown_date_is_reported_honestly() -> None:
    result = _cached_tools().get_activity_structure(date="2026-01-01")

    assert result["count"] == 0
    assert result["message"]


def test_missing_arguments_ask_for_one() -> None:
    result = _cached_tools().get_activity_structure()

    assert result["success"] is False
    assert "date" in result["error"]


# ---------------------------------------------------------------------------
# Стоимость: на горячем пути хода нет сети
# ---------------------------------------------------------------------------

def test_coach_path_never_calls_the_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC4 issue #639: инструмент не делает сетевой fetch провайдера."""
    import services.activity_intervals as activity_intervals
    import services.intervals_icu as intervals_icu

    calls: list[Any] = []

    def _refuse(*args: Any, **kwargs: Any) -> Any:
        calls.append((args, kwargs))
        raise AssertionError("инструмент Коуча не должен ходить к провайдеру")

    monkeypatch.setattr(activity_intervals, "fetch_activity_intervals", _refuse)
    monkeypatch.setattr(activity_intervals, "fetch_stream_structure", _refuse)
    monkeypatch.setattr(intervals_icu, "get_client", _refuse)

    tools = _cached_tools()
    cached = tools.get_activity_structure(date=_DAY)
    missing = _tools(
        activities=[_activity("act-bike")], links={"act-bike": "i991"}
    ).get_activity_structure(date=_DAY)

    assert cached["activities"][0]["has_structure"] is True
    assert missing["activities"][0]["structure_status"] == "unavailable"
    assert calls == []


def test_cache_source_helper_is_network_free() -> None:
    from services.activity_intervals import cached_intervals_source

    assert cached_intervals_source(_provider_cache(), "i991") == "intervals"
    assert cached_intervals_source(_garmin_cache(), None) == "garmin"
    # Legacy-строка без маркера, но нормализованной формы и со связью провайдера.
    legacy = {"intervals": [], "groups": []}
    # Legacy-строка провайдера до #435: маркера нет, но форма провайдерская.
    legacy_provider = {"analyzed": "2026-08-04T14:59:54Z", "intervals": [], "groups": []}
    assert cached_intervals_source(legacy_provider, None) == "intervals"
    assert cached_intervals_source(legacy, "i991") == "intervals"
    assert cached_intervals_source(legacy, None) == "garmin"
    assert cached_intervals_source({"intervals": "broken"}, None) is None
    assert cached_intervals_source(None, "i991") is None


# ---------------------------------------------------------------------------
# Презентер: модель видит только formatted_result
# ---------------------------------------------------------------------------

def test_presenter_renders_intervals_table() -> None:
    result = _cached_tools().get_activity_structure(date=_DAY)

    text = format_tool_result("get_activity_structure", result)

    assert "Структура выполненной активности" in text
    assert "198" in text          # мощность рабочего отрезка
    assert "2:00" in text         # длительность 120 с
    assert "340 м" in text        # дистанция отрезка < 1 км — как в вебе
    assert "1.4 км" in text       # разминочный отрезок >= 1 км
    # compliance провайдер отдаёт в процентах; веб печатает Math.round(...)%
    assert "соответствие плану 92%" in text
    assert "9190" not in text
    assert "спарено с плановой сессией" in text


def test_presenter_reports_unavailable_honestly() -> None:
    result = _tools(
        activities=[_activity("act-bike")], links={"act-bike": "i991"}
    ).get_activity_structure(date=_DAY)

    text = format_tool_result("get_activity_structure", result)

    assert "недоступна" in text.lower()
    assert "0 отрезков" not in text


def test_presenter_omits_columns_that_are_absent() -> None:
    """У беговой ноги без мощности не должно быть пустой колонки «Мощность»."""
    tools = _tools(
        activities=[_activity("act-run", sport="run")],
        intervals={"act-run": _garmin_cache()},
    )
    result = tools.get_activity_structure(date=_DAY)

    text = format_tool_result("get_activity_structure", result)

    header = next(line for line in text.splitlines() if line.startswith("| #"))
    assert "Мощность" not in header
    assert "ЧСС" in header


def test_execute_tool_wraps_the_result() -> None:
    outcome = _cached_tools().execute_tool("get_activity_structure", date=_DAY)

    assert outcome["success"] is True
    assert outcome["result"]["count"] == 1
